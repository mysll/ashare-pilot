#!/usr/bin/env python3
"""Build deterministic predict/{date}/theme_stocks.base.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import workspace_path

from ashare_pilot.mapping.daily_contract import (
    CODE_RE,
    clean_text,
    default_predict_dir,
    deterministic_filter_from_technical,
    load_pool,
    parse_float,
    read_json,
    scope_decision,
    technical_from_pool_entry,
    theme_projection_errors,
    utc_now_iso,
    write_json,
)


def theme_library_dir() -> Path:
    return workspace_path("data", "theme-library")


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*()]', "_", name)


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
    # Extras may expand membership but may not self-assert decision-visible source
    # flags. Structured news/market/LHB inputs set those flags later.
    for key in ("news_ref", "market_ref"):
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
        "schema_version": "daily_theme_stocks_universe.v2",
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
    theme_score = parse_float(theme.get("final_heat"))
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
        resolved_theme = {
            "name": theme["name"],
            "rank": theme.get("rank"),
            "final_heat": parse_float(theme.get("final_heat")),
            "attention_direction": clean_text(
                theme.get("attention_direction")
            ),
            "evidence_refs": list(theme.get("evidence_refs") or []),
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
    if data.get("schema_version") != "daily_theme_stocks_universe.v2":
        raise ValueError(f"theme stock universe schema_version must be daily_theme_stocks_universe.v2: {path}")
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
        for key in ("news_ref", "market_ref"):
            if clean_text(item.get(key)):
                stock[key] = clean_text(item.get(key))
        stocks_by_code[code] = stock

    themes = data.get("themes") if isinstance(data.get("themes"), list) else []
    projection_errors = [
        error
        for index, theme in enumerate(themes)
        for error in theme_projection_errors(theme, f"themes[{index}]")
    ]
    if projection_errors:
        raise ValueError(
            "invalid theme stock universe projection:\n"
            + "\n".join(f"  - {error}" for error in projection_errors)
        )
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
        "schema_version": "daily_theme_stocks_base.v2",
        "date": date,
        "generated_at": utc_now_iso(),
        "generation_mode": "theme_universe_filter",
        "themes": themes,
        "stocks": final_stocks,
        "board_excluded": dedupe_by_code(board_excluded),
        "removed_stocks": dedupe_by_code(removed_stocks),
        "generation_notes": generation_notes,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build theme_stocks.base.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--pool", help="Path to pool_indicators.json; default predict/{date}/pool_indicators.json")
    parser.add_argument("--universe", help="Path to theme_stocks.universe.json; default predict/{date}/theme_stocks.universe.json")
    parser.add_argument("--output", help="Path to output base JSON; default predict/{date}/theme_stocks.base.json")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    pool_path = Path(args.pool) if args.pool else predict_dir / "pool_indicators.json"
    output_path = Path(args.output) if args.output else predict_dir / "theme_stocks.base.json"
    universe_path = Path(args.universe) if args.universe else predict_dir / "theme_stocks.universe.json"

    pool = load_pool(pool_path)
    if not universe_path.exists():
        print(f"[ERROR] missing theme_stocks.universe.json: {universe_path}", file=sys.stderr)
        print("[ERROR] run build_theme_stocks_universe.py first, then refresh pool_indicators.json with --codes-file", file=sys.stderr)
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
