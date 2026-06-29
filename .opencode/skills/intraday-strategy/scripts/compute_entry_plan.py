#!/usr/bin/env python3
"""Compute Entry Plan for stock pool. V1.1.

Entry Plan answers "can we trade now, and at what price?" — it produces concrete
BuyLo/BuyHi, Stop, Position, EntryMode, PlanStatus. It consumes a Trade Profile
(playbook, anchor preference, chase policy) and real-time market data.

Supports two sessions:
  --session open      (9:25 auction data) — Opening Entry Plan (optional)
  --session intraday  (14:30 live data)   — Tail Entry Plan (primary execution)

Usage:
    python compute_entry_plan.py sh603986 --session open --profile strategy.json --json
    python compute_entry_plan.py sh603986 --session intraday \
      --profile strategy.json --intraday-data features.json --json
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


def position_state(price, ma20, atr, board_streak, high20):
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


def _entry(code, buy_lo, buy_hi, anchor, entry_mode, plan_status,
           tail_action, stop, position, profile_match, profile_note,
           tomorrow_expect=None):
    result = {
        "code": code,
        "can_execute": plan_status == "ACTIONABLE",
        "tail_action": tail_action,
        "buy_lo": buy_lo,
        "buy_hi": buy_hi,
        "anchor": anchor,
        "entry_mode": entry_mode,
        "stop": stop,
        "position": position,
        "profile_match": profile_match,
        "profile_note": profile_note,
    }
    if tomorrow_expect:
        result["tomorrow_expect"] = tomorrow_expect
    return result


def no_entry(code, reason, profile_match="Aligned"):
    return _entry(code, None, None, None, "NO_CHASE", "NO_CHASE",
                  "No Chase", None, 0, profile_match, reason)


def price_from_anchor(anchor, ctx):
    """Compute BuyLo/BuyHi from anchor type. Returns (lo, hi, stop_mult)."""
    price = ctx.get("price")
    ma20 = ctx.get("ma20")
    ma5 = ctx.get("ma5")
    atr = ctx.get("atr")
    open_p = ctx.get("open_price")
    vwap = ctx.get("vwap")
    tail_low = ctx.get("tail_low_30m")
    tail_vwap = ctx.get("tail_vwap_30m")
    open_pct = ctx.get("open_pct", 0)

    if atr is None or atr == 0:
        return None, None, 1.5

    if anchor == "MA20":
        if ma20 is None:
            return None, None, 1.5
        return round(ma20, 2), round(ma20 + 0.5 * atr, 2), 1.5

    if anchor == "MA5":
        if ma5 is None:
            if ma20 is None:
                return None, None, 1.5
            return round(ma20, 2), round(ma20 + 0.5 * atr, 2), 1.5
        return round(ma5, 2), round(ma5 + 0.5 * atr, 2), 1.5

    if anchor == "OPEN":
        if open_p is None:
            return None, None, 1.5
        return round(open_p, 2), round(open_p + 0.3 * atr, 2), 1.5

    if anchor == "MA20_SHIFT":
        if ma20 is None or open_pct is None:
            return None, None, 1.5
        shifted_lo = round(ma20 * (1 + abs(open_pct) / 100), 2)
        return shifted_lo, round(shifted_lo + 0.5 * atr, 2), 1.5

    if anchor == "VWAP":
        if vwap is None:
            return None, None, 1.5
        return round(vwap - 0.3 * atr, 2), round(vwap, 2), 1.5

    if anchor == "TAIL":
        if tail_low is not None and tail_vwap is not None:
            lo_val = max(tail_low, tail_vwap - 0.3 * atr)
            return round(lo_val, 2), round(tail_vwap, 2), 1.5
        if price is not None and ma20 is not None:
            return round(ma20, 2), round(min(price, ma20 + 0.5 * atr), 2), 1.5
        return None, None, 1.5

    return None, None, 1.5


def compute_entry_plan(ctx, profile):
    """Main decision tree. Returns EntryPlan dict or None for skip."""
    tradeability = ctx.get("tradeability")
    tailflow = ctx.get("tail_flow")
    overnight = ctx.get("overnight_score", 0)
    session = ctx.get("session", "intraday")
    code = ctx["code"]

    # ── Pre-filter ──
    if tradeability in ("Avoid", "Extended"):
        return no_entry(code, f"Tradeability={tradeability}", "Invalidated")
    if tailflow == "Outflow":
        return no_entry(code, "TailFlow=Outflow", "Invalidated")
    if overnight < 60 and session == "intraday":
        return no_entry(code, "OvernightScore<60", "Invalidated")

    if profile is None:
        return no_entry(code, "No Trade Profile available", "New")

    playbook = profile.get("playbook", "WATCH_ONLY")
    chase = profile.get("chase_policy", "NO_CHASE")
    anchor_pref = profile.get("preferred_anchor", "MA20")
    budget = profile.get("position_budget", 0.02)
    stop_policy = profile.get("stop_policy", "ATR_1.5")

    atr = ctx.get("atr")
    price = ctx.get("price")
    ma20 = ctx.get("ma20")
    bs = ctx.get("board_streak", 0)
    high20 = ctx.get("high20")
    state = position_state(price, ma20, atr, bs, high20)

    # ── Playbook-specific logic ──

    if playbook == "WATCH_ONLY":
        return no_entry(code, "Playbook=WATCH_ONLY", "Aligned")

    if playbook == "DEFENSIVE":
        if session == "open" and ctx.get("wait_r70", False):
            return _entry(code, None, None, anchor_pref, "WAIT", "WAIT",
                          "Wait", None, 0, "Aligned", "R70: wait for morning dip")
        anchor = anchor_pref

    elif playbook == "LIMIT_UP_CONT" and session == "open":
        anchor = "OPEN"
        stop_policy = "PCT_R35"

    elif playbook == "MOMENTUM":
        anchor = "MA5"

    else:
        anchor = anchor_pref

    # ── Chase policy check ──
    if chase == "NO_CHASE" and state == "EXTENDED":
        return no_entry(code, f"NO_CHASE + {state}", "Aligned")

    # ── Compute prices ──
    lo, hi, stop_mult = price_from_anchor(anchor, ctx)
    if lo is None or hi is None:
        return no_entry(code, f"Cannot compute {anchor} zone (missing data)",
                        "Degraded")

    # ── Check if current price already above zone ──
    if session == "intraday" and price is not None:
        if price > lo + 1.0 * (atr or 0):
            return no_entry(code, f"Price {price:.1f} > zone_hi+ATR, no chase",
                            "Degraded")

    # ── Compute stop ──
    if stop_policy == "PCT_R35":
        stop = round(price * 0.97, 2) if price else None
    elif stop_policy == "ATR_2.0":
        stop = round(lo - 2.0 * atr, 2) if (atr and lo) else None
    else:
        stop = round(lo - 1.5 * atr, 2) if (atr and lo) else None

    # ── EntryMode & position ──
    if session == "intraday" and tradeability == "Suitable" and overnight >= 75:
        if state == "PULLBACK":
            mode = "TAIL_PROBE"
            position = min(0.02, budget)
        elif state == "TREND":
            mode = "TAIL_PROBE"
            position = min(0.015, budget)
        else:
            return no_entry(code, f"Intraday {state} not actionable",
                            "Degraded")
    elif session == "open":
        mode = "OPEN_PROBE" if playbook == "LIMIT_UP_CONT" else "LIMIT_IN_ZONE"
        position = budget if playbook != "WATCH_ONLY" else 0
        if playbook == "LIMIT_UP_CONT":
            position = min(0.01, budget)
    else:
        mode = "WAIT"
        position = 0

    tail_action = "Recommend" if position > 0.01 else "Light" if position > 0 else "Wait"

    return _entry(code, lo, hi, anchor, mode, "ACTIONABLE",
                  tail_action, stop, round(position, 4),
                  "Aligned", f"{playbook} via {anchor}")


def load_indicators(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        pool = json.load(f)
    return {e["code"]: e for e in pool}


def load_profiles(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    return {p["code"]: p for p in profiles}


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Compute Entry Plan for stock pool")
    parser.add_argument("codes", help="Comma-separated stock codes")
    parser.add_argument("--session", choices=["open", "intraday"],
                        default="intraday", help="Session mode")
    parser.add_argument("--profile", metavar="FILE",
                        help="Trade Profile JSON file")
    parser.add_argument("--indicators", metavar="FILE",
                        help="Pool indicators JSON file (V5 nested)")
    parser.add_argument("--intraday-data", metavar="FILE",
                        help="Intraday features JSON (for --session intraday)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON array")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="Save output to file")

    args = parser.parse_args()
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]

    indicators_map = {}
    if args.indicators:
        indicators_map = load_indicators(args.indicators)

    profiles_map = {}
    if args.profile:
        profiles_map = load_profiles(args.profile)

    intraday_map = {}
    if args.intraday_data:
        with open(args.intraday_data, "r", encoding="utf-8") as f:
            idata = json.load(f)
        intraday_map = {e.get("code", ""): e for e in idata}

    plans = []
    for code in codes:
        entry = indicators_map.get(code, {})
        if entry.get("fetch_failed"):
            plans.append(no_entry(code, "indicators fetch failed", "New"))
            continue

        raw = entry.get("raw_observation", {})
        id_row = intraday_map.get(code, {})
        profile = profiles_map.get(code)

        ctx = {
            "code": code,
            "session": args.session,
            "price": _raw_val(raw, "price"),
            "open_price": id_row.get("open") or _raw_val(raw, "price"),
            "open_pct": id_row.get("open_pct") or _raw_val(raw, "change_pct"),
            "ma20": _raw_val(raw, "ma20"),
            "ma5": _raw_val(raw, "ma5"),
            "atr": _raw_val(raw, "atr"),
            "board_streak": _raw_val(raw, "board_streak") or 0,
            "high20": _raw_val(raw, "high20"),
            "tradeability": id_row.get("tradeability"),
            "tail_flow": id_row.get("tail_flow"),
            "overnight_score": id_row.get("overnight_score", 0),
            "vwap": id_row.get("vwap"),
            "tail_low_30m": id_row.get("tail_low_30m"),
            "tail_vwap_30m": id_row.get("tail_vwap_30m"),
        }

        result = compute_entry_plan(ctx, profile)
        plans.append(result)

    if args.json:
        output_str = json.dumps(plans, ensure_ascii=False, indent=2)
    else:
        lines = ["Code        BuyLo    BuyHi    Anchor  Mode            Status      Pos%   Stop     Match"]
        lines.append("-" * 90)
        for p in plans:
            lo = f"{p['buy_lo']:>8.2f}" if p['buy_lo'] else "       —"
            hi = f"{p['buy_hi']:>8.2f}" if p['buy_hi'] else "       —"
            stop = f"{p['stop']:>8.2f}" if p['stop'] else "       —"
            lines.append(
                f"{p['code']:<12} {lo} {hi} "
                f"{p.get('anchor') or '—':<7} "
                f"{p['entry_mode']:<14} {p.get('plan_status', 'NO_CHASE'):<12} "
                f"{p['position']:>4.2%}  {stop}  {p['profile_match']}"
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
