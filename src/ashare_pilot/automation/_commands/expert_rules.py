"""Manage expert rules through the unified CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.automation.expert_rules import (
    ExpertRuleError,
    add_rule,
    find_rule,
    load_store,
    normalize_draft,
    remove_rule,
)
from ashare_pilot.market_data.runtime import workspace_path


BYPASS_WARNING = (
    "Direct CLI writes bypass Skill semantic and capability checks; "
    "prefer $manage-expert-rules."
)


def _add_rule_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", help="JSON rule draft path, or '-' for stdin")
    parser.add_argument("--name")
    parser.add_argument(
        "--applies-to",
        action="append",
        help="consumer name; repeat or use comma-separated values",
    )
    parser.add_argument("--decision-layer")
    parser.add_argument("--condition")
    parser.add_argument("--exclusion", action="append", default=[])
    parser.add_argument("--action")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage directly authorized expert rules. " + BYPASS_WARNING
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List current expert rules.")
    list_parser.add_argument("--json", action="store_true")

    show_parser = subparsers.add_parser("show", help="Show one expert rule.")
    show_parser.add_argument("rule_id")
    show_parser.add_argument("--json", action="store_true")

    validate_parser = subparsers.add_parser(
        "validate", help="Validate and normalize a rule draft without writing."
    )
    _add_rule_arguments(validate_parser)

    add_parser = subparsers.add_parser("add", help="Add an expert rule.")
    _add_rule_arguments(add_parser)
    add_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and preview the allocated ID without writing",
    )

    remove_parser = subparsers.add_parser(
        "remove", help="Preview or physically delete an expert rule."
    )
    remove_parser.add_argument("rule_id")
    remove_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm irreversible physical deletion",
    )
    return parser


def _load_json_input(path: str) -> Any:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8-sig")
    return json.loads(raw)


def _draft_from_args(args: argparse.Namespace) -> dict[str, Any]:
    direct_values = (
        args.name,
        args.applies_to,
        args.decision_layer,
        args.condition,
        args.exclusion,
        args.action,
    )
    if args.input:
        if any(
            value
            for value in direct_values
            if value not in (None, [])
        ):
            raise ExpertRuleError(
                "--input cannot be combined with direct rule fields"
            )
        try:
            return normalize_draft(_load_json_input(args.input))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExpertRuleError(f"cannot load rule draft: {exc}") from exc

    consumers: list[str] = []
    for raw in args.applies_to or []:
        consumers.extend(
            item.strip() for item in raw.split(",") if item.strip()
        )
    return normalize_draft(
        {
            "name": args.name,
            "applies_to": consumers,
            "decision_layer": args.decision_layer,
            "condition": args.condition,
            "exclusions": args.exclusion,
            "action": args.action,
        }
    )


def _print_rule(rule: dict[str, Any], *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(rule, ensure_ascii=False, indent=2))
        return
    print(f"{rule['id']}  {rule['name']}")
    print(f"  applies_to: {', '.join(rule['applies_to'])}")
    print(f"  decision_layer: {rule['decision_layer']}")
    print(f"  condition: {rule['condition']}")
    if rule["exclusions"]:
        print("  exclusions:")
        for item in rule["exclusions"]:
            print(f"    - {item}")
    else:
        print("  exclusions: []")
    print(f"  action: {rule['action']}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path = workspace_path("memory", "EXPERT_RULES.md")
    try:
        if args.command == "list":
            store = load_store(path)
            if args.json:
                print(
                    json.dumps(
                        {
                            "schema_version": "expert_rules.v1",
                            "next_id": store.next_id,
                            "count": len(store.rules),
                            "rules": list(store.rules),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            elif not store.rules:
                print("No expert rules.")
            else:
                for rule in store.rules:
                    _print_rule(dict(rule))
            return 0

        if args.command == "show":
            rule = find_rule(load_store(path), args.rule_id)
            _print_rule(rule, as_json=args.json)
            return 0

        if args.command == "validate":
            rule = add_rule(path, _draft_from_args(args), dry_run=True)
            _print_rule(rule, as_json=True)
            print(BYPASS_WARNING, file=sys.stderr)
            return 0

        if args.command == "add":
            rule = add_rule(
                path, _draft_from_args(args), dry_run=args.dry_run
            )
            _print_rule(rule, as_json=True)
            if args.dry_run:
                print("Dry run only; no rule was written.", file=sys.stderr)
            else:
                print(f"Added {rule['id']}.", file=sys.stderr)
            print(BYPASS_WARNING, file=sys.stderr)
            return 0

        if args.command == "remove":
            rule = remove_rule(path, args.rule_id, confirmed=args.yes)
            if args.yes:
                print(f"Removed {rule['id']}.")
            else:
                _print_rule(rule)
                print(
                    "Preview only; rerun with --yes to physically delete this rule."
                )
            return 0
    except ExpertRuleError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    parser.error("unknown expert-rule command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
