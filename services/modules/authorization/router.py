"""Authorization module router."""
from __future__ import annotations

from fastapi import APIRouter

from services.modules.authorization.service import AuthorizationResult, authorize_purchase
from services.shared.catalog import PurchasePayload

router = APIRouter(tags=["authorization"])


@router.post("/purchases/authorize", response_model=AuthorizationResult)
def authorize(card_id: str, payload: PurchasePayload) -> AuthorizationResult:
    """Purchase → authorization → persist state + outbox event (one transaction)."""
    return authorize_purchase(card_id, payload)
