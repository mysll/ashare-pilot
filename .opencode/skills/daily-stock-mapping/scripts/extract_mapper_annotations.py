#!/usr/bin/env python3
"""Extract mapper.annotations.json from an existing mapper.json.

This is a migration/test helper. The production target is for the Step 2 LLM to
write mapper.annotations.json directly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from mapper_json_lib import default_predict_dir, read_json, write_json


def annotation_from_mapper(doc: dict[str, Any]) -> dict[str, Any]:
    themes = []
    for theme in doc.get("themes", []):
        if not isinstance(theme, dict):
            continue
        item = {"name": theme.get("name")}
        if isinstance(theme.get("emotion"), dict) and theme["emotion"].get("value") is not None:
            item["emotion"] = theme["emotion"]
        if isinstance(theme.get("policy_polarity"), dict) and theme["policy_polarity"].get("value") is not None:
            item["policy_polarity"] = theme["policy_polarity"]
        if theme.get("catalyst_exception") is not None:
            item["catalyst_exception"] = theme.get("catalyst_exception")
        if item.get("name"):
            themes.append(item)

    stocks = []
    for stock in doc.get("candidate_pool", []):
        if not isinstance(stock, dict) or not stock.get("code"):
            continue
        scores = stock.get("scores", {})
        news_impact = scores.get("news_impact", {}) if isinstance(scores, dict) else {}
        news_value = news_impact.get("value") if isinstance(news_impact, dict) else None
        major = stock.get("major_event", {"polarity": "none", "confidence": 90})
        if isinstance(major, dict):
            major = dict(major)
            if not major.get("trace") and not major.get("evidence"):
                major["trace"] = "migration extract"
        else:
            major = {"polarity": "none", "confidence": 90, "trace": "migration extract"}

        pattern = {}
        for key, value in (stock.get("pattern", {}) or {}).items():
            if isinstance(value, dict):
                patched = dict(value)
                if not patched.get("trace") and not patched.get("evidence"):
                    patched["trace"] = "migration extract"
                pattern[key] = patched

        item = {
            "code": stock.get("code"),
            "news_relevance": {
                "r": "R2",
                "p": "P2",
                "value": news_value,
                "confidence": news_impact.get("confidence", 60) if isinstance(news_impact, dict) else 60,
                "evidence": stock.get("news_link"),
                "trace": news_impact.get("trace") if isinstance(news_impact, dict) else "migration extract",
            },
            "major_event": major,
            "pattern": pattern,
            "anomaly": stock.get("anomaly"),
            "news_link": stock.get("news_link"),
        }
        stocks.append(item)

    return {
        "schema_version": "daily_mapper_annotations.v1",
        "date": doc.get("date"),
        "themes": themes,
        "stocks": stocks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract mapper.annotations.json from mapper.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--input", help="Path to mapper.json; default predict/{date}/mapper.json")
    parser.add_argument("--output", help="Path to mapper.annotations.json; default predict/{date}/mapper.annotations.json")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    input_path = Path(args.input) if args.input else predict_dir / "mapper.json"
    output_path = Path(args.output) if args.output else predict_dir / "mapper.annotations.json"
    doc = read_json(input_path)
    if not isinstance(doc, dict):
        print("[ERROR] root must be object", file=sys.stderr)
        return 1
    write_json(output_path, annotation_from_mapper(doc))
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
