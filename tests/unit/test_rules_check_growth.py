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
        "EXPERT_RULES.md",
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

    expert_path = memory / "EXPERT_RULES.md"
    expert_text = expert_path.read_text(encoding="utf-8")
    invalid_rule = """[
    {
      "id": "E001",
      "name": "unsupported operation rule",
      "applies_to": ["OPERATION_GUIDE"],
      "decision_layer": "ENTRY_POSITION",
      "condition": "always",
      "exclusions": [],
      "action": "upgrade class"
    }
  ]"""
    expert_path.write_text(
        expert_text.replace('"next_id": 1', '"next_id": 2').replace(
            '"rules": []', f'"rules": {invalid_rule}'
        ),
        encoding="utf-8",
    )

    errors = check_rule_governance(tmp_path)
    assert any("expert:" in error and "OPERATION_GUIDE" in error for error in errors)
