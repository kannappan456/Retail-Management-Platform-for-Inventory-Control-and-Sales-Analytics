"""Business intelligence aggregation and PDF/Excel export services.

This module composes existing ShopSense analytics functions. It does not
reimplement marketplace or machine-learning calculations.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.graphics.shapes import Circle, Drawing, Line, String
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.customer.analytics import customer_overview
from app.inventory.inventory_tracking import inventory_overview, get_low_stock_products
from app.inventory.inventory_turnover import get_inventory_turnover
from app.inventory.warehouse_management import get_warehouses
from app.mlflow_tracking import (
    EXPERIMENTS,
    get_latest_run_artifact,
    list_experiment_runs,
    list_experiments,
    tracking_status,
)
from app.routes.analytics_routes import (
    admin_monthly_revenue,
    admin_revenue_overview,
    benchmark_categories,
    benchmark_vendors,
    product_performance,
    sales_summary,
    vendor_performance,
)
from app.workflow_scheduler import workflow_manager


MAX_VENDOR_ROWS = 100
MAX_WORKFLOW_ROWS = 50
_DARK = colors.HexColor("#17324d")
_BLUE = colors.HexColor("#2563eb")
_TEAL = colors.HexColor("#0d9488")
_PALE = colors.HexColor("#eef4fa")
_GRAY = colors.HexColor("#64748b")


def _safe_customer_summary(raw):
    """Keep aggregate customer measures; omit customer IDs and email fields."""
    if not isinstance(raw, dict):
        return {"available": False, "message": "Customer analytics are unavailable."}
    return {
        "available": True,
        "total_customers": raw.get("total_customers"),
        "total_customer_revenue": raw.get("total_customer_revenue"),
        "total_customer_orders": raw.get("total_customer_orders"),
        "average_customer_spend": raw.get("average_customer_spend"),
    }


def _safe_segmentation_result(result):
    if not result.get("available"):
        return {
            "available": False,
            "message": result.get("message") or "Segmentation tracking is unavailable.",
            "segments": [],
            "metrics": None,
        }
    artifact = result.get("artifact")
    if not isinstance(artifact, dict):
        return {
            "available": False,
            "message": "No tracked customer segmentation result is available yet.",
            "segments": [],
            "metrics": None,
        }
    # Stored segmentation artifacts are already aggregate-only. Pick the
    # supported fields again here so the BI/export response cannot expose IDs.
    segments = [
        {
            key: segment.get(key)
            for key in (
                "cluster_id",
                "customer_count",
                "average_spending",
                "average_orders",
                "average_order_value",
            )
        }
        for segment in artifact.get("segments", [])
        if isinstance(segment, dict)
    ]
    return {
        "available": True,
        "message": result.get("run", {}).get("tags", {}).get("evaluation.message")
        or artifact.get("evaluation_status"),
        "algorithm": result.get("run", {}).get("params", {}).get("algorithm", "K-Means"),
        "run_id": result.get("run", {}).get("run_id"),
        "evaluated_at": result.get("run", {}).get("start_time"),
        "customers_available": artifact.get("customers_available"),
        "cluster_count": artifact.get("optimal_clusters"),
        "silhouette_score": artifact.get("silhouette_score"),
        "segments": segments,
    }


def _latest_experiment_runs():
    experiment_response = list_experiments()
    if not experiment_response.get("available"):
        return {"available": False, "message": experiment_response.get("message"), "runs": []}
    by_name = {item["name"]: item for item in experiment_response.get("experiments", [])}
    latest = []
    for experiment_name in EXPERIMENTS.values():
        experiment = by_name.get(experiment_name)
        if not experiment:
            continue
        response = list_experiment_runs(experiment["experiment_id"], limit=1)
        if response.get("available") and response.get("runs"):
            run = response["runs"][0]
            latest.append({
                "experiment_name": experiment_name,
                "run_id": run.get("run_id"),
                "run_name": run.get("run_name"),
                "status": run.get("status"),
                "start_time": run.get("start_time"),
                "metrics": run.get("metrics") or {},
                "evaluation_status": run.get("tags", {}).get("evaluation.status"),
                "model_type": run.get("tags", {}).get("model.type"),
            })
    return {"available": True, "message": None, "runs": latest}


def _recommendation_evaluation(runs_response):
    run = next(
        (
            item for item in runs_response.get("runs", [])
            if item.get("experiment_name") == EXPERIMENTS["recommendations"]
        ),
        None,
    )
    if run is None:
        return {
            "available": False,
            "message": "No tracked recommendation evaluation is available yet.",
            "metrics": None,
        }
    metrics = run.get("metrics") or None
    return {
        "available": metrics is not None,
        "status": run.get("evaluation_status"),
        "run_id": run.get("run_id"),
        "evaluated_at": run.get("start_time"),
        "metrics": metrics,
        "message": None if metrics else (
            "The latest recommendation evaluation did not have enough purchase data to calculate metrics."
        ),
    }


def build_bi_overview(db, admin, months=12):
    """Build an aggregate BI payload from existing endpoints and MLflow runs."""
    if not 1 <= int(months) <= 60:
        raise ValueError("months must be between 1 and 60")
    months = int(months)

    # Existing analytics functions remain the source of truth for totals.
    summary = sales_summary(db=db, admin=admin)
    revenue = admin_revenue_overview(db=db, admin=admin)
    monthly = admin_monthly_revenue(months=months, db=db, admin=admin)["months"]
    vendor_data = benchmark_vendors(limit=MAX_VENDOR_ROWS, db=db, admin=admin)["vendors"]
    all_vendor_data = vendor_performance(db=db, admin=admin)
    categories = benchmark_categories(db=db, admin=admin)["categories"]
    products = product_performance(db=db, admin=admin)

    inventory = inventory_overview(admin=admin, db=db)
    low_stock = get_low_stock_products(admin=admin, db=db)
    turnover = get_inventory_turnover(admin=admin, db=db)
    warehouses = get_warehouses(admin=admin, db=db)

    customer_data = _safe_customer_summary(customer_overview(admin=admin, db=db))
    segmentation = _safe_segmentation_result(get_latest_run_artifact("segmentation"))
    forecast_result = get_latest_run_artifact("inventory")
    forecast_artifact = forecast_result.get("artifact") if forecast_result.get("available") else None
    if isinstance(forecast_artifact, dict):
        demand_forecast = {
            "available": True,
            "message": forecast_result.get("run", {}).get("tags", {}).get("evaluation.message"),
            "run_id": forecast_result.get("run", {}).get("run_id"),
            "evaluated_at": forecast_result.get("run", {}).get("start_time"),
            "forecast_method": forecast_artifact.get("forecast_method"),
            "forecast_period": forecast_artifact.get("forecast_period"),
            "validation_status": forecast_artifact.get("validation_status"),
            "forecasts": [
                {
                    key: item.get(key)
                    for key in (
                        "product_id",
                        "historical_sales_days",
                        "average_daily_demand",
                        "forecast_next_7_days",
                        "message",
                    )
                }
                for item in forecast_artifact.get("forecasts", [])
                if isinstance(item, dict)
            ],
        }
    else:
        demand_forecast = {
            "available": False,
            "message": forecast_result.get("message")
            or "No tracked demand forecast result is available yet.",
            "forecasts": [],
        }

    mlflow = tracking_status()
    latest_runs = _latest_experiment_runs()
    recommendation = _recommendation_evaluation(latest_runs)
    executions = workflow_manager.history(limit=MAX_WORKFLOW_ROWS)
    workflow_counts = {
        "success": sum(1 for item in executions if item.get("status") == "success"),
        "failed": sum(1 for item in executions if item.get("status") == "failed"),
        "running": sum(1 for item in executions if item.get("status") == "running"),
    }
    active_vendors = sum(1 for item in all_vendor_data if item.get("status") == "Active")

    return {
        "generated_at": datetime.now(ZoneInfo(workflow_manager.timezone_name)).isoformat(),
        "selected_months": months,
        "marketplace": {
            **summary,
            "gmv": revenue.get("gmv"),
            "completed_revenue": revenue.get("completed_revenue"),
            "completed_transaction_records": revenue.get("completed_transaction_records"),
            "mom_revenue_growth_percentage": revenue.get("mom_revenue_growth_percentage"),
            "current_month_revenue": revenue.get("current_month_revenue"),
            "previous_month_revenue": revenue.get("previous_month_revenue"),
            "total_active_vendors": active_vendors,
            "definition": revenue.get("definition"),
            "aov_note": revenue.get("aov_note"),
        },
        "revenue": {"overview": revenue, "monthly": monthly},
        "vendors": vendor_data,
        "categories": categories,
        "products": products,
        "inventory": {
            "overview": inventory,
            "low_stock": low_stock,
            "turnover": turnover,
            "warehouses": warehouses,
            "demand_forecast": demand_forecast,
        },
        "customers": {
            "summary": customer_data,
            "segmentation": segmentation,
        },
        "recommendation_evaluation": recommendation,
        "mlflow": {
            "status": mlflow,
            "latest_runs": latest_runs,
        },
        "workflow": {
            "scheduler": workflow_manager.scheduler_status(),
            "executions": executions,
            "counts": workflow_counts,
            "history_limit": MAX_WORKFLOW_ROWS,
        },
    }


def _money(value):
    return "Unavailable" if value is None else f"INR {float(value):,.2f}"


def _count(value):
    return "Unavailable" if value is None else f"{int(value):,}"


def _decimal(value, digits=2):
    return "Unavailable" if value is None else f"{float(value):,.{digits}f}"


def _percent(value):
    return "Unavailable" if value is None else f"{float(value):.2f}%"


def _ratio_percent(value):
    return "Unavailable" if value is None else f"{float(value) * 100:.2f}%"


def _date_string(value):
    if value is None:
        return "Unavailable"
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M %Z")
    return str(value).replace("T", " ")[:25]


def _table(headers, rows, empty_message, widths=None):
    style = getSampleStyleSheet()
    cell = ParagraphStyle("BICell", parent=style["BodyText"], fontName="Helvetica", fontSize=7.5, leading=9)
    heading = ParagraphStyle("BIHeader", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    values = [[Paragraph(str(item), heading) for item in headers]]
    safe_rows = rows or [[empty_message] + [""] * (len(headers) - 1)]
    for row in safe_rows:
        values.append([Paragraph(escape(str(item if item is not None else "Unavailable")), cell) for item in row])
    result = Table(values, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), _DARK),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7e0e9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if not rows and len(headers) > 1:
        commands.append(("SPAN", (0, 1), (-1, 1)))
    for row_index in range(1, len(values)):
        if row_index % 2 == 0:
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), _PALE))
    result.setStyle(TableStyle(commands))
    return result


def _revenue_chart(months):
    values = [(item.get("month"), float(item.get("revenue") or 0)) for item in months]
    if not values or max(value for _, value in values) <= 0:
        return None
    drawing = Drawing(485, 170)
    left, bottom, width, height = 42, 30, 425, 115
    maximum = max(value for _, value in values)
    drawing.add(Line(left, bottom, left + width, bottom, strokeColor=_GRAY, strokeWidth=0.7))
    drawing.add(Line(left, bottom, left, bottom + height, strokeColor=_GRAY, strokeWidth=0.7))
    points = []
    for index, (label, value) in enumerate(values):
        x = left + (width * index / max(1, len(values) - 1))
        y = bottom + height * value / maximum
        points.append((x, y))
        if len(values) <= 12 or index % max(1, len(values) // 8) == 0 or index == len(values) - 1:
            drawing.add(String(x - 9, 12, str(label)[-5:], fontName="Helvetica", fontSize=6, fillColor=_GRAY))
    for first, second in zip(points, points[1:]):
        drawing.add(Line(first[0], first[1], second[0], second[1], strokeColor=_BLUE, strokeWidth=1.8))
    for x, y in points:
        drawing.add(Circle(x, y, 2.2, fillColor=_TEAL, strokeColor=_TEAL))
    drawing.add(String(left, bottom + height + 6, f"INR 0 – {maximum:,.2f}", fontName="Helvetica", fontSize=7, fillColor=_GRAY))
    return drawing


def create_bi_pdf(data):
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=17 * mm,
        bottomMargin=18 * mm,
        title="ShopSense Marketplace Business Intelligence Report",
        author="ShopSense",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("BIReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", textColor=_DARK, alignment=TA_LEFT, fontSize=21, leading=25, spaceAfter=5))
    styles.add(ParagraphStyle("BISection", parent=styles["Heading2"], fontName="Helvetica-Bold", textColor=_DARK, fontSize=13, leading=16, spaceBefore=12, spaceAfter=7, keepWithNext=True))
    styles.add(ParagraphStyle("BISubtitle", parent=styles["BodyText"], textColor=_GRAY, fontSize=8.5, leading=12, spaceAfter=9))

    story = [
        Paragraph("ShopSense Marketplace BI Report", styles["BIReportTitle"]),
        Paragraph(
            f"Generated {_date_string(data.get('generated_at'))} · "
            f"Monthly revenue window: {data.get('selected_months', 'Unavailable')} months",
            styles["BISubtitle"],
        ),
    ]
    market = data.get("marketplace") or {}
    story.extend([
        Paragraph("Marketplace Overview", styles["BISection"]),
        _table(
            ["Measure", "Value"],
            [
                ["Completed revenue", _money(market.get("completed_revenue"))],
                ["GMV", _money(market.get("gmv"))],
                ["Completed transaction records", _count(market.get("completed_transaction_records"))],
                ["Active vendors", _count(market.get("total_active_vendors"))],
                ["Total vendors", _count(market.get("total_vendors"))],
                ["Total products", _count(market.get("total_products"))],
                ["Units sold", _count(market.get("total_units_sold"))],
                ["Month-over-month revenue growth", _percent(market.get("mom_revenue_growth_percentage"))],
            ],
            "Marketplace summary unavailable.",
            widths=[78 * mm, 90 * mm],
        ),
        Paragraph(str(market.get("definition") or "Revenue definition unavailable."), styles["BISubtitle"]),
        Paragraph("Revenue Analysis", styles["BISection"]),
    ])
    revenue = data.get("revenue") or {}
    monthly = revenue.get("monthly") or []
    chart = _revenue_chart(monthly)
    if chart is not None:
        story.append(chart)
    elif monthly:
        story.append(Paragraph("Revenue values are zero for this period; the table below contains the API results.", styles["BISubtitle"]))
    story.append(_table(
        ["Month", "Revenue", "GMV", "Completed records", "MoM growth"],
        [[item.get("month"), _money(item.get("revenue")), _money(item.get("gmv")), _count(item.get("completed_transaction_records")), _percent(item.get("mom_revenue_growth_percentage"))] for item in monthly],
        "No monthly revenue data is available.",
        widths=[28 * mm, 35 * mm, 35 * mm, 38 * mm, 32 * mm],
    ))

    story.extend([
        Paragraph("Vendor Performance", styles["BISection"]),
        _table(
            ["Vendor", "Status", "Revenue", "Contribution", "Units sold", "Products"],
            [[item.get("business_name"), item.get("status"), _money(item.get("revenue")), _percent(item.get("revenue_contribution_percentage")), _count(item.get("units_sold")), _count(item.get("product_count"))] for item in (data.get("vendors") or [])[:15]],
            "No vendor performance data is available.",
            widths=[48 * mm, 21 * mm, 29 * mm, 26 * mm, 25 * mm, 18 * mm],
        ),
        Paragraph("Category Performance", styles["BISection"]),
        _table(
            ["Category", "Revenue", "Units sold", "Completed records", "Products"],
            [[item.get("category"), _money(item.get("revenue")), _count(item.get("units_sold")), _count(item.get("completed_transaction_records")), _count(item.get("product_count"))] for item in (data.get("categories") or [])],
            "No category performance data is available.",
            widths=[49 * mm, 35 * mm, 27 * mm, 42 * mm, 24 * mm],
        ),
        Paragraph("Product Performance", styles["BISection"]),
        _table(
            ["Product", "Category", "Units sold", "Revenue"],
            [[item.get("product_name"), item.get("category") or "Uncategorized", _count(item.get("units_sold")), _money(item.get("revenue"))] for item in (data.get("products") or [])[:15]],
            "No product performance data is available.",
            widths=[62 * mm, 46 * mm, 30 * mm, 38 * mm],
        ),
    ])

    inventory = data.get("inventory") or {}
    inv = inventory.get("overview") or {}
    low = inventory.get("low_stock") or {}
    wh = inventory.get("warehouses") or {}
    turnover = inventory.get("turnover") or {}
    story.extend([
        Paragraph("Inventory Intelligence", styles["BISection"]),
        _table(
            ["Measure", "Value"],
            [
                ["Tracked products", _count(inv.get("total_products_tracked"))],
                ["Inventory units", _count(inv.get("total_stock_units"))],
                ["Inventory value", _money(inv.get("total_inventory_value"))],
                ["Low-stock products", _count(low.get("total_low_stock_products"))],
                ["Out-of-stock products", _count(inv.get("out_of_stock_products"))],
                ["Warehouses / allocation groups", _count(wh.get("total_warehouses"))],
                ["Turnover calculation", turnover.get("calculation") or "Unavailable"],
            ],
            "Inventory metrics unavailable.",
            widths=[78 * mm, 90 * mm],
        ),
        _table(
            ["Low-stock product", "Category", "Stock", "Reorder level", "Warehouse"],
            [[item.get("product_name"), item.get("category") or "Uncategorized", _count(item.get("current_stock")), _count(item.get("reorder_level")), item.get("warehouse") or "Unassigned"] for item in (low.get("low_stock_products") or [])[:15]],
            "No low-stock products were returned.",
            widths=[47 * mm, 40 * mm, 24 * mm, 33 * mm, 34 * mm],
        ),
        Paragraph("Warehouse Allocation", styles["BISection"]),
        _table(
            ["Warehouse", "Products", "Stock units"],
            [[item.get("warehouse"), _count(item.get("total_products")), _count(item.get("total_stock_units"))] for item in (wh.get("warehouses") or [])],
            "No warehouse allocation data is available.",
            widths=[75 * mm, 45 * mm, 58 * mm],
        ),
    ])
    forecast = inventory.get("demand_forecast") or {}
    story.extend([
        Paragraph("Latest Demand Forecast", styles["BISection"]),
        Paragraph(
            str(forecast.get("message") or forecast.get("forecast_method") or "No tracked forecast result is available."),
            styles["BISubtitle"],
        ),
        _table(
            ["Product ID", "Sales days", "Average daily demand", "Next 7 days", "Status"],
            [[_count(item.get("product_id")), _count(item.get("historical_sales_days")), _decimal(item.get("average_daily_demand")), _decimal(item.get("forecast_next_7_days")), item.get("message") or "Available"] for item in (forecast.get("forecasts") or [])[:15]],
            "No tracked demand forecast result is available.",
            widths=[28 * mm, 27 * mm, 43 * mm, 28 * mm, 52 * mm],
        ),
    ])

    customers = data.get("customers") or {}
    customer_summary = customers.get("summary") or {}
    segmentation = customers.get("segmentation") or {}
    story.extend([
        Paragraph("Customer Intelligence", styles["BISection"]),
        _table(
            ["Measure", "Value"],
            [
                ["Customers with completed purchases", _count(customer_summary.get("total_customers"))],
                ["Customer revenue", _money(customer_summary.get("total_customer_revenue"))],
                ["Customer transaction records", _count(customer_summary.get("total_customer_orders"))],
                ["Average spend per purchasing customer", _money(customer_summary.get("average_customer_spend"))],
                ["Latest segmentation silhouette score", "Unavailable" if segmentation.get("silhouette_score") is None else f"{float(segmentation['silhouette_score']):.4f}"],
            ],
            "Customer analytics are unavailable.",
            widths=[78 * mm, 90 * mm],
        ),
        Paragraph(str(segmentation.get("message") or segmentation.get("algorithm") or "Segmentation result unavailable."), styles["BISubtitle"]),
        _table(
            ["Cluster", "Customers", "Average spending", "Average orders", "Average order value"],
            [[_count(item.get("cluster_id")), _count(item.get("customer_count")), _money(item.get("average_spending")), _count(item.get("average_orders")), _money(item.get("average_order_value"))] for item in (segmentation.get("segments") or [])],
            "No tracked customer segments are available.",
            widths=[23 * mm, 30 * mm, 42 * mm, 34 * mm, 39 * mm],
        ),
        Paragraph("Recommendation Evaluation", styles["BISection"]),
    ])
    recommendation = data.get("recommendation_evaluation") or {}
    rec_metrics = recommendation.get("metrics") or {}
    story.append(_table(
        ["Status", "Run ID", "Precision@K", "Recall@K", "Hit Rate"],
        [[recommendation.get("status") or ("Available" if recommendation.get("available") else "Unavailable"), recommendation.get("run_id") or "Unavailable", _ratio_percent(rec_metrics.get("precision_at_k")), _ratio_percent(rec_metrics.get("recall_at_k")), _ratio_percent(rec_metrics.get("hit_rate_at_k"))]] if recommendation.get("available") else [],
        recommendation.get("message") or "No tracked recommendation evaluation is available.",
        widths=[31 * mm, 54 * mm, 30 * mm, 30 * mm, 25 * mm],
    ))

    mlflow = data.get("mlflow") or {}
    mlflow_runs = (mlflow.get("latest_runs") or {}).get("runs") or []
    story.extend([
        Paragraph("MLflow Experiment History", styles["BISection"]),
        _table(
            ["Experiment", "Run ID", "Started", "Status", "Latest metrics"],
            [[item.get("experiment_name"), item.get("run_id"), _date_string(item.get("start_time")), item.get("evaluation_status") or item.get("status"), ", ".join(f"{key}: {value}" for key, value in (item.get("metrics") or {}).items()) or "No metrics"] for item in mlflow_runs],
            (mlflow.get("status") or {}).get("message") or "No ShopSense MLflow runs are available.",
            widths=[47 * mm, 45 * mm, 34 * mm, 25 * mm, 48 * mm],
        ),
        Paragraph("Automated Workflow History", styles["BISection"]),
    ])
    workflow = data.get("workflow") or {}
    counts = workflow.get("counts") or {}
    story.append(_table(
        ["Successful", "Failed", "Running", "Scheduler", "Timezone"],
        [[_count(counts.get("success")), _count(counts.get("failed")), _count(counts.get("running")), (workflow.get("scheduler") or {}).get("status", "Unavailable"), (workflow.get("scheduler") or {}).get("timezone", "Unavailable")]],
        "Workflow status unavailable.",
        widths=[32 * mm, 28 * mm, 30 * mm, 40 * mm, 48 * mm],
    ))
    executions = workflow.get("executions") or []
    story.append(_table(
        ["Job", "Started", "Trigger", "Status", "Duration", "Result / error"],
        [[item.get("job_name"), _date_string(item.get("started_at")), item.get("trigger"), item.get("status"), f"{item.get('duration_seconds')}s" if item.get("duration_seconds") is not None else "Running", item.get("result_summary") or item.get("error") or "Unavailable"] for item in executions[:12]],
        "No workflow executions are recorded in the current process history.",
        widths=[36 * mm, 34 * mm, 22 * mm, 22 * mm, 22 * mm, 42 * mm],
    ))

    def draw_page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d7e0e9"))
        canvas.line(16 * mm, 13 * mm, A4[0] - 16 * mm, 13 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_GRAY)
        canvas.drawString(16 * mm, 8 * mm, "ShopSense · Business Intelligence")
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output.getvalue()


def _style_sheet(ws, header_row=1):
    header_fill = PatternFill("solid", fgColor="17324D")
    header_font = Font(color="FFFFFF", bold=True)
    border = Border(bottom=Side(style="thin", color="D7E0E9"))
    for cell in ws[header_row]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[header_row].height = 25
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = border
    for column in ws.columns:
        letter = get_column_letter(column[0].column)
        max_width = max((len(str(cell.value or "")) for cell in column), default=10)
        ws.column_dimensions[letter].width = min(max(max_width + 2, 12), 42)


def _append_data_rows(ws, rows, column_count):
    if rows:
        for row in rows:
            ws.append([_excel_safe_cell(value) for value in row])
    else:
        ws.append(["No data available"] + [None] * (column_count - 1))


def _excel_safe_cell(value):
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def create_bi_excel(data):
    workbook = Workbook()
    workbook.properties.title = "ShopSense Marketplace Business Intelligence Report"
    workbook.properties.creator = "ShopSense"

    overview = workbook.active
    overview.title = "Marketplace Overview"
    overview.append(["Metric", "Value"])
    market = data.get("marketplace") or {}
    overview_rows = [
        ("Generated at", _date_string(data.get("generated_at"))),
        ("Selected monthly window", data.get("selected_months")),
        ("Completed revenue", market.get("completed_revenue")),
        ("GMV", market.get("gmv")),
        ("Completed transaction records", market.get("completed_transaction_records")),
        ("Total active vendors", market.get("total_active_vendors")),
        ("Total vendors", market.get("total_vendors")),
        ("Total products", market.get("total_products")),
        ("Units sold", market.get("total_units_sold")),
        ("Current month revenue", market.get("current_month_revenue")),
        ("Previous month revenue", market.get("previous_month_revenue")),
        ("MoM revenue growth percentage", market.get("mom_revenue_growth_percentage")),
        ("Revenue definition", market.get("definition")),
        ("Order/AOV note", market.get("aov_note")),
    ]
    for row in overview_rows:
        overview.append([_excel_safe_cell(value) for value in row])
    _style_sheet(overview)
    for row in range(2, overview.max_row + 1):
        if overview.cell(row, 1).value in {"Completed revenue", "GMV", "Current month revenue", "Previous month revenue"}:
            overview.cell(row, 2).number_format = '"INR" #,##0.00'
        if overview.cell(row, 1).value == "MoM revenue growth percentage":
            overview.cell(row, 2).number_format = '0.00"%"'

    monthly = workbook.create_sheet("Monthly Revenue")
    monthly.append(["Month", "Revenue (INR)", "GMV (INR)", "Completed transaction records", "MoM revenue growth (%)"])
    rows = [[item.get("month"), item.get("revenue"), item.get("gmv"), item.get("completed_transaction_records"), item.get("mom_revenue_growth_percentage")] for item in (data.get("revenue") or {}).get("monthly", [])]
    _append_data_rows(monthly, rows, 5)
    _style_sheet(monthly)
    monthly.freeze_panes = "A2"
    monthly.auto_filter.ref = monthly.dimensions
    for row in range(2, monthly.max_row + 1):
        monthly.cell(row, 2).number_format = monthly.cell(row, 3).number_format = '"INR" #,##0.00'
        monthly.cell(row, 5).number_format = '0.00"%"'

    vendors = workbook.create_sheet("Vendor Performance")
    vendors.append(["Vendor", "Status", "Products", "Completed transaction records", "Units sold", "Revenue (INR)", "Revenue contribution (%)", "Average transaction value (INR)"])
    rows = [[item.get("business_name"), item.get("status"), item.get("product_count"), item.get("completed_transaction_records"), item.get("units_sold"), item.get("revenue"), item.get("revenue_contribution_percentage"), item.get("average_transaction_value")] for item in data.get("vendors", [])]
    _append_data_rows(vendors, rows, 8)
    _style_sheet(vendors)
    vendors.freeze_panes = "A2"
    vendors.auto_filter.ref = vendors.dimensions
    for row in range(2, vendors.max_row + 1):
        vendors.cell(row, 6).number_format = vendors.cell(row, 8).number_format = '"INR" #,##0.00'
        vendors.cell(row, 7).number_format = '0.00"%"'

    categories = workbook.create_sheet("Category Performance")
    categories.append(["Category", "Revenue (INR)", "Units sold", "Completed transaction records", "Products"])
    rows = [[item.get("category"), item.get("revenue"), item.get("units_sold"), item.get("completed_transaction_records"), item.get("product_count")] for item in data.get("categories", [])]
    _append_data_rows(categories, rows, 5)
    _style_sheet(categories)
    categories.freeze_panes = "A2"
    categories.auto_filter.ref = categories.dimensions
    for row in range(2, categories.max_row + 1):
        categories.cell(row, 2).number_format = '"INR" #,##0.00'

    products = workbook.create_sheet("Product Performance")
    products.append(["Product", "Category", "Units sold", "Revenue (INR)"])
    rows = [[item.get("product_name"), item.get("category") or "Uncategorized", item.get("units_sold"), item.get("revenue")] for item in data.get("products", [])]
    _append_data_rows(products, rows, 4)
    _style_sheet(products)
    products.freeze_panes = "A2"
    products.auto_filter.ref = products.dimensions
    for row in range(2, products.max_row + 1):
        products.cell(row, 4).number_format = '"INR" #,##0.00'

    inventory_sheet = workbook.create_sheet("Inventory Summary")
    inventory_sheet.append(["Inventory Metric", "Value"])
    inventory = data.get("inventory") or {}
    inv = inventory.get("overview") or {}
    low = inventory.get("low_stock") or {}
    wh = inventory.get("warehouses") or {}
    for row in [
        ("Tracked products", inv.get("total_products_tracked")),
        ("Inventory units", inv.get("total_stock_units")),
        ("Inventory value (INR)", inv.get("total_inventory_value")),
        ("Low-stock products", low.get("total_low_stock_products")),
        ("Out-of-stock products", inv.get("out_of_stock_products")),
        ("Warehouse allocation groups", wh.get("total_warehouses")),
        ("Turnover calculation", (inventory.get("turnover") or {}).get("calculation")),
        ("Turnover note", (inventory.get("turnover") or {}).get("note")),
        ("Demand forecast availability", (inventory.get("demand_forecast") or {}).get("message") or (inventory.get("demand_forecast") or {}).get("forecast_method")),
    ]:
        inventory_sheet.append([_excel_safe_cell(value) for value in row])
    inventory_sheet.append([None, None])
    inventory_product_header = inventory_sheet.max_row + 1
    inventory_sheet.append(["Product", "Category", "Current stock", "Reorder level", "Stock status", "Warehouse", "Inventory value (INR)", "Sales-to-current-stock ratio"])
    inventory_rows = [[item.get("product_name"), item.get("category") or "Uncategorized", item.get("current_stock"), item.get("reorder_level"), item.get("stock_status"), item.get("warehouse") or "Unassigned", item.get("inventory_value"), next((turn.get("sales_to_current_stock_ratio") for turn in (inventory.get("turnover") or {}).get("products", []) if turn.get("product_id") == item.get("product_id")), None)] for item in (inv.get("products") or [])]
    if inventory_rows:
        for row in inventory_rows:
            inventory_sheet.append([_excel_safe_cell(value) for value in row])
    else:
        inventory_sheet.append(["No inventory product data available"] + [None] * 7)
    _style_sheet(inventory_sheet, header_row=1)
    for cell in inventory_sheet[inventory_product_header]:
        cell.fill = PatternFill("solid", fgColor="17324D")
        cell.font = Font(color="FFFFFF", bold=True)
    inventory_sheet.freeze_panes = f"A{inventory_product_header + 1}"
    inventory_sheet.auto_filter.ref = f"A{inventory_product_header}:H{inventory_sheet.max_row}"
    for row in range(inventory_product_header + 1, inventory_sheet.max_row + 1):
        inventory_sheet.cell(row, 7).number_format = '"INR" #,##0.00'
        inventory_sheet.cell(row, 8).number_format = '0.00'
    for row in range(2, 11):
        if row != inventory_product_header - 1:
            inventory_sheet.cell(row, 2).alignment = Alignment(vertical="top", wrap_text=True)
    inventory_sheet.cell(4, 2).number_format = '"INR" #,##0.00'

    customers = workbook.create_sheet("Customer Analytics")
    customers.append(["Customer Intelligence Measure", "Value"])
    customer_summary = (data.get("customers") or {}).get("summary") or {}
    for row in [
        ("Customers with completed purchases", customer_summary.get("total_customers")),
        ("Customer revenue (INR)", customer_summary.get("total_customer_revenue")),
        ("Customer transaction records", customer_summary.get("total_customer_orders")),
        ("Average spend per purchasing customer (INR)", customer_summary.get("average_customer_spend")),
    ]:
        customers.append([_excel_safe_cell(value) for value in row])
    segmentation = (data.get("customers") or {}).get("segmentation") or {}
    customers.append([None, None])
    segment_header = customers.max_row + 1
    customers.append(["Cluster", "Customer count", "Average spending (INR)", "Average orders", "Average order value (INR)"])
    segments = segmentation.get("segments") or []
    if segments:
        for item in segments:
            customers.append([_excel_safe_cell(item.get(key)) for key in ("cluster_id", "customer_count", "average_spending", "average_orders", "average_order_value")])
    else:
        customers.append([_excel_safe_cell(segmentation.get("message") or "No tracked customer segment data available")])
    _style_sheet(customers)
    for cell in customers[segment_header]:
        cell.fill = PatternFill("solid", fgColor="17324D")
        cell.font = Font(color="FFFFFF", bold=True)
    customers.freeze_panes = f"A{segment_header + 1}"
    customers.auto_filter.ref = f"A{segment_header}:E{customers.max_row}"
    for row in range(2, segment_header):
        if customers.cell(row, 1).value and "INR" in str(customers.cell(row, 1).value):
            customers.cell(row, 2).number_format = '"INR" #,##0.00'
    for row in range(segment_header + 1, customers.max_row + 1):
        customers.cell(row, 3).number_format = customers.cell(row, 5).number_format = '"INR" #,##0.00'

    history = workbook.create_sheet("Workflow History")
    history.append(["Job", "Status", "Trigger", "Started at", "Completed at", "Duration (seconds)", "Result summary", "Error"])
    rows = [[item.get("job_name"), item.get("status"), item.get("trigger"), item.get("started_at"), item.get("completed_at"), item.get("duration_seconds"), item.get("result_summary"), item.get("error")] for item in (data.get("workflow") or {}).get("executions", [])]
    _append_data_rows(history, rows, 8)
    _style_sheet(history)
    history.freeze_panes = "A2"
    history.auto_filter.ref = history.dimensions

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
