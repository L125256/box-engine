# -*- coding: utf-8 -*-
"""批量点火 · 独立策略（第一批）：信号、价位、历史结果。

与 v2.1 / HF-1 完全独立：不改它们的代码、不共用资金池。

规则（2026-10-28 冻结）：
  点火：当日涨幅 ≥4% 且 成交量 ≥2×20 日中位，且个股站上 MA50，价格≥5、dv20≥30M、ATR%≤6%
        个股口径：不含 ETF、杠杆 ETF（2026-10-28 修订）
  批次：全市场同一天符合条件的 ≥3 只才开火（不足 3 只 → 当日不做）
  选择：按当日涨幅取前 5，次日开盘各开一个仓位
  仓位：5x 逐仓、单笔保证金 = 权益 3%（名义 15%）、最多 8 仓、毛敞口 2.4 倍
  退出：止损 = 入场 −2.5 ATR；到 +2.5 ATR 平一半；剩下一半到 +8 ATR 全平；
        否则持有 20 根日线按收盘平仓
  不设关火（2026-10-28 个股口径实测：5 日停新仓年化 40.8%、回撤 11.48%，
        不关火 52.2%、12.76%；被挡掉的 35 仓 PF 1.65、逐笔 +15.9pp，不是坏单）
"""
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))
import sys
sys.path.insert(0, os.path.join(WORK, 'v2'))
import v2_lib as L

RET1_MIN = 0.04
VOL_X = 2.0
MIN_BATCH = 3
TOP_K = 5
SL_ATR = 2.5
TP1_ATR = 2.5
CAP_ATR = 8.0
HOLD = 20
LEV = 5
MARGIN_PCT = 0.03
COST = 0.001
FUND = 0.0003


def load(cache='cache_fresh'):
    L.CACHE = os.path.join(WORK, cache) if not os.path.isabs(cache) else cache
    raw, cal, gi = L.load_all(include_lev=True, include_etf=True)
    A = L.align(raw, cal, gi)
    F = L.features(A)
    core = {s: b for s, b in A.items() if s not in L.ETF and s not in L.LEV}
    RG = L.build_regime(core, cal)
    return A, F, RG, cal


def _eligible(A, F, i, n):
    out = []
    for s, b in A.items():
        if s in L.ETF or s in L.LEV:
            continue
        f = F[s]
        if not b['real'][i] or i - b['first'] < 210:
            continue
        if b['jump'][i]:
            continue
        if b['c'][i] < 5 or f['dv20'][i] < 30e6:
            continue
        if np.isnan(f['atrp'][i]) or f['atrp'][i] > 0.06:
            continue
        if f['ret1'][i] < RET1_MIN:
            continue
        vm = float(np.median(b['v'][max(0, i - 20):i]))
        if vm <= 0 or b['v'][i] < VOL_X * vm:
            continue
        out.append(dict(sym=s, ret1=float(f['ret1'][i]), close=float(b['c'][i]),
                        atr=float(f['atr'][i]), ma50=float(f['ma50'][i]),
                        above50=bool(b['c'][i] > f['ma50'][i]), volx=float(b['v'][i] / vm)))
    out.sort(key=lambda x: -x['ret1'])
    return out


def state_today(A, F, RG, cal, lookback=6, asof=None):
    n = len(cal)
    i = next((k for k, d in enumerate(cal) if d >= asof), n - 1) if asof else n - 1
    ign = _eligible(A, F, i, n)
    above = [x for x in ign if x['above50']]
    return dict(asof=cal[i], n_ign=len(ign), n_above=len(above),
                candidates=above[:TOP_K])


def levels(ref, atr):
    return dict(stop=ref - SL_ATR * atr, tp1=ref + TP1_ATR * atr, cap=ref + CAP_ATR * atr)


def simulate_one(b, i, entry_i, atr, hold=HOLD):
    """按 2.5ATR 平半 + 剩余 8ATR 封顶 + 止损 2.5ATR + 20 根时间退出，返回加权净收益（名义口径）。"""
    n = len(b['c'])
    ep = b['o'][entry_i]
    if ep <= 0:
        return None
    stop = ep - SL_ATR * atr
    tp1 = ep + TP1_ATR * atr
    cap = ep + CAP_ATR * atr
    rest = 1.0
    realized = 0.0
    half_done = False
    fund = 0.0
    why = 'time'
    end = min(n - 1, entry_i + hold)
    for k in range(entry_i, end + 1):
        if b['jump'][k]:
            continue
        lo, hi = b['l'][k], b['h'][k]
        fund += FUND * rest
        if k > entry_i and b['o'][k] <= stop:
            realized += rest * (b['o'][k] / ep - 1)
            rest = 0; why = 'stop_gap'; break
        if lo <= stop:
            realized += rest * (stop / ep - 1)
            rest = 0; why = 'stop'; break
        if not half_done and hi >= tp1:
            realized += 0.5 * (tp1 / ep - 1)
            rest -= 0.5
            half_done = True
            why = 'tp1+'
        if hi >= cap:
            realized += rest * (cap / ep - 1)
            rest = 0; why = 'cap'; break
    if rest > 0:
        realized += rest * (b['c'][end] / ep - 1)
    gross = realized
    cost = 2 * COST
    return dict(pnl=gross - cost - fund, why=why, bars=end - entry_i)


def recent_signals(A, F, RG, cal, k=5):
    n = len(cal)
    out = []
    i = n - 2
    while i > 210 and len(out) < k:
        ign = _eligible(A, F, i, n)
        above = [x for x in ign if x['above50']]
        if len(above) >= MIN_BATCH:
            picks = above[:TOP_K]
            ei = None
            for x in picks:
                b = A[x['sym']]
                e = next((q for q in range(i + 1, min(n, i + 4))
                          if b['real'][q] and not b['jump'][q]), -1)
                if e > 0:
                    r = simulate_one(b, i, e, x['atr'])
                    if r:
                        out.append(dict(date=cal[i], sym=x['sym'], ret1=x['ret1'],
                                        entry=float(b['o'][e]), atr=x['atr'],
                                        levels=levels(float(b['o'][e]), x['atr']),
                                        pnl=r['pnl'], why=r['why'], bars=r['bars']))
            i -= 10
        else:
            i -= 1
    return out
