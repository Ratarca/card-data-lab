"""Synthetic journey generator (Stage 2B).

Creates N clients with properties, onboards them through the OLTP layer,
issues/activates cards and replays purchases over simulated months.
Fraud/default rates are parameterized so downstream models have signal.

Run: uv run task simulate
"""
from __future__ import annotations

import json
import random
import uuid
from argparse import ArgumentParser
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone

from oltp.run_migrations import get_connection
from services.shared.catalog import (
    CustomerOnboardedPayload,
    PurchasePayload,
    customer_onboarded,
    purchase_authorized,
)
from services.shared.outbox import persist_event

SEGMENTS = ["basic", "standard", "premium"]
MERCHANTS = ["ACME Market", "Globex Electronics", "Initech Cafe", "Umbrella Pharmacy", "Stark Apparel"]


def _rand_client(rng: random.Random) -> dict:
    segment = rng.choices(SEGMENTS, weights=[0.4, 0.4, 0.2])[0]
    income = {"basic": rng.uniform(1500, 3500), "standard": rng.uniform(3000, 8000), "premium": rng.uniform(7000, 25000)}[segment]
    return {
        "client_id": str(uuid.uuid4()),
        "name": f"Client-{rng.randint(10000, 99999)}",
        "income": round(income, 2),
        "age": rng.randint(21, 70),
        "segment": segment,
    }


def _insert_client(conn, client: dict, created_at: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO client.clients (client_id, name, income, age, segment, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                client["client_id"],
                client["name"],
                client["income"],
                client["age"],
                client["segment"],
                created_at,
            ),
        )


def _issue_card(conn, client_id: str, rng: random.Random, issued_at: datetime) -> str:
    card_id = str(uuid.uuid4())
    product = rng.choice(["basic", "gold", "platinum"])
    with conn.cursor() as cur:
        # 'active' so purchases authorize; issued→activated flow is a later stage refinement
        cur.execute(
            """
            INSERT INTO card.cards (card_id, client_id, product, status, issued_at)
            VALUES (%s,%s,%s,'active',%s)
            """,
            (card_id, client_id, product, issued_at),
        )
    return card_id


def _shift_months(day: date, months: int) -> date:
    """Shift a date by calendar months while keeping a valid day-of-month."""
    month_index = day.year * 12 + day.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def _simulation_window(
    months: int, start_date: date | None, end_date: date | None
) -> tuple[date, date]:
    if months < 1:
        raise ValueError("months must be at least 1")

    end_date = end_date or datetime.now(timezone.utc).date()
    start_date = start_date or _shift_months(end_date, -months)
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    return start_date, end_date


def _timestamp_for(day: date, rng: random.Random) -> datetime:
    return datetime.combine(
        day,
        time(hour=rng.randrange(6, 23), minute=rng.randrange(60), second=rng.randrange(60)),
        tzinfo=timezone.utc,
    )


def _set_event_time(event, event_at: datetime):
    """Apply a simulated timestamp to the immutable business-event contract."""
    event.ts_event = event_at
    event.dt_event = event_at.date()
    return event


def _month_windows(start_date: date, end_date: date) -> list[tuple[date, date]]:
    """Return clipped calendar-month windows covering the requested history."""
    windows: list[tuple[date, date]] = []
    cursor = date(start_date.year, start_date.month, 1)
    while cursor <= end_date:
        last_day = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        windows.append((max(start_date, cursor), min(end_date, last_day)))
        cursor = _shift_months(cursor, 1)
    return windows


def simulate(
    n_clients: int = 100,
    months: int = 1,
    fraud_rate: float = 0.02,
    decline_rate: float = 0.10,
    seed: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Generate historical customer journeys across a configurable date range."""
    rng = random.Random(seed)
    start_date, end_date = _simulation_window(months, start_date, end_date)
    month_windows = _month_windows(start_date, end_date)
    conn = get_connection()
    stats = {
        "clients": 0,
        "cards": 0,
        "purchases": 0,
        "declines": 0,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": (end_date - start_date).days + 1,
    }
    try:
        for _ in range(n_clients):
            client = _rand_client(rng)
            onboarding_day = start_date + timedelta(
                days=rng.randrange(min(14, (end_date - start_date).days) + 1)
            )
            onboarding_at = _timestamp_for(onboarding_day, rng)
            _insert_client(conn, client, onboarding_at)
            stats["clients"] += 1

            # onboarded event
            ev = _set_event_time(
                customer_onboarded(
                    client_id=client["client_id"],
                    p=CustomerOnboardedPayload(
                        income=client["income"], age=client["age"], segment=client["segment"]
                    ),
                ),
                onboarding_at,
            )
            with conn.cursor() as cur:
                persist_event(cur, ev)

            card_id = _issue_card(conn, client["client_id"], rng, onboarding_at)
            stats["cards"] += 1

            # Purchases are distributed across calendar months after onboarding.
            for window_start, window_end in month_windows:
                eligible_start = max(window_start, onboarding_day)
                if eligible_start > window_end:
                    continue
                n_purchases = rng.randint(3, 12)
                for _ in range(n_purchases):
                    event_day = eligible_start + timedelta(
                        days=rng.randrange((window_end - eligible_start).days + 1)
                    )
                    event_at = _timestamp_for(event_day, rng)
                    payload = PurchasePayload(
                        amount=round(rng.uniform(5, 500), 2),
                        merchant=rng.choice(MERCHANTS),
                        channel=rng.choices(["credit", "debit"], weights=[0.7, 0.3])[0],
                    )
                    if rng.random() < fraud_rate:
                        payload.amount = round(payload.amount * rng.uniform(8, 20), 2)  # outlier spike

                    with conn.cursor() as cur:
                        if rng.random() < decline_rate:
                            from services.shared.catalog import purchase_declined

                            ev = _set_event_time(
                                purchase_declined(
                                    client["client_id"],
                                    {
                                        "amount": payload.amount,
                                        "merchant": payload.merchant,
                                        "channel": payload.channel,
                                        "decline_reason": "limit_exceeded",
                                        "card_id": card_id,
                                    },
                                ),
                                event_at,
                            )
                            stats["declines"] += 1
                        else:
                            cur.execute(
                                """
                                INSERT INTO purchase.authorizations
                                    (card_id, amount, merchant, channel, approved, authorized_at)
                                VALUES (%s,%s,%s,%s,true,%s)
                                RETURNING authorization_id
                                """,
                                (card_id, payload.amount, payload.merchant, payload.channel, event_at),
                            )
                            auth_id = cur.fetchone()[0]
                            cur.execute(
                                """
                                INSERT INTO purchase.purchases
                                    (authorization_id, card_id, amount, purchased_at)
                                VALUES (%s,%s,%s,%s)
                                """,
                                (auth_id, card_id, payload.amount, event_at),
                            )
                            ev = _set_event_time(
                                purchase_authorized(
                                    client["client_id"],
                                    {**payload.model_dump(), "card_id": card_id},
                                ),
                                event_at,
                            )
                            stats["purchases"] += 1
                        persist_event(cur, ev)
        conn.commit()
        return stats
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = ArgumentParser(description="Generate synthetic credit-card customer journeys.")
    parser.add_argument("--n-clients", type=int, default=100)
    parser.add_argument("--months", type=int, default=1)
    parser.add_argument("--fraud-rate", type=float, default=0.02)
    parser.add_argument("--decline-rate", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    args = parser.parse_args()
    summary = simulate(
        n_clients=args.n_clients,
        months=args.months,
        fraud_rate=args.fraud_rate,
        decline_rate=args.decline_rate,
        seed=args.seed,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(json.dumps(summary, indent=2))
