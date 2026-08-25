"""Domain enums and type aliases — the vocabulary of the platform."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

# ---------- Enums ----------

class ClientSegment:
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"

    ALL = (BASIC, STANDARD, PREMIUM)


class CardProduct:
    BASIC = "basic"
    GOLD = "gold"
    PLATINUM = "platinum"

    ALL = (BASIC, GOLD, PLATINUM)


class CardStatus:
    ISSUED = "issued"
    ACTIVE = "active"
    LOCKED = "locked"
    CANCELLED = "cancelled"

    AUTHORIZABLE = (ACTIVE,)  # only these states allow purchases


class PurchaseChannel:
    CREDIT = "credit"
    DEBIT = "debit"

    ALL = (CREDIT, DEBIT)


class DeclineReason:
    CARD_NOT_FOUND = "card_not_found"
    CARD_NOT_ACTIVE = "card_not_active"
    LIMIT_EXCEEDED = "limit_exceeded"


# ---------- Type aliases ----------

ClientId = str
CardId = str
InvoiceId = str
EventId = str
Money = Decimal  # monetary amounts; DB layer converts to NUMERIC(12,2)

# Literal versions for pydantic validation at API edges
SegmentLiteral = Literal["basic", "standard", "premium"]
ChannelLiteral = Literal["credit", "debit"]
ProductLiteral = Literal["basic", "gold", "platinum"]
StatusLiteral = Literal["issued", "active", "locked", "cancelled"]
