"""Base domain models shared across services, simulator and tests."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from core.enums import ChannelLiteral, SegmentLiteral


class Client(BaseModel):
    """Aggregate root for the client context."""

    client_id: UUID
    name: str = Field(min_length=1)
    income: float = Field(gt=0)
    age: int = Field(ge=18, le=120)
    segment: SegmentLiteral


class Card(BaseModel):
    """Card aggregate — status drives authorization."""

    card_id: UUID
    client_id: UUID
    product: str = "basic"
    status: str = "issued"

    @property
    def authorizable(self) -> bool:
        return self.status == "active"


class PurchaseRequest(BaseModel):
    """Value object entering the authorization flow."""

    amount: float = Field(gt=0)
    merchant: str = Field(min_length=1)
    channel: ChannelLiteral


class AuthorizationDecision(BaseModel):
    """Result of the authorization flow."""

    approved: bool
    decline_reason: str | None = None
    authorization_id: int | None = None


class EventMetadata(BaseModel):
    """Envelope metadata (traceability)."""

    trace_id: str
    source_service: str
    schema_version: int = 1
    emitted_at: datetime | None = None
