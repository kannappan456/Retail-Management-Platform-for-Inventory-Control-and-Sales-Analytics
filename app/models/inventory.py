
from sqlalchemy import Column, Integer, String, ForeignKey, CheckConstraint

from app.database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    inventory_id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("products.product_id"),
        unique=True,
        nullable=False
    )
    current_stock = Column(Integer, nullable=False, default=0)
    warehouse = Column(String(100))
    reorder_level = Column(Integer, nullable=False, default=10)

    __table_args__ = (
        CheckConstraint(
            "current_stock >= 0",
            name="check_inventory_stock"
        ),
        CheckConstraint(
            "reorder_level >= 0",
            name="check_inventory_reorder"
        ),
    )
