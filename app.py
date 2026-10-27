# Streamlit app :

from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Olist E-Commerce Analytics",
    page_icon="📊",
    layout="wide"
)

import hashlib
import hmac


def require_login():
    if st.session_state.get("authenticated", False):
        st.sidebar.write(
            f"Signed in as: {st.session_state['username']}"
        )

        if st.sidebar.button("Log out"):
            st.session_state.clear()
            st.rerun()

        return

    st.title("Olist E-Commerce Analytics")
    st.subheader("Sign in")
    st.write("Enter your credentials to access the dashboard.")

    with st.form("login_form", clear_on_submit=True):
        username = st.text_input("User ID")
        password = st.text_input(
            "Password",
            type="password"
        )

        submitted = st.form_submit_button("Log in")

    if submitted:
        accounts = st.secrets["login_users"]
        username = username.strip()

        account_exists = username in accounts

        if account_exists:
            account = accounts[username]
        else:
            account = {
                "salt": "00" * 16,
                "password_hash": "00" * 32,
                "iterations": 600_000
            }

        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(account["salt"]),
            int(account["iterations"])
        ).hex()

        password_matches = hmac.compare_digest(
            candidate_hash,
            account["password_hash"]
        )

        if account_exists and password_matches:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.rerun()
        else:
            st.error("Invalid user ID or password.")

    st.stop()


require_login()

DATA_DIR = Path(__file__).resolve().parent / "data"


@st.cache_data
def load_data():
    orders = pd.read_csv(
        DATA_DIR / "orders_dashboard.csv"
    )

    items = pd.read_csv(
        DATA_DIR / "items_dashboard.csv"
    )

    orders["order_purchase_timestamp"] = pd.to_datetime(
        orders["order_purchase_timestamp"],
        errors="coerce"
    )

    # Handle boolean values consistently after CSV loading.
    for column in ["late_delivery", "valid_delivery"]:
        orders[column] = (
            orders[column]
            .astype("string")
            .str.strip()
            .str.lower()
            .isin(["true", "1"])
        )

    return orders, items


st.title("Olist E-Commerce Analytics")
st.caption(
    "Explore merchandise sales, delivery performance, "
    "customer ratings, and sellers. Currency: Brazilian real (BRL)."
)

required_files = [
    DATA_DIR / "orders_dashboard.csv",
    DATA_DIR / "items_dashboard.csv"
]

if any(not path.exists() for path in required_files):
    st.error("Required CSV files are missing from the data folder.")
    st.stop()

orders, items = load_data()

dated_orders = orders.dropna(
    subset=["order_purchase_timestamp"]
)

if dated_orders.empty:
    st.error("No valid purchase dates were found.")
    st.stop()

# ---------------- Sidebar filters ----------------

st.sidebar.header("Dashboard filters")

states = sorted(
    orders["customer_state"].dropna().unique().tolist()
)

selected_states = st.sidebar.multiselect(
    "Customer states",
    options=states,
    default=states
)

minimum_date = dated_orders[
    "order_purchase_timestamp"
].min().date()

maximum_date = dated_orders[
    "order_purchase_timestamp"
].max().date()

date_range = st.sidebar.date_input(
    "Purchase date range",
    value=(minimum_date, maximum_date),
    min_value=minimum_date,
    max_value=maximum_date
)

if len(date_range) != 2:
    st.info("Select both a start date and an end date.")
    st.stop()

start_date, end_date = date_range

purchase_dates = orders[
    "order_purchase_timestamp"
].dt.date

filtered_orders = orders.loc[
    orders["customer_state"].isin(selected_states)
    & purchase_dates.between(start_date, end_date)
].copy()

if filtered_orders.empty:
    st.warning("No orders match the selected filters.")
    st.stop()

# Sales measures use delivered orders.
delivered_orders = filtered_orders.loc[
    filtered_orders["order_status"].eq("delivered")
].copy()

delivered_items = items.loc[
    items["order_id"].isin(delivered_orders["order_id"])
].copy()

total_sales = delivered_items["price"].sum()
total_orders = delivered_orders["order_id"].nunique()

average_order_value = (
    total_sales / total_orders
    if total_orders
    else None
)

# Delivery measures require valid delivery records.
delivery_orders = filtered_orders.loc[
    filtered_orders["valid_delivery"]
].copy()

late_rate = (
    delivery_orders["late_delivery"].mean() * 100
    if not delivery_orders.empty
    else None
)

# ---------------- KPI cards ----------------

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Merchandise sales",
    f"R$ {total_sales:,.2f}"
)

col2.metric(
    "Delivered orders",
    f"{total_orders:,}"
)

col3.metric(
    "Average order value",
    f"R$ {average_order_value:,.2f}"
    if average_order_value is not None
    else "N/A"
)

col4.metric(
    "Late delivery rate",
    f"{late_rate:.2f}%"
    if late_rate is not None
    else "N/A"
)

st.caption(
    "Sales and average order value exclude freight and use delivered "
    "orders. Late delivery rate uses valid delivery records only."
)

sales_tab, delivery_tab, seller_tab, data_tab = st.tabs(
    ["Sales", "Delivery and ratings", "Sellers", "Data"]
)

# ---------------- Sales ----------------

with sales_tab:
    st.subheader("Monthly merchandise sales")

    monthly_sales = (
        delivered_orders
        .assign(
            month=delivered_orders[
                "order_purchase_timestamp"
            ].dt.to_period("M").astype(str)
        )
        .groupby("month")["merchandise_value"]
        .sum()
        .sort_index()
    )

    st.line_chart(monthly_sales)

    st.subheader("Top 15 product categories")

    category_sales = (
        delivered_items
        .groupby("category")["price"]
        .sum()
        .sort_values(ascending=False)
        .head(15)
        .rename("Sales (BRL)")
    )

    st.bar_chart(category_sales)

# ---------------- Delivery and ratings ----------------

with delivery_tab:
    st.subheader("Delivery performance")

    average_delivery = delivery_orders["delivery_days"].mean()

    st.metric(
        "Average delivery time",
        f"{average_delivery:.1f} days"
        if pd.notna(average_delivery)
        else "N/A"
    )

    st.caption(
        "Late means delivered after the estimated calendar date."
    )

    rated_orders = delivery_orders.dropna(
        subset=["average_review_score"]
    ).copy()

    rated_orders["delivery_status"] = (
        rated_orders["late_delivery"].map(
            {False: "On time", True: "Late"}
        )
    )

    rating_summary = (
        rated_orders
        .groupby("delivery_status", as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            average_rating=("average_review_score", "mean")
        )
    )

    st.subheader("Average order rating by delivery status")
    st.dataframe(rating_summary, hide_index=True)

    st.caption(
        "Each rated order receives equal weight. "
        "This comparison shows an association, not proof of causation."
    )

# ---------------- Sellers ----------------

with seller_tab:
    st.subheader("Top 15 sellers by merchandise sales")

    seller_sales = (
        delivered_items
        .groupby("seller_id", as_index=False)
        .agg(
            merchandise_sales=("price", "sum"),
            delivered_orders=("order_id", "nunique")
        )
        .sort_values(
            "merchandise_sales",
            ascending=False
        )
        .head(15)
    )

    st.dataframe(seller_sales, hide_index=True)

    st.caption(
        "Seller results follow the selected customer states "
        "and purchase dates."
    )

# ---------------- Data and download ----------------

with data_tab:
    st.subheader("Filtered order data")

    st.dataframe(
        filtered_orders.head(500),
        hide_index=True
    )

    st.caption("Preview shows up to 500 rows; download includes all matches.")

    st.download_button(
        label="Download filtered orders",
        data=filtered_orders.to_csv(index=False).encode("utf-8"),
        file_name="olist_filtered_orders.csv",
        mime="text/csv"
    )