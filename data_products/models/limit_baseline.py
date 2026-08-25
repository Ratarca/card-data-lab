"""ML v1 baseline: credit limit assignment / risk score (Stage 6B).

Features derived from warehouse facts via DuckDB; target synthesized from
client segment/income signal embedded by the simulator. Evaluates against a
naive benchmark (predict the mean) on a holdout split.

Run: uv run task ml-baseline
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

LAKE_PATH = Path("lake/events.duckdb")


def load_features() -> pd.DataFrame:
    con = duckdb.connect(str(LAKE_PATH), read_only=True)
    try:
        return con.execute(
            """
            select
                c.client_id,
                c.income,
                c.age,
                case c.segment when 'basic' then 0 when 'standard' then 1 else 2 end as segment_ord,
                coalesce(s.tx_count, 0)   as tx_count,
                coalesce(s.avg_ticket, 0) as avg_ticket,
                coalesce(s.spend_velocity, 0) as spend_velocity,
                coalesce(s.payment_ratio, 1.0)::float as payment_ratio,
                -- proxy target: "safe limit" = income share modulated by behavior.
                -- In later stages this becomes observed default outcomes.
                (c.income * 0.30
                 * (1 + coalesce(s.payment_ratio, 1.0) - 1)
                 * least(coalesce(s.avg_ticket, 0) / nullif(c.income * 0.05, 0), 2.0)
                )::float as target_limit
            from silver.dim_client c
            left join (
                select
                    client_id,
                    count(*)                                          as tx_count,
                    avg(amount)                                       as avg_ticket,
                    count(*) * 1.0 / greatest(date_diff('day',
                        min(dt_event), max(dt_event) + interval 1 day), 1) as spend_velocity,
                    1.0                                               as payment_ratio
                from silver.fct_purchases
                where status = 'approved'
                group by 1
            ) s using (client_id)
            where c.is_current
            """
        ).df()
    finally:
        con.close()


def evaluate() -> dict:
    df = load_features()
    feature_cols = ["income", "age", "segment_ord", "tx_count", "avg_ticket", "spend_velocity", "payment_ratio"]
    X, y = df[feature_cols], df["target_limit"]

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42)

    naive = DummyRegressor(strategy="mean").fit(X_tr, y_tr)
    model = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_tr, y_tr)

    def scores(est):
        pred = est.predict(X_te)
        return {"mae": round(mean_absolute_error(y_te, pred), 2), "r2": round(r2_score(y_te, pred), 3)}

    naive_s, model_s = scores(naive), scores(model)
    beats_naive = model_s["mae"] < naive_s["mae"]

    return {
        "n_clients": len(df),
        "features": feature_cols,
        "naive_baseline": naive_s,
        "random_forest": model_s,
        "beats_naive_benchmark": beats_naive,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
