import os
import socket
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = Path(os.environ.get("CSV_PATH", ROOT / "data" / "source_data.csv"))
SOURCE_TABLE = "raw_monthly_report"
LOCAL_PORTS = {"source_db": "5433", "dwh_db": "5434"}


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


def create_source_table_sql(columns):
    fields = [sql.SQL("id SERIAL PRIMARY KEY")]
    for col in columns:
        typ = "VARCHAR(128) NOT NULL" if col == "name" else (
            "VARCHAR(16) NOT NULL" if col == "code" else "INTEGER NOT NULL"
        )
        fields.append(sql.SQL("{} " + typ).format(sql.Identifier(col)))
    return sql.SQL("CREATE TABLE {} ({})").format(
        sql.Identifier(SOURCE_TABLE),
        sql.SQL(", ").join(fields),
    )


def load_source(conn):
    df = pd.read_csv(CSV_PATH)
    columns = list(df.columns)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(SOURCE_TABLE))
            )
            cur.execute(create_source_table_sql(columns))
            buf = StringIO()
            df.to_csv(buf, index=False, header=False)
            buf.seek(0)
            copy_sql = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV)").format(
                sql.Identifier(SOURCE_TABLE),
                sql.SQL(", ").join(map(sql.Identifier, columns)),
            )
            cur.copy_expert(copy_sql.as_string(conn), buf)
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(SOURCE_TABLE)))
            print(f"loaded {cur.fetchone()[0]} rows into {SOURCE_TABLE}")


def main():
    load_env(ROOT / ".env")
    source_conn = connect("SOURCE")
    try:
        load_source(source_conn)
    finally:
        source_conn.close()


if __name__ == "__main__":
    main()
