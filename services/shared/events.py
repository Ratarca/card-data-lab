"""Baseline event envelope shared by every event in the platform."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field


class EventHeader(BaseModel):
    """Metadata that comes from the API: traceability and fan-out info."""

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_service: str
    schema_version: int = 1


class BaseEvent(BaseModel):
    """Envelope defined in README → Baseline event envelope."""

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid7())
        if hasattr(uuid, "uuid7")
        else str(uuid.uuid4())
    )
    event_type: str
    ts_event: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dt_event: date = None  # type: ignore[assignment]
    aggregate_id: str  # client_id / card_id / invoice_id
    header: EventHeader
    payload: dict

    def model_post_init(self, __context) -> None:
        if self.dt_event is None:
            self.dt_event = self.ts_event.date()
