#!/usr/bin/env python3
# box_module.py — 独立箱体引擎（v1.0）：全池日线 → status/box-live.txt
# 参数（终版冻结）：N=20 k=6.0 m=2 b=0.25 x=0.75 e=0.2 TP=箱顶(回归)/箱顶+1ATR(突破)
# 止损=显示止损-0.3ATR有效止损（收盘判定）；30天硬顶；回归单挂池牛市闸(idx>MA50)
# 仓位=风险预算（止损2%满权、>8%放弃）；资金费0.03%/天。不触碰 replica_monitor.py。
import json, os, sys, datetime
CACHE = sys.argv[1] if len(sys.argv) > 1 else '/tmp/weekly_topic/run/cache'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'status/box-live.txt'
N,K,M,B,X,E,Q,AMAX = 20,6.0,2,0.25,0.75,0.2,30,60

def atrs(bars, n=14):
    out=[None]*len(bars); trs=[]
    for i in range(1,len(bars)):
        trs.append(max(bars[i]['high']-bars[i]['low'],abs(bars[i]['high']-bars[i-1]['close']),abs(bars[i]['low']-bars[i-1]['close'])))
        if i>=n: out[i]=sum(trs[-n:])/n
    return out

def scan(bars, idx_above_ma):
    """单票：返回当前箱体状态 dict 或 None"""
    a=atrs(bars)
    state='seek';streak=0;box=None;pos=None;trades=[]
    for i in range(max(N,14)+1,len(bars)):
        if a[i] is None: continue
        px=bars[i]['close']
        if pos:
            hold=i-pos['ei']; r=(px-pos['ep'])/pos['ep']*100-0.03*hold
            if px<=pos['eff'] or px>=pos['tp'] or hold>=Q:
                trades.append(dict(ep=pos['ep'],xi=i,xc=px,kind=pos['kind'],r=round(r,2),
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

def main():
    pool={}
    for f in sorted(os.listdir(CACHE)):
        d=json.load(open(os.path.join(CACHE,f)))['bars_d']
        cl=[b for b in d if b['low']>0 and b['close']>0 and b['low']<=b['high'] and b['low']<=b['close']<=b['high']]
        if len(cl)>=100: pool[f.replace('.json','')]=cl
    all_dates=sorted({b['time'] for bars in pool.values() for b in bars})
    idx={}
    for dt in all_dates:
        vals=[b['close'] for bars in pool.values() for b in bars if b['time']==dt]
        if vals: idx[dt]=sum(vals)/len(vals)
    dts=sorted(idx); ma50={}
    for i,dt in enumerate(dts):
        w=dts[max(0,i-49):i+1]; ma50[dt]=sum(idx[d] for d in w)/len(w)
    bull={dt: idx[dt]>ma50[dt] for dt in dts}
    cards=[]
    for tkr,bars in pool.items():
        res=scan(bars, bull); a=atrs(bars)
        pos, box = res['pos'], res['box']
        if pos:
            cards.append(dict(tkr=tkr, mode='持仓中', kind=pos['kind'], ep=pos['ep'], tp=round(pos['tp'],2),
                              disp=round(pos['disp'],2), eff=round(pos['eff'],2), days=len(bars)-1-pos['ei'],
                              last=bars[-1]['close']))
        elif box:
            L,H,li,_=box
            trig=round(H+B*a[len(bars)-1],2)
            cards.append(dict(tkr=tkr, mode='箱体锁定', top=round(H,2), bot=round(L,2),
                              age=len(bars)-1-li, last=bars[-1]['close'], trig=trig,
                              dist=round((trig-bars[-1]['close'])/bars[-1]['close']*100,2),
                              pos_in_box=round((bars[-1]['close']-L)/(H-L),2) if H>L else 0.5))
    hist=[]
    for tkr,bars in pool.items():
        for t in scan(bars, bull)['trades']:
            if t['xi']>=len(bars)-30:
                hist.append(dict(tkr=tkr, **t, xt=bars[t['xi']]['time']))
    hist=sorted(hist,key=lambda x:-x['xi'])[:40]
    out=dict(generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
             version='box-v1.0', params=dict(N=N,k=K,m=M,b=B,bull_gate='idx>MA50'),
             stats=dict(total=len(hist), wins=len([h for h in hist if h['r']>0]),
                        mean=round(sum(h['r'] for h in hist)/max(1,len(hist)),2)),
             cards=cards[:40], recent=hist)
    with open(OUT,'w') as f: json.dump(out,f,ensure_ascii=False,indent=1)
    print(f"box-live.txt: {len(cards)}卡 / 近30日{len(hist)}笔")

if __name__=='__main__':
    main()
