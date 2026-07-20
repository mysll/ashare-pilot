#!/usr/bin/env python3
"""State-aware orchestrator for the intraday operation guide lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time as time_module
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterator

from operation_time import MARKET_TZ, now_market, parse_market_datetime
from validate_operation_snapshot import validate as validate_snapshot


ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent
SAFE_DELAY_SECONDS = 10
READINESS_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 2
ELIGIBLE_PREVIOUS_ACTIONS = {"EVALUATE", "WAIT_SECOND_CONFIRMATION"}
LATE_FOLLOWUP_EXPIRY = time(9, 50, 10)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def publish_immutable(pending: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(pending, destination)
    except FileExistsError as exc:
        raise RuntimeError(f"refusing to overwrite immutable artifact: {destination}") from exc
    pending.unlink()


def immutable_snapshot_paths(operation_dir: Path) -> list[Path]:
    paths = []
    for path in operation_dir.glob("operation_snapshot_*.json"):
        if path.name == "operation_snapshot_latest.json" or ".pending" in path.name:
            continue
        paths.append(path)
    return paths


def committed_snapshot_names(operation_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in operation_dir.glob("operation_run_*.json"):
        manifest = read_json(path)
        if manifest is None or manifest.get("schema_version") != "intraday_operation_run_manifest.v1":
            continue
        valid = True
        for name_key, hash_key in (
            ("snapshot", "snapshot_sha256"),
            ("decision", "decision_sha256"),
            ("html", "html_sha256"),
        ):
            name = manifest.get(name_key)
            expected = manifest.get(hash_key)
            artifact = operation_dir / name if isinstance(name, str) else None
            if artifact is None or not artifact.exists() or not isinstance(expected, str) or file_sha256(artifact) != expected:
                valid = False
                break
        if valid:
            names.add(str(manifest["snapshot"]))
    return names


def eligible_snapshots(operation_dir: Path, trade_date: str, before: datetime) -> list[tuple[datetime, Path, dict[str, Any]]]:
    eligible: list[tuple[datetime, Path, dict[str, Any]]] = []
    committed = committed_snapshot_names(operation_dir)
    for path in immutable_snapshot_paths(operation_dir):
        doc = read_json(path)
        if doc is None or doc.get("date") != trade_date or validate_snapshot(
            doc, reference_base=ROOT, require_references=True
        ):
            continue
        generated = parse_market_datetime(doc.get("generated_at"))
        action = doc.get("delivery_confirmation", {}).get("execution_action")
        if doc.get("run_mode") is not None and path.name not in committed:
            continue
        if generated is None or generated >= before or action not in ELIGIBLE_PREVIOUS_ACTIONS:
            continue
        eligible.append((generated, path, doc))
    return sorted(eligible, key=lambda item: (item[0], item[1].name))


def confirmation_phase(doc: dict[str, Any]) -> str | None:
    delivery = doc.get("delivery_confirmation") if isinstance(doc.get("delivery_confirmation"), dict) else {}
    action = delivery.get("execution_action")
    if action == "WAIT_SECOND_CONFIRMATION" or (
        action == "EVALUATE" and delivery.get("requires_second_confirmation") is True
    ):
        return "AWAITING_SECOND"
    if action == "EVALUATE" and delivery.get("requires_second_confirmation") is not True:
        return "CONFIRMED"
    return None


def latest_eligible_snapshot(operation_dir: Path, trade_date: str, before: datetime) -> tuple[Path, dict[str, Any]] | None:
    candidates = [item for item in eligible_snapshots(operation_dir, trade_date, before) if confirmation_phase(item[2]) == "CONFIRMED"]
    return (candidates[-1][1], candidates[-1][2]) if candidates else None


def pending_confirmation_snapshot(
    operation_dir: Path, trade_date: str, current: datetime
) -> tuple[Path, dict[str, Any]] | None:
    local_time = current.astimezone(MARKET_TZ).time()
    if local_time < time(9, 45, SAFE_DELAY_SECONDS):
        allowed_slots = {"09:35"}
    elif local_time < LATE_FOLLOWUP_EXPIRY:
        allowed_slots = {"09:40"}
    else:
        return None
    candidates = [
        item for item in eligible_snapshots(operation_dir, trade_date, current)
        if item[2].get("snapshot_slot") in allowed_slots and confirmation_phase(item[2]) == "AWAITING_SECOND"
    ]
    return (candidates[-1][1], candidates[-1][2]) if candidates else None


def snapshot_for_slot(operation_dir: Path, trade_date: str, slot: str, before: datetime) -> tuple[Path, dict[str, Any]] | None:
    matches = [item for item in eligible_snapshots(operation_dir, trade_date, before) if item[2].get("snapshot_slot") == slot]
    return (matches[-1][1], matches[-1][2]) if matches else None


def target_datetime(trade_date: date, hour: int, minute: int, settle_seconds: int) -> datetime:
    return datetime.combine(trade_date, time(hour, minute, settle_seconds), MARKET_TZ)


def expected_completed_bar(value: datetime) -> datetime | None:
    local = value.astimezone(MARKET_TZ)
    current = local.time()
    if current < time(9, 35, SAFE_DELAY_SECONDS):
        return None
    if time(11, 30) < current < time(13, 5, SAFE_DELAY_SECONDS):
        return datetime.combine(local.date(), time(11, 30), MARKET_TZ)
    if current >= time(15, 0, SAFE_DELAY_SECONDS):
        return datetime.combine(local.date(), time(15, 0), MARKET_TZ)
    minute = (local.minute // 5) * 5
    boundary = local.replace(minute=minute, second=0, microsecond=0)
    if local < boundary + timedelta(seconds=SAFE_DELAY_SECONDS):
        boundary -= timedelta(minutes=5)
    return boundary


def snapshot_has_expected_bars(doc: dict[str, Any], expected: datetime | None) -> tuple[bool, list[str]]:
    if expected is None:
        return True, []
    missing: list[str] = []
    stocks = doc.get("stocks") if isinstance(doc.get("stocks"), list) else []
    valid_quotes = 0
    for stock in stocks:
        quote = stock.get("quote") if isinstance(stock, dict) else {}
        if not isinstance(quote, dict) or not isinstance(quote.get("price"), (int, float)):
            continue
        valid_quotes += 1
        latest = stock.get("signals", {}).get("latest_completed_bar", {})
        bar_end = parse_market_datetime(latest.get("bar_end")) if isinstance(latest, dict) else None
        if bar_end is None or bar_end < expected:
            missing.append(str(stock.get("code") or "unknown"))
    if not stocks:
        missing.append("no_strategy_stocks")
    elif valid_quotes == 0:
        missing.append("no_valid_stock_quotes")
    indices = doc.get("market_confirmation", {}).get("indices", {})
    for code in ("sh000001", "sz399001", "sh000688"):
        if not isinstance(indices.get(code), dict) or indices[code].get("valid") is not True:
            missing.append(f"invalid_index:{code}")
    return not missing, missing


def unique_artifact_pair(operation_dir: Path, snapshot_prefix: str, generated: datetime) -> tuple[Path, Path]:
    stem = f"{snapshot_prefix}_{generated.strftime('%H%M%S')}"
    suffix = 1
    while True:
        marker = "" if suffix == 1 else f"_{suffix:02d}"
        snapshot = operation_dir / f"{stem}{marker}.json"
        decision = snapshot.with_name(snapshot.name.replace("operation_snapshot_", "operation_decision_"))
        manifest = snapshot.with_name(snapshot.name.replace("operation_snapshot_", "operation_run_"))
        if not snapshot.exists() and not decision.exists() and not manifest.exists():
            return snapshot, decision
        suffix += 1


def unique_html_path(operation_dir: Path, prefix: str, generated: datetime) -> Path:
    stem = f"{prefix}_{generated.strftime('%H%M%S')}"
    candidate = operation_dir / f"{stem}.html"
    suffix = 2
    while candidate.exists():
        candidate = operation_dir / f"{stem}_{suffix:02d}.html"
        suffix += 1
    return candidate


def run_command(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")


def write_state(operation_dir: Path, status: str, **extra: Any) -> None:
    atomic_write_json(operation_dir / "operation_run_state.json", {
        "schema_version": "intraday_operation_run_state.v1",
        "updated_at": now_market().isoformat(timespec="seconds"),
        "status": status,
        **extra,
    })


@contextmanager
def operation_lock(operation_dir: Path) -> Iterator[None]:
    lock_path = operation_dir / "operation_guide.lock"
    operation_dir.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError("operation guide is already running") from exc
    try:
        metadata = json.dumps({
            "pid": os.getpid(),
            "started_at": now_market().isoformat(timespec="seconds"),
        }).encode("utf-8")
        handle.seek(0)
        handle.truncate()
        handle.write(metadata)
        handle.flush()
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def wait_until(target: datetime, operation_dir: Path, status: str) -> None:
    write_state(operation_dir, status, next_action_at=target.isoformat(timespec="seconds"))
    print(f"Waiting until {target.isoformat(timespec='seconds')} for {status}", flush=True)
    while True:
        remaining = (target - now_market()).total_seconds()
        if remaining <= 0:
            return
        time_module.sleep(min(30.0, remaining))


def build_current_artifacts(
    *,
    trade_date: str,
    operation_dir: Path,
    slot: str,
    run_mode: str,
    previous: Path | None,
    as_of: datetime | None,
    quotes_fixture: str | None,
    intraday_fixture_dir: str | None,
    no_network: bool,
    readiness_timeout: int,
    poll_interval: int,
) -> tuple[Path, Path]:
    generated = as_of or now_market()
    if slot in {"09:35", "09:40"}:
        suffix = slot.replace(":", "")
        snapshot_path = operation_dir / f"operation_snapshot_{suffix}.json"
        decision_path = operation_dir / f"operation_decision_{suffix}.json"
        opening_manifest = operation_dir / f"operation_run_{suffix}.json"
        if snapshot_path.exists() or decision_path.exists() or opening_manifest.exists():
            snapshot_path, decision_path = unique_artifact_pair(
                operation_dir, f"operation_snapshot_{suffix}", generated
            )
    else:
        snapshot_path, decision_path = unique_artifact_pair(operation_dir, "operation_snapshot", generated)

    expected = expected_completed_bar(generated)
    deadline = time_module.monotonic() + readiness_timeout
    pending = operation_dir / f".{snapshot_path.name}.pending"
    while True:
        command = [
            sys.executable,
            str(SCRIPT_DIR / "build_operation_snapshot.py"),
            "--date", trade_date,
            "--slot", slot,
            "--run-mode", run_mode,
            "-o", str(pending),
        ]
        if previous is not None:
            command.extend(["--previous-snapshot", portable_path(previous)])
        if as_of is not None:
            command.extend(["--as-of", as_of.isoformat()])
        if quotes_fixture:
            command.extend(["--quotes-fixture", quotes_fixture])
        if intraday_fixture_dir:
            command.extend(["--intraday-fixture-dir", intraday_fixture_dir])
        if no_network:
            command.append("--no-network")
        run_command(command)
        pending_doc = read_json(pending)
        if pending_doc is None:
            raise RuntimeError("snapshot builder produced invalid JSON")
        ready, missing = snapshot_has_expected_bars(pending_doc, expected)
        if ready:
            errors = validate_snapshot(pending_doc)
            if errors:
                raise RuntimeError("snapshot validation failed: " + "; ".join(errors))
            break
        pending.unlink(missing_ok=True)
        if as_of is not None:
            raise RuntimeError(f"fixture data did not contain expected bar {expected.isoformat()}: {', '.join(missing)}")
        if time_module.monotonic() >= deadline:
            raise RuntimeError(f"market data did not publish expected bar {expected.isoformat()}: {', '.join(missing)}")
        print(f"Expected bar not ready for {', '.join(missing)}; retrying...", flush=True)
        time_module.sleep(poll_interval)

    publish_immutable(pending, snapshot_path)

    run_command([
        sys.executable, str(SCRIPT_DIR / "validate_operation_snapshot.py"), str(snapshot_path)
    ])
    pending_decision = operation_dir / f".{decision_path.name}.pending"
    run_command([
        sys.executable, str(SCRIPT_DIR / "build_operation_decision.py"),
        "--snapshot", portable_path(snapshot_path), "-o", str(pending_decision),
    ])
    run_command([
        sys.executable, str(SCRIPT_DIR / "validate_operation_decision.py"), str(pending_decision)
    ])
    publish_immutable(pending_decision, decision_path)
    html_path = operation_dir / snapshot_path.name.replace("operation_snapshot_", "operation_guide_").replace(".json", ".html")
    if html_path.exists():
        html_path = unique_html_path(operation_dir, "operation_guide", generated)
    pending_html = operation_dir / f".{html_path.name}.pending"
    run_command([
        sys.executable, str(SCRIPT_DIR / "render_operation_guide_html.py"),
        "--date", trade_date,
        "--decision", portable_path(decision_path),
        "--snapshot", portable_path(snapshot_path),
        "--output", str(pending_html),
    ])
    publish_immutable(pending_html, html_path)
    atomic_copy(snapshot_path, operation_dir / "operation_snapshot.latest.json")
    atomic_copy(decision_path, operation_dir / "operation_decision.latest.json")
    atomic_copy(html_path, operation_dir / "operation_guide.html")
    manifest_path = operation_dir / snapshot_path.name.replace("operation_snapshot_", "operation_run_")
    pending_manifest = operation_dir / f".{manifest_path.name}.pending"
    manifest = {
        "schema_version": "intraday_operation_run_manifest.v1",
        "date": trade_date,
        "generated_at": (read_json(snapshot_path) or {}).get("generated_at"),
        "run_mode": run_mode,
        "snapshot": snapshot_path.name,
        "snapshot_sha256": file_sha256(snapshot_path),
        "decision": decision_path.name,
        "decision_sha256": file_sha256(decision_path),
        "html": html_path.name,
        "html_sha256": file_sha256(html_path),
    }
    atomic_write_json(pending_manifest, manifest)
    publish_immutable(pending_manifest, manifest_path)
    atomic_copy(manifest_path, operation_dir / "operation_run.latest.json")
    write_state(
        operation_dir,
        "COMPLETED",
        run_mode=run_mode,
        snapshot=str(snapshot_path),
        decision=str(decision_path),
        manifest=str(manifest_path),
    )
    return snapshot_path, decision_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run state-aware intraday operation guide")
    parser.add_argument("--date", help="YYYY-MM-DD; defaults to current Shanghai date")
    parser.add_argument("--as-of", help="ISO datetime override; performs one immediate deterministic run")
    parser.add_argument("--quotes-fixture")
    parser.add_argument("--intraday-fixture-dir")
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--settle-seconds", type=int, default=SAFE_DELAY_SECONDS)
    parser.add_argument("--readiness-timeout", type=int, default=READINESS_TIMEOUT_SECONDS)
    parser.add_argument("--poll-interval", type=int, default=POLL_INTERVAL_SECONDS)
    args = parser.parse_args()

    if args.settle_seconds < SAFE_DELAY_SECONDS:
        parser.error(f"--settle-seconds must be at least {SAFE_DELAY_SECONDS}")
    current = parse_market_datetime(args.as_of) if args.as_of else now_market()
    if current is None:
        parser.error("invalid --as-of")
    trade_date = args.date or current.date().isoformat()
    if current.date().isoformat() != trade_date:
        parser.error("--date must match current/as-of Shanghai date")
    operation_dir = ROOT / "operation" / trade_date

    try:
        with operation_lock(operation_dir):
            first_target = target_datetime(current.date(), 9, 35, args.settle_seconds)
            second_target = target_datetime(current.date(), 9, 40, args.settle_seconds)
            late_followup_target = target_datetime(current.date(), 9, 45, args.settle_seconds)

            if args.as_of:
                confirmed = latest_eligible_snapshot(operation_dir, trade_date, current)
                pending_confirmation = pending_confirmation_snapshot(operation_dir, trade_date, current)
                if current < first_target:
                    mode, slot, previous_path = "EARLY", "auto", None
                elif confirmed is not None:
                    mode, slot, previous_path = "RECHECK", "auto", confirmed[0]
                elif current >= second_target and pending_confirmation is not None:
                    mode, slot, previous_path = "SECOND_CONFIRMATION", "auto", pending_confirmation[0]
                elif current < second_target:
                    mode, slot, previous_path = "INITIAL_CONFIRMATION", "09:35", None
                elif current < late_followup_target:
                    mode, slot, previous_path = "LATE_INITIAL_CONFIRMATION", "09:40", None
                else:
                    mode, slot, previous_path = "LATE_OBSERVE_ONLY", "auto", None
                build_current_artifacts(
                    trade_date=trade_date, operation_dir=operation_dir, slot=slot,
                    run_mode=mode, previous=previous_path, as_of=current,
                    quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                    no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                    poll_interval=args.poll_interval,
                )
                return 0

            if current < second_target:
                existing_first = snapshot_for_slot(operation_dir, trade_date, "09:35", now_market())
                if existing_first is None:
                    if now_market().time() >= time(9, 40):
                        wait_until(second_target, operation_dir, "WAITING_LATE_INITIAL_CONFIRMATION")
                        late_snapshot, _ = build_current_artifacts(
                            trade_date=trade_date, operation_dir=operation_dir, slot="09:40",
                            run_mode="LATE_INITIAL_CONFIRMATION", previous=None, as_of=None,
                            quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                            no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                            poll_interval=args.poll_interval,
                        )
                        wait_until(late_followup_target, operation_dir, "WAITING_LATE_SECOND_CONFIRMATION")
                        build_current_artifacts(
                            trade_date=trade_date, operation_dir=operation_dir, slot="09:45",
                            run_mode="SECOND_CONFIRMATION", previous=late_snapshot, as_of=None,
                            quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                            no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                            poll_interval=args.poll_interval,
                        )
                        return 0
                    if now_market() < first_target:
                        wait_until(first_target, operation_dir, "WAITING_FIRST_CONFIRMATION")
                    build_current_artifacts(
                        trade_date=trade_date, operation_dir=operation_dir, slot="09:35",
                        run_mode="INITIAL_CONFIRMATION", previous=None, as_of=None,
                        quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                        no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                        poll_interval=args.poll_interval,
                    )
                if now_market() < second_target:
                    wait_until(second_target, operation_dir, "WAITING_SECOND_CONFIRMATION")
                previous = snapshot_for_slot(operation_dir, trade_date, "09:35", now_market())
                if previous is None:
                    raise RuntimeError("09:35 confirmation is unavailable; refusing unchained 09:40 confirmation")
                build_current_artifacts(
                    trade_date=trade_date, operation_dir=operation_dir, slot="09:40",
                    run_mode="SECOND_CONFIRMATION", previous=previous[0], as_of=None,
                    quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                    no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                    poll_interval=args.poll_interval,
                )
                return 0

            current_live = now_market()
            confirmed = latest_eligible_snapshot(operation_dir, trade_date, current_live)
            if confirmed is not None:
                build_current_artifacts(
                    trade_date=trade_date, operation_dir=operation_dir, slot="auto",
                    run_mode="RECHECK", previous=confirmed[0], as_of=None,
                    quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                    no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                    poll_interval=args.poll_interval,
                )
                return 0
            pending_confirmation = pending_confirmation_snapshot(operation_dir, trade_date, current_live)
            if pending_confirmation is not None:
                build_current_artifacts(
                    trade_date=trade_date, operation_dir=operation_dir, slot="auto",
                    run_mode="SECOND_CONFIRMATION", previous=pending_confirmation[0], as_of=None,
                    quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                    no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                    poll_interval=args.poll_interval,
                )
                return 0
            if current_live < late_followup_target:
                late_snapshot, _ = build_current_artifacts(
                    trade_date=trade_date, operation_dir=operation_dir, slot="09:40",
                    run_mode="LATE_INITIAL_CONFIRMATION", previous=None, as_of=None,
                    quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                    no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                    poll_interval=args.poll_interval,
                )
                if now_market() < late_followup_target:
                    wait_until(late_followup_target, operation_dir, "WAITING_LATE_SECOND_CONFIRMATION")
                build_current_artifacts(
                    trade_date=trade_date, operation_dir=operation_dir, slot="09:45",
                    run_mode="SECOND_CONFIRMATION", previous=late_snapshot, as_of=None,
                    quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                    no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                    poll_interval=args.poll_interval,
                )
                return 0
            build_current_artifacts(
                trade_date=trade_date, operation_dir=operation_dir, slot="auto",
                run_mode="LATE_OBSERVE_ONLY", previous=None, as_of=None,
                quotes_fixture=args.quotes_fixture, intraday_fixture_dir=args.intraday_fixture_dir,
                no_network=args.no_network, readiness_timeout=args.readiness_timeout,
                poll_interval=args.poll_interval,
            )
            return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
