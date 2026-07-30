#!/usr/bin/env python3
"""Build a validation-only intraday shadow-rule contract."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from ashare_pilot.review.intraday_shadow_contract import (
    build_contract,
    default_config_path,
    default_output_path,
    write_json,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an isolated intraday shadow-rule validation contract"
    )
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--since")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing snapshot for the same as-of date.",
    )
    args = parser.parse_args(argv)
    config_path = args.config or default_config_path()
    output_path = args.output or default_output_path(args.as_of)
    if output_path.exists() and not args.replace:
        parser.error(f"output already exists: {output_path}; use --replace")
    contract = build_contract(
        as_of_date=args.as_of,
        config_path=config_path,
        since=args.since,
    )
    write_json(output_path, contract)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
