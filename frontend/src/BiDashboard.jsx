import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart,
  Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Download, RefreshCw } from "lucide-react";
import api from "./services/api";

const chartColors = ["#2563eb", "#0d9488", "#7c3aed", "#f59e0b", "#ef4444", "#64748b"];
const number = (value) => value == null ? "Unavailable" : Number(value).toLocaleString("en-IN");
const money = (value) => value == null ? "Unavailable" : `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const rate = (value) => value == null ? "Unavailable" : `${(Number(value) * 100).toFixed(2)}%`;

export default function BiDashboard() {
  const [months, setMonths] = useState(12);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState("");

  const load = useCallback(async (signal) => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get("/reports/bi/overview", { params: { months }, signal });
      if (!signal?.aborted) setData(response.data);
    } catch (err) {
      if (!signal?.aborted) setError(err.response?.data?.detail || "Unable to load business intelligence data.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [months]);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => load(controller.signal));
    return () => controller.abort();
  }, [load]);

  const inventoryStatus = useMemo(() => {
    const products = data?.inventory?.overview?.products || [];
    return ["In Stock", "Low Stock", "Out of Stock"].map((status) => ({
      name: status,
      value: products.filter((item) => item.stock_status === status).length,
    })).filter((item) => item.value > 0);
  }, [data]);

  const download = async (format) => {
    setDownloading(format);
    setError("");
    try {
      const response = await api.get(`/reports/bi/${format}`, {
        params: { months },
        responseType: "blob",
      });
      const type = format === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
      const blob = new Blob([response.data], { type });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = format === "pdf" ? "shopsense-bi-report.pdf" : "shopsense-bi-report.xlsx";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      let message = "Report download failed.";
      if (err.response?.data instanceof Blob) {
        try {
          const payload = JSON.parse(await err.response.data.text());
          message = payload.detail || message;
        } catch { /* Retain the generic download error. */ }
      } else {
        message = err.response?.data?.detail || message;
      }
      setError(message);
    } finally {
      setDownloading("");
    }
  };

  if (loading && !data) return <div className="analytics-page bi-dashboard"><div className="analytics-card" role="status">Loading business intelligence dashboard…</div></div>;
  if (error && !data) return <div className="analytics-page bi-dashboard"><div className="analytics-card bi-error" role="alert"><p>{error}</p><button className="secondary-button" onClick={() => load()}>Retry</button></div></div>;
  if (!data) return null;

  const market = data.marketplace || {};
  const overview = data.inventory?.overview || {};
  const customers = data.customers?.summary || {};
  const recommendation = data.recommendation_evaluation || {};
  const revenue = data.revenue?.overview || {};
  const segments = data.customers?.segmentation?.segments || [];
  const workflowCounts = data.workflow?.counts || {};
  const workflowChart = Object.entries(workflowCounts).map(([name, value]) => ({ name, value }));
  const kpis = [
    ["Completed revenue", money(market.completed_revenue)],
    ["Gross merchandise value", money(market.gmv)],
    ["Completed transaction records", number(market.completed_transaction_records)],
    ["Active vendors", number(market.total_active_vendors)],
    ["Products", number(market.total_products)],
    ["Revenue growth", market.mom_revenue_growth_percentage == null ? "Unavailable" : `${Number(market.mom_revenue_growth_percentage).toFixed(2)}%`],
  ];

  return (
    <div className="analytics-page bi-dashboard">
      <header className="bi-toolbar">
        <div><h2>Business Intelligence</h2><p>Marketplace, inventory, customer, and workflow performance from ShopSense data.</p></div>
        <div className="bi-actions">
          <label>Revenue window <select value={months} onChange={(event) => setMonths(Number(event.target.value))}>{[3, 6, 12, 24, 36, 60].map((value) => <option key={value} value={value}>{value} months</option>)}</select></label>
          <button className="secondary-button" onClick={() => load()} disabled={loading}><RefreshCw size={16} /> Refresh</button>
          <button className="secondary-button" onClick={() => download("pdf")} disabled={Boolean(downloading)}><Download size={16} /> {downloading === "pdf" ? "Preparing PDF…" : "PDF"}</button>
          <button className="primary-button" onClick={() => download("excel")} disabled={Boolean(downloading)}><Download size={16} /> {downloading === "excel" ? "Preparing Excel…" : "Excel"}</button>
        </div>
      </header>
      {error && <div className="bi-inline-error" role="alert">{error}</div>}
      {loading && <div className="bi-refreshing" role="status">Refreshing dashboard…</div>}

      <section className="bi-kpis" aria-label="Marketplace overview">
        {kpis.map(([label, value]) => <article className="analytics-card bi-kpi" key={label}><span>{label}</span><strong>{value}</strong></article>)}
      </section>
      <p className="bi-note">{market.definition || "Revenue definition unavailable."} {market.aov_note || ""}</p>

      <div className="bi-grid">
        <BiChart title="Monthly revenue" subtitle={`${data.selected_months} month window`} empty="No monthly revenue data available.">
          {(data.revenue?.monthly || []).length ? <ResponsiveContainer width="100%" height={290}><LineChart data={data.revenue.monthly}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="month" /><YAxis tickFormatter={(value) => `₹${Number(value).toLocaleString("en-IN")}`} /><Tooltip formatter={(value) => money(value)} /><Line type="monotone" dataKey="revenue" name="Completed revenue" stroke="#2563eb" strokeWidth={2.5} dot /></LineChart></ResponsiveContainer> : null}
        </BiChart>
        <BiChart title="Vendor revenue comparison" empty="No vendor performance data available.">
          {(data.vendors || []).length ? <ResponsiveContainer width="100%" height={290}><BarChart data={(data.vendors || []).slice(0, 12)}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="business_name" tick={{ fontSize: 11 }} /><YAxis /><Tooltip formatter={(value) => money(value)} /><Bar dataKey="revenue" name="Revenue" fill="#7c3aed" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer> : null}
        </BiChart>
        <BiChart title="Category revenue" empty="No category data available.">
          {(data.categories || []).length ? <ResponsiveContainer width="100%" height={290}><PieChart><Pie data={data.categories} dataKey="revenue" nameKey="category" outerRadius="68%" label={({ name }) => name}>{data.categories.map((entry, index) => <Cell key={entry.category || index} fill={chartColors[index % chartColors.length]} />)}</Pie><Tooltip formatter={(value) => money(value)} /><Legend /></PieChart></ResponsiveContainer> : null}
        </BiChart>
        <BiChart title="Inventory status" empty="No inventory records available.">
          {inventoryStatus.length ? <ResponsiveContainer width="100%" height={290}><PieChart><Pie data={inventoryStatus} dataKey="value" nameKey="name" outerRadius="68%" label>{inventoryStatus.map((item, index) => <Cell key={item.name} fill={chartColors[index]} />)}</Pie><Tooltip /><Legend /></PieChart></ResponsiveContainer> : null}
        </BiChart>
        <BiChart title="Customer segments" empty={data.customers?.segmentation?.message || "No tracked customer segments are available."}>
          {segments.length ? <ResponsiveContainer width="100%" height={290}><BarChart data={segments}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="cluster_id" tickFormatter={(value) => `Cluster ${value}`} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="customer_count" name="Customers" fill="#0d9488" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer> : null}
        </BiChart>
        <BiChart title="Workflow execution status" empty="No workflow execution history in this process.">
          {workflowChart.some((item) => item.value > 0) ? <ResponsiveContainer width="100%" height={290}><BarChart data={workflowChart}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="value" name="Executions" fill="#2563eb" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer> : null}
        </BiChart>
      </div>

      <section className="analytics-card bi-section"><h3>Inventory intelligence</h3><div className="bi-summary-grid"><Summary label="Inventory units" value={number(overview.total_stock_units)} /><Summary label="Inventory value" value={money(overview.total_inventory_value)} /><Summary label="Low-stock products" value={number(data.inventory?.low_stock?.total_low_stock_products)} /><Summary label="Out of stock" value={number(overview.out_of_stock_products)} /><Summary label="Warehouse allocation groups" value={number(data.inventory?.warehouses?.total_warehouses)} /><Summary label="Turnover calculation" value={data.inventory?.turnover?.calculation || "Unavailable"} /></div><DataTable title="Low-stock products" headers={["Product", "Category", "Stock", "Reorder level", "Warehouse"]} rows={(data.inventory?.low_stock?.low_stock_products || []).map((item) => [item.product_name, item.category || "Uncategorized", item.current_stock, item.reorder_level, item.warehouse || "Unassigned"])} /><DataTable title="Warehouse allocation" headers={["Warehouse", "Products", "Stock units"]} rows={(data.inventory?.warehouses?.warehouses || []).map((item) => [item.warehouse, item.total_products, item.total_stock_units])} /></section>
      <section className="analytics-card bi-section"><h3>Customer intelligence</h3><div className="bi-summary-grid"><Summary label="Customers with completed purchases" value={number(customers.total_customers)} /><Summary label="Customer revenue" value={money(customers.total_customer_revenue)} /><Summary label="Completed customer transactions" value={number(customers.total_customer_orders)} /><Summary label="Average customer spend" value={money(customers.average_customer_spend)} /></div><p>{data.customers?.segmentation?.message || (segments.length ? `${data.customers.segmentation.algorithm || "Customer segmentation"} · ${segments.length} segments` : "Segmentation unavailable.")}</p><h4>Recommendation evaluation</h4>{recommendation.metrics ? <div className="bi-summary-grid"><Summary label="Precision@K" value={rate(recommendation.metrics.precision_at_k)} /><Summary label="Recall@K" value={rate(recommendation.metrics.recall_at_k)} /><Summary label="Hit rate@K" value={rate(recommendation.metrics.hit_rate_at_k)} /></div> : <p>{recommendation.message || "No tracked recommendation evaluation is available."}</p>}</section>
      <section className="analytics-card bi-section"><h3>MLflow and workflow activity</h3><p>MLflow: {data.mlflow?.status?.available ? "Available" : data.mlflow?.status?.message || "Unavailable"}</p><DataTable title="Latest MLflow runs" headers={["Experiment", "Run ID", "Started", "Status", "Metrics"]} rows={(data.mlflow?.latest_runs?.runs || []).map((run) => [run.experiment_name, run.run_id, run.start_time ? new Date(run.start_time).toLocaleString() : "Unavailable", run.evaluation_status || run.status, Object.entries(run.metrics || {}).map(([key, value]) => `${key}: ${value}`).join(", ") || "No metrics"])} /><p>Workflow jobs — successful: {number(workflowCounts.success)}, failed: {number(workflowCounts.failed)}, running: {number(workflowCounts.running)}. Scheduler: {data.workflow?.scheduler?.status || "Unavailable"}.</p><DataTable title="Recent workflow executions" headers={["Job", "Trigger", "Started", "Status", "Duration"]} rows={(data.workflow?.executions || []).slice(0, 10).map((item) => [item.job_name, item.trigger, item.started_at ? new Date(item.started_at).toLocaleString() : "Unavailable", item.status, item.duration_seconds == null ? "Running" : `${item.duration_seconds}s`])} /></section>
      <section className="analytics-card bi-section"><h3>Revenue growth and category performance</h3><div className="bi-summary-grid"><Summary label="Current month revenue" value={money(revenue.current_month_revenue)} /><Summary label="Previous month revenue" value={money(revenue.previous_month_revenue)} /><Summary label="Month-over-month growth" value={revenue.mom_revenue_growth_percentage == null ? "Unavailable" : `${Number(revenue.mom_revenue_growth_percentage).toFixed(2)}%`} /></div><DataTable title="Category performance" headers={["Category", "Revenue", "Units sold", "Completed transaction records", "Products"]} rows={(data.categories || []).map((item) => [item.category, money(item.revenue), number(item.units_sold), number(item.completed_transaction_records), number(item.product_count)])} /></section>
      <p className="bi-generated">Generated {data.generated_at ? new Date(data.generated_at).toLocaleString() : "timestamp unavailable"}</p>
    </div>
  );
}

function BiChart({ title, subtitle, empty, children }) {
  const hasChildren = Boolean(children);
  return <section className="analytics-card bi-chart"><h3>{title}</h3>{subtitle && <p className="analytics-subtitle">{subtitle}</p>}{hasChildren ? children : <p className="bi-empty">{empty}</p>}</section>;
}

function Summary({ label, value }) { return <div className="bi-summary"><span>{label}</span><strong>{value}</strong></div>; }

function DataTable({ title, headers, rows }) {
  return <div className="bi-table-block"><h4>{title}</h4><div className="analytics-table-wrapper"><table className="analytics-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.length ? rows.map((row, index) => <tr key={`${title}-${index}`}>{row.map((value, column) => <td key={`${index}-${column}`}>{value ?? "Unavailable"}</td>)}</tr>) : <tr><td colSpan={headers.length}>No data available.</td></tr>}</tbody></table></div></div>;
}
