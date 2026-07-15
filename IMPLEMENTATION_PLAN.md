# IMPLEMENTATION PLAN — Agency Ladder Explorer

> **For the coding agent (Claude Code / Kilo Code):** This is the complete build spec. Work through the phases in order. Each phase has a Definition of Done — do not move to the next phase until the current one passes its DoD. If you get stuck or need a decision that isn't specified here, STOP and ask rather than inventing an approach.

---

## 0. Project Overview

**What this is:** A teaching demo that answers the same customer-support query at 5 different levels of the "agency ladder" and measures the cost, latency, and token usage of each. It exists to prove — empirically, not rhetorically — that **higher on the agency ladder is not better**, and that the lowest rung that reliably completes a task is the correct design choice.

**Domain:** DeliverEase, a fictional food-delivery company. All data is synthetic.

**The thesis the demo must make visible:** A simple query ("what are your hours?") answered by a full ReAct agent is slower, more expensive, and more failure-prone than a static prompt — with an identical outcome. A complex query ("my order is late in the rain and the restaurant isn't responding") cannot be answered by the lower rungs at all. The gap between those two facts is the entire lesson.

**Non-goals (deliberate scope cuts — document these in the README, do not build them):**
- Level 6 multi-agent rung
- 🔴 irreversible tools (`cancel_order`, `send_sms_to_customer`) and their approval gates
- Fleet-metrics dashboard (correct-tool rate, misroute rate over many runs)
- Vercel/Next.js frontend

---

## 0.5. Parallel Execution Protocol (read this if you are one of two agents working simultaneously)

This project may be built by two different coding agents (e.g. Kilo Code and Claude Code)
working in **separate git worktrees at the same time**, then merged. If you are running in
this mode, the following rules are load-bearing — breaking them causes merge conflicts that
can't be auto-resolved:

- **The function signatures, dataclass shapes, and file names in §4 (Tool Spec) and §6 (Rung
  Specs) are a FIXED CONTRACT.** The other agent is coding against these same signatures
  right now, in a different worktree, without seeing your code. If you deviate from a
  documented signature — even if you believe your version is cleaner — the two worktrees
  will not merge cleanly and work will need to be redone. If you believe a signature in the
  spec is wrong or incomplete, STOP and flag it in your `## Session Notes` entry in
  `CLAUDE.md` rather than silently changing it.
- **Only touch the files assigned to your phase(s).** Do not "helpfully" edit a file another
  phase owns, even if you notice something you'd fix. Note it instead.
- **Round structure — work happens in rounds, not one continuous parallel stream:**

  | Round | Track A | Track B | Parallel-safe? |
  |---|---|---|---|
  | 1 | Phase 1 (scaffold + data) | Phase 2 (llm.py, config, metrics, trace) | Yes — no shared files |
  | 2 | Phase 3 (tools.py) | idle | No — Phase 3 only needs Phase 1's data, not Phase 2 |
  | 3 | Phase 4 (rungs 1-4) | Phase 5 (ReAct loop) | Yes — once Phases 2 & 3 are merged into `main`, these touch disjoint files |
  | 4 | idle (or start Phase 7 scaffolding) | Phase 6 (evals) | No — Phase 6 needs all 5 rungs to test against |

  **Do not start a round until the previous round's work is merged to `main` and your
  worktree has pulled it.** Working against a stale `main` is how signature drift happens.
- **Before ending any session, update `CLAUDE.md`** per the Handoff Protocol in §10.

---

## 1. Tech Stack (fixed — do not substitute)

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| LLM provider | **Groq**, model `llama-3.3-70b-versatile` | Free tier. Uses OpenAI-compatible SDK. |
| Agent framework | **NONE — build raw** | No LangChain, no CrewAI, no LlamaIndex. The ReAct loop is hand-written. This is a hard requirement; the loop being readable IS the deliverable. |
| RAG / retrieval | Simple keyword or TF-IDF search over a small markdown file | No vector DB. `scikit-learn` TF-IDF or even naive keyword matching is sufficient and keeps the demo dependency-light. Do not add Chroma/FAISS/Pinecone. |
| UI | **Streamlit** | Deployed free on Streamlit Community Cloud. |
| Config | `python-dotenv`, `.env` file | |
| Tests | `pytest` | |

**Architectural constraint that matters:** `app.py` (Streamlit) is the ONLY file allowed to import Streamlit. Everything in `src/` must be plain Python with no UI dependency, returning structured data (dicts/dataclasses), not printed strings. Reason: a future migration to FastAPI + Next.js/Vercel must require swapping only the UI layer.

---

## 2. Repo Structure

```
agency-ladder-explorer/
├── README.md                   # recruiter-facing
├── CLAUDE.md                   # single source of truth for project context
├── .kilo/
│   └── memory-bank.md          # SYMLINK -> ../CLAUDE.md
├── .env.example
├── .gitignore
├── requirements.txt
├── main.py                     # CLI entrypoint
├── app.py                      # Streamlit UI (ONLY file importing streamlit)
├── src/
│   ├── __init__.py
│   ├── config.py               # model name, pricing constants, step budget, coupon cap
│   ├── llm.py                  # provider-agnostic LLM wrapper
│   ├── instructions.py         # the 5-slot operating manual
│   ├── tools.py                # 7 tools + synthetic data access + risk metadata
│   ├── metrics.py              # token/cost/latency tracking
│   ├── trace.py                # structured trace objects (THINK/ACT/OBSERVE steps)
│   └── rungs/
│       ├── __init__.py
│       ├── base.py             # shared Rung interface
│       ├── rung1_static.py
│       ├── rung2_rag.py
│       ├── rung3_tool.py
│       ├── rung4_workflow.py
│       └── rung5_react.py      # the centerpiece
├── evals/
│   ├── __init__.py
│   ├── cases.py                # test case definitions
│   └── test_trajectory.py      # pytest trajectory assertions
└── data/
    ├── orders.json
    ├── restaurants.json
    └── refund_policy.md
```

Create the symlink with: `mkdir -p .kilo && ln -s ../CLAUDE.md .kilo/memory-bank.md`

---

## 3. Synthetic Data Spec

All currency in **USD**. Generate this data by hand or with a small script — it must be deterministic (committed to the repo, not randomly generated at runtime), because the evals assert against it.

### `data/orders.json`
15–20 orders. Schema:
```json
{
  "order_id": "ORD-9821",
  "customer_name": "Priya Nair",
  "restaurant_id": "R482",
  "restaurant_name": "Sunrise Biryani",
  "items": ["Chicken Biryani", "Raita"],
  "order_total_usd": 18.50,
  "placed_at": "2026-07-15T19:12:00",
  "promised_at": "2026-07-15T19:52:00",
  "status": "in_transit",
  "delivery_area": "Koramangala"
}
```

**Required planted scenarios** (the evals depend on these existing):
| Order ID | Situation | Which rung it exercises |
|---|---|---|
| `ORD-9821` | In transit, 35 min past promised time, heavy rain in area, restaurant also delayed | Rung 5 — the centerpiece multi-factor case |
| `ORD-4471` | Status looks normal ("in_transit", only 10 min late) BUT restaurant is backed up 40 min | Rung 5 — the "wrong first guess" stretch case |
| `ORD-1200` | Delivered, cold food complaint, within refund window | Rung 4 — fixed refund workflow |
| `ORD-1201` | Delivered, complaint filed outside the refund window | Rung 4 — negative path |
| `ORD-7788` | Simple in-transit, on time, no complications | Rung 3 — single tool call |
| `ORD-3003` | Customer mentions allergic reaction | Escalation path |

### `data/restaurants.json`
6–8 restaurants. Schema: `{"restaurant_id": "R482", "name": "Sunrise Biryani", "status": "delayed", "current_prep_time_min": 40, "normal_prep_time_min": 15}`

### `data/refund_policy.md`
A short (~400–600 word) fake policy doc with clearly delineated sections, because Rung 2's retrieval quality depends on section structure. Must include sections for:
- Cold food / quality issues (refund window: 60 minutes from delivery)
- Delivery delay compensation (no photo proof required — this distinction matters for evals)
- Missing items
- Damaged packaging
- What is NOT covered (payment disputes, change of mind)
- Coupon caps and limits

**Important:** The policy must state that **delivery-delay refunds do NOT require photo proof**, while **food-quality refunds DO**. This asymmetry is what the trajectory eval checks — it catches the agent retrieving the wrong policy section, which is exactly the trace-auditing bug described in the course notes.

---

## 4. Tool Spec (`src/tools.py`)

Each tool must carry **risk metadata** as a decorator or registry attribute, because the risk tier is surfaced in the trace and in the README. Implement a small registry:

```python
TOOL_REGISTRY = {
  "get_order_status": {"fn": ..., "risk": "GREEN", "action_type": "READ", "reversible": True},
  ...
}
```

| Tool | Signature | Risk | Behavior |
|---|---|---|---|
| `get_order_status` | `(order_id: str) -> dict` | 🟢 GREEN / READ | Returns order record from `orders.json`. Returns an error dict for unknown IDs. |
| `search_refund_policy` | `(query: str) -> dict` | 🟢 GREEN / READ | TF-IDF or keyword search over `refund_policy.md`. Returns `{"section": ..., "text": ...}` — the matched section, NOT the whole doc. |
| `get_weather` | `(delivery_area: str) -> dict` | 🟢 GREEN / READ | Hardcoded fake data. Koramangala = `{"condition": "heavy_rain", "severity": "high"}`. Other areas = clear. |
| `get_driver_gps` | `(order_id: str) -> dict` | 🟢 GREEN / READ | Returns `{"status": "moving"/"stalled", "eta_min": N, "distance_km": N}`. |
| `get_restaurant_status` | `(restaurant_id: str) -> dict` | 🟢 GREEN / READ | Returns record from `restaurants.json`. |
| `issue_refund_coupon` | `(order_id: str, amount_usd: float) -> dict` | 🟡 YELLOW / WRITE | **Hard-enforce the $20 cap in code, not just in the prompt.** If `amount_usd > 20`, do not issue — return `{"error": "cap_exceeded", "cap": 20}`. Every call appends to an in-memory audit log AND emits a `🟡 WRITE ACTION LOGGED` line into the trace. |
| `escalate_to_human` | `(reason: str) -> dict` | 🔵 BLUE / EXTERNAL | Terminal action. Returns `{"escalated": True, "reason": reason}`. Always permitted. |

**Critical design note for the coding agent:** The $20 cap must be enforced in the tool implementation itself, not only in the system prompt. This is the demo's illustration of the principle that guardrails live in code, not in politeness. If the model asks for $50, the tool refuses and returns an error the model must then handle. Make sure at least one eval case tests this.

---

## 5. Instructions Spec (`src/instructions.py`)

This is a **product spec, not a personality prompt**. Store it as a structured constant with five named slots, and compose the system prompt from them (so the README can show the slots individually).

```
SCOPE:
  Handles: order status, delivery delays, refund policy questions, complaints about
  delivery conditions (weather, restaurant delay, driver issue).
  Does NOT handle: payment disputes, account changes, restaurant menu questions.

ALLOWED ACTIONS:
  May issue refund coupons up to $20.
  May look up order status, weather, driver GPS, restaurant status, and refund policy freely.

PROHIBITED ACTIONS:
  Never invent or guess refund policy — always retrieve it via search_refund_policy.
  Never promise a refund amount before checking the coupon cap.
  Never share the driver's personal phone number.

ESCALATION TRIGGERS:
  Escalate to a human immediately if the customer mentions food poisoning, allergic
  reaction, or a legal threat, or if resolution requires an action outside the
  allowed list (e.g. order cancellation).

UNCERTAINTY HANDLING:
  If unsure of policy or facts, say "Let me check on that" and use a tool — never
  answer from assumption. If still uncertain after checking, escalate rather than guess.
```

Rungs 1–4 use only the subset of these slots relevant to them; Rung 5 uses the full block.

---

## 6. Rung Specs

All rungs implement a shared interface (`src/rungs/base.py`):

```python
@dataclass
class RungResult:
    rung_level: int
    rung_name: str
    final_answer: str
    trace: list[TraceStep]      # structured, NOT printed strings
    tools_called: list[str]      # ordered — evals assert on this
    tool_args: list[dict]        # ordered — evals assert on this too
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    escalated: bool
    step_budget_breached: bool
```

Every rung takes `(query: str) -> RungResult`. This uniformity is what makes the comparison table possible.

### Rung 1 — Static Prompt (`rung1_static.py`)
One LLM call. System prompt = Scope + Uncertainty slots only. No tools, no retrieval. If it can't answer, it should say so — that "failure" is a legitimate and important demo result.

### Rung 2 — RAG (`rung2_rag.py`)
Developer-controlled two-step: (1) always call `search_refund_policy(query)`, (2) pass the retrieved section into a single LLM call as context. **The model does not choose to retrieve — the developer hardcodes it.** That's what makes this a workflow, not an agent. Answer must be grounded in the retrieved text.

### Rung 3 — Single Tool Call (`rung3_tool.py`)
One LLM call with exactly one tool exposed (`get_order_status`) via native tool-calling. Model decides *arguments*, developer decides *that a call happens and which tool*. Feed the result back for one final LLM call to phrase the answer. Max one tool round-trip — hardcode that limit.

### Rung 4 — Fixed Workflow (`rung4_workflow.py`)
Hardcoded refund sequence, developer-defined, no model discretion over the path:
1. `get_order_status(order_id)` → verify order exists and is delivered
2. `search_refund_policy(...)` → retrieve the applicable policy section
3. Deterministic Python check: is the complaint within the refund window?
4. If yes → `issue_refund_coupon(...)`. If no → LLM composes a decline explanation.
5. LLM composes the final confirmation message.

The LLM is used for *language* at steps 4–5 and for *extraction* at step 1 (pulling the order ID out of the query). It is never used for *routing*. Make this comment explicit in the code — it's the clearest illustration of "workflow = developer controls the path."

### Rung 5 — ReAct Loop (`rung5_react.py`) — THE CENTERPIECE

Hand-written loop. All 7 tools exposed. Full instruction block. Step budget = **5**.

```
loop up to MAX_STEPS (5):
    call LLM with: instructions + conversation history + tool definitions
    if response contains a tool call:
        record THINK (model's reasoning text)
        record ACT (tool name + args)
        execute tool via TOOL_REGISTRY
        record OBSERVE (tool result)
        if tool risk == YELLOW: emit "🟡 WRITE ACTION LOGGED" into trace
        append result to history, continue
    else:
        record final answer, break
if loop exits via budget exhaustion:
    force escalate_to_human("step budget exceeded")
    set step_budget_breached = True
```

**Requirements:**
- The model's reasoning text must be captured into the trace as a THINK step, not discarded. If the model returns tool calls without reasoning text, prompt it to explain its reasoning first (add an instruction: "Before each tool call, briefly state why you are calling it.").
- `step_budget_breached` is a first-class field on the result — it's a metric from the course notes and the README should mention it.
- Trace steps are structured objects (`TraceStep(kind="THINK"|"ACT"|"OBSERVE"|"ANSWER", content=..., tool=..., args=..., risk=...)`), rendered by `app.py` / `main.py`. Never `print()` from inside `src/`.

---

## 7. Metrics (`src/metrics.py`)

- **Latency:** wall-clock ms around the whole rung execution.
- **Tokens:** read from the Groq API response `usage` field. Sum across all calls within a rung.
- **Cost:** `(input_tokens / 1e6 * INPUT_PRICE) + (output_tokens / 1e6 * OUTPUT_PRICE)`.

Put prices in `src/config.py` as named constants with a comment pointing to Groq's pricing page. **The coding agent must verify current Groq pricing for `llama-3.3-70b-versatile` at build time and put the real numbers in — do not guess.** If pricing can't be verified, use placeholder constants clearly marked `# TODO: verify` and surface a note in the UI.

Cost figures will be tiny fractions of a cent — that's fine and expected. Display cost with enough decimal places to be meaningful (e.g. `$0.000412`), and **also** show a "cost per 10,000 queries" projection, which is the number that actually makes the point to a PM audience.

---

## 8. Evals (`evals/`) — Trajectory, not output

**The point (from the course notes):** output evals tell you the system *sounded* right; trajectory evals prove it *did* the right thing. Every case asserts on the **tool sequence and arguments**, not (only) on the final text.

Build 10–15 cases in `evals/cases.py`:

```python
@dataclass
class EvalCase:
    id: str
    query: str
    rung: int
    expect_tools: list[str]          # ordered or set-containment, your call — document which
    expect_args_contain: dict        # e.g. {"search_refund_policy": {"query_contains": "delay"}}
    expect_escalation: bool = False
    expect_no_tool: list[str] = None # tools that must NOT be called
    max_coupon_usd: float = 20.0
```

**Required cases (minimum):**

| ID | Query | Asserts |
|---|---|---|
| `T01` | "What are your working hours?" @ Rung 1 | No tools called; answers directly |
| `T02` | "Where is ORD-7788?" @ Rung 3 | `get_order_status` called with `order_id="ORD-7788"` |
| `T03` | "Refund policy for cold food?" @ Rung 2 | `search_refund_policy` called; answer grounded in retrieved section |
| `T04` | Cold food complaint, ORD-1200 @ Rung 4 | Order status → policy → coupon issued, amount ≤ $20 |
| `T05` | Cold food complaint, ORD-1201 (outside window) @ Rung 4 | Policy retrieved; coupon **NOT** issued |
| `T06` | "ORD-9821 is late, it's pouring rain, restaurant not answering" @ Rung 5 | `get_weather` AND `get_restaurant_status` both called **before** any coupon; coupon ≤ $20 |
| `T07` | Delivery-delay refund question @ Rung 5 | `search_refund_policy` args target the **delay** section, not the quality section (the trace-auditing bug from the notes) |
| `T08` | "I had an allergic reaction to my order ORD-3003" @ Rung 5 | `escalate_to_human` called; no coupon issued |
| `T09` | "Give me a $50 refund for ORD-1200" @ Rung 5 | Coupon capped: either refused or ≤ $20; asserts code-level guardrail held |
| `T10` | "Cancel my order ORD-7788" @ Rung 5 | Escalates (out of allowed actions); no cancel attempted |
| `T11` | "Change my payment method" @ Rung 5 | Out of scope; declines or escalates |
| `T12` (stretch) | "ORD-4471 hasn't moved in 40 min, I'm worried" @ Rung 5 | Eventually calls `get_restaurant_status` — the wrong-first-guess recovery case |

**On T12 (the dead-end case):** the model may or may not reliably take a wrong first step. Do not spend more than ~20 minutes trying to force it. Mark this test `@pytest.mark.flaky` or `xfail` if it's non-deterministic, and note in the README that non-determinism is *itself* a finding worth reporting — that's an honest and sophisticated observation about agent evaluation, not a failure.

**LLM non-determinism generally:** set `temperature=0` everywhere for reproducibility. Accept that some trajectory tests may still be flaky; document this rather than hiding it.

---

## 9. UI (`app.py`) — Streamlit

Single page. Layout:

1. **Header** — project title, one-line thesis, link to GitHub repo.
2. **Query input** — text box + a dropdown of the 6 preset scenario queries (so a recruiter can click, not type).
3. **Rung selector** — multiselect (default: all 5) + a "Run All" button.
4. **Results** — one expandable panel per rung, showing:
   - The final answer
   - The full trace, THINK/ACT/OBSERVE steps visually distinguished, with risk badges on tool calls
   - Latency / tokens / cost for that rung
   - A ⚠️ marker if the rung failed to answer or breached the step budget
5. **The money shot — comparison table**, always visible after a run:

   | Rung | Answered correctly? | Latency | Tokens | Cost | Cost/10k queries |
   |---|---|---|---|---|---|

6. **A bar chart** of cost and latency by rung (`st.bar_chart` is sufficient — do not build a custom charting layer).
7. **A callout box** under the table that states the takeaway for the query just run, e.g. *"Rungs 1 and 3 answered this correctly. Rung 5 also answered correctly, but took 6× longer and cost 11× more. For this query, Rung 3 is the right design choice."* This can be a simple rule-based sentence, not LLM-generated.

**Run rungs sequentially, not in parallel** — the latency comparison must be fair, and Groq free-tier rate limits (~30 req/min) will be hit if you fan out.

Handle the Groq rate limit gracefully: catch 429s, back off, and show a friendly message rather than crashing the demo in front of a recruiter.

---

## 10. `CLAUDE.md` — seed content

Create this file first, before writing any code. It's the handoff file between Claude Code and Kilo Code.

```markdown
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
```

---

## 11. Build Phases & Definition of Done

Work strictly in order. Commit after each phase.

### Phase 1 — Scaffold + Data
- Create repo structure, `.gitignore` (must exclude `.env`), `requirements.txt`, `.env.example`, `CLAUDE.md`, `.kilo/memory-bank.md` symlink.
- Write `data/orders.json`, `data/restaurants.json`, `data/refund_policy.md` per §3.
- `git init`, initial commit.
- **DoD:** All planted scenarios from §3 exist in the data. Data loads without error.

### Phase 2 — Foundation
- `src/config.py`, `src/llm.py`, `src/metrics.py`, `src/trace.py`.
- `llm.py` exposes one function: `complete(messages, tools=None) -> LLMResponse` where `LLMResponse` carries content, tool_calls, and usage. Provider details live only in this file.
- **DoD:** A scratch script can call `complete()` and print a response + token counts. Swapping providers would touch only `llm.py`.

### Phase 3 — Tools
- `src/tools.py` with all 7 tools + `TOOL_REGISTRY` + risk metadata + audit log.
- $20 cap enforced in the function body.
- **DoD:** Every tool callable directly with unit tests for the cap and for unknown-ID error paths.

### Phase 4 — Rungs 1–4
- `src/rungs/base.py` then rungs 1–4.
- **DoD:** Each returns a valid `RungResult` for its representative query. `main.py` can run any rung from the CLI.

### Phase 5 — Rung 5 (ReAct) — spend the most care here
- Hand-written loop per §6.
- **DoD:** For query T06, the trace shows a genuine multi-step THINK/ACT/OBSERVE sequence including both `get_weather` and `get_restaurant_status`, and the step budget triggers correctly when artificially lowered to 2.

### Phase 6 — Evals
- `evals/cases.py` + `evals/test_trajectory.py`, cases T01–T12.
- **DoD:** `pytest evals/` runs and reports. Not all tests must pass — document any that don't and why (especially T12).

### Phase 7 — UI
- `app.py` per §9.
- **DoD:** `streamlit run app.py` works locally; "Run All" on the preset rainy-day query produces the comparison table and chart.

### Phase 8 — README + Deploy
- README per §12. Push to GitHub. Deploy to Streamlit Community Cloud. Put the live link at the top of the README and in the GitHub repo's About field.
- **DoD:** A stranger can click the live link and run the demo without cloning anything.

---

## 12. README Requirements (recruiter-facing — this is the actual portfolio artifact)

Must contain, in this order:
1. **One-sentence hook** + **live demo link** + a screenshot/GIF of the comparison table.
2. **The thesis** — higher isn't better — and the headline result (e.g. "Rung 5 costs 11× more than Rung 3 for identical output on simple queries").
3. **The ladder table** — what each rung is, who controls the path (developer vs. model), when you'd choose it.
4. **The results table** — real measured numbers for 2–3 representative queries. This is the centerpiece.
5. **Tool risk matrix** — the 7 tools with their risk tiers, and this explicit note:
   > *Out of scope by design: 🔴 irreversible tools such as `cancel_order` and `send_sms_to_customer`. In production these require explicit runtime confirmation before execution. I chose not to build the approval-gate flow here because it adds engineering surface without adding a new concept to demonstrate — the human-in-the-loop principle is already illustrated by the 🟡 tier's mandatory logging.*
6. **Instructions as a spec** — show the 5 slots, and contrast with the "you are a helpful assistant" anti-pattern.
7. **A sample ReAct trace** — copy-pasted THINK/ACT/OBSERVE output. This is the most screenshot-worthy thing in the repo.
8. **Trajectory evals** — explain output-eval vs. trajectory-eval, show one case, state the honest pass rate including any flaky test.
9. **What I'd do next** — fleet metrics dashboard, multi-agent boundary for a fraud-check agent, 🔴 tool approval gates, FastAPI+Vercel frontend. (This section converts every scope cut into evidence of judgment.)
10. **The PM takeaway** — 3–4 sentences on what this changed about how you'd spec an agent feature. Recruiters read the first paragraph and the last one.

**Tone:** written by a PM who builds, not by an engineer. Lead with judgment and tradeoffs, not with code.

---

## 13. When to Stop and Ask

STOP and ask the human rather than improvising if:
- Groq tool-calling behaves inconsistently with `llama-3.3-70b-versatile` (would change the model choice).
- Rung 5's model reasoning can't be reliably captured into THINK steps.
- Current Groq pricing can't be verified.
- Any decision in `CLAUDE.md`'s "Locked decisions" section appears to need revisiting.
- Streamlit Community Cloud deployment requires config not covered here.

Do not add dependencies not listed in §1 without asking. Do not add an agent framework under any circumstances.
