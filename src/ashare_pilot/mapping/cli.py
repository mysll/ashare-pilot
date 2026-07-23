"""CLI registration for daily and intraday mapping commands."""

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
    parser.set_defaults(
        handler=_forward(module_name, prog),
        _parser=parser,
        _forwarded_leaf=True,
    )


def _context(subparsers, name: str, help_text: str):
    parser = subparsers.add_parser(name, help=help_text)
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    return parser.add_subparsers(dest=f"mapping_{name}_command", metavar="COMMAND")


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "mapping", help="Candidate mapping and evidence contracts."
    )
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    contexts = parser.add_subparsers(dest="mapping_context", metavar="CONTEXT")

    daily = _context(contexts, "daily", "Pre-market mapping pipeline.")
    daily_commands = {
        "build-theme-evidence": ("Build compact theme evidence.", "theme_evidence"),
        "build-theme-stock-universe": ("Build the theme-stock universe.", "theme_stock_universe"),
        "build-theme-stock-base": ("Build deterministic theme-stock base.", "theme_stock_base"),
        "build-theme-stocks": ("Publish theme_stocks.json.", "theme_stocks"),
        "validate-themes": ("Validate themes.json.", "validate_themes"),
        "validate-theme-stocks": ("Validate theme_stocks.json.", "validate_theme_stocks"),
        "build-mapper-base": ("Build deterministic mapper base.", "mapper_base"),
        "validate-annotations": ("Validate mapper annotations.", "validate_annotations"),
        "build-mapper": ("Merge daily mapper annotations.", "mapper"),
        "validate-mapper": ("Validate mapper.json.", "validate_mapper"),
        "build-strategy-view": ("Build the Step 3 projection.", "strategy_view"),
        "build-timing": ("Update Step 2 timing report.", "timing"),
        "prepare": ("Prepare deterministic Step 2 inputs.", "prepare"),
        "finalize": ("Finalize Step 2 outputs.", "finalize"),
        "compare-regression": ("Compare Step 2 regression outputs.", "compare_regression"),
    }
    for command, (help_text, module) in daily_commands.items():
        _leaf(
            daily,
            command,
            help_text,
            f"ashare_pilot.mapping._commands.daily.{module}",
            f"ashare-pilot mapping daily {command}",
        )

    intraday = _context(contexts, "intraday", "Intraday mapping pipeline.")
    intraday_commands = {
        "build-scan-pool": ("Build the intraday scan pool.", "scan_pool"),
        "enrich-compute-pool": ("Enrich the intraday compute pool.", "compute_pool"),
        "build-mapper-base": ("Build deterministic intraday mapper base.", "mapper_base"),
        "validate-annotations": ("Validate intraday mapper annotations.", "validate_annotations"),
        "build-mapper": ("Merge intraday mapper annotations.", "mapper"),
        "validate-mapper": ("Validate intraday_mapper.json.", "validate_mapper"),
    }
    for command, (help_text, module) in intraday_commands.items():
        _leaf(
            intraday,
            command,
            help_text,
            f"ashare_pilot.mapping._commands.intraday.{module}",
            f"ashare-pilot mapping intraday {command}",
        )
