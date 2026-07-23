#!/usr/bin/env python3
"""Build deterministic intraday_mapper.base.json from compute-layer JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ashare_pilot.mapping.intraday_contract import (
    cache_dir,
    attach_theme_evidence,
    intraday_dir,
    opportunity_stocks,
    read_json,
    utc_now_iso,
    write_json,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = Path(args.cache_dir) if args.cache_dir else cache_dir(args.date)
    output = Path(args.output) if args.output else intraday_dir(args.date) / "intraday_mapper.base.json"
    required = {
        name: root / f"{name}.json"
        for name in ("market_breadth", "indices", "concept_dashboard", "theme_ranking", "opportunity_pool")
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        print("[ERROR] missing inputs: " + ", ".join(missing), file=sys.stderr)
        return 1
    values = {name: read_json(path) for name, path in required.items()}
    pool = values["opportunity_pool"]
    if not isinstance(pool, dict):
        print("[ERROR] opportunity_pool.json root must be an object", file=sys.stderr)
        return 1
    theme_contract = values["theme_ranking"]
    if (
        not isinstance(theme_contract, dict)
        or theme_contract.get("schema_version") != "intraday_theme_ranking.v2"
        or not isinstance(theme_contract.get("stock_themes"), dict)
    ):
        print("[ERROR] theme_ranking.json must be intraday_theme_ranking.v2", file=sys.stderr)
        return 1
    stock_themes = (
        theme_contract.get("stock_themes", {})
        if isinstance(theme_contract, dict)
        else {}
    )
    stocks = attach_theme_evidence(opportunity_stocks(pool), stock_themes)
    doc = {
        "schema_version": "intraday_mapper_base.v1",
        "date": args.date,
        "generated_at": utc_now_iso(),
        "source_files": {
            name: str(path if args.cache_dir else Path(".cache") / "intraday" / args.date / path.name)
            for name, path in required.items()
        },
        "market": {
            "breadth": values["market_breadth"],
            "indices": values["indices"],
            "concept_dashboard": values["concept_dashboard"],
        },
        "themes": theme_contract,
        "pool_summary": {
            key: pool.get(key)
            for key in (
                "weights_version", "scoring_policy_version", "pool_size", "scored_count",
                "quality_filtered_count", "floor_rejected_count",
                "opportunity_pool_size", "score_stats", "pool_warning",
                "regime_snapshot", "data_quality_summary",
                "i14_applied_count", "i14_skipped_no_quick_score", "vwap_missing_count",
            )
        },
        "stocks": stocks,
        "quality_filtered": pool.get("quality_filtered", []),
    }
    write_json(output, doc)
    print(f"OK: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
