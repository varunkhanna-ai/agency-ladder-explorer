"""Interactive Explorer — run Rungs 4 & 5 live against a query.

Second page of the multipage app (the Executive Dashboard is the landing
page). This page DOES make live LLM calls; the dashboard never does.

Streamlit is imported here (and in the dashboard) only. Everything under
`src/` stays UI-free so a future FastAPI/Vercel frontend only replaces the
Streamlit layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# This file lives in pages/, so the repo root is two levels up.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.llm import LLMError, MissingAPIKeyError  # noqa: E402
from src.rungs import rung4_workflow, rung5_react  # noqa: E402
from src.rungs.base import RungResult  # noqa: E402

# ---------------------------------------------------------------------------
# Static config: which rungs exist, and the preset scenario queries.
# ---------------------------------------------------------------------------

RUNGS: dict[int, dict] = {
    4: {
        "name": "Fixed Workflow",
        "run": rung4_workflow.run,
        "controls_path": "Developer",
        "blurb": "Hardcoded 5-step refund sequence. The model extracts and phrases; it never routes.",
    },
    5: {
        "name": "ReAct Loop",
        "run": rung5_react.run,
        "controls_path": "Model",
        "blurb": "Hand-written THINK/ACT/OBSERVE loop, all 7 tools, step budget 5.",
    },
}

# The 6 planted scenarios from IMPLEMENTATION_PLAN.md §3, as natural-language
# customer messages, so a recruiter can click instead of typing.
PRESET_QUERIES: dict[str, str] = {
    "ORD-9821 — late + rain + restaurant silent (the centerpiece)": (
        "ORD-9821 is late, it's pouring rain, restaurant not answering"
    ),
    "ORD-4471 — looks fine but restaurant is backed up": (
        "ORD-4471 hasn't moved in 40 min, I'm worried. Pizza should be here by now."
    ),
    "ORD-1200 — cold food, within refund window": (
        "My order ORD-1200 from Burger Barn arrived cold. The cheese was "
        "congealed. I want a refund."
    ),
    "ORD-1201 — cold food, outside refund window": (
        "I ordered from Sushi Zen (ORD-1201) yesterday and the salmon roll "
        "was warm. I need a refund."
    ),
    "ORD-7788 — simple, on-time, no complications": (
        "Where is my order ORD-7788?"
    ),
    "ORD-3003 — allergic reaction (must escalate)": (
        "I had an allergic reaction to my order ORD-3003. What should I do?"
    ),
}

RISK_BADGE = {"GREEN": "🟢", "YELLOW": "🟡", "BLUE": "🔵"}

GITHUB_URL = "https://github.com/varunkhanna-ai/agency-ladder-explorer"

# Page config + title/icon are set by app.py's st.navigation (which runs this
# script as a page) — calling st.set_page_config here again would error.

# ---------------------------------------------------------------------------
# 1. Header
# ---------------------------------------------------------------------------

st.title("🔬 Interactive Explorer")
st.caption(
    "Run the same query through Rung 4 (fixed workflow) and Rung 5 (ReAct "
    "loop) live, and watch the cost/latency gap. "
    f"[View source]({GITHUB_URL})"
)

st.warning(
    "Live calls use Groq's free tier, which has a tight daily token quota. If "
    "a rung shows a rate-limit message, that's the quota, not a bug — the "
    "pre-computed numbers on the dashboard don't depend on this.",
    icon="⚠️",
)

# ---------------------------------------------------------------------------
# 2. Query input — text box + dropdown of preset scenario queries
# ---------------------------------------------------------------------------

st.subheader("1. Pick or write a query")
col_a, col_b = st.columns([1, 2])
with col_a:
    preset_label = st.selectbox(
        "Preset DeliverEase scenarios", list(PRESET_QUERIES.keys())
    )
with col_b:
    query = st.text_area(
        "Query sent to every selected rung",
        value=PRESET_QUERIES[preset_label],
        height=90,
    )

# ---------------------------------------------------------------------------
# 3. Rung selector
# ---------------------------------------------------------------------------

st.subheader("2. Choose rungs to compare")
st.caption(
    "Only Rungs 4 and 5 are built in this demo (Rungs 1-3 were scoped out — "
    "see the README). Comparing a deterministic workflow against an agentic "
    "loop is where the thesis actually lives."
)
selected = st.multiselect(
    "Rungs",
    options=list(RUNGS.keys()),
    default=list(RUNGS.keys()),
    format_func=lambda lvl: f"Rung {lvl} — {RUNGS[lvl]['name']}",
)
run_clicked = st.button("▶️ Run All", type="primary", disabled=not selected)

if run_clicked:
    st.session_state["results"] = {}
    st.session_state["errors"] = {}
    st.session_state["last_query"] = query

    # Sequential on purpose: fair latency comparison + Groq free-tier rate
    # limits (~30 req/min) would be hit by fanning out (§9).
    for level in sorted(selected):
        info = RUNGS[level]
        with st.spinner(f"Running Rung {level} — {info['name']}..."):
            try:
                result: RungResult = info["run"](query)
                st.session_state["results"][level] = result
            except MissingAPIKeyError:
                st.session_state["errors"][level] = (
                    "No Groq API key configured. Set GROQ_API_KEY in your "
                    "environment or .env file."
                )
            except LLMError as exc:
                msg = str(exc)
                if "429" in msg or "rate" in msg.lower():
                    st.session_state["errors"][level] = (
                        "Groq's free-tier rate limit was hit while running "
                        "this rung. Wait a minute and try again — this isn't "
                        "a bug in the rung itself."
                    )
                else:
                    st.session_state["errors"][level] = f"LLM call failed: {msg}"
            except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
                st.session_state["errors"][level] = f"Unexpected error: {exc}"

# ---------------------------------------------------------------------------
# 4. Results — one expandable panel per rung
# ---------------------------------------------------------------------------

results: dict[int, RungResult] = st.session_state.get("results", {})
errors: dict[int, str] = st.session_state.get("errors", {})

if results or errors:
    st.subheader("3. Results")

    for level in sorted(set(results) | set(errors)):
        info = RUNGS[level]
        if level in errors:
            with st.expander(f"⚠️ Rung {level} — {info['name']} (failed)", expanded=True):
                st.error(errors[level])
            continue

        res = results[level]
        warn = " ⚠️" if res.step_budget_breached else ""
        with st.expander(
            f"Rung {level} — {info['name']}{warn}", expanded=True
        ):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Latency", f"{res.latency_ms:,} ms")
            m2.metric("Tokens", f"{res.input_tokens + res.output_tokens:,}")
            m3.metric("Cost", f"${res.cost_usd:.6f}")
            m4.metric("Cost / 10k queries", f"${res.cost_usd * 10_000:,.2f}")

            if res.step_budget_breached:
                st.warning("Step budget was exhausted — forced escalation to a human.")
            elif res.escalated:
                st.info("This rung escalated to a human.")

            st.markdown("**Final answer:**")
            st.write(res.final_answer)

            st.markdown("**Trace:**")
            for step in res.trace:
                if step.kind == "THINK":
                    st.markdown(f"🧠 **THINK** — {step.content}")
                elif step.kind == "ACT":
                    badge = RISK_BADGE.get(step.risk or "", "")
                    st.markdown(f"⚙️ **ACT** {badge} `{step.tool}({step.args})`")
                elif step.kind == "OBSERVE":
                    if step.content == "🟡 WRITE ACTION LOGGED":
                        st.markdown("🟡 **WRITE ACTION LOGGED**")
                    else:
                        st.markdown(f"👁️ **OBSERVE** — `{step.content}`")
                elif step.kind == "ANSWER":
                    st.markdown(f"✅ **ANSWER** — {step.content}")

# ---------------------------------------------------------------------------
# 5. The money shot — comparison table
# ---------------------------------------------------------------------------

if results or errors:
    st.subheader("4. Comparison")

    rows = []
    for level in sorted(RUNGS):
        info = RUNGS[level]
        if level in errors:
            rows.append(
                {
                    "Rung": f"Rung {level} — {info['name']}",
                    "Answered?": "❌ Failed",
                    "Latency (ms)": None,
                    "Tokens": None,
                    "Cost (USD)": None,
                    "Cost / 10k queries": None,
                }
            )
        elif level in results:
            res = results[level]
            if res.step_budget_breached:
                answered = "⚠️ Budget breached"
            elif res.escalated:
                answered = "🔵 Escalated"
            elif res.final_answer:
                answered = "✅ Yes"
            else:
                answered = "❌ No answer"
            rows.append(
                {
                    "Rung": f"Rung {level} — {info['name']}",
                    "Answered?": answered,
                    "Latency (ms)": res.latency_ms,
                    "Tokens": res.input_tokens + res.output_tokens,
                    "Cost (USD)": round(res.cost_usd, 6),
                    "Cost / 10k queries": round(res.cost_usd * 10_000, 2),
                }
            )

    df = pd.DataFrame(rows).set_index("Rung")
    st.dataframe(df, use_container_width=True)
    st.caption(
        "\"Answered?\" reflects whether the rung completed without error — "
        "not an automated correctness grader. Escalation is a legitimate, "
        "designed outcome, not a failure."
    )

    # ---------------------------------------------------------------------
    # 6. Bar chart — cost and latency by rung
    # ---------------------------------------------------------------------
    chart_df = df.dropna(subset=["Latency (ms)"])
    if not chart_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Latency by rung (ms)")
            st.bar_chart(chart_df[["Latency (ms)"]])
        with c2:
            st.caption("Cost per 10,000 queries (USD)")
            st.bar_chart(chart_df[["Cost / 10k queries"]])

    # ---------------------------------------------------------------------
    # 7. Callout — rule-based takeaway sentence
    # ---------------------------------------------------------------------
    ok_levels = [lvl for lvl in results if lvl not in errors]
    if len(ok_levels) == 2:
        lvl_lo, lvl_hi = sorted(ok_levels)
        r_lo, r_hi = results[lvl_lo], results[lvl_hi]

        def _answered_ok(r: RungResult) -> bool:
            return bool(r.final_answer) and not r.step_budget_breached

        lo_ok, hi_ok = _answered_ok(r_lo), _answered_ok(r_hi)
        lat_ratio = (r_hi.latency_ms / r_lo.latency_ms) if r_lo.latency_ms else float("inf")
        cost_ratio = (r_hi.cost_usd / r_lo.cost_usd) if r_lo.cost_usd else float("inf")

        if lo_ok and hi_ok:
            if lat_ratio >= 1.5 or cost_ratio >= 1.5:
                takeaway = (
                    f"Both Rung {lvl_lo} and Rung {lvl_hi} answered this query. "
                    f"Rung {lvl_hi} took {lat_ratio:.1f}× longer and cost "
                    f"{cost_ratio:.1f}× more. For this query, Rung {lvl_lo} "
                    "is the right design choice."
                )
            else:
                takeaway = (
                    f"Both Rung {lvl_lo} and Rung {lvl_hi} answered this query "
                    "at similar cost and latency — the simpler rung's "
                    "reliability isn't being bought at a premium here."
                )
        elif hi_ok and not lo_ok:
            takeaway = (
                f"Rung {lvl_lo} could not resolve this query on its fixed "
                f"path; Rung {lvl_hi}'s model-controlled discovery was "
                "needed. This is exactly the case where the extra cost and "
                "latency of a higher rung is justified."
            )
        elif lo_ok and not hi_ok:
            takeaway = (
                f"Rung {lvl_lo} answered directly; Rung {lvl_hi} escalated or "
                "exhausted its step budget on the same query. More agency "
                "did not produce a better outcome here."
            )
        else:
            takeaway = (
                f"Neither Rung {lvl_lo} nor Rung {lvl_hi} produced a "
                "resolving answer for this query — both escalated or hit "
                "their limits."
            )
        st.info(f"**Takeaway:** {takeaway}")
else:
    st.info("Pick a query, choose rungs, and click **Run All** to see results.")
