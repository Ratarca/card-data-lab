"""Protocol conformance tests — implementations satisfy their ports (unit, no DB)."""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from core.models import Card, Client, PurchaseRequest
from core.protocols import (
    CardRepository,
    ClientRepository,
    EventPublisher,
    PurchaseAuthorizer,
)
from tests.conftest import unit

pytestmark = unit


class InMemoryClientRepository:
    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def get(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def add(self, client: Client) -> None:
        self._store[str(client.client_id)] = client


class InMemoryCardRepository:
    def __init__(self, cards: list[Card]) -> None:
        self._cards = {str(c.card_id): c for c in cards}

    def get(self, card_id: str) -> Card | None:
        return self._cards.get(card_id)

    def set_status(self, card_id: str, status: str) -> bool:
        if card_id in self._cards:
            self._cards[card_id].status = status
            return True
        return False


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    def publish(self, event_type: str, aggregate_id: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, aggregate_id, payload))


class AlwaysApproveAuthorizer:
    def authorize(self, card_id: str, request: PurchaseRequest) -> dict[str, Any]:
        return {"approved": True, "authorization_id": 1}


def test_in_memory_repositories_satisfy_protocols():
    assert issubclass(InMemoryClientRepository, ClientRepository)
    assert issubclass(InMemoryCardRepository, CardRepository)
    assert issubclass(RecordingPublisher, EventPublisher)
    assert issubclass(AlwaysApproveAuthorizer, PurchaseAuthorizer)


def test_client_repository_roundtrip():
    repo = InMemoryClientRepository()
    client = Client(client_id=uuid.uuid4(), name="Ada", income=100, age=30, segment="basic")
    repo.add(client)
    assert repo.get(str(client.client_id)) == client
    assert repo.get("missing") is None


def test_card_repository_set_status():
    card = Card(card_id=uuid.uuid4(), client_id=uuid.uuid4(), status="issued")
    repo = InMemoryCardRepository([card])
    assert repo.set_status(str(card.card_id), "active") is True
    assert repo.get(str(card.card_id)).status == "active"
    assert repo.set_status("missing", "active") is False


def test_publisher_records_events():
    pub = RecordingPublisher()
    pub.publish("purchase.authorized", "agg-1", {"amount": 10})
    pub.publish("purchase.declined", "agg-2", {"amount": 5})
    assert len(pub.events) == 2
    assert pub.events[0][0] == "purchase.authorized"


def test_authorizer_port_contract():
    auth = AlwaysApproveAuthorizer()
    result = auth.authorize("card-1", PurchaseRequest(amount=1, merchant="M", channel="credit"))
    assert result["approved"] is True


def test_non_conforming_class_fails_runtime_check():
    class Broken:
        pass  # missing all protocol methods

    assert not issubclass(Broken, ClientRepository)
