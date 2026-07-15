"""The operating manual — a product spec, not a personality prompt (§5).

Stored as five named slots so the README can show them individually and each
rung can compose only the slots it needs:
  - Rungs 1-4 use the subset relevant to them.
  - Rung 5 (ReAct) uses the full block.

This is deliberately NOT "you are a helpful assistant." Every line is a scope
boundary, an allowed/prohibited action, an escalation trigger, or an
uncertainty rule — the anti-pattern contrast the README makes (§12.6).
"""

from __future__ import annotations

SCOPE = """SCOPE:
  Handles: order status, delivery delays, refund policy questions, complaints about
  delivery conditions (weather, restaurant delay, driver issue).
  Does NOT handle: payment disputes, account changes, restaurant menu questions."""

ALLOWED_ACTIONS = """ALLOWED ACTIONS:
  May issue refund coupons up to $20.
  May look up order status, weather, driver GPS, restaurant status, and refund policy freely."""

PROHIBITED_ACTIONS = """PROHIBITED ACTIONS:
  Never invent or guess refund policy — always retrieve it via search_refund_policy.
  Never promise a refund amount before checking the coupon cap.
  Never share the driver's personal phone number."""

ESCALATION_TRIGGERS = """ESCALATION TRIGGERS:
  Escalate to a human immediately if the customer mentions food poisoning, allergic
  reaction, or a legal threat, or if resolution requires an action outside the
  allowed list (e.g. order cancellation)."""

UNCERTAINTY = """UNCERTAINTY HANDLING:
  If unsure of policy or facts, say "Let me check on that" and use a tool — never
  answer from assumption. If still uncertain after checking, escalate rather than guess."""

# Ordered so `full_system_prompt()` reads top-to-bottom like the spec.
SLOTS: dict[str, str] = {
    "SCOPE": SCOPE,
    "ALLOWED_ACTIONS": ALLOWED_ACTIONS,
    "PROHIBITED_ACTIONS": PROHIBITED_ACTIONS,
    "ESCALATION_TRIGGERS": ESCALATION_TRIGGERS,
    "UNCERTAINTY": UNCERTAINTY,
}


def compose(*slot_names: str) -> str:
    """Compose a system prompt from the named slots, in the given order.

    Unknown slot names raise KeyError so a rung can't silently ship an empty
    prompt. With no arguments, returns the full block.
    """
    if not slot_names:
        return full_system_prompt()
    return "\n\n".join(SLOTS[name] for name in slot_names)


def full_system_prompt() -> str:
    """The complete five-slot block, used by Rung 5."""
    return "\n\n".join(SLOTS.values())
