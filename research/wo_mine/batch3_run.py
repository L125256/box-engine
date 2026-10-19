#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch 3 · 框架 5 族 38 变体 + 图谱收口（MINE_SPEC_v1 §四 框架清单逐字，禁加号）
====================================================================================
K1 轮动增强 12（d 降权 3 档 / d 换门 3 配置 / S3×D1 交叉格 6——已跑 8 格确定性重放做
   D2 深挖层，4 个新格 D1 全套）/ K2 均值回归 6（引用 Q2 域先验参数带，终裁前置①）/
   K3 突破分域重审 6（brk 冻结臂 R1 参数一行不动）/ K4 事件驱动 6 / K5 fd 另类出场 8
   （fd 冻结臂 V-FD-A/E2/refresh 入场逻辑一行不动，审计红线）。
R10 红线：本件域标签只作离线研究分层，任何函数不产出「域读数→仓位」映射。
判线：全部引用 MINE_SPEC_v1 §五（C1–C6 / §5.3 / BH 合并族 m=86 / 双池同向 §5.4 /
   n<60 只入册 §2.4-4），本件零新增判线数字。p 值补 m=86 合并表（只补表）。
已烧窗口禁触（MINE_SPEC §六批次纪律）：fd/brk realC 终验已烧——K3/K5 不出 REALC 轴行，
   域格内 2026-06 后数字=图谱记账引用，不构成二次终验（FULL 行注登记）。
用法：
  python3 batch3_run.py d0                        # 仅 D0 闸
  python3 batch3_run.py smoke K1|K2|K3|K4|K5      # 每族冒烟（截断窗 2026-08-01→10-17，R8）
  python3 batch3_run.py full  K1|K2|K3|K4|K5 [i n]  # 全量分族（K3/K5 支持分片 [i/n]）
  python3 batch3_run.py assemble                  # FACTBOOK_BATCH3 + FDR m=86 合并表
产出：batch3_partial_K*.json / FACTBOOK_BATCH3.jsonl / FDR_MERGED_M86.jsonl（重建全表）/
      batch3_result.json / ATLAS_v1.json / ATLAS_v1.md
"""
import json
import os
import subprocess
import sys
import time
from multiprocessing import get_context

import numpy as np
import pandas as pd
import scipy.stats as sst

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mine_common as MC
import batch1_run as B1

OUT = MC.OUT_DIR
FULL = B1.FULL
REALB = B1.REALB
REALC = B1.REALC
HOLD = B1.HOLD
SMOKE_WIN = B1.SMOKE_WIN
D1N = MC.D1_NAMES
D2N = ['宽低费', '宽高费', '中低费', '中高费', '窄低费', '窄高费']
N_PROC = 32
COLS = ['batch', 'variant_id', 'family', 'pool', 'axis', 'domain', 'n_days', 'n_sig',
        'win_rate_pct', 'ann_pct', 'excess_pp', 'mdd_pct', 'ic_mean', 'ic_t', 'n_ic',
        'spread_net_pp', 'avoid_pp', 'mdd_red_pct', 'cushion_x', 'fdr_q',
        'ci95_low', 'ci95_high', 'loto_pass', 'yearly_flip', 'lag_flip',
        'evidence_tag', 'anchor_ref', 'notes']
_OPS = '【口径操作化·R7 登记·MINE_SPEC §四 未逐字定义处提请终裁】'
PRIOR_REF = 'Q2_PRIOR_BANDS.json（batch2 Q2 域先验参数带，终裁前置①落盘引用）'

_CTX = None


def ctx():
    global _CTX
    if _CTX is None:
        _CTX = MC.build_ctx()
        dom = json.load(open(os.path.join(OUT, 'domains.json')))
        B1._D1 = {'full144': dom['labels']['d1']}
        _D2['full144'] = dom['labels']['d2']
    return _CTX


_D2 = {}


def d2_labels(pname):
    """D2 域标签（lag1，domains.json 冻结）。D2 锚=full144 冻结分位（MINE_SPEC §2.2 落盘口径，
    无逐池 D2 锚）→ 双池共用 full144 冻结标签（行注登记）。"""
    ctx()  # 触发装载
    return _D2['full144']


def dom_dates_gen(pname, win, labels):
    P = ctx()[pname]
    out = {}
    for t in P['cal']:
        if not (win[0] <= t <= win[1]):
            continue
        v = labels.get(str(t.date()))
        if v is not None:
            out.setdefault(v, []).append(t)
    return out


# ================================================================ D0 闸（Batch 1/2 同谱系）
def d0_gate():
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(OUT, 'batch0_domains.py')],
                       capture_output=True, text=True)
    res = json.load(open(os.path.join(OUT, 'D0_RESULT.json')))
    ok = bool(r.returncode == 0 and res.get('all_pass') is True)
    out = {'pass': ok, 'returncode': r.returncode, 'd0_all_pass': res.get('all_pass'),
           'd0_runtime_sec': res.get('runtime_sec'), 'gate_runtime_sec': round(time.time() - t0, 1),
           'lineage': 'batch0_domains.py 四对拍（Batch 1/2 同谱系，停工条款逐字适用）'}
    json.dump(out, open(os.path.join(OUT, 'd0_gate_batch3.json'), 'w'),
              ensure_ascii=False, indent=1)
    print(f"D0 闸：all_pass={res.get('all_pass')} → {'放行' if ok else '停工'}", flush=True)
    return ok


# ================================================================ 行构建（§七 27 字段；batch=batch3）
def fw_rows(vid, family, pname, arm_curve, base_curve, win, axis='D1', labels=None,
            band_wins=None, anchor_ref='new', notes=''):
    """框架族域行（batch1 framework_variant_rows 同构扩展：axis/labels 参数化；batch=batch3）。
    labels=None → D1 冻结标签（batch1.d1_labels）。"""
    rows = []
    if labels is None:
        labels = B1.d1_labels(pname)
    dd = dom_dates_gen(pname, win, labels)
    ex = B1.daily_excess(arm_curve, base_curve)
    for d in sorted(dd):
        dom_d = dd[d]
        if not dom_d:
            continue
        r_arm = arm_curve.pct_change().reindex(dom_d).dropna()
        r_bse = base_curve.pct_change().reindex(dom_d).dropna()
        ex_d = ex.reindex(dom_d).dropna()
        wr = B1.week_winrate(arm_curve, dom_d)
        wr_b = B1.week_winrate(base_curve, dom_d)
        ann_a = B1.seg_ann(arm_curve, dom_d[0], dom_d[-1])
        ann_b = B1.seg_ann(base_curve, dom_d[0], dom_d[-1])
        excess = None if (ann_a is None or ann_b is None) else ann_a - ann_b
        mdd_a = MC.mdd_of(r_arm) if len(r_arm) else None
        mdd_b = MC.mdd_of(r_bse) if len(r_bse) else None
        ci = MC.stationary_boot(ex_d.values) if len(ex_d) >= 5 else np.array([])
        cushion = None
        if len(ex_d) >= 5 and len(ex) > len(ex_d):
            bmed = float(np.median(MC.perm_baseline(ex.values, len(dom_d))))
            if bmed != 0:
                cushion = float(np.mean(ex_d.values)) / bmed
        P = ctx()[pname]
        n_sig = sum(1 for t in P['sig_days']
                    if P['cal'].get_loc(t) + 1 < len(P['cal'])
                    and P['cal'][P['cal'].get_loc(t) + 1] in set(dom_d))
        rows.append({'batch': 'batch3', 'variant_id': vid, 'family': family,
                     'pool': pname, 'axis': axis, 'domain': d,
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
                     'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                     'evidence_tag': '【实证】', 'anchor_ref': anchor_ref, 'notes': notes,
                     '_meta': {'win_rate_base': None if wr_b is None else round(wr_b, 2),
                               'band_median_win': None if not band_wins else band_wins.get(d),
                               'mdd_base': None if mdd_b is None else round(mdd_b, 2),
                               'p_one': B1.boot_p_one_sided(ex_d.values) if len(ex_d) >= 5 else 1.0,
                               'ci_obj': '域内日超额（臂−base）均值 95% CI'}})
    gs, bs = B1.seg_stats(arm_curve, *win), B1.seg_stats(base_curve, *win)
    mdd_red = ((abs(bs['mdd_pct']) - abs(gs['mdd_pct'])) / abs(bs['mdd_pct']) * 100
               if bs['mdd_pct'] != 0 else None)
    ex_f = ex[(ex.index >= win[0]) & (ex.index <= win[1])]
    if axis == 'D1':
        ci = MC.stationary_boot(ex_f.values) if len(ex_f) >= 5 else np.array([])
        rows.append({'batch': 'batch3', 'variant_id': vid, 'family': family, 'pool': pname,
                     'axis': 'FULL', 'domain': 'all', 'n_days': gs['n_days'], 'n_sig': None,
                     'win_rate_pct': None, 'ann_pct': round(B1.seg_ann(arm_curve, *win), 2),
                     'excess_pp': None, 'mdd_pct': gs['mdd_pct'],
                     'ic_mean': None, 'ic_t': None, 'n_ic': None, 'spread_net_pp': None,
                     'avoid_pp': round(gs['ret_pp'] - bs['ret_pp'], 4),
                     'mdd_red_pct': None if mdd_red is None else round(mdd_red, 2),
                     'cushion_x': None, 'fdr_q': None,
                     'ci95_low': round(float(np.percentile(ci, 2.5)), 4) if ci.size else None,
                     'ci95_high': round(float(np.percentile(ci, 97.5)), 4) if ci.size else None,
                     'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                     'evidence_tag': '【实证】', 'anchor_ref': anchor_ref,
                     'notes': (notes + ' 对照列：avoid=臂段净收益−base 段净收益（PB-7）；'
                               'mdd_red=PB-8；CI 对象=FULL 窗日超额').strip(),
                     '_meta': {'p_one': B1.boot_p_one_sided(ex_f.values) if len(ex_f) else 1.0}})
    return rows


def trade_rows(vid, family, trades, notes='', axis_rows=('D1', 'FULL'), full_note=''):
    """事件式族（K3/K5）域行：ic_mean 字段承载「单笔 R 均值（%）」（字段复用登记）；
    n_sig=域内入场笔数；win_rate_pct=笔胜率；CI/p=域内日 R 合计序列 stationary boot /
    boot_p_one_sided。无净值曲线 → ann/excess/mdd 空（如实）。"""
    lab = B1.d1_labels('full144')
    rows = []
    by_dom = {d: {'days': set(), 'rs': [], 'daily': {}} for d in D1N}
    all_daily = {}
    for tr in trades:
        t = pd.Timestamp(tr['et'])
        g = lab.get(str(t.date()))
        r = float(tr['r'])
        all_daily[t] = all_daily.get(t, 0.0) + r
        if g in by_dom:
            by_dom[g]['days'].add(t)
            by_dom[g]['rs'].append(r)
            by_dom[g]['daily'][t] = by_dom[g]['daily'].get(t, 0.0) + r
    for d in D1N:
        if d not in by_dom:
            continue
        rs = by_dom[d]['rs']
        dl = sorted(by_dom[d]['daily'].items())
        dv = np.array([v for _, v in dl], dtype=float)
        n_days_dom = len(by_dom[d]['days'])
        ci = MC.stationary_boot(dv) if len(dv) >= 5 else np.array([])
        cushion = None
        if len(dv) >= 5 and len(all_daily) > len(dv):
            bmed = float(np.median(MC.perm_baseline(np.array(list(all_daily.values())), len(dv))))
            if bmed != 0:
                cushion = float(dv.mean()) / bmed
        p = B1.boot_p_one_sided(dv) if len(dv) >= 5 else 1.0
        mean_r = float(np.mean(rs)) if rs else None
        win_pct = float(np.mean([r > 0 for r in rs]) * 100) if rs else None
        rows.append({'batch': 'batch3', 'variant_id': vid, 'family': family,
                     'pool': 'full144', 'axis': 'D1', 'domain': d,
                     'n_days': int(n_days_dom), 'n_sig': int(len(rs)),
                     'win_rate_pct': None if win_pct is None else round(win_pct, 2),
                     'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
                     'ic_mean': None if mean_r is None else round(mean_r, 4),
                     'ic_t': None, 'n_ic': None, 'spread_net_pp': None,
                     'avoid_pp': None, 'mdd_red_pct': None,
                     'cushion_x': None if cushion is None else round(cushion, 2),
                     'fdr_q': None,
                     'ci95_low': None if not ci.size else round(float(np.percentile(ci, 2.5)), 6),
                     'ci95_high': None if not ci.size else round(float(np.percentile(ci, 97.5)), 6),
                     'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                     'evidence_tag': '【实证】', 'anchor_ref': 'new',
                     'notes': notes + '；事件式族：ic_mean 字段=单笔 R 均值%（字段复用），'
                                      'n_sig=入场笔数，win=笔胜率，CI/p=域内日 R 合计序列'
                                      '（无净值曲线，ann/excess/mdd 空）',
                     '_meta': {'p_one': p, 'sum_r': round(float(np.sum(rs)), 2) if rs else 0.0,
                               'ci_obj': '域内日 R 合计均值 95% CI'}})
    if 'FULL' in axis_rows:
        rs = [float(t['r']) for t in trades]
        dv = np.array([v for _, v in sorted(all_daily.items())], dtype=float)
        ci = MC.stationary_boot(dv) if len(dv) >= 5 else np.array([])
        rows.append({'batch': 'batch3', 'variant_id': vid, 'family': family, 'pool': 'full144',
                     'axis': 'FULL', 'domain': 'all',
                     'n_days': int(len(all_daily)), 'n_sig': int(len(rs)),
                     'win_rate_pct': round(float(np.mean([r > 0 for r in rs]) * 100), 2) if rs else None,
                     'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
                     'ic_mean': round(float(np.mean(rs)), 4) if rs else None,
                     'ic_t': None, 'n_ic': None, 'spread_net_pp': None,
                     'avoid_pp': None, 'mdd_red_pct': None, 'cushion_x': None, 'fdr_q': None,
                     'ci95_low': round(float(np.percentile(ci, 2.5)), 4) if ci.size else None,
                     'ci95_high': round(float(np.percentile(ci, 97.5)), 4) if ci.size else None,
                     'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                     'evidence_tag': '【实证】', 'anchor_ref': 'new',
                     'notes': notes + '；' + full_note,
                     '_meta': {'p_one': B1.boot_p_one_sided(dv) if len(dv) else 1.0,
                               'sum_r': round(float(np.sum(rs)), 2) if rs else 0.0}})
    return rows


# ================================================================ K1 轮动增强（12）
def _w_sim(spec):
    tf = B1.rand_target_fn(spec['random_seed']) if spec.get('random_seed') is not None else None
    return MC.simulate(ctx(), spec['pname'], slot_mult=spec.get('slot_mult', 1.0),
                       overlay=spec.get('overlay'), lineage='gate', win=spec.get('win'),
                       fee=spec.get('fee'), fund=spec.get('fund'), target_fn=tf)


K1_EXIST_D1 = ['K1-d-downweight-slot05', 'K1-d-gate-vol20p80-pause',
               'K1-s3d1-armA', 'K1-s3d1-armB', 'K1-s3d1-armC']


def run_arms(specs, n_proc=N_PROC):
    with get_context('fork').Pool(min(n_proc, len(specs))) as pool:
        return pool.map(_w_sim, specs)


def run_k1(win, smoke):
    """新 4 格 D1 全套（base+C1 随机带 20 种子共享）+ 已跑 8 格确定性重放 D2 深挖。
    重放校验：FULL avoid/mdd_red vs FACTBOOK_BATCH1 同键行（±0.01）不过即停工。"""
    t0 = time.time()
    thr80 = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool']
    # 换门 p70 阈值：谱系窗 LN_REALA 逐池自算，先落盘后回放（同 batch0 p80 先例）
    thr70 = {p: float(ctx()[p]['vol20'][(ctx()[p]['vol20'].index >= MC.LN_REALA[0]) &
                                        (ctx()[p]['vol20'].index <= MC.LN_REALA[1])].quantile(0.7))
             for p in ('old131', 'full144')}
    specs, keys = [], []
    for p in ('old131', 'full144'):
        P = ctx()[p]
        cond80 = (P['vol20'] > thr80[p]).fillna(False)
        cond70 = (P['vol20'] > thr70[p]).fillna(False)
        # 新 4 格臂（默认现行费率，同 batch1 降权/换门口径；降权三档=slot_mult 谱系 0.75/0.5/0.25）
        specs.append({'pname': p, 'win': win}); keys.append((p, 'base'))
        specs.append({'pname': p, 'slot_mult': 0.75, 'win': win}); keys.append((p, 'dw075'))
        specs.append({'pname': p, 'slot_mult': 0.25, 'win': win}); keys.append((p, 'dw025'))
        specs.append({'pname': p, 'slot_abs': None, 'win': win,
                      'overlay': {'off': cond70.shift(1).fillna(False), 'mode': 'pause'}})
        keys.append((p, 'gate70'))
        specs.append({'pname': p, 'slot_abs': None, 'win': win,
                      'overlay': {'off': cond80.shift(2).fillna(False), 'mode': 'pause'}})
        keys.append((p, 'gate80lag1'))
        # 重放臂（已跑 8 格 D2 深挖需要曲线）：dw05 / gate80 / 费压交叉 5 臂
        specs.append({'pname': p, 'slot_mult': 0.5, 'win': win}); keys.append((p, 'dw05'))
        specs.append({'pname': p, 'slot_abs': None, 'win': win,
                      'overlay': {'off': cond80.shift(1).fillna(False), 'mode': 'pause'}})
        keys.append((p, 'gate80'))
        for tag, cond, mode in (('v2', cond80, 'pause'), ('s3', cond80, 's3'),
                                ('d1', cond80 & (P['idx'] < P['idx_ma']).fillna(False), 'pause'),
                                ('s3d1', cond80 & (P['idx'] < P['idx_ma']).fillna(False), 's3')):
            specs.append({'pname': p, 'win': win, 'fee': B1.FEE_S, 'fund': B1.FUND_S,
                          'overlay': {'off': cond.shift(1).fillna(False), 'mode': mode}})
            keys.append((p, tag))
        specs.append({'pname': p, 'win': win, 'fee': B1.FEE_S, 'fund': B1.FUND_S})
        keys.append((p, 'base_s'))
        for s in range(42, 62):   # C1 随机带（ALPHA B 臂法，新 4 格共用）
            specs.append({'pname': p, 'win': win, 'random_seed': s})
            keys.append((p, f'band{s}'))
    res = dict(zip(keys, run_arms(specs)))
    rows, detail = [], {'gate_p70_by_pool_frozen': {p: round(thr70[p], 6) for p in thr70},
                        'gate_p80_by_pool_ref': thr80, 'replay_check': {}}
    lab_d2 = {p: d2_labels(p) for p in ('old131', 'full144')}
    NEW = [('K1-d-downweight-slot075', 'dw075', 'MINE_SPEC §4.1 降权三档 SLOT 0.075/0.05/0.025 '
            '（0.05 已 batch1 跑，本件补 0.075/0.025，slot_mult 0.75/0.25 谱系）', 'dw'),
           ('K1-d-downweight-slot025', 'dw025', 'MINE_SPEC §4.1 降权三档（第三档）', 'dw'),
           ('K1-d-gate-vol20p70-pause', 'gate70', 'MINE_SPEC §4.1 换门配置 vol20 p70 pause'
            '（逐池 P70 阈值谱系窗先落盘后回放，见 detail.gate_p70_by_pool_frozen）', 'gate'),
           ('K1-d-gate-vol20p80-pause-lag1', 'gate80lag1', 'MINE_SPEC §4.1 换门配置 p80+lag1'
            '（门信号 shift(2)=执行日读前二日状态；batch1 lag 臂为披露不判分，本格为预算内变体）', 'gate')]
    for p in ('old131', 'full144'):
        base_c = res[(p, 'base')]['curve']
        dd = B1.dom_dates(p, win or FULL)
        band_wins = {}
        for d in D1N:
            per = [B1.week_winrate(res[(p, f'band{s}')]['curve'], dd[d])
                   for s in range(42, 62) if dd[d]]
            per = [x for x in per if x is not None]
            band_wins[d] = float(np.median(per)) if per else None
        for vid, tag, nt, kind in NEW:
            rows += fw_rows(vid, 'K1', p, res[(p, tag)]['curve'], base_c, win or FULL,
                            band_wins=band_wins, notes=nt + '；' + _OPS)
            dd = B1.dom_dates(p, win or FULL)
            detail.setdefault(vid, {})[p] = {
                'placebo': B1.placebo_framework(B1.daily_excess(res[(p, tag)]['curve'], base_c),
                                                {d: dd[d] for d in D1N})}
        # 重放 D2 深挖：已跑 8 格（降权/换门/交叉 3 臂 ×2 池）
        for vid, tag in (('K1-d-downweight-slot05', 'dw05'), ('K1-d-gate-vol20p80-pause', 'gate80'),
                         ('K1-s3d1-armA', 's3'), ('K1-s3d1-armB', 'd1'), ('K1-s3d1-armC', 's3d1')):
            bcur = base_c if tag in ('dw05', 'gate80') else res[(p, 'base_s')]['curve']
            rc = res[(p, tag)]['curve']
            rows += fw_rows(vid, 'K1', p, rc, bcur, win or FULL, axis='D2',
                            labels=lab_d2[p],
                            notes='D2 深挖层（宽×费六格，MINE_SPEC §2.2）：引用重放 batch1 变体'
                                  '（同代码路径/seed 确定性复现，非 D1 判线重跑，不占重跑配额）；'
                                  'D2 只入事实手册不入图谱判分（MINE_SPEC §5.4 图谱=D1）')
            if win is None:
                gs, bs = B1.seg_stats(rc, *FULL), B1.seg_stats(bcur, *FULL)
                mdd_red = ((abs(bs['mdd_pct']) - abs(gs['mdd_pct'])) / abs(bs['mdd_pct']) * 100
                           if bs['mdd_pct'] != 0 else None)
                detail['replay_check'][f'{vid}|{p}'] = {
                    'replay_FULL_avoid': round(gs['ret_pp'] - bs['ret_pp'], 4),
                    'replay_mdd_red': None if mdd_red is None else round(mdd_red, 2)}
    # 重放确定性校验 vs batch1 FACTBOOK FULL 行
    fb1 = [json.loads(l) for l in open(os.path.join(OUT, 'FACTBOOK_BATCH1.jsonl'))]
    chk_all = True
    for r in fb1:
        if r['axis'] != 'FULL' or r['family'] != 'K1' or r['variant_id'] not in K1_EXIST_D1:
            continue
        k = f"{r['variant_id']}|{r['pool']}"
        rc = detail['replay_check'].get(k)
        if rc is None:
            continue
        d_av = abs(rc['replay_FULL_avoid'] - r['avoid_pp'])
        d_mr = None if (rc['replay_mdd_red'] is None or r['mdd_red_pct'] is None) \
            else abs(rc['replay_mdd_red'] - r['mdd_red_pct'])
        ok = d_av <= 0.01 and (d_mr is None or d_mr <= 0.01)
        rc.update({'batch1_avoid': r['avoid_pp'], 'batch1_mdd_red': r['mdd_red_pct'],
                   'verdict': 'hit' if ok else 'MISS'})
        chk_all = chk_all and ok
    detail['replay_check_all'] = 'hit' if chk_all else 'MISS'
    if not chk_all:
        raise SystemExit('K1 重放确定性校验 MISS——停工（同切分重跑配额纪律，禁带病出数）')
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, detail


# ================================================================ K2 均值回归（6）
def k2_simulate(pname, depth, hold, volconf=False, weak_only=False, win=None):
    """个股事件式均值回归（MINE_SPEC §4.2）：急跌（单日 ret1<−depth）后次日开盘入场，
    硬止损 −8% 盘中 + 时间出场（持有 hold 交易日后次日口径=入场后第 hold 根 K 开盘）。
    仓位=entry 时点权益 10%（DE.SLOT 谱系），可并发，受现金约束；费 FEE_SIDE/FUNDING。
    【_OPS】触发=单日收盘收益（「N 日累计」档未启用：预算 6 格分配给深度×持有×确认×域过滤，
    MINE_SPEC §4.2 变体清单逐字）；缺开盘价顺延至有价日开盘；域过滤=入场日 D1(lag1)∈{弱稳,弱躁}。"""
    P = ctx()[pname]
    cal_all = P['cal']
    if win is not None:
        cal = cal_all[(cal_all >= win[0]) & (cal_all <= win[1])]
    else:
        cal = cal_all
    C, O, L, V, mark = P['close'], P['open_'], P['low'], P['mark'], P['mark']
    V = P.get('vol_panel')
    if V is None:
        V = pd.DataFrame({s: ctx()['data'][s]['volume'] for s in P['syms']}).reindex(cal_all)
        ctx()[pname]['vol_panel'] = V
    ret1 = C.pct_change()
    vma = V.rolling(20).mean()
    lab = B1.d1_labels(pname)
    trig = (ret1 < -depth)
    if volconf:
        trig = trig & (V > vma)
    cash, pos, eq = 1.0, {}, {}
    for i, t in enumerate(cal):
        o_t, lo_t, mk_t = O.loc[t], L.loc[t], mark.loc[t]
        # 1) 持仓出场：止损（盘中/开盘触发）→ 时间出场（开盘）
        for s in list(pos):
            pp = pos[s]
            stop_p = pp['entry'] * (1 + MC.DE.STOP)
            px = None
            if pd.notna(o_t.get(s, np.nan)) and o_t[s] <= stop_p:
                px = o_t[s]
            elif pd.notna(lo_t.get(s, np.nan)) and lo_t[s] <= stop_p:
                px = stop_p
            elif i - pp['ei'] >= hold:
                px = o_t[s] if pd.notna(o_t.get(s, np.nan)) else mk_t.get(s, np.nan)
            if px is not None and pd.notna(px):
                cash += pp['qty'] * px * (1 - MC.DE.FEE_SIDE)
                del pos[s]
        # 2) 入场：昨日触发 → 今日开盘
        if i > 0:
            tp = trig.loc[cal[i - 1]]
            if weak_only:
                g = lab.get(str(t.date()))
                tp = tp & (g in ('弱稳', '弱躁'))
            eq_prev = eq[cal[i - 1]] if cal[i - 1] in eq else 1.0
            for s in P['syms']:
                if not bool(tp.get(s, False)) or s in pos:
                    continue
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    continue
                budget = min(MC.DE.SLOT * eq_prev, max(cash, 0.0))
                if budget <= 0:
                    continue
                qty = budget / px
                cash -= qty * px * (1 + MC.DE.FEE_SIDE)
                pos[s] = {'qty': qty, 'entry': px, 'ei': i}
        # 3) 收盘记账 + 资金费
        equity = cash
        for s, pp in pos.items():
            m = mk_t.get(s, np.nan)
            if pd.isna(m):
                m = 0.0
            equity += pp['qty'] * m
            f = pp['qty'] * m * MC.DE.FUNDING
            cash -= f
        eq[t] = equity
    return pd.Series(eq).sort_index()


def base_curve(pname, win=None):
    """K2/K4 参照臂：池等权 idx 买入持有（C2 参照「池等权同域」，MINE_SPEC §5.2）。"""
    P = ctx()[pname]
    idx = P['idx']
    if win is not None:
        idx = idx[(idx.index >= win[0]) & (idx.index <= win[1])]
    return idx / idx.iloc[0]


def run_k2(win, smoke):
    t0 = time.time()
    prior = json.load(open(os.path.join(OUT, 'Q2_PRIOR_BANDS.json')))
    hl = prior['prior_bands']['Q2-ar1-hl-ret']
    hl_note = (f"先验引用：AR1 半衰期域带（{PRIOR_REF}，batch2 落盘值）牛稳 {hl['牛稳']['mean']:.1f} 日"
               f"/牛躁 {hl['牛躁']['mean']:.1f}/弱稳 {hl['弱稳']['mean']:.1f}(n={hl['弱稳']['n']}<60 INSUFFICIENT)"
               f"/弱躁 {hl['弱躁']['mean']:.1f} → 持有 5/10 日双档覆盖快回归域，上限不与牛稳慢回归冲突")
    VS = [
        ('K2-mr-d5-h5', dict(depth=0.05, hold=5), '急跌深度 −5% 单日 × 持有 5 日'),
        ('K2-mr-d5-h10', dict(depth=0.05, hold=10), '急跌深度 −5% 单日 × 持有 10 日'),
        ('K2-mr-d8-h5', dict(depth=0.08, hold=5), '急跌深度 −8% 单日 × 持有 5 日'),
        ('K2-mr-d8-h10', dict(depth=0.08, hold=10), '急跌深度 −8% 单日 × 持有 10 日'),
        ('K2-mr-d5-h5-volconf', dict(depth=0.05, hold=5, volconf=True),
         '急跌 −5% + 量能确认（V>V20 均值）× 持有 5 日'),
        ('K2-mr-d8-h10-domweak', dict(depth=0.08, hold=10, weak_only=True),
         '急跌 −8% × 持有 10 日 + 域过滤（仅弱域=弱稳/弱躁，MINE_SPEC §4.2「仅弱域测试」）'),
    ]
    rows, detail = [], {'prior_ref': PRIOR_REF, 'prior_band_ar1_hl': hl}
    for p in ('old131', 'full144'):
        bc = base_curve(p, win)
        for vid, cfg, desc in VS:
            ac = k2_simulate(p, win=win, **cfg)
            nt = f'{desc}；{hl_note}' if vid == 'K2-mr-d5-h5' else f'{desc}；先验引用={PRIOR_REF}'
            rr = fw_rows(vid, 'K2', p, ac, bc, win or FULL, notes=nt + '；' + _OPS)
            rows += rr
            dd = B1.dom_dates(p, win or FULL)
            detail.setdefault(vid, {})[p] = {
                'placebo': B1.placebo_framework(B1.daily_excess(ac, bc), {d: dd[d] for d in D1N})}
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, detail


# ================================================================ K3 突破分域重审（6）
def brk_panels():
    """brk 面板（brk_cond_run.panels 最小子集，f6/费档不建——本件不用）。
    谱系：wo_fdbrk/brk_cond_run.py:19-35 同式；池/牛闸=common_fdbrk.pool_bull（D0 已对拍）。"""
    sys.path.insert(0, '/workspace/repo_ready/research/wo_fdbrk')
    import common_fdbrk as CF
    pool, bull, idxv = CF.pool_bull()
    if 'pan' in brk_panels.__dict__:
        return brk_panels.pan
    rows = {c: pd.DataFrame({t: {b['time']: b[c] for b in bars} for t, bars in pool.items()}
                            ).sort_index() for c in ('open', 'high', 'low', 'close', 'volume')}
    pan = dict(O=rows['open'], H=rows['high'], L=rows['low'], C=rows['close'], V=rows['volume'])
    ma50 = pan['C'].rolling(50, min_periods=50).mean()
    pan['breadth'] = ((pan['C'] > ma50).sum(axis=1) / pan['C'].notna().sum(axis=1)) >= 0.40
    brk_panels.pan = pan
    brk_panels.pool = pool
    return pan


def brk_scan(pan, pool, gate_extra=None, confirm=0, cfg=None):
    """brk 冻结臂扫描（wo_fdbrk/brk_cond_run.py scan_brk_tk/_open 逐字 import 复用；
    R1 红线：entry=next_open / tp R3 / stop atr / hardcap 30 / win20 / vr1.5 一行不动）。
    gate_extra=信号日集合过滤（D1 域过滤用，full144 D1 lag1 标签）。交易窗=fd/brk 谱系
    MAIN=2025-06-01 起（与 B1.FULL 06-02 差一日，谱系窗口径优先，_OPS 登记）。"""
    import brk_cond_run as BR
    cfg = cfg or dict(entry='next_open', tp_mode='R3', stop_mode='atr', hardcap=30)
    gate = pan['breadth']
    sig, _ = BR.sig_arrs(pan, 20, 1.5)
    trs = []
    for tk, bars in pool.items():
        dts = np.array([b['time'] for b in bars])
        gd = set(dts[gate.reindex(dts).fillna(False).values])
        if gate_extra is not None:
            gd = {t for t in gd if t in gate_extra}
        for t in BR.scan_brk_tk(bars, None, gd, confirm=confirm, **cfg):
            trs.append(dict(tkr=tk, **t))
    return [t for t in trs if t['et'] >= '2025-06-01']


def short_mirror_events(pan, weak_only=False, win_n=20):
    """空头镜像事件研究（R9 排除册候选承接，MINE_SPEC §4.3）：20 日新低 + 量比>1.5；
    事件收益=做空 fwd5（−fwd5）【事件研究口径，非可部署净值，_OPS 登记】。"""
    C, L, V = pan['C'], pan['L'], pan['V']
    newlow = C <= L.rolling(win_n, min_periods=win_n).min().shift(1)
    vr = V / V.rolling(win_n, min_periods=win_n).mean()
    sig = newlow & (vr > 1.5)
    lab = B1.d1_labels('full144')
    if weak_only:
        weak = {'弱稳', '弱躁'}
    else:
        weak = {'牛稳', '牛躁', '弱稳', '弱躁'}
    f5 = C.shift(-5) / C - 1
    ev = []
    for t in C.index[(sig.sum(axis=1) > 0)]:
        if str(t)[:10] < '2025-06-01':
            continue
        if lab.get(str(pd.Timestamp(t).date())) not in weak:
            continue
        xs = sig.loc[t]
        ys = f5.loc[t]
        mm = xs & ys.notna()
        for s in xs.index[mm]:
            ev.append({'et': t, 'tkr': s, 'r': float(-ys[s]) * 100})
    return ev


def run_k3(win=None, smoke=False, shard=(0, 1)):
    """K3 六变体。win/smoke 仅保持接口一致——brk 冻结臂 R1 参数一行不动，冒烟=截断交易日
    集（只裁 et，禁改参数）；full 时 shard 分片变体清单（R8）。"""
    t0 = time.time()
    pan = brk_panels()
    pool = brk_panels.pool
    lab = B1.d1_labels('full144')
    bulls = {'牛稳': {d for d in pan['C'].index if lab.get(str(pd.Timestamp(d).date())) == '牛稳'},
             '牛躁': {d for d in pan['C'].index if lab.get(str(pd.Timestamp(d).date())) == '牛躁'}}
    VID = ['K3-brk-frozen-breadth', 'K3-brk-domfilter-niuwen', 'K3-brk-domfilter-niunao',
           'K3-brk-short-mirror-20', 'K3-brk-short-mirror-20-weak', 'K3-brk-pullback-confirm']
    lo, hi = shard
    seg = VID[lo::hi]
    rows, detail = [], {}
    if 'K3-brk-frozen-breadth' in seg:
        trs = brk_scan(pan, pool)
        rows += trade_rows('K3-brk-frozen-breadth', 'K3', trs,
                           notes='brk 冻结臂（breadth 门版 entry=next_open/R3/atr/30/win20/vr1.5，'
                                 'brk_result.json frozen_base+final.cfg 逐字）分域记账：不重调参纯图谱重切'
                                 '（R1 参数一行不动；MINE_SPEC §4.3 变体①）',
                           full_note='realC 窗数字=图谱记账引用（fd/brk realC 已烧，禁二次终验，'
                                     'MINE_SPEC §六批次纪律）')
        detail['K3-brk-frozen-breadth'] = {'n_trades': len(trs)}
    if 'K3-brk-domfilter-niuwen' in seg:
        trs = brk_scan(pan, pool, gate_extra=bulls['牛稳'])
        rows += trade_rows('K3-brk-domfilter-niuwen', 'K3', trs,
                           notes='突破+域过滤（仅牛稳；MINE_SPEC §4.3 变体②；域过滤依据=' + PRIOR_REF
                                 + ' Hurst-trend 牛稳 0.6217 最高=趋势持续性最强域）',
                           full_note='realC 图谱记账引用（同上禁二次终验）')
        detail['K3-brk-domfilter-niuwen'] = {'n_trades': len(trs)}
    if 'K3-brk-domfilter-niunao' in seg:
        trs = brk_scan(pan, pool, gate_extra=bulls['牛躁'])
        rows += trade_rows('K3-brk-domfilter-niunao', 'K3', trs,
                           notes='突破+域过滤（仅牛躁；MINE_SPEC §4.3 变体③；' + PRIOR_REF + '）',
                           full_note='realC 图谱记账引用（同上禁二次终验）')
        detail['K3-brk-domfilter-niunao'] = {'n_trades': len(trs)}
    if 'K3-brk-short-mirror-20' in seg:
        ev = short_mirror_events(pan, weak_only=False)
        rows += trade_rows('K3-brk-short-mirror-20', 'K3', ev,
                           notes='空头镜像事件研究：20 日新低+量比>1.5，事件收益=−fwd5'
                                 '（R9 排除册 n=2534 候选承接；MINE_SPEC §4.3 变体④；'
                                 '【事件研究口径非可部署净值，_OPS】）')
        detail['K3-brk-short-mirror-20'] = {'n_events': len(ev)}
    if 'K3-brk-short-mirror-20-weak' in seg:
        ev = short_mirror_events(pan, weak_only=True)
        rows += trade_rows('K3-brk-short-mirror-20-weak', 'K3', ev,
                           notes='空头镜像+域过滤（仅弱域=弱稳/弱躁；MINE_SPEC §4.3 变体⑤；'
                                 '【事件研究口径非可部署净值，_OPS】）')
        detail['K3-brk-short-mirror-20-weak'] = {'n_events': len(ev)}
    if 'K3-brk-pullback-confirm' in seg:
        trs = brk_scan(pan, pool, confirm=3)
        rows += trade_rows('K3-brk-pullback-confirm', 'K3', trs,
                           notes='回踩确认分域：冻结臂+confirm=3（信号后 3 bar 内回踩 level 入场，'
                                 'scan_brk_tk pend 语义逐字；MINE_SPEC §4.3 变体⑥；'
                                 'confirm 窗 3 bar=【_OPS】）',
                           full_note='realC 图谱记账引用（同上禁二次终验）')
        detail['K3-brk-pullback-confirm'] = {'n_trades': len(trs)}
    detail['wall_secs'] = round(time.time() - t0, 1)
    detail['shard'] = list(shard)
    return rows, detail


# ================================================================ K4 事件驱动（6）
def crash_recovery_off(pname, win=None, wait_ma=20):
    """崩市→重入窗：med_ret<−5% 崩市日起，至 idx 收复 MA(wait_ma) 日（不含）为 OFF（pause）。"""
    P = ctx()[pname]
    cal = P['cal']
    idx, ma = P['idx'], P['idx'].rolling(wait_ma).mean()
    med = P['med_ret']
    off = pd.Series(False, index=cal)
    in_crash = False
    for t in cal:
        crash = bool(pd.notna(med.get(t, np.nan)) and med[t] < MC.DE.CRASH_MED)
        if crash:
            in_crash = True
        if in_crash:
            off[t] = True
            if pd.notna(ma.get(t, np.nan)) and idx[t] >= ma[t]:
                in_crash = False
    return off


def gate_switch_sim(pname, sameday, win=None):
    """闸切换日执行节奏自定义引擎（gate 谱系骨架 + 闸关清仓两节奏；_OPS 首次定义）：
    - 周信号日（ISO 首日）闸开→top5 目标次日开盘成交（gate 谱系逐字）；闸关→空目标；
    - 闸关清仓：sameday=切换日收盘价全清（费 FEE_SIDE）；else=挂单次日开盘（alpha 5b 谱系）；
    - 止损 −8% 盘中 / 崩市闸 med_ret<−5% 次日开盘清仓照抄 gate 谱系。"""
    P = ctx()[pname]
    cal_all = P['cal']
    cal = cal_all[(cal_all >= win[0]) & (cal_all <= win[1])] if win else cal_all
    C, O, L, mark = P['close'], P['open_'], P['low'], P['mark']
    idx, idx_ma, med_ret, sig_days = P['idx'], P['idx_ma'], P['med_ret'], P['sig_days']
    g = (idx >= idx_ma)   # NaN→False（闸关）
    cash, pos, eq = 1.0, {}, {}
    pending_sells = set()
    pending_exec = None
    prev_g = {}
    cal_list = list(cal)
    for i, t in enumerate(cal_list):
        o_t, lo_t = O.loc[t], L.loc[t]
        for s in list(pos):                                   # 止损
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            stop_p = pos[s]['entry'] * (1 + MC.DE.STOP)
            if o_t[s] <= stop_p:
                px = o_t[s]
            elif pd.notna(lo_t.get(s, np.nan)) and lo_t[s] <= stop_p:
                px = stop_p
            else:
                continue
            q = pos[s]['qty']
            cash += q * px * (1 - MC.DE.FEE_SIDE)
            del pos[s]
        for s in list(pending_sells):                          # 挂单清仓
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                q = pos[s]['qty']
                cash += q * px * (1 - MC.DE.FEE_SIDE)
                del pos[s]
            pending_sells.discard(s)
        if i > 0:
            pt = cal_list[i - 1]
            prev_g[t] = bool(g[pt]) if pd.notna(g[pt]) else False
        g_t = bool(g[t]) if pd.notna(g[t]) else False
        if sameday and i > 0 and (not g_t) and prev_g.get(t, True) and pos:
            # 闸切换日当日收盘清仓
            for s in list(pos):
                px = C.at[t, s]
                if pd.isna(px):
                    pending_sells.add(s)
                    continue
                q = pos[s]['qty']
                cash += q * px * (1 - MC.DE.FEE_SIDE)
                del pos[s]
        elif (not sameday) and i > 0 and (not g_t) and prev_g.get(t, True):
            pending_sells.update(pos.keys())                   # 次日开盘（alpha 5b 谱系）
        if pending_exec is not None and t == pending_exec[0]:
            _, target = pending_exec
            pending_exec = None
            for s in list(pos):
                if s in target or s in pending_sells:
                    continue
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    pending_sells.add(s)
                    continue
                q = pos[s]['qty']
                cash += q * px * (1 - MC.DE.FEE_SIDE)
                del pos[s]
            slot = MC.DE.SLOT
            eq_sig = cash + sum(p['qty'] * mark.at[t, s] for s, p in pos.items() if pd.notna(mark.at[t, s]))
            for s in target:
                if s in pos:
                    continue
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    continue
                budget = min(slot * eq_sig, max(cash, 0.0))
                if budget <= 0:
                    continue
                qty = budget / px
                cash -= qty * px * (1 + MC.DE.FEE_SIDE)
                pos[s] = {'qty': qty, 'entry': px}
        equity = cash
        for s, pp in pos.items():
            m = mark.at[t, s]
            equity += pp['qty'] * m
            cash -= pp['qty'] * m * MC.DE.FUNDING
        eq[t] = equity
        if len(pos) > 0 and pd.notna(med_ret.get(t, np.nan)) and med_ret[t] < MC.DE.CRASH_MED:
            pending_sells.update(pos.keys())
        if t in sig_days:
            target = [] if not g_t else list(
                MC.DE.cross_scores(ctx()['F'], P['syms'], t, MC.DE.FACTORS_4).index[:MC.DE.TOP_N])
            pending_exec = (cal_list[i + 1], target) if i + 1 < len(cal_list) else None
    return pd.Series(eq).sort_index()


def run_k4(win, smoke):
    t0 = time.time()
    rows, detail = [], {}
    turn_anchor = {}
    for p in ('old131', 'full144'):
        P = ctx()[p]
        bc = base_curve(p, win)
        # ① 崩市后重入 2：次日（=既有周调节奏立即恢复，gate 谱系 base 语义）vs 待 idx 收复 MA20
        base_c = dict(zip([(p, 'base')], B1.run_arms(
            [{'pname': p, 'win': win}], 1)))[(p, 'base')]['curve']
        rr = fw_rows('K4-reentry-nextday', 'K4', p, base_c, bc, win or FULL,
                     notes='崩市后重入①「次日」：gate 谱系无重入限制（崩市清仓后下一信号日即恢复'
                           '建仓，=base 臂逐字；MINE_SPEC §4.4 变体①）')
        rows += rr
        off = crash_recovery_off(p, win, wait_ma=20)
        arm = B1.run_arms([{'pname': p, 'win': win,
                            'overlay': {'off': off.shift(1).fillna(False), 'mode': 'pause'}}], 1)[0]
        rows += fw_rows('K4-reentry-ma20', 'K4', p, arm['curve'], base_c, win or FULL,
                        notes='崩市后重入②「待 idx 收复 MA20」：崩市日起 pause，收复 MA20 次执行日'
                              '恢复（MINE_SPEC §4.4 变体②；MA20=【_OPS】逐字承接纲领文本）')
        dd = B1.dom_dates(p, win or FULL)
        plc = B1.placebo_framework(B1.daily_excess(arm['curve'], base_c), {d: dd[d] for d in D1N})
        detail.setdefault('K4-reentry-ma20', {})[p] = {'placebo': plc}
        # ② 闸切换日执行节奏 2
        for vid, sd in (('K4-gateexec-sameday', True), ('K4-gateexec-nextopen', False)):
            ac = gate_switch_sim(p, sd, win)
            rows += fw_rows(vid, 'K4', p, ac, base_c, win or FULL,
                            notes=('闸切换日当日收盘清仓' if sd else '闸切换日次日开盘清仓（alpha 5b 谱系）')
                                  + '；base=gate 谱系无闸清仓对照（差异含整个闸关出场机制，两节奏之差'
                                    '为执行节奏答题主体；MINE_SPEC §4.4 变体③④；_OPS）')
            ac2 = ac
            detail.setdefault(vid, {})[p] = {
                'placebo': B1.placebo_framework(B1.daily_excess(ac2, base_c), {d: dd[d] for d in D1N})}
        # ③ 费压代理跳变后换手降档 2：turn_med 上穿 MS_REALA P80（先落盘后回放）
        tn = P['turn_med']
        p80 = float(tn[(tn.index >= MC.MS_REALA[0]) & (tn.index <= MC.MS_REALA[1])].quantile(0.8))
        turn_anchor[p] = round(p80, 6)
        fee_hi = (tn > p80).fillna(False)
        for vid, mode, desc in (('K4-feeproxy-pause', 'pause', '跳变周暂停开新仓与换仓卖出'),
                                ('K4-feeproxy-halfslot', 's3', '跳变周半额开仓+跳过卖出（换手降档）')):
            arm = B1.run_arms([{'pname': p, 'win': win,
                                'overlay': {'off': fee_hi.shift(1).fillna(False), 'mode': mode}}], 1)[0]
            rows += fw_rows(vid, 'K4', p, arm['curve'], base_c, win or FULL,
                            notes=f'费压代理=turn_med 上穿 MS_REALA P80（先落盘后回放 p80={p80:.6f}）；'
                                  f'{desc}；MINE_SPEC §4.4 变体⑤⑥；_OPS')
            detail.setdefault(vid, {})[p] = {
                'placebo': B1.placebo_framework(B1.daily_excess(arm['curve'], base_c),
                                                {d: dd[d] for d in D1N})}
    detail['turn_med_p80_frozen'] = turn_anchor
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, detail


# ================================================================ K5 fd 另类出场（8）
def scan_fd_exit(bars, bullmap, exit_fn, N=15):
    """fd 冻结臂入场逐字（fd_indep_run.scan_fd_indep V-FD-A/N15/refresh 路径；审计红线：
    入场逻辑一行不动），仅出场经 exit_fn 注入。exit_fn(bars, ei, ep, eff, a)→(xi, xpx, why, r)。"""
    import eng_final as ENG
    a = ENG.atrs(bars)
    trades = []
    last_frame = None
    i = max(N, 20, 14) + 1
    n = len(bars)
    while i < n:
        if a[i] is None:
            i += 1; continue
        t = bars[i]['time']
        if not bool(bullmap.get(t)):
            i += 1; continue
        px = bars[i]['close']; lo = bars[i]['low']
        w = bars[i - N + 1:i + 1]
        L_ = min(x['low'] for x in w); H_ = max(x['high'] for x in w); rng = H_ - L_
        fire = (lo <= L_ + 0.2 * rng) and (px > L_)
        frame = (round(L_, 10), round(H_, 10))
        if fire:
            ok = (last_frame is None) or (frame != last_frame)      # refresh 语义
            eff = L_ - 0.3 * a[i]
            risk = (px - L_) / px * 100
            if ok and eff > 0 and px > eff and risk <= 8.0:
                ep = px
                xi, xpx, why, r = exit_fn(bars, i, ep, eff, a[i])
                trades.append(dict(ep=ep, ei=i, xi=xi, xc=round(xpx, 4), r=r, why=why,
                                   et=t, xt=bars[xi]['time']))
                last_frame = frame
                i = xi + 1
                continue
            elif ok:
                last_frame = frame
        i += 1
    return trades


def _fd_exit_fns(catr_frozen=3.5669):
    """8 个出场变体的出场函数（V2 可实现口径逐字：收盘判定触发+触发价与 open 顺延+费 0.03%/bar，
    common_fdbrk.v2_exit 谱系；审计红线：仅出场结构改动，入场零改动）。"""
    import common_fdbrk as CF
    FEE = CF.FEE

    def v2(bars, ei, ep, tp, eff, hardcap):
        return CF.v2_exit(bars, ei, ep, tp, eff, hardcap)

    def mk_partial(breakeven):
        def fn(bars, ei, ep, eff, A):
            n = len(bars)
            half_done = False
            r_acc = 0.0
            w = [1.0, 1.0]   # 两半仓权重记账（各按各自出场 R）
            eff2 = ep if breakeven else eff   # 余仓 eff（保本上移【_OPS】）
            tp = ep + catr_frozen * A
            i = ei
            while i < n:
                i += 1
                if i >= n:
                    break
                px = bars[i]['close']
                if not half_done and px >= ep + 3.0 * (ep - eff):   # +3R 出半（收盘判定）
                    xpx = px
                    j = i
                    while j < n - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                        j += 1; xpx = bars[j]['open']
                    r1 = (xpx - ep) / ep * 100 - FEE * (j - ei)
                    r_acc += 0.5 * r1
                    half_done = True
                    i = j
                    continue
                if px <= (eff2 if half_done else eff) or px >= tp or i - ei >= 30:
                    if px >= tp: xpx = max(tp, bars[i]['open'])
                    elif px <= (eff2 if half_done else eff): xpx = min(eff2 if half_done else eff, bars[i]['open'])
                    else: xpx = px
                    j = i
                    while j < n - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                        j += 1; xpx = bars[j]['open']
                    r2 = (xpx - ep) / ep * 100 - FEE * (j - ei)
                    r = r_acc + (0.5 * r2 if half_done else r2)
                    return j, xpx, ('分批+3R' + ('/保本' if breakeven else '') +
                                    ('/止盈' if px >= tp else ('/止损' if px <= (eff2 if half_done else eff) else '/硬顶'))), r
            i = n - 1
            r2 = (bars[i]['close'] - ep) / ep * 100 - FEE * (i - ei)
            return i, bars[i]['close'], '数据末', r_acc + (0.5 * r2 if half_done else r2)
        return fn

    def mk_time(hardcap):
        def fn(bars, ei, ep, eff, A):
            tp = ep + catr_frozen * A
            return v2(bars, ei, ep, tp, eff, hardcap)
        return fn

    def mk_atr(catr):
        def fn(bars, ei, ep, eff, A):
            tp = ep + catr * A
            return v2(bars, ei, ep, tp, eff, 30)
        return fn

    def mix(bars, ei, ep, eff, A):
        # 混合（时间+ATR）：ATR 目标 2× 与时间 20 bar 先到者【_OPS】
        tp = ep + 2.0 * A
        return v2(bars, ei, ep, tp, eff, 20)

    def ctrl(bars, ei, ep, eff, A):
        return v2(bars, ei, ep, ep + catr_frozen * A, eff, 30)   # 出场不变对照（冻结臂 E2）

    return {
        'K5-fd-exit-ctrl': ctrl,
        'K5-fd-exit-partial3r-keep': mk_partial(False),
        'K5-fd-exit-partial3r-breakeven': mk_partial(True),
        'K5-fd-exit-time20': mk_time(20),
        'K5-fd-exit-time45': mk_time(45),
        'K5-fd-exit-atr2': mk_atr(2.0),
        'K5-fd-exit-atr3': mk_atr(3.0),
        'K5-fd-exit-mix-timeatr': mix,
    }
FD_EXIT_DESC = {
    'K5-fd-exit-ctrl': '出场不变对照（冻结臂 E2 catr=3.5669/hardcap30 逐字；锚=fd_result final n=1802/sum_r=2125.96）',
    'K5-fd-exit-partial3r-keep': '分批止盈①：+3R 收盘判定出半、余仓原 tp/eff 跟踪',
    'K5-fd-exit-partial3r-breakeven': '分批止盈②：+3R 出半、余仓 eff 上移至保本（【_OPS】）',
    'K5-fd-exit-time20': '时间出场 20 bar（hardcap=20，E2 tp 不变）',
    'K5-fd-exit-time45': '时间出场 45 bar（hardcap=45）',
    'K5-fd-exit-atr2': 'ATR 目标 2×（E2 同构 catr=2.0；【_OPS】固定目标非动态跟踪，与冻结臂可对拍）',
    'K5-fd-exit-atr3': 'ATR 目标 3×（catr=3.0；【_OPS】同上）',
    'K5-fd-exit-mix-timeatr': '混合（时间+ATR）：ATR 2× 目标 ∧ 20 bar 先到者（【_OPS】）',
}


def _fd_worker(job):
    vid, = job
    sys.path.insert(0, '/workspace/repo_ready/research/wo_fdbrk')
    sys.path.insert(0, '/tmp/eng_wt_rc')
    import common_fdbrk as CF
    pool, bull, idxv = CF.pool_bull()
    fns = _fd_exit_fns()
    trs = []
    for tk, bars in pool.items():
        for t in scan_fd_exit(bars, bull, fns[vid]):
            trs.append(dict(tkr=tk, **t))
    main = [t for t in trs if t['et'] >= CF.MAIN]
    return vid, main


def run_k5(win=None, smoke=False, shard=(0, 1)):
    t0 = time.time()
    VID = list(FD_EXIT_DESC.keys())
    lo, hi = shard
    seg = [(v,) for v in VID[lo::hi]]
    with get_context('fork').Pool(min(N_PROC, len(seg))) as p:
        out = p.map(_fd_worker, seg)
    rows, detail = [], {}
    for vid, trs in out:
        note = FD_EXIT_DESC[vid] + '；fd 冻结臂入场逻辑一行不动（审计红线），判死结论不改'
        if vid == 'K5-fd-exit-ctrl':
            note += '；R5 抢救义务正面执行：出场=唯一未穷举自由度（MINE_SPEC §4.5）'
        rows += trade_rows(vid, 'K5', trs, notes=note,
                           full_note='realC 窗数字=图谱记账引用（fd realC 终验已烧验后即烧，'
                                     'MINE_SPEC §六批次纪律；本行不构成二次终验）')
        detail[vid] = {'n_trades': len(trs)}
    detail['wall_secs'] = round(time.time() - t0, 1)
    detail['shard'] = list(shard)
    return rows, detail


# ================================================================ K5 锚校验（ctrl 变体）
def k5_ctrl_anchor(rows):
    fd = json.load(open('/workspace/repo_ready/research/wo_fdbrk/fd_result.json'))
    want = fd['final']['main']
    r = [x for x in rows if x['variant_id'] == 'K5-fd-exit-ctrl' and x['axis'] == 'FULL']
    if not r:
        return None
    got_n, got_sum, got_mean = r[0]['n_sig'], r[0]['_meta']['sum_r'], r[0]['ic_mean']
    # §0.5 容差换算：pp 类 ±0.05 为单值口径；sum_r 为 n 笔合计 → ±0.05×n（batch1 vintage 漂移同先例）
    ok = (got_n == want['n'] and abs(got_mean - want['mean']) <= 0.05
          and abs(got_sum - want['sum_r']) <= 0.05 * want['n'])
    return {'anchor': 'fd_result.json final.main（fd_indep 终验 n=1802/sum_r=2125.96/mean=1.1798）',
            'got': {'n': got_n, 'sum_r': got_sum, 'mean': got_mean}, 'want': want,
            'tol': '笔数逐位 / mean ±0.05 / sum_r ±0.05×n（§0.5 换算）',
            'vintage_note': ('n=1802 逐位、mean 差 %.4f（«±0.05）；sum 差源自 vintage 微漂移'
                             '（batch1 同先例，锚不改）' % abs(got_mean - want['mean'])),
            'verdict': 'hit' if ok else 'MISS'}


RUNNERS = {'K1': run_k1, 'K2': run_k2, 'K3': run_k3, 'K4': run_k4, 'K5': run_k5}
SHARDABLE = {'K3', 'K5'}
BUDGET = {'K1': 12, 'K2': 6, 'K3': 6, 'K4': 6, 'K5': 8}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'smoke'
    fam = sys.argv[2] if len(sys.argv) > 2 else 'K1'
    shard = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) >= 6 else (0, 1)
    t0 = time.time()
    if mode == 'd0':
        sys.exit(0 if d0_gate() else 3)
    if mode == 'smoke':
        win, smoke = SMOKE_WIN, True
        print(f'[smoke] {fam} 截断窗 {win[0].date()}~{win[1].date()}（R8 冒烟）', flush=True)
    elif mode == 'full':
        if not d0_gate():
            sys.exit(3)
        win, smoke = None, False
        print(f'[full] {fam} 全量（预算 {BUDGET[fam]} 变体，shard {shard}）', flush=True)
    elif mode == 'assemble':
        assemble()
        return
    else:
        raise SystemExit(f'unknown mode {mode}')
    rows, detail = RUNNERS[fam](win=win, smoke=smoke, shard=shard) \
        if fam in SHARDABLE else RUNNERS[fam](win, smoke)
    n_v = len({r['variant_id'] for r in rows})
    print(f'      变体={n_v} 行={len(rows)} {detail["wall_secs"]}s', flush=True)
    if mode == 'full':
        path = os.path.join(OUT, f'batch3_partial_{fam}.json')
        if fam in SHARDABLE and shard != (0, 1) and os.path.exists(path):
            old = json.load(open(path))
            seen = {r['variant_id'] for r in old['rows']}
            rows = old['rows'] + [r for r in rows if r['variant_id'] not in seen]
            old['detail'].update({k: v for k, v in detail.items() if k != 'rows'})
            detail = old['detail']
        json.dump({'family': fam, 'rows': rows, 'detail': detail,
                   'ts': time.strftime('%F %T')}, open(path, 'w'),
                  ensure_ascii=False, indent=1, default=str)
        print(f'      → batch3_partial_{fam}.json', flush=True)
    print(f'done {round(time.time() - t0, 1)}s', flush=True)


# ================================================================ assemble：FACTBOOK+FDR+锚+图谱
def assemble():
    t0 = time.time()
    print('[assemble] 合并五族 + FDR m=86 + K5 锚校验 + ATLAS …', flush=True)
    rows, details = [], {}
    for fam in ('K1', 'K2', 'K3', 'K4', 'K5'):
        path = os.path.join(OUT, f'batch3_partial_{fam}.json')
        if not os.path.exists(path):
            print(f'      {fam}: MISSING（如实登记，未跑）', flush=True)
            details[fam] = {'status': 'MISSING'}
            continue
        part = json.load(open(path))
        rows += part['rows']
        details[fam] = part['detail']
        print(f"      {fam}: 变体 {len(set(r['variant_id'] for r in part['rows']))} "
              f"行 {len(part['rows'])}", flush=True)
    # K5 ctrl 锚校验（须在 _meta 出清前）
    k5a = k5_ctrl_anchor(rows)
    if k5a:
        print(f"      K5 ctrl 锚：{k5a['verdict']} (n={k5a['got']['n']}/want {k5a['want']['n']})",
              flush=True)
    rows = apply_fdr_and_judgment(rows)
    judge3 = [{'variant_id': r['variant_id'], 'pool': r['pool'], 'domain': r['domain'],
               **r['_judge']} for r in rows if r['axis'] == 'D1' and '_judge' in r]
    json.dump({'ts': time.strftime('%F %T'), 'judgment': judge3},
              open(os.path.join(OUT, 'batch3_judgment.json'), 'w'), ensure_ascii=False, indent=1)
    for r in rows:
        r.pop('_meta', None)
    fb3 = os.path.join(OUT, 'FACTBOOK_BATCH3.jsonl')
    with open(fb3, 'w') as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in COLS}, ensure_ascii=False) + '\n')
    # FDR m=86 合并表：既有表（batch1+batch2 格，p 随行）+ batch3 全部 D1 格 → BH 全表重算
    cells = []
    seen = set()
    for l in open(os.path.join(OUT, 'FDR_MERGED_M86.jsonl')):
        cc = json.loads(l)
        k = (cc['batch'], cc['variant_id'], cc['pool'], cc['domain'])
        if k not in seen:
            seen.add(k)
            cells.append(cc)
    b3_cells = [{'batch': 'batch3', 'variant_id': r['variant_id'], 'pool': r['pool'],
                 'domain': r['domain'], 'p': r['_p3'],
                 'p_kind': r['_p_kind']} for r in rows
                if r['axis'] == 'D1' and r.get('_p3') is not None]
    cells += [c for c in b3_cells if (c['batch'], c['variant_id'], c['pool'], c['domain']) not in seen]
    qs = MC.bh_fdr_q([c['p'] for c in cells], m_total=MC.BATCH_BUDGET_M)
    qmap = {}
    with open(os.path.join(OUT, 'FDR_MERGED_M86.jsonl'), 'w') as f:
        for c, q in zip(cells, qs):
            c['q_merged'] = round(float(q), 6)
            qmap[(c['batch'], c['variant_id'], c['pool'], c['domain'])] = c['q_merged']
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    for r in rows:
        if r['axis'] == 'D1':
            r['fdr_q'] = qmap.get(('batch3', r['variant_id'], r['pool'], r['domain']))
    with open(fb3, 'w') as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in COLS}, ensure_ascii=False) + '\n')
    n_q = int(sum(1 for q in qs if q <= 0.10))
    # 双实现对拍登记（batch3_repl.py 产出；缺件如实登记）
    rp = os.path.join(OUT, 'batch3_repl_result.json')
    dual = json.load(open(rp)) if os.path.exists(rp) else \
        {'status': 'MISSING', 'note': 'batch3_repl_result.json 缺件，如实登记'}
    res = {'ts': time.strftime('%F %T'),
           'budget': {'K1': 12, 'K2': 6, 'K3': 6, 'K4': 6, 'K5': 8, 'total': 38,
                      'note': 'MINE_SPEC §4.6 冻结预算逐字；全纲领 86=Batch1 16+Batch2 34+Batch3 38'},
           'n_factbook_rows_batch3': len(rows),
           'k5_ctrl_anchor': k5a,
           'fdr_merged': {'m_total': MC.BATCH_BUDGET_M, 'n_cells_total': len(cells),
                          'n_cells_batch3': len(b3_cells), 'n_q_le_010': n_q,
                          'note': 'BH 合并族 m=86 全纲领一张表逐批补入（本批重建全表：batch1+2 既有格'
                                  ' p 原值 + batch3 格 p），禁止分批放宽'},
           'd0_gate': json.load(open(os.path.join(OUT, 'd0_gate_batch3.json'))),
           'dual_impl_check': dual,
           'r10_note': '本运行不产出任何「域读数→仓位」映射（R10）',
           'ruling_note': 'm=86 正式判读不在本单——待首席终裁统一判读（用户工单⑥）',
           'judgment': judge3,
           'detail': details, 'runtime_sec': round(time.time() - t0, 1)}
    json.dump(res, open(os.path.join(OUT, 'batch3_result.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    print(f'      FACTBOOK_BATCH3 行={len(rows)}；FDR 合并表 {len(cells)} 格（q≤0.10 共 {n_q}）',
          flush=True)
    build_atlas()
    print(f'done {res["runtime_sec"]}s', flush=True)


def apply_fdr_and_judgment(rows):
    """C6 补表 p（框架=域内日超额/R 合计 boot p_one）+ §5.3 格级胜任判定（本批收口）。"""
    for r in rows:
        if r['axis'] == 'D1' and r.get('_meta', {}).get('p_one') is not None:
            r['_p3'] = float(r['_meta']['p_one'])
            r['_p_kind'] = 'boot_p_one_sided（域内日超额/日R合计 ≤0 频率，块长10 B1000 seed42）'
    for r in rows:
        m = r.pop('_meta', None)
        if r['axis'] != 'D1':
            continue
        n = r['n_days'] or 0
        if n < 60:
            r['notes'] = (r['notes'] + ' INSUFFICIENT(n<60)').strip()
        if m is None:
            continue
        c1 = (r['win_rate_pct'] is not None and m.get('band_median_win') is not None
              and r['win_rate_pct'] >= m['band_median_win']) if 'band_median_win' in m else None
        c2 = (r['excess_pp'] is not None and r['excess_pp'] > 0
              and r['ci95_low'] is not None and r['ci95_low'] > 0)
        if c2 is False and r.get('ic_mean') is not None:
            c2 = (r['ic_mean'] > 0 and r['ci95_low'] is not None and r['ci95_low'] > 0)
        c3 = (r['mdd_pct'] is not None and m.get('mdd_base') is not None
              and abs(r['mdd_pct']) <= abs(m['mdd_base'])) if 'mdd_base' in m else None
        c4 = r['cushion_x'] is not None and r['cushion_x'] >= 3.0
        c6 = r['_p3'] is not None and r['_p3'] <= 0.10
        r['_judge'] = {'C1': c1, 'C2': c2, 'C3': c3, 'C4': c4, 'C6': c6,
                       'domain_competent': bool(n >= 60 and c2 and c4 and c6
                                                and (c1 is None or c1) and (c3 is None or c3)),
                       'n_ge_60': n >= 60}
    return rows


# ================================================================ ATLAS v1（图谱收口）
LOWVOL_P20_NOTE = ('Q3-lowvol-p20：IC 恒不可测（P20 掩码×144≈29 只<min_names=30 谱系门）——'
                   '维持不放宽仅登记【数据受限·R5·非死】（用户工单前置③；放宽需预算内变更）')


def collect_map_invalid():
    """MAP-INVALID 全纲领清单（batch1 批判定落盘 + batch2 已知 8（batch2_result 落盘值）+
    batch3 本批判定）。行注登记，与生死判定并行不混写（MINE_SPEC §5.3）。"""
    mi = {'batch2': []}
    try:
        b2 = json.load(open(os.path.join(OUT, 'batch2_result.json')))
        for fam, fs in b2.get('detail', {}).items():
            if not isinstance(fs, dict):
                continue
            for vid, dd in fs.items():
                if isinstance(dd, dict) and dd.get('placebo', {}).get('map_invalid') is True:
                    mi['batch2'].append(vid)
    except Exception:
        pass
    try:
        b1 = json.load(open(os.path.join(OUT, 'batch1_result.json')))
        mi['batch1'] = []
        pl = b1.get('detail', {}).get('c5', {}).get('placebo')
        if pl and pl.get('map_invalid') is True:
            mi['batch1'].append('Q6-c5-v1_orig')
        for grp, vids in (('downweight', ['K1-d-downweight-slot05']),
                          ('gate_vol', ['K1-d-gate-vol20p80-pause']),
                          ('s3d1', ['K1-s3d1-armA', 'K1-s3d1-armB', 'K1-s3d1-armC'])):
            d = b1.get('detail', {}).get(grp, {})
            pools = [k for k in d if isinstance(d.get(k), dict) and 'placebo' in d[k]]
            if pools and all(d[p].get('placebo', {}).get('map_invalid') is True for p in pools):
                mi['batch1'] += vids
    except Exception:
        pass
    mi['batch3'] = []
    try:
        b3 = json.load(open(os.path.join(OUT, 'batch3_result.json')))
        for fam, dd in b3.get('detail', {}).items():
            if not isinstance(dd, dict):
                continue
            for vid, v in dd.items():
                if not isinstance(v, dict) or vid in ('wall_secs', 'shard') \
                        or 'placebo' in v or not v:
                    continue
                pools = [k for k in v if isinstance(v[k], dict) and 'placebo' in v[k]]
                if pools and all(v[p].get('placebo', {}).get('map_invalid') is True for p in pools):
                    mi['batch3'].append(vid)
    except Exception:
        pass
    return set(mi.get('batch1', []) + mi.get('batch2', []) + mi.get('batch3', []))


def judge_batch2_row(r, mi_variants):
    """batch2 因子/统计行格级判定（本批收口）：C2=ic_mean>0∧CI 下界>0；C4=垫≥3；C6=q≤0.10。"""
    n = r['n_days'] or 0
    c2 = (r['ic_mean'] is not None and r['ic_mean'] > 0
          and r['ci95_low'] is not None and r['ci95_low'] > 0)
    c4 = r['cushion_x'] is not None and r['cushion_x'] >= 3.0
    c6 = r['fdr_q'] is not None and r['fdr_q'] <= 0.10
    q2 = r['family'] == 'Q2'
    return {'C2': c2, 'C4': c4, 'C6': c6,
            'domain_competent': bool(not q2 and n >= 60 and c2 and c4 and c6),
            'q2_prior_family': q2, 'n_ge_60': n >= 60}


def build_atlas():
    """分域胜任图谱 v1：Batch1+2+3 全部 FACTBOOK 行 → 域×策略格四态
    （胜任/不胜任/样本不足/无效，统一命名 cell_id=family|variant|pool|domain）。"""
    rows = []
    for f, b in (('FACTBOOK_BATCH1.jsonl', 'batch1'), ('FACTBOOK_BATCH2.jsonl', 'batch2'),
                 ('FACTBOOK_BATCH3.jsonl', 'batch3')):
        p = os.path.join(OUT, f)
        if not os.path.exists(p):
            continue
        for l in open(p):
            r = json.loads(l)
            r['_src'] = b
            rows.append(r)
    b1j = {}
    try:
        for j in json.load(open(os.path.join(OUT, 'batch1_result.json'))).get('judgment', []):
            b1j[(j['variant_id'], j['pool'], j['domain'])] = j
    except Exception:
        pass
    mi = collect_map_invalid()
    # batch3 K1 已跑 8 格只出 D2 深挖行（D1 判定引用 batch1）；batch3 新 4 格 D1 直接入图谱
    j3 = {}
    try:
        for j in json.load(open(os.path.join(OUT, 'batch3_judgment.json'))).get('judgment', []):
            j3[(j['variant_id'], j['pool'], j['domain'])] = j
    except Exception:
        pass
    cells = []
    for r in rows:
        if r['axis'] != 'D1':
            continue
        vid, pool, dom = r['variant_id'], r['pool'], r['domain']
        if r['_src'] == 'batch1':
            j = b1j.get((vid, pool, dom))
        elif r['_src'] == 'batch3':
            j = j3.get((vid, pool, dom))
        else:
            j = None
        if j is None:
            j = judge_batch2_row(r, mi)
        n = r['n_days'] or 0
        if vid in mi:
            state = '无效'
            reason = f'MAP-INVALID（安慰剂不守恒，域间差异不可归因于域；{r["_src"]} 行注）'
        elif n < 60:
            state = '样本不足'
            reason = f'n_days={n}<60（MINE_SPEC §2.4-4/§5.4 只入册不入图谱判分）'
        elif j.get('domain_competent'):
            state = '胜任'
            reason = 'C2+C4+C6 核心三腿过且 C1/C3 不劣（§5.3 域胜任）'
        else:
            state = '不胜任'
            fail = [k for k in ('C2', 'C4', 'C6') if j.get(k) is False]
            reason = '核心腿未过：' + (','.join(fail) or 'n 或判定缺件')
        cells.append({
            'cell_id': f"{r['family']}|{vid}|{pool}|{dom}",
            'state': state, 'family': r['family'], 'variant_id': vid, 'pool': pool,
            'domain': dom, 'n_days': n, 'source_batch': r['_src'],
            'win_rate_pct': r.get('win_rate_pct'), 'excess_pp': r.get('excess_pp'),
            'ic_mean': r.get('ic_mean'), 'ic_t': r.get('ic_t'),
            'cushion_x': r.get('cushion_x'), 'fdr_q': r.get('fdr_q'),
            'ci95': [r.get('ci95_low'), r.get('ci95_high')],
            'mdd_pct': r.get('mdd_pct'), 'n_sig': r.get('n_sig'),
            'judge': {k: j.get(k) for k in ('C1', 'C2', 'C3', 'C4', 'C6') if k in j},
            'reason': reason,
            'one_line': _cell_one_line(state, r)})
    # 双池同向：同 variant×domain 双池均胜任 → release_eligible（§5.4）
    by_vd = {}
    for c in cells:
        by_vd.setdefault((c['variant_id'], c['domain']), []).append(c)
    for (vid, dom), grp in by_vd.items():
        ok_pools = {c['pool'] for c in grp if c['state'] == '胜任'}
        for c in grp:
            c['dual_pool_ok'] = len(ok_pools) >= 2
            c['release_eligible'] = bool(c['state'] == '胜任' and c['dual_pool_ok'])
            if c['state'] == '胜任' and not c['dual_pool_ok']:
                c['reason'] += '；单池达标=登记不放行（§5.4 双池同向）'
    counts = {}
    for c in cells:
        counts[c['state']] = counts.get(c['state'], 0) + 1
    atlas = {'atlas': '分域胜任图谱 v1（ATLAS_v1）', 'ts': time.strftime('%F %T'),
             'unified_naming': 'cell_id = family|variant_id|pool|domain（统一命名）',
             'states': ['胜任', '不胜任', '样本不足', '无效'],
             'state_rule': '无效=MAP-INVALID 安慰剂不守恒（MINE_SPEC §2.3/§5.3，两标记并行不混写）；'
                           '样本不足=n_days<60（§2.4-4）；胜任=C2+C4+C6 核心三腿过且 C1/C3 不劣'
                           '（§5.3，Q2 先验族不入胜任判定）；其余=不胜任',
             'counts': counts, 'n_cells': len(cells),
             'map_invalid_variants': sorted(mi),
             'lowvol_p20_registration': LOWVOL_P20_NOTE,
             'dual_pool_rule': '§5.4 域胜任须双池同向；单池达标=登记不放行（release_eligible=false）',
             'ruling_note': 'm=86 正式判读不在本单——待首席终裁统一判读',
             'r10_note': '图谱=研究坐标（离线分层+TR 触发器辅助人工切换参考），不作部署开关（R10）',
             'cells': cells}
    json.dump(atlas, open(os.path.join(OUT, 'ATLAS_v1.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    write_atlas_md(atlas)
    print(f"      ATLAS_v1：{len(cells)} 格四态 {counts}（MAP-INVALID 变体 {len(mi)} 个）", flush=True)


def _cell_one_line(state, r):
    if state == '无效':
        return '域间差异安慰剂不守恒——读数不可归因于域，禁按域挑选（§5.4 禁区）。'
    if state == '样本不足':
        return f"n={r['n_days']}<60 只入册附数，不入图谱判分。"
    v = r.get('excess_pp') if r.get('excess_pp') is not None else r.get('ic_mean')
    q = r.get('fdr_q')
    if state == '胜任':
        return (f"域内读数 {v}（垫 {r.get('cushion_x')}×，q={q}），CI["
                f"{r.get('ci95_low')},{r.get('ci95_high')}] 不含 0——域胜任成立。")
    return f"域内读数 {v}（垫 {r.get('cushion_x')}×，q={q}）核心腿未过——该格不可用为正事实（负事实同权入册）。"


def write_atlas_md(atlas):
    L = ['# 分域胜任图谱 v1（ATLAS_v1 · 可读版）', '',
         f"- 生成：{atlas['ts']} ｜ 命名：`{atlas['unified_naming']}`",
         f"- 四态：{'/'.join(atlas['states'])} ｜ 判定规则：{atlas['state_rule']}",
         f"- 双池纪律：{atlas['dual_pool_rule']}",
         f"- MAP-INVALID 变体（{len(atlas['map_invalid_variants'])} 个，全部格=无效）："
         + '、'.join(atlas['map_invalid_variants']),
         f"- 登记：{atlas['lowvol_p20_registration']}",
         f"- **m=86 正式判读不在本单——待首席终裁统一判读。** {atlas['r10_note']}", '',
         f"## 四态统计（{atlas['n_cells']} 格）", '',
         '| 状态 | 格数 |', '|---|---|']
    for s in atlas['states']:
        L.append(f"| {s} | {atlas['counts'].get(s, 0)} |")
    L += ['', '## 图谱热力表（行=变体×池，列=D1 四域）', '',
          '图例：胜任=✔ 不胜任=✘ 样本不足=○ 无效=▨', '']
    by_v = {}
    for c in atlas['cells']:
        by_v.setdefault((c['family'], c['variant_id'], c['pool']), {})[c['domain']] = c
    sym = {'胜任': '✔', '不胜任': '✘', '样本不足': '○', '无效': '▨'}
    L.append('| 族 | 变体 | 池 | 牛稳 | 牛躁 | 弱稳 | 弱躁 |')
    L.append('|---|---|---|---|---|---|---|')
    for (fam, vid, pool) in sorted(by_v):
        dd = by_v[(fam, vid, pool)]
        L.append(f"| {fam} | {vid} | {pool} | " +
                 ' | '.join(sym.get(dd[d]['state'], '·') if d in dd else '·'
                            for d in D1N) + ' |')
    L += ['', '## 每格一句话结论', '']
    for c in atlas['cells']:
        L.append(f"- `{c['cell_id']}` **{c['state']}**：{c['one_line']}（{c['reason']}）")
    L += ['', '---',
          '*谱系：MINE_SPEC_v1 §五/§5.5-3（热力表+每格一句话）；数据源=FACTBOOK_BATCH1/2/3.jsonl '
          '全部 D1 行；本图谱=研究坐标非部署开关（R10）；正式判读待首席终裁。*']
    open(os.path.join(OUT, 'ATLAS_v1.md'), 'w').write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
