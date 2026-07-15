"""Rung 5 — the ReAct loop. The centerpiece (§6).

A hand-written THINK / ACT / OBSERVE loop. No agent framework — the loop being
readable IS the deliverable (§1). All 7 tools are exposed; the full five-slot
instruction block is used; the step budget is 5, after which the loop force-
escalates to a human.

Contrast with the lower rungs: here the *model* decides the path (which tools,
in what order, when to stop). That flexibility is exactly what costs more
latency, more tokens, and more failure surface — which is the whole point the
comparison table makes.
"""

from __future__ import annotations

import json
from typing import Any

from .. import config, instructions
from ..llm import complete, tool_result_message
from ..metrics import RungMetrics
from ..tools import TOOL_REGISTRY
from ..trace import TraceStep, act, answer, observe, think
from .base import RungResult, tool_definitions

RUNG_LEVEL = 5
RUNG_NAME = "ReAct Loop"

# All 7 tools are on the table for the agent (§6).
_ALL_TOOLS = list(TOOL_REGISTRY.keys())

# Appended to the instruction block so the model's reasoning lands in the
# message content (captured as a THINK step) rather than being discarded (§6).
_REACT_DIRECTIVE = (
    "You are the DeliverEase support agent. You have tools available. "
    "Before each tool call, briefly state in one sentence why you are calling "
    "it. Call tools one logical step at a time and use their results to decide "
    "the next step. When you have enough information, stop calling tools and "
    "give the customer a final answer."
)


def _system_prompt() -> str:
    return instructions.full_system_prompt() + "\n\n" + _REACT_DIRECTIVE


def _execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run a tool from the registry, defensively.

    The model chooses the tool name and args, so guard against a hallucinated
    tool name or malformed arguments rather than crashing the loop.
    """
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return {"error": "unknown_tool", "tool": name}
    try:
        return entry["fn"](**args)
    except TypeError as exc:
        return {"error": "bad_arguments", "tool": name, "detail": str(exc)}


def run(query: str, max_steps: int | None = None) -> RungResult:
    """Answer `query` via a hand-written ReAct loop.

    Args:
        query: The customer's message.
        max_steps: Overrides the step budget (config.STEP_BUDGET). Exposed so
            tests can lower it (e.g. to 2) and prove the budget-breach path.
    """
    budget = config.STEP_BUDGET if max_steps is None else max_steps

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": query},
    ]
    tools = tool_definitions(_ALL_TOOLS)

    trace: list[TraceStep] = []
    tools_called: list[str] = []
    tool_args: list[dict] = []
    escalated = False
    step_budget_breached = False
    final_answer = ""

    metrics = RungMetrics()
    with metrics:
        for _ in range(budget):
            resp = complete(messages, tools=tools)
            metrics.add_usage(resp)

            # No tool calls -> the model is done; record its final answer.
            if not resp.has_tool_calls:
                final_answer = resp.content or ""
                trace.append(answer(final_answer))
                break

            # THINK: capture the model's reasoning text (may accompany calls).
            if resp.content:
                trace.append(think(resp.content))

            # Keep the assistant turn (with its tool_calls) in history so the
            # tool results we append next line up by tool_call_id.
            messages.append(resp.assistant_message)

            terminal = False
            for call in resp.tool_calls:
                risk = TOOL_REGISTRY.get(call.name, {}).get("risk")

                # ACT
                trace.append(act(call.name, call.arguments, risk=risk))
                tools_called.append(call.name)
                tool_args.append(call.arguments)

                # Execute + OBSERVE
                result = _execute_tool(call.name, call.arguments)
                trace.append(observe(call.name, result, risk=risk))

                # YELLOW writes are logged into the trace (§4, §6).
                if risk == "YELLOW":
                    trace.append(
                        TraceStep(
                            kind="OBSERVE",
                            content="🟡 WRITE ACTION LOGGED",
                            tool=call.name,
                            risk="YELLOW",
                        )
                    )

                messages.append(
                    tool_result_message(call.id, json.dumps(result))
                )

                # escalate_to_human is terminal (§4): stop the loop and hand off.
                if call.name == "escalate_to_human":
                    escalated = True
                    terminal = True
                    reason = call.arguments.get("reason", "escalated to human")
                    final_answer = (
                        "I've escalated this to a human specialist who will "
                        f"follow up with you. Reason: {reason}"
                    )
                    trace.append(answer(final_answer))

            if terminal:
                break
        else:
            # Loop ran the full budget without a final answer -> force escalate.
            step_budget_breached = True
            escalated = True
            reason = "step budget exceeded"
            result = TOOL_REGISTRY["escalate_to_human"]["fn"](reason)
            trace.append(act("escalate_to_human", {"reason": reason}, risk="BLUE"))
            trace.append(observe("escalate_to_human", result, risk="BLUE"))
            tools_called.append("escalate_to_human")
            tool_args.append({"reason": reason})
            final_answer = (
                "I wasn't able to resolve this within my step budget, so I've "
                "escalated it to a human specialist."
            )
            trace.append(answer(final_answer))

    return RungResult(
        rung_level=RUNG_LEVEL,
        rung_name=RUNG_NAME,
        final_answer=final_answer,
        trace=trace,
        tools_called=tools_called,
        tool_args=tool_args,
        latency_ms=metrics.latency_ms,
        input_tokens=metrics.input_tokens,
        output_tokens=metrics.output_tokens,
        cost_usd=metrics.cost_usd,
        escalated=escalated,
        step_budget_breached=step_budget_breached,
    )
