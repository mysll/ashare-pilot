#!/usr/bin/env python3
"""Helpers for the daily mapper JSON contract.

Normal flow is annotations/base JSON -> mapper.json -> rendered mapper.md.
Legacy Markdown parsing remains available only for old dates.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODE_RE = re.compile(r"\b(?:[a-z]{2}\d{6}|[a-z]{2,4}_[a-z0-9]+)\b", re.IGNORECASE)
MISSING_VALUES = {"", "-", "--", "None", "none", "null", "N/A", "鈥?", "鈥擿", "—"}
NUMERIC_TOLERANCE = 0.005
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
    return Path(__file__).resolve().parents[4]


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
    return workspace_root() / ".opencode" / "config" / "trading-scope.json"


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


def extract_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_match = re.search(r"(?m)^##\s+", text[start + len(marker) :])
    end = len(text) if next_match is None else start + len(marker) + next_match.start()
    return text[start:end]


def parse_markdown_table(section: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells:
            continue
        if header is None:
            header = cells
            continue
        if all(set(cell.replace(":", "").strip()) <= {"-"} for cell in cells):
            continue
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        rows.append({header[i]: cells[i] for i in range(len(header))})
    return rows


def parse_market_state(mapper_text: str) -> dict[str, Any]:
    rows = parse_markdown_table(extract_section(mapper_text, "Market State"))
    state: dict[str, Any] = {
        "dominant_themes": [],
        "financing_flow": None,
        "risk_flags": [],
        "board_policy": {},
    }
    for row in rows:
        field = row.get("Field")
        value = clean_text(row.get("Value"))
        if field == "DominantThemes" and value:
            state["dominant_themes"] = parse_dominant_themes(value)
        elif field == "FinancingFlow":
            state["financing_flow"] = value
        elif field == "RiskFlags" and value:
            state["risk_flags"] = [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
        elif field == "BoardPolicy" and value:
            state["board_policy"] = parse_board_policy(value)
    return state


def parse_dominant_themes(value: str) -> list[dict[str, Any]]:
    themes: list[dict[str, Any]] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"(.+?)\(([-+]?\d+(?:\.\d+)?)\)$", part)
        if match:
            themes.append({"name": match.group(1).strip(), "heat": parse_float(match.group(2))})
        else:
            themes.append({"name": part, "heat": None})
    return themes


def parse_board_policy(value: str) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    for part in value.split(","):
        if "=" not in part:
            continue
        key, raw = [x.strip() for x in part.split("=", 1)]
        policy[key] = raw
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


def parse_themes(mapper_text: str) -> list[dict[str, Any]]:
    rows = parse_markdown_table(extract_section(mapper_text, "Theme Ranking"))
    themes: list[dict[str, Any]] = []
    for row in rows:
        name = clean_text(row.get("Theme"))
        if not name:
            continue
        themes.append(
            {
                "name": name,
                "rank": parse_int(row.get("Rank")),
                "final_heat": parse_float(row.get("Final")),
                "heat_trace": clean_text(row.get("HeatTrace")),
            }
        )
    return themes


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


def parse_candidate_pool(mapper_text: str, pool: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = parse_markdown_table(extract_section(mapper_text, "Candidate Pool"))
    candidates: list[dict[str, Any]] = []
    for row in rows:
        code = clean_text(row.get("Code"))
        if not code or not CODE_RE.fullmatch(code):
            continue
        news_link = clean_text(row.get("NewsLink"))
        candidates.append(
            {
                "code": code,
                "name": clean_text(row.get("Name")),
                "role_tags": parse_list_cell(row.get("RoleTags")),
                "scores": {
                    "composite": score(row.get("comp.value"), row.get("comp.conf")),
                    "tech": score(row.get("tech.value"), row.get("tech.conf")),
                    "theme_heat": score(row.get("th_heat.value")),
                    "news_impact": score(row.get("news_imp.value"), None, news_link or "phase 1 mapper bridge"),
                    "auction": score(row.get("auc.value"), 100, "from mapper phase 1 bridge"),
                    "money_flow": score(50, 50, "phase 1 default"),
                },
                "major_event": {
                    "polarity": normalize_major_event(row.get("maj_ev.pol")),
                    "confidence": 90,
                    "evidence": news_link,
                },
                "risk_type": {
                    "value": parse_list_cell(row.get("risk_type.value")) or parse_list_cell(computed_value(pool.get(code), "risk_type")),
                    "confidence": 100,
                },
                "pattern": {
                    "heat": pattern_state(row.get("pattern.heat")),
                    "leader": pattern_state(row.get("pattern.leader")),
                    "auction": pattern_state(row.get("pattern.auct")),
                    "rotation": pattern_state(row.get("pattern.rotation")),
                    "volume": pattern_state(row.get("pattern.volume")),
                },
                "anomaly": clean_text(row.get("anomaly")),
                "news_link": news_link,
                "strategy_inputs": strategy_inputs_from_pool(code, pool),
            }
        )
    return candidates


def normalize_major_event(value: Any) -> str:
    text = (clean_text(value) or "none").lower()
    if text in {"positive", "negative", "none", "unknown"}:
        return text
    return "none"


def pattern_state(value: Any) -> dict[str, Any]:
    text = clean_text(value)
    return {"state": text or "UNKNOWN", "confidence": 80 if text else 0, "trace": None}


def parse_observation_pool(mapper_text: str) -> list[dict[str, Any]]:
    rows = parse_markdown_table(extract_section(mapper_text, "Observation Pool"))
    result: list[dict[str, Any]] = []
    for row in rows:
        code = clean_text(row.get("Code"))
        if code and CODE_RE.fullmatch(code):
            result.append(
                {
                    "code": code,
                    "name": clean_text(row.get("Name")),
                    "composite": parse_float(row.get("Composite")),
                    "theme": clean_text(row.get("Theme")),
                    "reason": clean_text(row.get("Reason")),
                    "anomaly": clean_text(row.get("Anomaly")),
                }
            )
    return result


def parse_excluded_stocks(mapper_text: str) -> list[dict[str, Any]]:
    rows = parse_markdown_table(extract_section(mapper_text, "Excluded Stocks"))
    result: list[dict[str, Any]] = []
    for row in rows:
        code = clean_text(row.get("Code"))
        if code and CODE_RE.fullmatch(code):
            result.append(
                {
                    "code": code,
                    "name": clean_text(row.get("Name")),
                    "reason": clean_text(row.get("ExclusionReason")),
                    "source": clean_text(row.get("ExclusionSource")),
                }
            )
    return result


def extract_removed_stocks_section(theme_stocks_text: str) -> str:
    marker = "**Removed stocks (failed hard filters):**"
    start = theme_stocks_text.find(marker)
    if start < 0:
        return ""
    next_heading = re.search(r"(?m)^##\s+", theme_stocks_text[start + len(marker) :])
    end = len(theme_stocks_text) if next_heading is None else start + len(marker) + next_heading.start()
    return theme_stocks_text[start:end]


def validate_theme_stocks_markdown_contract(theme_stocks_text: str, label: str = "theme_stocks.md") -> None:
    if not extract_section(theme_stocks_text, "Stock Pool (After Technical Enrichment)"):
        raise ValueError(f"{label} missing required section: ## Stock Pool (After Technical Enrichment)")
    if "**Removed stocks (failed hard filters):**" not in theme_stocks_text:
        raise ValueError(f"{label} missing required section: **Removed stocks (failed hard filters):**")


def parse_theme_observation_pool(theme_stocks_text: str, candidate_codes: set[str]) -> list[dict[str, Any]]:
    rows = parse_markdown_table(extract_section(theme_stocks_text, "Stock Pool (After Technical Enrichment)"))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        code = clean_text(row.get("Code"))
        if not code or not CODE_RE.fullmatch(code) or code in candidate_codes or code in seen:
            continue
        risk = clean_text(row.get("Risk?"))
        if not risk or risk.lower() == "no":
            continue
        result.append(
            {
                "code": code,
                "name": clean_text(row.get("Name")),
                "composite": parse_float(row.get("Best Score")),
                "theme": clean_text(row.get("Source Themes")),
                "reason": risk,
                "anomaly": None,
            }
        )
        seen.add(code)
    return result


def parse_theme_excluded_stocks(theme_stocks_text: str) -> list[dict[str, Any]]:
    rows = parse_markdown_table(extract_removed_stocks_section(theme_stocks_text))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        code = clean_text(row.get("Code"))
        if not code or not CODE_RE.fullmatch(code) or code in seen:
            continue
        result.append(
            {
                "code": code,
                "name": clean_text(row.get("Name")),
                "reason": clean_text(row.get("Reason")),
                "source": clean_text(row.get("ExclusionSource")),
            }
        )
        seen.add(code)
    return result


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
        result.append(
            {
                "code": code,
                "name": clean_text(stock.get("name")) or code,
                "composite": parse_float(stock.get("best_score") or stock.get("composite")),
                "theme": theme_stock_theme_text(stock),
                "reason": filt["reason"] or "observation",
                "anomaly": clean_text(stock.get("anomaly")),
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


def merge_theme_stock_annotations(base_doc: dict[str, Any], annotations: dict[str, Any], date: str) -> dict[str, Any]:
    doc = json.loads(json.dumps(base_doc, ensure_ascii=False))
    doc["schema_version"] = "daily_theme_stocks.v1"
    doc["date"] = date
    doc["generated_at"] = utc_now_iso()
    doc["generation_mode"] = "base_annotations_merge"
    doc["annotation_schema_version"] = annotations.get("schema_version")

    theme_annotations = {
        item.get("name"): item
        for item in annotations.get("themes", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    for theme in doc.get("themes", []):
        if not isinstance(theme, dict):
            continue
        ann = theme_annotations.get(theme.get("name"))
        if not ann:
            continue
        if clean_text(ann.get("note")):
            theme["note"] = clean_text(ann.get("note"))
        if clean_text(ann.get("evidence")):
            theme["evidence"] = clean_text(ann.get("evidence"))

    stock_annotations = {
        item.get("code"): item
        for item in annotations.get("stocks", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    for stock in doc.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        ann = stock_annotations.get(stock.get("code"))
        if not ann:
            continue
        if "source_flags" in ann:
            stock["source_flags"] = merge_source_flags(stock.get("source_flags"), ann.get("source_flags"))
        for key in ("news_ref", "market_ref", "anomaly", "source_explanation", "note"):
            if key in ann:
                stock[key] = clean_text(ann.get(key))
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


def build_mapper_from_markdown(date: str, mapper_text: str, pool: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "daily_mapper.v1",
        "date": date,
        "generated_at": utc_now_iso(),
        "generation_mode": "phase1_markdown_bridge",
        "market_state": parse_market_state(mapper_text),
        "themes": parse_themes(mapper_text),
        "candidate_pool": parse_candidate_pool(mapper_text, pool),
        "observation_pool": parse_observation_pool(mapper_text),
        "excluded_stocks": parse_excluded_stocks(mapper_text),
    }


def build_base_from_annotations(
    date: str,
    annotations: dict[str, Any],
    pool: dict[str, dict[str, Any]],
    theme_stocks_text: str | None = None,
    theme_stocks_doc: dict[str, Any] | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    theme_stock_by_code: dict[str, dict[str, Any]] = {}
    theme_heat_by_name: dict[str, float] = {}
    if theme_stocks_doc is not None:
        for theme in theme_stocks_doc.get("themes", []):
            if not isinstance(theme, dict):
                continue
            name = clean_text(theme.get("name"))
            heat = parse_float(theme.get("heat"))
            if name and heat is not None:
                theme_heat_by_name[name] = heat
        for stock in theme_stocks_doc.get("stocks", []):
            if not isinstance(stock, dict):
                continue
            code = clean_text(stock.get("code"))
            if code:
                theme_stock_by_code[code] = stock

    themes = []
    for i, item in enumerate(annotations.get("themes", []), start=1):
        if not isinstance(item, dict) or not item.get("name"):
            continue
        themes.append(
            {
                "name": item.get("name"),
                "rank": i,
                "final_heat": parse_float(annotation_value(item.get("emotion"), "value")) or 50,
                "heat_trace": "from mapper.annotations.json",
            }
        )

    candidates = []
    for item in annotations.get("stocks", []):
        if not isinstance(item, dict):
            continue
        code = clean_text(item.get("code"))
        if not code or not CODE_RE.fullmatch(code):
            continue
        if theme_stocks_doc is not None:
            theme_stock = theme_stock_by_code.get(code)
            if theme_stock is None:
                raise ValueError(f"mapper.annotations stock {code} missing from theme_stocks.json stocks[]")
            status = theme_stock_filter(theme_stock)["status"]
            if status != "candidate":
                raise ValueError(f"mapper.annotations stock {code} has theme_stocks.json filter.status={status!r}, expected 'candidate'")
        else:
            theme_stock = None
        entry = pool.get(code)
        tech = computed_value(entry, "tech_score")
        risk = computed_value(entry, "risk_type")
        theme_heat, theme_heat_trace = theme_heat_from_theme_stock(theme_stock, theme_heat_by_name)
        candidates.append(
            {
                "code": code,
                "name": clean_text(item.get("name")) or clean_text(theme_stock.get("name") if isinstance(theme_stock, dict) else None) or code,
                "role_tags": role_tags_from_theme_stock(theme_stock),
                "scores": {
                    "composite": score(0, 0, "recomputed after annotation merge"),
                    "tech": score(tech, 100 if tech is not None else 0, "pool_indicators"),
                    "theme_heat": score(theme_heat if theme_heat is not None else 50, 100 if theme_heat is not None else 50, theme_heat_trace),
                    "news_impact": score(None, 0, "filled from annotations"),
                    "auction": score(50, 100, "base default"),
                    "money_flow": score(50, 50, "base default"),
                },
                "major_event": {"polarity": "unknown", "confidence": 0, "trace": "filled from annotations"},
                "risk_type": {"value": risk if isinstance(risk, list) else [], "confidence": 100 if risk is not None else 0},
                "pattern": {
                    "heat": pattern_state(None),
                    "leader": pattern_state(None),
                    "auction": pattern_state(None),
                    "rotation": pattern_state(None),
                    "volume": pattern_state(None),
                },
                "anomaly": None,
                "news_link": None,
                "strategy_inputs": strategy_inputs_from_pool(code, pool),
            }
        )

    candidate_codes = {item["code"] for item in candidates}
    if theme_stocks_doc is not None:
        observation_pool = observation_pool_from_theme_stocks(theme_stocks_doc, candidate_codes)
        excluded_stocks = excluded_stocks_from_theme_stocks(theme_stocks_doc)
    elif theme_stocks_text:
        validate_theme_stocks_markdown_contract(theme_stocks_text)
        observation_pool = parse_theme_observation_pool(theme_stocks_text, candidate_codes)
        excluded_stocks = parse_theme_excluded_stocks(theme_stocks_text)
    else:
        observation_pool = []
        excluded_stocks = []

    resolved_scope = scope or load_trading_scope()

    return {
        "schema_version": "daily_mapper_base.v1",
        "date": date,
        "generated_at": utc_now_iso(),
        "generation_mode": "annotations_base",
        "market_state": {
            "dominant_themes": [{"name": item["name"], "heat": item.get("final_heat")} for item in themes[:3]],
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
    doc = dict(base)
    doc["schema_version"] = "daily_mapper.v1"
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

    theme_annotations = {
        item.get("name"): item
        for item in annotations.get("themes", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    for theme in doc.get("themes", []):
        ann = theme_annotations.get(theme.get("name"))
        if not ann:
            continue
        theme["emotion"] = scored_annotation(ann.get("emotion"))
        theme["policy_polarity"] = ann.get("policy_polarity")
        theme["catalyst_exception"] = ann.get("catalyst_exception")

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
