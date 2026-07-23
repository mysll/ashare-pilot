#!/usr/bin/env python3
"""Build theme library from cached concept data.

Generates:
  - concepts/*.json      (one per East Money concept board)
  - themes/*.json         (one per Theme, grouping multiple concepts)
  - stocks/*.json         (one per stock, with both themes and concepts)
  - aliases/theme_aliases.json
  - index/theme_to_concept.json
  - index/theme_to_stock.json
  - index/concept_to_stock.json
  - index/stock_to_theme.json
  - index/stock_to_concept.json
  - index/keyword_to_theme.json
  - metadata/concept_list.json
  - metadata/update_log.json

Theme Industry Ranking v5:
  purity_score = coverage_pct * purity_coverage_weight + rank_score * purity_rank_weight
  industry_score = purity * industry_purity_weight + liquidity * industry_liquidity_weight + market_cap * industry_market_cap_weight
  candidate_score = purity * candidate_purity_weight + liquidity * candidate_liquidity_weight
                   + market_cap * candidate_market_cap_weight + momentum * candidate_momentum_weight (momentum=0)
  Eligibility: coverage_pct >= min_coverage OR matched_concepts >= min_concepts
  Exceptions: anchor stocks and rank-1 in core concept

Usage:
    python build_library.py
    python build_library.py --clean
    python build_library.py --themes-only
    python build_library.py --concepts-only
    python build_library.py --stocks-only
"""

import argparse
import io
import json
import math
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from ashare_pilot.themes.runtime import (
    theme_cache_path,
    theme_config_path,
    theme_data_path,
)

CACHE_DIR = theme_cache_path()
STOCKS_CACHE_DIR = CACHE_DIR / "stocks"
CONCEPTS_DIR = theme_data_path("concepts")
THEMES_DIR = theme_data_path("themes")
STOCKS_DIR = theme_data_path("stocks")
ALIASES_DIR = theme_data_path("aliases")
METADATA_DIR = theme_data_path("metadata")
INDEX_DIR = theme_data_path("index")

CONFIG_FILE = theme_config_path("theme-config.json")
LIBRARY_CONFIG_FILE = theme_config_path("theme-library-config.json")

RANK_FACTORS = {
    1: 1.00,
    2: 0.80,
    3: 0.65,
}


def _rank_factor(rank):
    if rank in RANK_FACTORS:
        return RANK_FACTORS[rank]
    if 4 <= rank <= 10:
        return 0.40
    if 11 <= rank <= 20:
        return 0.20
    return 0


def _load_config():
    if not CONFIG_FILE.exists():
        return {}, {}, {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return (
        cfg.get("themes", {}),
        cfg.get("concept_aliases", {}),
        cfg.get("related_themes", {}),
    )


def _load_member_fetch_exclusions():
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    value = cfg.get("member_fetch_exclusions", {})
    return value if isinstance(value, dict) else {}


def _load_library_config():
    defaults = {
        "pure_limit": 50,
        "leader_limit": 20,
        "candidate_limit": 30,
        "pure_threshold": 30,
        "leader_threshold": 50,
        "candidate_threshold": 60,
        "default_min_coverage": 15,
        "default_min_concepts": 2,
        "aggregation": {
            "core_weight": 1.0,
            "qualified_purity_scale": 0.01,
            "qualified_weight_min": 0.0,
            "qualified_weight_max": 1.0,
            "edge_theme_weight_scale": 0.1,
            "edge_weight_min": 0.0,
            "edge_weight_max": 1.0,
        },
        "scoring": {
            "purity_coverage_weight": 0.60,
            "purity_rank_weight": 0.40,
            "leader_purity_weight": 0.40,
            "leader_liquidity_weight": 0.35,
            "leader_market_cap_weight": 0.25,
            "candidate_purity_weight": 0.30,
            "candidate_liquidity_weight": 0.30,
            "candidate_market_cap_weight": 0.20,
            "candidate_momentum_weight": 0.20,
        },
    }
    if not LIBRARY_CONFIG_FILE.exists():
        return defaults
    with open(LIBRARY_CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for key, val in defaults.items():
        if key not in cfg:
            cfg[key] = val
        elif isinstance(val, dict) and isinstance(cfg[key], dict):
            for dk, dv in val.items():
                if dk not in cfg[key]:
                    cfg[key][dk] = dv
    return cfg


THEMES_CONFIG, CONCEPT_ALIASES, RELATED_THEMES_MAP = {}, {}, {}
MEMBER_FETCH_EXCLUSIONS = {}
LIBRARY_CONFIG = {}


def reload_configuration():
    global THEMES_CONFIG, CONCEPT_ALIASES, RELATED_THEMES_MAP
    global MEMBER_FETCH_EXCLUSIONS, LIBRARY_CONFIG
    THEMES_CONFIG, CONCEPT_ALIASES, RELATED_THEMES_MAP = _load_config()
    MEMBER_FETCH_EXCLUSIONS = _load_member_fetch_exclusions()
    LIBRARY_CONFIG = _load_library_config()


def load_concept_stocks():
    if not STOCKS_CACHE_DIR.exists():
        print(f"Error: {STOCKS_CACHE_DIR} not found. Run fetch_concept_stocks.py first.")
        sys.exit(1)
    all_data = {}
    for f in STOCKS_CACHE_DIR.glob("*.json"):
        code = f.stem
        with open(f, "r", encoding="utf-8") as fh:
            value = json.load(fh)
        stocks = value.get("stocks", []) if isinstance(value, dict) else []
        unique_codes = {
            stock.get("code")
            for stock in stocks
            if isinstance(stock, dict) and stock.get("code")
        }
        ignored = value.get("status") == "ignored"
        valid_ignored = (
            ignored
            and value.get("concept_name") in MEMBER_FETCH_EXCLUSIONS
            and value.get("reported_total") == 0
            and value.get("stock_count") == 0
            and stocks == []
        )
        valid_complete = (
            value.get("status") == "complete"
            and value.get("reported_total") == value.get("stock_count")
            and value.get("stock_count") == len(stocks)
            and len(unique_codes) == len(stocks)
        )
        if not valid_ignored and not valid_complete:
            print(
                f"Error: incomplete or legacy concept cache {f}. "
                "Run themes concepts fetch-stocks --reset first."
            )
            sys.exit(1)
        all_data[code] = value
    if not all_data:
        print(f"Error: No concept stock files found in {STOCKS_CACHE_DIR}. Run fetch_concept_stocks.py first.")
        sys.exit(1)
    return all_data


def load_concepts():
    cache_path = CACHE_DIR / "concepts.json"
    if not cache_path.exists():
        return {}
    with open(cache_path, "r", encoding="utf-8") as f:
        concepts = json.load(f)
    return {c["code"]: c for c in concepts}


def calc_weight(rank, total):
    if total <= 0:
        return 1
    ratio = rank / total
    if ratio <= 0.02:
        return 10
    elif ratio <= 0.05:
        return 9
    elif ratio <= 0.10:
        return 8
    elif ratio <= 0.20:
        return 7
    elif ratio <= 0.35:
        return 6
    elif ratio <= 0.50:
        return 5
    elif ratio <= 0.65:
        return 4
    elif ratio <= 0.80:
        return 3
    elif ratio <= 0.90:
        return 2
    else:
        return 1


def _safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _compute_concept_similarity(concept_name, theme_name):
    """Compute name similarity between concept and theme (0-100).

    Method: character overlap ratio weighted by position.
    """
    cn = concept_name.lower()
    tn = theme_name.lower()

    if cn == tn:
        return 100

    if tn in cn or cn in tn:
        overlap = len(tn) / max(len(cn), len(tn))
        return round(overlap * 100)

    cn_chars = set(cn)
    tn_chars = set(tn)
    common = cn_chars & tn_chars
    if not common:
        return 0
    union = cn_chars | tn_chars
    return round(len(common) / len(union) * 100)


def _compute_concept_weight(concept_name, theme_name, concept_stock_count, all_stock_counts):
    """Compute concept weight within a theme.

    weight = similarity_score * 0.6 + stock_count_score * 0.4

    Returns float 0.0-1.0.
    """
    similarity = _compute_concept_similarity(concept_name, theme_name)

    if all_stock_counts:
        min_sc = min(all_stock_counts)
        max_sc = max(all_stock_counts)
        if max_sc > min_sc:
            count_score = 1.0 - (concept_stock_count - min_sc) / (max_sc - min_sc) * 0.5
        else:
            count_score = 0.5
    else:
        count_score = 0.5

    raw = (similarity / 100.0) * 0.6 + count_score * 0.4

    weight = max(0.1, min(1.0, raw))
    weight = round(weight, 2)

    return weight


def _get_concept_weights(theme_name, theme_cfg, child_concepts, concept_info, all_stock_counts):
    """Get concept weights, using manual overrides if available, else auto-generated."""
    overrides = theme_cfg.get("concept_weights_override", {})

    weights = {}
    for cn in child_concepts:
        if cn in overrides:
            weights[cn] = overrides[cn]
        else:
            stock_count = concept_info.get(cn, {}).get("stock_count", 50)
            weights[cn] = _compute_concept_weight(cn, theme_name, stock_count, all_stock_counts)

    return weights


def _normalize_scores(values, floor=0):
    """Normalize a list of numeric values to 0-100 range."""
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [50.0] * len(values)
    return [((v - min_v) / (max_v - min_v)) * 100 for v in values]


def _normalize_log_scores(raw_values):
    """Normalize values using log scale to 0-100 range."""
    positive = [v for v in raw_values if v > 0]
    if not positive:
        return [0.0] * len(raw_values)
    log_min = math.log(max(min(positive), 1))
    log_max = math.log(max(max(positive), 2))
    if log_max > log_min:
        return [((math.log(max(v, 1)) - log_min) / (log_max - log_min)) * 100 for v in raw_values]
    return [50.0] * len(raw_values)


def _is_eligible(coverage_pct, matched_concepts, is_anchor, is_rank1_in_core, min_coverage, min_concepts):
    """V4 eligibility filter: stock is eligible if coverage_pct >= min_coverage
    OR matched_concepts >= min_concepts, with exceptions for anchors and rank-1."""
    if is_anchor or is_rank1_in_core:
        return True
    return coverage_pct >= min_coverage or matched_concepts >= min_concepts


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _safe_filename(name):
    return re.sub(r'[<>:"/\\|?*()]', '_', name)


def build_concepts(all_data, concepts_map):
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)

    concept_info = {}
    for concept_code, data in all_data.items():
        name = data["concept_name"]
        stocks = data["stocks"]
        stock_count = len(stocks)

        safe_name = _safe_filename(name)
        concept_path = CONCEPTS_DIR / f"{safe_name}.json"

        aliases = CONCEPT_ALIASES.get(name, [])

        sorted_stocks = sorted(stocks, key=lambda s: s.get("total_mv", 0) or 0, reverse=True)
        stock_codes = [s["code"] for s in sorted_stocks]

        concept_data = {
            "id": concept_code,
            "name": name,
            "source": {
                "provider": "eastmoney",
                "concept_code": concept_code,
            },
            "aliases": aliases,
            "stock_count": stock_count,
            "stocks": stock_codes,
            "member_fetch_status": data.get("status", "complete"),
            "last_update": time.strftime('%Y-%m-%d'),
        }
        if data.get("status") == "ignored":
            concept_data["ignore_reason"] = data.get("ignore_reason")

        _write_json(concept_path, concept_data)

        concept_info[name] = {
            "code": concept_code,
            "file": f"{safe_name}.json",
            "stock_count": stock_count,
            "stocks": stock_codes,
            "aliases": aliases,
            "member_fetch_status": data.get("status", "complete"),
        }

    return concept_info


def _compute_theme_scores(theme_name, theme_cfg, child_concepts, all_concept_stocks, concept_info):
    """Compute V5 multi-dimensional ranking: purity, industry, candidate scores.

    Returns display Top-N lists, complete member evidence, weights, and qualified count.
    """
    all_stock_counts = [
        concept_info.get(cn, {}).get("stock_count", 50)
        for cn in child_concepts
        if cn in concept_info
    ]
    concept_weights = _get_concept_weights(theme_name, theme_cfg, child_concepts, concept_info, all_stock_counts)

    total_theme_weight = sum(concept_weights.get(cn, 0.5) for cn in child_concepts)

    anchor_codes = set(theme_cfg.get("anchors", []))
    min_coverage = theme_cfg.get("min_coverage", LIBRARY_CONFIG["default_min_coverage"])
    min_concepts = theme_cfg.get("min_concepts", LIBRARY_CONFIG["default_min_concepts"])
    scoring = LIBRARY_CONFIG["scoring"]

    stock_data = {}

    for cn in child_concepts:
        if cn not in all_concept_stocks:
            continue
        cw = concept_weights.get(cn, 0.5)
        sorted_stocks = all_concept_stocks[cn]
        for rank_0, s in enumerate(sorted_stocks):
            rank = rank_0 + 1
            code = s["code"]
            if code not in stock_data:
                stock_data[code] = {
                    "code": code,
                    "name": s["name"],
                    "total_mv": _safe_float(s.get("total_mv", 0)),
                    "turnover": _safe_float(s.get("turnover", 0)),
                    "amount": _safe_float(s.get("amount", 0)),
                    "concept_ranks": {},
                    "weighted_coverage": 0.0,
                    "rank_weighted_sum": 0.0,
                    "theme_weight": 0.0,
                }
            stock_data[code]["concept_ranks"][cn] = rank
            stock_data[code]["weighted_coverage"] += cw
            stock_data[code]["rank_weighted_sum"] += cw * _rank_factor(rank)
            stock_data[code]["theme_weight"] = max(
                stock_data[code]["theme_weight"],
                round(calc_weight(rank_0, len(sorted_stocks)) * cw, 2),
            )

    if not stock_data or total_theme_weight <= 0:
        return [], [], [], [], concept_weights, 0

    coverage_pcts = []
    raw_rank_scores = []
    raw_liquidity_scores = []
    raw_mcap_scores = []

    for sd in stock_data.values():
        coverage_pcts.append((sd["weighted_coverage"] / total_theme_weight) * 100)
        raw_rank_scores.append(sd["rank_weighted_sum"])
        raw_liquidity_scores.append(sd["amount"])
        raw_mcap_scores.append(sd["total_mv"])

    max_rank_ws = max(raw_rank_scores) if raw_rank_scores else 1
    rank_scores = [(v / max_rank_ws) * 100 for v in raw_rank_scores]

    liquidity_scores = _normalize_log_scores(raw_liquidity_scores)
    mcap_scores = _normalize_log_scores(raw_mcap_scores)

    eligible_stocks = []
    members = []
    codes = list(stock_data.keys())

    for i, code in enumerate(codes):
        sd = stock_data[code]
        coverage_pct = coverage_pcts[i]
        rank_score = rank_scores[i]
        liquidity_score = liquidity_scores[i]
        market_cap_score = mcap_scores[i]

        matched_concepts_list = [cn for cn in child_concepts if cn in sd["concept_ranks"]]
        matched_count = len(matched_concepts_list)

        is_anchor = code in anchor_codes
        is_rank1_in_core = any(
            sd["concept_ranks"][cn] == 1 and concept_weights.get(cn, 0.5) >= 0.8
            for cn in child_concepts
            if cn in sd["concept_ranks"]
        )

        eligible = _is_eligible(
            coverage_pct, matched_count, is_anchor, is_rank1_in_core, min_coverage, min_concepts
        )
        if not eligible:
            members.append({
                "code": code,
                "name": sd["name"],
                "eligible": False,
                "member_role": "edge",
                "anchor": False,
                "theme_weight": sd["theme_weight"],
            })
            continue

        purity_score = round(
            coverage_pct * scoring["purity_coverage_weight"]
            + rank_score * scoring["purity_rank_weight"], 1
        )
        industry_score = round(
            purity_score * scoring["leader_purity_weight"]
            + liquidity_score * scoring["leader_liquidity_weight"]
            + market_cap_score * scoring["leader_market_cap_weight"], 1
        )
        candidate_score = round(
            purity_score * scoring["candidate_purity_weight"]
            + liquidity_score * scoring["candidate_liquidity_weight"]
            + market_cap_score * scoring["candidate_market_cap_weight"]
            + 0 * scoring["candidate_momentum_weight"], 1
        )

        member_role = (
            "core"
            if is_anchor or industry_score >= LIBRARY_CONFIG["leader_threshold"]
            else "qualified"
        )
        scored_member = {
            "code": code,
            "name": sd["name"],
            "eligible": True,
            "member_role": member_role,
            "theme_weight": sd["theme_weight"],
            "purity_score": purity_score,
            "industry_score": industry_score,
            "candidate_score": candidate_score,
            "liquidity_score": round(liquidity_score, 1),
            "market_cap_score": round(market_cap_score, 1),
            "anchor": is_anchor,
        }
        eligible_stocks.append(scored_member)
        members.append(dict(scored_member))

    qualified_count = len(eligible_stocks)

    pure_limit = LIBRARY_CONFIG["pure_limit"]
    leader_limit = LIBRARY_CONFIG["leader_limit"]
    candidate_limit = LIBRARY_CONFIG["candidate_limit"]

    pure_list = sorted(eligible_stocks, key=lambda x: x["purity_score"], reverse=True)[:pure_limit]
    pure_list = [{"code": s["code"], "name": s["name"], "purity_score": s["purity_score"]} for s in pure_list]

    industry_list = sorted(eligible_stocks, key=lambda x: x["industry_score"], reverse=True)[:leader_limit]
    industry_list = [
        {
            "code": s["code"],
            "name": s["name"],
            "industry_score": s["industry_score"],
            "purity_score": s["purity_score"],
            "liquidity_score": s["liquidity_score"],
            "market_cap_score": s["market_cap_score"],
            "anchor": s["anchor"],
        }
        for s in industry_list
    ]

    candidate_list = sorted(eligible_stocks, key=lambda x: x["candidate_score"], reverse=True)[:candidate_limit]
    candidate_list = [
        {
            "code": s["code"],
            "name": s["name"],
            "candidate_score": s["candidate_score"],
            "purity_score": s["purity_score"],
            "liquidity_score": s["liquidity_score"],
            "market_cap_score": s["market_cap_score"],
        }
        for s in candidate_list
    ]

    members.sort(
        key=lambda x: (
            {"core": 0, "qualified": 1, "edge": 2}[x["member_role"]],
            -x.get("industry_score", 0),
            -x.get("purity_score", 0),
            x["code"],
        )
    )
    return pure_list, industry_list, candidate_list, members, concept_weights, qualified_count


def build_themes(all_data, concept_info):
    THEMES_DIR.mkdir(parents=True, exist_ok=True)

    all_concept_stocks = {}
    for concept_code, data in all_data.items():
        name = data["concept_name"]
        sorted_stocks = sorted(data["stocks"], key=lambda s: s.get("total_mv", 0) or 0, reverse=True)
        all_concept_stocks[name] = sorted_stocks

    theme_info = {}
    for theme_name, theme_cfg in THEMES_CONFIG.items():
        concept_names = theme_cfg["concepts"]
        theme_aliases = theme_cfg.get("aliases", [])

        merged_stocks = []
        seen_codes = set()
        child_concepts = []

        for cn in concept_names:
            if cn not in concept_info:
                print(f"  Warning: concept '{cn}' not found for theme '{theme_name}', skipping")
                continue

            child_concepts.append(cn)

            if cn in all_concept_stocks:
                for s in all_concept_stocks[cn]:
                    if s["code"] not in seen_codes:
                        seen_codes.add(s["code"])
                        merged_stocks.append(s)

        (
            pure_stocks,
            industry_stocks,
            candidate_stocks,
            members,
            concept_weights,
            qualified_count,
        ) = _compute_theme_scores(
            theme_name, theme_cfg, child_concepts, all_concept_stocks, concept_info
        )

        merged_stocks_sorted = sorted(merged_stocks, key=lambda s: s.get("total_mv", 0) or 0, reverse=True)
        stock_codes = [s["code"] for s in merged_stocks_sorted]

        keywords = list(dict.fromkeys([theme_name] + theme_aliases + child_concepts[:5]))[:15]

        weighted_concepts = [
            {"name": cn, "weight": concept_weights.get(cn, 0.5)}
            for cn in child_concepts
        ]

        anchor_codes = list(theme_cfg.get("anchors", []))

        theme_data = {
            "name": theme_name,
            "concepts": child_concepts,
            "concept_weights": weighted_concepts,
            "aliases": theme_aliases,
            "keywords": keywords,
            "anchors": anchor_codes,
            "stock_count": len(stock_codes),
            "qualified_stock_count": qualified_count,
            "pure_stocks": pure_stocks,
            "industry_leaders": industry_stocks,
            "candidate_stocks": candidate_stocks,
            "members": members,
            "stocks": stock_codes,
            "library_version": time.strftime('%Y-%m-%d'),
            "last_update": time.strftime('%Y-%m-%d'),
        }

        safe_name = _safe_filename(theme_name)
        theme_path = THEMES_DIR / f"{safe_name}.json"
        _write_json(theme_path, theme_data)

        theme_info[theme_name] = {
            "concepts": child_concepts,
            "concept_weights": concept_weights,
            "aliases": theme_aliases,
            "keywords": keywords,
            "stock_count": len(stock_codes),
            "qualified_stock_count": qualified_count,
            "stocks": stock_codes,
            "pure_stocks": pure_stocks,
            "industry_leaders": industry_stocks,
            "candidate_stocks": candidate_stocks,
            "members": members,
            "anchors": anchor_codes,
            "library_version": time.strftime('%Y-%m-%d'),
            "file": f"{safe_name}.json",
        }

    return theme_info


def build_stocks(all_data, theme_info):
    STOCKS_DIR.mkdir(parents=True, exist_ok=True)

    concept_stock_weights = defaultdict(list)
    for concept_code, data in all_data.items():
        name = data["concept_name"]
        stocks = data["stocks"]
        total = len(stocks)
        sorted_stocks = sorted(stocks, key=lambda s: s.get("total_mv", 0) or 0, reverse=True)
        for rank, s in enumerate(sorted_stocks):
            weight = calc_weight(rank, total)
            concept_stock_weights[s["code"]].append({
                "name": name,
                "weight": weight,
                "stock_name": s["name"],
            })

    theme_stock_weights = defaultdict(list)
    for theme_name, info in theme_info.items():
        concept_weights = info.get("concept_weights", {})
        for concept_name in info["concepts"]:
            cw = concept_weights.get(concept_name, 0.5)
            for code, concepts in concept_stock_weights.items():
                for c in concepts:
                    if c["name"] == concept_name:
                        theme_weight = round(c["weight"] * cw, 2)
                        existing = [t for t in theme_stock_weights[code] if t["name"] == theme_name]
                        if existing:
                            if theme_weight > existing[0]["weight"]:
                                existing[0]["weight"] = theme_weight
                        else:
                            theme_stock_weights[code].append({
                                "name": theme_name,
                                "weight": theme_weight,
                                "stock_name": c["stock_name"],
                            })

    theme_scores = {}
    for theme_name, info in theme_info.items():
        for stock in info.get("members", []):
            code = stock["code"]
            theme_scores.setdefault(code, {})[theme_name] = dict(stock)

    stock_files = {}
    for stock_code in set(list(concept_stock_weights.keys()) + list(theme_stock_weights.keys())):
        concepts = concept_stock_weights.get(stock_code, [])
        themes = theme_stock_weights.get(stock_code, [])

        concepts_sorted = sorted(concepts, key=lambda t: t["weight"], reverse=True)
        themes_sorted = sorted(themes, key=lambda t: theme_scores.get(stock_code, {}).get(t["name"], {}).get("purity_score", 0), reverse=True)

        stock_name = ""
        if concepts_sorted:
            stock_name = concepts_sorted[0]["stock_name"]
        elif themes_sorted:
            stock_name = themes_sorted[0]["stock_name"]

        market = "SH" if stock_code.startswith("sh") else "SZ" if stock_code.startswith("sz") else "BJ"

        core_concept = concepts_sorted[0]["name"] if concepts_sorted else ""

        safe_code = stock_code.lower()
        stock_path = STOCKS_DIR / f"{safe_code}.json"

        theme_entries = []
        for t in themes_sorted:
            entry = {"name": t["name"], "weight": t["weight"]}
            scores = theme_scores.get(stock_code, {}).get(t["name"])
            if scores:
                entry["eligible"] = scores["eligible"]
                entry["member_role"] = scores["member_role"]
                entry["anchor"] = scores.get("anchor", False)
                for score_name in (
                    "purity_score",
                    "industry_score",
                    "candidate_score",
                    "liquidity_score",
                    "market_cap_score",
                ):
                    if score_name in scores:
                        entry[score_name] = scores[score_name]
            theme_entries.append(entry)

        stock_data = {
            "code": stock_code,
            "name": stock_name,
            "market": market,
            "themes": theme_entries,
            "concepts": [{"name": c["name"], "weight": c["weight"]} for c in concepts_sorted],
            "core_concept": core_concept,
            "theme_count": len(themes_sorted),
            "concept_count": len(concepts_sorted),
            "library_version": time.strftime('%Y-%m-%d'),
            "last_update": time.strftime('%Y-%m-%d'),
        }

        _write_json(stock_path, stock_data)

        stock_files[stock_code] = {
            "name": stock_name,
            "core_concept": core_concept,
            "theme_count": len(themes_sorted),
            "concept_count": len(concepts_sorted),
            "themes": theme_entries,
            "concepts": concepts_sorted,
        }

    return stock_files


def build_aliases(theme_info):
    ALIASES_DIR.mkdir(parents=True, exist_ok=True)

    alias_data = {}
    for theme_name, info in sorted(theme_info.items()):
        aliases = info.get("aliases", [])
        if aliases:
            alias_data[theme_name] = aliases

    _write_json(ALIASES_DIR / "theme_aliases.json", alias_data)


def build_indexes(theme_info, concept_info, stock_files):
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    theme_to_concept = {}
    for name, info in theme_info.items():
        theme_to_concept[name] = info["concepts"]
    _write_json(INDEX_DIR / "theme_to_concept.json", theme_to_concept)

    theme_to_stock = {}
    for name, info in theme_info.items():
        theme_to_stock[name] = info["stocks"]
    _write_json(INDEX_DIR / "theme_to_stock.json", theme_to_stock)

    concept_to_stock = {}
    for name, info in concept_info.items():
        concept_to_stock[name] = info["stocks"]
    _write_json(INDEX_DIR / "concept_to_stock.json", concept_to_stock)

    stock_to_theme = {}
    stock_to_concept = {}
    for code, info in stock_files.items():
        stock_to_theme[code] = [t["name"] for t in info.get("themes", [])]
        stock_to_concept[code] = [c["name"] for c in info.get("concepts", [])]
    _write_json(INDEX_DIR / "stock_to_theme.json", stock_to_theme)
    _write_json(INDEX_DIR / "stock_to_concept.json", stock_to_concept)

    keyword_to_theme = {}
    for name, info in theme_info.items():
        for kw in [name] + info.get("aliases", []) + info.get("keywords", []):
            if kw not in keyword_to_theme:
                keyword_to_theme[kw] = name
    _write_json(INDEX_DIR / "keyword_to_theme.json", keyword_to_theme)

    return theme_to_concept, theme_to_stock, concept_to_stock, stock_to_theme, stock_to_concept, keyword_to_theme


def build_update_log(theme_info, concept_info, stock_files):
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    themed_concepts = set()
    for info in theme_info.values():
        themed_concepts.update(info["concepts"])
    unthemed = len(concept_info) - len(themed_concepts & set(concept_info.keys()))

    log_data = {
        "last_build": time.strftime('%Y-%m-%d %H:%M:%S'),
        "library_version": time.strftime('%Y-%m-%d'),
        "industry_ranking_version": "v5",
        "theme_count": len(theme_info),
        "concept_count": len(concept_info),
        "ignored_concept_count": sum(
            info.get("member_fetch_status") == "ignored"
            for info in concept_info.values()
        ),
        "themed_concepts": len(themed_concepts & set(concept_info.keys())),
        "unthemed_concepts": unthemed,
        "stock_count": len(stock_files),
        "top_themes": [
            {"name": name, "stock_count": info["stock_count"]}
            for name, info in sorted(theme_info.items(), key=lambda x: x[1]["stock_count"], reverse=True)[:20]
        ],
    }

    _write_json(METADATA_DIR / "update_log.json", log_data)


def main(argv=None):
    reload_configuration()
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Build theme library from cached data")
    parser.add_argument("--clean", action="store_true", help="Clean existing files before build")
    parser.add_argument("--themes-only", action="store_true", help="Only build theme files")
    parser.add_argument("--concepts-only", action="store_true", help="Only build concept files")
    parser.add_argument("--stocks-only", action="store_true", help="Only build stock files")
    args = parser.parse_args(argv)

    print("Loading cached concept data...")
    referenced_concepts = {
        concept_name
        for theme in THEMES_CONFIG.values()
        for concept_name in theme.get("concepts", [])
    }
    conflicts = sorted(set(MEMBER_FETCH_EXCLUSIONS) & referenced_concepts)
    if conflicts:
        print(
            "Error: member_fetch_exclusions contains theme-referenced concepts: "
            + ", ".join(conflicts)
        )
        return 1
    all_data = load_concept_stocks()
    concepts_map = load_concepts()
    missing = sorted(set(concepts_map) - set(all_data))
    extra = sorted(set(all_data) - set(concepts_map))
    if missing or extra:
        print(
            "Error: concept member cache does not exactly cover concepts.json "
            f"(missing={len(missing)}, extra={len(extra)}). "
            "Run themes concepts fetch-stocks --reset first."
        )
        return 1
    print(f"Loaded {len(all_data)} concept boards.")

    if args.clean:
        import shutil
        for d in [THEMES_DIR, CONCEPTS_DIR, STOCKS_DIR, ALIASES_DIR, INDEX_DIR]:
            if d.exists():
                shutil.rmtree(d)
                d.mkdir(parents=True, exist_ok=True)
        print("Cleaned existing files.")

    concept_info = {}
    theme_info = {}
    stock_files = {}

    if not args.stocks_only:
        print("Building concept files...")
        concept_info = build_concepts(all_data, concepts_map)
        print(f"Built {len(concept_info)} concept files.")

        print("Building theme files (with industry ranking v5)...")
        theme_info = build_themes(all_data, concept_info)
        print(f"Built {len(theme_info)} theme files.")

    if not args.themes_only and not args.concepts_only:
        print("Building stock files...")
        stock_files = build_stocks(all_data, theme_info)
        print(f"Built {len(stock_files)} stock files.")

    if not args.themes_only and not args.concepts_only and not args.stocks_only:
        if not concept_info:
            print("Rebuilding concept info for indexes...")
            all_data = load_concept_stocks()
            concept_info = build_concepts(all_data, concepts_map)
            theme_info = build_themes(all_data, concept_info)
            stock_files = build_stocks(all_data, theme_info)

        print("Building alias file...")
        build_aliases(theme_info)

        print("Building index files...")
        t2c, t2s, c2s, s2t, s2c, k2t = build_indexes(theme_info, concept_info, stock_files)
        print(f"Indexes: {len(t2c)} themes, {len(c2s)} concepts, {len(s2t)} stocks, {len(k2t)} keywords")

        print("Building update log...")
        build_update_log(theme_info, concept_info, stock_files)

    print("\nBuild complete!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
