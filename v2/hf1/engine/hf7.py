#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第七轮：把 v2.1 的 A 层与 B 层叠成「高胜率 + 机会多」系统，并做邻域/成本/样本外检验。

不新增拟合参数：B 层是 v2_final 里已有但没启用的第二层（RSI2≤15、收阳、止盈1.5/止损2.0/持有7）。
只测：层数、槽位与保证金、广度阈值、B 层阈值邻域、成本。
"""
import os, sys, json, datetime, itertools, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
ROOT = os.path.dirname(WORK)
TOP = os.path.dirname(ROOT)
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'),
           os.path.join(ROOT, 'v2'), os.path.join(ROOT, 'v2', 'engine'),
           os.path.join(TOP, 'v2', 'engine'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
import v2_lib as V                                        # noqa: E402
from v2_final import A_RULES, B_RULES, dedupe, START      # noqa: E402

BR_WIN = 5


def load():
    for _c in (os.environ.get('V2_CACHE'), os.path.join(WORK, 'cache_fresh'),
               os.path.join(TOP, 'cache_fresh'), os.path.join(ROOT, 'cache_fresh')):
        if _c and os.path.isdir(_c):
            V.CACHE = _c
            break
    raw, cal, g = V.load_all(include_lev=False, include_etf=False)
    A = V.align(raw, cal, g)
    F = V.features(A)
    RG = V.build_regime(A, cal)
    BR, _ = V.breadth(A, F, cal)
    BR5 = V._roll(np.where(np.isnan(BR), 0.0, BR), BR_WIN)
    return A, F, RG, BR, BR5, cal


def gate_of(RG, br5, br_min):
    r = dict(RG)
    gt = RG['gate'].copy()
    if br_min is not None:
        gt = gt & (np.nan_to_num(br5, nan=0.0) >= br_min)
    r['gate'] = gt
    return r


def tier(b_dev=-0.02, b_rsi=15, b_atrp=0.06, exit_=None):
    r = dict(B_RULES)
    r.update(dev20_max=b_dev, rsi2_max=b_rsi, atrp_max=b_atrp)
    r['sig_exit'] = exit_ or dict(sl_atr=2.0, tp_atr=1.5, hold=7)
    return r


def C_layer(min_drop5=-0.05, rsi=25, dev=-0.02, atrp=0.05):
    """第三层：5 日跌幅达标 + RSI2 低位 + 收阳确认（不追高：仍在 MA20 下方）。"""
    return dict(require_gate=True, gate_mode='ma50', trend_ma=100, slope_min=0.0,
                dev20_max=dev, rsi2_max=rsi, ret3_max=9.9, atrp_max=atrp,
                min_dv=20e6, min_price=5, warmup=210, score='rsi', tier='C',
                green_only=True, min_drop5=min_drop5,
                sig_exit=dict(sl_atr=2.0, tp_atr=1.5, hold=7))


def evaluate(A, F, RG, BR, BR5, cal, layers, br_min, prof, cost_side=None, tag=''):
    RGx = gate_of(RG, BR5, br_min)
    sig = []
    for r in layers:
        sig += V.make_signals(A, F, RGx, BR, dict(r))
    sig = dedupe(sig)
    p = dict(prof)
    if cost_side:
        p['cost_side'] = cost_side
    sim = V.simulate(A, F, RGx, sig, p)
    st = V.stats(sim, START, len(cal) - 1)
    oos = V.stats(sim, [i for i, d in enumerate(cal) if d >= '2026-01-01'][0], len(cal) - 2)
    days = (np.datetime64(cal[-2]) - np.datetime64(cal[START])).astype(int)
    months = days / 30.44
    tr = sim['trades']
    ex = np.array([t['pnl'] for t in tr]) if tr else np.array([0.0])
    top5 = float(np.sort(ex)[::-1][:5].sum() / max(1e-9, ex[ex > 0].sum()) * 100)
    mix = collections.Counter(t.get('tier', 'A') for t in tr)
    # 追高检查：信号日收盘距 20 日最高
    chase = []
    for t in tr:
        s, i = t['sym'], t['entry'] - 1
        b = A[s]
        if i > 0:
            hi = b['h'][max(0, i - 19):i + 1].max()
            chase.append(float(b['c'][i] / hi - 1))
    near = round(float(np.mean([x > -0.02 for x in chase]) * 100), 1) if chase else None
    return dict(tag=tag, n=st['n'], per_month=round(st['n'] / months, 1),
                win=round(st['win'], 1), payoff=round(st['payoff'], 2), pf=round(st['pf'], 2),
                cagr=round(st['cagr'], 1), mdd=round(st['mdd'], 2), liq=st['liq'],
                expo=round(st['expo'], 1), top5=round(top5, 1), near_high_pct=near,
                oos_n=oos['n'], oos_win=round(oos['win'], 1), oos_pf=round(oos['pf'], 2),
                oos_cagr=round(oos['cagr'], 1), oos_mdd=round(oos['mdd'], 2),
                mix=dict(mix), sig=len(sig))


def show(r):
    print('%-30s n=%4d win=%5.1f pay=%4.2f pf=%4.2f cagr=%5.1f mdd=%5.1f pm=%4.1f top5=%4.1f 追高=%4.1f%% '
          '| 2026 n=%3d win=%5.1f pf=%4.2f' % (
              r['tag'], r['n'], r['win'], r['payoff'], r['pf'], r['cagr'], r['mdd'],
              r['per_month'], r['top5'], r['near_high_pct'] or 0, r['oos_n'], r['oos_win'], r['oos_pf']),
          flush=True)


def main():
    A, F, RG, BR, BR5, cal = load()
    P4 = dict(lev=5, margin_pct=0.04, max_pos=12, gross_cap=2.5)
    P3 = dict(lev=5, margin_pct=0.03, max_pos=16, gross_cap=2.5)
    P25 = dict(lev=5, margin_pct=0.025, max_pos=20, gross_cap=2.5)
    P2 = dict(lev=5, margin_pct=0.02, max_pos=25, gross_cap=2.5)
    rows = []

    print('=== 层数对照（广度 45%）')
    for tag, layers, prof in (
            ('A 单腿(=v2.1)', [dict(A_RULES)], P4),
            ('A+B', [dict(A_RULES), tier()], P4),
            ('A+B 3%×16', [dict(A_RULES), tier()], P3),
            ('A+B 2.5%×20', [dict(A_RULES), tier()], P25),
            ('A+B 2%×25', [dict(A_RULES), tier()], P2),
            ('A+C', [dict(A_RULES), C_layer()], P3),
            ('A+B+C', [dict(A_RULES), tier(), C_layer()], P3),
            ('A+B+C 2.5%×20', [dict(A_RULES), tier(), C_layer()], P25),
            ('A+B+C 2%×25', [dict(A_RULES), tier(), C_layer()], P2)):
        r = evaluate(A, F, RG, BR, BR5, cal, layers, 0.45, prof, tag=tag)
        rows.append(r); show(r)

    print('\n=== 广度阈值（A+B+C，3%×16）')
    for bm in (None, 0.40, 0.45, 0.50, 0.55):
        r = evaluate(A, F, RG, BR, BR5, cal, [dict(A_RULES), tier(), C_layer()], bm, P3,
                     tag='广度 %s' % bm)
        rows.append(r); show(r)

    print('\n=== B/C 层阈值邻域（A+B+C，3%×16，广度45%）')
    for dv, rs in itertools.product((-0.03, -0.02, -0.015), (10, 15, 20)):
        r = evaluate(A, F, RG, BR, BR5, cal,
                     [dict(A_RULES), tier(b_dev=dv, b_rsi=rs), C_layer(dev=dv, rsi=rs)], 0.45, P3,
                     tag='B/C dev%.3f rsi%d' % (dv, rs))
        rows.append(r); show(r)

    print('\n=== 成本敏感性（A+B+C，3%×16，广度45%）')
    lay = [dict(A_RULES), tier(), C_layer()]
    for cs in (0.001, 0.0015, 0.002):
        r = evaluate(A, F, RG, BR, BR5, cal, lay, 0.45, P3, cost_side=cs,
                     tag='单边 %.2f%%（往返 %.1f%%）' % (cs * 100, cs * 200))
        rows.append(r); show(r)

    json.dump(rows, open(os.path.join(HERE, 'sweep7.json'), 'w'), ensure_ascii=False, indent=1)
    print('\n=== 按 min(全样本PF, 2026PF) 排序')
    for r in sorted(rows, key=lambda z: -min(z['pf'], z['oos_pf'])):
        print('%-30s 全 win=%5.1f pf=%4.2f pm=%4.1f mdd=%5.1f | 2026 win=%5.1f pf=%4.2f' % (
            r['tag'], r['win'], r['pf'], r['per_month'], r['mdd'], r['oos_win'], r['oos_pf']))


if __name__ == '__main__':
    main()
