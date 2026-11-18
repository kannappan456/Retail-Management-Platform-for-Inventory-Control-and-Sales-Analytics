from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.vendor import Vendor
from app.models.user import User
from app.schemas.vendor_schema import VendorCreate, VendorResponse
from app.security import get_current_user, require_admin


router = APIRouter(prefix="/vendors", tags=["Vendors"])


# Public vendor registration.
# New vendors must still be approved by an Admin before logging in.
@router.post("/", response_model=VendorResponse, status_code=201)
def register_vendor(
    vendor_data: VendorCreate,
    db: Session = Depends(get_db)
):
    existing_vendor = db.query(Vendor).filter(
        Vendor.email == vendor_data.email
    ).first()

    if existing_vendor:
        raise HTTPException(
            status_code=409,
            detail="A vendor with this email already exists."
        )

    vendor = Vendor(
        business_name=vendor_data.business_name,
        owner_name=vendor_data.owner_name,
        email=vendor_data.email,
        phone=vendor_data.phone,
        category=vendor_data.category,
        status="Pending"
    )

    db.add(vendor)
    db.commit()
    db.refresh(vendor)

    return vendor


# Admin only: view every vendor.
@router.get("/", response_model=list[VendorResponse])
def list_vendors(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    return db.query(Vendor).order_by(
        Vendor.vendor_id.desc()
    ).all()


# Admin only: view a specific vendor.
@router.get("/{vendor_id}", response_model=VendorResponse)
def get_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == vendor_id
    ).first()

    if not vendor:
        raise HTTPException(
            status_code=404,
            detail="Vendor not found."
        )

    return vendor


# Admin only: approve a vendor.
@router.patch("/{vendor_id}/activate", response_model=VendorResponse)
def activate_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == vendor_id
    ).first()

    if not vendor:
        raise HTTPException(
            status_code=404,
            detail="Vendor not found."
        )

    vendor.status = "Active"
    db.commit()
    db.refresh(vendor)

    return vendor