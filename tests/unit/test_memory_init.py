from __future__ import annotations

import re
import shutil
from pathlib import Path

from ashare_pilot.automation import check_rule_governance, initialize_memory
from ashare_pilot.workspace import Workspace


ROOT = Path(__file__).resolve().parents[2]


def make_workspace(path: Path) -> Workspace:
    path.mkdir()
    (path / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\nversion = '0'\n",
        encoding="utf-8",
    )
    (path / "config").mkdir()
    for guide in ("AGENTS.md", "CLAUDE.md"):
        (path / guide).write_text("See memory/RULE_GOVERNANCE.md\n", encoding="utf-8")
    template_parent = path / "resources" / "templates"
    template_parent.mkdir(parents=True)
    shutil.copytree(ROOT / "resources" / "templates" / "memory", template_parent / "memory")
    return Workspace(path)


def test_initialize_memory_creates_empty_rule_templates(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path / "workspace")

    created, existing = initialize_memory(workspace=workspace)

    assert existing == []
    assert {path.relative_to(workspace.root).as_posix() for path in created} == {
        "memory/MEMORY.md",
        "memory/RULE_GOVERNANCE.md",
        "memory/PERFORMANCE.md",
        "memory/RULES.md",
        "memory/SHARED_RULES.md",
        "memory/INTRADAY_RULES.md",
        "memory/EXPERT_RULES.md",
        "memory/daily/INDEX.md",
        "memory/intraday/INDEX.md",
    }
    for name in ("RULES.md", "SHARED_RULES.md", "INTRADAY_RULES.md"):
        text = (workspace.root / "memory" / name).read_text(encoding="utf-8")
        assert "## 可执行规则族" in text
        assert "## 候选规则（不执行、不计容量）" in text
        assert "RULE_GOVERNANCE.md" in text
        assert not any(re.match(r"\| [RI]\d+", line) for line in text.splitlines())
    expert_text = (workspace.root / "memory" / "EXPERT_RULES.md").read_text(
        encoding="utf-8"
    )
    assert '"schema_version": "expert_rules.v1"' in expert_text
    assert '"next_id": 1' in expert_text
    assert '"rules": []' in expert_text
    assert "空规则模板" in (workspace.root / "memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert check_rule_governance(workspace=workspace) == []


def test_initialize_memory_is_idempotent_and_never_overwrites(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path / "workspace")
    initialize_memory(workspace=workspace)
    memory_path = workspace.root / "memory" / "MEMORY.md"
    memory_path.write_text("user-owned memory\n", encoding="utf-8")

    created, existing = initialize_memory(workspace=workspace)

    assert created == []
    assert len(existing) == 9
    assert memory_path.read_text(encoding="utf-8") == "user-owned memory\n"
