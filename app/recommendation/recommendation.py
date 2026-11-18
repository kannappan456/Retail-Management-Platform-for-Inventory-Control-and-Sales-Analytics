from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd

from app.database import get_db
from app.security import require_customer, require_admin
from app.models.user import User
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.inventory import Inventory
from app.models.vendor import Vendor
from app.mlflow_tracking import log_workflow_run

router = APIRouter(
    prefix="/recommendations",
    tags=["Product Recommendations"]
)


def _track_recommendation_evaluation(result, k):
    """Record the existing evaluation result without altering its algorithm."""
    metrics = result.get("metrics")
    tracked = log_workflow_run(
        "recommendations",
        "recommendation-leave-one-out-evaluation",
        params={
            "algorithm": result.get("algorithm", "Cosine Similarity"),
            "k": k,
            "customers_available": result.get("customers_available"),
            "eligible_customers": result.get("eligible_customers"),
            "evaluated_customers": result.get("evaluated_customers", 0),
        },
        metrics=metrics or {},
        evaluation_status="evaluated" if metrics is not None else "insufficient_data",
        evaluation_message=result.get("message"),
        evaluation_method=result.get("evaluation_method", "Leave-One-Out"),
        artifact={
            key: value for key, value in result.items()
            if key != "tracking"
        },
        model_type="cosine_similarity_evaluation",
    )
    result["tracking"] = tracked
    return result


def _general_product_suggestions(
    db: Session,
    current_user: User,
    limit: int,
    reason: str,
    customers_available: int = 0,
    products_available: int = 0,
    purchased_products=None,
):
    """Return buyable catalog suggestions without inventing personalization."""
    purchased_products = set(purchased_products or [])
    available_products = db.query(
        Product,
        Inventory.current_stock
    ).join(
        Vendor,
        Product.vendor_id == Vendor.vendor_id
    ).join(
        Inventory,
        Product.product_id == Inventory.product_id
    ).filter(
        Vendor.status == "Active",
        Inventory.current_stock > 0
    ).order_by(
        Product.product_id.desc()
    ).all()

    if current_user.vendor_id is not None:
        available_products = [
            (product, current_stock)
            for product, current_stock in available_products
            if product.vendor_id != current_user.vendor_id
        ]

    suggestions = [
        {
            "product_id": product.product_id,
            "product_name": product.product_name,
            "category": product.category,
            "price": float(product.price),
            "vendor_id": product.vendor_id,
            "current_stock": current_stock,
        }
        for product, current_stock in available_products
        if product.product_id not in purchased_products
    ][:limit]

    if not available_products:
        message = "No active products with available stock can be suggested right now."
    elif not suggestions:
        message = "There are no new available products to suggest right now."
    else:
        message = f"{reason} Showing general product suggestions instead of personalized recommendations."

    return {
        "algorithm": "Cosine Similarity",
        "recommendation_type": "general",
        "recommendation_label": "General product suggestions",
        "message": message,
        "customers_available": customers_available,
        "products_available": products_available or len(available_products),
        "recommendations": suggestions,
        "recommendation_count": len(suggestions),
    }


@router.get("/")
def recommend_products(
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(require_customer),
    db: Session = Depends(get_db)
):
    # Retrieve completed customer-product interactions.
    interactions = db.query(
        Transaction.customer_id,
        Transaction.product_id,
        func.sum(Transaction.quantity).label("quantity")
    ).filter(
        Transaction.customer_id.isnot(None),
        Transaction.status == "Completed"
    ).group_by(
        Transaction.customer_id,
        Transaction.product_id
    ).all()

    customer_purchases = {
        row.product_id
        for row in interactions
        if row.customer_id == current_user.user_id
    }

    if not interactions:
        return _general_product_suggestions(
            db,
            current_user,
            limit,
            "No customer purchase interactions are available yet.",
        )

    # Build the customer-product interaction matrix.
    interaction_data = pd.DataFrame([
        {
            "customer_id": row.customer_id,
            "product_id": row.product_id,
            "quantity": row.quantity
        }
        for row in interactions
    ])

    matrix = interaction_data.pivot(
        index="customer_id",
        columns="product_id",
        values="quantity"
    ).fillna(0)

    # Include products that have not yet been purchased.
    all_products = db.query(Product).all()

    if not all_products:
        return _general_product_suggestions(
            db,
            current_user,
            limit,
            "The marketplace catalog is empty.",
        )

    product_ids = [product.product_id for product in all_products]

    matrix = matrix.reindex(columns=product_ids, fill_value=0)

    # Check whether useful interaction patterns exist.
    if matrix.shape[0] < 2 or matrix.shape[1] < 2:
        return _general_product_suggestions(
            db,
            current_user,
            limit,
            "More customer purchase interactions are needed to generate meaningful personalized recommendations.",
            customers_available=int(matrix.shape[0]),
            products_available=int(matrix.shape[1]),
            purchased_products=customer_purchases,
        )

    # Calculate product-to-product cosine similarity.
    similarity_matrix = cosine_similarity(matrix.T)

    similarity_df = pd.DataFrame(
        similarity_matrix,
        index=matrix.columns,
        columns=matrix.columns
    )

    customer_id = current_user.user_id

    if customer_id not in matrix.index:
        return _general_product_suggestions(
            db,
            current_user,
            limit,
            "You have no recorded purchase history yet.",
            customers_available=int(matrix.shape[0]),
            products_available=int(matrix.shape[1]),
            purchased_products=customer_purchases,
        )

    # Get products already purchased by this customer.
    customer_history = matrix.loc[customer_id]

    purchased_products = customer_history[
        customer_history > 0
    ].index.tolist()

    if not purchased_products:
        return _general_product_suggestions(
            db,
            current_user,
            limit,
            "You have no recorded purchase history yet.",
            customers_available=int(matrix.shape[0]),
            products_available=int(matrix.shape[1]),
            purchased_products=customer_purchases,
        )

    # Calculate recommendation scores using purchase quantities.
    scores = similarity_df[purchased_products].dot(
        customer_history[purchased_products]
    )

    scores = scores / customer_history[purchased_products].sum()

    # Remove products the customer has already purchased.
    scores = scores.drop(
        labels=purchased_products,
        errors="ignore"
    )

    scores = scores.sort_values(ascending=False)

    # Return only products with a positive similarity score.
    recommendations = []

    product_lookup = {
        product.product_id: product
        for product in all_products
    }

    for product_id, score in scores.items():

        if score <= 0:
            continue

        product = product_lookup.get(product_id)

        if not product:
            continue

        recommendations.append({
            "product_id": product.product_id,
            "product_name": product.product_name,
            "category": product.category,
            "price": float(product.price),
            "vendor_id": product.vendor_id,
            "similarity_score": round(float(score), 4)
        })

        if len(recommendations) >= limit:
            break

    return {
        "algorithm": "Cosine Similarity",
        "recommendation_type": "personalized",
        "recommendation_label": "Personalized recommendations",
        "customer_id": customer_id,
        "customers_available": int(matrix.shape[0]),
        "products_available": int(matrix.shape[1]),
        "purchased_products": purchased_products,
        "recommendations": recommendations,
        "recommendation_count": len(recommendations)
    }

@router.get("/evaluation")
def evaluate_recommendations(
    k: int = Query(default=5, ge=1, le=20),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    # Fetch actual completed purchase interactions.
    interactions = db.query(
        Transaction.customer_id,
        Transaction.product_id,
        func.sum(Transaction.quantity).label("quantity")
    ).filter(
        Transaction.customer_id.isnot(None),
        Transaction.status == "Completed"
    ).group_by(
        Transaction.customer_id,
        Transaction.product_id
    ).all()

    if not interactions:
        return _track_recommendation_evaluation({
            "algorithm": "Cosine Similarity",
            "message": "No purchase interactions available for evaluation.",
            "evaluated_customers": 0,
            "metrics": None
        }, k)

    interaction_data = pd.DataFrame([
        {
            "customer_id": row.customer_id,
            "product_id": row.product_id,
            "quantity": row.quantity
        }
        for row in interactions
    ])

    # Each eligible customer must have purchased at least 2 products.
    customer_product_counts = interaction_data.groupby(
        "customer_id"
    )["product_id"].nunique()

    eligible_customers = customer_product_counts[
        customer_product_counts >= 2
    ].index.tolist()

    if len(eligible_customers) < 2:
        return _track_recommendation_evaluation({
            "algorithm": "Cosine Similarity",
            "evaluation_method": "Leave-One-Out",
            "message": (
                "At least 2 customers with purchases across "
                "2 or more products each are required for evaluation."
            ),
            "customers_available": int(
                interaction_data["customer_id"].nunique()
            ),
            "eligible_customers": len(eligible_customers),
            "evaluated_customers": 0,
            "metrics": None
        }, k)

    # Hold out one purchased product for each eligible customer.
    training_rows = []
    test_rows = []

    for customer_id in eligible_customers:
        customer_rows = interaction_data[
            interaction_data["customer_id"] == customer_id
        ].sort_values("product_id")

        # Deterministic holdout for reproducible evaluation.
        held_out = customer_rows.iloc[-1]

        test_rows.append({
            "customer_id": customer_id,
            "product_id": int(held_out["product_id"])
        })

        training_rows.extend(
            customer_rows.iloc[:-1].to_dict("records")
        )

    training_data = pd.DataFrame(training_rows)

    # Build the training interaction matrix.
    matrix = training_data.pivot(
        index="customer_id",
        columns="product_id",
        values="quantity"
    ).fillna(0)

    all_products = db.query(Product).all()
    product_ids = [p.product_id for p in all_products]

    matrix = matrix.reindex(columns=product_ids, fill_value=0)

    if matrix.shape[0] < 2 or matrix.shape[1] < 2:
        return _track_recommendation_evaluation({
            "algorithm": "Cosine Similarity",
            "message": "Insufficient training data for evaluation.",
            "evaluated_customers": 0,
            "metrics": None
        }, k)

    # Calculate item-item cosine similarity using training data only.
    similarity_matrix = cosine_similarity(matrix.T)

    similarity_df = pd.DataFrame(
        similarity_matrix,
        index=matrix.columns,
        columns=matrix.columns
    )

    hits = 0
    precision_scores = []
    recall_scores = []

    for test in test_rows:
        customer_id = test["customer_id"]
        actual_product = test["product_id"]

        customer_history = matrix.loc[customer_id]

        purchased_products = customer_history[
            customer_history > 0
        ].index.tolist()

        if not purchased_products:
            continue

        # Generate recommendations using training purchases only.
        scores = similarity_df[purchased_products].dot(
            customer_history[purchased_products]
        )

        scores = scores / customer_history[purchased_products].sum()

        scores = scores.drop(
            labels=purchased_products,
            errors="ignore"
        )

        top_products = scores[
            scores > 0
        ].sort_values(ascending=False).head(k).index.tolist()

        # Compare recommendations against the hidden purchase.
        hit = int(actual_product in top_products)

        hits += hit
        precision_scores.append(hit / k)
        recall_scores.append(float(hit))

    evaluated = len(precision_scores)

    if evaluated == 0:
        return _track_recommendation_evaluation({
            "algorithm": "Cosine Similarity",
            "message": "No customers could be evaluated.",
            "evaluated_customers": 0,
            "metrics": None
        }, k)

    return _track_recommendation_evaluation({
        "algorithm": "Cosine Similarity",
        "evaluation_method": "Leave-One-Out",
        "evaluated_customers": evaluated,
        "k": k,
        "hits": hits,
        "metrics": {
            "precision_at_k": round(
                sum(precision_scores) / evaluated, 4
            ),
            "recall_at_k": round(
                sum(recall_scores) / evaluated, 4
            ),
            "hit_rate_at_k": round(
                hits / evaluated, 4
            )
        },
        "note": (
            "Metrics are calculated from held-out actual purchases. "
            "They are not guaranteed to represent future performance."
        )
    }, k)
