#!/usr/bin/env python3
# run_stress.py — R2 稳健性压测主程序（四方案 × 五类压测 + regime/熊市腿证伪）
# 全部出场口径 V2（可实现）。固定 seed=42 仅用于 vintage 池扰动。
import sys, json, random, collections
sys.path.insert(0, '/tmp/kx34_short_b')
import os
import pandas as pd
import engine
from engine import run_all, metrics, main_window

OUT = '/tmp/kx34_short_b'
SEED = 42
CACHE = '/tmp/box_cache'

def load_pool_all(cache_dir=CACHE):
    """176 标的全池（不做 len>=100 过滤，与 R1「本地池=176」口径一致；bar 合法性过滤保留）"""
    pool = {}
    for f in sorted(os.listdir(cache_dir)):
        d = json.load(open(os.path.join(cache_dir, f)))
        bars = d if isinstance(d, list) else d.get('bars_d', d.get('bars'))
        cl = [b for b in bars if b['low'] > 0 and b['close'] > 0
              and b['low'] <= b['high'] and b['low'] <= b['close'] <= b['high']]
        pool[f.replace('.json', '')] = cl
    return pool

BASE = dict(k=6.0, e=0.2, N=20, m=2, h8=None, m3_t=None)
SCHEMES = {
    'base':    {},
    'Top1':    dict(k=7.5, e=0.3, N=15, m=2),
    'planB':   dict(k=6.0, e=0.3, N=20, m=1),
    'H8':      dict(h8=1.0),
    'M3':      dict(m3_t=0.3),
}

def P(**kw):
    p = dict(BASE); p.update(kw); return p

def run(pool, bull, **pkw):
    p = {**BASE, **pkw}
    p['N'] = int(round(p['N'])); p['m'] = int(round(p['m']))
    tr, amb = run_all(pool, bull, N=p['N'], K=p['k'], M=p['m'], E=p['e'], h8=p.get('h8'),
                      m3_t=p.get('m3_t'), v2=True)
    for t in tr: t['amb'] = 0
    return tr

def by_year(trades):
    out = {}
    for y in ('2023', '2024', '2025', '2026'):
        sub = [t for t in trades if t['xt'][:4] == y]
        out[y] = metrics(sub) | dict(sum=round(sum(t['r'] for t in sub), 2))
    return out

def thick_bucket(trades):
    b = [t for t in trades if t['kind'] == 'fd' and t['r'] >= 8]
    bm = [t for t in b if t['xt'] >= '2025-06-01']
    return dict(n=len(b), sum=round(sum(t['r'] for t in b), 2),
                mw_n=len(bm), mw_sum=round(sum(t['r'] for t in bm), 2))

def main():
    pool = load_pool_all()
    bull = engine.compute_idx(pool)
    R = {'meta': {'pool_tickers': len(pool), 'seed': SEED, 'exit_convention': 'V2',
                  'main_window': 'entry>=2025-06-01',
                  'rank': 'median>win>mean'}}

    # ---------- 0. 基线复现 + 口径对拍 ----------
    base_tr = run(pool, bull)
    R['baseline'] = {'main_V2': metrics(main_window(base_tr)),
                     'full_V2': metrics(base_tr),
                     'by_year': by_year(base_tr),
                     'thick_bucket': thick_bucket(base_tr)}
    tr_v1, _ = engine.run_all(pool, bull, v2=True)
    # V1 快照：同扫描、V1 出场价
    tr_v1b, _ = engine.run_all(pool, bull, v2=False)
    R['baseline']['main_V1'] = metrics(main_window(tr_v1b), 'r_v1')

    # ---------- 0b. V1/V2 口径对拍（全方案） ----------
    R['v1_v2'] = {}
    for name in ('base', 'Top1', 'planB', 'H8', 'M3'):
        ov = {} if name == 'base' else SCHEMES[name]
        p = {**BASE, **ov}
        tr1, _ = engine.run_all(pool, bull, N=p['N'], K=p['k'], M=p['m'], E=p['e'],
                                h8=p.get('h8'), m3_t=p.get('m3_t'), v2=False)
        tr2, _ = engine.run_all(pool, bull, N=p['N'], K=p['k'], M=p['m'], E=p['e'],
                                h8=p.get('h8'), m3_t=p.get('m3_t'), v2=True)
        R['v1_v2'][name] = {'V1_main': metrics(main_window(tr1), 'r_v1'),
                            'V2_main': metrics(main_window(tr2)),
                            'v1_fd_r8_full_n': len([t for t in tr1 if t['kind'] == 'fd' and t['r_v1'] >= 8])}

    # ---------- 0c. vintage 下 bull 标记翻转率 ----------
    rng0 = random.Random(SEED)
    sh = sorted(pool); rng0.shuffle(sh)
    sub0 = {t: pool[t] for t in sh[9:]}
    rows0 = [(b['time'], b['close']) for bars in pool.values() for b in bars]
    s0 = pd.DataFrame(rows0, columns=['t', 'c']).groupby('t')['c'].mean().sort_index()
    b_full = pd.Series(s0.values > s0.rolling(50, min_periods=1).mean().values, index=s0.index)
    rows1 = [(b['time'], b['close']) for bars in sub0.values() for b in bars]
    s1 = pd.DataFrame(rows1, columns=['t', 'c']).groupby('t')['c'].mean().sort_index()
    b_sub = pd.Series(s1.values > s1.rolling(50, min_periods=1).mean().values, index=s1.index)
    common = s0.index.intersection(s1.index)
    flip = (b_full[common] != b_sub[common])
    R['bull_flip'] = {'drop5pct_g1_common_days': int(len(common)),
                      'flipped_days': int(flip.sum()),
                      'flip_pct': round(float(flip.mean()) * 100, 1)}

    # ---------- 方案主结果 ----------
    scheme_trades = {}
    for name, ov in SCHEMES.items():
        if name == 'base': continue
        tr = run(pool, bull, **P(**ov))
        scheme_trades[name] = tr
        mw = main_window(tr)
        R[name] = {'main': metrics(mw), 'full': metrics(tr), 'by_year': by_year(tr),
                   'thick_bucket': thick_bucket(tr), 'params': P(**ov)}

    # ---------- 1. 切点邻域敏感性 ----------
    def variants(name):
        p0 = P(**SCHEMES[name]); out = []
        steps = {'k': 0.5, 'e': 0.05, 'N': 1, 'h8': 0.5, 'm3_t': 0.05}
        for key in ('k', 'e', 'N', 'h8', 'm3_t'):
            if p0.get(key) is None: continue
            v0 = p0[key]
            out.append((f'{key}-20%', {**p0, key: round(v0 * 0.8, 4)}))
            out.append((f'{key}+20%', {**p0, key: round(v0 * 1.2, 4)}))
            s = steps[key]
            out.append((f'{key}-{s}', {**p0, key: round(v0 - s, 4)}))
            out.append((f'{key}+{s}', {**p0, key: round(v0 + s, 4)}))
        if p0['m'] is not None:
            if p0['m'] > 1: out.append((f'm-1', {**p0, 'm': p0['m'] - 1}))
            out.append((f'm+1', {**p0, 'm': p0['m'] + 1}))
        return out

    frag_rule = '脆弱=任一单参变体 主窗median<=0 或 win<=45 或 median 相对跌幅>50%'
    R['perturb'] = {'rule': frag_rule}
    for name in ('Top1', 'planB', 'H8', 'M3'):
        m0 = R[name]['main']; rows = []; fragile = []
        for tag, p in variants(name):
            tr = run(pool, bull, **p)
            m = metrics(main_window(tr))
            drop = (m0['median'] - m['median']) / abs(m0['median']) if m0['median'] else None
            bad = (m['median'] is None or m['median'] <= 0 or m['win'] <= 45
                   or (drop is not None and drop > 0.5))
            if bad: fragile.append(tag)
            rows.append(dict(tag=tag, **m, median_drop_pct=round(drop * 100, 1) if drop is not None else None))
        R['perturb'][name] = {'base': m0, 'variants': rows, 'fragile_tags': fragile,
                              'verdict': '切点脆弱' if len(fragile) >= 3 else ('需更多证据' if fragile else '连续稳健')}

    # ---------- 2. 分年稳定性（主窗内 2025H2 vs 2026 + 全窗分年） ----------
    R['yearly'] = {}
    for name in ('base', 'Top1', 'planB', 'H8', 'M3'):
        tr = base_tr if name == 'base' else scheme_trades[name]
        mw = main_window(tr)
        tot = sum(t['r'] for t in mw) or 1e-9
        ysum = {y: sum(t['r'] for t in mw if t['xt'][:4] == y) for y in ('2025', '2026')}
        driver = max(ysum.values()) / tot if tot else None
        R['yearly'][name] = {'main_window_by_year': by_year(mw),
                             'year_sum_share': {y: round(v / tot * 100, 1) for y, v in ysum.items()},
                             'full_by_year': by_year(tr),
                             'single_year_driver_gt100pct': bool(driver and driver > 1.0)}

    # ---------- 3. walk-forward 前验 ----------
    grid = [dict(k=k, e=e, N=N, m=m) for k in (6.0, 7.5) for e in (0.2, 0.3)
            for N in (15, 20) for m in (1, 2)]
    cuts = [('2025-01-01', '2025-06-01'), ('2025-06-01', '2026-01-01'), ('2026-01-01', '2026-12-31')]
    wf = []
    grid_res = {}
    for g in grid:
        tr = run(pool, bull, **g)
        grid_res[tuple(sorted(g.items()))] = tr
    for t0, t1 in cuts:
        cands = []
        for g in grid:
            tr = grid_res[tuple(sorted(g.items()))]
            mtr = metrics([t for t in tr if t['xt'] < t0])
            if mtr['n'] >= 30 and mtr['median'] is not None:
                cands.append((mtr['median'], mtr['win'], mtr['mean'], g))
        cands.sort(key=lambda x: (-x[0], -x[1], -x[2]))
        best = cands[0]
        tr = grid_res[tuple(sorted(best[3].items()))]
        test = metrics([t for t in tr if t0 <= t['xt'] < t1])
        base_test = metrics([t for t in base_tr if t0 <= t['xt'] < t1])
        wf.append(dict(cut=t0, test_until=t1, picked=best[3],
                       train_n=metrics([t for t in grid_res[tuple(sorted(best[3].items()))] if t['xt'] < t0])['n'],
                       test=test, base_test=base_test, nonneg=bool(test['median'] is not None and test['median'] >= 0)))
    R['walkforward'] = wf

    # ---------- 4. 肥尾依赖度（主窗剔 top5% 厚利笔） ----------
    R['fattail'] = {}
    for name in ('base', 'Top1', 'planB', 'H8', 'M3'):
        tr = base_tr if name == 'base' else scheme_trades[name]
        mw = main_window(tr)
        m0 = metrics(mw)
        rs = sorted(mw, key=lambda t: -t['r'])
        k = max(1, int(round(0.05 * len(mw))))
        top = rs[:k]; rest = rs[k:]
        m1 = metrics(rest)
        R['fattail'][name] = dict(top5_n=k, top5_sum=round(sum(t['r'] for t in top), 2),
                                  top5_share_of_mean_pct=round(sum(t['r'] for t in top) / (m0['mean'] * m0['n']) * 100, 1) if m0['mean'] else None,
                                  after=dict(n=m1['n'], median=m1['median'], mean=m1['mean'], win=m1['win']),
                                  mean_retained_pct=round(m1['mean'] / m0['mean'] * 100, 1) if m0['mean'] else None)

    # ---------- 厚利桶保全线（fd r>=8, 一票否决） ----------
    tb0 = R['baseline']['thick_bucket']
    R['thick_veto'] = {'baseline': tb0, 'schemes': {}, 'rule': 'fd(r>=8) sum 降幅>5% → 一票否决'}
    for name in ('Top1', 'planB', 'H8', 'M3'):
        tb = R[name]['thick_bucket']
        drop = (tb0['sum'] - tb['sum']) / tb0['sum'] * 100 if tb0['sum'] else None
        R['thick_veto']['schemes'][name] = dict(bucket=tb, sum_drop_pct=round(drop, 1) if drop is not None else None,
                                                veto=bool(drop is not None and drop > 5))

    # ---------- 5. vintage 敏感性（seed=42，3 组 5% + 3 组 10%） ----------
    rng = random.Random(SEED)
    tkrs = sorted(pool)
    R['vintage'] = {}
    for frac, ngrp in ((0.05, 3), (0.10, 3)):
        ndrop = max(1, round(frac * len(tkrs)))
        res = []
        for gi in range(ngrp):
            shuffled = tkrs[:]; rng.shuffle(shuffled)
            sub = {t: pool[t] for t in shuffled[ndrop:]}
            sb = engine.compute_idx(sub)
            row = {}
            for name in ('base', 'Top1', 'planB', 'H8', 'M3'):
                tr = run(sub, sb) if name == 'base' else run(sub, sb, **P(**SCHEMES[name]))
                row[name] = metrics(main_window(tr))
            res.append(dict(group=gi + 1, dropped=ndrop, metrics=row))
        R['vintage'][f'drop{int(frac*100)}pct'] = res

    # ---------- 7. regime / 熊市腿证伪 ----------
    # 7a. fd×bull 定义性恒真复核（有闸时 fd 全在 bull 日）
    fd_all = [t for t in base_tr if t['kind'] == 'fd']
    R['regime'] = {'fd_bull_gate_tautology': {'fd_total': len(fd_all),
                    'fd_on_bull_days': len(fd_all), 'note': '闸内在场=恒真，无信息量'}}
    # 7b. 无闸对照：fd_bear（熊市腿）表现
    tr_ng, _ = engine.run_all(pool, bull, fd_gate=False, v2=True)
    fd_ng = [t for t in tr_ng if t['kind'] == 'fd']

    rows = [(b['time'], b['close']) for bars in pool.values() for b in bars]
    s = pd.DataFrame(rows, columns=['t', 'c']).groupby('t')['c'].mean().sort_index()
    ma = s.rolling(50, min_periods=1).mean()
    bullmap = {t: bool(s[t] > ma[t]) for t in s.index}
    fd_bear = [t for t in fd_ng if not bullmap.get(t['xt'], False)]
    fd_bull = [t for t in fd_ng if bullmap.get(t['xt'], False)]
    bk = [t for t in base_tr if t['kind'] == 'bk']
    bk_bear = [t for t in bk if not bullmap.get(t['xt'], False)]
    bk_bull = [t for t in bk if bullmap.get(t['xt'], False)]
    R['regime'].update({
        'nogate_main': metrics(main_window(tr_ng)),
        'fd_bear_full': metrics(fd_bear), 'fd_bull_full': metrics(fd_bull),
        'fd_bear_by_year': by_year(fd_bear),
        'bk_bear_full': metrics(bk_bear), 'bk_bull_full': metrics(bk_bull),
        'bk_bear_by_year': by_year(bk_bear),
        'regime_asymmetry': 'fd_bear vs fd_bull 对比 = 熊市腿是否被闸掩盖/制造',
    })

    # ---------- 落盘 ----------
    def clean(o):
        import math
        if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)): return [clean(v) for v in o]
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)): return None
        return o
    with open(f'{OUT}/stress_results.json', 'w') as f:
        json.dump(clean(R), f, ensure_ascii=False, indent=1, default=str)
    print('WROTE', f'{OUT}/stress_results.json')

    # ---------- 控制台摘要 ----------
    print('\n=== 主窗(V2) ===')
    for name in ('base', 'Top1', 'planB', 'H8', 'M3'):
        m = R['baseline']['main_V2'] if name == 'base' else R[name]['main']
        print(f"{name:6s} n={m['n']:5d} median={m['median']:8.4f} win={m['win']}% mean={m['mean']}")
    print('\n=== 厚利桶 ===')
    print('base:', tb0)
    for name, v in R['thick_veto']['schemes'].items():
        print(f"{name:6s} drop={v['sum_drop_pct']}% veto={v['veto']}")
    print('\n=== 脆弱标签 ===')
    for name in ('Top1', 'planB', 'H8', 'M3'):
        print(name, R['perturb'][name]['verdict'], R['perturb'][name]['fragile_tags'])
    print('\n=== walk-forward ===')
    for w in wf: print(w['cut'], 'picked', w['picked'], 'test', w['test'], 'nonneg', w['nonneg'])
    print('\n=== 肥尾(mean保留%) ===')
    for name in ('base', 'Top1', 'planB', 'H8', 'M3'):
        print(name, R['fattail'][name]['mean_retained_pct'], 'top5占mean%', R['fattail'][name]['top5_share_of_mean_pct'])
    print('\n=== regime ===')
    print('fd_bear:', R['regime']['fd_bear_full'], 'by_year', R['regime']['fd_bear_by_year'])
    print('fd_bull:', R['regime']['fd_bull_full'])
    print('bk_bear:', R['regime']['bk_bear_full'])
    print('nogate_main:', R['regime']['nogate_main'])
    print('\n=== vintage(主窗 median 漂移) ===')
    for key, res in R['vintage'].items():
        for r in res:
            print(key, r['group'], {k: v['median'] for k, v in r['metrics'].items()})

if __name__ == '__main__':
    main()
