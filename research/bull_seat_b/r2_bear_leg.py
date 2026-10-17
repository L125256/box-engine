#!/usr/bin/env python3
# r2_bear_leg.py — 多头席R2：熊市腿立项论证（只读 box_module.py，本地复刻其状态机）
# 目标函数：主窗(入场>=2025-06-01) median 第一 / win 第二 / mean 第三 / PF 参照
import json, os, math, sys
import numpy as np
np.random.seed(42)

CACHE = '/tmp/box_cache'
OUTDIR = '/tmp/bull_seat_b'
MAIN_WIN = '2025-06-01'
N,K,M,B,X,E,Q,AMAX = 20,6.0,2,0.25,0.75,0.2,30,60  # 冻结参数

# ---------- 数据装载（缓存为 bars 数组；box_module 期望 bars_d 键，故自行装载，不改其代码）----------
def load_pool():
    pool = {}
    for f in sorted(os.listdir(CACHE)):
        d = json.load(open(os.path.join(CACHE, f)))
        bars = d if isinstance(d, list) else d.get('bars_d', d.get('bars'))
        cl = [b for b in bars if b['low']>0 and b['close']>0
              and b['low']<=b['high'] and b['low']<=b['close']<=b['high']]
        if len(cl) >= 100:
            pool[f.replace('.json','')] = cl
    return pool

def atrs(bars, n=14):  # 逐行复刻 box_module.atrs
    out=[None]*len(bars); trs=[]
    for i in range(1,len(bars)):
        trs.append(max(bars[i]['high']-bars[i]['low'],
                       abs(bars[i]['high']-bars[i-1]['close']),
                       abs(bars[i]['low']-bars[i-1]['close'])))
        if i>=n: out[i]=sum(trs[-n:])/n
    return out

def build_regime(pool):
    all_dates = sorted({b['time'] for bars in pool.values() for b in bars})
    idx = {}
    for dt in all_dates:
        vals = [b['close'] for bars in pool.values() for b in bars if b['time']==dt]
        if vals: idx[dt] = sum(vals)/len(vals)
    dts = sorted(idx); ma50 = {}
    for i,dt in enumerate(dts):
        w = dts[max(0,i-49):i+1]
        ma50[dt] = sum(idx[d] for d in w)/len(w)
    bull = {dt: idx[dt] > ma50[dt] for dt in dts}
    # 20日动量用于把 bull=False 细分 震荡/熊（自定义口径，仅用于分腿矩阵）
    mom20 = {}
    for i,dt in enumerate(dts):
        j = max(0, i-20)
        mom20[dt] = (idx[dt]/idx[dts[j]] - 1) if idx[dts[j]]>0 else 0.0
    regime = {dt: ('bull' if bull[dt] else ('bear' if mom20[dt] < 0 else 'range')) for dt in dts}
    return idx, ma50, bull, regime

# ---------- 通用引擎（严格复刻 box_module.scan 的多头逻辑；空头为镜像扩展）----------
# overlay 模式：空头引擎独立跟踪自己的箱体（多头信号不哑火空头箱体），与多头簿互不干扰；
# 冲突排除：多头簿持仓区间 [ei, xi] 内不开空（同票同日不可多空双向）。
def run_engine(bars, bull_map, short_cfg=None):
    """short_cfg: None=纯基线(多头)；dict(tg=触发倍率, gate(str|None), q=持仓上限, tp_atr=TP距L的ATR倍数)
    返回 (trades, pos_intervals, fd_gate_blocked, box_stats)"""
    a = atrs(bars)
    state='seek'; streak=0; box=None; pos=None; trades=[]
    s_state='seek'; s_streak=0; s_box=None; s_pos=None; s_trades=[]
    intervals=[]; fd_gate_blocked=0
    locked_days_bull = {'bull':0,'nonbull':0}
    n_lock = 0
    for i in range(max(N,14)+1, len(bars)):
        if a[i] is None: continue
        px = bars[i]['close']; dt = bars[i]['time']

        # --- 多头持仓管理（复刻） ---
        if pos:
            hold = i-pos['ei']; r = (px-pos['ep'])/pos['ep']*100 - 0.03*hold
            if px<=pos['eff'] or px>=pos['tp'] or hold>=pos['q']:
                trades.append(dict(ep=pos['ep'], ei=pos['ei'], xi=i, xc=px, kind=pos['kind'],
                                   r=round(r,2), et=bars[pos['ei']]['time'], xt=dt,
                                   why='tp' if px>=pos['tp'] else ('sl' if px<=pos['eff'] else 'time')))
                intervals.append((pos['ei'], i))
                pos=None
        # --- 空头持仓管理（镜像：px>=eff 平/px<=tp 平/期满；资金费同 0.03%/bar） ---
        if s_pos:
            hold = i-s_pos['ei']; r = (s_pos['ep']-px)/s_pos['ep']*100 - 0.03*hold
            if px>=s_pos['eff'] or px<=s_pos['tp'] or hold>=s_pos['q']:
                s_trades.append(dict(ep=s_pos['ep'], ei=s_pos['ei'], xi=i, xc=px, kind=s_pos['kind'],
                                     r=round(r,2), et=bars[s_pos['ei']]['time'], xt=dt,
                                     why='tp' if px<=s_pos['tp'] else ('sl' if px>=s_pos['eff'] else 'time')))
                s_pos=None

        # --- 多头状态机（复刻 box_module.scan） ---
        if state=='seek':
            w = bars[i-N+1:i+1]
            Hh=max(x['high'] for x in w); Ll=min(x['low'] for x in w); rng=Hh-Ll
            if rng>0 and rng<K*a[i]: streak+=1
            else: streak=0
            if streak>=M: state='locked'; box=[Ll,Hh,i,'',bull_map.get(dt,False)]; n_lock+=1; streak=0
            continue
        if box is not None and not pos:
            L,H,li,fired,lock_bull = box; rng=H-L; age=i-li
            if not fired:
                locked_days_bull['bull' if lock_bull else 'nonbull'] += 1
            sig=None
            if 'L' not in fired and px>H+B*a[i]: sig=('bk',px)
            elif 'L' not in fired and bars[i]['low']<=L+E*rng:
                if bull_map.get(dt,False): sig=('fd',px)
                else: fd_gate_blocked+=1  # fd 触发但牛闸拦截（复核 R1「恒真」缺陷）
            if sig is None and (px>H+X*a[i] or px<L-X*a[i] or age>AMAX): state='seek'; box=None
            elif sig:
                kind,ep=sig; box[3]+='L'
                tp = H+a[i] if kind=='bk' else H
                disp = ep-1.5*a[i] if kind=='bk' else L
                eff = disp-0.3*a[i]
                risk=(ep-disp)/ep*100
                if eff>0 and risk<=8.0: pos=dict(ep=ep,tp=tp,disp=disp,eff=eff,ei=i,kind=kind,q=Q)

        # --- 空头状态机（overlay 独立箱体；多头触发不哑火空头箱体） ---
        if short_cfg is not None:
            if s_state=='seek':
                w = bars[i-N+1:i+1]
                Hh=max(x['high'] for x in w); Ll=min(x['low'] for x in w); rng=Hh-Ll
                if rng>0 and rng<K*a[i]: s_streak+=1
                else: s_streak=0
                if s_streak>=M: s_state='locked'; s_box=[Ll,Hh,i,'']; s_streak=0
                # continue 不能用：多头部分已处理完，直接往下
            elif s_box is not None and not s_pos:
                L,H,li,fired=s_box; rng=H-L; age=i-li
                bks_on=short_cfg.get('bks',False); fds_on=short_cfg.get('fds',False)
                bks_gate=short_cfg.get('bks_gate'); fds_gate=short_cfg.get('fds_gate')
                qq=short_cfg.get('q',Q); tp_atr=short_cfg.get('tp_atr',1.0)
                bks_live = (bks_gate=='bear' and not bull_map.get(dt,False)) or (bks_gate is None)
                fds_live = (fds_gate=='bear' and not bull_map.get(dt,False)) or (fds_gate is None)
                sig=None
                if bks_on and bks_live and 'L' not in fired and px<L-short_cfg.get('bks_trig_tg',0.25)*a[i]: sig=('bks',px)
                elif fds_on and 'L' not in fired and fds_live and bars[i]['high']>=H-0.2*rng: sig=('fds',px)
                if sig is None and (px>H+X*a[i] or px<L-X*a[i] or age>AMAX): s_state='seek'; s_box=None
                elif sig:
                    kind,ep=sig; s_box[3]+='L'
                    if kind=='bks':
                        tp = L-tp_atr*a[i]; disp = ep+1.5*a[i]; eff = disp+0.3*a[i]
                        risk=(disp-ep)/ep*100
                    else:  # fds：TP=箱底 L，止损=箱顶上方
                        tp = L; disp = H; eff = H+0.3*a[i]
                        risk=(disp-ep)/ep*100
                    if eff>0 and risk<=8.0 and pos is None and not any(s<=i<=e for s,e in intervals):
                        s_pos=dict(ep=ep,tp=tp,disp=disp,eff=eff,ei=i,kind=kind,q=qq)
    return trades, s_trades, fd_gate_blocked, locked_days_bull, n_lock

def stats(trs):
    if not trs:
        return dict(n=0)
    rs=[t['r'] for t in trs]
    wins=[r for r in rs if r>0]; losses=[r for r in rs if r<=0]
    return dict(n=len(rs),
                median=round(float(np.median(rs)),3),
                win=round(100.0*len(wins)/len(rs),2),
                mean=round(float(np.mean(rs)),3),
                pf=round(sum(wins)/abs(sum(losses)),3) if losses else None,
                sum=round(float(np.sum(rs)),1))

def tail_diag(trs):
    if not trs: return {}
    rs_sorted=sorted((t['r'] for t in trs), reverse=True)
    tot=sum(t['r'] for t in trs)
    seq=[t['r'] for t in sorted(trs, key=lambda x:(x['et'],x['ei']))]  # 入场时间序
    cum=0; peak=0; mdd=0
    for r in seq:
        cum+=r; peak=max(peak,cum); mdd=max(mdd,peak-cum)
    return dict(top5_sum=round(sum(rs_sorted[:5]),1),
                top5_share=round(100*sum(rs_sorted[:5])/tot,1) if tot>0 else None,
                worst=round(rs_sorted[-1],2), best=round(rs_sorted[0],2),
                cum_maxdd=round(mdd,1))

def by_key(trs, keyfn):
    out={}
    for t in trs: out.setdefault(keyfn(t),[]).append(t)
    return {k: stats(v) for k,v in sorted(out.items())}

def main():
    pool = load_pool()
    idx, ma50, bull, regime = build_regime(pool)
    print(f'pool={len(pool)}  dates={len(idx)}  span={min(idx)}~{max(idx)}')

    # 市况占比
    from collections import Counter
    rc = Counter(regime[d] for d in idx)
    print('regime days:', dict(rc))

    # ---- 基线 ----
    base_trades, _, _, lock_bull_days, n_lock_total = run_engine_engine_all(pool, bull, None)
    base_main = [t for t in base_trades if t['et'] >= MAIN_WIN]
    print('BASE all :', stats(base_trades))
    print('BASE main:', stats(base_main))
    print('BASE main by year:', by_key(base_main, lambda t:t['et'][:4]))
    print('BASE main by regime:', by_key(base_main, lambda t:regime[t['et']]))
    print('BASE main by kind:', by_key(base_main, lambda t:t['kind']))
    print('locked box-days bull/nonbull:', lock_bull_days, 'locks total:', n_lock_total)

    json.dump(dict(base_all=stats(base_trades), base_main=stats(base_main)), open('/tmp/bull_seat_b/_base_check.json','w'))
    # 保存中间结果供后续脚本
    json.dump(base_trades, open('/tmp/bull_seat_b/_base_trades.json','w'))

def run_engine_engine_all(pool, bull, short_cfg):
    allt=[]; alls=[]; lb={'bull':0,'nonbull':0}; nlock=0
    for tkr,bars in pool.items():
        t,s,_,lbn,nl = run_engine(bars, bull, short_cfg)
        for x in t: x['tkr']=tkr
        for x in s: x['tkr']=tkr
        allt+=t; alls+=s
        lb['bull']+=lbn['bull']; lb['nonbull']+=lbn['nonbull']; nlock+=nl
    return allt, alls, None, lb, nlock

if __name__=='__main__':
    main()
