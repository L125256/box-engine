# -*- coding: utf-8 -*-
"""单兵趋势持有实验：不做 0.8 ATR 快打，改成「沿 MA10 持有」。

入场（个股条件，无市场闸门）：
  TH1: MA10 回收——收盘 > MA10，前一日 <= MA10；且 c>MA10>MA20>MA50，MA10 5日向上，ret20>0
  TH2: 5 日新高——收盘 >= 前 5 日最高收盘；其余趋势条件同 TH1
  TH3: 浅回踩——dev20 <= -1%，收盘仍 > MA10；其余趋势条件同 TH1
出场：
  止损 1.5 ATR；+1.0 ATR 平一半并把止损移到成本；剩余收盘跌破 MA10 全平；最多 20 根
仓位：研究脚本只算逐笔；组合口径另跑。
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
ROOT = os.path.dirname(WORK)
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'),
           os.path.join(ROOT, 'v2', 'engine'),
           os.path.join(HERE, 'fastdip'), os.path.join(WORK, 'fastdip'),
           os.path.join(WORK, 'fd1'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import v2_lib as L
from strategy import load

COST = 0.001
FUND = 0.0003


def stack_ok(b, f, i, full=True):
    c = b['c'][i]
    ma10, ma20, ma50 = f['ma10'][i], f['ma20'][i], f['ma50'][i]
    if np.isnan(ma10) or np.isnan(ma20) or np.isnan(ma50):
        return False
    if not (c > ma10 > ma20 > ma50):
        return False
    if full:
        ma100 = f['ma100'][i]
        if np.isnan(ma100) or not (ma50 > ma100):
            return False
    if f['ret20'][i] <= 0:
        return False
    if i < 10 or np.isnan(f['ma10'][i - 5]) or f['ma10'][i] <= f['ma10'][i - 5]:
        return False
    if i < 10 or np.isnan(f['ma50'][i - 10]) or f['ma50'][i] < f['ma50'][i - 10]:
        return False
    return True


def sim_hold(b, f, i, atr, sl=1.5, tp1=1.0, hold=20, ma_key='ma10'):
    n = len(b['c'])
    e = i + 1
    if e >= n or not b['real'][e] or b['jump'][e]:
        return None
    ep = float(b['o'][e])
    if ep <= 0:
        return None
    stop = ep - sl * atr
    rest, realized, fund = 1.0, 0.0, 0.0
    why = 'time'
    half = False
    end = min(n - 1, e + hold)
    for k in range(e, end + 1):
        if b['jump'][k]:
            continue
        fund += FUND * rest
        if k > e and b['o'][k] <= stop:
            realized += rest * (b['o'][k] / ep - 1); why = 'stop_gap'; rest = 0; break
        if b['l'][k] <= stop:
            realized += rest * (stop / ep - 1); why = 'stop'; rest = 0; break
        if not half and b['h'][k] >= ep + tp1 * atr:
            realized += 0.5 * (tp1 * atr / ep)
            rest = 0.5
            half = True
            stop = max(stop, ep)
            why = 'tp1+'
        if k > e and b['c'][k] < f[ma_key][k]:
            realized += rest * (b['c'][k] / ep - 1)
            rest = 0
            why = 'ma'
            break
    if rest > 0:
        realized += rest * (b['c'][end] / ep - 1)
    return dict(pnl=realized - 2 * COST - fund, why=why, bars=end - e, entry=e)


def stat(rows):
    p = np.array([r['pnl'] for r in rows]) if rows else np.array([])
    if not len(p):
        return dict(n=0, win=0, avg=0, pf=0, bars=0, ma=0, stop=0)
    return dict(n=len(p), win=round(float((p > 0).mean() * 100), 1),
                avg=round(float(p.mean() * 100), 2),
                pf=round(float(p[p > 0].sum() / max(-p[p <= 0].sum(), 1e-9)), 2),
                bars=round(float(np.mean([r['bars'] for r in rows])), 1),
                ma=sum(1 for r in rows if r['why'] == 'ma'),
                stop=sum(1 for r in rows if r['why'].startswith('stop')))


def main():
    A, F, RG, cal = load()
    n = len(cal)
    i0 = next(k for k, d in enumerate(cal) if d >= '2026-01-26')
    for kind in ('TH1', 'TH2', 'TH3'):
        for full in (True, False):
            rows = []
            for i in range(230, n - 1):
                for s, b in A.items():
                    if s in L.ETF or s in L.LEV:
                        continue
                    if not b['real'][i] or i - b['first'] < 230 or b['jump'][i]:
                        continue
                    f = F[s]
                    c = float(b['c'][i])
                    if c < 5 or f['dv20'][i] < 30e6 or np.isnan(f['atrp'][i]) or f['atrp'][i] > 0.06:
                        continue
                    if not stack_ok(b, f, i, full):
                        continue
                    if kind == 'TH1':
                        if not (c > f['ma10'][i] and b['c'][i - 1] <= f['ma10'][i - 1]):
                            continue
                    elif kind == 'TH2':
                        if c < max(b['c'][i - 5:i]):
                            continue
                    elif kind == 'TH3':
                        if f['dev20'][i] > -0.01:
                            continue
                    r = sim_hold(b, f, i, float(f['atr'][i]))
                    if r:
                        rows.append(r)
            s = stat(rows)
            r26 = stat([r for r in rows if cal[r['entry']] >= '2026-01-26'])
            print('%-4s %-6s n=%3d 胜率 %5.1f%% 均值 %+5.2f%% PF %5.2f 均持 %4.1f根 ｜ 26 n=%2d 胜率 %5.1f%% PF %5.2f ｜ MA退出 %d 止损 %d'
                  % (kind, '全栈' if full else 'MA50', s['n'], s['win'], s['avg'], s['pf'], s['bars'],
                     r26['n'], r26['win'], r26['pf'], s['ma'], s['stop']))


if __name__ == '__main__':
    main()
