
import math

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, Date

from app.database import get_db
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.user import User
from app.security import require_admin
from app.mlflow_tracking import log_workflow_run

router = APIRouter(
    prefix="/inventory-forecast",
    tags=["Inventory Forecasting"]
)


@router.get("/demand")
def forecast_demand(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    sales = db.query(
        Transaction.product_id,
        func.date(Transaction.transaction_date).label("sale_date"),
        func.sum(Transaction.quantity).label("units_sold")
    ).filter(
        Transaction.status == "Completed"
    ).group_by(
        Transaction.product_id,
        func.date(Transaction.transaction_date)
    ).order_by(
        Transaction.product_id,
        func.date(Transaction.transaction_date)
    ).all()

    product_sales = {}
    product_sale_dates = {}

    for sale in sales:
        product_sales.setdefault(sale.product_id, []).append(
            int(sale.units_sold or 0)
        )
        product_sale_dates.setdefault(sale.product_id, []).append(str(sale.sale_date))

    forecasts = []

    products = db.query(Product).all()

    for product in products:
        history = product_sales.get(product.product_id, [])

        if not history:
            forecasts.append({
                "product_id": product.product_id,
                "product_name": product.product_name,
                "historical_sales_days": 0,
                "average_daily_demand": 0,
                "forecast_next_7_days": 0,
                "message": "Insufficient sales history"
            })
            continue

        average_daily_demand = sum(history) / len(history)
        forecast = round(average_daily_demand * 7)

        forecasts.append({
            "product_id": product.product_id,
            "product_name": product.product_name,
            "historical_sales_days": len(history),
            "average_daily_demand": round(average_daily_demand, 2),
            "forecast_next_7_days": forecast,
            "message": "Estimated using historical average demand"
        })

    # Validate the existing daily-average heuristic against each product's
    # last observed sales day; this does not alter the production forecast.
    actual_daily_units = []
    predicted_daily_units = []
    for history in product_sales.values():
        if len(history) < 2:
            continue
        actual_daily_units.append(history[-1])
        predicted_daily_units.append(sum(history[:-1]) / len(history[:-1]))

    validation_metrics = {}
    if actual_daily_units:
        errors = [
            prediction - actual
            for prediction, actual in zip(predicted_daily_units, actual_daily_units)
        ]
        validation_metrics = {
            "holdout_mae_units": sum(abs(error) for error in errors) / len(errors),
            "holdout_rmse_units": math.sqrt(
                sum(error * error for error in errors) / len(errors)
            ),
            "products_evaluated": len(errors),
        }

    tracking = log_workflow_run(
        "inventory",
        "inventory-demand-forecast",
        params={
            "forecast_method": "Historical Average Demand",
            "forecast_horizon_days": 7,
            "aggregation": "completed quantity grouped by product and observed sale date",
            "validation_method": "last observed sale day holdout",
            "products_in_catalog": len(products),
            "products_with_sales_history": len(product_sales),
            "validation_products": len(actual_daily_units),
        },
        metrics=validation_metrics,
        evaluation_status="evaluated" if actual_daily_units else "insufficient_data",
        evaluation_message=None if actual_daily_units else (
            "At least two observed sales days are required for holdout evaluation."
        ),
        evaluation_method="last observed sale day holdout",
        artifact={
            "forecast_method": "Historical Average Demand",
            "forecast_period": "Next 7 days",
            "validation_status": "evaluated" if actual_daily_units else "insufficient_data",
            "validation_dates_by_product": {
                str(product_id): dates
                for product_id, dates in product_sale_dates.items()
            },
            "forecasts": [
                {
                    key: forecast[key]
                    for key in (
                        "product_id",
                        "historical_sales_days",
                        "average_daily_demand",
                        "forecast_next_7_days",
                        "message",
                    )
                }
                for forecast in forecasts
            ],
        },
        model_type="historical_average_heuristic",
    )

    return {
        "forecast_method": "Historical Average Demand",
        "forecast_period": "Next 7 days",
        "total_products": len(forecasts),
        "forecasts": forecasts,
        "tracking": tracking,
    }
