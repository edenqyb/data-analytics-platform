import os
import socket
import time
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
LOCAL_PORTS = {"source_db": "5433", "dwh_db": "5434"}


def load_env(path=None):
    path = Path(path) if path is not None else ROOT / ".env"
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


def connect(prefix, retries=30, delay=2):
    host, port = db_host_port(f"{prefix}_DB_HOST", f"{prefix}_DB_PORT")
    params = dict(
        host=host,
        port=port,
        user=os.environ[f"{prefix}_DB_USER"],
        password=os.environ[f"{prefix}_DB_PASSWORD"],
        dbname=os.environ[f"{prefix}_DB_NAME"],
    )
    for _ in range(retries):
        try:
            return psycopg2.connect(**params)
        except psycopg2.OperationalError:
            time.sleep(delay)
    raise RuntimeError(f"{prefix.lower()} postgres is not ready")
