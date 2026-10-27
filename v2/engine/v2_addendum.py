# -*- coding: utf-8 -*-
"""Build addendum data: breadth confirmation, base comparison, Gate funding,
factbook audit. Writes v2_addendum.json and merges into v2_page.json."""
import os, sys, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v2_lib as L
from v2_final import A_RULES, dedupe, START, rolling

C_PROFILE = dict(lev=5, margin_pct=0.04, max_pos=12, gross_cap=2.5)
RESEARCH = os.environ.get('V2_RESEARCH') or os.path.abspath(
    os.path.join(HERE, '..', 'research', 'wo_mine'))


def sim_for(gate, A, F, RG, BR):
    RGx = dict(RG); RGx['gate'] = gate
    sig = dedupe(L.make_signals(A, F, RGx, BR, A_RULES))
    return L.simulate(A, F, RGx, sig, dict(C_PROFILE)), sig


def pack(sim, sig, cal, gate, BR, BR5):
    n = len(cal)
    st = L.stats(sim, START, n - 1)
    i26 = next(i for i in range(START, n) if cal[i] >= '2026-01-01')
    s26 = L.stats(sim, i26, n - 1)
    y26 = float(sim['curve'][n - 1] / sim['curve'][i26 - 1] - 1) * 100
    rr = rolling(sim, 130, 20)
    vals = [(x['final'] - 1) * 100 for x in rr]
    years = {k: round(v, 1) for k, v in L.yearly(sim, START).items()}
    trades = [dict(sym=t['sym'], entry=cal[t['entry']], exit=cal[t['exit']],
                   pnl=round(float(t['pnl'] * 100), 2), ret=round(float(t['ret'] * 100), 2),
                   why=t['why'], bars=int(t['bars']), entry_i=int(t['entry']),
                   breadth=round(float(BR[t['entry']]) * 100, 1),
                   breadth5=round(float(BR5[t['entry']]) * 100, 1))
              for t in sim['trades']]
    return dict(st=dict(final=round(st['final'], 3), cagr=round(st['cagr'], 1),
                        mdd=round(st['mdd'], 2), sharpe=round(st['sharpe'], 2),
                        n=st['n'], win=round(st['win'], 1), payoff=round(st['payoff'], 2),
                        pf=round(st['pf'], 2), expo=round(st['expo'], 1)),
                y2026=round(y26, 1), pf2026=round(s26['pf'], 2), n2026=s26['n'],
                years=years, rolling=dict(n=len(rr), pos=sum(1 for v in vals if v > 0),
                                          min=round(min(vals), 2), med=round(sorted(vals)[len(vals) // 2], 2),
                                          max=round(max(vals), 2)),
                gate_on=round(float(np.mean(gate[START:n - 1]) * 100), 1),
                signals=len(sig), trades=trades)


def funding_block():
    with open(os.path.join(HERE, 'gate_funding.json'), encoding='utf-8') as f:
        gf = json.load(f)
    with open(os.path.join(HERE, 'gate_funding_ew.json'), encoding='utf-8') as f:
        ew = json.load(f)['ew']
    syms = gf['symbols']
    rows = []
    for s, v in syms.items():
        rows.append(dict(sym=s, avg=round(float(v.get('avg_daily', 0)) * 100, 4),
                         ann=round(float(v.get('ann_avg', 0)) * 100, 1),
                         p95=round(float(v.get('p95_daily', 0)) * 100, 3),
                         max=round(float(v.get('max_daily', 0)) * 100, 3),
                         days=int(v.get('days', 0)), oi=float(v.get('oi', 0) or 0)))
    rows.sort(key=lambda x: -x['avg'])
    # mature period: drop first 30 daily observations after contract launch
    mat = []
    for s, v in syms.items():
        days = sorted(v['daily'].items())
        arr = np.array([x[1] for x in days[30:]], dtype=float)
        if len(arr) >= 30:
            mat.append(dict(sym=s, avg=round(float(arr.mean()) * 100, 4),
                            med=round(float(np.median(arr)) * 100, 4),
                            positive=round(float((arr > 0).mean()) * 100, 1),
                            days=int(len(arr))))
    mat.sort(key=lambda x: -x['avg'])
    ma = np.array([x['avg'] for x in mat], dtype=float)
    # daily EW, only days with enough names
    full = [(d, v, c) for d, v, c in ew if c >= 20]
    vals = np.array([v for _, v, _ in full], dtype=float)
    lastd = full[-1][0]
    last30 = [(d, v) for d, v, _ in full if d >= '2026-09-27']
    l30 = np.array([v for _, v in last30], dtype=float)
    gt = float((vals > 0.0003).mean() * 100)
    all_days = sorted({x[0] for x in ew})
    return dict(n_sym=len(rows), days=len(all_days),
                span=gf['summary'].get('span'), avg_daily=round(float(gf['summary']['avg_daily']) * 100, 4),
                ann=round(float(gf['summary']['ann']) * 100, 1),
                positive=int(gf['summary']['positive']),
                median_symbol=round(float(gf['summary']['median_symbol']) * 100, 4),
                ew_mean=round(float(vals.mean()) * 100, 4),
                ew_median=round(float(np.median(vals)) * 100, 4),
                ew_p90=round(float(np.percentile(vals, 90)) * 100, 4),
                ew_p95=round(float(np.percentile(vals, 95)) * 100, 4),
                ew_max=round(float(vals.max()) * 100, 4),
                ew_last30=round(float(l30.mean()) * 100, 4),
                last30_from=last30[0][0], last30_to=last30[-1][0],
                share_above_003=round(gt, 1), last_date=lastd,
                mature=dict(n=len(mat), mean=round(float(ma.mean()), 4),
                            median=round(float(np.median(ma)), 4),
                            p90=round(float(np.percentile(ma, 90)), 4),
                            p95=round(float(np.percentile(ma, 95)), 4),
                            max=round(float(ma.max()), 4),
                            positive=sum(1 for x in mat if x['avg'] > 0),
                            top=mat[:6]),
                top=rows[:8], bottom=rows[-5:],
                series=[dict(d=d, v=round(float(v) * 100, 4)) for d, v, _ in full])


def factbook_block():
    with open(os.path.join(RESEARCH, 'ATLAS_v1.json'), encoding='utf-8') as f:
        a = json.load(f)
    cells = a['cells']
    fam = {}
    for c in cells:
        f = fam.setdefault(c['family'], dict(cells=0, winning=0, invalid=0, thin=0, weak=0,
                                             variants=set()))
        f['cells'] += 1
        f['variants'].add(c['variant_id'])
        st = c['state']
        if st == '胜任': f['winning'] += 1
        elif st == '无效': f['invalid'] += 1
        elif st == '样本不足': f['thin'] += 1
        else: f['weak'] += 1
    fams = []
    for k in sorted(fam):
        v = fam[k]
        fams.append(dict(family=k, cells=v['cells'], variants=len(v['variants']),
                         winning=v['winning'], weak=v['weak'], thin=v['thin'], invalid=v['invalid']))
    comp = [dict(cell=c['cell_id'], family=c['family'], variant=c['variant_id'], domain=c['domain'],
                 n=c['n_days'], win=c['win_rate_pct'], excess=c['excess_pp'], ic=c['ic_mean'],
                 cushion=c['cushion_x'], q=c['fdr_q'], md=c['mdd_pct'], release=c['release_eligible'])
            for c in cells if c['state'] == '胜任']
    return dict(n_cells=a['n_cells'], counts=a['counts'], n_invalid_variants=len(a['map_invalid_variants']),
                n_variants=len(set(c['variant_id'] for c in cells)), families=fams,
                competent=comp, release_eligible=sum(1 for c in cells if c['release_eligible']),
                note='ATLAS v1 · 392 格；胜任 4 格全部为单池、release_eligible=false')


def bases_block():
    with open(os.path.join(HERE, 'v2_bases.json'), encoding='utf-8') as f:
        rows = json.load(f)
    keep = ['ma50', 'ma50_br50', 'ma80', 'ma100', 'ma200', 'br50', 'br60', 'vol80',
            'slope_only', 'none', 'ma100_dd8', 'ma50_slope']
    out = []
    for k in keep:
        for r in rows:
            if r['key'] == k:
                out.append(dict(key=k, desc=r['desc'], final=round(r['final'], 3),
                                cagr=round(r['cagr'], 1), mdd=round(r['mdd'], 2), pf=round(r['pf'], 2),
                                n=r['n'], win=round(r['win'], 1), expo=round(r['expo'], 1),
                                y2025=round(r['y2025'], 1), y2026=round(r['y2026'], 1),
                                pf2026=round(r['pf2026'], 2), gate_on=round(r['gate_on'], 1)))
                break
    return out


def weekly_curve(sim, cal):
    n = len(cal)
    ii = list(range(START, n, 5))
    if ii[-1] != n - 1:
        ii.append(n - 1)
    return dict(dates=[cal[i] for i in ii], curve=[round(float(sim['curve'][i]), 5) for i in ii])


def main():
    raw, cal, g = L.load_all(include_lev=False, include_etf=False)
    A = L.align(raw, cal, g); F = L.features(A); RG = L.build_regime(A, cal)
    BR, _ = L.breadth(A, F, cal)
    n = len(cal)
    idx, ma50 = RG['idx'], RG['ma50']
    BR0 = np.where(np.isnan(BR), 0.0, BR)
    base_gate = idx > ma50
    cand_gate = base_gate & (L._roll(BR0, 5) >= 0.45)

    BR5 = L._roll(BR0, 5)
    sim_b, sig_b = sim_for(base_gate, A, F, RG, BR)
    sim_c, sig_c = sim_for(cand_gate, A, F, RG, BR)
    base = pack(sim_b, sig_b, cal, base_gate, BR, BR5)
    cand = pack(sim_c, sig_c, cal, cand_gate, BR, BR5)

    kb = {(t['sym'], t['entry']): t for t in base['trades']}
    kc = {(t['sym'], t['entry']): t for t in cand['trades']}
    dropped = [kb[k] for k in kb if k not in kc]
    added = [kc[k] for k in kc if k not in kb]
    dropped.sort(key=lambda x: x['pnl'])
    added.sort(key=lambda x: x['pnl'])

    # current state under candidate gate
    last = n - 1
    br5 = float(BR5[last])
    state = dict(asof=cal[last], base_gate=bool(base_gate[last]), cand_gate=bool(cand_gate[last]),
                 breadth=round(float(BR[last]) * 100, 1), breadth5=round(br5 * 100, 1),
                 idx=round(float(idx[last]), 3), ma50=round(float(ma50[last]), 3),
                 gap=round(float(idx[last] / ma50[last] - 1) * 100, 2))

    out = dict(base=dict(st=base['st'], years=base['years'], rolling=base['rolling'],
                         y2026=base['y2026'], pf2026=base['pf2026'], n2026=base['n2026'],
                         gate_on=base['gate_on'], signals=base['signals']),
               cand=dict(st=cand['st'], years=cand['years'], rolling=cand['rolling'],
                         y2026=cand['y2026'], pf2026=cand['pf2026'], n2026=cand['n2026'],
                         gate_on=cand['gate_on'], signals=cand['signals']),
               rule='指数 > MA50 且 5 日平滑市场宽度 ≥ 45%（宽度=站上自身 MA50 的标的占比）',
               curve=dict(dates=weekly_curve(sim_c, cal)['dates'],
                          base=weekly_curve(sim_b, cal)['curve'],
                          cand=weekly_curve(sim_c, cal)['curve']),
               dropped=[{k: t[k] for k in ('sym', 'entry', 'exit', 'pnl', 'ret', 'why', 'bars', 'breadth', 'breadth5')} for t in dropped],
               added=[{k: t[k] for k in ('sym', 'entry', 'exit', 'pnl', 'ret', 'why', 'bars', 'breadth', 'breadth5')} for t in added],
               state=state, funding=funding_block(), factbook=factbook_block(), bases=bases_block())
    with open(os.path.join(HERE, 'v2_addendum.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print('base', base['st'], base['rolling'], base['y2026'], 'cand', cand['st'], cand['rolling'], cand['y2026'])
    print('dropped', len(dropped), [(t['sym'], t['entry'], t['pnl'], t['breadth']) for t in dropped])
    print('added', len(added), [(t['sym'], t['entry'], t['pnl'], t['breadth']) for t in added])
    print('state', state)
    print('funding', {k: v for k, v in out['funding'].items() if k not in ('series', 'top', 'bottom')})
    print('factbook', out['factbook']['counts'], out['factbook']['n_variants'], out['factbook']['release_eligible'])

    # merge into page payload
    with open(os.path.join(HERE, 'v2_page.json'), encoding='utf-8') as f:
        page = json.load(f)
    page['addendum'] = out
    with open(os.path.join(HERE, 'v2_page.json'), 'w', encoding='utf-8') as f:
        json.dump(page, f, ensure_ascii=False, indent=1, default=float)
    print('merged into v2_page.json')


if __name__ == '__main__':
    main()
