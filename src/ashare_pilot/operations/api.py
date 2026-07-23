"""Public APIs for intraday operation computation and contracts."""

from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.operations._commands.decision import build as _build_decision
from ashare_pilot.operations._commands.render_guide import render as render_operation_guide
from ashare_pilot.operations._commands.snapshot import build_stock_snapshot as _build_stock_snapshot
from ashare_pilot.operations._commands.validate_decision import validate as validate_operation_decision
from ashare_pilot.operations._commands.validate_snapshot import validate as validate_operation_snapshot
from ashare_pilot.workspace import Workspace


def build_operation_decision(snapshot: dict[str, Any], source_path: Path) -> dict[str, Any]:
    return _build_decision(snapshot, source_path)


def build_stock_snapshot(*args: Any, workspace: Workspace, **kwargs: Any) -> dict[str, Any]:
    with use_workspace(workspace):
        return _build_stock_snapshot(*args, **kwargs)


__all__ = [
    "build_operation_decision",
    "build_stock_snapshot",
    "render_operation_guide",
    "validate_operation_decision",
    "validate_operation_snapshot",
]
