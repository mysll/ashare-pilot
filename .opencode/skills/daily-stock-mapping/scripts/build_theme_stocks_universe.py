#!/usr/bin/env python3
"""Build deterministic predict/{date}/theme_stocks.universe.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from build_theme_stocks_base import (
    build_doc_from_themes,
    load_extra_stocks,
    theme_library_dir,
    universe_doc,
)
from mapper_json_lib import clean_text, default_predict_dir, ensure_doc_date, load_trading_scope, parse_float, read_json, write_json


def collect_theme_specs_from_json(path: Path, date: str) -> list[dict[str, object]]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"themes.json must be a JSON object: {path}")
    ensure_doc_date(data, date, str(path))
    if data.get("schema_version") != "daily_themes.v1":
        raise ValueError(f"themes.json schema_version must be daily_themes.v1: {path}")
    themes = data.get("themes")
    if not isinstance(themes, list):
        raise ValueError(f"themes.json missing themes[]: {path}")

    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for i, item in enumerate(themes):
        if not isinstance(item, dict):
            raise ValueError(f"themes[{i}] must be object")
        status = clean_text(item.get("status")) or clean_text(item.get("pool")) or "tradeable"
        if status not in {"tradeable", "candidate"}:
            continue
        name = clean_text(item.get("name") or item.get("theme"))
        if not name or name in seen:
            continue
        heat = parse_float(item.get("heat") or item.get("final_heat") or item.get("final"))
        confidence = parse_float(item.get("confidence") or item.get("conf"))
        result.append(
            {
                "name": name,
                "rank": int(parse_float(item.get("rank")) or len(result) + 1),
                "heat": heat,
                "confidence": confidence,
            }
        )
        seen.add(name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build theme_stocks.universe.json from selected themes")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--themes-json", help="Path to themes.json; default predict/{date}/themes.json")
    parser.add_argument("--scope", help="Path to trading-scope.json")
    parser.add_argument("--theme-library", help="Path to theme-library skill dir")
    parser.add_argument("--extra", help="Path to theme_stocks.extra.json; default predict/{date}/theme_stocks.extra.json when present")
    parser.add_argument("--top-candidates", type=int, default=15, help="Candidate stocks per theme from Theme Library")
    parser.add_argument("--top-leaders", type=int, default=10, help="Industry leaders per theme from Theme Library")
    parser.add_argument("--top-pure", type=int, default=15, help="Pure stocks per theme from Theme Library")
    parser.add_argument("--output", help="Path to output universe JSON; default predict/{date}/theme_stocks.universe.json")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    output_path = Path(args.output) if args.output else predict_dir / "theme_stocks.universe.json"
    extra_path = Path(args.extra) if args.extra else predict_dir / "theme_stocks.extra.json"
    themes_json_path = Path(args.themes_json) if args.themes_json else predict_dir / "themes.json"

    try:
        themes = collect_theme_specs_from_json(themes_json_path, args.date)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    if not themes:
        print("[ERROR] no tradeable themes found in themes.json", file=sys.stderr)
        return 2

    try:
        scope = load_trading_scope(Path(args.scope) if args.scope else None)
        extra_stocks = load_extra_stocks(extra_path if extra_path.exists() else None, args.date)
        resolved_themes, stocks_by_code, board_excluded, generation_notes = build_doc_from_themes(
            args.date,
            themes,
            scope,
            Path(args.theme_library) if args.theme_library else theme_library_dir(),
            args.top_candidates,
            args.top_leaders,
            args.top_pure,
            extra_stocks,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    write_json(output_path, universe_doc(args.date, resolved_themes, stocks_by_code, board_excluded, generation_notes))
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
