"""Executive Dashboard — the landing page.

A static, at-a-glance summary of the Rung 4 vs Rung 5 tradeoff for a
decision-maker. It reads ONLY `data/benchmark_results.json` (generated once by
`scripts/generate_benchmarks.py`) and makes NO live LLM calls — so it loads
instantly and shows stable numbers. Every multiple ("N× slower / more
expensive") is computed from the aggregates at render time, never hardcoded.

For live, real-time runs, the Interactive Explorer page makes the actual calls.

Layout (exactly five sections):
  1. Title + one-sentence thesis
  2. Metric strip (cost/latency multiples + win/fail counts)
  3. Two grouped bar charts (cost by rung, latency by rung)
  4. Verdict table (one row per query + recommendation)
  5. CTA row (explorer + contact links)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
BENCHMARK_PATH = ROOT / "data" / "benchmark_results.json"

GITHUB_URL = "https://github.com/varunkhanna-ai/agency-ladder-explorer"
LINKEDIN_URL = "https://www.linkedin.com/in/khannavarun/"
EMAIL = "mailvarunkhanna@gmail.com"

RUNG_LABELS = {"4": "Rung 4 — Fixed Workflow", "5": "Rung 5 — ReAct Loop"}
TIER_LABELS = {"simple": "Simple", "medium": "Medium", "complex": "Complex"}

# Dark plotly template that blends into Streamlit's dark theme.
_PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
)
_RUNG_COLORS = {"Rung 4 — Fixed Workflow": "#4c8bf5", "Rung 5 — ReAct Loop": "#f5a34c"}

st.set_page_config(page_title="Executive Dashboard", page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------
# Data loading + completeness guard
# ---------------------------------------------------------------------------


def load_benchmarks() -> dict | None:
    if not BENCHMARK_PATH.exists():
        return None
    try:
        return json.loads(BENCHMARK_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def is_complete(data: dict) -> bool:
    """True only if every run succeeded and every aggregate mean is present."""
    runs = data.get("runs", [])
    if not runs or any(r.get("error") for r in runs):
        return False
    agg = data.get("aggregates", {})
    overall = agg.get("overall", {})
    for lvl in ("4", "5"):
        cell = overall.get(lvl, {})
        if not cell.get("cost_usd") or not cell.get("latency_ms"):
            return False
    return True


def _fmt_when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%B %d, %Y at %H:%M UTC")
    except (ValueError, TypeError):
        return iso or "unknown"


def _cta_row() -> None:
    """Section 5 — shown on every render, even when data is pending."""
    st.subheader("Try it yourself")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.page_link(
            "pages/2_🔬_Interactive_Explorer.py",
            label="Run it live →",
            icon="🔬",
        )
    with c2:
        st.markdown(f"[🔗 LinkedIn]({LINKEDIN_URL})")
    with c3:
        st.markdown(f"[📧 Email](mailto:{EMAIL})")
    with c4:
        st.markdown(f"[💻 GitHub]({GITHUB_URL})")


# ===========================================================================
# 1. Title + one-sentence thesis
# ===========================================================================

st.title("📊 Agency Ladder — Executive Dashboard")
st.markdown(
    "**Higher on the agency ladder is not better: the lowest rung that "
    "reliably completes the task is the correct design choice.**"
)

data = load_benchmarks()

# Graceful state while the static benchmark is being (re)generated.
if data is None or not is_complete(data):
    st.warning(
        "📉 **Benchmark data is being regenerated.** These numbers come from a "
        "one-time offline run of `scripts/generate_benchmarks.py`; the last run "
        "hit Groq's daily free-tier token limit before completing, so the full "
        "table is pending the next run. The Interactive Explorer still works "
        "for live queries.",
        icon="⏳",
    )
    st.divider()
    _cta_row()
    st.stop()

st.caption(
    f"Static benchmark — {len(data['runs'])} runs "
    f"({data['aggregates']['by_tier']['simple']['n_queries']} queries per tier "
    f"× {len(RUNG_LABELS)} rungs). Generated {_fmt_when(data['generated_at'])}. "
    "No live model calls on this page."
)

overall = data["aggregates"]["overall"]
by_tier = data["aggregates"]["by_tier"]

# ===========================================================================
# 2. Metric strip — all multiples computed from the JSON at render time
# ===========================================================================

cost4 = overall["4"]["cost_usd"]["mean"]
cost5 = overall["5"]["cost_usd"]["mean"]
lat4 = overall["4"]["latency_ms"]["mean"]
lat5 = overall["5"]["latency_ms"]["mean"]

cost_mult = cost5 / cost4 if cost4 else float("nan")
lat_mult = lat5 / lat4 if lat4 else float("nan")

simple_wins = by_tier["simple"]["r5_wins_over_r4"]
simple_n = by_tier["simple"]["n_queries"]
complex_fails = by_tier["complex"]["r4_fail_count"]
complex_n = by_tier["complex"]["n_queries"]

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Rung 5 cost / query",
    f"${cost5:.6f}",
    delta=f"{cost_mult:.1f}× vs Rung 4",
    delta_color="inverse",  # more expensive = red
)
m2.metric(
    "Rung 5 latency / query",
    f"{lat5:,.0f} ms",
    delta=f"{lat_mult:.1f}× vs Rung 4",
    delta_color="inverse",  # slower = red
)
m3.metric(
    "Simple queries where Rung 5 wins",
    f"{simple_wins} of {simple_n}",
)
m4.metric(
    "Complex queries where Rung 4 fails",
    f"{complex_fails} of {complex_n}",
)

st.divider()

# ===========================================================================
# 3. Two grouped bar charts side by side — cost by rung, latency by rung
# ===========================================================================

# Shape the per-tier means into a long dataframe: (Complexity, Rung, cost, latency).
chart_rows = []
for tier in data["tiers"]:
    for lvl in ("4", "5"):
        cell = by_tier[tier][lvl]
        chart_rows.append(
            {
                "Complexity": TIER_LABELS.get(tier, tier),
                "Rung": RUNG_LABELS[lvl],
                "Cost per query (USD)": cell["cost_usd"]["mean"] if cell["cost_usd"] else 0,
                "Latency per query (ms)": cell["latency_ms"]["mean"] if cell["latency_ms"] else 0,
            }
        )
chart_df = pd.DataFrame(chart_rows)
tier_order = [TIER_LABELS.get(t, t) for t in data["tiers"]]

left, right = st.columns(2)
with left:
    st.markdown("**Cost per query by rung**")
    fig_cost = px.bar(
        chart_df,
        x="Complexity",
        y="Cost per query (USD)",
        color="Rung",
        barmode="group",
        category_orders={"Complexity": tier_order},
        color_discrete_map=_RUNG_COLORS,
    )
    fig_cost.update_layout(**_PLOTLY_LAYOUT)
    st.plotly_chart(fig_cost, use_container_width=True)
with right:
    st.markdown("**Latency per query by rung**")
    fig_lat = px.bar(
        chart_df,
        x="Complexity",
        y="Latency per query (ms)",
        color="Rung",
        barmode="group",
        category_orders={"Complexity": tier_order},
        color_discrete_map=_RUNG_COLORS,
    )
    fig_lat.update_layout(**_PLOTLY_LAYOUT)
    st.plotly_chart(fig_lat, use_container_width=True)

st.divider()

# ===========================================================================
# 4. Verdict table — one row per query + plain-language recommendation
# ===========================================================================

st.subheader("Per-query verdict")
verdict_rows = []
for v in data["verdicts"]:
    verdict_rows.append(
        {
            "Query": v["query"],
            "Tier": TIER_LABELS.get(v["tier"], v["tier"]),
            "Rung 4": "✅" if v["rung4_correct"] else "❌",
            "Rung 5": "✅" if v["rung5_correct"] else "❌",
            "Recommendation": v["recommendation"],
        }
    )
st.dataframe(
    pd.DataFrame(verdict_rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Query": st.column_config.TextColumn(width="medium"),
        "Recommendation": st.column_config.TextColumn(width="large"),
    },
)
st.caption(
    "“Correct” is a per-query behavioral check (right tools called / escalated "
    "when it should), stored in the benchmark JSON so it's auditable."
)

st.divider()

# ===========================================================================
# 5. CTA row
# ===========================================================================

_cta_row()
