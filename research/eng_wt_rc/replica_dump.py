#!/usr/bin/env python3
# replica_v2.py — WT-A 独立复算（testing-expert 席，双审制度）
# 独立实现，未参考实现席代码；状态机规格照抄 box_module.py（只读）：
#   N=20 k6.0 m2 b0.25 x0.75 e0.2 Q30 AMAX60
#   seek→locked（N日振幅<K×ATR14 连续M日）
#   bk: 收盘>H+b×ATR, TP=H+1ATR, disp=ep-1.5ATR
#   fd: idx>MA50 且 low<=L+e×箱幅, TP=H, disp=L
#   eff=disp-0.3ATR; 门槛 eff>0 且 risk<=8%; 作废 px>H+xATR 或 px<L-xATR 或 age>60
#   资金费 0.03%/bar
# V2 可实现出场（本席独立解释，假设均已注释）：
#   止损 fill=min(eff, bar open)，fill 须在 [low,high] 内否则顺延（gap 低开按开盘价成交）
#   止盈 fill=max(tp, bar open)，fill 须在 [low,high] 内否则顺延（gap 高开按开盘价成交）
#   同根 bar 止损/止盈同时触发：保守取止损优先
#   硬顶 hold>=Q 按收盘价出场（当根止损/止盈未成交时）
# 主窗=入场日>=2025-06-01；seed=42
import json, os, random, statistics, sys

CACHE = '/tmp/box_cache'
OUT_DIR = '/tmp/eng_wt_test'
MAIN_WIN = '2025-06-01'
SEED = 42

PARAMS = {
    'baseline': dict(N=20, K=6.0, M=2, B=0.25, X=0.75, E=0.2, Q=30),
    'top1':     dict(N=15, K=7.5, M=2, B=0.25, X=0.75, E=0.3, Q=30),
    'planb':    dict(N=20, K=6.0, M=1, B=0.25, X=0.75, E=0.3, Q=30),
}
AMAX = 60  # 作废 60bar（三套通用）
FEE = 0.03  # %/bar


def load_pool():
    """176 文件，字段先探测（本环境下均为裸 list）；清洗后 bars>=100 入池"""
    pool = {}
    for f in sorted(os.listdir(CACHE)):
        d = json.load(open(os.path.join(CACHE, f)))
        if isinstance(d, dict):
            d = d.get('bars_d', [])
        cl = [b for b in d
              if b.get('low', 0) > 0 and b.get('close', 0) > 0
              and b['low'] <= b['high'] and b['low'] <= b['close'] <= b['high']]
        if len(cl) >= 100:
            pool[f.replace('.json', '')] = cl
    return pool


def atrs(bars, n=14):
    """照抄 box_module.atrs：TR 自 i=1 起，i>=n 时取最近 n 个 TR 均值"""
    out = [None] * len(bars)
    trs = []
    for i in range(1, len(bars)):
        trs.append(max(bars[i]['high'] - bars[i]['low'],
                       abs(bars[i]['high'] - bars[i - 1]['close']),
                       abs(bars[i]['low'] - bars[i - 1]['close'])))
        if i >= n:
            out[i] = sum(trs[-n:]) / n
    return out


def build_bull(pool):
    """全池等权 idx 与 MA50 牛市闸（照抄 box_module.main 的口径）"""
    all_dates = sorted({b['time'] for bars in pool.values() for b in bars})
    idx = {}
    for dt in all_dates:
        vals = [b['close'] for bars in pool.values() for b in bars if b['time'] == dt]
        if vals:
            idx[dt] = sum(vals) / len(vals)
    dts = sorted(idx)
    ma50 = {}
    for i, dt in enumerate(dts):
        w = dts[max(0, i - 49):i + 1]
        ma50[dt] = sum(idx[d] for d in w) / len(w)
    return {dt: idx[dt] > ma50[dt] for dt in dts}


def backtest(bars, bull, N, K, M, B, X, E, Q):
    """单票状态机 + V2 可实现出场；返回全部历史 trades（含审计字段）"""
    a = atrs(bars)
    state = 'seek'; streak = 0; box = None; pos = None; trades = []
    for i in range(max(N, 14) + 1, len(bars)):
        if a[i] is None:
            continue
        px = bars[i]['close']
        if pos:
            hold = i - pos['ei']
            o, lo, hi = bars[i]['open'], bars[i]['low'], bars[i]['high']
            xc = None; why = None
            # --- V2 止损：fill=min(eff, open)，须在 [low,high] 否则顺延 ---
            es = min(pos['eff'], o)
            if lo <= es <= hi:
                xc = es
                why = '止损gap' if o <= pos['eff'] else '止损'
            else:
                # --- V2 止盈：fill=max(tp, open)，须在 [low,high] 否则顺延 ---
                et = max(pos['tp'], o)
                if lo <= et <= hi:
                    xc = et
                    why = '止盈gap' if o >= pos['tp'] else '止盈'
            # --- 硬顶按收盘 ---
            if xc is None and hold >= Q:
                xc = px; why = '30天期满'
            if xc is not None:
                r = (xc - pos['ep']) / pos['ep'] * 100 - FEE * hold
                trades.append(dict(kind=pos['kind'], ep=pos['ep'], ei=pos['ei'],
                                   etime=bars[pos['ei']]['time'],
                                   xi=i, xtime=bars[i]['time'], xc=xc, r=r, why=why,
                                   hold=hold, eff=pos['eff'], tp=pos['tp'],
                                   xbar=dict(o=o, h=hi, l=lo, c=px)))
                pos = None
            continue
        if state == 'seek':
            w = bars[i - N + 1:i + 1]
            Hh = max(x['high'] for x in w); Ll = min(x['low'] for x in w)
            rng = Hh - Ll
            if rng > 0 and rng < K * a[i]:
                streak += 1
            else:
                streak = 0
            if streak >= M:
                state = 'locked'; box = [Ll, Hh, i, '']; streak = 0
            continue
        L, H, li, fired = box; rng = H - L; age = i - li
        sig = None
        if 'L' not in fired and px > H + B * a[i]:
            sig = ('bk', px)
        elif ('L' not in fired and bull.get(bars[i]['time'], False)
              and bars[i]['low'] <= L + E * rng):
            sig = ('fd', px)
        if sig is None and (px > H + X * a[i] or px < L - X * a[i] or age > AMAX):
            state = 'seek'; box = None; continue
        if sig:
            kind, ep = sig; box[3] += 'L'
            tp = H + a[i] if kind == 'bk' else H
            disp = ep - 1.5 * a[i] if kind == 'bk' else L
            eff = disp - 0.3 * a[i]
            risk = (ep - disp) / ep * 100
            if eff > 0 and risk <= 8.0:
                pos = dict(ep=ep, tp=tp, disp=disp, eff=eff, ei=i, kind=kind)
    return trades


def stats(trades):
    """n/median/win/mean/PF/sum + 厚利桶(r>=8) + 分年（按入场年）"""
    rs = [t['r'] for t in trades]
    n = len(rs)
    wins = [r for r in rs if r > 0]; losses = [r for r in rs if r <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses else None
    thick = [t for t in trades if t['r'] >= 8]
    yearly = {}
    for t in trades:
        y = t['etime'][:4]
        yearly.setdefault(y, []).append(t['r'])
    return dict(
        n=n,
        median=round(statistics.median(rs), 4) if rs else None,
        win=round(len(wins) / n * 100, 2) if n else None,
        mean=round(sum(rs) / n, 4) if n else None,
        pf=round(pf, 4) if pf is not None else None,
        sum=round(sum(rs), 4),
        thick=dict(n=len(thick), sum=round(sum(t['r'] for t in thick), 4)),
        yearly={y: dict(n=len(v), win=round(len([x for x in v if x > 0]) / len(v) * 100, 2),
                        median=round(statistics.median(v), 4),
                        mean=round(sum(v) / len(v), 4), sum=round(sum(v), 4))
                for y, v in sorted(yearly.items())},
    )


def verify_fill(t):
    """逐笔复核出场价可实性：fill 与当根 bar OHLC 及规则自洽"""
    o, hi, lo = t['xbar']['o'], t['xbar']['h'], t['xbar']['l']
    xc, eff, tp = t['xc'], t['eff'], t['tp']
    in_range = lo <= xc <= hi
    if t['why'].startswith('止损'):
        rule_ok = xc <= max(eff, o) + 1e-9 and (xc == o if o <= eff else abs(xc - eff) < 1e-9)
    elif t['why'].startswith('止盈'):
        rule_ok = xc >= min(tp, o) - 1e-9 and (xc == o if o >= tp else abs(xc - tp) < 1e-9)
    else:
        rule_ok = abs(xc - t['xbar']['c']) < 1e-9
    return dict(tkr=t['tkr'], etime=t['etime'], xtime=t['xtime'], kind=t['kind'], why=t['why'],
                ep=round(t['ep'], 4), xc=round(xc, 4), eff=round(eff, 4), tp=round(tp, 4),
                r=round(t['r'], 2), hold=t['hold'],
                bar=dict(o=o, h=hi, l=lo, c=t['xbar']['c']),
                fill_in_range=in_range, ok=in_range and rule_ok)


def main():
    pool = load_pool()
    print(f'pool={len(pool)} (expect 144)')
    bull = build_bull(pool)

    results = {}
    all_trades = {}
    for name, p in PARAMS.items():
        trs = []
        for tkr, bars in pool.items():
            for t in backtest(bars, bull, p['N'], p['K'], p['M'], p['B'], p['X'], p['E'], p['Q']):
                t['tkr'] = tkr
                trs.append(t)
        trs.sort(key=lambda t: (t['etime'], t['tkr']))
        main_trs = [t for t in trs if t['etime'] >= MAIN_WIN]
        all_trades[name] = main_trs
        results[name] = dict(all=dict(n=len(trs)), main=stats(main_trs))
        import csv
        with open(f'test_{name}.csv','w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['tkr','etime','xtime','kind','ep','xc','r','why','hold','eff','tp','ei','xi'])
            w.writeheader()
            for t in trs:
                w.writerow({k:t[k] for k in w.fieldnames})
        m = results[name]['main']
        print(f"{name}: all={len(trs)} main n={m['n']} median={m['median']} "
              f"win={m['win']} mean={m['mean']} pf={m['pf']} sum={m['sum']} "
              f"thick(n/sum)={m['thick']['n']}/{m['thick']['sum']}")

    # 独立性抽验：seed=42 随机 20 笔（主窗），验证出场价可实现
    random.seed(SEED)
    base = all_trades['baseline']
    samp = random.sample(base, min(20, len(base)))
    audit = [verify_fill(t) for t in samp]
    bad = [x for x in audit if not x['ok']]
    print(f'audit: {len(audit)} sampled, {len(bad)} failed')

    out = dict(
        generated='testing-expert replica_v2 (WT-A 双审)',
        seed=SEED, main_window=MAIN_WIN, pool=len(pool),
        data_note='box_cache 176 文件均为裸 list（无 bars_d 包裹），字段 time/open/high/low/close/volume',
        params={k: dict(v, AMAX=AMAX, fee_pct_per_bar=FEE) for k, v in PARAMS.items()},
        assumptions=dict(
            same_bar_priority='止损优先于止盈（保守）',
            gap_fill='止损 gap 低开按 open 成交、止盈 gap 高开按 open 成交；fill 不在 [low,high] 则顺延',
            hard_cap='hold>=Q 当根止损/止盈未成交则按收盘出场',
            yearly='按入场年分组',
        ),
        results=results,
        audit=audit,
    )
    with open(os.path.join(OUT_DIR, 'test_results.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('written test_results.json')


if __name__ == '__main__':
    main()
