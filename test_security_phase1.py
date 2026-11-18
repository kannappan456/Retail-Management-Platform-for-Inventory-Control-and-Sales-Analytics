import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from app.main import app
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.auth_schema import RegisterRequest
from app.security import (
    require_admin,
    require_vendor,
    require_customer,
    get_current_user,
    SECRET_KEY,
    ALGORITHM
)
from app.database import get_db
from jose import jwt

# Helper to send requests directly into FastAPI via ASGI
async def asgi_request(method, path, headers=None, body=b''):
    """Minimal in-process HTTP client; signals disconnect after response completion."""
    headers_list = []
    if headers:
        for k, v in headers.items():
            headers_list.append((k.lower().encode('utf-8'), v.encode('utf-8')))
    
    query_string = b''
    if '?' in path:
        path_part, query_part = path.split('?', 1)
        path = path_part
        query_string = query_part.encode('utf-8')

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': method,
        'scheme': 'http',
        'path': path,
        'raw_path': path.encode('utf-8'),
        'query_string': query_string,
        'headers': headers_list,
        'client': ('127.0.0.1', 12345),
        'server': ('127.0.0.1', 8000),
    }
    
    response_headers = []
    status_code = None
    response_body = []
    request_sent = False
    response_complete = asyncio.Event()
    
    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await response_complete.wait()
        return {'type': 'http.disconnect'}
        
    async def send(message):
        nonlocal status_code, response_headers
        if message['type'] == 'http.response.start':
            status_code = message['status']
            response_headers = message['headers']
        elif message['type'] == 'http.response.body':
            response_body.append(message.get('body', b''))
            if not message.get('more_body', False):
                response_complete.set()
            
    await app(scope, receive, send)
    
    body_text = b''.join(response_body).decode('utf-8')
    try:
        data = json.loads(body_text)
    except:
        data = body_text
        
    return status_code, data


def run_async(coro):
    return asyncio.run(coro)


class TestSecurityPhase1(unittest.TestCase):
    def setUp(self):
        # Create mock users
        self.admin_user = User(
            user_id=1,
            email="admin_test@shopsense.com",
            role="Admin",
            is_active=True
        )
        self.customer_user = User(
            user_id=2,
            email="customer_test@shopsense.com",
            role="Customer",
            is_active=True
        )
        self.vendor_user = User(
            user_id=3,
            email="vendor_test@shopsense.com",
            role="Vendor",
            vendor_id=1,
            is_active=True
        )

        self.admin_token = jwt.encode(
            {"sub": "1", "role": "Admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=60)},
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        self.customer_token = jwt.encode(
            {"sub": "2", "role": "Customer", "exp": datetime.now(timezone.utc) + timedelta(minutes=60)},
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        self.vendor_token = jwt.encode(
            {"sub": "3", "role": "Vendor", "exp": datetime.now(timezone.utc) + timedelta(minutes=60)},
            SECRET_KEY,
            algorithm=ALGORITHM
        )

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_unauthenticated_admin_endpoints(self):
        """All protected admin endpoints must return 401 when no token is supplied."""
        endpoints = [
            ("GET", "/customer-analytics/overview"),
            ("GET", "/customer-analytics/top-customers"),
            ("GET", "/customer-analytics/segments"),
            ("GET", "/categories/"),
            ("GET", "/categories/Electronics/products"),
            ("GET", "/inventory-forecast/demand"),
            ("GET", "/inventory-analytics/overview"),
            ("GET", "/inventory-analytics/low-stock"),
            ("GET", "/inventory-analytics/vendor-summary"),
            ("GET", "/inventory-turnover/"),
            ("GET", "/stock-alerts/"),
            ("GET", "/warehouse/"),
            ("GET", "/warehouse/North/products"),
            ("PATCH", "/warehouse/1/assign?warehouse_name=Central"),
            ("GET", "/recommendations/evaluation"),
            ("GET", "/analytics/revenue/overview"),
            ("GET", "/analytics/revenue/monthly?months=2"),
            ("GET", "/analytics/benchmarking/vendors"),
            ("GET", "/analytics/benchmarking/categories"),
            ("GET", "/analytics/benchmarking/products"),
            ("GET", "/analytics/vendor/revenue/overview"),
            ("GET", "/analytics/vendor/revenue/monthly?months=2"),
            ("GET", "/analytics/vendor/revenue/categories"),
            ("GET", "/analytics/vendor/revenue/products"),
        ]

        for method, endpoint in endpoints:
            status, data = run_async(asgi_request(method, endpoint))
            self.assertEqual(
                status, 401,
                f"Endpoint {method} {endpoint} expected 401 unauthenticated, got {status} ({data})"
            )

    def test_customer_access_to_admin_endpoints_denied(self):
        """Customer role must be denied (HTTP 403) from all protected admin endpoints."""
        app.dependency_overrides[get_current_user] = lambda: self.customer_user

        headers = {"Authorization": f"Bearer {self.customer_token}"}
        endpoints = [
            ("GET", "/customer-analytics/overview"),
            ("GET", "/customer-analytics/top-customers"),
            ("GET", "/customer-analytics/segments"),
            ("GET", "/categories/"),
            ("GET", "/categories/Electronics/products"),
            ("GET", "/inventory-forecast/demand"),
            ("GET", "/inventory-analytics/overview"),
            ("GET", "/inventory-analytics/low-stock"),
            ("GET", "/inventory-analytics/vendor-summary"),
            ("GET", "/inventory-turnover/"),
            ("GET", "/stock-alerts/"),
            ("GET", "/warehouse/"),
            ("GET", "/warehouse/North/products"),
            ("PATCH", "/warehouse/1/assign?warehouse_name=Central"),
            ("GET", "/recommendations/evaluation"),
            ("GET", "/analytics/revenue/overview"),
            ("GET", "/analytics/revenue/monthly?months=2"),
            ("GET", "/analytics/benchmarking/vendors"),
            ("GET", "/analytics/benchmarking/categories"),
            ("GET", "/analytics/benchmarking/products"),
            ("GET", "/analytics/vendor/revenue/overview"),
            ("GET", "/analytics/vendor/revenue/monthly?months=2"),
            ("GET", "/analytics/vendor/revenue/categories"),
            ("GET", "/analytics/vendor/revenue/products"),
        ]

        for method, endpoint in endpoints:
            status, data = run_async(asgi_request(method, endpoint, headers=headers))
            self.assertEqual(
                status, 403,
                f"Endpoint {method} {endpoint} expected 403 for Customer, got {status} ({data})"
            )

    def test_vendor_access_to_admin_endpoints_denied(self):
        """Vendor role must be denied (HTTP 403) from all protected admin endpoints."""
        app.dependency_overrides[get_current_user] = lambda: self.vendor_user

        headers = {"Authorization": f"Bearer {self.vendor_token}"}
        endpoints = [
            ("GET", "/customer-analytics/overview"),
            ("GET", "/customer-analytics/top-customers"),
            ("GET", "/customer-analytics/segments"),
            ("GET", "/categories/"),
            ("GET", "/categories/Electronics/products"),
            ("GET", "/inventory-forecast/demand"),
            ("GET", "/inventory-analytics/overview"),
            ("GET", "/inventory-analytics/low-stock"),
            ("GET", "/inventory-analytics/vendor-summary"),
            ("GET", "/inventory-turnover/"),
            ("GET", "/stock-alerts/"),
            ("GET", "/warehouse/"),
            ("GET", "/warehouse/North/products"),
            ("PATCH", "/warehouse/1/assign?warehouse_name=Central"),
            ("GET", "/recommendations/evaluation"),
            ("GET", "/analytics/revenue/overview"),
            ("GET", "/analytics/revenue/monthly?months=2"),
            ("GET", "/analytics/benchmarking/vendors"),
            ("GET", "/analytics/benchmarking/categories"),
            ("GET", "/analytics/benchmarking/products"),
        ]

        for method, endpoint in endpoints:
            status, data = run_async(asgi_request(method, endpoint, headers=headers))
            self.assertEqual(
                status, 403,
                f"Endpoint {method} {endpoint} expected 403 for Vendor, got {status} ({data})"
            )

    def test_admin_access_allowed_to_admin_endpoints(self):
        """Admin role must successfully pass role guard on admin endpoints (does not return 401 or 403)."""
        app.dependency_overrides[get_current_user] = lambda: self.admin_user

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        endpoints = [
            ("GET", "/customer-analytics/overview"),
            ("GET", "/customer-analytics/top-customers"),
            ("GET", "/categories/"),
            ("GET", "/inventory-analytics/overview"),
            ("GET", "/inventory-analytics/low-stock"),
            ("GET", "/inventory-analytics/vendor-summary"),
            ("GET", "/stock-alerts/"),
            ("GET", "/warehouse/"),
            ("GET", "/analytics/revenue/overview"),
            ("GET", "/analytics/revenue/monthly?months=2"),
            ("GET", "/analytics/benchmarking/vendors"),
            ("GET", "/analytics/benchmarking/categories"),
            ("GET", "/analytics/benchmarking/products"),
        ]

        for method, endpoint in endpoints:
            status, data = run_async(asgi_request(method, endpoint, headers=headers))
            self.assertNotIn(
                status, [401, 403],
                f"Endpoint {method} {endpoint} should allow Admin, but got {status} ({data})"
            )

    def test_customer_recommendations_allowed(self):
        """Customer accessing /recommendations/ is allowed (returns 200, not 401 or 403)."""
        app.dependency_overrides[get_current_user] = lambda: self.customer_user
        headers = {"Authorization": f"Bearer {self.customer_token}"}

        status, data = run_async(asgi_request("GET", "/recommendations/", headers=headers))
        self.assertNotIn(status, [401, 403], f"Customer should be allowed on /recommendations/, got {status}")

    def test_admin_cannot_access_vendor_revenue_endpoints(self):
        """Vendor revenue endpoints must reject Admin role as well as other roles."""
        app.dependency_overrides[get_current_user] = lambda: self.admin_user
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        endpoints = [
            "/analytics/vendor/revenue/overview",
            "/analytics/vendor/revenue/monthly?months=2",
            "/analytics/vendor/revenue/categories",
            "/analytics/vendor/revenue/products",
        ]
        for endpoint in endpoints:
            status, data = run_async(asgi_request("GET", endpoint, headers=headers))
            self.assertEqual(status, 403, f"Admin must be denied at {endpoint}: {data}")

    def test_vendor_can_access_vendor_revenue_endpoints(self):
        """Vendor endpoints accept Vendor role and retain their vendor-scoped handlers."""
        app.dependency_overrides[get_current_user] = lambda: self.vendor_user
        headers = {"Authorization": f"Bearer {self.vendor_token}"}
        endpoints = [
            "/analytics/vendor/revenue/overview",
            "/analytics/vendor/revenue/monthly?months=2",
            "/analytics/vendor/revenue/categories",
            "/analytics/vendor/revenue/products",
        ]
        for endpoint in endpoints:
            status, data = run_async(asgi_request("GET", endpoint, headers=headers))
            self.assertNotIn(status, [401, 403], f"Vendor should be allowed at {endpoint}: {data}")

    def test_admin_recommendations_denied(self):
        """Admin accessing /recommendations/ is denied with 403 (Customer access required)."""
        app.dependency_overrides[get_current_user] = lambda: self.admin_user
        headers = {"Authorization": f"Bearer {self.admin_token}"}

        status, data = run_async(asgi_request("GET", "/recommendations/", headers=headers))
        self.assertEqual(status, 403, f"Admin should be denied on /recommendations/, got {status}")

    def test_public_registration_admin_rejected(self):
        """Public registration attempting role='Admin' must be rejected (422 Pydantic or 400)."""
        body = json.dumps({
            "email": "hacker@test.com",
            "password": "Password123!",
            "role": "Admin"
        }).encode('utf-8')

        headers = {"Content-Type": "application/json"}
        status, data = run_async(asgi_request("POST", "/auth/register", headers=headers, body=body))
        self.assertIn(status, [400, 422], f"Admin registration should be rejected with 400 or 422, got {status}: {data}")

    def test_public_registration_customer_accepted_schema(self):
        """Valid customer registration payload parses through schema validation."""
        payload = {
            "email": "newcustomer@test.com",
            "password": "StrongPassword123!",
            "role": "Customer"
        }
        req = RegisterRequest(**payload)
        self.assertEqual(req.role, "Customer")

    def test_public_registration_vendor_accepted_schema(self):
        """Valid vendor registration payload parses through schema validation and preserves vendor fields."""
        payload = {
            "email": "newvendor@test.com",
            "password": "StrongPassword123!",
            "role": "Vendor",
            "business_name": "Acme Corp",
            "owner_name": "John Doe",
            "phone": "9876543210",
            "category": "Electronics"
        }
        req = RegisterRequest(**payload)
        self.assertEqual(req.role, "Vendor")
        self.assertEqual(req.business_name, "Acme Corp")


if __name__ == "__main__":
    unittest.main()
