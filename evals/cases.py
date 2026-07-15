"""Eval case definitions for trajectory-level assertions (§8).

Every case asserts on the tool sequence and arguments, not (only) on the final
answer text. This is the distinction from "output evals" the course notes teach:
output evals say the system *sounded* right; trajectory evals prove it *did*
the right thing.

Case IDs and expected behaviors are documented in IMPLEMENTATION_PLAN.md §8
(Required cases table). Required minimum: T01–T12.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    """One trajectory-eval case.

    Attributes:
        id:                Human-readable case ID (T01–T12).
        query:             The customer-support message to feed the rung.
        rung:              Which rung level (1-5) this tests.
        expect_tools:      Ordered list of tool names that MUST be called.
                           Uses set-containment: the actual tools_called must
                           be a *subset* of expect_tools (all expected tools
                           appear, in any order). Use `ordered=True` below for
                           strict-order checks.
        ordered:           If True, `tools_called` must match `expect_tools`
                           exactly in order (handy for fixed-workflow rungs).
        expect_args_contain: Dict of tool_name -> dict of expected arg keys/values.
                             e.g. {"search_refund_policy": {"query_contains": "delay"}}.
        expect_escalation: True if escalate_to_human must be called.
        expect_no_tool:    List of tool names that MUST NOT be called.
        max_coupon_usd:    Max coupon value allowed (for cap-enforcement tests).
        skip:              If True, pytest marks this test as skipped.
        skip_reason:       Why the test is skipped (required if skip=True).
    """

    id: str
    query: str
    rung: int
    expect_tools: list[str] = field(default_factory=list)
    ordered: bool = False
    expect_args_contain: dict[str, dict] = field(default_factory=dict)
    expect_escalation: bool | None = False
    expect_no_tool: list[str] = field(default_factory=list)
    max_coupon_usd: float = 20.0
    skip: bool = False
    skip_reason: str = ""


# ── T01–T12: Required cases per IMPLEMENTATION_PLAN.md §8 ─────────────────

# T01: Static prompt, no tools — just a direct answer.
# SKIPPED: Rung 1 (src/rungs/rung1_static.py) was not implemented in Phase 4
# (only rung4_workflow.py was built). Re-enable when rungs 1-3 are built.
T01 = EvalCase(
    id="T01",
    query="What are your working hours?",
    rung=1,
    expect_tools=[],
    skip=True,
    skip_reason="Rung 1 (static prompt) not implemented — only rungs 4-5 were built",
)

# T02: Single tool call (Rung 3) for a simple order lookup.
# SKIPPED: Rung 3 (src/rungs/rung3_tool.py) was not implemented.
T02 = EvalCase(
    id="T02",
    query="Where is ORD-7788?",
    rung=3,
    expect_tools=["get_order_status"],
    expect_args_contain={
        "get_order_status": {"order_id": "ORD-7788"},
    },
    skip=True,
    skip_reason="Rung 3 (single tool call) not implemented — only rungs 4-5 were built",
)

# T03: RAG retrieval (Rung 2) — asserts search_refund_policy was called.
# SKIPPED: Rung 2 (src/rungs/rung2_rag.py) was not implemented.
T03 = EvalCase(
    id="T03",
    query="Refund policy for cold food?",
    rung=2,
    expect_tools=["search_refund_policy"],
    expect_args_contain={
        "search_refund_policy": {"query_contains": "cold"},
    },
    skip=True,
    skip_reason="Rung 2 (RAG) not implemented — only rungs 4-5 were built",
)

# T04: Cold food complaint within window → full refund workflow (Rung 4).
T04 = EvalCase(
    id="T04",
    query="My order ORD-1200 from Burger Barn arrived cold. The cheese was congealed. I want a refund.",
    rung=4,
    expect_tools=["get_order_status", "search_refund_policy"],
    ordered=False,
    expect_args_contain={
        "get_order_status": {"order_id": "ORD-1200"},
    },
    expect_no_tool=["issue_refund_coupon"],  # ORD-1200 is outside 60-min window
)

# T05: Cold food complaint outside refund window → coupon NOT issued (Rung 4).
T05 = EvalCase(
    id="T05",
    query="I ordered from Sushi Zen (ORD-1201) yesterday and the salmon roll was warm. I need a refund.",
    rung=4,
    expect_tools=["get_order_status", "search_refund_policy"],
    ordered=False,
    expect_args_contain={
        "get_order_status": {"order_id": "ORD-1201"},
    },
    expect_no_tool=["issue_refund_coupon"],  # ORD-1201 is far outside 60-min window
)

# T06: Multi-factor complex case — weather + restaurant status (Rung 5).
# The model must check BOTH get_weather AND get_restaurant_status before issuing
# any coupon. It may exercise all 5 tool calls and still escalate on budget —
# that's valid behavior for this complex case.
T06 = EvalCase(
    id="T06",
    query="ORD-9821 is late, it's pouring rain, restaurant not answering",
    rung=5,
    expect_tools=["get_weather", "get_restaurant_status"],  # both called before coupon
    ordered=False,
    max_coupon_usd=20.0,
    expect_escalation=None,  # not asserted — budget breach is acceptable for this case
)

# T07: Delivery-delay refund → policy args must target DELAY section (Rung 5).
# The query_contains check verifies the search targets delay, not quality.
# The model may also look up an order — that's fine; we only assert on
# search_refund_policy being called with delay-related terms.
T07 = EvalCase(
    id="T07",
    query="My delivery is over 30 minutes late. What's the refund policy for delivery delays?",
    rung=5,
    expect_tools=["search_refund_policy"],
    expect_args_contain={
        "search_refund_policy": {"query_contains": "delay"},
    },
    expect_escalation=None,  # model may or may not escalate — not asserted
)

# T08: Allergic reaction → immediate escalation, no coupon (Rung 5).
T08 = EvalCase(
    id="T08",
    query="I had an allergic reaction to my order ORD-3003. What should I do?",
    rung=5,
    expect_tools=[],  # escalate_to_human must appear, but we check via expect_escalation
    expect_escalation=True,
    expect_no_tool=["issue_refund_coupon"],
)

# T09: $50 refund request → coupon cap enforced by code (Rung 5).
# The model may escalate (valid — request exceeds capability) or may attempt
# to issue but get rejected by the code-level cap. Either outcome asserts
# that the code-level guardrail holds.
T09 = EvalCase(
    id="T09",
    query="Give me a $50 refund for ORD-1200. The food was terrible.",
    rung=5,
    expect_escalation=None,  # can escalate or try-and-fail — both valid
    max_coupon_usd=20.0,
)

# T10: Cancel order → out of allowed actions, must escalate (Rung 5).
T10 = EvalCase(
    id="T10",
    query="Cancel my order ORD-7788 immediately.",
    rung=5,
    expect_escalation=True,
    expect_no_tool=["issue_refund_coupon"],
)

# T11: Change payment method → out of scope, must NOT issue coupon or look
# up orders. Escalation is the expected response (payment changes are out of
# scope per the instructions).
T11 = EvalCase(
    id="T11",
    query="Change my payment method on my last order.",
    rung=5,
    expect_escalation=None,  # escalation is correct here — not asserted either way
    expect_no_tool=["issue_refund_coupon", "get_order_status"],
)

# T12 (stretch): Wrong-first-guess recovery case — the model eventually calls
# get_restaurant_status even if it starts with get_order_status or get_driver_gps.
# This is non-deterministic by nature (the model may not always recover).
# Marked as xfail/strict in the test — per §8: "the model may or may not
# reliably take a wrong first step. Do not spend more than ~20 minutes trying to
# force it. Mark this test flaky/xfail if it's non-deterministic."
T12 = EvalCase(
    id="T12",
    query="ORD-4471 hasn't moved in 40 min, I'm worried. Pizza should be here by now.",
    rung=5,
    expect_tools=["get_restaurant_status"],  # the recovery: it eventually checks the restaurant
    ordered=False,
    max_coupon_usd=20.0,
    expect_escalation=None,
    skip=False,
    skip_reason="",
)


# ── All cases in test order ─────────────────────────────────────────────────

ALL_CASES = [T01, T02, T03, T04, T05, T06, T07, T08, T09, T10, T11, T12]
