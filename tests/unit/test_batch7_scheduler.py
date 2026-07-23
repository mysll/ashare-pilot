import contextlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo


from ashare_pilot.automation._commands import scheduler as cron_daemon

ROOT = Path(__file__).resolve().parents[2]


SHANGHAI = ZoneInfo("Asia/Shanghai")


def write_calendar(root: Path, years: dict | None = None) -> Path:
    path = root / "trading-calendar.json"
    path.write_text(
        json.dumps(
            {
                "market": "A-share",
                "timezone": "Asia/Shanghai",
                "years": years
                or {
                    "2026": {
                        "closures": [
                            ["2026-10-01", "2026-10-07"],
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def task(
    task_id: str,
    run_time: str,
    policy: str = "T0",
    order: int = 0,
    timeout: int = 7200,
):
    return cron_daemon.TaskConfig(
        id=task_id,
        enabled=True,
        run_time=time.fromisoformat(run_time),
        command=f"/{task_id}",
        date_policy=policy,
        model="provider/model",
        timeout_seconds=timeout,
        order=order,
    )


class ConfigTests(unittest.TestCase):
    def test_default_config_loads_four_tasks_and_overrides_defaults(self):
        config = cron_daemon.load_config(ROOT / "config" / "cron-tasks.json")
        self.assertEqual(
            [item.id for item in config.enabled_tasks],
            [
                "daily-analysis",
                "intraday-review",
                "intraday-analysis",
                "daily-review",
            ],
        )
        self.assertEqual(config.tasks[0].time_text, "09:20")
        self.assertEqual(config.tasks[1].date_policy, "TP1")
        self.assertEqual(config.tasks[0].timeout_seconds, 7200)

    def test_invalid_time_and_unknown_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calendar_path = write_calendar(root)
            raw = {
                "schema_version": "cron_tasks.v1",
                "calendar": str(calendar_path),
                "defaults": {
                    "model": "provider/model",
                    "timeout_seconds": 10,
                },
                "tasks": [
                    {
                        "id": "bad",
                        "enabled": True,
                        "time": "9:20",
                        "command": "/bad",
                        "date_policy": "T0",
                    }
                ],
            }
            config_path = root / "tasks.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(
                cron_daemon.ConfigurationError, "zero-padded HH:MM"
            ):
                cron_daemon.load_config(config_path)

            raw["tasks"][0]["time"] = "09:20"
            raw["tasks"][0]["typo"] = True
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(cron_daemon.ConfigurationError, "typo"):
                cron_daemon.load_config(config_path)

            del raw["tasks"][0]["typo"]
            raw["tasks"][0]["id"] = "../escape"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(
                cron_daemon.ConfigurationError, "lowercase letters"
            ):
                cron_daemon.load_config(config_path)

    def test_disabled_only_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calendar_path = write_calendar(root)
            config_path = root / "tasks.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": "cron_tasks.v1",
                        "calendar": str(calendar_path),
                        "defaults": {
                            "model": "provider/model",
                            "timeout_seconds": 10,
                        },
                        "tasks": [
                            {
                                "id": "disabled",
                                "enabled": False,
                                "time": "09:20",
                                "command": "/disabled",
                                "date_policy": "T0",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                cron_daemon.ConfigurationError, "At least one task"
            ):
                cron_daemon.load_config(config_path)


class CalendarAndSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.calendar = cron_daemon.TradingCalendar(write_calendar(self.root))
        self.tasks = (
            task("daily-analysis", "09:20", order=0),
            task("intraday-review", "09:45", policy="TP1", order=1),
            task("intraday-analysis", "14:30", order=2),
            task("daily-review", "15:10", order=3),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_no_startup_catchup_uses_next_future_time(self):
        after = datetime(2026, 7, 21, 9, 21, tzinfo=SHANGHAI)
        runs = cron_daemon.next_scheduled_runs(self.tasks, after, self.calendar)
        self.assertEqual([run.task.id for run in runs], ["intraday-review"])
        self.assertEqual(runs[0].scheduled_at.hour, 9)
        self.assertEqual(runs[0].scheduled_at.minute, 45)

    def test_tasks_due_while_busy_remain_reachable_from_schedule_cursor(self):
        first = cron_daemon.next_scheduled_runs(
            self.tasks,
            datetime(2026, 7, 21, 9, 0, tzinfo=SHANGHAI),
            self.calendar,
        )
        self.assertEqual(first[0].task.id, "daily-analysis")
        second = cron_daemon.next_scheduled_runs(
            self.tasks, first[0].scheduled_at, self.calendar
        )
        self.assertEqual(second[0].task.id, "intraday-review")

    def test_same_time_tasks_follow_config_order(self):
        same_time = (
            task("second", "09:20", order=1),
            task("first", "09:20", order=0),
        )
        runs = cron_daemon.next_scheduled_runs(
            same_time,
            datetime(2026, 7, 21, 9, 0, tzinfo=SHANGHAI),
            self.calendar,
        )
        self.assertEqual([run.task.id for run in runs], ["first", "second"])

    def test_holiday_is_skipped_and_tp1_uses_previous_trading_day(self):
        runs = cron_daemon.next_scheduled_runs(
            self.tasks,
            datetime(2026, 9, 30, 16, 0, tzinfo=SHANGHAI),
            self.calendar,
        )
        self.assertEqual(runs[0].scheduled_at.date(), date(2026, 10, 8))
        review = cron_daemon.ScheduledRun(
            scheduled_at=datetime(2026, 10, 8, 9, 45, tzinfo=SHANGHAI),
            task=self.tasks[1],
        )
        self.assertEqual(
            cron_daemon.processing_date_for(review, self.calendar),
            date(2026, 9, 30),
        )

    def test_missing_year_errors_only_when_it_is_needed_by_next_task(self):
        after_early_task = datetime(2026, 12, 31, 14, 31, tzinfo=SHANGHAI)
        runs = cron_daemon.next_scheduled_runs(
            self.tasks, after_early_task, self.calendar
        )
        self.assertEqual(runs[0].task.id, "daily-review")

        with self.assertRaisesRegex(
            cron_daemon.MissingCalendarYearError, "no data for 2027"
        ):
            cron_daemon.next_scheduled_runs(
                self.tasks,
                datetime(2026, 12, 31, 15, 11, tzinfo=SHANGHAI),
                self.calendar,
            )

    def test_wait_rechecks_wall_clock_every_minute_then_every_second(self):
        current = [datetime(2026, 7, 21, 9, 0, tzinfo=SHANGHAI)]
        scheduled_at = current[0] + timedelta(seconds=121)
        sleeps: list[float] = []

        def sleep_and_advance(seconds: float) -> None:
            sleeps.append(seconds)
            current[0] += timedelta(seconds=seconds)
            if len(sleeps) == 1:
                current[0] += timedelta(seconds=30)

        cron_daemon._wait_until(
            scheduled_at,
            SHANGHAI,
            now_fn=lambda: current[0],
            sleep_fn=sleep_and_advance,
        )

        self.assertEqual(sleeps[0], 60.0)
        self.assertEqual(sleeps[1:], [1.0] * 31)
        self.assertEqual(current[0], scheduled_at)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.calendar = cron_daemon.TradingCalendar(write_calendar(self.root))
        self.logger = logging.getLogger(f"cron-test-{id(self)}")
        self.logger.handlers.clear()
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_failed_task_returns_false_and_writes_separate_log(self):
        run = cron_daemon.ScheduledRun(
            scheduled_at=datetime(2026, 7, 21, 9, 20, tzinfo=SHANGHAI),
            task=task("failure", "09:20"),
        )
        command = [
            sys.executable,
            "-c",
            "import sys; print('task output'); sys.exit(7)",
        ]
        options = {"start_new_session": True} if os.name != "nt" else {}
        with mock.patch.object(
            cron_daemon, "_popen_command", return_value=(command, options)
        ):
            self.assertFalse(
                cron_daemon.run_task(
                    run, self.calendar, self.logger, task_log_root=self.root / "logs"
                )
            )
        log_path = self.root / "logs" / "2026-07-21" / "failure.log"
        self.assertIn("task output", log_path.read_text(encoding="utf-8"))

    def test_timed_out_task_is_terminated_and_returns_false(self):
        run = cron_daemon.ScheduledRun(
            scheduled_at=datetime(2026, 7, 21, 9, 20, tzinfo=SHANGHAI),
            task=task("timeout", "09:20", timeout=1),
        )
        command = [sys.executable, "-c", "import time; time.sleep(30)"]
        options = {"start_new_session": True} if os.name != "nt" else {}
        with mock.patch.object(
            cron_daemon, "_popen_command", return_value=(command, options)
        ):
            self.assertFalse(
                cron_daemon.run_task(
                    run, self.calendar, self.logger, task_log_root=self.root / "logs"
                )
            )

    @unittest.skipIf(os.name == "nt", "POSIX process-group assertion")
    def test_process_tree_termination_stops_active_process(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
        )
        cron_daemon._terminate_process_tree(process, self.logger)
        self.assertIsNotNone(process.poll())

    def test_command_contains_resolved_processing_date(self):
        configured_task = task("intraday-review", "09:45", policy="TP1")
        with mock.patch.object(cron_daemon.platform, "system", return_value="Linux"):
            command, options = cron_daemon._popen_command(
                configured_task, date(2026, 7, 20)
            )
        self.assertEqual(command[2], "/intraday-review 2026-07-20")
        self.assertTrue(options["start_new_session"])


class CliTests(unittest.TestCase):
    def test_legacy_single_task_flags_are_removed(self):
        parser = cron_daemon.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--cron", "20 9 * * 1-5"])

    def test_once_requires_a_task_id(self):
        parser = cron_daemon.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--once"])


if __name__ == "__main__":
    unittest.main()
