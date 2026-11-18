
import { useCallback, useEffect, useState } from "react";
import {
  Users,
  IndianRupee,
  ShoppingBag,
  TrendingUp,
  RefreshCw,
} from "lucide-react";

import api from "./services/api";

function CustomerAnalytics() {
  const [data, setData] = useState(null);
  const [topCustomers, setTopCustomers] = useState([]);
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [overviewRes, topRes, segmentRes] = await Promise.all([
        api.get("/customer-analytics/overview"),
        api.get("/customer-analytics/top-customers"),
        api.get("/customer-analytics/segments"),
      ]);

      setData(overviewRes.data);
      setTopCustomers(topRes.data.top_customers || []);
      setSegments(segmentRes.data.segments || []);
    } catch (err) {
      console.error("Customer analytics error:", err);
      setError(
        err.response?.data?.detail ||
        "Could not load customer analytics."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadData);
  }, [loadData]);

  const currency = (value) =>
    `₹${Number(value || 0).toLocaleString("en-IN", {
      maximumFractionDigits: 2,
    })}`;

  if (loading) {
    return <div className="activity-card">Loading customer analytics...</div>;
  }

  if (error) {
    return (
      <div className="activity-card">
        <h3>Customer Analytics Error</h3>
        <p>{error}</p>
        <button className="primary-button" onClick={loadData}>
          Try Again
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="section-heading">
        <div>
          <h2>Customer Analytics</h2>
          <p>Understand customer spending and purchasing behaviour.</p>
        </div>

        <button className="secondary-button" onClick={loadData}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-top">
            <span>Total Customers</span>
            <Users size={20} />
          </div>
          <h2>{data?.total_customers ?? 0}</h2>
          <div className="stat-change">Customers with recorded purchases</div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>Customer Revenue</span>
            <IndianRupee size={20} />
          </div>
          <h2>{currency(data?.total_customer_revenue)}</h2>
          <div className="stat-change">Revenue from completed orders</div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>Total Orders</span>
            <ShoppingBag size={20} />
          </div>
          <h2>{data?.total_customer_orders ?? 0}</h2>
          <div className="stat-change">Completed customer orders</div>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <span>Average Customer Spend</span>
            <TrendingUp size={20} />
          </div>
          <h2>{currency(data?.average_customer_spend)}</h2>
          <div className="stat-change">Average spending per customer</div>
        </div>
      </div>

      <div className="activity-card">
        <h3>Customer Spending Details</h3>

        {data?.customers?.length ? (
          <div className="products-list">
            {data.customers.map((customer) => (
              <div className="product-row" key={customer.customer_id}>
                <div style={{ flex: 1 }}>
                  <strong>{customer.email}</strong>
                  <p>Customer ID: {customer.customer_id}</p>
                </div>

                <div>
                  <strong>{customer.total_orders} orders</strong>
                  <p>{customer.total_units} units purchased</p>
                </div>

                <div>
                  <strong>{currency(customer.total_spent)}</strong>
                  <p>AOV: {currency(customer.average_order_value)}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p>No customer purchase records available.</p>
        )}
      </div>

      <div className="activity-card">
        <h3>Top Customers</h3>

        {topCustomers.length ? (
          <div className="products-list">
            {topCustomers.map((customer, index) => (
              <div className="product-row" key={customer.customer_id}>
                <strong>#{index + 1} {customer.email}</strong>
                <strong>{currency(customer.total_spent)}</strong>
              </div>
            ))}
          </div>
        ) : (
          <p>No top customer data available yet.</p>
        )}
      </div>

      <div className="activity-card">
        <h3>Customer Segmentation — K-Means</h3>

        {segments.length ? (
          segments.map((segment, index) => (
            <div className="product-row" key={index}>
              <strong>{segment.segment_name || `Segment ${index + 1}`}</strong>
              <span>{segment.customer_count} customers</span>
            </div>
          ))
        ) : (
          <p>
            Not enough customer purchase history to generate reliable
            customer segments yet. More customer data is required.
          </p>
        )}
      </div>
    </div>
  );
}

export default CustomerAnalytics;
