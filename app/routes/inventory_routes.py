from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user, require_customer
from app.models.user import User
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.vendor import Vendor

router = APIRouter(prefix="/inventory", tags=["Inventory"])


class StockUpdate(BaseModel):
    quantity: int = Field(gt=0)


@router.get("/{product_id}/availability")
def get_product_availability(
    product_id: int,
    _current_user: User = Depends(require_customer),
    db: Session = Depends(get_db),
):
    """Return current marketplace stock for a customer's cart validation."""
    product = db.query(Product).filter(
        Product.product_id == product_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id
    ).first()

    if not inventory:
        raise HTTPException(
            status_code=404,
            detail="Inventory record not found for this product.",
        )

    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == product.vendor_id
    ).first()
    available_for_purchase = bool(
        inventory.current_stock > 0 and vendor and vendor.status == "Active"
    )

    return {
        "product_id": product_id,
        "current_stock": inventory.current_stock,
        "available_for_purchase": available_for_purchase,
    }


@router.post("/{product_id}/stock")
def add_stock(
    product_id: int,
    stock_data: StockUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only Vendors and Admins can add stock.
    if current_user.role not in ["Vendor", "Admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only vendors and admins can update inventory."
        )

    # Find the product.
    product = db.query(Product).filter(
        Product.product_id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found."
        )

    # Vendors can update stock only for their own products.
    if current_user.role == "Vendor":
        if current_user.vendor_id is None:
            raise HTTPException(
                status_code=403,
                detail="Your account is not linked to a vendor."
            )

        if product.vendor_id != current_user.vendor_id:
            raise HTTPException(
                status_code=403,
                detail="You can only update stock for your own products."
            )

    # Confirm that the product's vendor is active.
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == product.vendor_id
    ).first()

    if not vendor or vendor.status != "Active":
        raise HTTPException(
            status_code=400,
            detail="Stock can only be added for products belonging to active vendors."
        )

    try:
        inventory = db.query(Inventory).filter(
            Inventory.product_id == product_id
        ).with_for_update().first()

        if not inventory:
            inventory = Inventory(
                product_id=product_id,
                current_stock=0,
                reorder_level=10
            )
            db.add(inventory)
            db.flush()

        inventory.current_stock += stock_data.quantity

        db.commit()
        db.refresh(inventory)

        return {
            "message": "Stock added successfully",
            "product_id": product_id,
            "quantity_added": stock_data.quantity,
            "current_stock": inventory.current_stock
        }

    except Exception as error:
        db.rollback()
        print(f"STOCK UPDATE ERROR: {error}")

        raise HTTPException(
            status_code=500,
            detail="Could not update stock."
        )
