#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H-A2 机械重判常设件（RESCUE_PACK a 单 + d 单搭车 · 2026-10-18）
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/RESCUE_PACK.md §三 a/d 单
- a 单：重跑 IC(RankIC/NormalIC)、分位多空价差、费后 breakeven、按日稳定性；
  只报数不改状态；接口 --date YYYY-MM-DD --lookback 20；每日收盘后自动跑并追加台账。
- d 单：三时钟（日历30自然日/样本每20 IC日/性能滚动20日费后IC<0）触发=重判触发器
  而非死亡判令；触发后自动出重判报表 + 降权/换周期/换门三改造路径各附数，
  三者试尽才允许退场（本件输出三路径数字，退场决定权归会诊）。

【口径（OD-R1..R7，开工即冻结）】
OD-R1 数据态 = /tmp/box_cache（engine_snapshot 唯一数据态，聚合 md5=
  0e4c4fb9e487ff251639efa5fe06b05e 已核，与 /tmp/dneg/box_cache 零漂移）；禁换源。
OD-R2 合成信号 = dneg_engine（f1_backtest_v2 逐行权威谱系）四因子 cross_scores
  z-mean（ma20_slope/obv_slope20/dist_52w_high/mom_1m），与 H-A OD8 完全同构。
OD-R3 IC 日 = 每周首个交易日；前向收益 = fwd5 交易日收盘收益；截面 ≥30 名才计。
OD-R4 RankIC = 截面 Spearman；NormalIC = 截面 Pearson。
OD-R5 分位多空价差 = 合成分排序五分位 Q5−Q1 的 fwd5 均值差（pp）。
OD-R6 费后 breakeven = Q5−Q1 价差(pp) ÷ 双边费(pp)；双边费=2×FEE_SIDE×100
  （现行 0.10pp；费压×1.5=0.15pp 伴行）。常数费不改秩，费后 IC≡毛 IC（口径注记）。
OD-R7 20 IC 日对账基准 = H-A stage2 p3 base_ic（old131 −0.008448042967886888 /
  full144 +0.00402764271546957，n=20，realC 2026-06-01→2026-10-17）。
  重跑逐日 RankIC 均值与基准差 >1e-6 必须给口径解释。
OD-R8 d 单性能时钟 = 滚动 20 个 IC 日 RankIC 均值首次 <0（费后口径注记见 OD-R6）。
OD-R9 d 单三路径：①降权=SLOT 0.10→0.05 重跑 base 引擎；②换周期=fwd5→fwd10/fwd20
  同 20 信号日 RankIC；③换门=H-D 冻结 T2 vol20 p80 pause 门（引用 wo_hd_result.json
  权威数字，不重跑不烧窗）。路径 viable = realC 净年化改善>0 且 MDD 不放大。

用法：
  python3 h_a2_rejudge.py                        # 默认 date=数据末日 lookback=20
  python3 h_a2_rejudge.py --date 2026-10-17 --lookback 20
台账：research/wo_rescue/h_a2_ledger.jsonl（追加写；重判+衰减双报表一次产出）。
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, '/workspace/repo_ready/research/wo_dneg')
import dneg_engine as DE

SEED = 42
CACHE = '/tmp/box_cache'
OUT = '/workspace/repo_ready/research/wo_rescue'
os.makedirs(OUT, exist_ok=True)
LEDGER = os.path.join(OUT, 'h_a2_ledger.jsonl')
REALC = (pd.Timestamp('2026-06-01'), pd.Timestamp('2026-10-17'))
BASELINE_REJUDGE = {'old131': -0.008448042967886888, 'full144': 0.00402764271546957}
BASELINE_N = 20
# OD-R9 换门权威数字（引用，不重跑）：wo_hd 八列表 realC 段
WO_HD = '/workspace/repo_ready/research/wo_hd/wo_hd_result.json'

_DATA = None
_POOLS = None
_F = None


def _init():
    global _DATA, _POOLS, _F
    if _DATA is None:
        _DATA = DE.load_data(CACHE)
        _POOLS = DE.build_pools(_DATA)
        _F = DE.build_factors(_DATA)


def signal_days(syms, date_hi):
    """OD-R3：每周首个交易日，≤date_hi。"""
    close = pd.DataFrame({s: _DATA[s]['close'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(_DATA[s].index) for s in syms])))
    cal = cal[cal <= date_hi]
    iso = cal.isocalendar()
    sig = pd.DatetimeIndex(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)
    return cal, sig


def rejudge_day(task):
    """单池单信号日：RankIC/NormalIC/Q5-Q1 价差（引擎 cross_scores 同构）。"""
    pname, t, fwd_h = task
    syms = _POOLS[pname]
    score = DE.cross_scores(_F, syms, t, DE.FACTORS_4)
    close = pd.DataFrame({s: _DATA[s]['close'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(_DATA[s].index) for s in syms])))
    close = close.reindex(cal)
    y = close.shift(-fwd_h) / close - 1
    y = y.loc[t]
    m = score.index.intersection(y.dropna().index)
    if len(m) < 30 or score[m].std() == 0:
        return None
    s, yy = score[m], y[m]
    rank_ic = float(np.corrcoef(s.rank(), yy.rank())[0, 1])
    norm_ic = float(np.corrcoef(s, yy)[0, 1])
    q = pd.qcut(s.rank(method='first'), 5, labels=False)
    spread_pp = float(yy[q == 4].mean() - yy[q == 0].mean()) * 100.0
    return {'date': str(t.date()), 'rank_ic': rank_ic, 'normal_ic': norm_ic,
            'q5_q1_spread_pp': round(spread_pp, 4), 'n_names': int(len(m))}


def run_rejudge(date_hi, lookback, fwd_horizons=(5,)):
    """OD-R2..R6：最近 lookback 个 IC 日逐日重判（多 horizon 供 d 单换周期路径）。"""
    _init()
    out = {}
    for pname in _POOLS:
        cal, sig = signal_days(_POOLS[pname], date_hi)
        sig = sig[(sig >= REALC[0])] if date_hi >= REALC[0] else sig
        sig = sig[-lookback:]
        # 逐 horizon 重判（rejudge_day 单日单 horizon；本量级直跑）
        by_h = {}
        for h in fwd_horizons:
            hh = [rejudge_day((pname, t, h)) for t in sig]
            hh = [r for r in hh if r is not None]
            ric = pd.Series({pd.Timestamp(r['date']): r['rank_ic'] for r in hh})
            by_h[h] = {
                'days': hh,
                'n': len(hh),
                'rank_ic_mean': float(ric.mean()) if len(ric) else None,
                'rank_ic_std': float(ric.std(ddof=1)) if len(ric) > 1 else None,
                'icir': float(ric.mean() / ric.std(ddof=1)) if len(ric) > 1 else None,
                't_stat': float(ric.mean() / ric.std(ddof=1) * np.sqrt(len(ric)))
                          if len(ric) > 1 else None,
                'pos_day_share': float((ric > 0).mean()) if len(ric) else None,
                'normal_ic_mean': float(np.mean([r['normal_ic'] for r in hh]))
                                  if hh else None,
                'q5_q1_spread_mean_pp': float(np.mean([r['q5_q1_spread_pp'] for r in hh]))
                                        if hh else None,
                'breakeven_x_cur_fee': float(np.mean([r['q5_q1_spread_pp'] for r in hh])
                                             / (2 * DE.FEE_SIDE * 100)) if hh else None,
                'breakeven_x_fee_stress15': float(np.mean([r['q5_q1_spread_pp'] for r in hh])
                                                  / (3 * DE.FEE_SIDE * 100)) if hh else None,
            }
        out[pname] = {'n_signal_days_window': int(len(sig)), 'horizons': by_h,
                      'primary': by_h.get(5, by_h[fwd_horizons[0]])}
    return out


def reconcile(date_hi):
    """OD-R7：realC 20 IC 日逐日 RankIC 重跑 vs H-A stage2 base_ic 均值。"""
    _init()
    rec = {'baseline': BASELINE_REJUDGE, 'tolerance': 1e-6, 'per_pool': {}}
    ok_all = True
    for pname in _POOLS:
        cal, sig = signal_days(_POOLS[pname], min(date_hi, REALC[1]))
        sig = sig[sig >= REALC[0]]
        days = [rejudge_day((pname, t, 5)) for t in sig]
        days = [d for d in days if d is not None]
        mean = float(np.mean([d['rank_ic'] for d in days]))
        base = BASELINE_REJUDGE[pname]
        diff = abs(mean - base)
        ok = diff <= 1e-6
        ok_all = ok_all and ok
        rec['per_pool'][pname] = {
            'n_days': len(days), 'recomputed_mean_rank_ic': mean,
            'baseline_mean_rank_ic': base, 'abs_diff': diff,
            'pass_1e-6': bool(ok),
            'per_day': days,
            'explanation': None if ok else
                '口径解释：见报告（重跑与 H-A OD8 同构；差异来源须列明数据态/因子/截面过滤）'}
    rec['OVERALL'] = 'PASS' if ok_all else 'FAIL'
    return rec


# ---------------------------------------------------------------- d 单三时钟
def decay_monitor(rej, date_hi, baseline_n=BASELINE_N):
    """三时钟判定 + 触发后三改造路径附数（触发=重判触发器，非死亡判令）。"""
    _init()
    state = {}
    if os.path.exists(LEDGER):
        lines = [json.loads(l) for l in open(LEDGER) if l.strip()]
        state = lines[-1] if lines else {}
    last_review = state.get('date')
    days_since = None if last_review is None else \
        (pd.Timestamp(date_hi) - pd.Timestamp(last_review)).days
    ic_days_seen = state.get('n_ic_days', baseline_n)

    clocks = {}
    # 1) 日历时钟：每 30 自然日强制复审（无台账史 → 首审即触发）
    clocks['calendar_30d'] = {'days_since_last_review': days_since,
                              'trigger': bool(days_since is None or days_since >= 30)}
    # 2) 样本时钟：每新增 20 IC 日滚动复审
    n_now = max(v['primary']['n'] for v in rej.values())
    clocks['sample_20ic'] = {'ic_days_now': int(n_now), 'ic_days_baseline': int(ic_days_seen),
                             'new_ic_days': int(max(0, n_now - ic_days_seen)),
                             'trigger': bool(n_now - ic_days_seen >= 20)}
    # 3) 性能时钟：滚动 20 IC 日费后 IC（OD-R6 注记：常数费不改秩）均值首次<0
    perf = {}
    for pname, v in rej.items():
        ric = pd.Series({pd.Timestamp(d['date']): d['rank_ic']
                         for d in v['primary']['days']})
        roll = ric.rolling(min(20, len(ric))).mean().dropna()
        first_neg = roll.index[roll < 0]
        perf[pname] = {'rolling20_ic_mean': float(roll.iloc[-1]) if len(roll) else None,
                       'first_trigger_date': str(first_neg[0].date()) if len(first_neg) else None,
                       'trigger': bool(len(roll) and roll.iloc[-1] < 0)}
    clocks['performance_rolling20_ic_neg'] = perf
    clocks['performance_trigger'] = any(v['trigger'] for v in perf.values())
    triggered = clocks['calendar_30d']['trigger'] or clocks['sample_20ic']['trigger'] \
        or clocks['performance_trigger']

    paths = three_paths(rej) if triggered else {'note': '未触发，不出三路径报表'}
    return {'triggered': bool(triggered), 'clocks': clocks,
            'sunset_semantics': '触发→自动重判+三路径改造评估；降权/换周期/换门试尽才许退场，退场归会诊',
            'reform_paths': paths}


def three_paths(rej):
    """OD-R9：降权/换周期/换门三路径，各附数。"""
    _init()
    out = {}
    # ① 降权 SLOT→半（base 引擎重跑，realC 段指标）
    def seg(curve, t0, t1):
        s = curve[(curve.index >= t0) & (curve.index <= t1)]
        if len(s) < 2:
            return {}
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        ann = (s.iloc[-1] / s.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1
        mdd = (s / s.cummax() - 1).min()
        return {'ann_pct': round(ann * 100, 2), 'mdd_pct': round(mdd * 100, 2)}
    down = {}
    for pname, syms in _POOLS.items():
        r_full = DE.run_instr(_DATA, F=_F, syms=syms, gated=False, record=False)
        old = DE.SLOT
        DE.SLOT = old / 2.0
        try:
            r_half = DE.run_instr(_DATA, F=_F, syms=syms, gated=False, record=False)
        finally:
            DE.SLOT = old
        base_c = seg(r_full['curve'], *REALC)
        half_c = seg(r_half['curve'], *REALC)
        down[pname] = {'base_realC': base_c, 'half_weight_realC': half_c,
                       'viable': bool(half_c and base_c and
                                      half_c['ann_pct'] > base_c['ann_pct'] and
                                      half_c['mdd_pct'] >= base_c['mdd_pct'])}
    out['1_downweight_slot_half'] = down
    # ② 换周期：fwd10/fwd20 RankIC（同 20 信号日）vs 基准 fwd5
    cyc = {}
    for pname in _POOLS:
        cyc[pname] = {h: {'rank_ic_mean': rej[pname]['horizons'][h]['rank_ic_mean'],
                          't_stat': rej[pname]['horizons'][h]['t_stat']}
                      for h in rej[pname]['horizons']}
        best = max(((h, (v['rank_ic_mean'] or -9)) for h, v in cyc[pname].items()),
                   key=lambda x: x[1])
        cyc[pname]['best_horizon'] = best[0]
        cyc[pname]['viable'] = bool(cyc[pname][best[0]]['rank_ic_mean'] >
                                    (rej[pname]['primary']['rank_ic_mean'] or 0)
                                    and (cyc[pname][best[0]]['t_stat'] or 0) > 1)
    out['2_switch_horizon'] = cyc
    # ③ 换门：H-D T2 vol20 p80 pause（权威数字引用，不重跑）
    gate = {'source': WO_HD, 'note': '引用 wo_hd 八列表 realC 段（权威谱系，避免重烧）'}
    try:
        hd = json.load(open(WO_HD))
        tab = hd['eight_col_table']
        g = {}
        for pname in _POOLS:
            b = tab[f'{pname}|base']['realC']
            gg = tab[f'{pname}|gate_pause']['realC']
            g[pname] = {'base_realC_ann': b['annualized_pct'], 'base_realC_mdd': b['mdd_pct'],
                        'gate_realC_ann': gg['annualized_pct'], 'gate_realC_mdd': gg['mdd_pct'],
                        'viable': bool(gg['annualized_pct'] > b['annualized_pct']
                                       and gg['mdd_pct'] >= b['mdd_pct'])}
        gate['vol20_p80_pause'] = g
    except Exception as e:
        gate['error'] = f'{type(e).__name__}: {e}'
    out['3_switch_gate_vol20p80'] = gate
    any_viable = any(d.get('viable') for d in down.values()) or \
        any(v.get('viable') for v in cyc.values()) or \
        any(v.get('viable') for v in gate.get('vol20_p80_pause', {}).values())
    out['all_paths_dead'] = not any_viable
    out['disposition'] = ('存在 viable 改造路径 → 续命/改造（会诊择路）' if any_viable
                          else '三路径全灭 → 退场候选，附本穷举记录交会诊终裁（不自动下线）')
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='H-A2 机械重判常设件（a 单）+ 三时钟衰减监测（d 单搭车）')
    ap.add_argument('--date', default=None, help='YYYY-MM-DD，默认=数据末日')
    ap.add_argument('--lookback', type=int, default=20, help='IC 日数，默认 20')
    ap.add_argument('--no-reconcile', action='store_true', help='跳过 realC 20 日对账')
    args = ap.parse_args()

    _init()
    date_hi = pd.Timestamp(args.date) if args.date else \
        max(d.index[-1] for d in _DATA.values())
    t0 = time.time()

    rej = run_rejudge(date_hi, args.lookback, fwd_horizons=(5, 10, 20))
    result = {'tool': 'h_a2_rejudge', 'ts': time.strftime('%F %T'),
              'date': str(date_hi.date()), 'lookback': args.lookback,
              'cache': CACHE, 'od': 'OD-R1..R9（见文件头注，冻结）',
              'seed': SEED, 'rejudge': rej}
    if not args.no_reconcile and date_hi >= REALC[1]:
        result['reconcile_realC_20ic'] = reconcile(min(date_hi, REALC[1]))
    result['decay_monitor'] = decay_monitor(rej, date_hi)
    result['wall_secs'] = round(time.time() - t0, 1)

    with open(os.path.join(OUT, 'a_rescue_rejudge.json'), 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    with open(LEDGER, 'a') as f:      # 台账追加（重判+衰减双报表一次产出，d 单搭车）
        f.write(json.dumps({'ts': result['ts'], 'date': result['date'],
                            'lookback': args.lookback,
                            'rank_ic_mean': {p: v['primary']['rank_ic_mean']
                                             for p, v in rej.items()},
                            'n_ic_days': {p: v['primary']['n'] for p, v in rej.items()},
                            'decay_triggered': result['decay_monitor']['triggered']}
                           , ensure_ascii=False) + '\n')
    with open(os.path.join(OUT, 'd_decay_monitor.json'), 'w') as f:
        json.dump({'ts': result['ts'], 'date': result['date'],
                   **result['decay_monitor']}, f, ensure_ascii=False, indent=1)

    print('== H-A2 机械重判 ==', result['date'], f"lookback={args.lookback} "
          f"({result['wall_secs']}s)")
    for p, v in rej.items():
        pr = v['primary']
        print(f"{p}: RankIC={pr['rank_ic_mean']:+.6f} NormalIC={pr['normal_ic_mean']:+.6f} "
              f"ICIR={pr['icir']:+.3f} t={pr['t_stat']:+.2f} n={pr['n']} "
              f"Q5-Q1={pr['q5_q1_spread_mean_pp']:+.4f}pp "
              f"breakeven_x={pr['breakeven_x_cur_fee']:.2f}")
    if 'reconcile_realC_20ic' in result:
        r = result['reconcile_realC_20ic']
        print('对账:', r['OVERALL'],
              {p: f"diff={v['abs_diff']:.2e}" for p, v in r['per_pool'].items()})
    dm = result['decay_monitor']
    print('d 单三时钟: triggered =', dm['triggered'],
          {k.replace('_30d', '').replace('_20ic', ''): v.get('trigger')
           for k, v in dm['clocks'].items() if isinstance(v, dict) and 'trigger' in v})
    if dm['triggered']:
        print('改造路径 disposition:', dm['reform_paths'].get('disposition'))


if __name__ == '__main__':
    main()
