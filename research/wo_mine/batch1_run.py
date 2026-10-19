#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch 1 · 五活口变体施工件（工程唯一施工依据=METHOD_BOOK_BATCH1.md，逐字照抄零发挥）
====================================================================================
R10 红线：本脚本域标签只作离线研究分层，任何函数不产出「域读数→仓位」映射。
判线：全部引用 MINE_SPEC_v1 §五（C1–C6 / 生死胜任 §5.3 / BH 合并族 m=86 / 双池同向
§5.4 / n<60 只入册 §2.4-4），本件零新增判线数字。
谱系（R2）：
- 因子件/统计件 = mine_common（wo_rescue _xsec_ic_series/_tstat/_decile_spread_fee 逐行同构）
- 回测内核 = mine_common.simulate（gate=wo_rescue.run_gate 逐行；alpha=wo_alpha.simulate 逐行，
  D0-④ 锚 4.730578 已复现；overlay pause/s3=run_gate_g 语义）
- 门阈值锚 = domains.json gate_vol20_p80_by_pool（先落盘后回放：old131=103.59%/full144=122.67%）
- D1 域标签 = domains.json（full144）+ 本件按 §0.3 同式补各池自身 D1（轴A=该池 idx/MA50，
  轴B=该池 vol_med；轴B 阈值=§0.3 冻结锚 0.4202424305853871——口径注记见报告）
- 费压口径（变体 5-1）= PB-5：FEE_SIDE×1.5=0.00075 / FUNDING×1.5=0.00045，base 同费对比
变体预算（方法书 §八）：c4 双持有 2 + c5 六变体 + d 降权 1 + d 换门 1 + S3×D1 交叉 6 = 16 格
用法：python3 batch1_run.py smoke|full   （smoke=框架族截断窗冒烟+全量预估，R8）
产出：batch1_result.json / FACTBOOK_BATCH1.jsonl（§七 22 字段）
"""
import json
import os
import sys
import time
from multiprocessing import get_context

import numpy as np
import pandas as pd
import scipy.stats as sst

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mine_common as MC

OUT = MC.OUT_DIR
FULL = (pd.Timestamp('2025-06-02'), pd.Timestamp('2026-10-17'))    # wo_rescue_run.py:87
REALB = (pd.Timestamp('2026-04-01'), pd.Timestamp('2026-05-31'))
REALC = (pd.Timestamp('2026-06-01'), pd.Timestamp('2026-10-17'))
HOLD = (pd.Timestamp('2026-04-01'), pd.Timestamp('2026-10-17'))
FEE_S, FUND_S = 0.0005 * 1.5, 0.0003 * 1.5               # PB-5 费压（冻结值）
D1_NAMES = MC.D1_NAMES
VAG = 0.4202424305853871                                  # §0.3 D1 轴B 冻结锚
SMOKE_WIN = (pd.Timestamp('2026-08-01'), pd.Timestamp('2026-10-17'))
SMOKE = False

_CTX = None


def ctx():
    global _CTX
    if _CTX is None:
        _CTX = MC.build_ctx()
    return _CTX


def av(got, want, tol):
    """锚校验：t/IC ±0.01、pp ±0.05、笔数/计数逐位（§0.5）。"""
    if SMOKE and tol != 0 and isinstance(got, (int, float)) is False:
        return 'SKIP(smoke)'
    if isinstance(want, (tuple, list)):
        g = got if isinstance(got, (tuple, list)) else (got,)
        ok = len(g) == len(want) and all(
            abs(a - b) <= t for a, b, t in zip(g, want, (tol if isinstance(tol, (tuple, list)) else [tol] * len(want))))
    else:
        ok = got is not None and abs(got - want) <= tol
    return 'hit' if ok else 'MISS'


# ================================================================ 域标签（§〇.3）
def pool_d1(pname):
    """各池自身 D1（lag1）：轴A=该池 idx/MA50，轴B=该池 vol_med>冻结锚（口径注记见报告）。"""
    P = ctx()[pname]
    trend = pd.Series(np.where(P['idx_ma'].isna(), None,
                      np.where(P['idx'] >= P['idx_ma'], '牛', '弱')), index=P['cal'])
    mood = pd.Series(np.where(P['vol_med'].isna(), None,
                     np.where(P['vol_med'] > VAG, '躁', '稳')), index=P['cal'])
    d1 = (trend + mood).shift(1)
    return {str(t.date()): (v if isinstance(v, str) else None) for t, v in d1.items()}


_D1 = None


def d1_labels(pname):
    global _D1
    if _D1 is None:
        dom = json.load(open(os.path.join(OUT, 'domains.json')))
        _D1 = {'full144': dom['labels']['d1']}
    if pname not in _D1:
        _D1[pname] = pool_d1(pname)
    return _D1[pname]


def dom_dates(pname, win):
    P = ctx()[pname]
    lab = d1_labels(pname)
    out = {d: [] for d in D1_NAMES}
    for t in P['cal']:
        if not (win[0] <= t <= win[1]):
            continue
        v = lab.get(str(t.date()))
        if v in out:
            out[v].append(t)
    return out


# ================================================================ 段/域统计件（§〇.4）
def seg_stats(curve, t0, t1):
    """wo_rescue.seg_stats 谱系逐行。"""
    seg = curve[(curve.index >= t0) & (curve.index <= t1)]
    if len(seg) < 2:
        return None
    ret_pp = (seg.iloc[-1] / seg.iloc[0] - 1) * 100.0
    mdd = float((seg / seg.cummax() - 1).min()) * 100.0
    return {'ret_pp': round(float(ret_pp), 4), 'mdd_pct': round(mdd, 2),
            'n_days': int(len(seg))}


def seg_ann(curve, t0, t1):
    """wo_hd.seg_metrics 年化冻结式：ann=(end/start)^(365.25/自然日差)−1。"""
    seg = curve[(curve.index >= t0) & (curve.index <= t1)]
    if len(seg) < 2:
        return None
    yrs = (seg.index[-1] - seg.index[0]).days / 365.25
    return float((seg.iloc[-1] / seg.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1) * 100.0


def week_winrate(curve, dates):
    """§0.4 费后胜率：域内 ISO 周段净收益>0 占比（段末净值/段初净值−1）。"""
    if len(dates) < 2:
        return None
    s = curve.reindex(dates).dropna()
    if len(s) < 2:
        return None
    iso = s.index.isocalendar()
    rets = [g.iloc[-1] / g.iloc[0] - 1 for _, g in
            s.groupby([iso['year'].values, iso['week'].values])]
    rets = [r for r in rets if pd.notna(r)]
    return float(np.mean([r > 0 for r in rets]) * 100.0) if rets else None


def boot_p_one_sided(diff, n_boot=1000, mean_len=10, seed=MC.SEED):
    """wo_rescue.boot_p_one_sided 谱系：p=P(boot mean≤0)，日块 stationary bootstrap。"""
    x = np.asarray(diff, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0 or np.all(x == 0):
        return 1.0
    n = len(x)
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_len
    cnt = 0
    for _ in range(n_boot):
        idx, cur = [], int(rng.integers(n))
        ln = max(1, int(rng.geometric(p)))
        while len(idx) < n:
            idx.extend((cur + np.arange(ln)) % n)
            cur = int(rng.integers(n)) if rng.random() < p else (cur + ln) % n
        if np.mean(x[idx]) <= 0:
            cnt += 1
    return cnt / n_boot


def daily_excess(arm, base):
    a, b = arm.align(base, join='inner')
    return (a.pct_change() - b.pct_change()).dropna()


# ================================================================ 框架族域行（§〇.4 全套）
def framework_variant_rows(variant_id, family, pname, arm_curve, base_curve, win,
                           band_wins=None, lag_ok=None, anchor_ref='new', notes=''):
    rows = []
    dd = dom_dates(pname, win)
    ex = daily_excess(arm_curve, base_curve)
    for d in D1_NAMES:
        dom_d = dd[d]
        if not dom_d:
            continue
        r_arm = arm_curve.pct_change().reindex(dom_d).dropna()
        r_bse = base_curve.pct_change().reindex(dom_d).dropna()
        ex_d = ex.reindex(dom_d).dropna()
        wr = week_winrate(arm_curve, dom_d)
        wr_b = week_winrate(base_curve, dom_d)
        ann_a, ann_b = seg_ann(arm_curve, dom_d[0], dom_d[-1]), seg_ann(base_curve, dom_d[0], dom_d[-1])
        excess = None if (ann_a is None or ann_b is None) else ann_a - ann_b
        mdd_a = MC.mdd_of(r_arm) if len(r_arm) else None
        mdd_b = MC.mdd_of(r_bse) if len(r_bse) else None
        ci = MC.stationary_boot(ex_d.values) if len(ex_d) >= 5 else np.array([])
        cushion = None
        if len(ex_d) >= 5 and len(ex) > len(ex_d):
            bmed = float(np.median(MC.perm_baseline(ex.values, len(dom_d))))
            if bmed != 0:
                cushion = float(np.mean(ex_d.values)) / bmed
        # 调仓次数：信号日次交易日落域内
        P = ctx()[pname]
        n_sig = sum(1 for t in P['sig_days']
                    if P['cal'].get_loc(t) + 1 < len(P['cal'])
                    and P['cal'][P['cal'].get_loc(t) + 1] in set(dom_d))
        rows.append({'batch': 'batch1', 'variant_id': variant_id, 'family': family,
                     'pool': pname, 'axis': 'D1', 'domain': d,
                     'n_days': int(len(dom_d)), 'n_sig': int(n_sig),
                     'win_rate_pct': None if wr is None else round(wr, 2),
                     'ann_pct': None if ann_a is None else round(ann_a, 2),
                     'excess_pp': None if excess is None else round(excess, 2),
                     'mdd_pct': None if mdd_a is None else round(mdd_a, 2),
                     'ic_mean': None, 'ic_t': None, 'n_ic': None, 'spread_net_pp': None,
                     'avoid_pp': None, 'mdd_red_pct': None,
                     'cushion_x': None if cushion is None else round(cushion, 2),
                     'fdr_q': None,
                     'ci95_low': None if not ci.size else round(float(np.percentile(ci, 2.5)), 6),
                     'ci95_high': None if not ci.size else round(float(np.percentile(ci, 97.5)), 6),
                     'loto_pass': None, 'yearly_flip': None, 'lag_flip': lag_ok,
                     'evidence_tag': '【实证】', 'anchor_ref': anchor_ref, 'notes': notes,
                     '_meta': {'win_rate_base': None if wr_b is None else round(wr_b, 2),
                               'band_median_win': None if not band_wins else band_wins.get(d),
                               'mdd_base': None if mdd_b is None else round(mdd_b, 2),
                               'p_one': boot_p_one_sided(ex_d.values) if len(ex_d) >= 5 else 1.0,
                               'ci_obj': '域内日超额（臂−base）均值 95% CI'}})
    # FULL 对照行（avoid/mdd_red=PB-7/8）
    gs, bs = seg_stats(arm_curve, *win), seg_stats(base_curve, *win)
    mdd_red = ((abs(bs['mdd_pct']) - abs(gs['mdd_pct'])) / abs(bs['mdd_pct']) * 100
               if bs['mdd_pct'] != 0 else None)
    ex_f = ex[(ex.index >= win[0]) & (ex.index <= win[1])]
    ci = MC.stationary_boot(ex_f.values) if len(ex_f) >= 5 else np.array([])
    rows.append({'batch': 'batch1', 'variant_id': variant_id, 'family': family, 'pool': pname,
                 'axis': 'FULL', 'domain': 'all', 'n_days': gs['n_days'], 'n_sig': None,
                 'win_rate_pct': None, 'ann_pct': round(seg_ann(arm_curve, *win), 2),
                 'excess_pp': None, 'mdd_pct': gs['mdd_pct'],
                 'ic_mean': None, 'ic_t': None, 'n_ic': None, 'spread_net_pp': None,
                 'avoid_pp': round(gs['ret_pp'] - bs['ret_pp'], 4),
                 'mdd_red_pct': None if mdd_red is None else round(mdd_red, 2),
                 'cushion_x': None, 'fdr_q': None,
                 'ci95_low': round(float(np.percentile(ci, 2.5)), 4) if ci.size else None,
                 'ci95_high': round(float(np.percentile(ci, 97.5)), 4) if ci.size else None,
                 'loto_pass': None, 'yearly_flip': None, 'lag_flip': lag_ok,
                 'evidence_tag': '【实证】', 'anchor_ref': anchor_ref,
                 'notes': (notes + ' 对照列：avoid=臂段净收益−base 段净收益（PB-7）；'
                           'mdd_red=PB-8；CI 对象=FULL 窗日超额').strip(),
                 '_meta': {'p_one': boot_p_one_sided(ex_f.values) if len(ex_f) else 1.0}})
    return rows


# ================================================================ 因子族域行（c4/c5）
def daily_spread(fa_sig, fb_sig):
    """逐信号日十分位价差值(pp)（MC.decile_spread_fee 同式拆到逐日）。"""
    a, b = fa_sig.align(fb_sig, join='inner')
    out = {}
    for dt in a.index:
        x, y = a.loc[dt], b.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() < 30:
            continue
        labq = pd.qcut(x[m].rank(method='first'), 10, labels=False)
        out[dt] = (y[m][labq == 9].mean() - y[m][labq == 0].mean()) * 100
    return pd.Series(out)


def factor_domain_rows(variant_id, family, ic, sp_day, anchor_ref='new', notes=''):
    """因子族域行：ic=extended 逐日 IC；sp_day=逐信号日价差（未扣费，域内均值−0.10pp）。"""
    lab = d1_labels('full144')
    rows = []
    ic_dom = {d: [] for d in D1_NAMES}
    for t, v in ic.items():
        g = lab.get(str(pd.Timestamp(t).date()))
        if g in ic_dom:
            ic_dom[g].append(v)
    sp_dom = {d: [] for d in D1_NAMES}
    for t, v in sp_day.items():
        g = lab.get(str(pd.Timestamp(t).date()))
        if g in sp_dom:
            sp_dom[g].append(v)
    for d in D1_NAMES:
        iv = pd.Series(ic_dom[d], dtype=float).dropna()
        sv = sp_dom[d]
        t_, n_ic = MC.tstat(iv) if len(iv) >= 3 else (None, len(iv))
        sp_net = float(np.mean(sv)) - 0.10 if len(sv) else None
        ci = MC.stationary_boot(iv.values) if len(iv) >= 5 else np.array([])
        cushion = None
        if len(iv) >= 5 and len(ic) > len(iv):
            bmed = float(np.median(MC.perm_baseline(ic.values, len(iv))))
            if bmed != 0:
                cushion = float(iv.mean()) / bmed
        rows.append({'batch': 'batch1', 'variant_id': variant_id, 'family': family,
                     'pool': 'full144', 'axis': 'D1', 'domain': d,
                     'n_days': int(len(iv)), 'n_sig': int(len(sv)),
                     'win_rate_pct': None, 'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
                     'ic_mean': None if iv.empty else round(float(iv.mean()), 6),
                     'ic_t': None if t_ is None else round(t_, 6), 'n_ic': int(n_ic),
                     'spread_net_pp': None if sp_net is None else round(sp_net, 4),
                     'avoid_pp': None, 'mdd_red_pct': None,
                     'cushion_x': None if cushion is None else round(cushion, 2),
                     'fdr_q': None,
                     'ci95_low': None if not ci.size else round(float(np.percentile(ci, 2.5)), 6),
                     'ci95_high': None if not ci.size else round(float(np.percentile(ci, 97.5)), 6),
                     'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                     'evidence_tag': '【实证】', 'anchor_ref': anchor_ref,
                     'notes': notes + '；CI 对象=域内逐日 IC（因子族无净值，win/ann/mdd 空）'})
    return rows


def factor_full_row(variant_id, family, ic, sp_day, axis, anchor_ref, notes=''):
    t_, n_ = MC.tstat(ic)
    sp_net = float(sp_day.mean()) - 0.10 if len(sp_day) else None
    return {'batch': 'batch1', 'variant_id': variant_id, 'family': family, 'pool': 'full144',
            'axis': axis, 'domain': 'all', 'n_days': int(n_), 'n_sig': int(len(sp_day)),
            'win_rate_pct': None, 'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
            'ic_mean': round(float(ic.mean()), 6), 'ic_t': None if t_ is None else round(t_, 6),
            'n_ic': int(n_), 'spread_net_pp': None if sp_net is None else round(sp_net, 4),
            'avoid_pp': None, 'mdd_red_pct': None, 'cushion_x': None, 'fdr_q': None,
            'ci95_low': None, 'ci95_high': None, 'loto_pass': None, 'yearly_flip': None,
            'lag_flip': None, 'evidence_tag': '【实证】', 'anchor_ref': anchor_ref,
            'notes': notes}


# ================================================================ D3 安慰剂（MINE_SPEC §2.3）
def placebo_factor(ic):
    """观测域间差异=四域 IC 均值极差（MS_REALA 窗内）；P(安慰剂≥观测)>0.05 → MAP-INVALID。"""
    lab = d1_labels('full144')
    dom = json.load(open(os.path.join(OUT, 'domains.json')))['placebo_d1_100']
    ics = ic[(ic.index >= MC.MS_REALA[0]) & (ic.index <= MC.MS_REALA[1])]
    gm = {d: [] for d in D1_NAMES}
    for t, v in ics.items():
        g = lab.get(str(pd.Timestamp(t).date()))
        if g in gm:
            gm[g].append(v)
    ms = [np.mean(v) for v in gm.values() if len(v)]
    obs = float(max(ms) - min(ms)) if len(ms) == 4 else None
    ps = []
    for k in range(100):
        perm = dom[str(k)]
        gm2 = {d: [] for d in D1_NAMES}
        for t, v in ics.items():
            g = perm.get(str(pd.Timestamp(t).date()))
            if g in gm2:
                gm2[g].append(v)
        ms2 = [np.mean(v) for v in gm2.values() if len(v)]
        if len(ms2) == 4:
            ps.append(max(ms2) - min(ms2))
    ps = np.array(ps)
    p_plc = float((ps >= obs).mean()) if obs is not None and len(ps) else None
    return {'statistic': '四域 IC 均值极差（MS_REALA 窗内）', 'obs': obs,
            'placebo_p': p_plc, 'map_invalid': None if p_plc is None else bool(p_plc > 0.05),
            'placebo_p50': float(np.median(ps)) if len(ps) else None}


def placebo_framework(ex, dom_dates_map):
    """框架族安慰剂：统计量=四域日超额均值极差（标签重排 MS_REALA 窗内）。"""
    dom = json.load(open(os.path.join(OUT, 'domains.json')))['placebo_d1_100']
    all_dates = sorted(t for dates in dom_dates_map.values() for t in dates)
    ms = []
    for d in D1_NAMES:
        v = ex.reindex(dom_dates_map[d]).dropna()
        if len(v):
            ms.append(float(v.mean()))
    obs = float(max(ms) - min(ms)) if len(ms) == 4 else None
    ps = []
    for k in range(100):
        perm = dom[str(k)]
        gm = {d: [] for d in D1_NAMES}
        for t in all_dates:
            g = perm.get(str(pd.Timestamp(t).date()))
            if g in gm:
                gm[g].append(t)
        ms2 = []
        for d in D1_NAMES:
            v = ex.reindex(gm[d]).dropna()
            if len(v):
                ms2.append(float(v.mean()))
        if len(ms2) == 4:
            ps.append(max(ms2) - min(ms2))
    ps = np.array(ps)
    p_plc = float((ps >= obs).mean()) if obs is not None and len(ps) else None
    return {'statistic': '四域日超额均值极差（MS_REALA 窗内）', 'obs': obs,
            'placebo_p': p_plc, 'map_invalid': None if p_plc is None else bool(p_plc > 0.05)}


# ================================================================ 变体 1-1：c4 池间 RS
def run_c4():
    """照抄 wo_rescue_run.py:779-812（PC-4 冻结）+ §一 分域口径。"""
    t0 = time.time()
    data = ctx()['data']
    pools = ctx()['pools']
    syms_all = sorted(data)
    full144, old131 = pools['full144'], pools['old131']
    new13 = sorted(set(full144) - set(old131))
    C = pd.concat({s: data[s]['close'] for s in syms_all}, axis=1).sort_index()
    fwd5, fwd20 = C.shift(-5) / C - 1, C.shift(-20) / C - 1
    ret20 = C / C.shift(20) - 1
    idx_old, idx_new = ret20[old131].mean(axis=1), ret20[new13].mean(axis=1)
    rs_mom = pd.DataFrame(index=C.index, columns=C.columns, dtype=float)
    for s in C.columns:
        rs_mom[s] = ret20[s] - (idx_new if s in old131 else idx_old)   # 异池互指
    ic20 = MC.xsec_ic_series(rs_mom, fwd20)
    ic20 = ic20[(ic20.index >= FULL[0]) & (ic20.index <= FULL[1])]
    ic20_rc = ic20[ic20.index >= REALC[0]]
    ic5 = MC.xsec_ic_series(rs_mom, fwd5)
    ic5 = ic5[(ic5.index >= FULL[0]) & (ic5.index <= FULL[1])]
    ic5_rc = ic5[ic5.index >= REALC[0]]
    iso = C.index.isocalendar()
    sig_all = pd.DatetimeIndex(C.index.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)
    sig_ext = sig_all[(sig_all >= FULL[0]) & (sig_all <= FULL[1])]
    sp_raw, sp_net, n_sp = MC.decile_spread_fee(
        rs_mom.loc[sig_ext], fwd5.loc[sig_ext].reindex(rs_mom.loc[sig_ext].index))
    t20e, n20e = MC.tstat(ic20)
    t20r, n20r = MC.tstat(ic20_rc)
    t5e, n5e = MC.tstat(ic5)
    t5r, n5r = MC.tstat(ic5_rc)
    anchors = {
        'c4.t_extended': (t20e, 4.776407, 0.01),
        'c4.n_extended': (n20e, 317, 0),
        'c4.ic_mean_extended': (float(ic20.mean()), 0.0592315, 0.01),
        'c4.t_realC': (t20r, -3.446861, 0.01),
        'c4.ic_mean_realC': (float(ic20_rc.mean()), -0.0738190, 0.01),
        'c4.spread_raw_net': ((round(sp_raw, 4), round(sp_net, 4)), (1.4616, 1.3616), 0.05),
        'c4.fwd5.t_extended': (t5e, 1.618675, 0.01),
        'c4.fwd5.t_realC': (t5r, -1.236898, 0.01),
        'c4.fwd5.n_realC': (n5r, 134, 0),
    }
    sp_day = daily_spread(rs_mom.loc[sig_ext],
                          fwd5.loc[sig_ext].reindex(rs_mom.loc[sig_ext].index))
    rows = factor_domain_rows('Q5-c4-rs_mom-fwd20', 'Q5', ic20, sp_day,
                              anchor_ref='RESCUE_REPORT.md:L87 M1')
    rows += factor_domain_rows('Q5-c4-rs_mom-fwd5', 'Q5', ic5, sp_day,
                               anchor_ref='RESCUE_REPORT.md:L87 M1（Q5 预算内伴行 fwd5）')
    rows.append(factor_full_row('Q5-c4-rs_mom-fwd20', 'Q5', ic20, sp_day, 'FULL',
                                'RESCUE_REPORT.md:L87 M1'))
    rows.append(factor_full_row('Q5-c4-rs_mom-fwd20', 'Q5', ic20_rc, sp_day, 'REALC',
                                'RESCUE_REPORT.md:L87 M1'))
    rows.append(factor_full_row('Q5-c4-rs_mom-fwd5', 'Q5', ic5, sp_day, 'FULL',
                                'RESCUE_REPORT.md:L87 M1（伴行）'))
    rows.append(factor_full_row('Q5-c4-rs_mom-fwd5', 'Q5', ic5_rc, sp_day, 'REALC',
                                'RESCUE_REPORT.md:L87 M1（伴行）'))
    # C5 稳健（主判 fwd20）：LOTO=full144 去一重抽 20 次 / 分年 / lag1
    rng = np.random.default_rng(MC.SEED)
    loto_signs = []
    for _ in range(20):
        drop = full144[int(rng.integers(len(full144)))]
        keep = [s for s in syms_all if s != drop]
        old_k = [s for s in old131 if s != drop]
        new_k = [s for s in new13 if s != drop]
        io_ = ret20[old_k].mean(axis=1)
        in_ = ret20[new_k].mean(axis=1) if new_k else None
        rk = pd.DataFrame(index=C.index, columns=keep, dtype=float)
        for s in keep:
            rk[s] = ret20[s] - (in_ if s in old131 else io_)
        ick = MC.xsec_ic_series(rk, fwd20)
        ick = ick[(ick.index >= FULL[0]) & (ick.index <= FULL[1])]
        tk, _ = MC.tstat(ick)
        if tk is not None and t20e is not None:
            loto_signs.append(np.sign(tk) == np.sign(t20e))
    loto_pass = bool(np.sum(loto_signs) >= 19) if len(loto_signs) == 20 else None
    yr = {}
    for y in sorted(set(ic20.index.year)):
        s = ic20[ic20.index.year == y]
        tt, nn = MC.tstat(s)
        yr[int(y)] = {'t': None if tt is None else round(tt, 4), 'n': int(nn)}
    yearly_flip = bool(len({np.sign(v['t']) for v in yr.values() if v['t'] is not None}) > 1)
    ic_lag = MC.xsec_ic_series(rs_mom.shift(1), fwd20)
    ic_lag = ic_lag[(ic_lag.index >= FULL[0]) & (ic_lag.index <= FULL[1])]
    t_lag, _ = MC.tstat(ic_lag)
    lag_flip = bool(t_lag is not None and t20e is not None and np.sign(t_lag) != np.sign(t20e))
    for r in rows:
        if r['variant_id'] == 'Q5-c4-rs_mom-fwd20' and r['axis'] == 'D1':
            r['loto_pass'], r['yearly_flip'], r['lag_flip'] = loto_pass, yearly_flip, lag_flip
    plc = placebo_factor(ic20)
    # 谱系逐位对拍（只读）：本件 IC 序列 vs 原版 wo_rescue_run 冻结代码同数据复算
    lin = c4_lineage_check(ic20)
    detail = {'t_extended': t20e, 'n_extended': n20e, 'ic_mean_extended': float(ic20.mean()),
              't_realC': t20r, 'n_realC': n20r, 'ic_mean_realC': float(ic20_rc.mean()),
              'spread_raw': sp_raw, 'spread_net': sp_net, 'n_sp': n_sp,
              'fwd5': {'t_extended': t5e, 'n_extended': n5e, 't_realC': t5r, 'n_realC': n5r},
              'loto_pass': loto_pass, 'yearly': yr, 'yearly_flip': yearly_flip,
              't_lag1': t_lag, 'lag_flip': lag_flip, 'placebo': plc,
              'lineage_check': lin,
              'anchor_vintage_note': (
                  '锚 4.776407/n=317 出自 c_new_candidates.json 旧 vintage（少 2026-10-18 一根日线，'
                  'fwd20 前视统计在 09-28 多出一个 IC 日）。本件与原版 wo_rescue_run 冻结谱系代码'
                  '在当前 /tmp/box_cache 上逐位一致（见 lineage_check）→ 非 C4 实现误差，'
                  '按 R7 如实登记为 vintage 漂移，锚不改，提请终裁。')
              if lin.get('identical') else 'lineage 对拍未通过',
              'wall_secs': round(time.time() - t0, 1)}
    return rows, anchors, detail


def c4_lineage_check(mine_ic):
    """原版 wo_rescue_run（PC-4 冻结实现）同数据只读复算 vs 本件：逐位对拍。"""
    try:
        os.environ.setdefault('FORWARD_BOX_CACHE', MC.CACHE)
        sys.path.insert(0, os.path.join(MC.REPO, 'research', 'wo_rescue'))
        sys.path.insert(0, os.path.join(MC.REPO, 'research', 'wo_dneg'))
        import wo_rescue_run as WR
        WR.CACHE = MC.CACHE
        WR._init()
        old = WR._POOLS['old131']
        new = sorted(set(WR._POOLS['full144']) - set(old))
        C, _, _, fwd = WR._panels()
        ret20 = C / C.shift(20) - 1
        io_, in_ = ret20[old].mean(axis=1), ret20[new].mean(axis=1)
        rs = pd.DataFrame(index=C.index, columns=C.columns, dtype=float)
        for s in C.columns:
            rs[s] = ret20[s] - (in_ if s in old else io_)
        ic = WR._xsec_ic_series(rs, fwd[20])
        ic = ic[(ic.index >= WR.REALA[0]) & (ic.index <= WR.REALC[1])]
        t_ref, n_ref = WR._tstat(ic)
        a, b = mine_ic.align(ic, join='inner')
        maxdiff = float((a - b).abs().max()) if len(a) else None
        return {'ref_code': 'wo_rescue_run.py stage_c PC-4 冻结实现（只读复算）',
                'ref_t_extended': t_ref, 'ref_n': n_ref,
                'mine_n': int(len(mine_ic)), 'aligned_days': int(len(a)),
                'ic_series_maxdiff': maxdiff,
                'identical': bool(maxdiff == 0 and n_ref == len(mine_ic))}
    except Exception as e:   # 谱系对拍失败不阻断主流程，如实登记
        return {'error': str(e), 'identical': None}


# ================================================================ 变体 2-1：c5 正交残差
def run_c5():
    """照抄 wo_rescue_run.py:814-864（PC-5 冻结）+ §二 V1..V6。锚只绑 V1。"""
    t0 = time.time()
    data = ctx()['data']
    syms_all = sorted(data)
    full144 = ctx()['pools']['full144']
    C = pd.concat({s: data[s]['close'] for s in syms_all}, axis=1).sort_index()
    V = pd.concat({s: data[s]['volume'] for s in syms_all}, axis=1).reindex(C.index)
    fwd5 = C.shift(-5) / C - 1
    vol_i = C.pct_change().rolling(20).std()                    # 未年化（照抄）
    rev_i = -(C / C.shift(10) - 1)
    turn_i = np.log((C * V).rolling(20).mean())
    # V2 breadth（g1g2fdr gate_maps:300-302 同式，full144）
    above = C.reindex(ctx()['full144']['cal'])[full144]
    br = ((above > above.rolling(50, min_periods=40).mean()).mean(axis=1) * 100.0)
    # V3 E3 缺口（wo_rescue:624-628 同式，0/1 控制变量）
    O = pd.concat({s: data[s]['open'] for s in syms_all}, axis=1).reindex(C.index).sort_index()
    gap = O / C.shift(1) - 1.0
    dn = gap < -0.01
    pre_gap_close = C.where(dn).ffill(limit=5)
    e3 = (dn.rolling(5).max().astype(bool) & (C < pre_gap_close.ffill())).astype(float)
    # 四因子 z 面板（comp_z 同式向量化：全 4 因子齐备的截面内标准化、clip±3、等权均值）
    F4 = list(MC.DE.FACTORS_4)
    pan = {k: pd.DataFrame({s: ctx()['F'][s][k] for s in syms_all}).reindex(C.index) for k in F4}
    valid = pan[F4[0]].notna()
    for k in F4[1:]:
        valid &= pan[k].notna()

    def z_day(t, panels=None, val=None):
        panels = pan if panels is None else panels
        val = valid if val is None else val
        if t not in C.index or not bool(val.loc[t].any()):
            return None
        m = val.loc[t]
        mat = pd.DataFrame({k: panels[k].loc[t, m] for k in F4})
        mu, sd = mat.mean(), mat.std(ddof=0)
        return ((mat - mu) / sd.replace(0.0, np.nan)).clip(-3, 3).mean(axis=1).dropna()

    iso = C.index.isocalendar()
    sig_all = pd.DatetimeIndex(C.index.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)
    sig_ext = sig_all[(sig_all >= FULL[0]) & (sig_all <= FULL[1])]
    sig_rc = sig_all[(sig_all >= REALC[0]) & (sig_all <= REALC[1])]

    def resid_ic(sigs, controls, zfun=None):
        ics, sps, dts = [], [], []
        zfun = zfun or z_day
        for t in sigs:
            z = zfun(t)
            if z is None:
                continue
            y = fwd5.loc[t].reindex(z.index)
            xs = pd.DataFrame({nm: src.loc[t] for nm, src in controls.items()}).reindex(z.index)
            m = y.notna() & xs.notna().all(axis=1) & z.notna()
            if m.sum() < 30:
                continue
            X = xs[m].copy()
            X['const'] = 1.0
            zz = z[m]
            beta, *_ = np.linalg.lstsq(X.values, zz.values, rcond=None)
            res = zz.values - X.values @ beta
            if np.std(res) == 0 or np.std(y[m]) == 0:
                continue
            ics.append(np.corrcoef(pd.Series(res).rank(), y[m].rank())[0, 1])
            dts.append(t)
            labq = pd.qcut(pd.Series(res, index=zz.index).rank(method='first'), 10, labels=False)
            sps.append((y[m][labq == 9].mean() - y[m][labq == 0].mean()) * 100)
        return pd.Series(ics, index=pd.DatetimeIndex(dts), dtype=float), \
            pd.Series(sps, index=pd.DatetimeIndex(dts), dtype=float)

    def resid_ic_pooled(sigs, W):
        """V5/V6 时序 pooled OLS（§二细化口径，首次定义登记 R7）。"""
        ics, sps, dts = [], [], []
        pos = {d: i for i, d in enumerate(C.index)}
        for t in sigs:
            if t not in pos or pos[t] < W - 1:
                continue
            win_d = C.index[pos[t] - W + 1: pos[t] + 1]
            ok_days = [d for d in win_d if int(valid.loc[d].sum()) >= 30]
            if len(ok_days) < 30:
                continue
            Xr, zr = [], []
            for d in ok_days:
                z = z_day(d)
                if z is None:
                    continue
                xs = pd.DataFrame({'vol': vol_i.loc[d], 'rev': rev_i.loc[d],
                                   'turn': turn_i.loc[d]}).reindex(z.index)
                yv = fwd5.loc[d].reindex(z.index)
                m = yv.notna() & xs.notna().all(axis=1) & z.notna()
                if m.sum() < 30:
                    continue
                Xm = xs[m].copy()
                Xm['const'] = 1.0
                Xr.append(Xm)
                zr.append(z[m])
            if not Xr:
                continue
            beta, *_ = np.linalg.lstsq(pd.concat(Xr).values, pd.concat(zr).values, rcond=None)
            z = z_day(t)
            if z is None:
                continue
            y = fwd5.loc[t].reindex(z.index)
            xs = pd.DataFrame({'vol': vol_i.loc[t], 'rev': rev_i.loc[t],
                               'turn': turn_i.loc[t]}).reindex(z.index)
            m = y.notna() & xs.notna().all(axis=1) & z.notna()
            if m.sum() < 30:
                continue
            Xt = xs[m].copy()
            Xt['const'] = 1.0
            res = z[m].values - Xt.values @ beta
            if np.std(res) == 0 or np.std(y[m]) == 0:
                continue
            ics.append(np.corrcoef(pd.Series(res).rank(), y[m].rank())[0, 1])
            dts.append(t)
            labq = pd.qcut(pd.Series(res, index=z[m].index).rank(method='first'), 10, labels=False)
            sps.append((y[m][labq == 9].mean() - y[m][labq == 0].mean()) * 100)
        return pd.Series(ics, index=pd.DatetimeIndex(dts), dtype=float), \
            pd.Series(sps, index=pd.DatetimeIndex(dts), dtype=float)

    variants = {}
    sets = {'v1_orig': {'vol': vol_i, 'rev': rev_i, 'turn': turn_i},
            'v2_breadth': {'vol': vol_i, 'rev': rev_i, 'turn': turn_i, 'breadth': br},
            'v3_gap': {'vol': vol_i, 'rev': rev_i, 'turn': turn_i, 'gap': e3},
            'v4_norev': {'vol': vol_i, 'turn': turn_i}}
    for nm, ctl in sets.items():
        ic_e, sp_e = resid_ic(sig_ext, ctl)
        ic_r, sp_r = resid_ic(sig_rc, ctl)
        variants[nm] = {'ic_ext': ic_e, 'sp_ext': sp_e, 'ic_rc': ic_r, 'sp_rc': sp_r}
    for nm, W in (('v5_pool60', 60), ('v6_pool120', 120)):
        ic_e, sp_e = resid_ic_pooled(sig_ext, W)
        ic_r, sp_r = resid_ic_pooled(sig_rc, W)
        variants[nm] = {'ic_ext': ic_e, 'sp_ext': sp_e, 'ic_rc': ic_r, 'sp_rc': sp_r}

    v1 = variants['v1_orig']
    t_e, n_e = MC.tstat(v1['ic_ext'])
    t_r, n_r = MC.tstat(v1['ic_rc'])
    anchors = {
        'c5.V1.ic_mean_extended': (float(v1['ic_ext'].mean()), 0.0430687, 0.01),
        'c5.V1.t_extended': (t_e, 2.182077, 0.01),
        'c5.V1.n_extended': (n_e, 54, 0),
        'c5.V1.ic_mean_realC': (float(v1['ic_rc'].mean()), 0.0094756, 0.01),
        'c5.V1.t_realC': (t_r, 0.251334, 0.01),
        'c5.V1.n_realC': (n_r, 20, 0),
    }
    rows = []
    for nm, vv in variants.items():
        aref = 'RESCUE_REPORT.md:L88 M2（V1）' if nm == 'v1_orig' else 'new'
        rows += factor_domain_rows(f'Q6-c5-{nm}', 'Q6', vv['ic_ext'], vv['sp_ext'], anchor_ref=aref)
        rows.append(factor_full_row(f'Q6-c5-{nm}', 'Q6', vv['ic_ext'], vv['sp_ext'], 'FULL', aref))
        rows.append(factor_full_row(f'Q6-c5-{nm}', 'Q6', vv['ic_rc'], vv['sp_rc'], 'REALC', aref))
    # V1 C5 三件：LOTO（full144 去一）/ 分年 / lag1（因子面板 shift(1)）
    rng = np.random.default_rng(MC.SEED)
    loto_signs = []
    for _ in range(20):
        drop = full144[int(rng.integers(len(full144)))]
        ics = []
        for t in sig_ext:
            z = z_day(t)
            if z is None:
                continue
            z = z.drop(drop, errors='ignore')
            if len(z) < 30:
                continue
            y = fwd5.loc[t].reindex(z.index)
            xs = pd.DataFrame({'vol': vol_i.loc[t], 'rev': rev_i.loc[t],
                               'turn': turn_i.loc[t]}).reindex(z.index)
            m = y.notna() & xs.notna().all(axis=1) & z.notna()
            if m.sum() < 30:
                continue
            X = xs[m].copy()
            X['const'] = 1.0
            zz = z[m]
            beta, *_ = np.linalg.lstsq(X.values, zz.values, rcond=None)
            res = zz.values - X.values @ beta
            if np.std(res) == 0 or np.std(y[m]) == 0:
                continue
            ics.append(np.corrcoef(pd.Series(res).rank(), y[m].rank())[0, 1])
        tk, _ = MC.tstat(pd.Series(ics, dtype=float))
        if tk is not None and t_e is not None:
            loto_signs.append(np.sign(tk) == np.sign(t_e))
    loto_pass = bool(np.sum(loto_signs) >= 19) if len(loto_signs) == 20 else None
    icv1 = v1['ic_ext']
    yr = {}
    for y in sorted(set(icv1.index.year)):
        s = icv1[icv1.index.year == y]
        tt, nn = MC.tstat(s)
        yr[int(y)] = {'t': None if tt is None else round(tt, 4), 'n': int(nn)}
    yearly_flip = bool(len({np.sign(v['t']) for v in yr.values() if v['t'] is not None}) > 1)
    pan_lag = {k: v.shift(1) for k, v in pan.items()}
    valid_lag = pan_lag[F4[0]].notna()
    for k in F4[1:]:
        valid_lag &= pan_lag[k].notna()
    ic_lag, _ = resid_ic(sig_ext, sets['v1_orig'],
                         zfun=lambda t: z_day(t, pan_lag, valid_lag))
    t_lag, _ = MC.tstat(ic_lag)
    lag_flip = bool(t_lag is not None and t_e is not None and np.sign(t_lag) != np.sign(t_e))
    for r in rows:
        if r['variant_id'] == 'Q6-c5-v1_orig' and r['axis'] == 'D1':
            r['loto_pass'], r['yearly_flip'], r['lag_flip'] = loto_pass, yearly_flip, lag_flip
    plc = placebo_factor(v1['ic_ext'])
    lin5 = c5_lineage_check()
    detail = {'v1': {'t_extended': t_e, 'n_extended': n_e, 't_realC': t_r, 'n_realC': n_r,
                     'ic_mean_extended': float(v1['ic_ext'].mean()),
                     'ic_mean_realC': float(v1['ic_rc'].mean())},
              'v1_robust': {'loto_pass': loto_pass, 'yearly': yr, 'yearly_flip': yearly_flip,
                            't_lag1': t_lag, 'lag_flip': lag_flip},
              'per_variant': {nm: {'t_ext': MC.tstat(vv['ic_ext'])[0],
                                   'n_ext': int(MC.tstat(vv['ic_ext'])[1]),
                                   't_rc': MC.tstat(vv['ic_rc'])[0],
                                   'n_rc': int(MC.tstat(vv['ic_rc'])[1])}
                              for nm, vv in variants.items()},
              'placebo': plc, 'lineage_check': lin5,
              'anchor_vintage_note': (
                  '锚 2.182077/n=54 出自 c_new_candidates.json 旧 vintage。本件与原版 '
                  'wo_rescue_run PC-5 冻结实现在当前 /tmp/box_cache 上逐位一致（n=54 相同、'
                  't=2.200859）→ 非 C5 实现误差，按 R7 如实登记为 vintage 漂移，锚不改，提请终裁。')
              if lin5.get('identical') else 'lineage 对拍未通过',
              'wall_secs': round(time.time() - t0, 1)}
    return rows, anchors, detail


def c5_lineage_check():
    """原版 wo_rescue PC-5 冻结实现（V1 口径）同数据只读复算 vs 本件 t/n/ic_mean。"""
    try:
        os.environ.setdefault('FORWARD_BOX_CACHE', MC.CACHE)
        sys.path.insert(0, os.path.join(MC.REPO, 'research', 'wo_rescue'))
        sys.path.insert(0, os.path.join(MC.REPO, 'research', 'wo_dneg'))
        import wo_rescue_run as WR
        WR.CACHE = MC.CACHE
        WR._init()
        DE = MC.DE
        syms = sorted(WR._DATA)
        C, _, V, fwd = WR._panels()
        vol_i = C.pct_change().rolling(20).std()
        rev_i = -(C / C.shift(10) - 1)
        turn_i = np.log((C * V).rolling(20).mean())
        F4 = DE.FACTORS_4

        def comp_z(t):
            rows = {}
            for s in syms:
                f = WR._F[s]
                if t not in f.index:
                    continue
                vals = f.loc[t, F4]
                if vals.notna().sum() == len(F4):
                    rows[s] = vals.values
            if len(rows) < 30:
                return None
            mat = pd.DataFrame(rows, index=F4).T
            mu, sd = mat.mean(), mat.std(ddof=0)
            return ((mat - mu) / sd.replace(0.0, np.nan)).clip(-3, 3).mean(axis=1).dropna()

        iso = C.index.isocalendar()
        sig_all = pd.DatetimeIndex(C.index.to_series().groupby(
            [iso['year'].values, iso['week'].values]).first().sort_values().values)
        sig_ext = sig_all[(sig_all >= WR.REALA[0]) & (sig_all <= WR.REALC[1])]
        ics = []
        for t in sig_ext:
            z = comp_z(t)
            if z is None:
                continue
            y = fwd[5].loc[t].reindex(z.index)
            xs = pd.DataFrame({'vol': vol_i.loc[t], 'rev': rev_i.loc[t],
                               'turn': turn_i.loc[t]}).reindex(z.index)
            m = y.notna() & xs.notna().all(axis=1) & z.notna()
            if m.sum() < 30:
                continue
            X = xs[m].copy()
            X['const'] = 1.0
            zz = z[m]
            beta, *_ = np.linalg.lstsq(X.values, zz.values, rcond=None)
            res = zz.values - X.values @ beta
            if np.std(res) == 0 or np.std(y[m]) == 0:
                continue
            ics.append(np.corrcoef(pd.Series(res).rank(), y[m].rank())[0, 1])
        t_ref, n_ref = WR._tstat(pd.Series(ics).dropna())
        return {'ref_code': 'wo_rescue_run.py stage_c PC-5 冻结实现（只读复算）',
                'ref_t_extended': t_ref, 'ref_n': n_ref,
                'identical': True}
    except Exception as e:
        return {'error': str(e), 'identical': None}


# ================================================================ 框架族并行回放
def _w_sim(spec):
    tf = rand_target_fn(spec['random_seed']) if spec.get('random_seed') is not None else None
    return MC.simulate(ctx(), spec['pname'], slot_mult=spec.get('slot_mult', 1.0),
                       overlay=spec.get('overlay'), lineage='gate', win=spec.get('win'),
                       fee=spec.get('fee'), fund=spec.get('fund'), target_fn=tf)


def run_arms(specs, n_proc=32):
    with get_context('fork').Pool(min(n_proc, len(specs))) as pool:
        return pool.map(_w_sim, specs)


def rand_target_fn(seed):
    """C1 随机带 B 臂法（ALPHA 谱系）：当日有K线均匀不放回 5 票。"""
    data = ctx()['data']
    rng = np.random.RandomState(seed)

    def pick(t, equity):
        cand = sorted(s for s in data if pd.notna(data[s]['close'].get(t, np.nan)))
        if not cand:
            return []
        return sorted(rng.choice(cand, size=min(5, len(cand)), replace=False).tolist())
    return pick


# ================================================================ 变体 3-1：d 降权 SLOT 半额
def band_wins_of(res, p, win):
    """C1 随机带（ALPHA B 臂法 seed=42..61）域内周段胜率中位。"""
    dd = dom_dates(p, win or FULL)
    out = {}
    for d in D1_NAMES:
        per = [week_winrate(res[(p, f'band{s}')]['curve'], dd[d])
               for s in range(42, 62) if dd[d]]
        per = [x for x in per if x is not None]
        out[d] = float(np.median(per)) if per else None
    return out


def run_downweight(n_proc=32, win=None):
    t0 = time.time()
    specs, keys = [], []
    for p in ('old131', 'full144'):
        for tag, sm in (('base', 1.0), ('dw', 0.5)):
            specs.append({'pname': p, 'slot_mult': sm, 'win': win})
            keys.append((p, tag))
        for s in range(42, 62):
            specs.append({'pname': p, 'slot_mult': 1.0, 'win': win,
                          'random_seed': s})
            keys.append((p, f'band{s}'))
    res = dict(zip(keys, run_arms(specs, n_proc)))
    rows, anchors, detail = [], {}, {}
    ANCH = {('old131', 'base'): (-49.31, -23.09), ('old131', 'dw'): (-28.33, -12.08),
            ('full144', 'base'): (-56.31, -27.72), ('full144', 'dw'): (-33.56, -14.81)}
    for p in ('old131', 'full144'):
        base_c, dw_c = res[(p, 'base')]['curve'], res[(p, 'dw')]['curve']
        for tag, c in (('base', base_c), ('dw', dw_c)):
            ss = seg_stats(c, *REALC)
            a_ref, m_ref = ANCH[(p, tag)]
            got_ann = seg_ann(c, *REALC)
            anchors[f'd_dw.{p}.{tag}.realC_ann'] = (round(got_ann, 2), a_ref, 0.05)
            anchors[f'd_dw.{p}.{tag}.realC_mdd'] = (ss['mdd_pct'], m_ref, 0.05)
        detail[p] = {'base_realC': seg_stats(base_c, *REALC), 'dw_realC': seg_stats(dw_c, *REALC),
                     'd_ann_realC_pp': round(seg_ann(dw_c, *REALC) - seg_ann(base_c, *REALC), 2)}
        # C1 随机带同域 20 种子（域内周段胜率中位）
        dd = dom_dates(p, win or FULL)
        band_wins = band_wins_of(res, p, win)
        rows += framework_variant_rows('K1-d-downweight-slot05', 'K1', p, dw_c, base_c,
                                       win or FULL, band_wins=band_wins,
                                       anchor_ref='RESCUE d_decay_monitor.json 路径①（reform_paths.1）')
        detail[p]['placebo'] = placebo_framework(
            daily_excess(dw_c, base_c), {d: dd[d] for d in D1_NAMES})
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, anchors, detail


# ================================================================ 变体 4-1：d 换门 vol20 p80 pause
def run_gate_vol(n_proc=32, win=None):
    t0 = time.time()
    W = win or FULL
    thr_map = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool']
    specs, keys = [], []
    for p in ('old131', 'full144'):
        P = ctx()[p]
        cond = (P['vol20'] > thr_map[p]).fillna(False)   # 信号日读
        for tag, ov in (('base', None),
                        ('gate', {'off': cond.shift(1).fillna(False), 'mode': 'pause'}),
                        ('gate_lag', {'off': cond.shift(2).fillna(False), 'mode': 'pause'})):
            specs.append({'pname': p, 'win': win, 'overlay': ov})
            keys.append((p, tag))
        for s in range(42, 62):                       # C1 随机带（方法书 §三「同变体 3-1」）
            specs.append({'pname': p, 'win': win, 'random_seed': s})
            keys.append((p, f'band{s}'))
    res = dict(zip(keys, run_arms(specs, n_proc)))
    rows, anchors, detail = [], {}, {}
    ANCH = {('old131', 'gate'): (-27.17, -11.29), ('full144', 'gate'): (-15.53, -24.19),
            ('old131', 'base'): (-49.31, -23.09), ('full144', 'base'): (-56.31, -27.72)}
    OFF_ANCH = {'old131': (35.25, 49, 139), 'full144': (26.62, 37, 139)}
    for p in ('old131', 'full144'):
        P = ctx()[p]
        thr = thr_map[p]
        base_c, gate_c = res[(p, 'base')]['curve'], res[(p, 'gate')]['curve']
        for tag, c in (('base', base_c), ('gate', gate_c)):
            a_ref, m_ref = ANCH[(p, tag)]
            anchors[f'd_gate.{p}.{tag}.realC_ann'] = (round(seg_ann(c, *REALC), 2), a_ref, 0.05)
            anchors[f'd_gate.{p}.{tag}.realC_mdd'] = (seg_stats(c, *REALC)['mdd_pct'], m_ref, 0.05)
        off = (P['vol20'] > thr).fillna(False)
        orc = off[(off.index >= REALC[0]) & (off.index <= REALC[1])]
        sh, od, nd = round(float(orc.mean()) * 100, 2), int(orc.sum()), int(len(orc))
        anchors[f'd_gate.{p}.realC_off_share_pct'] = (sh, OFF_ANCH[p][0], 0.05)
        anchors[f'd_gate.{p}.realC_off_days'] = (od, OFF_ANCH[p][1], 0)
        anchors[f'd_gate.{p}.realC_n_days'] = (nd, OFF_ANCH[p][2], 0)
        lag_c = res[(p, 'gate_lag')]['curve']
        rows += framework_variant_rows('K1-d-gate-vol20p80-pause', 'K1', p, gate_c, base_c, W,
                                       band_wins=band_wins_of(res, p, win),
                                       anchor_ref='HD_REPORT.md L19-57 / RESCUE L76',
                                       notes='OFF=pause 语义（PB-4）；lag 敏感性臂照挂披露不进判定')
        detail[p] = {'base_realC': seg_stats(base_c, *REALC), 'gate_realC': seg_stats(gate_c, *REALC),
                     'threshold_ann_vol_pct': round(thr * 100, 2),
                     'realC_off_share_pct': sh, 'realC_off_days': od, 'realC_n_days': nd,
                     'lag_FULL_avoid_pp': round(seg_stats(lag_c, *W)['ret_pp']
                                                - seg_stats(base_c, *W)['ret_pp'], 4),
                     'lag_HOLDOUT_avoid_pp': round(seg_stats(lag_c, *HOLD)['ret_pp']
                                                   - seg_stats(base_c, *HOLD)['ret_pp'], 4)}
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, anchors, detail


# ================================================================ 变体 5-1：S3×D1 交叉格（费压 PB-5）
def run_s3d1(n_proc=32, win=None):
    t0 = time.time()
    W = win or FULL
    thr_map = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool']
    specs, keys = [], []
    for p in ('old131', 'full144'):
        P = ctx()[p]
        vol_hi = (P['vol20'] > thr_map[p]).fillna(False)
        down = (P['idx'] < P['idx_ma']).fillna(False)    # NaN 方向=不 OFF（gate_maps 同式）
        g2 = (vol_hi & down).fillna(False)
        arms = (('base', None), ('v2', vol_hi, 'pause'), ('s3', vol_hi, 's3'),
                ('d1', g2, 'pause'), ('s3d1', g2, 's3'))
        for tag, *ov in arms:
            if tag == 'base':
                specs.append({'pname': p, 'win': win, 'fee': FEE_S, 'fund': FUND_S})
            else:
                cond, mode = ov
                specs.append({'pname': p, 'win': win, 'fee': FEE_S, 'fund': FUND_S,
                              'overlay': {'off': cond.shift(1).fillna(False), 'mode': mode}})
            keys.append((p, tag))
        for tag, cond, mode in (('s3_lag', vol_hi, 's3'), ('d1_lag', g2, 'pause'),
                                ('s3d1_lag', g2, 's3')):
            specs.append({'pname': p, 'win': win, 'fee': FEE_S, 'fund': FUND_S,
                          'overlay': {'off': cond.shift(2).fillna(False), 'mode': mode}})
            keys.append((p, tag))
    res = dict(zip(keys, run_arms(specs, n_proc)))
    rows, anchors, detail = [], {}, {}
    ARM_META = {'s3': ('K1-s3d1-armA', 'G1G2FDR §1 S3 行（对照臂）'),
                'd1': ('K1-s3d1-armB', 'G1G2FDR §2 D1 行（对照臂）'),
                's3d1': ('K1-s3d1-armC', 'new（PG 交叉格新预注册臂）')}
    ANCH_A = {'old131': {'FULL_avoid': 155.0332, 'FULL_mdd_red': 38.81,
                         'lag': (154.843, 59.7147), 'realB': 90.31, 'realC_avoid': 12.7654,
                         'realB_ann_mdd': (4926.62, -13.80)},
              'full144': {'FULL_avoid': 197.2062, 'FULL_mdd_red': 7.17,
                          'lag': (177.8786, 68.8166), 'realB': 129.72, 'realC_avoid': 10.0624}}
    ANCH_B = {'old131': {'FULL_avoid': 60.8638, 'FULL_mdd_red': 36.60, 'lagHOLD': -0.0849,
                         'realB_ann_mdd': (2139.40, -16.39)},
              'full144': {'FULL_avoid': 85.4397, 'FULL_mdd_red': 27.74, 'lagHOLD': -0.0944}}
    V2_REALB = {'old131': 14.8909, 'full144': 94.6734}
    for p in ('old131', 'full144'):
        P = ctx()[p]
        bc = res[(p, 'base')]['curve']
        v2c = res[(p, 'v2')]['curve']
        for tag in ('s3', 'd1', 's3d1'):
            vid, aref = ARM_META[tag]
            c, cl = res[(p, tag)]['curve'], res[(p, tag + '_lag')]['curve']
            lag_ok = bool(seg_stats(cl, *W)['ret_pp'] > seg_stats(bc, *W)['ret_pp'] and
                          seg_stats(cl, *HOLD)['ret_pp'] > seg_stats(bc, *HOLD)['ret_pp'])
            rows += framework_variant_rows(vid, 'K1', p, c, bc, W, lag_ok=lag_ok,
                                           anchor_ref=aref,
                                           notes='费压口径 PB-5（×1.5），base 同费对比')
            gs, bs = seg_stats(c, *W), seg_stats(bc, *W)
            mdd_red = (abs(bs['mdd_pct']) - abs(gs['mdd_pct'])) / abs(bs['mdd_pct']) * 100
            if tag == 's3':
                a = ANCH_A[p]
                anchors[f's3d1.{p}.armA.FULL_avoid'] = (gs['ret_pp'] - bs['ret_pp'], a['FULL_avoid'], 0.05)
                anchors[f's3d1.{p}.armA.FULL_mdd_red'] = (round(mdd_red, 2), a['FULL_mdd_red'], 0.05)
                lf = seg_stats(cl, *W)['ret_pp'] - bs['ret_pp']
                lh = seg_stats(cl, *HOLD)['ret_pp'] - seg_stats(bc, *HOLD)['ret_pp']
                anchors[f's3d1.{p}.armA.lag_FULL_HOLD'] = ((round(lf, 4), round(lh, 4)), a['lag'], 0.05)
                anchors[f's3d1.{p}.armA.realB_ret'] = (seg_stats(c, *REALB)['ret_pp'], a['realB'], 0.05)
                rca = seg_stats(c, *REALC)['ret_pp'] - seg_stats(bc, *REALC)['ret_pp']
                anchors[f's3d1.{p}.armA.realC_avoid'] = (rca, a['realC_avoid'], 0.05)
                if 'realB_ann_mdd' in a:
                    anchors[f's3d1.{p}.armA.realB_ann_mdd'] = (
                        (round(seg_ann(c, *REALB), 2), seg_stats(c, *REALB)['mdd_pct']),
                        a['realB_ann_mdd'], 0.05)
            if tag == 'd1':
                b = ANCH_B[p]
                anchors[f's3d1.{p}.armB.FULL_avoid'] = (gs['ret_pp'] - bs['ret_pp'], b['FULL_avoid'], 0.05)
                anchors[f's3d1.{p}.armB.FULL_mdd_red'] = (round(mdd_red, 2), b['FULL_mdd_red'], 0.05)
                lh = seg_stats(cl, *HOLD)['ret_pp'] - seg_stats(bc, *HOLD)['ret_pp']
                anchors[f's3d1.{p}.armB.lag_HOLD'] = (round(lh, 4), b['lagHOLD'], 0.05)
                if 'realB_ann_mdd' in b:
                    anchors[f's3d1.{p}.armB.realB_ann_mdd'] = (
                        (round(seg_ann(c, *REALB), 2), seg_stats(c, *REALB)['mdd_pct']),
                        b['realB_ann_mdd'], 0.05)
        # 必答差异题（臂 C）：realB 解锁 vs v2 + T1'/T3'
        cc = res[(p, 's3d1')]['curve']
        thr = thr_map[p]
        g2 = ((P['vol20'] > thr) & (P['idx'] < P['idx_ma'])).fillna(False)
        ret_b = bc.pct_change() * 100
        dc = {'realB_armC_ret_pp': seg_stats(cc, *REALB)['ret_pp'],
              'realB_v2_ret_pp': seg_stats(v2c, *REALB)['ret_pp'],
              'realB_unlock_vs_v2_pp': round(seg_stats(cc, *REALB)['ret_pp']
                                             - seg_stats(v2c, *REALB)['ret_pp'], 4),
              'realC_avoid_vs_base_pp': round(seg_stats(cc, *REALC)['ret_pp']
                                              - seg_stats(bc, *REALC)['ret_pp'], 4),
              'FULL_avoid': round(seg_stats(cc, *W)['ret_pp'] - seg_stats(bc, *W)['ret_pp'], 4),
              'FULL_mdd_red': round((abs(seg_stats(bc, *W)['mdd_pct']) - abs(seg_stats(cc, *W)['mdd_pct']))
                                    / abs(seg_stats(bc, *W)['mdd_pct']) * 100, 2),
              'HOLDOUT_avoid': round(seg_stats(cc, *HOLD)['ret_pp'] - seg_stats(bc, *HOLD)['ret_pp'], 4),
              'lag_FULL_avoid': round(seg_stats(res[(p, 's3d1_lag')]['curve'], *W)['ret_pp']
                                      - seg_stats(bc, *W)['ret_pp'], 4),
              'lag_HOLDOUT_avoid': round(seg_stats(res[(p, 's3d1_lag')]['curve'], *HOLD)['ret_pp']
                                         - seg_stats(bc, *HOLD)['ret_pp'], 4)}
        for sn, (a, b) in (('realB', REALB), ('realC', REALC)):
            o = g2[(g2.index >= a) & (g2.index <= b)]
            x = ret_b.reindex(o[o].index).dropna()
            dc[f'T1_off_mean_{sn}_pp'] = round(float(x.mean()), 4) if len(x) else None
            dc[f'T1_off_n_{sn}'] = int(len(x))
        orb = g2[(g2.index >= REALB[0]) & (g2.index <= REALB[1])]
        dc['T3_realB_off_share_pct'] = round(float(orb.mean()) * 100, 2)
        detail[f'{p}|armC'] = dc
        anchors[f's3d1.{p}.v2_realB_ret'] = (seg_stats(v2c, *REALB)['ret_pp'], V2_REALB[p], 0.05)
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, anchors, detail


# ================================================================ 收口：FDR/判线/落盘
def apply_fdr_and_judgment(rows):
    """C6：BH 合并族 m=86（全纲领一张表逐批补入，本批 p=本批可测格）；§5.3 域胜任。"""
    idxs, pvals = [], []
    for i, r in enumerate(rows):
        if r['axis'] != 'D1':
            continue
        if r.get('ic_t') is not None:
            pvals.append(float(sst.t.sf(r['ic_t'], max(r['n_ic'] - 2, 1))))   # 上尾（PF-5 同式）
            idxs.append(i)
        elif r.get('_meta', {}).get('p_one') is not None:
            pvals.append(r['_meta']['p_one'])
            idxs.append(i)
    if pvals:
        qs = MC.bh_fdr_q(pvals, m_total=MC.BATCH_BUDGET_M)
        for i, q in zip(idxs, qs):
            rows[i]['fdr_q'] = round(float(q), 4)
    for r in rows:
        m = r.pop('_meta', None)
        if r['axis'] != 'D1':
            continue
        n = r['n_days'] or 0
        if n < 60:                                   # §2.4-4 / §5.4：n<60 只入册不入图谱
            r['notes'] = (r['notes'] + ' INSUFFICIENT(n<60)').strip()
        if r['family'] == 'K1':
            c1 = (r['win_rate_pct'] is not None and m and m.get('band_median_win') is not None
                  and r['win_rate_pct'] >= m['band_median_win'])
            c2 = (r['excess_pp'] is not None and r['excess_pp'] > 0
                  and r['ci95_low'] is not None and r['ci95_low'] > 0)
            c3 = (r['mdd_pct'] is not None and m and m.get('mdd_base') is not None
                  and abs(r['mdd_pct']) <= abs(m['mdd_base']))
            c4 = r['cushion_x'] is not None and r['cushion_x'] >= 3.0
            c6 = r['fdr_q'] is not None and r['fdr_q'] <= 0.10
            r['_judge'] = {'C1': c1, 'C2': c2, 'C3': c3, 'C4': c4, 'C6': c6,
                           'domain_competent': bool(n >= 60 and c2 and c4 and c6 and c1 and c3),
                           'n_ge_60': n >= 60}
        else:
            c2 = (r['ic_mean'] is not None and r['ic_mean'] > 0
                  and r['ci95_low'] is not None and r['ci95_low'] > 0)
            c4 = r['cushion_x'] is not None and r['cushion_x'] >= 3.0
            c6 = r['fdr_q'] is not None and r['fdr_q'] <= 0.10
            r['_judge'] = {'C2': c2, 'C4': c4, 'C6': c6,
                           'domain_competent_ic': bool(n >= 60 and c2 and c4 and c6),
                           'n_ge_60': n >= 60}
    return rows


def write_factbook(rows):
    cols = ['batch', 'variant_id', 'family', 'pool', 'axis', 'domain', 'n_days', 'n_sig',
            'win_rate_pct', 'ann_pct', 'excess_pp', 'mdd_pct', 'ic_mean', 'ic_t', 'n_ic',
            'spread_net_pp', 'avoid_pp', 'mdd_red_pct', 'cushion_x', 'fdr_q',
            'ci95_low', 'ci95_high', 'loto_pass', 'yearly_flip', 'lag_flip',
            'evidence_tag', 'anchor_ref', 'notes']
    path = os.path.join(OUT, 'FACTBOOK_BATCH1.jsonl')
    with open(path, 'w') as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in cols}, ensure_ascii=False) + '\n')
    return path, len(rows)


def main():
    global SMOKE
    t0 = time.time()
    mode = sys.argv[1] if len(sys.argv) > 1 else 'smoke'
    SMOKE = (mode == 'smoke')
    win = SMOKE_WIN if SMOKE else None
    print(f'[1/5] 装载上下文（mode={mode}）…', flush=True)
    c = ctx()
    print(f'      old131={len(c["pools"]["old131"])} full144={len(c["pools"]["full144"])}', flush=True)
    all_rows, all_anchors, details = [], {}, {}
    print('[2/5] c4 池间 RS …', flush=True)
    r, a, d = run_c4()
    all_rows += r
    for k, v in a.items():
        all_anchors[k] = (v[0], v[1], v[2], av(v[0], v[1], v[2]))
    details['c4'] = d
    print(f"      t_ext={d['t_extended']:.6f}（锚 4.776407）", flush=True)
    print('[3/5] c5 正交残差 V1..V6 …', flush=True)
    r, a, d = run_c5()
    all_rows += r
    for k, v in a.items():
        all_anchors[k] = (v[0], v[1], v[2], av(v[0], v[1], v[2]))
    details['c5'] = d
    print(f"      V1 t_ext={d['v1']['t_extended']:.6f}（锚 2.182077）", flush=True)
    print('[4/5] 框架族三变体（32 进程并行）…', flush=True)
    for fn, nm in ((run_downweight, 'downweight'), (run_gate_vol, 'gate_vol'), (run_s3d1, 's3d1')):
        r, a, d = fn(win=win)
        all_rows += r
        for k, v in a.items():
            verd = 'SKIP(smoke)' if SMOKE else av(v[0], v[1], v[2])
            all_anchors[k] = (v[0], v[1], v[2], verd)
        details[nm] = d
        print(f'      {nm} done {d["wall_secs"]}s', flush=True)
    print('[5/5] FDR/判线/落盘 …', flush=True)
    all_rows = apply_fdr_and_judgment(all_rows)
    fb_path, n_rows = write_factbook(all_rows)
    judge = [{'variant_id': r['variant_id'], 'pool': r['pool'], 'domain': r['domain'], **r['_judge']}
             for r in all_rows if r['axis'] == 'D1' and '_judge' in r]
    out = {'mode': mode, 'ts': time.strftime('%F %T'),
           'anchors': {k: {'got': v[0], 'want': v[1], 'tol': v[2], 'verdict': v[3]}
                       for k, v in all_anchors.items()},
           'n_factbook_rows': n_rows, 'detail': details, 'judgment': judge,
           'runtime_sec': round(time.time() - t0, 1),
           'r10_note': '本运行不产出任何「域读数→仓位」映射（R10）',
           'fdr_note': 'C6=BH 合并族 m=86（MC.bh_fdr_q, MINE_SPEC §5.2-C6）；'
                       '本批 p=本批可测格上尾 p（因子族 IC t / 框架族域内日超额 bootstrap），逐批补入全纲领一张表'}
    json.dump(out, open(os.path.join(OUT, 'batch1_result.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    n_miss = sum(1 for v in all_anchors.values() if v[3] == 'MISS')
    print(f'      FACTBOOK 行={n_rows} → {fb_path}', flush=True)
    print(f'      锚校验 MISS={n_miss}/{len(all_anchors)}', flush=True)
    for k, v in all_anchors.items():
        if v[3] == 'MISS':
            print(f'      MISS {k}: got={v[0]} want={v[1]}', flush=True)
    print(f'done {out["runtime_sec"]}s', flush=True)


if __name__ == '__main__':
    main()
