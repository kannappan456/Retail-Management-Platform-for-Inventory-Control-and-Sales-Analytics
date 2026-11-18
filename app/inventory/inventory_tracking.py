
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.user import User
from app.security import require_admin

router = APIRouter(
    prefix="/inventory-analytics",
    tags=["Inventory Analytics"]
)


@router.get("/overview")
def inventory_overview(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    records = db.query(
        Product.product_id,
        Product.product_name,
        Product.category,
        Product.price,
        Product.vendor_id,
        Inventory.current_stock,
        Inventory.reorder_level,
        Inventory.warehouse
    ).join(
        Inventory,
        Product.product_id == Inventory.product_id
    ).all()

    products = []
    total_stock = 0
    total_inventory_value = 0
    low_stock_count = 0
    out_of_stock_count = 0

    for item in records:
        stock = item.current_stock
        reorder_level = item.reorder_level

        inventory_value = float(item.price) * stock

        if stock == 0:
            stock_status = "Out of Stock"
            out_of_stock_count += 1
        elif stock <= reorder_level:
            stock_status = "Low Stock"
            low_stock_count += 1
        else:
            stock_status = "In Stock"

        total_stock += stock
        total_inventory_value += inventory_value

        products.append({
            "product_id": item.product_id,
            "product_name": item.product_name,
            "category": item.category,
            "vendor_id": item.vendor_id,
            "price": float(item.price),
            "current_stock": stock,
            "reorder_level": reorder_level,
            "warehouse": item.warehouse,
            "inventory_value": round(inventory_value, 2),
            "stock_status": stock_status
        })

    return {
        "total_products_tracked": len(products),
        "total_stock_units": total_stock,
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_products": low_stock_count,
        "out_of_stock_products": out_of_stock_count,
        "products": products
    }


@router.get("/low-stock")
def get_low_stock_products(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    records = db.query(
        Product.product_id,
        Product.product_name,
        Product.category,
        Inventory.current_stock,
        Inventory.reorder_level,
        Inventory.warehouse
    ).join(
        Inventory,
        Product.product_id == Inventory.product_id
    ).filter(
        Inventory.current_stock <= Inventory.reorder_level
    ).order_by(
        Inventory.current_stock.asc()
    ).all()

    return {
        "total_low_stock_products": len(records),
        "low_stock_products": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "category": item.category,
                "current_stock": item.current_stock,
                "reorder_level": item.reorder_level,
                "warehouse": item.warehouse
            }
            for item in records
        ]
    }


@router.get("/vendor-summary")
def vendor_inventory_summary(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    records = db.query(
        Product.vendor_id,
        func.count(Product.product_id).label("total_products"),
        func.sum(Inventory.current_stock).label("total_stock")
    ).join(
        Inventory,
        Product.product_id == Inventory.product_id
    ).group_by(
        Product.vendor_id
    ).all()

    return {
        "vendor_inventory": [
            {
                "vendor_id": item.vendor_id,
                "total_products": item.total_products,
                "total_stock_units": item.total_stock or 0
            }
            for item in records
        ]
    }
