# Agency Ladder Explorer — Project Context

## What this is
A teaching demo that answers the same DeliverEase customer-support query at 5 rungs of the
agency ladder (static prompt → RAG → single tool call → fixed workflow → ReAct loop) and
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
- [ ] Phase 4 — rungs 1-4
- [x] Phase 5 — rung 5 (ReAct)
- [ ] Phase 6 — evals
- [ ] Phase 7 — Streamlit UI
- [ ] Phase 8 — README + deploy

## Handoff Protocol
Before ending any session (whether switching tools, or finishing a parallel worktree round):
1. Check off completed phases above. Only check a phase if its Definition of Done
   (IMPLEMENTATION_PLAN.md §11) is fully met — not "mostly working."
2. Add a dated entry under `## Session Notes` below (1-3 lines): what you built, any
   deviation from the spec and why, and anything the next agent should watch for.
3. Do not leave uncommitted changes. Commit with a message naming the phase.

## Session Notes
<!-- Newest entries at the top. Both Kilo Code and Claude Code append here. -->

### 2026-07-15 — Claude Code (Track B) — Phase 5 complete (ReAct loop)
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
