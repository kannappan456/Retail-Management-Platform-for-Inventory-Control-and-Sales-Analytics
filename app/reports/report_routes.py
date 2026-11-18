"""Admin-only business intelligence overview and report downloads."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.reports.bi_reports import build_bi_overview, create_bi_excel, create_bi_pdf
from app.security import require_admin


router = APIRouter(prefix="/reports/bi", tags=["Business Intelligence Reports"])


@router.get("/overview")
def bi_overview(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        return build_bi_overview(db, admin, months)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _report_data(months, db, admin):
    try:
        return build_bi_overview(db, admin, months)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/pdf")
def bi_pdf(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    content = create_bi_pdf(_report_data(months, db, admin))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="shopsense-bi-report.pdf"'},
    )


@router.get("/excel")
def bi_excel(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    content = create_bi_excel(_report_data(months, db, admin))
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="shopsense-bi-report.xlsx"'},
    )
