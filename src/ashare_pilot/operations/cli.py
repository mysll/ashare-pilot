"""CLI registration for intraday operation commands."""

from __future__ import annotations

import argparse
import importlib
import sys

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace


def _help(namespace: argparse.Namespace, _workspace: Workspace) -> int:
    parser = namespace._parser
    if namespace._command_args:
        parser.error(f"unrecognized arguments: {' '.join(namespace._command_args)}")
    parser.print_help()
    return 0


def _forward(module_name: str, prog: str):
    def handler(namespace: argparse.Namespace, workspace: Workspace | None) -> int:
        previous = sys.argv[0]
        sys.argv[0] = prog
        try:
            module = importlib.import_module(module_name)
            if workspace is None:
                result = module.main(namespace._command_args)
            else:
                with use_workspace(workspace):
                    result = module.main(namespace._command_args)
        finally:
            sys.argv[0] = previous
        return result if isinstance(result, int) else 0
    return handler


def _context(subparsers, name: str, help_text: str):
    parser = subparsers.add_parser(name, help=help_text)
    parser.set_defaults(handler=_help, _parser=parser)
    return parser.add_subparsers(dest=f"operations_{name}_command", metavar="COMMAND")


def _leaf(subparsers, name: str, help_text: str, module: str, *, capability: str = "operations", context: str) -> None:
    parser = subparsers.add_parser(name, add_help=False, help=help_text)
    parser.set_defaults(
        handler=_forward(f"ashare_pilot.{capability}._commands.{module}", f"ashare-pilot {capability} {context} {name}"),
        _parser=parser,
        _forwarded_leaf=True,
    )


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("operations", help="Intraday operation state and decisions.")
    parser.set_defaults(handler=_help, _parser=parser)
    contexts = parser.add_subparsers(dest="operations_context", metavar="CONTEXT")
    snapshot = _context(contexts, "snapshot", "Operation snapshots.")
    _leaf(snapshot, "build", "Build an operation snapshot.", "snapshot", context="snapshot")
    _leaf(snapshot, "validate", "Validate an operation snapshot.", "validate_snapshot", context="snapshot")
    decision = _context(contexts, "decision", "Operation decisions.")
    _leaf(decision, "build", "Build an operation decision.", "decision", context="decision")
    _leaf(decision, "validate", "Validate an operation decision.", "validate_decision", context="decision")
    guide = _context(contexts, "guide", "Operation guide lifecycle.")
    _leaf(guide, "render", "Render the operation guide.", "render_guide", context="guide")
    _leaf(guide, "run", "Run the operation guide lifecycle.", "run_guide", context="guide")
