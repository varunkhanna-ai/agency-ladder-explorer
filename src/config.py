"""Central configuration: model, pricing, and hard limits.

All the numbers that the demo's thesis depends on live here as named
constants so they can be shown verbatim in the README and the UI. Nothing in
this module imports a provider SDK or Streamlit — it is pure data.
"""

from __future__ import annotations

import os

# --- Provider / model -------------------------------------------------------

# Groq, OpenAI-compatible endpoint. See §1 of IMPLEMENTATION_PLAN.md.
MODEL = "llama-3.3-70b-versatile"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Environment variable that holds the Groq API key. The key itself is never
# stored here; llm.py reads it from the environment (loaded from .env).
API_KEY_ENV_VAR = "GROQ_API_KEY"

# temperature=0 everywhere for reproducibility (see §8 — trajectory evals).
TEMPERATURE = 0.0

# --- Pricing ----------------------------------------------------------------
#
# Groq on-demand pricing for llama-3.3-70b-versatile, in USD per 1,000,000
# tokens. Verified 2026-07-15 against Groq's pricing page.
#   Source: https://groq.com/pricing
# If Groq changes these, update here and nowhere else — metrics.py reads them.
INPUT_PRICE_PER_M = 0.59   # USD per 1M input (prompt) tokens
OUTPUT_PRICE_PER_M = 0.79  # USD per 1M output (completion) tokens

# Flip to False and the UI should surface a "pricing unverified" note. Prices
# above were confirmed against the live pricing page at build time, so this is
# True. (See §7: use `# TODO: verify` placeholders only if unverifiable.)
PRICING_VERIFIED = True

# --- Hard limits (guardrails live in code, not just prompts) ----------------

# ReAct step budget: after this many loop iterations the loop force-escalates
# to a human and sets step_budget_breached=True (see §6, Rung 5).
STEP_BUDGET = 5

# Maximum value of a single refund coupon, enforced inside issue_refund_coupon
# in tools.py — not merely requested in the system prompt (see §4).
COUPON_CAP_USD = 20.0


def get_api_key() -> str | None:
    """Return the Groq API key from the environment, or None if unset.

    Kept here (rather than reading os.environ directly in llm.py) so the env
    var name is defined in exactly one place.
    """
    return os.environ.get(API_KEY_ENV_VAR)
