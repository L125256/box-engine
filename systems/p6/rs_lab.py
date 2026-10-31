# -*- coding: utf-8 -*-
"""单兵相对强度实验：不设全市场闸门，只看个股自己的趋势 + 相对强度。

候选入场（全部只用收盘及以前的数据，次日开盘成交）：
  P  趋势回踩：站上 MA50、MA50>MA100、MA50/MA100 向上；20 日跑赢等权指数；
     回踩 MA20（dev20<=-2%）且 RSI2<=40
  PD 深回踩：同上，但 dev20<=-5%、RSI2<=30
  B  新高突破：趋势 + 相对强度；收盘创 20/60 日新高
  R  MA10/MA20 回收：趋势 + 相对强度；先前 5 日内曾低于 MA50 达 5%，今天收回 MA10/MA20

出场：单档止盈/止损 + 时间退出；5x、单笔保证金 3%、最多 16 仓、毛敞口 2.5 倍。
输出：全样本、2026 真实段、组合年化/回撤。研究脚本，不生成页面。
"""
import os
import sys
import json

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))          # work/regime_lab
WORK = os.path.dirname(HERE)                               # local: work/regime_lab -> work
ROOT = os.path.dirname(WORK)                               # repo: systems/p6 -> repo
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'),
           os.path.join(ROOT, 'v2', 'engine'),
           os.path.join(HERE, 'fastdip'), os.path.join(WORK, 'fastdip'),
           os.path.join(WORK, 'fd1'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import v2_lib as L
from strategy import load
from variants import sim_trade
from portfolio import port

COST = 0.001
FUND = 0.0003


def build_events(A, F, RG, cal, kind, trend='ma50', rs='idx+2', min_dv=30e6):
    n = len(cal)
    idx = RG['idx']
    ms50 = {}
    for s in A:
        ma = F[s]['ma50']
        a = np.full(n, np.nan)
        a[10:] = ma[10:] / ma[:-10] - 1
        ms50[s] = a

    out = []
    for i in range(230, n - 1):
        idx20 = idx[i] / idx[i - 20] - 1 if i >= 20 else 0.0
        for s, b in A.items():
            if s in L.ETF or s in L.LEV:
                continue
            if not b['real'][i] or i - b['first'] < 220 or b['jump'][i]:
                continue
            f = F[s]
            c = float(b['c'][i])
            if c < 5 or f['dv20'][i] < min_dv:
                continue
            if np.isnan(f['atrp'][i]) or f['atrp'][i] > 0.06:
                continue
            ma50, ma100 = f['ma50'][i], f['ma100'][i]
            if np.isnan(ma50) or np.isnan(ma100) or np.isnan(f['slope100'][i]):
                continue
            if trend == 'ma50':
                if not (c > ma50 > ma100) or ms50[s][i] < 0 or f['slope100'][i] < 0:
                    continue
            elif trend == 'ma50_only':
                if not (c > ma50) or ms50[s][i] < 0:
                    continue
            elif trend == 'ma100':
                if not (c > ma100) or f['slope100'][i] < 0:
                    continue
            else:
                raise ValueError(trend)

            r20 = float(f['ret20'][i])
            if rs == 'idx' and not (r20 > idx20):
                continue
            if rs == 'idx+2' and not (r20 > idx20 + 0.02):
                continue
            if rs == 'idx+5' and not (r20 > idx20 + 0.05):
                continue
            if rs == 'abs' and r20 <= 0:
                continue
            if rs == 'abs+idx2' and not (r20 > 0 and r20 > idx20 + 0.02):
                continue
            if rs == 'abs+idx5' and not (r20 > 0 and r20 > idx20 + 0.05):
                continue

            if kind == 'pullback':
                if f['dev20'][i] > -0.02 or f['rsi2'][i] > 40:
                    continue
                score = float(f['rsi2'][i])
            elif kind == 'pullback_deep':
                if f['dev20'][i] > -0.05 or f['rsi2'][i] > 30:
                    continue
                score = float(f['rsi2'][i])
            elif kind in ('breakout20', 'breakout60'):
                hi = f['hi20'][i - 1] if kind == 'breakout20' else f['hi60'][i - 1]
                if c < hi:
                    continue
                score = -r20
            elif kind in ('reclaim10', 'reclaim20'):
                ma = f['ma10'] if kind == 'reclaim10' else f['ma20']
                if np.isnan(ma[i]) or np.isnan(ma[i - 1]):
                    continue
                if not (c > ma[i] and b['c'][i - 1] <= ma[i - 1]):
                    continue
                was_deep = False
                for j in range(max(0, i - 5), i):
                    if not np.isnan(f['ma50'][j]) and b['c'][j] < f['ma50'][j] * 0.95:
                        was_deep = True
                        break
                if not was_deep:
                    continue
                score = float(f['rsi2'][i])
            else:
                raise ValueError(kind)
            out.append(dict(i=i, sym=s, score=score, atr=float(f['atr'][i])))
    return out


def stats_rows(rows):
    p = np.array([r['pnl'] for r in rows]) if rows else np.array([])
    if not len(p):
        return dict(n=0, win=0, avg=0, pf=0)
    return dict(n=len(p), win=round(float((p > 0).mean() * 100), 1),
                avg=round(float(p.mean() * 100), 2),
                pf=round(float(p[p > 0].sum() / max(-p[p <= 0].sum(), 1e-9)), 2))


def main():
    A, F, RG, cal = load()
    months = (len(cal) - 230) / 30.44
    cases = [
        # name, kind, trend, rs, sl, tp, hold
        ('P1 回踩 RS2', 'pullback', 'ma50', 'idx+2', 1.5, 0.8, 5),
        ('P2 回踩 无RS', 'pullback', 'ma50', 'none', 1.5, 0.8, 5),
        ('P3 回踩 RS5', 'pullback', 'ma50', 'idx+5', 1.5, 0.8, 5),
        ('P4 回踩 仅MA50', 'pullback', 'ma50_only', 'idx+2', 1.5, 0.8, 5),
        ('P5 回踩 MA100', 'pullback', 'ma100', 'idx+2', 1.5, 0.8, 5),
        ('PD 深回踩 RS2', 'pullback_deep', 'ma50', 'idx+2', 1.5, 0.8, 5),
        ('PD2 深回踩 绝对', 'pullback_deep', 'ma50', 'abs', 1.5, 0.8, 5),
        ('P6 回踩 绝对RS', 'pullback', 'ma50', 'abs', 1.5, 0.8, 5),
        ('P7 回踩 绝对+RS2', 'pullback', 'ma50', 'abs+idx2', 1.5, 0.8, 5),
        ('P8 回踩 绝对+RS2 1.0TP', 'pullback', 'ma50', 'abs+idx2', 1.5, 1.0, 8),
        ('P9 回踩 绝对+RS2 1.5TP', 'pullback', 'ma50', 'abs+idx2', 1.5, 1.5, 10),
        ('P10 回踩 绝对+RS2 1.2SL', 'pullback', 'ma50', 'abs+idx2', 1.2, 0.8, 5),
        ('B1 20日新高 RS2', 'breakout20', 'ma50', 'idx+2', 1.5, 1.5, 10),
        ('B2 20日新高 无RS', 'breakout20', 'ma50', 'none', 1.5, 1.5, 10),
        ('B3 60日新高 RS2', 'breakout60', 'ma50', 'idx+2', 1.5, 2.0, 10),
        ('R1 MA10回收 RS2', 'reclaim10', 'ma50', 'idx+2', 1.5, 0.8, 5),
        ('R2 MA20回收 RS2', 'reclaim20', 'ma50', 'idx+2', 1.5, 1.0, 8),
        ('R3 MA10回收 绝对', 'reclaim10', 'ma50', 'abs', 1.5, 0.8, 5),
        ('R4 MA20回收 绝对', 'reclaim20', 'ma50', 'abs', 1.5, 1.0, 8),
    ]
    i0 = next(k for k, d in enumerate(cal) if d >= '2026-01-26')
    print('%-18s %5s %6s %6s %5s %6s | %5s %6s %5s | %6s %6s | %7s %7s' % (
        '变体', 'n', '笔/月', '胜率', 'PF', '均值', '25笔', '25PF', '26笔', '26胜率', '26PF', '26年化', '26回撤'))
    out = []
    for name, kind, trend, rs, sl, tp, hold in cases:
        ev = build_events(A, F, RG, cal, kind, trend, rs)
        if not ev:
            print('%-18s 无信号' % name)
            continue
        by = {}
        for x in ev:
            by.setdefault(x['i'], []).append(x)
        rows = []
        for i in sorted(by):
            for x in sorted(by[i], key=lambda z: z['score'])[:5]:
                r = sim_trade(A[x['sym']], x['i'], x['atr'], sl, [(tp, 1.0)], hold)
                if r:
                    rows.append(r)
        s = stats_rows(rows)
        r25 = stats_rows([r for r in rows if cal[r['entry']] < '2026-01-26'])
        r26 = stats_rows([r for r in rows if cal[r['entry']] >= '2026-01-26'])
        po = port(A, cal, ev, sl=sl, tp=tp, hold=hold, margin=0.03, maxpos=16,
                  gross_cap=2.5, capday=5)
        ev26 = [x for x in ev if x['i'] >= i0]
        po26 = port(A, cal, ev26, sl=sl, tp=tp, hold=hold, margin=0.03, maxpos=16,
                    gross_cap=2.5, capday=5, start=i0)
        print('%-18s %5d %6.1f %6.1f %5.2f %+6.2f | %5d %6.2f %5d %6.1f %5.2f | %+6.1f%% %6.2f%% | %+7.1f%% %7.2f%%' % (
            name, s['n'], s['n'] / months, s['win'], s['pf'], s['avg'],
            r25['n'], r25['pf'], r26['n'], r26['win'], r26['pf'], po['cagr'], po['mdd'],
            po26['cagr'], po26['mdd']))
        out.append(dict(name=name, kind=kind, trend=trend, rs=rs, sl=sl, tp=tp, hold=hold,
                        stats=s, s25=r25, s26=r26, port=po, port26=po26))

    print('\nP6 仓位敏感性（2026 段，回踩 + 绝对RS + 0.8TP/1.5SL/5根）：')
    ev = build_events(A, F, RG, cal, 'pullback', 'ma50', 'abs')
    ev26 = [x for x in ev if x['i'] >= i0]
    for tag, margin, maxpos, capday in [
            ('3%×16 cap5', 0.03, 16, 5),
            ('4%×12 cap5', 0.04, 12, 5),
            ('5%×10 cap5', 0.05, 10, 5),
            ('4%×12 cap3', 0.04, 12, 3),
            ('5%×10 cap3', 0.05, 10, 3)]:
        p = port(A, cal, ev26, sl=1.5, tp=0.8, hold=5, margin=margin, maxpos=maxpos,
                 gross_cap=2.5, capday=capday, start=i0)
        print('  %-12s 期末 %.3f  年化 %+5.1f%%  回撤 %5.2f%%  笔数 %d' % (
            tag, p['final'], p['cagr'], p['mdd'], p['n']))

    print('\nP6 去掉 20 日均额门槛（min_dv=0）：')
    for tag, rs_mode in [('绝对RS', 'abs'), ('无RS', 'none'), ('跑赢指数2pp', 'idx+2')]:
        ev_nd = build_events(A, F, RG, cal, 'pullback', 'ma50', rs_mode, min_dv=0)
        byn = {}
        for x in ev_nd:
            byn.setdefault(x['i'], []).append(x)
        rows_nd = []
        for i in sorted(byn):
            for x in sorted(byn[i], key=lambda z: z['score'])[:5]:
                r = sim_trade(A[x['sym']], x['i'], x['atr'], 1.5, [(0.8, 1.0)], 5)
                if r:
                    rows_nd.append(r)
        s_nd = stats_rows(rows_nd)
        r26_nd = stats_rows([r for r in rows_nd if cal[r['entry']] >= '2026-01-26'])
        po_nd = port(A, cal, [x for x in ev_nd if x['i'] >= i0], sl=1.5, tp=0.8, hold=5,
                     margin=0.03, maxpos=16, gross_cap=2.5, capday=5, start=i0)
        print('  %-12s n=%3d 笔/月 %5.1f 胜率 %5.1f%% PF %5.2f ｜ 26 n=%3d 胜率 %5.1f%% PF %5.2f ｜ 3%%×16 年化 %+5.1f%% 回撤 %5.2f%%'
              % (tag, s_nd['n'], s_nd['n'] / months, s_nd['win'], s_nd['pf'],
                 r26_nd['n'], r26_nd['win'], r26_nd['pf'], po_nd['cagr'], po_nd['mdd']))

    print('\nP6 按市场状态拆分（全样本 / 2026）：')
    for label, evs in [('全样本', ev), ('2026', ev26)]:
        bym = {}
        for x in evs:
            bym.setdefault(x['i'], []).append(x)
        pairs = []
        for i in sorted(bym):
            for x in sorted(bym[i], key=lambda z: z['score'])[:5]:
                r = sim_trade(A[x['sym']], x['i'], x['atr'], 1.5, [(0.8, 1.0)], 5)
                if r:
                    pairs.append((x, r))
        for tag, test in [('指数>MA50', lambda x: RG['gate'][x['i']]),
                          ('指数<MA50', lambda x: not RG['gate'][x['i']]),
                          ('指数>MA100', lambda x: RG['gate100'][x['i']]),
                          ('指数<MA100', lambda x: not RG['gate100'][x['i']])]:
            rr = [r for x, r in pairs if test(x)]
            st = stats_rows(rr)
            print('  %-4s %-9s n=%3d 胜率 %5.1f%% PF %5.2f 均值 %+5.2f%%' % (
                label, tag, st['n'], st['win'], st['pf'], st['avg']))

    json.dump(out, open(os.path.join(HERE, 'rs_lab.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
