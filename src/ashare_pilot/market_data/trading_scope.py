"""Shared trading-scope policy for intraday recall and execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import workspace_path


def default_scope_path() -> Path:
    return workspace_path("config", "trading-scope.json")


def load_trading_scope(path: Path | None = None) -> dict[str, Any]:
    scope_path = path or default_scope_path()
    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid trading scope: {scope_path}") from exc
    if not isinstance(scope, dict) or not isinstance(scope.get("boards"), dict):
        raise ValueError(f"invalid trading scope: {scope_path}")
    if not isinstance(scope.get("overrides", []), list):
        raise ValueError(f"invalid trading scope overrides: {scope_path}")
    return scope


def scope_decision(code: str, scope: dict[str, Any]) -> dict[str, Any]:
    """Resolve a code using exact overrides, then the longest board prefix."""
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
        normalized_codes = {str(value).strip().lower() for value in codes}
        if normalized not in normalized_codes:
            continue
        excluded = (
            not bool(override.get("allowed"))
            if "allowed" in override
            else bool(override.get("exclude"))
        )
        return {
            "allowed": not excluded,
            "excluded": excluded,
            "matched_rule": f"overrides.{normalized}",
            "reason": override.get("reason")
            or ("excluded by override" if excluded else "allowed by override"),
        }

    boards = scope.get("boards", {})
    matches = [
        str(prefix)
        for prefix in boards
        if normalized.startswith(str(prefix).strip().lower())
    ]
    if not matches:
        return {
            "allowed": False,
            "excluded": True,
            "matched_rule": "boards.<none>",
            "reason": "no matching trading-scope board",
        }
    prefix = max(matches, key=len)
    rule = boards.get(prefix) if isinstance(boards.get(prefix), dict) else {}
    excluded = bool(rule.get("exclude"))
    return {
        "allowed": not excluded,
        "excluded": excluded,
        "matched_rule": f"boards.{prefix}",
        "reason": rule.get("reason")
        or ("excluded by trading scope" if excluded else "allowed by trading scope"),
    }


def partition_by_scope(
    stocks: list[dict[str, Any]],
    scope: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition stocks without mutating records or duplicating policy logic."""
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for stock in stocks:
        target = removed if scope_decision(stock.get("code", ""), scope)["excluded"] else kept
        target.append(stock)
    return kept, removed
