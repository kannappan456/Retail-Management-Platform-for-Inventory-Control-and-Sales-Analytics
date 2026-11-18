"""Admin-only controls and status for scheduled analytics workflows."""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.models.user import User
from app.security import require_admin
from app.workflow_scheduler import JobAlreadyRunning, workflow_manager


router = APIRouter(prefix="/workflows", tags=["Analytics Workflows"])


@router.get("/status")
def workflow_status(admin: User = Depends(require_admin)):
    return workflow_manager.scheduler_status()


@router.get("/jobs")
def workflow_jobs(admin: User = Depends(require_admin)):
    return {
        "scheduler": workflow_manager.scheduler_status(),
        "jobs": workflow_manager.list_jobs(),
    }


@router.get("/jobs/{job_id}")
def workflow_job(job_id: str, admin: User = Depends(require_admin)):
    job = workflow_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Workflow job was not found.")
    return job


@router.post("/jobs/{job_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_workflow_now(job_id: str, admin: User = Depends(require_admin)):
    try:
        job = workflow_manager.trigger_manual(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow job was not found.")
    except JobAlreadyRunning:
        raise HTTPException(status_code=409, detail="This workflow is already running.")
    return {"message": "Manual workflow run queued.", "job": job}


@router.post("/jobs/{job_id}/pause")
def pause_workflow(job_id: str, admin: User = Depends(require_admin)):
    try:
        return workflow_manager.pause_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow job was not found.")


@router.post("/jobs/{job_id}/resume")
def resume_workflow(job_id: str, admin: User = Depends(require_admin)):
    try:
        return workflow_manager.resume_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow job was not found.")


@router.get("/history")
def workflow_history(
    limit: int = Query(default=50, ge=1, le=200),
    admin: User = Depends(require_admin),
):
    return {
        "history_limit": workflow_manager.scheduler_status()["history_limit"],
        "executions": workflow_manager.history(limit),
    }
