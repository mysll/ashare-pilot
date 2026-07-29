#!/usr/bin/env python3
"""Validate a selected-only Step 3 draft and publish final contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import workspace_path

from .draft_link import INPUT_HASH_FILENAME, validate_draft_link
from .timing import update_report
from .llm_input import SCHEMA as INPUT_SCHEMA, index_percent
from .trade_profile import compute_trade_profile
from .render_report import render_report
from .validate_strategy import (
    ANCHORS, CHASE_POLICIES, ENTRY_WINDOWS, HORIZONS, PLAYBOOKS,
    REGIME_STOCK_LIMITS, STOP_POLICIES, validate as validate_strategy,
)

DRAFT_SCHEMA = "daily_strategy_draft.tmp.v2"
FINAL_SCHEMA = "daily_strategy.v3"
NEWS_RE = re.compile(r"news#\d+")
KNOWN_ROLE_TAGS = {"ThemeLibrary", "MarketActive", "NewsDirect", "MultiTheme", "Anchor", "LHB"}
PROFILE_OVERRIDE_ENUMS = {
    "playbook": PLAYBOOKS, "preferred_anchor": ANCHORS, "chase_policy": CHASE_POLICIES,
    "entry_window": ENTRY_WINDOWS, "stop_policy": STOP_POLICIES, "time_horizon": HORIZONS,
}
PROFILE_OVERRIDE_FIELDS = set(PROFILE_OVERRIDE_ENUMS) | {
    "invalidation", "note", "max_extension_atr",
    "ref_ma20", "ref_ma10", "ref_ma5", "ref_high20",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def candidate_index(compact: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    candidates = compact.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("compact candidates must be list")
    codes: list[str] = []
    by_code: dict[str, dict[str, Any]] = {}
    for row in candidates:
        if not isinstance(row, dict) or not isinstance(row.get("code"), str):
            raise ValueError("compact candidate must have code")
        code = row["code"]
        if code in by_code:
            raise ValueError(f"duplicate compact candidate: {code}")
        codes.append(code)
        by_code[code] = row
    return codes, by_code


def draft_contract_errors(draft: dict[str, Any]) -> list[str]:
    """Run the final v3 contract against draft-owned fields before materialize.

    A valid placeholder profile prevents Python-owned profile materialization
    from masking or delaying errors in LLM-owned stock decisions.
    """
    errors: list[str] = []
    generated_at = draft.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        errors.append("generated_at: must be non-empty ISO-8601 string")
    else:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("generated_at: must be valid ISO-8601")

    market = draft.get("market")
    if not isinstance(market, dict):
        errors.append("market: must be object")
    else:
        if not isinstance(market.get("stop_atr_multiplier"), (int, float)) or isinstance(market.get("stop_atr_multiplier"), bool):
            errors.append("market.stop_atr_multiplier: must be number")
        if "position_multiplier" in market:
            errors.append("market.position_multiplier: forbidden; v3 uses qualitative position tiers")
        if not isinstance(market.get("notes"), str) or not market.get("notes", "").strip():
            errors.append("market.notes: must be non-empty string")

    stocks = draft.get("stocks") if isinstance(draft.get("stocks"), list) else []
    provisional_stocks: list[Any] = []
    required = {
        "code", "name", "sector", "direction", "rating", "entry_profile", "anchor",
        "entry_trigger", "no_buy_condition", "position_tier", "horizon", "preopen_plan",
        "t1_risk_plan", "rules_applied", "profile_trace", "reasoning", "profile_overrides",
    }
    for index, stock in enumerate(stocks):
        if not isinstance(stock, dict):
            provisional_stocks.append(stock)
            continue
        base = f"stocks[{index}]"
        for field in sorted(required - set(stock)):
            errors.append(f"{base}.{field}: missing required draft field")
        rules = stock.get("rules_applied")
        if "rules_applied" in stock and not (isinstance(rules, list) and all(isinstance(item, str) and item for item in rules)):
            errors.append(f"{base}.rules_applied: must be list of non-empty rule IDs")
        if not isinstance(stock.get("profile_trace"), str) or not stock.get("profile_trace", "").strip():
            errors.append(f"{base}.profile_trace: must be non-empty string")
        reasoning = stock.get("reasoning")
        if not isinstance(reasoning, dict):
            errors.append(f"{base}.reasoning: must be object")
        else:
            for field in ("source_basis", "direction_path", "risk", "reread", "override"):
                if not isinstance(reasoning.get(field), str) or not reasoning.get(field, "").strip():
                    errors.append(f"{base}.reasoning.{field}: must be non-empty string")
        provisional = {key: value for key, value in stock.items() if key != "profile_overrides"}
        provisional["profile"] = {
            "playbook": "PULLBACK", "preferred_anchor": "FLEX", "chase_policy": "NO_CHASE",
            "entry_window": "ANY", "stop_policy": "ATR_1.5", "time_horizon": "T+1",
        }
        provisional_stocks.append(provisional)

    provisional_doc = {
        "schema_version": FINAL_SCHEMA, "date": draft.get("date"),
        "market": draft.get("market"), "portfolio_limits": draft.get("portfolio_limits"),
        "stocks": provisional_stocks, "observation_pool": [],
    }
    errors.extend(validate_strategy(provisional_doc))
    return errors


def validate_profile_overrides(overrides: Any, stock: dict[str, Any], base: str, errors: list[str]) -> None:
    if overrides is None:
        return
    if not isinstance(overrides, dict):
        errors.append(f"{base}.profile_overrides: must be object")
        return
    for field, override in overrides.items():
        path = f"{base}.profile_overrides.{field}"
        if field not in PROFILE_OVERRIDE_FIELDS:
            errors.append(f"{path}: field is not whitelisted")
            continue
        if not isinstance(override, dict) or set(override) != {"value", "reason"}:
            errors.append(f"{path}: must contain exactly value and reason")
            continue
        if not isinstance(override.get("reason"), str) or not override["reason"].strip():
            errors.append(f"{path}.reason: must be non-empty")
        value = override.get("value")
        if field in PROFILE_OVERRIDE_ENUMS and value not in PROFILE_OVERRIDE_ENUMS[field]:
            errors.append(f"{path}.value: invalid enum {value!r}")
        elif field in {"invalidation", "note"} and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{path}.value: must be non-empty string")
        elif field in {"max_extension_atr", "ref_ma20", "ref_ma5", "ref_high20"} and not isinstance(value, (int, float)):
            errors.append(f"{path}.value: must be number")
        elif field == "ref_ma10" and value is not None:
            errors.append(f"{path}.value: ref_ma10 must remain null because it is absent from Step 2 inputs")
        if field in {"ref_ma20", "ref_ma5", "ref_high20"} and isinstance(value, (int, float)):
            source_key = {"ref_ma20": "ma20", "ref_ma5": "ma5", "ref_high20": "high20"}[field]
            # Reference overrides may choose exact source precision or its established
            # two-decimal display precision, but may not invent a price.
            source_value = stock.get("_candidate_strategy_inputs", {}).get(source_key)
            if isinstance(source_value, (int, float)) and value not in {source_value, round(source_value, 2)}:
                errors.append(f"{path}.value: must equal exact or 2-decimal Step 2 source value")
    horizon = overrides.get("time_horizon") if isinstance(overrides, dict) else None
    if isinstance(horizon, dict) and horizon.get("value") != stock.get("horizon"):
        errors.append(f"{base}.profile_overrides.time_horizon: must equal selected stock horizon")


def validate_draft(draft: dict[str, Any], compact: dict[str, Any], expected_date: str) -> list[str]:
    errors: list[str] = []
    if draft.get("schema_version") != DRAFT_SCHEMA:
        errors.append(f"schema_version: must be {DRAFT_SCHEMA}")
    if draft.get("date") != expected_date or compact.get("date") != expected_date:
        errors.append("date: draft, input, and requested date must match")
    if compact.get("schema_version") != INPUT_SCHEMA or compact.get("non_contract") is not True:
        errors.append(f"input: must be {INPUT_SCHEMA} non-contract artifact")
    if "source" in draft:
        errors.append("source: forbidden; input fingerprint is Python-owned")
    errors.extend(draft_contract_errors(draft))
    _, candidates = candidate_index(compact)
    stocks = draft.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        errors.append("stocks: must be non-empty selected-only list")
        return errors
    regime = draft.get("market", {}).get("regime_prior") if isinstance(draft.get("market"), dict) else None
    limit = REGIME_STOCK_LIMITS.get(regime)
    if limit is None:
        errors.append(f"market.regime_prior: unsupported {regime!r}")
    elif len(stocks) > limit:
        errors.append(f"stocks: {regime} allows at most {limit}, got {len(stocks)}")
    theme_refs = {
        item.get("name"): set(NEWS_RE.findall(str(item.get("evidence") or "")))
        for item in compact.get("themes", []) if isinstance(item, dict)
    }
    seen: set[str] = set()
    for index, stock in enumerate(stocks):
        base = f"stocks[{index}]"
        if not isinstance(stock, dict):
            errors.append(f"{base}: must be object")
            continue
        code = stock.get("code")
        if code not in candidates:
            errors.append(f"{base}.code: not present in compact candidate set")
            continue
        if code in seen:
            errors.append(f"{base}.code: duplicate {code}")
        seen.add(code)
        candidate = candidates[code]
        stock_for_profile_validation = dict(stock)
        stock_for_profile_validation["_candidate_strategy_inputs"] = candidate.get("strategy_inputs", {})
        if stock.get("name") != candidate.get("name"):
            errors.append(f"{base}.name: differs from compact candidate")
        if stock.get("sector") not in candidate.get("source_themes", []):
            errors.append(f"{base}.sector: must be one of candidate source_themes")
        reasoning = stock.get("reasoning")
        source_basis = reasoning.get("source_basis", "") if isinstance(reasoning, dict) else ""
        allowed_refs = {candidate.get("news_link")} if isinstance(candidate.get("news_link"), str) else set()
        for theme in candidate.get("source_themes", []):
            allowed_refs.update(theme_refs.get(theme, set()))
        used_refs = set(NEWS_RE.findall(json.dumps(stock, ensure_ascii=False)))
        if not used_refs.issubset(allowed_refs):
            errors.append(f"{base}: unsupported news references {sorted(used_refs - allowed_refs)}")
        mentioned_tags = {
            tag for tag in KNOWN_ROLE_TAGS
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(tag)}(?![A-Za-z0-9_])", source_basis)
        }
        unsupported_tags = mentioned_tags - set(candidate.get("role_tags", []))
        if unsupported_tags:
            errors.append(f"{base}.reasoning.source_basis: unsupported role tags {sorted(unsupported_tags)}")
        validate_profile_overrides(stock.get("profile_overrides", {}), stock_for_profile_validation, base, errors)
    overrides = draft.get("exclusion_overrides", [])
    if not isinstance(overrides, list):
        errors.append("exclusion_overrides: must be list when present")
    else:
        override_seen: set[str] = set()
        for index, item in enumerate(overrides):
            if not isinstance(item, dict) or set(item) != {"code", "reason"}:
                errors.append(f"exclusion_overrides[{index}]: must contain exactly code and reason")
                continue
            code = item.get("code")
            if code not in candidates or code in seen or code in override_seen:
                errors.append(f"exclusion_overrides[{index}].code: must be a unique unselected input candidate")
            override_seen.add(code)
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                errors.append(f"exclusion_overrides[{index}].reason: must be non-empty")
    return errors


def recompute_profile(candidate: dict[str, Any], compact: dict[str, Any], regime: str) -> dict[str, Any]:
    strategy_inputs = candidate.get("strategy_inputs", {})
    profile_inputs = candidate.get("profile_inputs", {})
    raw = {key: {"value": value} for key, value in {**strategy_inputs, **profile_inputs}.items() if key != "price_source"}
    market_inputs = compact.get("market_inputs", {})
    market_state = market_inputs.get("market_state", {})
    dominant = {item.get("name") for item in market_state.get("dominant_themes", []) if isinstance(item, dict)}
    indices = market_inputs.get("indices", {})
    profile = compute_trade_profile(
        candidate["code"], raw, {}, regime, candidate.get("primary_theme") in dominant,
        candidate.get("scores", {}).get("theme_heat"), index_percent(indices, "sh000688"), None,
    )
    profile.pop("code", None)
    profile.pop("position_tier", None)
    profile.update({
        "ref_ma20": strategy_inputs.get("ma20"), "ref_ma10": None,
        "ref_ma5": strategy_inputs.get("ma5"), "ref_high20": strategy_inputs.get("high20"),
    })
    return profile


def apply_overrides(profile: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = dict(profile)
    for field, item in overrides.items():
        result[field] = item["value"]
    return result


def materialize(draft: dict[str, Any], compact: dict[str, Any]) -> dict[str, Any]:
    candidate_codes, candidates = candidate_index(compact)
    regime = draft["market"]["regime_prior"]
    selected: list[dict[str, Any]] = []
    selected_codes: set[str] = set()
    for draft_stock in draft["stocks"]:
        stock = {key: value for key, value in draft_stock.items() if key != "profile_overrides"}
        if isinstance(stock.get("t1_risk_plan"), dict):
            stock["t1_risk_plan"] = {
                key: value
                for key, value in stock["t1_risk_plan"].items()
                if key != "max_holding_days"
            }
        profile = recompute_profile(candidates[stock["code"]], compact, regime)
        stock["profile"] = apply_overrides(profile, draft_stock.get("profile_overrides", {}))
        if stock["profile"].get("time_horizon") != stock.get("horizon"):
            raise ValueError(f"{stock['code']} final profile time_horizon contradicts selected stock")
        selected.append(stock)
        selected_codes.add(stock["code"])
    explicit = {item["code"]: item["reason"] for item in draft.get("exclusion_overrides", [])}
    limit = REGIME_STOCK_LIMITS[regime]
    limit_reached = len(selected) >= limit
    observations = []
    for code in candidate_codes:
        if code in selected_codes:
            continue
        candidate = candidates[code]
        primary = candidate.get("primary_theme") or "未标注主题"
        hard_reason = candidate.get("hard_unbuyable_reason")
        if code in explicit:
            reason = explicit[code]
        elif isinstance(hard_reason, str) and hard_reason.strip():
            reason = hard_reason.strip()
        elif limit_reached:
            reason = f"{regime}主策略名额限制；主主题：{primary}"
        else:
            reason = f"完整候选比较后未入选；主主题：{primary}"
        observations.append({"code": code, "name": candidate.get("name") or code, "reason": reason})
    return {
        "schema_version": FINAL_SCHEMA, "date": draft["date"],
        "generated_at": draft.get("generated_at"), "market": draft.get("market"),
        "portfolio_limits": draft.get("portfolio_limits"), "stocks": selected,
        "observation_pool": observations,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Finalize selected-only daily strategy draft")
    parser.add_argument("--date", required=True)
    parser.add_argument("--input-dir", help="Input contracts directory; defaults to predict/{date}")
    parser.add_argument("--output-dir", help="Output directory; defaults to input directory")
    parser.add_argument("--draft")
    parser.add_argument("--validation-retries", type=int, default=0)
    parser.add_argument("--llm-duration", type=float, help="Measured LLM wall time in seconds; preferred for Gate D")
    args = parser.parse_args(argv)
    if args.llm_duration is not None and args.llm_duration < 0:
        parser.error("--llm-duration must be non-negative")
    started = time.perf_counter()
    input_dir = Path(args.input_dir) if args.input_dir else workspace_path("predict", args.date)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    compact_path = input_dir / ".strategy_llm_input.json"
    input_hash_path = input_dir / INPUT_HASH_FILENAME
    draft_path = Path(args.draft) if args.draft else input_dir / "strategy.draft.json"
    failure_recorded = False
    try:
        compact, draft = load(compact_path), load(draft_path)
        if not isinstance(compact, dict) or not isinstance(draft, dict):
            raise ValueError("compact input and draft roots must be objects")
        llm_duration = args.llm_duration if args.llm_duration is not None else max(0.0, draft_path.stat().st_mtime - compact_path.stat().st_mtime)
        llm_timing_method = "measured" if args.llm_duration is not None else "mtime_estimate"
        candidate_count = len(compact.get("candidates", [])) if isinstance(compact.get("candidates"), list) else 0
        selected_count = len(draft.get("stocks", [])) if isinstance(draft.get("stocks"), list) else 0
        update_report(output_dir / "step3_timing.json", args.date, "strategy_llm", llm_duration,
                      [compact_path, input_hash_path], [draft_path],
                      {"candidate_count": candidate_count, "selected_count": selected_count,
                       "observation_count": 0, "conditional_news_count": len(compact.get("news_evidence", [])),
                       "llm_input_bytes": compact_path.stat().st_size, "llm_output_bytes": draft_path.stat().st_size},
                      validation_retries=args.validation_retries, timing_method=llm_timing_method)
        errors = validate_draft_link(compact, draft_path, input_hash_path)
        errors.extend(validate_draft(draft, compact, args.date))
        if errors:
            update_report(
                output_dir / "step3_timing.json",
                args.date,
                "finalize",
                time.perf_counter() - started,
                [compact_path, input_hash_path, draft_path],
                [],
                validation_retries=args.validation_retries,
                validation_status="failed",
                validation_errors=errors,
            )
            failure_recorded = True
            raise ValueError("draft validation failed:\n" + "\n".join(f"  - {item}" for item in errors))
        strategy = materialize(draft, compact)
        validation_errors = validate_strategy(strategy)
        if validation_errors:
            raise ValueError("final strategy validation failed:\n" + "\n".join(f"  - {item}" for item in validation_errors))
        view = load(input_dir / "mapper.strategy_view.json")
        mapper = load(input_dir / "mapper.json")
        themes_path = input_dir / "themes.json"
        themes = load(themes_path) if themes_path.exists() else None
        news_path = input_dir / "news.json"
        html = render_report(args.date, strategy, view, mapper, themes, news_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        strategy_path = output_dir / "strategy.json"
        html_path = output_dir / "daily_report.html"
        strategy_tmp = strategy_path.with_suffix(".json.tmp")
        html_tmp = html_path.with_suffix(".html.tmp")
        strategy_tmp.write_text(json.dumps(strategy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        html_tmp.write_text(html, encoding="utf-8", newline="\n")
        strategy_tmp.replace(strategy_path)
        html_tmp.replace(html_path)
        duration = time.perf_counter() - started
        update_report(output_dir / "step3_timing.json", args.date, "finalize", duration,
                      [compact_path, input_hash_path, draft_path], [strategy_path, html_path],
                      {"candidate_count": len(compact["candidates"]), "selected_count": len(strategy["stocks"]),
                       "observation_count": len(strategy["observation_pool"]),
                       "conditional_news_count": len(compact.get("news_evidence", [])),
                       "llm_input_bytes": compact_path.stat().st_size, "llm_output_bytes": draft_path.stat().st_size},
                      validation_retries=args.validation_retries,
                      validation_status="passed")
    except Exception as exc:
        if not failure_recorded:
            update_report(
                output_dir / "step3_timing.json",
                args.date,
                "finalize",
                time.perf_counter() - started,
                [compact_path, input_hash_path, draft_path],
                [],
                validation_retries=args.validation_retries,
                validation_status="failed",
                validation_errors=str(exc).splitlines(),
            )
        print(f"[ERROR] finalize_daily_strategy failed: {exc}", file=sys.stderr)
        return 1
    print(f"OK: published {strategy_path} and {html_path} in {duration:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
