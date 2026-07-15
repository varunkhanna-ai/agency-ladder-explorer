"""Token / cost / latency accounting.

The demo's whole point is the comparison table, so measurement lives in one
place. Costs are computed from the prices in config.py; nothing here hardcodes
a number. Provider details (where `usage` comes from) live in llm.py — this
module only consumes plain integers.

Definitions (from §7):
  latency : wall-clock milliseconds around the whole rung execution.
  tokens  : summed from every LLM call's `usage` within a rung.
  cost    : (in/1e6 * INPUT_PRICE) + (out/1e6 * OUTPUT_PRICE).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import config


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    """USD cost for a given token count, using config.py prices."""
    return (
        input_tokens / 1_000_000 * config.INPUT_PRICE_PER_M
        + output_tokens / 1_000_000 * config.OUTPUT_PRICE_PER_M
    )


def cost_per_n(cost_usd: float, n_queries: int) -> float:
    """Project a single-query cost out to `n` queries.

    The "cost per 10,000 queries" figure (§7) is the number that actually
    lands with a PM audience, since per-query cost is a sub-cent fraction.
    """
    return cost_usd * n_queries


@dataclass
class Usage:
    """Token counts from one or more LLM calls."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class RungMetrics:
    """Accumulates tokens across a rung's LLM calls and times the whole run.

    Usage in a rung::

        m = RungMetrics()
        with m:                      # starts the wall-clock timer
            resp = complete(messages)
            m.add(resp)              # sum this call's usage
            ...
        # after the `with` block, m.latency_ms is populated
        RungResult(
            latency_ms=m.latency_ms,
            input_tokens=m.input_tokens,
            output_tokens=m.output_tokens,
            cost_usd=m.cost_usd,
            ...
        )
    """

    def __init__(self) -> None:
        self._usage = Usage()
        self._start: float | None = None
        self.latency_ms: int = 0

    # -- timing (context manager) -------------------------------------------

    def __enter__(self) -> "RungMetrics":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.stop()
        return False  # never suppress exceptions

    def start(self) -> None:
        self._start = time.perf_counter()

    def stop(self) -> int:
        """Freeze latency_ms and return it. Safe to call without start()."""
        if self._start is not None:
            self.latency_ms = int((time.perf_counter() - self._start) * 1000)
        return self.latency_ms

    # -- token accumulation --------------------------------------------------

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Add raw token counts from one LLM call."""
        self._usage.input_tokens += input_tokens
        self._usage.output_tokens += output_tokens

    def add_usage(self, obj: object) -> None:
        """Add usage from anything carrying `input_tokens`/`output_tokens`.

        Accepts an `LLMResponse` (from llm.py), a `Usage`, or any object with
        those two integer attributes — so rungs can pass the response object
        directly without reaching into provider internals.
        """
        self.add(
            getattr(obj, "input_tokens"),
            getattr(obj, "output_tokens"),
        )

    # -- readouts ------------------------------------------------------------

    @property
    def input_tokens(self) -> int:
        return self._usage.input_tokens

    @property
    def output_tokens(self) -> int:
        return self._usage.output_tokens

    @property
    def total_tokens(self) -> int:
        return self._usage.total_tokens

    @property
    def cost_usd(self) -> float:
        return compute_cost(self._usage.input_tokens, self._usage.output_tokens)

    def cost_per(self, n_queries: int) -> float:
        return cost_per_n(self.cost_usd, n_queries)
