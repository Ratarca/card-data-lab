-- 001_initial_schema.sql
-- OLTP schema: one schema per bounded context + shared event_outbox.
-- All statements are idempotent (IF NOT EXISTS) so the runner can be re-run safely.

CREATE SCHEMA IF NOT EXISTS client;
CREATE SCHEMA IF NOT EXISTS eligibility;
CREATE SCHEMA IF NOT EXISTS limits;
CREATE SCHEMA IF NOT EXISTS card;
CREATE SCHEMA IF NOT EXISTS purchase;
CREATE SCHEMA IF NOT EXISTS billing;
CREATE SCHEMA IF NOT EXISTS benefits;

-- ---------- Client ----------
CREATE TABLE IF NOT EXISTS client.clients (
    client_id   UUID PRIMARY KEY,
    name        TEXT NOT NULL,
    income      NUMERIC(12, 2) NOT NULL CHECK (income > 0),
    age         INT NOT NULL CHECK (age BETWEEN 18 AND 120),
    segment     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Eligibility ----------
CREATE TABLE IF NOT EXISTS eligibility.policies (
    policy_version TEXT PRIMARY KEY,
    rules          JSONB NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS eligibility.decisions (
    decision_id    BIGSERIAL PRIMARY KEY,
    client_id      UUID NOT NULL REFERENCES client.clients(client_id),
    policy_version TEXT NOT NULL REFERENCES eligibility.policies(policy_version),
    approved       BOOLEAN NOT NULL,
    reason         TEXT,
    decided_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Limits ----------
CREATE TABLE IF NOT EXISTS limits.credit_limits (
    limit_id      BIGSERIAL PRIMARY KEY,
    client_id     UUID NOT NULL REFERENCES client.clients(client_id),
    limit_amount  NUMERIC(12, 2) NOT NULL CHECK (limit_amount >= 0),
    model_version TEXT NOT NULL,
    assigned_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Card ----------
CREATE TABLE IF NOT EXISTS card.cards (
    card_id     UUID PRIMARY KEY,
    client_id   UUID NOT NULL REFERENCES client.clients(client_id),
    product     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'issued'
                CHECK (status IN ('issued', 'active', 'locked', 'cancelled')),
    issued_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Purchase / Authorization ----------
CREATE TABLE IF NOT EXISTS purchase.authorizations (
    authorization_id BIGSERIAL PRIMARY KEY,
    card_id          UUID NOT NULL REFERENCES card.cards(card_id),
    amount           NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    merchant         TEXT NOT NULL,
    channel          TEXT NOT NULL CHECK (channel IN ('credit', 'debit')),
    approved         BOOLEAN NOT NULL,
    decline_reason   TEXT,
    authorized_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS purchase.purchases (
    purchase_id      BIGSERIAL PRIMARY KEY,
    authorization_id BIGINT NOT NULL UNIQUE REFERENCES purchase.authorizations(authorization_id),
    card_id          UUID NOT NULL REFERENCES card.cards(card_id),
    amount           NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    purchased_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Billing ----------
CREATE TABLE IF NOT EXISTS billing.invoices (
    invoice_id  BIGSERIAL PRIMARY KEY,
    client_id   UUID NOT NULL REFERENCES client.clients(client_id),
    total       NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
    due_date    DATE NOT NULL,
    closed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS billing.payments (
    payment_id  BIGSERIAL PRIMARY KEY,
    invoice_id  BIGINT NOT NULL REFERENCES billing.invoices(invoice_id),
    amount      NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    paid_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Benefits ----------
CREATE TABLE IF NOT EXISTS benefits.benefits (
    benefit_id  BIGSERIAL PRIMARY KEY,
    client_id   UUID NOT NULL REFERENCES client.clients(client_id),
    program     TEXT NOT NULL,
    points      INT NOT NULL CHECK (points >= 0),
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Shared outbox (event-driven integration) ----------
CREATE TABLE IF NOT EXISTS event_outbox (
    event_id       UUID PRIMARY KEY,
    event_type     TEXT NOT NULL,
    ts_event       TIMESTAMPTZ NOT NULL,
    dt_event       DATE NOT NULL,
    aggregate_id   UUID NOT NULL,
    schema_version INT NOT NULL DEFAULT 1,
    header         JSONB NOT NULL,
    payload        JSONB NOT NULL,
    published_at   TIMESTAMPTZ           -- NULL = not yet exported to DuckDB lake
);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON event_outbox (dt_event) WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_outbox_aggregate
    ON event_outbox (aggregate_id, ts_event);
