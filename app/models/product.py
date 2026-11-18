
from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy import ForeignKey, CheckConstraint, func

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(
        Integer,
        ForeignKey("vendors.vendor_id"),
        nullable=False
    )
    product_name = Column(String(150), nullable=False)
    category = Column(String(100))
    price = Column(Numeric(10, 2), nullable=False)
    created_at = Column(
        DateTime,
        server_default=func.current_timestamp()
    )

    __table_args__ = (
        CheckConstraint("price >= 0", name="check_product_price"),
    )
