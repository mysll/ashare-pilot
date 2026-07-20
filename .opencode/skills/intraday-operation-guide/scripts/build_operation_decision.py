#!/usr/bin/env python3
"""Project a validated operation snapshot into a deterministic decision contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from validate_operation_snapshot import validate as validate_snapshot


def read_doc(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(doc, dict):
        raise ValueError("snapshot root must be object")
    return doc


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trigger_for(stock: dict[str, Any], class_name: str) -> str:
    if class_name == "A":
        return "当前机械确认已满足，可在仓位上限内人工执行"
    if class_name == "B":
        signals = stock.get("signals", {})
        if signals.get("below_vwap"):
            return "等待完整5分钟K重新站回VWAP"
        if signals.get("near_ma5"):
            return "等待锚点MA5附近出现完整5分钟K确认"
        if signals.get("near_ma20"):
            return "等待MA20附近企稳并由完整5分钟K确认"
        return "等待下一根完整5分钟K完成价格与量能确认"
    return "当天不形成新买入触发"


def build(snapshot: dict[str, Any], source_path: Path) -> dict[str, Any]:
    stocks = []
    actionable_exposure = 0.0
    for stock in snapshot.get("stocks", []):
        guard = stock["decision_guardrails"]
        final_class = guard["mechanical_class"]
        final_position = guard["position"]["final_max"] if final_class == "A" else 0.0
        actionable_exposure += final_position
        stocks.append({
            "code": stock.get("code"),
            "name": stock.get("name"),
            "mechanical_class": guard["mechanical_class"],
            "max_allowed_class": guard["max_allowed_class"],
            "final_class": final_class,
            "class_reasons": guard.get("class_reasons", []),
            "hard_blocks": guard.get("hard_blocks", []),
            "final_position_max": final_position,
            "trigger": trigger_for(stock, final_class),
            "t1_controls": guard.get("t1_controls"),
        })
    return {
        "schema_version": "intraday_operation_decision.v1",
        "date": snapshot.get("date"),
        "generated_at": snapshot.get("generated_at"),
        "snapshot_slot": snapshot.get("snapshot_slot"),
        "run_mode": snapshot.get("run_mode"),
        "lineage": snapshot.get("lineage"),
        "source_snapshot": str(source_path),
        "source_snapshot_sha256": file_sha256(source_path),
        "global_action": snapshot.get("market_confirmation", {}).get("global_action"),
        "market_confirmation": snapshot.get("market_confirmation"),
        "delivery_confirmation": snapshot.get("delivery_confirmation"),
        "portfolio": {
            "actionable_exposure": round(actionable_exposure, 6),
            "allocation": snapshot.get("portfolio_allocation"),
        },
        "stocks": stocks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build operation decision from snapshot")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    source = Path(args.snapshot)
    output = Path(args.output)
    try:
        snapshot = read_doc(source)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    errors = validate_snapshot(snapshot)
    if errors:
        print("[ERROR] source snapshot failed validation:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    decision = build(snapshot, source)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    print(f"Saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
