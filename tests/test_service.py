"""Stage 2A gate tests: API + transactional outbox (uses TestClient, no live server)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from services.main import app
from tests.conftest import db, requires_db

pytestmark = db

client = TestClient(app)


def _make_active_card(conn) -> str:
    client_id = str(uuid.uuid4())
    card_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO client.clients (client_id, name, income, age, segment) VALUES (%s,%s,%s,%s,%s)",
            (client_id, "Test User", 5000, 30, "standard"),
        )
        cur.execute(
            "INSERT INTO card.cards (card_id, client_id, product, status) VALUES (%s,%s,%s,'active')",
            (card_id, client_id, "gold"),
        )
    conn.commit()
    return card_id


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@requires_db
def test_authorize_approved_and_outbox_written(clean_outbox):
    card_id = _make_active_card(clean_outbox)
    r = client.post(
        "/api/purchases/authorize",
        params={"card_id": card_id},
        json={"amount": 99.9, "merchant": "ACME", "channel": "credit"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] is True
    assert body["authorization_id"] is not None

    # business rows + event committed together (scoped to this test's card)
    with clean_outbox.cursor() as cur:
        cur.execute("SELECT count(*) FROM purchase.purchases WHERE card_id = %s", (uuid.UUID(card_id),))
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT count(*) FROM event_outbox WHERE event_type = 'purchase.authorized' AND aggregate_id = %s",
            (uuid.UUID(card_id),),
        )
        assert cur.fetchone()[0] == 1


@requires_db
def test_authorize_declined_unknown_card(clean_outbox):
    r = client.post(
        "/api/purchases/authorize",
        params={"card_id": str(uuid.uuid4())},
        json={"amount": 10, "merchant": "X", "channel": "debit"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] is False
    assert body["decline_reason"] == "card_not_found"

    with clean_outbox.cursor() as cur:
        cur.execute("SELECT count(*) FROM event_outbox WHERE event_type = 'purchase.declined'")
        assert cur.fetchone()[0] == 1


@requires_db
def test_transaction_rollback_removes_both(clean_outbox):
    """If the event insert fails, the business row must roll back too (atomicity)."""
    from services.shared.catalog import PurchasePayload
    from services.modules.authorization.service import authorize_purchase

    card_id = _make_active_card(clean_outbox)
    payload = PurchasePayload(amount=50, merchant="Y", channel="credit")

    # Break the outbox by pre-inserting a conflicting event id is hard from outside;
    # instead simulate failure via monkeypatched persist_event raising.
    from services.modules.authorization import service as auth_service

    original = auth_service.persist_event

    def boom(cur, event):
        raise RuntimeError("forced failure")

    auth_service.persist_event = boom
    try:
        with pytest.raises(RuntimeError):
            authorize_purchase(card_id, payload)
    finally:
        auth_service.persist_event = original

    with clean_outbox.cursor() as cur:
        cur.execute("SELECT count(*) FROM purchase.purchases WHERE card_id = %s", (uuid.UUID(card_id),))
        assert cur.fetchone()[0] == 0, "business row must be rolled back"
        cur.execute(
            "SELECT count(*) FROM event_outbox WHERE aggregate_id = %s",
            (uuid.UUID(card_id),),
        )
        assert cur.fetchone()[0] == 0, "no partial events"
