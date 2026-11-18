
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.transaction import Transaction
from app.models.user import User
from app.security import require_admin

router = APIRouter(
    prefix="/inventory-turnover",
    tags=["Inventory Turnover"]
)


@router.get("/")
def get_inventory_turnover(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    products = db.query(
        Product.product_id,
        Product.product_name,
        Inventory.current_stock,
        Inventory.reorder_level,
        func.coalesce(func.sum(Transaction.quantity), 0).label("total_units_sold"),
    ).join(
        Inventory,
        Product.product_id == Inventory.product_id
    ).outerjoin(
        Transaction,
        (Transaction.product_id == Product.product_id)
        & (Transaction.status == "Completed"),
    ).group_by(
        Product.product_id,
        Product.product_name,
        Inventory.current_stock,
        Inventory.reorder_level,
    ).order_by(Product.product_id).all()

    results = []

    for product in products:

        units_sold = int(product.total_units_sold or 0)

        current_stock = product.current_stock

        # Sales-to-current-stock ratio (a proxy, not
        # the standard accounting inventory turnover ratio).
        turnover_ratio = (
            round(units_sold / current_stock, 2)
            if current_stock > 0 else None
        )

        results.append({
            "product_id": product.product_id,
            "product_name": product.product_name,
            "total_units_sold": units_sold,
            "current_stock": current_stock,
            "reorder_level": product.reorder_level,
            "sales_to_current_stock_ratio": turnover_ratio
        })

    return {
        "calculation": "Completed units sold / current stock",
        "note": "This is a sales-to-current-stock proxy. Standard inventory turnover requires cost of goods sold and average inventory value.",
        "total_products": len(results),
        "products": results
    }
