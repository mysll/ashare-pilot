#!/usr/bin/env python3
"""Build the compact, non-contract Step 3 LLM input."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import workspace_path
from ashare_pilot.mapping.daily_contract import theme_projection_errors

from .trade_profile import compute_trade_profile

SCHEMA = "strategy_llm_input.tmp.v2"
SCORE_KEYS = ("composite", "tech", "theme_heat", "news_impact", "auction", "money_flow")
PATTERN_KEYS = ("heat", "leader", "auction", "rotation", "volume")
NEWS_RE = re.compile(r"^news#(\d+)$")
NEWS_ANY_RE = re.compile(r"news#(\d+)")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def compact_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_bytes(value) + b"\n")
    temporary.replace(path)


def number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def percent_number(value: Any) -> float | None:
    parsed = number(value)
    if parsed is not None:
        return parsed
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    if not text or text in {"-", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def score_value(candidate: dict[str, Any], key: str) -> float | None:
    item = candidate.get("scores", {}).get(key, {})
    return number(item.get("value")) if isinstance(item, dict) else None


def direction_base(composite: float | None) -> str:
    if composite is None or composite < 45:
        return "看空"
    if composite < 55:
        return "中性"
    if composite < 70:
        return "偏多"
    return "看多"


def risk_severity(risks: list[str], regime: str) -> int:
    severities = []
    for risk in risks:
        if risk == "trend_weak":
            severities.append(2 if regime == "strong-sector" else 3)
        elif risk == "overbought":
            severities.append(1 if regime == "strong-sector" else 2)
        elif risk == "oversold_opportunity":
            severities.append(1)
        elif risk == "broken_board":
            severities.append(2 if regime == "strong-sector" else (3 if regime in {"weak", "panic"} else 2))
        elif risk == "auction_anomaly":
            severities.append(2)
        else:
            severities.append(1)
    return max(severities, default=0)


def index_percent(indices: dict[str, Any], code: str) -> float | None:
    value = indices.get(code)
    if not isinstance(value, dict):
        return None
    for key in ("percent", "change_pct", "pct_change"):
        parsed = percent_number(value.get(key))
        if parsed is not None:
            return parsed
    return None


def derive_regime(indices: dict[str, Any], market_state: dict[str, Any], themes: list[dict[str, Any]]) -> str:
    sh_pct = index_percent(indices, "sh000001")
    kcb_pct = index_percent(indices, "sh000688")
    dominant_heat = max(
        [number(item.get("final_heat")) or 0 for item in market_state.get("dominant_themes", []) if isinstance(item, dict)]
        + [number(item.get("final_heat")) or 0 for item in themes if isinstance(item, dict)]
        + [0]
    )
    if sh_pct is not None and sh_pct < -1.5:
        return "panic"
    if sh_pct is not None and sh_pct < -0.5:
        return "weak"
    # strong-sector is structural strength inside an otherwise neutral broad
    # index. A broad-index rise >0.5% is kept neutral in this four-state
    # contract; the LLM still sees the raw index and owns the final regime.
    if sh_pct is not None and -0.5 <= sh_pct <= 0.5 and (dominant_heat >= 85 or (kcb_pct is not None and kcb_pct > 2)):
        return "strong-sector"
    return "neutral"


def theme_index(theme_stocks: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["code"]: item for item in theme_stocks.get("stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }


def pool_index(pool: Any) -> dict[str, dict[str, Any]]:
    return {
        item["code"]: item for item in pool
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    } if isinstance(pool, list) else {}


def raw_profile_inputs(candidate: dict[str, Any], pool_entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = dict(pool_entry.get("raw_observation", {})) if isinstance(pool_entry.get("raw_observation"), dict) else {}
    for key, value in candidate.get("strategy_inputs", {}).items():
        if key != "price_source":
            raw[key] = {"value": value}
    computed = pool_entry.get("computed_perception", {}) if isinstance(pool_entry.get("computed_perception"), dict) else {}
    return raw, computed


def build_profile(candidate: dict[str, Any], pool_entry: dict[str, Any], regime: str,
                  primary_theme: str | None, market_state: dict[str, Any], indices: dict[str, Any]) -> dict[str, Any]:
    dominant = {item.get("name") for item in market_state.get("dominant_themes", []) if isinstance(item, dict)}
    raw, computed = raw_profile_inputs(candidate, pool_entry)
    profile = compute_trade_profile(
        candidate.get("code"), raw, computed, regime, primary_theme in dominant,
        score_value(candidate, "theme_heat"), index_percent(indices, "sh000688"), None,
    )
    strategy_inputs = candidate.get("strategy_inputs", {})
    profile["ref_ma20"] = strategy_inputs.get("ma20")
    profile["ref_ma5"] = strategy_inputs.get("ma5")
    profile["ref_high20"] = strategy_inputs.get("high20")
    profile["ref_ma10"] = None
    profile.pop("code", None)
    return profile


def reread_triggers(candidate: dict[str, Any], auction_change_pct: float | None = None) -> list[str]:
    triggers: list[str] = []
    anomaly = str(candidate.get("anomaly") or "").strip()
    if anomaly and anomaly != "—":
        triggers.append("anomaly")
    # Composite confidence is the minimum of all weighted inputs. Its normal
    # value is currently 50 when the deterministic money-flow default is used;
    # rereading news cannot resolve that missing input. Trigger only when an
    # underlying perception field that news/evidence review can affect is low.
    confidence_keys = ("tech", "theme_heat", "news_impact")
    low_fields = [
        key for key in confidence_keys
        if number(candidate.get("scores", {}).get(key, {}).get("confidence")) is not None
        and number(candidate["scores"][key]["confidence"]) < 60
    ]
    if low_fields:
        triggers.append("low_confidence:" + ",".join(low_fields))
    theme_heat, tech = score_value(candidate, "theme_heat"), score_value(candidate, "tech")
    polarity = str(candidate.get("major_event", {}).get("polarity") or "").lower()
    composite = score_value(candidate, "composite")
    if theme_heat is not None and tech is not None and theme_heat >= 80 and tech < 40:
        triggers.append("theme_tech_contradiction")
    if polarity == "positive" and composite is not None and composite < 50:
        triggers.append("event_score_contradiction")
    news_impact = score_value(candidate, "news_impact")
    if auction_change_pct is not None and auction_change_pct > 3 and news_impact is not None and news_impact < 40:
        triggers.append("auction_news_contradiction")
    return triggers


def news_map(news: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        item["id"]: item for item in news.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }


def candidate_news_id(candidate: dict[str, Any]) -> int | None:
    link = candidate.get("news_link")
    match = NEWS_RE.fullmatch(link) if isinstance(link, str) else None
    return int(match.group(1)) if match else None


def build_input(view: dict[str, Any], theme_stocks: dict[str, Any], pool: Any,
                news: dict[str, Any], indices: dict[str, Any]) -> dict[str, Any]:
    if view.get("schema_version") != "daily_strategy_input.v2":
        raise ValueError("strategy view schema_version must be daily_strategy_input.v2")
    if theme_stocks.get("schema_version") != "daily_theme_stocks.v2":
        raise ValueError("theme_stocks schema_version must be daily_theme_stocks.v2")
    projection_errors = [
        error
        for source, rows in (
            ("strategy_view", view.get("themes")),
            ("theme_stocks", theme_stocks.get("themes")),
        )
        if isinstance(rows, list)
        for index, theme in enumerate(rows)
        for error in theme_projection_errors(
            theme, f"{source}.themes[{index}]"
        )
    ]
    if not isinstance(view.get("themes"), list):
        projection_errors.append("strategy_view.themes: must be list")
    if not isinstance(theme_stocks.get("themes"), list):
        projection_errors.append("theme_stocks.themes: must be list")
    if projection_errors:
        raise ValueError(
            "invalid theme projection:\n"
            + "\n".join(f"  - {error}" for error in projection_errors)
        )
    if any(doc.get("date") != view.get("date") for doc in (theme_stocks, news)):
        raise ValueError("strategy view, theme_stocks, and news dates must match")
    themes = [item for item in view.get("themes", []) if isinstance(item, dict)]
    market_state = view.get("market_state", {}) if isinstance(view.get("market_state"), dict) else {}
    regime = derive_regime(indices, market_state, themes)
    stocks_by_code = theme_index(theme_stocks)
    pool_by_code = pool_index(pool)
    available_news = news_map(news)
    for theme in themes:
        refs = theme.get("evidence_refs")
        if not isinstance(refs, list):
            raise ValueError("theme evidence_refs must be a list")
        for ref in refs:
            match = NEWS_RE.fullmatch(ref) if isinstance(ref, str) else None
            if not match or int(match.group(1)) not in available_news:
                raise ValueError(f"unresolved theme news reference: {ref}")
    output_candidates: list[dict[str, Any]] = []
    evidence_ids: set[int] = set()
    seen: set[str] = set()
    for candidate in view.get("candidates", []):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("code"), str):
            raise ValueError("every strategy-view candidate must be an object with code")
        code = candidate["code"]
        if code in seen:
            raise ValueError(f"duplicate strategy-view candidate: {code}")
        seen.add(code)
        source = stocks_by_code.get(code, {})
        source_themes = [
            item.get("name") for item in source.get("source_themes", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        primary_theme = source_themes[0] if source_themes else None
        scores = {key: score_value(candidate, key) for key in SCORE_KEYS}
        confidence_exceptions = {
            key: candidate.get("scores", {}).get(key, {}).get("confidence") for key in SCORE_KEYS
            if candidate.get("scores", {}).get(key, {}).get("confidence") != 100
        }
        pattern = {key: candidate.get("pattern", {}).get(key, {}).get("state") for key in PATTERN_KEYS}
        pool_entry = pool_by_code.get(code, {})
        raw = pool_entry.get("raw_observation", {}) if isinstance(pool_entry.get("raw_observation"), dict) else {}
        def raw_value(key: str) -> Any:
            item = raw.get(key)
            return item.get("value") if isinstance(item, dict) else item
        auction_change_pct = number(raw_value("auction_change_pct"))
        trigger_flags = reread_triggers(candidate, auction_change_pct)
        news_id = candidate_news_id(candidate)
        if news_id is not None and news_id not in available_news:
            raise ValueError(f"unresolved news reference for {code}: news#{news_id}")
        conditional_triggers = trigger_flags if news_id is not None else []
        if conditional_triggers:
            evidence_ids.add(news_id)
        risks = candidate.get("risk_type") if isinstance(candidate.get("risk_type"), list) else []
        strategy_inputs = candidate.get("strategy_inputs", {}) if isinstance(candidate.get("strategy_inputs"), dict) else {}
        row: dict[str, Any] = {
            "code": code, "name": candidate.get("name"),
            "primary_theme": primary_theme, "source_themes": source_themes,
            "role_tags": candidate.get("role_tags") or [], "news_link": candidate.get("news_link"),
            "scores": scores, "risk_type": risks, "pattern": pattern,
            "major_event": {
                "polarity": candidate.get("major_event", {}).get("polarity"),
                "confidence": candidate.get("major_event", {}).get("confidence"),
            },
            "anomaly": candidate.get("anomaly"),
            "strategy_inputs": {key: strategy_inputs.get(key) for key in ("price_source", "price", "ma5", "ma20", "atr", "atr_pct", "high20", "low20")},
            "profile_inputs": {key: value for key, value in {
                "board_streak": raw_value("board_streak"), "yesterday_limit_up": raw_value("yesterday_limit_up")
            }.items() if value is not None},
            "direction_base_hint": direction_base(scores["composite"]),
            "risk_severity_base_hint": risk_severity(risks, regime),
            "profile_base": {"regime_basis": regime, **build_profile(candidate, pool_entry, regime, primary_theme, market_state, indices)},
        }
        # Reference prices and T+1 already exist in strategy_inputs/the output
        # contract. Avoid duplicating them in every advisory profile row.
        for redundant in ("ref_ma20", "ref_ma10", "ref_ma5", "ref_high20", "time_horizon"):
            row["profile_base"].pop(redundant, None)
        if auction_change_pct is not None:
            row["strategy_inputs"]["auction_change_pct"] = auction_change_pct
        if trigger_flags:
            row["triggers"] = {"flags": trigger_flags, "conditional_news": conditional_triggers}
        if confidence_exceptions:
            row["confidence_exceptions"] = confidence_exceptions
        output_candidates.append(row)
    input_codes = [item["code"] for item in output_candidates]
    view_codes = [item.get("code") for item in view.get("candidates", []) if isinstance(item, dict)]
    if input_codes != view_codes or set(input_codes) != set(view_codes):
        raise ValueError("compact candidate coverage/order differs from strategy view")
    evidence = [
        {key: available_news[item_id].get(key) for key in ("id", "title", "source", "desc")}
        for item_id in sorted(evidence_ids)
    ]
    return {
        "schema_version": SCHEMA, "date": view.get("date"), "non_contract": True,
        "source": {"strategy_view_sha256": canonical_sha256(view)},
        "market_inputs": {"market_state": market_state, "indices": indices, "regime_hint": regime},
        "themes": [{key: item.get(key) for key in ("name", "rank", "final_heat", "attention_direction", "evidence_refs")} for item in themes],
        "news_evidence": evidence, "candidates": output_candidates,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build compact Step 3 LLM input")
    parser.add_argument("--date")
    parser.add_argument("--hash-only", help="Diagnostic: print canonical SHA-256 for an existing JSON artifact")
    parser.add_argument("--strategy-view")
    parser.add_argument("--theme-stocks")
    parser.add_argument("--pool")
    parser.add_argument("--news")
    parser.add_argument("--indices", help="Prepared index quote JSON")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.hash_only:
        try:
            print(canonical_sha256(json.loads(Path(args.hash_only).read_text(encoding="utf-8-sig"))))
            return 0
        except Exception as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
    if not args.date or not args.indices:
        parser.error("--date and --indices are required unless --hash-only is used")
    pdir = workspace_path("predict", args.date)
    try:
        load = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))
        view = load(args.strategy_view or pdir / "mapper.strategy_view.json")
        theme_stocks = load(args.theme_stocks or pdir / "theme_stocks.json")
        pool = load(args.pool or pdir / "pool_indicators.json")
        news = load(args.news or pdir / "news.json")
        indices = load(args.indices)
        if isinstance(indices, list):
            indices = {item.get("code"): item for item in indices if isinstance(item, dict) and item.get("code")}
        result = build_input(view, theme_stocks, pool, news, indices)
        output = Path(args.output) if args.output else pdir / ".strategy_llm_input.json"
        compact_write(output, result)
        # Local import avoids a module cycle: draft_link uses canonical_sha256
        # from this module.
        from .draft_link import INPUT_HASH_FILENAME, write_input_hash
        write_input_hash(output.with_name(INPUT_HASH_FILENAME), result)
        if output.stat().st_size > 90 * 1024:
            print(f"[WARN] compact input exceeds 90KB warning threshold: {output.stat().st_size} bytes", file=sys.stderr)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"OK: wrote {output} ({output.stat().st_size} bytes, {len(result['candidates'])} candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
