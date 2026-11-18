
import { useEffect, useState } from "react";
import {
  Sparkles,
  Package,
  Users,
  RefreshCw,
  Brain,
} from "lucide-react";

import api from "./services/api";

function RecommendationDashboard({ onAddToCart, onToggleWishlist, wishlist = [] }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadRecommendations() {
    setLoading(true);
    setError("");

    try {
      const response = await api.get("/recommendations/");
      setData(response.data);
    } catch (err) {
      console.error("Recommendation error:", err);
      setError(
        err.response?.data?.detail ||
        "Could not load product recommendations."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    Promise.resolve().then(loadRecommendations);
  }, []);

  if (loading) {
    return (
      <div className="activity-card">
        Loading product recommendations...
      </div>
    );
  }

  if (error) {
    return (
      <div className="activity-card">
        <h3>Recommendation Error</h3>
        <p>{error}</p>
        <button className="primary-button" onClick={loadRecommendations}>
          Try Again
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="section-heading">
        <div>
          <h2>Product Recommendations</h2>
          <p>Explore products selected from the current marketplace catalog.</p>
        </div>

        <button className="secondary-button" onClick={loadRecommendations}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-top">
            <span>Algorithm</span>
            <Brain size={20} />
          </div>
          <h2>{data?.algorithm || "N/A"}</h2>
          <div className="stat-change">Recommendation method</div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>Customers Available</span>
            <Users size={20} />
          </div>
          <h2>{data?.customers_available ?? 0}</h2>
          <div className="stat-change">Purchase interaction records</div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>Products Available</span>
            <Package size={20} />
          </div>
          <h2>{data?.products_available ?? 0}</h2>
          <div className="stat-change">Products in catalogue</div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>Recommendations</span>
            <Sparkles size={20} />
          </div>
          <h2>{data?.recommendations?.length ?? 0}</h2>
          <div className="stat-change">Generated recommendations</div>
        </div>
      </div>

      <div className="activity-card">
        <h3>
          <Sparkles size={19} /> Recommended Products
        </h3>

        <span className={`recommendation-type-badge ${data?.recommendation_type === "general" ? "general" : "personalized"}`}>
          {data?.recommendation_label || (data?.recommendation_type === "general" ? "General product suggestions" : "Personalized recommendations")}
        </span>

        <p>{data?.message}</p>

        {data?.recommendations?.length ? (
          <div className="product-grid recommendation-product-grid">
            {data.recommendations.map((item) => {
              const isWishlisted = wishlist.some(
                (product) => (product.product_id ?? product.id) === item.product_id
              );

              return (
                <div className="market-product" key={item.product_id}>
                  <div className="market-product-icon"><Package size={35} /></div>
                  <button className="secondary-button" onClick={() => onToggleWishlist?.(item)}>
                    {isWishlisted ? "♥ Remove from Wishlist" : "♡ Add to Wishlist"}
                  </button>
                  <h3>{item.product_name || `Product ${item.product_id}`}</h3>
                  <p>{item.category || "General"}</p>
                  <strong>₹{Number(item.price || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong>
                  {item.current_stock != null && <p>{item.current_stock} available</p>}
                  {data.recommendation_type !== "general" && item.similarity_score != null && (
                    <p>Similarity: {Number(item.similarity_score).toFixed(3)}</p>
                  )}
                  <button className="primary-button" onClick={() => onAddToCart?.(item)}>
                    Add to Cart
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="recommendation-empty-state">
            <Package size={28} />
            <strong>No products to show right now</strong>
            <p>{data?.message || "There are no available marketplace products at the moment."}</p>
          </div>
        )}
      </div>

      <div className="activity-card">
        <h3>About these suggestions</h3>
        {data?.recommendation_type === "general" ? (
          <p>These are general suggestions from active vendors with available stock. They are not personalized using your purchase history.</p>
        ) : (
          <>
            <p>Personalized recommendations use completed customer-product purchases.</p>
            <p>Cosine Similarity ranks products related to products in your purchase history.</p>
            <p>Products already purchased by you are excluded from personalized results.</p>
          </>
        )}
      </div>
    </div>
  );
}

export default RecommendationDashboard;
