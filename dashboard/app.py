"""Card Data Lab — KPI dashboard (Stage 6A).

Run with:  uv run task dashboard
Reads the dbt marts directly from the DuckDB lake (read-only).
"""
from __future__ import annotations

import os

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

DB_PATH = os.getenv("DASHBOARD_DB_PATH", "lake/events.duckdb")

st.set_page_config(page_title="Card Lab KPIs", page_icon="💳", layout="wide")


REQUIRED_GOLD_TABLES = {
    "kpi_activation_rate",
    "kpi_approval_rate",
    "kpi_delinquency_rate",
    "kpi_limit_utilization",
    "kpi_tpv",
}


@st.cache_data(ttl=60)
def query(sql: str) -> pd.DataFrame:
    """Run one read-only query without sharing a DuckDB connection between reruns."""
    with duckdb.connect(DB_PATH, read_only=True) as con:
        return con.execute(sql).df()


def validate_warehouse() -> None:
    """Stop with an actionable message when dbt has not built the gold layer."""
    try:
        tables = query(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'gold'
            """
        )
    except duckdb.Error as exc:
        st.error(f"Could not open DuckDB lake `{DB_PATH}`: {exc}")
        st.stop()

    missing = REQUIRED_GOLD_TABLES - set(tables["table_name"])
    if missing:
        st.error(
            "The gold dashboard tables are not available in this lake. "
            "Run `uv run task dbt-build` after the lake migration. "
            f"Missing: {', '.join(sorted(missing))}."
        )
        st.stop()


st.title("💳 Card Data Lab — KPI Dashboard")
st.caption("Stage 6A · KPI models built with dbt on the DuckDB lake")
validate_warehouse()

# ---------------------------------------------------------------- sidebar
segments = [None] + query(
    "select distinct segment from gold.kpi_approval_rate order by 1"
)["segment"].tolist()
seg = st.sidebar.selectbox("Client segment", segments, index=0)
seg_filter = f"where segment = '{seg}'" if seg else ""

# Only approval, utilization, and activation KPIs are segmented. TPV is by
# channel and delinquency is by decline reason, so filtering them by segment
# would produce a DuckDB binder error.
kpis = query(f"select * from gold.kpi_approval_rate {seg_filter}")
tpv = query("select * from gold.kpi_tpv")
delinq = query("select * from gold.kpi_delinquency_rate")
util = query(f"select * from gold.kpi_limit_utilization {seg_filter}")
act = query(f"select * from gold.kpi_activation_rate {seg_filter}")

# ---------------------------------------------------------------- headline KPIs
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Approval rate",
    f"{(kpis.approved.sum() / max(kpis.attempts.sum(), 1)):.1%}",
)
c2.metric("TPV", f"R$ {tpv.tpv.sum():,.0f}")
c3.metric(
    "Delinquency proxy",
    f"{(delinq.limit_exceeded_declines.sum() / max(delinq.declines.sum(), 1)):.1%}",
)
c4.metric(
    "Limit utilization",
    f"{(util.used_limit.sum() / max(util.capacity.sum(), 1)):.1%}",
)
c5.metric(
    "Activation rate",
    f"{(act.activated_clients.sum() / max(act.onboarded_clients.sum(), 1)):.1%}",
)

st.divider()

# ---------------------------------------------------------------- overview
st.subheader("Portfolio overview")
left, right = st.columns(2)

with left:
    st.subheader("TPV by channel")
    by_channel = tpv.groupby("channel", as_index=False)["tpv"].sum()
    st.bar_chart(by_channel.set_index("channel")["tpv"], height=280)

with right:
    st.subheader("TPV over time")
    st.bar_chart(tpv.groupby("date_key", as_index=False)["tpv"].sum().set_index("date_key"), height=280)

st.divider()

# ---------------------------------------------------------------- KPI details
st.subheader("KPI detail")
tab1, tab2, tab3 = st.tabs(["Approval rate", "Limit utilization", "Activation cohorts"])

with tab1:
    st.markdown("#### Approval quality and volume")
    daily = (
        kpis.groupby("date_key", as_index=False)[["attempts", "approved"]]
        .sum()
        .assign(approval_rate=lambda d: d.approved / d.attempts)
    )
    daily["approval_rate_7d"] = daily["approval_rate"].rolling(7, min_periods=1).mean()
    approval_base = alt.Chart(daily).encode(
        x=alt.X("date_key:T", title="Date"),
        tooltip=[
            alt.Tooltip("date_key:T", title="Date"),
            alt.Tooltip("attempts:Q", title="Attempts", format=",d"),
            alt.Tooltip("approved:Q", title="Approved", format=",d"),
            alt.Tooltip("approval_rate:Q", title="Daily rate", format=".1%"),
            alt.Tooltip("approval_rate_7d:Q", title="7-day rate", format=".1%"),
        ],
    )
    attempts_bars = approval_base.mark_bar(opacity=0.25, color="#64748b").encode(
        y=alt.Y("attempts:Q", title="Attempts")
    )
    approval_lines = approval_base.mark_line(color="#0f766e", point=True).encode(
        y=alt.Y("approval_rate:Q", title="Approval rate", axis=alt.Axis(format="%"))
    )
    rolling_line = approval_base.mark_line(color="#f59e0b", strokeDash=[6, 4], size=3).encode(
        y="approval_rate_7d:Q"
    )
    st.altair_chart(
        alt.layer(attempts_bars, approval_lines, rolling_line).resolve_scale(y="independent").properties(height=340),
        width="stretch",
    )
    st.caption("Bars show demand; teal is the daily approval rate; amber is the 7-day weighted view.")
    st.dataframe(kpis, width="stretch")

with tab2:
    st.markdown("#### Estimated limit stock versus daily usage")
    limit_daily = (
        util.groupby("date_key", as_index=False)[
            ["capacity", "used_limit", "available_limit", "over_limit_amount"]
        ]
        .sum()
    )
    limit_long = limit_daily.melt(
        id_vars="date_key",
        value_vars=["used_limit", "available_limit", "over_limit_amount"],
        var_name="measure",
        value_name="amount",
    )
    limit_long["measure"] = limit_long["measure"].map(
        {
            "used_limit": "Used limit",
            "available_limit": "Available limit",
            "over_limit_amount": "Over proxy limit",
        }
    )
    limit_chart = (
        alt.Chart(limit_long)
        .mark_bar()
        .encode(
            x=alt.X("date_key:T", title="Date"),
            y=alt.Y("amount:Q", title="Estimated credit capacity (R$)"),
            color=alt.Color(
                "measure:N",
                title="Limit position",
                scale=alt.Scale(
                    domain=["Used limit", "Available limit", "Over proxy limit"],
                    range=["#0f766e", "#cbd5e1", "#dc2626"],
                ),
            ),
            tooltip=[
                alt.Tooltip("date_key:T", title="Date"),
                alt.Tooltip("measure:N", title="Measure"),
                alt.Tooltip("amount:Q", title="Amount", format="R$ ,.0f"),
            ],
        )
        .properties(height=340)
    )
    st.altair_chart(limit_chart, width="stretch")
    st.caption(
        "The stack is the month-to-date balance: used + available equals the estimated "
        "monthly limit stock. Red shows spend beyond the proxy limit."
    )
    st.dataframe(util, width="stretch")

with tab3:
    st.markdown("#### Activation cohort heatmap")
    cohort = act.copy()
    cohort["cohort_month"] = pd.to_datetime(cohort["date_key"]).dt.to_period("M").astype(str)
    cohort = (
        cohort.groupby(["cohort_month", "segment"], as_index=False)[
            ["onboarded_clients", "activated_clients"]
        ]
        .sum()
        .assign(
            activation_rate=lambda d: d.activated_clients
            / d.onboarded_clients.clip(lower=1)
        )
    )
    heatmap = (
        alt.Chart(cohort)
        .mark_rect(stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("segment:N", title="Client segment"),
            y=alt.Y("cohort_month:O", title="Onboarding cohort month", sort="-y"),
            color=alt.Color(
                "activation_rate:Q",
                title="Activation rate",
                scale=alt.Scale(domain=[0, 1], scheme="redyellowgreen"),
                legend=alt.Legend(format=".0%"),
            ),
            tooltip=[
                alt.Tooltip("cohort_month:N", title="Cohort"),
                alt.Tooltip("segment:N", title="Segment"),
                alt.Tooltip("onboarded_clients:Q", title="Onboarded", format=",d"),
                alt.Tooltip("activated_clients:Q", title="Activated", format=",d"),
                alt.Tooltip("activation_rate:Q", title="Activation rate", format=".1%"),
            ],
        )
        .properties(height=340)
    )
    st.altair_chart(heatmap, width="stretch")
    st.caption("Each cell is a weighted monthly cohort rate using the 7-day activation rule.")
    st.dataframe(act, width="stretch")

st.caption(
    "Definitions & rules live in `warehouse/models/marts/kpis/` — each KPI is one "
    "dbt model with numerator/denominator columns; ratios are non-additive."
)
