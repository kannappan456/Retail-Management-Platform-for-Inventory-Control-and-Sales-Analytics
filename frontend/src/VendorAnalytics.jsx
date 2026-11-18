import { useCallback, useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import api from "./services/api";

function VendorAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overview, monthly, categories, products] = await Promise.all([
        api.get("/analytics/vendor/revenue/overview"),
        api.get("/analytics/vendor/revenue/monthly?months=12"),
        api.get("/analytics/vendor/revenue/categories"),
        api.get("/analytics/vendor/revenue/products"),
      ]);
      setData({ overview: overview.data, months: monthly.data.months || [], categories: categories.data.categories || [], products: products.data.products || [] });
    } catch (err) {
      setError(err.response?.data?.detail || "Unable to load your sales analytics.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { Promise.resolve().then(load); }, [load]);
  const money = (value) => value == null ? "—" : `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  const count = (value) => value == null ? "—" : Number(value).toLocaleString("en-IN");

  if (loading) return <div className="analytics-page"><div className="analytics-message" role="status">Loading your sales analytics…</div></div>;
  if (error) return <div className="analytics-page"><section className="analytics-card" role="alert"><h2>Vendor Analytics</h2><p>{error}</p><button className="secondary-button" onClick={load}>Retry</button></section></div>;
  if (!data) return null;

  const { overview } = data;
  const kpis = [
    ["Completed revenue", money(overview.completed_revenue)],
    ["GMV", money(overview.gmv)],
    ["Completed transaction records", count(overview.completed_transaction_records)],
    ["Units sold", count(overview.total_units_sold)],
    ["MoM revenue growth", overview.mom_revenue_growth_percentage == null ? "—" : `${Number(overview.mom_revenue_growth_percentage).toFixed(2)}%`],
    ["Average transaction value (proxy)", money(overview.average_transaction_value)],
  ];

  return (
    <div className="analytics-page">
      <div className="analytics-heading"><div><h2>Vendor Analytics</h2><p>Revenue and product performance for your vendor account.</p></div><button className="secondary-button" onClick={load}>Refresh</button></div>
      <div className="revenue-kpis">{kpis.map(([label, value]) => <article className="revenue-kpi" key={label}><span>{label}</span><strong>{value}</strong></article>)}</div>
      <p className="revenue-note">{overview.definition} {overview.aov_note} Your data is scoped to your vendor account.</p>
      <div className="revenue-grid">
        <section className="analytics-card"><h3>Monthly revenue</h3>{data.months.length ? <ResponsiveContainer width="100%" height={280}><LineChart data={data.months}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="month" /><YAxis /><Tooltip formatter={(value) => money(value)} /><Line type="monotone" dataKey="revenue" stroke="#2563eb" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer> : <p>No monthly revenue records.</p>}</section>
        <section className="analytics-card"><h3>Revenue by category</h3>{data.categories.length ? <ResponsiveContainer width="100%" height={280}><BarChart data={data.categories}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="category" /><YAxis /><Tooltip formatter={(value) => money(value)} /><Bar dataKey="revenue" fill="#0d9488" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer> : <p>No category revenue records.</p>}</section>
      </div>
      <section className="analytics-card analytics-table-card"><h3>Your product performance</h3><div className="analytics-table-wrapper"><table className="analytics-table"><thead><tr><th>Product</th><th>Category</th><th>Units sold</th><th>Completed transaction records</th><th>Revenue</th></tr></thead><tbody>{data.products.length ? data.products.map((product) => <tr key={product.product_id}><td>{product.product_name}</td><td>{product.category || "Uncategorized"}</td><td>{count(product.units_sold)}</td><td>{count(product.completed_transaction_records)}</td><td>{money(product.revenue)}</td></tr>) : <tr><td colSpan="5">No products available.</td></tr>}</tbody></table></div></section>
    </div>
  );
}

export default VendorAnalytics;
