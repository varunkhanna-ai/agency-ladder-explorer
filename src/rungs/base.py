"""Shared Rung interface.

Every rung returns a RungResult with the same shape (latency, tokens, cost,
trace) so the Streamlit comparison table can render them uniformly. This is
the fixed contract from IMPLEMENTATION_PLAN.md §6.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..trace import TraceStep


@dataclass
class RungResult:
    """Uniform result from any rung's `run(query: str)` call.

    Attributes:
        rung_level: 1 through 5.
        rung_name: Human-readable label (e.g. "Static Prompt").
        final_answer: The answer the model returned (or error text).
        trace: Structured THINK/ACT/OBSERVE/ANSWER steps.
        tools_called: Ordered list of tool names called (for trajectory evals).
        tool_args: Ordered list of argument dicts (for trajectory evals).
        latency_ms: Wall-clock milliseconds for the entire rung execution.
        input_tokens / output_tokens: Summed across all LLM calls.
        cost_usd: Computed from token counts using config.py prices.
        escalated: True if escalate_to_human was called.
        step_budget_breached: True if the rung exhausted its allotted steps
            (only meaningful for Rung 5; always False for rungs 1-4).
    """

    rung_level: int
    rung_name: str
    final_answer: str
    trace: list[TraceStep] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    tool_args: list[dict] = field(default_factory=list)
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    escalated: bool = False
    step_budget_breached: bool = False
