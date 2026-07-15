#!/usr/bin/env python3
"""Regenerate checked-in Step 3 frozen fixtures from local historical artifacts.

Tests consume only the generated fixtures. This helper is intentionally not
part of test discovery and is run manually when a fixture refresh is reviewed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / ".opencode" / "skills" / "daily-strategy" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_strategy_llm_input import build_input, canonical_sha256  # noqa: E402
from finalize_daily_strategy import (  # noqa: E402
    PROFILE_OVERRIDE_FIELDS, materialize, recompute_profile, validate_draft,
)

OUT = Path(__file__).parent / "fixtures" / "step3_real"
DATES = {
    "2026-07-13": {"sh000001": -0.75, "sz399001": -0.91, "sh000688": 0.66},
    "2026-07-14": {"sh000001": -0.12, "sz399001": 0.07, "sh000688": 0.01},
    "2026-07-15": {"sh000001": -0.09, "sz399001": 0.31, "sh000688": 0.59},
}
NEWS_RE = re.compile(r"news#(\d+)")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def projected_theme_stocks(doc: dict[str, Any], date: str) -> dict[str, Any]:
    return {
        "date": date,
        "stocks": [
            {"code": item.get("code"), "source_themes": item.get("source_themes", [])}
            for item in doc.get("stocks", []) if isinstance(item, dict)
        ],
    }


def projected_pool(doc: Any) -> list[dict[str, Any]]:
    result = []
    for item in doc if isinstance(doc, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str):
            continue
        raw = item.get("raw_observation", {}) if isinstance(item.get("raw_observation"), dict) else {}
        keep = {
            key: raw.get(key) for key in (
                "price", "ma5", "ma20", "atr", "high20", "board_streak",
                "yesterday_limit_up", "auction_change_pct",
            ) if key in raw
        }
        result.append({"code": item["code"], "raw_observation": keep, "computed_perception": {}})
    return result


def projected_news(doc: dict[str, Any], view: dict[str, Any], date: str) -> dict[str, Any]:
    ids: set[int] = set()
    for candidate in view.get("candidates", []):
        if isinstance(candidate, dict):
            ids.update(int(value) for value in NEWS_RE.findall(str(candidate.get("news_link") or "")))
    for theme in view.get("themes", []):
        if isinstance(theme, dict):
            ids.update(int(value) for value in NEWS_RE.findall(str(theme.get("evidence") or "")))
    return {
        "date": date,
        "items": [item for item in doc.get("items", []) if isinstance(item, dict) and item.get("id") in ids],
    }


def compliant_source_basis(candidate: dict[str, Any]) -> str:
    parts = [f"{candidate.get('primary_theme') or '未标注主题'}主题候选"]
    tags = [tag for tag in candidate.get("role_tags", []) if isinstance(tag, str)]
    if tags:
        parts.append("+".join(tags))
    if isinstance(candidate.get("news_link"), str):
        parts.append(candidate["news_link"])
    return "，".join(parts)


def draft_from_strategy(strategy: dict[str, Any], compact: dict[str, Any]) -> dict[str, Any]:
    by_code = {item["code"]: item for item in compact["candidates"]}
    theme_refs = {
        item.get("name"): {f"news#{value}" for value in NEWS_RE.findall(str(item.get("evidence") or ""))}
        for item in compact.get("themes", []) if isinstance(item, dict)
    }
    stocks = []
    for source_stock in strategy["stocks"]:
        stock = {key: value for key, value in source_stock.items() if key != "profile"}
        reasoning = dict(stock.get("reasoning", {}))
        if not isinstance(reasoning.get("source_basis"), str) or not reasoning["source_basis"].strip():
            reasoning["source_basis"] = compliant_source_basis(by_code[stock["code"]])
        candidate = by_code[stock["code"]]
        allowed_refs = {candidate.get("news_link")} if isinstance(candidate.get("news_link"), str) else set()
        for theme in candidate.get("source_themes", []):
            allowed_refs.update(theme_refs.get(theme, set()))
        for field, value in list(reasoning.items()):
            if not isinstance(value, str):
                continue
            reasoning[field] = re.sub(
                r"news#\d+", lambda match: match.group(0) if match.group(0) in allowed_refs else "历史未投影新闻",
                value,
            )
        stock["reasoning"] = reasoning
        base = recompute_profile(by_code[stock["code"]], compact, strategy["market"]["regime_prior"])
        overrides = {}
        for field, value in source_stock.get("profile", {}).items():
            if base.get(field) == value or field not in PROFILE_OVERRIDE_FIELDS:
                continue
            if field.startswith("ref_"):
                source_value = by_code[stock["code"]].get("strategy_inputs", {}).get(field[4:])
                allowed = {source_value, round(source_value, 2)} if isinstance(source_value, (int, float)) else {None}
                if value not in allowed:
                    continue
            overrides[field] = {"value": value, "reason": "frozen historical decision replay"}
        stock["profile_overrides"] = overrides
        stocks.append(stock)
    return {
        "schema_version": "daily_strategy_draft.tmp.v1", "date": strategy["date"],
        "generated_at": strategy["generated_at"],
        "source": {"strategy_input_sha256": canonical_sha256(compact)},
        "market": strategy["market"], "portfolio_limits": strategy["portfolio_limits"],
        "stocks": stocks, "exclusion_overrides": [],
    }


def expected_snapshot(strategy: dict[str, Any]) -> dict[str, Any]:
    fields = ("code", "direction", "rating", "position_budget", "entry_profile", "anchor", "rules_applied", "profile")
    return {
        "regime_prior": strategy["market"]["regime_prior"],
        "stocks": [{key: item.get(key) for key in fields} for item in strategy["stocks"]],
        "observation_codes": [item.get("code") for item in strategy["observation_pool"]],
    }


def main() -> int:
    legacy_date = "2026-07-09"
    legacy_view = load(ROOT / "predict" / legacy_date / "mapper.strategy_view.json")
    write(OUT / f"{legacy_date}.json", {
        "schema_version": "step3_frozen_legacy.v1", "date": legacy_date,
        "expected_prepare_error": "canonical news.json unavailable in legacy artifact",
        "view": legacy_view,
        "candidate_codes": [item.get("code") for item in legacy_view.get("candidates", [])],
    })

    for date, percentages in DATES.items():
        pdir = ROOT / "predict" / date
        view = load(pdir / "mapper.strategy_view.json")
        theme_stocks = projected_theme_stocks(load(pdir / "theme_stocks.json"), date)
        pool = projected_pool(load(pdir / "pool_indicators.json"))
        news = projected_news(load(pdir / "news.json"), view, date)
        indices = {code: {"code": code, "percent": value} for code, value in percentages.items()}
        compact = build_input(view, theme_stocks, pool, news, indices)
        draft = draft_from_strategy(load(pdir / "strategy.json"), compact)
        errors = validate_draft(draft, compact, date)
        if errors:
            raise ValueError(f"{date} draft invalid:\n" + "\n".join(errors))
        final = materialize(draft, compact)
        bundle = {
            "schema_version": "step3_frozen_replay.v1", "date": date,
            "view": view, "theme_stocks": theme_stocks, "pool": pool, "news": news,
            "indices": indices, "expected_compact_sha256": canonical_sha256(compact),
            "draft": draft, "expected": expected_snapshot(final),
        }
        write(OUT / f"{date}.json", bundle)
        print(f"wrote {date}: {len(compact['candidates'])} candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
