#!/usr/bin/env python3
"""Compute Theme Ranking from compute pool + theme library lookups."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r'E:\trading-office')
INPUT = ROOT / 'intraday' / '2026-07-01' / 'compute_pool_enriched.json'
OUTPUT = ROOT / 'intraday' / '2026-07-01' / 'theme_ranking.md'
QUERY_SCRIPT = ROOT / '.opencode' / 'skills' / 'theme-library' / 'scripts' / 'query_theme.py'

with open(INPUT, 'r', encoding='utf-8') as f:
    data = json.load(f)

pool = data['compute_pool']
pool.sort(key=lambda x: x.get('quick_score', 0), reverse=True)
top = pool[:40]

all_themes = {}

for stk in top:
    code = stk['code']
    name = stk['name']
    cp = stk.get('change_pct', '0%')
    change_val = float(cp.replace('+', '').replace('%', ''))
    enriched = stk.get('enriched', {})
    mf = enriched.get('money_flow', {})
    try:
        inflow = float(mf.get('main_net_inflow', '0.00'))
    except ValueError:
        inflow = 0.0
    result = subprocess.run(
        [sys.executable, str(QUERY_SCRIPT), 'stock', code, '--json'],
        capture_output=True, text=False, cwd=str(ROOT)
    )
    try:
        raw = json.loads(result.stdout.decode('utf-8'))
        if code in raw:
            si = raw[code]
        else:
            si = raw
        for t in si.get('themes', []):
            tn = t['name']
            if tn not in all_themes:
                all_themes[tn] = []
            all_themes[tn].append({
                'code': code, 'name': name,
                'change_pct': change_val,
                'main_net_inflow': inflow
            })
    except Exception:
        pass

scores = []
for theme, stocks in all_themes.items():
    n = len(stocks)
    lc = max(s['change_pct'] for s in stocks)
    ls = max(stocks, key=lambda s: s['change_pct'])
    ti = sum(s['main_net_inflow'] for s in stocks)
    ac = sum(s['change_pct'] for s in stocks) / n
    scores.append({
        'theme': theme, 'count': n,
        'leader_change': lc, 'leader_code': ls['code'],
        'leader_name': ls['name'], 'total_inflow': ti,
        'avg_change': ac,
        'stocks': [(s['code'], s['name'], s['change_pct'], s['main_net_inflow']) for s in stocks]
    })

max_count = max(s['count'] for s in scores) or 1
max_lc = max(abs(s['leader_change']) for s in scores) or 1
max_ti = max(abs(s['total_inflow']) for s in scores) or 1
min_ac = min(s['avg_change'] for s in scores)
max_ac = max(s['avg_change'] for s in scores)
ac_range = max_ac - min_ac or 1

for s in scores:
    bn = s['count'] / max_count
    ln = abs(s['leader_change']) / max_lc
    cn = abs(s['total_inflow']) / max_ti
    mn = (s['avg_change'] - min_ac) / ac_range
    s['heat'] = bn * 20 + ln * 30 + cn * 25 + mn * 15 + 10  # continuation = 10

scores.sort(key=lambda x: x['heat'], reverse=True)
top15 = scores[:15]

lines = []
lines.append(f"## Theme Ranking (2026-07-01 14:30)")
lines.append(f"")
lines.append(f"基于ComputePool前40只个股的Bottom-Up统计聚合（股票→主题），Top 15主题热度排名")
lines.append(f"")
lines.append(f"| # | 主题 | 热度 | 池内个股数 | 平均涨幅 | 领涨股 | 领涨涨幅 | 主力净流入(亿) |")
lines.append(f"|---|------|------|-----------|---------|--------|---------|---------------|")
for i, s in enumerate(top15):
    lines.append(f"| {i+1} | {s['theme']} | {s['heat']:.1f} | {s['count']} | {s['avg_change']:+.2f}% | {s['leader_name']} | {s['leader_change']:+.2f}% | {s['total_inflow']:+.2f} |")

lines.append(f"")
lines.append(f"### 热度分项构成")
lines.append(f"")
lines.append(f"| # | 主题 | 总热度 | 广度(20%) | 领涨力(30%) | 资金(25%) | 动量(15%) | 持续性(10%) |")
lines.append(f"|---|------|--------|----------|------------|----------|----------|------------|")
for i, s in enumerate(top15):
    max_count_v = max_count
    max_lc_v = max_lc
    max_ti_v = max_ti
    bn_pct = (s['count'] / max_count) * 20
    ln_pct = (abs(s['leader_change']) / max_lc) * 30
    cn_pct = (abs(s['total_inflow']) / max_ti) * 25
    ac_range_v = max_ac - min_ac or 1
    mn_pct = ((s['avg_change'] - min_ac) / ac_range_v) * 15
    cn_pct2 = 10  # continuation fixed
    lines.append(f"| {i+1} | {s['theme']} | {s['heat']:.1f} | {bn_pct:.1f} | {ln_pct:.1f} | {cn_pct:.1f} | {mn_pct:.1f} | {cn_pct2:.1f} |")

lines.append(f"")
lines.append(f"### 主题成分股明细")
lines.append(f"")
for i, s in enumerate(top15):
    lines.append(f"**{i+1}. {s['theme']}**（热度 {s['heat']:.1f}，池内 {s['count']} 只）")
    for stk_code, stk_name, stk_chg, stk_flow in s['stocks']:
        flow_str = f"{stk_flow:+.2f}亿" if stk_flow != 0 else "-"
        lines.append(f"  - {stk_name}（{stk_code}）涨幅{stk_chg:+.2f}%，主力净流入 {flow_str}")
    lines.append(f"")

lines.append(f"---")
lines.append(f"*本文件为Perception层输出，不含交易推荐*")
lines.append(f"*生成时间：2026-07-01 14:35*")

content = '\n'.join(lines)
with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Written to {OUTPUT}")
for line in lines[:25]:
    print(line)
