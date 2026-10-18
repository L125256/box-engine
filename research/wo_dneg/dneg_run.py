#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DNEG 主执行（D0→D1→D2→D3→D4）· R8 全程 Pool(32) 并行
判据全部照 /tmp/trade9_specs/DNEG_SPEC.md 冻结口径，一次成活，跑后不改。
输出 /tmp/dneg/d1..d4 json → 复制 /workspace/repo_ready/research/wo_dneg/。
"""
import json
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, '/tmp/dneg')
import dneg_engine as de

OUT = '/tmp/dneg'
D0 = json.load(open(f'{OUT}/d0_gate.json'))
assert D0['maxdiff_all_zero'], 'D0 未过 → 全线停'

# ---------------------------------------------------------------- 全局（fork 继承）
DATA = de.load_data()
POOLS = de.build_pools(DATA)
F = de.build_factors(DATA)

SEGS = {'realA': ('2025-06-02', '2026-03-31'),
        'holdout': ('2026-04-01', '2026-10-17'),
        'realB': ('2026-04-01', '2026-05-31'),
        'realC': ('2026-06-01', '2026-10-17')}

# R8 台账参照（v1 引擎口径，mdd_attribution.json 主 episode 2026-05-11→10-17 sym_pnl）
R8_REF = {'old131': {'INTWUSDT': -0.2802, 'MVLLUSDT': -0.1545, 'SOXLUSDT': -0.0925,
                     'AXTIUSDT': -0.0697, 'KLACUSDT': -0.0499},
          'full144': {'INTWUSDT': -0.2932, 'MVLLUSDT': -0.1682, 'SNXXUSDT': -0.1102,
                      'SOXLUSDT': -0.0838, 'AXTIUSDT': -0.0754}}


def ann_pct(curve, t0, t1):
    seg = curve[(curve.index >= pd.Timestamp(t0)) & (curve.index <= pd.Timestamp(t1))]
    yrs = (seg.index[-1] - seg.index[0]).days / 365.25
    return float(((seg.iloc[-1] / seg.iloc[0]) ** (1 / yrs) - 1) * 100), \
           float((seg.iloc[-1] / seg.iloc[0] - 1) * 100), float(yrs)


def seg_net_pp(curve, t0, t1):
    prev = curve[curve.index < pd.Timestamp(t0)]
    base = prev.iloc[-1] if len(prev) else curve.iloc[0]
    seg = curve[(curve.index >= pd.Timestamp(t0)) & (curve.index <= pd.Timestamp(t1))]
    return float((seg.iloc[-1] / base - 1) * 100)


# ================================================================ D1
def d1_worker(pname):
    syms = POOLS[pname]
    r = de.run_instr(DATA, F, syms, gated=False, factors=de.FACTORS_4, record=True)
    curve = r['curve']
    trades = pd.DataFrame(r['trades'].values())
    dd = pd.DataFrame(r['day_rows'], columns=['t', 'sym', 'tid', 'price', 'fee',
                                              'fund', 'event', 'gap'])
    dd['t'] = pd.to_datetime(dd['t'])
    return {'pool': pname,
            'curve': {str(k.date()): float(v) for k, v in curve.items()},
            'trades': trades.to_dict('records'),
            'day_rows': dd.to_dict('records')}


def decompose(res, t0, t1):
    """恒等式切片：①毛选票=Σprice ②交易费=Σfee ③资金费=Σfund；
    桶=窗口内有无平仓事件（stop/rebal/crash），无则 eow。"""
    dd = pd.DataFrame(res['day_rows'])
    dd['t'] = pd.to_datetime(dd['t'])
    m = (dd['t'] >= pd.Timestamp(t0)) & (dd['t'] <= pd.Timestamp(t1))
    w = dd[m]
    closed_in = set(w.loc[w['event'].notna() & w['event'].str.startswith('close:'), 'tid'])
    reason_of = w.loc[w['event'].notna() & w['event'].str.startswith('close:')] \
        .groupby('tid')['event'].first().str.replace('close:', '', regex=False).to_dict()
    w = w.copy()
    w['bucket'] = w['tid'].map(lambda x: reason_of.get(x, 'eow'))
    g = w.groupby('bucket')[['price', 'fee', 'fund']].sum()
    out = {}
    for b in ['stop', 'rebal', 'crash', 'eow']:
        if b in g.index:
            p, fe, fu = g.loc[b]
        else:
            p = fe = fu = 0.0
        out[b] = {'gross_pp': round(p * 100, 4), 'fee_pp': round(fe * 100, 4),
                  'funding_pp': round(fu * 100, 4), 'net_pp': round((p - fe + fu) * 100, 4)}
    tot = g.sum()
    ident = {'gross_ticket_pp': round(tot['price'] * 100, 4),
             'trade_fee_pp': round(tot['fee'] * 100, 4),
             'funding_pp': round(tot['fund'] * 100, 4)}
    ident['sum_pp'] = round(ident['gross_ticket_pp'] - ident['trade_fee_pp']
                            + ident['funding_pp'], 4)
    curve = pd.Series({pd.Timestamp(k): v for k, v in res['curve'].items()}).sort_index()
    prev = curve[curve.index < pd.Timestamp(t0)]
    base = prev.iloc[-1] if len(prev) else curve.iloc[0]
    seg_c = curve[(curve.index >= pd.Timestamp(t0)) & (curve.index <= pd.Timestamp(t1))]
    # 绝对 pp 口径（初始权益=1.0=100pp，与 R8 sym_pnl 可对账；逐日合计与曲线差=末日资金费时序）
    ident['curve_net_pp'] = round(float((seg_c.iloc[-1] - base) * 100), 4)
    ident['curve_net_rel_pct'] = round(float((seg_c.iloc[-1] / base - 1) * 100), 2)
    ident['funding_timing_adj_pp'] = round(ident['curve_net_pp'] - ident['sum_pp'], 4)
    ident['G1_abs_diff_pp'] = round(abs(ident['curve_net_pp'] - ident['sum_pp']), 4)
    ident['G1_pass_le_0.5pp'] = bool(ident['G1_abs_diff_pp'] <= 0.5)
    # 踏空⑥ 参考口径（不进闭合）：现金周池等权 + regret
    seg_c = curve[(curve.index >= pd.Timestamp(t0)) & (curve.index <= pd.Timestamp(t1))]
    wk = seg_c.resample('W').last().pct_change().dropna()
    cash_wk = wk[wk.round(10) == 0].index
    close = pd.DataFrame({s: DATA[s]['close'] for s in POOLS[res['pool']]})
    ew = close.pct_change().mean(axis=1)
    ewc = (1 + ew.fillna(0)).cumprod()
    ew_wk = ewc.resample('W').last().pct_change().dropna()
    cash_ew = sum(ew_wk.reindex(cash_wk).dropna()) * 100
    end_px = close.ffill().iloc[-1]
    regret = 0.0
    tr = pd.DataFrame(res['trades'])
    tr['close_date'] = pd.to_datetime(tr['close_date'])
    sel = tr[(tr['close_date'] >= pd.Timestamp(t0)) & (tr['close_date'] <= pd.Timestamp(t1))
             & (tr['exit_reason'] != 'eow')]
    for _, row in sel.iterrows():
        fwd = end_px[row['sym']] / row['exit_px'] - 1 if end_px[row['sym']] == end_px[row['sym']] else 0.0
        regret += row['qty'] * row['exit_px'] * fwd
    tr_all = pd.DataFrame(res['trades'])
    tr_all['close_date'] = pd.to_datetime(tr_all['close_date'])
    st = tr_all[(tr_all['exit_reason'] == 'stop') & (tr_all['close_date'] >= pd.Timestamp(t0))
                & (tr_all['close_date'] <= pd.Timestamp(t1))]
    ref4 = {'cash_week_pool_ew_pp': round(float(cash_ew), 4),
           'n_cash_weeks': int(len(cash_wk)),
           'regret_pp': round(regret * 100, 4),
           'miss_pp_total': round(float(cash_ew) + regret * 100, 4)}
    net = ident['curve_net_pp']
    four = {'fee_drag_pp': round(ident['trade_fee_pp'] + ident['funding_pp'], 4),
            'stop_grinder_pp': out['stop']['net_pp'],
            'ticket_quality_pp': round(out['rebal']['net_pp'] + out['crash']['net_pp']
                                       + out['eow']['net_pp'], 4)}
    four['miss_ref_pp'] = ref4['miss_pp_total']
    gsum = abs(four['fee_drag_pp']) + abs(four['stop_grinder_pp']) + abs(four['ticket_quality_pp'])
    four['share_denominator_note'] = '主口径=|分项|/Σ|三分项|；副口径=|分项|/|净损益|（净为正时副口径失真，仅存档）'
    for k in ['fee_drag_pp', 'stop_grinder_pp', 'ticket_quality_pp']:
        four[k + '_share_of_grosssum'] = round(abs(four[k]) / gsum * 100, 2) if gsum > 1e-9 else None
        four[k + '_share_of_net'] = round(four[k] / abs(net) * 100, 2) if abs(net) > 1e-9 else None
    return {'identity': ident, 'buckets': out, 'miss_reference': ref4,
            'four_way': four,
            'stop_gap_vs_intraday': {
                'gap_n': int((st['stop_type'] == 'gap').sum()),
                'intraday_n': int((st['stop_type'] == 'intraday').sum()),
                'gap_loss_pp': round(float(st['gap_loss'].sum() * 100), 4),
                'stop_n': int(len(st)),
                'stop_net_pp': out['stop']['net_pp']}}


def top_losers(res, t0, t1, n=20):
    tr = pd.DataFrame(res['trades'])
    tr['close_date'] = pd.to_datetime(tr['close_date'])
    sel = tr[(tr['close_date'] >= pd.Timestamp(t0)) & (tr['close_date'] <= pd.Timestamp(t1))].copy()
    sel['net_pp'] = ((sel['price_pnl'] - sel['entry_fee'] - sel['exit_fee'] + sel['funding']) * 100).round(4)
    sel = sel.sort_values('net_pp').head(n)
    cols = ['sym', 'open_date', 'close_date', 'open_px', 'stop_px', 'gap_loss',
            'exit_reason', 'stop_type', 'realized_pp', 'allocated_fees']
    sel['realized_pp'] = sel['net_pp']
    sel['allocated_fees'] = (sel['entry_fee'] + sel['exit_fee'] - sel['funding']).round(6)
    sel['close_date'] = sel['close_date'].dt.strftime('%Y-%m-%d')
    recs = sel[cols].to_dict('records')
    for rrec in recs:
        for k, v in rrec.items():
            if isinstance(v, float) and (v != v):
                rrec[k] = None
    return recs


def r8_recon(res):
    dd = pd.DataFrame(res['day_rows'])
    dd['t'] = pd.to_datetime(dd['t'])
    w = dd[(dd['t'] > pd.Timestamp('2026-05-11')) & (dd['t'] <= pd.Timestamp('2026-10-17'))]
    by = (w.groupby('sym')[['price', 'fee', 'fund']].sum()
          .assign(net=lambda x: (x['price'] - x['fee'] + x['fund']) * 100)['net']
          .sort_values().round(4))
    ref = {s: round(v * 100, 2) for s, v in R8_REF[res['pool']].items()}
    recon = {s: {'dneg_pp': round(float(by.get(s, 0.0)), 4), 'r8_v1_pp': v,
                 'diff_pp': round(float(by.get(s, 0.0)) - v, 4)} for s, v in ref.items()}
    recon['_note'] = 'R8 台账为 v1 引擎（无 BUG-04 口径），|diff|≤0.35pp 即对账成立'
    return recon, by.head(10).to_dict()


def run_d1():
    with Pool(32) as p:
        results = p.map(d1_worker, list(POOLS))
    out = {'meta': {'identity': '后段净=①毛选票+②交易费+③资金费；①=④止损+⑤非止损(rebal/crash/eow)；⑥踏空单列不进闭合',
                    'units': 'pp 相对初始权益=100pp（绝对口径，与 R8 sym_pnl 可对账）',
                    'G1': '分项合计 vs 曲线 ≤0.5pp（累计口径，双池×后段）'},
           'pools': {}}
    ledger = []
    for res in results:
        pname = res['pool']
        segs = {name: decompose(res, t0, t1) for name, (t0, t1) in SEGS.items()}
        losers = top_losers(res, *SEGS['holdout'])
        recon, top10_syms = r8_recon(res)
        out['pools'][pname] = {'curve': res['curve'], 'segments': segs,
                               'top20_losers_holdout': losers,
                               'r8_recon_main_episode': recon,
                               'worst10_sym_holdout': top10_syms}
        tr = pd.DataFrame(res['trades'])
        tr['pool'] = pname
        ledger.append(tr)
        # 落 CSV
        trc = tr.copy()
        trc['net_pp'] = ((trc['price_pnl'] - trc['entry_fee'] - trc['exit_fee'] + trc['funding']) * 100).round(4)
        trc['allocated_fees'] = (trc['entry_fee'] + trc['exit_fee'] - trc['funding']).round(6)
        cols = ['pool', 'sym', 'open_date', 'close_date', 'open_px', 'stop_px', 'gap_loss',
                'exit_reason', 'stop_type', 'net_pp', 'allocated_fees', 'qty', 'exit_px',
                'entry_fee', 'exit_fee', 'funding', 'price_pnl']
        trc[cols].sort_values(['close_date', 'sym']).to_csv(
            f'{OUT}/trade_ledger_{pname}.csv', index=False)
    allseg = {p: {s: out['pools'][p]['segments'][s]['identity']['G1_pass_le_0.5pp']
                  for s in SEGS} for p in POOLS}
    out['G1_all_pass'] = {p: bool(all(v.values())) for p, v in allseg.items()}
    json.dump(out, open(f'{OUT}/d1_attribution.json', 'w'), ensure_ascii=False, indent=1)
    print('D1 done. G1:', out['G1_all_pass'])
    for p in POOLS:
        fw = out['pools'][p]['segments']['holdout']['four_way']
        print(f"  {p} 后段四分项: 费拖累{fw['fee_drag_pp']}pp(占Σ|.| {fw['fee_drag_pp_share_of_grosssum']}%) "
              f"止损{fw['stop_grinder_pp']}pp(占Σ|.| {fw['stop_grinder_pp_share_of_grosssum']}%) "
              f"选票{fw['ticket_quality_pp']}pp(占Σ|.| {fw['ticket_quality_pp_share_of_grosssum']}%) "
              f"踏空参考{fw['miss_ref_pp']}pp")
    return out


# ================================================================ D2
def weekly_sig_days(syms):
    close = pd.DataFrame({s: DATA[s]['close'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(DATA[s].index) for s in syms])))
    iso = cal.isocalendar()
    sig = cal.to_series().groupby([iso['year'].values, iso['week'].values]).first()
    return cal, close, sorted(d for d in sig if d >= de.REALA_START
                              and cal.get_loc(d) + 5 < len(cal))


def spear(a, b):
    m = a.notna() & b.notna()
    if m.sum() < 5:
        return np.nan
    ra, rb = a[m].rank(), b[m].rank()
    return float(np.corrcoef(ra, rb)[0, 1])


def compute_ic(pname):
    syms = POOLS[pname]
    cal, close, sig = weekly_sig_days(syms)
    pos = {d: i for i, d in enumerate(cal)}
    ic = {f: [] for f in de.FACTORS_4}
    spread = []
    dates = []
    for t in sig:
        i = pos[t]
        fwd = close.iloc[i + 5] / close.iloc[i] - 1
        for f in de.FACTORS_4:
            fv = pd.Series({s: (F[s].loc[t, f] if t in F[s].index else np.nan) for s in syms})
            ic[f].append(spear(fv, fwd))
        sc = de.cross_scores(F, syms, t, de.FACTORS_4)
        if len(sc) >= de.TOP_N:
            top5 = list(sc.index[:5])
            spread.append(float(fwd[top5].mean() - fwd[sc.index].mean()))
        else:
            spread.append(np.nan)
        dates.append(t)
    return pd.DataFrame(ic, index=pd.DatetimeIndex(dates)), \
        pd.Series(spread, index=pd.DatetimeIndex(dates))


def stat_boot(x, n_boot=1000, mean_block=10, seed=42):
    rng = np.random.default_rng(seed)
    x = np.asarray([v for v in x if not np.isnan(v)], float)
    n = len(x)
    if n < 5:
        return None
    means = np.empty(n_boot)
    for b in range(n_boot):
        idx = []
        while len(idx) < n:
            start = rng.integers(0, n)
            L = rng.geometric(1.0 / mean_block)
            idx.extend((start + np.arange(L)) % n)
        means[b] = x[np.array(idx[:n])].mean()
    return {'mean': round(float(x.mean()), 4),
            'icir': round(float(x.mean() / x.std(ddof=1)), 4) if n > 2 else None,
            'n_days': n,
            'ci_low': round(float(np.percentile(means, 2.5)), 4),
            'ci_high': round(float(np.percentile(means, 97.5)), 4)}


def d2_boot_task(args):
    pname, factor, segname = args
    ics = ICS[pname][0][factor]
    t0, t1 = SEGS[segname]
    sub = ics[(ics.index >= pd.Timestamp(t0)) & (ics.index <= pd.Timestamp(t1))].dropna()
    r = stat_boot(sub.values)
    return (pname, factor, segname, r)


ICS = {}


def run_d2():
    global ICS
    ICS = {p: compute_ic(p) for p in POOLS}
    tasks = [(p, f, s) for p in POOLS for f in de.FACTORS_4 for s in SEGS]
    with Pool(32) as pool:
        res = pool.map(d2_boot_task, tasks)
    table = {}
    for pname, factor, segname, r in res:
        table.setdefault(pname, {}).setdefault(factor, {})[segname] = r
    # top5-EW 辅证（分段均值，realB/realC 分开）
    aux = {}
    for p in POOLS:
        sp = ICS[p][1]
        aux[p] = {s: round(float(sp[(sp.index >= pd.Timestamp(t0)) & (sp.index <= pd.Timestamp(t1))]
                                   .mean()) * 100, 4) for s, (t0, t1) in SEGS.items()}
    # 三档判定（冻结）：dead: 前段IC>=+0.03 且 后段IC<=0；alive: 同号且|后段|>=0.5|前段|；
    # 死/活须对应 CI 不跨 0（dead 要求前段CI下界>0且后段CI上界<0；alive 要求后段CI不跨0）
    verdict = {}
    for p in POOLS:
        verdict[p] = {}
        for f in de.FACTORS_4:
            a = table[p][f]['realA']
            h = table[p][f]['holdout']
            dead_raw = a['mean'] >= 0.03 and h['mean'] <= 0
            alive_raw = (a['mean'] * h['mean'] > 0) and abs(h['mean']) >= 0.5 * abs(a['mean'])
            ci_a_pos = a['ci_low'] > 0
            ci_h_neg = h['ci_high'] < 0
            ci_h_excl0 = h['ci_low'] > 0 or h['ci_high'] < 0
            if dead_raw and ci_a_pos and ci_h_neg:
                v = 'dead'
            elif alive_raw and ci_h_excl0:
                v = 'alive'
            else:
                v = 'pending'
            verdict[p][f] = {'verdict': v, 'raw_dead': bool(dead_raw),
                             'raw_alive': bool(alive_raw),
                             'ci_note': 'dead需前段CI>0且后段CI<0；alive需后段CI不跨0（开工注记，冻结）'}
    out = {'meta': {'method': '信号日(每周首个交易日)横截面 Spearman rank IC vs 前向5交易日收益；'
                            '日块 stationary bootstrap(平均块长10) 1000次 CI，seed=42',
                    'criteria_frozen': 'dead: 前段IC>=+0.03且后段IC<=0；alive: 同号且|后段|>=0.5|前段|；'
                                       '其余待定（只报CI）；死/活须CI不跨0',
                    'segments': 'realA/后段 强制两层，realB/realC 分开报'},
           'ic_table': table, 'verdict': verdict, 'top5_minus_ew_spread_pp': aux}
    json.dump(out, open(f'{OUT}/d2_factors.json', 'w'), ensure_ascii=False, indent=1)
    for p in POOLS:
        for f in de.FACTORS_4:
            a, h = table[p][f]['realA'], table[p][f]['holdout']
            print(f"D2 {p:8s} {f:14s} realA IC={a['mean']:+.4f} CI[{a['ci_low']},"
                  f"{a['ci_high']}] 后段 IC={h['mean']:+.4f} CI[{h['ci_low']},{h['ci_high']}] "
                  f"→ {verdict[p][f]['verdict']}")
    return out


# ================================================================ D3
def rand_target(rng, syms):
    idx = sorted(rng.choice(len(syms), size=de.TOP_N, replace=False).tolist())
    return [syms[i] for i in idx]


def d3_worker(args):
    pname, seed = args
    r = de.run_instr(DATA, None, POOLS[pname], gated=False, target_fn=rand_target,
                     rng_seed=seed)
    ho = ann_pct(r['curve'], *SEGS['holdout'])
    rc = ann_pct(r['curve'], *SEGS['realC'])
    return {'pool': pname, 'seed': seed, 'holdout_ann': round(ho[0], 2),
            'holdout_total': round(ho[1], 2), 'realC_ann': round(rc[0], 2),
            'realC_total': round(rc[1], 2)}


def ew_arm(pname):
    close = pd.DataFrame({s: DATA[s]['close'] for s in POOLS[pname]})
    ew = close.pct_change().mean(axis=1)
    curve = (1 + ew.fillna(0)).cumprod()
    out = {}
    for s, (t0, t1) in SEGS.items():
        a, tot, yrs = ann_pct(curve, t0, t1)
        seg = curve[(curve.index >= pd.Timestamp(t0)) & (curve.index <= pd.Timestamp(t1))]
        out[s] = {'annualized_pct': round(a, 2), 'total_return_pct': round(tot, 2),
                  'mdd_pct': round(float(((seg / seg.cummax()) - 1).min()) * 100, 2)}
    monthly = curve[(curve.index >= pd.Timestamp(SEGS['holdout'][0]))].resample('ME').last().pct_change().dropna()
    out['holdout_monthly_pct'] = {str(k.date()): round(float(v) * 100, 2) for k, v in monthly.items()}
    return out


def run_d3(d1out):
    # F1 base（seed=42, ungated v2）后段定位：BASE_CURVES 由 main 注入
    tasks = [(p, seed) for p in POOLS for seed in range(42, 542)]
    with Pool(32) as pool:
        res = pool.map(d3_worker, tasks, chunksize=8)
    band = {}
    for p in POOLS:
        arr = np.array([r['holdout_ann'] for r in res if r['pool'] == p])
        arrc = np.array([r['realC_ann'] for r in res if r['pool'] == p])
        ho_ann, ho_tot, _ = ann_pct(
            pd.Series({pd.Timestamp(k): v for k, v in d1['pools'][p].get('curve', {}).items()}).sort_index()
            if False else BASE_CURVES[p], *SEGS['holdout'])
        rc_ann, rc_tot, _ = ann_pct(BASE_CURVES[p], *SEGS['realC'])
        band[p] = {'n_runs': int(len(arr)),
                   'holdout_ann_percentiles': {q: round(float(np.percentile(arr, q)), 2)
                                               for q in [5, 25, 50, 75, 95]},
                   'realC_ann_percentiles': {q: round(float(np.percentile(arrc, q)), 2)
                                             for q in [5, 25, 50, 75, 95]},
                   'f1_holdout_ann': round(ho_ann, 2), 'f1_holdout_total_pp': round(ho_tot, 2),
                   'f1_realC_ann': round(rc_ann, 2), 'f1_realC_total_pp': round(rc_tot, 2)}
        v = band[p]['f1_holdout_ann']
        pct = band[p]['holdout_ann_percentiles']
        if v < pct[5]:
            verdict = 'strategy_specific（<p5 策略特有深负坐实）'
        elif v <= pct[75]:
            verdict = ('market_wide（p25~p75 池底色同亏·定性翻案）' if v >= pct[25]
                       else 'below_p25（p5~p25 之间，介于两档——按规格非策略特有非池底色，报待定带）')
        else:
            verdict = 'above_p75（>p75 深负不成立，复查口径）'
        band[p]['verdict_holdout'] = verdict
    arm1 = {p: ew_arm(p) for p in POOLS}
    out = {'meta': {'arm2': '同引擎同费(ungated base 口径)、目标名单=池内随机5票，seeds=42..541(500)×双池',
                    'criteria_frozen': '后段F1净年化<随机带p5→策略特有；p25~p75→池底色同亏；>p75→复查口径',
                    'burn_note': '随机带1000 run 为诊断分布，非上线判据窗'},
           'arm1_pool_ew': arm1, 'arm2_random_band': band,
           'arm1_f1_base': {p: {'holdout': dict(zip(['annualized_pct', 'total_return_pct', 'yrs'],
                                                    [round(x, 2) for x in ann_pct(BASE_CURVES[p], *SEGS['holdout'])])),
                                'realA': dict(zip(['annualized_pct', 'total_return_pct', 'yrs'],
                                                  [round(x, 2) for x in ann_pct(BASE_CURVES[p], *SEGS['realA'])]))}
                            for p in POOLS}}
    json.dump(out, open(f'{OUT}/d3_regime.json', 'w'), ensure_ascii=False, indent=1)
    for p in POOLS:
        b = band[p]
        print(f"D3 {p}: F1后段年化={b['f1_holdout_ann']}% vs 随机带 p5={b['holdout_ann_percentiles'][5]} "
              f"p25={b['holdout_ann_percentiles'][25]} p50={b['holdout_ann_percentiles'][50]} "
              f"p75={b['holdout_ann_percentiles'][75]} p95={b['holdout_ann_percentiles'][95]} → {b['verdict_holdout']}")
    return out


# ================================================================ D4
def d4_worker(args):
    kind, pname, param = args
    if kind == 'factors':
        r = de.run_instr(DATA, F, POOLS[pname], gated=False, factors=param, record=True)
    elif kind == 'biweekly':
        r = de.run_instr(DATA, F, POOLS[pname], gated=False, factors=de.FACTORS_4,
                         rebal_every_weeks=2, record=True)
    elif kind == 'nostop':
        r = de.run_instr(DATA, F, POOLS[pname], gated=False, factors=de.FACTORS_4,
                         stop=None, record=True)
    elif kind == 'stop12':
        r = de.run_instr(DATA, F, POOLS[pname], gated=False, factors=de.FACTORS_4,
                         stop=-0.12, record=True)
    elif kind == 'trail12':
        r = de.run_instr(DATA, F, POOLS[pname], gated=False, factors=de.FACTORS_4,
                         trail=0.12, record=True)
    ho = ann_pct(r['curve'], *SEGS['holdout'])
    ra = ann_pct(r['curve'], *SEGS['realA'])
    rc = ann_pct(r['curve'], *SEGS['realC'])
    # 后段费拖累切片（费拖累=交易费+资金费，年化）
    dd = pd.DataFrame(r['day_rows'], columns=['t', 'sym', 'tid', 'price', 'fee',
                                              'fund', 'event', 'gap'])
    dd['t'] = pd.to_datetime(dd['t'])
    m = (dd['t'] >= pd.Timestamp(SEGS['holdout'][0])) & (dd['t'] <= pd.Timestamp(SEGS['holdout'][1]))
    fee_drag_ho_ann = float((dd.loc[m, 'fee'].sum() - dd.loc[m, 'fund'].sum()) / ho[2] * 100)
    return {'kind': kind, 'pool': pname, 'param': str(param),
            'holdout_ann': round(ho[0], 2), 'holdout_total_pp': round(ho[1], 2),
            'holdout_fee_drag_ann_pp': round(fee_drag_ho_ann, 2),
            'realA_ann': round(ra[0], 2), 'realC_ann': round(rc[0], 2),
            'realC_total_pp': round(rc[1], 2)}


BASE_CURVES = {}


def run_d4(d1out, d2out, d3out):
    # 触发判定
    verdicts = {p: [d2out['verdict'][p][f]['verdict'] for f in de.FACTORS_4] for p in POOLS}
    n_dead = sum(v.count('dead') for v in verdicts.values())
    n_alive = sum(v.count('alive') for v in verdicts.values())
    trigA = n_dead >= 1 and n_alive >= 1
    fw = {p: d1out['pools'][p]['segments']['holdout']['four_way'] for p in POOLS}
    trigB = any((fw[p]['fee_drag_pp_share_of_grosssum'] or 0) >= 30 for p in POOLS)
    trigC = any((fw[p]['stop_grinder_pp_share_of_grosssum'] or 0) >= 30 for p in POOLS)
    trigD = all('strategy_specific' in d3out['arm2_random_band'][p]['verdict_holdout'] for p in POOLS)
    dead_factors = sorted({f for p in POOLS for f in de.FACTORS_4
                           if d2out['verdict'][p][f]['verdict'] == 'dead'})
    alive_factors = sorted({f for p in POOLS for f in de.FACTORS_4
                            if d2out['verdict'][p][f]['verdict'] == 'alive'})
    keep = [f for f in de.FACTORS_4 if f not in dead_factors] if dead_factors else de.FACTORS_4
    tasks = []
    if trigA:
        tasks += [('factors', p, keep) for p in POOLS]
    if trigB:
        tasks += [('biweekly', p, 2) for p in POOLS]
    if trigC:
        tasks += [('nostop', p, None) for p in POOLS] + \
                 [('stop12', p, -0.12) for p in POOLS] + \
                 [('trail12', p, 0.12) for p in POOLS]
    with Pool(32) as pool:
        res = pool.map(d4_worker, tasks) if tasks else []
    by = {(r['kind'], r['pool']): r for r in res}
    out = {'meta': {'triggers_frozen': 'H-A: D2判死>=1且判活>=1；H-B: 费拖累后段占比>=30%；'
                            'H-C: 止损绞肉占比>=30%；H-D: D3判策略特有',
                    'burn_ledger': '反事实参数跑过即烧窗，不得复用为上线判据窗',
                    'HD_preregistered': 'T2=池等权20日已实现波动率（开工冻结）；阈值=realA 80分位；'
                                        'OFF=vol20>阈值；命中率=后段OFF日中F1净日收益<0占比>=80%；'
                                        '误伤=realA OFF日占比<=20%'},
           'triggers': {'H_A_swap_factor': bool(trigA), 'H_B_lower_frequency': bool(trigB),
                        'H_C_stop_structure': bool(trigC), 'H_D_state_gate': bool(trigD)},
           'dead_factors': dead_factors, 'alive_factors': alive_factors, 'runs': res}
    # H-A 判据：去死因子版 净年化>=准入线60%（realA 主判，RWR 制度内）且真实窗 IC 方向为正
    if trigA:
        ha = {}
        for p in POOLS:
            r = by[('factors', p)]
            ic_pos = all(d2out['ic_table'][p][f]['realA']['mean'] > 0 for f in keep)
            ha[p] = {'kept_factors': keep, 'realA_ann': r['realA_ann'],
                     'holdout_ann': r['holdout_ann'], 'realC_ann': r['realC_ann'],
                     'realA_ge_60': bool(r['realA_ann'] >= 60), 'realA_ic_positive': bool(ic_pos),
                     'pass': bool(r['realA_ann'] >= 60 and ic_pos)}
        out['H_A_verdict'] = ha
    # H-B 判据：后段费拖累年化降幅>=5pp 且净年化不降
    if trigB:
        hb = {}
        for p in POOLS:
            r = by[('biweekly', p)]
            hb[p] = {'biweekly_holdout_ann': r['holdout_ann'],
                     'biweekly_fee_drag_ann_pp': r['holdout_fee_drag_ann_pp'],
                     'base_holdout_ann': round(ann_pct(BASE_CURVES[p], *SEGS['holdout'])[0], 2)}
            # base 后段费拖累年化 = 累计pp / 年数
            yrs = ann_pct(BASE_CURVES[p], *SEGS['holdout'])[2]
            hb[p]['base_fee_drag_ann_pp'] = round(fw[p]['fee_drag_pp'] / yrs, 2)
            hb[p]['fee_drag_ann_drop_pp'] = round(hb[p]['base_fee_drag_ann_pp']
                                                  - r['holdout_fee_drag_ann_pp'], 2)
            hb[p]['fee_drop_ge5pp'] = bool(hb[p]['fee_drag_ann_drop_pp'] >= 5)
            hb[p]['ann_not_lower'] = bool(hb[p]['biweekly_holdout_ann'] >= hb[p]['base_holdout_ann'])
            hb[p]['pass'] = bool(hb[p]['fee_drop_ge5pp'] and hb[p]['ann_not_lower'])
        out['H_B_verdict'] = hb
    # H-C 判据：无止损臂后段净改善>=10pp（累计口径）
    if trigC:
        hc = {}
        for p in POOLS:
            b_tot = ann_pct(BASE_CURVES[p], *SEGS['holdout'])[1]
            ns = by[('nostop', p)]
            s12 = by[('stop12', p)]
            tl = by[('trail12', p)]
            hc[p] = {'base_total_pp': round(b_tot, 2),
                     'nostop_total_pp': ns['holdout_total_pp'],
                     'stop12_total_pp': s12['holdout_total_pp'],
                     'trail12_total_pp': tl['holdout_total_pp'],
                     'nostop_improve_pp': round(ns['holdout_total_pp'] - b_tot, 2),
                     'nostop_improve_ge10pp': bool(ns['holdout_total_pp'] - b_tot >= 10),
                     'nostop_realC_total_pp': ns['realC_total_pp']}
        out['H_C_verdict'] = hc
    # H-D：T2 状态门诊断（无新引擎跑，曲线叠加）
    if trigD:
        hd = {}
        for p in POOLS:
            close = pd.DataFrame({s: DATA[s]['close'] for s in POOLS[p]})
            ew = close.pct_change().mean(axis=1)
            vol20 = ew.rolling(20).std()
            thr = float(vol20[(vol20.index >= pd.Timestamp(SEGS['realA'][0])) &
                              (vol20.index <= pd.Timestamp(SEGS['realA'][1]))].quantile(0.80))
            curve = BASE_CURVES[p]
            ret = curve.pct_change()
            off = vol20 > thr
            ho_m = (off.index >= pd.Timestamp(SEGS['holdout'][0]))
            ra_m = (off.index >= pd.Timestamp(SEGS['realA'][0])) & (off.index <= pd.Timestamp(SEGS['realA'][1]))
            off_ho = off[ho_m] & ret[ho_m].notna()
            hit = float((ret[ho_m][off_ho] < 0).mean()) if off_ho.sum() else np.nan
            off_ra = off[ra_m] & ret[ra_m].notna()
            hurt = float(off_ra.mean())
            hd[p] = {'vol_threshold_realA_p80': round(thr, 6),
                     'holdout_off_days': int(off_ho.sum()),
                     'holdout_hit_rate': round(hit, 4) if hit == hit else None,
                     'hit_rate_ge_80': bool(hit >= 0.8) if hit == hit else False,
                     'realA_off_share': round(hurt, 4),
                     'hurt_le_20': bool(hurt <= 0.2),
                     'pass': bool((hit >= 0.8) if hit == hit else False and hurt <= 0.2)}
        out['H_D_verdict'] = hd
    json.dump(out, open(f'{OUT}/d4_actions.json', 'w'), ensure_ascii=False, indent=1)
    print('D4 triggers:', out['triggers'])
    return out


# ================================================================ main
def main():
    global BASE_CURVES
    d1 = run_d1()
    for p in POOLS:
        BASE_CURVES[p] = pd.Series({pd.Timestamp(k): v for k, v in d1['pools'][p]['curve'].items()}).sort_index()
    d2 = run_d2()
    d3 = run_d3(d1)
    d4 = run_d4(d1, d2, d3)
    json.dump({'spec': 'DNEG 冻结规格', 'seed': 42,
               'd0': D0, 'd1_G1': d1['G1_all_pass'],
               'triggers': d4['triggers']}, open(f'{OUT}/dneg_results.json', 'w'),
              ensure_ascii=False, indent=1)
    print('ALL DONE → /tmp/dneg/dneg_results.json')


if __name__ == '__main__':
    main()
