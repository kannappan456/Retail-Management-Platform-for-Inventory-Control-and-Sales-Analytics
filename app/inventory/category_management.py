
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.security import require_admin

router = APIRouter(
    prefix="/categories",
    tags=["Category Management"]
)


@router.get("/")
def get_categories(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    normalized_category = func.coalesce(
        func.nullif(Product.category, ""),
        "Uncategorized"
    ).label("category")

    records = db.query(
        normalized_category,
        func.count(Product.product_id).label("total_products")
    ).group_by(
        normalized_category
    ).order_by(
        normalized_category
    ).all()

    categories = []

    for item in records:
        categories.append({
            "category": item.category,
            "total_products": item.total_products
        })

    return {
        "total_categories": len(categories),
        "categories": categories
    }


@router.get("/{category_name}/products")
def get_category_products(
    category_name: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    query = db.query(Product)

    if category_name == "Uncategorized":
        query = query.filter(or_(
            Product.category.is_(None),
            Product.category == "",
            Product.category == "Uncategorized"
        ))
    else:
        query = query.filter(Product.category == category_name)

    products = query.all()

    return {
        "category": category_name,
        "total_products": len(products),
        "products": [
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "price": float(product.price),
                "vendor_id": product.vendor_id
            }
            for product in products
        ]
    }
