import { useCallback, useEffect, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";

import api from "./services/api";

function Analytics() {
  const [summary, setSummary] = useState(null);
  const [products, setProducts] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [evaluation, setEvaluation] = useState(null);
  const [evaluationLoading, setEvaluationLoading] = useState(true);
  const [evaluationError, setEvaluationError] = useState("");

  const loadRecommendationEvaluation = useCallback(async () => {
    try {
      const response = await api.get("/recommendations/evaluation");
      setEvaluation(response.data);
    } catch (err) {
      setEvaluationError(
        err.response?.data?.detail ||
          "Unable to load recommendation evaluation. Please retry."
      );
    } finally {
      setEvaluationLoading(false);
    }
  }, []);

  function retryRecommendationEvaluation() {
    setEvaluationLoading(true);
    setEvaluationError("");
    loadRecommendationEvaluation();
  }

  useEffect(() => {
    async function loadAnalytics() {
      try {
        const results = await Promise.all([
          api.get("/analytics/summary"),
          api.get("/analytics/products"),
          api.get("/analytics/vendors"),
        ]);

        setSummary(results[0].data);

        const productData = results[1].data;
        setProducts(
          Array.isArray(productData)
            ? productData
            : productData.products || []
        );

        const vendorData = results[2].data;
        setVendors(
          Array.isArray(vendorData)
            ? vendorData
            : vendorData.vendors || []
        );
      } catch (err) {
        setError(
          err.response?.data?.detail ||
            "Unable to load analytics. Please log in again and retry."
        );
      } finally {
        setLoading(false);
      }
    }

    loadAnalytics();
    Promise.resolve().then(loadRecommendationEvaluation);
  }, [loadRecommendationEvaluation]);

  if (loading) {
    return (
      <div className="analytics-page">
        <div className="analytics-message">Loading analytics...</div>
        <RecommendationEvaluation
          data={evaluation}
          loading={evaluationLoading}
          error={evaluationError}
          onRetry={retryRecommendationEvaluation}
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="analytics-page">
        <div className="analytics-error">{error}</div>
        <RecommendationEvaluation
          data={evaluation}
          loading={evaluationLoading}
          error={evaluationError}
          onRetry={retryRecommendationEvaluation}
        />
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="analytics-page">
        <div className="analytics-message">No analytics data available.</div>
        <RecommendationEvaluation
          data={evaluation}
          loading={evaluationLoading}
          error={evaluationError}
          onRetry={retryRecommendationEvaluation}
        />
      </div>
    );
  }

  // Support the field names used by different summary responses.
  const completedSales =
    summary.completed_sales ??
    summary.completed_transactions ??
    summary.total_completed_transactions ??
    0;

  const metrics = [
    {
      title: "Total Revenue",
      value: `₹${Number(
        summary.total_revenue || 0
      ).toLocaleString("en-IN")}`,
      icon: "₹",
    },
    {
      title: "Completed Sales",
      value: Number(completedSales).toLocaleString("en-IN"),
      icon: "✓",
    },
    {
      title: "Units Sold",
      value: Number(
        summary.total_units_sold || 0
      ).toLocaleString("en-IN"),
      icon: "📦",
    },
    {
      title: "Total Products",
      value: Number(
        summary.total_products || 0
      ).toLocaleString("en-IN"),
      icon: "🛍️",
    },
    {
      title: "Total Vendors",
      value: Number(
        summary.total_vendors || 0
      ).toLocaleString("en-IN"),
      icon: "🏪",
    },
  ];

  // Product chart data
  const productChartData = products.map((product) => ({
    name:
      product.product_name ||
      product.name ||
      `Product ${product.product_id}`,
    Revenue: Number(product.revenue || 0),
    "Units Sold": Number(product.units_sold || 0),
  }));

  // Vendor chart data
  const vendorChartData = vendors.map((vendor) => ({
    name:
      vendor.business_name ||
      `Vendor ${vendor.vendor_id}`,
    Revenue: Number(vendor.revenue || 0),
    Products: Number(vendor.product_count || 0),
  }));

  // Vendor approval status
  const statusData = [
    {
      name: "Active",
      value: vendors.filter(
        (vendor) => vendor.status === "Active"
      ).length,
    },
    {
      name: "Pending",
      value: vendors.filter(
        (vendor) => vendor.status === "Pending"
      ).length,
    },
    {
      name: "Suspended",
      value: vendors.filter(
        (vendor) => vendor.status === "Suspended"
      ).length,
    },
  ].filter((item) => item.value > 0);

  const pieColors = [
    "#16a34a",
    "#f59e0b",
    "#dc2626",
  ];

  // Shared axis settings to improve readability.
  const axisStyle = {
    fontSize: 11,
    fill: "#64748b",
  };

  const chartMargin = {
    top: 10,
    right: 15,
    left: 5,
    bottom: 25,
  };

  return (
    <div className="analytics-page">
      {/* Dashboard heading */}
      <div className="analytics-heading">
        <div>
          <h2>Marketplace Analytics</h2>
          <p>
            Monitor revenue, products, vendors, and marketplace
            performance.
          </p>
        </div>

        <span className="analytics-live-badge">
          Live Database Data
        </span>
      </div>

      {/* Summary cards */}
      <RevenueAnalyticsPanel />

      <div className="analytics-metrics">
        {metrics.map((metric) => (
          <div
            className="analytics-metric-card"
            key={metric.title}
          >
            <div className="analytics-metric-icon">
              {metric.icon}
            </div>

            <p>{metric.title}</p>

            <h3>{metric.value}</h3>
          </div>
        ))}
      </div>

      <RecommendationEvaluation
        data={evaluation}
        loading={evaluationLoading}
        error={evaluationError}
        onRetry={retryRecommendationEvaluation}
      />

      {/* Charts */}
      <div className="analytics-chart-grid">
        {/* Product Revenue */}
        <section className="analytics-card">
          <h3>Product Revenue</h3>

          <p className="analytics-subtitle">
            Revenue generated by each product
          </p>

          {productChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={340}>
              <BarChart
                data={productChartData}
                margin={chartMargin}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#e2e8f0"
                />

                <XAxis
                  dataKey="name"
                  angle={-25}
                  textAnchor="end"
                  height={100}
                  interval={0}
                  tick={axisStyle}
                  tickMargin={12}
                  axisLine={{ stroke: "#cbd5e1" }}
                  tickLine={false}
                />

                <YAxis
                  tick={axisStyle}
                  width={55}
                  tickFormatter={(value) =>
                    value >= 1000
                      ? `₹${(value / 1000).toFixed(0)}k`
                      : `₹${value}`
                  }
                  axisLine={false}
                  tickLine={false}
                />

                <Tooltip
                  formatter={(value) => [
                    `₹${Number(value).toLocaleString("en-IN")}`,
                    "Revenue",
                  ]}
                  contentStyle={{
                    borderRadius: "10px",
                    border: "1px solid #e2e8f0",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                  }}
                />

                <Legend verticalAlign="bottom" />

                <Bar
                  dataKey="Revenue"
                  fill="#2563eb"
                  radius={[5, 5, 0, 0]}
                  maxBarSize={48}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p>No product revenue data available yet.</p>
          )}
        </section>

        {/* Product Units Sold */}
        <section className="analytics-card">
          <h3>Product Units Sold</h3>

          <p className="analytics-subtitle">
            Number of units sold per product
          </p>

          {productChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={340}>
              <BarChart
                data={productChartData}
                margin={chartMargin}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#e2e8f0"
                />

                <XAxis
                  dataKey="name"
                  angle={-25}
                  textAnchor="end"
                  height={100}
                  interval={0}
                  tick={axisStyle}
                  tickMargin={12}
                  axisLine={{ stroke: "#cbd5e1" }}
                  tickLine={false}
                />

                <YAxis
                  allowDecimals={false}
                  tick={axisStyle}
                  axisLine={false}
                  tickLine={false}
                />

                <Tooltip
                  formatter={(value) => [
                    Number(value).toLocaleString("en-IN"),
                    "Units Sold",
                  ]}
                  contentStyle={{
                    borderRadius: "10px",
                    border: "1px solid #e2e8f0",
                  }}
                />

                <Legend verticalAlign="bottom" />

                <Bar
                  dataKey="Units Sold"
                  fill="#0d9488"
                  radius={[5, 5, 0, 0]}
                  maxBarSize={48}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p>No sales data available yet.</p>
          )}
        </section>

        {/* Vendor Revenue */}
        <section className="analytics-card">
          <h3>Vendor Revenue</h3>

          <p className="analytics-subtitle">
            Revenue generated by each vendor
          </p>

          {vendorChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={340}>
              <BarChart
                data={vendorChartData}
                margin={chartMargin}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#e2e8f0"
                />

                <XAxis
                  dataKey="name"
                  angle={-25}
                  textAnchor="end"
                  height={100}
                  interval={0}
                  tick={axisStyle}
                  tickMargin={12}
                  axisLine={{ stroke: "#cbd5e1" }}
                  tickLine={false}
                />

                <YAxis
                  tick={axisStyle}
                  width={55}
                  tickFormatter={(value) =>
                    value >= 1000
                      ? `₹${(value / 1000).toFixed(0)}k`
                      : `₹${value}`
                  }
                  axisLine={false}
                  tickLine={false}
                />

                <Tooltip
                  formatter={(value) => [
                    `₹${Number(value).toLocaleString("en-IN")}`,
                    "Revenue",
                  ]}
                  contentStyle={{
                    borderRadius: "10px",
                    border: "1px solid #e2e8f0",
                  }}
                />

                <Legend verticalAlign="bottom" />

                <Bar
                  dataKey="Revenue"
                  fill="#7c3aed"
                  radius={[5, 5, 0, 0]}
                  maxBarSize={48}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p>No vendor revenue data available yet.</p>
          )}
        </section>

        {/* Vendor Approval Status */}
        <section className="analytics-card">
          <h3>Vendor Approval Status</h3>

          <p className="analytics-subtitle">
            Overview of vendor account statuses
          </p>

          {statusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={340}>
              <PieChart>
                <Pie
                  data={statusData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="45%"
                  outerRadius={100}
                  paddingAngle={3}
                  label
                >
                  {statusData.map((entry, index) => (
                    <Cell
                      key={entry.name}
                      fill={pieColors[index % pieColors.length]}
                    />
                  ))}
                </Pie>

                <Tooltip />

                <Legend verticalAlign="bottom" />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p>No vendor status data available yet.</p>
          )}
        </section>
      </div>

      {/* Product Performance Table */}
      <section className="analytics-card analytics-table-card">
        <h3>Product Performance Details</h3>

        <div className="analytics-table-wrapper">
          <table className="analytics-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Category</th>
                <th>Units Sold</th>
                <th>Revenue</th>
              </tr>
            </thead>

            <tbody>
              {products.map((product) => (
                <tr key={product.product_id}>
                  <td>
                    {product.product_name ||
                      product.name ||
                      "Unnamed Product"}
                  </td>

                  <td>
                    {product.category || "Uncategorized"}
                  </td>

                  <td>
                    {Number(
                      product.units_sold || 0
                    ).toLocaleString("en-IN")}
                  </td>

                  <td>
                    ₹
                    {Number(
                      product.revenue || 0
                    ).toLocaleString("en-IN")}
                  </td>
                </tr>
              ))}

              {products.length === 0 && (
                <tr>
                  <td colSpan="4">
                    No products found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Vendor Performance Table */}
      <section className="analytics-card analytics-table-card">
        <h3>Vendor Performance Details</h3>

        <div className="analytics-table-wrapper">
          <table className="analytics-table">
            <thead>
              <tr>
                <th>Vendor</th>
                <th>Status</th>
                <th>Products</th>
                <th>Revenue</th>
              </tr>
            </thead>

            <tbody>
              {vendors.map((vendor) => (
                <tr key={vendor.vendor_id}>
                  <td>
                    {vendor.business_name ||
                      `Vendor ${vendor.vendor_id}`}
                  </td>

                  <td>
                    <span
                      className={`analytics-status analytics-status-${String(
                        vendor.status || "unknown"
                      ).toLowerCase()}`}
                    >
                      {vendor.status || "Unknown"}
                    </span>
                  </td>

                  <td>
                    {Number(vendor.product_count || 0)}
                  </td>

                  <td>
                    ₹
                    {Number(
                      vendor.revenue || 0
                    ).toLocaleString("en-IN")}
                  </td>
                </tr>
              ))}

              {vendors.length === 0 && (
                <tr>
                  <td colSpan="4">
                    No vendors found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function RevenueAnalyticsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overview, monthly, vendors, categories, products] = await Promise.all([
        api.get("/analytics/revenue/overview"),
        api.get("/analytics/revenue/monthly?months=12"),
        api.get("/analytics/benchmarking/vendors?limit=10"),
        api.get("/analytics/benchmarking/categories"),
        api.get("/analytics/benchmarking/products?limit=10"),
      ]);
      setData({
        overview: overview.data,
        months: monthly.data.months || [],
        vendors: vendors.data.vendors || [],
        categories: categories.data.categories || [],
        products: products.data.products || [],
      });
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to load revenue analytics.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { Promise.resolve().then(load); }, [load]);

  if (loading) return <section className="analytics-card revenue-panel" role="status">Loading revenue and benchmarking data…</section>;
  if (error) return <section className="analytics-card revenue-panel" role="alert"><p>{error}</p><button className="secondary-button" onClick={load}>Retry</button></section>;
  if (!data) return null;

  const overview = data.overview;
  const money = (value) => value == null ? "—" : `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  const count = (value) => value == null ? "—" : Number(value).toLocaleString("en-IN");
  const growth = overview.mom_revenue_growth_percentage;
  const kpis = [
    ["GMV", money(overview.gmv)],
    ["Completed revenue", money(overview.completed_revenue)],
    ["Completed transaction records", count(overview.completed_transaction_records)],
    ["MoM revenue growth", growth == null ? "—" : `${Number(growth).toFixed(2)}%`],
    ["Average transaction value (proxy)", money(overview.average_transaction_value)],
    ["Average order value", "Unavailable"],
  ];

  return (
    <section className="revenue-panel" aria-label="Revenue analytics and marketplace benchmarking">
      <div className="revenue-panel-heading">
        <div><h3>Revenue Analytics &amp; Marketplace Benchmarking</h3><p>{overview.definition} {overview.aov_note}</p></div>
        <button className="secondary-button" onClick={load}>Refresh</button>
      </div>
      <div className="revenue-kpis">
        {kpis.map(([label, value]) => <article className="revenue-kpi" key={label}><span>{label}</span><strong>{value}</strong></article>)}
      </div>
      <p className="revenue-note">Order count and true AOV are unavailable because transaction records are not grouped by order. Cancelled and refunded transaction records are excluded.</p>
      <div className="revenue-grid">
        <section className="analytics-card"><h3>Revenue trend</h3>{data.months.length ? <ResponsiveContainer width="100%" height={260}><LineChart data={data.months}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="month" /><YAxis /><Tooltip formatter={(value) => money(value)} /><Line type="monotone" dataKey="revenue" stroke="#2563eb" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer> : <p>No monthly revenue records.</p>}</section>
        <section className="analytics-card"><h3>Revenue by category</h3>{data.categories.length ? <ResponsiveContainer width="100%" height={260}><BarChart data={data.categories}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="category" /><YAxis /><Tooltip formatter={(value) => money(value)} /><Bar dataKey="revenue" fill="#0d9488" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer> : <p>No category revenue records.</p>}</section>
      </div>
      <div className="revenue-grid">
        <RevenueTable title="Top vendors" headers={["Vendor", "Revenue", "Share", "Transactions", "Avg. transaction value"]} rows={data.vendors.map((item) => [item.business_name, money(item.revenue), item.revenue_contribution_percentage == null ? "—" : `${Number(item.revenue_contribution_percentage).toFixed(2)}%`, count(item.completed_transaction_records), money(item.average_transaction_value)])} />
        <RevenueTable title="Top products" headers={["Product", "Category", "Vendor", "Units", "Revenue"]} rows={data.products.map((item) => [item.product_name, item.category || "Uncategorized", item.business_name, count(item.units_sold), money(item.revenue)])} />
      </div>
    </section>
  );
}

function RevenueTable({ title, headers, rows }) {
  return <section className="analytics-card analytics-table-card"><h3>{title}</h3><div className="analytics-table-wrapper"><table className="analytics-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.length ? rows.map((row, index) => <tr key={`${title}-${index}`}>{row.map((cell, cellIndex) => <td key={`${index}-${cellIndex}`}>{cell ?? "—"}</td>)}</tr>) : <tr><td colSpan={headers.length}>No data available.</td></tr>}</tbody></table></div></section>;
}

function RecommendationEvaluation({ data, loading, error, onRetry }) {
  const hasMetrics = data?.metrics != null;
  const count = (value) =>
    value == null ? "—" : Number(value).toLocaleString("en-IN");
  const percentage = (value) =>
    value == null ? "—" : `${(Number(value) * 100).toFixed(2)}%`;

  return (
    <section className="analytics-card recommendation-evaluation">
      <div className="evaluation-heading">
        <div>
          <h3>Recommendation Evaluation</h3>
          <p className="evaluation-description">
            Offline evaluation based on held-out completed purchases.
          </p>
        </div>
        {data?.algorithm && (
          <span className="evaluation-algorithm">{data.algorithm}</span>
        )}
      </div>

      {loading ? (
        <div className="analytics-message" role="status">
          Loading recommendation evaluation...
        </div>
      ) : error ? (
        <div className="evaluation-error" role="alert">
          <p>{error}</p>
          <button className="evaluation-retry" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : (
        <>
          <dl className="evaluation-details">
            <div><dt>Evaluation method</dt><dd>{data?.evaluation_method || "—"}</dd></div>
            <div><dt>Total customers available</dt><dd>{count(data?.customers_available)}</dd></div>
            <div><dt>Eligible customers</dt><dd>{count(data?.eligible_customers)}</dd></div>
            <div><dt>Evaluated customers</dt><dd>{count(data?.evaluated_customers)}</dd></div>
            <div><dt>K value</dt><dd>{count(data?.k)}</dd></div>
          </dl>

          {hasMetrics ? (
            <div className="evaluation-metrics">
              <div><span>Precision@K</span><strong>{percentage(data.metrics.precision_at_k)}</strong></div>
              <div><span>Recall@K</span><strong>{percentage(data.metrics.recall_at_k)}</strong></div>
              <div><span>Hit Rate</span><strong>{percentage(data.metrics.hit_rate_at_k)}</strong></div>
            </div>
          ) : (
            <div className="evaluation-insufficient" role="status">
              <strong>{data?.message || "Evaluation metrics are unavailable."}</strong>
              <p>More customer purchase interactions are needed to calculate recommendation evaluation metrics.</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default Analytics;
