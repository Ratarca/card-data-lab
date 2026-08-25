"""Event catalog — one pydantic model per event_type (README → Event catalog)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from services.shared.events import BaseEvent, EventHeader


class EventType(str, Enum):
    CUSTOMER_ONBOARDED = "customer.onboarded"
    ELIGIBILITY_EVALUATED = "eligibility.evaluated"
    LIMIT_ASSIGNED = "limit.assigned"
    CARD_ISSUED = "card.issued"
    CARD_ACTIVATED = "card.activated"
    PURCHASE_AUTHORIZED = "purchase.authorized"
    PURCHASE_DECLINED = "purchase.declined"
    INVOICE_CLOSED = "invoice.closed"
    PAYMENT_RECEIVED = "payment.received"
    BENEFIT_GRANTED = "benefit.granted"


# ---------- payloads ----------


class CustomerOnboardedPayload(BaseModel):
    income: float = Field(gt=0)
    age: int = Field(ge=18, le=120)
    segment: str


class EligibilityEvaluatedPayload(BaseModel):
    policy_version: str
    approved: bool
    reason: str | None = None


class LimitAssignedPayload(BaseModel):
    limit_amount: float = Field(ge=0)
    model_version: str


class CardIssuedPayload(BaseModel):
    product: str


class CardActivatedPayload(BaseModel):
    pass  # no extra fields


class PurchasePayload(BaseModel):
    amount: float = Field(gt=0)
    merchant: str
    channel: str  # credit | debit


class PurchaseDeclinedPayload(PurchasePayload):
    decline_reason: str


class InvoiceClosedPayload(BaseModel):
    total: float = Field(ge=0)
    due_date: str


class PaymentReceivedPayload(BaseModel):
    invoice_id: str
    amount: float = Field(gt=0)
    paid_at: str


class BenefitGrantedPayload(BaseModel):
    program: str
    points: int = Field(ge=0)


# ---------- events (envelope + typed payload) ----------


def _make(event_type: EventType, aggregate_id: str, payload: "BaseModel | dict", source: str) -> BaseEvent:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump()
    return BaseEvent(
        event_type=event_type.value,
        aggregate_id=aggregate_id,
        header=EventHeader(source_service=source),
        payload=payload,
    )


def customer_onboarded(client_id: str, p: CustomerOnboardedPayload) -> BaseEvent:
    return _make(EventType.CUSTOMER_ONBOARDED, client_id, p, "onboarding")


def eligibility_evaluated(client_id: str, p: EligibilityEvaluatedPayload) -> BaseEvent:
    return _make(EventType.ELIGIBILITY_EVALUATED, client_id, p, "eligibility")


def limit_assigned(client_id: str, p: LimitAssignedPayload) -> BaseEvent:
    return _make(EventType.LIMIT_ASSIGNED, client_id, p, "limits")


def card_issued(card_id: str, client_id: str, p: CardIssuedPayload) -> BaseEvent:
    return _make(EventType.CARD_ISSUED, card_id, p, "card")


def card_activated(card_id: str) -> BaseEvent:
    return _make(EventType.CARD_ACTIVATED, card_id, CardActivatedPayload(), "card")


def purchase_authorized(card_id: str, p: PurchasePayload) -> BaseEvent:
    return _make(EventType.PURCHASE_AUTHORIZED, card_id, p, "authorization")


def purchase_declined(card_id: str, p: PurchaseDeclinedPayload) -> BaseEvent:
    return _make(EventType.PURCHASE_DECLINED, card_id, p, "authorization")


def invoice_closed(client_id: str, p: InvoiceClosedPayload) -> BaseEvent:
    return _make(EventType.INVOICE_CLOSED, client_id, p, "invoices")


def payment_received(invoice_id: str, client_id: str, p: PaymentReceivedPayload) -> BaseEvent:
    return _make(EventType.PAYMENT_RECEIVED, invoice_id, p, "payments")


def benefit_granted(client_id: str, p: BenefitGrantedPayload) -> BaseEvent:
    return _make(EventType.BENEFIT_GRANTED, client_id, p, "benefits")


CATALOG: dict[str, type[BaseModel]] = {
    EventType.CUSTOMER_ONBOARDED.value: CustomerOnboardedPayload,
    EventType.ELIGIBILITY_EVALUATED.value: EligibilityEvaluatedPayload,
    EventType.LIMIT_ASSIGNED.value: LimitAssignedPayload,
    EventType.CARD_ISSUED.value: CardIssuedPayload,
    EventType.CARD_ACTIVATED.value: CardActivatedPayload,
    EventType.PURCHASE_AUTHORIZED.value: PurchasePayload,
    EventType.PURCHASE_DECLINED.value: PurchaseDeclinedPayload,
    EventType.INVOICE_CLOSED.value: InvoiceClosedPayload,
    EventType.PAYMENT_RECEIVED.value: PaymentReceivedPayload,
    EventType.BENEFIT_GRANTED.value: BenefitGrantedPayload,
}
