#!/usr/bin/env python3
"""Validate an intraday shadow-rule contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_pilot.review.intraday_shadow_contract import (
    read_json,
    validate_contract,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an isolated intraday shadow-rule contract"
    )
    parser.add_argument("input", type=Path)
    args = parser.parse_args(argv)
    errors = validate_contract(read_json(args.input))
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"valid": True, "input": str(args.input)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
