from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user
from app.models.user import User
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.inventory import Inventory
from app.schemas.product_schema import ProductCreate, ProductResponse

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("/", response_model=ProductResponse, status_code=201)
def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only Vendors and Admins can create products.
    if current_user.role not in ["Vendor", "Admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only vendors and admins can create products."
        )

    # Vendors can create products only under their own vendor ID.
    if current_user.role == "Vendor":
        if current_user.vendor_id is None:
            raise HTTPException(
                status_code=403,
                detail="Your account is not linked to a vendor."
            )

        if product_data.vendor_id != current_user.vendor_id:
            raise HTTPException(
                status_code=403,
                detail="You can only create products for your own vendor account."
            )

    # Confirm that the target vendor exists.
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == product_data.vendor_id
    ).first()

    if not vendor:
        raise HTTPException(
            status_code=404,
            detail="Vendor not found."
        )

    # Products can only be added to active vendors.
    if vendor.status != "Active":
        raise HTTPException(
            status_code=400,
            detail="Only active vendors can add products."
        )

    product = Product(
        vendor_id=product_data.vendor_id,
        product_name=product_data.product_name,
        category=product_data.category,
        price=product_data.price
    )

    try:
        db.add(product)
        db.flush()

        inventory = Inventory(
            product_id=product.product_id,
            current_stock=0,
            reorder_level=10
        )

        db.add(inventory)
        db.commit()
        db.refresh(product)

        return product

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create product and inventory record."
        )


@router.get("/", response_model=list[ProductResponse])
def list_products(
    vendor_id: int = None,
    db: Session = Depends(get_db)
):
    query = db.query(Product)

    if vendor_id is not None:
        query = query.filter(Product.vendor_id == vendor_id)

    return query.order_by(Product.product_id.desc()).all()


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.product_id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found."
        )

    return product