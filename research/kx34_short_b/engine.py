#!/usr/bin/env python3
# engine.py — 箱体引擎参数化复刻（只读复刻 box_module.py v1.0）+ V2 可实现出场口径
# 口径说明：
#   V1 = 引擎原口径：出场价=触发当根 bar 收盘 px
#   V2 = 可实现口径：止盈 fill=min(tp, 当根high)（开盘≥tp 按开盘价，缺口利多）
#                    止损 fill=eff（当根开盘>eff 则盘中穿越，按 eff 成交）；
#                    开盘≤eff 直接按开盘价（向下缺口）；期满按收盘。
#                    同根 bar 同时触及 eff 与 tp：保守按止损成交（occurrences 单独计数）。
import json, os

CACHE = '/tmp/box_cache'

def load_pool(cache_dir=CACHE):
    pool = {}
    for f in sorted(os.listdir(cache_dir)):
        d = json.load(open(os.path.join(cache_dir, f)))
        bars = d if isinstance(d, list) else d.get('bars_d', d.get('bars'))
        cl = [b for b in bars if b['low'] > 0 and b['close'] > 0
              and b['low'] <= b['high'] and b['low'] <= b['close'] <= b['high']]
        if len(cl) >= 100:
            pool[f.replace('.json', '')] = cl
    return pool

def compute_idx(pool):
    """池等权收盘均价 + MA50 + bull 闸（复刻 box_module.main 的 idx/ma50/bull）"""
    import pandas as pd
    rows = [(b['time'], b['close']) for bars in pool.values() for b in bars]
    s = pd.DataFrame(rows, columns=['t', 'c']).groupby('t')['c'].mean().sort_index()
    ma50 = s.rolling(50, min_periods=1).mean()
    bull = {t: bool(s[t] > ma50[t]) for t in s.index}
    return bull

def atrs(bars, n=14):
    out = [None] * len(bars); trs = []
    for i in range(1, len(bars)):
        trs.append(max(bars[i]['high'] - bars[i]['low'],
                       abs(bars[i]['high'] - bars[i - 1]['close']),
                       abs(bars[i]['low'] - bars[i - 1]['close'])))
        if i >= n:
            out[i] = sum(trs[-n:]) / n
    return out

def scan(bars, bull, N=20, K=6.0, M=2, B=0.25, X=0.75, E=0.2, Q=30, AMAX=60,
         fd_gate=True, h8=None, m3_t=None, v2=True):
    """单票状态机复刻；h8=fd 触发日 low≥L*(1-h8%)；m3_t=fd 需 ep≥L+m3_t*箱幅；均 None=关闭"""
    a = atrs(bars)
    state = 'seek'; streak = 0; box = None; pos = None; trades = []; amb = 0
    for i in range(max(N, 14) + 1, len(bars)):
        if a[i] is None:
            continue
        px = bars[i]['close']
        if pos:
            hold = i - pos['ei']; r = (px - pos['ep']) / pos['ep'] * 100 - 0.03 * hold
            if px <= pos['eff'] or px >= pos['tp'] or hold >= Q:
                fill = px
                if v2:
                    o, hi, lo = bars[i]['open'], bars[i]['high'], bars[i]['low']
                    stop_hit, tp_hit = lo <= pos['eff'], hi >= pos['tp']
                    if stop_hit and tp_hit:
                        fill = pos['eff']; amb += 1  # 同根bar双触：保守按止损
                    elif o <= pos['eff']:
                        fill = o                      # 向下缺口
                    elif px >= pos['tp']:
                        fill = o if o >= pos['tp'] else pos['tp']  # 止盈：向上缺口按开盘价，否则按 tp
                    elif px <= pos['eff']:
                        fill = pos['eff']             # 盘中穿越止损
                    # 期满：fill=px（收盘）
                rr = (fill - pos['ep']) / pos['ep'] * 100 - 0.03 * hold
                trades.append(dict(ep=pos['ep'], xi=i,
                                   xt=bars[i]['time'], kind=pos['kind'],
                                   fill=round(fill, 6), xc=px,
                                   r=round(rr, 4), r_v1=round(r, 4),
                                   hold=hold,
                                   why='止盈' if px >= pos['tp'] else ('止损' if px <= pos['eff'] else '30天期满')))
                pos = None
            continue
        if state == 'seek':
            w = bars[i - N + 1:i + 1]
            Hh = max(x['high'] for x in w); Ll = min(x['low'] for x in w); rng = Hh - Ll
            if rng > 0 and rng < K * a[i]: streak += 1
            else: streak = 0
            if streak >= M: state = 'locked'; box = [Ll, Hh, i, '']; streak = 0
            continue
        L, H, li, fired = box; rng = H - L
        sig = None
        if 'L' not in fired and px > H + B * a[i]:
            sig = ('bk', px)
        elif ('L' not in fired and (bull.get(bars[i]['time']) if fd_gate else bars[i]['time'] in bull)
              and bars[i]['low'] <= L + E * rng):
            ok = True
            if h8 is not None and bars[i]['low'] < L * (1 - h8 / 100.0): ok = False
            if ok and m3_t is not None and px < L + m3_t * rng: ok = False
            if ok: sig = ('fd', px)
        if sig is None and (px > H + X * a[i] or px < L - X * a[i] or i - li > AMAX):
            state = 'seek'; box = None; continue
        if sig:
            kind, ep = sig; box[3] += 'L'
            tp = H + a[i] if kind == 'bk' else H
            disp = ep - 1.5 * a[i] if kind == 'bk' else L
            eff = disp - 0.3 * a[i]
            risk = (ep - disp) / ep * 100
            if eff > 0 and risk <= 8.0:
                pos = dict(ep=ep, tp=tp, disp=disp, eff=eff, ei=i, kind=kind)
    return dict(trades=trades, ambiguous=amb)

def run_all(pool, bull, **kw):
    """全池扫描，返回 (trades, ambiguous_count)"""
    all_t, amb = [], 0
    for tkr, bars in pool.items():
        res = scan(bars, bull, **kw)
        for t in res['trades']:
            t['tkr'] = tkr
        all_t += res['trades']; amb += res['ambiguous']
    return all_t, amb

def metrics(trades, key='r'):
    import statistics as st
    rs = [t[key] for t in trades]
    if not rs:
        return dict(n=0, median=None, win=None, mean=None)
    return dict(n=len(rs), median=round(st.median(rs), 4),
                win=round(sum(1 for x in rs if x > 0) / len(rs) * 100, 2),
                mean=round(sum(rs) / len(rs), 4))

def main_window(trades, t0='2025-06-01'):
    return [t for t in trades if t['xt'] >= t0]
