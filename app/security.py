import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User


SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is missing from your .env file."
    )

ALGORITHM = "HS256"

# Accept bearer tokens directly through Swagger's Authorize button.
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = int(payload.get("sub"))

    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login token."
        )

    user = db.query(User).filter(
        User.user_id == user_id
    ).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Account not found or disabled."
        )

    # Check the current vendor status on every authenticated request.
    if user.role == "Vendor":
        from app.models.vendor import Vendor

        vendor = db.query(Vendor).filter(
            Vendor.vendor_id == user.vendor_id
        ).first()

        if not vendor or vendor.status != "Active":
            raise HTTPException(
                status_code=403,
                detail="Your vendor account is pending approval or suspended."
            )

    return user


def require_admin(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required."
        )

    return current_user


def require_vendor(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "Vendor":
        raise HTTPException(
            status_code=403,
            detail="Vendor access required."
        )

    return current_user


def require_customer(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "Customer":
        raise HTTPException(
            status_code=403,
            detail="Customer access required."
        )

    return current_user