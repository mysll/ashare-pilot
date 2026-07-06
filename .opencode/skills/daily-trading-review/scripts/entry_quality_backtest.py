#!/usr/bin/env python3
"""Entry-quality analyzer for the Schema-Locked verification tables.

Reads memory/daily/{date}/verification.md, finds the schema-locked
「买入结果表」(see daily-trading-review SKILL §3a), computes entry-relative
quality metrics from RAW prices, and aggregates by 策略 and by 首根K确认.

It is ALSO the format validator: a verification file whose buy table does not
match the locked column signature is reported as a SCHEMA VIOLATION.

Locked columns (order-independent, all mandatory):
  代码 | 名称 | 评级 | 策略 | 入场锚 | 开盘 | 最低 | 盘中最高 | 收盘 | 触及 | 首根K确认 | 利润给回% | 结果

Derived (computed here, never hand-filled):
  MAE%  = (最低 - 入场锚)/入场锚 * 100      被套幅度 (filled only)
  持收% = (收盘 - 入场锚)/入场锚 * 100      hold-to-close return
  给回% = (盘中最高 - 收盘)/入场锚 * 100    profit give-back

Usage:
  python entry_quality_backtest.py                 # all files
  python entry_quality_backtest.py --since 2026-07-06
"""
import re, sys, glob, os, argparse, statistics as st

sys.stdout.reconfigure(encoding="utf-8")

MANDATORY = ["代码", "策略", "入场锚", "开盘", "最低", "盘中最高", "收盘", "触及", "首根K确认", "结果"]

def to_f(s):
    if s is None: return None
    m = re.search(r"-?\d+\.?\d*", s.replace(",", ""))
    return float(m.group()) if m else None

def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]

def parse_anchor(cell):
    """'MA20:41.62' / 'MA5：899.81' / '追入:66.06' / '—' -> (kind, price)."""
    if not cell or cell.strip() in ("—", "-", ""): return (None, None)
    c = cell.replace("：", ":")
    if ":" in c:
        kind, val = c.split(":", 1)
        return (kind.strip().upper(), to_f(val))
    return ("ZONE", to_f(c))

def parse_file(fp):
    """Return (records, violations)."""
    with open(fp, encoding="utf-8") as f:
        lines = f.read().splitlines()
    date = fp.split(os.sep)[-2]
    recs, violations = [], []
    # locate the buy table: a header row mentioning 代码 and 收盘 and 结果
    found_buy = False
    for i, ln in enumerate(lines):
        if ln.count("|") >= 6 and "代码" in ln and "收盘" in ln and "结果" in ln:
            hdr = split_row(ln)
            missing = [c for c in MANDATORY if not any(c in h for h in hdr)]
            found_buy = True
            if missing:
                violations.append(f"{date}: buy table missing columns {missing}")
                continue
            idx = {c: next(j for j, h in enumerate(hdr) if c in h) for c in MANDATORY}
            j = i + 2  # skip separator
            while j < len(lines) and lines[j].count("|") >= 6 and "---" not in lines[j]:
                cells = split_row(lines[j])
                if len(cells) < len(hdr): j += 1; continue
                code = cells[idx["代码"]]
                if not re.match(r"(sh|sz)\d{6}", code): j += 1; continue
                kind, anchor = parse_anchor(cells[idx["入场锚"]])
                recs.append(dict(
                    date=date, code=code, strat=cells[idx["策略"]],
                    anchor_kind=kind, anchor=anchor,
                    open=to_f(cells[idx["开盘"]]), low=to_f(cells[idx["最低"]]),
                    high=to_f(cells[idx["盘中最高"]]), close=to_f(cells[idx["收盘"]]),
                    touched=cells[idx["触及"]].strip(),
                    confirm=cells[idx["首根K确认"]].strip(),
                    result=cells[idx["结果"]].strip()))
                j += 1
            break
    if not found_buy:
        violations.append(f"{date}: no buy-results table found")
    return recs, violations

def metrics(r):
    e = r["anchor"]
    filled = r["touched"] in ("是", "Y", "yes") and e
    r["filled"] = bool(filled)
    if filled and e:
        if r["low"] is not None:  r["mae"]  = (r["low"] - e) / e * 100
        if r["close"] is not None: r["hold"] = (r["close"] - e) / e * 100
        if r["high"] is not None and r["close"] is not None:
            r["giveback"] = (r["high"] - r["close"]) / e * 100
    return r

def summarize(rows, label):
    filled = [r for r in rows if r.get("filled") and r.get("hold") is not None]
    if not filled:
        print(f"\n== {label}: no filled trades"); return
    holds = [r["hold"] for r in filled]
    maes  = [r["mae"] for r in filled if r.get("mae") is not None]
    gbs   = [r["giveback"] for r in filled if r.get("giveback") is not None]
    win   = sum(1 for h in holds if h > 0) / len(holds) * 100
    brk   = sum(1 for h in holds if h <= -1.5) / len(holds) * 100
    print(f"\n== {label}  (filled n={len(filled)})")
    print(f"   持收%  mean {st.mean(holds):+6.2f}  median {st.median(holds):+.2f}")
    if maes: print(f"   MAE%   mean {st.mean(maes):+6.2f}  median {st.median(maes):+.2f}  worst {min(maes):+.2f}")
    if gbs:  print(f"   给回%  mean {st.mean(gbs):+6.2f}  median {st.median(gbs):+.2f}")
    print(f"   胜率(持收>0) {win:5.0f}%   击穿率(持收<=-1.5%) {brk:5.0f}%")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="only files with date >= YYYY-MM-DD")
    ap.add_argument("--glob", default="memory/daily/*/verification.md")
    args = ap.parse_args()

    files = sorted(glob.glob(args.glob))
    if args.since:
        files = [f for f in files if f.split(os.sep)[-2] >= args.since]

    all_recs, all_viol = [], []
    for fp in files:
        recs, viol = parse_file(fp)
        all_recs += [metrics(r) for r in recs]
        all_viol += viol

    print(f"Scanned {len(files)} files -> {len(all_recs)} conforming rows")
    if all_viol:
        print(f"\n⚠️  SCHEMA VIOLATIONS ({len(all_viol)}) — files not yet on locked format:")
        for v in all_viol: print("   " + v)

    if not all_recs:
        print("\nNo conforming rows yet. New locked-format files will populate this.")
        return

    print("\n" + "=" * 66)
    print("ENTRY QUALITY BY 策略")
    print("=" * 66)
    for s in ["趋势跟随", "回调布局", "强势接力", "防御布局"]:
        summarize([r for r in all_recs if r["strat"] == s], f"策略={s}")

    print("\n" + "=" * 66)
    print("CONFIRMATION SIGNAL: 首根K确认  企稳 vs 击穿  (核心假设检验)")
    print("=" * 66)
    for c in ["企稳", "击穿"]:
        summarize([r for r in all_recs if r["confirm"] == c], f"首根K={c}")

if __name__ == "__main__":
    main()
