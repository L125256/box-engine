# -*- coding: utf-8 -*-
"""Consolidated diagnostics for the v2 review page (core-only)."""
import os, sys, json, math, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2_lib as L
from v2_final import A_RULES, START, rolling, window

HERE = os.path.dirname(os.path.abspath(__file__))

PROFILES = {
    'B': dict(lev=3, margin_pct=0.06, max_pos=12, gross_cap=2.5),
    'C': dict(lev=5, margin_pct=0.04, max_pos=12, gross_cap=2.5),
    'D': dict(lev=5, margin_pct=0.06, max_pos=12, gross_cap=2.5),
}


def monthly(sm):
    cal = sm['dates']; cv = sm['curve']; out = {}
    for m in sorted({cal[i][:7] for i in range(START, len(cal))}):
        idx = [i for i in range(START, len(cal)) if cal[i][:7] == m]
        a, b = idx[0], idx[-1]
        out[m] = round(float(cv[b] / (cv[a - 1] if a > 0 else 1.0) - 1) * 100, 2)
    return out


def quarterly(sm):
    cal = sm['dates']; out = {}
    qs = sorted({(cal[i][:4], (int(cal[i][5:7]) - 1) // 3 + 1) for i in range(START, len(cal))})
    for y, q in qs:
        idx = [i for i in range(START, len(cal)) if cal[i][:4] == y and (int(cal[i][5:7]) - 1) // 3 + 1 == q]
        i0, i1 = idx[0], idx[-1]
        st = L.stats(sm, i0, i1)
        out['%sQ%d' % (y, q)] = dict(final=round(st['final'], 4), mdd=round(st['mdd'], 2),
                                     n=st['n'], win=round(st['win'], 1), pf=round(st['pf'], 2),
                                     avg=round(st['avg'], 2))
    return out


def weekly(sm):
    cal = sm['dates']; cv = sm['curve']
    idxs = list(range(START, len(cv), 5))
    if idxs[-1] != len(cv) - 1:
        idxs.append(len(cv) - 1)
    return dict(dates=[cal[i] for i in idxs], curve=[round(float(cv[i]), 5) for i in idxs])


def drawdown(sm):
    w = weekly(sm); c = np.array(w['curve']); pk = np.maximum.accumulate(c)
    return dict(dates=w['dates'], dd=[round(float((x / p - 1) * 100), 2) for x, p in zip(c, pk)])


def max_concurrent(sm):
    ev = []
    for t in sm['trades']:
        ev.append((t['entry'], 1)); ev.append((t['exit'], -1))
    ev.sort()
    cur = mx = 0
    for _, d in ev:
        cur += d; mx = max(mx, cur)
    return mx


def by_symbol(sm):
    d = {}
    for t in sm['trades']:
        r = d.setdefault(t['sym'], dict(n=0, pnl=0.0, w=0))
        r['n'] += 1; r['pnl'] += t['pnl']; r['w'] += t['pnl'] > 0
    out = [dict(sym=k, n=v['n'], pnl=round(v['pnl'] * 100, 2),
                win=round(v['w'] / v['n'] * 100, 1)) for k, v in d.items()]
    out.sort(key=lambda x: -x['pnl'])
    return out


def by_exit(sm):
    d = {}
    for t in sm['trades']:
        r = d.setdefault(t['why'], dict(n=0, pnl=0.0, w=0))
        r['n'] += 1; r['pnl'] += t['pnl']; r['w'] += t['pnl'] > 0
    return {k: dict(n=v['n'], pnl=round(v['pnl'] * 100, 2), win=round(v['w'] / v['n'] * 100, 1))
            for k, v in d.items()}


def risk(sm, st):
    tr = sm['trades']; p = np.array([t['pnl'] for t in tr])
    holds = np.array([t['bars'] for t in tr])
    ex = sm['exposure'][START:]
    return dict(
        avg_hold=round(float(holds.mean()), 1),
        med_hold=round(float(np.median(holds)), 1),
        max_hold=int(holds.max()), min_hold=int(holds.min()),
        best=round(float(p.max() * 100), 2), worst=round(float(p.min() * 100), 2),
        avg_win=round(float(p[p > 0].mean() * 100), 2) if (p > 0).any() else 0,
        avg_loss=round(float(p[p <= 0].mean() * 100), 2) if (p <= 0).any() else 0,
        win_rate=round(float((p > 0).mean() * 100), 1),
        expo_p95=round(float(np.nanpercentile(ex, 95)) * 100, 1),
        expo_max=round(float(np.nanmax(ex)) * 100, 1),
        max_concurrent=max_concurrent(sm),
        max_dd=round(st['mdd'], 2),
        in_market=round(float((ex > 1e-6).mean() * 100), 1),
    )


def concentration(sm):
    p = np.array([t['pnl'] for t in sm['trades']])
    gp = float(p[p > 0].sum())
    order = np.sort(p)[::-1]
    k = max(1, len(p) // 20)
    by_sym = {}
    for t in sm['trades']:
        by_sym[t['sym']] = by_sym.get(t['sym'], 0.0) + t['pnl']
    top = max(by_sym.items(), key=lambda kv: kv[1])
    return dict(top5_share=round(float(order[:k].sum() / max(gp, 1e-9) * 100), 1),
                drop5_sum=round(float(order[k:].sum() * 100), 2),
                top_sym=top[0], top_sym_share=round(float(top[1] / max(gp, 1e-9) * 100), 1),
                gross_profit=round(gp * 100, 1))


def cfg_stat(A, F, RG, BR, entry=None, exit=None):
    p = dict(A_RULES)
    if entry:
        p.update(entry)
    if exit:
        p['sig_exit'] = exit
    sig = L.make_signals(A, F, RG, BR, p)
    sm = L.simulate(A, F, RG, sig, dict(lev=5, margin_pct=0.04, max_pos=12, gross_cap=2.5))
    st = L.stats(sm, START)
    return dict(final=round(st['final'], 3), cagr=round(st['cagr'], 1), mdd=round(st['mdd'], 2),
                n=st['n'], win=round(st['win'], 1), payoff=round(st['payoff'], 2), pf=round(st['pf'], 2))


def weekly_expo(sm):
    ex = sm['exposure'][START:]
    idxs = list(range(0, len(ex), 5))
    if idxs[-1] != len(ex) - 1:
        idxs.append(len(ex) - 1)
    return dict(dates=[sm['dates'][START + i] for i in idxs],
                expo=[round(float(ex[i]) * 100, 1) for i in idxs])


def yearly_detail(sm):
    cal = sm['dates']; cv = sm['curve']; out = {}
    for y in sorted({cal[i][:4] for i in range(START, len(cal))}):
        idx = [i for i in range(START, len(cal)) if cal[i][:4] == y]
        i0, i1 = idx[0], idx[-1]
        st = L.stats(sm, i0, i1)
        out[y] = dict(final=round(float(cv[i1] / (cv[i0 - 1] if i0 > 0 else 1.0) - 1) * 100, 1),
                      n=st['n'], win=round(st['win'], 1), pf=round(st['pf'], 2),
                      mdd=round(st['mdd'], 2))
    return out


def gate_stats(RG, cal, BR):
    g = RG['gate']; i0 = START
    on = int(np.nansum(g[i0:]))
    total = len(g) - i0
    k = len(g) - 1
    while k >= 0 and not g[k]:
        k -= 1
    cur = len(g) - 1 - k
    longest = 0; run = 0
    for x in g[i0:]:
        if not x:
            run += 1; longest = max(longest, run)
        else:
            run = 0
    by_year = {}
    for y in sorted({cal[i][:4] for i in range(i0, len(cal))}):
        idx = [i for i in range(i0, len(cal)) if cal[i][:4] == y]
        by_year[y] = round(float(np.nansum(g[idx]) / len(idx) * 100), 1)
    return dict(on_pct=round(on / total * 100, 1), current_closed_days=cur,
                longest_closed=longest, by_year=by_year)


def main():
    raw, cal, g = L.load_all(include_lev=False, include_etf=False)
    A = L.align(raw, cal, g); F = L.features(A); RG = L.build_regime(A, cal)
    BR, _ = L.breadth(A, F, cal)
    sig = L.make_signals(A, F, RG, BR, A_RULES)
    print('signals', len(sig))

    out = dict(asof=cal[-1], start=cal[START], universe=len(A),
               config=dict(entry={k: v for k, v in A_RULES.items() if k != 'sig_exit'},
                           exit=A_RULES['sig_exit'],
                           costs=dict(fee_side=0.05, slip_side=0.05, funding_bar=0.03,
                                      mmr=1.0, liq_fee=0.6)),
               profiles={}, curves={}, dd={}, trades={}, monthly={}, quarterly={},
               rolling={}, symbols={}, exits={}, risk={}, gate=gate_stats(RG, cal, BR),
               stress=[], benchmark={})

    sims = {}
    for nm, p in PROFILES.items():
        sm = L.simulate(A, F, RG, sig, p)
        sims[nm] = sm
        st = L.stats(sm, START)
        out['profiles'][nm] = dict(params=p, st=st,
                                   years={k: round(v, 1) for k, v in L.yearly(sm, START).items()},
                                   sub={lab: L.stats(sm, next(i for i in range(len(cal)) if cal[i] >= a),
                                                     max(i for i in range(len(cal)) if cal[i] <= b))
                                        for lab, a, b in [('2025H1', '2025-01-01', '2025-06-30'),
                                                          ('2025H2', '2025-07-01', '2025-12-31'),
                                                          ('2026', '2026-01-01', '2026-12-31')]})
        out['curves'][nm] = weekly(sm)
        out['dd'][nm] = drawdown(sm)
        out['monthly'][nm] = monthly(sm)
        out['quarterly'][nm] = quarterly(sm)
        out['rolling'][nm] = rolling(sm, 130, 20)
        out['symbols'][nm] = by_symbol(sm)
        out['exits'][nm] = by_exit(sm)
        out['risk'][nm] = risk(sm, st)
        print('%-2s final %.3f cagr %.1f mdd %.2f n %d win %.1f pay %.2f pf %.2f expo %.0f'
              % (nm, st['final'], st['cagr'], st['mdd'], st['n'], st['win'], st['payoff'], st['pf'], st['expo']))

    C = PROFILES['C']; sm = sims['C']
    out['trades']['C'] = [dict(sym=t['sym'], entry=cal[t['entry']], exit=cal[t['exit']],
                               pnl=round(float(t['pnl'] * 100), 3), ret=round(float(t['ret'] * 100), 2),
                               why=t['why'], bars=int(t['bars']), entry_i=int(t['entry']))
                          for t in sm['trades']]
    out['worst'] = sorted(out['trades']['C'], key=lambda x: x['pnl'])[:8]
    out['best'] = sorted(out['trades']['C'], key=lambda x: -x['pnl'])[:8]
    out['concentration'] = concentration(sm)
    out['expo_curve'] = weekly_expo(sm)
    out['yearly_detail'] = {'C': yearly_detail(sm)}
    sig_days = collections.Counter(x['i'] for x in sig)
    out['signal_days'] = dict(days=len(sig_days), max_day=max(sig_days.values()),
                              avg=round(len(sig) / max(1, len(sig_days)), 1),
                              crowded=sum(1 for v in sig_days.values() if v >= 12))

    out['neighborhood'] = dict(exit=[], entry=[])
    for sl, tp, hd in ((2.5, 2.0, 8), (2.5, 2.0, 9), (2.5, 2.0, 10), (2.5, 2.0, 11),
                       (2.0, 2.0, 10), (3.0, 2.0, 10), (2.5, 1.5, 10), (2.5, 2.5, 10)):
        r = cfg_stat(A, F, RG, BR, exit=dict(sl_atr=sl, tp_atr=tp, hold=hd))
        r.update(sl=sl, tp=tp, hold=hd)
        out['neighborhood']['exit'].append(r)
    for lab, ov in (('dev20 -3%', dict(dev20_max=-0.03)), ('dev20 -4%', {}),
                    ('dev20 -5%', dict(dev20_max=-0.05)),
                    ('RSI2 20', dict(rsi2_max=20)), ('RSI2 25', {}),
                    ('RSI2 30', dict(rsi2_max=30)),
                    ('ATR 4.0%', dict(atrp_max=0.04)), ('ATR 4.5%', {}),
                    ('ATR 5.0%', dict(atrp_max=0.05))):
        r = cfg_stat(A, F, RG, BR, entry=ov)
        r['label'] = lab
        out['neighborhood']['entry'].append(r)
    print('neighborhood done')

    for cs, fd in ((0.0005, 0.0003), (0.001, 0.0003), (0.0015, 0.0005),
                   (0.002, 0.0005), (0.002, 0.0008), (0.003, 0.001)):
        pp = dict(C); pp['cost_side'] = cs; pp['funding'] = fd
        sx = L.simulate(A, F, RG, sig, pp); st = L.stats(sx, START)
        out['stress'].append(dict(cost=cs * 100, funding=fd * 100, final=st['final'],
                                  mdd=st['mdd'], pf=st['pf'], win=st['win']))
        print('stress cost %.2f fund %.2f -> %.3f pf %.2f win %.1f' % (cs * 100, fd * 100, st['final'], st['pf'], st['win']))

    idx = RG['idx'][START:]; base = idx[0]
    bc = idx / base; pk = np.maximum.accumulate(bc)
    bi = list(range(0, len(idx), 5))
    if bi[-1] != len(idx) - 1:
        bi.append(len(idx) - 1)
    dr = np.diff(bc) / bc[:-1]
    out['benchmark'] = dict(final=float(bc[-1]), mdd=float(-(bc / pk - 1).min() * 100),
                            dates=[cal[START + i] for i in bi],
                            curve=[round(float(bc[i]), 5) for i in bi],
                            sharpe=round(float(dr.mean() / max(1e-9, dr.std()) * math.sqrt(365)), 2))

    out['funnel'] = dict(signals=len(sig), dbg=sm['dbg'], executed=sm['n_sig'])
    last = len(cal) - 1
    out['state'] = dict(asof=cal[last], gate=bool(RG['gate'][last]),
                        idx=round(float(RG['idx'][last]), 3), ma50=round(float(RG['ma50'][last]), 3),
                        ma100=round(float(RG['ma100'][last]), 3),
                        breadth=round(float(BR[last]) * 100, 1),
                        gap=round(float(RG['idx'][last] / RG['ma50'][last] - 1) * 100, 2),
                        participants=int(sum(1 for s in A if A[s]['real'][last])))
    out['candidates'] = []
    for x in sig:
        if x['i'] == last:
            out['candidates'].append(dict(sym=x['sym'], rsi2=round(x['rsi2'], 1),
                                          dev20=round(x['dev20'] * 100, 2), close=round(x['close'], 2)))
    with open(os.path.join(HERE, 'v2_page.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print('wrote v2_page.json')
    print('gate', out['gate'])


if __name__ == '__main__':
    main()
