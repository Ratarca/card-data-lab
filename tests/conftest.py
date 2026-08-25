"""Shared pytest fixtures and fast/ordered test suite configuration.

Design goals (fast iteration):
- One shared session DB connection (no per-test connect cost).
- Ordered execution: schema tests → database → service → simulator → lake,
  so cheap/fast tests fail first and expensive data-generation tests run last.
- DB tests auto-skip when Postgres is unreachable.

Markers:
    pytest -m unit          # no DB needed, runs in <1s
    pytest -m db            # needs Postgres
    uv run task test-fast   # unit + db without simulator/lake
"""
from __future__ import annotations

import os

import psycopg2
import pytest

from oltp.run_migrations import get_connection, run_migrations


def _db_available() -> bool:
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason="PostgreSQL not reachable — run `uv run task infra && uv run task migrate`",
)

# Markers used by the layered suite.
unit = pytest.mark.unit
db = pytest.mark.db


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast tests, no external dependencies")
    config.addinivalue_line("markers", "db: requires a reachable PostgreSQL")
    config.addinivalue_line("markers", "slow: generates large volumes of data")


@pytest.fixture(scope="session")
def db_conn():
    """Session-scoped connection with migrations applied."""
    conn = get_connection()
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture()
def clean_outbox(db_conn):
    """Truncate outbox before the test that uses it.

    Tests that need pre-existing outbox volume should create their own events
    rather than relying on shared state — this keeps each test hermetic and
    avoids cross-suite destruction of data.
    """
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE event_outbox")
    db_conn.commit()
    yield db_conn


PG_SETTINGS = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5433")),  # 5433: host 5432 is used by Airflow's postgres
    "user": os.getenv("PGUSER", "cardlab"),
    "password": os.getenv("PGPASSWORD", "cardlab"),
    "dbname": os.getenv("PGDATABASE", "cardlab"),
}


def test_pg_settings_documented():
    assert PG_SETTINGS["port"] == 5433
