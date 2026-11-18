"""MLflow file-store and registry tests with temporary local tracking stores."""
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.inventory.inventory_forecasting import forecast_demand
from app.mlflow_tracking import (
    get_experiment_run,
    list_experiment_runs,
    list_experiments,
    list_registered_models,
    log_workflow_run,
    tracking_status,
)
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vendor import Vendor


class TestMlflowTracking(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(
            prefix="shopsense-mlflow-", ignore_cleanup_errors=True
        )
        self.root = Path(self.tempdir.name)
        self.old_enabled = os.environ.get("MLFLOW_TRACKING_ENABLED")
        self.old_tracking = os.environ.get("MLFLOW_TRACKING_URI")
        self.old_registry = os.environ.get("MLFLOW_REGISTRY_URI")
        self.old_allow_file = os.environ.get("MLFLOW_ALLOW_FILE_STORE")
        os.environ["MLFLOW_TRACKING_ENABLED"] = "true"
        os.environ["MLFLOW_TRACKING_URI"] = (self.root / "file-store").as_uri()
        os.environ.pop("MLFLOW_REGISTRY_URI", None)
        os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"

    def tearDown(self):
        for key, value in (
            ("MLFLOW_TRACKING_ENABLED", self.old_enabled),
            ("MLFLOW_TRACKING_URI", self.old_tracking),
            ("MLFLOW_REGISTRY_URI", self.old_registry),
            ("MLFLOW_ALLOW_FILE_STORE", self.old_allow_file),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tempdir.cleanup()

    def test_file_store_experiment_runs_params_metrics_artifacts_and_registry_status(self):
        result = log_workflow_run(
            "inventory",
            "test-inventory-run",
            params={"forecast_horizon_days": 7, "api_token": "must-not-log"},
            metrics={"sample_metric": 1.25, "ignored_nan": float("nan")},
            evaluation_status="evaluated",
            evaluation_method="isolated test holdout",
            artifact={"forecast": [1, 2, 3]},
            model_type="test-heuristic",
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["status"], "logged")
        self.assertEqual(result["model_registry"]["status"], "not_applicable")

        experiment_response = list_experiments()
        experiment = next(
            item for item in experiment_response["experiments"]
            if item["name"] == "shopsense-inventory-demand-forecasting"
        )
        runs = list_experiment_runs(experiment["experiment_id"])
        run = next(item for item in runs["runs"] if item["run_id"] == result["run_id"])
        self.assertEqual(run["params"]["forecast_horizon_days"], "7")
        self.assertNotIn("api_token", run["params"])
        self.assertEqual(run["metrics"]["sample_metric"], 1.25)
        self.assertNotIn("ignored_nan", run["metrics"])
        self.assertEqual(get_experiment_run(result["run_id"])["run"]["run_id"], result["run_id"])

        import mlflow
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        artifacts = mlflow.tracking.MlflowClient().list_artifacts(result["run_id"])
        self.assertIn("shopsense_result.json", {item.path for item in artifacts})
        self.assertFalse(tracking_status()["registry_supported"])

    def test_insufficient_data_records_run_without_fabricated_metrics(self):
        result = log_workflow_run(
            "segmentation",
            "test-insufficient-segmentation",
            params={"customers_available": 2},
            metrics=None,
            evaluation_status="insufficient_data",
            evaluation_message="Two customers are below the required minimum.",
            artifact={"metrics": None},
            model_type="kmeans_customer_segmentation",
        )
        self.assertTrue(result["available"])
        run = get_experiment_run(result["run_id"])["run"]
        self.assertEqual(run["tags"]["evaluation.status"], "insufficient_data")
        self.assertEqual(run["metrics"], {})

    def test_disabled_mlflow_fails_open_for_existing_workflows(self):
        os.environ["MLFLOW_TRACKING_ENABLED"] = "false"
        status = tracking_status()
        self.assertFalse(status["available"])
        result = log_workflow_run("inventory", "tracking-disabled")
        self.assertFalse(result["available"])
        self.assertIsNone(result["run_id"])

    def test_missing_mlflow_package_fails_open_for_existing_workflows(self):
        with patch("app.mlflow_tracking.importlib.import_module", side_effect=ImportError):
            status = tracking_status()
            result = log_workflow_run("inventory", "tracking-package-missing")
        self.assertFalse(status["available"])
        self.assertFalse(result["available"])
        self.assertIsNone(result["run_id"])

    def test_inventory_forecast_logs_actual_holdout_metrics_without_changing_forecast(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            vendor = Vendor(
                business_name="Temporary test vendor",
                owner_name="Test owner",
                email="mlflow-forecast@example.test",
                status="Active",
            )
            db.add(vendor)
            db.flush()
            product = Product(
                vendor_id=vendor.vendor_id,
                product_name="Temporary test product",
                category="Test",
                price=10,
            )
            db.add(product)
            db.flush()
            db.add_all([
                Transaction(
                    product_id=product.product_id,
                    vendor_id=vendor.vendor_id,
                    quantity=2,
                    amount=20,
                    status="Completed",
                    transaction_date=datetime(2025, 1, 1),
                ),
                Transaction(
                    product_id=product.product_id,
                    vendor_id=vendor.vendor_id,
                    quantity=4,
                    amount=40,
                    status="Completed",
                    transaction_date=datetime(2025, 1, 2),
                ),
            ])
            db.commit()

            response = forecast_demand(
                User(user_id=1, email="admin@example.test", role="Admin", is_active=True),
                db,
            )

            self.assertEqual(response["forecasts"][0]["forecast_next_7_days"], 21)
            self.assertEqual(response["tracking"]["status"], "logged")
            run = get_experiment_run(response["tracking"]["run_id"])["run"]
            self.assertEqual(run["metrics"]["holdout_mae_units"], 2.0)
            self.assertEqual(run["metrics"]["holdout_rmse_units"], 2.0)
            self.assertEqual(run["metrics"]["products_evaluated"], 1.0)
        finally:
            db.close()
            Base.metadata.drop_all(engine)
            engine.dispose()

    def test_database_backend_supports_model_registry_and_versioning(self):
        database_path = (self.root / "registry.db").as_posix()
        sqlite_uri = f"sqlite:///{database_path}"
        os.environ["MLFLOW_TRACKING_URI"] = sqlite_uri
        os.environ["MLFLOW_REGISTRY_URI"] = sqlite_uri

        samples = [[0.0], [0.1], [10.0], [10.1]]
        model = KMeans(n_clusters=2, random_state=42, n_init=10).fit(samples)
        score = silhouette_score(samples, model.labels_)
        result = log_workflow_run(
            "segmentation",
            "test-registered-segmentation",
            params={"n_clusters": 2, "random_state": 42},
            metrics={"silhouette_score": score},
            evaluation_status="evaluated",
            artifact={"cluster_count": 2},
            sklearn_model=model,
            model_name="shopsense-customer-segmentation",
            model_type="test-kmeans",
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["model_registry"]["status"], "registered")
        self.assertEqual(result["model_registry"]["version"], "1")
        registry = list_registered_models()
        model_info = next(
            item for item in registry["models"]
            if item["name"] == "shopsense-customer-segmentation"
        ) if registry["models"] else None
        self.assertTrue(registry["registry_supported"])
        self.assertIsNotNone(model_info)
        self.assertEqual(str(model_info["versions"][0]["version"]), "1")


if __name__ == "__main__":
    unittest.main()
