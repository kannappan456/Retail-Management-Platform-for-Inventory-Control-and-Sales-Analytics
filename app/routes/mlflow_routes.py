"""Admin-only read APIs for ShopSense MLflow experiments and model versions."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.user import User
from app.security import require_admin
from app.mlflow_tracking import (
    get_experiment_run,
    list_experiment_runs,
    list_experiments,
    list_registered_models,
    tracking_status,
)


router = APIRouter(prefix="/mlflow", tags=["MLflow Tracking"])


@router.get("/status")
def mlflow_status(admin: User = Depends(require_admin)):
    return tracking_status()


@router.get("/experiments")
def experiments(admin: User = Depends(require_admin)):
    return list_experiments()


@router.get("/experiments/{experiment_id}/runs")
def experiment_runs(
    experiment_id: str,
    limit: int = Query(25, ge=1, le=100),
    admin: User = Depends(require_admin),
):
    return list_experiment_runs(experiment_id, limit)


@router.get("/runs/{run_id}")
def experiment_run(run_id: str, admin: User = Depends(require_admin)):
    result = get_experiment_run(run_id)
    if result["available"] and result["run"] is None:
        raise HTTPException(status_code=404, detail="ShopSense MLflow run was not found.")
    return result


@router.get("/models")
def registered_models(admin: User = Depends(require_admin)):
    return list_registered_models()
