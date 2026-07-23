"""Mechanical live-market confirmation for morning execution."""

from __future__ import annotations

from typing import Any


INDEX_CODES = ("sh000001", "sz399001", "sh000688")
REGIMES = {"panic", "weak", "neutral", "strong-sector"}
GLOBAL_ACTIONS = {"NORMAL", "SELECTIVE", "WAIT", "NO_NEW_BUY"}


def number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def normalize_indices(quotes: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    by_code = {item.get("code"): item for item in quotes if isinstance(item, dict)}
    result: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for code in INDEX_CODES:
        quote = by_code.get(code, {})
        current = number(quote.get("percent"))
        open_price = number(quote.get("open"))
        previous = number(quote.get("yestclose"))
        open_pct = ((open_price / previous - 1) * 100) if open_price is not None and previous else None
        valid = "error" not in quote and current is not None and open_pct is not None
        if not valid:
            warnings.append(f"{code}_quote_invalid")
        result[code] = {
            "open_pct": round(open_pct, 2) if open_pct is not None else None,
            "current_pct": round(current, 2) if current is not None else None,
            "quote_time": quote.get("time"),
            "valid": valid,
        }
    return result, warnings


def classify_live_regime(indices: dict[str, dict[str, Any]], prior: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    values = {code: item.get("current_pct") for code, item in indices.items()}
    if any(values.get(code) is None for code in INDEX_CODES):
        return "neutral", ["index_data_incomplete"]
    sh = float(values["sh000001"])
    sz = float(values["sz399001"])
    kcb = float(values["sh000688"])
    if sz <= -2.5 and sh <= -1.5:
        return "panic", ["broad_index_panic"]
    if sz <= -1.5 or (sz <= -1.0 and kcb <= -2.0):
        return "weak", ["sz_or_tech_index_weak"]
    if sz <= -0.5:
        return "weak", ["sz_below_-0.5"]
    if sz < -0.3 and prior == "strong-sector":
        return "neutral", ["strong_prior_failed_sz_below_-0.3"]
    if kcb - sz >= 1.5 and sz < 0:
        return "neutral", ["kcb_sz_divergence"]
    if prior == "strong-sector" and sz >= 0 and (kcb >= 0 or sh >= 0):
        return "strong-sector", ["strong_prior_cross_index_confirmed"]
    return "neutral", reasons or ["live_market_neutral"]


def global_action(regime: str, warnings: list[str], breadth_available: bool = False) -> tuple[str, list[str]]:
    if any(item.endswith("quote_invalid") for item in warnings):
        return "WAIT", ["index_quote_missing"]
    if regime in {"panic", "weak"}:
        return "NO_NEW_BUY", [f"regime_{regime}"]
    if regime == "strong-sector" and breadth_available:
        return "NORMAL", ["strong_market_confirmed"]
    if regime == "strong-sector":
        return "SELECTIVE", ["market_breadth_unavailable"]
    return "SELECTIVE", ["neutral_or_divergent_market"]


def build_market_confirmation(
    quotes: list[dict[str, Any]], prior: str, breadth_available: bool = False
) -> dict[str, Any]:
    indices, warnings = normalize_indices(quotes)
    live, regime_reasons = classify_live_regime(indices, prior)
    action, action_reasons = global_action(live, warnings, breadth_available)
    return {
        "regime_prior": prior if prior in REGIMES else "neutral",
        "regime_live": live,
        "regime_confirmed": live,
        "regime_changed": live != prior,
        "indices": indices,
        "breadth": None,
        "global_action": action,
        "reasons": regime_reasons + action_reasons,
        "data_warnings": warnings + ([] if breadth_available else ["market_breadth_unavailable"]),
    }
