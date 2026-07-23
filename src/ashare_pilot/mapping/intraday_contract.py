#!/usr/bin/env python3
"""Shared helpers for the intraday mapper JSON contract."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import workspace_path


HOLD_DIRECTIONS = {"持有偏多", "持有", "谨慎持有"}
STOP_LOSS_BASES = {"day_low", "ma5", "ma10", "ma20", "not_applicable"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def intraday_dir(date: str) -> Path:
    return workspace_path("intraday", date)


def cache_dir(date: str) -> Path:
    return workspace_path(".cache", "intraday", date)


def stock_code(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    code = item.get("code")
    return code if isinstance(code, str) and code else None


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace("%", "").replace("+", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def default_scope_path() -> Path:
    return workspace_path("config", "trading-scope.json")


def load_trading_scope(path: Path | None = None) -> dict[str, Any]:
    scope_path = path or default_scope_path()
    scope = read_json(scope_path)
    if not isinstance(scope, dict) or not isinstance(scope.get("boards"), dict):
        raise ValueError(f"invalid trading scope: {scope_path}")
    if not isinstance(scope.get("overrides", []), list):
        raise ValueError(f"invalid trading scope overrides: {scope_path}")
    return scope


def scope_decision(code: str, scope: dict[str, Any]) -> dict[str, Any]:
    normalized = str(code or "").strip().lower()
    for override in scope.get("overrides", []):
        if not isinstance(override, dict):
            continue
        codes = override.get("codes")
        if isinstance(codes, str):
            codes = [codes]
        elif not isinstance(codes, list):
            single = override.get("code")
            codes = [single] if isinstance(single, str) else []
        if normalized not in {str(value).lower() for value in codes}:
            continue
        excluded = not bool(override.get("allowed")) if "allowed" in override else bool(override.get("exclude"))
        return {
            "excluded": excluded,
            "matched_rule": f"overrides.{normalized}",
            "reason": override.get("reason") or ("excluded by override" if excluded else "allowed by override"),
        }
    boards = scope.get("boards", {})
    matches = [str(prefix) for prefix in boards if normalized.startswith(str(prefix).lower())]
    if not matches:
        return {"excluded": True, "matched_rule": "boards.<none>", "reason": "no matching trading-scope board"}
    prefix = max(matches, key=len)
    rule = boards.get(prefix) if isinstance(boards.get(prefix), dict) else {}
    excluded = bool(rule.get("exclude"))
    return {
        "excluded": excluded,
        "matched_rule": f"boards.{prefix}",
        "reason": rule.get("reason") or ("excluded by trading scope" if excluded else "allowed by trading scope"),
    }


def limit_ratio(code: str, name: str) -> Decimal:
    normalized_name = str(name or "").upper().replace(" ", "")
    if "ST" in normalized_name:
        return Decimal("0.05")
    if str(code or "").startswith(("sz300", "sh688")):
        return Decimal("0.20")
    if str(code or "").startswith("bj"):
        return Decimal("0.30")
    return Decimal("0.10")


def limit_up_price(stock: dict[str, Any]) -> float | None:
    rt = stock.get("enriched", {}).get("real_time", {})
    rt = rt if isinstance(rt, dict) else {}
    try:
        previous = Decimal(str(rt.get("yestclose")))
        if previous <= 0:
            return None
        value = (previous * (Decimal("1") + limit_ratio(stock.get("code", ""), stock.get("name", "")))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return float(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def execution_state(stock: dict[str, Any], scope: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derive non-overridable tail-execution eligibility from compute fields."""
    code = str(stock.get("code") or "")
    rt = stock.get("enriched", {}).get("real_time", {})
    rt = rt if isinstance(rt, dict) else {}
    price = numeric(rt.get("price", stock.get("price")))
    high = numeric(rt.get("high"))
    limit_price = limit_up_price(stock)
    quote_complete = price is not None and high is not None and limit_price is not None
    is_limit_up = quote_complete and abs(price - limit_price) < 0.005
    is_sealed = bool(is_limit_up and abs(price - high) < 0.005)
    board = scope_decision(code, scope or load_trading_scope())
    board_excluded = board["excluded"]
    reason = (
        "board_policy"
        if board_excluded
        else "quote_data_missing"
        if not quote_complete
        else "sealed_limit_up"
        if is_sealed
        else None
    )
    return {
        "is_limit_up": bool(is_limit_up),
        "is_sealed": is_sealed,
        "limit_up_price": limit_price,
        "quote_complete": quote_complete,
        "source_pool_limit_up": stock.get("source_pool") == "limit_up",
        "board_excluded": board_excluded,
        "board_rule": board["matched_rule"],
        "board_reason": board["reason"],
        "eligible": reason is None,
        "exclusion_reason": reason,
    }


def stop_loss_price(stock: dict[str, Any], basis: Any) -> float | None:
    if basis == "not_applicable":
        return None
    rt = stock.get("enriched", {}).get("real_time", {})
    rt = rt if isinstance(rt, dict) else {}
    technicals = stock.get("technicals") if isinstance(stock.get("technicals"), dict) else {}
    source = {
        "day_low": rt.get("low"),
        "ma5": technicals.get("ma5"),
        "ma10": technicals.get("ma10"),
        "ma20": technicals.get("ma20"),
    }.get(basis)
    value = numeric(source)
    return round(value, 4) if value is not None else None


def resolved_stop_loss(stock: dict[str, Any], basis: Any) -> dict[str, Any]:
    labels = {"day_low": "今日最低价", "ma5": "MA5", "ma10": "MA10", "ma20": "MA20"}
    price = stop_loss_price(stock, basis)
    if basis == "not_applicable":
        return {"stop_loss_basis": basis, "stop_loss_price": None, "stop_loss": "不适用"}
    label = labels.get(str(basis), str(basis))
    text = f"{label} {price:g}" if price is not None else f"{label}（数据缺失）"
    return {"stop_loss_basis": basis, "stop_loss_price": price, "stop_loss": text}


def reasoning_invariant_errors(stock: dict[str, Any], reasoning: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    direction = reasoning.get("direction")
    tradeability = reasoning.get("tradeability")
    derived_state = execution_state(stock)
    stored_state = stock.get("execution_state")
    if isinstance(stored_state, dict) and stored_state != derived_state:
        errors.append("execution_state differs from deterministic compute fields")
    state = derived_state
    actionable = direction in HOLD_DIRECTIONS
    plan = reasoning.get("t_plus_1_plan")
    plan = plan if isinstance(plan, dict) else {}
    basis = plan.get("stop_loss_basis")

    if state.get("is_sealed") and direction != "观望":
        errors.append("sealed limit-up requires direction=观望")
    if state.get("board_excluded") and direction != "观望":
        errors.append("board-policy exclusion requires direction=观望")
    if actionable and not state.get("eligible"):
        errors.append("actionable direction requires execution_state.eligible=true")
    if actionable and basis not in STOP_LOSS_BASES - {"not_applicable"}:
        errors.append("actionable direction requires a structured stop_loss_basis")
    if not actionable and basis != "not_applicable":
        errors.append("observation direction requires stop_loss_basis=not_applicable")
    if actionable:
        stop = stop_loss_price(stock, basis)
        current = numeric(stock.get("enriched", {}).get("real_time", {}).get("price", stock.get("price")))
        if stop is None or current is None or stop <= 0 or stop >= current:
            errors.append("resolved stop loss must be positive and below current price")
    if basis in STOP_LOSS_BASES:
        resolved = resolved_stop_loss(stock, basis)
        for field in ("stop_loss_price", "stop_loss"):
            if field in plan and plan.get(field) != resolved[field]:
                errors.append(f"{field} differs from deterministic stop-loss resolution")
    return errors


def opportunity_stocks(pool: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every scored opportunity once, preserving compute-layer values."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, tier in (
        ("leader_watch", "A"),
        ("premium_candidates", "B"),
        ("early_breakout", "C"),
        ("opportunity_pool", None),
    ):
        values = pool.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            code = stock_code(value)
            if not code or code in seen:
                continue
            item = dict(value)
            if tier and not item.get("tier"):
                item["tier"] = tier
            item["execution_state"] = execution_state(item)
            result.append(item)
            seen.add(code)
    return result


def merge_annotations(base: dict[str, Any], annotations: dict[str, Any]) -> dict[str, Any]:
    stock_notes = {
        item["code"]: item
        for item in annotations.get("stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    stocks = []
    for stock in base.get("stocks", []):
        item = dict(stock)
        note = stock_notes.get(stock.get("code"))
        if note:
            reasoning = {key: value for key, value in note.items() if key != "code"}
            plan = reasoning.get("t_plus_1_plan")
            if isinstance(plan, dict):
                plan = dict(plan)
                plan.update(resolved_stop_loss(stock, plan.get("stop_loss_basis")))
                reasoning["t_plus_1_plan"] = plan
            item["reasoning"] = reasoning
        stocks.append(item)

    result = dict(base)
    result["schema_version"] = "intraday_mapper.v1"
    result["generated_at"] = utc_now_iso()
    result["generation_mode"] = "compute_base_plus_llm_annotations"
    result["market_assessment"] = annotations.get("market_assessment")
    result["strategy"] = annotations.get("strategy")
    result["stocks"] = stocks
    result["annotation_coverage"] = {
        "annotated": len(stock_notes),
        "scored": len(stocks),
    }
    return result
