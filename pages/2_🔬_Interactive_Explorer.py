"""Food Delivery Customer Chat Agent — run Rungs 4 & 5 live against a query.

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

# Rung 4's fixed workflow (src/rungs/rung4_workflow.py) is a decision tree
# built for exactly one situation: a cold-food / quality refund complaint. It
# always runs that same 5-step sequence regardless of what's actually being
# asked, so on any OTHER kind of query it can "complete without error" (no
# exception, a final answer produced) while still being the wrong response —
# e.g. issuing a refund coupon for a query that was actually about weather-
# related delay, or never recognizing a safety issue that must escalate.
# This is a static, documented fact about the two on-path preset scenarios
# (cold-food complaints) vs. the four off-path ones — not a per-run grader,
# since we have no ground truth for arbitrary typed queries.
_RUNG4_OFF_PATH_QUERIES: set[str] = {
    PRESET_QUERIES["ORD-9821 — late + rain + restaurant silent (the centerpiece)"],
    PRESET_QUERIES["ORD-4471 — looks fine but restaurant is backed up"],
    PRESET_QUERIES["ORD-7788 — simple, on-time, no complications"],
    PRESET_QUERIES["ORD-3003 — allergic reaction (must escalate)"],
}


def _ratio_phrase(
    hi_val: float, lo_val: float, hi_label: str, lo_label: str,
    higher_word: str, lower_word: str,
) -> str:
    """Direction-aware ratio phrasing — never says "took 0.5x longer".

    Compares hi_val to lo_val and always describes whichever one is actually
    larger, using the correct word for that direction, so the sentence stays
    true regardless of which rung happened to be slower/costlier in this
    particular live run (a real possibility given network variance).
    """
    if lo_val <= 0:
        return f"{hi_label}'s value couldn't be compared to {lo_label} (no baseline)"
    if hi_val >= lo_val:
        return f"{hi_label} was {hi_val / lo_val:.1f}× {higher_word} than {lo_label}"
    return f"{hi_label} was actually {lo_val / hi_val:.1f}× {lower_word} than {lo_label}"


def _ratio_magnitude(ratio: float) -> float:
    """How far a ratio deviates from 1, symmetric in either direction."""
    if ratio in (0, float("inf")):
        return float("inf")
    return max(ratio, 1 / ratio)

GITHUB_URL = "https://github.com/varunkhanna-ai/agency-ladder-explorer"

# Page config + title/icon are set by app.py's st.navigation (which runs this
# script as a page) — calling st.set_page_config here again would error.

# ---------------------------------------------------------------------------
# 1. Header
# ---------------------------------------------------------------------------

st.title("Food Delivery Customer Chat Agent")
st.caption(
    "Run the same query through Rung 4 (fixed workflow) and Rung 5 (ReAct "
    "loop) live, and watch the cost/latency gap. "
    f"[View source]({GITHUB_URL})"
)

st.markdown(
    "This is a real-world example of a Food Delivery Customer Chat Agent. "
    "You're interacting with two different agent implementations (Rung 4: "
    "deterministic workflow, Rung 5: agentic reasoning loop) handling "
    "customer support queries for DeliverEase. Run a query to see how cost, "
    "latency, and correctness differ between the two approaches."
)

st.markdown(
    "This demo focuses on Rungs 4 and 5 of the Agent Ladder to illustrate "
    "the core tradeoff: deterministic workflow vs. agentic reasoning. "
    "(Rungs 1–3 were deliberately scoped out.)"
)
st.markdown(
    """
| Rung | Name | Who controls the path? | Built here? | When you'd choose it |
|---|---|---|---|---|
| 1 | Static Prompt | Developer (no tools at all) | ❌ scoped out | Query never needs live data — pure policy/FAQ text |
| 2 | RAG | Developer (retrieval is hardcoded) | ❌ scoped out | Answer lives in a document, but doesn't require fresh state |
| 3 | Single Tool Call | Developer decides *that* + *which* tool; model decides args | ❌ scoped out | One clear lookup, no branching logic needed |
| 4 | Fixed Workflow | **Developer** — the model extracts and phrases, never routes | ✅ | The steps and branching logic are known in advance and don't change per query |
| 5 | ReAct Loop | **Model** — decides which tools, in what order, when to stop | ✅ | The path can't be known in advance; the query requires investigation |
"""
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
    "loop is where the Agent Ladder thesis actually lives."
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
                    "Completed?": "❌ Failed",
                    "Latency (ms)": None,
                    "Tokens": None,
                    "Cost (USD)": None,
                    "Cost / 10k queries": None,
                }
            )
        elif level in results:
            res = results[level]
            if res.step_budget_breached:
                completed = "⚠️ Budget breached"
            elif res.escalated:
                completed = "🔵 Escalated"
            elif res.final_answer:
                completed = "✅ Ran without error"
            else:
                completed = "❌ No answer"
            # Rung 4 always "completes" on off-path queries — that doesn't
            # mean its answer was appropriate (see caption + takeaway below).
            if (
                level == 4
                and completed == "✅ Ran without error"
                and query in _RUNG4_OFF_PATH_QUERIES
            ):
                completed += " ⚠️ off-path for this query type"
            rows.append(
                {
                    "Rung": f"Rung {level} — {info['name']}",
                    "Completed?": completed,
                    "Latency (ms)": res.latency_ms,
                    "Tokens": res.input_tokens + res.output_tokens,
                    "Cost (USD)": round(res.cost_usd, 6),
                    "Cost / 10k queries": round(res.cost_usd * 10_000, 2),
                }
            )

    df = pd.DataFrame(rows).set_index("Rung")
    st.dataframe(df, use_container_width=True)
    st.caption(
        "\"Completed?\" reflects whether the rung ran without error — it is "
        "NOT an automated correctness grader (renamed from \"Answered?\" to "
        "avoid implying otherwise). Escalation is a legitimate, designed "
        "outcome, not a failure. Rung 4 runs the same fixed cold-food-refund "
        "decision tree regardless of what's actually asked, so it can "
        "\"complete\" on an off-path query (weather delay, safety issue, a "
        "plain status check) while still producing an inappropriate answer — "
        "flagged above where detectable. For real correctness grading against "
        "known-good outcomes, see the Executive Dashboard's verdict table."
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
        lvl_lo, lvl_hi = sorted(ok_levels)  # this app only has (4, 5)
        r_lo, r_hi = results[lvl_lo], results[lvl_hi]

        def _completed(r: RungResult) -> bool:
            return bool(r.final_answer) and not r.step_budget_breached

        lo_ok, hi_ok = _completed(r_lo), _completed(r_hi)
        lat_ratio = (r_hi.latency_ms / r_lo.latency_ms) if r_lo.latency_ms else float("inf")
        cost_ratio = (r_hi.cost_usd / r_lo.cost_usd) if r_lo.cost_usd else float("inf")
        notable = (
            _ratio_magnitude(lat_ratio) >= 1.5 or _ratio_magnitude(cost_ratio) >= 1.5
        )
        # Rung 4 always runs the same cold-food-refund decision tree — it can
        # "complete" on a query it was never built to evaluate, and that
        # completion doesn't mean the answer was actually correct.
        rung4_off_path = lvl_lo == 4 and query in _RUNG4_OFF_PATH_QUERIES

        # Rung 4's off-path caveat applies whenever it "completed" on a query
        # its fixed workflow wasn't built for — independent of whether Rung 5
        # also completed. Checking this FIRST (before the plain completion
        # comparison) matters: without it, a case like "Rung 4 completes (but
        # wrongly) while Rung 5 escalates" would fall through to the generic
        # "more agency didn't help" framing and implicitly vouch for Rung 4's
        # answer as correct, which we have no basis to claim.
        rung4_action = (
            "issued a coupon" if "issue_refund_coupon" in r_lo.tools_called
            else "declined a refund"
        )

        if lo_ok and rung4_off_path and hi_ok:
            takeaway = (
                f"Rung {lvl_lo} {rung4_action} quickly by applying its one "
                "fixed rule for cold-food complaints — but this isn't that "
                "kind of complaint, so speed doesn't mean it got the right "
                "answer (check its trace above for what it actually based "
                f"that on). Rung {lvl_hi} took longer because it actually "
                "investigated the real situation before answering. "
                + _ratio_phrase(
                    r_hi.latency_ms, r_lo.latency_ms, f"Rung {lvl_hi}", f"Rung {lvl_lo}",
                    "slower", "faster",
                )
                + f". The right choice depends on whether speed or accuracy "
                f"matters more here: Rung {lvl_lo} if you need a fast answer "
                f"and can tolerate an occasional wrong one; Rung {lvl_hi} if "
                "the answer actually needs to be right."
            )
        elif lo_ok and rung4_off_path and not hi_ok:
            takeaway = (
                f"Rung {lvl_lo} {rung4_action} quickly by applying its one "
                "fixed rule for cold-food complaints — but this isn't that "
                "kind of complaint, so its speed doesn't mean it got the "
                "right answer (check its trace above for what it actually "
                f"based that on, applying a generic rule to a situation it "
                f"wasn't built to evaluate). Rung {lvl_hi}, instead of "
                "guessing, kept investigating once it recognized the "
                "situation was more complex than a simple refund — and ran "
                "out of step budget before it could finish, escalating to a "
                "human rather than answering incorrectly. The right choice "
                "depends on whether speed or accuracy matters more here: "
                f"Rung {lvl_lo} gives you a fast answer that may be wrong; "
                f"Rung {lvl_hi} gives you no answer yet, but never a "
                "confidently wrong one."
            )
        elif lo_ok and hi_ok:
            if notable:
                takeaway = (
                    f"Both Rung {lvl_lo} and Rung {lvl_hi} completed this query. "
                    + _ratio_phrase(
                        r_hi.latency_ms, r_lo.latency_ms, f"Rung {lvl_hi}", f"Rung {lvl_lo}",
                        "slower", "faster",
                    )
                    + ", and "
                    + _ratio_phrase(
                        r_hi.cost_usd, r_lo.cost_usd, f"Rung {lvl_hi}", f"Rung {lvl_lo}",
                        "more expensive", "cheaper",
                    )
                    + f". For this query, Rung {lvl_lo} is the right design choice."
                )
            else:
                takeaway = (
                    f"Both Rung {lvl_lo} and Rung {lvl_hi} completed this query "
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
                f"Rung {lvl_lo} completed directly; Rung {lvl_hi} escalated or "
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
