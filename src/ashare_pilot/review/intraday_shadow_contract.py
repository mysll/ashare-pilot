"""Validation-only contract for prospectively testing intraday shadow rules.

The contract deliberately lives outside the overnight strategy pipeline.  It
does not express direction, tradeability, sizing, or an order.  Historical
rows are calibration evidence only; rows after ``frozen_on`` are the sole
prospective evidence used by the review gate.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.intraday_contract import execution_state, numeric
from ashare_pilot.market_data.runtime import workspace_path
from ashare_pilot.market_data.trading_calendar import is_trading_day
from ashare_pilot.market_data.trading_scope import load_trading_scope


SCHEMA_VERSION = "intraday_shadow_rule_validation.v1"
MODE = "VALIDATION_ONLY"
EVIDENCE_STATUSES = {
    "awaiting_prospective_evidence",
    "continue_observation",
    "review_ready",
}
FORBIDDEN_DECISION_FIELDS = {
    "direction",
    "tradeability",
    "position",
    "position_tier",
    "risk_severity",
    "recommendations",
    "orders",
    "buy",
    "sell",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _next_trading_day(value: str) -> str:
    current = date.fromisoformat(value) + timedelta(days=1)
    while not is_trading_day(current):
        current += timedelta(days=1)
    return current.isoformat()


def _prefixed_code(stock: dict[str, Any]) -> str | None:
    raw = str(stock.get("code") or "")
    market = stock.get("market")
    if len(raw) != 6 or not raw.isdigit():
        return None
    if market == 1:
        return f"sh{raw}"
    if market == 0:
        return f"sz{raw}"
    return None


def _real_time(stock: dict[str, Any]) -> dict[str, Any]:
    enriched = stock.get("enriched")
    enriched = enriched if isinstance(enriched, dict) else {}
    value = enriched.get("real_time")
    return value if isinstance(value, dict) else {}


def _feature_row(
    stock: dict[str, Any],
    *,
    market_up_ratio: float,
    scope: dict[str, Any],
) -> dict[str, Any] | None:
    state = execution_state(stock, scope)
    if not state["eligible"]:
        return None
    rt = _real_time(stock)
    entry = numeric(rt.get("price", stock.get("price")))
    vwap = numeric(rt.get("vwap"))
    high = numeric(rt.get("high"))
    low = numeric(rt.get("low"))
    change_pct = numeric(stock.get("change_pct"))
    turnover_pct = numeric(stock.get("turnover"))
    if (
        entry is None
        or entry <= 0
        or vwap is None
        or vwap <= 0
        or high is None
        or low is None
        or high <= low
        or change_pct is None
        or turnover_pct is None
    ):
        return None
    return {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "entry_price": entry,
        "market_up_ratio": float(market_up_ratio),
        "change_pct": change_pct,
        "vwap_gap_pct": (entry / vwap - 1) * 100,
        "close_location": (entry - low) / (high - low),
        "turnover_pct": turnover_pct,
    }


def _condition_matches(value: float, condition: dict[str, Any]) -> bool:
    if "min" in condition and value < float(condition["min"]):
        return False
    if "max" in condition and value > float(condition["max"]):
        return False
    return True


def _matches_rule(features: dict[str, Any], rule: dict[str, Any]) -> bool:
    conditions = rule.get("conditions")
    if not isinstance(conditions, list):
        return False
    for condition in conditions:
        if not isinstance(condition, dict):
            return False
        field = condition.get("field")
        value = features.get(field)
        if not isinstance(value, (int, float)) or not _condition_matches(
            float(value), condition
        ):
            return False
    return True


def _outcome(
    features: dict[str, Any],
    next_stock: dict[str, Any],
    *,
    threshold_pct: float,
    next_mark_timestamp: Any,
) -> dict[str, Any] | None:
    entry = float(features["entry_price"])
    open_price = numeric(next_stock.get("open"))
    high_price = numeric(next_stock.get("high"))
    mark_price = numeric(next_stock.get("price"))
    if (
        open_price is None
        or open_price <= 0
        or high_price is None
        or high_price <= 0
        or mark_price is None
        or mark_price <= 0
    ):
        return None
    high_return = (high_price / entry - 1) * 100
    return {
        "t_plus_1_open_return_pct": _round((open_price / entry - 1) * 100),
        "t_plus_1_high_return_pct": _round(high_return),
        "t_plus_1_mark_return_pct": _round((mark_price / entry - 1) * 100),
        "t_plus_1_mark_timestamp": next_mark_timestamp,
        "primary_success": high_return >= threshold_pct,
    }


def _daily_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["source_date"])].append(row)
    result = []
    for source_date, values in sorted(grouped.items()):
        outcomes = [value["outcome"] for value in values]
        result.append(
            {
                "source_date": source_date,
                "sample_count": len(values),
                "primary_success_rate": _round(
                    sum(bool(value["primary_success"]) for value in outcomes)
                    / len(outcomes)
                ),
                "mean_t_plus_1_mark_return_pct": _round(
                    statistics.fmean(
                        float(value["t_plus_1_mark_return_pct"]) for value in outcomes
                    )
                ),
            }
        )
    return result


def _metrics(
    rows: list[dict[str, Any]], *, assumed_round_trip_cost_bps: float
) -> dict[str, Any]:
    if not rows:
        return {
            "sample_count": 0,
            "market_day_count": 0,
            "primary_success_count": 0,
            "primary_success_rate": None,
            "market_day_equal_weight_success_rate": None,
            "mean_t_plus_1_open_return_pct": None,
            "mean_t_plus_1_high_return_pct": None,
            "mean_t_plus_1_mark_return_pct": None,
            "mean_t_plus_1_mark_net_return_pct": None,
            "worst_day_equal_weight_mark_return_pct": None,
            "daily": [],
        }
    outcomes = [row["outcome"] for row in rows]
    daily = _daily_metrics(rows)
    cost_pct = assumed_round_trip_cost_bps / 100
    return {
        "sample_count": len(rows),
        "market_day_count": len(daily),
        "primary_success_count": sum(
            bool(value["primary_success"]) for value in outcomes
        ),
        "primary_success_rate": _round(
            sum(bool(value["primary_success"]) for value in outcomes) / len(outcomes)
        ),
        "market_day_equal_weight_success_rate": _round(
            statistics.fmean(
                float(value["primary_success_rate"]) for value in daily
            )
        ),
        "mean_t_plus_1_open_return_pct": _round(
            statistics.fmean(
                float(value["t_plus_1_open_return_pct"]) for value in outcomes
            )
        ),
        "mean_t_plus_1_high_return_pct": _round(
            statistics.fmean(
                float(value["t_plus_1_high_return_pct"]) for value in outcomes
            )
        ),
        "mean_t_plus_1_mark_return_pct": _round(
            statistics.fmean(
                float(value["t_plus_1_mark_return_pct"]) for value in outcomes
            )
        ),
        "mean_t_plus_1_mark_net_return_pct": _round(
            statistics.fmean(
                float(value["t_plus_1_mark_return_pct"]) - cost_pct
                for value in outcomes
            )
        ),
        "worst_day_equal_weight_mark_return_pct": _round(
            min(float(value["mean_t_plus_1_mark_return_pct"]) for value in daily)
        ),
        "daily": daily,
    }


def _lift(rule_metrics: dict[str, Any], baseline_metrics: dict[str, Any]) -> dict[str, Any]:
    def difference(field: str) -> float | None:
        left = rule_metrics.get(field)
        right = baseline_metrics.get(field)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return None
        return _round(float(left) - float(right))

    return {
        "primary_success_rate": difference("primary_success_rate"),
        "market_day_equal_weight_success_rate": difference(
            "market_day_equal_weight_success_rate"
        ),
        "mean_t_plus_1_mark_net_return_pct": difference(
            "mean_t_plus_1_mark_net_return_pct"
        ),
    }


def _gate_status(
    prospective: dict[str, Any],
    baseline: dict[str, Any],
    gates: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    day_count = int(prospective["market_day_count"])
    minimum_days = int(gates["minimum_prospective_market_days"])
    checks = [
        {
            "name": "minimum_prospective_market_days",
            "actual": day_count,
            "required": minimum_days,
            "passed": day_count >= minimum_days,
        }
    ]
    if day_count < minimum_days:
        return "awaiting_prospective_evidence", checks

    success_rate = prospective.get("primary_success_rate")
    baseline_rate = baseline.get("primary_success_rate")
    lift = (
        None
        if success_rate is None or baseline_rate is None
        else float(success_rate) - float(baseline_rate)
    )
    checks.extend(
        [
            {
                "name": "minimum_primary_success_rate",
                "actual": success_rate,
                "required": gates["minimum_primary_success_rate"],
                "passed": success_rate is not None
                and success_rate >= float(gates["minimum_primary_success_rate"]),
            },
            {
                "name": "minimum_success_rate_lift",
                "actual": _round(lift),
                "required": gates["minimum_success_rate_lift"],
                "passed": lift is not None
                and lift >= float(gates["minimum_success_rate_lift"]),
            },
            {
                "name": "minimum_mean_mark_net_return_pct",
                "actual": prospective.get("mean_t_plus_1_mark_net_return_pct"),
                "required": gates["minimum_mean_mark_net_return_pct"],
                "passed": prospective.get("mean_t_plus_1_mark_net_return_pct")
                is not None
                and prospective["mean_t_plus_1_mark_net_return_pct"]
                >= float(gates["minimum_mean_mark_net_return_pct"]),
            },
        ]
    )
    return (
        "review_ready" if all(check["passed"] for check in checks) else "continue_observation",
        checks,
    )


def _cache_dates(cache_root: Path, as_of_date: str, since: str | None) -> list[str]:
    return sorted(
        path.parent.name
        for path in cache_root.glob("*/compute_pool_enriched.json")
        if path.parent.name <= as_of_date
        and (since is None or path.parent.name >= since)
    )


def build_contract(
    *,
    as_of_date: str,
    config_path: Path,
    since: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build one immutable snapshot of the shadow-rule evidence contract."""
    config = read_json(config_path)
    rule = config["rule"]
    label = config["label"]
    quality = config["data_quality"]
    gates = config["prospective_gates"]
    frozen_on = str(rule["frozen_on"])
    scope = load_trading_scope()
    cache_root = workspace_path(".cache", "intraday")
    baseline_verified: list[dict[str, Any]] = []
    matched_verified: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    excluded_pairs: list[dict[str, Any]] = []
    pair_summaries: list[dict[str, Any]] = []
    primary_threshold = float(label["primary_threshold_pct"])

    for source_date in _cache_dates(cache_root, as_of_date, since):
        source_dir = cache_root / source_date
        pool_doc = read_json(source_dir / "compute_pool_enriched.json")
        pool = pool_doc.get("compute_pool", [])
        breadth_path = source_dir / "market_breadth.json"
        if not isinstance(pool, list) or len(pool) < int(quality["minimum_compute_pool_rows"]):
            excluded_pairs.append(
                {"source_date": source_date, "reason": "compute_pool_too_small"}
            )
            continue
        if not breadth_path.exists():
            excluded_pairs.append(
                {"source_date": source_date, "reason": "market_breadth_missing"}
            )
            continue
        breadth = read_json(breadth_path)
        up_ratio = numeric(breadth.get("up_ratio"))
        if up_ratio is None:
            excluded_pairs.append(
                {"source_date": source_date, "reason": "market_up_ratio_missing"}
            )
            continue
        next_date = _next_trading_day(source_date)
        next_path = cache_root / next_date / "all_stocks_cache.json"
        features = [
            value
            for stock in pool
            if isinstance(stock, dict)
            and (
                value := _feature_row(
                    stock, market_up_ratio=float(up_ratio), scope=scope
                )
            )
            is not None
        ]
        matches = [value for value in features if _matches_rule(value, rule)]

        if next_date > as_of_date:
            pending.extend(
                {
                    "source_date": source_date,
                    "expected_t_plus_1_date": next_date,
                    "code": value["code"],
                    "name": value["name"],
                    "features": {
                        key: _round(cell)
                        for key, cell in value.items()
                        if key not in {"code", "name"}
                    },
                }
                for value in matches
            )
            pair_summaries.append(
                {
                    "source_date": source_date,
                    "t_plus_1_date": next_date,
                    "status": "pending",
                    "eligible_rows": len(features),
                    "matched_rows": len(matches),
                }
            )
            continue
        if not next_path.exists():
            excluded_pairs.append(
                {
                    "source_date": source_date,
                    "t_plus_1_date": next_date,
                    "reason": "exact_t_plus_1_cache_missing",
                }
            )
            continue
        next_doc = read_json(next_path)
        next_stocks = next_doc.get("stocks", [])
        if (
            not isinstance(next_stocks, list)
            or len(next_stocks) < int(quality["minimum_t_plus_1_market_rows"])
        ):
            excluded_pairs.append(
                {
                    "source_date": source_date,
                    "t_plus_1_date": next_date,
                    "reason": "t_plus_1_market_cache_too_small",
                    "actual_rows": len(next_stocks)
                    if isinstance(next_stocks, list)
                    else None,
                }
            )
            continue
        next_by_code = {
            code: stock
            for stock in next_stocks
            if isinstance(stock, dict) and (code := _prefixed_code(stock))
        }
        matched_codes = sum(
            isinstance(stock, dict) and stock.get("code") in next_by_code
            for stock in pool
        )
        match_ratio = matched_codes / len(pool)
        if match_ratio < float(quality["minimum_t_plus_1_match_ratio"]):
            excluded_pairs.append(
                {
                    "source_date": source_date,
                    "t_plus_1_date": next_date,
                    "reason": "t_plus_1_match_ratio_too_low",
                    "actual_ratio": _round(match_ratio),
                }
            )
            continue

        verified_count = 0
        matched_count = 0
        for value in features:
            next_stock = next_by_code.get(str(value["code"]))
            if next_stock is None:
                continue
            outcome = _outcome(
                value,
                next_stock,
                threshold_pct=primary_threshold,
                next_mark_timestamp=next_doc.get("fetched_at"),
            )
            if outcome is None:
                continue
            row = {
                "source_date": source_date,
                "t_plus_1_date": next_date,
                "phase": "calibration"
                if source_date <= frozen_on
                else "prospective",
                "code": value["code"],
                "name": value["name"],
                "features": {
                    key: _round(cell)
                    for key, cell in value.items()
                    if key not in {"code", "name"}
                },
                "outcome": outcome,
            }
            baseline_verified.append(row)
            verified_count += 1
            if _matches_rule(value, rule):
                matched_verified.append(row)
                matched_count += 1
        pair_summaries.append(
            {
                "source_date": source_date,
                "t_plus_1_date": next_date,
                "status": "verified",
                "eligible_rows": len(features),
                "verified_rows": verified_count,
                "matched_rows": matched_count,
            }
        )

    cost_bps = float(label["assumed_round_trip_cost_bps"])
    phases: dict[str, Any] = {}
    for phase in ("calibration", "prospective"):
        baseline_rows = [
            row for row in baseline_verified if row["phase"] == phase
        ]
        rule_rows = [row for row in matched_verified if row["phase"] == phase]
        baseline_metrics = _metrics(
            baseline_rows, assumed_round_trip_cost_bps=cost_bps
        )
        rule_metrics = _metrics(rule_rows, assumed_round_trip_cost_bps=cost_bps)
        phases[phase] = {
            "baseline": baseline_metrics,
            "rule": rule_metrics,
            "lift": _lift(rule_metrics, baseline_metrics),
        }
    status, gate_results = _gate_status(
        phases["prospective"]["rule"],
        phases["prospective"]["baseline"],
        gates,
    )
    generated = now or datetime.now(timezone.utc)
    contract = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": f"{rule['rule_id']}.v{rule['version']}.{as_of_date}",
        "as_of_date": as_of_date,
        "generated_at": generated.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "mode": MODE,
        "integration_boundary": {
            "strategy_consumption_allowed": False,
            "formal_rule_update_allowed": False,
            "recommendation_generation_allowed": False,
            "order_generation_allowed": False,
            "allowed_use": "prospective_validation_only",
        },
        "rule": rule,
        "label": label,
        "data_quality_policy": quality,
        "dataset": {
            "since": since,
            "source_cache": ".cache/intraday/{date}",
            "pairing_policy": "exact_next_trading_day_only",
            "pair_summaries": pair_summaries,
            "excluded_pairs": excluded_pairs,
            "baseline_verified_rows": len(baseline_verified),
            "matched_verified_rows": len(matched_verified),
            "pending_matched_rows": len(pending),
        },
        "evidence": {
            "calibration_warning": (
                "Historical thresholds were selected with visibility into this "
                "period; calibration metrics are not out-of-sample evidence."
            ),
            "phases": phases,
            "verified_matches": matched_verified,
            "pending_matches": pending,
        },
        "prospective_review": {
            "evidence_status": status,
            "automatic_promotion_allowed": False,
            "gates": gates,
            "gate_results": gate_results,
        },
        "iteration_policy": {
            "append_only_snapshots": True,
            "rule_changes_require_new_version": True,
            "condition_changes_reset_prospective_evidence": True,
            "minimum_review_frequency": "every_5_new_prospective_market_days",
            "next_action": (
                "Continue collecting exact T+1 snapshots; do not modify the "
                "production strategy or learned-rule files."
            ),
        },
    }
    errors = validate_contract(contract)
    if errors:
        raise ValueError("invalid generated shadow contract: " + "; ".join(errors))
    return contract


def _forbidden_paths(value: Any, path: str = "") -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}.{key}" if path else key
            if key.lower() in FORBIDDEN_DECISION_FIELDS:
                result.append(nested_path)
            result.extend(_forbidden_paths(nested, nested_path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            result.extend(_forbidden_paths(nested, f"{path}[{index}]"))
    return result


def validate_contract(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["root: must be object"]
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if document.get("mode") != MODE:
        errors.append(f"mode must be {MODE}")
    boundary = document.get("integration_boundary")
    if not isinstance(boundary, dict):
        errors.append("integration_boundary must be object")
    else:
        for field in (
            "strategy_consumption_allowed",
            "formal_rule_update_allowed",
            "recommendation_generation_allowed",
            "order_generation_allowed",
        ):
            if boundary.get(field) is not False:
                errors.append(f"integration_boundary.{field} must be false")
    rule = document.get("rule")
    if not isinstance(rule, dict):
        errors.append("rule must be object")
    else:
        if not isinstance(rule.get("rule_id"), str) or not rule["rule_id"]:
            errors.append("rule.rule_id must be non-empty string")
        if not isinstance(rule.get("version"), int) or rule["version"] < 1:
            errors.append("rule.version must be positive integer")
        if not isinstance(rule.get("conditions"), list) or not rule["conditions"]:
            errors.append("rule.conditions must be non-empty list")
    status = (
        document.get("prospective_review", {}).get("evidence_status")
        if isinstance(document.get("prospective_review"), dict)
        else None
    )
    if status not in EVIDENCE_STATUSES:
        errors.append("prospective_review.evidence_status is unsupported")
    forbidden = _forbidden_paths(document)
    errors.extend(f"{path}: decision field forbidden" for path in forbidden)
    evidence = document.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be object")
        return errors
    verified = evidence.get("verified_matches")
    pending = evidence.get("pending_matches")
    if not isinstance(verified, list):
        errors.append("evidence.verified_matches must be list")
        verified = []
    if not isinstance(pending, list):
        errors.append("evidence.pending_matches must be list")
        pending = []
    seen: set[tuple[Any, Any]] = set()
    threshold = numeric(document.get("label", {}).get("primary_threshold_pct"))
    for index, row in enumerate(verified):
        if not isinstance(row, dict):
            errors.append(f"evidence.verified_matches[{index}] must be object")
            continue
        key = (row.get("source_date"), row.get("code"))
        if key in seen:
            errors.append(f"evidence.verified_matches[{index}] duplicate date/code")
        seen.add(key)
        outcome = row.get("outcome")
        if not isinstance(outcome, dict):
            errors.append(f"evidence.verified_matches[{index}].outcome must be object")
            continue
        high_return = numeric(outcome.get("t_plus_1_high_return_pct"))
        success = outcome.get("primary_success")
        if (
            threshold is None
            or high_return is None
            or success is not (high_return >= threshold)
        ):
            errors.append(
                f"evidence.verified_matches[{index}].primary_success inconsistent"
            )
    for index, row in enumerate(pending):
        if not isinstance(row, dict):
            errors.append(f"evidence.pending_matches[{index}] must be object")
        elif "outcome" in row:
            errors.append(f"evidence.pending_matches[{index}].outcome forbidden")
    return errors


def default_config_path() -> Path:
    return workspace_path("config", "intraday-shadow-rules.json")


def default_output_path(as_of_date: str) -> Path:
    return workspace_path(
        "research",
        "intraday-shadow",
        as_of_date,
        "shadow_rule_validation.json",
    )
