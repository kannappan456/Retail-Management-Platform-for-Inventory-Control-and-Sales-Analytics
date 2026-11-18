"""HTTP-level authorization, stock-availability, and checkout checks on isolated SQLite data."""
import asyncio
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vendor import Vendor
from app.security import ALGORITHM, SECRET_KEY


class TestPhase5HTTP(unittest.TestCase):
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
        self._seed()
        self.tokens = {
            role: jwt.encode(
                {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                SECRET_KEY,
                algorithm=ALGORITHM,
            )
            for role, user_id in (("Admin", 1), ("Vendor", 2), ("Customer", 3))
        }

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _seed(self):
        with self.Session() as db:
            db.add(Vendor(vendor_id=1, business_name="HTTP Test Vendor", owner_name="Test Owner", email="vendor@shopsense-test.example.com", status="Active"))
            db.flush()
            db.add_all([
                User(user_id=1, email="admin@shopsense-test.example.com", password_hash="unused", role="Admin", is_active=True),
                User(user_id=2, email="vendor-user@shopsense-test.example.com", password_hash="unused", role="Vendor", vendor_id=1, is_active=True),
                User(user_id=3, email="customer@shopsense-test.example.com", password_hash="unused", role="Customer", is_active=True),
                User(user_id=4, email="other-customer@shopsense-test.example.com", password_hash="unused", role="Customer", is_active=True),
            ])
            db.flush()
            db.add(Product(product_id=1, vendor_id=1, product_name="HTTP Test Product", category="Grocery", price=10))
            db.flush()
            db.add(Inventory(product_id=1, current_stock=10, reorder_level=2, warehouse="Isolated"))
            db.add(Transaction(transaction_id=1, product_id=1, vendor_id=1, customer_id=3, quantity=1, amount=10, status="Completed", transaction_date=datetime.now()))
            db.add(Transaction(transaction_id=2, product_id=1, vendor_id=1, customer_id=4, quantity=2, amount=20, status="Completed", transaction_date=datetime.now()))
            db.commit()

    async def _request(self, method, path, token=None, body=None):
        raw_body = json.dumps(body).encode() if body is not None else b""
        headers = []
        if token:
            headers.append((b"authorization", f"Bearer {token}".encode()))
        if raw_body:
            headers.append((b"content-type", b"application/json"))
            headers.append((b"content-length", str(len(raw_body)).encode()))
        path_part, _, query = path.partition("?")
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path_part,
            "raw_path": path_part.encode(), "query_string": query.encode(),
            "headers": headers, "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
        }
        response = {"status": None, "headers": [], "body": []}
        request_sent = False
        response_complete = asyncio.Event()

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": raw_body, "more_body": False}
            await response_complete.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
                response["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response["body"].append(message.get("body", b""))
                if not message.get("more_body", False):
                    response_complete.set()

        await app(scope, receive, send)
        response["headers"] = dict(response["headers"])
        response["body"] = b"".join(response["body"])
        return response

    def request(self, method, path, role=None, body=None):
        token = self.tokens.get(role) if role else None
        return asyncio.run(self._request(method, path, token, body))

    def test_admin_can_retrieve_bi_mlflow_and_workflow_data(self):
        with patch.dict(os.environ, {"MLFLOW_TRACKING_ENABLED": "false"}):
            for path in (
                "/reports/bi/overview", "/mlflow/status", "/workflows/jobs",
                "/inventory-analytics/overview", "/inventory-forecast/demand",
                "/inventory-turnover/", "/warehouse/", "/categories/",
                "/customer-analytics/overview", "/customer-analytics/segments",
            ):
                response = self.request("GET", path, "Admin")
                self.assertEqual(response["status"], 200, f"{path}: {response['body']!r}")
            evaluation = self.request("GET", "/recommendations/evaluation", "Admin")
        self.assertEqual(evaluation["status"], 200)
        self.assertIsNone(json.loads(evaluation["body"])["metrics"])

    def test_vendor_customer_and_anonymous_are_denied_admin_routes(self):
        admin_paths = (
            "/reports/bi/overview", "/reports/bi/pdf", "/reports/bi/excel",
            "/mlflow/status", "/workflows/jobs", "/inventory-analytics/overview",
            "/analytics/revenue/overview", "/recommendations/evaluation",
            "/inventory-forecast/demand", "/customer-analytics/overview",
            "/customer-analytics/segments", "/inventory-turnover/",
            "/warehouse/", "/categories/",
        )
        for path in admin_paths:
            for role in ("Vendor", "Customer"):
                self.assertEqual(self.request("GET", path, role)["status"], 403, f"{role} {path}")
            self.assertEqual(self.request("GET", path)["status"], 401, f"Anonymous {path}")

    def test_customer_only_recommendations_reject_other_roles(self):
        with patch.dict(os.environ, {"MLFLOW_TRACKING_ENABLED": "false"}):
            customer_response = self.request("GET", "/recommendations/", "Customer")
            self.assertEqual(customer_response["status"], 200)
            self.assertEqual(json.loads(customer_response["body"])["recommendation_type"], "general")
            self.assertEqual(self.request("GET", "/recommendations/", "Vendor")["status"], 403)
            self.assertEqual(self.request("GET", "/recommendations/", "Admin")["status"], 403)
            self.assertEqual(self.request("GET", "/recommendations/")["status"], 401)

    def test_customer_history_is_scoped_to_authenticated_customer(self):
        customer_response = self.request("GET", "/transactions/mine", "Customer")
        self.assertEqual(customer_response["status"], 200)
        body = json.loads(customer_response["body"])
        self.assertEqual(body["total_transactions"], 1)
        self.assertEqual(body["transactions"][0]["amount"], 10.0)
        for role in ("Admin", "Vendor"):
            self.assertEqual(self.request("GET", "/transactions/mine", role)["status"], 403)
        self.assertEqual(self.request("GET", "/transactions/mine")["status"], 401)

    def test_admin_pdf_and_excel_endpoints_return_download_files(self):
        with patch.dict(os.environ, {"MLFLOW_TRACKING_ENABLED": "false"}):
            pdf = self.request("GET", "/reports/bi/pdf?months=2", "Admin")
            excel = self.request("GET", "/reports/bi/excel?months=2", "Admin")
        self.assertEqual(pdf["status"], 200)
        self.assertTrue(pdf["body"].startswith(b"%PDF-"))
        self.assertIn(b"attachment", pdf["headers"][b"content-disposition"])
        self.assertEqual(excel["status"], 200)
        self.assertTrue(excel["body"].startswith(b"PK"))
        self.assertIn(b"attachment", excel["headers"][b"content-disposition"])


    # ------------------------------------------------------------------ #
    # Stock-availability endpoint tests                                    #
    # ------------------------------------------------------------------ #

    def test_customer_can_check_in_stock_product_availability(self):
        """Product 1 has 10 units; customer should see it as available."""
        response = self.request("GET", "/inventory/1/availability", "Customer")
        self.assertEqual(response["status"], 200, response["body"])
        body = json.loads(response["body"])
        self.assertEqual(body["product_id"], 1)
        self.assertGreater(body["current_stock"], 0)
        self.assertTrue(body["available_for_purchase"])

    def test_customer_can_check_zero_stock_product(self):
        """A product with zero stock must report available_for_purchase=False."""
        # Set product 1 stock to zero via the isolated DB session.
        with self.Session() as db:
            inv = db.query(Inventory).filter(Inventory.product_id == 1).first()
            inv.current_stock = 0
            db.commit()

        response = self.request("GET", "/inventory/1/availability", "Customer")
        self.assertEqual(response["status"], 200, response["body"])
        body = json.loads(response["body"])
        self.assertEqual(body["current_stock"], 0)
        self.assertFalse(body["available_for_purchase"])

    def test_availability_returns_404_for_missing_product(self):
        """An unknown product_id must return 404."""
        response = self.request("GET", "/inventory/9999/availability", "Customer")
        self.assertEqual(response["status"], 404)

    def test_non_customer_roles_cannot_access_availability_endpoint(self):
        """Admin and Vendor must receive 403; anonymous must receive 401."""
        self.assertEqual(self.request("GET", "/inventory/1/availability", "Admin")["status"], 403)
        self.assertEqual(self.request("GET", "/inventory/1/availability", "Vendor")["status"], 403)
        self.assertEqual(self.request("GET", "/inventory/1/availability")["status"], 401)

    # ------------------------------------------------------------------ #
    # Checkout transaction tests                                           #
    # ------------------------------------------------------------------ #

    def test_checkout_succeeds_for_in_stock_product(self):
        """Normal checkout with sufficient stock must return 201."""
        payload = {"items": [{"product_id": 1, "vendor_id": 1, "quantity": 2}]}
        response = self.request("POST", "/transactions/checkout", "Customer", payload)
        self.assertEqual(response["status"], 201, response["body"])
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "Completed")
        self.assertIn("checkout_reference", body)
        # Stock should have decreased by 2 (started at 10).
        with self.Session() as db:
            inv = db.query(Inventory).filter(Inventory.product_id == 1).first()
            self.assertEqual(inv.current_stock, 8)

    def test_checkout_rejected_for_zero_stock(self):
        """Checkout when stock is 0 must return 400."""
        with self.Session() as db:
            inv = db.query(Inventory).filter(Inventory.product_id == 1).first()
            inv.current_stock = 0
            db.commit()

        payload = {"items": [{"product_id": 1, "vendor_id": 1, "quantity": 1}]}
        response = self.request("POST", "/transactions/checkout", "Customer", payload)
        self.assertEqual(response["status"], 400, response["body"])
        detail = json.loads(response["body"])["detail"]
        self.assertIn("stock", detail.lower())

    def test_checkout_rejected_when_quantity_exceeds_stock(self):
        """Requesting more than available stock must return 400."""
        payload = {"items": [{"product_id": 1, "vendor_id": 1, "quantity": 100}]}
        response = self.request("POST", "/transactions/checkout", "Customer", payload)
        self.assertEqual(response["status"], 400, response["body"])
        detail = json.loads(response["body"])["detail"]
        self.assertIn("stock", detail.lower())

    def test_checkout_rejected_when_stock_drops_between_add_and_place(self):
        """
        Simulate a race: availability check shows 5 units; by checkout time
        another process depletes the stock.  Backend must still reject.
        """
        # Set stock to 1 so a quantity-of-5 request is refused.
        with self.Session() as db:
            inv = db.query(Inventory).filter(Inventory.product_id == 1).first()
            inv.current_stock = 1
            db.commit()

        payload = {"items": [{"product_id": 1, "vendor_id": 1, "quantity": 5}]}
        response = self.request("POST", "/transactions/checkout", "Customer", payload)
        self.assertEqual(response["status"], 400, response["body"])

    def test_checkout_with_multiple_items_fails_if_one_is_unavailable(self):
        """
        Cart with two products where product 2 has zero stock:
        the whole checkout must be rejected atomically.
        """
        # Add a second product with no stock.
        with self.Session() as db:
            db.add(Product(product_id=2, vendor_id=1, product_name="Zero Stock Product", category="Test", price=5))
            db.flush()
            db.add(Inventory(product_id=2, current_stock=0, reorder_level=1))
            db.commit()

        payload = {"items": [
            {"product_id": 1, "vendor_id": 1, "quantity": 1},
            {"product_id": 2, "vendor_id": 1, "quantity": 1},
        ]}
        response = self.request("POST", "/transactions/checkout", "Customer", payload)
        self.assertEqual(response["status"], 400, response["body"])
        # Product 1 stock must be unchanged (transaction rolled back).
        with self.Session() as db:
            inv = db.query(Inventory).filter(Inventory.product_id == 1).first()
            self.assertEqual(inv.current_stock, 10)

    def test_checkout_with_all_in_stock_items_completes(self):
        """
        Cart with two products both in stock must complete
        and reduce both inventories correctly.
        """
        with self.Session() as db:
            db.add(Product(product_id=3, vendor_id=1, product_name="Second In-Stock Product", category="Test", price=20))
            db.flush()
            db.add(Inventory(product_id=3, current_stock=5, reorder_level=1))
            db.commit()

        payload = {"items": [
            {"product_id": 1, "vendor_id": 1, "quantity": 3},
            {"product_id": 3, "vendor_id": 1, "quantity": 2},
        ]}
        response = self.request("POST", "/transactions/checkout", "Customer", payload)
        self.assertEqual(response["status"], 201, response["body"])
        with self.Session() as db:
            inv1 = db.query(Inventory).filter(Inventory.product_id == 1).first()
            inv3 = db.query(Inventory).filter(Inventory.product_id == 3).first()
            self.assertEqual(inv1.current_stock, 7)
            self.assertEqual(inv3.current_stock, 3)

    def test_backend_rejects_checkout_from_non_customer(self):
        """Admin and Vendor accounts must not be able to place orders."""
        payload = {"items": [{"product_id": 1, "vendor_id": 1, "quantity": 1}]}
        self.assertEqual(
            self.request("POST", "/transactions/checkout", "Admin", payload)["status"], 403
        )
        self.assertEqual(
            self.request("POST", "/transactions/checkout", "Vendor", payload)["status"], 403
        )
        self.assertEqual(
            self.request("POST", "/transactions/checkout", None, payload)["status"], 401
        )

    # ------------------------------------------------------------------ #
    # Vendor orders endpoint tests                                         #
    # ------------------------------------------------------------------ #

    def test_vendor_can_view_own_orders(self):
        """Vendor must see only orders for their own products."""
        response = self.request("GET", "/transactions/vendor-orders", "Vendor")
        self.assertEqual(response["status"], 200, response["body"])
        body = json.loads(response["body"])
        self.assertIn("orders", body)
        # Seed created 2 transactions for vendor_id=1; both should be visible.
        self.assertEqual(body["total_orders"], 2)
        # Every returned order must reference vendor's product.
        for order in body["orders"]:
            self.assertEqual(order["product_id"], 1)

    def test_non_vendor_cannot_access_vendor_orders(self):
        """Customer, Admin, and anonymous must all be rejected."""
        self.assertEqual(self.request("GET", "/transactions/vendor-orders", "Customer")["status"], 403)
        self.assertEqual(self.request("GET", "/transactions/vendor-orders", "Admin")["status"], 403)
        self.assertEqual(self.request("GET", "/transactions/vendor-orders")["status"], 401)

    # ------------------------------------------------------------------ #
    # Customer profile update tests                                        #
    # ------------------------------------------------------------------ #

    def test_customer_can_fetch_own_profile(self):
        """GET /auth/me must return the customer's email and role."""
        response = self.request("GET", "/auth/me", "Customer")
        self.assertEqual(response["status"], 200, response["body"])
        body = json.loads(response["body"])
        self.assertEqual(body["email"], "customer@shopsense-test.example.com")
        self.assertEqual(body["role"], "Customer")

    def test_customer_can_update_email(self):
        """PATCH /auth/me with a new email must succeed and persist the change."""
        payload = {"email": "updated-customer@shopsense-test.example.com"}
        response = self.request("PATCH", "/auth/me", "Customer", payload)
        self.assertEqual(response["status"], 200, response["body"])
        body = json.loads(response["body"])
        self.assertEqual(body["email"], "updated-customer@shopsense-test.example.com")
        self.assertIn("email", body["message"])

    def test_profile_update_rejects_duplicate_email(self):
        """Cannot change email to one already in use by another account."""
        payload = {"email": "other-customer@shopsense-test.example.com"}
        response = self.request("PATCH", "/auth/me", "Customer", payload)
        self.assertEqual(response["status"], 409, response["body"])

    def test_profile_update_requires_current_password_for_password_change(self):
        """Attempting to set a new password without current_password returns 400."""
        payload = {"new_password": "NewSecure99!"}
        response = self.request("PATCH", "/auth/me", "Customer", payload)
        self.assertEqual(response["status"], 400, response["body"])

    def test_profile_update_no_changes_returns_success(self):
        """Sending an empty payload must return 200 with a no-changes message."""
        response = self.request("PATCH", "/auth/me", "Customer", {})
        self.assertEqual(response["status"], 200, response["body"])
        body = json.loads(response["body"])
        self.assertIn("No changes", body["message"])

    def test_anonymous_cannot_access_profile_endpoints(self):
        """Profile endpoints require authentication."""
        self.assertEqual(self.request("GET", "/auth/me")["status"], 401)
        self.assertEqual(self.request("PATCH", "/auth/me", None, {})["status"], 401)


if __name__ == "__main__":
    unittest.main()
