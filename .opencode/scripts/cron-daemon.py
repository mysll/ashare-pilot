"""Trading-day scheduler for configured OpenCode tasks.

The daemon loads all task definitions once at startup, schedules each task on
A-share trading days, and runs due tasks serially. Tasks that became due while
another task was running stay in the in-memory queue; schedules missed while
the daemon was stopped are not replayed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_DIR / ".opencode" / "config" / "cron-tasks.json"
LOG_DIR = PROJECT_DIR / ".opencode" / "logs"
SCHEDULER_LOG_PATH = LOG_DIR / "cron-daemon.log"
TASK_LOG_ROOT = LOG_DIR / "cron-tasks"
SCHEMA_VERSION = "cron_tasks.v1"
DATE_POLICIES = {"T0", "TP1"}
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
TASK_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")


class ConfigurationError(ValueError):
    """Raised when scheduler or calendar configuration is invalid."""


class MissingCalendarYearError(ConfigurationError):
    """Raised when an execution date needs an unconfigured calendar year."""


@dataclass(frozen=True)
class TaskConfig:
    id: str
    enabled: bool
    run_time: datetime_time
    command: str
    date_policy: str
    model: str
    timeout_seconds: int
    order: int

    @property
    def time_text(self) -> str:
        return self.run_time.strftime("%H:%M")


@dataclass(frozen=True)
class SchedulerConfig:
    path: Path
    calendar_path: Path
    tasks: tuple[TaskConfig, ...]

    @property
    def enabled_tasks(self) -> tuple[TaskConfig, ...]:
        return tuple(task for task in self.tasks if task.enabled)


@dataclass(frozen=True)
class ScheduledRun:
    scheduled_at: datetime
    task: TaskConfig


class TradingCalendar:
    """A-share trading calendar loaded from the configured JSON contract."""

    def __init__(self, path: Path):
        self.path = path
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Trading calendar not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"Invalid trading calendar JSON at {path}: {exc}"
            ) from exc

        if not isinstance(raw, dict):
            raise ConfigurationError("Trading calendar root must be an object")
        timezone_name = raw.get("timezone")
        if not isinstance(timezone_name, str) or not timezone_name:
            raise ConfigurationError("Trading calendar must define a timezone")
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError(
                f"Unknown trading calendar timezone: {timezone_name}"
            ) from exc

        years = raw.get("years")
        if not isinstance(years, dict) or not years:
            raise ConfigurationError("Trading calendar must define non-empty years")

        self.known_years: frozenset[int] = frozenset(
            self._parse_year_key(value) for value in years
        )
        closures: set[date] = set()
        for year_text, year_config in years.items():
            if not isinstance(year_config, dict):
                raise ConfigurationError(
                    f"Trading calendar year {year_text} must be an object"
                )
            ranges = year_config.get("closures", [])
            if not isinstance(ranges, list):
                raise ConfigurationError(
                    f"Trading calendar year {year_text}.closures must be a list"
                )
            for item in ranges:
                if not isinstance(item, list) or len(item) != 2:
                    raise ConfigurationError(
                        f"Invalid closure range for {year_text}: {item!r}"
                    )
                try:
                    start = date.fromisoformat(item[0])
                    end = date.fromisoformat(item[1])
                except (TypeError, ValueError) as exc:
                    raise ConfigurationError(
                        f"Invalid closure date range for {year_text}: {item!r}"
                    ) from exc
                expected_year = int(year_text)
                if start.year != expected_year or end.year != expected_year or end < start:
                    raise ConfigurationError(
                        f"Closure range must be ordered and stay within {year_text}: {item!r}"
                    )
                current = start
                while current <= end:
                    closures.add(current)
                    current += timedelta(days=1)
        self.closures = frozenset(closures)

    @staticmethod
    def _parse_year_key(value: object) -> int:
        try:
            year = int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid trading calendar year: {value!r}") from exc
        if str(year) != str(value) or year < 1:
            raise ConfigurationError(f"Invalid trading calendar year: {value!r}")
        return year

    def require_year(self, year: int) -> None:
        if year not in self.known_years:
            raise MissingCalendarYearError(
                f"Trading calendar has no data for {year}. Add that year's closure "
                f"information to {self.path} before starting the daemon."
            )

    def is_trading_day(self, day: date) -> bool:
        self.require_year(day.year)
        return day.weekday() < 5 and day not in self.closures

    def previous_trading_day(self, day: date) -> date:
        current = day - timedelta(days=1)
        while not self.is_trading_day(current):
            current -= timedelta(days=1)
        return current


def _expect_keys(value: dict, allowed: set[str], location: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ConfigurationError(
            f"Unknown field(s) in {location}: {', '.join(sorted(unknown))}"
        )


def _positive_int(value: object, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{location} must be a positive integer")
    return value


def _non_empty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{location} must be a non-empty string")
    return value.strip()


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path.resolve()


def load_config(path: Path) -> SchedulerConfig:
    path = path.resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Scheduler config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid scheduler JSON at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigurationError("Scheduler config root must be an object")
    _expect_keys(raw, {"schema_version", "calendar", "defaults", "tasks"}, "root")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ConfigurationError(
            f"schema_version must be {SCHEMA_VERSION!r}"
        )

    calendar_text = _non_empty_string(raw.get("calendar"), "calendar")
    defaults = raw.get("defaults")
    if not isinstance(defaults, dict):
        raise ConfigurationError("defaults must be an object")
    _expect_keys(defaults, {"model", "timeout_seconds"}, "defaults")
    default_model = _non_empty_string(defaults.get("model"), "defaults.model")
    default_timeout = _positive_int(
        defaults.get("timeout_seconds"), "defaults.timeout_seconds"
    )

    raw_tasks = raw.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ConfigurationError("tasks must be a non-empty list")

    tasks: list[TaskConfig] = []
    ids: set[str] = set()
    for index, item in enumerate(raw_tasks):
        location = f"tasks[{index}]"
        if not isinstance(item, dict):
            raise ConfigurationError(f"{location} must be an object")
        _expect_keys(
            item,
            {
                "id",
                "enabled",
                "time",
                "command",
                "date_policy",
                "model",
                "timeout_seconds",
            },
            location,
        )
        task_id = _non_empty_string(item.get("id"), f"{location}.id")
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise ConfigurationError(
                f"{location}.id must contain only lowercase letters, digits, "
                "hyphens, or underscores"
            )
        if task_id in ids:
            raise ConfigurationError(f"Duplicate task id: {task_id}")
        ids.add(task_id)

        enabled = item.get("enabled")
        if not isinstance(enabled, bool):
            raise ConfigurationError(f"{location}.enabled must be a boolean")

        time_text = _non_empty_string(item.get("time"), f"{location}.time")
        if not TIME_PATTERN.fullmatch(time_text):
            raise ConfigurationError(f"{location}.time must use zero-padded HH:MM")
        run_time = datetime_time.fromisoformat(time_text)

        command = _non_empty_string(item.get("command"), f"{location}.command")
        date_policy = _non_empty_string(
            item.get("date_policy"), f"{location}.date_policy"
        )
        if date_policy not in DATE_POLICIES:
            raise ConfigurationError(
                f"{location}.date_policy must be one of {sorted(DATE_POLICIES)}"
            )

        model = _non_empty_string(
            item.get("model", default_model), f"{location}.model"
        )
        timeout_seconds = _positive_int(
            item.get("timeout_seconds", default_timeout),
            f"{location}.timeout_seconds",
        )
        tasks.append(
            TaskConfig(
                id=task_id,
                enabled=enabled,
                run_time=run_time,
                command=command,
                date_policy=date_policy,
                model=model,
                timeout_seconds=timeout_seconds,
                order=index,
            )
        )

    config = SchedulerConfig(
        path=path,
        calendar_path=_resolve_project_path(calendar_text),
        tasks=tuple(tasks),
    )
    if not config.enabled_tasks:
        raise ConfigurationError("At least one task must be enabled")
    return config


def next_scheduled_runs(
    tasks: tuple[TaskConfig, ...], after: datetime, calendar: TradingCalendar
) -> list[ScheduledRun]:
    """Return all tasks at the first configured time strictly after *after*.

    Dates are scanned before individual task recurrences are considered. This
    matters at year-end: a later task on the last known trading day must still
    run before the scheduler reports that the following calendar year is
    missing.
    """
    local_after = after.astimezone(calendar.timezone)
    current = local_after.date()
    while True:
        calendar.require_year(current.year)
        if calendar.is_trading_day(current):
            candidates = [
                ScheduledRun(
                    scheduled_at=datetime.combine(
                        current, task.run_time, tzinfo=calendar.timezone
                    ),
                    task=task,
                )
                for task in tasks
                if datetime.combine(
                    current, task.run_time, tzinfo=calendar.timezone
                )
                > local_after
            ]
            if candidates:
                first_time = min(run.scheduled_at for run in candidates)
                return sorted(
                    (run for run in candidates if run.scheduled_at == first_time),
                    key=lambda run: run.task.order,
                )
        current += timedelta(days=1)


def processing_date_for(run: ScheduledRun, calendar: TradingCalendar) -> date:
    trigger_day = run.scheduled_at.astimezone(calendar.timezone).date()
    if run.task.date_policy == "T0":
        return trigger_day
    if run.task.date_policy == "TP1":
        return calendar.previous_trading_day(trigger_day)
    raise ConfigurationError(f"Unsupported date policy: {run.task.date_policy}")


def upcoming_runs(
    tasks: tuple[TaskConfig, ...],
    calendar: TradingCalendar,
    after: datetime,
    count: int = 8,
) -> list[ScheduledRun]:
    result: list[ScheduledRun] = []
    cursor = after
    while len(result) < count:
        batch = next_scheduled_runs(tasks, cursor, calendar)
        result.extend(batch[: count - len(result)])
        cursor = batch[0].scheduled_at
    return result


def setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cron-daemon")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def _terminate_process_tree(process: subprocess.Popen, logger: logging.Logger) -> None:
    if process.poll() is not None:
        return
    logger.warning("Terminating active task process tree (pid=%s)", process.pid)
    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, OSError) as exc:
        logger.warning("Could not terminate process tree cleanly: %s", exc)
    finally:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _popen_command(task: TaskConfig, processing_date: date) -> tuple[list[str], dict]:
    prompt = f"{task.command} {processing_date.isoformat()}"
    command = [
        "opencode",
        "run",
        prompt,
        "--model",
        task.model,
        "--dangerously-skip-permissions",
    ]
    if platform.system() == "Windows":
        shell_command = "& " + subprocess.list2cmdline(command)
        return (
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                shell_command,
            ],
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP},
        )
    return command, {"start_new_session": True}


def _stream_pipe(
    pipe,
    destination,
    task_log,
    log_lock: threading.Lock,
) -> None:
    for line in iter(pipe.readline, ""):
        if not line:
            continue
        destination.write(line)
        destination.flush()
        with log_lock:
            task_log.write(line)
            task_log.flush()


def run_task(
    run: ScheduledRun,
    calendar: TradingCalendar,
    logger: logging.Logger,
    task_log_root: Path = TASK_LOG_ROOT,
) -> bool:
    task = run.task
    processing_date = processing_date_for(run, calendar)
    log_dir = task_log_root / run.scheduled_at.date().isoformat()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{task.id}.log"
    command, platform_options = _popen_command(task, processing_date)

    logger.info(
        "Task starting: id=%s scheduled=%s policy=%s processing_date=%s model=%s",
        task.id,
        run.scheduled_at.isoformat(),
        task.date_policy,
        processing_date,
        task.model,
    )
    process: subprocess.Popen | None = None
    try:
        with log_path.open("a", encoding="utf-8") as task_log:
            task_log.write(
                f"\n=== {datetime.now(calendar.timezone).isoformat()} "
                f"task={task.id} processing_date={processing_date} ===\n"
            )
            task_log.flush()
            process = subprocess.Popen(
                command,
                cwd=PROJECT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **platform_options,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            log_lock = threading.Lock()
            stdout_thread = threading.Thread(
                target=_stream_pipe,
                args=(process.stdout, sys.stdout, task_log, log_lock),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_stream_pipe,
                args=(process.stderr, sys.stderr, task_log, log_lock),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()
            try:
                process.wait(timeout=task.timeout_seconds)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(process, logger)
                logger.error(
                    "Task timed out: id=%s timeout_seconds=%s log=%s",
                    task.id,
                    task.timeout_seconds,
                    log_path,
                )
                return False
            except KeyboardInterrupt:
                _terminate_process_tree(process, logger)
                raise
            finally:
                stdout_thread.join(timeout=10)
                stderr_thread.join(timeout=10)
                process.stdout.close()
                process.stderr.close()

        if process.returncode == 0:
            logger.info("Task completed: id=%s log=%s", task.id, log_path)
            return True
        logger.error(
            "Task failed: id=%s exit_code=%s log=%s",
            task.id,
            process.returncode,
            log_path,
        )
        return False
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        if process is not None:
            _terminate_process_tree(process, logger)
        logger.exception("Unexpected task error: id=%s error=%s", task.id, exc)
        return False


def daemon_loop(
    tasks: tuple[TaskConfig, ...],
    calendar: TradingCalendar,
    logger: logging.Logger,
) -> None:
    cursor = datetime.now(calendar.timezone)
    logger.info(
        "Daemon started: timezone=%s tasks=%s",
        calendar.timezone.key,
        ",".join(task.id for task in tasks),
    )

    while True:
        batch = next_scheduled_runs(tasks, cursor, calendar)
        scheduled_at = batch[0].scheduled_at
        logger.info(
            "Next task%s: ids=%s scheduled=%s",
            "s" if len(batch) > 1 else "",
            ",".join(run.task.id for run in batch),
            scheduled_at.isoformat(),
        )
        delay = (scheduled_at - datetime.now(calendar.timezone)).total_seconds()
        if delay > 0:
            time.sleep(delay)
        for run in batch:
            run_task(run, calendar, logger)
        cursor = scheduled_at


def _config_path_from_argument(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _print_schedule(
    logger: logging.Logger,
    tasks: tuple[TaskConfig, ...],
    calendar: TradingCalendar,
    now: datetime,
    count: int,
) -> None:
    logger.info("Upcoming trading-day tasks:")
    for run in upcoming_runs(tasks, calendar, now, count=count):
        logger.info(
            "  %s  %-18s processing_date=%s (%s)",
            run.scheduled_at.isoformat(),
            run.task.id,
            processing_date_for(run, calendar),
            run.task.date_policy,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run configured OpenCode tasks on A-share trading days"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"scheduler config path (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate config, show upcoming task runs, and exit",
    )
    parser.add_argument(
        "--once",
        metavar="TASK_ID",
        help="run one configured task immediately on the current trading day",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger = setup_logger(SCHEDULER_LOG_PATH)
    try:
        config = load_config(_config_path_from_argument(args.config))
        calendar = TradingCalendar(config.calendar_path)
        now = datetime.now(calendar.timezone)
        logger.info("PROJECT_DIR: %s", PROJECT_DIR)
        logger.info("Config loaded: %s", config.path)
        logger.info("Trading calendar: %s", calendar.path)

        if args.once:
            matching = [task for task in config.tasks if task.id == args.once]
            if not matching:
                raise ConfigurationError(f"Unknown task id for --once: {args.once}")
            task = matching[0]
            if not task.enabled:
                raise ConfigurationError(f"Task is disabled: {task.id}")
            if not calendar.is_trading_day(now.date()):
                raise ConfigurationError(
                    f"--once requires a trading day; {now.date()} is not one"
                )
            scheduled_at = datetime.combine(
                now.date(), task.run_time, tzinfo=calendar.timezone
            )
            succeeded = run_task(
                ScheduledRun(scheduled_at=scheduled_at, task=task),
                calendar,
                logger,
            )
            return 0 if succeeded else 1

        _print_schedule(
            logger,
            config.enabled_tasks,
            calendar,
            now,
            count=8 if args.dry_run else 1,
        )
        if args.dry_run:
            logger.info("Dry run complete.")
            return 0

        daemon_loop(config.enabled_tasks, calendar, logger)
        return 0
    except (ConfigurationError, MissingCalendarYearError) as exc:
        logger.error("Configuration error: %s", exc)
        return 2
    except KeyboardInterrupt:
        logger.info("Daemon stopped by user. No missed task will be replayed.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
