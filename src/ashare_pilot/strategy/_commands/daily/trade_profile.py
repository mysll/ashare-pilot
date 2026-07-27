#!/usr/bin/env python3
"""Compute Trade Profile for stock pool. V1.1.

Trade Profile answers "what style to trade" — it produces playbook, anchor
preference, chase policy, position budget, and invalidation conditions.
It does NOT produce Buy Zone / Stop / Target prices (those are Entry Plan territory).

Usage:
    python compute_trade_profile.py sh603986,sz000977 --regime strong-sector --json
    python compute_trade_profile.py sh603986 --regime neutral --json -o profile.json
"""

import argparse
import json
import sys
from pathlib import Path

def _raw_val(raw, field):
    """Extract value from V5 raw_observation[field]."""
    if isinstance(raw, dict):
        entry = raw.get(field, {})
        return entry.get("value") if isinstance(entry, dict) else entry
    return raw.get(field)


def _cp_val(cp, field):
    """Extract value from V5 computed_perception[field]."""
    entry = cp.get(field, {})
    return entry.get("value") if isinstance(entry, dict) else entry


def position_state(price, ma20, atr, board_streak, high20):
    """Recompute position_state from Trade-Profile inputs."""
    if price is None or ma20 is None or atr is None or atr == 0:
        return None
    da = (price - ma20) / atr
    if da <= 1.0:
        state = "PULLBACK"
    elif da <= 2.5:
        state = "TREND"
    else:
        state = "EXTENDED"
    if (board_streak is not None and board_streak >= 2 and
            high20 is not None and price is not None and
            price >= high20 * 0.98):
        state = "EXTENDED"
    return state


def _profile(code, playbook, anchor, chase, entry_window,
             stop_policy, time_horizon, position_tier,
             invalidation, note, ref_ma20, ref_ma5, ref_high20,
             max_extension_atr=2.5):
    return {
        "code": code,
        "playbook": playbook,
        "preferred_anchor": anchor,
        "chase_policy": chase,
        "entry_window": entry_window,
        "stop_policy": stop_policy,
        "time_horizon": time_horizon,
        "position_tier": position_tier,
        "invalidation": invalidation,
        "note": note,
        "ref_ma20": ref_ma20,
        "ref_ma5": ref_ma5,
        "ref_high20": ref_high20,
        "max_extension_atr": max_extension_atr,
    }


def compute_trade_profile(code, raw_obs, cp, regime, mainline,
                          sector_heat, kcb_pct, sector_pct,
                          open_pct=None):
    """Decision tree: Produce Trade Profile (no prices)."""
    price = _raw_val(raw_obs, "price")
    ma20 = _raw_val(raw_obs, "ma20")
    ma5 = _raw_val(raw_obs, "ma5")
    atr = _raw_val(raw_obs, "atr")
    high20 = _raw_val(raw_obs, "high20")
    bs = _raw_val(raw_obs, "board_streak")
    ylu = _raw_val(raw_obs, "yesterday_limit_up")

    state = position_state(price, ma20, atr, bs, high20)
    ref_ma20 = round(ma20, 2) if ma20 else None
    ref_ma5 = round(ma5, 2) if ma5 else None
    ref_high20 = round(high20, 2) if high20 else None

    # ── Decision tree (§7.2) ──

    # 1. Weak / Panic regime
    if regime in ("weak", "panic"):
        if state == "PULLBACK":
            return _profile(code,
                playbook="DEFENSIVE", anchor="MA20",
                chase="NO_CHASE", entry_window="MORNING_DIP",
                stop_policy="ATR_2.0", time_horizon="T+1",
                position_tier="LIGHT",
                invalidation="大盘继续恶化或个股破MA20",
                note="R70 弱市观测30min",
                ref_ma20=ref_ma20, ref_ma5=ref_ma5,
                ref_high20=ref_high20)
        return _profile(code,
            playbook="WATCH_ONLY", anchor="FLEX",
            chase="NO_CHASE", entry_window="TAIL",
            stop_policy="ATR_2.0", time_horizon="T+1",
            position_tier="WATCH_ONLY",
            invalidation="弱市无交易信号",
            note="弱/恐慌市场, 仅观察",
            ref_ma20=ref_ma20, ref_ma5=ref_ma5,
            ref_high20=ref_high20)

    # 2. Limit-up continuation (R35-v4)
    if ylu and mainline and sector_heat and sector_heat >= 4:
        return _profile(code,
            playbook="LIMIT_UP_CONT", anchor="OPEN",
            chase="OPEN_PROBE_OK", entry_window="OPEN",
            stop_policy="PCT_R35", time_horizon="T+1",
            position_tier="STANDARD",
            invalidation="板块热度<4★或炸板",
            note="R35-v4 涨停延续试探",
            ref_ma20=ref_ma20, ref_ma5=ref_ma5,
            ref_high20=ref_high20)

    # 3. Momentum (R68)
    if mainline and ((kcb_pct is not None and kcb_pct > 2.0) or
                     (sector_pct is not None and sector_pct > 2.5)):
        return _profile(code,
            playbook="MOMENTUM", anchor="MA5",
            chase="MA5_ONLY", entry_window="OPEN",
            stop_policy="ATR_1.5", time_horizon="T+1",
            position_tier="STANDARD",
            invalidation="板块涨幅<2%或科创50回落",
            note="R68 强势主线MA5基准",
            ref_ma20=ref_ma20, ref_ma5=ref_ma5,
            ref_high20=ref_high20,
            max_extension_atr=2.5)

    # 4. Extended — don't chase
    if state == "EXTENDED":
        return _profile(code,
            playbook="WATCH_ONLY", anchor="FLEX",
            chase="NO_CHASE", entry_window="TAIL",
            stop_policy="ATR_1.5", time_horizon="T+1",
            position_tier="WATCH_ONLY",
            invalidation="位置过高, 等尾盘或次日回踩",
            note="EXTENDED 不追高",
            ref_ma20=ref_ma20, ref_ma5=ref_ma5,
            ref_high20=ref_high20)

    # 5. Default: PULLBACK
    return _profile(code,
        playbook="PULLBACK", anchor="MA20",
        chase="NO_CHASE", entry_window="ANY",
        stop_policy="ATR_1.5", time_horizon="T+1",
        position_tier="STANDARD",
        invalidation="跌破MA20且板块热度<3★",
        note="震荡回踩MA20",
        ref_ma20=ref_ma20, ref_ma5=ref_ma5,
        ref_high20=ref_high20)


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Compute Trade Profile for stock pool"
    )
    parser.add_argument("codes", help="Comma-separated stock codes")
    parser.add_argument("--regime", default="neutral",
                        choices=["panic", "weak", "neutral", "strong-sector"],
                        help="Market regime (default: neutral)")
    parser.add_argument("--mainline", action="store_true",
                        help="Flag: stock belongs to mainline theme")
    parser.add_argument("--sector-heat", type=float, default=None,
                        help="Sector theme heat (0-100)")
    parser.add_argument("--kcb-pct", type=float, default=None,
                        help="科创50 change%%")
    parser.add_argument("--sector-pct", type=float, default=None,
                        help="Sector/plate change%%")
    parser.add_argument("--open-pct", type=float, default=None,
                        help="Open auction change pct (optional, for 9:25+)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON array")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="Save output to file")
    parser.add_argument("--from-indicators", metavar="FILE",
                        help="Read V5 pool indicators JSON file instead of fetching")
    parser.add_argument("--source", choices=["sohu", "sina"], default="sina",
                        help="Data source (default: sina, only if fetching)")

    args = parser.parse_args(argv)
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]

    # Load indicators data
    indicators_data = {}
    if args.from_indicators:
        with open(args.from_indicators, "r", encoding="utf-8") as f:
            pool = json.load(f)
        if not pool:
            print("[ERROR] Indicators file is empty", file=sys.stderr)
            sys.exit(1)
        for i, entry in enumerate(pool):
            if not isinstance(entry, dict) or "code" not in entry:
                first_key = list(entry.keys())[0] if isinstance(entry, dict) else type(entry).__name__
                print(
                    f"[ERROR] Entry [{i}] missing 'code' key (found: {first_key}). "
                    f"Pool format mismatch: `fetch_indicators.py` produces K-line records — "
                    f"use `fetch_pool_indicators.py` instead for V5 nested format.",
                    file=sys.stderr,
                )
                sys.exit(1)
            indicators_data[entry["code"]] = entry
    else:
        # For standalone use, we require --from-indicators
        print("[ERROR] Use --from-indicators to provide pool indicators JSON", file=sys.stderr)
        sys.exit(1)

    profiles = []
    for code in codes:
        entry = indicators_data.get(code)
        if not entry or entry.get("fetch_failed"):
            profiles.append({
                "code": code, "fetch_failed": True,
                "playbook": "WATCH_ONLY",
                "note": "indicators fetch failed — default WATCH_ONLY",
            })
            continue

        raw = entry.get("raw_observation", {})
        cp = entry.get("computed_perception", {})

        profile = compute_trade_profile(
            code=code,
            raw_obs=raw,
            cp=cp,
            regime=args.regime,
            mainline=args.mainline,
            sector_heat=args.sector_heat,
            kcb_pct=args.kcb_pct,
            sector_pct=args.sector_pct,
            open_pct=args.open_pct,
        )
        profiles.append(profile)

    if args.json:
        output_str = json.dumps(profiles, ensure_ascii=False, indent=2)
    else:
        lines = ["Code        Playbook       Anchor  Chase          Position    Stop     Invalidation"]
        lines.append("-" * 80)
        for p in profiles:
            lines.append(
                f"{p['code']:<12} {p['playbook']:<14} {p['preferred_anchor']:<7} "
                f"{p['chase_policy']:<14} {p['position_tier']:<11} "
                f"{p['stop_policy']:<8} {p.get('invalidation', '-')[:30]}"
            )
        output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
