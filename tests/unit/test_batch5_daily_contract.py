from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from ashare_pilot.strategy._commands.daily.timing import update_report, validation_retry_count
from ashare_pilot.strategy._commands.daily.draft_link import (
    INPUT_HASH_FILENAME, validate_draft_link, write_input_hash,
)
from ashare_pilot.strategy._commands.daily.llm_input import (
    build_input, derive_regime, expand_candidate, index_percent, reread_triggers,
)
from ashare_pilot.strategy._commands.daily.finalize import materialize, validate_draft
from ashare_pilot.strategy._commands.daily.plan_baseline import entry_trigger
from ashare_pilot.strategy._commands.daily.prepare import fetch_indices, normalize_indices
from ashare_pilot.strategy._commands.daily.render_report import render_report
from ashare_pilot.strategy._commands.daily.validate_strategy import validate

REAL_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "strategy" / "step3_real"


def load_fixture(date: str) -> dict:
    return json.loads((REAL_FIXTURES / f"{date}.json").read_text(encoding="utf-8"))


def candidate(code: str) -> dict:
    score = lambda value=60, confidence=100: {"value": value, "confidence": confidence}
    state = lambda value: {"state": value, "confidence": 100}
    return {
        "code": code, "name": f"股票{code[-3:]}", "role_tags": ["ThemeLibrary"],
        "scores": {"composite": score(60, 50), "tech": score(65), "theme_heat": score(70),
                   "news_impact": score(50), "auction": score(50), "money_flow": score(50, 50)},
        "major_event": {"polarity": "none", "confidence": 100}, "risk_type": [],
        "pattern": {"heat": state("STABLE"), "leader": state("STABLE"),
                    "auction": state("UNKNOWN"), "rotation": state("PRIMARY"), "volume": state("NORMAL")},
        "anomaly": None, "news_link": None,
        "strategy_inputs": {"price_source": "PrevClose", "price": 10.0, "ma5": 9.8, "ma20": 9.5,
                            "atr": 0.5, "atr_pct": 5.0, "high20": 11.0, "low20": 8.0},
    }


def small_inputs(date: str, count: int = 2):
    codes = [f"sh{600000 + index:06d}" for index in range(count)]
    view = {
        "schema_version": "daily_strategy_input.v2", "date": date,
        "source": {"mapper_sha256": "fixture"},
        "market_state": {"dominant_themes": [{"name": "测试主题", "final_heat": 70}]},
        "themes": [{"name": "测试主题", "rank": 1, "final_heat": 70,
                    "attention_direction": "bullish", "evidence_refs": []}],
        "candidates": [candidate(code) for code in codes], "observation_pool": [],
    }
    themes = {"schema_version": "daily_theme_stocks.v2", "date": date,
              "themes": copy.deepcopy(view["themes"]),
              "stocks": [{"code": code, "source_themes": [{"name": "测试主题", "score": 70}]} for code in codes]}
    pool = [{"code": code, "raw_observation": {}, "computed_perception": {}} for code in codes]
    news = {"date": date, "items": []}
    indices = {code: {"code": code, "percent": 0.0} for code in ("sh000001", "sz399001", "sh000688")}
    return codes, build_input(view, themes, pool, news, indices)


def selected_stock(row: dict) -> dict:
    return {
        "code": row["code"], "direction": "偏多", "rating": "4★",
        "entry_profile": "回调布局", "anchor": "MA20",
        "position_tier": "STANDARD", "entry_setup": "PULLBACK",
        "rules_applied": ["R70"],
        "reasoning": {"source_basis": "测试主题 ThemeLibrary", "direction_path": "base=偏多"},
        "profile_overrides": {},
    }


def draft_for(date: str, compact: dict, selected: list[dict], regime: str = "neutral") -> dict:
    return {
        "schema_version": "daily_strategy_draft.tmp.v3", "date": date,
        "market": {"regime_prior": regime, "notes": "fixture"},
        "stocks": selected, "exclusion_overrides": [],
    }


def snapshot(strategy: dict) -> dict:
    fields = ("code", "direction", "rating", "position_tier", "entry_profile", "anchor", "rules_applied", "profile")
    return {
        "regime_prior": strategy["market"]["regime_prior"],
        "stocks": [{key: item.get(key) for key in fields} for item in strategy["stocks"]],
        "observation_codes": [item.get("code") for item in strategy["observation_pool"]],
    }


def contains_key(value, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return bool(set(value) & forbidden) or any(contains_key(item, forbidden) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, forbidden) for item in value)
    return False


class Step3RealFrozenGateTests(unittest.TestCase):
    def test_2026_07_09_oversized_legacy_fixture_is_real_and_explicitly_unreplayable(self):
        fixture = load_fixture("2026-07-09")
        codes = [item.get("code") for item in fixture["view"]["candidates"]]
        self.assertEqual(82, len(codes))
        self.assertEqual(fixture["candidate_codes"], codes)
        self.assertEqual(len(codes), len(set(codes)))
        self.assertIn("canonical news.json unavailable", fixture["expected_prepare_error"])

    def test_gate_a_real_input_equivalence(self):
        for date in ("2026-07-13", "2026-07-14", "2026-07-15"):
            with self.subTest(date=date):
                fixture = load_fixture(date)
                compact = build_input(fixture["view"], fixture["theme_stocks"], fixture["pool"], fixture["news"], fixture["indices"])
                source_rows = fixture["view"]["candidates"]
                projected_rows = [expand_candidate(compact, row) for row in compact["candidates"]]
                self.assertEqual([row["code"] for row in source_rows], [row["code"] for row in projected_rows])
                self.assertEqual(fixture["view"]["market_state"], compact["market_inputs"]["market_state"])
                for source, projected in zip(source_rows, projected_rows):
                    self.assertEqual({key: item.get("value") for key, item in source["scores"].items()}, projected["scores"])
                    self.assertEqual(source["risk_type"], projected["risk_type"])
                    self.assertEqual({key: item.get("state") for key, item in source["pattern"].items()}, projected["pattern"])
                    self.assertEqual(source["major_event"]["polarity"], projected["major_event"]["polarity"])
                    self.assertEqual(source.get("anomaly"), projected.get("anomaly"))
                    self.assertEqual(
                        re.findall(r"news#\d+", str(source.get("news_link") or "")),
                        re.findall(r"news#\d+", str(projected.get("news_link") or "")),
                    )
                evidence_ids = {f"news#{item['id']}" for item in compact["news_evidence"]}
                for row in projected_rows:
                    if row.get("triggers", {}).get("conditional_news"):
                        self.assertIn(row.get("news_link"), evidence_ids)
                if date == "2026-07-15":
                    payload = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    self.assertLessEqual(len(payload) + 1, 80 * 1024)

    def test_gate_b_qualitative_draft_replay(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        draft = draft_for(date, compact, [selected_stock(compact["candidates"][0])])
        self.assertEqual([], validate_draft(draft, compact, date))
        strategy = materialize(draft, compact)
        self.assertEqual("daily_strategy.v3", strategy["schema_version"])
        self.assertEqual("STANDARD", strategy["stocks"][0]["position_tier"])
        self.assertNotIn("position_budget", json.dumps(strategy))

    def test_gate_c_qualitative_contract_and_html(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        draft = draft_for(date, compact, [selected_stock(compact["candidates"][0])])
        strategy = materialize(draft, compact)
        self.assertEqual([], validate(strategy))
        with tempfile.TemporaryDirectory() as tmp:
            news_path = Path(tmp) / "news.json"
            news_path.write_text(json.dumps({"date": date, "items": []}), encoding="utf-8")
            html = render_report(
                date,
                strategy,
                {"schema_version": "daily_strategy_input.v2", "market_state": {},
                 "themes": [], "candidates": [], "observation_pool": []},
                {"schema_version": "daily_mapper.v2", "observation_pool": [], "excluded_stocks": []},
                {"schema_version": "daily_themes.v2", "themes": []},
                news_path,
            )
        self.assertIn("标准仓", html)
        self.assertIn("不代表账户百分比或具体手数", html)


class Step3BoundaryTests(unittest.TestCase):
    def test_incomplete_selected_stock_fails_before_materialize(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        row = compact["candidates"][0]
        incomplete = {"code": row["code"], "sector": "测试主题"}
        errors = validate_draft(draft_for(date, compact, [incomplete]), compact, date)
        self.assertTrue(any("direction" in error for error in errors))
        self.assertTrue(any("entry_setup" in error for error in errors))
        self.assertTrue(any("reasoning" in error for error in errors))

    def test_composite_default_confidence_does_not_trigger_news_reread(self):
        row = candidate("sh600000")
        self.assertEqual([], reread_triggers(row))
        row["scores"]["news_impact"]["confidence"] = 50
        self.assertIn("low_confidence:news_impact", reread_triggers(row))

    def test_auction_news_contradiction_is_restored(self):
        row = candidate("sh600000")
        row["scores"]["news_impact"]["value"] = 30
        self.assertIn("auction_news_contradiction", reread_triggers(row, 3.1))

    def test_regime_hint_requires_neutral_broad_index_for_strong_sector(self):
        state = {"dominant_themes": [{"name": "强主题", "final_heat": 90}]}
        themes = [{"name": "强主题", "final_heat": 90}]
        indices = {"sh000001": {"percent": 0.8}, "sh000688": {"percent": 2.5}}
        self.assertEqual("neutral", derive_regime(indices, state, themes))
        indices["sh000001"]["percent"] = 0.2
        self.assertEqual("strong-sector", derive_regime(indices, state, themes))

    def test_fetch_stock_percent_strings_are_normalized_for_regime(self):
        raw = [
            {"code": "sh000001", "name": "上证指数", "percent": "-1.09%", "open": "3912.38"},
            {"code": "sz399001", "name": "深证成指", "percent": "-1.91%", "open": "14497.429"},
            {"code": "sh000688", "name": "科创50", "percent": "-2.82%", "open": "1869.94"},
        ]
        indices = normalize_indices(raw)
        self.assertEqual(-1.09, indices["sh000001"]["percent"])
        self.assertEqual(-1.91, index_percent(indices, "sz399001"))
        self.assertEqual("weak", derive_regime(indices, {}, []))

    def test_fetch_indices_does_not_mark_percent_strings_as_failed(self):
        raw = [
            {"code": "sh000001", "percent": "-1.09%"},
            {"code": "sz399001", "percent": "-1.91%"},
            {"code": "sh000688", "percent": "-2.82%"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "indices.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            indices, _, failed = fetch_indices(path)
        self.assertFalse(failed)
        self.assertEqual(-2.82, indices["sh000688"]["percent"])

    def test_not_selected_reason_is_generic_when_limit_not_reached(self):
        date = "2026-07-15"
        codes, compact = small_inputs(date)
        stock = selected_stock(compact["candidates"][0])
        draft = draft_for(date, compact, [stock])
        self.assertEqual([], validate_draft(draft, compact, date))
        strategy = materialize(draft, compact)
        self.assertEqual(codes[1], strategy["observation_pool"][0]["code"])
        self.assertIn("完整候选比较后未入选", strategy["observation_pool"][0]["reason"])

    def test_unsupported_sources_fail(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        stock = selected_stock(compact["candidates"][0])
        stock["reasoning"]["source_basis"] += " NewsDirect news#999"
        draft = draft_for(date, compact, [stock])
        errors = validate_draft(draft, compact, date)
        self.assertTrue(any("unsupported news" in error for error in errors))
        self.assertTrue(any("unsupported role tags" in error for error in errors))

    def test_llm_owned_input_hash_field_is_forbidden(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        draft = draft_for(date, compact, [selected_stock(compact["candidates"][0])])
        draft["source"] = {"strategy_input_sha256": "0" * 64}
        errors = validate_draft(draft, compact, date)
        self.assertIn("source: forbidden; input fingerprint is Python-owned", errors)

    def test_python_owned_input_fingerprint_accepts_current_draft(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hash_path = root / INPUT_HASH_FILENAME
            draft_path = root / "strategy.draft.json"
            write_input_hash(hash_path, compact)
            draft_path.write_text("{}", encoding="utf-8")
            hash_mtime = hash_path.stat().st_mtime_ns
            os.utime(draft_path, ns=(hash_mtime + 1, hash_mtime + 1))
            self.assertEqual([], validate_draft_link(compact, draft_path, hash_path))

    def test_python_owned_input_fingerprint_rejects_stale_draft(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hash_path = root / INPUT_HASH_FILENAME
            draft_path = root / "strategy.draft.json"
            draft_path.write_text("{}", encoding="utf-8")
            write_input_hash(hash_path, compact)
            draft_mtime = draft_path.stat().st_mtime_ns
            os.utime(hash_path, ns=(draft_mtime + 1, draft_mtime + 1))
            errors = validate_draft_link(compact, draft_path, hash_path)
            self.assertTrue(any("not written after current prepare" in error for error in errors))

    def test_python_owned_input_fingerprint_rejects_changed_input(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hash_path = root / INPUT_HASH_FILENAME
            draft_path = root / "strategy.draft.json"
            write_input_hash(hash_path, compact)
            draft_path.write_text("{}", encoding="utf-8")
            hash_mtime = hash_path.stat().st_mtime_ns
            os.utime(draft_path, ns=(hash_mtime + 1, hash_mtime + 1))
            compact["market_inputs"]["index_fetch_failed"] = True
            errors = validate_draft_link(compact, draft_path, hash_path)
            self.assertTrue(any("does not match current compact input" in error for error in errors))

    def test_timing_requires_exact_content_linkage_and_invalidates_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compact, draft, strategy = root / "input.json", root / "draft.json", root / "strategy.json"
            compact.write_text("{}", encoding="utf-8")
            draft.write_text("{}", encoding="utf-8")
            strategy.write_text("{}", encoding="utf-8")
            report = root / "step3_timing.json"
            update_report(report, "2026-07-15", "prepare", 1, [], [compact])
            update_report(report, "2026-07-15", "strategy_llm", 2, [compact], [draft], timing_method="measured")
            update_report(
                report,
                "2026-07-15",
                "finalize",
                3,
                [draft],
                [strategy],
                validation_retries=1,
                validation_status="passed",
            )
            doc = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(doc["complete_same_run"])
            self.assertTrue(doc["gate_d_eligible"])
            self.assertEqual("measured", doc["stages"]["strategy_llm"]["timing_method"])
            self.assertEqual(1, doc["stages"]["finalize"]["validation_retry_count"])
            self.assertEqual("passed", doc["validation_attempts"][-1]["status"])
            compact.write_text('{"changed":true}', encoding="utf-8")
            update_report(report, "2026-07-15", "prepare", 1, [], [compact])
            doc = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(doc["complete_same_run"])
            self.assertEqual({"prepare"}, set(doc["stages"]))

    def test_failed_finalize_timing_is_not_gate_d_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compact, draft = root / "input.json", root / "draft.json"
            compact.write_text("{}", encoding="utf-8")
            draft.write_text("{}", encoding="utf-8")
            report = root / "step3_timing.json"
            update_report(report, "2026-07-15", "prepare", 1, [], [compact])
            update_report(
                report,
                "2026-07-15",
                "strategy_llm",
                2,
                [compact],
                [draft],
                validation_retries=0,
                timing_method="measured",
            )
            update_report(
                report,
                "2026-07-15",
                "finalize",
                1,
                [compact, draft],
                [],
                validation_retries=0,
                validation_status="failed",
                validation_errors=["draft invalid"],
            )
            doc = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(doc["complete_same_run"])
            self.assertFalse(doc["gate_d_eligible"])
            self.assertEqual(["draft invalid"], doc["validation_attempts"][0]["errors"])

    def test_validation_retry_count_is_inferred_from_current_input_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compact = root / "input.json"
            draft = root / "draft.json"
            report = root / "step3_timing.json"
            compact.write_text('{"input":1}', encoding="utf-8")
            draft.write_text("{}", encoding="utf-8")
            update_report(report, "2026-07-15", "prepare", 1, [], [compact])
            update_report(
                report,
                "2026-07-15",
                "finalize",
                1,
                [compact, draft],
                [],
                validation_status="failed",
                validation_errors=["draft invalid"],
            )
            self.assertEqual(1, validation_retry_count(report, "2026-07-15", compact))
            compact.write_text('{"input":2}', encoding="utf-8")
            self.assertEqual(0, validation_retry_count(report, "2026-07-15", compact))

    def test_materialize_owns_fixed_fields_and_canonical_name(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        stock = selected_stock(compact["candidates"][0])
        draft = draft_for(date, compact, [stock])
        strategy = materialize(draft, compact)
        selected = strategy["stocks"][0]
        self.assertEqual(compact["candidates"][0]["name"], selected["name"])
        self.assertEqual("T+1", selected["horizon"])
        self.assertEqual("09:35:05", selected["preopen_plan"]["earliest_entry_time"])
        self.assertTrue(selected["profile_trace"])
        self.assertEqual(
            {"max_new_positions": 7, "max_theme_positions": 3, "max_correlated_names": 2},
            strategy["portfolio_limits"],
        )

    def test_old_temporary_schemas_fail_closed(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        draft = draft_for(date, compact, [selected_stock(compact["candidates"][0])])
        draft["schema_version"] = "daily_strategy_draft.tmp.v2"
        self.assertTrue(any("daily_strategy_draft.tmp.v3" in error for error in validate_draft(draft, compact, date)))
        compact["schema_version"] = "strategy_llm_input.tmp.v2"
        self.assertTrue(any("strategy_llm_input.tmp.v3" in error for error in validate_draft(draft, compact, date)))

    def test_candidate_defaults_and_profile_refs_expand_semantically(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        row = compact["candidates"][0]
        self.assertNotIn("risk_type", row)
        self.assertNotIn("major_event", row)
        self.assertNotIn("source_themes", row)
        self.assertNotIn("role_tags", row)
        self.assertNotIn("profile_base", row)
        expanded = expand_candidate(compact, row)
        self.assertEqual([], expanded["risk_type"])
        self.assertEqual(["ThemeLibrary"], expanded["role_tags"])
        self.assertEqual(["测试主题"], expanded["source_themes"])
        self.assertIsInstance(expanded["profile_base"], dict)

    def test_plan_override_is_sparse_reasoned_and_whitelisted(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        stock = selected_stock(compact["candidates"][0])
        stock["plan_overrides"] = {
            "entry_trigger": {"value": "仅在放量站回MA20后参与", "reason": "个股波动较大"}
        }
        draft = draft_for(date, compact, [stock])
        self.assertEqual([], validate_draft(draft, compact, date))
        self.assertEqual("仅在放量站回MA20后参与", materialize(draft, compact)["stocks"][0]["entry_trigger"])
        stock["plan_overrides"]["latest_entry_time"] = {"value": "10:30:00", "reason": "越界"}
        self.assertTrue(any("not whitelisted" in error for error in validate_draft(draft, compact, date)))

    def test_plan_baselines_cover_all_entry_setups_and_anchors(self):
        setups = (
            "LIMIT_UP_CONT", "MOMENTUM", "FIRST_BAR_OR_PULLBACK",
            "PULLBACK", "DEFENSIVE", "WATCH_ONLY",
        )
        anchors = ("MA5", "MA10", "MA20", "OPEN", "VWAP", "首根5min", "FLEX", "无", "—")
        for setup in setups:
            for anchor in anchors:
                with self.subTest(setup=setup, anchor=anchor):
                    self.assertTrue(entry_trigger(anchor, setup))

    def test_empty_duplicate_and_unknown_selections_fail_closed(self):
        date = "2026-07-15"
        _, compact = small_inputs(date)
        empty = draft_for(date, compact, [])
        self.assertTrue(any("must be non-empty" in error for error in validate_draft(empty, compact, date)))
        stock = selected_stock(compact["candidates"][0])
        duplicate = draft_for(date, compact, [copy.deepcopy(stock), copy.deepcopy(stock)])
        self.assertTrue(any("duplicate" in error for error in validate_draft(duplicate, compact, date)))
        stock["code"] = "sh699999"
        unknown = draft_for(date, compact, [stock])
        self.assertTrue(any("not present" in error for error in validate_draft(unknown, compact, date)))


if __name__ == "__main__":
    unittest.main()
