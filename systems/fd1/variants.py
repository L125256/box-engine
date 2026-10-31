# -*- coding: utf-8 -*-
"""深踩快打 · 变体与优化：出场结构、分档止盈、保本、市场急跌过滤、参数邻域。"""
import os, sys, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
import v2_lib as L
from strategy import load, _eligible, SL_ATR, TP_ATR, HOLD

COST = 0.001
FUND = 0.0003


def entries(A, F, RG, cal, dev=-0.05, rsi=30.0, crash=None, volx=None, atrp_max=0.06):
    n = len(cal); idx = RG['idx']; out = []
    for i in range(220, n - 1):
        if crash is not None and i >= 3 and idx[i] / idx[i - 3] - 1 < crash:
            continue
        for x in _eligible(A, F, i):
            if x['dev20'] > dev or x['rsi2'] > rsi or x['atrp'] > atrp_max:
                continue
            if volx is not None:
                b = A[x['sym']]
                vm = float(np.median(b['v'][max(0, i - 20):i]))
                if vm <= 0 or b['v'][i] < volx * vm:
                    continue
            out.append(dict(i=i, sym=x['sym'], score=x['rsi2'], atr=x['atr']))
    return out


def sim_trade(b, i, atr, sl, tps, hold, be_after=None):
    """tps=[(atr, frac), ...]；每根最多成交一档。"""
    n = len(b['c'])
    e = i + 1
    if e >= n or not b['real'][e] or b['jump'][e]:
        return None
    ep = b['o'][e]
    if ep <= 0:
        return None
    stop = ep - sl * atr
    rest, realized, fund = 1.0, 0.0, 0.0
    why = 'time'
    end = min(n - 1, e + hold)
    for k in range(e, end + 1):
        if b['jump'][k]:
            continue
        fund += FUND * rest
        if k > e and b['o'][k] <= stop:
            realized += rest * (b['o'][k] / ep - 1); rest = 0; why = 'stop_gap'; break
        if b['l'][k] <= stop:
            realized += rest * (stop / ep - 1); rest = 0; why = 'stop'; break
        for ti, (a, f) in enumerate(tps):
            if rest > 1e-9 and b['h'][k] >= ep + a * atr:
                realized += f * (a * atr / ep); rest -= f
                if be_after is not None and ti == be_after:
                    stop = max(stop, ep)
                why = 'tp'
                break
        if rest <= 1e-9:
            break
    if rest > 1e-9:
        realized += rest * (b['c'][end] / ep - 1)
    return dict(pnl=realized - 2 * COST - fund, why=why, bars=end - e, entry=e)


def stat(A, ev, sl, tps, hold, be_after=None, cap=3):
    by_day = {}
    for x in ev:
        by_day.setdefault(x['i'], []).append(x)
    res = []
    for i in sorted(by_day):
        for x in sorted(by_day[i], key=lambda z: z['score'])[:cap]:
            r = sim_trade(A[x['sym']], x['i'], x['atr'], sl, tps, hold, be_after)
            if r:
                res.append(r)
    if not res:
        return None
    p = np.array([r['pnl'] for r in res])
    return dict(n=len(p), win=round(float((p > 0).mean() * 100), 1), avg=round(float(p.mean() * 100), 2),
                pf=round(float(p[p > 0].sum() / max(-p[p <= 0].sum(), 1e-9)), 2),
                sum=round(float(p.sum() * 100), 1), bars=round(float(np.mean([r['bars'] for r in res])), 1),
                tp=sum(1 for r in res if r['why'].startswith('tp')),
                stop=sum(1 for r in res if r['why'].startswith('stop')),
                time=sum(1 for r in res if r['why'] == 'time'), rows=res)


def main():
    A, F, RG, cal = load()
    months = (len(cal) - 220) / 30.44
    base_ev = entries(A, F, RG, cal)
    print('基准信号 %d 个 ｜ %.1f/月' % (len(base_ev), len(base_ev) / months))

    variants = [
        ('V0 基准 0.8ATR/1.5ATR/5根', dict(sl=1.5, tps=[(0.8, 1.0)], hold=5)),
        ('V1 止盈0.6ATR', dict(sl=1.5, tps=[(0.6, 1.0)], hold=5)),
        ('V2 止盈1.0ATR', dict(sl=1.5, tps=[(1.0, 1.0)], hold=5)),
        ('V3 止损1.2ATR', dict(sl=1.2, tps=[(0.8, 1.0)], hold=5)),
        ('V4 分档 0.6+1.2', dict(sl=1.5, tps=[(0.6, 0.5), (1.2, 0.5)], hold=8)),
        ('V5 分档+0.6后保本', dict(sl=1.5, tps=[(0.6, 0.5), (1.2, 0.5)], hold=8, be_after=0)),
        ('V6 基准+急跌过滤(-4%)', dict(sl=1.5, tps=[(0.8, 1.0)], hold=5, crash=-0.04)),
        ('V7 基准+RSI2≤20', dict(sl=1.5, tps=[(0.8, 1.0)], hold=5, rsi=20)),
        ('V8 基准+偏离≤-6%', dict(sl=1.5, tps=[(0.8, 1.0)], hold=5, dev=-0.06)),
        ('V9 基准+放量1.2x', dict(sl=1.5, tps=[(0.8, 1.0)], hold=5, volx=1.2)),
        ('V10 基准+低波ATR≤4%', dict(sl=1.5, tps=[(0.8, 1.0)], hold=5, atrp_max=0.04)),
        ('V11 持有8根', dict(sl=1.5, tps=[(0.8, 1.0)], hold=8)),
        ('V12 止盈0.6+持有8', dict(sl=1.5, tps=[(0.6, 1.0)], hold=8)),
        ('V13 分档0.5+1.0 无保本', dict(sl=1.5, tps=[(0.5, 0.5), (1.0, 0.5)], hold=8)),
        ('V14 止损1.8 止盈0.8', dict(sl=1.8, tps=[(0.8, 1.0)], hold=5)),
        ('V15 止盈1.2', dict(sl=1.5, tps=[(1.2, 1.0)], hold=8)),
    ]
    print('%-26s %5s %4s %6s %5s %7s %5s %4s %4s %4s' % ('变体', 'n', '胜率', '均值', 'PF', '累计', '持有', '止盈', '止损', '到期'))
    out = []
    for name, cfg in variants:
        ev = entries(A, F, RG, cal, dev=cfg.get('dev', -0.05), rsi=cfg.get('rsi', 30.0),
                     crash=cfg.get('crash'), volx=cfg.get('volx'), atrp_max=cfg.get('atrp_max', 0.06))
        s = stat(A, ev, cfg['sl'], cfg['tps'], cfg['hold'], cfg.get('be_after'))
        if not s:
            continue
        out.append(dict(name=name, **{k: v for k, v in s.items() if k != 'rows'}))
        print('%-26s %5d %5.1f %+6.2f %5.2f %+7.1f %5.1f %4d %4d %4d' % (
            name, s['n'], s['win'], s['avg'], s['pf'], s['sum'], s['bars'], s['tp'], s['stop'], s['time']))
    json.dump(out, open(os.path.join(HERE, 'variants.json'), 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
