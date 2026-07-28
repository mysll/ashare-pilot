#!/usr/bin/env python3
"""Build deterministic intraday_mapper.base.json from compute-layer JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ashare_pilot.mapping.intraday_contract import (
    MAPPER_BASE_SCHEMA_VERSION,
    cache_dir,
    attach_theme_evidence,
    execution_state,
    intraday_dir,
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
        for name in (
            "market_breadth",
            "indices",
            "concept_dashboard",
            "theme_ranking",
            "selection_pools",
        )
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        print("[ERROR] missing inputs: " + ", ".join(missing), file=sys.stderr)
        return 1
    values = {name: read_json(path) for name, path in required.items()}
    pool = values["selection_pools"]
    if not isinstance(pool, dict):
        print("[ERROR] selection_pools.json root must be an object", file=sys.stderr)
        return 1
    if pool.get("schema_version") != "intraday_selection_pools.v1":
        print(
            "[ERROR] selection_pools.json must be intraday_selection_pools.v1",
            file=sys.stderr,
        )
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
    executable = pool.get("executable_pool")
    observation = pool.get("observation_pool")
    if not isinstance(executable, list) or not isinstance(observation, list):
        print("[ERROR] selection pools must be arrays", file=sys.stderr)
        return 1
    for pool_name, stocks in (
        ("executable_pool", executable),
        ("observation_pool", observation),
    ):
        for stock in stocks:
            stored = stock.get("execution_state")
            derived = execution_state(stock)
            if stored != derived:
                print(
                    f"[ERROR] {pool_name} {stock.get('code')}: "
                    "execution_state differs from deterministic fields",
                    file=sys.stderr,
                )
                return 1
    executable_stocks = attach_theme_evidence(
        executable, stock_themes, theme_contract
    )
    observation_stocks = attach_theme_evidence(
        observation, stock_themes, theme_contract
    )
    doc = {
        "schema_version": MAPPER_BASE_SCHEMA_VERSION,
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
            **(
                pool.get("pool_summary")
                if isinstance(pool.get("pool_summary"), dict)
                else {}
            ),
            "scored_pool_summary": pool.get("scored_pool_summary", {}),
            "configured_limits": pool.get("configured_limits", {}),
            "regime_snapshot": pool.get("regime_snapshot", {}),
            "recall_quality": pool.get("recall_quality", {}),
            "data_quality": pool.get("data_quality", {}),
        },
        "executable_stocks": executable_stocks,
        "observation_stocks": observation_stocks,
    }
    write_json(output, doc)
    print(f"OK: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
