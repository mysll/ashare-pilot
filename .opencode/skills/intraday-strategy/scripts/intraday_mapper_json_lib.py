#!/usr/bin/env python3
"""Shared helpers for the intraday mapper JSON contract."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    return Path("intraday") / date


def cache_dir(date: str) -> Path:
    return Path(".cache") / "intraday" / date


def stock_code(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    code = item.get("code")
    return code if isinstance(code, str) and code else None


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
            item["reasoning"] = {key: value for key, value in note.items() if key != "code"}
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
