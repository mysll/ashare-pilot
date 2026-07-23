#!/usr/bin/env python3
"""Build a compact Step 3 input view from mapper.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.daily_contract import default_predict_dir, ensure_doc_date, read_json, utc_now_iso, write_json


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def value_conf(item: Any, include_trace: bool = False) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"value": None, "confidence": 0}
    result = {
        "value": item.get("value"),
        "confidence": item.get("confidence"),
    }
    if include_trace:
        result["trace"] = item.get("trace")
        result["evidence"] = item.get("evidence")
    return result


def pattern_state(item: Any, include_trace: bool = False) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"state": "UNKNOWN", "confidence": 0}
    result = {
        "state": item.get("state", "UNKNOWN"),
        "confidence": item.get("confidence", 0),
    }
    if include_trace:
        result["trace"] = item.get("trace")
        result["evidence"] = item.get("evidence")
    return result


def normalize_reason(reason: Any) -> str:
    text = str(reason or "").strip()
    if not text:
        return "unknown"
    if "fetch_error" in text:
        return "fetch_error"
    if "atr_pct" in text:
        return "atr_pct > 8%"
    if "tech_score" in text or re.search(r"\btech\s*[=<]", text):
        return "tech_score < 50"
    if "amount" in text:
        return "amount < 30000万"
    return text


def excluded_payload(items: list[Any], mode: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    if mode == "none":
        return None
    if mode == "full":
        return [item for item in items if isinstance(item, dict)]

    reasons = Counter()
    sources = Counter()
    for item in items:
        if not isinstance(item, dict):
            continue
        reasons[normalize_reason(item.get("reason"))] += 1
        source = item.get("source") or "unknown"
        sources[str(source)] += 1
    return {
        "count": len(items),
        "top_reasons": [{"reason": key, "count": count} for key, count in reasons.most_common()],
        "sources": [{"source": key, "count": count} for key, count in sources.most_common()],
    }


def build_view(doc: dict[str, Any], include_excluded: str = "summary", include_trace: bool = False) -> dict[str, Any]:
    candidates = []
    for stock in doc.get("candidate_pool", []):
        if not isinstance(stock, dict):
            continue
        scores = stock.get("scores") if isinstance(stock.get("scores"), dict) else {}
        pattern = stock.get("pattern") if isinstance(stock.get("pattern"), dict) else {}
        major = stock.get("major_event") if isinstance(stock.get("major_event"), dict) else {}
        risk = stock.get("risk_type") if isinstance(stock.get("risk_type"), dict) else {}
        candidates.append(
            {
                "code": stock.get("code"),
                "name": stock.get("name"),
                "role_tags": stock.get("role_tags") or [],
                "scores": {
                    "composite": value_conf(scores.get("composite"), include_trace),
                    "theme_heat": value_conf(scores.get("theme_heat"), include_trace),
                    "news_impact": value_conf(scores.get("news_impact"), include_trace),
                    "auction": value_conf(scores.get("auction"), include_trace),
                    "tech": value_conf(scores.get("tech"), include_trace),
                    "money_flow": value_conf(scores.get("money_flow"), include_trace),
                },
                "major_event": {
                    "polarity": major.get("polarity", "unknown"),
                    "confidence": major.get("confidence", 0),
                    **({"trace": major.get("trace"), "evidence": major.get("evidence")} if include_trace else {}),
                },
                "risk_type": risk.get("value") or [],
                "risk_confidence": risk.get("confidence", 0),
                "pattern": {
                    "heat": pattern_state(pattern.get("heat"), include_trace),
                    "leader": pattern_state(pattern.get("leader"), include_trace),
                    "auction": pattern_state(pattern.get("auction"), include_trace),
                    "rotation": pattern_state(pattern.get("rotation"), include_trace),
                    "volume": pattern_state(pattern.get("volume"), include_trace),
                },
                "anomaly": stock.get("anomaly"),
                "news_link": stock.get("news_link"),
                "strategy_inputs": stock.get("strategy_inputs") or {},
            }
        )

    observation_pool = [
        {
            "code": item.get("code"),
            "name": item.get("name"),
            "composite": item.get("composite"),
            "theme": item.get("theme"),
            "reason": item.get("reason"),
            "anomaly": item.get("anomaly"),
        }
        for item in doc.get("observation_pool", [])
        if isinstance(item, dict)
    ]

    view: dict[str, Any] = {
        "schema_version": "daily_strategy_input.v1",
        "date": doc.get("date"),
        "generated_at": utc_now_iso(),
        "source": {
            "schema_version": doc.get("schema_version"),
            "generated_at": doc.get("generated_at"),
            "generation_mode": doc.get("generation_mode"),
            "mapper_sha256": canonical_sha256(doc),
        },
        "market_state": doc.get("market_state") or {},
        "themes": [
            {
                "name": item.get("name"),
                "rank": item.get("rank"),
                "final_heat": item.get("final_heat"),
                "direction": item.get("direction"),
                "evidence": item.get("evidence"),
            }
            for item in doc.get("themes", [])
            if isinstance(item, dict)
        ],
        "candidates": candidates,
        "observation_pool": observation_pool,
    }

    excluded = excluded_payload(doc.get("excluded_stocks", []), include_excluded)
    if excluded is not None:
        view["excluded_stocks"] = excluded
    return view


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build mapper.strategy_view.json for Step 3")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--input", help="Path to mapper.json; default predict/{date}/mapper.json")
    parser.add_argument("--output", help="Path to mapper.strategy_view.json; default predict/{date}/mapper.strategy_view.json")
    parser.add_argument("--include-excluded", choices=("summary", "full", "none"), default="summary")
    parser.add_argument("--include-traces", action="store_true", help="Keep trace/evidence fields for debugging or audit")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    input_path = Path(args.input) if args.input else predict_dir / "mapper.json"
    output_path = Path(args.output) if args.output else predict_dir / "mapper.strategy_view.json"

    doc = read_json(input_path)
    if not isinstance(doc, dict):
        print("[ERROR] mapper root must be object", file=sys.stderr)
        return 1
    if doc.get("schema_version") != "daily_mapper.v1":
        print("[ERROR] input schema_version must be daily_mapper.v1", file=sys.stderr)
        return 1
    try:
        ensure_doc_date(doc, args.date, str(input_path))
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    write_json(output_path, build_view(doc, args.include_excluded, args.include_traces))
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
