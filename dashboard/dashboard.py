import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from app.database import engine

st.set_page_config(
    page_title="ShopSense Dashboard",
    page_icon="🛍️",
    layout="wide"
)

st.title("ShopSense — Marketplace Analytics")
st.caption("Multi-Vendor E-Commerce Analytics Platform")

if st.button("Refresh Dashboard"):
    st.rerun()


def load_data(query):
    with engine.connect() as connection:
        return pd.read_sql_query(text(query), connection)


try:
    # 1. Summary metrics
    summary = load_data("""
        SELECT
            COALESCE(SUM(CASE
                WHEN status = 'Completed' THEN amount
                ELSE 0
            END), 0) AS total_revenue,
            SUM(CASE
                WHEN status = 'Completed' THEN 1
                ELSE 0
            END) AS completed_sales,
            COALESCE(SUM(CASE
                WHEN status = 'Completed' THEN quantity
                ELSE 0
            END), 0) AS units_sold
        FROM transactions
    """)

    products = load_data("""
        SELECT COUNT(*) AS total_products
        FROM products
    """)

    vendors = load_data("""
        SELECT COUNT(*) AS total_vendors
        FROM vendors
    """)

    total_revenue = float(summary.iloc[0]["total_revenue"] or 0)
    completed_sales = int(summary.iloc[0]["completed_sales"] or 0)
    units_sold = int(summary.iloc[0]["units_sold"] or 0)
    total_products = int(products.iloc[0]["total_products"] or 0)
    total_vendors = int(vendors.iloc[0]["total_vendors"] or 0)

    # 2. KPI cards
    st.subheader("Marketplace Overview")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total Revenue", f"₹{total_revenue:,.2f}")
    col2.metric("Completed Sales", completed_sales)
    col3.metric("Units Sold", units_sold)
    col4.metric("Products", total_products)
    col5.metric("Vendors", total_vendors)

    st.divider()

    # 3. Product performance
    st.subheader("Product Performance")

    product_data = load_data("""
        SELECT
            p.product_id,
            p.product_name,
            p.category,
            p.price,
            COALESCE(SUM(
                CASE WHEN t.status = 'Completed'
                THEN t.quantity ELSE 0 END
            ), 0) AS units_sold,
            COALESCE(SUM(
                CASE WHEN t.status = 'Completed'
                THEN t.amount ELSE 0 END
            ), 0) AS revenue
        FROM products p
        LEFT JOIN transactions t
            ON p.product_id = t.product_id
        GROUP BY
            p.product_id, p.product_name, p.category, p.price
        ORDER BY revenue DESC
    """)

    if not product_data.empty:
        left, right = st.columns(2)

        with left:
            fig = px.bar(
                product_data,
                x="product_name",
                y="revenue",
                title="Revenue by Product",
                labels={
                    "product_name": "Product",
                    "revenue": "Revenue (₹)"
                }
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            fig = px.bar(
                product_data,
                x="product_name",
                y="units_sold",
                title="Units Sold by Product",
                labels={
                    "product_name": "Product",
                    "units_sold": "Units Sold"
                }
            )
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(product_data, use_container_width=True)
    else:
        st.info("No products found yet.")

    st.divider()

    # 4. Vendor performance
    st.subheader("Vendor Performance")

    vendor_data = load_data("""
        SELECT
            v.vendor_id,
            v.business_name,
            v.status,
            COUNT(DISTINCT p.product_id) AS product_count,
            COALESCE(SUM(
                CASE WHEN t.status = 'Completed'
                THEN t.amount ELSE 0 END
            ), 0) AS revenue,
            COALESCE(SUM(
                CASE WHEN t.status = 'Completed'
                THEN t.quantity ELSE 0 END
            ), 0) AS units_sold
        FROM vendors v
        LEFT JOIN products p
            ON v.vendor_id = p.vendor_id
        LEFT JOIN transactions t
            ON v.vendor_id = t.vendor_id
            AND p.product_id = t.product_id
        GROUP BY v.vendor_id, v.business_name, v.status
        ORDER BY revenue DESC
    """)

    if not vendor_data.empty:
        left, right = st.columns(2)

        with left:
            fig = px.bar(
                vendor_data,
                x="business_name",
                y="revenue",
                title="Revenue by Vendor",
                labels={
                    "business_name": "Vendor",
                    "revenue": "Revenue (₹)"
                }
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            st.dataframe(vendor_data, use_container_width=True)
    else:
        st.info("No vendors found yet.")

    st.divider()

    # 5. Inventory monitoring
    st.subheader("Inventory Monitoring")

    inventory_data = load_data("""
        SELECT
            p.product_id,
            p.product_name,
            i.current_stock,
            i.reorder_level,
            i.warehouse
        FROM inventory i
        JOIN products p
            ON i.product_id = p.product_id
        ORDER BY i.current_stock ASC
    """)

    if not inventory_data.empty:
        st.dataframe(inventory_data, use_container_width=True)

        low_stock = inventory_data[
            inventory_data["current_stock"]
            <= inventory_data["reorder_level"]
        ]

        if not low_stock.empty:
            st.warning(
                f"{len(low_stock)} product(s) are at or below "
                "their reorder level."
            )
            st.dataframe(low_stock, use_container_width=True)
        else:
            st.success("No products are currently at the reorder level.")
    else:
        st.info("No inventory records found.")

    st.caption("ShopSense Milestone 1 | Live database analytics")

except Exception as error:
    st.error("Could not load dashboard data.")
    st.write(str(error))
    st.info(
        "Check that MySQL is running, your .env settings are correct, "
        "and the database tables exist."
    )
