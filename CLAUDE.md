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
- [x] Phase 4 — rungs 1-4
- [ ] Phase 5 — rung 5 (ReAct)
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

- **2026-07-15 (Kilo Code, Track A):** Phase 4 complete — `src/rungs/base.py` (RungResult dataclass) + `src/rungs/rung4_workflow.py` (5-step fixed refund workflow per §6). LLM used for extraction (step 1: order ID via tool calling) and language (steps 4-5), NEVER for routing (step 3 is deterministic Python). Tested: cold food outside window → decline with no coupon; unknown order → error message. Fixed `RungMetrics` timing (moved from context-manager-with-return to explicit start/stop).

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
