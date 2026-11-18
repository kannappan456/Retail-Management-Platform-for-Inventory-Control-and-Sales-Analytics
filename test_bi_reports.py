"""Isolated SQLite tests for BI aggregation, file exports, and route security wiring."""
import os
import unittest
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vendor import Vendor
from app.reports.report_routes import bi_excel, bi_overview, bi_pdf
from app.reports.report_routes import router as bi_report_router
from app.security import require_admin


class TestBIReports(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.admin = SimpleNamespace(role="Admin", user_id=1)
        self.vendor = SimpleNamespace(role="Vendor", user_id=2)
        self.customer = SimpleNamespace(role="Customer", user_id=3)
        self._seed()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _seed(self):
        with self.Session() as db:
            db.add(Vendor(vendor_id=1, business_name="Isolated Vendor", owner_name="Owner", email="vendor@isolated.test", status="Active"))
            db.flush()
            db.add_all([
                User(user_id=1, email="admin@isolated.test", role="Admin", password_hash="unused", is_active=True),
                User(user_id=2, email="vendor-user@isolated.test", role="Vendor", vendor_id=1, password_hash="unused", is_active=True),
                User(user_id=3, email="private-customer@isolated.test", role="Customer", password_hash="unused", is_active=True),
            ])
            db.flush()
            db.add_all([
                Product(product_id=1, vendor_id=1, product_name="Isolated Tea", category="Grocery", price=12),
                Product(product_id=2, vendor_id=1, product_name="Isolated Cup", category="Home", price=30),
            ])
            db.flush()
            db.add_all([
                Inventory(product_id=1, current_stock=3, reorder_level=5, warehouse="North"),
                Inventory(product_id=2, current_stock=20, reorder_level=5, warehouse="South"),
            ])
            now = datetime.now()
            db.add_all([
                Transaction(transaction_id=1, product_id=1, vendor_id=1, customer_id=3, quantity=2, amount=24, status="Completed", transaction_date=now),
                Transaction(transaction_id=2, product_id=2, vendor_id=1, customer_id=3, quantity=1, amount=30, status="Completed", transaction_date=now),
                Transaction(transaction_id=3, product_id=1, vendor_id=1, customer_id=3, quantity=1, amount=12, status="Cancelled", transaction_date=now),
                Transaction(transaction_id=4, product_id=1, vendor_id=1, customer_id=3, quantity=1, amount=12, status="Refunded", transaction_date=now),
            ])
            db.commit()

    def test_admin_bi_overview_reconciles_completed_transactions_and_omits_pii(self):
        with patch.dict(os.environ, {"MLFLOW_TRACKING_ENABLED": "false"}):
            with self.Session() as db:
                body = bi_overview(months=2, db=db, admin=self.admin)
        self.assertEqual(body["marketplace"]["completed_revenue"], 54.0)
        self.assertEqual(body["marketplace"]["completed_transaction_records"], 2)
        self.assertEqual(sum(item["revenue"] for item in body["revenue"]["monthly"]), 54.0)
        self.assertEqual(body["vendors"][0]["revenue"], 54.0)
        self.assertEqual(sum(item["revenue"] for item in body["categories"]), 54.0)
        self.assertEqual(sum(item["revenue"] for item in body["products"]), 54.0)
        self.assertEqual(body["inventory"]["overview"]["total_stock_units"], 23)
        turnover_by_id = {
            item["product_id"]: item
            for item in body["inventory"]["turnover"]["products"]
        }
        self.assertEqual(turnover_by_id[1]["total_units_sold"], 2)
        self.assertEqual(turnover_by_id[1]["sales_to_current_stock_ratio"], 0.67)
        self.assertEqual(turnover_by_id[2]["total_units_sold"], 1)
        self.assertNotIn("customers", body["customers"]["summary"])
        self.assertNotIn("private-customer@isolated.test", str(body))

    def test_pdf_and_excel_generate_valid_files_and_expected_worksheets(self):
        with patch.dict(os.environ, {"MLFLOW_TRACKING_ENABLED": "false"}):
            with self.Session() as db:
                pdf_response = bi_pdf(months=2, db=db, admin=self.admin)
                excel_response = bi_excel(months=2, db=db, admin=self.admin)
        pdf_bytes = pdf_response.body
        excel_bytes = excel_response.body
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertEqual(pdf_response.media_type, "application/pdf")
        self.assertIn("attachment", pdf_response.headers["content-disposition"])
        self.assertEqual(excel_response.status_code, 200)
        self.assertIn("spreadsheetml", excel_response.media_type)
        self.assertIn("attachment", excel_response.headers["content-disposition"])
        workbook = load_workbook(BytesIO(excel_bytes), read_only=True)
        self.assertEqual(workbook.sheetnames, [
            "Marketplace Overview", "Monthly Revenue", "Vendor Performance",
            "Category Performance", "Product Performance", "Inventory Summary",
            "Customer Analytics", "Workflow History",
        ])
        values = " ".join(str(cell) for sheet in workbook for row in sheet.iter_rows(values_only=True) for cell in row if cell is not None)
        self.assertIn("Isolated Tea", values)
        self.assertNotIn("private-customer@isolated.test", values)
        workbook.close()

    def test_bi_routes_are_admin_gated_and_non_admin_roles_are_rejected(self):
        routes = list(bi_report_router.routes)
        self.assertEqual({route.path for route in routes}, {"/reports/bi/overview", "/reports/bi/pdf", "/reports/bi/excel"})
        for route in routes:
            self.assertIn(require_admin, [dependency.call for dependency in route.dependant.dependencies])
        self.assertIs(require_admin(current_user=self.admin), self.admin)
        for user in (self.vendor, self.customer):
            with self.assertRaises(HTTPException) as caught:
                require_admin(current_user=user)
            self.assertEqual(caught.exception.status_code, 403)

    def test_empty_marketplace_has_zero_totals_and_exportable_empty_sheets(self):
        with self.Session() as db:
            db.query(Transaction).delete()
            db.query(Inventory).delete()
            db.query(Product).delete()
            db.query(User).filter(User.role == "Vendor").update({User.vendor_id: None})
            db.query(Vendor).delete()
            db.commit()
            with patch.dict(os.environ, {"MLFLOW_TRACKING_ENABLED": "false"}):
                body = bi_overview(months=1, db=db, admin=self.admin)
                excel_response = bi_excel(months=1, db=db, admin=self.admin)
        self.assertEqual(body["marketplace"]["completed_revenue"], 0)
        self.assertEqual(body["marketplace"]["total_products"], 0)
        self.assertEqual(body["revenue"]["monthly"][-1]["revenue"], 0)
        self.assertEqual(body["products"], [])
        workbook = load_workbook(BytesIO(excel_response.body), read_only=True)
        self.assertIn("No data available", str(list(workbook["Product Performance"].values)))
        workbook.close()


if __name__ == "__main__":
    unittest.main()
