import os
import socket
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parent.parent
LOCAL_PORTS = {"source_db": "5433", "dwh_db": "5434"}
MONTH_NAMES = {
    1: "فروردین",
    2: "اردیبهشت",
    3: "خرداد",
    4: "تیر",
    5: "مرداد",
    6: "شهریور",
    7: "مهر",
    8: "آبان",
    9: "آذر",
    10: "دی",
    11: "بهمن",
    12: "اسفند",
}

FACT_FROM = """
FROM fact_work_order_status f
JOIN dim_office o ON o.office_id = f.office_id
JOIN dim_date d ON d.date_id = f.date_id
JOIN dim_category c ON c.category_id = f.category_id
JOIN dim_status s ON s.status_id = f.status_id
"""


def load_env(path):
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_env(ROOT / ".env")


def db_host_port():
    host = os.environ["DWH_DB_HOST"]
    port = os.environ["DWH_DB_PORT"]
    try:
        socket.getaddrinfo(host, int(port))
        return host, port
    except socket.gaierror:
        if host in LOCAL_PORTS:
            return "localhost", LOCAL_PORTS[host]
        raise


def connect():
    host, port = db_host_port()
    return psycopg2.connect(
        host=host,
        port=port,
        user=os.environ["DWH_DB_USER"],
        password=os.environ["DWH_DB_PASSWORD"],
        dbname=os.environ["DWH_DB_NAME"],
    )


@contextmanager
def cursor():
    conn = connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


def filters_sql(year, month, code, category_code, status_code):
    clauses = []
    params = []
    if year not in (None, ""):
        clauses.append("d.year = %s")
        params.append(int(year))
    if month not in (None, ""):
        clauses.append("d.month = %s")
        params.append(int(month))
    if code:
        clauses.append("o.code = %s")
        params.append(code)
    if category_code:
        clauses.append("c.category_code = %s")
        params.append(category_code)
    if status_code:
        clauses.append("s.status_code = %s")
        params.append(status_code)
    where = " AND ".join(clauses) if clauses else "TRUE"
    return where, params


def fetch_all(query, params=None):
    with cursor() as cur:
        cur.execute(query, params or [])
        return list(cur.fetchall())


def fetch_one(query, params=None):
    with cursor() as cur:
        cur.execute(query, params or [])
        row = cur.fetchone()
        return dict(row) if row else {}


app = FastAPI(title="Open Work Orders API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    fetch_one("SELECT 1 AS ok")
    return {"status": "ok"}


@app.get("/api/filters")
def api_filters():
    periods = fetch_all(
        "SELECT year, month FROM dim_date ORDER BY year, month"
    )
    for period in periods:
        period["month_name"] = MONTH_NAMES.get(period["month"], str(period["month"]))
    return {
        "periods": periods,
        "offices": fetch_all(
            "SELECT code, name FROM dim_office ORDER BY code"
        ),
        "categories": fetch_all(
            "SELECT category_code FROM dim_category ORDER BY category_code"
        ),
        "statuses": fetch_all(
            "SELECT status_code, name_fa FROM dim_status ORDER BY status_id"
        ),
    }


@app.get("/api/kpis")
def api_kpis(
    year=Query(default=None),
    month=Query(default=None),
    code=Query(default=None),
    category_code=Query(default=None),
    status_code=Query(default=None),
):
    where, params = filters_sql(year, month, code, category_code, status_code)
    totals = fetch_one(
        f"""
        SELECT
            COALESCE(SUM(f.order_count), 0) AS total_open,
            COUNT(DISTINCT o.code) AS office_count
        {FACT_FROM}
        WHERE {where}
        """,
        params,
    )
    top = fetch_one(
        f"""
        SELECT c.category_code, SUM(f.order_count) AS total
        {FACT_FROM}
        WHERE {where}
        GROUP BY c.category_code
        ORDER BY total DESC
        LIMIT 1
        """,
        params,
    )
    return {
        "total_open": int(totals.get("total_open") or 0),
        "office_count": int(totals.get("office_count") or 0),
        "top_category": top.get("category_code"),
        "top_category_total": int(top.get("total") or 0) if top else 0,
    }


@app.get("/api/metrics/trend")
def api_trend(
    year=Query(default=None),
    month=Query(default=None),
    code=Query(default=None),
    category_code=Query(default=None),
    status_code=Query(default=None),
):
    where, params = filters_sql(year, month, code, category_code, status_code)
    rows = fetch_all(
        f"""
        SELECT d.year, d.month, SUM(f.order_count) AS total
        {FACT_FROM}
        WHERE {where}
        GROUP BY d.year, d.month
        ORDER BY d.year, d.month
        """,
        params,
    )
    for row in rows:
        row["total"] = int(row["total"])
        row["month_name"] = MONTH_NAMES.get(row["month"], str(row["month"]))
    return rows


@app.get("/api/metrics/by-office")
def api_by_office(
    year=Query(default=None),
    month=Query(default=None),
    code=Query(default=None),
    category_code=Query(default=None),
    status_code=Query(default=None),
):
    where, params = filters_sql(year, month, code, category_code, status_code)
    rows = fetch_all(
        f"""
        SELECT o.code, o.name, SUM(f.order_count) AS total
        {FACT_FROM}
        WHERE {where}
        GROUP BY o.code, o.name
        ORDER BY total DESC
        """,
        params,
    )
    for row in rows:
        row["total"] = int(row["total"])
    return rows


@app.get("/api/metrics/by-category")
def api_by_category(
    year=Query(default=None),
    month=Query(default=None),
    code=Query(default=None),
    category_code=Query(default=None),
    status_code=Query(default=None),
):
    where, params = filters_sql(year, month, code, category_code, status_code)
    rows = fetch_all(
        f"""
        SELECT c.category_code, SUM(f.order_count) AS total
        {FACT_FROM}
        WHERE {where}
        GROUP BY c.category_code
        ORDER BY total DESC
        """,
        params,
    )
    for row in rows:
        row["total"] = int(row["total"])
    return rows


@app.get("/api/metrics/by-status")
def api_by_status(
    year=Query(default=None),
    month=Query(default=None),
    code=Query(default=None),
    category_code=Query(default=None),
    status_code=Query(default=None),
):
    where, params = filters_sql(year, month, code, category_code, status_code)
    rows = fetch_all(
        f"""
        SELECT s.status_code, s.name_fa, SUM(f.order_count) AS total
        {FACT_FROM}
        WHERE {where}
        GROUP BY s.status_id, s.status_code, s.name_fa
        ORDER BY total DESC
        """,
        params,
    )
    for row in rows:
        row["total"] = int(row["total"])
    return rows


@app.get("/api/metrics/matrix")
def api_matrix(
    year=Query(default=None),
    month=Query(default=None),
    code=Query(default=None),
    category_code=Query(default=None),
    status_code=Query(default=None),
):
    where, params = filters_sql(year, month, code, category_code, status_code)
    rows = fetch_all(
        f"""
        SELECT o.name, c.category_code, SUM(f.order_count) AS total
        {FACT_FROM}
        WHERE {where}
        GROUP BY o.name, c.category_code
        ORDER BY o.name, c.category_code
        """,
        params,
    )
    for row in rows:
        row["total"] = int(row["total"])
    return rows
