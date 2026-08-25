"""Core base models & enums tests (unit — no DB)."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from core.enums import (
    CardProduct,
    CardStatus,
    ClientSegment,
    DeclineReason,
    PurchaseChannel,
)
from core.models import AuthorizationDecision, Card, Client, EventMetadata, PurchaseRequest
from tests.conftest import unit

pytestmark = unit


def test_enum_values_match_database_constraints():
    # These must stay in sync with oltp/migrations CHECK constraints.
    assert set(ClientSegment.ALL) == {"basic", "standard", "premium"}
    assert set(PurchaseChannel.ALL) == {"credit", "debit"}
    assert set(CardProduct.ALL) == {"basic", "gold", "platinum"}
    assert CardStatus.AUTHORIZABLE == ("active",)


def test_client_model_valid():
    c = Client(client_id=uuid.uuid4(), name="Ada", income=5000, age=30, segment="premium")
    assert c.segment == "premium"


def test_client_rejects_invalid_segment():
    with pytest.raises(ValidationError):
        Client(client_id=uuid.uuid4(), name="Ada", income=5000, age=30, segment="vip")


def test_card_authorizable_property():
    card = Card(card_id=uuid.uuid4(), client_id=uuid.uuid4(), status="active")
    assert card.authorizable is True
    locked = Card(card_id=uuid.uuid4(), client_id=uuid.uuid4(), status="locked")
    assert locked.authorizable is False


def test_purchase_request_channel_validation():
    ok = PurchaseRequest(amount=10, merchant="ACME", channel="debit")
    assert ok.channel == "debit"
    with pytest.raises(ValidationError):
        PurchaseRequest(amount=10, merchant="ACME", channel="pix")


def test_purchase_request_positive_amount():
    with pytest.raises(ValidationError):
        PurchaseRequest(amount=-1, merchant="ACME", channel="credit")


def test_decision_and_metadata_models():
    d = AuthorizationDecision(approved=False, decline_reason=DeclineReason.CARD_NOT_FOUND)
    assert d.approved is False
    m = EventMetadata(trace_id="t1", source_service="authorization")
    assert m.schema_version == 1
