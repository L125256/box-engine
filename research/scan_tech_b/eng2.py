#!/usr/bin/env python3
# eng2.py — v2 切换表 + 预算内 BULL 扩展网格 + 补充风险指标（依赖 eng.py 的函数）
import json, os, sys, statistics
sys.path.insert(0, '/tmp/scan_tech_b')
import numpy as np
np.random.seed(42)
from eng import load_pool, build_index, regime_map, scan, metrics, rank_key, MAIN_START

OUTDIR = '/tmp/scan_tech_b'

pool = load_pool()
idx, dts, ma50, ma20, ma10 = build_index(pool)
bull = {dt: idx[dt] > ma50[dt] for dt in dts}
rm = regime_map(dts, idx, ma50, ma20)

# 已跑 54 组合 + 本轮扩展 12 = 66 ≤ 预算 150
base_combos = [(N, K, M, E) for K in (5.0, 6.0, 7.5) for E in (0.15, 0.2, 0.3)
               for N in (15, 20, 25) for M in (1, 2)]
extra = [  # BULL 主 regime（45.5% 天数）定向扩展
    (12, 7.5, 1, 0.3), (12, 7.5, 1, 0.35), (15, 7.5, 1, 0.35), (18, 7.5, 1, 0.3),
    (15, 9.0, 1, 0.3), (15, 9.0, 1, 0.2), (18, 9.0, 1, 0.3), (12, 9.0, 1, 0.3),
    (15, 7.5, 3, 0.3), (15, 9.0, 3, 0.3), (20, 9.0, 1, 0.3), (15, 9.0, 1, 0.35),
]
combos = base_combos + extra
grid = {}
for c in combos:
    trs = []
    for tkr, bars in pool.items():
        for t in scan(bars, bull, *c):
            t['tkr'] = tkr; trs.append(t)
    grid[c] = trs
print("total combos:", len(grid))

def combo_of(d): return (d['N'], d['k'], d['m'], d['e'])

# 分 regime 排名（主窗）
per_regime = {}
for rg in ('BULL', 'CHOP', 'BEAR'):
    rows = []
    for c, trs in grid.items():
        sel = [t for t in trs if rm.get(t['ei_date']) == rg and t['ei_date'] >= MAIN_START]
        m = metrics(sel)
        if m['n'] > 0: rows.append(dict(combo=dict(N=c[0], k=c[1], m=c[2], e=c[3]), **m))
    rows.sort(key=lambda r: rank_key(r), reverse=True)
    per_regime[rg] = rows
    print(f"\n== {rg} top6 ==")
    for r in rows[:6]: print(' ', r)
    ok100 = [r for r in rows if r['n'] >= 100]
    print(f"  n>=100 best:", ok100[0] if ok100 else None)

# v1 表（原规则：各 regime rank1，n<100 标不可上线）
# v2 表：rank1 若 n<100 → 取该 regime 内 n>=100 的最优（CHOP 修复）
table_v2 = {}
for rg in ('BULL', 'CHOP', 'BEAR'):
    ok100 = [r for r in per_regime[rg] if r['n'] >= 100]
    pick = ok100[0] if ok100 else None
    table_v2[rg] = pick
    print('v2', rg, pick['combo'] if pick else None, pick['n'] if pick else None)

def combined(rmap, tbl):
    out = []
    for rg, row in tbl.items():
        c = combo_of(row['combo'])
        out += [t for t in grid[c] if rmap.get(t['ei_date']) == rg]
    return out

comb_v1 = combined(rm, {rg: per_regime[rg][0] for rg in per_regime})
comb_v2 = combined(rm, table_v2)

# 稳健性重打标
rm_lag = {dt: rm[dts[max(0, j - 3)]] for j, dt in enumerate(dts)}
rm_alt = {}
for dt in dts:
    if idx[dt] > ma50[dt] * 1.01: rg = 'BULL'
    elif idx[dt] < ma50[dt] * 0.99: rg = 'BEAR' if ma10[dt] < ma50[dt] else 'CHOP'
    else: rg = 'CHOP'
    rm_alt[dt] = rg

def block(trs):
    return dict(main=metrics(trs, date_from=MAIN_START),
                y2024=metrics(trs, year=2024), y2025=metrics(trs, year=2025),
                y2026=metrics(trs, year=2026), full=metrics(trs))

res2 = dict(
    total_combos=len(grid),
    per_regime_top10={rg: per_regime[rg][:10] for rg in per_regime},
    table_v2={rg: dict(combo=r['combo'], n=r['n'], median=r['median'], win=r['win'],
                       mean=r['mean'], pf=r['pf'], online_ok=r['n'] >= 100)
              for rg, r in table_v2.items()},
    v2_compare=dict(
        combined_v2=block(comb_v2),
        combined_v2_lag3=block(combined(rm_lag, table_v2)),
        combined_v2_altdef=block(combined(rm_alt, table_v2)),
    ),
)

# 切点日历占比 + bk/fd 结构
switch_days = set()
nflips = 0
for j in range(1, len(dts)):
    if rm[dts[j]] != rm[dts[j - 1]]:
        nflips += 1
        for k2 in range(max(0, j - 5), min(len(dts), j + 6)): switch_days.add(dts[k2])
dayshare_near = round(len(switch_days) / len(dts) * 100, 1)
kind_break = {}
for rg, row in table_v2.items():
    c = combo_of(row['combo'])
    sel = [t for t in grid[c] if rm.get(t['ei_date']) == rg and t['ei_date'] >= MAIN_START]
    for kd in ('bk', 'fd'):
        s = [t for t in sel if t['kind'] == kd]
        if s:
            kind_break.setdefault(rg, {})[kd] = dict(
                n=len(s), median=statistics.median([t['r'] for t in s]),
                mean=round(sum(t['r'] for t in s) / len(s), 3),
                win=round(sum(1 for t in s if t['r'] > 0) / len(s) * 100, 2))
res2['risk_extra'] = dict(near_switch_day_share_pct=dayshare_near, total_flips=nflips,
                          kind_breakdown=kind_break)

# v1/v2/Top1 主窗+分年 对比总表
res2['final_compare'] = dict(
    global_top1=block(grid[(15, 7.5, 2, 0.3)]),
    combined_v1=block(comb_v1),
    combined_v2=block(comb_v2),
)

with open(os.path.join(OUTDIR, 'regime_results_v2.json'), 'w') as f:
    json.dump(res2, f, ensure_ascii=False, indent=1)

print("\nV2 COMBINED(main):", res2['v2_compare']['combined_v2']['main'])
print("V2 lag3(main):", res2['v2_compare']['combined_v2_lag3']['main'])
print("V2 altdef(main):", res2['v2_compare']['combined_v2_altdef']['main'])
print("near-day-share:", dayshare_near, "% flips:", nflips)
print("kind:", json.dumps(kind_break))
print("saved -> regime_results_v2.json")
