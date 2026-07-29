#!/usr/bin/env python3
"""Helpers for the daily mapper JSON contract."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import workspace_path


CODE_RE = re.compile(r"\b(?:[a-z]{2}\d{6}|[a-z]{2,4}_[a-z0-9]+)\b", re.IGNORECASE)
MISSING_VALUES = {"", "-", "--", "None", "none", "null", "N/A", "鈥?", "鈥擿", "—"}
NUMERIC_TOLERANCE = 0.005
THEME_PROJECTION_FIELDS = {
    "name",
    "rank",
    "final_heat",
    "attention_direction",
    "evidence_refs",
}
THEME_ATTENTION_DIRECTIONS = {
    "bullish",
    "mixed",
    "panic",
    "neutral",
    "unknown",
}
NEWS_IMPACT_MATRIX = {
    ("R4", "P0"): 0,
    ("R4", "P3"): 95,
    ("R4", "P2"): 85,
    ("R4", "P1"): 70,
    ("R3", "P0"): 0,
    ("R3", "P3"): 80,
    ("R3", "P2"): 70,
    ("R3", "P1"): 55,
    ("R2", "P0"): 0,
    ("R2", "P3"): 65,
    ("R2", "P2"): 55,
    ("R2", "P1"): 40,
    ("R1", "P0"): 0,
    ("R1", "P3"): 45,
    ("R1", "P2"): 35,
    ("R1", "P1"): 25,
    ("R0", "P3"): 0,
    ("R0", "P2"): 0,
    ("R0", "P1"): 0,
    ("R0", "P0"): 0,
}


def workspace_root() -> Path:
    return workspace_path()


def default_predict_dir(date: str) -> Path:
    return workspace_root() / "predict" / date


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def ensure_doc_date(doc: dict[str, Any], expected_date: str, label: str = "document") -> None:
    actual = doc.get("date")
    if actual != expected_date:
        raise ValueError(f"{label} date mismatch: expected {expected_date}, got {actual!r}")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text in MISSING_VALUES else text


def parse_float(value: Any) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    text = text.replace("%", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    number = parse_float(value)
    if number is None:
        return None
    return int(number)


def theme_projection_errors(item: Any, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(item, dict):
        return [f"{path}: must be object"]
    missing = sorted(THEME_PROJECTION_FIELDS - set(item))
    unexpected = sorted(set(item) - THEME_PROJECTION_FIELDS)
    if missing:
        errors.append(f"{path}: missing fields {missing}")
    if unexpected:
        errors.append(f"{path}: unexpected fields {unexpected}")
    if not clean_text(item.get("name")):
        errors.append(f"{path}.name: required")
    rank = item.get("rank")
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
        errors.append(f"{path}.rank: must be positive integer")
    heat = item.get("final_heat")
    if (
        not isinstance(heat, (int, float))
        or isinstance(heat, bool)
        or not 0 <= heat <= 100
    ):
        errors.append(f"{path}.final_heat: must be number in [0, 100]")
    if item.get("attention_direction") not in THEME_ATTENTION_DIRECTIONS:
        errors.append(f"{path}.attention_direction: invalid enum")
    refs = item.get("evidence_refs")
    if not isinstance(refs, list) or not all(
        isinstance(ref, str) and re.fullmatch(r"news#\d+", ref) for ref in refs
    ):
        errors.append(f"{path}.evidence_refs: must be canonical news ref list")
    return errors


def format_num(value: Any, percent: bool = False) -> str:
    number = parse_float(value)
    if number is None:
        return "-"
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{text}%" if percent else text


def raw_value(pool_entry: dict[str, Any] | None, field: str) -> Any:
    if not pool_entry:
        return None
    raw = pool_entry.get("raw_observation", {})
    value = raw.get(field)
    if isinstance(value, dict):
        return value.get("value")
    return value


def computed_value(pool_entry: dict[str, Any] | None, field: str) -> Any:
    if not pool_entry:
        return None
    computed = pool_entry.get("computed_perception", {})
    value = computed.get(field)
    if isinstance(value, dict):
        return value.get("value")
    return value


def load_pool(path: Path) -> dict[str, dict[str, Any]]:
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"pool_indicators must be a list: {path}")
    result: dict[str, dict[str, Any]] = {}
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("code"), str):
            result[item["code"]] = item
    return result


def default_scope_path() -> Path:
    return workspace_root() / "config" / "trading-scope.json"


def load_trading_scope(path: Path | None = None) -> dict[str, Any]:
    scope_path = path or default_scope_path()
    data = read_json(scope_path)
    if not isinstance(data, dict):
        raise ValueError(f"trading scope must be an object: {scope_path}")
    if not isinstance(data.get("boards"), dict):
        raise ValueError(f"trading scope missing boards object: {scope_path}")
    if not isinstance(data.get("overrides", []), list):
        raise ValueError(f"trading scope overrides must be a list: {scope_path}")
    return data


def scope_decision(code: str, scope: dict[str, Any]) -> dict[str, Any]:
    """Return tradeability using trading-scope.json only.

    Longest board prefix wins. Overrides may use either {"code": "..."} or
    {"codes": [...]} and can set exclude/allowed plus an optional reason.
    """
    normalized = str(code or "").strip()
    for override in scope.get("overrides", []):
        if not isinstance(override, dict):
            continue
        codes = override.get("codes")
        if isinstance(codes, str):
            codes = [codes]
        elif not isinstance(codes, list):
            single = override.get("code")
            codes = [single] if isinstance(single, str) else []
        if normalized not in codes:
            continue
        if "allowed" in override:
            allowed = bool(override.get("allowed"))
            exclude = not allowed
        else:
            exclude = bool(override.get("exclude"))
            allowed = not exclude
        return {
            "allowed": allowed,
            "matched_rule": f"overrides.{normalized}",
            "reason": clean_text(override.get("reason")) or ("allowed by override" if allowed else "excluded by override"),
        }

    boards = scope.get("boards", {})
    matches = [prefix for prefix in boards if isinstance(prefix, str) and normalized.startswith(prefix)]
    if not matches:
        return {"allowed": False, "matched_rule": "boards.<none>", "reason": "no matching trading-scope board"}
    prefix = max(matches, key=len)
    rule = boards.get(prefix) if isinstance(boards.get(prefix), dict) else {}
    exclude = bool(rule.get("exclude"))
    return {
        "allowed": not exclude,
        "matched_rule": f"boards.{prefix}",
        "reason": clean_text(rule.get("reason")) or ("allowed by trading scope" if not exclude else "excluded by trading scope"),
    }


def board_policy_from_scope(scope: dict[str, Any]) -> dict[str, str]:
    policy: dict[str, str] = {}
    boards = scope.get("boards", {})
    for prefix, rule in boards.items():
        if not isinstance(rule, dict):
            continue
        policy[str(prefix)] = "exclude" if rule.get("exclude") else "allow"
    return policy


def parse_list_cell(value: Any) -> list[str]:
    text = clean_text(value)
    if text is None:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text.replace("'", '"'))
            if isinstance(parsed, list):
                return [str(item) for item in parsed if clean_text(item)]
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in text.split(",") if clean_text(part)]


def field_conf(value: Any) -> int:
    return 100 if clean_text(value) is not None else 0


def score(value: Any, confidence: Any = None, trace: str | None = None) -> dict[str, Any]:
    number = parse_float(value)
    return {
        "value": number,
        "confidence": parse_int(confidence) if confidence is not None else field_conf(number),
        "trace": clean_text(trace),
    }


def annotation_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def scored_annotation(obj: Any, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = fallback or {}
    if not isinstance(obj, dict):
        return dict(fallback)
    return {
        "value": parse_float(obj.get("value", fallback.get("value"))),
        "confidence": parse_int(obj.get("confidence", fallback.get("confidence", 0))) or 0,
        "trace": clean_text(obj.get("trace", fallback.get("trace"))),
        "evidence": clean_text(obj.get("evidence", fallback.get("evidence"))),
    }


def strategy_inputs_from_pool(code: str, pool: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entry = pool.get(code)
    return {
        "price": parse_float(raw_value(entry, "price")),
        "price_source": "PrevClose",
        "ma20": parse_float(raw_value(entry, "ma20")),
        "ma5": parse_float(raw_value(entry, "ma5")),
        "atr": parse_float(raw_value(entry, "atr")),
        "atr_pct": parse_float(raw_value(entry, "atr_pct")),
        "high20": parse_float(raw_value(entry, "high20")),
        "low20": parse_float(raw_value(entry, "low20")),
    }


def normalize_major_event(value: Any) -> str:
    text = (clean_text(value) or "none").lower()
    if text in {"positive", "negative", "none", "unknown"}:
        return text
    return "none"


def pattern_state(value: Any) -> dict[str, Any]:
    text = clean_text(value)
    return {"state": text or "UNKNOWN", "confidence": 80 if text else 0, "trace": None}


def technical_value(stock: dict[str, Any], pool_entry: dict[str, Any] | None, field: str) -> Any:
    technical = stock.get("technical") if isinstance(stock.get("technical"), dict) else {}
    if field in technical:
        return technical.get(field)
    if field == "tech_score":
        return computed_value(pool_entry, "tech_score")
    if field in {"risk_type", "risk_flags"}:
        return computed_value(pool_entry, field)
    if field == "fetch_failed":
        return bool(pool_entry.get("fetch_failed")) if pool_entry else None
    return raw_value(pool_entry, field)


def theme_stock_filter(stock: dict[str, Any]) -> dict[str, Any]:
    filt = stock.get("filter") if isinstance(stock.get("filter"), dict) else {}
    status = clean_text(filt.get("status")) or clean_text(stock.get("status")) or "candidate"
    return {
        "status": status,
        "reason": clean_text(filt.get("reason")) or clean_text(stock.get("reason")),
        "source": clean_text(filt.get("source")) or clean_text(stock.get("source")),
    }


def theme_stock_theme_text(stock: dict[str, Any]) -> str | None:
    themes = stock.get("source_themes")
    if isinstance(themes, list):
        parts = []
        for item in themes:
            if isinstance(item, dict):
                name = clean_text(item.get("name") or item.get("theme"))
                score_value = item.get("score")
                score_num = parse_float(score_value)
                if name and score_num is not None:
                    parts.append(f"{name}({format_num(score_num)})")
                elif name:
                    parts.append(name)
            else:
                text = clean_text(item)
                if text:
                    parts.append(text)
        return ", ".join(parts) if parts else None
    return clean_text(themes)


def observation_pool_from_theme_stocks(theme_doc: dict[str, Any], candidate_codes: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for stock in theme_doc.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        code = clean_text(stock.get("code"))
        if not code or code in seen or code in candidate_codes:
            continue
        filt = theme_stock_filter(stock)
        if filt["status"] != "observation":
            continue
        risk_flags = technical_value(stock, None, "risk_flags")
        risk_text = ", ".join(str(item) for item in risk_flags) if isinstance(risk_flags, list) else clean_text(risk_flags)
        anomaly = "; ".join(part for part in (filt["reason"], risk_text) if part)
        result.append(
            {
                "code": code,
                "name": clean_text(stock.get("name")) or code,
                "composite": parse_float(stock.get("best_score") or stock.get("composite")),
                "theme": theme_stock_theme_text(stock),
                "reason": filt["reason"] or "observation",
                "anomaly": anomaly or None,
            }
        )
        seen.add(code)
    return result


def excluded_stocks_from_theme_stocks(theme_doc: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_item(item: dict[str, Any], default_source: str) -> None:
        code = clean_text(item.get("code"))
        if not code or code in seen:
            return
        result.append(
            {
                "code": code,
                "name": clean_text(item.get("name")) or code,
                "reason": clean_text(item.get("reason")) or clean_text((item.get("filter") or {}).get("reason") if isinstance(item.get("filter"), dict) else None),
                "source": clean_text(item.get("source")) or clean_text((item.get("filter") or {}).get("source") if isinstance(item.get("filter"), dict) else None) or default_source,
            }
        )
        seen.add(code)

    for item in theme_doc.get("removed_stocks", []):
        if isinstance(item, dict):
            append_item(item, "removed")
    for item in theme_doc.get("board_excluded", []):
        if isinstance(item, dict):
            append_item(item, "board-policy")
    for stock in theme_doc.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        filt = theme_stock_filter(stock)
        if filt["status"] == "removed":
            append_item(
                {
                    "code": stock.get("code"),
                    "name": stock.get("name"),
                    "reason": filt["reason"],
                    "source": filt["source"],
                },
                "removed",
            )
    return result


def source_flags_from_value(value: Any) -> dict[str, bool]:
    if isinstance(value, dict):
        return {
            "candidate": bool(value.get("candidate", value.get("theme_library", False))),
            "market": bool(value.get("market", value.get("mkt", False))),
            "news": bool(value.get("news", value.get("news_direct", False))),
            "lhb": bool(value.get("lhb", False)),
        }
    text = clean_text(value) or ""
    lowered = text.lower()
    return {
        "candidate": "candidate" in lowered or "pure" in lowered,
        "market": "market" in lowered or "mkt" in lowered,
        "news": "news" in lowered or "✓" in text,
        "lhb": "lhb" in lowered,
    }


def merge_source_flags(base: Any, override: Any) -> dict[str, bool]:
    result = source_flags_from_value(base)
    extra = source_flags_from_value(override)
    for key, value in extra.items():
        result[key] = bool(result.get(key) or value)
    return result


def technical_from_pool_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "tech_score": parse_float(computed_value(entry, "tech_score")),
        "amount": parse_float(raw_value(entry, "amount")),
        "atr_pct": parse_float(raw_value(entry, "atr_pct")),
        "risk_type": computed_value(entry, "risk_type") or [],
        "risk_flags": computed_value(entry, "risk_flags") or [],
        "fetch_failed": bool(entry.get("fetch_failed")) if entry else True,
    }


def deterministic_filter_from_technical(technical: dict[str, Any]) -> dict[str, Any]:
    if technical.get("fetch_failed"):
        return {"status": "removed", "reason": "fetch_failed", "source": "indicators-fetch-failed"}
    amount = parse_float(technical.get("amount"))
    atr_pct = parse_float(technical.get("atr_pct"))
    hard_reasons = []
    if amount is not None and amount < 30000:
        hard_reasons.append(f"amount={format_num(amount)} < 30000")
    if atr_pct is not None and atr_pct > 8:
        hard_reasons.append(f"atr_pct={format_num(atr_pct, percent=True)} > 8%")
    if hard_reasons:
        return {"status": "removed", "reason": ", ".join(hard_reasons), "source": "hard-filter"}
    tech_score = parse_float(technical.get("tech_score"))
    if tech_score is None:
        return {"status": "observation", "reason": "IndicatorsMissing", "source": "soft-filter"}
    if tech_score < 50:
        return {"status": "observation", "reason": f"tech_score={format_num(tech_score)} < 50", "source": "soft-filter"}
    return {"status": "candidate", "reason": None, "source": None}


def publish_theme_stocks(base_doc: dict[str, Any], date: str) -> dict[str, Any]:
    """Publish the deterministic theme-stock contract without an LLM overlay."""
    if base_doc.get("schema_version") != "daily_theme_stocks_base.v2":
        raise ValueError(
            "theme stock base schema_version must be daily_theme_stocks_base.v2"
        )
    doc = json.loads(json.dumps(base_doc, ensure_ascii=False))
    doc["schema_version"] = "daily_theme_stocks.v2"
    doc["date"] = date
    doc["generated_at"] = utc_now_iso()
    doc["generation_mode"] = "deterministic_base_publish"
    return doc


def role_tags_from_theme_stock(stock: dict[str, Any] | None) -> list[str]:
    if not isinstance(stock, dict):
        return []
    flags = source_flags_from_value(stock.get("source_flags"))
    tags = []
    if flags.get("candidate"):
        tags.append("ThemeLibrary")
    if flags.get("market"):
        tags.append("MarketActive")
    if flags.get("news"):
        tags.append("NewsDirect")
    if flags.get("lhb"):
        tags.append("LHB")
    source_themes = stock.get("source_themes") if isinstance(stock.get("source_themes"), list) else []
    if len(source_themes) >= 2:
        tags.append("MultiTheme")
    if any(isinstance(item, dict) and item.get("anchor") for item in source_themes):
        tags.append("Anchor")
    return tags


def theme_heat_from_theme_stock(stock: dict[str, Any] | None, theme_heat_by_name: dict[str, float]) -> tuple[float | None, str]:
    if not isinstance(stock, dict):
        return None, "theme_stocks.json unavailable"
    candidates: list[float] = []
    for item in stock.get("source_themes", []):
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"))
        if name and name in theme_heat_by_name:
            candidates.append(theme_heat_by_name[name])
        else:
            value = parse_float(item.get("score"))
            if value is not None:
                candidates.append(value)
    if not candidates:
        value = parse_float(stock.get("best_score"))
        return value, "theme_stocks.json best_score" if value is not None else "theme_stocks.json missing theme heat"
    return max(candidates), "theme_stocks.json source_themes"


def deterministic_pattern(
    stock: dict[str, Any],
    pool_entry: dict[str, Any] | None,
    theme_heat: float | None,
) -> dict[str, dict[str, Any]]:
    """Build script-owned Pattern defaults only from available structured inputs."""
    amount = parse_float(technical_value(stock, pool_entry, "amount"))
    if amount is None:
        volume = pattern_state(None)
        volume["trace"] = "amount unavailable"
    elif amount >= 80000:
        volume = {"state": "SURGE", "confidence": 100, "trace": f"amount={format_num(amount)} >= 80000"}
    elif amount >= 30000:
        volume = {"state": "NORMAL", "confidence": 100, "trace": f"30000 <= amount={format_num(amount)} < 80000"}
    else:
        volume = {"state": "DRY", "confidence": 100, "trace": f"amount={format_num(amount)} < 30000"}

    source_themes = stock.get("source_themes") if isinstance(stock.get("source_themes"), list) else []
    is_anchor = any(isinstance(item, dict) and item.get("anchor") for item in source_themes)
    streak = parse_int(raw_value(pool_entry, "board_streak")) or 0
    seal_raw = raw_value(pool_entry, "seal_quality")
    seal = parse_float(seal_raw)
    seal_stable = clean_text(seal_raw) in {"封死", "sealed", "stable"} or (seal is not None and seal >= 70)
    if is_anchor or streak >= 2 or seal_stable:
        leader = {"state": "STABLE", "confidence": 90, "trace": f"anchor={is_anchor}; board_streak={streak}; seal_quality={seal_raw}"}
    elif streak == 1:
        leader = {"state": "DIVERGENCE", "confidence": 70, "trace": "single board streak without stable leader confirmation"}
    else:
        leader = {"state": "ABSENT", "confidence": 80, "trace": "no anchor, board streak, or seal confirmation"}

    theme_count = len([item for item in source_themes if isinstance(item, dict)])
    rotation = {
        "state": "PRIMARY" if is_anchor else ("SECONDARY" if theme_count >= 2 else "TERTIARY"),
        "confidence": 85,
        "trace": f"anchor={is_anchor}; source_theme_count={theme_count}",
    }

    auction_value = raw_value(pool_entry, "auction_change_pct")
    if auction_value is None:
        auction = {"state": "UNKNOWN", "confidence": 0, "trace": "real auction input unavailable"}
    else:
        change = parse_float(auction_value)
        state = "LEADING" if change is not None and change >= 2 else "LAGGING" if change is not None and change <= -1 else "NEUTRAL"
        auction = {"state": state, "confidence": 100, "trace": f"auction_change_pct={format_num(change, percent=True)}"}

    if theme_heat is None:
        heat = {"state": "UNKNOWN", "confidence": 0, "trace": "comparable theme heat unavailable"}
    else:
        heat = {"state": "STABLE", "confidence": 50, "trace": f"single-day theme_heat={format_num(theme_heat)}; no comparable prior heat"}
    return {"heat": heat, "leader": leader, "auction": auction, "rotation": rotation, "volume": volume}


def build_deterministic_mapper_base(
    date: str,
    pool: dict[str, dict[str, Any]],
    theme_stocks_doc: dict[str, Any],
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if theme_stocks_doc.get("schema_version") != "daily_theme_stocks.v2":
        raise ValueError(
            "theme_stocks schema_version must be daily_theme_stocks.v2"
        )
    projection_errors = [
        error
        for index, theme in enumerate(theme_stocks_doc.get("themes", []))
        for error in theme_projection_errors(theme, f"themes[{index}]")
    ]
    if projection_errors:
        raise ValueError(
            "invalid theme projection:\n"
            + "\n".join(f"  - {error}" for error in projection_errors)
        )
    theme_stock_by_code: dict[str, dict[str, Any]] = {}
    theme_heat_by_name: dict[str, float] = {}
    for theme in theme_stocks_doc.get("themes", []):
        if not isinstance(theme, dict):
            continue
        name = clean_text(theme.get("name"))
        heat = parse_float(theme.get("final_heat"))
        if name and heat is not None:
            theme_heat_by_name[name] = heat
    for stock in theme_stocks_doc.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        code = clean_text(stock.get("code"))
        if code:
            theme_stock_by_code[code] = stock

    themes = []
    for i, item in enumerate(theme_stocks_doc.get("themes", []), start=1):
        if not isinstance(item, dict) or not item.get("name"):
            continue
        themes.append(
            {
                "name": item.get("name"),
                "rank": parse_int(item.get("rank")) or i,
                "final_heat": parse_float(item.get("final_heat")),
                "attention_direction": clean_text(
                    item.get("attention_direction")
                ),
                "evidence_refs": list(item.get("evidence_refs") or []),
            }
        )

    candidates = []
    for theme_stock in theme_stocks_doc.get("stocks", []):
        if not isinstance(theme_stock, dict):
            continue
        code = clean_text(theme_stock.get("code"))
        if not code or not CODE_RE.fullmatch(code):
            continue
        status = theme_stock_filter(theme_stock)["status"]
        if status != "candidate":
            continue
        entry = pool.get(code)
        tech = computed_value(entry, "tech_score")
        risk = computed_value(entry, "risk_type")
        theme_heat, theme_heat_trace = theme_heat_from_theme_stock(theme_stock, theme_heat_by_name)
        candidates.append(
            {
                "code": code,
                "name": clean_text(theme_stock.get("name")) or code,
                "role_tags": role_tags_from_theme_stock(theme_stock),
                "scores": {
                    "composite": score(0, 0, "recomputed after annotation merge"),
                    "tech": score(tech, 100 if tech is not None else 0, "pool_indicators"),
                    "theme_heat": score(theme_heat if theme_heat is not None else 50, 100 if theme_heat is not None else 50, theme_heat_trace),
                    "news_impact": score(None, 0, "filled from annotations"),
                    "auction": score(50, 100, "base default"),
                    "money_flow": score(50, 50, "base default"),
                },
                "major_event": {"polarity": "none", "confidence": 100, "trace": "no named company-level event in sparse annotation"},
                "risk_type": {"value": risk if isinstance(risk, list) else [], "confidence": 100 if risk is not None else 0},
                "pattern": deterministic_pattern(theme_stock, entry, theme_heat),
                "anomaly": None,
                "news_link": clean_text(theme_stock.get("news_ref")) or None,
                "strategy_inputs": strategy_inputs_from_pool(code, pool),
            }
        )

    candidate_codes = {item["code"] for item in candidates}
    observation_pool = observation_pool_from_theme_stocks(theme_stocks_doc, candidate_codes)
    excluded_stocks = excluded_stocks_from_theme_stocks(theme_stocks_doc)

    resolved_scope = scope or load_trading_scope()

    return {
        "schema_version": "daily_mapper_base.v2",
        "date": date,
        "generated_at": utc_now_iso(),
        "generation_mode": "deterministic_theme_stock_base",
        "market_state": {
            "dominant_themes": [
                {
                    "name": item["name"],
                    "final_heat": item.get("final_heat"),
                }
                for item in themes[:3]
            ],
            "financing_flow": None,
            "risk_flags": [],
            "board_policy": board_policy_from_scope(resolved_scope),
        },
        "themes": themes,
        "candidate_pool": candidates,
        "observation_pool": observation_pool,
        "excluded_stocks": excluded_stocks,
    }


def normalize_base_doc(base: dict[str, Any], date: str) -> dict[str, Any]:
    if base.get("schema_version") != "daily_mapper_base.v2":
        raise ValueError("mapper base schema_version must be daily_mapper_base.v2")
    doc = dict(base)
    doc["schema_version"] = "daily_mapper.v2"
    doc["date"] = date
    doc["generated_at"] = utc_now_iso()
    doc["generation_mode"] = "annotations_merge"
    return doc


def calculate_news_impact(news_relevance: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = fallback or {}
    if not isinstance(news_relevance, dict):
        return dict(fallback)
    r = clean_text(news_relevance.get("r"))
    p = clean_text(news_relevance.get("p"))
    value = NEWS_IMPACT_MATRIX.get((r or "", p or ""))
    if value is None:
        value = parse_float(news_relevance.get("value", fallback.get("value")))
    confidence = parse_int(news_relevance.get("confidence", fallback.get("confidence", 0))) or 0
    trace_parts = []
    if r or p:
        trace_parts.append(f"{r or 'R?'}x{p or 'P?'}")
    trace = clean_text(news_relevance.get("trace")) or clean_text(fallback.get("trace"))
    if trace:
        trace_parts.append(trace)
    evidence = clean_text(news_relevance.get("evidence")) or clean_text(fallback.get("evidence"))
    return {
        "value": value,
        "confidence": confidence,
        "trace": "; ".join(trace_parts) if trace_parts else evidence or "annotation",
        "evidence": evidence,
    }


def merge_pattern(base_pattern: dict[str, Any], annotation_pattern: Any) -> dict[str, Any]:
    result = dict(base_pattern or {})
    if not isinstance(annotation_pattern, dict):
        return result
    for key in ("heat", "leader", "auction", "rotation", "volume"):
        item = annotation_pattern.get(key)
        if not isinstance(item, dict):
            continue
        existing = result.get(key, {})
        result[key] = {
            "state": clean_text(item.get("state")) or existing.get("state") or "UNKNOWN",
            "confidence": parse_int(item.get("confidence", existing.get("confidence", 0))) or 0,
            "trace": clean_text(item.get("trace", existing.get("trace"))),
            "evidence": clean_text(item.get("evidence", existing.get("evidence"))),
        }
    return result


def recalculate_composite(scores: dict[str, Any]) -> None:
    weights = {
        "theme_heat": 0.30,
        "news_impact": 0.20,
        "auction": 0.20,
        "tech": 0.20,
        "money_flow": 0.10,
    }
    total = 0.0
    missing = []
    confidences = []
    for key, weight in weights.items():
        item = scores.get(key, {})
        value = parse_float(item.get("value") if isinstance(item, dict) else None)
        if value is None:
            missing.append(key)
            value = 0.0
        else:
            conf = parse_int(item.get("confidence") if isinstance(item, dict) else None)
            if conf is not None:
                confidences.append(conf)
        total += value * weight
    scores["composite"] = {
        "value": round(total, 1),
        "confidence": min(confidences) if confidences else 0,
        "trace": "T*0.30+N*0.20+A*0.20+Tech*0.20+MF*0.10" + (f"; missing={','.join(missing)}" if missing else ""),
    }


def merge_annotations(base: dict[str, Any], annotations: dict[str, Any], date: str) -> dict[str, Any]:
    doc = normalize_base_doc(base, date)
    doc["annotation_schema_version"] = annotations.get("schema_version")

    stock_annotations = {
        item.get("code"): item
        for item in annotations.get("stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    for stock in doc.get("candidate_pool", []):
        code = stock.get("code")
        ann = stock_annotations.get(code)
        if not ann:
            continue
        scores = stock.setdefault("scores", {})
        scores["news_impact"] = calculate_news_impact(ann.get("news_relevance"), scores.get("news_impact"))

        major = ann.get("major_event")
        if isinstance(major, dict):
            stock["major_event"] = {
                "polarity": normalize_major_event(major.get("polarity")),
                "confidence": parse_int(major.get("confidence", 90)) or 90,
                "evidence": clean_text(major.get("evidence")),
                "trace": clean_text(major.get("trace")),
            }

        stock["pattern"] = merge_pattern(stock.get("pattern", {}), ann.get("pattern"))
        if "anomaly" in ann:
            stock["anomaly"] = clean_text(ann.get("anomaly"))
        if clean_text(ann.get("news_link")):
            stock["news_link"] = clean_text(ann.get("news_link"))
        elif isinstance(ann.get("news_relevance"), dict) and clean_text(ann["news_relevance"].get("evidence")):
            stock["news_link"] = clean_text(ann["news_relevance"].get("evidence"))

        recalculate_composite(scores)

    candidate_codes = {stock.get("code") for stock in doc.get("candidate_pool", []) if isinstance(stock, dict)}
    for code in stock_annotations:
        if code not in candidate_codes:
            print(f"[WARN] mapper.annotations stock {code} is not a deterministic candidate; skipping", file=sys.stderr)

    doc["candidate_pool"] = sorted(
        doc.get("candidate_pool", []),
        key=lambda item: parse_float(item.get("scores", {}).get("composite", {}).get("value")) or -1,
        reverse=True,
    )
    return doc


def numbers_match(value: Any, source: Any, tolerance: float = NUMERIC_TOLERANCE) -> bool:
    left = parse_float(value)
    right = parse_float(source)
    if right is None:
        return left is None
    if left is None:
        return False
    return abs(left - right) <= max(abs(right) * tolerance, 0.02)
