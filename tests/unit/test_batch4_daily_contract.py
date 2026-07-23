from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ashare_pilot.mapping._commands.daily.compare_regression import (
    classify_changes,
    diff,
    normalized,
)
from ashare_pilot.mapping._commands.daily.prepare import annotation_input
from ashare_pilot.mapping._commands.daily.theme_evidence import build_input
from ashare_pilot.mapping._commands.daily.theme_stock_base import (
    merge_extra_stock,
    stock_template,
)
from ashare_pilot.mapping._commands.daily.theme_stock_universe import (
    enrich_structured_source_flags,
)
from ashare_pilot.mapping._commands.daily.timing import update_report
from ashare_pilot.mapping._commands.daily.validate_annotations import (
    validate,
    validate_candidate_coverage,
    validate_news_refs,
)
from ashare_pilot.mapping.daily_contract import (
    build_deterministic_mapper_base,
    deterministic_pattern,
    merge_annotations,
    publish_theme_stocks,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mapping"


def nested(value):
    return {"value": value, "confidence": 100}


def pool_entry(amount=80000, auction=None):
    raw = {
        "price": nested(10), "ma20": nested(9), "ma5": nested(9.5), "atr": nested(0.3),
        "atr_pct": nested(3), "high20": nested(11), "low20": nested(8), "amount": nested(amount),
        "board_streak": nested(0), "seal_quality": nested(None), "auction_change_pct": nested(auction),
    }
    return {"code": "sz000001", "fetch_failed": False, "raw_observation": raw,
            "computed_perception": {"tech_score": nested(70), "risk_type": nested([]), "risk_flags": nested([])}}


def theme_stocks():
    return {
        "schema_version": "daily_theme_stocks.v1", "date": "2026-07-14",
        "themes": [{"name": "银行", "rank": 1, "heat": 70, "direction": "bullish", "evidence": "news#1"}],
        "stocks": [
            {"code": "sz000001", "name": "平安银行", "source_themes": [{"name": "银行", "score": 70}],
             "source_flags": {"candidate": True, "market": False, "news": False, "lhb": False},
             "filter": {"status": "candidate"}},
            {"code": "sh600000", "name": "浦发银行", "source_themes": [{"name": "银行", "score": 70}],
             "source_flags": {"candidate": True, "market": False, "news": False, "lhb": False},
             "filter": {"status": "observation", "reason": "tech_score=40 < 50"}},
        ],
    }


class OwnershipTests(unittest.TestCase):
    def test_candidate_membership_and_theme_ownership_ignore_annotations(self):
        doc = build_deterministic_mapper_base("2026-07-14", {"sz000001": pool_entry()}, theme_stocks())
        self.assertEqual([item["code"] for item in doc["candidate_pool"]], ["sz000001"])
        self.assertEqual([(item["name"], item["rank"], item["final_heat"]) for item in doc["themes"]], [("银行", 1, 70.0)])
        self.assertEqual((doc["themes"][0]["direction"], doc["themes"][0]["evidence"]), ("bullish", "news#1"))

    def test_deterministic_base_preserves_structured_news_ref(self):
        fixture = theme_stocks()
        fixture["stocks"][0]["news_ref"] = "news#7"
        fixture["stocks"][0]["source_flags"]["news"] = True
        doc = build_deterministic_mapper_base("2026-07-14", {"sz000001": pool_entry()}, fixture)
        self.assertEqual(doc["candidate_pool"][0]["news_link"], "news#7")

    def test_missing_annotation_does_not_remove_candidate_but_coverage_fails(self):
        base = build_deterministic_mapper_base("2026-07-14", {"sz000001": pool_entry()}, theme_stocks())
        merged = merge_annotations(base, {"schema_version": "daily_mapper_annotations.v1", "date": "2026-07-14", "stocks": []}, "2026-07-14")
        self.assertEqual([item["code"] for item in merged["candidate_pool"]], ["sz000001"])
        errors, _ = validate_candidate_coverage({"stocks": []}, theme_stocks())
        self.assertTrue(any("sz000001" in item for item in errors))

    def test_extra_non_candidate_warns_without_requiring_semantics(self):
        doc = {
            "schema_version": "daily_mapper_annotations.v1", "date": "2026-07-14",
            "stocks": [
                {"code": "sz000001", "news_relevance": {"r": "R0", "p": "P0", "confidence": 90, "trace": "none"}},
                {"code": "sh600000"},
            ],
        }
        self.assertEqual(validate(doc, {"sz000001"}), [])
        errors, warnings = validate_candidate_coverage(doc, theme_stocks())
        self.assertEqual(errors, [])
        self.assertTrue(any("sh600000" in item for item in warnings))

    def test_unresolved_news_ref_fails(self):
        annotations = {"stocks": [{"code": "sz000001", "news_relevance": {
            "r": "R4", "p": "P3", "confidence": 90, "evidence": "news#99"}}]}
        self.assertTrue(any("news#99" in item for item in validate_news_refs(annotations, {"items": [{"id": 1}]})))

    def test_duplicate_theme_annotations_are_rejected(self):
        doc = {"schema_version": "daily_mapper_annotations.v1", "date": "2026-07-14",
               "themes": [{"name": "银行"}], "stocks": []}
        self.assertTrue(any(item.startswith("themes:") for item in validate(doc)))

    def test_observation_cannot_be_promoted_by_annotation(self):
        base = build_deterministic_mapper_base("2026-07-14", {"sz000001": pool_entry()}, theme_stocks())
        annotations = {"stocks": [{"code": "sh600000", "news_relevance": {"r": "R0", "p": "P0", "confidence": 90, "trace": "none"}}]}
        merged = merge_annotations(base, annotations, "2026-07-14")
        self.assertNotIn("sh600000", [item["code"] for item in merged["candidate_pool"]])


class PatternTests(unittest.TestCase):
    def test_volume_boundaries_and_missing_auction(self):
        stock = theme_stocks()["stocks"][0]
        self.assertEqual(deterministic_pattern(stock, pool_entry(80000), 70)["volume"]["state"], "SURGE")
        self.assertEqual(deterministic_pattern(stock, pool_entry(30000), 70)["volume"]["state"], "NORMAL")
        self.assertEqual(deterministic_pattern(stock, pool_entry(29999), 70)["volume"]["state"], "DRY")
        self.assertEqual(deterministic_pattern(stock, pool_entry(), 70)["auction"], {"state": "UNKNOWN", "confidence": 0, "trace": "real auction input unavailable"})

    def test_valid_auction_and_sparse_override(self):
        stock = theme_stocks()["stocks"][0]
        pattern = deterministic_pattern(stock, pool_entry(80000, 2.5), 70)
        self.assertEqual(pattern["auction"]["state"], "LEADING")
        base = build_deterministic_mapper_base("2026-07-14", {"sz000001": pool_entry()}, theme_stocks())
        annotations = {"stocks": [{"code": "sz000001", "news_relevance": {"r": "R0", "p": "P0", "confidence": 90, "trace": "none"},
                                   "pattern": {"rotation": {"state": "PRIMARY", "confidence": 95, "trace": "reviewed"}}}]}
        merged = merge_annotations(base, annotations, "2026-07-14")
        actual = merged["candidate_pool"][0]["pattern"]
        self.assertEqual(actual["rotation"]["state"], "PRIMARY")
        self.assertEqual(actual["auction"]["state"], "UNKNOWN")


class SourceTests(unittest.TestCase):
    def test_extra_cannot_self_assert_source_flags(self):
        stock = stock_template("sz000001", "平安银行")
        merge_extra_stock(stock, {"source": "news_direct", "source_themes": ["银行"],
                                  "source_flags": {"news": True, "market": True, "lhb": True},
                                  "news_ref": "news#999"})
        self.assertEqual(stock["source_flags"], {"candidate": False, "market": False, "news": False, "lhb": False})

    def test_structured_source_flags(self):
        stocks = {"sz000001": {"code": "sz000001", "name": "平安银行", "source_flags": {"candidate": True, "market": False, "news": False, "lhb": False}}}
        news = {"items": [{"id": 7, "title": "平安银行发布公告", "desc": ""}]}
        market = {"themes": {"银行": {"top_gainers": [{"code": "sz000001", "change_pct": 3.0}]}}}
        enrich_structured_source_flags(stocks, news, market, {"items": [{"code": "sz000001"}]})
        self.assertEqual(stocks["sz000001"]["source_flags"], {"candidate": True, "market": True, "news": True, "lhb": True})
        self.assertEqual(stocks["sz000001"]["news_ref"], "news#7")

    def test_market_threshold_rows_are_not_limited_to_display_top_ten(self):
        stocks = {
            "sz000001": {"code": "sz000001", "name": "平安银行", "source_flags": {"candidate": True, "market": False, "news": False, "lhb": False}},
            "sh600000": {"code": "sh600000", "name": "浦发银行", "source_flags": {"candidate": True, "market": False, "news": False, "lhb": False}},
        }
        market = {"themes": {"银行": {
            "top_gainers": [], "market_attention": [], "cross_rank_highlights": [],
            "threshold_gainers": [{"code": "sz000001", "change_pct": 3.1}],
            "threshold_attention": [{"code": "sh600000", "attention_score": 81}],
        }}}
        enrich_structured_source_flags(stocks, None, market, None)
        self.assertTrue(stocks["sz000001"]["source_flags"]["market"])
        self.assertTrue(stocks["sh600000"]["source_flags"]["market"])

    def test_publish_deletes_annotation_metadata_and_prose(self):
        base = theme_stocks()
        base["schema_version"] = "daily_theme_stocks_base.v1"
        published = publish_theme_stocks(base, "2026-07-14")
        self.assertEqual(published["generation_mode"], "deterministic_base_publish")
        self.assertNotIn("annotation_schema_version", published)

    def test_compact_theme_input_preserves_recall_and_drops_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp)
            (library / "themes").mkdir()
            (library / "themes" / "AI.json").write_text(json.dumps({
                "name": "AI算力", "aliases": ["算力"], "keywords": ["GPU"], "concepts": ["数据中心"]
            }, ensure_ascii=False), encoding="utf-8")
            news = {"date": "2026-07-14", "items": [
                {"id": 8, "category": "policy", "source": "x", "title": "GPU算力政策发布", "url": "https://example.test/8", "source_item_no": 2, "desc": ""},
                {"id": 9, "category": "policy", "source": "y", "title": "GPU算力政策发布", "url": "https://example.test/9", "source_item_no": 3, "desc": ""},
            ]}
            result = build_input(news, library)
            item = result["themes"][0]["items"][0]
            self.assertEqual(item["ids"], ["news#8", "news#9"])
            self.assertNotIn("url", item)
            self.assertNotIn("source_item_no", item)

    def test_mapper_input_links_candidates_to_compact_news(self):
        fixture = theme_stocks()
        fixture["stocks"][0]["news_ref"] = "news#7"
        fixture["stocks"][0]["source_flags"]["news"] = True
        base = build_deterministic_mapper_base("2026-07-14", {"sz000001": pool_entry()}, fixture)
        news = {"items": [
            {"id": 7, "category": "company", "source": "x", "title": "平安银行发布公告", "desc": "直接事件"},
            {"id": 8, "category": "policy", "source": "y", "title": "银行政策", "desc": "行业事件"},
        ]}
        evidence = {"themes": [{"name": "银行", "items": [
            {"ids": ["news#8"], "category": "policy", "source": "y", "title": "银行政策", "desc": "行业事件"}
        ]}]}
        result = annotation_input(base, fixture, news, evidence)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["source_themes"], ["银行"])
        self.assertEqual(candidate["direct_news_refs"], ["news#7"])
        self.assertEqual(candidate["theme_news_refs"], ["news#8"])
        self.assertEqual({ref for row in result["news_evidence"] for ref in row["refs"]}, {"news#7", "news#8"})

    def test_timing_total_requires_one_linked_complete_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "timing.json"
            news, themes, mapper_input, annotations, mapper = [root / name for name in (
                "news.json", "themes.json", "mapper_input.json", "annotations.json", "mapper.json"
            )]
            for path in (news, themes, mapper_input, annotations, mapper):
                path.write_text("{}\n", encoding="utf-8")
            update_report(report, "2026-07-14", "theme_llm", 1, [news], [themes])
            update_report(report, "2026-07-14", "prepare", 2, [themes], [mapper_input])
            update_report(report, "2026-07-14", "mapper_annotation_llm", 3, [mapper_input], [annotations])
            update_report(report, "2026-07-14", "finalize", 4, [annotations], [mapper])
            complete = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(complete["complete_same_run"])
            self.assertEqual(complete["total_recorded_seconds"], 10)
            update_report(report, "2026-07-14", "prepare", 2.5, [themes], [mapper_input])
            incomplete = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(incomplete["complete_same_run"])
            self.assertIsNone(incomplete["total_recorded_seconds"])
            self.assertNotIn("finalize", incomplete["stages"])


class FrozenGateTests(unittest.TestCase):
    def test_dated_frozen_gate_cases(self):
        fixture_path = FIXTURES / "step2_frozen_gates.json"
        cases = json.loads(fixture_path.read_text(encoding="utf-8"))["cases"]
        self.assertEqual([item["date"] for item in cases], ["2026-07-09", "2026-07-13", "2026-07-14"])
        for case in cases:
            with self.subTest(date=case["date"], gate=case["gate"]):
                changes = diff(normalized(case["before"]), normalized(case["after"]))
                _, blocked = classify_changes(changes, case["gate"], case["allowlist"])
                self.assertEqual(blocked, [])

    def test_task2_blocks_role_tag_shrinkage(self):
        before = {"candidates": [{"code": "sz000001", "role_tags": ["ThemeLibrary", "MarketActive"]}]}
        after = {"candidates": [{"code": "sz000001", "role_tags": ["ThemeLibrary"]}]}
        _, blocked = classify_changes(diff(before, after), "task2")
        self.assertTrue(blocked)

    def test_task45_requires_exact_allowlist_for_confidence_and_trace(self):
        changes = [("$.candidates[0].pattern.leader.confidence", 80, 20)]
        _, blocked = classify_changes(changes, "task45")
        self.assertEqual(blocked, changes)

    def test_2026_07_14_market_source_correction_audit_is_complete(self):
        path = FIXTURES / "2026-07-14-market-source-corrections.json"
        audit = json.loads(path.read_text(encoding="utf-8"))
        structured = set(audit["structured_market_active_codes"])
        unsupported = set(audit["unsupported_historical_market_active_codes"])
        self.assertFalse(structured & unsupported)
        self.assertEqual(len(structured), 23)
        self.assertEqual(len(unsupported), 22)
        self.assertEqual(len(structured | unsupported), audit["historical_blanket_market_active_count"])


if __name__ == "__main__":
    unittest.main()
