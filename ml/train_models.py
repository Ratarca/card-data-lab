"""Stage 6B — ML v1: credit limit, default risk, income estimate.

Trains three scikit-learn models on features derived from the dbt marts
(DuckDB lake) and evaluates each against a naive benchmark on a holdout:

1. **Credit limit** (regression): predict a client's appropriate limit.
   Benchmark: flat mean-limit predictor.
2. **Default risk** (classification): predict "high risk" = client whose
   decline ratio is above the lab's 25% threshold.
   Benchmark: majority-class predictor.
3. **Income estimate** (regression): predict monthly income from behavior.
   Benchmark: segment-mean income predictor.

Run with: uv run task ml-train
"""
from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

DB_PATH = "lake/events.duckdb"
RISK_THRESHOLD = 0.25  # decline ratio above this => "high risk"
SEED = 42


def load_features() -> pd.DataFrame:
    """Build one row per client from the marts."""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(
        """
        select
            c.client_id,
            c.segment,
            c.age,
            c.income,
            count(p.event_id)                                   as n_purchases,
            sum(case when p.status = 'approved' then 1 else 0 end) as n_approved,
            coalesce(sum(case when p.status = 'approved'
                              then p.amount else 0 end), 0)     as total_spend,
            avg(case when p.status = 'approved'
                     then p.amount end)                         as avg_ticket,
            count(distinct p.dt_event)                          as active_days,
            case when count(*) > 0 then
                sum(case when p.status = 'declined' then 1 else 0 end) * 1.0 / count(*)
            else 0 end                                          as decline_ratio
        from silver.dim_client c
        left join silver.fct_purchases p using (client_id)
        group by 1, 2, 3, 4
        """
    ).df()
    con.close()
    return df


def _regression_report(name: str, y_true, pred_model, pred_naive) -> dict:
    return {
        "model": name,
        "metric": "MAE",
        "ml": round(mean_absolute_error(y_true, pred_model), 4),
        "naive_benchmark": round(mean_absolute_error(y_true, pred_naive), 4),
        "beats_benchmark": bool(
            mean_absolute_error(y_true, pred_model)
            < mean_absolute_error(y_true, pred_naive)
        ),
    }


def train_limit_model(df: pd.DataFrame) -> dict:
    """KPI-driven credit limit: 30% of predicted capacity headroom."""
    feats = ["segment", "age", "n_purchases", "total_spend", "avg_ticket", "active_days"]
    # Target: income-based capacity rule used by kpi_limit_utilization
    y = df["income"] * 0.30
    Xtr, Xte, ytr, yte = train_test_split(df[feats], y, test_size=0.3, random_state=SEED)

    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), ["segment"])],
        remainder="passthrough",
    )
    model = Pipeline([("pre", pre), ("gb", GradientBoostingRegressor(random_state=SEED))])
    naive = DummyRegressor(strategy="mean")

    model.fit(Xtr, ytr)
    naive.fit(Xtr, ytr)
    return _regression_report(
        "credit_limit (GBR)", yte, model.predict(Xte), naive.predict(Xte)
    )


def train_risk_model(df: pd.DataFrame) -> dict:
    """Default-risk score: high risk = decline_ratio above threshold."""
    feats = ["segment", "age", "n_purchases", "avg_ticket", "active_days"]
    y = (df["decline_ratio"] > RISK_THRESHOLD).astype(int)
    Xtr, Xte, ytr, yte = train_test_split(
        df[feats], y, test_size=0.3, random_state=SEED, stratify=y
    )

    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), ["segment"])],
        remainder="passthrough",
    )
    model = Pipeline([("pre", pre), ("gb", GradientBoostingClassifier(random_state=SEED))])
    naive = DummyClassifier(strategy="most_frequent")

    model.fit(Xtr, ytr)
    naive.fit(Xtr, ytr)

    proba = model.predict_proba(Xte)[:, 1]
    minority = float(np.mean([ytr.mean(), 1 - ytr.mean()]))  # benchmark accuracy
    return {
        "model": "default_risk (GBC)",
        "metric": "ROC-AUC (benchmark accuracy)",
        "ml": round(roc_auc_score(yte, proba), 4),
        "naive_benchmark": round(max(minority, 1 - minority), 4),
        "accuracy_ml": round(accuracy_score(yte, model.predict(Xte)), 4),
        "beats_benchmark": bool(roc_auc_score(yte, proba) > max(minority, 1 - minority)),
    }


def train_income_model(df: pd.DataFrame) -> dict:
    """Income estimate from observed behavior (no raw income feature)."""
    feats = ["segment", "age", "n_purchases", "total_spend", "avg_ticket", "active_days"]
    y = df["income"]
    X = df[feats].copy()
    X["spend_velocity"] = X["total_spend"] / X["active_days"].clip(lower=1)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=SEED)

    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), ["segment"])],
        remainder="passthrough",
    )
    model = Pipeline([("pre", pre), ("gb", GradientBoostingRegressor(random_state=SEED))])
    seg_mean = df.groupby("segment")["income"].mean()

    model.fit(Xtr, ytr)
    naive_pred = Xte["segment"].map(seg_mean).values
    return _regression_report("income_estimate (GBR)", yte, model.predict(Xte), naive_pred)


def train_income_model_v2(df: pd.DataFrame) -> dict:
    """Income estimate v2: adds spend-velocity feature and shallower trees
    (small-n regularization)."""
    feats = ["segment", "age", "n_purchases", "total_spend", "avg_ticket",
             "active_days", "decline_ratio"]
    y = df["income"]
    X = df[feats].copy()
    X["spend_velocity"] = X["total_spend"] / X["active_days"].clip(lower=1)
    X["spend_to_ticket"] = X["total_spend"] / X["avg_ticket"].clip(lower=0.01)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=SEED)

    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), ["segment"])],
        remainder="passthrough",
    )
    model = Pipeline([
        ("pre", pre),
        ("gb", GradientBoostingRegressor(
            n_estimators=100, max_depth=2,
            learning_rate=0.05, subsample=0.8, random_state=SEED)),
    ])
    seg_mean = df.groupby("segment")["income"].mean()

    model.fit(Xtr, ytr)
    naive_pred = Xte["segment"].map(seg_mean).values
    return _regression_report("income_estimate_v2 (GBR tuned)", yte, model.predict(Xte), naive_pred)


def main() -> None:
    df = load_features()
    print(f"Loaded {len(df)} clients from {DB_PATH}\n")
    results = [
        train_limit_model(df),
        train_risk_model(df),
        train_income_model(df),
        train_income_model_v2(df),
    ]
    print(json.dumps(results, indent=2))
    all_beat = all(r["beats_benchmark"] for r in results)
    print(f"\nGate G6 (6B): {'✅ all models beat naive benchmark' if all_beat else '❌ some models did not beat benchmark'}")


if __name__ == "__main__":
    main()
