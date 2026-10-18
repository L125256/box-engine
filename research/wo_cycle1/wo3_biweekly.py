#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WO3 双周档最后一枪（R12 · 冻结规格 v1.0 · 一次成活 · seed=42）
对照：双周（每 2 ISO 周首个交易日收盘出信号，次日开盘成交）vs 周（base ungated 权威形态）。
引擎：逐字复用 /tmp/r9/r9_final.py 的仪表化 ungated 引擎 run_instr（rebal_weeks 参数化，
源头 /tmp/eng_w2_f1/f1_backtest.py，R9 已做 T1 三账同源 diff=0 校验；本单复验一次）。
双池 old131/full144 × 数据出身分段（合成训练窗 / 合成留出段 2026-04~05 / 真实窗 >=2026-06）
× 八列（年化/累计/MDD/周胜率/周中位/换手/交易费/资金费）。
对称判据（冻结）：N = Δ费拖累(pp/年,省为负) + Δ年化(pp/年,少赚为负)，双周−周口径；
真实窗双池 N>=0 且 Δ费<0 零例外；MDD 劣化 <=1pp（真实窗）；
任一池真实窗 N<0 → 不对称 → F1 变体线连同关闭，无复活。
walk-forward：滚动 60 交易日窗逐窗 N；通过=双池各自 N>0 窗占比 >=70%，
且真实窗段内无连续 3 窗 N<−2pp。留出合成段仅 0.164 年，只看总收益不看年化。
复现：python3 wo3_biweekly.py
"""
import json
import os
import sys
import datetime

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
sys.path.insert(0, '/workspace/repo_ready/research/wo_cycle1')
sys.path.insert(0, '/tmp/eng_w2_f1')
from eng_f1_instr import run_instr, REAL_START   # noqa: E402
from f1_backtest import (load_data, build_pools, build_factors,   # noqa: E402
                         run_backtest, FACTORS_4, TRAIN_END, HOLD_START, SEED)

np.random.seed(SEED)
OUT = '/workspace/repo_ready/research/wo_cycle1'
WF_DAYS = 60          # walk-forward 滚动窗（交易日）
WF_LINE = -2.0        # 连续 3 窗 N<−2pp 红线
WF_SHARE = 0.70       # N>0 窗占比判据
MDD_TOL = 1.0         # MDD 劣化容忍（pp，真实窗）


def weekly_median(curve, t0, t1):
    seg = curve[(curve.index >= t0) & (curve.index <= t1)]
    if len(seg) < 2:
        return None
    wk = seg.resample('W').last().pct_change().dropna()
    return round(float(wk.median()) * 100, 3) if len(wk) else None


def eight_cols(res, t0, t1):
    """八列：年化/累计/MDD/周胜率/周中位/换手/交易费/资金费（年化口径，pp 与 x 分列）。"""
    curve = res['curve']
    seg = curve[(curve.index >= t0) & (curve.index <= t1)]
    if len(seg) < 2:
        return {}
    yrs = (seg.index[-1] - seg.index[0]).days / 365.25
    ann = (seg.iloc[-1] / seg.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1
    wk = seg.resample('W').last().pct_change().dropna()
    dd = (seg / seg.cummax() - 1).min()
    led = pd.DataFrame(res['fee_ledger'])
    led['date'] = pd.to_datetime(led['date'])
    led = led[(led['date'] >= t0) & (led['date'] <= t1)]
    fund = pd.Series(res['funding_by_day'], dtype=float)
    fund.index = pd.to_datetime(fund.index)
    fund = fund[(fund.index >= t0) & (fund.index <= t1)]
    trade_cum = float(led['fee'].sum())
    fund_cum = float(fund.sum())
    return {
        'annualized_pct': round(ann * 100, 2),
        'total_return_pct': round((seg.iloc[-1] / seg.iloc[0] - 1) * 100, 2),
        'mdd_pct': round(dd * 100, 2),
        'weekly_winrate_pct': round((wk > 0).mean() * 100, 2) if len(wk) else None,
        'median_weekly_pct': round(float(wk.median()) * 100, 3) if len(wk) else None,
        'turnover_ann_x': round(float(led['notional'].sum()) / yrs, 2),
        'trade_fee_ann_pp': round(trade_cum / yrs * 100, 2),
        'funding_ann_pp': round(fund_cum / yrs * 100, 2),
        'fee_total_ann_pp': round((trade_cum + fund_cum) / yrs * 100, 2),
        'yrs': round(yrs, 4), 'n_days': int(len(seg)),
    }


def walk_forward(res_w, res_b):
    """滚动 60 交易日窗逐窗 N = Δ费拖累(pp/年) + Δ年化(pp/年)，双周−周口径。"""
    cw, cb = res_w['curve'], res_b['curve']
    assert (cw.index == cb.index).all()
    n = len(cw)
    led_w = pd.DataFrame(res_w['fee_ledger']); led_w['date'] = pd.to_datetime(led_w['date'])
    led_b = pd.DataFrame(res_b['fee_ledger']); led_b['date'] = pd.to_datetime(led_b['date'])
    fund_w = pd.Series(res_w['funding_by_day'], dtype=float)
    fund_w.index = pd.to_datetime(fund_w.index)
    fund_b = pd.Series(res_b['funding_by_day'], dtype=float)
    fund_b.index = pd.to_datetime(fund_b.index)
    fee_w_d = (led_w.groupby('date')['fee'].sum().reindex(cw.index).fillna(0.0)
               + fund_w.reindex(cw.index).fillna(0.0))
    fee_b_d = (led_b.groupby('date')['fee'].sum().reindex(cw.index).fillna(0.0)
               + fund_b.reindex(cw.index).fillna(0.0))
    cum_w = fee_w_d.cumsum(); cum_b = fee_b_d.cumsum()
    rows = []
    for i in range(n - WF_DAYS):
        t0, t1 = cw.index[i], cw.index[i + WF_DAYS - 1]
        yrs = (t1 - t0).days / 365.25
        if yrs <= 0:
            continue
        ann_w = (cw.iloc[i + WF_DAYS - 1] / cw.iloc[i]) ** (1 / yrs) - 1
        ann_b = (cb.iloc[i + WF_DAYS - 1] / cb.iloc[i]) ** (1 / yrs) - 1
        fee_w = (float(cum_w.iloc[i + WF_DAYS - 1] - (cum_w.iloc[i - 1] if i else 0.0))
                 / yrs * 100)
        fee_b = (float(cum_b.iloc[i + WF_DAYS - 1] - (cum_b.iloc[i - 1] if i else 0.0))
                 / yrs * 100)
        n_val = (fee_b - fee_w) + (ann_b - ann_w) * 100
        rows.append({'i': i, 'start': str(t0.date()), 'end': str(t1.date()),
                     'd_fee_pp': round(fee_b - fee_w, 3),
                     'd_ann_pp': round((ann_b - ann_w) * 100, 3),
                     'N_pp': round(n_val, 3),
                     'in_real': bool(t0 >= REAL_START)})
    df = pd.DataFrame(rows)
    def consec_neg2(sub):
        mx = cur = 0
        for v in sub['N_pp']:
            cur = cur + 1 if v < WF_LINE else 0
            mx = max(mx, cur)
        return mx
    real = df[df['in_real']]
    return {
        'n_windows': int(len(df)),
        'share_N_gt0_all': round(float((df['N_pp'] > 0).mean()), 4),
        'n_windows_real': int(len(real)),
        'share_N_gt0_real': round(float((real['N_pp'] > 0).mean()), 4) if len(real) else None,
        'max_consec_N_lt_-2pp_real': int(consec_neg2(real)) if len(real) else None,
        'windows': rows,
    }


def main():
    data = load_data()
    pools = build_pools(data)
    F = build_factors(data)
    print(f"池: old131={len(pools['old131'])}, full144={len(pools['full144'])}")

    runs, t1v = {}, {}
    for pname, syms in pools.items():
        runs[pname] = {}
        for tag, rw in (('weekly', 1), ('biweekly', 2)):
            runs[pname][tag] = run_instr(data, F, syms, rebal_weeks=rw)
            print(f"[{pname}/{tag}] fees={runs[pname][tag]['fees']:.6f} "
                  f"events={len(runs[pname][tag]['events'])}")
        ref = run_backtest(data, F, syms, gated=False, factors=FACTORS_4)
        d = (runs[pname]['weekly']['curve'] - ref['curve']).abs().max()
        t1v[pname] = dict(curve_max_abs_diff=float(d),
                          fees_abs_diff=abs(runs[pname]['weekly']['fees'] - ref['fees']),
                          diff_zero=bool(d == 0.0))
        print(f"[{pname}] T1 同源复验: curve max|diff|={d}")

    end = pd.Timestamp(runs['old131']['weekly']['end'])
    segs = [
        ('train', pd.Timestamp(runs['old131']['weekly']['start']), TRAIN_END, '合成'),
        ('holdout_synth_0405', HOLD_START, REAL_START - pd.Timedelta(days=1), '合成'),
        ('real', REAL_START, end, '真实'),
    ]

    table, per_pool = [], {}
    for pname in pools:
        per_pool[pname] = {}
        for wname, t0, t1, origin in segs:
            t1_eff = min(t1, end)
            mw = eight_cols(runs[pname]['weekly'], t0, t1_eff)
            mb = eight_cols(runs[pname]['biweekly'], t0, t1_eff)
            d_fee = round(mb['fee_total_ann_pp'] - mw['fee_total_ann_pp'], 2)
            d_ann = round(mb['annualized_pct'] - mw['annualized_pct'], 2)
            d_mdd = round(mb['mdd_pct'] - mw['mdd_pct'], 2)
            N = round(d_fee + d_ann, 2)
            per_pool[pname][wname] = dict(
                origin=origin, weekly=mw, biweekly=mb,
                delta_bi_minus_weekly=dict(fee_ann_pp=d_fee, annualized_pp=d_ann,
                                           mdd_pp=d_mdd, N_pp=N))
            for variant, m in (('weekly', mw), ('biweekly', mb)):
                table.append({'pool': pname, 'variant': variant, 'win': wname,
                              'origin': origin, **m})
            print(f"[{pname}/{wname}|{origin}] 周年化{mw['annualized_pct']} 双周年化"
                  f"{mb['annualized_pct']} Δ费{d_fee} Δ年化{d_ann} N={N} "
                  f"ΔMDD{d_mdd} (周{mw['mdd_pct']}/双周{mb['mdd_pct']})")

    # 对称判据（真实窗，冻结）
    sym = {}
    for pname in pools:
        r = per_pool[pname]['real']
        sym[pname] = {
            'N_pp': r['delta_bi_minus_weekly']['N_pp'],
            'delta_fee_lt0': bool(r['delta_bi_minus_weekly']['fee_ann_pp'] < 0),
            'mdd_deterioration_pp': r['delta_bi_minus_weekly']['mdd_pp'],
            'mdd_ok_le1pp': bool(r['delta_bi_minus_weekly']['mdd_pp'] <= MDD_TOL),
            'N_ge0': bool(r['delta_bi_minus_weekly']['N_pp'] >= 0),
        }
    symmetric_pass = bool(all(v['N_ge0'] and v['delta_fee_lt0'] and v['mdd_ok_le1pp']
                              for v in sym.values()))
    asymmetric_close = bool(any(not v['N_ge0'] for v in sym.values()))

    # walk-forward（冻结判据）
    wf = {}
    wf_pass = {}
    for pname in pools:
        wf[pname] = walk_forward(runs[pname]['weekly'], runs[pname]['biweekly'])
        wf_pass[pname] = bool(wf[pname]['share_N_gt0_all'] >= WF_SHARE
                              and wf[pname]['max_consec_N_lt_-2pp_real'] is not None
                              and wf[pname]['max_consec_N_lt_-2pp_real'] < 3)
        print(f"[{pname}] walk-forward: N>0 占比(全窗)={wf[pname]['share_N_gt0_all']} "
              f"(真实窗)={wf[pname]['share_N_gt0_real']} "
              f"真实窗连续N<−2pp 最长={wf[pname]['max_consec_N_lt_-2pp_real']}窗 "
              f"PASS={wf_pass[pname]}")

    out = dict(
        generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        workorder='WO3 双周档最后一枪（R12）· 冻结规格 v1.0',
        seed=SEED,
        caliber=dict(form='base 裸奔 ungated 权威形态（f1_backtest 引擎，R9 仪表化 run_instr 逐字复用）',
                     biweekly='每 2 ISO 周首个交易日收盘出信号，次日开盘成交（r8_fee 参数化逐字）',
                     segments='合成训练窗(start~2026-03-31)/合成留出段(2026-04-01~05-31)/真实窗(>=2026-06-01)；'
                              '美股合约代币 2026-06 上线，此前数据按美股本体合成（R9 数据出身铁律）',
                     N_def='N = Δ费拖累(pp/年,省为负) + Δ年化(pp/年,少赚为负)，双周−周口径；'
                           'Δ年化为曲线净年化（费已入账），故 N<0 ⟺ 毛口径少赚 > 费省',
                     unit='年化(pp/年、x)与累计(pp)分列；留出合成段仅 0.164 年，判定用总收益不看年化'),
        t1_same_source_verify=t1v,
        eight_col_table=table,
        per_pool_segments=per_pool,
        symmetric_criteria=dict(
            per_pool=sym,
            pass_=symmetric_pass,
            asymmetric_close_variant_line=asymmetric_close,
            rule='真实窗双池 N>=0 且 Δ费<0 零例外；MDD 劣化<=1pp；任一池真实窗 N<0 → F1 变体线连同关闭无复活'),
        walk_forward={p: {k: v for k, v in wf[p].items() if k != 'windows'}
                      for p in pools},
        walk_forward_pass=wf_pass,
        walk_forward_windows={p: wf[p]['windows'] for p in pools},
        pass_action='通过仅为条件性降频载体备胎不上线，立影子并行单另裁（维持 R10 终裁四）',
    )
    # walk_forward windows 太长，落盘独立键压缩为逐窗 N 序列
    with open(os.path.join(OUT, 'wo3_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('OK ->', os.path.join(OUT, 'wo3_result.json'))
    print('对称判据:', 'PASS' if symmetric_pass else
          ('FAIL→变体线关闭' if asymmetric_close else 'FAIL'))
    print('walk-forward 判据:', wf_pass)


if __name__ == '__main__':
    main()
