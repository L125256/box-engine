#!/usr/bin/env python3
# eng.py — R2 regime 自适应参数表论证引擎（技术席B，独立目录 /tmp/scan_tech_b/）
# 只读 /tmp/box_cache/*.json 与 /root/.codebuddy/artifact/kx-combo/box_module.py
# 逻辑严格复刻 box_module.py v1.0 状态机，仅参数化 N/K/M/E（b/x/Q/AMAX 冻结）
import json, os, glob, statistics, sys
import numpy as np
np.random.seed(42)

CACHE = '/tmp/box_cache'
OUTDIR = '/tmp/scan_tech_b'
MAIN_START = '2025-06-01'
B0, X0, Q0, AMAX = 0.25, 0.75, 30, 60   # 冻结参数

# ---------- 数据加载（与 box_module.main 完全一致的清洗口径） ----------
def load_pool():
    pool = {}
    for f in sorted(glob.glob(os.path.join(CACHE, '*.json'))):
        d = json.load(open(f))
        if isinstance(d, dict): d = d.get('bars_d', d)
        cl = [b for b in d if b['low'] > 0 and b['close'] > 0 and b['low'] <= b['high'] and b['low'] <= b['close'] <= b['high']]
        if len(cl) >= 100:
            pool[os.path.basename(f).replace('.json', '')] = cl
    return pool

def atrs(bars, n=14):
    out = [None] * len(bars); trs = []
    for i in range(1, len(bars)):
        trs.append(max(bars[i]['high'] - bars[i]['low'],
                       abs(bars[i]['high'] - bars[i-1]['close']),
                       abs(bars[i]['low'] - bars[i-1]['close'])))
        if i >= n: out[i] = sum(trs[-n:]) / n
    return out

# ---------- 指数 idx / MA50 / regime（全部只用当日及之前信息） ----------
def build_index(pool):
    all_dates = sorted({b['time'] for bars in pool.values() for b in bars})
    idx = {}
    for dt in all_dates:
        vals = [b['close'] for bars in pool.values() for b in bars if b['time'] == dt]
        if vals: idx[dt] = sum(vals) / len(vals)
    dts = sorted(idx)
    def ma(dts, idx, w):
        out = {}
        for i, dt in enumerate(dts):
            win = dts[max(0, i - w + 1):i + 1]
            out[dt] = sum(idx[d] for d in win) / len(win)
        return out
    ma50 = ma(dts, idx, 50); ma20 = ma(dts, idx, 20); ma10 = ma(dts, idx, 10)
    return idx, dts, ma50, ma20, ma10

def regime_map(dts, idx, ma50, ma20):
    """R2 主 regime 定义（3态，全为当日可算信息，无前视）：
    BULL: idx>MA50
    BEAR: idx<=MA50 且 idx20<MA50（均线下方且短均线更弱 → 下行）
    CHOP: idx<=MA50 且 idx20>=MA50（均线下方但短均线不弱 → 箱型震荡）"""
    rm = {}
    for dt in dts:
        if idx[dt] > ma50[dt]: rm[dt] = 'BULL'
        elif idx[dt] <= ma50[dt] and ma20[dt] < ma50[dt]: rm[dt] = 'BEAR'
        else: rm[dt] = 'CHOP'
    return rm

# ---------- 状态机复刻（box_module.scan 参数化，逐行对齐） ----------
def scan(bars, bull, N, K, M, E):
    a = atrs(bars)
    state = 'seek'; streak = 0; box = None; pos = None; trades = []
    for i in range(max(N, 14) + 1, len(bars)):
        if a[i] is None: continue
        px = bars[i]['close']
        if pos:
            hold = i - pos['ei']; r = (px - pos['ep']) / pos['ep'] * 100 - 0.03 * hold
            if px <= pos['eff'] or px >= pos['tp'] or hold >= Q0:
                trades.append(dict(ep=pos['ep'], xi=i, kind=pos['kind'], r=round(r, 2),
                                   xt=bars[i]['time'], ei_date=bars[pos['ei']]['time']))
                pos = None
            continue
        if state == 'seek':
            w = bars[i - N + 1:i + 1]
            Hh = max(x['high'] for x in w); Ll = min(x['low'] for x in w); rng = Hh - Ll
            if rng > 0 and rng < K * a[i]: streak += 1
            else: streak = 0
            if streak >= M: state = 'locked'; box = [Ll, Hh, i, '']; streak = 0
            continue
        L, H, li, fired = box; rng = H - L; age = i - li
        sig = None
        if 'L' not in fired and px > H + B0 * a[i]: sig = ('bk', px)
        elif ('L' not in fired and bull.get(bars[i]['time']) and bars[i]['low'] <= L + E * rng): sig = ('fd', px)
        if sig is None and (px > H + X0 * a[i] or px < L - X0 * a[i] or age > AMAX):
            state = 'seek'; box = None; continue
        if sig:
            kind, ep = sig; box[3] += 'L'
            tp = H + a[i] if kind == 'bk' else H
            disp = ep - 1.5 * a[i] if kind == 'bk' else L
            eff = disp - 0.3 * a[i]
            risk = (ep - disp) / ep * 100
            if eff > 0 and risk <= 8.0: pos = dict(ep=ep, tp=tp, disp=disp, eff=eff, ei=i, kind=kind)
    return trades

def run_grid(pool, bull, combos):
    """每组合跑一次全池回放；返回 {combo: [trades]}，trade 含入场日期"""
    res = {}
    for (N, K, M, E) in combos:
        trs = []
        for tkr, bars in pool.items():
            for t in scan(bars, bull, N, K, M, E):
                t['tkr'] = tkr; trs.append(t)
        res[(N, K, M, E)] = trs
    return res

# ---------- 指标（目标函数钉死：median > win > mean > PF 参照） ----------
def metrics(trs, date_from=None, date_to=None, year=None):
    sel = trs
    if date_from is not None: sel = [t for t in sel if t['ei_date'] >= date_from]
    if date_to is not None: sel = [t for t in sel if t['ei_date'] < date_to]
    if year is not None: sel = [t for t in sel if t['ei_date'][:4] == str(year)]
    rs = [t['r'] for t in sel]
    n = len(rs)
    if n == 0: return dict(n=0)
    pos = sum(r for r in rs if r > 0); neg = sum(r for r in rs if r < 0)
    return dict(n=n,
                median=round(statistics.median(rs), 4),
                win=round(sum(1 for r in rs if r > 0) / n * 100, 2),
                mean=round(sum(rs) / n, 4),
                pf=round(pos / abs(neg), 4) if neg < 0 else None,
                thick_sum=round(sum(r for r in rs if r >= 8), 2),
                thick_n=sum(1 for r in rs if r >= 8))

def rank_key(m):
    # 目标函数：median 第一，win 第二，mean 第三，PF 参照
    return (m['median'], m['win'], m['mean'], m['pf'] if m['pf'] is not None else 99)

def main():
    pool = load_pool()
    idx, dts, ma50, ma20, ma10 = build_index(pool)
    bull = {dt: idx[dt] > ma50[dt] for dt in dts}
    rm = regime_map(dts, idx, ma50, ma20)

    print(f"pool={len(pool)} symbols, dates={dts[0]}..{dts[-1]}, n_dates={len(dts)}")

    # ---- Step1: 本地基线复现（默认冻结参数）+ Top1 + 方案B 对拍 ----
    combos = []
    for K in (5.0, 6.0, 7.5):
        for E in (0.15, 0.2, 0.3):
            for N in (15, 20, 25):
                for M in (1, 2):
                    combos.append((N, K, M, E))
    # 54 组合 ≤ 预算150；Top1=(15,7.5,2,0.3) 与 方案B=(20,6.0,1,0.3) 均在网格内
    assert (15, 7.5, 2, 0.3) in combos and (20, 6.0, 1, 0.3) in combos
    grid = run_grid(pool, bull, combos)
    print("grid done:", len(grid), "combos")

    base = metrics(grid[(20, 6.0, 2, 0.2)], date_from=MAIN_START)
    top1 = metrics(grid[(15, 7.5, 2, 0.3)], date_from=MAIN_START)
    planb = metrics(grid[(20, 6.0, 1, 0.3)], date_from=MAIN_START)
    print("BASE(main):", base)
    print("TOP1(main):", top1)
    print("PLANB(main):", planb)

    # ---- Step2: 分 regime 网格评估 ----
    regimes = ['BULL', 'CHOP', 'BEAR']
    per_regime = {}
    for rg in regimes:
        rows = []
        for combo, trs in grid.items():
            sel = [t for t in trs if rm.get(t['ei_date']) == rg and t['ei_date'] >= MAIN_START]
            m = metrics(sel)
            if m['n'] > 0: rows.append(dict(combo=dict(N=combo[0], k=combo[1], m=combo[2], e=combo[3]), **m))
        rows.sort(key=lambda r: rank_key(r), reverse=True)
        per_regime[rg] = rows
        print(f"\n== {rg} top5 (main window) ==")
        for r in rows[:5]:
            print(r)

    # ---- Step3: 固定切换表（每 regime 取 rank 第一；n<100 标不可上线） ----
    table = {}
    for rg in regimes:
        best = per_regime[rg][0]
        ok = best['n'] >= 100
        table[rg] = dict(combo=best['combo'], n=best['n'], online_ok=ok,
                         median=best['median'], win=best['win'], mean=best['mean'], pf=best['pf'])
    print("\nSWITCH TABLE:", json.dumps(table, ensure_ascii=False))

    # ---- Step4: 合成策略（union of per-regime best subsets）vs Top1 vs 基线 ----
    def combined_set(rmap):
        out = []
        for rg, cfg in table.items():
            combo = (cfg['combo']['N'], cfg['combo']['k'], cfg['combo']['m'], cfg['combo']['e'])
            out += [t for t in grid[combo] if rmap.get(t['ei_date']) == rg]
        return out

    comb = combined_set(rm)
    out = {}
    def block(trs):
        return dict(main=metrics(trs, date_from=MAIN_START),
                    y2023=metrics(trs, year=2023), y2024=metrics(trs, year=2024),
                    y2025=metrics(trs, year=2025), y2026=metrics(trs, year=2026),
                    full=metrics(trs))
    out['baseline_default'] = block(grid[(20, 6.0, 2, 0.2)])
    out['global_top1'] = block(grid[(15, 7.5, 2, 0.3)])
    out['plan_b'] = block(grid[(20, 6.0, 1, 0.3)])
    out['regime_combined'] = block(comb)
    print("\nCOMBINED(main):", out['regime_combined']['main'])

    # ---- Step5: 风险自查 ----
    # 5.1 大肉保全线：r>=8 厚利桶 sum 对比（基线/Top1 为参照，降幅>5% 一票否决）
    thick = {name: dict(sum=v['full']['thick_sum'], n=v['full']['thick_n'])
             for name, v in out.items()}
    # 5.2 切换滞后：regime 序列整体滞后3个交易日重打标，切换表不变
    rm_lag = {}
    for j, dt in enumerate(dts):
        rm_lag[dt] = rm[dts[max(0, j - 3)]]
    out['regime_combined_lag3'] = block(combined_set(rm_lag))
    # 5.3 regime 口径敏感性：chop/bear 分界改用 idx10；bull 加 ±1% 迟滞带
    rm_alt = {}
    for dt in dts:
        if idx[dt] > ma50[dt] * 1.01: rg = 'BULL'
        elif idx[dt] < ma50[dt] * 0.99:
            rg = 'BEAR' if ma10[dt] < ma50[dt] else 'CHOP'
        else: rg = 'CHOP'
        rm_alt[dt] = rg
    out['regime_combined_altdef'] = block(combined_set(rm_alt))
    # 5.4 regime 误判率：用未来20交易日 idx 收益做「事后」检验（仅评估用，不用于判定）
    fwd = {}
    for j, dt in enumerate(dts):
        if j + 20 < len(dts):
            fwd[dt] = (idx[dts[j + 20]] / idx[dt] - 1) * 100
    misj = {}
    for rg in regimes:
        vals = [fwd[dt] for dt in dts if rm[dt] == rg and dt in fwd]
        if rg == 'BULL':
            mis = sum(1 for v in vals if v < 0) / len(vals) * 100
        elif rg == 'BEAR':
            mis = sum(1 for v in vals if v > 0) / len(vals) * 100
        else:
            mis = sum(1 for v in vals if abs(v) > 8) / len(vals) * 100  # 震荡被单边突破
        misj[rg] = dict(days=len(vals), median_fwd20=round(statistics.median(vals), 3),
                        misjudge_pct=round(mis, 2))
    # 5.5 切点邻域敏感性：regime 切换日 ±5 个交易日内入场的交易表现
    switch_days = set()
    for j in range(1, len(dts)):
        if rm[dts[j]] != rm[dts[j - 1]]:
            for k in range(max(0, j - 5), min(len(dts), j + 6)): switch_days.add(dts[k])
    near = {'top1': metrics([t for t in grid[(15, 7.5, 2, 0.3)] if t['ei_date'] in switch_days]),
            'combined': metrics([t for t in comb if t['ei_date'] in switch_days])}
    # 5.6 regime 翻转频率（whipsaw）
    flips = {}
    for y in ('2024', '2025', '2026'):
        c = sum(1 for j in range(1, len(dts)) if dts[j][:4] == y and rm[dts[j]] != rm[dts[j - 1]])
        days = sum(1 for dt in dts if dt[:4] == y)
        flips[y] = dict(flips=c, days=days)
    dayshare = {rg: round(sum(1 for dt in dts if rm[dt] == rg) / len(dts) * 100, 1) for rg in regimes}

    # ---- 落盘 ----
    result = dict(
        meta=dict(seed=42, pool_symbols=len(pool), date_range=[dts[0], dts[-1]],
                  grid_combos=len(combos), budget=150, main_start=MAIN_START,
                  cache_key_names=['time','open','high','low','close','volume']),
        baseline_repro=dict(handover=dict(median=0.365, win=51.48, n=1084, pool=143),
                            local_default=dict(N=20, k=6.0, m=2, e=0.2), main=base),
        top1_main=top1, planb_main=planb,
        regime_def=dict(BULL='idx>MA50', BEAR='idx<=MA50 且 idx20<MA50', CHOP='idx<=MA50 且 idx20>=MA50',
                        day_share_pct=dayshare),
        per_regime_top10={rg: per_regime[rg][:10] for rg in regimes},
        switch_table=table,
        compare=out,
        risk=dict(thick_bucket=thick,
                  regime_misjudge=misj,
                  switch_flips_per_year=flips,
                  near_switch=near),
    )
    with open(os.path.join(OUTDIR, 'regime_results.json'), 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("\nthick:", json.dumps(thick))
    print("misjudge:", json.dumps(misj))
    print("near_switch:", json.dumps(near))
    print("dayshare:", dayshare, "flips:", flips)
    print("saved ->", os.path.join(OUTDIR, 'regime_results.json'))

if __name__ == '__main__':
    main()
