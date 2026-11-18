import { useCallback, useEffect, useState } from "react";
import { RefreshCw, ShoppingBag } from "lucide-react";
import api from "./services/api";

function CustomerOrders({ recentOrder, onContinueShopping }) {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadTransactions = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get("/transactions/mine");
      setTransactions(response.data.transactions || []);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not load your purchase history.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadTransactions);
  }, [loadTransactions]);

  const formatCurrency = (value) => `₹${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  const formatDate = (value) => value ? new Date(value).toLocaleString("en-IN") : "Unavailable";

  return (
    <div className="activity-card customer-orders">
      <div className="customer-orders-heading">
        <div>
          <h2><ShoppingBag size={22} /> My Purchase History</h2>
          <p>Purchases appear as individual transaction records.</p>
        </div>
        <button className="secondary-button" onClick={loadTransactions} disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {recentOrder && (
        <div className="customer-order-confirmation" role="status">
          <strong>Recent checkout completed</strong>
          <span>Reference: {recentOrder.checkout_reference || "Unavailable"}</span>
          <span>Total: {formatCurrency(recentOrder.total_amount)}</span>
        </div>
      )}

      {loading ? (
        <p className="analytics-message" role="status">Loading your purchase history…</p>
      ) : error ? (
        <div className="bi-error" role="alert"><p>{error}</p><button className="secondary-button" onClick={loadTransactions}>Retry</button></div>
      ) : transactions.length ? (
        <div className="analytics-table-wrapper">
          <table className="analytics-table">
            <thead><tr><th>Date</th><th>Product</th><th>Vendor</th><th>Quantity</th><th>Amount</th><th>Status</th></tr></thead>
            <tbody>{transactions.map((item) => (
              <tr key={item.transaction_id}>
                <td>{formatDate(item.transaction_date)}</td>
                <td>{item.product_name || "Unavailable"}<small>{item.category || "Uncategorized"}</small></td>
                <td>{item.business_name || "Unavailable"}</td>
                <td>{Number(item.quantity).toLocaleString("en-IN")}</td>
                <td>{formatCurrency(item.amount)}</td>
                <td><span className={`analytics-status analytics-status-${String(item.status || "unknown").toLowerCase()}`}>{item.status || "Unknown"}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : (
        <div className="recommendation-empty-state"><ShoppingBag size={28} /><strong>No purchase records yet</strong><p>Completed checkouts will appear here.</p></div>
      )}

      <button className="primary-button" onClick={onContinueShopping}>Continue Shopping</button>
    </div>
  );
}

export default CustomerOrders;
