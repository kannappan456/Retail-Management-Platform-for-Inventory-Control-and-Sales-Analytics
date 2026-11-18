from app.database import SessionLocal
from app.models.vendor import Vendor

db = SessionLocal()

try:
    email = "techworld.test01@example.com"

    vendor = db.query(Vendor).filter(
        Vendor.email == email
    ).first()

    if vendor:
        vendor.status = "Active"
        db.commit()

        print("Vendor activated successfully!")
        print("Business:", vendor.business_name)
        print("Email:", vendor.email)
        print("Status:", vendor.status)
    else:
        print("Vendor not found. Check the email address.")

except Exception as e:
    db.rollback()
    print("Error:", e)

finally:
    db.close()