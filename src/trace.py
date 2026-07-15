"""Structured trace objects.

A rung's execution is recorded as an ordered list of `TraceStep`s — never as
printed strings. `main.py` and `app.py` are responsible for *rendering* these;
nothing in `src/` prints. This is what lets the same trace drive both a CLI and
a future web UI (see §6 and the "no print() in src/" convention in §10).

Step kinds (from §6):
  THINK   - the model's reasoning text before an action
  ACT     - a tool invocation (carries tool name, args, and risk tier)
  OBSERVE - the result returned by a tool
  ANSWER  - the model's final natural-language answer

The 🟡 "WRITE ACTION LOGGED" line that Rung 5 emits for YELLOW-tier tools is
represented as an OBSERVE/ACT step whose `risk` is "YELLOW"; the rung composes
the human-readable marker at render time. We deliberately do not add a fifth
kind, to keep this contract small and stable across the two build tracks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

StepKind = Literal["THINK", "ACT", "OBSERVE", "ANSWER"]

# Risk tiers mirror the tool registry in tools.py (§4). Kept as plain strings
# so trace.py has no dependency on tools.py.
RiskTier = Literal["GREEN", "YELLOW", "BLUE"]


@dataclass
class TraceStep:
    """One structured step in a rung's execution trace.

    Attributes:
        kind:    THINK | ACT | OBSERVE | ANSWER.
        content: Free-text payload. Reasoning for THINK, final answer for
                 ANSWER, a stringified/structured result for OBSERVE. May be
                 empty for a pure ACT step.
        tool:    Tool name, set on ACT (and echoed on the matching OBSERVE).
        args:    Tool arguments dict, set on ACT.
        risk:    Risk tier of the tool, set on ACT/OBSERVE for tool steps.
        observation: Optional structured (dict) form of a tool result, so the
                 UI can render fields without re-parsing `content`.
    """

    kind: StepKind
    content: str = ""
    tool: str | None = None
    args: dict[str, Any] | None = None
    risk: RiskTier | None = None
    observation: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for UI / logging. Omits None fields for compactness."""
        d: dict[str, Any] = {"kind": self.kind, "content": self.content}
        if self.tool is not None:
            d["tool"] = self.tool
        if self.args is not None:
            d["args"] = self.args
        if self.risk is not None:
            d["risk"] = self.risk
        if self.observation is not None:
            d["observation"] = self.observation
        return d


# --- Convenience constructors ----------------------------------------------
#
# Rungs use these instead of the raw dataclass so call sites read like the
# THINK/ACT/OBSERVE/ANSWER pseudocode in §6.


def think(content: str) -> TraceStep:
    """Record the model's reasoning text."""
    return TraceStep(kind="THINK", content=content)


def act(tool: str, args: dict[str, Any], risk: RiskTier | None = None) -> TraceStep:
    """Record a tool invocation."""
    return TraceStep(kind="ACT", content="", tool=tool, args=args, risk=risk)


def observe(
    tool: str,
    result: Any,
    risk: RiskTier | None = None,
    content: str | None = None,
) -> TraceStep:
    """Record a tool result. `content` defaults to str(result)."""
    return TraceStep(
        kind="OBSERVE",
        content=content if content is not None else str(result),
        tool=tool,
        risk=risk,
        observation=result,
    )


def answer(content: str) -> TraceStep:
    """Record the model's final answer."""
    return TraceStep(kind="ANSWER", content=content)


def trace_to_dicts(trace: list[TraceStep]) -> list[dict[str, Any]]:
    """Serialize a whole trace (e.g. for JSON export or the UI)."""
    return [step.to_dict() for step in trace]
