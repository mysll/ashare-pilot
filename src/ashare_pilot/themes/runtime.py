"""Dynamic Workspace-backed paths for theme-library operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import current_workspace


class WorkspacePath(os.PathLike[str]):
    """A path proxy resolved against the active Workspace on every operation."""

    __slots__ = ("_parts",)

    def __init__(self, *parts: str):
        self._parts = tuple(parts)

    def resolve_path(self) -> Path:
        return current_workspace().root.joinpath(*self._parts)

    def __fspath__(self) -> str:
        return os.fspath(self.resolve_path())

    def __str__(self) -> str:
        return str(self.resolve_path())

    def __repr__(self) -> str:
        return f"WorkspacePath({', '.join(repr(p) for p in self._parts)})"

    def __truediv__(self, other: str | os.PathLike[str]) -> WorkspacePath:
        return WorkspacePath(*self._parts, os.fspath(other))

    @property
    def parent(self) -> WorkspacePath:
        return WorkspacePath(*self._parts[:-1])

    def __getattr__(self, name: str) -> Any:
        return getattr(self.resolve_path(), name)


def workspace_path(*parts: str) -> WorkspacePath:
    return WorkspacePath(*parts)


def theme_data_path(*parts: str) -> WorkspacePath:
    return WorkspacePath("data", "theme-library", *parts)


def theme_cache_path(*parts: str) -> WorkspacePath:
    return WorkspacePath(".cache", "theme-library", *parts)


def theme_config_path(*parts: str) -> WorkspacePath:
    return WorkspacePath("config", "themes", *parts)
