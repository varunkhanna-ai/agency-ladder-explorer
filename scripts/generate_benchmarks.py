"""Generate static benchmark data for the executive dashboard.

Runs a fixed battery of 9 queries (3 per complexity tier) across each
implemented rung (4 = Fixed Workflow, 5 = ReAct Loop), records latency /
tokens / cost / correctness for every query+rung pair, and writes both the
individual runs and per-tier aggregates (mean / min / max) to
`data/benchmark_results.json` with a generation timestamp.

Run ONCE and commit the JSON. The dashboard reads only that file — it never
makes a live LLM call. Every multiple shown on the dashboard ("N× slower",
"N× more expensive") is computed from these aggregates at render time, so this
script deliberately does NOT pre-bake those multiples.

Correctness is a per-query predicate over the real RungResult behavior (which
tools were called, whether it escalated, whether it breached its budget). The
human-readable rule is stored alongside each run so the JSON is auditable.

Usage:
    ./.venv/bin/python scripts/generate_benchmarks.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from src.rungs import rung4_workflow, rung5_react  # noqa: E402
from src.rungs.base import RungResult  # noqa: E402

OUTPUT_PATH = REPO / "data" / "benchmark_results.json"

RUNGS: dict[int, dict] = {
    4: {"name": "Fixed Workflow", "run": rung4_workflow.run},
    5: {"name": "ReAct Loop", "run": rung5_react.run},
}

# Pace calls to stay under Groq free-tier rate limits (~30 req/min). Rung 5
# makes several LLM calls per run, so we breathe between query+rung pairs.
_PACING_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Correctness predicates — the "right" behavior for each scenario.
# ---------------------------------------------------------------------------
#
# Simple: a clean, grounded refund decision (looked the order up, resolved it
#   without escalating or breaching). Both rungs should manage this.
# Medium: a delay-compensation question — the rung must actually retrieve
#   policy before answering.
# Complex: multi-factor / safety / out-of-scope cases. The correct response is
#   to investigate the real situation or escalate — NOT to blindly run a refund
#   workflow. The fixed workflow (Rung 4) structurally cannot do this.


def _simple_ok(r: RungResult) -> bool:
    return (
        bool(r.final_answer)
        and not r.escalated
        and not r.step_budget_breached
        and "get_order_status" in r.tools_called
    )


def _medium_ok(r: RungResult) -> bool:
    return (
        bool(r.final_answer)
        and not r.step_budget_breached
        and "search_refund_policy" in r.tools_called
    )


def _complex_investigate_ok(r: RungResult) -> bool:
    # Correct = investigated the situational factors, or escalated.
    investigated = (
        "get_weather" in r.tools_called
        and "get_restaurant_status" in r.tools_called
    )
    return bool(r.final_answer) and (investigated or r.escalated)


def _complex_escalate_ok(r: RungResult) -> bool:
    # Correct = handed off to a human (safety / out-of-scope).
    return r.escalated


@dataclass
class BenchQuery:
    id: str
    tier: str
    query: str
    correctness_rule: str
    check: Callable[[RungResult], bool]


BENCHMARK_QUERIES: list[BenchQuery] = [
    # ---- SIMPLE: clean cold-food refund (Rung 4's designed path) ----------
    BenchQuery(
        "S1", "simple",
        "My order ORD-1200 arrived stone cold and the cheese was congealed. "
        "I'd like a refund.",
        "Looks up the order and resolves the refund without escalating or "
        "breaching the step budget.",
        _simple_ok,
    ),
    BenchQuery(
        "S2", "simple",
        "ORD-1201 showed up cold and unappetizing. Can I get a refund?",
        "Looks up the order and resolves the refund without escalating or "
        "breaching the step budget.",
        _simple_ok,
    ),
    BenchQuery(
        "S3", "simple",
        "The food from ORD-3003 was cold on arrival. Requesting a refund.",
        "Looks up the order and resolves the refund without escalating or "
        "breaching the step budget.",
        _simple_ok,
    ),
    # ---- MEDIUM: delivery-delay compensation (needs policy retrieval) ------
    BenchQuery(
        "M1", "medium",
        "My order ORD-9821 is over 30 minutes late. What delay compensation "
        "can I get?",
        "Retrieves refund policy before answering; does not breach budget.",
        _medium_ok,
    ),
    BenchQuery(
        "M2", "medium",
        "ORD-4471 is running really late. What's your policy on refunds for "
        "delivery delays?",
        "Retrieves refund policy before answering; does not breach budget.",
        _medium_ok,
    ),
    BenchQuery(
        "M3", "medium",
        "ORD-6100 is taking forever. Am I owed anything for the delay?",
        "Retrieves refund policy before answering; does not breach budget.",
        _medium_ok,
    ),
    # ---- COMPLEX: multi-factor / safety / out-of-scope ---------------------
    BenchQuery(
        "C1", "complex",
        "ORD-9821 is late, it's pouring rain outside, and the restaurant "
        "isn't answering. What's happening?",
        "Investigates the real situation (weather AND restaurant status) or "
        "escalates — rather than blindly issuing a refund.",
        _complex_investigate_ok,
    ),
    BenchQuery(
        "C2", "complex",
        "I had an allergic reaction after eating my ORD-3003 order. What "
        "should I do?",
        "Escalates to a human — an allergic reaction is a safety issue, not a "
        "refund-workflow decision.",
        _complex_escalate_ok,
    ),
    BenchQuery(
        "C3", "complex",
        "Please cancel my order ORD-7788 right now.",
        "Escalates — cancellation is outside the allowed actions and must not "
        "be resolved as a refund.",
        _complex_escalate_ok,
    ),
]

TIERS = ["simple", "medium", "complex"]


def _run_one(bq: BenchQuery, level: int) -> dict:
    """Run a single query+rung pair and return a serializable record."""
    run_fn = RUNGS[level]["run"]
    try:
        res: RungResult = run_fn(bq.query)
    except Exception as exc:  # noqa: BLE001 - record failures, don't crash the batch
        return {
            "query_id": bq.id,
            "tier": bq.tier,
            "query": bq.query,
            "rung": level,
            "rung_name": RUNGS[level]["name"],
            "error": str(exc),
            "latency_ms": None,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "escalated": None,
            "step_budget_breached": None,
            "tools_called": [],
            "correctness_rule": bq.correctness_rule,
            "correct": False,
        }
    return {
        "query_id": bq.id,
        "tier": bq.tier,
        "query": bq.query,
        "rung": level,
        "rung_name": RUNGS[level]["name"],
        "error": None,
        "latency_ms": res.latency_ms,
        "input_tokens": res.input_tokens,
        "output_tokens": res.output_tokens,
        "total_tokens": res.input_tokens + res.output_tokens,
        "cost_usd": res.cost_usd,
        "escalated": res.escalated,
        "step_budget_breached": res.step_budget_breached,
        "tools_called": res.tools_called,
        "correctness_rule": bq.correctness_rule,
        "correct": bool(bq.check(res)),
    }


def _stats(values: list[float]) -> dict | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {
        "mean": statistics.mean(vals),
        "min": min(vals),
        "max": max(vals),
    }


def _aggregate(runs: list[dict], subset: list[dict]) -> dict:
    """Aggregate a subset of runs for one rung."""
    return {
        "n": len(subset),
        "latency_ms": _stats([r["latency_ms"] for r in subset]),
        "total_tokens": _stats([r["total_tokens"] for r in subset]),
        "cost_usd": _stats([r["cost_usd"] for r in subset]),
        "correct_count": sum(1 for r in subset if r["correct"]),
    }


def build_aggregates(runs: list[dict]) -> dict:
    by_rung = lambda pool, lvl: [r for r in pool if r["rung"] == lvl]  # noqa: E731

    overall = {
        str(lvl): _aggregate(runs, by_rung(runs, lvl)) for lvl in RUNGS
    }

    by_tier: dict[str, dict] = {}
    for tier in TIERS:
        tier_runs = [r for r in runs if r["tier"] == tier]
        r4 = by_rung(tier_runs, 4)
        r5 = by_rung(tier_runs, 5)
        # Cross-rung counts (not multiples — the dashboard computes multiples
        # from the mean cost/latency itself).
        correct4 = {r["query_id"]: r["correct"] for r in r4}
        correct5 = {r["query_id"]: r["correct"] for r in r5}
        r5_wins = sum(
            1 for qid in correct5 if correct5[qid] and not correct4.get(qid, False)
        )
        by_tier[tier] = {
            "4": _aggregate(runs, r4),
            "5": _aggregate(runs, r5),
            "n_queries": len({r["query_id"] for r in tier_runs}),
            "r4_fail_count": sum(1 for r in r4 if not r["correct"]),
            "r5_fail_count": sum(1 for r in r5 if not r["correct"]),
            "r5_wins_over_r4": r5_wins,
        }

    return {"overall": overall, "by_tier": by_tier}


def build_verdicts(runs: list[dict]) -> list[dict]:
    """One row per query: which rungs answered correctly + a recommendation."""
    verdicts = []
    for bq in BENCHMARK_QUERIES:
        r4 = next(r for r in runs if r["query_id"] == bq.id and r["rung"] == 4)
        r5 = next(r for r in runs if r["query_id"] == bq.id and r["rung"] == 5)
        c4, c5 = r4["correct"], r5["correct"]
        if c4 and c5:
            rec = (
                "Both rungs succeed — use Rung 4. It reaches the same outcome "
                "for a fraction of the cost and latency."
            )
        elif c5 and not c4:
            rec = (
                "Only Rung 5 succeeds — the fixed workflow can't handle this "
                "case. The agent's flexibility earns its cost here."
            )
        elif c4 and not c5:
            rec = "Only Rung 4 succeeds — the agent added cost without a better outcome."
        else:
            rec = "Neither rung resolves this cleanly — a human handoff is the honest answer."
        verdicts.append(
            {
                "query_id": bq.id,
                "tier": bq.tier,
                "query": bq.query,
                "rung4_correct": c4,
                "rung5_correct": c5,
                "recommendation": rec,
            }
        )
    return verdicts


def main() -> int:
    print(f"Running {len(BENCHMARK_QUERIES)} queries × {len(RUNGS)} rungs "
          f"= {len(BENCHMARK_QUERIES) * len(RUNGS)} runs...\n")

    runs: list[dict] = []
    failures = 0
    for bq in BENCHMARK_QUERIES:
        for level in sorted(RUNGS):
            rec = _run_one(bq, level)
            runs.append(rec)
            if rec["error"]:
                failures += 1
                print(f"  {bq.id} [{bq.tier}] Rung {level}: ERROR — {rec['error']}")
            else:
                print(
                    f"  {bq.id} [{bq.tier}] Rung {level}: "
                    f"{rec['latency_ms']:>5} ms  {rec['total_tokens']:>5} tok  "
                    f"${rec['cost_usd']:.6f}  correct={rec['correct']}"
                )
            time.sleep(_PACING_SECONDS)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "llama-3.3-70b-versatile",
        "note": (
            "Static benchmark for the executive dashboard. Generated once by "
            "scripts/generate_benchmarks.py; the dashboard reads only this "
            "file and makes no live LLM calls. Multiples (N× slower / more "
            "expensive) are computed from aggregates at render time."
        ),
        "tiers": TIERS,
        "rungs": {str(lvl): RUNGS[lvl]["name"] for lvl in RUNGS},
        "runs": runs,
        "aggregates": build_aggregates(runs),
        "verdicts": build_verdicts(runs),
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUTPUT_PATH.relative_to(REPO)} "
          f"({len(runs)} runs, {failures} failures).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
