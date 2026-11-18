from getpass import getpass

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.models.vendor import Vendor


password_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def create_admin():
    db: Session = SessionLocal()

    try:
        print("\n===== ShopSense Admin Account Setup =====")

        email = input("Enter Admin email: ").strip().lower()

        if not email or "@" not in email:
            print("Invalid email address.")
            return

        existing_user = db.query(User).filter(
            User.email == email
        ).first()

        if existing_user:
            if existing_user.role == "Admin":
                print("An Admin account with this email already exists.")
            else:
                print(
                    "This email already belongs to a "
                    f"{existing_user.role} account."
                )
                print("Use a different email address.")
            return

        password = getpass("Create Admin password: ")
        confirm_password = getpass("Confirm Admin password: ")

        if len(password) < 8:
            print("Password must contain at least 8 characters.")
            return

        if len(password.encode("utf-8")) > 72:
            print("Password is too long for the configured password hasher.")
            return

        if password != confirm_password:
            print("Passwords do not match.")
            return

        admin = User(
            email=email,
            password_hash=password_context.hash(password),
            role="Admin",
            vendor_id=None,
            is_active=True
        )

        db.add(admin)
        db.commit()

        print("\nAdmin account created successfully!")
        print("Email:", email)
        print("Role: Admin")
        print("You can now log in through the ShopSense login page.")

    except Exception as error:
        db.rollback()
        print("Could not create the Admin account.")
        print("Error:", error)

    finally:
        db.close()


if __name__ == "__main__":
    create_admin()