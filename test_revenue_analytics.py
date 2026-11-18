"""Isolated analytics aggregation tests using synthetic in-memory SQLite data."""
import unittest
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import the application models so all foreign-key tables are registered.
from app.main import app  # noqa: F401
from app.database import Base
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.routes.analytics_routes import (
    admin_monthly_revenue,
    admin_revenue_overview,
    benchmark_categories,
    benchmark_products,
    benchmark_vendors,
    vendor_revenue_overview,
)


class TestRevenueAnalytics(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.add_all([
            Vendor(vendor_id=1, business_name="North Goods", owner_name="Owner 1", email="north@test.local", status="Active"),
            Vendor(vendor_id=2, business_name="South Goods", owner_name="Owner 2", email="south@test.local", status="Active"),
        ])
        self.db.flush()
        self.db.add_all([
            Product(product_id=11, vendor_id=1, product_name="Tea", category="Grocery", price=10),
            Product(product_id=12, vendor_id=1, product_name="Mug", category="Home", price=20),
            Product(product_id=21, vendor_id=2, product_name="Coffee", category="Grocery", price=15),
        ])
        self.db.flush()
        now = datetime.now()
        current_month = datetime(now.year, now.month, min(now.day, 20), 12)
        previous_month = datetime(now.year - (now.month == 1), 12 if now.month == 1 else now.month - 1, 15, 12)
        self.db.add_all([
            Transaction(transaction_id=101, product_id=11, vendor_id=1, quantity=2, amount=20, status="Completed", transaction_date=current_month),
            Transaction(transaction_id=102, product_id=12, vendor_id=1, quantity=1, amount=20, status="Completed", transaction_date=previous_month),
            Transaction(transaction_id=103, product_id=21, vendor_id=2, quantity=3, amount=45, status="Completed", transaction_date=current_month),
            Transaction(transaction_id=104, product_id=21, vendor_id=2, quantity=1, amount=15, status="Cancelled", transaction_date=current_month),
            Transaction(transaction_id=105, product_id=12, vendor_id=1, quantity=1, amount=20, status="Refunded", transaction_date=current_month),
        ])
        self.db.commit()
        self.admin = SimpleNamespace(role="Admin")
        self.vendor = SimpleNamespace(role="Vendor", vendor_id=1)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_admin_summary_excludes_cancelled_and_refunded(self):
        result = admin_revenue_overview(self.db, self.admin)
        self.assertEqual(result["completed_revenue"], 85.0)
        self.assertEqual(result["gmv"], 85.0)
        self.assertEqual(result["completed_transaction_records"], 3)
        self.assertIsNone(result["total_orders"])
        self.assertIsNone(result["average_order_value"])
        self.assertAlmostEqual(result["average_transaction_value"], 85 / 3)

    def test_vendor_overview_is_vendor_scoped(self):
        result = vendor_revenue_overview(self.db, self.vendor)
        self.assertEqual(result["completed_revenue"], 40.0)
        self.assertEqual(result["completed_transaction_records"], 2)

    def test_monthly_series_has_calendar_months_and_revenue(self):
        result = admin_monthly_revenue(months=2, db=self.db, admin=self.admin)
        self.assertEqual(len(result["months"]), 2)
        self.assertEqual([row["revenue"] for row in result["months"]], [20.0, 65.0])

    def test_benchmarking_aggregates_vendor_category_and_product_metrics(self):
        vendors = benchmark_vendors(limit=10, db=self.db, admin=self.admin)["vendors"]
        self.assertEqual(vendors[0]["business_name"], "South Goods")
        self.assertEqual(vendors[0]["revenue"], 45.0)
        self.assertEqual(vendors[0]["completed_transaction_records"], 1)
        categories = benchmark_categories(db=self.db, admin=self.admin)["categories"]
        grocery = next(item for item in categories if item["category"] == "Grocery")
        self.assertEqual(grocery["revenue"], 65.0)
        products = benchmark_products(limit=10, db=self.db, admin=self.admin)["products"]
        tea = next(item for item in products if item["product_name"] == "Tea")
        self.assertEqual(tea["units_sold"], 2)
        self.assertEqual(tea["revenue"], 20.0)


if __name__ == "__main__":
    unittest.main()
