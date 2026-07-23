#!/usr/bin/env python3
"""Compute the deterministic intraday theme evidence contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.themes._commands.query import METADATA_DIR, query_stock
from ashare_pilot.themes.runtime import theme_config_path


def _number(value: Any) -> float:
    try:
        return float(str(value or 0).replace("+", "").replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _load_aggregation_config() -> dict[str, float]:
    path = theme_config_path("theme-library-config.json")
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = data.get("aggregation") if isinstance(data.get("aggregation"), dict) else {}
    required = {
        "core_weight",
        "qualified_purity_scale",
        "qualified_weight_min",
        "qualified_weight_max",
        "edge_theme_weight_scale",
        "edge_weight_min",
        "edge_weight_max",
    }
    missing = sorted(required - set(cfg))
    if missing:
        raise ValueError("theme aggregation config missing: " + ", ".join(missing))
    return {key: float(cfg[key]) for key in required}


def _library_metadata() -> tuple[str | None, str | None]:
    path = METADATA_DIR / "update_log.json"
    if not path.exists():
        return None, None
    value = json.loads(path.read_text(encoding="utf-8"))
    version = value.get("library_version")
    if not version:
        version = str(value.get("last_build") or "")[:10] or None
    return version, version


def _stock_theme_data(input_data: dict[str, Any], code: str) -> dict[str, Any] | None:
    injected = input_data.get("stock_themes")
    if isinstance(injected, dict) and isinstance(injected.get(code), dict):
        return injected[code]
    return query_stock(code)


def _compact_relation(value: Any) -> dict[str, Any] | None:
    relation = value if isinstance(value, dict) else {"name": str(value)}
    name = relation.get("name")
    if not isinstance(name, str) or not name:
        return None
    result = {"name": name}
    for field in (
        "eligible",
        "member_role",
        "weight",
        "purity_score",
        "industry_score",
        "candidate_score",
        "liquidity_score",
        "market_cap_score",
        "anchor",
    ):
        if field in relation:
            result[field] = relation[field]
    return result


def _pool_rows(input_data: dict[str, Any]) -> list[dict[str, Any]]:
    pool = input_data.get("compute_pool", input_data)
    return [row for row in pool if isinstance(row, dict)] if isinstance(pool, list) else []


def _market_as_of(input_data: dict[str, Any], date: str = "") -> str | None:
    for field in ("market_as_of", "enriched_time", "generated_at", "fetch_time"):
        value = input_data.get(field)
        if isinstance(value, str) and value:
            return value
    return f"{date} 14:30:00" if date else None


def _member_weight(relation: dict[str, Any], cfg: dict[str, float]) -> tuple[str, float]:
    role = relation.get("member_role")
    if role not in {"core", "qualified", "edge"}:
        raise ValueError(
            f"theme relation {relation.get('name')} missing valid member_role; rebuild theme library"
        )
    if role == "core":
        return "core", cfg["core_weight"]
    if role == "qualified":
        if relation.get("purity_score") is None:
            raise ValueError(
                f"qualified relation {relation.get('name')} missing purity_score; rebuild theme library"
            )
        weight = _number(relation.get("purity_score")) * cfg["qualified_purity_scale"]
        return "core", _clamp(
            weight, cfg["qualified_weight_min"], cfg["qualified_weight_max"]
        )
    if relation.get("weight") is None:
        raise ValueError(
            f"edge relation {relation.get('name')} missing theme weight; rebuild theme library"
        )
    weight = _number(relation.get("weight")) * cfg["edge_theme_weight_scale"]
    return "diffusion", _clamp(weight, cfg["edge_weight_min"], cfg["edge_weight_max"])


def _heat_inputs(
    observations: dict[str, list[dict[str, Any]]], group: str
) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    for theme, rows in observations.items():
        selected = [row for row in rows if row["heat_group"] == group and row["aggregation_weight"] > 0]
        weight_sum = sum(row["aggregation_weight"] for row in selected)
        if not selected or weight_sum <= 0:
            values[theme] = {
                "breadth": 0.0,
                "leader": 0.0,
                "capital": 0.0,
                "momentum": 0.0,
            }
            continue
        values[theme] = {
            "breadth": weight_sum,
            "leader": max(row["change_pct"] for row in selected),
            "capital": sum(
                row["main_net_inflow"] * row["aggregation_weight"] for row in selected
            ),
            "momentum": sum(
                row["change_pct"] * row["aggregation_weight"] for row in selected
            ) / weight_sum,
        }
    return values


def _heat_scores(
    values: dict[str, dict[str, float]]
) -> dict[str, tuple[float, dict[str, float]]]:
    if not values:
        return {}
    max_breadth = max((v["breadth"] for v in values.values()), default=0) or 1
    max_leader = max((abs(v["leader"]) for v in values.values()), default=0) or 1
    max_capital = max((abs(v["capital"]) for v in values.values()), default=0) or 1
    active_momentum = [v["momentum"] for v in values.values() if v["breadth"] > 0]
    min_momentum = min(active_momentum, default=0)
    max_momentum = max(active_momentum, default=0)
    momentum_range = max_momentum - min_momentum or 1
    result = {}
    for theme, value in values.items():
        if value["breadth"] <= 0:
            result[theme] = (0.0, {
                "breadth": 0.0, "leader": 0.0, "capital": 0.0,
                "momentum": 0.0, "continuation": 0.0,
            })
            continue
        parts = {
            "breadth": value["breadth"] / max_breadth * 20,
            "leader": abs(value["leader"]) / max_leader * 30,
            "capital": value["capital"] / max_capital * 25,
            "momentum": (value["momentum"] - min_momentum) / momentum_range * 15,
            "continuation": 10.0,
        }
        result[theme] = (_clamp(sum(parts.values()), 0, 100), parts)
    return result


def _build_evidence(
    input_data: dict[str, Any], pool_cutoff: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cfg = _load_aggregation_config()
    pool = _pool_rows(input_data)
    ranked = sorted(
        pool,
        key=lambda x: x.get("quick_score", 0) or x.get("overnight_score", 0) or 0,
        reverse=True,
    )
    stock_themes: dict[str, dict[str, Any]] = {}
    observations: dict[str, list[dict[str, Any]]] = {}

    for stock in pool:
        code = str(stock.get("code") or "")
        if not code:
            continue
        static = _stock_theme_data(input_data, code) or {}
        relations = [
            compact
            for value in static.get("themes", [])
            if (compact := _compact_relation(value)) is not None
        ]
        stock_themes[code] = {
            "code": code,
            "name": stock.get("name") or static.get("name", ""),
            "themes": relations,
        }

    selected_codes = {str(stock.get("code") or "") for stock in ranked[:pool_cutoff]}
    selected = [stock for stock in pool if str(stock.get("code") or "") in selected_codes]
    for stock in selected:
        code = str(stock.get("code") or "")
        change = _number(stock.get("change_pct"))
        flow = _number(
            (stock.get("enriched") or {}).get("money_flow", {}).get("main_net_inflow")
            if isinstance(stock.get("enriched"), dict)
            else 0
        )
        for relation in stock_themes.get(code, {}).get("themes", []):
            group, weight = _member_weight(relation, cfg)
            observations.setdefault(relation["name"], []).append({
                "code": code,
                "name": stock.get("name", ""),
                "member_role": relation.get("member_role", "edge"),
                "eligible": relation.get("eligible", False),
                "aggregation_weight": weight,
                "heat_group": group,
                "purity_score": relation.get("purity_score"),
                "industry_score": relation.get("industry_score"),
                "candidate_score": relation.get("candidate_score"),
                "theme_weight": relation.get("weight"),
                "anchor": relation.get("anchor", False),
                "change_pct": change,
                "main_net_inflow": flow,
            })

    core_values = _heat_inputs(observations, "core")
    diffusion_values = _heat_inputs(observations, "diffusion")
    core_scores = _heat_scores(core_values)
    diffusion_scores = _heat_scores(diffusion_values)
    rankings = []
    for theme, rows in observations.items():
        core_candidates = [row for row in rows if row["member_role"] == "core"]
        fallback = False
        if not core_candidates:
            core_candidates = [row for row in rows if row["member_role"] == "qualified"]
            fallback = bool(core_candidates)
        core_leader_row = (
            max(core_candidates, key=lambda row: (row["change_pct"], row["code"]))
            if core_candidates else None
        )
        momentum_row = max(rows, key=lambda row: (row["change_pct"], row["code"]))
        core_leader = None
        if core_leader_row:
            core_leader = {
                "code": core_leader_row["code"],
                "name": core_leader_row["name"],
                "change_pct": core_leader_row["change_pct"],
                "leader_role": core_leader_row["member_role"],
                "leader_fallback": fallback,
            }
        momentum_leader = {
            "code": momentum_row["code"],
            "name": momentum_row["name"],
            "change_pct": momentum_row["change_pct"],
            "leader_role": momentum_row["member_role"],
        }
        contributors = []
        for row in sorted(rows, key=lambda value: value["code"]):
            flags = [row["heat_group"] + "_heat"]
            if core_leader_row is row:
                flags.append("core_leader")
            if momentum_row is row:
                flags.append("momentum_leader")
            contributor = {
                key: row.get(key)
                for key in (
                    "code", "name", "member_role", "eligible", "aggregation_weight",
                    "theme_weight", "purity_score", "industry_score", "candidate_score",
                    "anchor", "change_pct", "main_net_inflow",
                )
                if row.get(key) is not None
            }
            contributor["contributions"] = flags
            contributors.append(contributor)
        core_heat, core_parts = core_scores[theme]
        diffusion_heat, diffusion_parts = diffusion_scores[theme]
        rankings.append({
            "theme": theme,
            "core_heat": round(core_heat, 2),
            "diffusion_heat": round(diffusion_heat, 2),
            "core_member_count": sum(
                row["member_role"] in {"core", "qualified"} for row in rows
            ),
            "edge_member_count": sum(row["member_role"] == "edge" for row in rows),
            "core_leader": core_leader,
            "momentum_leader": momentum_leader,
            "core_breakdown": {key: round(value, 2) for key, value in core_parts.items()},
            "diffusion_breakdown": {
                key: round(value, 2) for key, value in diffusion_parts.items()
            },
            "contributors": contributors,
        })
    rankings.sort(
        key=lambda row: (-row["core_heat"], -row["diffusion_heat"], row["theme"])
    )
    return rankings, stock_themes


def compute_theme_ranking(input_data: dict, pool_cutoff: int = 40) -> list:
    """Return all deterministic theme rankings; CLI applies the Top-N display cut."""
    return _build_evidence(input_data, pool_cutoff)[0]


def build_theme_ranking_document(
    input_data: dict[str, Any],
    *,
    pool_cutoff: int = 40,
    top_n: int = 15,
    date: str = "",
) -> dict[str, Any]:
    rankings, stock_themes = _build_evidence(input_data, pool_cutoff)
    library_version, membership_as_of = _library_metadata()
    injected_version = input_data.get("library_version")
    if isinstance(injected_version, str):
        library_version = membership_as_of = injected_version
    return {
        "schema_version": "intraday_theme_ranking.v2",
        "library_version": library_version,
        "membership_as_of": membership_as_of,
        "market_as_of": _market_as_of(input_data, date),
        "theme_ranking": rankings[:top_n] if top_n else rankings,
        "total_themes": len(rankings),
        "stock_themes": stock_themes,
    }


def format_markdown(scores: list, top_n: int = 15, date: str = "") -> str:
    lines = [f"## Theme Ranking ({date} 14:30)" if date else "## Theme Ranking", ""]
    lines.extend([
        "基于 ComputePool 与已发布主题成员关系的确定性聚合（感知层，不含交易推荐）",
        "",
        "| # | 主题 | 核心热度 | 扩散热度 | 核心领涨 | 动量领涨 |",
        "|---|------|---------:|---------:|----------|----------|",
    ])
    for index, row in enumerate(scores[:top_n], 1):
        core = row.get("core_leader") or {}
        momentum = row.get("momentum_leader") or {}
        lines.append(
            f"| {index} | {row['theme']} | {row['core_heat']:.1f} | "
            f"{row['diffusion_heat']:.1f} | {core.get('name', '—')} | "
            f"{momentum.get('name', '—')} |"
        )
    return "\n".join(lines)


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Compute intraday theme evidence")
    parser.add_argument("input")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--output")
    parser.add_argument("--pool-cutoff", type=int, default=40)
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    try:
        document = build_theme_ranking_document(
            data, pool_cutoff=args.pool_cutoff, top_n=args.top_n, date=args.date or ""
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    output = (
        json.dumps(document, ensure_ascii=False, indent=2)
        if args.json
        else format_markdown(document["theme_ranking"], top_n=args.top_n, date=args.date or "")
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Written to {args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
