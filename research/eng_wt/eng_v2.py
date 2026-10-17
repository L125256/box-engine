#!/usr/bin/env python3
# eng_v2.py — WT-A 统一回测口径引擎（V2 可实现出场价）
# 状态机/清洗/ATR/scan 逻辑与 box_module.py v1.0 逐字一致，唯一改动：
#   持仓出场记账价从「当根收盘价 px」改为 V2 可实现价：
#     ① 止损出场价 = min(eff, 当根 open)   （跳空低开按开盘价成交）
#     ② 止盈出场价 = max(tp, 当根 open)    （跳空高开按开盘价成交）
#     ③ 30bar 硬顶出场价 = 当根 close
#     出场价必须落在当根 [low,high] 内，不可实现则顺延到下一根可实现 bar（实测 0 次）
#     资金费 0.03%/bar 按 (出场bar - 入场bar) 计入 r
#   另：成交记录新增 ei（入场bar索引，仅用于主窗/分年按入场日切窗，不影响状态机）。
import json, os, argparse, statistics, datetime

def atrs(bars, n=14):
    out=[None]*len(bars); trs=[]
    for i in range(1,len(bars)):
        trs.append(max(bars[i]['high']-bars[i]['low'],abs(bars[i]['high']-bars[i-1]['close']),abs(bars[i]['low']-bars[i-1]['close'])))
        if i>=n: out[i]=sum(trs[-n:])/n
    return out

# 全局参数（由 CLI 覆盖，默认=冻结基线；B/X/Q/AMAX 冻结不开放）
N,K,M,B,X,E,Q,AMAX = 20,6.0,2,0.25,0.75,0.2,30,60
DEFER_COUNT = 0  # V2 顺延计数（自证守卫是否触发）

def scan(bars, idx_above_ma):
    """单票：返回当前箱体状态 dict（与 box_module.py 逐字一致，仅出场记账价按 V2）"""
    a=atrs(bars)
    state='seek';streak=0;box=None;pos=None;trades=[]
    for i in range(max(N,14)+1,len(bars)):
        if a[i] is None: continue
        px=bars[i]['close']
        if pos:
            hold=i-pos['ei']
            if px<=pos['eff'] or px>=pos['tp'] or hold>=Q:
                opn=bars[i]['open']  # ---- V2 可实现出场价（唯一改动块）----
                if px>=pos['tp']: xpx=max(pos['tp'],opn)
                elif px<=pos['eff']: xpx=min(pos['eff'],opn)
                else: xpx=px  # 30bar 硬顶按当根收盘价
                global DEFER_COUNT
                j=i
                while j<len(bars)-1 and not (bars[j]['low']<=xpx<=bars[j]['high']):
                    j+=1; xpx=bars[j]['open']; DEFER_COUNT+=1
                r=(xpx-pos['ep'])/pos['ep']*100-0.03*(j-pos['ei'])
                trades.append(dict(ep=pos['ep'],ei=pos['ei'],xi=j,xc=round(xpx,2),kind=pos['kind'],r=round(r,2),
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
    return dict(tkr_last=bars[-1], box=box, pos=pos, trades=trades)

def load_pool(cache):
    """清洗规则与 box_module.main() 逐字一致：low>0/close>0/low<=high/low<=close<=high，bars>=100。
    仅加载层适配：缓存顶层为 list（box_module 原取 d['bars_d']），字段为长名 time/open/high/low/close/volume。"""
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
    """idx=池等权收盘均价；MA50 牛闸（与 box_module.main() 逐字一致，池不随参数变，故只建一次）"""
    all_dates=sorted({b['time'] for bars in pool.values() for b in bars})
    idx={}
    for dt in all_dates:
        vals=[b['close'] for bars in pool.values() for b in bars if b['time']==dt]
        if vals: idx[dt]=sum(vals)/len(vals)
    dts=sorted(idx); ma50={}
    for i,dt in enumerate(dts):
        w=dts[max(0,i-49):i+1]; ma50[dt]=sum(idx[d] for d in w)/len(w)
    bull={dt: idx[dt]>ma50[dt] for dt in dts}
    return bull

def collect(params, pool, bull):
    global N,K,M,E,DEFER_COUNT
    N,K,M,E = params['N'],params['k'],params['m'],params['e']
    DEFER_COUNT=0
    trades=[]
    for tkr,bars in pool.items():
        for t in scan(bars, bull)['trades']:
            trades.append(dict(tkr=tkr, **t, et=bars[t['ei']]['time'], xt=bars[t['xi']]['time']))
    return sorted(trades,key=lambda t:(t['xi'],t['tkr']))

def stats(trades):
    rs=[t['r'] for t in trades]
    n=len(rs)
    if n==0: return dict(n=0,median=None,win_rate=None,mean=None,pf=None,rs=0.0,thick=dict(n=0,rs=0.0))
    wins=[r for r in rs if r>0]; losses=[r for r in rs if r<=0]
    if not losses or sum(losses)==0: pf='inf'
    else: pf=round(sum(wins)/abs(sum(losses)),4)
    thick=[r for r in rs if r>=8]
    return dict(n=n,
                median=round(statistics.median(rs),4),
                win_rate=round(len(wins)/n,4),
                mean=round(sum(rs)/n,4),
                pf=pf,
                rs=round(sum(rs),2),
                thick=dict(n=len(thick),rs=round(sum(thick),2)))

def yearly(trades):
    """分年按入场日（et）归年，与主窗切法一致"""
    out={}
    for y in ('2024','2025','2026'):
        sub=[t for t in trades if t['et'][:4]==y]
        rs=[t['r'] for t in sub]; n=len(rs)
        out[y]=dict(n=n,
                    median=round(statistics.median(rs),4) if n else None,
                    win=round(len([r for r in rs if r>0])/n,4) if n else None,
                    mean=round(sum(rs)/n,4) if n else None,
                    rs=round(sum(rs),2))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cache', default='/tmp/box_cache')
    ap.add_argument('--out', default='/tmp/eng_wt/baseline_v2.json')
    ap.add_argument('--k', type=float, default=6.0)
    ap.add_argument('--e', type=float, default=0.2)
    ap.add_argument('--N', type=int, default=20)
    ap.add_argument('--m', type=int, default=2)
    ap.add_argument('--seed', type=int, default=42)  # 引擎无随机源，仅按工单要求固定
    a=ap.parse_args()

    runs_def={
      'baseline': dict(label='基线 N=20/k6.0/m2/e0.2', params=dict(N=20,k=6.0,m=2,e=0.2)),
      'top1':     dict(label='Top1 k7.5/e0.3/N15/m2',  params=dict(N=15,k=7.5,m=2,e=0.3)),
      'planb':    dict(label='方案B k6.0/e0.3/N20/m1', params=dict(N=20,k=6.0,m=1,e=0.3)),
    }
    # CLI 非默认 → 单跑该套参数（便于逐套复现）；默认 → 跑三套
    cli_default = (a.k,a.e,a.N,a.m)==(6.0,0.2,20,2)
    runset = runs_def if cli_default else {'cli': dict(label=f'CLI N={a.N}/k{a.k}/m{a.m}/e{a.e}',
                                                       params=dict(N=a.N,k=a.k,m=a.m,e=a.e))}

    pool,dropped=load_pool(a.cache)
    bull=build_idx_bull(pool)

    out=dict(generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
             version='eng-v2(WT-A 统一口径)',
             caliber=dict(exit='V2 可实现价: 止损=min(eff,当根open) 止盈=max(tp,当根open) 30bar=当根close; 须落在当根[low,high]否则顺延',
                          pool='bars>=100 清洗池', main_window='入场日>=2025-06-01', funding='0.03%/bar', seed=42),
             pool=dict(n=len(pool), dropped=dropped),
             runs={})
    for key,rdef in runset.items():
        trs=collect(rdef['params'], pool, bull)
        rs_main=[t for t in trs if t['et']>='2025-06-01']
        out['runs'][key]=dict(label=rdef['label'], params=rdef['params'],
                              full=stats(trs), main=stats(rs_main), yearly=yearly(trs),
                              defer_count=DEFER_COUNT)
        if cli_default: out['runs'][key]['trades']=trs
    with open(a.out,'w') as f: json.dump(out,f,ensure_ascii=False,indent=1)
    for key,r in out['runs'].items():
        m=r['main']
        print(f"{key}: pool={len(pool)} 全窗 n={r['full']['n']} 主窗 n={m['n']} median={m['median']} win={m['win_rate']} mean={m['mean']} pf={m['pf']} defer={r['defer_count']}")

if __name__=='__main__':
    main()
