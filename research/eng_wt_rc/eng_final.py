#!/usr/bin/env python3
# eng_final.py — WT-A 权威基线引擎（仲裁版 v1.0，2026-10-17）
# 状态机/清洗/ATR/idx/scan 与 box_module.py v1.0 逐字一致（信号序列零改动红线）。
# 唯一口径改动 = 工单 V2 可实现出场记账（触发仍为 V1 收盘判定）：
#   触发（收盘判定，V1 逐字）：px<=eff 或 px>=tp 或 hold>=Q
#   成交价：
#     止盈 = max(tp, 当根open)   止损 = min(eff, 当根open)   硬顶 = 当根close
#     成交价须落在当根 [low,high]，否则顺延至下一根 open（守卫计数 defer_count）
#   资金费 0.03%/bar × (实际出场bar - 入场bar)
# 主窗 = 入场日(et) >= 2025-06-01；池 = 清洗后 bars>=100 的 144 标的；idx 仅用池内标的。
# 内置回归锚：--anchor 时以 V1 收盘口径复跑，断言三套参数成交键集合与 V2 完全一致。
import json, os, argparse, statistics, datetime

N,K,M,B,X,E,Q,AMAX = 20,6.0,2,0.25,0.75,0.2,30,60
FEE = 0.03  # %/bar

def atrs(bars, n=14):
    out=[None]*len(bars); trs=[]
    for i in range(1,len(bars)):
        trs.append(max(bars[i]['high']-bars[i]['low'],abs(bars[i]['high']-bars[i-1]['close']),abs(bars[i]['low']-bars[i-1]['close'])))
        if i>=n: out[i]=sum(trs[-n:])/n
    return out

def scan(bars, idx_above_ma, v1=False):
    """单票状态机。v1=False: V2 可实现出场价；v1=True: box_module 原版收盘记账（回归锚）。"""
    a=atrs(bars)
    state='seek';streak=0;box=None;pos=None;trades=[]
    stat=dict(defer=0,gap_stop=0,gap_tp=0,hardcap=0)
    for i in range(max(N,14)+1,len(bars)):
        if a[i] is None: continue
        px=bars[i]['close']
        if pos:
            hold=i-pos['ei']
            if px<=pos['eff'] or px>=pos['tp'] or hold>=Q:   # V1 收盘判定触发（逐字）
                if v1:
                    r=(px-pos['ep'])/pos['ep']*100-FEE*hold
                    trades.append(dict(ep=pos['ep'],ei=pos['ei'],xi=i,xc=px,kind=pos['kind'],r=r,
                                       why='止盈' if px>=pos['tp'] else ('止损' if px<=pos['eff'] else '30天期满')))
                    stat['hardcap']+= 1 if (pos['eff']<px<pos['tp']) else 0
                    pos=None
                    continue
                if px>=pos['tp']:
                    xpx=max(pos['tp'],bars[i]['open'])
                    if bars[i]['open']>=pos['tp']: stat['gap_tp']+=1
                elif px<=pos['eff']:
                    xpx=min(pos['eff'],bars[i]['open'])
                    if bars[i]['open']<=pos['eff']: stat['gap_stop']+=1
                else:
                    xpx=px; stat['hardcap']+=1               # 30bar 硬顶按当根收盘
                j=i
                while j<len(bars)-1 and not (bars[j]['low']<=xpx<=bars[j]['high']):
                    j+=1; xpx=bars[j]['open']; stat['defer']+=1
                r=(xpx-pos['ep'])/pos['ep']*100-FEE*(j-pos['ei'])
                trades.append(dict(ep=pos['ep'],ei=pos['ei'],xi=j,xc=round(xpx,4),kind=pos['kind'],r=r,
                                   why='止盈' if px>=pos['tp'] else ('止损' if px<=pos['eff'] else '30天期满')))
                pos=None
            continue
        if state=='seek':
            w=bars[i-N+1:i+1]
            Hh=max(x['high'] for x in w);Ll=min(x['low'] for x in w);rng=Hh-Ll
            if rng>0 and rng<K*a[i]: streak+=1
            else: streak=0
            if streak>=M: state='locked';box=[Ll,Hh,i,''];streak=0
            continue
        L,H,li,fired=box; rng=H-L; age=i-li
        sig=None
        if 'L' not in fired and px>H+B*a[i]: sig=('bk',px)
        elif ('L' not in fired and idx_above_ma.get(bars[i]['time']) and bars[i]['low']<=L+E*rng): sig=('fd',px)
        if sig is None and (px>H+X*a[i] or px<L-X*a[i] or age>AMAX): state='seek';box=None;continue
        if sig:
            kind,ep=sig; box[3]+='L'
            tp = H+a[i] if kind=='bk' else H
            disp = ep-1.5*a[i] if kind=='bk' else L
            eff = disp-0.3*a[i]
            risk=(ep-disp)/ep*100
            if eff>0 and risk<=8.0: pos=dict(ep=ep,tp=tp,disp=disp,eff=eff,ei=i,kind=kind)
    return dict(trades=trades, stat=stat)

def load_pool(cache):
    """清洗与 box_module.main() 逐字一致。加载层适配：缓存为裸 list 或 {'bars_d': [...]}。"""
    kept={}; dropped=[]
    for f in sorted(os.listdir(cache)):
        d=json.load(open(os.path.join(cache,f)))
        if isinstance(d,dict): d=d.get('bars_d',d)
        cl=[b for b in d if b['low']>0 and b['close']>0 and b['low']<=b['high'] and b['low']<=b['close']<=b['high']]
        t=f.replace('.json','')
        if len(cl)>=100: kept[t]=cl
        else: dropped.append(dict(tkr=t,bars_raw=len(d),bars_clean=len(cl)))
    return kept,dropped

def build_idx_bull(pool):
    """idx=池等权收盘均价（仅池内标的），MA50 牛闸，与 box_module.main() 逐字一致"""
    all_dates=sorted({b['time'] for bars in pool.values() for b in bars})
    idx={}
    for dt in all_dates:
        vals=[b['close'] for bars in pool.values() for b in bars if b['time']==dt]
        if vals: idx[dt]=sum(vals)/len(vals)
    dts=sorted(idx); ma50={}
    for i,dt in enumerate(dts):
        w=dts[max(0,i-49):i+1]; ma50[dt]=sum(idx[d] for d in w)/len(w)
    return {dt: idx[dt]>ma50[dt] for dt in dts}

def collect(params, pool, bull, v1=False):
    global N,K,M,E
    N,K,M,E = params['N'],params['k'],params['m'],params['e']
    trades=[]; agg=dict(defer=0,gap_stop=0,gap_tp=0,hardcap=0)
    for tkr,bars in pool.items():
        res=scan(bars, bull, v1=v1)
        for t in res['trades']:
            trades.append(dict(tkr=tkr, **t, et=bars[t['ei']]['time'], xt=bars[t['xi']]['time']))
        for k in agg: agg[k]+=res['stat'][k]
    return sorted(trades,key=lambda t:(t['xi'],t['tkr'])), agg

def stats(trades):
    rs=[t['r'] for t in trades]; n=len(rs)
    if n==0: return dict(n=0,median=None,win_rate=None,mean=None,pf=None,sum_r=0.0,thick=dict(n=0,sum_r=0.0))
    wins=[r for r in rs if r>0]; losses=[r for r in rs if r<=0]
    pf=(sum(wins)/abs(sum(losses))) if losses and sum(losses)!=0 else None
    thick=[r for r in rs if r>=8]
    return dict(n=n,
                median=round(statistics.median(rs),4),
                win_rate=round(len(wins)/n,4),
                win_pct=round(len(wins)/n*100,2),
                mean=round(sum(rs)/n,4),
                pf=round(pf,4) if pf is not None else 'inf',
                sum_r=round(sum(rs),2),
                thick=dict(n=len(thick),sum_r=round(sum(thick),2)))

def yearly(trades):
    """分年按入场日（et）归年，与主窗切法一致"""
    out={}
    for y in ('2024','2025','2026'):
        rs=[t['r'] for t in trades if t['et'][:4]==y]; n=len(rs)
        out[y]=dict(n=n,
                    median=round(statistics.median(rs),4) if n else None,
                    win_pct=round(len([r for r in rs if r>0])/n*100,2) if n else None,
                    mean=round(sum(rs)/n,4) if n else None,
                    sum_r=round(sum(rs),2))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cache', default='/tmp/box_cache')
    ap.add_argument('--out', default='/tmp/eng_wt_rc/authoritative_baseline.json')
    ap.add_argument('--anchor', action='store_true', help='内置 V1 回归锚自检')
    a=ap.parse_args()

    runs={
      'baseline': dict(label='基线 N=20/k6.0/m2/e0.2',        params=dict(N=20,k=6.0,m=2,e=0.2)),
      'top1':     dict(label='Top1 N=15/k7.5/m2/e0.3',        params=dict(N=15,k=7.5,m=2,e=0.3)),
      'planb':    dict(label='方案B N=20/k6.0/m1/e0.3',       params=dict(N=20,k=6.0,m=1,e=0.3)),
    }
    pool,dropped=load_pool(a.cache)
    bull=build_idx_bull(pool)
    MAIN='2025-06-01'

    out=dict(generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
             version='eng-final(WT-A 仲裁权威基线 v1.0)',
             caliber=dict(trigger='V1 收盘判定: close<=eff / close>=tp / hold>=30（信号序列零改动）',
                          fill='V2 可实现价: 止损=min(eff,open) 止盈=max(tp,open) 30bar=close; 须在当根[low,high]否则顺延下一根 open',
                          funding='0.03%/bar ×(出场bar-入场bar)', pool='清洗 low>0/close>0/OHLC 自洽 且 bars>=100 → 144 标的',
                          idx='池内标的等权收盘均价 > MA50 牛闸', main_window='入场日 et>=2025-06-01',
                          forming_bar='末根 bar 参与回测（与 box_module v1.0 一致）', seed=None),
             pool=dict(n=len(pool), dropped=dropped),
             runs={}, anchor=None)
    anchor_ok=True
    for key,rdef in runs.items():
        trs,agg=collect(rdef['params'], pool, bull, v1=False)
        rs_main=[t for t in trs if t['et']>=MAIN]
        r=dict(label=rdef['label'], params=rdef['params'],
               full=stats(trs), main=stats(rs_main),
               yearly_full=yearly(trs), yearly_main=yearly(rs_main),
               exit_stat=agg, trades=trs)
        if a.anchor:
            v1trs,_=collect(rdef['params'], pool, bull, v1=True)
            k2={(t['tkr'],t['et'],t['kind']) for t in v1trs}
            k1={(t['tkr'],t['et'],t['kind']) for t in trs}
            r['anchor']=dict(v1_n=len(k2), v2_n=len(k1), key_set_equal=(k1==k2))
            anchor_ok &= (k1==k2)
        out['runs'][key]=r
    out['anchor_all_pass']=anchor_ok if a.anchor else 'not run (--anchor)'
    with open(a.out,'w') as f: json.dump(out,f,ensure_ascii=False,indent=1)
    for key,r in out['runs'].items():
        fm,m=r['full'],r['main']
        print(f"{key}: 全窗 n={fm['n']} median={fm['median']} win={fm['win_pct']} | 主窗 n={m['n']} median={m['median']} win={m['win_pct']} mean={m['mean']} pf={m['pf']} thick={m['thick']['n']}/{m['thick']['sum_r']} exit={r['exit_stat']}")
    print('anchor_all_pass =', out['anchor_all_pass'])

if __name__=='__main__':
    main()
