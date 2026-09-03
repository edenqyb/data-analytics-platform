import os

import httpx
import pandas as pd
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
ALL = "All"

st.set_page_config(page_title="Dashboard", layout="wide")

@st.cache_data(ttl=30)
def api_get(path, params=None):
    with httpx.Client(base_url=API_BASE_URL, timeout=20.0) as client:
        response = client.get(path, params=params or {})
        response.raise_for_status()
        return response.json()


def selected_params(filters):
    return {key: value for key, value in filters.items() if value not in (None, "", ALL)}


st.title("Dashboard of open work orders")

try:
    catalog = api_get("/api/filters")
except Exception as exc:
    st.error(
       f"connection to API failed ({API_BASE_URL}). "
        "please start the services with docker compose up.\n"
        f"error: {exc}"
    )
    st.stop()

periods = catalog["periods"]
offices = catalog["offices"]
categories = catalog["categories"]
statuses = catalog["statuses"]

with st.sidebar:
    st.header("Filters")
    period_options = [ALL] + [
        f"{p['year']}/{p['month']:02d} - {p['month_name']}"
        for p in periods
    ]
    period_choice = st.selectbox("Period", period_options)
    office_options = [ALL] + [f"{o['name']} ({o['code']})" for o in offices]
    office_choice = st.selectbox("Offices", office_options)
    category_options = [ALL] + [c["category_code"] for c in categories]
    category_choice = st.selectbox("Category", category_options)
    status_options = [ALL] + [f"{s['name_fa']} ({s['status_code']})" for s in statuses]
    status_choice = st.selectbox("Status", status_options)

filters = {}
if period_choice != ALL:
    period = periods[period_options.index(period_choice) - 1]
    filters["year"] = period["year"]
    filters["month"] = period["month"]
if office_choice != ALL:
    filters["code"] = offices[office_options.index(office_choice) - 1]["code"]
if category_choice != ALL:
    filters["category_code"] = category_choice
if status_choice != ALL:
    filters["status_code"] = statuses[status_options.index(status_choice) - 1]["status_code"]

params = selected_params(filters)

try:
    kpis = api_get("/api/kpis", params)
    trend = api_get("/api/metrics/trend", params)
    by_office = api_get("/api/metrics/by-office", params)
    by_category = api_get("/api/metrics/by-category", params)
    by_status = api_get("/api/metrics/by-status", params)
    matrix = api_get("/api/metrics/matrix", params)
except Exception as exc:
    st.error(f"error fetching data from API: {exc}")
    st.stop()

kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("Total open work orders", f"{kpis['total_open']:,}")
kpi2.metric("Number of offices", kpis["office_count"])
top_cat = kpis.get("top_category")
kpi3.metric(
    "Most common category",
    top_cat or "-",
    f"{kpis.get('top_category_total', 0):,}" if top_cat else None,
)

st.subheader("Monthly trend")
trend_df = pd.DataFrame(trend)
if trend_df.empty:
    st.info("No data to display.")
else:
    trend_df["period"] = trend_df.apply(
        lambda r: f"{int(r['year'])}/{int(r['month']):02d} {r['month_name']}", axis=1
    )
    st.bar_chart(trend_df.set_index("period")["total"])

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("By office")
    office_df = pd.DataFrame(by_office)
    if office_df.empty:
        st.info("No data to display.")
    else:
        st.bar_chart(office_df.set_index("name")["total"])
with col_b:
    st.subheader("By category")
    cat_df = pd.DataFrame(by_category)
    if cat_df.empty:
        st.info("No data to display.")
    else:
        st.bar_chart(cat_df.set_index("category_code")["total"])

st.subheader("By status")
status_df = pd.DataFrame(by_status)
if status_df.empty:
    st.info("No data to display.")
else:
    st.bar_chart(status_df.set_index("name_fa")["total"])

st.subheader("Office × Category matrix")
matrix_df = pd.DataFrame(matrix)
if matrix_df.empty:
    st.info("No data to display.")
else:
    pivot = matrix_df.pivot_table(
        index="name",
        columns="category_code",
        values="total",
        aggfunc="sum",
        fill_value=0,
    )
    st.dataframe(pivot, use_container_width=True)
