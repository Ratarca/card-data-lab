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
from datetime import datetime, timedelta, timezone

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


def _insert_client(conn, client: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO client.clients (client_id, name, income, age, segment) VALUES (%s,%s,%s,%s,%s)",
            (client["client_id"], client["name"], client["income"], client["age"], client["segment"]),
        )


def _issue_card(conn, client_id: str, rng: random.Random) -> str:
    card_id = str(uuid.uuid4())
    product = rng.choice(["basic", "gold", "platinum"])
    with conn.cursor() as cur:
        # 'active' so purchases authorize; issued→activated flow is a later stage refinement
        cur.execute(
            "INSERT INTO card.cards (card_id, client_id, product, status) VALUES (%s,%s,%s,'active')",
            (card_id, client_id, product),
        )
    return card_id


def simulate(
    n_clients: int = 100,
    months: int = 1,
    fraud_rate: float = 0.02,
    decline_rate: float = 0.10,
    seed: int | None = None,
) -> dict:
    """Generate journeys. Returns summary counts."""
    rng = random.Random(seed)
    conn = get_connection()
    stats = {"clients": 0, "cards": 0, "purchases": 0, "declines": 0}
    try:
        for _ in range(n_clients):
            client = _rand_client(rng)
            _insert_client(conn, client)
            stats["clients"] += 1

            # onboarded event
            ev = customer_onboarded(
                client_id=client["client_id"],
                p=CustomerOnboardedPayload(income=client["income"], age=client["age"], segment=client["segment"]),
            )
            with conn.cursor() as cur:
                persist_event(cur, ev)

            card_id = _issue_card(conn, client["client_id"], rng)
            stats["cards"] += 1

            # purchases over simulated months
            now = datetime.now(timezone.utc)
            for month in range(months):
                n_purchases = rng.randint(3, 12)
                for _ in range(n_purchases):
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

                            ev = purchase_declined(
                                client["client_id"],
                                {"amount": payload.amount, "merchant": payload.merchant, "channel": payload.channel, "decline_reason": "limit_exceeded", "card_id": card_id},
                            )
                            stats["declines"] += 1
                        else:
                            cur.execute(
                                "INSERT INTO purchase.authorizations (card_id, amount, merchant, channel, approved) "
                                "VALUES (%s,%s,%s,%s,true) RETURNING authorization_id",
                                (card_id, payload.amount, payload.merchant, payload.channel),
                            )
                            auth_id = cur.fetchone()[0]
                            cur.execute(
                                "INSERT INTO purchase.purchases (authorization_id, card_id, amount) VALUES (%s,%s,%s)",
                                (auth_id, card_id, payload.amount),
                            )
                            ev = purchase_authorized(client["client_id"], {**payload.model_dump(), "card_id": card_id})
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
    summary = simulate(n_clients=100, months=1, seed=42)
    print(json.dumps(summary, indent=2))
