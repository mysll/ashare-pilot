#!/usr/bin/env python3
"""Entry-quality analyzer for the Schema-Locked verification tables.

Reads memory/daily/{date}/verification.md, finds the schema-locked
「买入结果表」(see daily-trading-review SKILL §3a), computes entry-relative
quality metrics from RAW prices, and aggregates by 策略 and by 首根K确认.

It ALSO reports 踏空统计 (missed-entry), split into 踏空 (未触及但上涨) vs
观望正确 (未触及且下跌) and stratified by market regime — because strong
markets miss to the upside (真踏空) while weak markets "miss" to the downside
(正确回避); averaging them together is meaningless.

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
        text = f.read()
    lines = text.splitlines()
    date = fp.split(os.sep)[-2]
    # RegimeHint from the locked 市场环境 section (§4a). Default 'unknown'.
    m = re.search(r"RegimeHint[:：]\s*([A-Za-z\-]+)", text)
    regime = m.group(1).strip().lower() if m else "unknown"
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
                    date=date, regime=regime, code=code, strat=cells[idx["策略"]],
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


# ── 踏空 (missed-entry) aggregation ────────────────────────────────
# Missed entry = NOT filled. Split into two opposite outcomes so the two
# never contaminate one average:
#   踏空 (bad miss)  = 未触及 but the stock rose  → should have bought, didn't
#   观望正确 (good)  = 未触及 and the stock fell   → correctly stayed out
# Classification priority: use 结果 column keywords; fall back to close-vs-open
# for legacy/unlabeled rows.
def miss_class(r):
    """Return '踏空' | '观望正确' | None(=filled, not a miss)."""
    if r.get("filled"):
        return None
    res = r.get("result", "")
    if "踏空" in res: return "踏空"
    if "观望" in res or "回避" in res: return "观望正确"
    # fallback: rose after we missed => 踏空; fell => 观望正确
    o, c = r.get("open"), r.get("close")
    if o and c is not None:
        return "踏空" if c > o else "观望正确"
    return None  # indeterminate (e.g. 暂不参与 with no prices) — excluded


def missed_summary(rows, label):
    """rows = all recommendations in a stratum (filled + missed)."""
    total = len(rows)
    filled = [r for r in rows if r.get("filled")]
    missed = [r for r in rows if not r.get("filled")]
    taku = [r for r in missed if miss_class(r) == "踏空"]
    watch = [r for r in missed if miss_class(r) == "观望正确"]
    indet = len(missed) - len(taku) - len(watch)
    if total == 0:
        print(f"\n== {label}: no rows"); return
    fill_pct = len(filled) / total * 100
    taku_pct = len(taku) / total * 100
    watch_pct = len(watch) / total * 100
    print(f"\n== {label}  (推荐 n={total})")
    print(f"   触及率      {len(filled):>2}/{total} = {fill_pct:4.0f}%")
    print(f"   踏空率      {len(taku):>2}/{total} = {taku_pct:4.0f}%   (未触及但上涨=该买没买到)")
    print(f"   观望正确率  {len(watch):>2}/{total} = {watch_pct:4.0f}%   (未触及且下跌=正确回避)")
    if indet:
        print(f"   未分类      {indet:>2}/{total}         (暂不参与/无价格)")
    # 踏空 magnitude: how much upside was missed (open->close of 踏空 names)
    ups = [(r["close"] - r["open"]) / r["open"] * 100
           for r in taku if r.get("open") and r.get("close") is not None]
    if ups:
        print(f"   踏空涨幅    mean {st.mean(ups):+.2f}%  median {st.median(ups):+.2f}%  max {max(ups):+.2f}%")


def print_missed(all_recs):
    print("\n" + "=" * 66)
    print("踏空统计 (MISSED ENTRY) — 分市场 regime + 策略, 踏空 vs 观望正确不混淆")
    print("=" * 66)
    print("\n[ALL]")
    missed_summary(all_recs, "全部")
    # by regime — the key stratification (strong markets miss upward, weak miss downward)
    regimes = sorted({r.get("regime", "unknown") for r in all_recs})
    print("\n[BY REGIME]")
    for rg in regimes:
        missed_summary([r for r in all_recs if r.get("regime") == rg], f"regime={rg}")
    # by strategy
    print("\n[BY 策略]")
    for s in ["趋势跟随", "回调布局", "强势接力", "防御布局"]:
        sub = [r for r in all_recs if r["strat"] == s]
        if sub: missed_summary(sub, f"策略={s}")


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

    print_missed(all_recs)

if __name__ == "__main__":
    main()
