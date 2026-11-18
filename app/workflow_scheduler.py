"""In-process APScheduler integration for existing ShopSense workflows."""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import SessionLocal
from app.inventory.inventory_forecasting import forecast_demand
from app.customer.segmentation import customer_segments
from app.recommendation.recommendation import evaluate_recommendations
from app.mlflow_tracking import workflow_tracking_context


logger = logging.getLogger(__name__)
HISTORY_LIMIT = 200


@dataclass(frozen=True)
class WorkflowJob:
    job_id: str
    name: str
    description: str
    interval_hours: int
    minimum_interval_hours: int
    handler: Callable

    @property
    def schedule(self):
        return f"Every {self.interval_hours} hour(s)"


def _environment_hours(variable: str, default: int, minimum: int) -> int:
    try:
        value = int(os.getenv(variable, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; using default %s hours", variable, default)
        return default
    if value < minimum:
        logger.warning("%s is below the safe minimum; using %s hours", variable, minimum)
        return minimum
    if value > 8760:
        logger.warning("%s exceeds one year; clamping to 8760 hours", variable)
        return 8760
    return value


def _recommendation_k() -> int:
    try:
        value = int(os.getenv("WORKFLOW_RECOMMENDATION_K", "5"))
    except (TypeError, ValueError):
        logger.warning("Invalid WORKFLOW_RECOMMENDATION_K; using 5")
        return 5
    if not 1 <= value <= 20:
        logger.warning("WORKFLOW_RECOMMENDATION_K must be 1..20; clamping to that range")
        return max(1, min(value, 20))
    return value


def _forecast(db):
    return forecast_demand(admin=None, db=db)


def _segment(db):
    return customer_segments(admin=None, db=db)


def _evaluate_recommendations(db):
    k = _recommendation_k()
    return evaluate_recommendations(k=k, admin=None, db=db)


def _job_definitions():
    return (
        WorkflowJob(
            job_id="inventory_demand_forecast",
            name="Inventory demand forecasting",
            description="Runs the existing historical-average demand forecast and validation.",
            interval_hours=_environment_hours("WORKFLOW_FORECAST_INTERVAL_HOURS", 24, 6),
            minimum_interval_hours=6,
            handler=_forecast,
        ),
        WorkflowJob(
            job_id="customer_segmentation",
            name="Customer segmentation",
            description="Runs the existing K-Means segmentation and silhouette evaluation.",
            interval_hours=_environment_hours("WORKFLOW_SEGMENTATION_INTERVAL_HOURS", 168, 24),
            minimum_interval_hours=24,
            handler=_segment,
        ),
        WorkflowJob(
            job_id="recommendation_evaluation",
            name="Recommendation evaluation",
            description="Runs the existing leave-one-out cosine-similarity evaluation.",
            interval_hours=_environment_hours("WORKFLOW_RECOMMENDATION_INTERVAL_HOURS", 24, 12),
            minimum_interval_hours=12,
            handler=_evaluate_recommendations,
        ),
    )


class JobAlreadyRunning(Exception):
    """Raised when a manual run would overlap another run of the same job."""


class WorkflowManager:
    """Owns one process-local scheduler and bounded, non-persistent history."""

    def __init__(self, session_factory=SessionLocal, jobs=None, history_limit=HISTORY_LIMIT):
        self.session_factory = session_factory
        self.jobs = {job.job_id: job for job in (jobs or _job_definitions())}
        self.timezone_name = os.getenv("WORKFLOW_TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"
        self._configuration_error = None
        try:
            timezone = ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            self._configuration_error = "Invalid WORKFLOW_TIMEZONE; using Asia/Kolkata."
            logger.warning("Invalid workflow scheduler timezone %r", self.timezone_name)
            self.timezone_name = "Asia/Kolkata"
            timezone = ZoneInfo(self.timezone_name)

        self.enabled = os.getenv("WORKFLOW_SCHEDULER_ENABLED", "true").strip().lower() not in {
            "0", "false", "no", "off"
        }
        self._scheduler = BackgroundScheduler(
            timezone=timezone,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            },
        )
        self._history = deque(maxlen=history_limit)
        self._state = {job_id: {} for job_id in self.jobs}
        self._job_locks = {job_id: threading.Lock() for job_id in self.jobs}
        self._manager_lock = threading.RLock()
        self._manual_executor = ThreadPoolExecutor(
            max_workers=max(1, min(4, len(self.jobs))),
            thread_name_prefix="shopsense-workflow",
        )
        self._registered = False
        self._shutdown = False
        self._last_error = None

    def start(self):
        """Register jobs once and start scheduling when enabled."""
        with self._manager_lock:
            if self._shutdown:
                return self.scheduler_status()
            try:
                if not self._registered:
                    for job in self.jobs.values():
                        self._scheduler.add_job(
                            self._scheduled_run,
                            trigger=IntervalTrigger(
                                hours=job.interval_hours,
                                timezone=self._scheduler.timezone,
                            ),
                            id=job.job_id,
                            name=job.name,
                            args=[job.job_id],
                            replace_existing=True,
                            coalesce=True,
                            max_instances=1,
                            misfire_grace_time=3600,
                        )
                    self._registered = True
                if self.enabled and not self._scheduler.running:
                    self._scheduler.start()
                self._last_error = None
            except Exception:
                self._last_error = "The scheduler could not start. Check application logs."
                logger.exception("ShopSense workflow scheduler failed to start")
            return self.scheduler_status()

    def shutdown(self):
        """Stop APScheduler and finish queued manual runs cleanly."""
        with self._manager_lock:
            if self._shutdown:
                return
            self._shutdown = True
            scheduler_running = self._scheduler.running
        try:
            if scheduler_running:
                self._scheduler.shutdown(wait=True)
        finally:
            self._manual_executor.shutdown(wait=True, cancel_futures=False)

    def scheduler_status(self):
        running = self._scheduler.running
        if self._shutdown:
            state = "stopped"
        elif self._last_error:
            state = "error"
        elif not self.enabled:
            state = "disabled"
        elif running:
            state = "running"
        else:
            state = "stopped"
        return {
            "status": state,
            "running": running,
            "enabled": self.enabled,
            "timezone": self.timezone_name,
            "job_count": len(self.jobs),
            "history_limit": self._history.maxlen,
            "message": self._last_error or self._configuration_error,
        }

    def list_jobs(self):
        with self._manager_lock:
            return [self._job_snapshot(job_id) for job_id in self.jobs]

    def get_job(self, job_id):
        with self._manager_lock:
            if job_id not in self.jobs:
                return None
            return self._job_snapshot(job_id)

    def _job_snapshot(self, job_id):
        definition = self.jobs[job_id]
        state = dict(self._state[job_id])
        scheduled_job = self._scheduler.get_job(job_id)
        paused = bool(state.get("paused"))
        running = self._job_locks[job_id].locked() and state.get("status") == "running"
        if running:
            status = "running"
        elif state.get("status") == "queued":
            status = "queued"
        elif paused:
            status = "paused"
        elif self._last_error:
            status = "scheduler_error"
        elif not self._scheduler.running:
            status = "stopped" if self.enabled else "disabled"
        else:
            status = state.get("last_execution_status") or "scheduled"
        next_run = getattr(scheduled_job, "next_run_time", None) if scheduled_job else None
        if paused or not self._scheduler.running:
            next_run = None
        return {
            "job_id": job_id,
            "name": definition.name,
            "description": definition.description,
            "schedule": definition.schedule,
            "interval_hours": definition.interval_hours,
            "minimum_interval_hours": definition.minimum_interval_hours,
            "status": status,
            "is_running": running,
            "last_execution_status": state.get("last_execution_status"),
            "last_execution_time": state.get("completed_at"),
            "last_started_at": state.get("started_at"),
            "next_execution_time": next_run.isoformat() if next_run else None,
            "last_result_summary": state.get("result_summary"),
            "last_error": state.get("error"),
        }

    def history(self, limit=50):
        limit = max(1, min(int(limit), self._history.maxlen))
        with self._manager_lock:
            return [dict(item) for item in reversed(list(self._history)[-limit:])]

    def _scheduled_run(self, job_id):
        return self.run_job(job_id, trigger="scheduled")

    def run_job(self, job_id, trigger="manual"):
        """Run synchronously, mainly for scheduler execution and testability."""
        if job_id not in self.jobs:
            raise KeyError(job_id)
        lock = self._job_locks[job_id]
        if not lock.acquire(blocking=False):
            if trigger == "manual":
                raise JobAlreadyRunning(job_id)
            logger.info("Skipping overlapping scheduled workflow %s", job_id)
            return None
        return self._execute_locked(job_id, trigger)

    def trigger_manual(self, job_id):
        """Queue a manual run without holding the HTTP request open."""
        if job_id not in self.jobs:
            raise KeyError(job_id)
        lock = self._job_locks[job_id]
        if not lock.acquire(blocking=False):
            raise JobAlreadyRunning(job_id)
        with self._manager_lock:
            self._state[job_id]["status"] = "queued"
        try:
            self._manual_executor.submit(self._execute_locked, job_id, "manual")
        except Exception:
            lock.release()
            with self._manager_lock:
                self._state[job_id]["status"] = "failed"
                self._state[job_id]["error"] = "Manual execution could not be queued."
            raise
        return self.get_job(job_id)

    def pause_job(self, job_id):
        if job_id not in self.jobs:
            raise KeyError(job_id)
        with self._manager_lock:
            if self._scheduler.running:
                self._scheduler.pause_job(job_id)
            self._state[job_id]["paused"] = True
            if not self._job_locks[job_id].locked():
                self._state[job_id]["status"] = "paused"
            return self._job_snapshot(job_id)

    def resume_job(self, job_id):
        if job_id not in self.jobs:
            raise KeyError(job_id)
        with self._manager_lock:
            if self._scheduler.running:
                self._scheduler.resume_job(job_id)
            self._state[job_id]["paused"] = False
            if not self._job_locks[job_id].locked():
                self._state[job_id]["status"] = "scheduled" if self._scheduler.running else "stopped"
            return self._job_snapshot(job_id)

    def _execute_locked(self, job_id, trigger):
        definition = self.jobs[job_id]
        started = datetime.now(ZoneInfo(self.timezone_name))
        started_monotonic = time.monotonic()
        record = {
            "execution_id": f"{job_id}-{started.timestamp():.6f}",
            "job_id": job_id,
            "job_name": definition.name,
            "trigger": trigger,
            "started_at": started.isoformat(),
            "completed_at": None,
            "duration_seconds": None,
            "status": "running",
            "result_summary": None,
            "error": None,
        }
        with self._manager_lock:
            self._state[job_id].update({"status": "running", "started_at": record["started_at"]})
            self._history.append(record)
        logger.info("Workflow %s started (%s)", job_id, trigger)

        db = None
        try:
            db = self.session_factory()
            with workflow_tracking_context(trigger=trigger, job_id=job_id):
                result = definition.handler(db)
            record["result_summary"] = _result_summary(job_id, result)
            record["status"] = "success"
        except Exception:
            record["status"] = "failed"
            record["error"] = "Job execution failed. Check application logs for details."
            logger.exception("Workflow %s failed (%s)", job_id, trigger)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    logger.exception("Could not close database session for workflow %s", job_id)
                    if record["status"] == "success":
                        record["status"] = "failed"
                        record["error"] = "Job finished but its database session did not close cleanly."
            record["completed_at"] = datetime.now(ZoneInfo(self.timezone_name)).isoformat()
            record["duration_seconds"] = round(time.monotonic() - started_monotonic, 3)
            with self._manager_lock:
                self._state[job_id].update({
                    "status": "paused" if self._state[job_id].get("paused") else record["status"],
                    "last_execution_status": record["status"],
                    "started_at": record["started_at"],
                    "completed_at": record["completed_at"],
                    "result_summary": record["result_summary"],
                    "error": record["error"],
                })
            logger.info(
                "Workflow %s completed with status=%s duration_seconds=%s",
                job_id, record["status"], record["duration_seconds"],
            )
            self._job_locks[job_id].release()
        return dict(record)


def _result_summary(job_id, result):
    if not isinstance(result, dict):
        return "Workflow completed."
    message = result.get("message")
    if message:
        return str(message)[:300]
    if job_id == "inventory_demand_forecast":
        return f"Generated forecasts for {int(result.get('total_products', 0))} products."
    if job_id == "customer_segmentation":
        if result.get("optimal_clusters") is not None:
            return (
                f"Produced {int(result['optimal_clusters'])} clusters from "
                f"{int(result.get('customers_available', 0))} customers."
            )
        return "No valid segmentation result was returned."
    if job_id == "recommendation_evaluation":
        metrics = result.get("metrics")
        if metrics is None:
            return "Evaluation completed without metrics because data was insufficient."
        return (
            f"Evaluated {int(result.get('evaluated_customers', 0))} customers "
            f"at K={int(result.get('k', 5))}; actual metrics were returned."
        )
    return "Workflow completed."


workflow_manager = WorkflowManager()
