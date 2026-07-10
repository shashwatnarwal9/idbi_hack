"""आय·AI dashboard: Streamlit over the Postgres serving store.

Point lookups only: profile, spending breakdown, precomputed prospect score +
SHAP reason codes. No LLM, no chatbot, no cloud calls.

Run:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from aayai.serving.db import connect
from aayai.serving.queries import portfolio_summary, ranked_prospects

# validated reference palette (dataviz method): one hue for magnitude,
# blue<->red diverging for signed SHAP, recessive chrome for axes/grid
BLUE = "#2a78d6"
RED = "#e34948"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

st.set_page_config(page_title="आय·AI", page_icon="₹", layout="wide")


@st.cache_resource
def _conn():
    return connect()


@st.cache_data(ttl=300)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a parameterised point-lookup query and return a dataframe."""
    with _conn().cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


@st.cache_data(ttl=300)
def get_summary() -> dict:
    """Live book-level aggregates from the serving store."""
    return portfolio_summary(_conn())


def fmt_inr(value: float | None) -> str:
    """Rupee formatting with an honest fallback for missing aggregates."""
    return f"₹{value:,.0f}" if value is not None else "unavailable"


@st.cache_data(ttl=300)
def get_ranked(bands: tuple[str, ...]) -> pd.DataFrame:
    """Live prospect ranking, recomputed from stored scores."""
    return pd.DataFrame(ranked_prospects(_conn(), list(bands)))


def fmt_reasons(reasons: list[dict], k: int = 3) -> str:
    """Compact signed reason codes, e.g. '+investable_surplus · −total_emi'."""
    return " · ".join(
        f"{'+' if r['shap'] > 0 else '−'}{r['feature']}" for r in reasons[:k]
    )


def _axis(**kw):
    """Altair axis with the recessive chrome colors used on every chart."""
    return alt.Axis(
        labelColor=INK_2,
        titleColor=MUTED,
        gridColor=GRID,
        domainColor=BASELINE,
        tickColor=BASELINE,
        **kw,
    )


st.title("आय·AI")
st.caption(
    "**आय** (aay) = income. True income & investable surplus, "
    "reconstructed from raw bank narrations, derived features only."
)

try:
    summary = get_summary()
except Exception:
    st.error(
        "Serving store unavailable. Start it with "
        "`docker compose up -d serving-postgres`, load it with "
        "`python -m aayai.serving.load`, then reload this page."
    )
    st.stop()

# portfolio pulse: every number computed live from customer_profiles
uplift = (
    summary["avg_reconstructed"] - summary["avg_declared"]
    if summary["avg_reconstructed"] is not None and summary["avg_declared"] is not None
    else None
)
bands = summary["bands"]
p1, p2, p3, p4 = st.columns(4)
p1.metric("Customers", summary["customers"])
p2.metric(
    "Avg reconstructed income",
    fmt_inr(summary["avg_reconstructed"]),
    delta=f"₹{uplift:+,.0f} vs declared" if uplift is not None else None,
)
p3.metric("Median investable surplus", fmt_inr(summary["median_surplus"]))
p4.metric(
    "High-trust estimates",
    (
        f"{bands['high']} of {summary['customers']}"
        if summary["customers"]
        else "unavailable"
    ),
)
st.divider()

if "view" not in st.session_state:
    st.session_state.view = "profile"

# ------------------------------------------------- deep analysis (ranked view)
if st.session_state.view == "analysis":
    if st.button("< Back to profile view"):
        st.session_state.view = "profile"
        st.rerun()
    st.subheader("Deep Analysis: prospects ranked by score")

    band_options = q(
        "SELECT DISTINCT confidence_band FROM customer_profiles ORDER BY 1"
    )["confidence_band"].tolist()
    chosen = st.multiselect("Confidence band", band_options, default=band_options)

    table = get_ranked(tuple(chosen))
    if table.empty:
        st.info("No customers match the selected bands.")
        st.stop()

    display = pd.DataFrame(
        {
            "Rank": table["rank"],
            "Customer": table["customer_id"],
            "Name": table["name"],
            "Score /100": (table["score"] * 100).round(1),
            "Confidence": table["band"],
            "Top signals": table["reasons"].map(fmt_reasons),
        }
    )
    st.caption(
        f"{len(display)} customers, ranked live from stored model scores. "
        "Select a row to open that customer's profile."
    )
    event = st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
    )
    if event.selection.rows:
        st.session_state.selected_customer = display.iloc[event.selection.rows[0]][
            "Customer"
        ]
        st.session_state.view = "profile"
        st.rerun()
    st.stop()

if st.button("Start Deep Analysis", type="primary"):
    st.session_state.view = "analysis"
    st.rerun()

ids = q("SELECT customer_id FROM customer_profiles ORDER BY customer_id")
options = ids["customer_id"].tolist()
preselect = st.session_state.get("selected_customer")
cid = st.selectbox(
    "Customer",
    options,
    index=options.index(preselect) if preselect in options else 0,
)

p = q("SELECT * FROM customer_profiles WHERE customer_id = %s", (cid,)).iloc[0]
score = q(
    "SELECT p_good_prospect, reasons FROM prospect_scores " "WHERE customer_id = %s",
    (cid,),
).iloc[0]

# ---------------------------------------------------------------- profile
m1, m2, m3, m4 = st.columns(4)
delta_vs_declared = p.true_monthly_income - p.declared_monthly_income
m1.metric(
    "Reconstructed monthly income",
    f"₹{p.true_monthly_income:,.0f}",
    delta=f"₹{delta_vs_declared:+,.0f} vs declared",
)
m2.metric("Investable surplus / month", f"₹{p.investable_surplus:,.0f}")
m3.metric("Savings rate", f"{p.savings_rate:.0%}")
m4.metric("Prospect score", f"{score.p_good_prospect:.0%}")

i1, i2, i3, i4, i5 = st.columns(5)
i1.metric("Income type", p.income_type)
i2.metric("Risk capacity", p.risk_capacity)
i3.metric("Confidence band", p.confidence_band)
i4.metric("Months of history", int(p.months_history))
i5.metric("Narrations parsed confidently", f"{p.pct_categorized:.0%}")
st.caption(
    f"{p.occupation_declared.title()} · {p.region} · income volatility "
    f"{p.income_volatility:.2f} · surplus stability {p.surplus_stability:.2f}"
)

left, right = st.columns(2)

# ------------------------------------------------- spending breakdown chart
with left:
    st.subheader("Where the money goes")
    spend = q(
        "SELECT category, avg_monthly FROM spending_breakdown "
        "WHERE customer_id = %s ORDER BY avg_monthly DESC",
        (cid,),
    )
    bars = (
        alt.Chart(spend)
        .mark_bar(color=BLUE, size=16, cornerRadiusEnd=4)
        .encode(
            x=alt.X(
                "avg_monthly:Q",
                title="avg monthly spend (₹)",
                axis=_axis(format=",.0f"),
            ),
            y=alt.Y("category:N", sort="-x", title=None, axis=_axis(grid=False)),
            tooltip=[
                alt.Tooltip("category:N", title="category"),
                alt.Tooltip("avg_monthly:Q", title="₹/month", format=",.0f"),
            ],
        )
    )
    st.altair_chart(bars, use_container_width=True)
    st.caption("Average monthly debit outflow per derived category, full history.")

# ------------------------------------------------- score + reason codes
with right:
    st.subheader("Why the model scored them this way")
    st.progress(
        float(score.p_good_prospect),
        text=f"P(good investment prospect) = {score.p_good_prospect:.0%}",
    )
    reasons = pd.DataFrame(score.reasons)
    reasons["direction"] = reasons["shap"].map(
        lambda v: "pushes up" if v > 0 else "pushes down"
    )
    reason_bars = (
        alt.Chart(reasons)
        .mark_bar(size=16, cornerRadiusEnd=4)
        .encode(
            x=alt.X(
                "shap:Q",
                title="SHAP contribution (log-odds)",
                axis=_axis(format="+.2f"),
            ),
            y=alt.Y(
                "feature:N",
                title=None,
                sort=alt.EncodingSortField("shap", op="sum", order="descending"),
                axis=_axis(grid=False),
            ),
            color=alt.condition(alt.datum.shap > 0, alt.value(BLUE), alt.value(RED)),
            tooltip=[
                alt.Tooltip("feature:N"),
                alt.Tooltip("value:Q", title="feature value", format=",.2f"),
                alt.Tooltip("shap:Q", title="SHAP", format="+.3f"),
                alt.Tooltip("direction:N"),
            ],
        )
    )
    labels = (
        alt.Chart(reasons)
        .mark_text(align="left", dx=4, color=INK_2)
        .encode(
            x="shap:Q",
            y=alt.Y(
                "feature:N",
                title=None,
                sort=alt.EncodingSortField("shap", op="sum", order="descending"),
            ),
            text=alt.Text("shap:Q", format="+.2f"),
        )
    )
    st.altair_chart(reason_bars + labels, use_container_width=True)
    st.caption(
        "Top SHAP drivers. Blue (+) pushes the score toward good "
        "prospect, red (−) away; signed labels carry the direction too."
    )

st.divider()
st.caption("आय·AI · synthetic data, fully local · serving store: Postgres")
