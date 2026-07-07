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


CODE_RE = re.compile(r"\b(?:sh|sz)\d{6}\b")
MISSING_VALUES = {"", "-", "--", "None", "none", "null", "N/A", "鈥?", "鈥擿", "—"}
NUMERIC_TOLERANCE = 0.005
NEWS_IMPACT_MATRIX = {
    ("R4", "P3"): 95,
    ("R4", "P2"): 85,
    ("R4", "P1"): 70,
    ("R3", "P3"): 80,
    ("R3", "P2"): 70,
    ("R3", "P1"): 55,
    ("R2", "P3"): 65,
    ("R2", "P2"): 55,
    ("R2", "P1"): 40,
    ("R1", "P3"): 45,
    ("R1", "P2"): 35,
    ("R1", "P1"): 25,
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
) -> dict[str, Any]:
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
        entry = pool.get(code)
        tech = computed_value(entry, "tech_score")
        risk = computed_value(entry, "risk_type")
        candidates.append(
            {
                "code": code,
                "name": clean_text(item.get("name")) or code,
                "role_tags": [],
                "scores": {
                    "composite": score(0, 0, "recomputed after annotation merge"),
                    "tech": score(tech, 100 if tech is not None else 0, "pool_indicators"),
                    "theme_heat": score(50, 50, "base default; refine upstream when themes.json exists"),
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
    observation_pool = parse_theme_observation_pool(theme_stocks_text, candidate_codes) if theme_stocks_text else []
    excluded_stocks = parse_theme_excluded_stocks(theme_stocks_text) if theme_stocks_text else []

    return {
        "schema_version": "daily_mapper_base.v1",
        "date": date,
        "generated_at": utc_now_iso(),
        "generation_mode": "annotations_base",
        "market_state": {
            "dominant_themes": [{"name": item["name"], "heat": item.get("final_heat")} for item in themes[:3]],
            "financing_flow": None,
            "risk_flags": [],
            "board_policy": {"sh688": "exclude", "bj": "exclude"},
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
