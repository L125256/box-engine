#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HF-1 定稿：三层叠加（A 深回撤 / B 极端超卖收阳 / C 5日急跌）+ 执行清单与稳健性明细。
产出 hf1.json（页面数据）与 stdout 摘要。
"""
import os, sys, json, datetime, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'v2'))
sys.path.insert(0, HERE)
import v2_lib as V                                        # noqa: E402
from v2_final import A_RULES, dedupe, START               # noqa: E402
import hf7 as H7                                          # noqa: E402

BR_MIN = 0.45
BR_WIN = 5
PROF = dict(lev=5, margin_pct=0.025, max_pos=20, gross_cap=2.5)
LAYERS = [('A 深回撤', dict(A_RULES)),
          ('B 极端超卖', H7.tier()),
          ('C 5日急跌', H7.C_layer())]
EQUITY = 10000
CST = datetime.timezone(datetime.timedelta(hours=8))


def _v21_ref():
    """v2.1 对照口径：优先读刚重建的 v2_page.json，读不到才用上次落盘的常数。"""
    try:
        p = json.load(open(os.path.join(HERE, '..', 'v2', 'v2_page.json'), encoding='utf-8'))
        s = p['addendum']['cand']['st']
        days = p['profiles']['C']['st']['days']
        return dict(n=s['n'], win=round(s['win'], 1), payoff=round(s['payoff'], 2),
                    pf=round(s['pf'], 2), cagr=round(s['cagr'], 1), mdd=round(s['mdd'], 2),
                    per_month=round(s['n'] / (days / 30.44), 1))
    except Exception:
        return dict(n=110, win=63.6, payoff=1.44, pf=2.53, cagr=30.0, mdd=7.48, per_month=4.8)


def add_weekdays(d, k):
    x = datetime.date.fromisoformat(d)
    while k > 0:
        x += datetime.timedelta(days=1)
        if x.weekday() < 5:
            k -= 1
    return x.isoformat()


def next_weekday(d):
    return add_weekdays(d, 1)


def bar_complete(d):
    day = datetime.datetime.strptime(d[:10], '%Y-%m-%d').replace(tzinfo=CST)
    return datetime.datetime.now(CST) >= day + datetime.timedelta(days=1, hours=8)


def main():
    A, F, RG, BR, BR5, cal = H7.load()
    RGx = H7.gate_of(RG, BR5, BR_MIN)
    sig_all = dedupe(sum([V.make_signals(A, F, RGx, BR, dict(r)) for _, r in LAYERS], []))
    sim = V.simulate(A, F, RGx, sig_all, dict(PROF))
    st = V.stats(sim, START, len(cal) - 1)
    tr = sim['trades']
    ex = np.array([t['pnl'] for t in tr])

    # ---- 分层贡献
    by_tier = {}
    for code, r in LAYERS:
        sub = [t for t in tr if t.get('tier') == r['tier']]
        if not sub:
            by_tier[code] = dict(n=0); continue
        e = np.array([t['pnl'] for t in sub])
        w, l = e[e > 0], e[e <= 0]
        by_tier[code] = dict(n=len(sub), win=round(float((e > 0).mean() * 100), 1),
                             pf=round(float(w.sum() / max(1e-9, -l.sum())), 2),
                             avg=round(float(e.mean() * 100), 2),
                             rules=dict(dev20_max=r['dev20_max'], rsi2_max=r['rsi2_max'],
                                        exit=r['sig_exit']))

    # ---- 滚动 6 个月窗口
    cv = sim['curve']
    win_rows = []
    step = 183
    for s0 in range(START, len(cal) - 2 - step, 61):
        s1 = s0 + step
        r = float(cv[s1] / cv[s0] - 1)
        seg = cv[s0:s1 + 1]
        mdd = float(-((np.maximum.accumulate(seg) - seg) / np.maximum.accumulate(seg)).min() * 100)
        sub = [t for t in tr if s0 <= t['exit'] <= s1]
        e = np.array([t['pnl'] for t in sub]) if sub else np.array([0.0])
        win_rows.append(dict(from_=cal[s0], to=cal[s1], ret=round(r * 100, 1), mdd=round(mdd, 1),
                             n=len(sub), win=round(float((e > 0).mean() * 100), 1) if sub else None))

    # ---- 分月
    mon = collections.OrderedDict()
    for t in tr:
        k = cal[t['exit']][:7]
        mon[k] = mon.get(k, 0.0) + t['pnl']
    monthly = {k: round(v * 100, 2) for k, v in mon.items()}

    # ---- 今日闸门与候选
    i = len(cal) - 1
    while i > 0 and not bar_complete(cal[i]):
        i -= 1
    asof = cal[i]
    gate_open = bool(RGx['gate'][i])
    idx, ma = float(RG['idx'][i]), float(RG['ma50'][i])
    br_now, br5_now = float(BR[i]), float(np.nan_to_num(BR5[i]))
    closed = 0
    j = i
    while j > 0 and not RGx['gate'][j]:
        closed += 1; j -= 1
    # ---- 逐标的在最后一根收全日线上判定三层规则（与 make_signals 同条件）
    def hit_at(sym, k, r):
        b = A[sym]; f = F[sym]
        if not b['real'][k] or k - b['first'] < r.get('warmup', 210):
            return None
        if b['jump'][k]:
            return None
        c = float(b['c'][k])
        if c < r['min_price'] or f['dv20'][k] < r['min_dv']:
            return None
        if not np.isfinite(f['atrp'][k]) or f['atrp'][k] > r['atrp_max']:
            return None
        if c < f['ma%d' % r['trend_ma']][k] or f['slope100'][k] < r['slope_min']:
            return None
        if f['dev20'][k] > r['dev20_max'] or f['rsi2'][k] > r['rsi2_max']:
            return None
        if f['ret3'][k] > r['ret3_max']:
            return None
        if r.get('green_only') and not c > float(b['o'][k]):
            return None
        if r.get('min_drop5') is not None and f['ret5'][k] > r['min_drop5']:
            return None
        if r.get('ma_touch'):
            ma = f['ma%d' % r['ma_touch']][k]
            if not (abs(c / ma - 1) <= r.get('touch_tol', 0.01)):
                return None
        return dict(sym=sym, close=c, atr=float(f['atr'][k]),
                    rsi2=float(f['rsi2'][k]), dev20=float(f['dev20'][k]),
                    atrp=float(f['atrp'][k]), dv20=float(f['dv20'][k]),
                    ret5=float(f['ret5'][k]),
                    g20=float(c / b['h'][max(0, k - 19):k + 1].max() - 1))

    def miss_at(sym, k, r):
        b = A[sym]; f = F[sym]; out = []
        c = float(b['c'][k])
        if not b['real'][k] or k - b['first'] < r.get('warmup', 210):
            out.append('历史不足')
        if c < r['min_price']:
            out.append('价 %g < %g' % (c, r['min_price']))
        if f['dv20'][k] < r['min_dv']:
            out.append('20日均额 %.0fM < %.0fM' % (f['dv20'][k] / 1e6, r['min_dv'] / 1e6))
        if not np.isfinite(f['atrp'][k]) or f['atrp'][k] > r['atrp_max']:
            out.append('ATR%% %.2f%% > %.2f%%' % (f['atrp'][k] * 100, r['atrp_max'] * 100))
        if c < f['ma%d' % r['trend_ma']][k]:
            out.append('未站上 MA%d' % r['trend_ma'])
        if f['slope100'][k] < r['slope_min']:
            out.append('MA100 斜率为负')
        if f['dev20'][k] > r['dev20_max']:
            out.append('20日偏离 %.2f%% > %.2f%%' % (f['dev20'][k] * 100, r['dev20_max'] * 100))
        if f['rsi2'][k] > r['rsi2_max']:
            out.append('RSI2 %.1f > %g' % (f['rsi2'][k], r['rsi2_max']))
        if r.get('green_only') and not c > float(b['o'][k]):
            out.append('当日未收阳')
        if r.get('min_drop5') is not None and f['ret5'][k] > r['min_drop5']:
            out.append('5日跌幅 %.1f%% 不足' % (f['ret5'][k] * 100))
        return out

    cands, near = [], []
    seen = set()
    for code, r in LAYERS:
        for sym in sorted(A):
            h = hit_at(sym, i, r)
            if h and sym not in seen:
                seen.add(sym)
                E = h['close']
                ex_ = r['sig_exit']
                cands.append(dict(sym=sym, tier=code, close=round(E, 4), atr=round(h['atr'], 4),
                                  rsi2=round(h['rsi2'], 1), dev20=round(h['dev20'] * 100, 2),
                                  atrp=round(h['atrp'] * 100, 2), dv20=round(h['dv20'] / 1e6, 1),
                                  g20=round(h['g20'] * 100, 2),
                                  ref=E, stop=round(E - ex_['sl_atr'] * h['atr'], 4),
                                  tp=round(E + ex_['tp_atr'] * h['atr'], 4),
                                  stop_pct=round(-ex_['sl_atr'] * h['atr'] / E * 100, 2),
                                  tp_pct=round(ex_['tp_atr'] * h['atr'] / E * 100, 2),
                                  hold=ex_['hold'],
                                  margin=round(EQUITY * PROF['margin_pct'], 2),
                                  notional=round(EQUITY * PROF['margin_pct'] * PROF['lev'], 2),
                                  qty=round(EQUITY * PROF['margin_pct'] * PROF['lev'] / E, 4),
                                  stop_eq_pct=round(-ex_['sl_atr'] * h['atr'] / E * 100 *
                                                    PROF['lev'] * PROF['margin_pct'], 3),
                                  expiry=add_weekdays(next_weekday(asof), ex_['hold'])))
            elif sym not in seen:
                mm = miss_at(sym, i, r)
                if len(mm) <= 2:
                    fa = F[sym]
                    near.append(dict(sym=sym, tier=code, close=round(float(A[sym]['c'][i]), 4),
                                     atr=round(float(fa['atr'][i]), 4),
                                     rsi2=round(float(fa['rsi2'][i]), 1),
                                     dev20=round(float(fa['dev20'][i]) * 100, 2),
                                     atrp=round(float(fa['atrp'][i]) * 100, 2),
                                     miss=mm, n_miss=len(mm)))
    ded = {}
    for x in near:
        if x['sym'] not in ded or x['n_miss'] < ded[x['sym']]['n_miss']:
            ded[x['sym']] = x
    near = sorted(ded.values(), key=lambda z: (z['n_miss'], z['close']))
    if not gate_open and not os.environ.get('HF1_FORCE_OPEN'):
        cands, near = [], (cands + near)
        for x in near:
            x.setdefault('miss', [])
            if x.get('tier'):
                x['miss'] = ['闸门关闭'] + [m for m in x['miss'] if m != '闸门关闭']
                x['n_miss'] = len(x['miss'])
        near.sort(key=lambda z: z['n_miss'])
        seen2, ded = set(), []
        for x in near:
            if x['sym'] in seen2:
                continue
            seen2.add(x['sym']); ded.append(x)
        near = ded
    else:
        near.sort(key=lambda z: z.get('n_miss', 9))
    # 候补差距（闸门关闭时说明还差什么）
    gaps = []
    if not gate_open:
        gaps.append('指数 %.3f 低于 MA50 %.3f（差 %.2f%%）' % (idx, ma, (idx / ma - 1) * 100))
        gaps.append('5 日平滑广度 %.1f%% 低于阈值 %.0f%%' % (br5_now * 100, BR_MIN * 100))

    days = (np.datetime64(cal[-2]) - np.datetime64(cal[START])).astype(int) / 30.44
    oos0 = [k for k, d in enumerate(cal) if d >= '2026-01-01'][0]
    oos = V.stats(sim, oos0, len(cal) - 2)
    top5 = float(np.sort(ex)[::-1][:5].sum() / max(1e-9, ex[ex > 0].sum()) * 100)
    run = mx = 0
    for x in ex:
        run = run + 1 if x <= 0 else 0
        mx = max(mx, run)

    out = dict(
        name='HF-1 三层叠加', built_at=datetime.datetime.now(CST).strftime('%Y-%m-%d %H:%M'),
        asof=asof, next_entry=next_weekday(asof),
        gate=dict(open=gate_open, idx=round(idx, 3), ma50=round(ma, 3),
                  gap=round((idx / ma - 1) * 100, 2), br=round(br_now * 100, 1),
                  br5=round(br5_now * 100, 1), br_min=BR_MIN * 100, closed_days=closed),
        gaps=gaps,
        config=dict(layers=[dict(code=c, dev20_max=r['dev20_max'], rsi2_max=r['rsi2_max'],
                                 atrp_max=r['atrp_max'], min_dv=r['min_dv'],
                                 green_only=r.get('green_only', False),
                                 min_drop5=r.get('min_drop5'), exit=r['sig_exit'])
                            for c, r in LAYERS],
                    n_universe=len(A), prof=PROF, equity=EQUITY,
                    max_stop_pct=round(max(r['sig_exit']['sl_atr'] * r['atrp_max'] for _, r in LAYERS) * 100, 2),
                    abandon_pct=round((1.0 / PROF['lev'] - 0.01) * 0.8 * 100, 1),
                    cost_rt=round(PROF.get('cost_side', 0.001) * 200, 2),
                    fund_day=0.03, liq_pct=19.0),
        stats=dict(n=st['n'], per_month=round(st['n'] / days, 1), win=round(st['win'], 1),
                   payoff=round(st['payoff'], 2), pf=round(st['pf'], 2),
                   cagr=round(st['cagr'], 1), mdd=round(st['mdd'], 2),
                   sharpe=round(st['sharpe'], 2), avg=round(st['avg'], 2),
                   expo=round(st['expo'], 1), liq=st['liq'], top5=round(top5, 1),
                   max_consec_loss=mx, months_pos=int(sum(1 for v in mon.values() if v > 0)),
                   months=len(mon), exit_mix=dict(collections.Counter(t['why'] for t in tr)),
                   oos=dict(n=oos['n'], win=round(oos['win'], 1), pf=round(oos['pf'], 2),
                            cagr=round(oos['cagr'], 1), mdd=round(oos['mdd'], 2))),
        by_tier=by_tier, monthly=monthly, rolling=win_rows,
        candidates=cands[:20], near=near[:20],
        curve=[round(float(x), 4) for x in sim['curve'][START:len(cal) - 1:4]],
        curve_dates=cal[START:len(cal) - 1:4],
        v21=_v21_ref(),
    )
    with open(os.path.join(HERE, 'hf1.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=float)
    s = out['stats']
    print('HF-1  n=%d  %.1f 笔/月  胜率 %.1f%%  赔率 %.2f  PF %.2f  年化 %.1f%%  回撤 %.2f%%  爆仓 %d' % (
        s['n'], s['per_month'], s['win'], s['payoff'], s['pf'], s['cagr'], s['mdd'], s['liq']))
    print('2026 样本外  n=%d  胜率 %.1f%%  PF %.2f  年化 %.1f%%  回撤 %.2f%%' % (
        s['oos']['n'], s['oos']['win'], s['oos']['pf'], s['oos']['cagr'], s['oos']['mdd']))
    print('分层', json.dumps({k: v.get('n') for k, v in by_tier.items()}, ensure_ascii=False))
    print('闸门', out['gate']['open'], '候选', len(cands), '候补', len(near), 'asof', asof)
    print('滚动窗口胜率', [w['win'] for w in win_rows])


if __name__ == '__main__':
    main()
