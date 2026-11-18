from app.database import SessionLocal
from app.models.product import Product
from app.models.inventory import Inventory

db = SessionLocal()

try:
    products = db.query(Product).order_by(Product.product_id).all()

    print("\n--- PRODUCT INVENTORY CHECK ---")

    for product in products:
        inventory = db.query(Inventory).filter(
            Inventory.product_id == product.product_id
        ).first()

        if inventory:
            print(
                f"Product ID: {product.product_id} | "
                f"Name: {product.product_name} | "
                f"Stock: {inventory.current_stock}"
            )
        else:
            print(
                f"Product ID: {product.product_id} | "
                f"Name: {product.product_name} | "
                "INVENTORY RECORD MISSING"
            )

finally:
    db.close()