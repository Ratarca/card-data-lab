"""Card Data Lab — KPI dashboard (Stage 6A).

Run with:  uv run task dashboard
Reads the dbt marts directly from the DuckDB lake (read-only).
"""
from __future__ import annotations

import os

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
    f"{(util.spend.sum() / max(util.capacity.sum(), 1)):.1%}",
)
c5.metric(
    "Activation rate",
    f"{(act.activated_clients.sum() / max(act.onboarded_clients.sum(), 1)):.1%}",
)

st.divider()

# ---------------------------------------------------------------- charts
left, right = st.columns(2)

with left:
    st.subheader("Approval rate over time")
    daily = (
        kpis.groupby("date_key", as_index=False)[["attempts", "approved"]]
        .sum()
        .assign(approval_rate=lambda d: d.approved / d.attempts)
    )
    st.line_chart(daily.set_index("date_key")["approval_rate"], height=280)

    st.subheader("TPV by channel")
    by_channel = tpv.groupby("channel", as_index=False)["tpv"].sum()
    st.bar_chart(by_channel.set_index("channel")["tpv"], height=280)

with right:
    st.subheader("TPV over time")
    st.bar_chart(tpv.groupby("date_key", as_index=False)["tpv"].sum().set_index("date_key"), height=280)

    st.subheader("Declines by reason")
    st.bar_chart(delinq.groupby("decline_reason", as_index=False)["declines"].sum().set_index("decline_reason"), height=280)

# ---------------------------------------------------------------- tables
st.subheader("KPI detail")
tab1, tab2, tab3 = st.tabs(["Approval rate", "Limit utilization", "Activation cohorts"])
tab1.dataframe(kpis, width="stretch")
tab2.dataframe(util, width="stretch")
tab3.dataframe(act, width="stretch")

st.caption(
    "Definitions & rules live in `warehouse/models/marts/kpis/` — each KPI is one "
    "dbt model with numerator/denominator columns; ratios are non-additive."
)
