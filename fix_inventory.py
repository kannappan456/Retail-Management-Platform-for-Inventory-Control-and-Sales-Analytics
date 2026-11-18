
from app.database import SessionLocal
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.inventory import Inventory

db = SessionLocal()

try:
    product = db.query(Product).filter(
        Product.product_id == 3
    ).first()

    if product is None:
        print("Product 3 does not exist.")
    else:
        inventory = db.query(Inventory).filter(
            Inventory.product_id == 3
        ).first()

        if inventory is None:
            inventory = Inventory(
                product_id=3,
                current_stock=0,
                reorder_level=10
            )
            db.add(inventory)
            db.commit()
            print("Inventory record created for product 3.")
        else:
            print("Inventory record already exists.")

finally:
    db.close()
