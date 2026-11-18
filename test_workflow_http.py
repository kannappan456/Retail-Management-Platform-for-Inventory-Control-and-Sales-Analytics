"""HTTP-level role checks for Admin-only workflow management routes."""
import asyncio
import unittest
from unittest.mock import patch

from app.main import app
from app.models.user import User
from app.security import get_current_user
from app.workflow_scheduler import workflow_manager
from test_security_phase1 import asgi_request


class TestWorkflowAuthorizationHTTP(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def request(self, method, path, role=None):
        if role:
            app.dependency_overrides[get_current_user] = lambda: User(
                user_id=1,
                email=f"{role.lower()}@workflow-test.local",
                role=role,
                is_active=True,
            )
        headers = {"Authorization": "Bearer isolated-test"} if role else None
        return asyncio.run(asgi_request(method, path, headers=headers))

    def test_unauthenticated_customer_and_vendor_access_is_rejected(self):
        status_code, _ = self.request("GET", "/workflows/jobs")
        self.assertEqual(status_code, 401)
        for role in ("Customer", "Vendor"):
            status_code, _ = self.request("POST", "/workflows/jobs/inventory_demand_forecast/run", role)
            self.assertEqual(status_code, 403, role)

    def test_admin_can_list_jobs_and_request_a_manual_run(self):
        status_code, body = self.request("GET", "/workflows/jobs", "Admin")
        self.assertEqual(status_code, 200, body)
        self.assertEqual(len(body["jobs"]), 3)
        self.assertIn("scheduler", body)

        queued_job = {"job_id": "inventory_demand_forecast", "status": "queued"}
        with patch.object(workflow_manager, "trigger_manual", return_value=queued_job) as trigger:
            status_code, body = self.request(
                "POST", "/workflows/jobs/inventory_demand_forecast/run", "Admin"
            )
        self.assertEqual(status_code, 202, body)
        self.assertEqual(body["job"]["status"], "queued")
        trigger.assert_called_once_with("inventory_demand_forecast")


if __name__ == "__main__":
    unittest.main()
