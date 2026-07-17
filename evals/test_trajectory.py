"""Trajectory-level evals — pytest assertions on tool sequence + args.

These tests run the rungs against the eval cases defined in cases.py and assert
on the *trajectory* (which tools were called, in what order, with what arguments)
rather than on the final answer text alone.

Per §8: "output evals tell you the system *sounded* right; trajectory evals
prove it *did* the right thing."

On LLM non-determinism: all rung calls use temperature=0, but some trajectory
tests (especially T12) may still be flaky. This is documented per §8.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the src/ directory is on the path so rung imports resolve.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from evals.cases import ALL_CASES, EvalCase  # noqa: E402

# ── Rung import helpers (lazy, per-case) ─────────────────────────────────────

# Rung modules keyed by level. We lazily import so missing rungs (1-3) only
# cause errors when a case actually tries to use them.
_RUNG_MODULES: dict[int, str] = {
    1: "src.rungs.rung1_static",
    2: "src.rungs.rung2_rag",
    3: "src.rungs.rung3_tool",
    4: "src.rungs.rung4_workflow",
    5: "src.rungs.rung5_react",
}


def _load_env():
    """Load .env from the project root so the Groq API key is available."""
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)


def _run_case(case: EvalCase):
    """Run a single eval case against its target rung.

    Returns the RungResult from the rung's run() function, or raises
    ImportError/ModuleNotFoundError if the rung module doesn't exist.
    """
    module_name = _RUNG_MODULES[case.rung]
    import importlib

    mod = importlib.import_module(module_name)
    return mod.run(case.query)


# ── Helper assertions ────────────────────────────────────────────────────────


def _assert_tools(result, case: EvalCase):
    """Verify the tool sequence (names only) matches the case expectations."""
    tools = result.tools_called

    if case.ordered:
        # Strict ordered match: every expected tool, exact order.
        expected = case.expect_tools
        for idx, expected_tool in enumerate(expected):
            if idx >= len(tools):
                pytest.fail(
                    f"Expected tool '{expected_tool}' at position {idx}, "
                    f"but only got {len(tools)} tools: {tools}"
                )
            actual = tools[idx]
            assert actual == expected_tool, (
                f"Tool order mismatch at position {idx}: "
                f"expected '{expected_tool}', got '{actual}'. "
                f"Full sequence: {tools}"
            )
    else:
        # Set containment: all expected tools appear somewhere.
        for expected_tool in case.expect_tools:
            assert expected_tool in tools, (
                f"Expected tool '{expected_tool}' not found in {tools}"
            )

    # Tools that must NOT appear.
    for forbidden in case.expect_no_tool:
        assert forbidden not in tools, (
            f"Tool '{forbidden}' should NOT have been called, but it was. "
            f"Tools called: {tools}"
        )

    # Escalation assertion (only when explicitly set, not None).
    if case.expect_escalation is not None:
        assert result.escalated == case.expect_escalation, (
            f"Escalation: expected {case.expect_escalation}, got {result.escalated}. "
            f"Tools: {tools}"
        )


def _assert_args(result, case: EvalCase):
    """Verify tool argument dicts contain expected keys/values.

    tool_args is an ordered list of dicts parallel to tools_called. Each dict
    maps parameter names (e.g. 'order_id', 'query', 'amount_usd') to values.

    Special key 'query_contains': checks that the query arg value contains
    a substring (for search_refund_policy trajectory evals like T07).
    """
    for tool_name, tool_args_dict in zip(result.tools_called, result.tool_args):
        if tool_name in case.expect_args_contain:
            expected = case.expect_args_contain[tool_name]
            for key, val in expected.items():
                if key == "query_contains":
                    actual_val = tool_args_dict.get("query")
                    assert isinstance(actual_val, str) and val.lower() in actual_val.lower(), (
                        f"Tool '{tool_name}' arg 'query' must contain '{val}', "
                        f"got: {actual_val!r}"
                    )
                else:
                    actual_val = tool_args_dict.get(key)
                    assert actual_val == val, (
                        f"Tool '{tool_name}' arg '{key}': expected {val!r}, "
                        f"got {actual_val!r}"
                    )


def _assert_cap(result, case: EvalCase):
    """Verify no coupon exceeds the max cap."""
    for args in result.tool_args:
        if isinstance(args, dict) and "amount_usd" in args:
            amount = args["amount_usd"]
            assert amount <= case.max_coupon_usd, (
                f"Coupon amount ${amount:.2f} exceeds max ${case.max_coupon_usd:.2f}. "
                f"Args: {args}"
            )


def _assert_t06_ordering(result):
    """T06: get_weather and get_restaurant_status must appear before any coupon.

    This is the 'multi-factor diagnosis' test — the agent should investigate
    both weather and restaurant before issuing compensation.
    """
    tools = result.tools_called
    if "issue_refund_coupon" not in tools:
        return  # no coupon at all → ok

    coupon_idx = tools.index("issue_refund_coupon")
    weather_idx = tools.index("get_weather") if "get_weather" in tools else -1
    restaurant_idx = tools.index("get_restaurant_status") if "get_restaurant_status" in tools else -1

    assert weather_idx >= 0, f"T06 requires get_weather, got: {tools}"
    assert restaurant_idx >= 0, f"T06 requires get_restaurant_status, got: {tools}"
    assert weather_idx < coupon_idx, (
        f"get_weather (idx {weather_idx}) must appear BEFORE "
        f"issue_refund_coupon (idx {coupon_idx})"
    )
    assert restaurant_idx < coupon_idx, (
        f"get_restaurant_status (idx {restaurant_idx}) must appear BEFORE "
        f"issue_refund_coupon (idx {coupon_idx})"
    )


# ── Parametrized test ────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", ALL_CASES, ids=[c.id for c in ALL_CASES])
def test_trajectory(case: EvalCase):
    """Main trajectory-eval test, parametrized across all 12 cases."""
    if case.skip:
        pytest.skip(case.skip_reason)

    _load_env()

    result = _run_case(case)

    # All results must be valid RungResults.
    assert result.rung_level == case.rung, (
        f"Rung level mismatch: expected {case.rung}, got {result.rung_level}"
    )
    assert result.final_answer, "Final answer must not be empty"
    assert result.latency_ms > 0, "Latency must be positive"

    # Tool-level assertions.
    _assert_tools(result, case)
    _assert_args(result, case)
    _assert_cap(result, case)

    # T06 special ordering check.
    if case.id == "T06":
        _assert_t06_ordering(result)


# ── T12: xfail / wrong-first-guess recovery ──────────────────────────────────

# T12 is inherently non-deterministic — the model may or may not take a wrong
# first step. Per §8: "Do not spend more than ~20 minutes trying to force it.
# Mark this test flaky or xfail if it's non-deterministic, and note in the
# README that non-determinism is itself a finding worth reporting."

# We run T12 through the standard test_trajectory parametrize (above), but
# also through this xfail variant that documents the known non-determinism.
@pytest.mark.xfail(
    reason=(
        "T12 is non-deterministic: the model does not always call "
        "get_restaurant_status after checking get_order_status/get_driver_gps. "
        "Per §8, this is a known finding — not all trajectories are "
        "deterministic even at temperature=0."
    ),
    strict=False,
)
@pytest.mark.parametrize("case", [ALL_CASES[11]], ids=["T12"])
def test_t12_xfail(case: EvalCase):
    """T12 — wrong-first-guess recovery (inherently non-deterministic).

    The model should eventually call get_restaurant_status even if it starts
    with get_order_status or get_driver_gps, but this is not guaranteed.
    """
    if case.skip:
        pytest.skip(case.skip_reason)

    _load_env()
    result = _run_case(case)

    assert result.rung_level == case.rung
    assert result.final_answer

    _assert_tools(result, case)
    _assert_args(result, case)
    _assert_cap(result, case)


# ── Step budget breach test ──────────────────────────────────────────────────


def test_step_budget_breach():
    """When max_steps=2, the ReAct loop force-escalates and sets the flag.

    This is NOT a test of the model's behavior — it's a contract test that
    the step budget enforcement in rung5_react.py works correctly regardless
    of what the model returns.
    """
    _load_env()

    import importlib

    mod = importlib.import_module("src.rungs.rung5_react")

    # A query complex enough that the model won't finish in 2 steps.
    result = mod.run(
        "ORD-9821 is 40 minutes late, it's foggy in SOMA, "
        "and the restaurant hasn't updated. I want a full refund.",
        max_steps=2,
    )

    assert result.step_budget_breached, (
        f"Expected step_budget_breached=True with max_steps=2, "
        f"got step_budget_breached={result.step_budget_breached}"
    )
    assert result.escalated, (
        f"Expected escalated=True when budget breached, got {result.escalated}"
    )
    assert "escalate_to_human" in result.tools_called, (
        f"Expected escalate_to_human in tools_called: {result.tools_called}"
    )
