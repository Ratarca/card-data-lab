"""Stage 1 gate: every event_type has a versioned schema and validates samples.

Marker: unit — no DB needed, runs in milliseconds.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.shared.catalog import (
    CATALOG,
    EventType,
    benefit_granted,
    card_activated,
    card_issued,
    customer_onboarded,
    eligibility_evaluated,
    invoice_closed,
    limit_assigned,
    payment_received,
    purchase_authorized,
    purchase_declined,
)
from services.shared.events import BaseEvent
from tests.conftest import unit

pytestmark = unit

EXPECTED_TYPES = {
    "customer.onboarded",
    "eligibility.evaluated",
    "limit.assigned",
    "card.issued",
    "card.activated",
    "purchase.authorized",
    "purchase.declined",
    "invoice.closed",
    "payment.received",
    "benefit.granted",
}


def test_catalog_has_all_10_event_types():
    assert set(CATALOG.keys()) == EXPECTED_TYPES
    assert {e.value for e in EventType} == EXPECTED_TYPES


def test_every_payload_model_has_json_schema():
    for payload_cls in CATALOG.values():
        schema = payload_cls.model_json_schema()
        assert schema["type"] == "object"


def test_envelope_has_required_fields():
    ev = card_activated(card_id="11111111-1111-1111-1111-111111111111")
    assert isinstance(ev, BaseEvent)
    assert ev.event_type == "card.activated"
    assert ev.dt_event == ev.ts_event.date()
    assert ev.header.schema_version >= 1


def test_customer_onboarded_validates():
    from services.shared.catalog import CustomerOnboardedPayload

    ev = customer_onboarded(
        client_id="22222222-2222-2222-2222-222222222222",
        p=CustomerOnboardedPayload(income=5000, age=30, segment="premium"),
    )
    assert ev.payload["income"] == 5000


def test_invalid_income_rejected():
    from services.shared.catalog import CustomerOnboardedPayload

    with pytest.raises(ValidationError):
        CustomerOnboardedPayload(income=-1, age=30, segment="x")


def test_purchase_events():
    from services.shared.catalog import PurchaseDeclinedPayload, PurchasePayload

    ok = purchase_authorized(
        card_id="33333333-3333-3333-3333-333333333333",
        p=PurchasePayload(amount=99.9, merchant="ACME", channel="credit"),
    )
    assert ok.payload["channel"] == "credit"

    bad = purchase_declined(
        card_id="33333333-3333-3333-3333-333333333333",
        p=PurchaseDeclinedPayload(amount=10, merchant="ACME", channel="debit", decline_reason="limit_exceeded"),
    )
    assert bad.payload["decline_reason"] == "limit_exceeded"


def test_invoice_payment_benefit_helpers():
    inv = invoice_closed(
        client_id="44444444-4444-4444-4444-444444444444",
        p={"total": 250, "due_date": "2026-09-10"},
    )
    pay = payment_received(
        invoice_id="1",
        client_id="44444444-4444-4444-4444-444444444444",
        p={"invoice_id": "1", "amount": 250, "paid_at": "2026-09-01"},
    )
    ben = benefit_granted(client_id="44444444-4444-4444-4444-444444444444", p={"program": "points", "points": 100})
    lim = limit_assigned(client_id="44444444-4444-4444-4444-444444444444", p={"limit_amount": 2000, "model_version": "v1"})
    eli = eligibility_evaluated(client_id="44444444-4444-4444-4444-444444444444", p={"policy_version": "p1", "approved": True})
    issued = card_issued(card_id="55555555-5555-5555-5555-555555555555", client_id="44444444-4444-4444-4444-444444444444", p={"product": "gold"})

    assert all(isinstance(e, BaseEvent) for e in [inv, pay, ben, lim, eli, issued])
