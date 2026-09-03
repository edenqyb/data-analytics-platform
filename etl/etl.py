import os
import socket
import time
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parent.parent
SOURCE_TABLE = "raw_monthly_report"
LOCAL_PORTS = {"source_db": "5433", "dwh_db": "5434"}

CATEGORIES = {
    "cat1": ["in_progress", "invoice_prep", "at_hq", "at_finance"],
    "cat2": ["in_progress", "invoice_prep", "at_hq", "at_finance"],
    "cat3": ["in_progress", "invoice_prep", "at_hq", "at_finance"],
    "cat4": ["in_progress", "invoice_prep", "at_consultant", "at_hq", "at_finance"],
    "cat5": ["in_progress", "invoice_prep", "at_consultant", "at_hq", "at_finance"],
    "cat6": ["in_progress", "invoice_prep", "at_consultant", "at_hq", "at_finance"],
    "cat7": ["in_progress", "invoice_prep", "at_consultant", "at_hq", "at_finance"],
}

STATUSES = [
    ("in_progress", "در دست اجرا"),
    ("invoice_prep", "تهیه صورت وضعیت"),
    ("at_consultant", "صورت وضعیت نزد مشاور"),
    ("at_hq", "صورت وضعیت نزد ستاد"),
    ("at_finance", "صورت وضعیت نزد مالی"),
]

WAREHOUSE_DDL = """
DROP TABLE IF EXISTS fact_work_order_status CASCADE;
DROP TABLE IF EXISTS dim_office CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;
DROP TABLE IF EXISTS dim_category CASCADE;
DROP TABLE IF EXISTS dim_status CASCADE;

CREATE TABLE dim_office (
    office_id SERIAL PRIMARY KEY,
    code VARCHAR(16) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL
);

CREATE TABLE dim_date (
    date_id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    UNIQUE (year, month)
);

CREATE TABLE dim_category (
    category_id SERIAL PRIMARY KEY,
    category_code TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_status (
    status_id SERIAL PRIMARY KEY,
    status_code TEXT NOT NULL UNIQUE,
    name_fa TEXT NOT NULL
);

CREATE TABLE fact_work_order_status (
    id SERIAL PRIMARY KEY,
    office_id INTEGER NOT NULL REFERENCES dim_office (office_id),
    date_id INTEGER NOT NULL REFERENCES dim_date (date_id),
    category_id INTEGER NOT NULL REFERENCES dim_category (category_id),
    status_id INTEGER NOT NULL REFERENCES dim_status (status_id),
    order_count INTEGER NOT NULL,
    UNIQUE (office_id, date_id, category_id, status_id)
);
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


def db_host_port(host_key, port_key):
    host = os.environ[host_key]
    port = os.environ[port_key]
    try:
        socket.getaddrinfo(host, int(port))
        return host, port
    except socket.gaierror:
        if host in LOCAL_PORTS:
            return "localhost", LOCAL_PORTS[host]
        raise


def connect(prefix):
    host, port = db_host_port(f"{prefix}_DB_HOST", f"{prefix}_DB_PORT")
    params = dict(
        host=host,
        port=port,
        user=os.environ[f"{prefix}_DB_USER"],
        password=os.environ[f"{prefix}_DB_PASSWORD"],
        dbname=os.environ[f"{prefix}_DB_NAME"],
    )
    for _ in range(30):
        try:
            return psycopg2.connect(**params)
        except psycopg2.OperationalError:
            time.sleep(2)
    raise RuntimeError(f"{prefix.lower()} postgres is not ready")


def read_source(conn):
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(SOURCE_TABLE)))
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    if not rows:
        raise RuntimeError(f"{SOURCE_TABLE} is empty — run data/create_db.py first")
    return pd.DataFrame(rows, columns=cols)


def unpivot(df):
    id_vars = ["name", "code", "year", "month"]
    value_vars = []
    measure_map = {}
    for category, statuses in CATEGORIES.items():
        for status in statuses:
            col = f"{category}_{status}"
            value_vars.append(col)
            measure_map[col] = (category, status)
    long = df.melt(
        id_vars=id_vars,
        value_vars=value_vars,
        var_name="measure",
        value_name="order_count",
    )
    long["category_code"] = long["measure"].map(lambda m: measure_map[m][0])
    long["status_code"] = long["measure"].map(lambda m: measure_map[m][1])
    long["code"] = long["code"].astype(str)
    long["name"] = long["name"].astype(str)
    long["year"] = long["year"].astype(int)
    long["month"] = long["month"].astype(int)
    long["order_count"] = pd.to_numeric(long["order_count"], errors="coerce")
    return long.dropna(subset=["order_count"])


def load_warehouse(conn, df):
    long = unpivot(df)
    with conn:
        with conn.cursor() as cur:
            cur.execute(WAREHOUSE_DDL)
            execute_values(
                cur,
                """
                INSERT INTO dim_office (code, name) VALUES %s
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
                """,
                long[["code", "name"]]
                .drop_duplicates()
                .itertuples(index=False, name=None),
            )
            execute_values(
                cur,
                """
                INSERT INTO dim_date (year, month) VALUES %s
                ON CONFLICT (year, month) DO NOTHING
                """,
                long[["year", "month"]].drop_duplicates().itertuples(index=False, name=None),
            )
            execute_values(
                cur,
                """
                INSERT INTO dim_category (category_code) VALUES %s
                ON CONFLICT (category_code) DO NOTHING
                """,
                [(code,) for code in CATEGORIES],
            )
            execute_values(
                cur,
                """
                INSERT INTO dim_status (status_code, name_fa) VALUES %s
                ON CONFLICT (status_code) DO UPDATE SET name_fa = EXCLUDED.name_fa
                """,
                STATUSES,
            )
            cur.execute("TRUNCATE fact_work_order_status RESTART IDENTITY")
            cur.execute("SELECT office_id, code FROM dim_office")
            office_ids = {code: oid for oid, code in cur.fetchall()}
            cur.execute("SELECT date_id, year, month FROM dim_date")
            date_ids = {(year, month): did for did, year, month in cur.fetchall()}
            cur.execute("SELECT category_id, category_code FROM dim_category")
            category_ids = {code: cid for cid, code in cur.fetchall()}
            cur.execute("SELECT status_id, status_code FROM dim_status")
            status_ids = {code: sid for sid, code in cur.fetchall()}
            facts = [
                (
                    office_ids[row.code],
                    date_ids[(row.year, row.month)],
                    category_ids[row.category_code],
                    status_ids[row.status_code],
                    int(row.order_count),
                )
                for row in long.itertuples(index=False)
            ]
            execute_values(
                cur,
                """
                INSERT INTO fact_work_order_status
                    (office_id, date_id, category_id, status_id, order_count)
                VALUES %s
                """,
                facts,
            )
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(order_count), 0) FROM fact_work_order_status"
            )
            n_rows, total = cur.fetchone()
            print(f"loaded {n_rows} fact rows, SUM(order_count)={total}")


def main():
    load_env(ROOT / ".env")
    source_conn = connect("SOURCE")
    dwh_conn = connect("DWH")
    try:
        source_df = read_source(source_conn)
        print(f"read {len(source_df)} rows from {SOURCE_TABLE}")
        load_warehouse(dwh_conn, source_df)
    finally:
        source_conn.close()
        dwh_conn.close()


if __name__ == "__main__":
    main()
