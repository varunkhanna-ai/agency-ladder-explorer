"""Rung 4 — Fixed Refund Workflow.

A developer-defined, hardcoded sequence for processing cold-food refund
complaints. The model has NO discretion over the path — it is used for
*extraction* (step 1: pulling the order ID from the query) and for *language*
(steps 4-5: composing the decline or confirmation message). It is never used
for *routing* (step 3 is deterministic Python).

This is the clearest illustration of "workflow = developer controls the path."
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import config, llm, metrics, tools, trace
from .base import RungResult

RUNG_LEVEL = 4
RUNG_NAME = "Fixed Workflow"

# The refund window for cold food / quality complaints, in minutes.
# Source: data/refund_policy.md §1 — 60 minutes from delivery.
_COLD_FOOD_REFUND_WINDOW_MINUTES = 60

# System prompt for step 1: extract the order ID from the query.
_EXTRACTION_SYSTEM_PROMPT = (
    "You are an order-support assistant. Your ONLY job is to extract the "
    "customer's order ID from their message and call get_order_status with "
    "that ID. Do not answer the query. Do not call any other function. "
    "If you cannot find an order ID, still call get_order_status with "
    "whatever you find."
)

# System prompt for step 2: policy retrieval. We give the model a focused
# query string for the policy search, but the actual search is deterministic
# (we call search_refund_policy ourselves based on the query_type).
_POLICY_SYSTEM_PROMPT = (
    "You are a policy-search assistant. Your ONLY job is to determine what "
    "type of complaint the customer is making. Return EXACTLY one word from "
    "this list: cold-food, missing-item, damaged-packaging, delivery-delay. "
    "If you are unsure, say cold-food."
)

# System prompt for step 4 (decline) and step 5 (confirmation): language-only.
_DECLINE_SYSTEM_PROMPT = (
    "You are a DeliverEase customer-support agent. Compose a polite, "
    "sympathetic decline message. Explain that the refund window has expired "
    "per our policy. Do not make promises you cannot keep."
)

_CONFIRMATION_SYSTEM_PROMPT = (
    "You are a DeliverEase customer-support agent. Compose a brief, friendly "
    "confirmation message telling the customer their refund coupon has been "
    "issued. Include the coupon amount."
)

# The "now" time used for window calculations. Overridable in tests.
# We use a fixed reference time since all synthetic order dates are relative.
_FIXED_NOW = datetime(2026, 7, 15, 20, 0, 0, tzinfo=timezone.utc)


def _parse_iso(dt_str: str) -> datetime:
    """Parse an ISO-8601 string (naive or tz-aware) into a tz-aware UTC datetime."""
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _extract_order_id(query: str) -> tuple[str | None, dict[str, Any], llm.LLMResponse]:
    """Step 1: use the LLM to extract the order ID from the user query.

    Returns (order_id | None, order_result, llm_response).
    If the LLM returns tool calls for get_order_status, we execute them.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    tool_defs = [
        {
            "type": "function",
            "function": {
                "name": "get_order_status",
                "description": "Get the status and details of a food delivery order.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "The order ID, e.g. ORD-9821.",
                        }
                    },
                    "required": ["order_id"],
                },
            },
        }
    ]

    resp = llm.complete(messages, tools=tool_defs)

    # If the model called get_order_status, execute it
    order_id: str | None = None
    order_result: dict[str, Any] = {"error": "no_tool_call"}

    for call in resp.tool_calls:
        if call.name == "get_order_status":
            order_id = call.arguments.get("order_id")
            order_result = tools.get_order_status(order_id)
            break

    # Fallback: if no tool call, try to grep an order ID from the query text
    if order_id is None:
        import re

        m = re.search(r"ORD-\d{4}", query)
        if m:
            order_id = m.group(0)
            order_result = tools.get_order_status(order_id)

    return order_id, order_result, resp


def _check_refund_window(order_result: dict[str, Any]) -> bool:
    """Step 3: deterministic Python check — is the complaint within the refund window?

    The refund window is 60 minutes from delivery (cold food / quality policy).
    We use the promised_at time as a proxy for delivery time since our data
    does not have an explicit delivered_at field.

    Returns True if within window, False otherwise.
    """
    if "error" in order_result:
        return False

    promised_at = _parse_iso(order_result["promised_at"])
    elapsed_minutes = (_FIXED_NOW - promised_at).total_seconds() / 60
    return elapsed_minutes <= _COLD_FOOD_REFUND_WINDOW_MINUTES


def run(query: str) -> RungResult:
    """Execute the fixed refund workflow for a customer support query.

    Returns a RungResult with trace, metrics, and the final answer.
    """
    m = metrics.RungMetrics()
    trace_steps: list[trace.TraceStep] = []
    tools_called: list[str] = []
    tool_args_list: list[dict[str, Any]] = []
    escalated = False
    final_answer: str = ""

    m.start()

    # ---------------------------------------------------------------
    # Step 1: Extract order ID and get order status (LLM for extraction)
    # ---------------------------------------------------------------
    order_id, order_result, ext_resp = _extract_order_id(query)

    # Record TRACE: THINK (model reasoning)
    if ext_resp.content:
        trace_steps.append(trace.think(ext_resp.content))

    # Record TRACE: ACT + OBSERVE for get_order_status
    risk = tools.TOOL_REGISTRY["get_order_status"]["risk"]
    act_step = trace.act("get_order_status", {"order_id": order_id}, risk=risk)
    trace_steps.append(act_step)
    tools_called.append("get_order_status")
    tool_args_list.append({"order_id": order_id})
    obs_step = trace.observe("get_order_status", order_result, risk=risk)
    trace_steps.append(obs_step)

    m.add_usage(ext_resp)

    # Error: unknown order
    if "error" in order_result:
        final_answer = (
            f"I could not find order {order_id}. Please double-check the "
            "order ID and try again."
        )
        trace_steps.append(trace.answer(final_answer))
        m.stop()
        return RungResult(
            rung_level=RUNG_LEVEL,
            rung_name=RUNG_NAME,
            final_answer=final_answer,
            trace=trace_steps,
            tools_called=tools_called,
            tool_args=tool_args_list,
            latency_ms=m.latency_ms,
            input_tokens=m.input_tokens,
            output_tokens=m.output_tokens,
            cost_usd=m.cost_usd,
            escalated=False,
            step_budget_breached=False,
        )

    # ---------------------------------------------------------------
    # Step 2: Retrieve the applicable policy section (deterministic)
    # ---------------------------------------------------------------
    # Use LLM for extraction (not routing) — incorporate the query context
    # into the policy search string.
    policy_query = (
        f"Customer complaint: {query}. Order status: {order_result.get('status')}. "
        "Find the refund policy section that applies to this situation."
    )

    policy_result = tools.search_refund_policy(policy_query)
    risk_policy = tools.TOOL_REGISTRY["search_refund_policy"]["risk"]

    trace_steps.append(
        trace.act(
            "search_refund_policy",
            {"query": policy_query},
            risk=risk_policy,
        )
    )
    tools_called.append("search_refund_policy")
    tool_args_list.append({"query": policy_query})
    trace_steps.append(
        trace.observe("search_refund_policy", policy_result, risk=risk_policy)
    )

    # ---------------------------------------------------------------
    # Step 3: Deterministic Python check — is the complaint within the refund window?
    # (NO model discretion over routing)
    # ---------------------------------------------------------------
    within_window = _check_refund_window(order_result)

    if within_window:
        # ---------------------------------------------------------------
        # Step 4 (yes): Issue refund coupon
        # ---------------------------------------------------------------
        coupon_amount = min(
            order_result.get("order_total_usd", 0), config.COUPON_CAP_USD
        )
        coupon_result = tools.issue_refund_coupon(order_id, coupon_amount)
        risk_coupon = tools.TOOL_REGISTRY["issue_refund_coupon"]["risk"]

        trace_steps.append(
            trace.act(
                "issue_refund_coupon",
                {"order_id": order_id, "amount_usd": coupon_amount},
                risk=risk_coupon,
            )
        )
        tools_called.append("issue_refund_coupon")
        tool_args_list.append({"order_id": order_id, "amount_usd": coupon_amount})
        trace_steps.append(
            trace.observe("issue_refund_coupon", coupon_result, risk=risk_coupon)
        )

        if "error" in coupon_result:
            # Coupon cap exceeded — compose a friendly message
            final_answer = (
                f"I was unable to issue a ${coupon_amount:.2f} coupon for "
                f"order {order_id} because it exceeds our ${config.COUPON_CAP_USD:.2f} "
                "refund cap. However, I can issue a $20 coupon. Would you like me to?"
            )
            trace_steps.append(trace.answer(final_answer))
            m.stop()
            return RungResult(
                rung_level=RUNG_LEVEL,
                rung_name=RUNG_NAME,
                final_answer=final_answer,
                trace=trace_steps,
                tools_called=tools_called,
                tool_args=tool_args_list,
                latency_ms=m.latency_ms,
                input_tokens=m.input_tokens,
                output_tokens=m.output_tokens,
                cost_usd=m.cost_usd,
                escalated=False,
                step_budget_breached=False,
            )

        # ---------------------------------------------------------------
        # Step 5 (yes): LLM composes the final confirmation message
        # ---------------------------------------------------------------
        confirm_messages: list[dict[str, Any]] = [
            {"role": "system", "content": _CONFIRMATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "order_id": order_id,
                        "amount_usd": coupon_amount,
                        "coupon_result": coupon_result,
                        "policy_section": policy_result.get("section"),
                        "policy_text": policy_result.get("text"),
                    }
                ),
            },
        ]
        confirm_resp = llm.complete(confirm_messages)
        m.add_usage(confirm_resp)
        final_answer = confirm_resp.content or ""
        trace_steps.append(trace.answer(final_answer))

        m.stop()
        return RungResult(
            rung_level=RUNG_LEVEL,
            rung_name=RUNG_NAME,
            final_answer=final_answer,
            trace=trace_steps,
            tools_called=tools_called,
            tool_args=tool_args_list,
            latency_ms=m.latency_ms,
            input_tokens=m.input_tokens,
            output_tokens=m.output_tokens,
            cost_usd=m.cost_usd,
            escalated=False,
            step_budget_breached=False,
        )

    else:
        # ---------------------------------------------------------------
        # Step 4 (no): LLM composes a decline explanation
        # ---------------------------------------------------------------
        elapsed = int(
            (_FIXED_NOW - _parse_iso(order_result["promised_at"])).total_seconds()
            / 60
        )
        decline_messages: list[dict[str, Any]] = [
            {"role": "system", "content": _DECLINE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "order_id": order_id,
                        "status": order_result.get("status"),
                        "elapsed_minutes": elapsed,
                        "refund_window_minutes": _COLD_FOOD_REFUND_WINDOW_MINUTES,
                        "policy_section": policy_result.get("section"),
                        "policy_text": policy_result.get("text"),
                    }
                ),
            },
        ]
        decline_resp = llm.complete(decline_messages)
        m.add_usage(decline_resp)
        final_answer = decline_resp.content or ""
        trace_steps.append(trace.answer(final_answer))

        m.stop()
        return RungResult(
            rung_level=RUNG_LEVEL,
            rung_name=RUNG_NAME,
            final_answer=final_answer,
            trace=trace_steps,
            tools_called=tools_called,
            tool_args=tool_args_list,
            latency_ms=m.latency_ms,
            input_tokens=m.input_tokens,
            output_tokens=m.output_tokens,
            cost_usd=m.cost_usd,
            escalated=False,
            step_budget_breached=False,
        )
