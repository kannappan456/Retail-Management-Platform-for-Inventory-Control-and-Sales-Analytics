from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline

import pandas as pd

from app.database import get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.security import require_admin
from app.mlflow_tracking import log_workflow_run

router = APIRouter(
    prefix="/customer-analytics",
    tags=["Customer Segmentation"]
)


@router.get("/segments")
def customer_segments(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    # Collect actual customer purchasing behaviour.
    result = db.query(
        User.user_id,
        User.email,
        func.count(Transaction.transaction_id).label("total_orders"),
        func.sum(Transaction.quantity).label("total_units"),
        func.sum(Transaction.amount).label("total_spent")
    ).join(
        Transaction,
        Transaction.customer_id == User.user_id
    ).filter(
        User.role == "Customer",
        Transaction.status == "Completed"
    ).group_by(
        User.user_id,
        User.email
    ).all()

    if len(result) < 3:
        response = {
            "message": (
                "Insufficient customer data for meaningful "
                "K-Means segmentation."
            ),
            "customers_available": len(result),
            "minimum_customers_required": 3,
            "silhouette_score": None,
            "segments": []
        }
        response["tracking"] = log_workflow_run(
            "segmentation",
            "customer-segmentation-insufficient-data",
            params={
                "algorithm": "K-Means",
                "minimum_customers_required": 3,
                "customers_available": len(result),
                "features": ["total_spent", "total_orders", "average_order_value"],
            },
            evaluation_status="insufficient_data",
            evaluation_message=response["message"],
            artifact={
                "evaluation_status": "insufficient_data",
                "customers_available": len(result),
                "minimum_customers_required": 3,
                "metrics": None,
            },
            model_type="kmeans_customer_segmentation",
        )
        return response

    # Prepare customer features.
    data = pd.DataFrame([
        {
            "customer_id": row.user_id,
            "email": row.email,
            "total_orders": row.total_orders,
            "total_units": row.total_units or 0,
            "total_spent": float(row.total_spent or 0),
            "average_order_value": (
                float(row.total_spent or 0) / row.total_orders
            )
        }
        for row in result
    ])

    features = data[
        ["total_spent", "total_orders", "average_order_value"]
    ]

    # Standardize features because their scales differ.
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)

    # Test different cluster counts and select the best score.
    maximum_clusters = min(5, len(data) - 1)

    best_model = None
    best_score = -1
    best_k = None

    for k in range(2, maximum_clusters + 1):

        model = KMeans(
            n_clusters=k,
            random_state=42,
            n_init=10
        )

        labels = model.fit_predict(scaled_features)

        # Silhouette score requires at least 2 and
        # fewer clusters than the number of customers.
        if len(set(labels)) < 2:
            continue

        score = silhouette_score(scaled_features, labels)

        if score > best_score:
            best_score = score
            best_model = model
            best_k = k

    if best_model is None:
        response = {
            "message": "Unable to create meaningful customer clusters.",
            "customers_available": len(data),
            "silhouette_score": None,
            "segments": []
        }
        response["tracking"] = log_workflow_run(
            "segmentation",
            "customer-segmentation-no-valid-clusters",
            params={
                "algorithm": "K-Means",
                "customers_available": len(data),
                "candidate_clusters": min(5, len(data) - 1),
                "features": ["total_spent", "total_orders", "average_order_value"],
            },
            evaluation_status="no_valid_clusters",
            evaluation_message=response["message"],
            artifact={
                "evaluation_status": "no_valid_clusters",
                "customers_available": len(data),
                "metrics": None,
            },
            model_type="kmeans_customer_segmentation",
        )
        return response

    data["cluster"] = best_model.labels_

    # Summarize every customer segment.
    segments = []

    for cluster_id in sorted(data["cluster"].unique()):

        cluster_data = data[data["cluster"] == cluster_id]

        segments.append({
            "cluster_id": int(cluster_id),
            "customer_count": len(cluster_data),
            "average_spending": round(
                cluster_data["total_spent"].mean(), 2
            ),
            "average_orders": round(
                cluster_data["total_orders"].mean(), 2
            ),
            "average_order_value": round(
                cluster_data["average_order_value"].mean(), 2
            ),
            "customers": cluster_data[
                ["customer_id", "email"]
            ].to_dict(orient="records")
        })

    response = {
        "algorithm": "K-Means",
        "features_used": [
            "total_spent",
            "total_orders",
            "average_order_value"
        ],
        "customers_available": len(data),
        "optimal_clusters": best_k,
        "silhouette_score": round(float(best_score), 4),
        "segments": segments
    }
    fitted_pipeline = Pipeline([
        ("standard_scaler", scaler),
        ("kmeans", best_model),
    ])
    response["tracking"] = log_workflow_run(
        "segmentation",
        "customer-segmentation",
        params={
            "algorithm": "K-Means",
            "n_clusters": best_k,
            "candidate_cluster_counts": list(range(2, maximum_clusters + 1)),
            "random_state": best_model.random_state,
            "n_init": best_model.n_init,
            "max_iter": best_model.max_iter,
            "scaler_with_mean": scaler.with_mean,
            "scaler_with_std": scaler.with_std,
            "features": ["total_spent", "total_orders", "average_order_value"],
            "customers_available": len(data),
        },
        metrics={
            "silhouette_score": float(best_score),
            "customers_available": len(data),
            "cluster_count": len(segments),
        },
        evaluation_status="evaluated",
        evaluation_method="silhouette score on standardized customer features",
        artifact={
            "evaluation_status": "evaluated",
            "customers_available": len(data),
            "optimal_clusters": best_k,
            "silhouette_score": round(float(best_score), 4),
            "segments": [
                {
                    key: segment[key]
                    for key in (
                        "cluster_id",
                        "customer_count",
                        "average_spending",
                        "average_orders",
                        "average_order_value",
                    )
                }
                for segment in segments
            ],
        },
        sklearn_model=fitted_pipeline,
        model_name="shopsense-customer-segmentation",
        model_type="standard_scaler_plus_kmeans",
    )
    return response
