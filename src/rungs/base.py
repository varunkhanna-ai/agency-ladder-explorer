"""Shared rung interface + the RungResult contract.

Every rung (1-5) implements the same shape: a callable taking `(query: str)`
and returning a `RungResult`. That uniformity is what makes the cross-rung
comparison table in the UI possible (§6, §9).

`RungResult`'s fields are a FIXED CONTRACT (§0.5 / §6) — evals and the UI read
them by name. Do not rename or drop fields without flagging it in CLAUDE.md
Session Notes first.

This module also provides `tool_definitions()`, which builds OpenAI-format tool
schemas from a list of tool names. It lives here (not in any single rung)
because Rungs 3, 4, and 5 all expose tools and would otherwise duplicate the
schemas. The schemas describe the tools in `tools.py`; keep the two in sync.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..trace import TraceStep


@dataclass
class RungResult:
    """Uniform result returned by every rung. Fields are read by evals + UI.

    See §6 for the canonical field list — this matches it exactly.
    """

    rung_level: int
    rung_name: str
    final_answer: str
    trace: list[TraceStep]          # structured steps, never printed strings
    tools_called: list[str]         # ordered — evals assert on this
    tool_args: list[dict]           # ordered, parallel to tools_called
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    escalated: bool
    step_budget_breached: bool


class Rung(ABC):
    """Optional base class documenting the rung interface.

    Rungs may subclass this or simply expose a module-level `run(query)` that
    returns a `RungResult` — the evals/UI only depend on the callable shape and
    on `RungResult`. `level` and `name` identify the rung in the comparison
    table.
    """

    level: int
    name: str

    @abstractmethod
    def run(self, query: str) -> RungResult:  # pragma: no cover - interface
        ...


# ---------------------------------------------------------------------------
# OpenAI-format tool schemas (shared by all tool-using rungs)
# ---------------------------------------------------------------------------
#
# Descriptions/params mirror the behavior documented in §4 and implemented in
# tools.py. They are intentionally terse but unambiguous so the model routes
# correctly (e.g. delay vs. quality refund sections — see eval T07).

_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_order_status": {
        "description": (
            "Look up a DeliverEase order by its ID. Returns the order record "
            "(status, items, restaurant, delivery area, promised/placed times)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order ID, e.g. 'ORD-9821'.",
                }
            },
            "required": ["order_id"],
        },
    },
    "search_refund_policy": {
        "description": (
            "Search the refund policy document and return the single most "
            "relevant section. Use the customer's specific issue as the query "
            "(e.g. 'delivery delay' vs 'cold food quality') so you retrieve "
            "the correct section."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look up, e.g. 'delivery delay refund'.",
                }
            },
            "required": ["query"],
        },
    },
    "get_weather": {
        "description": (
            "Get current weather for a delivery area. Useful to explain a "
            "delay caused by conditions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "delivery_area": {
                    "type": "string",
                    "description": "Delivery area name, e.g. 'Koramangala'.",
                }
            },
            "required": ["delivery_area"],
        },
    },
    "get_driver_gps": {
        "description": (
            "Get the driver's live GPS status for an order (moving/stalled, "
            "ETA, distance). Do not reveal the driver's personal details."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order ID, e.g. 'ORD-9821'.",
                }
            },
            "required": ["order_id"],
        },
    },
    "get_restaurant_status": {
        "description": (
            "Get a restaurant's current status and prep time (to see whether "
            "the restaurant is backed up)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "restaurant_id": {
                    "type": "string",
                    "description": "Restaurant ID, e.g. 'R482'.",
                }
            },
            "required": ["restaurant_id"],
        },
    },
    "issue_refund_coupon": {
        "description": (
            "Issue a goodwill refund coupon to the customer. The maximum is "
            "$20; larger amounts are rejected by the system. Only issue after "
            "confirming the applicable policy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order ID."},
                "amount_usd": {
                    "type": "number",
                    "description": "Coupon amount in USD (max 20).",
                },
            },
            "required": ["order_id", "amount_usd"],
        },
    },
    "escalate_to_human": {
        "description": (
            "Hand the case to a human agent. Use for safety issues (allergic "
            "reaction, food poisoning), legal threats, or any request outside "
            "the allowed actions (e.g. cancelling an order, payment changes)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why this is being escalated.",
                }
            },
            "required": ["reason"],
        },
    },
}


def tool_definitions(tool_names: list[str]) -> list[dict[str, Any]]:
    """Return OpenAI-format tool definitions for the given tool names.

    Raises KeyError if a name has no schema (keeps tools.py and this in sync).
    """
    defs: list[dict[str, Any]] = []
    for name in tool_names:
        schema = _TOOL_SCHEMAS[name]
        defs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            }
        )
    return defs
