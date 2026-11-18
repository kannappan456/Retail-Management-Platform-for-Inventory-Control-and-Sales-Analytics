"""HTTP-level revenue API verification with isolated in-memory SQLite data."""
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vendor import Vendor
from app.security import ALGORITHM, SECRET_KEY
from jose import jwt
from test_security_phase1 import asgi_request, run_async


ADMIN_ENDPOINTS = [
    "/analytics/revenue/overview",
    "/analytics/revenue/monthly?months=2",
    "/analytics/benchmarking/vendors",
    "/analytics/benchmarking/categories",
    "/analytics/benchmarking/products",
]
VENDOR_ENDPOINTS = [
    "/analytics/vendor/revenue/overview?vendor_id=2",
    "/analytics/vendor/revenue/monthly?months=2&vendor_id=2",
    "/analytics/vendor/revenue/categories?vendor_id=2",
    "/analytics/vendor/revenue/products?vendor_id=2",
]


class TestRevenueAnalyticsHTTP(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        def isolated_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = isolated_db
        self._seed_isolated_records()
        self.tokens = {
            "admin": self._token(1),
            "vendor_one": self._token(2),
            "customer": self._token(3),
            "vendor_two": self._token(4),
        }

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @staticmethod
    def _token(user_id):
        return jwt.encode(
            {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )

    def _seed_isolated_records(self):
        with self.Session() as db:
            db.add_all([
                Vendor(vendor_id=1, business_name="North Goods", owner_name="One", email="one@isolated.test", status="Active"),
                Vendor(vendor_id=2, business_name="South Goods", owner_name="Two", email="two@isolated.test", status="Active"),
            ])
            db.flush()
            db.add_all([
                User(user_id=1, email="admin@isolated.test", role="Admin", password_hash="unused", is_active=True),
                User(user_id=2, email="vendor1@isolated.test", role="Vendor", vendor_id=1, password_hash="unused", is_active=True),
                User(user_id=3, email="customer@isolated.test", role="Customer", password_hash="unused", is_active=True),
                User(user_id=4, email="vendor2@isolated.test", role="Vendor", vendor_id=2, password_hash="unused", is_active=True),
            ])
            db.flush()
            db.add_all([
                Product(product_id=11, vendor_id=1, product_name="Tea", category="Grocery", price=10),
                Product(product_id=12, vendor_id=1, product_name="Mug", category="Home", price=10),
                Product(product_id=21, vendor_id=2, product_name="Coffee", category="Grocery", price=10),
            ])
            now = datetime.now()
            current = datetime(now.year, now.month, min(now.day, 20), 12)
            previous = datetime(now.year - (now.month == 1), 12 if now.month == 1 else now.month - 1, 15, 12)
            db.add_all([
                Transaction(transaction_id=101, product_id=11, vendor_id=1, customer_id=3, quantity=2, amount=20, status="Completed", transaction_date=current),
                Transaction(transaction_id=102, product_id=12, vendor_id=1, customer_id=3, quantity=1, amount=10, status="Completed", transaction_date=previous),
                Transaction(transaction_id=103, product_id=21, vendor_id=2, customer_id=3, quantity=4, amount=40, status="Completed", transaction_date=current),
                Transaction(transaction_id=104, product_id=21, vendor_id=2, customer_id=3, quantity=1, amount=100, status="Cancelled", transaction_date=current),
                Transaction(transaction_id=105, product_id=12, vendor_id=1, customer_id=3, quantity=1, amount=50, status="Refunded", transaction_date=current),
            ])
            db.commit()

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    def _request(self, path, token=None):
        headers = self._headers(token) if token else None
        return run_async(asgi_request("GET", path, headers=headers))

    def test_admin_can_access_all_admin_revenue_endpoints_and_totals_reconcile(self):
        headers = self._headers(self.tokens["admin"])
        responses = {
            path: run_async(asgi_request("GET", path, headers=headers))
            for path in ADMIN_ENDPOINTS
        }
        for path, (status, body) in responses.items():
            self.assertEqual(status, 200, f"{path}: {body}")

        overview = responses[ADMIN_ENDPOINTS[0]][1]
        self.assertEqual(overview["gmv"], 70.0)
        self.assertEqual(overview["completed_revenue"], 70.0)
        self.assertEqual(overview["completed_transaction_records"], 3)
        self.assertIsNone(overview["total_orders"])
        self.assertIsNone(overview["average_order_value"])

        monthly = responses[ADMIN_ENDPOINTS[1]][1]["months"]
        self.assertEqual(sum(row["revenue"] for row in monthly), overview["completed_revenue"])
        vendors = responses[ADMIN_ENDPOINTS[2]][1]["vendors"]
        categories = responses[ADMIN_ENDPOINTS[3]][1]["categories"]
        products = responses[ADMIN_ENDPOINTS[4]][1]["products"]
        self.assertAlmostEqual(sum(row["revenue"] for row in vendors), 70.0)
        self.assertAlmostEqual(sum(row["revenue"] for row in categories), 70.0)
        self.assertAlmostEqual(sum(row["revenue"] for row in products), 70.0)

    def test_vendor_endpoints_stay_scoped_to_authenticated_vendor(self):
        responses = [self._request(path, self.tokens["vendor_one"]) for path in VENDOR_ENDPOINTS]
        for path, (status, body) in zip(VENDOR_ENDPOINTS, responses):
            self.assertEqual(status, 200, f"{path}: {body}")
        overview = responses[0][1]
        self.assertEqual(overview["completed_revenue"], 30.0)
        self.assertEqual(overview["completed_transaction_records"], 2)
        self.assertEqual(sum(row["revenue"] for row in responses[1][1]["months"]), 30.0)
        self.assertEqual(sum(row["revenue"] for row in responses[2][1]["categories"]), 30.0)
        self.assertEqual(sum(row["revenue"] for row in responses[3][1]["products"]), 30.0)
        self.assertNotIn("South Goods", str(responses))

    def test_customer_and_unauthenticated_access_are_denied(self):
        for path in ADMIN_ENDPOINTS + VENDOR_ENDPOINTS:
            status, body = self._request(path, self.tokens["customer"])
            self.assertEqual(status, 403, f"Customer {path}: {body}")
            status, body = self._request(path)
            self.assertEqual(status, 401, f"Anonymous {path}: {body}")

    def test_vendor_cannot_access_admin_analytics_and_admin_cannot_access_vendor_routes(self):
        for path in ADMIN_ENDPOINTS:
            status, body = self._request(path, self.tokens["vendor_one"])
            self.assertEqual(status, 403, f"Vendor {path}: {body}")
        for path in VENDOR_ENDPOINTS:
            status, body = self._request(path, self.tokens["admin"])
            self.assertEqual(status, 403, f"Admin {path}: {body}")

    def test_empty_data_and_zero_revenue_are_reported_without_fake_metrics(self):
        with self.Session() as db:
            db.query(Transaction).delete()
            db.commit()

        status, overview = self._request(ADMIN_ENDPOINTS[0], self.tokens["admin"])
        self.assertEqual(status, 200)
        self.assertEqual(overview["completed_revenue"], 0)
        self.assertEqual(overview["completed_transaction_records"], 0)
        self.assertIsNone(overview["average_transaction_value"])
        self.assertIsNone(overview["mom_revenue_growth_percentage"])
        self.assertEqual(self._request(ADMIN_ENDPOINTS[1], self.tokens["admin"])[1]["months"][-1]["revenue"], 0)

        with self.Session() as db:
            db.add(Transaction(transaction_id=201, product_id=11, vendor_id=1, customer_id=3,
                               quantity=1, amount=0, status="Completed", transaction_date=datetime.now()))
            db.commit()
        status, overview = self._request(ADMIN_ENDPOINTS[0], self.tokens["admin"])
        self.assertEqual(status, 200)
        self.assertEqual(overview["completed_transaction_records"], 1)
        self.assertEqual(overview["average_transaction_value"], 0)
        self.assertIsNone(overview["mom_revenue_growth_percentage"])


if __name__ == "__main__":
    unittest.main()
