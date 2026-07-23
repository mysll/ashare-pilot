from __future__ import annotations

import dataclasses
import importlib.util
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ashare_pilot.automation._commands import intraday, rules_check, scheduler
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace

ROOT = Path(__file__).resolve().parents[2]
LEGACY_SCRIPTS = ROOT / ".opencode" / "scripts"


def load_old(name: str, path: Path):
    if not path.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def task_shape(config) -> list[dict]:
    return [dataclasses.asdict(task) for task in config.tasks]


def test_root_scheduler_config_and_schedule_match_legacy() -> None:
    old = load_old("legacy_scheduler_batch7", LEGACY_SCRIPTS / "cron-daemon.py")
    old_config = old.load_config(ROOT / ".opencode" / "config" / "cron-tasks.json")
    with use_workspace(Workspace(ROOT)):
        new_config = scheduler.load_config(ROOT / "config" / "cron-tasks.json")
    assert task_shape(new_config) == task_shape(old_config)
    old_calendar = old.TradingCalendar(old_config.calendar_path)
    new_calendar = scheduler.TradingCalendar(new_config.calendar_path)
    after = datetime(2026, 9, 30, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    old_runs = old.upcoming_runs(old_config.enabled_tasks, old_calendar, after, count=8)
    new_runs = scheduler.upcoming_runs(new_config.enabled_tasks, new_calendar, after, count=8)
    assert [(run.scheduled_at, run.task.id, old.processing_date_for(run, old_calendar)) for run in old_runs] == [
        (run.scheduled_at, run.task.id, scheduler.processing_date_for(run, new_calendar)) for run in new_runs
    ]


def test_rule_governance_matches_legacy_and_detects_contract_failures(tmp_path: Path) -> None:
    old = load_old("legacy_rules_batch7", LEGACY_SCRIPTS / "check_rule_governance.py")
    assert old.main([]) == 0
    assert rules_check.check_rule_governance(ROOT) == []

    memory = tmp_path / "memory"
    memory.mkdir()
    for name in ("RULES.md", "SHARED_RULES.md", "INTRADAY_RULES.md", "RULE_GOVERNANCE.md", "MEMORY.md"):
        shutil.copyfile(ROOT / "memory" / name, memory / name)
    for name in ("AGENTS.md", "CLAUDE.md"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    rules_path = memory / "RULES.md"
    text = rules_path.read_text(encoding="utf-8")
    duplicate = next(line for line in text.splitlines() if line.startswith("| R32 |"))
    rules_path.write_text(text.replace(duplicate, duplicate + "\n" + duplicate, 1), encoding="utf-8")
    errors = rules_check.check_rule_governance(tmp_path)
    assert any("duplicate executable IDs" in error for error in errors)

    rules_path.write_text(text, encoding="utf-8")
    additions = "\n".join(
        f"| R{900 + index} | EMPIRICAL / ⚠️ | frozen capacity case | test |"
        for index in range(4)
    )
    rules_path.write_text(
        text.replace("\n## 候选规则（不执行、不计容量）", f"\n{additions}\n\n## 候选规则（不执行、不计容量）", 1),
        encoding="utf-8",
    )
    governance_path = memory / "RULE_GOVERNANCE.md"
    governance_path.write_text(
        governance_path.read_text(encoding="utf-8").replace("NO_TRADE_CONFLICT", "REMOVED_CONFLICT_TOKEN"),
        encoding="utf-8",
    )
    errors = rules_check.check_rule_governance(tmp_path)
    assert any("capacity 21/20 exceeded" in error for error in errors)
    assert any("missing required token 'NO_TRADE_CONFLICT'" in error for error in errors)


def test_intraday_pipeline_uses_only_public_cli_commands(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    commands: list[list[str]] = []
    monkeypatch.setattr(intraday._cache_ds, "fetch_all_astocks", lambda cache_dir: [])

    def fake_run(command: list[str], label: str = "") -> dict:
        commands.append(command)
        return {"success": True, "stdout": "", "stderr": "", "elapsed": 0.0}

    monkeypatch.setattr(intraday, "run_cmd", fake_run)
    with use_workspace(Workspace(tmp_path)):
        assert intraday.main(["--date", "2026-07-22"]) is None
    assert len(commands) == 8
    assert all(command[:3] == [sys.executable, "-m", "ashare_pilot"] for command in commands)
    assert all(".opencode" not in " ".join(command) for command in commands)
    actions = [tuple(command[5:8]) for command in commands]
    assert ("market-data", "breadth", "--json") in actions
    assert ("mapping", "intraday", "build-scan-pool") in actions
    assert ("strategy", "overnight", "score") in actions
    assert (tmp_path / ".cache" / "intraday" / "2026-07-22").is_dir()
    assert (tmp_path / "intraday" / "2026-07-22").is_dir()


def test_scheduler_dry_run_and_ctrl_c_exit_codes(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copyfile(ROOT / "config" / "trading-calendar.json", config_dir / "trading-calendar.json")
    raw = json.loads((ROOT / "config" / "cron-tasks.json").read_text(encoding="utf-8"))
    (config_dir / "cron-tasks.json").write_text(json.dumps(raw), encoding="utf-8")
    workspace = Workspace(tmp_path)
    with use_workspace(workspace):
        assert scheduler.main(["--dry-run"]) == 0
        monkeypatch.setattr(scheduler, "daemon_loop", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
        assert scheduler.main([]) == 130
    assert (tmp_path / "logs" / "cron-daemon.log").exists()
