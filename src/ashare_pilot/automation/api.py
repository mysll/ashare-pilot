"""Public APIs for scheduling, governance, and pipeline automation."""

from pathlib import Path

from ashare_pilot.automation._commands import intraday, memory_init, rules_check, scheduler
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace


def check_rule_governance(*, workspace: Workspace) -> list[str]:
    return rules_check.check_rule_governance(workspace.root)


def initialize_memory(*, workspace: Workspace) -> tuple[list[Path], list[Path]]:
    return memory_init.initialize_memory(workspace.root)


def load_scheduler_config(
    path: Path | None = None, *, workspace: Workspace
) -> scheduler.SchedulerConfig:
    with use_workspace(workspace):
        return scheduler.load_config(path or workspace.root / "config" / "cron-tasks.json")


def run_intraday_pipeline(argv: list[str], *, workspace: Workspace) -> int:
    with use_workspace(workspace):
        result = intraday.main(argv)
    return result if isinstance(result, int) else 0


__all__ = [
    "check_rule_governance",
    "initialize_memory",
    "load_scheduler_config",
    "run_intraday_pipeline",
    "scheduler",
]
