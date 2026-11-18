from datetime import datetime, timedelta, timezone
import os

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.auth_schema import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse
)
from app.security import get_current_user


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is missing from your .env file."
    )

ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60

password_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def create_access_token(user):
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user.user_id),
        "role": user.role,
        "exp": expire
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):
    if data.role not in ("Customer", "Vendor"):
        raise HTTPException(
            status_code=400,
            detail="Public registration is only allowed for Customer or Vendor roles."
        )

    email = str(data.email).lower().strip()

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists."
        )

    vendor = None

    if data.role == "Vendor":
        if not data.business_name or not data.business_name.strip():
            raise HTTPException(
                status_code=400,
                detail="Business name is required."
            )

        if not data.owner_name or not data.owner_name.strip():
            raise HTTPException(
                status_code=400,
                detail="Owner name is required."
            )

    try:
        if data.role == "Vendor":
            existing_vendor = db.query(Vendor).filter(
                Vendor.email == email
            ).first()

            if existing_vendor:
                raise HTTPException(
                    status_code=409,
                    detail="A vendor with this email already exists."
                )

            vendor = Vendor(
                business_name=data.business_name.strip(),
                owner_name=data.owner_name.strip(),
                email=email,
                phone=data.phone,
                category=data.category,
                status="Pending"
            )

            db.add(vendor)
            db.flush()

        user = User(
            email=email,
            password_hash=password_context.hash(data.password),
            role=data.role,
            vendor_id=vendor.vendor_id if vendor else None
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create the account. Please try again."
        )


@router.post(
    "/login",
    response_model=TokenResponse
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    email = str(data.email).lower().strip()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user or not password_context.verify(
        data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="This account has been disabled."
        )

    if user.role == "Vendor":
        vendor = db.query(Vendor).filter(
            Vendor.vendor_id == user.vendor_id
        ).first()

        if not vendor or vendor.status != "Active":
            raise HTTPException(
                status_code=403,
                detail="Your vendor account is pending approval or suspended."
            )

    access_token = create_access_token(user)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@router.get(
    "/me",
    response_model=UserResponse
)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user


class ProfileUpdateRequest(BaseModel):
    email: Optional[str] = Field(default=None, max_length=150)
    current_password: Optional[str] = Field(default=None, min_length=1, max_length=72)
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=72)


class ProfileUpdateResponse(BaseModel):
    user_id: int
    email: str
    role: str
    vendor_id: Optional[int] = None
    message: str

    class Config:
        from_attributes = True


@router.patch(
    "/me",
    response_model=ProfileUpdateResponse,
)
def update_profile(
    data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allow any authenticated user to update their own email or password."""
    changes_made = []

    # Email change
    if data.email is not None:
        new_email = str(data.email).lower().strip()
        if "@" not in new_email or "." not in new_email.split("@")[-1]:
            raise HTTPException(
                status_code=422,
                detail="Please enter a valid email address.",
            )
        if new_email != current_user.email:
            conflict = db.query(User).filter(
                User.email == new_email,
                User.user_id != current_user.user_id,
            ).first()
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail="An account with this email already exists.",
                )
            current_user.email = new_email
            changes_made.append("email")

    # Password change — requires the current password for verification
    if data.new_password is not None:
        if not data.current_password:
            raise HTTPException(
                status_code=400,
                detail="Current password is required to set a new password.",
            )
        if not password_context.verify(data.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=401,
                detail="Current password is incorrect.",
            )
        current_user.password_hash = password_context.hash(data.new_password)
        changes_made.append("password")

    if not changes_made:
        return {**current_user.__dict__, "message": "No changes were made."}

    try:
        db.commit()
        db.refresh(current_user)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not save profile changes.",
        )

    return {**current_user.__dict__, "message": f"Updated: {', '.join(changes_made)}."}