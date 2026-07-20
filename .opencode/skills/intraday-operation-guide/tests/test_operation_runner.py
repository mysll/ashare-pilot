from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from operation_time import MARKET_TZ  # noqa: E402
from run_operation_guide import (  # noqa: E402
    expected_completed_bar,
    latest_eligible_snapshot,
    operation_lock,
    pending_confirmation_snapshot,
    publish_immutable,
    snapshot_has_expected_bars,
)
import render_operation_guide_html as renderer  # noqa: E402
import run_operation_guide as runner  # noqa: E402


def write_snapshot(path: Path, generated_at: str, action: str, slot: str, requires_second: bool = False) -> None:
    path.write_text(json.dumps({
        "date": "2026-07-20",
        "generated_at": generated_at,
        "snapshot_slot": slot,
        "delivery_confirmation": {
            "execution_action": action,
            "requires_second_confirmation": requires_second,
        },
    }), encoding="utf-8")


class OperationRunnerTests(unittest.TestCase):
    def test_immutable_publish_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / ".pending"
            destination = root / "operation_snapshot_0935.json"
            pending.write_text("new", encoding="utf-8")
            destination.write_text("old", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                publish_immutable(pending, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), "old")

    def test_operation_lock_rejects_concurrent_holder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with operation_lock(root):
                with self.assertRaises(RuntimeError):
                    with operation_lock(root):
                        pass

    def test_preopen_single_invocation_schedules_both_confirmations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = datetime(2026, 7, 20, 9, 30, tzinfo=MARKET_TZ)
            previous = root / "operation" / "2026-07-20" / "operation_snapshot_0935.json"
            argv = ["run_operation_guide.py", "--date", "2026-07-20"]
            with (
                patch.object(sys, "argv", argv),
                patch.object(runner, "ROOT", root),
                patch.object(runner, "now_market", return_value=current),
                patch.object(runner, "wait_until") as wait,
                patch.object(runner, "snapshot_for_slot", side_effect=[None, (previous, {"snapshot_slot": "09:35"})]),
                patch.object(runner, "build_current_artifacts", return_value=(previous, root / "decision.json")) as build,
            ):
                self.assertEqual(runner.main(), 0)
            self.assertEqual([call.args[0].strftime("%H:%M:%S") for call in wait.call_args_list], ["09:35:10", "09:40:10"])
            self.assertEqual([call.kwargs["slot"] for call in build.call_args_list], ["09:35", "09:40"])
            self.assertEqual(build.call_args_list[1].kwargs["previous"], previous)

    def test_0940_late_initial_automatically_schedules_0945_followup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = datetime(2026, 7, 20, 9, 41, tzinfo=MARKET_TZ)
            late = root / "operation" / "2026-07-20" / "operation_snapshot_0940.json"
            argv = ["run_operation_guide.py", "--date", "2026-07-20"]
            with (
                patch.object(sys, "argv", argv),
                patch.object(runner, "ROOT", root),
                patch.object(runner, "now_market", return_value=current),
                patch.object(runner, "latest_eligible_snapshot", return_value=None),
                patch.object(runner, "wait_until") as wait,
                patch.object(runner, "build_current_artifacts", side_effect=[(late, root / "d1.json"), (root / "s2.json", root / "d2.json")]) as build,
            ):
                self.assertEqual(runner.main(), 0)
            self.assertEqual([call.args[0].strftime("%H:%M:%S") for call in wait.call_args_list], ["09:45:10"])
            self.assertEqual([call.kwargs["slot"] for call in build.call_args_list], ["09:40", "09:45"])
            self.assertEqual(build.call_args_list[1].kwargs["previous"], late)

    def test_newer_observe_only_does_not_poison_confirmation_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            confirmed = root / "operation_snapshot_0940.json"
            poisoned = root / "operation_snapshot_131500.json"
            write_snapshot(confirmed, "2026-07-20T09:40:10+08:00", "EVALUATE", "09:40")
            write_snapshot(poisoned, "2026-07-20T13:15:10+08:00", "OBSERVE_ONLY", "LATE")
            before = datetime(2026, 7, 20, 13, 20, tzinfo=MARKET_TZ)
            with patch("run_operation_guide.validate_snapshot", return_value=[]):
                selected = latest_eligible_snapshot(root, "2026-07-20", before)
            self.assertIsNotNone(selected)
            self.assertEqual(selected[0], confirmed)

    def test_new_snapshot_is_ineligible_until_full_manifest_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_path = root / "operation_snapshot_101000.json"
            decision_path = root / "operation_decision_101000.json"
            html_path = root / "operation_guide_101000.html"
            write_snapshot(snapshot_path, "2026-07-20T10:10:00+08:00", "EVALUATE", "LATE")
            doc = json.loads(snapshot_path.read_text(encoding="utf-8"))
            doc["run_mode"] = "RECHECK"
            snapshot_path.write_text(json.dumps(doc), encoding="utf-8")
            before = datetime(2026, 7, 20, 10, 15, tzinfo=MARKET_TZ)
            with patch("run_operation_guide.validate_snapshot", return_value=[]):
                self.assertIsNone(latest_eligible_snapshot(root, "2026-07-20", before))

            decision_path.write_text("decision", encoding="utf-8")
            html_path.write_text("html", encoding="utf-8")
            manifest = {
                "schema_version": "intraday_operation_run_manifest.v1",
                "snapshot": snapshot_path.name,
                "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
                "decision": decision_path.name,
                "decision_sha256": hashlib.sha256(decision_path.read_bytes()).hexdigest(),
                "html": html_path.name,
                "html_sha256": hashlib.sha256(html_path.read_bytes()).hexdigest(),
            }
            (root / "operation_run_101000.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch("run_operation_guide.validate_snapshot", return_value=[]):
                selected = latest_eligible_snapshot(root, "2026-07-20", before)
            self.assertEqual(selected[0], snapshot_path)

    def test_wait_second_confirmation_is_valid_predecessor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            waiting = root / "operation_snapshot_0940.json"
            write_snapshot(waiting, "2026-07-20T09:40:10+08:00", "WAIT_SECOND_CONFIRMATION", "09:40")
            before = datetime(2026, 7, 20, 9, 45, 10, tzinfo=MARKET_TZ)
            with patch("run_operation_guide.validate_snapshot", return_value=[]):
                selected = pending_confirmation_snapshot(root, "2026-07-20", before)
            self.assertEqual(selected[0], waiting)

    def test_incomplete_opening_chain_expires_before_afternoon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "operation_snapshot_0935.json"
            waiting = root / "operation_snapshot_0940.json"
            write_snapshot(first, "2026-07-20T09:35:10+08:00", "EVALUATE", "09:35", requires_second=True)
            write_snapshot(waiting, "2026-07-20T09:40:10+08:00", "WAIT_SECOND_CONFIRMATION", "09:40", requires_second=True)
            afternoon = datetime(2026, 7, 20, 13, 0, tzinfo=MARKET_TZ)
            with patch("run_operation_guide.validate_snapshot", return_value=[]):
                self.assertIsNone(latest_eligible_snapshot(root, "2026-07-20", afternoon))
                self.assertIsNone(pending_confirmation_snapshot(root, "2026-07-20", afternoon))

    def test_as_of_afternoon_does_not_recover_from_only_0935(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = datetime(2026, 7, 20, 13, 0, tzinfo=MARKET_TZ)
            argv = ["run_operation_guide.py", "--date", "2026-07-20", "--as-of", current.isoformat()]
            with (
                patch.object(sys, "argv", argv),
                patch.object(runner, "ROOT", root),
                patch.object(runner, "latest_eligible_snapshot", return_value=None),
                patch.object(runner, "pending_confirmation_snapshot", return_value=None),
                patch.object(runner, "build_current_artifacts", return_value=(root / "s.json", root / "d.json")) as build,
            ):
                self.assertEqual(runner.main(), 0)
            self.assertEqual(build.call_args.kwargs["run_mode"], "LATE_OBSERVE_ONLY")
            self.assertIsNone(build.call_args.kwargs["previous"])

    def test_as_of_0945_uses_waiting_0940_as_second_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = datetime(2026, 7, 20, 9, 46, tzinfo=MARKET_TZ)
            waiting = root / "operation_snapshot_0940.json"
            argv = ["run_operation_guide.py", "--date", "2026-07-20", "--as-of", current.isoformat()]
            with (
                patch.object(sys, "argv", argv),
                patch.object(runner, "ROOT", root),
                patch.object(runner, "latest_eligible_snapshot", return_value=None),
                patch.object(runner, "pending_confirmation_snapshot", return_value=(waiting, {})),
                patch.object(runner, "build_current_artifacts", return_value=(root / "s.json", root / "d.json")) as build,
            ):
                self.assertEqual(runner.main(), 0)
            self.assertEqual(build.call_args.kwargs["run_mode"], "SECOND_CONFIRMATION")
            self.assertEqual(build.call_args.kwargs["previous"], waiting)

    def test_completed_bar_boundary_waits_ten_seconds(self):
        at_five = datetime(2026, 7, 20, 9, 40, 5, tzinfo=MARKET_TZ)
        at_ten = datetime(2026, 7, 20, 9, 40, 10, tzinfo=MARKET_TZ)
        self.assertEqual(expected_completed_bar(at_five).strftime("%H:%M:%S"), "09:35:00")
        self.assertEqual(expected_completed_bar(at_ten).strftime("%H:%M:%S"), "09:40:00")

    def test_snapshot_readiness_requires_expected_bar_for_live_quote(self):
        expected = datetime(2026, 7, 20, 9, 40, tzinfo=MARKET_TZ)
        doc = {"market_confirmation": {"indices": {
            "sh000001": {"valid": True}, "sz399001": {"valid": True}, "sh000688": {"valid": True},
        }}, "stocks": [{
            "code": "sz000001",
            "quote": {"price": 10.0},
            "signals": {"latest_completed_bar": {"bar_end": "2026-07-20T09:35:00+08:00"}},
        }]}
        self.assertEqual(snapshot_has_expected_bars(doc, expected), (False, ["sz000001"]))
        doc["stocks"][0]["signals"]["latest_completed_bar"]["bar_end"] = "2026-07-20T09:40:00+08:00"
        self.assertEqual(snapshot_has_expected_bars(doc, expected), (True, []))

    def test_snapshot_with_no_valid_quotes_is_not_ready(self):
        expected = datetime(2026, 7, 20, 9, 40, tzinfo=MARKET_TZ)
        doc = {"market_confirmation": {"indices": {
            "sh000001": {"valid": True}, "sz399001": {"valid": True}, "sh000688": {"valid": True},
        }}, "stocks": [{"code": "sz000001", "quote": {"price": None}, "signals": {}}]}
        ready, missing = snapshot_has_expected_bars(doc, expected)
        self.assertFalse(ready)
        self.assertIn("no_valid_stock_quotes", missing)

    def test_renderer_rejects_decision_snapshot_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decision_path = root / "decision.json"
            snapshot_path = root / "snapshot.json"
            snapshot_path.write_text(json.dumps({
                "generated_at": "2026-07-20T13:15:10+08:00",
            }), encoding="utf-8")
            decision_path.write_text(json.dumps({
                "schema_version": "intraday_operation_decision.v1",
                "date": "2026-07-20",
                "generated_at": "2026-07-20T09:40:10+08:00",
                "source_snapshot_sha256": "bad",
            }), encoding="utf-8")
            argv = [
                "render_operation_guide_html.py", "--date", "2026-07-20",
                "--decision", str(decision_path), "--snapshot", str(snapshot_path),
                "--output", str(root / "guide.html"),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(renderer.main(), 1)
            self.assertFalse((root / "guide.html").exists())


if __name__ == "__main__":
    unittest.main()
