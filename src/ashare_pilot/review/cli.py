"""CLI registration for daily review commands."""

from __future__ import annotations

import argparse

from ashare_pilot.operations.cli import _context, _leaf, _help


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("review", help="Verification, review, and backtesting.")
    parser.set_defaults(handler=_help, _parser=parser)
    contexts = parser.add_subparsers(dest="review_context", metavar="CONTEXT")
    daily = _context(contexts, "daily", "Daily verification and backtests.")
    _leaf(daily, "verify", "Generate verification JSON.", "verify", capability="review", context="daily")
    _leaf(daily, "backtest-entry-band", "Backtest entry bands.", "backtest_entry_band", capability="review", context="daily")
    _leaf(daily, "backtest-entry-quality", "Backtest entry quality.", "backtest_entry_quality", capability="review", context="daily")
