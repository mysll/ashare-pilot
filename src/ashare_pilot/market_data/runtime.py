"""Workspace context for market-data runtime boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from ashare_pilot.workspace import Workspace, resolve_workspace

_CURRENT_WORKSPACE: ContextVar[Workspace | None] = ContextVar(
    "ashare_pilot_market_data_workspace", default=None
)


@contextmanager
def use_workspace(workspace: Workspace) -> Iterator[None]:
    """Make an explicitly resolved workspace available to internal boundaries."""

    token = _CURRENT_WORKSPACE.set(workspace)
    try:
        yield
    finally:
        _CURRENT_WORKSPACE.reset(token)


def current_workspace() -> Workspace:
    """Return the explicit context, or resolve one using the public rules."""

    workspace = _CURRENT_WORKSPACE.get()
    return workspace if workspace is not None else resolve_workspace()


def workspace_path(*parts: str) -> Path:
    return current_workspace().root.joinpath(*parts)
