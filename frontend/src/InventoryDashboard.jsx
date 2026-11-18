
import { useEffect, useRef, useState } from "react";
import {
  Package,
  AlertTriangle,
  Warehouse,
  IndianRupee,
  RefreshCw,
  TrendingUp,
  Boxes,
} from "lucide-react";

import api from "./services/api";

function StatCard({ title, value, icon: Icon, description }) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span>{title}</span>
        <div className="stat-icon">
          <Icon size={20} />
        </div>
      </div>
      <h2>{value}</h2>
      <div className="stat-change">{description}</div>
    </div>
  );
}

function InventoryDashboard() {
  const warehouseRequestId = useRef(0);
  const categoryRequestId = useRef(0);
  const [overview, setOverview] = useState(null);
  const [forecasts, setForecasts] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [turnover, setTurnover] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedWarehouse, setSelectedWarehouse] = useState("");
  const [warehouseProducts, setWarehouseProducts] = useState([]);
  const [warehouseLoading, setWarehouseLoading] = useState(false);
  const [warehouseError, setWarehouseError] = useState("");
  const [assignmentProduct, setAssignmentProduct] = useState("");
  const [assignmentWarehouse, setAssignmentWarehouse] = useState("");
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [assignmentFeedback, setAssignmentFeedback] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [categoryProducts, setCategoryProducts] = useState([]);
  const [categoryLoading, setCategoryLoading] = useState(false);
  const [categoryError, setCategoryError] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadInventoryData() {
    setLoading(true);
    setError("");

    try {
      const results = await Promise.all([
        api.get("/inventory-analytics/overview"),
        api.get("/inventory-analytics/low-stock"),
        api.get("/inventory-forecast/demand"),
        api.get("/stock-alerts/"),
        api.get("/inventory-turnover/"),
        api.get("/warehouse/"),
        api.get("/categories/"),
      ]);

      setOverview(results[0].data);
      setForecasts(results[2].data.forecasts || []);
      setAlerts(results[3].data.alerts || []);
      setTurnover(results[4].data.products || []);
      setWarehouses(results[5].data.warehouses || []);
      setCategories(results[6].data.categories || []);
    } catch (err) {
      console.error("Inventory dashboard error:", err);

      setError(
        err.response?.data?.detail ||
          "Could not load inventory dashboard. Check the backend."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    Promise.resolve().then(loadInventoryData);
  }, []);

  async function loadWarehouseProducts(warehouseName, inventoryProducts = overview?.products || []) {
    const requestId = ++warehouseRequestId.current;
    setSelectedWarehouse(warehouseName);
    setWarehouseError("");

    if (!warehouseName) {
      setWarehouseProducts([]);
      setWarehouseLoading(false);
      return;
    }

    if (warehouseName === "Unassigned") {
      setWarehouseProducts(
        inventoryProducts.filter((product) => !product.warehouse)
      );
      setWarehouseLoading(false);
      return;
    }

    setWarehouseLoading(true);
    try {
      const response = await api.get(
        `/warehouse/${encodeURIComponent(warehouseName)}/products`
      );
      const inventoryByProduct = new Map(
        inventoryProducts.map((product) => [product.product_id, product])
      );
      if (requestId === warehouseRequestId.current) {
        setWarehouseProducts(
          (response.data.products || []).map((product) => ({
          ...inventoryByProduct.get(product.product_id),
          ...product,
          }))
        );
      }
    } catch (err) {
      if (requestId === warehouseRequestId.current) {
        setWarehouseError(
          err.response?.data?.detail || "Could not load warehouse products."
        );
        setWarehouseProducts([]);
      }
    } finally {
      if (requestId === warehouseRequestId.current) {
        setWarehouseLoading(false);
      }
    }
  }

  async function handleWarehouseAssignment(event) {
    event.preventDefault();
    setAssignmentFeedback(null);

    const productId = Number(assignmentProduct);
    const warehouseName = assignmentWarehouse.trim();
    const productExists = overview?.products?.some(
      (product) => product.product_id === productId
    );

    if (!productId || !productExists) {
      setAssignmentFeedback({ type: "error", message: "Select a product with an inventory record." });
      return;
    }

    if (!warehouseName || warehouseName.length > 100 || warehouseName === "Unassigned") {
      setAssignmentFeedback({
        type: "error",
        message: "Enter a warehouse name between 1 and 100 characters. ‘Unassigned’ is a display label, not a warehouse name.",
      });
      return;
    }

    setAssignmentLoading(true);
    try {
      const response = await api.patch(
        `/warehouse/${productId}/assign`,
        null,
        { params: { warehouse_name: warehouseName } }
      );

      if (response.data.error) {
        throw new Error(response.data.error);
      }

      const [warehouseResponse, overviewResponse] = await Promise.all([
        api.get("/warehouse/"),
        api.get("/inventory-analytics/overview"),
      ]);
      const refreshedOverview = overviewResponse.data;
      setWarehouses(warehouseResponse.data.warehouses || []);
      setOverview(refreshedOverview);
      setAssignmentFeedback({
        type: "success",
        message: response.data.message || "Product assigned successfully.",
      });

      await loadWarehouseProducts(warehouseName, refreshedOverview.products || []);
      setAssignmentWarehouse(warehouseName);
    } catch (err) {
      setAssignmentFeedback({
        type: "error",
        message:
          err.response?.data?.detail || err.message || "Could not assign product to warehouse.",
      });
    } finally {
      setAssignmentLoading(false);
    }
  }

  async function handleCategoryChange(event) {
    const categoryName = event.target.value;
    const requestId = ++categoryRequestId.current;
    setSelectedCategory(categoryName);
    setCategoryError("");
    setCategoryProducts([]);

    if (!categoryName) {
      setCategoryLoading(false);
      return;
    }

    setCategoryLoading(true);
    try {
      let products;
      if (categoryName === "Uncategorized") {
        const response = await api.get("/products/");
        products = (Array.isArray(response.data) ? response.data : []).filter(
          (product) => !product.category
        );
      } else {
        const response = await api.get(
          `/categories/${encodeURIComponent(categoryName)}/products`
        );
        products = response.data.products || [];
      }

      const inventoryByProduct = new Map(
        (overview?.products || []).map((product) => [product.product_id, product])
      );
      if (requestId === categoryRequestId.current) {
        setCategoryProducts(
          products.map((product) => ({
          ...inventoryByProduct.get(product.product_id),
          ...product,
          category: product.category || categoryName,
          }))
        );
      }
    } catch (err) {
      if (requestId === categoryRequestId.current) {
        setCategoryError(
          err.response?.data?.detail || "Could not load products for this category."
        );
      }
    } finally {
      if (requestId === categoryRequestId.current) {
        setCategoryLoading(false);
      }
    }
  }

  function currency(value) {
    return `₹${Number(value || 0).toLocaleString("en-IN", {
      maximumFractionDigits: 2,
    })}`;
  }

  if (loading) {
    return (
      <div className="activity-card">
        <RefreshCw size={22} />
        <p>Loading inventory analytics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="activity-card">
        <h3>Inventory Dashboard Error</h3>
        <p>{error}</p>
        <button className="primary-button" onClick={loadInventoryData}>
          Try Again
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="section-heading">
        <div>
          <h2>Inventory Analytics</h2>
          <p>Monitor stock, demand, warehouses and replenishment.</p>
        </div>

        <button
          className="secondary-button"
          onClick={loadInventoryData}
          disabled={loading}
        >
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="stats-grid">
        <StatCard
          title="Products Tracked"
          value={overview?.total_products_tracked ?? 0}
          icon={Package}
          description="Products with inventory records"
        />

        <StatCard
          title="Total Stock Units"
          value={overview?.total_stock_units ?? 0}
          icon={Boxes}
          description="Available inventory units"
        />

        <StatCard
          title="Inventory Value"
          value={currency(overview?.total_inventory_value)}
          icon={IndianRupee}
          description="Current stock × product price"
        />

        <StatCard
          title="Low Stock Products"
          value={overview?.low_stock_products ?? 0}
          icon={AlertTriangle}
          description={`${overview?.out_of_stock_products ?? 0} out of stock`}
        />
      </div>

      <div className="activity-card">
        <h3>Product Stock Overview</h3>

        {overview?.products?.length ? (
          <div className="products-list">
            {overview.products.map((product) => (
              <div className="product-row" key={product.product_id}>
                <div style={{ flex: "1 1 180px" }}>
                  <strong>{product.product_name}</strong>
                  <p>{product.category || "Uncategorized"}</p>
                  <p>Warehouse: {product.warehouse || "Unassigned"}</p>
                </div>

                <div>
                  <strong>{product.current_stock} units</strong>
                  <p>Reorder level: {product.reorder_level}</p>
                </div>

                <div>
                  <strong>{currency(product.inventory_value)}</strong>
                  <p
                    style={{
                      color:
                        product.stock_status === "In Stock"
                          ? "green"
                          : "#d97706",
                    }}
                  >
                    {product.stock_status}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p>No inventory records found.</p>
        )}
      </div>

      <div className="activity-card">
        <h3>
          <AlertTriangle size={19} /> Low Stock Alerts
        </h3>

        {alerts.length ? (
          <div className="products-list">
            {alerts.map((alert) => (
              <div className="product-row" key={alert.product_id}>
                <div style={{ flex: 1 }}>
                  <strong>{alert.product_name}</strong>
                  <p>Current stock: {alert.current_stock}</p>
                  <p>Reorder level: {alert.reorder_level}</p>
                </div>

                <div>
                  <strong>{alert.priority}</strong>
                  <p>
                    Suggested replenishment:{" "}
                    {alert.recommended_replenishment} units
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p>No low-stock alerts currently.</p>
        )}
      </div>

      <div className="activity-card">
        <h3>
          <TrendingUp size={19} /> Seven-Day Demand Forecast
        </h3>

        <p>
          Method: Historical Average Demand. Estimates are based on recorded
          completed sales.
        </p>

        {forecasts.length ? (
          <div className="products-list">
            {forecasts.map((item) => (
              <div className="product-row" key={item.product_id}>
                <div style={{ flex: 1 }}>
                  <strong>{item.product_name}</strong>
                  <p>{item.message}</p>
                </div>
                <strong>{item.forecast_next_7_days} units</strong>
              </div>
            ))}
          </div>
        ) : (
          <p>No forecast data available.</p>
        )}
      </div>

      <div className="activity-card">
        <h3>Inventory Turnover</h3>
        <p>
          Sales-to-current-stock ratio (a proxy, not standard accounting
          inventory turnover).
        </p>

        {turnover.length ? (
          <div className="products-list">
            {turnover.map((item) => (
              <div className="product-row" key={item.product_id}>
                <div style={{ flex: 1 }}>
                  <strong>{item.product_name}</strong>
                  <p>Total units sold: {item.total_units_sold}</p>
                  <p>Current stock: {item.current_stock}</p>
                </div>
                <strong>
                  {item.sales_to_current_stock_ratio ?? "N/A"}
                </strong>
              </div>
            ))}
          </div>
        ) : (
          <p>No turnover data available.</p>
        )}
      </div>

      <div className="inventory-management-grid">
        <section className="activity-card inventory-management-card">
          <h3><Warehouse size={19} /> Warehouse Assignment</h3>
          <p>
            Each product has one warehouse value on its inventory record. Assigning
            it elsewhere replaces that value; this does not track multiple physical
            stock locations.
          </p>

          <h4>Available warehouse names</h4>
          {warehouses.length ? (
            <div className="inventory-chip-list">
              {warehouses.map((item) => (
                <button
                  type="button"
                  className="inventory-chip"
                  key={item.warehouse}
                  onClick={() => loadWarehouseProducts(item.warehouse)}
                  title="View products in this warehouse"
                >
                  {item.warehouse} · {item.total_products} products · {item.total_stock_units} units
                </button>
              ))}
            </div>
          ) : <p>No warehouse names are currently recorded.</p>}

          <div className="inventory-control">
            <label htmlFor="warehouse-view">View products in warehouse</label>
            <select
              id="warehouse-view"
              value={selectedWarehouse}
              onChange={(event) => loadWarehouseProducts(event.target.value)}
            >
              <option value="">Select a warehouse</option>
              {warehouses.map((item) => (
                <option key={item.warehouse} value={item.warehouse}>{item.warehouse}</option>
              ))}
            </select>
          </div>

          {warehouseLoading && <p role="status">Loading warehouse products...</p>}
          {warehouseError && <p className="inventory-feedback error" role="alert">{warehouseError}</p>}
          {!warehouseLoading && !warehouseError && selectedWarehouse && (
            warehouseProducts.length ? (
              <div className="products-list">
                {warehouseProducts.map((product) => (
                  <div className="product-row" key={product.product_id}>
                    <div>
                      <strong>{product.product_name}</strong>
                      <p>{product.category || "Uncategorized"} · Stock: {product.current_stock} · Reorder level: {product.reorder_level}</p>
                    </div>
                    {product.price != null && <strong>{currency(product.price)}</strong>}
                  </div>
                ))}
              </div>
            ) : <p>No products are assigned to {selectedWarehouse}.</p>
          )}

          <form className="inventory-assignment-form" onSubmit={handleWarehouseAssignment}>
            <h4>Assign or reassign a product</h4>
            <div className="inventory-control">
              <label htmlFor="assignment-product">Product</label>
              <select
                id="assignment-product"
                value={assignmentProduct}
                onChange={(event) => setAssignmentProduct(event.target.value)}
                required
              >
                <option value="">Select an inventory product</option>
                {(overview?.products || []).map((product) => (
                  <option key={product.product_id} value={product.product_id}>
                    {product.product_name} (#{product.product_id}) · {product.warehouse || "Unassigned"}
                  </option>
                ))}
              </select>
            </div>
            <div className="inventory-control">
              <label htmlFor="assignment-warehouse">Warehouse name</label>
              <input
                id="assignment-warehouse"
                list="warehouse-name-options"
                value={assignmentWarehouse}
                onChange={(event) => setAssignmentWarehouse(event.target.value)}
                maxLength={100}
                placeholder="Choose or enter a warehouse name"
                required
              />
              <datalist id="warehouse-name-options">
                {warehouses.filter((item) => item.warehouse !== "Unassigned").map((item) => (
                  <option key={item.warehouse} value={item.warehouse} />
                ))}
              </datalist>
            </div>
            <button className="primary-button" type="submit" disabled={assignmentLoading || !overview?.products?.length}>
              {assignmentLoading ? "Assigning..." : "Save warehouse assignment"}
            </button>
            {assignmentFeedback && (
              <p className={`inventory-feedback ${assignmentFeedback.type}`} role={assignmentFeedback.type === "error" ? "alert" : "status"}>
                {assignmentFeedback.message}
              </p>
            )}
          </form>
        </section>

        <section className="activity-card inventory-management-card">
          <h3>Category Product Filter</h3>
          <p>Select a category to view its products and inventory details.</p>
          <div className="inventory-control">
            <label htmlFor="category-filter">Product category</label>
            <select id="category-filter" value={selectedCategory} onChange={handleCategoryChange}>
              <option value="">All Categories</option>
              {categories.map((item) => (
                <option key={item.category} value={item.category}>
                  {item.category} ({item.total_products})
                </option>
              ))}
            </select>
          </div>

          {categoryLoading && <p role="status">Loading category products...</p>}
          {categoryError && <p className="inventory-feedback error" role="alert">{categoryError}</p>}
          {!categoryLoading && !categoryError && (() => {
            const products = selectedCategory ? categoryProducts : (overview?.products || []);
            return products.length ? (
              <div className="products-list">
                {products.map((product) => (
                  <div className="product-row" key={product.product_id}>
                    <div>
                      <strong>{product.product_name}</strong>
                      <p>{product.category || "Uncategorized"} · Stock: {product.current_stock ?? "Not tracked"}</p>
                    </div>
                    {product.price != null && <strong>{currency(product.price)}</strong>}
                  </div>
                ))}
              </div>
            ) : <p>{selectedCategory ? `No products found in ${selectedCategory}.` : "No inventory products found."}</p>;
          })()}
        </section>
      </div>
    </div>
  );
}

export default InventoryDashboard;
