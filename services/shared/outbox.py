"""Shared kernel: transactional outbox writer + in-process event bus."""
from __future__ import annotations

import json
import uuid
from typing import Callable

import psycopg2
import psycopg2.extras

from services.shared.events import BaseEvent

# Register UUID adapters once so uuid.UUID values bind to UUID columns.
psycopg2.extras.register_uuid()


def persist_event(cur, event: BaseEvent) -> None:
    """Write an event to event_outbox using an existing cursor/transaction.

    The caller owns the transaction: business rows + this insert commit together.
    """
    cur.execute(
        """
        INSERT INTO event_outbox
            (event_id, event_type, ts_event, dt_event, aggregate_id,
             schema_version, header, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid.UUID(event.event_id),
            event.event_type,
            event.ts_event,
            event.dt_event,
            uuid.UUID(event.aggregate_id),
            event.header.schema_version,
            json.dumps(event.header.model_dump()),
            json.dumps(event.payload),
        ),
    )


class EventBus:
    """Minimal in-process pub/sub. Handlers run synchronously after publish.

    In the modular monolith the bus replaces a message broker; the outbox row
    is the durable record that the lake worker consumes (Stage 3).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[BaseEvent], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[BaseEvent], None]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: BaseEvent) -> None:
        for handler in self._handlers.get(event.event_type, []):
            handler(event)


bus = EventBus()
