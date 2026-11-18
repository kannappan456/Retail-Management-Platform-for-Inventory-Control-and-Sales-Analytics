from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.database import get_db
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.inventory import Inventory
from app.models.user import User
from app.security import require_admin, require_vendor


router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _month_window(months: int):
    """Return ascending YYYY-MM labels and an inclusive-start/exclusive-end window."""
    today = date.today()
    current = today.year * 12 + today.month - 1
    indices = range(current - months + 1, current + 1)
    pairs = [(index // 12, index % 12 + 1) for index in indices]
    start_year, start_month = pairs[0]
    end_year, end_month = (today.year + (today.month == 12), today.month % 12 + 1)
    return (
        [f"{year:04d}-{month:02d}" for year, month in pairs],
        datetime(start_year, start_month, 1),
        datetime(end_year, end_month, 1),
    )


def _revenue_overview(db: Session, vendor_id=None):
    query = db.query(Transaction).filter(Transaction.status == "Completed")
    if vendor_id is not None:
        query = query.filter(Transaction.vendor_id == vendor_id)
    revenue, records, units = query.with_entities(
        func.coalesce(func.sum(Transaction.amount), 0),
        func.count(Transaction.transaction_id),
        func.coalesce(func.sum(Transaction.quantity), 0),
    ).one()
    now = datetime.now()
    current_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        next_start = datetime(now.year + 1, 1, 1)
    else:
        next_start = datetime(now.year, now.month + 1, 1)
    if now.month == 1:
        previous_start = datetime(now.year - 1, 12, 1)
    else:
        previous_start = datetime(now.year, now.month - 1, 1)

    def period_total(start, end):
        period = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.status == "Completed",
            Transaction.transaction_date >= start,
            Transaction.transaction_date < end,
        )
        if vendor_id is not None:
            period = period.filter(Transaction.vendor_id == vendor_id)
        return float(period.scalar() or 0)

    current_revenue = period_total(current_start, next_start)
    previous_revenue = period_total(previous_start, current_start)
    growth = (
        ((current_revenue - previous_revenue) / previous_revenue) * 100
        if previous_revenue > 0 else None
    )
    revenue = float(revenue or 0)
    return {
        "gmv": revenue,
        "completed_revenue": revenue,
        "completed_transaction_records": int(records or 0),
        "total_orders": None,
        "total_units_sold": int(units or 0),
        "average_order_value": None,
        "average_transaction_value": revenue / records if records else None,
        "current_month_revenue": current_revenue,
        "previous_month_revenue": previous_revenue,
        "mom_revenue_growth_percentage": growth,
        "definition": "GMV and completed revenue are the sum of amounts on Completed transaction records.",
        "aov_note": "Order value is unavailable because transactions have no order/group identifier. Average transaction value is shown as a proxy.",
    }


def _monthly_revenue(db: Session, months: int, vendor_id=None):
    labels, start, end = _month_window(months)
    query = db.query(
        extract("year", Transaction.transaction_date).label("year"),
        extract("month", Transaction.transaction_date).label("month"),
        func.coalesce(func.sum(Transaction.amount), 0).label("revenue"),
        func.count(Transaction.transaction_id).label("records"),
    ).filter(
        Transaction.status == "Completed",
        Transaction.transaction_date >= start,
        Transaction.transaction_date < end,
    )
    if vendor_id is not None:
        query = query.filter(Transaction.vendor_id == vendor_id)
    rows = query.group_by("year", "month").all()
    by_month = {f"{int(row.year):04d}-{int(row.month):02d}": row for row in rows}
    values = []
    previous = None
    for label in labels:
        row = by_month.get(label)
        revenue = float(row.revenue or 0) if row else 0.0
        records = int(row.records or 0) if row else 0
        growth = ((revenue - previous) / previous * 100) if previous else None
        values.append({
            "month": label,
            "revenue": revenue,
            "gmv": revenue,
            "completed_transaction_records": records,
            "mom_revenue_growth_percentage": growth,
        })
        previous = revenue
    return values


def _vendor_required(user: User):
    if user.vendor_id is None:
        raise HTTPException(status_code=403, detail="No vendor account is linked to this user.")
    return user.vendor_id


# =====================================================
# ADMIN ANALYTICS
# =====================================================

@router.get("/summary")
def sales_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    completed_sales = db.query(Transaction).filter(
        Transaction.status == "Completed"
    )

    total_revenue = completed_sales.with_entities(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).scalar()

    total_transactions = completed_sales.count()

    total_units_sold = completed_sales.with_entities(
        func.coalesce(func.sum(Transaction.quantity), 0)
    ).scalar()

    total_products = db.query(Product).count()
    total_vendors = db.query(Vendor).count()

    return {
        "total_revenue": float(total_revenue),
        "completed_transactions": total_transactions,
        "total_units_sold": int(total_units_sold),
        "total_products": total_products,
        "total_vendors": total_vendors
    }


@router.get("/products")
def product_performance(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    results = (
        db.query(
            Product.product_id,
            Product.product_name,
            Product.category,
            func.coalesce(
                func.sum(Transaction.quantity), 0
            ).label("units_sold"),
            func.coalesce(
                func.sum(Transaction.amount), 0
            ).label("revenue")
        )
        .outerjoin(
            Transaction,
            (Transaction.product_id == Product.product_id)
            & (Transaction.status == "Completed")
        )
        .group_by(
            Product.product_id,
            Product.product_name,
            Product.category
        )
        .order_by(
            func.coalesce(func.sum(Transaction.amount), 0).desc()
        )
        .all()
    )

    return [
        {
            "product_id": row.product_id,
            "product_name": row.product_name,
            "category": row.category,
            "units_sold": int(row.units_sold),
            "revenue": float(row.revenue)
        }
        for row in results
    ]


@router.get("/vendors")
def vendor_performance(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    results = (
        db.query(
            Vendor.vendor_id,
            Vendor.business_name,
            Vendor.status,
            func.count(
                func.distinct(Product.product_id)
            ).label("product_count"),
            func.coalesce(
                func.sum(Transaction.amount), 0
            ).label("revenue")
        )
        .outerjoin(
            Product,
            Product.vendor_id == Vendor.vendor_id
        )
        .outerjoin(
            Transaction,
            (Transaction.product_id == Product.product_id)
            & (Transaction.vendor_id == Vendor.vendor_id)
            & (Transaction.status == "Completed")
        )
        .group_by(
            Vendor.vendor_id,
            Vendor.business_name,
            Vendor.status
        )
        .order_by(
            func.coalesce(func.sum(Transaction.amount), 0).desc()
        )
        .all()
    )

    return [
        {
            "vendor_id": row.vendor_id,
            "business_name": row.business_name,
            "status": row.status,
            "product_count": row.product_count,
            "revenue": float(row.revenue)
        }
        for row in results
    ]


@router.get("/revenue/overview")
def admin_revenue_overview(
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    return _revenue_overview(db)


@router.get("/revenue/monthly")
def admin_monthly_revenue(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    return {"months": _monthly_revenue(db, months)}


@router.get("/benchmarking/vendors")
def benchmark_vendors(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    rows = db.query(
        Vendor.vendor_id,
        Vendor.business_name,
        Vendor.status,
        func.count(func.distinct(Product.product_id)).label("product_count"),
        func.count(func.distinct(Transaction.transaction_id)).label("completed_transaction_records"),
        func.coalesce(func.sum(Transaction.amount), 0).label("revenue"),
        func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
    ).outerjoin(Product, Product.vendor_id == Vendor.vendor_id).outerjoin(
        Transaction,
        (Transaction.product_id == Product.product_id)
        & (Transaction.vendor_id == Vendor.vendor_id)
        & (Transaction.status == "Completed"),
    ).group_by(Vendor.vendor_id, Vendor.business_name, Vendor.status).order_by(
        func.coalesce(func.sum(Transaction.amount), 0).desc(), Vendor.vendor_id
    ).limit(limit).all()
    total_revenue = float(db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.status == "Completed"
    ).scalar() or 0)
    result = []
    for rank, row in enumerate(rows, 1):
        revenue = float(row.revenue or 0)
        count = int(row.completed_transaction_records or 0)
        result.append({
            "rank": rank,
            "vendor_id": row.vendor_id,
            "business_name": row.business_name,
            "status": row.status,
            "product_count": int(row.product_count or 0),
            "completed_transaction_records": count,
            "total_orders": None,
            "units_sold": int(row.units_sold or 0),
            "revenue": revenue,
            "revenue_contribution_percentage": revenue / total_revenue * 100 if total_revenue else None,
            "average_order_value": None,
            "average_transaction_value": revenue / count if count else None,
        })
    return {"vendors": result, "aov_note": _revenue_overview(db)["aov_note"]}


@router.get("/benchmarking/categories")
def benchmark_categories(
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    category = func.coalesce(func.nullif(Product.category, ""), "Uncategorized")
    rows = db.query(
        category.label("category"),
        func.coalesce(func.sum(Transaction.amount), 0).label("revenue"),
        func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
        func.count(func.distinct(Transaction.transaction_id)).label("completed_transaction_records"),
        func.count(func.distinct(Product.product_id)).label("product_count"),
    ).outerjoin(Transaction, (Transaction.product_id == Product.product_id) &
                 (Transaction.status == "Completed")).group_by(category).order_by(
        func.coalesce(func.sum(Transaction.amount), 0).desc()
    ).all()
    return {"categories": [{
        "category": row.category,
        "revenue": float(row.revenue or 0),
        "units_sold": int(row.units_sold or 0),
        "completed_transaction_records": int(row.completed_transaction_records or 0),
        "product_count": int(row.product_count or 0),
    } for row in rows]}


@router.get("/benchmarking/products")
def benchmark_products(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    rows = db.query(
        Product.product_id, Product.product_name, Product.category,
        Product.vendor_id, Vendor.business_name,
        func.coalesce(func.sum(Transaction.amount), 0).label("revenue"),
        func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
        func.count(func.distinct(Transaction.transaction_id)).label("completed_transaction_records"),
    ).join(Vendor, Vendor.vendor_id == Product.vendor_id).outerjoin(
        Transaction, (Transaction.product_id == Product.product_id) &
        (Transaction.status == "Completed")
    ).group_by(Product.product_id, Product.product_name, Product.category,
               Product.vendor_id, Vendor.business_name).order_by(
        func.coalesce(func.sum(Transaction.amount), 0).desc(), Product.product_id
    ).limit(limit).all()
    return {"products": [{
        "product_id": row.product_id,
        "product_name": row.product_name,
        "category": row.category,
        "vendor_id": row.vendor_id,
        "business_name": row.business_name,
        "revenue": float(row.revenue or 0),
        "units_sold": int(row.units_sold or 0),
        "completed_transaction_records": int(row.completed_transaction_records or 0),
    } for row in rows]}


# =====================================================
# VENDOR ANALYTICS
# Vendors can access ONLY their own data.
# =====================================================

@router.get("/vendor/revenue/overview")
def vendor_revenue_overview(
    db: Session = Depends(get_db), vendor_user: User = Depends(require_vendor)
):
    return _revenue_overview(db, _vendor_required(vendor_user))


@router.get("/vendor/revenue/monthly")
def vendor_monthly_revenue(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db), vendor_user: User = Depends(require_vendor)
):
    return {"months": _monthly_revenue(db, months, _vendor_required(vendor_user))}


@router.get("/vendor/revenue/categories")
def vendor_revenue_categories(
    db: Session = Depends(get_db), vendor_user: User = Depends(require_vendor)
):
    vendor_id = _vendor_required(vendor_user)
    category = func.coalesce(func.nullif(Product.category, ""), "Uncategorized")
    rows = db.query(
        category.label("category"),
        func.coalesce(func.sum(Transaction.amount), 0).label("revenue"),
        func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
    ).join(Transaction, Transaction.product_id == Product.product_id).filter(
        Product.vendor_id == vendor_id, Transaction.vendor_id == vendor_id,
        Transaction.status == "Completed",
    ).group_by(category).order_by(func.sum(Transaction.amount).desc()).all()
    return {"categories": [{
        "category": row.category,
        "revenue": float(row.revenue or 0),
        "units_sold": int(row.units_sold or 0),
    } for row in rows]}


@router.get("/vendor/revenue/products")
def vendor_revenue_products(
    db: Session = Depends(get_db), vendor_user: User = Depends(require_vendor)
):
    vendor_id = _vendor_required(vendor_user)
    rows = db.query(
        Product.product_id, Product.product_name, Product.category,
        func.coalesce(func.sum(Transaction.amount), 0).label("revenue"),
        func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
        func.count(func.distinct(Transaction.transaction_id)).label("completed_transaction_records"),
    ).outerjoin(Transaction, (Transaction.product_id == Product.product_id) &
                 (Transaction.vendor_id == vendor_id) &
                 (Transaction.status == "Completed")).filter(
        Product.vendor_id == vendor_id
    ).group_by(Product.product_id, Product.product_name, Product.category).order_by(
        func.sum(Transaction.amount).desc()
    ).all()
    return {"products": [{
        "product_id": row.product_id,
        "product_name": row.product_name,
        "category": row.category,
        "revenue": float(row.revenue or 0),
        "units_sold": int(row.units_sold or 0),
        "completed_transaction_records": int(row.completed_transaction_records or 0),
    } for row in rows]}

@router.get("/vendor/summary")
def vendor_sales_summary(
    db: Session = Depends(get_db),
    vendor_user: User = Depends(require_vendor)
):
    vendor_id = vendor_user.vendor_id

    if vendor_id is None:
        raise HTTPException(
            status_code=403,
            detail="No vendor account is linked to this user."
        )

    completed_sales = db.query(Transaction).filter(
        Transaction.vendor_id == vendor_id,
        Transaction.status == "Completed"
    )

    total_revenue = completed_sales.with_entities(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).scalar()

    total_transactions = completed_sales.count()

    total_units_sold = completed_sales.with_entities(
        func.coalesce(func.sum(Transaction.quantity), 0)
    ).scalar()

    total_products = db.query(Product).filter(
        Product.vendor_id == vendor_id
    ).count()

    return {
        "total_revenue": float(total_revenue),
        "completed_transactions": total_transactions,
        "total_units_sold": int(total_units_sold),
        "total_products": total_products
    }


@router.get("/vendor/products")
def vendor_product_performance(
    db: Session = Depends(get_db),
    vendor_user: User = Depends(require_vendor)
):
    vendor_id = vendor_user.vendor_id

    if vendor_id is None:
        raise HTTPException(
            status_code=403,
            detail="No vendor account is linked to this user."
        )

    results = (
        db.query(
            Product.product_id,
            Product.product_name,
            Product.category,
            func.coalesce(
                func.sum(Transaction.quantity), 0
            ).label("units_sold"),
            func.coalesce(
                func.sum(Transaction.amount), 0
            ).label("revenue")
        )
        .outerjoin(
            Transaction,
            (Transaction.product_id == Product.product_id)
            & (Transaction.vendor_id == vendor_id)
            & (Transaction.status == "Completed")
        )
        .filter(Product.vendor_id == vendor_id)
        .group_by(
            Product.product_id,
            Product.product_name,
            Product.category
        )
        .order_by(
            func.coalesce(func.sum(Transaction.amount), 0).desc()
        )
        .all()
    )

    return [
        {
            "product_id": row.product_id,
            "product_name": row.product_name,
            "category": row.category,
            "units_sold": int(row.units_sold),
            "revenue": float(row.revenue)
        }
        for row in results
    ]


@router.get("/vendor/inventory")
def vendor_inventory(
    db: Session = Depends(get_db),
    vendor_user: User = Depends(require_vendor)
):
    vendor_id = vendor_user.vendor_id

    if vendor_id is None:
        raise HTTPException(
            status_code=403,
            detail="No vendor account is linked to this user."
        )

    results = (
        db.query(
            Product.product_id,
            Product.product_name,
            Product.category,
            Inventory.current_stock,
            Inventory.reorder_level,
            Inventory.warehouse
        )
        .join(
            Inventory,
            Inventory.product_id == Product.product_id
        )
        .filter(Product.vendor_id == vendor_id)
        .order_by(Product.product_name)
        .all()
    )

    return [
        {
            "product_id": row.product_id,
            "product_name": row.product_name,
            "category": row.category,
            "current_stock": row.current_stock,
            "reorder_level": row.reorder_level,
            "warehouse": row.warehouse,
            "low_stock": row.current_stock <= row.reorder_level
        }
        for row in results
    ]
