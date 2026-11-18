from sqlalchemy import (
    Column, Integer, Numeric, DateTime, ForeignKey,
    Enum, CheckConstraint, func
)

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(Integer, primary_key=True, index=True)

    product_id = Column(
        Integer,
        ForeignKey("products.product_id"),
        nullable=False
    )

    vendor_id = Column(
        Integer,
        ForeignKey("vendors.vendor_id"),
        nullable=False
    )

    customer_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True
    )

    quantity = Column(Integer, nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)

    transaction_date = Column(
        DateTime,
        server_default=func.current_timestamp()
    )

    status = Column(
        Enum("Completed", "Cancelled", "Refunded"),
        nullable=False,
        default="Completed"
    )

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="check_transaction_quantity"
        ),
        CheckConstraint(
            "amount >= 0",
            name="check_transaction_amount"
        ),
    )