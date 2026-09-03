import os
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
from psycopg2 import sql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

from common.db import connect, load_env

CSV_PATH = Path(os.environ.get("CSV_PATH", ROOT / "data" / "source_data.csv"))
SOURCE_TABLE = "raw_monthly_report"


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
    load_env()
    source_conn = connect("SOURCE")
    try:
        load_source(source_conn)
    finally:
        source_conn.close()


if __name__ == "__main__":
    main()
