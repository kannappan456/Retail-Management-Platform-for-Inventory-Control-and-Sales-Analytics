from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from uuid import uuid4

from app.database import get_db
from app.security import require_customer, get_current_user
from app.models.user import User
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.inventory import Inventory
from app.models.transaction import Transaction

router = APIRouter(prefix="/transactions", tags=["Transactions"])


class TransactionCreate(BaseModel):
    product_id: int = Field(gt=0)
    vendor_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class CheckoutItem(BaseModel):
    product_id: int = Field(gt=0)
    vendor_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class CheckoutCreate(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1, max_length=50)


@router.get("/vendor-orders")
def vendor_order_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return orders for products that belong to the authenticated vendor."""
    if current_user.role != "Vendor":
        raise HTTPException(
            status_code=403,
            detail="Vendor access required.",
        )

    vendor_id = current_user.vendor_id
    if vendor_id is None:
        raise HTTPException(
            status_code=403,
            detail="Your account is not linked to a vendor.",
        )

    records = (
        db.query(
            Transaction.transaction_id,
            Transaction.product_id,
            Product.product_name,
            Product.category,
            Transaction.quantity,
            Transaction.amount,
            Transaction.transaction_date,
            Transaction.status,
            Transaction.customer_id,
        )
        .join(Product, Product.product_id == Transaction.product_id)
        .filter(Transaction.vendor_id == vendor_id)
        .order_by(
            Transaction.transaction_date.desc(),
            Transaction.transaction_id.desc(),
        )
        .all()
    )

    return {
        "total_orders": len(records),
        "orders": [
            {
                "transaction_id": row.transaction_id,
                "product_id": row.product_id,
                "product_name": row.product_name,
                "category": row.category,
                "quantity": row.quantity,
                "amount": float(row.amount),
                "transaction_date": row.transaction_date,
                "status": row.status,
                # Customer ID only — no PII exposed without a separate profile lookup.
                "customer_id": row.customer_id,
            }
            for row in records
        ],
    }


@router.get("/mine")
def customer_transaction_history(
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    """Return completed/cancelled/refunded transaction rows owned by this customer."""
    records = db.query(
        Transaction.transaction_id,
        Transaction.product_id,
        Product.product_name,
        Product.category,
        Transaction.vendor_id,
        Vendor.business_name,
        Transaction.quantity,
        Transaction.amount,
        Transaction.transaction_date,
        Transaction.status,
    ).join(
        Product, Product.product_id == Transaction.product_id
    ).join(
        Vendor, Vendor.vendor_id == Transaction.vendor_id
    ).filter(
        Transaction.customer_id == current_user.user_id
    ).order_by(
        Transaction.transaction_date.desc(), Transaction.transaction_id.desc()
    ).all()

    return {
        "total_transactions": len(records),
        "transactions": [
            {
                "transaction_id": row.transaction_id,
                "product_id": row.product_id,
                "product_name": row.product_name,
                "category": row.category,
                "vendor_id": row.vendor_id,
                "business_name": row.business_name,
                "quantity": row.quantity,
                "amount": float(row.amount),
                "transaction_date": row.transaction_date,
                "status": row.status,
            }
            for row in records
        ],
    }


@router.post("/checkout", status_code=201)
def checkout(
    checkout_data: CheckoutCreate,
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db)
):
    """Allow authenticated customers to purchase available products."""
    try:
        prepared = []
        seen_product_ids = set()

        # Validate every cart item before changing inventory.
        for item in checkout_data.items:

            if item.product_id in seen_product_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "A product appears more than once in the cart. "
                        "Refresh your cart and try again."
                    )
                )

            seen_product_ids.add(item.product_id)

            product = db.query(Product).filter(
                Product.product_id == item.product_id
            ).first()

            if not product:
                raise HTTPException(
                    status_code=404,
                    detail=f"Product {item.product_id} not found."
                )

            # Verify that the product belongs to the specified vendor.
            if product.vendor_id != item.vendor_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Product {item.product_id} "
                        "does not belong to this vendor."
                    )
                )

            vendor = db.query(Vendor).filter(
                Vendor.vendor_id == item.vendor_id
            ).first()

            if not vendor or vendor.status != "Active":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Vendor for product {item.product_id} "
                        "must be active."
                    )
                )

            # Lock inventory while checking available stock.
            inventory = db.query(Inventory).filter(
                Inventory.product_id == product.product_id
            ).with_for_update().first()

            if not inventory:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Inventory record for product "
                        f"{item.product_id} not found."
                    )
                )

            if inventory.current_stock < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient stock for {product.product_name}. "
                        f"Available: {inventory.current_stock}, "
                        f"requested: {item.quantity}."
                    )
                )

            prepared.append((item, product, vendor, inventory))

        # All cart items passed validation.
        transaction_rows = []
        total_amount = 0.0

        # Calculate prices from the database and update stock.
        for item, product, vendor, inventory in prepared:
            amount = round(float(product.price) * item.quantity, 2)

            inventory.current_stock -= item.quantity

            transaction = Transaction(
                product_id=product.product_id,
                vendor_id=vendor.vendor_id,
                customer_id=current_user.user_id,
                quantity=item.quantity,
                amount=amount,
                status="Completed"
            )

            db.add(transaction)

            transaction_rows.append({
                "product_id": product.product_id,
                "vendor_id": vendor.vendor_id,
                "quantity": item.quantity,
                "amount": amount,
                "remaining_stock": inventory.current_stock
            })

            total_amount += amount

        # Save all transactions and stock changes together.
        db.commit()

        return {
            "message": "Order placed successfully",
            "checkout_reference": uuid4().hex[:12].upper(),
            "transactions": transaction_rows,
            "total_amount": round(total_amount, 2),
            "status": "Completed"
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print(f"Checkout failed: {error}")

        raise HTTPException(
            status_code=500,
            detail="Checkout failed. No cart items were saved."
        )


@router.post("/", status_code=403)
def create_transaction():
    """Disable manual sales creation outside the checkout process."""
    raise HTTPException(
        status_code=403,
        detail=(
            "Direct transaction creation is disabled. "
            "Use customer checkout."
        )
    )
