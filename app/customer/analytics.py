from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.security import require_admin

router = APIRouter(
    prefix="/customer-analytics",
    tags=["Customer Analytics"]
)


@router.get("/overview")
def customer_overview(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    # Only include completed purchases linked to customer accounts.
    result = db.query(
        User.user_id,
        User.email,
        func.count(Transaction.transaction_id).label("total_orders"),
        func.sum(Transaction.quantity).label("total_units"),
        func.sum(Transaction.amount).label("total_spent")
    ).join(
        Transaction,
        Transaction.customer_id == User.user_id
    ).filter(
        User.role == "Customer",
        Transaction.status == "Completed"
    ).group_by(
        User.user_id,
        User.email
    ).all()

    customers = []

    for row in result:
        total_orders = row.total_orders or 0
        total_spent = float(row.total_spent or 0)

        customers.append({
            "customer_id": row.user_id,
            "email": row.email,
            "total_orders": total_orders,
            "total_units": row.total_units or 0,
            "total_spent": round(total_spent, 2),
            "average_order_value": round(
                total_spent / total_orders, 2
            ) if total_orders else 0
        })

    total_customers = len(customers)

    total_revenue = sum(
        customer["total_spent"] for customer in customers
    )

    total_orders = sum(
        customer["total_orders"] for customer in customers
    )

    return {
        "total_customers": total_customers,
        "total_customer_revenue": round(total_revenue, 2),
        "total_customer_orders": total_orders,
        "average_customer_spend": round(
            total_revenue / total_customers, 2
        ) if total_customers else 0,
        "customers": customers
    }


@router.get("/top-customers")
def top_customers(
    limit: int = 10,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if limit < 1 or limit > 100:
        return {"error": "Limit must be between 1 and 100."}

    result = db.query(
        User.user_id,
        User.email,
        func.sum(Transaction.amount).label("total_spent")
    ).join(
        Transaction,
        Transaction.customer_id == User.user_id
    ).filter(
        User.role == "Customer",
        Transaction.status == "Completed"
    ).group_by(
        User.user_id,
        User.email
    ).order_by(
        func.sum(Transaction.amount).desc()
    ).limit(limit).all()

    return {
        "top_customers": [
            {
                "customer_id": row.user_id,
                "email": row.email,
                "total_spent": round(float(row.total_spent or 0), 2)
            }
            for row in result
        ]
    }