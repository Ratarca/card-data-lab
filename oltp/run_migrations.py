"""Migration runner: applies all .sql files in oltp/migrations in order.

Usage: uv run task migrate
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5433"),
        user=os.getenv("PGUSER", "cardlab"),
        password=os.getenv("PGPASSWORD", "cardlab"),
        dbname=os.getenv("PGDATABASE", "cardlab"),
    )


def run_migrations(conn=None) -> int:
    """Apply every migration file. Returns number of files applied."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    applied = 0
    try:
        with conn.cursor() as cur:
            for script in sorted(MIGRATIONS_DIR.glob("*.sql")):
                # Idempotent DDL: just execute; CREATE ... IF NOT EXISTS is a no-op if applied.
                cur.execute(script.read_text())
                applied += 1
        conn.commit()
    finally:
        if own_conn:
            conn.close()
    return applied


if __name__ == "__main__":
    n = run_migrations()
    print(f"Applied {n} migration file(s).")
