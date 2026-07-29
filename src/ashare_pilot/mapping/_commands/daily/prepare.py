#!/usr/bin/env python3
"""Prepare deterministic Step 2 inputs in one orchestration command."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from .timing import update_report
from .theme_stock_base import build_filtered_doc, load_extra_stocks, load_universe, theme_library_dir
from .theme_stock_universe import collect_theme_specs_from_json, enrich_structured_source_flags
from .theme_stock_base import build_doc_from_themes, universe_doc
from ashare_pilot.mapping.daily_contract import (build_deterministic_mapper_base, default_predict_dir, load_pool,
                             ensure_doc_date, load_trading_scope, read_json, write_json, publish_theme_stocks)
from .validate_theme_stocks import check_doc as check_theme_stocks_doc
from ashare_pilot.indicators._commands.pool_fetch import main as fetch_pool_indicators
from ashare_pilot.themes._commands.query import (
    _compute_market_view,
    _load_concept_cache_snapshot,
    _resolve_theme,
)


def market_views_for(themes: list[dict[str, Any]]) -> dict[str, Any]:
    resolved_themes = []
    for theme in themes:
        data = _resolve_theme(theme["name"])
        if data:
            resolved_themes.append((theme["name"], data))
    if not resolved_themes:
        return {"themes": {}}
    snapshot = _load_concept_cache_snapshot()
    result = {
        name: _compute_market_view(data, top=10, snapshot=snapshot)
        for name, data in resolved_themes
    }
    return {"themes": result}


def annotation_input(
    base: dict[str, Any],
    theme_stocks: dict[str, Any],
    news_doc: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a compact, candidate-linked semantic input without duplicating news prose."""
    theme_stock_by_code = {
        item.get("code"): item
        for item in theme_stocks.get("stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    canonical_news = {
        f"news#{item['id']}": {
            "refs": [f"news#{item['id']}"],
            "category": item.get("category"),
            "source": item.get("source"),
            "title": item.get("title"),
            **({"desc": item.get("desc")} if item.get("desc") else {}),
        }
        for item in (news_doc.get("items", []) if isinstance(news_doc, dict) else [])
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    refs_by_theme = {
        theme["name"]: list(theme.get("evidence_refs") or [])
        for theme in theme_stocks.get("themes", [])
        if isinstance(theme, dict) and isinstance(theme.get("name"), str)
    }

    referenced: set[str] = set()
    candidates = []
    for item in base.get("candidate_pool", []):
        if not isinstance(item, dict):
            continue
        theme_stock = theme_stock_by_code.get(item.get("code"), {})
        source_themes = [
            source.get("name")
            for source in theme_stock.get("source_themes", [])
            if isinstance(source, dict) and isinstance(source.get("name"), str)
        ]
        theme_news_refs = list(dict.fromkeys(
            ref for name in source_themes for ref in refs_by_theme.get(name, [])
        ))
        direct_ref = theme_stock.get("news_ref")
        direct_news_refs = [direct_ref] if direct_ref in canonical_news else []
        referenced.update(theme_news_refs)
        referenced.update(direct_news_refs)
        candidates.append(
            {
                "code": item.get("code"), "name": item.get("name"), "role_tags": item.get("role_tags"),
                "source_themes": source_themes,
                "direct_news_refs": direct_news_refs,
                "theme_news_refs": theme_news_refs,
                "theme_heat": item.get("scores", {}).get("theme_heat"),
                "technical": item.get("scores", {}).get("tech"),
                "risk_type": item.get("risk_type"), "pattern_defaults": item.get("pattern"),
            }
        )

    compact_evidence = [
        canonical_news[ref] for ref in sorted(referenced) if ref in canonical_news
    ]
    return {
        "schema_version": "mapper_annotation_input.tmp.v1",
        "date": base.get("date"),
        "non_contract": True,
        "news_evidence": compact_evidence,
        "candidates": candidates,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Prepare daily mapping")
    parser.add_argument("--date", required=True)
    parser.add_argument("--reuse-pool", action="store_true", help="Use existing pool_indicators.json (fixtures/debug only)")
    parser.add_argument("--scope")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    predict = default_predict_dir(args.date)
    themes_path = predict / "themes.json"
    universe_path = predict / "theme_stocks.universe.json"
    pool_path = predict / "pool_indicators.json"
    base_path = predict / "theme_stocks.base.json"
    final_path = predict / "theme_stocks.json"
    market_path = predict / ".theme_market_views.json"
    mapper_input_path = predict / ".mapper_annotation_input.json"
    try:
        themes = collect_theme_specs_from_json(themes_path, args.date)
        scope = load_trading_scope(Path(args.scope) if args.scope else None)
        extra_path = predict / "theme_stocks.extra.json"
        resolved, stocks, excluded, notes = build_doc_from_themes(
            args.date, themes, scope, theme_library_dir(), 15, 10, 15,
            load_extra_stocks(extra_path if extra_path.exists() else None, args.date),
        )
        market_views_started = time.perf_counter()
        market_views = market_views_for(themes)
        market_views_duration = time.perf_counter() - market_views_started
        write_json(market_path, market_views)
        news_path = predict / "news.json"
        news = read_json(news_path) if news_path.exists() else None
        if isinstance(news, dict):
            ensure_doc_date(news, args.date, str(news_path))
        lhb_path = predict / "lhb.json"
        lhb = read_json(lhb_path) if lhb_path.exists() else None
        if isinstance(lhb, dict) and lhb.get("date") is not None:
            ensure_doc_date(lhb, args.date, str(lhb_path))
        enrich_structured_source_flags(stocks, news if isinstance(news, dict) else None, market_views,
                                       lhb)
        write_json(universe_path, universe_doc(args.date, resolved, stocks, excluded, notes))

        indicator_started = time.perf_counter()
        if not args.reuse_pool:
            return_code = fetch_pool_indicators(
                ["--codes-file", str(universe_path), "--json", "-o", str(pool_path)]
            )
            if return_code:
                raise RuntimeError(f"indicator fetch failed with exit code {return_code}")
        pool = load_pool(pool_path)
        indicator_duration = time.perf_counter() - indicator_started
        failures = sum(1 for item in pool.values() if item.get("fetch_failed"))
        themes2, stocks2, excluded2, notes2 = load_universe(universe_path, args.date)
        base = build_filtered_doc(args.date, themes2, stocks2, excluded2, notes2, pool, universe_path)
        write_json(base_path, base)
        final = publish_theme_stocks(base, args.date)
        final_errors = check_theme_stocks_doc(final, scope, pool)
        if final_errors:
            raise ValueError("theme_stocks validation failed before publication:\n" + "\n".join(f"  - {item}" for item in final_errors))
        write_json(final_path, final)
        mapper_base = build_deterministic_mapper_base(args.date, pool, final, scope)
        write_json(
            mapper_input_path,
            annotation_input(
                mapper_base,
                final,
                news if isinstance(news, dict) else None,
            ),
        )
        duration = time.perf_counter() - started
        update_report(predict / "step2_timing.json", args.date, "prepare", duration,
                      [themes_path, news_path, extra_path], [universe_path, pool_path, final_path, mapper_input_path],
                      {"news_count": len(news.get("items", [])) if isinstance(news, dict) and isinstance(news.get("items"), list) else 0,
                       "theme_count": len(themes), "universe_count": len(stocks),
                       "candidate_count": len(mapper_base["candidate_pool"])}, failures,
                      market_views_duration=market_views_duration)
        update_report(predict / "step2_timing.json", args.date, "indicators", indicator_duration,
                      [universe_path], [pool_path], {"universe_count": len(stocks)}, failures)
    except Exception as exc:
        print(f"[ERROR] prepare_daily_mapping failed: {exc}", file=sys.stderr)
        return 1
    print(f"OK: prepared daily mapping for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
