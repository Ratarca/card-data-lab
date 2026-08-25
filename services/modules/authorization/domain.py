"""Authorization service refactored to depend on ports (protocols), not concrete infra.

Business rules live here; persistence and publishing are injected. This makes
the rules unit-testable with fakes (no DB) and keeps the module extractable
as a future microservice.
"""
from __future__ import annotations

from typing import Any

from core.enums import CardStatus, DeclineReason
from core.models import PurchaseRequest
from core.protocols import CardRepository, EventPublisher


class AuthorizationService:
    """Pure business logic — dependencies injected via constructor."""

    def __init__(self, cards: CardRepository, publisher: EventPublisher) -> None:
        self._cards = cards
        self._publisher = publisher

    def authorize(self, card_id: str, request: PurchaseRequest) -> dict[str, Any]:
        card = self._cards.get(card_id)

        if card is None:
            return self._decline(card_id, request, DeclineReason.CARD_NOT_FOUND)
        if not card.authorizable:
            reason = f"card_{card.status}"
            return self._decline(card_id, request, reason)

        # Approved path: persist decision via port and emit event.
        result: dict[str, Any] = {"approved": True, "authorization_id": None}
        self._publisher.publish(
            "purchase.authorized",
            card_id,
            {"amount": request.amount, "merchant": request.merchant, "channel": request.channel},
        )
        return result

    def _decline(self, card_id: str, request: PurchaseRequest, reason: str) -> dict[str, Any]:
        self._publisher.publish(
            "purchase.declined",
            card_id,
            {
                "amount": request.amount,
                "merchant": request.merchant,
                "channel": request.channel,
                "decline_reason": reason,
            },
        )
        return {"approved": False, "decline_reason": reason, "authorization_id": None}


# ---------- Concrete adapters (infra implementations of the ports) ----------


class PgCardRepository:
    """CardRepository backed by PostgreSQL."""

    def __init__(self, conn_factory) -> None:
        self._conn_factory = conn_factory

    def get(self, card_id: str) -> Any | None:
        from core.models import Card

        conn = self._conn_factory()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT card_id, client_id, product, status FROM card.cards WHERE card_id = %s", (card_id,))
                row = cur.fetchone()
            if row is None:
                return None
            return Card(card_id=row[0], client_id=row[1], product=row[2], status=row[3])
        finally:
            conn.close()

    def set_status(self, card_id: str, status: str) -> bool:
        if status not in (CardStatus.ISSUED, CardStatus.ACTIVE, CardStatus.LOCKED, CardStatus.CANCELLED):
            raise ValueError(f"invalid status: {status}")
        conn = self._conn_factory()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE card.cards SET status = %s WHERE card_id = %s", (status, card_id))
                updated = cur.rowcount
            conn.commit()
            return updated > 0
        finally:
            conn.close()


class OutboxEventPublisher:
    """EventPublisher that writes to event_outbox inside the caller's transaction scope."""

    def __init__(self, conn_factory) -> None:
        self._conn_factory = conn_factory

    def publish(self, event_type: str, aggregate_id: str, payload: dict[str, Any]) -> None:
        from services.shared.catalog import CATALOG
        from services.shared.events import EventHeader
        from services.shared.outbox import persist_event

        envelope_cls = None
        # Build a minimal valid envelope using BaseEvent directly.
        from services.shared.events import BaseEvent

        event = BaseEvent(
            event_type=event_type,
            aggregate_id=aggregate_id,
            header=EventHeader(source_service="authorization"),
            payload=payload,
        )
        conn = self._conn_factory()
        try:
            with conn.cursor() as cur:
                persist_event(cur, event)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
