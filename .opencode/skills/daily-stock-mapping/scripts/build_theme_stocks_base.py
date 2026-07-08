#!/usr/bin/env python3
"""Build deterministic predict/{date}/theme_stocks.base.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from mapper_json_lib import (
    CODE_RE,
    clean_text,
    default_predict_dir,
    deterministic_filter_from_technical,
    load_pool,
    load_trading_scope,
    parse_float,
    parse_markdown_table,
    read_json,
    scope_decision,
    source_flags_from_value,
    technical_from_pool_entry,
    utc_now_iso,
    write_json,
)


def extract_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_match = re.search(r"(?m)^##\s+", text[start + len(marker) :])
    end = len(text) if next_match is None else start + len(marker) + next_match.start()
    return text[start:end]


def parse_themes_summary(text: str) -> list[dict[str, Any]]:
    result = []
    for row in parse_markdown_table(extract_section(text, "Themes Summary")):
        name = clean_text(row.get("Theme"))
        if not name:
            continue
        result.append(
            {
                "name": name,
                "rank": int(parse_float(row.get("#")) or len(result) + 1),
                "heat": parse_float(row.get("Heat") or row.get("Final")),
                "confidence": parse_float(row.get("Confidence") or row.get("Conf")),
                "stock_count": clean_text(row.get("Stocks in Pool")),
            }
        )
    return result


def source_themes_from_row(row: dict[str, str], current_theme: str | None = None) -> list[dict[str, Any]]:
    raw = clean_text(row.get("Source Themes")) or clean_text(row.get("Theme")) or current_theme
    if not raw:
        return []
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    result = []
    for part in parts:
        match = re.match(r"(.+?)\(([-+]?\d+(?:\.\d+)?)\)$", part)
        if match:
            result.append({"name": match.group(1).strip(), "score": parse_float(match.group(2))})
        else:
            result.append({"name": part, "score": None})
    return result


def iter_stock_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    enriched = extract_section(text, "Stock Pool (After Technical Enrichment)")
    if enriched:
        for row in parse_markdown_table(enriched):
            rows.append({"row": row, "theme": None})
        return rows

    # Fallback for sectioned "Top Candidates per Theme" reports.
    current_theme: str | None = None
    section = extract_section(text, "Stock Pool (Deduplicated — Top Candidates per Theme)") or extract_section(
        text, "Stock Pool (Deduplicated - Top Candidates per Theme)"
    )
    if not section:
        section = extract_section(text, "Stock Pool (Deduplicated)")
    for line in section.splitlines():
        heading = re.match(r"^###\s+(.+?)(?:\s+[—-]\s+Top Candidates)?\s*$", line.strip())
        if heading:
            current_theme = heading.group(1).strip()
            continue
        if not line.strip().startswith("|"):
            continue
    # parse_markdown_table cannot keep per-subheading state, so do a small table scan.
    current_theme = None
    table_lines: list[str] = []
    for line in section.splitlines() + ["### END"]:
        heading = re.match(r"^###\s+(.+?)(?:\s+[—-]\s+Top Candidates)?\s*$", line.strip())
        if heading or line == "### END":
            for row in parse_markdown_table("\n".join(table_lines)):
                if clean_text(row.get("Code")):
                    rows.append({"row": row, "theme": current_theme})
            table_lines = []
            current_theme = heading.group(1).strip() if heading else None
            continue
        if line.strip().startswith("|"):
            table_lines.append(line)
    return rows


def extract_removed_stocks_section(text: str) -> str:
    marker = "**Removed stocks (failed hard filters):**"
    start = text.find(marker)
    if start < 0:
        return ""
    next_heading = re.search(r"(?m)^##\s+", text[start + len(marker) :])
    end = len(text) if next_heading is None else start + len(marker) + next_heading.start()
    return text[start:end]


def parse_removed_rows(text: str) -> list[dict[str, Any]]:
    result = []
    for row in parse_markdown_table(extract_removed_stocks_section(text)):
        code = clean_text(row.get("Code"))
        if not code or not CODE_RE.fullmatch(code):
            continue
        result.append(
            {
                "code": code,
                "name": clean_text(row.get("Name")) or code,
                "reason": clean_text(row.get("Reason")),
                "source": clean_text(row.get("ExclusionSource")) or "removed",
            }
        )
    return result


def theme_library_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "theme-library"


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*()]', "_", name)


def parse_theme_spec(spec: str) -> dict[str, Any]:
    raw = clean_text(spec)
    if not raw:
        raise ValueError("empty theme spec")
    parts = [part.strip() for part in re.split(r"[:|]", raw)]
    name = parts[0]
    if not name:
        raise ValueError(f"invalid theme spec: {spec!r}")
    return {
        "name": name,
        "heat": parse_float(parts[1]) if len(parts) > 1 else None,
        "confidence": parse_float(parts[2]) if len(parts) > 2 else None,
    }


def collect_theme_specs(theme_args: list[str] | None, themes_arg: str | None) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for item in theme_args or []:
        specs.append(parse_theme_spec(item))
    for item in (themes_arg or "").split(","):
        if item.strip():
            specs.append(parse_theme_spec(item))

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in specs:
        name = spec["name"]
        if name in seen:
            continue
        seen.add(name)
        spec["rank"] = len(result) + 1
        result.append(spec)
    return result


def load_theme(theme_name: str, library_dir: Path) -> dict[str, Any] | None:
    theme_path = library_dir / "themes" / f"{safe_filename(theme_name)}.json"
    if theme_path.exists():
        data = read_json(theme_path)
        if isinstance(data, dict):
            return data

    alias_path = library_dir / "aliases" / "theme_aliases.json"
    aliases = read_json(alias_path) if alias_path.exists() else {}
    if isinstance(aliases, dict):
        for canonical, names in aliases.items():
            if not isinstance(names, list):
                continue
            lowered = [str(item).lower() for item in names]
            if theme_name in names or theme_name.lower() in lowered:
                return load_theme(str(canonical), library_dir)
    return None


def load_stock_name(code: str, library_dir: Path) -> str | None:
    path = library_dir / "stocks" / f"{code.lower()}.json"
    if not path.exists():
        return None
    data = read_json(path)
    if isinstance(data, dict):
        return clean_text(data.get("name"))
    return None


def stock_score(item: dict[str, Any]) -> float | None:
    for key in ("candidate_score", "industry_score", "purity_score", "score"):
        score = parse_float(item.get(key))
        if score is not None:
            return score
    return None


def dedupe_by_code(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        code = clean_text(item.get("code"))
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(item)
    return result


def normalize_source_flags(value: Any, source: str | None = None) -> dict[str, bool]:
    flags = source_flags_from_value(value)
    source_text = clean_text(source) or ""
    if source_text in {"market", "market_active"}:
        flags["market"] = True
    if source_text in {"news", "news_direct", "news_mentioned"}:
        flags["news"] = True
    if source_text == "lhb":
        flags["lhb"] = True
    return flags


def load_extra_stocks(path: Path | None, date: str) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"extra stocks must be a JSON object: {path}")
    if data.get("date") not in {None, date}:
        raise ValueError(f"extra stocks date mismatch: expected {date}, got {data.get('date')}")
    stocks = data.get("stocks")
    if not isinstance(stocks, list):
        raise ValueError(f"extra stocks missing stocks[]: {path}")
    result: list[dict[str, Any]] = []
    for i, item in enumerate(stocks):
        if not isinstance(item, dict):
            raise ValueError(f"extra stocks[{i}] must be object")
        code = clean_text(item.get("code"))
        if not code or not CODE_RE.fullmatch(code):
            raise ValueError(f"extra stocks[{i}].code must be a trading code")
        result.append(item)
    return result


def merge_extra_stock(target: dict[str, Any], extra: dict[str, Any]) -> None:
    source = clean_text(extra.get("source")) or "extra"
    theme_names = extra.get("source_themes")
    if isinstance(theme_names, str):
        theme_names = [theme_names]
    if not isinstance(theme_names, list) or not theme_names:
        theme_names = [clean_text(extra.get("theme")) or source]
    existing = {item.get("name"): item for item in target.setdefault("source_themes", []) if isinstance(item, dict)}
    score_value = parse_float(extra.get("score") or extra.get("best_score"))
    for theme_name in theme_names:
        name = clean_text(theme_name)
        if not name:
            continue
        source_theme = {"name": name, "score": score_value, "source": source}
        if name not in existing:
            target["source_themes"].append(source_theme)
            existing[name] = source_theme
    if score_value is not None:
        best = parse_float(target.get("best_score"))
        if best is None or score_value > best:
            target["best_score"] = score_value
    flags = target.setdefault("source_flags", {"candidate": False, "market": False, "news": False, "lhb": False})
    for key, value in normalize_source_flags(extra.get("source_flags"), source).items():
        flags[key] = bool(flags.get(key) or value)
    for key in ("news_ref", "market_ref", "anomaly", "source_explanation", "note"):
        if clean_text(extra.get(key)):
            target[key] = clean_text(extra.get(key))


def universe_doc(
    date: str,
    themes: list[dict[str, Any]],
    stocks_by_code: dict[str, dict[str, Any]],
    board_excluded: list[dict[str, Any]],
    generation_notes: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "daily_theme_stocks_universe.v1",
        "date": date,
        "generated_at": utc_now_iso(),
        "themes": themes,
        "codes": sorted(stocks_by_code),
        "stocks": [
            {
                "code": stock.get("code"),
                "name": stock.get("name"),
                "source_themes": stock.get("source_themes", []),
                "source_flags": stock.get("source_flags", {}),
                "best_score": stock.get("best_score"),
                "news_ref": stock.get("news_ref"),
                "market_ref": stock.get("market_ref"),
                "anomaly": stock.get("anomaly"),
                "source_explanation": stock.get("source_explanation"),
                "note": stock.get("note"),
            }
            for stock in sorted(stocks_by_code.values(), key=lambda item: item.get("code") or "")
        ],
        "board_excluded": dedupe_by_code(board_excluded),
        "generation_notes": generation_notes,
    }


def missing_pool_codes(stocks_by_code: dict[str, dict[str, Any]], pool: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(code for code in stocks_by_code if code not in pool)


def stock_template(code: str, name: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "source_themes": [],
        "source_flags": {"candidate": False, "market": False, "news": False, "lhb": False},
        "best_score": None,
        "news_ref": None,
        "market_ref": None,
        "technical": {},
        "filter": {},
        "anomaly": None,
    }


def iter_theme_library_stocks(
    theme_data: dict[str, Any],
    library_dir: Path,
    top_candidates: int,
    top_leaders: int,
    top_pure: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add_many(items: Any, source: str, limit: int) -> None:
        if not isinstance(items, list):
            return
        for item in items[:limit] if limit > 0 else items:
            if not isinstance(item, dict):
                continue
            code = clean_text(item.get("code"))
            if not code or not CODE_RE.fullmatch(code):
                continue
            rows.append(
                {
                    "code": code,
                    "name": clean_text(item.get("name")) or load_stock_name(code, library_dir) or code,
                    "score": stock_score(item),
                    "source": source,
                    "anchor": bool(item.get("anchor")),
                }
            )

    anchors = theme_data.get("anchors") if isinstance(theme_data.get("anchors"), list) else []
    for code in anchors:
        code_text = clean_text(code)
        if code_text and CODE_RE.fullmatch(code_text):
            rows.append(
                {
                    "code": code_text,
                    "name": load_stock_name(code_text, library_dir) or code_text,
                    "score": 100.0,
                    "source": "anchor",
                    "anchor": True,
                }
            )

    add_many(theme_data.get("industry_leaders"), "industry_leader", top_leaders)
    add_many(theme_data.get("candidate_stocks"), "candidate", top_candidates)
    add_many(theme_data.get("pure_stocks"), "pure", top_pure)
    return rows


def merge_theme_library_stock(target: dict[str, Any], theme: dict[str, Any], row: dict[str, Any]) -> None:
    theme_score = parse_float(theme.get("heat")) or parse_float(row.get("score"))
    source_theme = {
        "name": theme["name"],
        "score": theme_score,
        "library_score": parse_float(row.get("score")),
        "source": row.get("source"),
    }
    if row.get("anchor"):
        source_theme["anchor"] = True

    existing = {item.get("name"): item for item in target.setdefault("source_themes", []) if isinstance(item, dict)}
    if theme["name"] not in existing:
        target["source_themes"].append(source_theme)
    else:
        old_score = parse_float(existing[theme["name"]].get("score"))
        if old_score is None or (theme_score is not None and theme_score > old_score):
            existing[theme["name"]].update(source_theme)

    best = parse_float(target.get("best_score"))
    for candidate in (theme_score, parse_float(row.get("score"))):
        if candidate is not None and (best is None or candidate > best):
            target["best_score"] = candidate
            best = candidate

    flags = target.setdefault("source_flags", {"candidate": False, "market": False, "news": False, "lhb": False})
    flags["candidate"] = True


def build_doc_from_themes(
    date: str,
    themes: list[dict[str, Any]],
    scope: dict[str, Any],
    library_dir: Path,
    top_candidates: int,
    top_leaders: int,
    top_pure: int,
    extra_stocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    stocks_by_code: dict[str, dict[str, Any]] = {}
    board_excluded: list[dict[str, Any]] = []
    generation_notes: list[str] = []
    resolved_themes: list[dict[str, Any]] = []

    for theme in themes:
        theme_data = load_theme(theme["name"], library_dir)
        if not theme_data:
            generation_notes.append(f"theme not found in Theme Library: {theme['name']}")
            continue
        theme_name = clean_text(theme_data.get("name")) or theme["name"]
        resolved_theme = {
            "name": theme_name,
            "rank": theme.get("rank"),
            "heat": parse_float(theme.get("heat")),
            "confidence": parse_float(theme.get("confidence")),
            "stock_count": theme_data.get("qualified_stock_count") or theme_data.get("stock_count"),
        }
        resolved_themes.append(resolved_theme)

        for row in iter_theme_library_stocks(theme_data, library_dir, top_candidates, top_leaders, top_pure):
            code = row["code"]
            name = clean_text(row.get("name")) or code
            decision = scope_decision(code, scope)
            if not decision["allowed"]:
                board_excluded.append(
                    {"code": code, "name": name, "reason": decision["reason"], "matched_rule": decision["matched_rule"]}
                )
                continue
            stock = stocks_by_code.setdefault(code, stock_template(code, name))
            merge_theme_library_stock(stock, resolved_theme, row)

    for extra in extra_stocks:
        code = clean_text(extra.get("code"))
        name = clean_text(extra.get("name")) or load_stock_name(code, library_dir) or code
        decision = scope_decision(code, scope)
        if not decision["allowed"]:
            board_excluded.append(
                {"code": code, "name": name, "reason": decision["reason"], "matched_rule": decision["matched_rule"]}
            )
            continue
        stock = stocks_by_code.setdefault(code, stock_template(code, name))
        merge_extra_stock(stock, extra)

    return resolved_themes, stocks_by_code, dedupe_by_code(board_excluded), generation_notes


def load_universe(path: Path, date: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"theme stock universe must be a JSON object: {path}")
    if data.get("schema_version") != "daily_theme_stocks_universe.v1":
        raise ValueError(f"theme stock universe schema_version must be daily_theme_stocks_universe.v1: {path}")
    if data.get("date") != date:
        raise ValueError(f"theme stock universe date mismatch: expected {date}, got {data.get('date')}")

    stocks_by_code: dict[str, dict[str, Any]] = {}
    stocks = data.get("stocks")
    if not isinstance(stocks, list):
        raise ValueError(f"theme stock universe missing stocks[]: {path}")
    for i, item in enumerate(stocks):
        if not isinstance(item, dict):
            raise ValueError(f"theme stock universe stocks[{i}] must be object")
        code = clean_text(item.get("code"))
        if not code or not CODE_RE.fullmatch(code):
            raise ValueError(f"theme stock universe stocks[{i}].code must be a trading code")
        name = clean_text(item.get("name")) or code
        stock = stock_template(code, name)
        stock["source_themes"] = item.get("source_themes") if isinstance(item.get("source_themes"), list) else []
        stock["source_flags"] = item.get("source_flags") if isinstance(item.get("source_flags"), dict) else stock["source_flags"]
        stock["best_score"] = parse_float(item.get("best_score"))
        for key in ("news_ref", "market_ref", "anomaly", "source_explanation", "note"):
            if clean_text(item.get(key)):
                stock[key] = clean_text(item.get(key))
        stocks_by_code[code] = stock

    themes = data.get("themes") if isinstance(data.get("themes"), list) else []
    board_excluded = data.get("board_excluded") if isinstance(data.get("board_excluded"), list) else []
    generation_notes = data.get("generation_notes") if isinstance(data.get("generation_notes"), list) else []
    return (
        [item for item in themes if isinstance(item, dict)],
        stocks_by_code,
        dedupe_by_code([item for item in board_excluded if isinstance(item, dict)]),
        [str(item) for item in generation_notes],
    )


def build_filtered_doc(
    date: str,
    themes: list[dict[str, Any]],
    stocks_by_code: dict[str, dict[str, Any]],
    board_excluded: list[dict[str, Any]],
    generation_notes: list[str],
    pool: dict[str, dict[str, Any]],
    universe_path: Path,
) -> dict[str, Any]:
    removed_stocks: list[dict[str, Any]] = []

    missing_codes = missing_pool_codes(stocks_by_code, pool)
    if missing_codes:
        raise ValueError(
            "pool_indicators.json missing codes from theme stock universe: "
            + ",".join(missing_codes[:20])
            + ("..." if len(missing_codes) > 20 else "")
            + f"; refresh indicators from {universe_path}"
        )

    final_stocks = []
    for code, stock in stocks_by_code.items():
        technical = technical_from_pool_entry(pool.get(code))
        stock["technical"] = technical
        filt = deterministic_filter_from_technical(technical)
        if filt["status"] == "removed":
            removed_stocks.append({"code": code, "name": stock.get("name") or code, "reason": filt["reason"], "source": filt["source"]})
            continue
        stock["filter"] = filt
        final_stocks.append(stock)

    return {
        "schema_version": "daily_theme_stocks_base.v1",
        "date": date,
        "generated_at": utc_now_iso(),
        "generation_mode": "theme_universe_filter",
        "themes": themes,
        "stocks": final_stocks,
        "board_excluded": dedupe_by_code(board_excluded),
        "removed_stocks": dedupe_by_code(removed_stocks),
        "generation_notes": generation_notes,
    }


def merge_stock(target: dict[str, Any], row: dict[str, str], current_theme: str | None) -> None:
    source_themes = source_themes_from_row(row, current_theme)
    existing = {item.get("name"): item for item in target.setdefault("source_themes", []) if isinstance(item, dict)}
    for item in source_themes:
        name = item.get("name")
        if not name:
            continue
        if name not in existing:
            target["source_themes"].append(item)
            existing[name] = item
        elif item.get("score") is not None:
            old = parse_float(existing[name].get("score"))
            new = parse_float(item.get("score"))
            if old is None or (new is not None and new > old):
                existing[name]["score"] = new

    score = parse_float(row.get("Best Score") or row.get("Score"))
    if score is not None:
        old = parse_float(target.get("best_score"))
        if old is None or score > old:
            target["best_score"] = score
    flags = target.setdefault("source_flags", {"candidate": False, "market": False, "news": False, "lhb": False})
    from_source = source_flags_from_value(row.get("Source"))
    for key, value in from_source.items():
        flags[key] = bool(flags.get(key) or value)
    if clean_text(row.get("News?")):
        flags["news"] = flags["news"] or clean_text(row.get("News?")) not in {"-", "—"}
    if clean_text(row.get("LHB?")):
        flags["lhb"] = flags["lhb"] or clean_text(row.get("LHB?")) not in {"-", "—"}
    if clean_text(row.get("Mkt?")):
        flags["market"] = flags["market"] or clean_text(row.get("Mkt?")) not in {"-", "—"}
    if current_theme and "news-mentioned" in current_theme.lower():
        flags["news"] = True


def build_doc_from_markdown(date: str, theme_stocks_text: str, pool: dict[str, dict[str, Any]], scope: dict[str, Any]) -> dict[str, Any]:
    stocks_by_code: dict[str, dict[str, Any]] = {}
    board_excluded: list[dict[str, Any]] = []
    removed_stocks: list[dict[str, Any]] = []

    for item in iter_stock_rows(theme_stocks_text):
        row = item["row"]
        code = clean_text(row.get("Code"))
        if not code or not CODE_RE.fullmatch(code):
            continue
        name = clean_text(row.get("Name")) or code
        decision = scope_decision(code, scope)
        if not decision["allowed"]:
            board_excluded.append(
                {"code": code, "name": name, "reason": decision["reason"], "matched_rule": decision["matched_rule"]}
            )
            continue
        stock = stocks_by_code.setdefault(
            code,
            {
                "code": code,
                "name": name,
                "source_themes": [],
                "source_flags": {"candidate": False, "market": False, "news": False, "lhb": False},
                "best_score": None,
                "news_ref": None,
                "market_ref": None,
                "technical": {},
                "filter": {},
                "anomaly": None,
            },
        )
        merge_stock(stock, row, item.get("theme"))

    final_stocks = []
    for code, stock in stocks_by_code.items():
        entry = pool.get(code)
        technical = technical_from_pool_entry(entry)
        stock["technical"] = technical
        filt = deterministic_filter_from_technical(technical)
        if filt["status"] == "removed":
            removed_stocks.append({"code": code, "name": stock.get("name") or code, "reason": filt["reason"], "source": filt["source"]})
            continue
        stock["filter"] = filt
        if not stock.get("source_themes"):
            stock["source_themes"] = [{"name": "unknown", "score": None}]
        final_stocks.append(stock)

    removed_seen = {item["code"] for item in removed_stocks if isinstance(item, dict) and item.get("code")}
    stock_seen = {item["code"] for item in final_stocks if isinstance(item, dict) and item.get("code")}
    board_seen = {item["code"] for item in board_excluded if isinstance(item, dict) and item.get("code")}
    for item in parse_removed_rows(theme_stocks_text):
        code = item["code"]
        if code in removed_seen or code in stock_seen or code in board_seen:
            continue
        decision = scope_decision(code, scope)
        if not decision["allowed"]:
            board_excluded.append(
                {"code": code, "name": item.get("name") or code, "reason": decision["reason"], "matched_rule": decision["matched_rule"]}
            )
            board_seen.add(code)
            continue
        removed_stocks.append(item)
        removed_seen.add(code)

    return {
        "schema_version": "daily_theme_stocks_base.v1",
        "date": date,
        "generated_at": utc_now_iso(),
        "generation_mode": "markdown_pool_bridge",
        "themes": parse_themes_summary(theme_stocks_text),
        "stocks": final_stocks,
        "board_excluded": dedupe_by_code(board_excluded),
        "removed_stocks": dedupe_by_code(removed_stocks),
        "generation_notes": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build theme_stocks.base.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--theme", action="append", help="Tradeable theme selected by LLM. Repeatable. Optional format: name:heat:confidence")
    parser.add_argument("--themes", help="Comma-separated tradeable themes selected by LLM. Optional item format: name:heat:confidence")
    parser.add_argument("--theme-stocks-md", help="Legacy source theme_stocks.md path. Only used when explicitly provided.")
    parser.add_argument("--pool", help="Path to pool_indicators.json; default predict/{date}/pool_indicators.json")
    parser.add_argument("--scope", help="Path to trading-scope.json")
    parser.add_argument("--theme-library", help="Path to theme-library skill dir")
    parser.add_argument("--extra", help="Path to theme_stocks.extra.json; default predict/{date}/theme_stocks.extra.json when present")
    parser.add_argument("--universe", help="Path to theme_stocks.universe.json; default predict/{date}/theme_stocks.universe.json")
    parser.add_argument("--universe-output", help="Deprecated alias for --universe")
    parser.add_argument("--universe-only", action="store_true", help="Only write the stock universe; skip pool_indicators filtering")
    parser.add_argument("--top-candidates", type=int, default=15, help="Candidate stocks per theme from Theme Library")
    parser.add_argument("--top-leaders", type=int, default=10, help="Industry leaders per theme from Theme Library")
    parser.add_argument("--top-pure", type=int, default=15, help="Pure stocks per theme from Theme Library")
    parser.add_argument("--output", help="Path to output base JSON; default predict/{date}/theme_stocks.base.json")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    pool_path = Path(args.pool) if args.pool else predict_dir / "pool_indicators.json"
    output_path = Path(args.output) if args.output else predict_dir / "theme_stocks.base.json"
    extra_path = Path(args.extra) if args.extra else predict_dir / "theme_stocks.extra.json"
    universe_path = Path(args.universe or args.universe_output) if (args.universe or args.universe_output) else predict_dir / "theme_stocks.universe.json"

    pool = {} if args.universe_only else load_pool(pool_path)
    scope = load_trading_scope(Path(args.scope) if args.scope else None)
    if args.theme_stocks_md:
        md_path = Path(args.theme_stocks_md)
        if not md_path.exists():
            print(f"[ERROR] missing legacy theme_stocks.md source: {md_path}", file=sys.stderr)
            return 1
        doc = build_doc_from_markdown(args.date, md_path.read_text(encoding="utf-8"), pool, scope)
    else:
        if args.universe_only:
            try:
                themes = collect_theme_specs(args.theme, args.themes)
            except ValueError as exc:
                print(f"[ERROR] {exc}", file=sys.stderr)
                return 2
            if not themes:
                print("[ERROR] provide at least one --theme or --themes item when building theme_stocks.universe.json", file=sys.stderr)
                return 2
            try:
                extra_stocks = load_extra_stocks(extra_path if extra_path.exists() else None, args.date)
                resolved_themes, stocks_by_code, board_excluded, generation_notes = build_doc_from_themes(
                    args.date,
                    themes,
                    scope,
                    Path(args.theme_library) if args.theme_library else theme_library_dir(),
                    args.top_candidates,
                    args.top_leaders,
                    args.top_pure,
                    extra_stocks,
                )
            except ValueError as exc:
                print(f"[ERROR] {exc}", file=sys.stderr)
                return 1
            write_json(universe_path, universe_doc(args.date, resolved_themes, stocks_by_code, board_excluded, generation_notes))
            print(f"OK: wrote {universe_path}")
            return 0
        if not universe_path.exists():
            print(f"[ERROR] missing theme_stocks.universe.json: {universe_path}", file=sys.stderr)
            print("[ERROR] run with --universe-only first, then refresh pool_indicators.json with --codes-file", file=sys.stderr)
            return 1
        try:
            resolved_themes, stocks_by_code, board_excluded, generation_notes = load_universe(universe_path, args.date)
            doc = build_filtered_doc(args.date, resolved_themes, stocks_by_code, board_excluded, generation_notes, pool, universe_path)
        except ValueError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
    write_json(output_path, doc)
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
