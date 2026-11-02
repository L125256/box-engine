# -*- coding: utf-8 -*-
"""深踩快打（Fast Dip）· FD-1 双通道 v2（2026-11-03 替换）

通道 A 深踩（保留原版）：
  收盘 > MA100 且 MA100 20 日斜率 ≥ 0；20 日偏离 ≤ −5%；RSI2 ≤ 30；
  价格 ≥ 5、20 日均额 ≥ 30M、ATR% ≤ 6%。
通道 B 突破（新增）：
  收盘 > 过去 20 根收盘最高（不含当日）；当日量 ≥ 2.0 × 过去 20 日中位量；
  收盘 > MA100 且 MA100 20 日斜率 ≥ 0；价格 ≥ 5、20 日均额 ≥ 30M、ATR% ≤ 6%；
  同一标的 10 根内只取第一次。
出场（两通道共用）：
  +0.8 ATR 止盈、−1.5 ATR 止损、最多 5 根日线；跳空按开盘。
仓位：
  5x 逐仓、单笔保证金 3% 权益、最多 16 仓、毛敞口 2.5 倍。

组合实测（asof 2026-11-01，120 只个股，5x/3%/16/2.5x）：
  双通道 519 笔 / 胜率 70.7% / PF 1.49 / 年化 36.7% / 回撤 12.46%
  2026-01-26 起 147 笔 / 72.8% / PF 1.78 / 年化 34.7% / 回撤 5.35%
  原版深踩对照 271 笔 / 70.8% / PF 1.60 / 年化 22.3% / 回撤 8.52%（与双通道同信号集；旧研究口径 274/1.59/21.7）
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
# 通道 B 突破（2026-11-03 新增）
VOLX = 2.0
BRK_LOOKBACK = 20
BRK_DEDUP = 10


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


# ---------------------------------------------------------------- 通道 B：20 日新高 + 2 倍量能
def _breakout_qualified(A, F, s, i, volx=VOLX):
    b = A[s]; f = F[s]
    if not b['real'][i] or i - b['first'] < 210 or b['jump'][i]:
        return False
    c = b['c'][i]
    if c < MIN_PX or f['dv20'][i] < MIN_DV:
        return False
    if np.isnan(f['atrp'][i]) or f['atrp'][i] > ATR_MAX:
        return False
    if c <= f['ma100'][i] or f['slope100'][i] < 0:
        return False
    hi20 = float(np.max(b['c'][max(0, i - BRK_LOOKBACK):i]))
    vm = float(np.median(b['v'][max(0, i - BRK_LOOKBACK):i]))
    return vm > 0 and b['v'][i] >= volx * vm and c > hi20


def _breakout_row(A, F, s, i, volx=VOLX):
    if not _breakout_qualified(A, F, s, i, volx):
        return None
    b = A[s]; f = F[s]
    vm = float(np.median(b['v'][max(0, i - BRK_LOOKBACK):i]))
    hi20 = float(np.max(b['c'][max(0, i - BRK_LOOKBACK):i]))
    return dict(sym=s, close=float(b['c'][i]), atr=float(f['atr'][i]),
                volx=float(b['v'][i] / max(vm, 1e-9)), hi20=hi20,
                atrp=float(f['atrp'][i]))


def _breakout_eligible(A, F, i, volx=VOLX):
    out = []
    for s, b in A.items():
        if s in L.ETF or s in L.LEV:
            continue
        x = _breakout_row(A, F, s, i, volx)
        if x:
            out.append(x)
    out.sort(key=lambda x: -x['volx'])
    return out


def _breakout_recent(A, F, s, i, lookback=BRK_DEDUP - 1, volx=VOLX):
    return any(_breakout_qualified(A, F, s, j, volx)
               for j in range(max(0, i - lookback), i))


def breakout_signals(A, F, cal, volx=VOLX, start=220, end=None):
    """通道 B 回测信号；同标的 10 根内只取第一次。"""
    n = len(cal)
    end = n - 2 if end is None else end
    out = []
    last = {}
    for i in range(start, end + 1):
        for x in _breakout_eligible(A, F, i, volx):
            s = x['sym']
            if i - last.get(s, -99) < BRK_DEDUP:
                continue
            x = dict(x)
            x.update(i=i, score=x['volx'],
                     ex=dict(sl_atr=SL_ATR, tp_atr=TP_ATR, hold=HOLD))
            out.append(x)
            last[s] = i
    out.sort(key=lambda x: (x['i'], -x['score']))
    return out


def state_today(A, F, RG, cal, asof=None, topk=8):
    n = len(cal)
    i = next((k for k, d in enumerate(cal) if d >= asof), n - 1) if asof else n - 1
    deep = _eligible(A, F, i)
    brk = [x for x in _breakout_eligible(A, F, i)
           if not _breakout_recent(A, F, x['sym'], i)]
    return dict(asof=cal[i], deep=deep[:topk], brk=brk[:topk],
                n_deep=len(deep), n_brk=len(brk), n=len(deep) + len(brk))


def _old_state_today(A, F, RG, cal, asof=None, topk=8):
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


def _entry_i(b, i, cal):
    import datetime
    for k in range(i + 1, min(len(b['c']), i + 4)):
        if b['real'][k] and not b['jump'][k] and datetime.date.fromisoformat(cal[k]).weekday() < 5:
            return k
    return -1


def recent_combined(A, F, RG, cal, k=8, per_channel=False):
    """最近成交：深踩 + 突破，按信号日倒序；per_channel=True 时两通道各取一半。"""
    deep, brk = [], []
    for i in range(220, len(cal) - 1):
        for x in _eligible(A, F, i):
            deep.append((i, '深踩', x))
    for x in breakout_signals(A, F, cal):
        brk.append((x['i'], '突破', x))
    deep.sort(key=lambda z: -z[0])
    brk.sort(key=lambda z: -z[0])
    if per_channel:
        ev = deep[:max(1, k // 2)] + brk[:max(1, k - k // 2)]
    else:
        ev = deep + brk
    ev.sort(key=lambda z: -z[0])
    out = []
    for i, ch, x in ev:
        b = A[x['sym']]
        e = _entry_i(b, i, cal)
        if e <= 0:
            continue
        r = simulate_one(b, e, x['atr'])
        if r:
            out.append(dict(date=cal[i], channel=ch, sym=x['sym'],
                            entry=float(b['o'][e]), atr=x['atr'],
                            levels=levels(float(b['o'][e]), x['atr']), **r))
        if len(out) >= k:
            break
    return out


cal_ref = None


def main():
    global cal_ref
    A, F, RG, cal = load()
    cal_ref = cal
    st = state_today(A, F, RG, cal)
    print('asof %s ｜ 深踩 %d 只 ｜ 突破 %d 只' % (st['asof'], st['n_deep'], st['n_brk']))
    print('深踩候选：')
    for x in st['deep']:
        lv = levels(x['close'], x['atr'])
        print('  %-9s 收盘 %.2f  ATR %.2f  RSI2 %4.1f  20日偏离 %+5.1f%%  → 止损 %.2f 止盈 %.2f' % (
            x['sym'], x['close'], x['atr'], x['rsi2'], x['dev20'] * 100, lv['stop'], lv['tp']))
    print('突破候选：')
    for x in st['brk']:
        lv = levels(x['close'], x['atr'])
        print('  %-9s 收盘 %.2f  ATR %.2f  量比 %.2fx  20日高 %.2f  → 止损 %.2f 止盈 %.2f' % (
            x['sym'], x['close'], x['atr'], x['volx'], x['hi20'], lv['stop'], lv['tp']))
    print('\n最近成交（信号日 / 通道 / 标的 / 入场 / 止损 / 止盈 / 结果）：')
    for t in recent_combined(A, F, RG, cal, 8):
        print('  %s %-4s %-9s E %.2f  止损 %.2f  止盈 %.2f  %+6.2f%%  %s  %d根' % (
            t['date'], t['channel'], t['sym'], t['entry'], t['levels']['stop'], t['levels']['tp'],
            t['pnl'] * 100, t['why'], t['bars']))


if __name__ == '__main__':
    main()
