
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy import Enum

from app.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String(100), nullable=False)
    owner_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(20))
    category = Column(String(100))
    status = Column(
    Enum("Pending", "Active", "Suspended", "Rejected"),
    nullable=False,
    default="Pending"
)
    created_at = Column(DateTime, server_default=func.current_timestamp())
