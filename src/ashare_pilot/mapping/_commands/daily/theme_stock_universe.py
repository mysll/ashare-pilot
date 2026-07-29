#!/usr/bin/env python3
"""Build deterministic predict/{date}/theme_stocks.universe.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .theme_stock_base import (
    build_doc_from_themes,
    load_extra_stocks,
    theme_library_dir,
    universe_doc,
)
from ashare_pilot.mapping.daily_contract import CODE_RE, clean_text, default_predict_dir, ensure_doc_date, load_trading_scope, parse_float, read_json, write_json
from ashare_pilot.themes._commands.daily.contract import (
    THEMES_SCHEMA,
    formal_theme_shape_errors,
)


def collect_theme_specs_from_json(path: Path, date: str) -> list[dict[str, object]]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"themes.json must be a JSON object: {path}")
    ensure_doc_date(data, date, str(path))
    if data.get("schema_version") != THEMES_SCHEMA:
        raise ValueError(
            f"themes.json schema_version must be {THEMES_SCHEMA}: {path}"
        )
    themes = data.get("themes")
    if not isinstance(themes, list):
        raise ValueError(f"themes.json missing themes[]: {path}")

    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for i, item in enumerate(themes):
        shape_errors = formal_theme_shape_errors(item, f"themes[{i}]")
        if shape_errors:
            raise ValueError(
                "themes.json formal Theme validation failed:\n"
                + "\n".join(f"  - {error}" for error in shape_errors)
            )
        assert isinstance(item, dict)
        status = clean_text(item.get("status"))
        if status not in {"tradeable", "watch", "discarded"}:
            raise ValueError(
                f"themes[{i}].status must be tradeable, watch, or discarded"
            )
        if status != "tradeable":
            continue
        name = clean_text(item.get("name"))
        if not name or name in seen:
            continue
        score = item.get("score")
        if not isinstance(score, dict):
            raise ValueError(f"themes[{i}].score must be object")
        final_heat = parse_float(score.get("final_heat"))
        evidence_refs = item.get("evidence_refs")
        if final_heat is None:
            raise ValueError(f"themes[{i}].score.final_heat must be numeric")
        if not isinstance(evidence_refs, list) or not all(
            isinstance(ref, str) for ref in evidence_refs
        ):
            raise ValueError(f"themes[{i}].evidence_refs must be string list")
        result.append(
            {
                "name": name,
                "rank": int(parse_float(item.get("rank")) or 0),
                "final_heat": final_heat,
                "attention_direction": clean_text(
                    item.get("attention_direction")
                ),
                "evidence_refs": evidence_refs,
            }
        )
        seen.add(name)
    return result


def _news_ref(item: dict[str, object]) -> str | None:
    value = item.get("id")
    return f"news#{value}" if isinstance(value, int) else None


def enrich_structured_source_flags(
    stocks_by_code: dict[str, dict[str, object]],
    news_doc: dict[str, object] | None = None,
    market_views: dict[str, object] | None = None,
    lhb_doc: object | None = None,
) -> None:
    """Set source flags only from actual structured inputs; unavailable sources stay false."""
    news_items = news_doc.get("items", []) if isinstance(news_doc, dict) else []
    valid_news_refs = {_news_ref(item) for item in news_items if isinstance(item, dict)}
    for code, stock in stocks_by_code.items():
        flags = stock.setdefault("source_flags", {"candidate": False, "market": False, "news": False, "lhb": False})
        existing_ref = clean_text(stock.get("news_ref"))
        if existing_ref in valid_news_refs:
            flags["news"] = True
        name = clean_text(stock.get("name"))
        for item in news_items:
            if not isinstance(item, dict):
                continue
            haystack = " ".join(str(item.get(key) or "") for key in ("title", "desc"))
            if code in haystack or (name and name in haystack):
                flags["news"] = True
                stock["news_ref"] = _news_ref(item)
                break

    views = market_views.get("themes", market_views) if isinstance(market_views, dict) else {}
    if isinstance(views, dict):
        for theme_name, payload in views.items():
            view = payload.get("market_view", payload) if isinstance(payload, dict) else {}
            if not isinstance(view, dict):
                continue
            qualified: set[str] = set()
            for item in view.get("cross_rank_highlights", []):
                if isinstance(item, dict) and CODE_RE.fullmatch(str(item.get("code") or "")):
                    qualified.add(str(item["code"]))
            for item in view.get("threshold_attention", view.get("market_attention", [])):
                if isinstance(item, dict) and parse_float(item.get("attention_score")) is not None and parse_float(item.get("attention_score")) >= 80:
                    qualified.add(str(item.get("code")))
            for item in view.get("threshold_gainers", view.get("top_gainers", [])):
                if isinstance(item, dict) and parse_float(item.get("change_pct")) is not None and parse_float(item.get("change_pct")) >= 3:
                    qualified.add(str(item.get("code")))
            for code in qualified:
                if code in stocks_by_code:
                    stocks_by_code[code]["source_flags"]["market"] = True
                    stocks_by_code[code]["market_ref"] = f"theme-market:{theme_name}"

    rows = []
    if isinstance(lhb_doc, list):
        rows = lhb_doc
    elif isinstance(lhb_doc, dict):
        for key in ("items", "stocks", "data"):
            if isinstance(lhb_doc.get(key), list):
                rows = lhb_doc[key]
                break
    for item in rows:
        if not isinstance(item, dict):
            continue
        code = clean_text(item.get("code") or item.get("stock_code"))
        if code in stocks_by_code:
            stocks_by_code[code]["source_flags"]["lhb"] = True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build theme_stocks.universe.json from selected themes")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--themes-json", help="Path to themes.json; default predict/{date}/themes.json")
    parser.add_argument("--scope", help="Path to trading-scope.json")
    parser.add_argument("--theme-library", help="Path to theme-library skill dir")
    parser.add_argument("--extra", help="Path to theme_stocks.extra.json; default predict/{date}/theme_stocks.extra.json when present")
    parser.add_argument("--news", help="Path to canonical news.json; default predict/{date}/news.json when present")
    parser.add_argument("--market-views", help="Optional structured selected-theme market views JSON")
    parser.add_argument("--lhb", help="Optional structured LHB JSON for the day")
    parser.add_argument("--top-candidates", type=int, default=15, help="Candidate stocks per theme from Theme Library")
    parser.add_argument("--top-leaders", type=int, default=10, help="Industry leaders per theme from Theme Library")
    parser.add_argument("--top-pure", type=int, default=15, help="Pure stocks per theme from Theme Library")
    parser.add_argument("--output", help="Path to output universe JSON; default predict/{date}/theme_stocks.universe.json")
    args = parser.parse_args(argv)

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
        news_path = Path(args.news) if args.news else predict_dir / "news.json"
        market_path = Path(args.market_views) if args.market_views else predict_dir / "theme_market_views.json"
        lhb_path = Path(args.lhb) if args.lhb else predict_dir / "lhb.json"
        news_doc = read_json(news_path) if news_path.exists() else None
        if isinstance(news_doc, dict):
            ensure_doc_date(news_doc, args.date, str(news_path))
        lhb_doc = read_json(lhb_path) if lhb_path.exists() else None
        if isinstance(lhb_doc, dict) and lhb_doc.get("date") is not None:
            ensure_doc_date(lhb_doc, args.date, str(lhb_path))
        enrich_structured_source_flags(
            stocks_by_code,
            news_doc if isinstance(news_doc, dict) else None,
            read_json(market_path) if market_path.exists() else None,
            lhb_doc,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    write_json(output_path, universe_doc(args.date, resolved_themes, stocks_by_code, board_excluded, generation_notes))
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
