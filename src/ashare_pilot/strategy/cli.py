"""CLI registration for daily and overnight strategy commands."""

from __future__ import annotations

import argparse
import importlib
import sys

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace


def _show_group_help(namespace: argparse.Namespace, _workspace: Workspace) -> int:
    parser: argparse.ArgumentParser = namespace._parser
    if namespace._command_args:
        parser.error(f"unrecognized arguments: {' '.join(namespace._command_args)}")
    parser.print_help()
    return 0


def _forward(module_name: str, prog: str):
    def handler(namespace: argparse.Namespace, workspace: Workspace | None) -> int:
        previous_prog = sys.argv[0]
        sys.argv[0] = prog
        try:
            if workspace is None:
                module = importlib.import_module(module_name)
                result = module.main(namespace._command_args)
            else:
                with use_workspace(workspace):
                    module = importlib.import_module(module_name)
                    result = module.main(namespace._command_args)
        finally:
            sys.argv[0] = previous_prog
        return result if isinstance(result, int) else 0

    return handler


def _leaf(subparsers, name: str, help_text: str, module_name: str, prog: str):
    parser = subparsers.add_parser(name, add_help=False, help=help_text)
    parser.set_defaults(handler=_forward(module_name, prog), _parser=parser, _forwarded_leaf=True)


def _context(subparsers, name: str, help_text: str):
    parser = subparsers.add_parser(name, help=help_text)
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    return parser.add_subparsers(dest=f"strategy_{name}_command", metavar="COMMAND")


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("strategy", help="Daily and overnight strategy contracts.")
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    contexts = parser.add_subparsers(dest="strategy_context", metavar="CONTEXT")

    daily = _context(contexts, "daily", "Pre-market strategy pipeline.")
    daily_commands = {
        "build-llm-input": ("Build compact Step 3 LLM input.", "llm_input"),
        "compute-trade-profile": ("Compute deterministic Trade Profiles.", "trade_profile"),
        "normalize-selection": ("Normalize strategy selection limits.", "normalize_selection"),
        "validate-draft": ("Validate the LLM strategy draft.", "validate_draft"),
        "validate": ("Validate the final daily strategy.", "validate_strategy"),
        "build-timing": ("Update Step 3 timing report.", "timing"),
        "prepare": ("Prepare deterministic Step 3 inputs.", "prepare"),
        "finalize": ("Finalize and publish daily strategy.", "finalize"),
        "render-report": ("Render the daily HTML report.", "render_report"),
        "compare-shadow": ("Compare daily strategy shadow outputs.", "compare_shadow"),
    }
    for command, (help_text, module) in daily_commands.items():
        _leaf(daily, command, help_text, f"ashare_pilot.strategy._commands.daily.{module}", f"ashare-pilot strategy daily {command}")

    overnight = _context(contexts, "overnight", "Overnight strategy pipeline.")
    overnight_commands = {
        "score": ("Score the enriched intraday pool.", "score"),
        "build": ("Build overnight_strategy.json.", "build"),
        "validate": ("Validate overnight_strategy.json.", "validate"),
        "render-report": ("Render the overnight HTML report.", "render_report"),
    }
    for command, (help_text, module) in overnight_commands.items():
        _leaf(overnight, command, help_text, f"ashare_pilot.strategy._commands.overnight.{module}", f"ashare-pilot strategy overnight {command}")
