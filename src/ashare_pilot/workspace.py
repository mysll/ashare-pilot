"""Resolve and represent the A-Share Pilot project workspace."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ashare_pilot.errors import WorkspaceError

WORKSPACE_ENV_VAR = "ASHARE_PILOT_WORKSPACE"


@dataclass(frozen=True, slots=True)
class Workspace:
    """Explicit paths belonging to one A-Share Pilot workspace."""

    root: Path

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def resources_dir(self) -> Path:
        return self.root / "resources"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def cache_dir(self) -> Path:
        return self.root / ".cache"


def resolve_workspace(
    explicit: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> Workspace:
    """Resolve a workspace using CLI, environment, then parent discovery.

    Explicit and environment-provided paths are authoritative. If either is
    present but invalid, resolution fails instead of silently falling back.
    """

    environment = os.environ if environ is None else environ

    if explicit is not None:
        return _workspace_from_candidate(explicit, source="--workspace")

    configured = environment.get(WORKSPACE_ENV_VAR)
    if configured:
        return _workspace_from_candidate(configured, source=WORKSPACE_ENV_VAR)

    start = Path.cwd() if cwd is None else Path(cwd)
    start = start.expanduser().resolve()
    for candidate in (start, *start.parents):
        if _is_workspace_root(candidate):
            return Workspace(candidate)

    raise WorkspaceError(
        f"Could not locate an A-Share Pilot workspace from {start}. "
        f"Use --workspace or set {WORKSPACE_ENV_VAR}."
    )


def _workspace_from_candidate(
    candidate: str | os.PathLike[str], *, source: str
) -> Workspace:
    root = Path(candidate).expanduser().resolve()
    if not _is_workspace_root(root):
        raise WorkspaceError(
            f"Invalid workspace from {source}: {root}. "
            "Expected both pyproject.toml and config/."
        )
    return Workspace(root)


def _is_workspace_root(candidate: Path) -> bool:
    return (candidate / "pyproject.toml").is_file() and (candidate / "config").is_dir()
