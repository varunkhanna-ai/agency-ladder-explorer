"""Phase 3: 7 tools + TOOL_REGISTRY + risk metadata + audit log.

Tool data is loaded from committed synthetic-data files in `data/`, deterministically
(never generated at runtime), per IMPLEMENTATION_PLAN.md §3.
"""

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

# Root of the worktree is one level above src/
_DATA_DIR = (Path(__file__).parent.parent / "data").resolve()


def _load_orders():
    with open(_DATA_DIR / "orders.json", "r") as f:
        return json.load(f)


def _load_restaurants():
    with open(_DATA_DIR / "restaurants.json", "r") as f:
        return json.load(f)


def _load_policy_md():
    with open(_DATA_DIR / "refund_policy.md", "r") as f:
        return f.read()


def _split_policy_sections(policy_text: str) -> list[dict[str, str]]:
    """Split the markdown policy into sections indexed by their ## heading."""
    sections: list[dict[str, str]] = []
    parts = re.split(r"\n(?=## )", policy_text)
    for part in parts:
        lines = part.strip().split("\n", 1)
        heading = lines[0].lstrip("#").strip()
        body = lines[1] if len(lines) > 1 else ""
        sections.append({"section": heading, "text": body})
    return sections


_POLICY_SECTIONS = _split_policy_sections(_load_policy_md())
_POLICY_CORPUS = [f"{s['section']}\n{s['text']}" for s in _POLICY_SECTIONS]
_tfidf = TfidfVectorizer(analyzer="word", stop_words="english")
_POLICY_MATRIX = _tfidf.fit_transform(_POLICY_CORPUS)
_POLICY_FEATURE_NAMES = _tfidf.get_feature_names_out()

_AUDIT_LOG: list[dict[str, Any]] = []


def get_audit_log() -> list[dict[str, Any]]:
    return list(_AUDIT_LOG)


def _emit_audit(tool_name: str, risk: str, result: dict[str, Any]) -> None:
    _AUDIT_LOG.append({"tool": tool_name, "risk": risk, "result": result})


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def get_order_status(order_id: str) -> dict[str, Any]:
    """Return order record from orders.json, or an error dict for unknown IDs."""
    orders = {o["order_id"]: o for o in _load_orders()}
    if order_id not in orders:
        return {"error": "unknown_order", "order_id": order_id}
    return orders[order_id]


def search_refund_policy(query: str) -> dict[str, str]:
    """TF-IDF search over refund_policy.md. Returns the best-matching section."""
    query_vec = _tfidf.transform([query])
    similarities = (query_vec * _POLICY_MATRIX.T).toarray()[0]
    best_idx = int(np.argmax(similarities))
    section = _POLICY_SECTIONS[best_idx]
    return {"section": section["section"], "text": section["text"]}


_WEATHER_DATA: dict[str, dict[str, str]] = {
    "koramangala": {"condition": "heavy_rain", "severity": "high"},
}


def get_weather(delivery_area: str) -> dict[str, str]:
    """Hardcoded weather data. Koramangala=heavy rain; all other areas=clear."""
    area_key = delivery_area.strip().lower().replace(" ", "")
    if area_key in _WEATHER_DATA:
        return _WEATHER_DATA[area_key]
    return {"condition": "clear", "severity": "none"}


_DRIVER_GPS: dict[str, dict[str, Any]] = {
    "ORD-9821": {"status": "stalled", "eta_min": 45, "distance_km": 2.1},
    "ORD-4471": {"status": "moving", "eta_min": 8, "distance_km": 1.5},
    "ORD-7788": {"status": "moving", "eta_min": 5, "distance_km": 0.8},
    "ORD-1200": {"status": "delivered", "eta_min": 0, "distance_km": 0.0},
    "ORD-1201": {"status": "delivered", "eta_min": 0, "distance_km": 0.0},
    "ORD-3003": {"status": "delivered", "eta_min": 0, "distance_km": 0.0},
    "ORD-5500": {"status": "not_assigned", "eta_min": 15, "distance_km": 3.0},
    "ORD-6100": {"status": "moving", "eta_min": 12, "distance_km": 2.5},
}


def get_driver_gps(order_id: str) -> dict[str, Any]:
    """Return simulated driver GPS for an order."""
    if order_id not in _DRIVER_GPS:
        return {"error": "no_driver_data", "order_id": order_id}
    return _DRIVER_GPS[order_id]


def get_restaurant_status(restaurant_id: str) -> dict[str, Any]:
    """Return restaurant record from restaurants.json, or an error dict."""
    restaurants = {r["restaurant_id"]: r for r in _load_restaurants()}
    if restaurant_id not in restaurants:
        return {"error": "unknown_restaurant", "restaurant_id": restaurant_id}
    return restaurants[restaurant_id]


_COUPON_CAP_USD = 20.0


def issue_refund_coupon(order_id: str, amount_usd: float) -> dict[str, Any]:
    """Issue a refund coupon up to $20. Hard-enforced cap in code.

    Returns {"error": "cap_exceeded", "cap": 20} if amount > $20.
    """
    if amount_usd > _COUPON_CAP_USD:
        result: dict[str, Any] = {"error": "cap_exceeded", "cap": _COUPON_CAP_USD}
        _emit_audit("issue_refund_coupon", "YELLOW", result)
        return result

    result = {
        "coupon_issued": True,
        "order_id": order_id,
        "amount_usd": amount_usd,
        "currency": "USD",
    }
    _emit_audit("issue_refund_coupon", "YELLOW", result)
    return result


def escalate_to_human(reason: str) -> dict[str, Any]:
    """Terminal action — always permitted. Returns escalated=True."""
    result = {"escalated": True, "reason": reason}
    _emit_audit("escalate_to_human", "BLUE", result)
    return result


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "get_order_status": {
        "fn": get_order_status,
        "risk": "GREEN",
        "action_type": "READ",
        "reversible": True,
    },
    "search_refund_policy": {
        "fn": search_refund_policy,
        "risk": "GREEN",
        "action_type": "READ",
        "reversible": True,
    },
    "get_weather": {
        "fn": get_weather,
        "risk": "GREEN",
        "action_type": "READ",
        "reversible": True,
    },
    "get_driver_gps": {
        "fn": get_driver_gps,
        "risk": "GREEN",
        "action_type": "READ",
        "reversible": True,
    },
    "get_restaurant_status": {
        "fn": get_restaurant_status,
        "risk": "GREEN",
        "action_type": "READ",
        "reversible": True,
    },
    "issue_refund_coupon": {
        "fn": issue_refund_coupon,
        "risk": "YELLOW",
        "action_type": "WRITE",
        "reversible": False,
    },
    "escalate_to_human": {
        "fn": escalate_to_human,
        "risk": "BLUE",
        "action_type": "EXTERNAL",
        "reversible": False,
    },
}
