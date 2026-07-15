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
- [ ] Phase 1 — scaffold + data
- [ ] Phase 2 — llm.py, config, metrics, trace
- [ ] Phase 3 — tools.py
- [ ] Phase 4 — rungs 1-4
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

## Conventions
- No `print()` inside `src/` — return structured data.
- Every tool carries risk metadata in TOOL_REGISTRY.
- Guardrails enforced in code, not only in prompts.
- **If working in a parallel worktree round (see §0.5): do not deviate from documented
  function signatures without flagging it in Session Notes first.**
