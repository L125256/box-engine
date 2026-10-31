# -*- coding: utf-8 -*-
"""深踩快打 · 组合口径复核：5x、单笔保证金、仓位数上限、毛敞口 2.5 倍。"""
import os, sys, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
import v2_lib as L
from strategy import load
from variants import entries

COST = 0.001
FUND = 0.0003
LEV = 5.0


def port(A, cal, ev, sl=1.5, tp=0.8, hold=5, margin=0.03, maxpos=16,
         gross_cap=2.5, capday=99, start=220):
    n = len(cal)
    by = {}
    for x in ev:
        by.setdefault(x['i'], []).append(x)
    eq = 1.0
    curve = np.full(n, np.nan)
    pos = {}
    ntr = 0
    for i in range(n):
        for s in list(pos):
            q = pos[s]; b = A[s]
            if i < q['e'] or b['jump'][i]:
                continue
            ep, stop, tgt = q['ep'], q['stop'], q['tgt']
            done = None
            if i > q['e'] and b['o'][i] <= stop:
                done = (b['o'][i] / ep - 1, 'stop_gap')
            elif b['l'][i] <= stop:
                done = (stop / ep - 1, 'stop')
            elif b['h'][i] >= tgt:
                done = (tgt / ep - 1, 'tp')
            elif i >= q['e'] + hold:
                done = (b['c'][i] / ep - 1, 'time')
            if done:
                r, _ = done
                eq += q['notional'] * r - q['notional'] * 2 * COST - q['notional'] * FUND * (i - q['e'])
                pos.pop(s); ntr += 1
        curve[i] = eq
        if i in by:
            used = 0
            for x in sorted(by[i], key=lambda z: z['score']):
                if len(pos) >= maxpos or used >= capday:
                    break
                s = x['sym']
                if s in pos:
                    continue
                e = i + 1
                if e >= n or not A[s]['real'][e] or A[s]['jump'][e]:
                    continue
                ep = A[s]['o'][e]
                if ep <= 0:
                    continue
                notional = margin * eq * LEV
                if sum(q['notional'] for q in pos.values()) + notional > gross_cap * eq:
                    continue
                pos[s] = dict(e=e, ep=ep, stop=ep - sl * x['atr'], tgt=ep + tp * x['atr'],
                              notional=notional)
                used += 1
    cv = curve[start:]
    final = float(cv[-1])
    peak = np.maximum.accumulate(cv)
    mdd = float((cv / peak - 1).min() * 100)
    cagr = (final ** (365.0 / len(cv)) - 1) * 100
    return dict(final=round(final, 3), cagr=round(cagr, 1), mdd=round(mdd, 2), n=ntr)


def main():
    A, F, RG, cal = load()
    cases = [
        ('基准 3%×16', dict(), dict()),
        ('基准 4%×12', dict(), dict(margin=0.04, maxpos=12)),
        ('急跌过滤 3%×16', dict(crash=-0.04), dict()),
        ('急跌过滤 4%×12', dict(crash=-0.04), dict(margin=0.04, maxpos=12)),
        ('急跌+RSI20+偏离6% 3%×16', dict(crash=-0.04, rsi=20, dev=-0.06), dict()),
    ]
    for tag, ekw, pkw in cases:
        ev = entries(A, F, RG, cal, **ekw)
        r = port(A, cal, ev, **pkw)
        print('%-24s 期末 %.3f 年化 %5.1f%% 回撤 %5.2f%% 笔数 %d' % (
            tag, r['final'], r['cagr'], r['mdd'], r['n']))


if __name__ == '__main__':
    main()
