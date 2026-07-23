from pathlib import Path

import pytest

from ashare_pilot.errors import WorkspaceError
from ashare_pilot.workspace import WORKSPACE_ENV_VAR, resolve_workspace


def make_workspace(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
    (path / "config").mkdir()
    return path.resolve()


def test_explicit_workspace_has_highest_priority(tmp_path: Path) -> None:
    explicit = make_workspace(tmp_path / "explicit")
    configured = make_workspace(tmp_path / "configured")
    discovered = make_workspace(tmp_path / "discovered")

    actual = resolve_workspace(
        explicit,
        environ={WORKSPACE_ENV_VAR: str(configured)},
        cwd=discovered,
    )

    assert actual.root == explicit


def test_environment_workspace_precedes_parent_discovery(tmp_path: Path) -> None:
    configured = make_workspace(tmp_path / "configured")
    discovered = make_workspace(tmp_path / "discovered")

    actual = resolve_workspace(
        environ={WORKSPACE_ENV_VAR: str(configured)},
        cwd=discovered,
    )

    assert actual.root == configured


def test_discovers_workspace_from_nested_directory(tmp_path: Path) -> None:
    root = make_workspace(tmp_path / "project")
    nested = root / "one" / "two"
    nested.mkdir(parents=True)

    actual = resolve_workspace(environ={}, cwd=nested)

    assert actual.root == root
    assert actual.config_dir == root / "config"
    assert actual.resources_dir == root / "resources"


def test_invalid_explicit_workspace_does_not_fall_back(tmp_path: Path) -> None:
    discovered = make_workspace(tmp_path / "discovered")
    invalid = tmp_path / "invalid"
    invalid.mkdir()

    with pytest.raises(WorkspaceError, match="--workspace"):
        resolve_workspace(invalid, environ={}, cwd=discovered)


def test_missing_workspace_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError, match="ASHARE_PILOT_WORKSPACE"):
        resolve_workspace(environ={}, cwd=tmp_path)
