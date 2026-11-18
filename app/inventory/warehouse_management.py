
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.user import User
from app.security import require_admin

router = APIRouter(
    prefix="/warehouse",
    tags=["Warehouse Management"]
)


@router.get("/")
def get_warehouses(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    records = db.query(
        Inventory.warehouse,
        func.count(Inventory.product_id).label("total_products"),
        func.sum(Inventory.current_stock).label("total_stock")
    ).group_by(
        Inventory.warehouse
    ).all()

    warehouses = []

    for item in records:
        warehouses.append({
            "warehouse": item.warehouse or "Unassigned",
            "total_products": item.total_products,
            "total_stock_units": item.total_stock or 0
        })

    return {
        "total_warehouses": len(warehouses),
        "warehouses": warehouses
    }


@router.get("/{warehouse_name}/products")
def get_warehouse_products(
    warehouse_name: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    records = db.query(
        Product.product_id,
        Product.product_name,
        Product.category,
        Inventory.current_stock,
        Inventory.reorder_level
    ).join(
        Inventory,
        Product.product_id == Inventory.product_id
    ).filter(
        Inventory.warehouse == warehouse_name
    ).all()

    return {
        "warehouse": warehouse_name,
        "total_products": len(records),
        "products": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "category": item.category,
                "current_stock": item.current_stock,
                "reorder_level": item.reorder_level
            }
            for item in records
        ]
    }


@router.patch("/{product_id}/assign")
def assign_product_to_warehouse(
    product_id: int,
    warehouse_name: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id
    ).first()

    if not inventory:
        return {"error": "Inventory record not found for this product."}

    inventory.warehouse = warehouse_name
    db.commit()
    db.refresh(inventory)

    return {
        "message": "Product assigned to warehouse successfully.",
        "product_id": product_id,
        "warehouse": inventory.warehouse
    }
