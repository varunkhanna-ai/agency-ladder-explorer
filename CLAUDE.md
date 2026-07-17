# Agent Ladder Explorer — Project Context

## What this is
A teaching demo that answers the same DeliverEase customer-support query at 5 rungs of the
agent ladder (static prompt → RAG → single tool call → fixed workflow → ReAct loop) and
measures cost, latency, and tokens at each. Thesis: higher on the ladder is not better; the
lowest rung that reliably completes the task is the correct design choice.

## Locked decisions (do not revisit without asking the human)
- Scenario: DeliverEase (fictional food delivery). All data synthetic. Currency: USD.
- Model: Groq `llama-3.3-70b-versatile`, temperature=0.
- NO agent framework. The ReAct loop is hand-written. This is deliberate and non-negotiable.
- No vector DB. TF-IDF/keyword search over one markdown file.
- Rungs built: 1, 2, 3, 4, 5. Rung 6 (multi-agent) is OUT of scope.
- Tools: 5 GREEN reads, 1 YELLOW write (`issue_refund_coupon`, $20 cap enforced IN CODE),
  1 escalation. No RED/irreversible tools — documented as out of scope in README.
- ReAct step budget: 5, then forced escalation.
- Evals: trajectory-level only (assert tool sequence + args). No fleet dashboard.
- UI: Streamlit. `app.py` is the ONLY file that may import streamlit. `src/` stays UI-free
  so a future FastAPI+Vercel migration only swaps the UI layer.

## Build status
- [x] Phase 1 — scaffold + data
- [x] Phase 2 — llm.py, config, metrics, trace
- [x] Phase 3 — tools.py
- [x] Phase 4 — rungs 1-4
- [x] Phase 5 — rung 5 (ReAct)
- [x] Phase 6 — evals
- [x] Phase 7 — Streamlit UI
- [x] Phase 8 — README + deploy

## Handoff Protocol
Before ending any session (whether switching tools, or finishing a parallel worktree round):
1. Check off completed phases above. Only check a phase if its Definition of Done
   (IMPLEMENTATION_PLAN.md §11) is fully met — not "mostly working."
2. Add a dated entry under `## Session Notes` below (1-3 lines): what you built, any
   deviation from the spec and why, and anything the next agent should watch for.
3. Do not leave uncommitted changes. Commit with a message naming the phase.

## Session Notes
<!-- Newest entries at the top. Both Kilo Code and Claude Code append here. -->

- **2026-07-16 (Claude Code):** Post-Phase-8 follow-ups, all on `claude-phase7`
  → merged to `main`. This is a substantial addendum to the "Phases 7+8
  complete" entry below — the UI has changed shape since that commit.
  - **Executive Dashboard added as the landing page.** Restructured `app.py`
    into a Streamlit multipage app via `st.navigation`/`st.Page`: `app.py` is
    now a **static** dashboard (thesis, metric strip, 2 Plotly grouped bar
    charts, verdict table, CTA row) that reads only
    `data/benchmark_results.json` and makes **no live LLM calls**; the
    original live-query UI moved to `pages/2_🔬_Interactive_Explorer.py`.
    Both files import Streamlit now — `src/` is still the only UI-free layer,
    not literally "one file" anymore.
  - **`scripts/generate_benchmarks.py`** (new): runs 9 queries (3 per
    complexity tier) × Rungs 4/5, records latency/tokens/cost/correctness per
    run + per-tier mean/min/max aggregates + a generation timestamp to
    `data/benchmark_results.json`. Run once, commit the output — the
    dashboard never calls Groq. **First run hit Groq's 100K TPD cap after only
    3/18 calls** (today's cumulative usage from earlier phases) — do not
    assume a clean run on the first try if the day's quota is already warm.
    Second run (after quota reset) completed 17/18; the one failure (a
    transient `400 tool_use_failed` malformed generation, not a rate limit)
    is recorded transparently in the JSON and excluded from that cell's mean,
    not hidden. `is_complete()` in `app.py` checks per-cell aggregate
    usability, not zero-raw-errors, specifically so one bad run doesn't block
    the whole dashboard.
  - **Real finding surfaced by live data, kept rather than hidden:** one
    medium-tier Rung 5 run took a genuine 602 seconds. The dashboard shows
    the true mean (not filtered), a caption disclosing the range, and the
    latency chart uses a log-scale y-axis so the outlier doesn't flatten
    every other bar — a readability fix, not a data change.
  - **Fixed a real correctness bug** in the Explorer's rule-based takeaway:
    it always said "Rung {hi} took {ratio}× longer/more" using rung *number*
    order, not which rung actually was slower — so a live run where Rung 4
    happened to be slower would print nonsense like "Rung 5 took 0.5×
    longer." Replaced with direction-aware phrasing
    (`_ratio_phrase`/`_ratio_magnitude`).
  - **"Answered?" renamed to "Completed?"** with a caption clarifying it's
    not a correctness grader — Rung 4 always runs its one fixed cold-food-
    refund decision tree regardless of the actual query, so it can "complete"
    while being wrong. On the 4 known preset queries outside that domain
    (weather delay, backed-up restaurant, plain status check, allergic
    reaction), the column flags "⚠️ off-path for this query type" and the
    takeaway names the real tradeoff (fast-but-possibly-wrong vs. slower-
    because-it-investigated) instead of implying a verdict. Caught via a live
    test on the ORD-9821 preset: Rung 4 issued an $18.50 "cold food" coupon
    for what the retrieved policy shows should be a $5–10 delivery-delay
    coupon, while Rung 5 escalated on budget exhaustion — the first version
    of this fix only covered the "both rungs complete" case and let this
    exact scenario fall through to language that implicitly vouched for
    Rung 4's wrong answer.
  - Also: added the ladder reference table (Rungs 1–5) to the top of the
    Interactive Explorer page for scope context; removed a duplicated
    "Final answer" block that repeated the trace's trailing ANSWER step.
  - **README.md updated** to match: new "The UI: a static dashboard + a live
    explorer" section, fixed two now-false "`app.py` is the only file that
    imports Streamlit" claims, "Running it locally" now explains the
    dashboard works with no API key (reads committed JSON) while the
    Explorer needs `GROQ_API_KEY`.

- **2026-07-15 (Claude Code):** Phases 7+8 complete. Streamlit UI built with all rungs 4–5, comparison table, cost/latency chart, and callout logic. README complete with thesis, eval findings, ReAct trace, and portfolio framing. Live demo deployed to Streamlit Community Cloud at https://agency-ladder-explorer-y6rsmz4pwqbd2ojhuzk4qv.streamlit.app/

- **2026-07-15 (Kilo Code):** Phase 6 complete — `evals/cases.py` (12 EvalCase definitions T01-T12 per §8) + `evals/test_trajectory.py` (trajectory-level pytest assertions on tool sequence + args, not final text). 9/12 pass live (Rung 4+5 cases), 3 skipped (T01-T03, rungs 1-3 not built), T12 marked xfail (non-deterministic wrong-first-guess recovery). step_budget_breach tested. Groq free-tier TPD (100K) recharged daily — run tests once per day. Run with `python3 -m pytest evals/ -v`.
- Built `src/rungs/rung5_react.py` (hand-written THINK/ACT/OBSERVE loop, all 7
  tools, full instruction block, step budget = `config.STEP_BUDGET` = 5, forced
  `escalate_to_human` on budget exhaustion). `run(query, max_steps=None)` —
  `max_steps` override exists so evals can lower the budget.
- **Also created two SHARED files this round (flagged for merge safety):**
  - `src/rungs/base.py` — the `RungResult` dataclass (EXACT §6 contract) + a
    `Rung` ABC + `tool_definitions(names)` (OpenAI tool schemas, shared by
    Rungs 3/4/5). §11 nominally lists base.py under Phase 4 (Kilo). **Kilo must
    PULL this base.py, not recreate it, or Phase 4↔5 will merge-conflict on it.**
  - `src/instructions.py` — the §5 five-slot manual + `compose()` /
    `full_system_prompt()`. Needed by all rungs; Rung 5 uses the full block.
    Same coordination note: Phase 4 should consume this, not re-author it.
- DoD met via LIVE Groq calls: T06 (ORD-9821, rainy, restaurant silent) produced
  a genuine multi-step trace calling BOTH `get_weather` and `get_restaurant_status`
  (+ order status, driver GPS, policy); budget lowered to 2 correctly breached and
  force-escalated. Also mock-tested: terminal escalate, YELLOW `🟡 WRITE ACTION
  LOGGED` step, coupon cap held in code ($50→cap_exceeded).
- **WATCH (for Phase 6 evals):** the multi-factor T06 tends to exhaust even the
  full 5-step budget (spends all steps investigating, then force-escalates rather
  than issuing a coupon). This is realistic but means T06's "coupon ≤ $20" is
  vacuously true (no coupon). Eval authors: assert on the tool sequence (weather +
  restaurant before any coupon) and treat budget-breach as an acceptable outcome,
  or raise the budget for that case. temperature=0 so it's reproducible.
- **STILL MISSING FROM REPO (Phase 1, Kilo):** `requirements.txt` and `.gitignore`
  are untracked on `main` — not committed. I installed deps into `.venv` manually
  (openai, python-dotenv, numpy, scikit-learn). `.gitignore` absence means `.venv`/
  `.env` are NOT ignored; I staged only my source files explicitly (never `git add -A`).

- **2026-07-15 (Kilo Code, Track A):** Phase 4 complete — `src/rungs/base.py` (RungResult dataclass) + `src/rungs/rung4_workflow.py` (5-step fixed refund workflow per §6). LLM used for extraction (step 1: order ID via tool calling) and language (steps 4-5), NEVER for routing (step 3 is deterministic Python). Tested: cold food outside window → decline with no coupon; unknown order → error message. Fixed `RungMetrics` timing (moved from context-manager-with-return to explicit start/stop).

- **2026-07-15 (Kilo Code):** Phase 3 complete — `src/tools.py` with all 7 tools + TOOL_REGISTRY risk metadata + audit log. $20 cap hard-enforced in `issue_refund_coupon`. TF-IDF via scikit-learn. All signatures match §4 spec. Tested: coupon cap, delay-vs-quality retrieval asymmetry, unknown-ID errors.

### 2026-07-15 — Claude Code (Track B) — Phase 2 complete
- Built `src/config.py`, `src/llm.py`, `src/metrics.py`, `src/trace.py` per §2/§7.
  No other files touched (no `src/__init__.py`, no `requirements.txt` — those are
  Track A's Phase 1). `src` imports fine as a namespace package meanwhile.
- Groq pricing verified against https://groq.com/pricing (2026-07-15):
  **$0.59 / 1M input, $0.79 / 1M output** for `llama-3.3-70b-versatile`. In config.py.
- DoD met: live `llm.complete()` call against real Groq API returned reply + token
  counts (53 in / 33 out, 974 ms). Also validated via mock (tool-call JSON→dict
  normalization, temperature=0, cost math, trace shapes).
- **ACTION FOR TRACK A (Phase 1):** `requirements.txt` MUST include `openai` and
  `python-dotenv` (Phase 2 runtime deps — I pip-installed them into `.venv` but did
  not create requirements.txt). `.gitignore` MUST exclude `.venv/` and `.env`
  (both exist locally, untracked; I only staged my 4 src files + CLAUDE.md).
- **CONTRACT NOTES for Phase 4/5 (rungs, other track):**
  - `complete(messages, tools=None) -> LLMResponse`. `messages` are plain
    OpenAI-format dicts (Groq speaks that wire format natively).
  - `LLMResponse` fields: `content: str|None`, `tool_calls: list[ToolCall]`,
    `input_tokens`, `output_tokens`, `assistant_message: dict` (append to history),
    `raw`. `ToolCall` = `{id, name, arguments: dict}` — args already JSON-parsed.
  - To continue a tool-calling turn: append `resp.assistant_message`, then one
    `llm.tool_result_message(call.id, result_str)` per tool call, then call again.
  - `TraceStep(kind, content, tool, args, risk, observation)` in trace.py with
    `think()/act()/observe()/answer()` constructors. Kinds: THINK/ACT/OBSERVE/ANSWER
    only (no 5th kind); the 🟡 WRITE marker rides on `risk="YELLOW"`.
  - `metrics.RungMetrics()` is a context manager (times latency) with
    `.add_usage(resp)` and `.input_tokens/.output_tokens/.cost_usd/.cost_per(n)`.
  - `RungResult` is NOT defined here — it belongs to `rungs/base.py` (Phase 4).

- **2026-07-15 (Kilo Code):** Phase 1 complete. Created worktree `../ladder-kilo-p1`, scaffold dirs (`src/`, `evals/`, `data/`), and deterministic synthetic data for all 6 required scenarios. Verified JSON validity.

## Conventions
- No `print()` inside `src/` — return structured data.
- Every tool carries risk metadata in TOOL_REGISTRY.
- Guardrails enforced in code, not only in prompts.
- **If working in a parallel worktree round (see §0.5): do not deviate from documented
  function signatures without flagging it in Session Notes first.**
