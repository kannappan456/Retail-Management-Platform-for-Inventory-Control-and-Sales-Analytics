import { useCallback, useEffect, useState } from "react";
import { RefreshCw, ShoppingBag } from "lucide-react";
import api from "./services/api";

function VendorOrders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadOrders = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get("/transactions/vendor-orders");
      setOrders(response.data.orders || []);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Could not load your orders. Check your connection and try again."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadOrders);
  }, [loadOrders]);

  const formatCurrency = (value) =>
    `₹${Number(value || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;

  const formatDate = (value) =>
    value ? new Date(value).toLocaleString("en-IN") : "Unavailable";

  return (
    <div className="vendor-orders-page">
      <div className="section-heading">
        <div>
          <h2>Orders</h2>
          <p>Customer orders containing your products.</p>
        </div>
        <button
          className="secondary-button"
          onClick={loadOrders}
          disabled={loading}
        >
          <RefreshCw size={16} />
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <div className="activity-card" role="alert">
          <p style={{ color: "#ff9ba4" }}>{error}</p>
          <button className="secondary-button" onClick={loadOrders}>
            Retry
          </button>
        </div>
      ) : loading ? (
        <div className="activity-card" role="status">
          <p style={{ color: "#9296aa" }}>Loading your orders…</p>
        </div>
      ) : orders.length === 0 ? (
        <div className="activity-card">
          <div className="empty-icon">
            <ShoppingBag size={26} />
          </div>
          <h3>No orders yet</h3>
          <p>
            Orders from customers who purchased your products will appear here.
          </p>
        </div>
      ) : (
        <div className="activity-card vendor-orders-card">
          <p className="vendor-orders-count">
            {orders.length} order record{orders.length !== 1 ? "s" : ""}
          </p>
          <div className="analytics-table-wrapper">
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>Order ID</th>
                  <th>Date</th>
                  <th>Product</th>
                  <th>Category</th>
                  <th>Qty</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.transaction_id}>
                    <td>
                      <span className="vendor-order-id">
                        #{order.transaction_id}
                      </span>
                    </td>
                    <td>{formatDate(order.transaction_date)}</td>
                    <td>
                      <strong style={{ display: "block", color: "#f0efff" }}>
                        {order.product_name || "Unavailable"}
                      </strong>
                    </td>
                    <td>{order.category || "Uncategorized"}</td>
                    <td>{Number(order.quantity).toLocaleString("en-IN")}</td>
                    <td>{formatCurrency(order.amount)}</td>
                    <td>
                      <span
                        className={`analytics-status analytics-status-${String(
                          order.status || "unknown"
                        ).toLowerCase()}`}
                      >
                        {order.status || "Unknown"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default VendorOrders;
