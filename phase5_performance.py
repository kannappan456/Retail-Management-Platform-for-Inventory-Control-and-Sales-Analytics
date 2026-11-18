"""Repeatable in-process API benchmark using temporary SQLite data only.

Run with the project's virtual environment. The script never connects to the
configured MySQL engine and does not write to the project's MLflow store.
Measurements include FastAPI/ASGI dispatch and isolated database work, but not
TCP, reverse-proxy, or production database latency.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

os.environ["MLFLOW_TRACKING_ENABLED"] = "false"
os.environ["WORKFLOW_SCHEDULER_ENABLED"] = "false"

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vendor import Vendor
from app.security import get_current_user
from app.routes.auth_routes import password_context


ITERATIONS = 20
VIRTUAL_USERS = 4
LOGIN_PASSWORD = "Phase5-Isolated-Load-Only-123!"


def _seed(db):
    vendors = [
        Vendor(vendor_id=1, business_name="Load Vendor One", owner_name="Test One", email="vendor1@load.test", status="Active"),
        Vendor(vendor_id=2, business_name="Load Vendor Two", owner_name="Test Two", email="vendor2@load.test", status="Active"),
    ]
    db.add_all(vendors)
    db.flush()
    db.add_all([
        User(user_id=1, email="admin@shopsense-performance.com", password_hash=password_context.hash(LOGIN_PASSWORD), role="Admin", is_active=True),
        User(user_id=2, email="vendor1-user@load.test", password_hash="not-used", role="Vendor", vendor_id=1, is_active=True),
        User(user_id=3, email="vendor2-user@load.test", password_hash="not-used", role="Vendor", vendor_id=2, is_active=True),
    ])
    db.flush()
    customers = [
        User(user_id=customer_id, email=f"customer{customer_id}@load.test", password_hash="not-used", role="Customer", is_active=True)
        for customer_id in range(10, 110)
    ]
    db.add_all(customers)
    db.flush()

    products = []
    inventory = []
    for product_id in range(1, 301):
        vendor_id = 1 if product_id % 2 else 2
        product = Product(
            product_id=product_id,
            vendor_id=vendor_id,
            product_name=f"Isolated Load Product {product_id}",
            category=("Grocery", "Home", "Electronics", "Apparel")[product_id % 4],
            price=10 + (product_id % 80),
        )
        products.append(product)
        inventory.append(Inventory(
            product_id=product_id,
            current_stock=500,
            reorder_level=20,
            warehouse=f"Test Warehouse {product_id % 5}",
        ))
    db.add_all(products)
    db.flush()
    db.add_all(inventory)
    db.flush()

    transactions = []
    transaction_id = 1
    now = datetime.now()
    for customer_id in range(10, 110):
        for order_number in range(8):
            product_id = ((customer_id * 11 + order_number * 17) % 300) + 1
            product = products[product_id - 1]
            quantity = (customer_id + order_number) % 3 + 1
            status = "Cancelled" if transaction_id % 23 == 0 else (
                "Refunded" if transaction_id % 29 == 0 else "Completed"
            )
            transactions.append(Transaction(
                transaction_id=transaction_id,
                product_id=product_id,
                vendor_id=product.vendor_id,
                customer_id=customer_id,
                quantity=quantity,
                amount=float(product.price) * quantity,
                status=status,
                transaction_date=now - timedelta(days=(transaction_id % 75)),
            ))
            transaction_id += 1
    db.add_all(transactions)
    db.commit()


async def _http_request(method, path, identity, body=None):
    request_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    headers = [(b"authorization", b"Bearer isolated-performance-request")]
    if body is not None:
        headers.append((b"content-type", b"application/json"))
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
            return {"type": "http.request", "body": request_bytes, "more_body": False}
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

    started = time.perf_counter()
    await app(scope, receive, send)
    elapsed = (time.perf_counter() - started) * 1000
    response["body"] = b"".join(response["body"])
    response["elapsed_ms"] = elapsed
    return response


def _percentile(values, percentile):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percentile * len(ordered) + 0.999999)) - 1))
    return ordered[index]


async def _measure(name, method, path, identity, body=None):
    # Exclude a warm-up request from the reported sample set.
    warmup = await _http_request(method, path, identity, body)
    if not 200 <= warmup["status"] < 300:
        raise RuntimeError(f"Warm-up failed for {name}: HTTP {warmup['status']} {warmup['body'][:300]!r}")

    latencies = []
    errors = 0
    statuses = {}
    shared_index = {"value": 0}
    started = time.perf_counter()

    async def worker():
        nonlocal errors
        while True:
            index = shared_index["value"]
            if index >= ITERATIONS:
                return
            shared_index["value"] += 1
            response = await _http_request(method, path, identity, body)
            latencies.append(response["elapsed_ms"])
            statuses[response["status"]] = statuses.get(response["status"], 0) + 1
            if not 200 <= response["status"] < 300:
                errors += 1

    await asyncio.gather(*(worker() for _ in range(VIRTUAL_USERS)))
    wall_seconds = time.perf_counter() - started
    return {
        "endpoint": name,
        "requests": len(latencies),
        "avg_ms": statistics.fmean(latencies),
        "median_ms": statistics.median(latencies),
        "p95_ms": _percentile(latencies, 0.95),
        "p99_ms": _percentile(latencies, 0.99),
        "requests_per_second": len(latencies) / wall_seconds if wall_seconds else 0,
        "errors": errors,
        "error_rate_percent": errors / len(latencies) * 100 if latencies else 0,
        "statuses": statuses,
    }


async def run_benchmarks(identities):
    admin = identities["admin"]
    customer = identities["customer"]
    vendor = identities["vendor"]
    cases = [
        ("Authentication login", "POST", "/auth/login", None, {"email": "admin@shopsense-performance.com", "password": LOGIN_PASSWORD}),
        ("Product listing", "GET", "/products/", admin, None),
        ("Vendor product filter", "GET", "/products/?vendor_id=1", admin, None),
        ("Category product filter", "GET", "/categories/Grocery/products", admin, None),
        ("Inventory analytics", "GET", "/inventory-analytics/overview", admin, None),
        ("Demand forecasting", "GET", "/inventory-forecast/demand", admin, None),
        ("Customer analytics", "GET", "/customer-analytics/overview", admin, None),
        ("Customer segmentation", "GET", "/customer-analytics/segments", admin, None),
        ("Customer recommendations", "GET", "/recommendations/", customer, None),
        ("Recommendation evaluation", "GET", "/recommendations/evaluation", admin, None),
        ("Vendor revenue analytics", "GET", "/analytics/vendor/revenue/overview", vendor, None),
        ("Marketplace revenue analytics", "GET", "/analytics/revenue/overview", admin, None),
        ("BI overview", "GET", "/reports/bi/overview?months=3", admin, None),
        ("BI PDF export", "GET", "/reports/bi/pdf?months=3", admin, None),
        ("BI Excel export", "GET", "/reports/bi/excel?months=3", admin, None),
    ]
    results = []
    for name, method, path, identity, body in cases:
        current_identity["user"] = identity
        results.append(await _measure(name, method, path, identity, body))
    return results


def main():
    global current_identity
    with tempfile.TemporaryDirectory(prefix="shopsense-phase5-") as temp_dir:
        db_path = Path(temp_dir) / "phase5-isolated.sqlite3"
        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
            pool_size=10,
            max_overflow=10,
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with Session() as db:
            _seed(db)
            identities = {
                "admin": db.get(User, 1),
                "vendor": db.get(User, 2),
                "customer": db.get(User, 10),
            }

        def isolated_db():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        current_identity = {"user": identities["admin"]}
        app.dependency_overrides[get_db] = isolated_db
        app.dependency_overrides[get_current_user] = lambda: current_identity["user"]
        try:
            with Session() as db:
                source_revenue = float(db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(Transaction.status == "Completed").scalar() or 0)
            results = asyncio.run(run_benchmarks(identities))
            current_identity["user"] = identities["admin"]
            # Check report/source consistency with real isolated DB records.
            from app.reports.bi_reports import build_bi_overview
            with Session() as db:
                overview = build_bi_overview(db, identities["admin"], months=3)
            if abs(overview["marketplace"]["completed_revenue"] - source_revenue) > 0.01:
                raise AssertionError("BI revenue does not match isolated Completed transaction records.")
            if abs(sum(row["revenue"] for row in overview["categories"]) - source_revenue) > 0.01:
                raise AssertionError("Category totals do not reconcile with isolated completed revenue.")
            if abs(sum(row["revenue"] for row in overview["products"]) - source_revenue) > 0.01:
                raise AssertionError("Product totals do not reconcile with isolated completed revenue.")
            if abs(sum(row["revenue"] for row in overview["vendors"]) - source_revenue) > 0.01:
                raise AssertionError("Vendor totals do not reconcile with isolated completed revenue.")
            if abs(sum(row["revenue"] for row in overview["revenue"]["monthly"]) - source_revenue) > 0.01:
                raise AssertionError("Monthly totals do not reconcile with isolated completed revenue.")
            print(f"Dataset: 2 vendors, 300 products, 100 customers, 800 transactions (isolated temporary SQLite).")
            print(f"Concurrency: {VIRTUAL_USERS} ASGI requests in parallel; {ITERATIONS} measured requests per endpoint plus one warm-up.")
            print("Timing includes FastAPI/ASGI dispatch and isolated database work; it excludes TCP/network, proxy, and production database latency.")
            print("Endpoint | n | avg ms | median ms | p95 ms | p99 ms | req/s | errors | error rate")
            for item in results:
                print(
                    f"{item['endpoint']} | {item['requests']} | {item['avg_ms']:.2f} | "
                    f"{item['median_ms']:.2f} | {item['p95_ms']:.2f} | {item['p99_ms']:.2f} | "
                    f"{item['requests_per_second']:.2f} | {item['errors']} | {item['error_rate_percent']:.2f}%"
                )
            print(f"Data consistency: passed; BI, monthly, vendor, category, and product revenue match Completed-source total INR {source_revenue:,.2f}.")
            if any(item["errors"] for item in results):
                raise SystemExit(1)
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


current_identity = {"user": None}


if __name__ == "__main__":
    main()
