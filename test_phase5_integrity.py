"""Isolated SQLite regression checks for checkout and inventory aggregates."""
import unittest
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.database import Base
from app.inventory.category_management import get_categories, get_category_products
from app.inventory.inventory_turnover import get_inventory_turnover
from app.inventory.warehouse_management import assign_product_to_warehouse, get_warehouse_products, get_warehouses
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vendor import Vendor
from app.routes.analytics_routes import admin_revenue_overview
from app.routes.transaction_routes import CheckoutCreate, CheckoutItem, checkout
from app.routes.inventory_routes import get_product_availability
from app.workflow_scheduler import WorkflowJob, WorkflowManager


class TestPhase5IsolatedIntegrity(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.vendor = Vendor(vendor_id=1, business_name="Test Vendor", owner_name="Owner", email="test-vendor@shopsense.test", status="Active")
        self.db.add(self.vendor)
        self.db.flush()
        self.admin = User(user_id=1, email="admin@shopsense.test", password_hash="unused", role="Admin", is_active=True)
        self.customer = User(user_id=2, email="customer@shopsense.test", password_hash="unused", role="Customer", is_active=True)
        self.db.add_all([self.admin, self.customer])
        self.db.flush()
        self.products = [
            Product(product_id=1, vendor_id=1, product_name="Tea", category="Grocery", price=12),
            Product(product_id=2, vendor_id=1, product_name="Cup", category="Home", price=30),
        ]
        self.db.add_all(self.products)
        self.db.flush()
        self.db.add_all([
            Inventory(product_id=1, current_stock=5, reorder_level=2, warehouse="North"),
            Inventory(product_id=2, current_stock=0, reorder_level=2, warehouse="South"),
        ])
        now = datetime.now()
        self.db.add_all([
            Transaction(transaction_id=1, product_id=1, vendor_id=1, customer_id=2, quantity=2, amount=24, status="Completed", transaction_date=now),
            Transaction(transaction_id=2, product_id=1, vendor_id=1, customer_id=2, quantity=1, amount=12, status="Cancelled", transaction_date=now),
            Transaction(transaction_id=3, product_id=1, vendor_id=1, customer_id=2, quantity=1, amount=12, status="Refunded", transaction_date=now),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_turnover_uses_one_aggregate_query_and_only_completed_units(self):
        statements = []

        def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().lower().startswith("select"):
                statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            result = get_inventory_turnover(admin=self.admin, db=self.db)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)

        self.assertEqual(len(statements), 1)
        self.assertEqual(result["total_products"], 2)
        first, second = result["products"]
        self.assertEqual(first["total_units_sold"], 2)
        self.assertEqual(first["sales_to_current_stock_ratio"], 0.4)
        self.assertEqual(second["total_units_sold"], 0)
        self.assertIsNone(second["sales_to_current_stock_ratio"])

    def test_checkout_reduces_isolated_stock_and_revenue_matches_completed_rows(self):
        result = checkout(
            CheckoutCreate(items=[CheckoutItem(product_id=1, vendor_id=1, quantity=2)]),
            current_user=self.customer,
            db=self.db,
        )
        self.assertEqual(result["status"], "Completed")
        self.assertEqual(result["total_amount"], 24.0)
        inventory = self.db.query(Inventory).filter(Inventory.product_id == 1).one()
        self.assertEqual(inventory.current_stock, 3)
        self.db.refresh(inventory)
        overview = admin_revenue_overview(db=self.db, admin=self.admin)
        self.assertEqual(overview["completed_revenue"], 48.0)
        self.assertEqual(overview["completed_transaction_records"], 2)

    def test_customer_stock_availability_reports_live_isolated_quantity(self):
        available = get_product_availability(1, current_user=self.customer, db=self.db)
        self.assertEqual(available["current_stock"], 5)
        self.assertTrue(available["available_for_purchase"])

        zero_stock = get_product_availability(2, current_user=self.customer, db=self.db)
        self.assertEqual(zero_stock["current_stock"], 0)
        self.assertFalse(zero_stock["available_for_purchase"])

    def test_checkout_rejects_stock_that_changed_after_cart_load_without_writes(self):
        inventory = self.db.query(Inventory).filter(Inventory.product_id == 1).one()
        inventory.current_stock = 1
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            checkout(
                CheckoutCreate(items=[CheckoutItem(product_id=1, vendor_id=1, quantity=2)]),
                current_user=self.customer,
                db=self.db,
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Available: 1, requested: 2", raised.exception.detail)
        self.db.refresh(inventory)
        self.assertEqual(inventory.current_stock, 1)
        self.assertEqual(self.db.query(Transaction).count(), 3)

        inventory.current_stock = 0
        self.db.commit()
        with self.assertRaises(HTTPException) as zero_stock_error:
            checkout(
                CheckoutCreate(items=[CheckoutItem(product_id=1, vendor_id=1, quantity=1)]),
                current_user=self.customer,
                db=self.db,
            )
        self.assertIn("Available: 0, requested: 1", zero_stock_error.exception.detail)
        self.db.refresh(inventory)
        self.assertEqual(inventory.current_stock, 0)
        self.assertEqual(self.db.query(Transaction).count(), 3)

    def test_category_and_warehouse_views_reflect_isolated_inventory(self):
        categories = get_categories(admin=self.admin, db=self.db)
        self.assertEqual(categories["total_categories"], 2)
        groceries = get_category_products("Grocery", admin=self.admin, db=self.db)
        self.assertEqual(groceries["total_products"], 1)
        self.assertEqual(groceries["products"][0]["product_name"], "Tea")

        assignment = assign_product_to_warehouse(
            2, "Central", admin=self.admin, db=self.db
        )
        self.assertEqual(assignment["warehouse"], "Central")
        warehouses = get_warehouses(admin=self.admin, db=self.db)
        self.assertIn("Central", {item["warehouse"] for item in warehouses["warehouses"]})
        central = get_warehouse_products("Central", admin=self.admin, db=self.db)
        self.assertEqual(central["total_products"], 1)
        self.assertEqual(central["products"][0]["product_id"], 2)

    def test_workflow_records_database_session_failure_without_exposing_details(self):
        def broken_session_factory():
            raise RuntimeError("isolated database connection detail")

        job = WorkflowJob(
            job_id="db_failure",
            name="Database failure probe",
            description="Test only",
            interval_hours=6,
            minimum_interval_hours=6,
            handler=lambda _db: {"ok": True},
        )
        manager = WorkflowManager(session_factory=broken_session_factory, jobs=[job])
        try:
            result = manager.run_job("db_failure")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"], "Job execution failed. Check application logs for details.")
            self.assertNotIn("isolated database connection detail", str(manager.history()))
        finally:
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()
