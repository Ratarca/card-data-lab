"""Card Data Lab — KPI dashboard (Stage 6A).

Run with:  uv run task dashboard
Reads the dbt marts directly from the DuckDB lake (read-only).
"""
from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

DB_PATH = "lake/events.duckdb"

st.set_page_config(page_title="Card Lab KPIs", page_icon="💳", layout="wide")


@st.cache_resource(ttl=60)
def get_conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


@st.cache_data(ttl=60)
def query(sql: str) -> pd.DataFrame:
    return get_conn().execute(sql).df()


st.title("💳 Card Data Lab — KPI Dashboard")
st.caption("Stage 6A · KPI models built with dbt on the DuckDB lake")

# ---------------------------------------------------------------- sidebar
segments = [None] + query(
    "select distinct segment from main.kpi_approval_rate order by 1"
)["segment"].tolist()
seg = st.sidebar.selectbox("Client segment", segments, index=0)
seg_filter = f"where segment = '{seg}'" if seg else ""

kpis = query(f"select * from main.kpi_approval_rate {seg_filter}")
tpv = query(f"select * from main.kpi_tpv {seg_filter}")
delinq = query(f"select * from main.kpi_delinquency_rate {seg_filter}")
util = query(f"select * from main.kpi_limit_utilization {seg_filter}")
act = query(f"select * from main.kpi_activation_rate {seg_filter}")

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
tab1.dataframe(kpis, use_container_width=True)
tab2.dataframe(util, use_container_width=True)
tab3.dataframe(act, use_container_width=True)

st.caption(
    "Definitions & rules live in `warehouse/models/marts/kpis/` — each KPI is one "
    "dbt model with numerator/denominator columns; ratios are non-additive."
)
