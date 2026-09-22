#!/usr/bin/env python3
"""Side-car limit-up cluster ST screen (informational only).

Dispatched by the orchestrating agent after the intraday overnight compute run
finishes, and reuses the Phase-0 all-stocks snapshot. It is deliberately not
part of ``automation intraday run`` because per-candidate K-line history makes it
slow. This screen never feeds the mapper, selection pools, or overnight
strategy; it only publishes a standalone JSON contract.

Locked filter (see config/screen-config.json):

    1. change_pct in [3.0, 6.0]           (inclusive)
    2. turnover in [5.0, 15.0]            (inclusive)
    3. belongs to an East Money concept whose *main-board, non-ST* limit-up
       member count is >= 3 (ChiNext/STAR/BSE excluded from the count)
    4. had at least one limit-up within the last 10 trading bars
    5. board scope excludes sh688 (STAR) and bj (BSE)
    6. candidates are ordinary stocks and ST/*ST names (`st_only` defaults off)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from ashare_pilot.market_data._commands.history import fetch_history
from ashare_pilot.market_data.runtime import workspace_path
from ashare_pilot.mapping.intraday_contract import limit_ratio, read_json, utc_now_iso

SCREEN_SCHEMA_VERSION = "limit_up_cluster_screen.v1"

DEFAULT_CONFIG: dict[str, Any] = {
    "chg_min": 3.0,
    "chg_max": 6.0,
    "turnover_min": 5.0,
    "turnover_max": 15.0,
    "min_limit_ups": 3,
    "history_window": 10,
    "st_only": False,
    "pseudo_concepts": [
        "低价股",
        "微利股",
        "百元股",
        "高市净率",
        "低市净率",
        "红利股",
        "红利破净股",
        "长期破净",
        "破净股",
        "破发股",
        "破增发价股",
        "超跌股",
        "反转股",
        "趋势股",
        "历史新高",
        "近期新高",
        "百日新高",
        "次新股",
        "近期摘帽",
        "ST股",
        "昨日打二板以上表现",
        "昨日炸板",
        "昨日高换手",
        "昨日涨停",
        "昨日涨停_含一字",
        "昨日连板",
        "昨日连板_含一字",
        "昨日首板",
        "最近多板",
        "昨日高振幅",
        "昨日触板",
        "2025三季报扭亏",
        "2025三季报预减",
        "2025三季报预增",
        "2026一季报扭亏",
        "2026一季报预减",
        "2026一季报预增",
        "2026中报扭亏",
        "2026中报预减",
        "2026中报预增",
        "2026中报首亏",
        "QFII重仓",
        "基金重仓",
        "社保重仓",
        "机构重仓",
        "券商金股",
        "证金持股",
        "养老金",
        "沪股通",
        "深股通",
        "融资融券",
        "转债标的",
        "密集调研",
        "举牌",
        "股权分散",
        "股权集中",
        "股权转让",
        "股权激励",
        "参股保险",
        "参股券商",
        "参股新三板",
        "参股期货",
        "参股银行",
        "大盘价值",
        "大盘成长",
        "大盘股",
        "中盘价值",
        "中盘成长",
        "中盘股",
        "小盘价值",
        "小盘成长",
        "小盘股",
        "微盘股",
        "微盘精选",
        "价值股",
        "高成长股",
        "权重股",
        "周期股",
        "先进制造风格",
        "医药医疗风格",
        "消费风格",
        "科技风格",
        "金融地产风格",
        "行业龙头",
        "超级品牌",
        "茅指数",
        "宁组合",
        "中字头",
        "中特估",
        "专精特新",
        "独角兽",
        "AB股",
        "AH股",
        "B股",
        "GDR",
        "MSCI中国",
        "富时罗素",
        "标准普尔",
        "HS300_",
        "上证50_",
        "上证180_",
        "上证380",
        "中证500",
        "深成500",
        "深证100R",
        "创业成份",
        "创业板综",
        "央视50_",
        "科创板做市商",
        "科创板做市股",
        "北交所概念",
        "东方财富热股",
        "题材股",
        "央国企改革",
        "一带一路",
        "上海自贸",
        "东北振兴",
        "乡村振兴",
        "京津冀",
        "成渝特区",
        "新型城镇化",
        "沪企改革",
        "深圳特区",
        "湖北自贸",
        "滨海新区",
        "粤港自贸",
        "统一大市场",
        "西部大开发",
        "长江三角",
        "雄安新区",
    ],
}

HistoryProvider = Callable[[str], list[dict] | None]


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    config_path = Path(path) if path else Path(workspace_path("config", "screen-config.json"))
    if config_path.exists():
        loaded = read_json(config_path)
        if isinstance(loaded, dict):
            config.update(loaded)
    return config


def to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace("%", "").replace("+", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def prefix_code(code: Any, market: Any = None) -> str:
    """Normalize a bare East Money code to a ``sh``/``sz``/``bj`` code."""
    text = str(code or "").strip()
    if text[:2] in ("sh", "sz", "bj"):
        return text
    if market == 2 or (len(text) == 6 and text[:1] in ("4", "8")) or text[:2] == "92":
        return "bj" + text
    if text[:1] == "6":
        return "sh" + text
    return "sz" + text


def board_of(code: str) -> str:
    if code.startswith("sh688"):
        return "STAR"
    if code.startswith("sz30"):
        return "ChiNext"
    if code.startswith("bj"):
        return "BSE"
    return "Main"


def is_st(name: Any) -> bool:
    return "ST" in str(name or "").upper().replace(" ", "")


def limit_bounds(ratio: float) -> tuple[float, float]:
    base = ratio * 100.0
    return base - 0.5, base + 1.0


def is_limit_up(change_pct: float | None, ratio: float) -> bool:
    if change_pct is None:
        return False
    low, high = limit_bounds(ratio)
    return low <= change_pct <= high


def _ratio(code: str, name: str) -> float:
    return float(limit_ratio(code, name))


def run_screen(
    all_stocks: list[dict[str, Any]],
    concept_to_stock: dict[str, list[str]],
    config: dict[str, Any],
    history_provider: HistoryProvider | None = None,
    snapshot_meta: dict[str, Any] | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Run the deterministic screen over already-loaded inputs."""
    pseudo = set(config.get("pseudo_concepts") or [])
    min_limit_ups = int(config.get("min_limit_ups", 3))
    window = int(config.get("history_window", 10))
    chg_min = float(config.get("chg_min", 3.0))
    chg_max = float(config.get("chg_max", 6.0))
    turnover_min = float(config.get("turnover_min", 5.0))
    turnover_max = float(config.get("turnover_max", 15.0))
    st_only = bool(config.get("st_only", True))

    market_limit_ups: set[str] = set()
    main_limit_ups: set[str] = set()
    by_code: dict[str, dict[str, Any]] = {}
    for stock in all_stocks:
        if not isinstance(stock, dict):
            continue
        code = prefix_code(stock.get("code"), stock.get("market"))
        by_code[code] = stock
        change_pct = to_float(stock.get("chg_pct"))
        ratio = _ratio(code, stock.get("name", ""))
        if is_limit_up(change_pct, ratio):
            market_limit_ups.add(code)
            if board_of(code) == "Main" and not is_st(stock.get("name")):
                main_limit_ups.add(code)

    qualifying: dict[str, list[str]] = {}
    for name, members in concept_to_stock.items():
        if name in pseudo or not isinstance(members, list):
            continue
        hits = [member for member in members if member in main_limit_ups]
        if len(hits) >= min_limit_ups:
            qualifying[name] = hits

    candidates_concepts: dict[str, set[str]] = defaultdict(set)
    for name in qualifying:
        for member in concept_to_stock.get(name, []):
            candidates_concepts[member].add(name)

    candidates: list[dict[str, Any]] = []
    for code, concepts in candidates_concepts.items():
        stock = by_code.get(code)
        if stock is None:
            continue
        board = board_of(code)
        if board in ("STAR", "BSE"):
            continue
        if st_only and not is_st(stock.get("name")):
            continue
        turnover = to_float(stock.get("turnover"))
        change_pct = to_float(stock.get("chg_pct"))
        if turnover is None or change_pct is None:
            continue
        if not (turnover_min <= turnover <= turnover_max):
            continue
        if not (chg_min <= change_pct <= chg_max):
            continue
        candidates.append(
            {
                "code": code,
                "name": stock.get("name"),
                "board": board,
                "is_st": is_st(stock.get("name")),
                "turnover": round(turnover, 2),
                "chg_pct": round(change_pct, 2),
                "concepts": sorted(concepts, key=lambda n: -len(qualifying.get(n, []))),
            }
        )

    kept: list[dict[str, Any]] = []
    history_failed: list[str] = []
    no_recent_limit_up: list[str] = []
    if history_provider is None:
        history_provider = _default_history_provider(date, window=window)

    for candidate in candidates:
        code = candidate["code"]
        try:
            records = history_provider(code)
        except Exception:
            records = None
        if not records:
            history_failed.append(code)
            continue
        threshold = _ratio(code, candidate.get("name", "")) * 100.0 - 0.5
        recent = records[-window:] if window > 0 else records
        freq = sum(
            1
            for row in recent
            if (value := to_float(row.get("change_pct"))) is not None and value >= threshold
        )
        if freq >= 1:
            kept.append({**candidate, "limit_up_freq": freq})
        else:
            no_recent_limit_up.append(code)

    kept.sort(key=lambda item: (-item["limit_up_freq"], -item["turnover"]))
    status = "complete" if kept else "empty"
    return {
        "schema_version": SCREEN_SCHEMA_VERSION,
        "date": date,
        "generated_at": utc_now_iso(),
        "status": status,
        "snapshot": snapshot_meta or {},
        "params": {
            "chg_min": chg_min,
            "chg_max": chg_max,
            "turnover_min": turnover_min,
            "turnover_max": turnover_max,
            "min_limit_ups": min_limit_ups,
            "history_window": window,
            "st_only": st_only,
            "pseudo_concepts": sorted(pseudo),
        },
        "summary": {
            "stock_count": len(by_code),
            "market_limit_up_count": len(market_limit_ups),
            "main_non_st_limit_up_count": len(main_limit_ups),
            "qualifying_concept_count": len(qualifying),
            "candidate_count": len(candidates),
            "final_count": len(kept),
            "history_failed_count": len(history_failed),
        },
        "concepts": [
            {"name": name, "main_limit_up_count": len(hits), "members": hits}
            for name, hits in sorted(qualifying.items(), key=lambda kv: -len(kv[1]))
        ],
        "candidates": kept,
        "dropped": {
            "history_failed": history_failed,
            "no_recent_limit_up": no_recent_limit_up,
        },
    }


def _history_range(window: int) -> str:
    """Calendar range that comfortably covers ``window`` trading bars."""
    days = max(int(window or 0), 1) * 2 + 10
    return f"{days}d"


def _default_history_provider(
    date: str | None,
    use_cache: bool = True,
    window: int = DEFAULT_CONFIG["history_window"],
) -> HistoryProvider:
    range_str = _history_range(window)

    def provider(code: str) -> list[dict] | None:
        return fetch_history(code, end=date, range_str=range_str, use_cache=use_cache)

    return provider


def build_from_files(
    date: str,
    all_stocks_path: str | Path | None = None,
    config_path: str | Path | None = None,
    concept_index_path: str | Path | None = None,
    history_provider: HistoryProvider | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Load the intraday snapshot and concept index, then run the screen."""
    snapshot_path = (
        Path(all_stocks_path)
        if all_stocks_path
        else Path(workspace_path(".cache", "intraday", date, "all_stocks_cache.json"))
    )
    index_path = (
        Path(concept_index_path)
        if concept_index_path
        else Path(workspace_path("data", "theme-library", "index", "concept_to_stock.json"))
    )
    config = load_config(config_path)

    if not snapshot_path.exists():
        return _unavailable(date, f"missing snapshot: {snapshot_path}")
    try:
        snapshot = read_json(snapshot_path)
    except (OSError, ValueError) as exc:
        return _unavailable(date, f"snapshot unreadable: {type(exc).__name__}")
    if not isinstance(snapshot, dict):
        return _unavailable(date, "snapshot root must be an object")

    all_stocks = snapshot.get("stocks")
    if not isinstance(all_stocks, list):
        return _unavailable(date, "snapshot.stocks must be an array")
    quality = snapshot.get("status")
    snapshot_meta = {
        "source": str(snapshot_path),
        "source_kind": snapshot.get("source"),
        "fetched_at": snapshot.get("fetched_at"),
        "stock_count": len(all_stocks),
        "status": quality,
    }
    if quality not in (None, "complete"):
        return _unavailable(date, f"snapshot status is {quality}", snapshot_meta)

    if not index_path.exists():
        return _unavailable(date, f"missing concept index: {index_path}", snapshot_meta)
    try:
        concept_to_stock = read_json(index_path)
    except (OSError, ValueError) as exc:
        return _unavailable(date, f"concept index unreadable: {type(exc).__name__}")
    if not isinstance(concept_to_stock, dict):
        return _unavailable(date, "concept index root must be an object", snapshot_meta)

    if history_provider is None:
        history_provider = _default_history_provider(
            date,
            use_cache=use_cache,
            window=int(config.get("history_window", DEFAULT_CONFIG["history_window"])),
        )

    result = run_screen(
        all_stocks,
        concept_to_stock,
        config,
        history_provider=history_provider,
        snapshot_meta=snapshot_meta,
        date=date,
    )
    return result


def _unavailable(
    date: str,
    error: str,
    snapshot_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCREEN_SCHEMA_VERSION,
        "date": date,
        "generated_at": utc_now_iso(),
        "status": "unavailable",
        "error": error,
        "snapshot": snapshot_meta or {},
        "params": {},
        "summary": {},
        "concepts": [],
        "candidates": [],
        "dropped": {"history_failed": [], "no_recent_limit_up": []},
    }


def to_table(result: dict[str, Any]) -> str:
    if result.get("status") == "unavailable":
        return f"[unavailable] {result.get('error')}"
    summary = result.get("summary", {})
    lines = [
        f"date={result.get('date')} status={result.get('status')} "
        f"concepts={summary.get('qualifying_concept_count')} "
        f"candidates={summary.get('final_count')} "
        f"(filtered={summary.get('candidate_count')})"
    ]
    header = f"{'code':<10} {'name':<12} {'chg%':>7} {'turnover%':>10} {'10d':>4}  concepts"
    lines.append(header)
    lines.append("-" * len(header))
    for item in result.get("candidates", []):
        lines.append(
            f"{item['code']:<10} {str(item.get('name')):<12} "
            f"{item.get('chg_pct'):>7} {item.get('turnover'):>10} "
            f"{item.get('limit_up_freq'):>4}  {'/'.join(item.get('concepts', []))}"
        )
    if not result.get("candidates"):
        lines.append("(no candidates)")
    return "\n".join(lines)


def main(argv=None) -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Side-car limit-up cluster ST screen (informational only)"
    )
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--all-stocks", help="Path to all_stocks_cache.json")
    parser.add_argument("--config", help="Path to screen-config.json")
    parser.add_argument("--concept-index", help="Path to concept_to_stock.json")
    parser.add_argument("--no-cache", action="store_true", help="Disable K-line cache")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args(argv)

    result = build_from_files(
        args.date,
        all_stocks_path=args.all_stocks,
        config_path=args.config,
        concept_index_path=args.concept_index,
        use_cache=not args.no_cache,
    )

    output_str = (
        json.dumps(result, ensure_ascii=False, indent=2)
        if args.json
        else to_table(result)
    )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_str + "\n", encoding="utf-8")
        print(f"Saved to {args.output}")
    else:
        print(output_str)
    return 0 if result.get("status") != "unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
