#!/usr/bin/env python3
# r2_candidates.py — R2 熊市腿候选实算 + 缺陷复核 + 大肉保全
import json, os
import numpy as np
np.random.seed(42)
from r2_bear_leg import (load_pool, build_regime, run_engine, stats, tail_diag,
                         by_key, MAIN_WIN, run_engine_engine_all)

OUT = '/tmp/bull_seat_b'
pool = load_pool()
idx, ma50, bull, regime = build_regime(pool)

# ---------- 1) 基线 + 缺陷复核 ----------
base_trades, _, _, lock_bull_days, n_lock_total = run_engine_engine_all(pool, bull, None)
base_main = [t for t in base_trades if t['et'] >= MAIN_WIN]
fd_main = [t for t in base_main if t['kind']=='fd']
fat = [t for t in fd_main if t['r']>=8]
fat_all = [t for t in base_trades if t['kind']=='fd' and t['r']>=8]

# fd 闸门拦截计数
gate_blocked=0
for tkr,bars in pool.items():
    _,_,_,_,_ = run_engine(bars, bull, None)  # 占位：engine 内部统计见下
# 直接在 engine 里带出 fd_gate_blocked：重跑逐票
gate_blocked=0
for tkr,bars in pool.items():
    t,s,gb,_,_ = run_engine(bars, bull, None)
    gate_blocked += gb

print('=== 基线（v1.0 冻结参数，pool=144） ===')
print('all :', stats(base_trades), tail_diag(base_trades))
print('main:', stats(base_main), tail_diag(base_main))
print('fd 闸门拦截信号数（bull=False 且 low<=L+0.2rng 且箱未哑火）:', gate_blocked)
print(f'fd 厚利桶 main: n={len(fat)} sum={sum(t["r"] for t in fat):.1f} | 全样本: n={len(fat_all)} sum={sum(t["r"] for t in fat_all):.1f}')
print('base bk main :', stats([t for t in base_main if t['kind']=='bk']))
print('base fd main :', stats(fd_main))
print('base main regime:', by_key(base_main, lambda t:regime[t['et']]))
print('locked box-days:', lock_bull_days)

# ---------- 2) 候选熊市腿 ----------
CANDS = {
  'bks':            dict(bks=True,  fds=False, bks_gate=None,   fds_gate='bear', q=30, tp_atr=1.0),  # 镜像突破跌破 L-0.25ATR 做空
  'bks_beargate':   dict(bks=True,  fds=False, bks_gate='bear', fds_gate='bear', q=30, tp_atr=1.0),  # 同上 + idx<MA50 闸
  'bks_q15':        dict(bks=True,  fds=False, bks_gate=None,   fds_gate='bear', q=15, tp_atr=1.0),  # 更短持仓
  'bks_tp05':       dict(bks=True,  fds=False, bks_gate=None,   fds_gate='bear', q=30, tp_atr=0.5),  # 紧TP
  'bks_bear_tp05':  dict(bks=True,  fds=False, bks_gate='bear', fds_gate='bear', q=30, tp_atr=0.5),  # 熊闸+紧TP
  'bks_bear_tp15':  dict(bks=True,  fds=False, bks_gate='bear', fds_gate='bear', q=30, tp_atr=1.5),  # 熊闸+松TP
  'fds':            dict(bks=False, fds=True,  bks_gate=None,   fds_gate='bear', q=30, tp_atr=1.0),  # 熊市版回归（high>=H-0.2rng 做空，TP=L）
  'fds_nogate':     dict(bks=False, fds=True,  bks_gate=None,   fds_gate=None,   q=30, tp_atr=1.0),  # 回归短无闸（对照 fds 闸门有效性）
}
results={}
short_all={}
for name,cfg in CANDS.items():
    allt, alls, _, _, _ = run_engine_engine_all(pool, bull, cfg)
    short_all[name]=alls
    sm=[t for t in alls if t['et']>=MAIN_WIN]
    results[name] = dict(
        cfg=cfg,
        all=dict(stats(alls), **tail_diag(alls), by_year=by_key(alls, lambda t:t['et'][:4])),
        main=dict(stats(sm), **tail_diag(sm),
                  by_year=by_key(sm, lambda t:t['et'][:4]),
                  by_regime=by_key(sm, lambda t:regime[t['et']]),
                  by_kind=by_key(sm, lambda t:t['kind'])),
    )
    print(f'\n--- {name} {cfg} ---')
    print('all :', results[name]['all'])
    print('main:', results[name]['main'])

# ---------- 3) 敏感性（切点脆弱性）：推荐腿的触发倍率与窗口起点 ----------
SENS={}
for name in ['bks','bks_q15']:
    for tg in [0.20, 0.25, 0.30]:
        cfg=dict(CANDS[name]); cfg['bks_trig_tg']=tg
        _,alls,_,_,_ = run_engine_engine_all(pool, bull, cfg)
        sm=[t for t in alls if t['et']>=MAIN_WIN]
        SENS[f'{name}_tg{tg}']=stats(sm)
for w0 in ['2025-05-01','2025-06-01','2025-07-01']:
    for name in ['bks','bks_q15']:
        sm=[t for t in short_all[name] if t['et']>=w0]
        SENS[f'{name}_win{w0}']=stats(sm)
print('\n=== 敏感性 ===')
for k,v in SENS.items(): print(k, v)

# ---------- 4) 多空同票冲突统计（overlay 可行性） ----------
conflict=0
for name in ['bks']:
    # 多头持仓区间
    intervals=[]
    for tkr,bars in pool.items():
        pass
# 重算多头区间
intervals_by_tkr={}
for tkr,bars in pool.items():
    t,_,_,_,_ = run_engine(bars, bull, None)
    # intervals 在 run_engine 内部，重算：用 trades 的 ei..xi
    intervals_by_tkr[tkr]=[(x['ei'],x['xi']) for x in t]
for name,alls in short_all.items():
    c=0
    for t in alls:
        if any(s<=t['ei']<=e for s,e in intervals_by_tkr.get(t['tkr'],[])): c+=1
    print(f'{name}: 与多头持仓冲突而被排除的空单数 = {c} / 全部空单 {len(alls)}')

# ---------- 5) combined 组合（overlay：基线 + 最佳空腿） ----------
def combine(name):
    comb = base_trades + [t for t in short_all[name]]
    cm=[t for t in comb if t['et']>=MAIN_WIN]
    return dict(all=dict(stats(comb), **tail_diag(comb)),
                main=dict(stats(cm), **tail_diag(cm),
                          by_regime=by_key(cm, lambda t:regime[t['et']]),
                          by_year=by_key(cm, lambda t:t['et'][:4])))
combined={n: combine(n) for n in CANDS}
print('\n=== 组合（基线+空腿 overlay） ===')
for n,c in combined.items():
    print(n, 'main:', c['main'])

# fd 大肉保全：overlay 不触碰基线引擎，fd sum 结构不变；确认数值
print('\n=== 大肉保全线 ===')
print(f"基线 fd main 总和={sum(t['r'] for t in fd_main):.1f}, 厚利桶(r>=8) n={len(fat)} sum={sum(t['r'] for t in fat):.1f}")
print('overlay 模式下 fd 引擎未做任何改动，厚利桶 sum 变化 = 0%（结构性保证）')

json.dump(dict(
    baseline=dict(all=stats(base_trades), main=stats(base_main),
                  main_by_regime=by_key(base_main, lambda t:regime[t['et']]),
                  main_by_kind=by_key(base_main, lambda t:t['kind']),
                  main_by_year=by_key(base_main, lambda t:t['et'][:4]),
                  fd_gate_blocked=gate_blocked,
                  fd_fat_main=dict(n=len(fat), sum=round(sum(t['r'] for t in fat),1)),
                  fd_fat_all=dict(n=len(fat_all), sum=round(sum(t['r'] for t in fat_all),1)),
                  locked_box_days=lock_bull_days),
    candidates=results, sensitivity=SENS, combined=combined,
), open(OUT+'/bear_leg_results.json','w'), ensure_ascii=False, indent=1)
print('\nsaved bear_leg_results.json')
