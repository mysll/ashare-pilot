from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ashare_pilot.themes._commands.daily.contract import (
    finalize_themes,
    round_score,
    score_components,
)
from ashare_pilot.themes._commands.daily.evidence import (
    build_input,
    main as evidence_main,
)
from ashare_pilot.themes._commands.daily.finalize import main as finalize_main
from ashare_pilot.themes._commands.daily.publish import main as publish_main
from ashare_pilot.themes._commands.daily.validate import validate
from ashare_pilot.themes._commands.daily.validate_annotations import (
    validate as validate_annotations,
)
from ashare_pilot.themes._commands.daily.timing import (
    update_report as update_step1_timing,
)
from ashare_pilot.mapping._commands.daily.strategy_view import build_view
from ashare_pilot.mapping._commands.daily.theme_stock_universe import (
    collect_theme_specs_from_json,
)
from ashare_pilot.mapping.daily_contract import (
    build_deterministic_mapper_base,
    publish_theme_stocks,
)
from ashare_pilot.strategy._commands.daily.llm_input import build_input as build_strategy_input


DATE = "2026-07-29"
REPLAY = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "themes"
    / "2026-07-29"
)


def evidence_theme(name: str, ref: str, title: str | None = None) -> dict:
    return {
        "name": name,
        "matched_concepts": ["数据中心"],
        "evidence": [
            {
                "refs": [ref],
                "category": "policy",
                "source": "测试源",
                "title": title or f"{name}新闻",
                "matches": [
                    {"kind": "alias", "term": name},
                    {"kind": "concept", "term": "数据中心"},
                ],
            }
        ],
        "market_signals": {
            "available": False,
            "trace": "no structured theme market signal",
        },
    }


def annotation(name: str, ref: str, **updates) -> dict:
    row = {
        "name": name,
        "accepted_refs": [ref],
        "confidence": 82,
        "attention_direction": "bullish",
        "market_action": 65,
        "emotion_raw": 80,
        "capital": 45,
        "policy_tier": "none",
        "policy_polarity": "neutral",
        "policy_ref": None,
        "catalyst": None,
        "reason": "证据与主题直接相关",
    }
    row.update(updates)
    return row


def docs(rows: list[tuple[str, str]]) -> tuple[dict, dict, dict]:
    evidence = {
        "schema_version": "theme_evidence_input.tmp.v2",
        "date": DATE,
        "themes": [evidence_theme(name, ref) for name, ref in rows],
    }
    annotations = {
        "schema_version": "daily_theme_annotations.v1",
        "date": DATE,
        "themes": [annotation(name, ref) for name, ref in rows],
    }
    news = {
        "schema_version": "daily_news.v1",
        "date": DATE,
        "items": [
            {"id": int(ref.split("#")[1]), "title": name}
            for name, ref in rows
        ],
    }
    return evidence, annotations, news


class EvidenceTests(unittest.TestCase):
    def test_match_provenance_and_title_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp)
            (library / "themes").mkdir()
            (library / "themes" / "AI.json").write_text(
                json.dumps(
                    {
                        "name": "AI算力",
                        "aliases": ["算力中心"],
                        "keywords": ["GPU"],
                        "concepts": ["数据中心"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            news = {
                "schema_version": "daily_news.v1",
                "date": DATE,
                "items": [
                    {"id": 1, "title": "GPU算力中心扩容", "category": "flash"},
                    {"id": 2, "title": "GPU算力中心扩容", "category": "flash"},
                    {"id": 3, "title": "无关高优先新闻", "category": "policy"},
                ],
            }
            result = build_input(news, library)
        self.assertEqual(result["schema_version"], "theme_evidence_input.tmp.v2")
        self.assertNotIn("unmatched_high_priority", result)
        item = result["themes"][0]["evidence"][0]
        self.assertEqual(item["refs"], ["news#1", "news#2"])
        self.assertEqual(
            {(row["kind"], row["term"]) for row in item["matches"]},
            {("alias", "算力中心"), ("keyword", "GPU")},
        )


class AnnotationValidationTests(unittest.TestCase):
    def test_collects_coverage_extra_and_ref_errors(self):
        evidence, annotations, _ = docs([("AI算力", "news#1")])
        annotations["themes"] = [
            annotation("额外主题", "news#1"),
            annotation("额外主题", "news#99"),
        ]
        errors = validate_annotations(annotations, evidence)
        self.assertTrue(any("not present in evidence input" in item for item in errors))
        self.assertTrue(any("duplicate" in item for item in errors))
        self.assertTrue(any("missing annotation for AI算力" in item for item in errors))

    def test_rejects_policy_and_catalyst_refs_outside_accepted_refs(self):
        evidence, annotations, _ = docs([("AI算力", "news#1")])
        row = annotations["themes"][0]
        row.update(
            {
                "policy_tier": "ministry",
                "policy_ref": "news#2",
                "catalyst": {
                    "type": "landmark_ipo",
                    "evidence_ref": "news#2",
                },
            }
        )
        errors = validate_annotations(annotations, evidence)
        self.assertTrue(any(".policy_ref" in item for item in errors))
        self.assertTrue(any(".catalyst.evidence_ref" in item for item in errors))


class FinalizerTests(unittest.TestCase):
    def test_formula_and_rounding_are_centralized(self):
        parts = score_components(65, 80, "bullish", 2, 45, "none", "neutral")
        self.assertEqual(parts["news_density"], 20)
        self.assertEqual(parts["base_heat"], 60.75)
        self.assertEqual(parts["policy_adjusted_heat"], 60.75)
        self.assertEqual(round_score(61.755), 61.76)

    def test_policy_polarity_and_attention_coefficients(self):
        bullish = score_components(50, 80, "bullish", 1, 45, "ministry", "bullish")
        bearish = score_components(50, 80, "panic", 1, 45, "ministry", "bearish")
        self.assertEqual(bullish["emotion_coefficient"], 1.0)
        self.assertEqual(bearish["emotion_coefficient"], 0.5)
        self.assertEqual(bullish["policy_bonus"], 5)
        self.assertEqual(bearish["policy_coefficient"], 0.0)

    def test_confidence_watch_rank_and_concept_projection(self):
        evidence, annotations, _ = docs(
            [("低置信", "news#1"), ("观察", "news#2"), ("交易", "news#3")]
        )
        annotations["themes"][0].update(confidence=59, market_action=90)
        annotations["themes"][1].update(
            market_action=50, emotion_raw=55, capital=45
        )
        annotations["themes"][2].update(market_action=80)
        result = finalize_themes(evidence, annotations)
        by_name = {item["name"]: item for item in result["themes"]}
        self.assertEqual(by_name["低置信"]["status"], "discarded")
        self.assertEqual(by_name["观察"]["status"], "watch")
        self.assertEqual(by_name["交易"]["status"], "tradeable")
        self.assertEqual(by_name["交易"]["matched_concepts"], ["数据中心"])
        self.assertEqual(
            [item["rank"] for item in result["themes"]],
            list(range(1, 4)),
        )

    def test_catalyst_floor_is_limited_to_two(self):
        rows = [(f"主题{i}", f"news#{i}") for i in range(1, 4)]
        evidence, annotations, _ = docs(rows)
        for item in annotations["themes"]:
            item.update(
                market_action=40,
                emotion_raw=50,
                capital=45,
                catalyst={
                    "type": "landmark_ipo",
                    "evidence_ref": item["accepted_refs"][0],
                },
            )
        result = finalize_themes(evidence, annotations)
        promoted = [item for item in result["themes"] if item["catalyst"]]
        self.assertEqual(len(promoted), 2)
        self.assertTrue(all(item["score"]["final_heat"] == 57 for item in promoted))

    def test_tradeable_is_capped_at_twenty(self):
        rows = [(f"主题{i:02d}", f"news#{i}") for i in range(1, 23)]
        evidence, annotations, _ = docs(rows)
        result = finalize_themes(evidence, annotations)
        self.assertEqual(
            sum(item["status"] == "tradeable" for item in result["themes"]), 20
        )
        self.assertEqual(
            sum(item["status"] == "discarded" for item in result["themes"]), 2
        )


class FormalValidationTests(unittest.TestCase):
    def test_2026_07_29_frozen_v2_replay(self):
        evidence = json.loads((REPLAY / "evidence.json").read_text(encoding="utf-8"))
        annotations = json.loads(
            (REPLAY / "annotations.json").read_text(encoding="utf-8")
        )
        news = json.loads((REPLAY / "news.json").read_text(encoding="utf-8"))
        formal = json.loads((REPLAY / "themes.json").read_text(encoding="utf-8"))
        self.assertEqual(validate(formal, evidence, annotations, news), [])
        self.assertEqual(len(evidence["themes"]), 21)
        self.assertEqual(len(annotations["themes"]), 21)
        self.assertEqual(
            {
                status: sum(
                    item["status"] == status for item in formal["themes"]
                )
                for status in ("tradeable", "watch", "discarded")
            },
            {"tradeable": 6, "watch": 8, "discarded": 7},
        )

    def test_detects_formula_status_rank_and_news_tampering(self):
        evidence, annotations, news = docs([("AI算力", "news#1")])
        formal = finalize_themes(evidence, annotations)
        tampered = copy.deepcopy(formal)
        tampered["themes"][0]["score"]["news_density"] = 99
        tampered["themes"][0]["rank"] = 2
        tampered["themes"][0]["evidence_refs"] = ["news#99"]
        errors = validate(tampered, evidence, annotations, news)
        self.assertTrue(any("missing from news.json" in item for item in errors))

    def test_finalize_fails_closed_on_zero_tradeable(self):
        evidence, annotations, _ = docs([("弱主题", "news#1")])
        annotations["themes"][0].update(
            confidence=40, market_action=10, emotion_raw=10, capital=10
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            annotations_path = root / "annotations.json"
            output_path = root / "themes.json"
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
            )
            annotations_path.write_text(
                json.dumps(annotations, ensure_ascii=False), encoding="utf-8"
            )
            code = finalize_main(
                [
                    "--date",
                    DATE,
                    "--evidence",
                    str(evidence_path),
                    "--annotations",
                    str(annotations_path),
                    "--output",
                    str(output_path),
                ]
            )
        self.assertEqual(code, 1)
        self.assertFalse(output_path.exists())


class AtomicCutoverTests(unittest.TestCase):
    def test_replaced_v1_contracts_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            themes_path = Path(tmp) / "themes.json"
            themes_path.write_text(
                json.dumps(
                    {
                        "schema_version": "daily_themes.v1",
                        "date": DATE,
                        "themes": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "daily_themes.v2"):
                collect_theme_specs_from_json(themes_path, DATE)

        with self.assertRaisesRegex(ValueError, "daily_theme_stocks.v2"):
            build_deterministic_mapper_base(
                DATE,
                {},
                {
                    "schema_version": "daily_theme_stocks.v1",
                    "date": DATE,
                    "themes": [],
                    "stocks": [],
                },
            )
        with self.assertRaisesRegex(ValueError, "daily_theme_stocks_base.v2"):
            publish_theme_stocks(
                {"schema_version": "daily_theme_stocks_base.v1"}, DATE
            )
        with self.assertRaisesRegex(ValueError, "daily_mapper.v2"):
            build_view({"schema_version": "daily_mapper.v1", "date": DATE})
        with self.assertRaisesRegex(ValueError, "daily_strategy_input.v2"):
            build_strategy_input(
                {"schema_version": "daily_strategy_input.v1", "date": DATE},
                {"schema_version": "daily_theme_stocks.v2", "date": DATE},
                [],
                {"date": DATE, "items": []},
                {},
            )

    def test_step1_timing_requires_linked_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "step1_timing.json"
            news = root / "news.json"
            evidence = root / "evidence.json"
            annotations = root / "annotations.json"
            themes = root / "themes.json"
            for path in (news, evidence, annotations, themes):
                path.write_text("{}\n", encoding="utf-8")
            update_step1_timing(
                report, DATE, "news_fetch", 1, [], [news], {}, 0
            )
            update_step1_timing(
                report, DATE, "theme_prepare", 2, [news], [evidence], {}, 0
            )
            update_step1_timing(
                report,
                DATE,
                "theme_llm",
                3,
                [evidence],
                [annotations],
                {},
                0,
            )
            update_step1_timing(
                report,
                DATE,
                "theme_finalize",
                4,
                [evidence, annotations],
                [themes],
                {},
                0,
            )
            timing = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(timing["complete_same_run"])
        self.assertEqual(timing["total_recorded_seconds"], 10)

    def test_step1_commands_record_timing_without_llm_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "theme-library"
            (library / "themes").mkdir(parents=True)
            (library / "themes" / "ai.json").write_text(
                json.dumps(
                    {
                        "name": "AI算力",
                        "aliases": ["AI算力"],
                        "keywords": [],
                        "concepts": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            news = {
                "test": [
                    {
                        "title": "AI算力政策落地",
                        "url": "https://example.test/1",
                        "desc": "产业迎来正向催化",
                    }
                ]
            }
            with (
                patch(
                    "ashare_pilot.themes._commands.daily.evidence.default_predict_dir",
                    return_value=root,
                ),
                patch(
                    "ashare_pilot.themes._commands.daily.evidence.fetch_daily_news",
                    return_value=news,
                ),
            ):
                self.assertEqual(
                    evidence_main(
                        [
                            "--date",
                            DATE,
                            "--theme-library",
                            str(library),
                            "--fetch-news",
                        ]
                    ),
                    0,
                )

            evidence = json.loads(
                (root / ".theme_evidence_input.json").read_text(
                    encoding="utf-8"
                )
            )
            ref = evidence["themes"][0]["evidence"][0]["refs"][0]
            annotations = {
                "schema_version": "daily_theme_annotations.v1",
                "date": DATE,
                "themes": [
                    annotation(
                        "AI算力", ref, attention_direction="bearish"
                    )
                ],
            }
            annotations_path = root / ".theme_annotations.json"
            annotations_path.write_text(
                json.dumps(annotations, ensure_ascii=False),
                encoding="utf-8",
            )
            themes_path = root / "themes.json"
            stale_themes = '{"stale": true}\n'
            themes_path.write_text(stale_themes, encoding="utf-8")
            with patch(
                "ashare_pilot.themes._commands.daily.publish.default_predict_dir",
                return_value=root,
            ):
                self.assertEqual(
                    publish_main(["--date", DATE]),
                    1,
                )
                self.assertEqual(
                    themes_path.read_text(encoding="utf-8"), stale_themes
                )
                annotations["themes"][0]["attention_direction"] = "bullish"
                annotations_path.write_text(
                    json.dumps(annotations, ensure_ascii=False),
                    encoding="utf-8",
                )
                self.assertEqual(
                    publish_main(["--date", DATE]),
                    0,
                )
                self.assertEqual(
                    json.loads(themes_path.read_text(encoding="utf-8"))[
                        "schema_version"
                    ],
                    "daily_themes.v2",
                )

            timing = json.loads(
                (root / "step1_timing.json").read_text(encoding="utf-8")
            )
        self.assertTrue(timing["complete_same_run"])
        self.assertIsInstance(timing["total_recorded_seconds"], float)
        self.assertEqual(
            timing["stages"]["theme_llm"]["validation_retry_count"], 1
        )
        self.assertEqual(
            timing["stages"]["theme_llm"]["validation_status"], "passed"
        )


if __name__ == "__main__":
    unittest.main()
