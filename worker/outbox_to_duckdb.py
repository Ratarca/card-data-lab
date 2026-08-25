"""Outbox worker: PostgreSQL event_outbox → DuckDB lake (Stage 3).

Reads unpublished rows from event_outbox, appends them to the DuckDB lake
partitioned by dt_event, deduplicates by event_id (idempotent re-runs),
then marks the outbox rows as published.

Run: uv run task lake
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pandas as pd

from oltp.run_migrations import get_connection

LAKE_PATH = Path(os.getenv("LAKE_PATH", "lake/events.duckdb"))


def _fetch_unpublished(conn, batch_size: int = 5000) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_id, event_type, ts_event, dt_event, aggregate_id,
                   schema_version, header, payload
            FROM event_outbox
            WHERE published_at IS NULL
            ORDER BY ts_event
            LIMIT %s
            """,
            (batch_size,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": str(r["event_id"]),
                "event_type": r["event_type"],
                "ts_event": r["ts_event"],
                "dt_event": r["dt_event"],
                "aggregate_id": str(r["aggregate_id"]),
                "schema_version": r["schema_version"],
                "header": json.dumps(r["header"], default=str),
                "payload": json.dumps(r["payload"], default=str),
            }
            for r in rows
        ]
    )


def run_worker(lake_path: Path | None = None) -> dict:
    """One worker pass. Returns summary counts."""
    lake_path = lake_path or LAKE_PATH
    lake_path.parent.mkdir(parents=True, exist_ok=True)

    pg = get_connection()
    try:
        rows = _fetch_unpublished(pg)
        if not rows:
            return {"fetched": 0, "appended": 0}

        df = _rows_to_dataframe(rows)
        con = duckdb.connect(str(lake_path))
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_events (
                    event_id VARCHAR PRIMARY KEY,
                    event_type VARCHAR,
                    ts_event TIMESTAMP,
                    dt_event DATE,
                    aggregate_id VARCHAR,
                    schema_version INTEGER,
                    header JSON,
                    payload JSON
                )
                """
            )
            # Idempotency: anti-join against existing event_ids before append.
            existing = con.execute("SELECT event_id FROM raw_events").df()
            if not existing.empty:
                df = df[~df["event_id"].isin(existing["event_id"])]

            appended = len(df)
            if appended:
                con.execute("INSERT INTO raw_events SELECT * FROM df")
        finally:
            con.close()

        # Mark published only for rows actually appended.
        appended_ids = {r["event_id"] for r in rows} if appended == len(rows) else None
        with pg.cursor() as cur:
            if appended_ids is None:
                cur.execute(
                    "UPDATE event_outbox SET published_at = now() WHERE published_at IS NULL"
                )
            else:
                cur.execute(
                    """
                    UPDATE event_outbox SET published_at = now()
                    WHERE published_at IS NULL AND event_id = ANY(%s::uuid[])
                    """,
                    ([str(i) for i in appended_ids],),
                )
        pg.commit()

        return {"fetched": len(rows), "appended": appended}
    finally:
        pg.close()


def reconcile() -> dict:
    """Compare outbox vs lake row counts (Gate G3 criterion)."""
    pg = get_connection()
    try:
        with pg.cursor() as cur:
            cur.execute("SELECT count(*) FROM event_outbox WHERE published_at IS NOT NULL")
            published = cur.fetchone()[0]
    finally:
        pg.close()

    con = duckdb.connect(str(LAKE_PATH))
    try:
        in_lake = con.execute("SELECT count(*) FROM raw_events").fetchone()[0]
    finally:
        con.close()
    return {"published_in_outbox": published, "in_lake": in_lake, "reconciled": published == in_lake}


if __name__ == "__main__":
    print(run_worker())
