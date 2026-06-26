"""
Cron-like daemon for running daily market analysis via opencode.

Usage:
    python cron-daemon.py                                                   # Default: ron schedule: 19 9 * * 1-5. Cmd: /daily-market-analysis Model: opencode-go/deepseek-v4-pro
    python cron-daemon.py --cron "30 9 * * 1-5"                             # Custom cron expression
    python cron-daemon.py --cmd "/stock-analysis"                           # Custom opencode command
    python cron-daemon.py --model "opencode-go/deepseek-v4-pro"             # Custom opencode model
    python cron-daemon.py --dry-run                                         # Check next run time, don't start
    python cron-daemon.py --once                                            # Run once immediately, then exit

Cron format: minute hour day month weekday
  - minute: 0-59
  - hour: 0-23
  - day: 1-31
  - month: 1-12
  - weekday: 0-6 (0=Sunday, 1=Monday, ..., 6=Saturday)
  - Supports: * (any), N (exact), N-M (range), N,M,L (list), */N (step)
"""

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path


class CronExpression:
    def __init__(self, expr: str):
        self.raw = expr
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression: '{expr}'. Expected 5 fields (minute hour day month weekday)"
            )
        self.minute = self._parse_field(parts[0], 0, 59)
        self.hour = self._parse_field(parts[1], 0, 23)
        self.day = self._parse_field(parts[2], 1, 31)
        self.month = self._parse_field(parts[3], 1, 12)
        self.weekday = self._parse_field(parts[4], 0, 6)

    def _parse_field(self, field: str, lo: int, hi: int) -> set[int]:
        values: set[int] = set()

        for segment in field.split(","):
            segment = segment.strip()
            if not segment:
                continue

            if "/" in segment:
                base, step = segment.split("/", 1)
                step = int(step)
                if base == "*":
                    rng = range(lo, hi + 1)
                elif "-" in base:
                    a, b = base.split("-", 1)
                    rng = range(int(a), int(b) + 1)
                else:
                    rng = range(int(base), hi + 1, step)
                for v in rng:
                    if (v - lo) % step == 0:
                        values.add(v)
            elif segment == "*":
                values.update(range(lo, hi + 1))
            elif "-" in segment:
                a, b = segment.split("-", 1)
                values.update(range(int(a), int(b) + 1))
            else:
                values.add(int(segment))

        return {v for v in values if lo <= v <= hi}

    def matches(self, dt: datetime) -> bool:
        if dt.minute not in self.minute:
            return False
        if dt.hour not in self.hour:
            return False
        if dt.month not in self.month:
            return False
        if self.weekday != set(range(0, 7)):
            wday = dt.weekday()
            sunday_as_zero = (wday + 1) % 7
            if sunday_as_zero not in self.weekday:
                return False
        if self.day != set(range(1, 32)):
            if dt.day not in self.day:
                return False
        return True

    def next_run(self, after: datetime | None = None) -> datetime:
        now = after or datetime.now()
        for days_ahead in range(366):
            check = now.replace(microsecond=0) + timedelta(days=days_ahead)
            for hour in range(24):
                for minute in range(60):
                    candidate = check.replace(hour=hour, minute=minute, second=0)
                    if candidate <= now:
                        continue
                    if self.matches(candidate):
                        return candidate
        raise RuntimeError("No matching time found within next 366 days")

    def __str__(self) -> str:
        return self.raw


CRON_DEFAULT = "20 9 * * 1-5"
CMD_DEFAULT = "/daily-market-analysis"
MODEL_DEFAULT = "opencode-go/deepseek-v4-pro"
PROJECT_DIR = os.getcwd()
LOG_DIR = os.path.join(PROJECT_DIR, ".opencode", "logs")


def setup_logger(log_dir: str) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(log_dir, "cron-daemon.log")
    logger = logging.getLogger("cron-daemon")
    logger.setLevel(logging.INFO)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(sh)

    return logger


def run_analysis(logger: logging.Logger, cmd_arg: str, model_arg: str) -> bool:
    logger.info(f"Starting daily market analysis (cmd: {cmd_arg} model: {model_arg})...")
    try:
        shell_cmd = f"opencode run '{cmd_arg}' --model {model_arg} --dangerously-skip-permissions"
        process = subprocess.Popen(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", shell_cmd],
            cwd=PROJECT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        log_file = os.path.join(LOG_DIR, "cron-daemon.log")

        def stream_stdout():
            for line in iter(process.stdout.readline, ''):
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(line)

        def stream_stderr():
            for line in iter(process.stderr.readline, ''):
                if line:
                    sys.stderr.write(line)
                    sys.stderr.flush()
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(line)

        t_out = threading.Thread(target=stream_stdout, daemon=True)
        t_err = threading.Thread(target=stream_stderr, daemon=True)
        t_out.start()
        t_err.start()

        process.wait(timeout=7200)
        t_out.join(timeout=10)
        t_err.join(timeout=10)

        if process.returncode == 0:
            logger.info("Daily market analysis completed successfully.")
            return True
        else:
            logger.error(
                f"Daily market analysis failed (exit code {process.returncode})"
            )
            return False

    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        logger.error("Daily market analysis timed out after 2 hours.")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return False


def daemon_loop(cron: CronExpression, logger: logging.Logger, cmd_arg: str, model_arg: str):
    logger.info(f"Daemon started. Cron schedule: {cron}. Cmd: {cmd_arg} Model: {model_arg}")
    logger.info(f"Next run: {cron.next_run()}")

    last_run_date = None

    while True:
        now = datetime.now()

        if cron.matches(now) and last_run_date != now.date():
            logger.info(f"Cron matched at {now}. Executing...")
            last_run_date = now.date()
            run_analysis(logger, cmd_arg, model_arg)

            next_dt = cron.next_run(now)
            logger.info(f"Next run scheduled: {next_dt}")

        sleep_until = (now + timedelta(minutes=1)).replace(
            second=0, microsecond=0
        )
        sleep_seconds = (sleep_until - now).total_seconds()
        time.sleep(max(sleep_seconds, 1))


def main():
    parser = argparse.ArgumentParser(
        description="Cron-like daemon for daily market analysis"
    )
    parser.add_argument(
        "--cron",
        default=CRON_DEFAULT,
        help=f"Cron expression (default: '{CRON_DEFAULT}' = weekdays 09:19)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show next run times and exit",
    )
    parser.add_argument(
        "--cmd",
        default=CMD_DEFAULT,
        help=f"opencode run command (default: '{CMD_DEFAULT}')",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once immediately and exit",
    )
    parser.add_argument(
        "--model",
        default=MODEL_DEFAULT,
        help="model to use in the format of provider/model",
    )
    args = parser.parse_args()

    logger = setup_logger(LOG_DIR)
    logger.info(f"PROJECT_DIR: {PROJECT_DIR}")

    try:
        cron = CronExpression(args.cron)
    except ValueError as e:
        logger.error(f"Invalid cron expression: {e}")
        sys.exit(1)
    logger.info(f"Cron expression: {cron}")
    night = datetime.now()
    for i in range(5):
        next_dt = cron.next_run(after=night)
        logger.info(f"  Next run #{i + 1}: {next_dt}")
        night = next_dt + timedelta(seconds=1)

    if args.dry_run:
        logger.info("Dry run mode. Exiting.")
        return

    if args.once:
        run_analysis(logger, args.cmd, args.model)
        return

    daemon_loop(cron, logger, args.cmd, args.model)


if __name__ == "__main__":
    main()
