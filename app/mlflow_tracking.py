"""Optional MLflow integration for ShopSense's existing ML workflows."""
from __future__ import annotations

import importlib
import json
import math
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = {
    "inventory": "shopsense-inventory-demand-forecasting",
    "segmentation": "shopsense-customer-segmentation",
    "recommendations": "shopsense-recommendation-evaluation",
}
_SENSITIVE_KEY = re.compile(
    r"password|secret|token|credential|artifact|(?:^|_)path(?:_|$)|uri|directory|filename|file_",
    re.IGNORECASE,
)
_SAFE_TAGS = {
    "workflow.status",
    "workflow.started_at",
    "workflow.completed_at",
    "evaluation.status",
    "evaluation.method",
    "evaluation.message",
    "model.name",
    "model.type",
    "model.registry.status",
    "model.registry.version",
    "workflow.trigger",
    "workflow.job_id",
    "mlflow.runName",
}
_WORKFLOW_CONTEXT = ContextVar("shopsense_mlflow_workflow_context", default=None)


@contextmanager
def workflow_tracking_context(trigger, job_id):
    """Attach scheduler/manual provenance to MLflow runs in this execution."""
    token = _WORKFLOW_CONTEXT.set({"trigger": trigger, "job_id": job_id})
    try:
        yield
    finally:
        _WORKFLOW_CONTEXT.reset(token)


def _tracking_uri():
    configured = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if not configured:
        return (PROJECT_ROOT / "mlruns").resolve().as_uri()
    if re.match(r"^[A-Za-z]:[\\/]", configured):
        return Path(configured).resolve().as_uri()
    if not urlparse(configured).scheme:
        return Path(configured).expanduser().resolve().as_uri()
    return configured


def _load_mlflow():
    enabled = os.getenv("MLFLOW_TRACKING_ENABLED", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return None, "MLflow tracking is disabled by configuration."
    try:
        tracking_uri = _tracking_uri()
        # MLflow versions that move the filesystem store into maintenance mode
        # require an explicit opt-in. File storage remains the documented
        # local development default for ShopSense.
        if urlparse(tracking_uri).scheme.lower() == "file":
            os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        mlflow = importlib.import_module("mlflow")
        mlflow.set_tracking_uri(tracking_uri)
        registry_uri = os.getenv("MLFLOW_REGISTRY_URI", "").strip()
        if registry_uri:
            mlflow.set_registry_uri(registry_uri)
        return mlflow, None
    except Exception:
        return None, "MLflow is unavailable. Install the declared dependency and verify its configuration."


def _clean_params(params):
    clean = {}
    for key, value in (params or {}).items():
        key = str(key)
        if _SENSITIVE_KEY.search(key) or value is None:
            continue
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, sort_keys=True, default=str)
        clean[key[:250]] = str(value)[:500]
    return clean


def _clean_metrics(metrics):
    clean = {}
    for key, value in (metrics or {}).items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            clean[str(key)[:250]] = number
    return clean


def _registry_available(mlflow):
    """Probe registry support without disclosing backend URIs or errors."""
    registry_uri = os.getenv("MLFLOW_REGISTRY_URI", "").strip()
    selected_uri = registry_uri or _tracking_uri()
    if urlparse(selected_uri).scheme.lower() == "file":
        return False
    try:
        mlflow.tracking.MlflowClient(registry_uri=registry_uri or None).search_registered_models(
            max_results=1
        )
        return True
    except Exception:
        return False


def tracking_status():
    mlflow, message = _load_mlflow()
    enabled = os.getenv("MLFLOW_TRACKING_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off"
    }
    if mlflow is None:
        return {
            "enabled": enabled,
            "available": False,
            "registry_supported": False,
            "message": message,
        }
    try:
        mlflow.tracking.MlflowClient().search_experiments(max_results=1)
        registry_supported = _registry_available(mlflow)
        return {
            "enabled": True,
            "available": True,
            "registry_supported": registry_supported,
            "message": None if registry_supported else (
                "Tracking is available. The configured backend does not support the Model Registry."
            ),
        }
    except Exception:
        return {
            "enabled": True,
            "available": False,
            "registry_supported": False,
            "message": "MLflow tracking storage could not be reached. Check its local configuration.",
        }


def log_workflow_run(
    experiment_key,
    run_name,
    *,
    params=None,
    metrics=None,
    workflow_status="completed",
    evaluation_status="available",
    evaluation_message=None,
    evaluation_method=None,
    artifact=None,
    sklearn_model=None,
    model_name=None,
    model_type=None,
):
    """Persist a completed workflow without making MLflow a runtime dependency."""
    mlflow, message = _load_mlflow()
    experiment_name = EXPERIMENTS[experiment_key]
    if mlflow is None:
        return {
            "available": False,
            "status": "unavailable",
            "experiment_name": experiment_name,
            "run_id": None,
            "message": message,
        }

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        experiment = mlflow.set_experiment(experiment_name)
        with mlflow.start_run(
            experiment_id=experiment.experiment_id,
            run_name=run_name,
            description=f"ShopSense {experiment_name} workflow run",
        ) as active_run:
            run_id = active_run.info.run_id
            tags = {
                "workflow.status": workflow_status,
                "workflow.started_at": started_at,
                "evaluation.status": evaluation_status,
                "model.type": model_type or "not_specified",
            }
            workflow_context = _WORKFLOW_CONTEXT.get()
            if workflow_context:
                tags["workflow.trigger"] = workflow_context["trigger"]
                tags["workflow.job_id"] = workflow_context["job_id"]
            if evaluation_method:
                tags["evaluation.method"] = str(evaluation_method)
            if evaluation_message:
                tags["evaluation.message"] = str(evaluation_message)[:500]
            if model_name:
                tags["model.name"] = model_name
            mlflow.set_tags(tags)
            clean_params = _clean_params(params)
            if clean_params:
                mlflow.log_params(clean_params)
            clean_metrics = _clean_metrics(metrics)
            if clean_metrics:
                mlflow.log_metrics(clean_metrics)
            if artifact is not None:
                mlflow.log_dict(artifact, "shopsense_result.json")

            registry_result = {
                "status": "not_applicable" if sklearn_model is None else "not_attempted",
                "version": None,
            }
            if sklearn_model is not None:
                try:
                    mlflow_sklearn = importlib.import_module("mlflow.sklearn")
                    model_info = mlflow_sklearn.log_model(sklearn_model, name="model")
                    if _registry_available(mlflow):
                        registered = mlflow.register_model(model_info.model_uri, model_name)
                        registry_result = {
                            "status": "registered",
                            "version": str(registered.version),
                        }
                    else:
                        registry_result = {"status": "unsupported", "version": None}
                except Exception:
                    registry_result = {"status": "failed", "version": None}
            mlflow.set_tag("model.registry.status", registry_result["status"])
            if registry_result["version"] is not None:
                mlflow.set_tag("model.registry.version", registry_result["version"])
            mlflow.set_tag(
                "workflow.completed_at", datetime.now(timezone.utc).isoformat()
            )

        return {
            "available": True,
            "status": "logged",
            "experiment_name": experiment_name,
            "run_id": run_id,
            "model_registry": registry_result,
            "message": None,
        }
    except Exception:
        return {
            "available": False,
            "status": "unavailable",
            "experiment_name": experiment_name,
            "run_id": None,
            "message": "MLflow could not record this run; the existing workflow completed.",
        }


def _safe_run(run, experiment_name):
    info = run.info
    return {
        "run_id": info.run_id,
        "experiment_name": experiment_name,
        "status": info.status,
        "start_time": info.start_time,
        "end_time": info.end_time,
        "run_name": run.data.tags.get("mlflow.runName"),
        "params": {
            key: value for key, value in run.data.params.items()
            if not _SENSITIVE_KEY.search(key)
        },
        "metrics": dict(run.data.metrics),
        "tags": {
            key: value for key, value in run.data.tags.items()
            if key in _SAFE_TAGS
        },
    }


def list_experiments():
    mlflow, message = _load_mlflow()
    if mlflow is None:
        return {"available": False, "experiments": [], "message": message}
    try:
        allowed_names = set(EXPERIMENTS.values())
        experiments = [
            {
                "experiment_id": exp.experiment_id,
                "name": exp.name,
                "lifecycle_stage": exp.lifecycle_stage,
                "creation_time": exp.creation_time,
                "last_update_time": exp.last_update_time,
            }
            for exp in mlflow.tracking.MlflowClient().search_experiments()
            if exp.name in allowed_names
        ]
        experiments.sort(key=lambda item: item["name"])
        return {"available": True, "experiments": experiments, "message": None}
    except Exception:
        return {"available": False, "experiments": [], "message": "MLflow experiments could not be retrieved."}


def list_experiment_runs(experiment_id, limit=25):
    mlflow, message = _load_mlflow()
    if mlflow is None:
        return {"available": False, "runs": [], "message": message}
    try:
        client = mlflow.tracking.MlflowClient()
        experiment = client.get_experiment(experiment_id)
        if experiment is None or experiment.name not in set(EXPERIMENTS.values()):
            return {"available": True, "runs": [], "message": None}
        runs = client.search_runs(
            [experiment_id], order_by=["attributes.start_time DESC"], max_results=limit
        )
        return {
            "available": True,
            "runs": [_safe_run(run, experiment.name) for run in runs],
            "message": None,
        }
    except Exception:
        return {"available": False, "runs": [], "message": "MLflow runs could not be retrieved."}


def get_experiment_run(run_id):
    mlflow, message = _load_mlflow()
    if mlflow is None:
        return {"available": False, "run": None, "message": message}
    try:
        client = mlflow.tracking.MlflowClient()
        run = client.get_run(run_id)
        experiment = client.get_experiment(run.info.experiment_id)
        if experiment is None or experiment.name not in set(EXPERIMENTS.values()):
            return {"available": True, "run": None, "message": None}
        return {"available": True, "run": _safe_run(run, experiment.name), "message": None}
    except Exception:
        return {"available": False, "run": None, "message": "MLflow run could not be retrieved."}


def get_latest_run_artifact(experiment_key):
    """Read the newest safe ShopSense result artifact without exposing its path."""
    experiment_name = EXPERIMENTS.get(experiment_key)
    if experiment_name is None:
        return {"available": False, "run": None, "artifact": None, "message": "Unknown ShopSense experiment."}
    mlflow, message = _load_mlflow()
    if mlflow is None:
        return {"available": False, "run": None, "artifact": None, "message": message}
    try:
        client = mlflow.tracking.MlflowClient()
        experiment = next(
            (item for item in client.search_experiments() if item.name == experiment_name),
            None,
        )
        if experiment is None:
            return {"available": True, "run": None, "artifact": None, "message": None}
        runs = client.search_runs(
            [experiment.experiment_id],
            order_by=["attributes.start_time DESC"],
            max_results=20,
        )
        for run in runs:
            try:
                artifact_path = client.download_artifacts(
                    run.info.run_id, "shopsense_result.json"
                )
                with open(artifact_path, "r", encoding="utf-8") as artifact_file:
                    artifact = json.load(artifact_file)
                return {
                    "available": True,
                    "run": _safe_run(run, experiment_name),
                    "artifact": artifact,
                    "message": None,
                }
            except Exception:
                continue
        return {"available": True, "run": None, "artifact": None, "message": None}
    except Exception:
        return {
            "available": False,
            "run": None,
            "artifact": None,
            "message": "The latest ShopSense workflow artifact could not be retrieved.",
        }


def list_registered_models():
    status = tracking_status()
    if not status["available"] or not status["registry_supported"]:
        return {
            "available": status["available"],
            "registry_supported": False,
            "models": [],
            "message": status["message"] or "The configured backend does not support the Model Registry.",
        }
    mlflow, _ = _load_mlflow()
    try:
        client = mlflow.tracking.MlflowClient(
            registry_uri=os.getenv("MLFLOW_REGISTRY_URI") or None
        )
        models = []
        for model in client.search_registered_models(max_results=100):
            if model.name != "shopsense-customer-segmentation":
                continue
            models.append({
                "name": model.name,
                "description": model.description,
                "versions": [{
                    "version": version.version,
                    "run_id": version.run_id,
                    "status": version.status,
                    "creation_timestamp": version.creation_timestamp,
                    "current_stage": version.current_stage,
                } for version in model.latest_versions],
            })
        return {"available": True, "registry_supported": True, "models": models, "message": None}
    except Exception:
        return {
            "available": True,
            "registry_supported": False,
            "models": [],
            "message": "The configured MLflow backend does not support registry operations.",
        }
