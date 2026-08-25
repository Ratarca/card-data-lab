"""Authorization module — decides approve/decline and emits events."""
from __future__ import annotations

from pydantic import BaseModel

from oltp.run_migrations import get_connection
from services.shared.catalog import (
    PurchaseDeclinedPayload,
    PurchasePayload,
    purchase_authorized,
    purchase_declined,
)
from services.shared.outbox import persist_event


class AuthorizationResult(BaseModel):
    approved: bool
    decline_reason: str | None = None
    authorization_id: int | None = None


def authorize_purchase(card_id: str, payload: PurchasePayload) -> AuthorizationResult:
    """Validate purchase against card state and emit the corresponding event.

    Business rules (thin v1):
      - card must exist and be active
      - channel must be credit or debit (enforced by schema too)
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM card.cards WHERE card_id = %s", (card_id,))
            row = cur.fetchone()
            if row is None:
                result = AuthorizationResult(approved=False, decline_reason="card_not_found")
                event = purchase_declined(card_id, PurchaseDeclinedPayload(**payload.model_dump(), decline_reason="card_not_found"))
            elif row[0] != "active":
                result = AuthorizationResult(approved=False, decline_reason=f"card_{row[0]}")
                event = purchase_declined(card_id, PurchaseDeclinedPayload(**payload.model_dump(), decline_reason=f"card_{row[0]}"))
            else:
                cur.execute(
                    "INSERT INTO purchase.authorizations (card_id, amount, merchant, channel, approved) "
                    "VALUES (%s, %s, %s, %s, true) RETURNING authorization_id",
                    (card_id, payload.amount, payload.merchant, payload.channel),
                )
                auth_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO purchase.purchases (authorization_id, card_id, amount) VALUES (%s, %s, %s)",
                    (auth_id, card_id, payload.amount),
                )
                result = AuthorizationResult(approved=True, authorization_id=auth_id)
                event = purchase_authorized(card_id, payload)

            # Transactional outbox: business rows + event commit atomically.
            persist_event(cur, event)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def activate_card(card_id: str) -> bool:
    """Activate an issued card (needed by tests/simulator before purchases)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE card.cards SET status = 'active' WHERE card_id = %s", (card_id,))
            updated = cur.rowcount
        conn.commit()
        return updated > 0
    finally:
        conn.close()
