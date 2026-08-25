"""Protocols (structural interfaces) for repository and publisher behaviors.

Modules depend on these protocols, not on concrete implementations —
enabling fakes in tests and future extraction into separate services.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.models import Card, Client, PurchaseRequest


@runtime_checkable
class ClientRepository(Protocol):
    """Persistence port for the client context."""

    def get(self, client_id: str) -> Client | None: ...

    def add(self, client: Client) -> None: ...


@runtime_checkable
class CardRepository(Protocol):
    """Persistence port for the card context."""

    def get(self, card_id: str) -> Card | None: ...

    def set_status(self, card_id: str, status: str) -> bool: ...


@runtime_checkable
class PurchaseAuthorizer(Protocol):
    """Behavior port: decide whether a purchase is approved."""

    def authorize(self, card_id: str, request: PurchaseRequest) -> dict[str, Any]: ...


@runtime_checkable
class EventPublisher(Protocol):
    """Behavior port: publish an event envelope to the outbox/bus."""

    def publish(self, event_type: str, aggregate_id: str, payload: dict[str, Any]) -> None: ...


@runtime_checkable
class OutboxWriter(Protocol):
    """Low-level port used by publishers that write inside a DB transaction."""

    def write(self, cur: Any, event: dict[str, Any]) -> None: ...
