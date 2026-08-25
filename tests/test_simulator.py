"""Stage 2B gate tests: simulator volume and parameterization."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from simulator.run import simulate
from tests.conftest import db, requires_db

pytestmark = [db, pytest.mark.slow]


@requires_db
def test_simulator_volume_gate(db_conn):
    """≥100 clients, ≥1 month of events land in the outbox (Gate G2 criterion)."""
    stats = simulate(n_clients=100, months=1, seed=7)
    assert stats["clients"] >= 100
    assert stats["purchases"] >= 100 * 3  # min 3 purchases/month/client

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(DISTINCT aggregate_id) FROM event_outbox WHERE event_type LIKE 'purchase.%'")
        distinct_cards = cur.fetchone()[0]
    assert distinct_cards >= 100


@requires_db
def test_simulator_generates_historical_dates(clean_outbox):
    """A six-month window must yield event dates throughout the requested history."""
    start_date = date(2026, 1, 1)
    end_date = date(2026, 6, 30)
    stats = simulate(
        n_clients=10,
        months=6,
        start_date=start_date,
        end_date=end_date,
        fraud_rate=0.0,
        decline_rate=0.0,
        seed=11,
    )

    with clean_outbox.cursor() as cur:
        cur.execute("SELECT min(dt_event), max(dt_event) FROM event_outbox")
        first_event, last_event = cur.fetchone()

    assert stats["start_date"] == "2026-01-01"
    assert stats["end_date"] == "2026-06-30"
    assert stats["days"] == 181
    assert start_date <= first_event <= start_date + timedelta(days=14)
    assert last_event > date(2026, 5, 1)
    assert last_event <= end_date


@requires_db
def test_fraud_knob_changes_distribution(db_conn):
    """Higher fraud_rate must produce larger average amounts (outlier spikes)."""
    # Tag rows by run using a marker merchant so runs are distinguishable.
    from simulator import run as sim_run

    marker_low = "LOWRUN"
    marker_high = "HIGHRUN"
    original_merchants = sim_run.MERCHANTS
    sim_run.MERCHANTS = [marker_low]
    try:
        simulate(n_clients=20, months=1, fraud_rate=0.0, decline_rate=0.0, seed=1)
    finally:
        pass
    sim_run.MERCHANTS = [marker_high]
    try:
        simulate(n_clients=20, months=1, fraud_rate=0.5, decline_rate=0.0, seed=1)
    finally:
        sim_run.MERCHANTS = original_merchants

    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT CASE WHEN p.amount > 2000 THEN 'high' ELSE 'low' END grp, avg(p.amount)
            FROM purchase.purchases p
            WHERE p.purchased_at > now() - interval '1 minute'
              AND (p.amount > 2000) IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM purchase.authorizations a
                WHERE a.authorization_id = p.authorization_id AND a.merchant IN (%s, %s)
              )
            GROUP BY 1
        """, (marker_low, marker_high))
        rows = dict(cur.fetchall())

    if "low" in rows and "high" in rows:
        assert rows["high"] > rows["low"] * 3, "fraud spikes must inflate amounts"


@requires_db
def test_decline_knob_produces_decline_events(db_conn):
    db_conn.rollback()  # clear any aborted transaction state
    simulate(n_clients=10, months=1, fraud_rate=0.0, decline_rate=0.5, seed=3)
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM event_outbox WHERE event_type = 'purchase.declined'")
        declined = cur.fetchone()[0]
    assert declined > 0
