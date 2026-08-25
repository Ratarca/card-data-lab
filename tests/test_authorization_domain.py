"""Unit tests for AuthorizationService — pure business logic with fakes (no DB)."""
from __future__ import annotations

import uuid

import pytest

from core.enums import CardStatus, DeclineReason
from core.models import Card, PurchaseRequest
from services.modules.authorization.domain import AuthorizationService
from tests.conftest import unit

pytestmark = unit


class FakeCardRepo:
    def __init__(self, cards: list[Card]) -> None:
        self._cards = {str(c.card_id): c for c in cards}

    def get(self, card_id: str) -> Card | None:
        return self._cards.get(card_id)

    def set_status(self, card_id: str, status: str) -> bool:
        if card_id in self._cards:
            self._cards[card_id].status = status
            return True
        return False


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    def publish(self, event_type: str, aggregate_id: str, payload: dict) -> None:
        self.events.append((event_type, aggregate_id, payload))


@pytest.fixture()
def active_card() -> Card:
    return Card(card_id=uuid.uuid4(), client_id=uuid.uuid4(), status=CardStatus.ACTIVE)


@pytest.fixture()
def service(active_card):
    return AuthorizationService(cards=FakeCardRepo([active_card]), publisher=FakePublisher())


def test_approves_active_card(service, active_card):
    result = service.authorize(str(active_card.card_id), PurchaseRequest(amount=10, merchant="M", channel="credit"))
    assert result["approved"] is True


def test_declines_unknown_card(service):
    result = service.authorize("missing", PurchaseRequest(amount=10, merchant="M", channel="credit"))
    assert result["approved"] is False
    assert result["decline_reason"] == DeclineReason.CARD_NOT_FOUND


def test_declines_locked_card(active_card):
    active_card.status = CardStatus.LOCKED
    svc = AuthorizationService(FakeCardRepo([active_card]), FakePublisher())
    result = svc.authorize(str(active_card.card_id), PurchaseRequest(amount=10, merchant="M", channel="debit"))
    assert result["decline_reason"] == "card_locked"


def test_emits_authorized_event(service, active_card):
    service.authorize(str(active_card.card_id), PurchaseRequest(amount=5, merchant="M", channel="credit"))
    assert service._publisher.events[-1][0] == "purchase.authorized"


def test_emits_declined_event_with_reason(service):
    service.authorize("missing", PurchaseRequest(amount=5, merchant="M", channel="credit"))
    event_type, _, payload = service._publisher.events[-1]
    assert event_type == "purchase.declined"
    assert payload["decline_reason"] == DeclineReason.CARD_NOT_FOUND
