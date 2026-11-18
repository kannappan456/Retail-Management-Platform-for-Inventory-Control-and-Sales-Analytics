"""Isolated scheduler, execution-history, and tracking-context tests."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.mlflow_tracking import get_experiment_run, log_workflow_run
from app.models import inventory, product, transaction, user, vendor  # noqa: F401
from app.workflow_scheduler import JobAlreadyRunning, WorkflowJob, WorkflowManager


class SessionStub:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class TestWorkflowManager(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(
            prefix="shopsense-workflows-", ignore_cleanup_errors=True
        )
        self.old_environment = {
            key: os.environ.get(key)
            for key in (
                "MLFLOW_TRACKING_ENABLED",
                "MLFLOW_TRACKING_URI",
                "MLFLOW_REGISTRY_URI",
                "MLFLOW_ALLOW_FILE_STORE",
            )
        }
        os.environ["MLFLOW_TRACKING_ENABLED"] = "true"
        os.environ["MLFLOW_TRACKING_URI"] = (Path(self.tempdir.name) / "mlruns").as_uri()
        os.environ.pop("MLFLOW_REGISTRY_URI", None)
        os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
        self.sessions = []

    def tearDown(self):
        if hasattr(self, "manager"):
            self.manager.shutdown()
        for key, value in self.old_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tempdir.cleanup()

    def make_manager(self, handlers):
        jobs = [
            WorkflowJob(
                job_id=job_id,
                name=job_id.replace("_", " ").title(),
                description=f"Test handler for {job_id}.",
                interval_hours=24,
                minimum_interval_hours=6,
                handler=handler,
            )
            for job_id, handler in handlers.items()
        ]

        def session_factory():
            session = SessionStub()
            self.sessions.append(session)
            return session

        self.manager = WorkflowManager(session_factory=session_factory, jobs=jobs)
        return self.manager

    def test_scheduler_registers_jobs_once_and_shuts_down(self):
        manager = WorkflowManager(session_factory=SessionStub)
        self.manager = manager
        first = manager.start()
        second = manager.start()
        self.assertEqual(first["status"], "running")
        self.assertEqual(second["status"], "running")
        self.assertEqual(len(manager._scheduler.get_jobs()), 3)
        self.assertIsNotNone(manager.get_job("inventory_demand_forecast")["next_execution_time"])
        manager.shutdown()
        self.assertEqual(manager.scheduler_status()["status"], "stopped")

    def test_execution_history_closes_database_session_and_records_success(self):
        manager = self.make_manager({"example": lambda db: {"total_products": 3}})
        record = manager.run_job("example", trigger="scheduled")
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["trigger"], "scheduled")
        self.assertEqual(record["result_summary"], "Workflow completed.")
        self.assertIsNotNone(record["completed_at"])
        self.assertGreaterEqual(record["duration_seconds"], 0)
        self.assertTrue(self.sessions[0].closed)
        self.assertEqual(manager.history()[0]["job_id"], "example")

    def test_failure_is_recorded_and_does_not_block_another_job(self):
        def fail(_db):
            raise RuntimeError("private database detail")

        manager = self.make_manager({
            "failing": fail,
            "healthy": lambda _db: {"message": "Completed using current data."},
        })
        failed = manager.run_job("failing")
        succeeded = manager.run_job("healthy")
        self.assertEqual(failed["status"], "failed")
        self.assertNotIn("private database detail", failed["error"])
        self.assertEqual(succeeded["status"], "success")
        self.assertEqual(succeeded["result_summary"], "Completed using current data.")

    def test_overlapping_runs_are_rejected(self):
        started = threading.Event()
        release = threading.Event()

        def blocking(_db):
            started.set()
            release.wait(timeout=5)
            return {"ok": True}

        manager = self.make_manager({"blocking": blocking})
        worker = threading.Thread(target=manager.run_job, args=("blocking", "scheduled"))
        worker.start()
        self.assertTrue(started.wait(timeout=2))
        self.assertIsNone(manager.run_job("blocking", trigger="scheduled"))
        with self.assertRaises(JobAlreadyRunning):
            manager.run_job("blocking", trigger="manual")
        release.set()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(manager.history()), 1)

    def test_manual_trigger_pause_and_resume(self):
        finished = threading.Event()

        def handler(_db):
            finished.set()
            return {"message": "Manual run completed."}

        manager = self.make_manager({"manual_job": handler})
        manager.start()
        queued = manager.trigger_manual("manual_job")
        self.assertIn(queued["status"], {"queued", "running", "success"})
        self.assertTrue(finished.wait(timeout=3))
        for _ in range(50):
            if manager.history():
                break
            threading.Event().wait(0.02)
        self.assertEqual(manager.history()[0]["trigger"], "manual")
        self.assertEqual(manager.pause_job("manual_job")["status"], "paused")
        resumed = manager.resume_job("manual_job")
        self.assertNotEqual(resumed["status"], "paused")
        self.assertIsNotNone(resumed["next_execution_time"])

    def test_resumed_job_without_prior_execution_has_scheduled_status(self):
        manager = self.make_manager({"fresh_job": lambda _db: {"ok": True}})
        manager.start()
        self.assertEqual(manager.pause_job("fresh_job")["status"], "paused")
        resumed = manager.resume_job("fresh_job")
        self.assertEqual(resumed["status"], "scheduled")
        self.assertIsNotNone(resumed["next_execution_time"])

    def test_mlflow_run_records_scheduled_trigger(self):
        def tracked(_db):
            validation_error = 2.0 - 3.0
            holdout_mae = abs(validation_error)
            return log_workflow_run(
                "inventory",
                "scheduled-inventory-test",
                params={"forecast_horizon_days": 7},
                metrics={"holdout_mae_units": holdout_mae},
                artifact={"test_run": True},
                model_type="historical_average_heuristic",
            )

        manager = self.make_manager({"inventory_demand_forecast": tracked})
        history = manager.run_job("inventory_demand_forecast", trigger="scheduled")
        self.assertEqual(history["status"], "success")
        # Retrieve the one run from the isolated ShopSense inventory experiment.
        from app.mlflow_tracking import list_experiments, list_experiment_runs
        experiments = list_experiments()["experiments"]
        experiment = next(item for item in experiments if item["name"] == "shopsense-inventory-demand-forecasting")
        run = list_experiment_runs(experiment["experiment_id"])["runs"][0]
        self.assertEqual(run["tags"]["workflow.trigger"], "scheduled")
        self.assertEqual(run["tags"]["workflow.job_id"], "inventory_demand_forecast")
        self.assertEqual(run["metrics"]["holdout_mae_units"], 1.0)
        self.assertIsNotNone(get_experiment_run(run["run_id"])["run"])

    def test_recommendation_insufficient_data_regression_is_tracked_without_metrics(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            manager = WorkflowManager(session_factory=lambda: db)
            execution = manager.run_job("recommendation_evaluation", trigger="scheduled")
            self.assertEqual(execution["status"], "success")
            self.assertIn("No purchase interactions", execution["result_summary"])
            from app.mlflow_tracking import list_experiments, list_experiment_runs
            experiment = next(
                item for item in list_experiments()["experiments"]
                if item["name"] == "shopsense-recommendation-evaluation"
            )
            run = list_experiment_runs(experiment["experiment_id"])["runs"][0]
            self.assertEqual(run["tags"]["evaluation.status"], "insufficient_data")
            self.assertEqual(run["tags"]["workflow.trigger"], "scheduled")
            self.assertEqual(run["metrics"], {})
        finally:
            if "manager" in locals():
                manager.shutdown()
            db.close()
            Base.metadata.drop_all(engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
