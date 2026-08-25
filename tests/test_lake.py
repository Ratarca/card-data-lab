"""Stage 3 gate tests: lake append, idempotency, reconciliation."""
from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pytest

from tests.conftest import db, requires_db
from worker.outbox_to_duckdb import run_worker

pytestmark = [db, pytest.mark.slow]


@pytest.fixture()
def tmp_lake(tmp_path) -> Path:
    return tmp_path / "events.duckdb"


@requires_db
def test_worker_appends_events(clean_outbox, tmp_lake):
    """Events in outbox land in the DuckDB lake."""
    from services.shared.catalog import CustomerOnboardedPayload, customer_onboarded
    from services.shared.outbox import persist_event

    client_id = str(uuid.uuid4())
    with clean_outbox.cursor() as cur:
        cur.execute(
            "INSERT INTO client.clients (client_id, name, income, age, segment) VALUES (%s,%s,%s,%s,%s)",
            (client_id, "Lake Test", 4000, 28, "basic"),
        )
        ev = customer_onboarded(client_id=client_id, p=CustomerOnboardedPayload(income=4000, age=28, segment="basic"))
        persist_event(cur, ev)
    clean_outbox.commit()

    result = run_worker(lake_path=tmp_lake)
    assert result["fetched"] >= 1
    assert result["appended"] >= 1

    con = duckdb.connect(str(tmp_lake))
    try:
        count = con.execute("SELECT count(*) FROM raw_events").fetchone()[0]
    finally:
        con.close()
    assert count == result["appended"]


@requires_db
def test_worker_idempotent_no_duplicates(clean_outbox, tmp_lake):
    """Re-running the worker must not duplicate rows (Gate G3 criterion)."""
    # Ensure at least one unpublished event exists.
    client_id = str(uuid.uuid4())
    with clean_outbox.cursor() as cur:
        cur.execute(
            "INSERT INTO client.clients (client_id, name, income, age, segment) VALUES (%s,%s,%s,%s,%s)",
            (client_id, "Idem Test", 3000, 40, "standard"),
        )
        from services.shared.catalog import CustomerOnboardedPayload, customer_onboarded
        from services.shared.outbox import persist_event

        ev = customer_onboarded(client_id=client_id, p=CustomerOnboardedPayload(income=3000, age=40, segment="standard"))
        persist_event(cur, ev)
    clean_outbox.commit()

    first = run_worker(lake_path=tmp_lake)
    assert first["appended"] >= 1

    con = duckdb.connect(str(tmp_lake))
    try:
        after_first = con.execute("SELECT count(*) FROM raw_events").fetchone()[0]
    finally:
        con.close()

    second = run_worker(lake_path=tmp_lake)

    con = duckdb.connect(str(tmp_lake))
    try:
        after_second = con.execute("SELECT count(*) FROM raw_events").fetchone()[0]
    finally:
        con.close()

    assert second["appended"] == 0
    assert after_second == after_first  # no duplicates


@requires_db
def test_reconciliation_outbox_vs_lake(clean_outbox, tmp_lake):
    """Published outbox rows == lake rows (Gate G3 reconciliation), scoped to this test."""
    from worker.outbox_to_duckdb import reconcile

    before = reconcile()
    run_worker(lake_path=tmp_lake)
    report = reconcile()
    delta_published = report["published_in_outbox"] - before["published_in_outbox"]
    delta_lake = report["in_lake"] - before["in_lake"]
    assert delta_published == delta_lake, f"delta mismatch: outbox +{delta_published} vs lake +{delta_lake}"
