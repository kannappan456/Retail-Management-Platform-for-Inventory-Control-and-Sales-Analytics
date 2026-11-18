import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
import pandas as pd

from app.database import Base
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vendor import Vendor
from app.customer.segmentation import customer_segments


class CustomerSegmentationTests(unittest.TestCase):
    """Exercise segmentation on an isolated in-memory SQLite database."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            autocommit=False,
        )

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.create_all(self.engine)
        self.db = self.Session()
        self.vendor = Vendor(
            business_name="Segmentation Test Vendor",
            owner_name="Test Owner",
            email="segmentation-vendor@example.com",
            status="Active",
        )
        self.db.add(self.vendor)
        self.db.flush()

        self.product = Product(
            vendor_id=self.vendor.vendor_id,
            product_name="Segmentation Test Product",
            category="Test",
            price=Decimal("10.00"),
        )
        self.db.add(self.product)
        self.db.flush()
        self.admin = User(
            email="segmentation-admin@example.com",
            password_hash="test-only",
            role="Admin",
            is_active=True,
        )

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def add_customer_with_orders(self, number, total_spent, order_count):
        customer = User(
            email=f"segmentation-customer-{number}@example.com",
            password_hash="test-only",
            role="Customer",
            is_active=True,
        )
        self.db.add(customer)
        self.db.flush()

        order_amount = Decimal(str(total_spent)) / order_count
        for _ in range(order_count):
            self.db.add(Transaction(
                product_id=self.product.product_id,
                vendor_id=self.vendor.vendor_id,
                customer_id=customer.user_id,
                quantity=1,
                amount=order_amount,
                status="Completed",
            ))
        return customer

    def test_returns_cluster_assignments_and_valid_silhouette_score(self):
        profiles = [
            (10, 1), (12, 2), (14, 1),
            (99, 3), (108, 4), (120, 5),
        ]
        customers = [
            self.add_customer_with_orders(index, spent, orders)
            for index, (spent, orders) in enumerate(profiles, start=1)
        ]
        self.db.commit()

        result = customer_segments(self.admin, self.db)

        self.assertEqual(result["algorithm"], "K-Means")
        self.assertEqual(result["customers_available"], len(customers))
        self.assertGreaterEqual(result["optimal_clusters"], 2)
        self.assertGreaterEqual(len(result["segments"]), 2)

        cluster_for_customer = {}
        for segment in result["segments"]:
            self.assertEqual(
                segment["customer_count"],
                len(segment["customers"]),
            )
            for customer in segment["customers"]:
                cluster_for_customer[customer["customer_id"]] = segment["cluster_id"]

        self.assertEqual(len(cluster_for_customer), len(customers))
        self.assertEqual(
            sum(segment["customer_count"] for segment in result["segments"]),
            len(customers),
        )

        features = pd.DataFrame([
            {
                "customer_id": customer.user_id,
                "total_spent": float(total_spent),
                "total_orders": order_count,
                "average_order_value": float(total_spent) / order_count,
            }
            for customer, (total_spent, order_count) in zip(customers, profiles)
        ]).set_index("customer_id")
        scaled_features = StandardScaler().fit_transform(features)
        labels = [cluster_for_customer[customer.user_id] for customer in customers]
        expected_score = round(float(silhouette_score(scaled_features, labels)), 4)

        self.assertIsNotNone(result["silhouette_score"])
        self.assertAlmostEqual(result["silhouette_score"], expected_score, places=4)

    def test_insufficient_customer_data_still_returns_no_clusters(self):
        for index, (spent, orders) in enumerate([(20, 1), (30, 2)], start=1):
            self.add_customer_with_orders(index, spent, orders)
        self.db.commit()

        result = customer_segments(self.admin, self.db)

        self.assertEqual(result["customers_available"], 2)
        self.assertEqual(result["minimum_customers_required"], 3)
        self.assertIsNone(result["silhouette_score"])
        self.assertEqual(result["segments"], [])


if __name__ == "__main__":
    unittest.main()
