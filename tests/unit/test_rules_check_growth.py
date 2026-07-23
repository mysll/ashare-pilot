from __future__ import annotations

import shutil
from pathlib import Path

from ashare_pilot.automation._commands.rules_check import check_rule_governance


ROOT = Path(__file__).resolve().parents[2]


def test_rule_governance_allows_organic_rule_growth(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    memory.mkdir()
    for name in (
        "RULES.md",
        "SHARED_RULES.md",
        "INTRADAY_RULES.md",
        "RULE_GOVERNANCE.md",
        "MEMORY.md",
    ):
        shutil.copyfile(ROOT / "memory" / name, memory / name)
    for name in ("AGENTS.md", "CLAUDE.md"):
        shutil.copyfile(ROOT / name, tmp_path / name)

    rules_path = memory / "RULES.md"
    text = rules_path.read_text(encoding="utf-8")
    learned_rule = "| R900 | EMPIRICAL / ⚠️ | organically learned rule | actual review evidence |"
    rules_path.write_text(
        text.replace(
            "\n## 候选规则（不执行、不计容量）",
            f"\n{learned_rule}\n\n## 候选规则（不执行、不计容量）",
            1,
        ),
        encoding="utf-8",
    )

    assert check_rule_governance(tmp_path) == []

