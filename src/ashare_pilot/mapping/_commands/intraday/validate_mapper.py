#!/usr/bin/env python3
"""Validate the final intraday mapper contract and compute/annotation coverage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ashare_pilot.mapping.intraday_contract import intraday_dir, read_json, reasoning_invariant_errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    args = parser.parse_args(argv)
    path = Path(args.input) if args.input else intraday_dir(args.date) / "intraday_mapper.json"
    doc = read_json(path)
    errors: list[str] = []
    if not isinstance(doc, dict) or doc.get("schema_version") != "intraday_mapper.v1":
        errors.append("schema_version must be intraday_mapper.v1")
    if not isinstance(doc, dict) or doc.get("date") != args.date:
        errors.append(f"date must be {args.date}")
    stocks = doc.get("stocks") if isinstance(doc, dict) else None
    if not isinstance(stocks, list):
        errors.append("stocks must be list")
        stocks = []
    codes = [item.get("code") for item in stocks if isinstance(item, dict)]
    if len(codes) != len(set(codes)):
        errors.append("stocks contains duplicate codes")
    annotated = [item for item in stocks if isinstance(item, dict) and isinstance(item.get("reasoning"), dict)]
    for item in annotated:
        for error in reasoning_invariant_errors(item, item["reasoning"]):
            errors.append(f"{item.get('code')}: {error}")
    coverage = doc.get("annotation_coverage", {}) if isinstance(doc, dict) else {}
    if coverage.get("annotated") != len(annotated) or coverage.get("scored") != len(stocks):
        errors.append("annotation_coverage does not match stocks")
    if errors:
        print(f"[ERROR] {path} failed validation:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"OK: {path} ({len(stocks)} scored, {len(annotated)} annotated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
