from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey,
    Enum, Boolean, func
)

from app.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)

    email = Column(
        String(150),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = Column(String(255), nullable=False)

    role = Column(
        Enum("Customer", "Vendor", "Admin"),
        nullable=False,
        default="Customer"
    )

    vendor_id = Column(
        Integer,
        ForeignKey("vendors.vendor_id"),
        nullable=True,
        unique=True
    )

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime,
        server_default=func.current_timestamp()
    )