# -*- coding: utf-8 -*-
"""深踩快打（Fast Dip）· 独立策略 v1（2026-10-29 冻结）

与 v2.1 / HF-1 / 点火完全独立：不共用入场、不共用闸门、不共用页。

规则：
  入场（日线收盘出信号，次日开盘成交）
    个股：收盘 > MA100 且 MA100 20 日斜率 ≥ 0（只做上升趋势里的回踩）
    深踩：20 日偏离 ≤ −5%，且 RSI2 ≤ 30
    过滤：价格 ≥ 5、20 日均额 ≥ 30M、ATR% ≤ 6%
    无市场闸门（个股趋势过滤替代；2026-10-29 实测优于 MA50+广度 45% 闸门）
  出场
    止盈 +0.8 ATR（跳空高开按开盘价成交）
    止损 −1.5 ATR（跳空低开按开盘价成交）
    最多持有 5 根日线，到期按收盘
  仓位
    5x 逐仓、单笔保证金 3% 权益（名义 15%）、最多 16 仓、毛敞口 2.5 倍
    止损占权益约 0.95%，止损占单仓保证金约 31.7%

实测（2026-10-31 同仓库引擎复算，数据截至 2026-10-30，个股 120 只）：
  274 笔 / 约 15.3 笔每月 / 胜率 70.8% / PF 1.61 / 年化 21.9% / 最大回撤 8.52%
  真实合约段（2026-01-26 起）65 笔 / 69.2% / PF 1.65 / 年化 12.8% / 回撤 4.05%
"""
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
import v2_lib as L

DEV20_MAX = -0.05
RSI2_MAX = 30.0
SL_ATR = 1.5
TP_ATR = 0.8
HOLD = 5
LEV = 5
MARGIN_PCT = 0.03
MAX_POS = 16
GROSS_CAP = 2.5
COST = 0.001
FUND = 0.0003
ATR_MAX = 0.06
MIN_PX = 5.0
MIN_DV = 30e6


def load(cache=None):
    cache = cache or os.environ.get('V2_CACHE') or 'cache_fresh'
    L.CACHE = os.path.join(WORK, cache) if not os.path.isabs(cache) else cache
    raw, cal, gi = L.load_all(include_lev=True, include_etf=True)
    A = L.align(raw, cal, gi)
    F = L.features(A)
    core = {s: b for s, b in A.items() if s not in L.ETF and s not in L.LEV}
    RG = L.build_regime(core, cal)
    return A, F, RG, cal


def _eligible(A, F, i):
    out = []
    for s, b in A.items():
        if s in L.ETF or s in L.LEV:
            continue
        f = F[s]
        if not b['real'][i] or i - b['first'] < 210 or b['jump'][i]:
            continue
        c = b['c'][i]
        if c < MIN_PX or f['dv20'][i] < MIN_DV:
            continue
        if np.isnan(f['atrp'][i]) or f['atrp'][i] > ATR_MAX:
            continue
        if c <= f['ma100'][i] or f['slope100'][i] < 0:
            continue
        if f['dev20'][i] > DEV20_MAX or f['rsi2'][i] > RSI2_MAX:
            continue
        out.append(dict(sym=s, close=float(c), atr=float(f['atr'][i]),
                        dev20=float(f['dev20'][i]), rsi2=float(f['rsi2'][i]),
                        atrp=float(f['atrp'][i])))
    out.sort(key=lambda x: x['rsi2'])
    return out


def state_today(A, F, RG, cal, asof=None, topk=8):
    n = len(cal)
    i = next((k for k, d in enumerate(cal) if d >= asof), n - 1) if asof else n - 1
    cand = _eligible(A, F, i)
    return dict(asof=cal[i], n=len(cand), candidates=cand[:topk])


def levels(ref, atr):
    return dict(stop=ref - SL_ATR * atr, tp=ref + TP_ATR * atr)


def simulate_one(b, entry_i, atr, hold=HOLD):
    n = len(b['c'])
    ep = b['o'][entry_i]
    if ep <= 0:
        return None
    stop, tgt = ep - SL_ATR * atr, ep + TP_ATR * atr
    fund = 0.0
    why = 'time'
    end = min(n - 1, entry_i + hold)
    for k in range(entry_i, end + 1):
        if b['jump'][k]:
            continue
        fund += FUND
        if k > entry_i and b['o'][k] <= stop:
            return dict(pnl=b['o'][k] / ep - 1 - 2 * COST - fund, why='stop_gap', bars=k - entry_i)
        if b['l'][k] <= stop:
            return dict(pnl=stop / ep - 1 - 2 * COST - fund, why='stop', bars=k - entry_i)
        if b['h'][k] >= tgt:
            return dict(pnl=tgt / ep - 1 - 2 * COST - fund, why='tp', bars=k - entry_i)
    return dict(pnl=b['c'][end] / ep - 1 - 2 * COST - fund, why=why, bars=end - entry_i)


def recent_signals(A, F, RG, cal, k=5):
    out = []
    n = len(cal)
    for i in range(n - 2, 210, -1):
        for x in _eligible(A, F, i):
            b = A[x['sym']]
            e = next((q for q in range(i + 1, min(n, i + 4)) if b['real'][q] and not b['jump'][q]), -1)
            if e <= 0:
                continue
            r = simulate_one(b, e, x['atr'])
            if r:
                out.append(dict(date=cal[i], sym=x['sym'], entry=float(b['o'][e]), atr=x['atr'],
                                levels=levels(float(b['o'][e]), x['atr']), **r))
            if len(out) >= k:
                return out
    return out


cal_ref = None


def main():
    global cal_ref
    A, F, RG, cal = load()
    cal_ref = cal
    st = state_today(A, F, RG, cal)
    print('asof %s ｜ 今日候选 %d 只' % (st['asof'], st['n']))
    for x in st['candidates']:
        lv = levels(x['close'], x['atr'])
        print('  %-9s 收盘 %.2f  ATR %.2f  RSI2 %4.1f  20日偏离 %+5.1f%%  → 止损 %.2f 止盈 %.2f' % (
            x['sym'], x['close'], x['atr'], x['rsi2'], x['dev20'] * 100, lv['stop'], lv['tp']))
    print('\n最近成交（信号日 / 标的 / 入场 / 止损 / 止盈 / 结果）：')
    for t in recent_signals(A, F, RG, cal, 6):
        print('  %s %-9s E %.2f  止损 %.2f  止盈 %.2f  %+6.2f%%  %s  %d根' % (
            t['date'], t['sym'], t['entry'], t['levels']['stop'], t['levels']['tp'],
            t['pnl'] * 100, t['why'], t['bars']))


if __name__ == '__main__':
    main()
