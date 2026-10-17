#!/usr/bin/env python3
# r2_variants.py — 决定性补充实验：fd 去牛闸（检验 R1 缺陷主张）+ bks 紧 TP 变体
import json
import numpy as np
np.random.seed(42)
from r2_bear_leg import load_pool, build_regime, run_engine, stats, tail_diag, by_key, MAIN_WIN

pool = load_pool()
idx, ma50, bull, regime = build_regime(pool)

# ---- 1) fd 去牛闸基线（多头 fd 不再要求 idx>MA50）----
import r2_bear_leg
orig_bull = bull
# 用一个恒真映射模拟去闸
alltrue = {d: True for d in bull}
def run_all(bullmap, cfg=None):
    allt=[]; alls=[]
    for tkr,bars in pool.items():
        t,s,_,_,_ = run_engine(bars, bullmap, cfg)
        for x in t: x['tkr']=tkr
        for x in s: x['tkr']=tkr
        allt+=t; alls+=s
    return allt, alls

base_t,_ = run_all(bull)
nogate_t,_ = run_all(alltrue)
for name,trs in [('base',base_t),('fd_nogate',nogate_t)]:
    m=[t for t in trs if t['et']>=MAIN_WIN]
    fdm=[t for t in m if t['kind']=='fd']
    print(name, 'main:', stats(m))
    print(name, 'fd main:', stats(fdm), 'fd sum:', round(sum(t['r'] for t in fdm),1))
    print(name, 'fd fat(r>=8):', stats([t for t in fdm if t['r']>=8]))

# ---- 2) bks 紧 TP 变体 ----
for name,cfg in [
    ('bks_tp05',        dict(bks=True, fds=False, bks_gate=None,   q=30, tp_atr=0.5)),
    ('bks_tp05_bear',   dict(bks=True, fds=False, bks_gate='bear', q=30, tp_atr=0.5)),
    ('bks_tp15',        dict(bks=True, fds=False, bks_gate=None,   q=30, tp_atr=1.5)),
    ('bks_bear_tp05',   dict(bks=True, fds=False, bks_gate='bear', q=30, tp_atr=0.5)),
    ('bks_bear_tp15',   dict(bks=True, fds=False, bks_gate='bear', q=30, tp_atr=1.5)),
]:
    allt, alls = run_all(bull, cfg)
    m=[t for t in alls if t['et']>=MAIN_WIN]
    print(name, 'all:', stats(allt), 'main:', stats(m), tail_diag(m))
    print('   main by regime:', by_key(m, lambda t:regime[t['et']]))
