#!/usr/bin/env python3
"""Validate sparse annotations and finalize Step 2 in one command."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .timing import update_report
from .strategy_view import build_view
from ashare_pilot.mapping.daily_contract import (build_deterministic_mapper_base, default_predict_dir, load_pool,
                             ensure_doc_date, load_trading_scope, merge_annotations, read_json, write_json,
                             theme_stock_filter)
from .validate_annotations import validate, validate_candidate_coverage, validate_news_refs
from .validate_mapper import check_doc
from .validate_theme_stocks import check_doc as check_theme_stocks_doc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Finalize daily mapping")
    parser.add_argument("--date", required=True)
    parser.add_argument("--scope")
    parser.add_argument("--annotations")
    parser.add_argument("--theme-stocks")
    parser.add_argument("--pool")
    parser.add_argument("--output-dir", help="Debug/fixture output directory; defaults to predict/{date}")
    parser.add_argument("--validation-retries", type=int, default=0)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    predict = default_predict_dir(args.date)
    output_dir = Path(args.output_dir) if args.output_dir else predict
    annotations_path = Path(args.annotations) if args.annotations else predict / "mapper.annotations.json"
    theme_stocks_path = Path(args.theme_stocks) if args.theme_stocks else predict / "theme_stocks.json"
    pool_path = Path(args.pool) if args.pool else predict / "pool_indicators.json"
    mapper_base_path = output_dir / "mapper.base.json"
    mapper_path = output_dir / "mapper.json"
    view_path = output_dir / "mapper.strategy_view.json"
    annotation_input_path = predict / ".mapper_annotation_input.json"
    try:
        annotations = read_json(annotations_path)
        theme_stocks = read_json(theme_stocks_path)
        if not isinstance(annotations, dict) or not isinstance(theme_stocks, dict):
            raise ValueError("annotations and theme_stocks roots must be objects")
        ensure_doc_date(annotations, args.date, str(annotations_path))
        ensure_doc_date(theme_stocks, args.date, str(theme_stocks_path))
        pool = load_pool(pool_path)
        scope = load_trading_scope(Path(args.scope) if args.scope else None)
        theme_errors = check_theme_stocks_doc(theme_stocks, scope, pool)
        if theme_errors:
            raise ValueError("theme_stocks validation failed:\n" + "\n".join(f"  - {item}" for item in theme_errors))
        candidate_codes = {
            stock.get("code") for stock in theme_stocks.get("stocks", [])
            if isinstance(stock, dict) and theme_stock_filter(stock)["status"] == "candidate"
        }
        errors = validate(annotations, candidate_codes)
        news_path = annotations_path.parent / "news.json"
        if not news_path.exists():
            news_path = predict / "news.json"
        if news_path.exists():
            news_doc = read_json(news_path)
            if isinstance(news_doc, dict):
                ensure_doc_date(news_doc, args.date, str(news_path))
                errors.extend(validate_news_refs(annotations, news_doc))
        annotation_input = read_json(annotation_input_path) if annotation_input_path.exists() else None
        coverage_errors, warnings = validate_candidate_coverage(
            annotations,
            theme_stocks,
            annotation_input if isinstance(annotation_input, dict) else None,
        )
        errors.extend(coverage_errors)
        for warning in warnings:
            print(f"[WARN] {warning}", file=sys.stderr)
        if errors:
            raise ValueError("annotation validation failed:\n" + "\n".join(f"  - {item}" for item in errors))
        base = build_deterministic_mapper_base(args.date, pool, theme_stocks, scope)
        write_json(mapper_base_path, base)
        mapper = merge_annotations(base, annotations, args.date)
        mapper_errors = check_doc(mapper, pool, scope)
        if mapper_errors:
            raise ValueError("mapper validation failed:\n" + "\n".join(f"  - {item}" for item in mapper_errors))
        write_json(mapper_path, mapper)
        write_json(view_path, build_view(mapper))
        duration = time.perf_counter() - started
        update_report(output_dir / "step2_timing.json", args.date, "finalize", duration,
                      [annotations_path, theme_stocks_path, pool_path], [mapper_base_path, mapper_path, view_path],
                      {"candidate_count": len(base["candidate_pool"]), "annotation_count": len(annotations.get("stocks", [])),
                       "final_count": len(mapper["candidate_pool"])},
                      validation_retries=args.validation_retries,
                      validation_status="passed")
    except Exception as exc:
        update_report(
            output_dir / "step2_timing.json",
            args.date,
            "finalize",
            time.perf_counter() - started,
            [annotations_path, theme_stocks_path, pool_path],
            [],
            validation_retries=args.validation_retries,
            validation_status="failed",
            validation_errors=str(exc).splitlines(),
        )
        print(f"[ERROR] finalize_daily_mapping failed: {exc}", file=sys.stderr)
        return 1
    print(f"OK: finalized daily mapping for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
