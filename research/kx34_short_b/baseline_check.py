#!/usr/bin/env python3
# baseline_check.py — 复现本地基线并与 R1 终裁数字对拍
import sys, json, collections
sys.path.insert(0, '/tmp/kx34_short_b')
from engine import load_pool, compute_idx, run_all, metrics, main_window

pool = load_pool()
bull = compute_idx(pool)
print(f"pool={len(pool)} tickers")

# fd×bull=False 定义性恒真验证：无闸版跑一遍，检查 fd 笔的 bull 标记
trades_nogate, _ = run_all(pool, bull, fd_gate=False)
fd_nogate = [t for t in trades_nogate if t['kind'] == 'fd']
# 给 fd 笔打 bull 标记（入场日）
import pandas as pd
rows = [(b['time'], b['close']) for bars in pool.values() for b in bars]
idx_s = pd.DataFrame(rows, columns=['t', 'c']).groupby('t')['c'].mean().sort_index()
ma50 = idx_s.rolling(50, min_periods=1).mean()
bullmap = {t: bool(idx_s[t] > ma50[t]) for t in idx_s.index}
fd_bear = [t for t in fd_nogate if not bullmap.get(t['xt'], False)]
print(f"[实证] fd×bull=False (无闸对照): n={len(fd_bear)} / fd总={len(fd_nogate)}  → {'恒真成立' if len(fd_bear)==0 else '恒真被证伪!'}")

# 基线参数
for v2 in (True, False):
    trades, amb = run_all(pool, bull, v2=v2)
    mw = main_window(trades)
    m = metrics(mw, 'r' if v2 else 'r_v1')
    mfull = metrics(trades, 'r' if v2 else 'r_v1')
    print(f"V{'2' if v2 else '1'} 主窗: {m}  全窗: {mfull}")
    if v2:
        fd8 = [t for t in trades if t['kind'] == 'fd' and t['r'] >= 8]
        fd8mw = [t for t in fd8 if t['xt'] >= '2025-06-01']
        print(f"  fd r>=8 厚利桶: 全窗 n={len(fd8)} sum={sum(t['r'] for t in fd8):.2f} | 主窗 n={len(fd8mw)} sum={sum(t['r'] for t in fd8mw):.2f}")
        yrs = collections.Counter(t['xt'][:4] for t in trades)
        print(f"  全窗分年入场笔数: {dict(sorted(yrs.items()))}")
        print(f"  ambiguous双触bar数: {amb}")
        kindy = collections.Counter((t['kind'], t['xt'][:4]) for t in trades)
        print(f"  分年×kind: {dict(sorted(kindy.items()))}")
