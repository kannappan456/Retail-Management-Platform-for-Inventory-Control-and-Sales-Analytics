
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.vendor_routes import router as vendor_router
from app.routes.product_routes import router as product_router
from app.routes.analytics_routes import router as analytics_router
from app.routes.mlflow_routes import router as mlflow_router
from app.routes.workflow_routes import router as workflow_router
from app.reports.report_routes import router as bi_reports_router
from app.workflow_scheduler import workflow_manager
from app.routes.inventory_routes import router as inventory_router
from app.routes.transaction_routes import router as transaction_router
from app.routes.auth_routes import router as auth_router
from app.customer.analytics import router as customer_analytics_router
from app.customer.segmentation import router as segmentation_router
from app.recommendation.recommendation import router as recommendation_router
from app.inventory.inventory_tracking import router as inventory_tracking_router
from app.inventory.inventory_forecasting import router as inventory_forecasting_router
from app.inventory.stock_alert import router as stock_alert_router
from app.inventory.warehouse_management import router as warehouse_management_router
from app.inventory.category_management import router as category_management_router
from app.inventory.inventory_turnover import router as inventory_turnover_router
@asynccontextmanager
async def lifespan(application):
    workflow_manager.start()
    try:
        yield
    finally:
        workflow_manager.shutdown()


app = FastAPI(
    title="ShopSense API",
    description="Multi-Vendor E-Commerce Analytics Platform",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(vendor_router)
app.include_router(product_router)
app.include_router(analytics_router)
app.include_router(mlflow_router)
app.include_router(workflow_router)
app.include_router(bi_reports_router)
app.include_router(inventory_router)
app.include_router(transaction_router)
app.include_router(auth_router)
app.include_router(customer_analytics_router)
app.include_router(segmentation_router)
app.include_router(recommendation_router)
app.include_router(inventory_tracking_router)
app.include_router(inventory_forecasting_router)
app.include_router(stock_alert_router)
app.include_router(warehouse_management_router)
app.include_router(category_management_router)
app.include_router(inventory_turnover_router)
@app.get("/")
def home():
    return {
        "message": "Welcome to ShopSense API",
        "status": "running",
        "milestone": "Milestone 1"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
