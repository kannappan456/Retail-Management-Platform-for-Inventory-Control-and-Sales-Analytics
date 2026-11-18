
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.user import User
from app.security import require_admin

router = APIRouter(
    prefix="/stock-alerts",
    tags=["Stock Alerts"]
)


@router.get("/")
def get_stock_alerts(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    records = db.query(
        Product.product_id,
        Product.product_name,
        Product.category,
        Product.vendor_id,
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

    alerts = []

    for item in records:
        if item.current_stock == 0:
            priority = "Critical"
            message = "Product is out of stock. Immediate replenishment required."
        else:
            priority = "High"
            message = "Stock has reached or fallen below the reorder level."

        recommended_quantity = max(
            item.reorder_level * 2 - item.current_stock,
            0
        )

        alerts.append({
            "product_id": item.product_id,
            "product_name": item.product_name,
            "category": item.category,
            "vendor_id": item.vendor_id,
            "current_stock": item.current_stock,
            "reorder_level": item.reorder_level,
            "recommended_replenishment": recommended_quantity,
            "warehouse": item.warehouse,
            "priority": priority,
            "message": message
        })

    return {
        "total_alerts": len(alerts),
        "critical_alerts": sum(
            1 for alert in alerts
            if alert["priority"] == "Critical"
        ),
        "high_alerts": sum(
            1 for alert in alerts
            if alert["priority"] == "High"
        ),
        "alerts": alerts
    }
