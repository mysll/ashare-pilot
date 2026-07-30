"""CLI registration for scheduler, governance, and intraday automation."""

from __future__ import annotations

import argparse

from ashare_pilot.operations.cli import _context, _help, _leaf


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("automation", help="Scheduling and rule governance.")
    parser.set_defaults(handler=_help, _parser=parser)
    contexts = parser.add_subparsers(dest="automation_context", metavar="CONTEXT")

    rules = _context(contexts, "rules", "Rule-governance checks.")
    _leaf(rules, "check", "Check the rule-governance contract.", "rules_check", capability="automation", context="rules")
    _leaf(
        rules,
        "expert",
        "Manage directly authorized expert rules.",
        "expert_rules",
        capability="automation",
        context="rules",
    )

    memory = _context(contexts, "memory", "Zero-history memory lifecycle.")
    _leaf(memory, "init", "Initialize memory files and empty rule templates.", "memory_init", capability="automation", context="memory")

    scheduler = _context(contexts, "scheduler", "Trading-day task scheduler.")
    _leaf(scheduler, "run", "Run or inspect the task scheduler.", "scheduler", capability="automation", context="scheduler")

    intraday = _context(contexts, "intraday", "Intraday compute pipeline.")
    _leaf(intraday, "run", "Run the intraday compute pipeline.", "intraday", capability="automation", context="intraday")
