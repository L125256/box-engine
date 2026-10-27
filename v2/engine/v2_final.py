# -*- coding: utf-8 -*-
"""Frozen v2 system: evaluation, leverage ladder, walk-forward windows, exports."""
import os
import sys
import json
import time
import math
import numpy as np
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2_lib as L

HERE = os.path.dirname(os.path.abspath(__file__))
START = 200

# ---------------------------------------------------------------- frozen config
A_RULES = dict(require_gate=True, gate_mode='ma50', trend_ma=100, slope_min=0.0,
               dev20_max=-0.04, rsi2_max=25, ret3_max=9.9, atrp_max=0.045,
               min_dv=30e6, min_price=5, warmup=210, score='rsi', tier='A',
               sig_exit=dict(sl_atr=2.5, tp_atr=2.0, hold=10))
B_RULES = dict(require_gate=True, gate_mode='ma50', trend_ma=100, slope_min=0.0,
               dev20_max=-0.02, rsi2_max=15, ret3_max=9.9, atrp_max=0.06,
               min_dv=20e6, min_price=5, warmup=210, score='rsi', tier='B',
               green_only=True, sig_exit=dict(sl_atr=2.0, tp_atr=1.5, hold=7))


def dedupe(sig):
    best = {}
    for x in sig:
        k = (x['sym'], x['i'])
        if k not in best or (x['tier'], -x['score']) < (best[k]['tier'], -best[k]['score']):
            best[k] = x
    out = list(best.values())
    out.sort(key=lambda x: (x['i'], x['tier'], -x['score']))
    return out


def monthly(sim, i0=START):
    cal = sim['dates']; cv = sim['curve']
    out = {}
    for m in sorted({cal[i][:7] for i in range(i0, len(cal))}):
        idx = [i for i in range(i0, len(cal)) if cal[i][:7] == m]
        a, b = idx[0], idx[-1]
        base = cv[a - 1] if a > 0 else 1.0
        out[m] = round(float(cv[b] / base - 1) * 100, 2)
    return out


def rolling(sim, win=130, step=20):
    cal = sim['dates']; out = []
    i = START
    while i < len(cal) - win:
        st = L.stats(sim, i, i + win)
        out.append(dict(a=cal[i], b=cal[i + win], final=round(st['final'], 4),
                        mdd=round(st['mdd'], 2), n=st['n'], win=round(st['win'], 1),
                        pf=round(st['pf'], 2)))
        i += step
    return out


def window(sim, d0, d1):
    cal = sim['dates']
    i0 = next(i for i in range(len(cal)) if cal[i] >= d0)
    i1 = max(i for i in range(len(cal)) if cal[i] <= d1)
    return L.stats(sim, i0, i1)


def conc(sim):
    p = np.array([t['pnl'] for t in sim['trades']])
    if len(p) == 0:
        return {}
    order = np.sort(p)[::-1]
    gp = p[p > 0].sum()
    out = dict(n=len(p), sum=float(p.sum() * 100),
               top5=float(order[:max(1, len(p) // 20)].sum() / max(gp, 1e-9) * 100),
               top10=float(order[:max(1, len(p) // 10)].sum() / max(gp, 1e-9) * 100))
    for pct in (0.05, 0.10, 0.20):
        k = int(len(p) * pct)
        out['drop%d' % int(pct * 100)] = float(order[k:].sum() * 100)
    return out


def tier_stats(sim):
    out = {}
    for t in ('A', 'B'):
        tr = [x for x in sim['trades'] if x.get('tier') == t]
        if not tr:
            continue
        p = np.array([x['pnl'] for x in tr])
        w = p[p > 0]; l = p[p <= 0]
        out[t] = dict(n=len(p), win=round(float((p > 0).mean() * 100), 1),
                      pay=round(float(w.mean() / max(1e-9, -l.mean())), 2) if len(l) else 99,
                      pf=round(float(w.sum() / max(1e-9, -l.sum())), 2),
                      sum=round(float(p.sum() * 100), 1))
    return out


def main():
    t0 = time.time()
    raw, cal, g = L.load_all(include_lev=False, include_etf=False)
    A = L.align(raw, cal, g)
    F = L.features(A)
    RG = L.build_regime(A, cal)
    BR, _ = L.breadth(A, F, cal)
    syms = sorted(A)

    sigA = L.make_signals(A, F, RG, BR, A_RULES)
    sigB = L.make_signals(A, F, RG, BR, B_RULES)
    sigAB = dedupe(sigA + sigB)
    print('universe %d  signals A=%d B=%d merged=%d' % (len(syms), len(sigA), len(sigB), len(sigAB)))

    # benchmark
    idx = RG['idx']
    cal_arr = np.array(cal)
    i0 = next(i for i in range(len(cal)) if cal[i] >= '2024-12-01')
    bench = idx[-1] / idx[i0 - 1]
    bcurve = idx[i0 - 1:] / idx[i0 - 1]
    bpk = np.maximum.accumulate(bcurve)
    print('benchmark EW index %.3f  mdd %.1f' % (bench, -(bcurve / bpk - 1).min() * 100))

    # profiles
    profiles = {
        'core': (sigA, dict(lev=5, margin_pct=0.02, max_pos=12, gross_cap=1.8)),
        'merge': (sigAB, dict(lev=5, margin_pct=0.02, max_pos=18, gross_cap=2.4)),
        'merge_m3': (sigAB, dict(lev=5, margin_pct=0.03, max_pos=18, gross_cap=2.4)),
        'merge_m4': (sigAB, dict(lev=5, margin_pct=0.04, max_pos=18, gross_cap=2.6)),
        'merge_m5': (sigAB, dict(lev=5, margin_pct=0.05, max_pos=18, gross_cap=3.0)),
        'merge_m6': (sigAB, dict(lev=5, margin_pct=0.06, max_pos=18, gross_cap=3.2)),
        'merge_b3_m4': (sigAB, dict(lev=3, margin_pct=0.04, max_pos=18, gross_cap=1.6)),
    }
    sims = {}
    out = dict(universe=len(syms), symbols=syms, benchmark=dict(final=float(bench),
               mdd=float(-(bcurve / bpk - 1).min() * 100), start=cal[i0 - 1]),
               config=dict(A={k: v for k, v in A_RULES.items() if k != 'sig_exit'},
                           B={k: v for k, v in B_RULES.items() if k != 'sig_exit'},
                           A_exit=A_RULES['sig_exit'], B_exit=B_RULES['sig_exit']),
               profiles={})
    for nm, (sig, p) in profiles.items():
        pp = dict(p)
        sm = L.simulate(A, F, RG, sig, pp)
        sims[nm] = sm
        st = L.stats(sm, START)
        yr = L.yearly(sm, START)
        out['profiles'][nm] = dict(
            st=st, years=yr, monthly=monthly(sm),
            sub={lab: window(sm, a, b) for lab, a, b in
                 [('2025H1', '2025-01-01', '2025-06-30'), ('2025H2', '2025-07-01', '2025-12-31'),
                  ('2026', '2026-01-01', '2026-12-31')]},
            conc=conc(sm), tiers=tier_stats(sm),
            exits=dict(collections.Counter(t['why'] for t in sm['trades'])),
            liq=sm['liq'], expo=st['expo'], trades=len(sm['trades']))
        print('\n%-12s final %.3f cagr %.1f mdd %.2f n %d win %.1f pay %.2f pf %.2f expo %.0f liq %d'
              % (nm, st['final'], st['cagr'], st['mdd'], st['n'], st['win'], st['payoff'],
                 st['pf'], st['expo'], sm['liq']))
        print('  years', {k: round(v, 1) for k, v in yr.items()})

    # rolling windows for core + merge
    out['rolling_core'] = rolling(sims['core'], 130, 20)
    out['rolling_merge'] = rolling(sims['merge'], 130, 20)
    out['rolling_merge4'] = rolling(sims['merge_m4'], 130, 20)

    # cost stress on merge_m4
    stress = []
    for cs, fd in ((0.001, 0.0003), (0.0015, 0.0005), (0.002, 0.0008), (0.003, 0.001)):
        pp = dict(profiles['merge_m4'][1]); pp['cost_side'] = cs; pp['funding'] = fd
        sm = L.simulate(A, F, RG, sigAB, pp)
        st = L.stats(sm, START)
        stress.append(dict(cost=cs * 100, funding=fd * 100, final=st['final'],
                           mdd=st['mdd'], pf=st['pf'], win=st['win']))
    out['stress'] = stress

    # monthly correlation core vs B-only (two-account check)
    smB = L.simulate(A, F, RG, sigB, dict(lev=5, margin_pct=0.02, max_pos=12, gross_cap=1.8))
    sims['B'] = smB
    out['B_only'] = L.stats(smB, START)

    # exported curves (weekly downsample) + trades for page
    def export(sm):
        cv = sm['curve']
        idxs = list(range(START, len(cv), 5))
        if idxs[-1] != len(cv) - 1:
            idxs.append(len(cv) - 1)
        return dict(dates=[sm['dates'][i] for i in idxs],
                    curve=[round(float(cv[i]), 5) for i in idxs])
    out['curves'] = {k: export(sims[k]) for k in ('core', 'merge', 'merge_m4')}
    out['trades'] = [dict(sym=t['sym'], entry=cal[t['entry']], exit=cal[t['exit']],
                          pnl=round(float(t['pnl'] * 100), 3), ret=round(float(t['ret'] * 100), 2),
                          why=t['why'], tier=t.get('tier'), bars=int(t['bars']))
                     for t in sims['merge_m4']['trades']]

    # latest state
    last = len(cal) - 1
    out['state'] = dict(asof=cal[last], gate=bool(RG['gate'][last]),
                        idx=round(float(RG['idx'][last]), 3), ma50=round(float(RG['ma50'][last]), 3),
                        breadth=round(float(BR[last]) * 100, 1),
                        gap=round(float(RG['idx'][last] / RG['ma50'][last] - 1) * 100, 2),
                        participants=int(sum(1 for s in A if A[s]['real'][last])))
    # candidates on the last close
    cands = []
    for s in ('A', 'B'):
        pass
    by_day = {}
    for x in sigAB:
        by_day.setdefault(x['i'], []).append(x)
    for x in by_day.get(last, []):
        b = A[x['sym']]
        cands.append(dict(sym=x['sym'], tier=x['tier'], rsi2=round(x['rsi2'], 1),
                          dev20=round(x['dev20'] * 100, 2), close=round(x['close'], 2),
                          atr=round(x['atr'], 2)))
    out['candidates'] = cands
    out['open_positions'] = []

    with open(os.path.join(HERE, 'v2_final.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print('\nwrote v2_final.json  %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
