import { useState, useEffect, useCallback } from "react";
import {
  Store,
  ShoppingBag,
  LayoutDashboard,
  Package,
  Users,
  BarChart3,
  Sparkles,
  Settings,
  Search,
  Bell,
  IndianRupee,
  ShoppingCart,
  Menu,
  Plus,
  Minus,
  Trash2,
  CheckCircle,
  Clock,
  ShieldCheck,
  RefreshCw,
  Activity,
  LogOut,
} from "lucide-react";
import Analytics from "./Analytics";
import MlflowDashboard from "./MlflowDashboard";
import WorkflowDashboard from "./WorkflowDashboard";
import BiDashboard from "./BiDashboard";
import CustomerOrders from "./CustomerOrders";
import CustomerProfile from "./CustomerProfile";
import VendorAnalytics from "./VendorAnalytics";
import VendorOrders from "./VendorOrders";
import api from "./services/api";
import InventoryDashboard from "./InventoryDashboard";
import CustomerAnalytics from "./CustomerAnalytics";
import RecommendationDashboard from "./RecommendationDashboard";
import Auth from "./Auth";
import "./App.css";

function App() {
  const [user, setUser] = useState(() => {
    const savedUser = localStorage.getItem("shopsense_user");
    const savedToken = localStorage.getItem("shopsense_token");

    if (!savedToken) {
      localStorage.removeItem("shopsense_user");
      return null;
    }

    try {
      return savedUser ? JSON.parse(savedUser) : null;
    } catch {
      localStorage.removeItem("shopsense_user");
      localStorage.removeItem("shopsense_token");
      return null;
    }
  });

  const [activeTab, setActiveTab] = useState(() => {
    const savedUser = localStorage.getItem("shopsense_user");

    try {
      const parsedUser = savedUser ? JSON.parse(savedUser) : null;
      return parsedUser?.role === "Customer"
        ? "Marketplace"
        : "Overview";
    } catch {
      return "Overview";
    }
  });

  const role = user?.role || "Customer";

  useEffect(() => {
    const enforceAuthentication = () => {
      if (!localStorage.getItem("shopsense_token") || !localStorage.getItem("shopsense_user")) {
        setUser(null);
      }
    };

    window.addEventListener("pageshow", enforceAuthentication);
    return () => window.removeEventListener("pageshow", enforceAuthentication);
  }, []);

  const [products, setProducts] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [cart, setCart] = useState([]);
  const [cartStock, setCartStock] = useState({});
  const [isCartStockLoading, setIsCartStockLoading] = useState(false);
  const [validatedCartKey, setValidatedCartKey] = useState("");
  const [wishlist, setWishlist] = useState([]);
  const cartProductIdsKey = [...new Set(
    cart.map((item) => Number(item.product_id ?? item.id)).filter(Boolean)
  )].sort((left, right) => left - right).join(",");

  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [checkoutError, setCheckoutError] = useState("");
  const [orderConfirmation, setOrderConfirmation] = useState(null);

  const [apiStatus, setApiStatus] = useState("Connecting to backend...");
  const [savingProduct, setSavingProduct] = useState(false);
  const [productError, setProductError] = useState("");

  const [adminSummary, setAdminSummary] = useState(null);
  const [adminError, setAdminError] = useState("");
  const [loadingAdmin, setLoadingAdmin] = useState(false);
  const [loadedAdminTab, setLoadedAdminTab] = useState(null);
  const [approvingVendor, setApprovingVendor] = useState(null);

  const [productForm, setProductForm] = useState({
    product_name: "",
    category: "",
    price: "",
    opening_stock: "0",
    reorder_level: "10",
  });

  // Fetch product data without updating component state.
  const fetchProducts = useCallback(async () => {
    const response = role === "Vendor" && user?.vendor_id
      ? await api.get("/products/", {
        params: { vendor_id: user.vendor_id },
      })
      : await api.get("/products/");

    return Array.isArray(response.data)
      ? response.data
      : response.data.products || [];
  }, [role, user]);

  // Load products from user actions such as checkout and product creation.
  const loadProducts = useCallback(async () => {
    try {
      setProducts(await fetchProducts());
      setApiStatus("Backend connected successfully");
    } catch (error) {
      console.error("Could not load products:", error);
      setApiStatus("Backend connection failed");
    }
  }, [fetchProducts]);

  const requestCartStock = useCallback(async (productIds) => {
    return Promise.all(productIds.map(async (productId) => {
      try {
        const response = await api.get(`/inventory/${productId}/availability`);
        return {
          productId,
          currentStock: Number(response.data.current_stock),
          availableForPurchase: Boolean(response.data.available_for_purchase),
          error: "",
        };
      } catch (error) {
        return {
          productId,
          currentStock: null,
          availableForPurchase: false,
          error: error.response?.data?.detail ||
            "Stock could not be verified. Retry before checkout.",
        };
      }
    }));
  }, []);

  useEffect(() => {
    if (role !== "Customer" || activeTab !== "Cart" || !cartProductIdsKey) {
      return undefined;
    }

    let cancelled = false;
    const productIds = cartProductIdsKey.split(",").map(Number);

    Promise.resolve().then(async () => {
      setIsCartStockLoading(true);
      const stockResults = await requestCartStock(productIds);
      if (cancelled) return;

      setCartStock((current) => ({
        ...current,
        ...Object.fromEntries(stockResults.map((item) => [item.productId, item])),
      }));
      setValidatedCartKey(cartProductIdsKey);
      setIsCartStockLoading(false);
    }).catch((error) => {
      if (cancelled) return;
      console.error("Cart stock validation failed:", error);
      setIsCartStockLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [activeTab, cartProductIdsKey, requestCartStock, role]);

  useEffect(() => {
    if (!user) return undefined;

    let cancelled = false;
    async function loadInitialProducts() {
      try {
        const data = await fetchProducts();
        if (cancelled) return;
        setProducts(data);
        setApiStatus("Backend connected successfully");
      } catch (error) {
        if (cancelled) return;
        console.error("Could not load products:", error);
        setApiStatus("Backend connection failed");
      }
    }

    void loadInitialProducts();
    return () => {
      cancelled = true;
    };
  }, [user, fetchProducts]);

  // Fetch Admin data without coupling the request to React state updates.
  const requestAdminData = useCallback(async (tab) => {
    if (role !== "Admin") return null;

    if (tab === "Overview") {
      const response = await api.get("/analytics/summary");
      return { tab, data: response.data };
    }

    if (tab === "Vendors") {
      const response = await api.get("/vendors/");
      return {
        tab,
        data: Array.isArray(response.data) ? response.data : [],
      };
    }

    if (tab === "Products") {
      const response = await api.get("/products/");
      return {
        tab,
        data: Array.isArray(response.data)
          ? response.data
          : response.data.products || [],
      };
    }

    return { tab };
  }, [role]);

  const applyAdminData = useCallback((result) => {
    if (!result) return;
    if (result.tab === "Overview") setAdminSummary(result.data);
    if (result.tab === "Vendors") setVendors(result.data);
    if (result.tab === "Products") setProducts(result.data);
    setAdminError("");
  }, []);

  const setAdminLoadError = useCallback((error) => {
    console.error("Admin dashboard error:", error);
    setAdminError(
      error.response?.data?.detail ||
        "Could not load dashboard data. Check your login and backend."
    );
  }, []);

  // User-triggered reloads retain the existing refresh indicator.
  const loadAdminData = useCallback(async (tab) => {
    setAdminError("");
    setLoadingAdmin(true);
    try {
      applyAdminData(await requestAdminData(tab));
    } catch (error) {
      setAdminLoadError(error);
    } finally {
      setLoadingAdmin(false);
      setLoadedAdminTab(tab);
    }
  }, [applyAdminData, requestAdminData, setAdminLoadError]);

  function navigateToTab(tab) {
    if (tab === "Cart") setValidatedCartKey("");
    if (
      role === "Admin" &&
      tab !== activeTab &&
      ["Overview", "Vendors", "Products"].includes(tab)
    ) {
      setAdminError("");
      setLoadingAdmin(true);
    }
    setActiveTab(tab);
  }

  useEffect(() => {
    if (
      user &&
      role === "Admin" &&
      ["Overview", "Vendors", "Products"].includes(activeTab)
    ) {
      let cancelled = false;
      async function loadInitialAdminData() {
        try {
          const result = await requestAdminData(activeTab);
          if (cancelled) return;
          applyAdminData(result);
        } catch (error) {
          if (cancelled) return;
          setAdminLoadError(error);
        } finally {
          if (!cancelled) {
            setLoadingAdmin(false);
            setLoadedAdminTab(activeTab);
          }
        }
      }

      void loadInitialAdminData();
      return () => {
        cancelled = true;
      };
    }
    return undefined;
  }, [activeTab, applyAdminData, requestAdminData, role, setAdminLoadError, user]);

  const isAdminLoading = loadingAdmin || (
    role === "Admin" &&
    ["Overview", "Vendors", "Products"].includes(activeTab) &&
    loadedAdminTab !== activeTab
  );

  // Approve a pending vendor.
  async function handleApproveVendor(vendorId) {
    setAdminError("");
    setApprovingVendor(vendorId);

    try {
      await api.patch(`/vendors/${vendorId}/activate`);

      await loadAdminData("Vendors");

      alert("Vendor approved successfully!");
    } catch (error) {
      console.error("Vendor approval failed:", error);

      setAdminError(
        error.response?.data?.detail ||
          "Could not approve the vendor."
      );
    } finally {
      setApprovingVendor(null);
    }
  }

  function updateProductForm(event) {
    const { name, value } = event.target;

    setProductForm((current) => ({
      ...current,
      [name]: value,
    }));
  }

  // Customer wishlist.
  function toggleWishlist(product) {
    const productId = product.product_id ?? product.id;

    setWishlist((current) => {
      const exists = current.some(
        (item) => (item.product_id ?? item.id) === productId
      );

      if (exists) {
        return current.filter(
          (item) => (item.product_id ?? item.id) !== productId
        );
      }

      return [...current, product];
    });
  }

  // Add a product to the shopping cart.
  async function handleAddToCart(product) {
    const productId = Number(product.product_id ?? product.id);
    const [stock] = await requestCartStock([productId]);
    setCartStock((current) => ({ ...current, [productId]: stock }));

    if (stock.error) {
      alert(stock.error);
      return;
    }
    if (!stock.availableForPurchase || stock.currentStock < 1) {
      alert(stock.currentStock === 0
        ? "This product is out of stock."
        : "This product is currently unavailable for purchase.");
      return;
    }

    const currentQuantity = cart.find(
      (item) => Number(item.product_id ?? item.id) === productId
    )?.quantity || 0;
    if (Number(currentQuantity) + 1 > stock.currentStock) {
      alert(`Only ${stock.currentStock} available for this product.`);
      return;
    }

    setCart((currentCart) => {
      const existingProduct = currentCart.find(
        (item) => Number(item.product_id ?? item.id) === productId
      );

      if (existingProduct) {
        return currentCart.map((item) =>
          Number(item.product_id ?? item.id) === productId
            ? { ...item, quantity: item.quantity + 1 }
            : item
        );
      }

      return [...currentCart, { ...product, quantity: 1 }];
    });

    alert(
      `${product.product_name || product.name || "Product"} added to cart!`
    );
  }

  async function handleRefreshCartStock() {
    if (!cartProductIdsKey) return;
    setIsCartStockLoading(true);
    setValidatedCartKey("");
    const productIds = cartProductIdsKey.split(",").map(Number);
    const stockResults = await requestCartStock(productIds);
    setCartStock((current) => ({
      ...current,
      ...Object.fromEntries(stockResults.map((item) => [item.productId, item])),
    }));
    setValidatedCartKey(cartProductIdsKey);
    setIsCartStockLoading(false);
  }

  // Checkout using the existing backend endpoint.
  async function handleCheckout() {
    if (cart.length === 0) {
      setCheckoutError("Your cart is empty.");
      return;
    }

    setIsCheckingOut(true);
    setCheckoutError("");
    setOrderConfirmation(null);

    try {
      setIsCartStockLoading(true);
      const productIds = cart.map((item) =>
        Number(item.product_id ?? item.id)
      );
      const stockResults = await requestCartStock(productIds);
      const stockById = Object.fromEntries(
        stockResults.map((item) => [item.productId, item])
      );
      setCartStock((current) => ({ ...current, ...stockById }));

      const invalidItems = cart.flatMap((item) => {
        const productId = Number(item.product_id ?? item.id);
        const productName = item.product_name || item.name || "Product";
        const stock = stockById[productId];

        if (!stock || stock.error) {
          return [`${productName}: ${stock?.error || "stock could not be verified."}`];
        }
        if (stock.currentStock === 0) return [`${productName} is out of stock.`];
        if (!stock.availableForPurchase) {
          return [`${productName} is currently unavailable for purchase.`];
        }
        if (Number(item.quantity) > stock.currentStock) {
          return [`${productName}: only ${stock.currentStock} available; requested ${item.quantity}.`];
        }
        return [];
      });
      setValidatedCartKey(cartProductIdsKey);

      if (invalidItems.length > 0) {
        setCheckoutError(invalidItems.join(" "));
        return;
      }

      const items = cart.map((item) => ({
        product_id: Number(item.product_id ?? item.id),
        vendor_id: Number(item.vendor_id),
        quantity: Number(item.quantity),
      }));

      if (
        items.some(
          (item) =>
            !item.product_id ||
            !item.vendor_id ||
            !item.quantity
        )
      ) {
        throw new Error(
          "A cart product is missing its product or vendor ID. Refresh the marketplace and try again."
        );
      }

      const response = await api.post("/transactions/checkout", {
        items,
      });

      setOrderConfirmation(response.data);
      setCart([]);
      setCartStock({});
      setValidatedCartKey("");

      await loadProducts();

      setActiveTab("My Orders");
    } catch (error) {
      console.error("Checkout failed:", error);

      const detail = error.response?.data?.detail;

      setCheckoutError(
        typeof detail === "string"
          ? detail
          : error.message ||
              "Checkout failed. Check stock and try again."
      );
      setIsCartStockLoading(true);
      setValidatedCartKey("");
      const refreshedStock = await requestCartStock(
        cart.map((item) => Number(item.product_id ?? item.id))
      );
      setCartStock((current) => ({
        ...current,
        ...Object.fromEntries(refreshedStock.map((item) => [item.productId, item])),
      }));
      setValidatedCartKey(cartProductIdsKey);
    } finally {
      setIsCartStockLoading(false);
      setIsCheckingOut(false);
    }
  }

  // Vendor product creation.
  async function handleAddProduct(event) {
    event.preventDefault();
    setProductError("");

    if (!user?.vendor_id) {
      setProductError(
        "This login does not have a vendor ID linked to it. Please use the correct vendor account."
      );
      return;
    }

    setSavingProduct(true);

    try {
      const response = await api.post("/products/", {
        vendor_id: Number(user.vendor_id),
        product_name: productForm.product_name.trim(),
        category: productForm.category || null,
        price: productForm.price,
      });

      const createdProduct = response.data;
      const productId = createdProduct.product_id;
      const stockQuantity = Number(productForm.opening_stock);

      let stockWarning = "";

      if (stockQuantity > 0) {
        try {
          await api.post(`/inventory/${productId}/stock`, {
            quantity: stockQuantity,
          });
        } catch (stockError) {
          console.error("Opening stock update failed:", stockError);

          stockWarning =
            " Product created, but opening stock could not be saved.";
        }
      }

      await loadProducts();

      setProductForm({
        product_name: "",
        category: "",
        price: "",
        opening_stock: "0",
        reorder_level: "10",
      });

      alert(`Product saved successfully!${stockWarning}`);

      setActiveTab("My Products");
    } catch (error) {
      console.error("Could not save product:", error);

      const detail = error.response?.data?.detail;

      setProductError(
        typeof detail === "string"
          ? detail
          : "Could not save the product. Check your vendor account."
      );
    } finally {
      setSavingProduct(false);
    }
  }

  function handleLogin(data) {
    localStorage.setItem("shopsense_token", data.access_token);
    localStorage.setItem("shopsense_user", JSON.stringify(data.user));

    setUser(data.user);
    setLoadedAdminTab(null);
    setLoadingAdmin(data.user.role === "Admin");
    setAdminError("");

    setActiveTab(
      data.user.role === "Customer" ? "Marketplace" : "Overview"
    );
  }

  function handleLogout() {
    localStorage.removeItem("shopsense_token");
    localStorage.removeItem("shopsense_user");
    sessionStorage.removeItem("shopsense_token");
    sessionStorage.removeItem("shopsense_user");

    setUser(null);
    setProducts([]);
    setVendors([]);
    setCart([]);
    setCartStock({});
    setValidatedCartKey("");
    setWishlist([]);
    setAdminSummary(null);
    setLoadedAdminTab(null);
    setLoadingAdmin(false);
    setAdminError("");
    setOrderConfirmation(null);
    setActiveTab("Overview");
  }

  const navigation = {
    Vendor: [
      { name: "Overview", icon: LayoutDashboard },
      { name: "My Products", icon: Package },
      { name: "Add Product", icon: ShoppingBag },
      { name: "Orders", icon: ShoppingCart },
      { name: "Analytics", icon: BarChart3 },
      { name: "Settings", icon: Settings },
    ],

    Customer: [
      { name: "Marketplace", icon: Store },
      { name: "Cart", icon: ShoppingCart },
      { name: "My Orders", icon: ShoppingBag },
      { name: "Wishlist", icon: Package },
      { name: "My Profile", icon: Users },
      { name: "Recommendations", icon: Sparkles },
      { name: "Settings", icon: Settings },
    ],

    Admin: [
      { name: "Overview", icon: LayoutDashboard },
      { name: "Vendors", icon: Users },
      { name: "Products", icon: Package },
      { name: "Analytics", icon: BarChart3 },
      { name: "BI Dashboard", icon: BarChart3 },
      { name: "Inventory", icon: Package },
      { name: "Customer Analytics", icon: Users },
      { name: "MLflow Tracking", icon: Activity },
      { name: "Workflows", icon: Clock },
      { name: "Settings", icon: Settings },
    ],
  };

  if (!user) {
    return <Auth onLogin={handleLogin} />;
  }

  const cartQuantity = cart.reduce(
    (total, item) => total + item.quantity,
    0
  );

  const cartTotal = cart.reduce(
    (total, item) =>
      total +
      Number(item.price ?? item.unit_price ?? 0) * item.quantity,
    0
  );
  const cartStockValidationPending = isCartStockLoading ||
    !cartProductIdsKey || validatedCartKey !== cartProductIdsKey;
  const cartHasInvalidStock = cart.some((item) => {
    const stock = cartStock[item.product_id ?? item.id];
    return !stock || stock.error || !stock.availableForPurchase ||
      Number(item.quantity) > stock.currentStock;
  });

  const pendingVendors = vendors.filter(
    (vendor) => vendor.status === "Pending"
  );

  function formatCurrency(value) {
    return `₹${Number(value || 0).toLocaleString("en-IN", {
      maximumFractionDigits: 2,
    })}`;
  }

  function formatCartCurrency(value) {
    return `₹ ${Number(value || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  function renderAdminOverview() {
    const summaryCards = [
      {
        title: "Total Revenue",
        value: formatCurrency(adminSummary?.total_revenue),
        icon: IndianRupee,
      },
      {
        title: "Completed Transactions",
        value: adminSummary?.completed_transactions ?? "—",
        icon: ShoppingCart,
      },
      {
        title: "Total Products",
        value: adminSummary?.total_products ?? "—",
        icon: Package,
      },
      {
        title: "Total Vendors",
        value: adminSummary?.total_vendors ?? "—",
        icon: Users,
      },
    ];

    return (
      <>
        {adminError && (
          <div className="activity-card" role="alert">
            <p>{adminError}</p>
            <button
              className="secondary-button"
              onClick={() => loadAdminData("Overview")}
            >
              Try again
            </button>
          </div>
        )}

        <div className="section-heading">
          <div>
            <h2>Marketplace Overview</h2>
            <p>Live statistics from your ShopSense database.</p>
          </div>

          <button
            className="secondary-button"
            onClick={() => loadAdminData("Overview")}
            disabled={isAdminLoading}
          >
            <RefreshCw size={16} />
            {isAdminLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        <div className="stats-grid">
          {summaryCards.map((stat) => {
            const Icon = stat.icon;

            return (
              <div className="stat-card" key={stat.title}>
                <div className="stat-top">
                  <span>{stat.title}</span>
                  <div className="stat-icon">
                    <Icon size={20} />
                  </div>
                </div>

                <h2>
                  {isAdminLoading && adminSummary === null
                    ? "Loading..."
                    : stat.value}
                </h2>

                <div className="stat-change">
                  <CheckCircle size={15} />
                  <span>Database statistics</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="activity-card">
          <div className="empty-icon">
            <ShieldCheck size={28} />
          </div>

          <h3>Admin Control Center</h3>

          <p>
            Manage vendor approvals, monitor products, and analyse
            marketplace performance from one dashboard.
          </p>

          <div className="form-actions">
            <button
              className="primary-button"
              onClick={() => navigateToTab("Vendors")}
            >
              <Users size={17} />
              Manage Vendors
              {pendingVendors.length > 0
                ? ` (${pendingVendors.length} pending)`
                : ""}
            </button>

            <button
              className="secondary-button"
              onClick={() => navigateToTab("Analytics")}
            >
              <BarChart3 size={17} />
              View Analytics
            </button>
          </div>
        </div>
      </>
    );
  }

  function renderAdminVendors() {
    return (
      <>
        {adminError && (
          <div className="activity-card" role="alert">
            <p>{adminError}</p>
          </div>
        )}

        <div className="section-heading">
          <div>
            <h2>Vendor Management</h2>
            <p>Review vendor registrations and manage approvals.</p>
          </div>

          <button
            className="secondary-button"
            onClick={() => loadAdminData("Vendors")}
            disabled={isAdminLoading}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-top">
              <span>Total Vendors</span>
              <div className="stat-icon">
                <Users size={20} />
              </div>
            </div>
            <h2>{isAdminLoading ? "..." : vendors.length}</h2>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span>Pending Approval</span>
              <div className="stat-icon">
                <Clock size={20} />
              </div>
            </div>
            <h2>{isAdminLoading ? "..." : pendingVendors.length}</h2>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span>Active Vendors</span>
              <div className="stat-icon">
                <CheckCircle size={20} />
              </div>
            </div>
            <h2>
              {isAdminLoading
                ? "..."
                : vendors.filter((vendor) => vendor.status === "Active")
                    .length}
            </h2>
          </div>
        </div>

        {isAdminLoading && vendors.length === 0 ? (
          <div className="activity-card">
            <p>Loading vendors...</p>
          </div>
        ) : vendors.length === 0 ? (
          <div className="activity-card">
            <Users size={30} />
            <h3>No vendors found</h3>
            <p>Registered vendors will appear here.</p>
          </div>
        ) : (
          <div className="activity-card">
            <h3>Registered Vendors</h3>

            <div className="products-list">
              {vendors.map((vendor) => (
                <div className="product-row" key={vendor.vendor_id}>
                  <div style={{ flex: "1 1 200px" }}>
                    <strong>{vendor.business_name}</strong>

                    <p>Owner: {vendor.owner_name}</p>
                    <p>Email: {vendor.email}</p>
                    <p>Category: {vendor.category || "Not specified"}</p>

                    <span
                      className={
                        vendor.status === "Active"
                          ? "status-dot connected"
                          : "status-dot"
                      }
                    />

                    <strong>{vendor.status}</strong>
                  </div>

                  {vendor.status === "Pending" && (
                    <button
                      className="primary-button"
                      disabled={approvingVendor === vendor.vendor_id}
                      onClick={() =>
                        handleApproveVendor(vendor.vendor_id)
                      }
                    >
                      <CheckCircle size={16} />
                      {approvingVendor === vendor.vendor_id
                        ? "Approving..."
                        : "Approve Vendor"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </>
    );
  }

  function renderAdminProducts() {
    return (
      <>
        {adminError && (
          <div className="activity-card" role="alert">
            <p>{adminError}</p>
          </div>
        )}

        <div className="section-heading">
          <div>
            <h2>Marketplace Products</h2>
            <p>Review products listed across the marketplace.</p>
          </div>

          <button
            className="secondary-button"
            onClick={() => loadAdminData("Products")}
            disabled={isAdminLoading}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>

        <div className="activity-card">
          <h3>{products.length} product(s)</h3>

          {isAdminLoading && products.length === 0 ? (
            <p>Loading products...</p>
          ) : products.length === 0 ? (
            <p>No products are currently available.</p>
          ) : (
            <div className="products-list">
              {products.map((product) => (
                <div
                  className="product-row"
                  key={product.product_id ?? product.id}
                >
                  <div style={{ flex: "1 1 180px" }}>
                    <strong>
                      {product.product_name || product.name || "Product"}
                    </strong>

                    <p>
                      Product ID: {product.product_id ?? product.id}
                    </p>

                    <p>Category: {product.category || "General"}</p>

                    <p>Vendor ID: {product.vendor_id ?? "—"}</p>
                  </div>

                  <strong>
                    {formatCurrency(product.price ?? product.unit_price)}
                  </strong>
                </div>
              ))}
            </div>
          )}
        </div>
      </>
    );
  }

function renderAdminAnalytics() {
  return <Analytics />;
}

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Store size={23} />
          </div>

          <div>
            <h2>ShopSense</h2>
            <span>Marketplace & Analytics</span>
          </div>
        </div>

        <div className="workspace-label">WORKSPACE</div>

        <nav className="navigation">
          {(navigation[role] || navigation.Customer).map((item) => {
            const Icon = item.icon;

            return (
              <button
                key={item.name}
                className={
                  activeTab === item.name
                    ? "nav-item active"
                    : "nav-item"
                }
                onClick={() => navigateToTab(item.name)}
              >
                <Icon size={19} />

                <span>
                  {item.name}
                  {role === "Customer" &&
                  item.name === "Cart" &&
                  cartQuantity > 0
                    ? ` (${cartQuantity})`
                    : ""}
                </span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <button className="nav-item" onClick={handleLogout}>
            <span>↪</span>
            <span>Logout</span>
          </button>

          <div className="user-card">
            <div className="avatar">
              {user.email?.charAt(0).toUpperCase() || "S"}
            </div>

            <div className="user-info">
              <strong>{user.email || "ShopSense User"}</strong>
              <span>{role} Account</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <button className="mobile-menu">
            <Menu size={22} />
          </button>

          <div className="breadcrumb">
            Workspace <span>/</span> {activeTab}
          </div>

          <div className="topbar-right">
            <div className="search-box">
              <Search size={18} />
              <input placeholder="Search anything..." />
            </div>

            <button className="notification">
              <Bell size={20} />
              <span />
            </button>

            <button
              className="secondary-button logout-button"
              type="button"
              onClick={handleLogout}
              aria-label="Log out of ShopSense"
            >
              <LogOut size={16} />
              <span>Logout</span>
            </button>

            <div className="avatar top-avatar">
              {user.email?.charAt(0).toUpperCase() || "S"}
            </div>
          </div>
        </header>

        <section className="content">
          <div className="welcome-row">
            <div>
              <div className="eyebrow">
                {role.toUpperCase()} DASHBOARD
              </div>

              <h1>
                {role === "Customer" && activeTab === "Marketplace"
                  ? "Discover products"
                  : activeTab === "Add Product"
                    ? "Add a new product"
                    : role === "Admin" && activeTab === "Vendors"
                      ? "Vendor Management"
                      : role === "Admin" && activeTab === "Products"
                        ? "Marketplace Products"
                        : role === "Admin" && activeTab === "Analytics"
                          ? "Marketplace Analytics"
                          : role === "Admin" && activeTab === "MLflow Tracking"
                            ? "MLflow & Model Tracking"
                          : `Welcome to ${activeTab}`}
              </h1>

              <p>
                {role === "Customer"
                  ? "Explore products from different marketplace sellers."
                  : role === "Admin"
                    ? "Manage marketplace activity, vendor approvals and analytics."
                    : "Manage your products and marketplace activity."}
              </p>
            </div>

            {role === "Vendor" && activeTab === "Overview" && (
              <button
                className="primary-button"
                onClick={() => navigateToTab("Add Product")}
              >
                <Plus size={17} /> Add Product
              </button>
            )}
          </div>

          <div className="backend-status">
            <span
              className={
                apiStatus === "Backend connected successfully"
                  ? "status-dot connected"
                  : "status-dot"
              }
            />

            {apiStatus}
          </div>

          {/* ADMIN DASHBOARD */}

          {role === "Admin" && activeTab === "Overview" &&
            renderAdminOverview()}

          {role === "Admin" && activeTab === "Vendors" &&
            renderAdminVendors()}

          {role === "Admin" && activeTab === "Products" &&
            renderAdminProducts()}

          {role === "Admin" && activeTab === "Analytics" &&
            renderAdminAnalytics()}
          {role === "Admin" && activeTab === "BI Dashboard" && (
            <BiDashboard />
          )}
          {role === "Admin" && activeTab === "Inventory" && (
           <InventoryDashboard />
                                 )}
          {role === "Admin" && activeTab === "Customer Analytics" && (
            <CustomerAnalytics />
                                 )}
          {role === "Admin" && activeTab === "MLflow Tracking" && (
            <MlflowDashboard />
          )}
          {role === "Admin" && activeTab === "Workflows" && (
            <WorkflowDashboard />
          )}
          {role === "Customer" && activeTab === "Recommendations" && (
           <RecommendationDashboard
             onAddToCart={handleAddToCart}
             onToggleWishlist={toggleWishlist}
             wishlist={wishlist}
           />
                                 )}
          {/* VENDOR OVERVIEW */}

          {role === "Vendor" && activeTab === "Overview" && (
            <>
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-top">
                    <span>My Products</span>
                    <div className="stat-icon">
                      <Package size={20} />
                    </div>
                  </div>

                  <h2>{products.length}</h2>

                  <div className="stat-change">Live product count</div>
                </div>

                <div className="stat-card">
                  <div className="stat-top">
                    <span>Sales Analytics</span>
                    <div className="stat-icon">
                      <BarChart3 size={20} />
                    </div>
                  </div>

                  <h2>—</h2>
                  <div className="stat-change">
                    Vendor-specific analytics not connected yet
                  </div>
                </div>
              </div>

              <div className="activity-card">
                <div className="empty-icon">
                  <ShoppingBag size={26} />
                </div>

                <h3>Your marketplace starts here</h3>

                <p>
                  Your account has {products.length} product(s) returned
                  by the backend. Add products to grow your business.
                </p>

                <button
                  className="primary-button"
                  onClick={() => navigateToTab("Add Product")}
                >
                  Add a product
                </button>
              </div>
            </>
          )}

          {/* VENDOR PRODUCTS */}

          {role === "Vendor" && activeTab === "My Products" && (
            <div className="activity-card">
              <h3>My Products ({products.length})</h3>

              {products.length === 0 ? (
                <p>No products found for this vendor.</p>
              ) : (
                <div className="products-list">
                  {products.map((product) => (
                    <div
                      className="product-row"
                      key={product.product_id ?? product.id}
                    >
                      <div>
                        <strong>
                          {product.product_name || product.name || "Product"}
                        </strong>

                        <p>
                          Category: {product.category || "Not specified"}
                        </p>
                      </div>

                      <strong>
                        {formatCurrency(
                          product.price ?? product.unit_price
                        )}
                      </strong>
                    </div>
                  ))}
                </div>
              )}

              <button
                className="primary-button"
                onClick={() => navigateToTab("Add Product")}
              >
                <Plus size={17} /> Add Product
              </button>
            </div>
          )}

          {/* ADD PRODUCT */}

          {role === "Vendor" && activeTab === "Add Product" && (
            <div className="form-card">
              <h2>Product Information</h2>
              <p>Enter the details of the product you want to list.</p>

              <form onSubmit={handleAddProduct}>
                <label>Product name</label>

                <input
                  name="product_name"
                  value={productForm.product_name}
                  onChange={updateProductForm}
                  required
                  minLength={2}
                  maxLength={150}
                  placeholder="e.g. Wireless Keyboard"
                />

                <label>Category</label>

                <select
                  name="category"
                  value={productForm.category}
                  onChange={updateProductForm}
                >
                  <option value="">Select category (optional)</option>
                  <option>Electronics</option>
                  <option>Fashion</option>
                  <option>Home & Living</option>
                  <option>Books</option>
                  <option>Other</option>
                </select>

                <div className="form-grid">
                  <div>
                    <label>Unit price (₹)</label>

                    <input
                      name="price"
                      value={productForm.price}
                      onChange={updateProductForm}
                      required
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder="999"
                    />
                  </div>

                  <div>
                    <label>Opening stock</label>

                    <input
                      name="opening_stock"
                      value={productForm.opening_stock}
                      onChange={updateProductForm}
                      required
                      type="number"
                      min="0"
                      step="1"
                      placeholder="50"
                    />
                  </div>
                </div>

                <label>Low-stock threshold</label>

                <input
                  name="reorder_level"
                  value={productForm.reorder_level}
                  onChange={updateProductForm}
                  type="number"
                  min="0"
                  disabled
                />

                <p>
                  The current backend uses a default low-stock threshold
                  of 10.
                </p>

                {productError && (
                  <p role="alert" style={{ color: "#fa737e" }}>
                    {productError}
                  </p>
                )}

                <div className="form-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => navigateToTab("Overview")}
                  >
                    Cancel
                  </button>

                  <button
                    className="primary-button"
                    type="submit"
                    disabled={savingProduct}
                  >
                    {savingProduct ? "Saving..." : "Save Product"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* CUSTOMER MARKETPLACE */}

          {role === "Customer" && activeTab === "Marketplace" && (
            <div className="product-grid">
              {products.length === 0 ? (
                <div className="activity-card">
                  <h3>No products available</h3>
                  <p>
                    No products were returned by the backend.
                  </p>
                </div>
              ) : (
                products.map((product) => {
                  const productId = product.product_id ?? product.id;

                  const isWishlisted = wishlist.some(
                    (item) =>
                      (item.product_id ?? item.id) === productId
                  );

                  return (
                    <div
                      className="market-product"
                      key={productId}
                    >
                      <div className="market-product-icon">
                        <Package size={35} />
                      </div>

                      <button
                        className="secondary-button"
                        onClick={() => toggleWishlist(product)}
                      >
                        {isWishlisted
                          ? "♥ Remove from Wishlist"
                          : "♡ Add to Wishlist"}
                      </button>

                      <h3>
                        {product.product_name || product.name || "Product"}
                      </h3>

                      <p>{product.category || "General"}</p>

                      <strong>
                        {formatCurrency(
                          product.price ?? product.unit_price
                        )}
                      </strong>

                      <button
                        className="primary-button"
                        onClick={() => handleAddToCart(product)}
                      >
                        Add to Cart
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* CUSTOMER CART */}

          {role === "Customer" && activeTab === "Cart" && (
            <div className="cart-page">
              <div className="section-heading">
                <div>
                  <h2>Your Shopping Cart</h2>
                  <p>
                    <strong>{cartQuantity}</strong>{" "}
                    {cartQuantity === 1 ? "item" : "items"} in your cart
                  </p>
                </div>
              </div>

              {cart.length === 0 ? (
                <div className="activity-card">
                  <ShoppingCart size={34} />
                  <h3>Your cart is empty</h3>

                  <p>
                    Browse the marketplace and add products you want to buy.
                  </p>

                  <button
                    className="primary-button"
                    onClick={() => navigateToTab("Marketplace")}
                  >
                    Continue Shopping
                  </button>
                </div>
              ) : (
                <div className="cart-layout">
                  <div className="cart-items">
                    {cart.map((item) => {
                      const itemId = item.product_id ?? item.id;
                      const price = Number(
                        item.price ?? item.unit_price ?? 0
                      );
                      const stock = cartStock[itemId];
                      const stockIsPending = cartStockValidationPending || !stock;
                      const stockIsInvalid = !stock || stock.error ||
                        !stock.availableForPurchase ||
                        Number(item.quantity) > stock.currentStock;
                      let stockMessage = "Checking current stock…";
                      if (!stockIsPending && stock.error) {
                        stockMessage = stock.error;
                      } else if (!stockIsPending && stock.currentStock === 0) {
                        stockMessage = "Out of Stock";
                      } else if (!stockIsPending && !stock.availableForPurchase) {
                        stockMessage = "Currently unavailable for purchase.";
                      } else if (!stockIsPending && Number(item.quantity) > stock.currentStock) {
                        stockMessage = `Only ${stock.currentStock} available; ${item.quantity} requested.`;
                      } else if (!stockIsPending) {
                        stockMessage = `${stock.currentStock} available`;
                      }

                      return (
                        <div
                          className={`activity-card cart-item${stockIsInvalid && !stockIsPending ? " cart-item-invalid" : ""}`}
                          key={itemId}
                        >
                          <div className="cart-product-icon" aria-hidden="true">
                            <Package size={23} />
                          </div>

                          <div className="cart-item-details">
                            <h3>
                              {item.product_name || item.name || "Product"}
                            </h3>

                            <p>{item.category || "General"}</p>
                            <span className="cart-unit-price">
                              {formatCartCurrency(price)} each
                            </span>
                            <p
                              className={`cart-stock-message${stockIsInvalid && !stockIsPending ? " invalid" : ""}`}
                              role={stockIsInvalid && !stockIsPending ? "alert" : "status"}
                            >
                              {stockMessage}
                            </p>
                          </div>

                          <div className="cart-quantity-control" aria-label="Quantity controls">
                            <button
                              className="secondary-button"
                              aria-label="Decrease quantity"
                              disabled={isCheckingOut || Number(item.quantity) <= 1}
                              onClick={() =>
                                setCart((currentCart) =>
                                  currentCart
                                    .map((cartItem) =>
                                      (cartItem.product_id ?? cartItem.id) ===
                                      itemId
                                        ? {
                                            ...cartItem,
                                            quantity: Math.max(1, Number(cartItem.quantity) - 1),
                                          }
                                        : cartItem
                                    )
                                )
                              }
                            >
                              <Minus size={16} />
                            </button>

                            <span aria-live="polite">{item.quantity}</span>

                            <button
                              className="secondary-button"
                              aria-label="Increase quantity"
                              disabled={isCheckingOut || !stock || stock.error ||
                                !stock.availableForPurchase ||
                                stock.currentStock <= 0 ||
                                Number(item.quantity) >= stock.currentStock}
                              onClick={() =>
                                setCart((currentCart) =>
                                  currentCart.map((cartItem) =>
                                    (cartItem.product_id ?? cartItem.id) ===
                                    itemId
                                      ? {
                                          ...cartItem,
                                          quantity:
                                            cartItem.quantity + 1,
                                        }
                                      : cartItem
                                  )
                                )
                              }
                            >
                              <Plus size={16} />
                            </button>
                          </div>

                          <div className="cart-item-subtotal">
                            <span>Subtotal</span>
                            <strong>{formatCartCurrency(price * Number(item.quantity))}</strong>
                          </div>

                          <button
                            className="secondary-button cart-remove-button"
                            aria-label={`Remove ${item.product_name || item.name || "product"} from cart`}
                            title="Remove from cart"
                            disabled={isCheckingOut}
                            onClick={() =>
                              setCart((currentCart) =>
                                currentCart.filter(
                                  (cartItem) =>
                                    (cartItem.product_id ?? cartItem.id) !==
                                    itemId
                                )
                              )
                            }
                          >
                            <Trash2 size={17} />
                          </button>
                        </div>
                      );
                    })}
                  </div>

                  <div className="activity-card cart-summary">
                    <h3>Order Summary</h3>

                    <div className="cart-summary-row">
                      <span>Items</span>
                      <strong>{cartQuantity}</strong>
                    </div>

                    <div className="cart-summary-row">
                      <span>Subtotal</span>
                      <strong>{formatCartCurrency(cartTotal)}</strong>
                    </div>

                    <div className="cart-summary-total">
                      <strong>Final total</strong>
                      <strong>{formatCartCurrency(cartTotal)}</strong>
                    </div>

                    <p className={`cart-validation-summary${cartHasInvalidStock ? " invalid" : ""}`} role={cartHasInvalidStock && !cartStockValidationPending ? "alert" : "status"}>
                      {cartStockValidationPending
                        ? "Checking current availability for your items…"
                        : cartHasInvalidStock
                          ? "Resolve stock issues before placing your order. You can reduce quantity or remove an unavailable product."
                          : "All items are within current available stock."}
                    </p>

                    <button
                      className="secondary-button cart-refresh-button"
                      type="button"
                      onClick={handleRefreshCartStock}
                      disabled={isCartStockLoading || isCheckingOut}
                    >
                      <RefreshCw size={15} />
                      {isCartStockLoading ? "Checking stock…" : "Refresh availability"}
                    </button>

                    {checkoutError && (
                      <p className="cart-checkout-error" role="alert">
                        {checkoutError}
                      </p>
                    )}

                    <button
                      className="primary-button"
                      onClick={handleCheckout}
                      disabled={isCheckingOut || cart.length === 0 || cartStockValidationPending || cartHasInvalidStock}
                    >
                      {isCheckingOut
                        ? isCartStockLoading ? "Checking stock…" : "Placing order…"
                        : "Place Order"}
                    </button>

                    <button
                      className="secondary-button"
                      style={{ marginTop: "10px", width: "100%" }}
                      onClick={() => navigateToTab("Marketplace")}
                    >
                      Continue Shopping
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* CUSTOMER WISHLIST */}

          {role === "Customer" && activeTab === "Wishlist" && (
            <div className="wishlist-page">
              <div className="section-heading">
                <div>
                  <h2>My Wishlist</h2>
                  <p>
                    {wishlist.length === 0
                      ? "Save products here to buy them later."
                      : `${wishlist.length} saved ${wishlist.length === 1 ? "product" : "products"}`}
                  </p>
                </div>
              </div>

              {wishlist.length === 0 ? (
                <div className="activity-card">
                  <div className="empty-icon">
                    <Package size={26} />
                  </div>
                  <h3>Your wishlist is empty</h3>
                  <p>
                    Browse the Marketplace and tap the heart button on any
                    product to save it here.
                  </p>
                  <button
                    className="primary-button"
                    onClick={() => navigateToTab("Marketplace")}
                  >
                    Browse Marketplace
                  </button>
                </div>
              ) : (
                <div className="wishlist-grid">
                  {wishlist.map((product) => {
                    const productId = product.product_id ?? product.id;
                    return (
                      <div className="market-product" key={productId}>
                        <div className="market-product-icon">
                          <Package size={35} />
                        </div>

                        <h3>
                          {product.product_name || product.name || "Product"}
                        </h3>

                        <p>{product.category || "General"}</p>

                        <strong>
                          {formatCurrency(product.price ?? product.unit_price)}
                        </strong>

                        <div className="wishlist-actions">
                          <button
                            className="primary-button"
                            onClick={() => handleAddToCart(product)}
                          >
                            Add to Cart
                          </button>

                          <button
                            className="secondary-button wishlist-remove-btn"
                            aria-label={`Remove ${product.product_name || product.name || "product"} from wishlist`}
                            onClick={() => toggleWishlist(product)}
                          >
                            ♥ Remove
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* CUSTOMER ORDERS */}

          {role === "Customer" && activeTab === "My Orders" && (
            <CustomerOrders
              recentOrder={orderConfirmation}
              onContinueShopping={() => navigateToTab("Marketplace")}
            />
          )}

          {/* CUSTOMER PROFILE */}

          {role === "Customer" && activeTab === "My Profile" && (
            <CustomerProfile
              onProfileUpdate={(updated) => {
                const stored = localStorage.getItem("shopsense_user");
                try {
                  const parsed = stored ? JSON.parse(stored) : {};
                  const merged = { ...parsed, email: updated.email };
                  localStorage.setItem("shopsense_user", JSON.stringify(merged));
                  setUser((u) => ({ ...u, email: updated.email }));
                } catch {
                  // ignore parse errors
                }
              }}
            />
          )}

          {/* VENDOR ORDERS */}

          {role === "Vendor" && activeTab === "Orders" && (
            <VendorOrders />
          )}

          {/* VENDOR ANALYTICS */}

          {role === "Vendor" && activeTab === "Analytics" && (
            <VendorAnalytics />
          )}

          {/* SETTINGS — Coming Soon for all roles */}

          {activeTab === "Settings" && (
            <div className="settings-page">
              <div className="section-heading">
                <div>
                  <h2>Settings</h2>
                  <p>Manage your account and workspace preferences.</p>
                </div>
              </div>

              <div className="activity-card settings-coming-soon">
                <div className="empty-icon">
                  <Settings size={26} />
                </div>

                <h3>Coming Soon</h3>

                <p>
                  Account preferences, notification settings and workspace
                  configuration will be available in a future update.
                </p>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
