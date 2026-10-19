#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch 2 · 因子四族 34 变体（MINE_SPEC_v1 §3.1-3.4 预算逐字冻结，禁加号）
====================================================================================
Q1 量价结构 8 / Q2 时序统计 8（优先跑，产出为 K2/K3 域结构先验）/ Q3 横截面 10 /
Q4 微观结构 8。合计 34（+Batch1 16 +Batch3 38 = 86 冻结预算）。
R10 红线：本件域标签只作离线研究分层，任何函数不产出「域读数→仓位」映射。
判线纪律（用户 Batch 2 工单指令）：p 值补入 m=86 合并表——只补表，本批不做生死判定
（C5 稳健三件与格级胜任判定统一 Batch 3 收口，本批 loto/yearly/lag 字段留空登记）。
D0 延续（同 Batch 1 谱系）：full 模式开工前重跑 batch0_domains.py 四对拍，all_pass
方入场（任一不过即停工，MINE_SPEC §六 Batch 0 逐字）。
复现锚替代（用户指令）：本批新变体无历史锚，以「独立第二实现抽 3 变体逐位对拍」
替代（batch2_repl.py），结果登记 batch2_result.json dual_impl。
D3 安慰剂统计量=BATCH1_RULING_3COND.json cond2 冻结口径（四域效应极差）。
用法：
  python3 batch2_run.py d0              # 仅跑 D0 闸
  python3 batch2_run.py smoke Q2|Q1|Q3|Q4   # 每族冒烟（截断窗，R8）
  python3 batch2_run.py full  Q2|Q1|Q3|Q4   # 全量分族跑 → batch2_partial_QX.json
  python3 batch2_run.py assemble        # 合并 + FDR m=86 合并表 + FACTBOOK 落盘
产出：FACTBOOK_BATCH2.jsonl（§七 22 字段同 Batch 1 格式）/ batch2_result.json /
      FDR_MERGED_M86.jsonl / FACTBOOK_BATCH1.jsonl（old131 K1 行按终裁条件①替换）
"""
import json
import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import scipy.stats as sst

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mine_common as MC
import batch1_run as B1

OUT = MC.OUT_DIR
FULL = B1.FULL
REALC = B1.REALC
SMOKE_WIN = B1.SMOKE_WIN
D1N = MC.D1_NAMES
N_PROC = 32
COLS = ['batch', 'variant_id', 'family', 'pool', 'axis', 'domain', 'n_days', 'n_sig',
        'win_rate_pct', 'ann_pct', 'excess_pp', 'mdd_pct', 'ic_mean', 'ic_t', 'n_ic',
        'spread_net_pp', 'avoid_pp', 'mdd_red_pct', 'cushion_x', 'fdr_q',
        'ci95_low', 'ci95_high', 'loto_pass', 'yearly_flip', 'lag_flip',
        'evidence_tag', 'anchor_ref', 'notes']
_OPS = '【口径操作化·R7 登记·MINE_SPEC 未逐字定义处提请终裁】'

_CTX = None


def ctx():
    global _CTX
    if _CTX is None:
        _CTX = MC.build_ctx()
        dom = json.load(open(os.path.join(OUT, 'domains.json')))
        B1._D1 = {'full144': dom['labels']['d1']}       # 冻结标签（full144 不受条件①影响）
    return _CTX


# ================================================================ D0 闸（Batch 1 同谱系）
def d0_gate():
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(OUT, 'batch0_domains.py')],
                       capture_output=True, text=True)
    res = json.load(open(os.path.join(OUT, 'D0_RESULT.json')))
    ok = bool(r.returncode == 0 and res.get('all_pass') is True)
    out = {'pass': ok, 'returncode': r.returncode, 'd0_all_pass': res.get('all_pass'),
           'd0_runtime_sec': res.get('runtime_sec'), 'gate_runtime_sec': round(time.time() - t0, 1),
           'lineage': 'batch0_domains.py 四对拍（Batch 1 同谱系，停工条款逐字适用）'}
    json.dump(out, open(os.path.join(OUT, 'd0_gate_batch2.json'), 'w'),
              ensure_ascii=False, indent=1)
    print(f"D0 闸：all_pass={res.get('all_pass')} → {'放行' if ok else '停工'}", flush=True)
    return ok


# ================================================================ 面板（full144，全变体共用）
def panels():
    c = ctx()
    syms = c['pools']['full144']
    data = c['data']
    cal = c['full144']['cal']
    P = {}
    for k, key in (('C', 'close'), ('O', 'open'), ('H', 'high'), ('L', 'low'), ('V', 'volume')):
        P[k] = pd.DataFrame({s: data[s][key] for s in syms}).reindex(cal)
    P['fwd5'] = P['C'].shift(-5) / P['C'] - 1
    P['fwd20'] = P['C'].shift(-20) / P['C'] - 1
    P['ret1'] = P['C'].pct_change()
    P['ret5'] = P['C'] / P['C'].shift(5) - 1
    P['ret10'] = P['C'] / P['C'].shift(10) - 1
    P['ret20'] = P['C'] / P['C'].shift(20) - 1
    P['vol20'] = P['ret1'].rolling(20).std()            # 未年化（c5/PC-5 谱系）
    P['turn20'] = np.log((P['C'] * P['V']).rolling(20).mean())
    return P


def sig_days(C):
    """ISO 周首交易日（sig_ext 谱系，batch1 同式）。"""
    iso = C.index.isocalendar()
    return pd.DatetimeIndex(C.index.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)


def zrow(df):
    mu, sd = df.mean(axis=1), df.std(axis=1, ddof=0)
    return df.sub(mu, axis=0).div(sd.replace(0.0, np.nan), axis=0).clip(-3, 3)


# ================================================================ 行构建（§七 22 字段同 Batch 1 格式）
def f_domain_rows(vid, family, ic, sp_day, notes=''):
    """因子族域行（batch1 factor_domain_rows 同构，batch=batch2）。返回 rows+cells。"""
    lab = B1.d1_labels('full144')
    rows, cells = [], []
    ic_dom = {d: [] for d in D1N}
    for t, v in ic.items():
        g = lab.get(str(pd.Timestamp(t).date()))
        if g in ic_dom:
            ic_dom[g].append(v)
    sp_dom = {d: [] for d in D1N}
    for t, v in sp_day.items():
        g = lab.get(str(pd.Timestamp(t).date()))
        if g in sp_dom:
            sp_dom[g].append(v)
    for d in D1N:
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
        p = float(sst.t.sf(t_, max(n_ic - 2, 1))) if t_ is not None else None   # 上尾（PF-5 同式）
        rows.append({'batch': 'batch2', 'variant_id': vid, 'family': family,
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
                     'evidence_tag': '【实证】', 'anchor_ref': 'new',
                     'notes': notes + '；CI 对象=域内逐日 IC（因子族无净值，win/ann/mdd 空）；'
                                      'C5 三件与格级胜任判定统一 Batch 3 收口'})
        cells.append({'batch': 'batch2', 'variant_id': vid, 'family': family,
                      'pool': 'full144', 'domain': d, 'p': p,
                      'p_kind': 't.sf(ic_t, n_ic-2) 上尾（batch1 PF-5 同式）'})
    return rows, cells


def f_full_row(vid, family, ic, sp_day, axis, notes=''):
    t_, n_ = MC.tstat(ic)
    sp_net = float(sp_day.mean()) - 0.10 if len(sp_day) else None
    return {'batch': 'batch2', 'variant_id': vid, 'family': family, 'pool': 'full144',
            'axis': axis, 'domain': 'all', 'n_days': int(n_), 'n_sig': int(len(sp_day)),
            'win_rate_pct': None, 'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
            'ic_mean': round(float(ic.mean()), 6), 'ic_t': None if t_ is None else round(t_, 6),
            'n_ic': int(n_), 'spread_net_pp': None if sp_net is None else round(sp_net, 4),
            'avoid_pp': None, 'mdd_red_pct': None, 'cushion_x': None, 'fdr_q': None,
            'ci95_low': None, 'ci95_high': None, 'loto_pass': None, 'yearly_flip': None,
            'lag_flip': None, 'evidence_tag': '【实证】', 'anchor_ref': 'new', 'notes': notes}


def ts_domain_rows(vid, family, sr, notes=''):
    """Q2 时序统计族域行：ic_mean 字段承载「域内统计量均值」（字段复用，R7 登记）。"""
    lab = B1.d1_labels('full144')
    rows, cells = [], []
    dom = {d: [] for d in D1N}
    for t, v in sr.items():
        g = lab.get(str(pd.Timestamp(t).date()))
        if g in dom and pd.notna(v):
            dom[g].append(float(v))
    for d in D1N:
        iv = pd.Series(dom[d], dtype=float).dropna()
        n = len(iv)
        t_ = float(iv.mean() / iv.std(ddof=1) * np.sqrt(n)) if n >= 3 and iv.std(ddof=1) else None
        ci = MC.stationary_boot(iv.values) if n >= 5 else np.array([])
        cushion = None
        if n >= 5 and len(sr.dropna()) > n:
            bmed = float(np.median(MC.perm_baseline(sr.dropna().values, n)))
            if bmed != 0:
                cushion = float(iv.mean()) / bmed
        p = float(2 * sst.t.sf(abs(t_), max(n - 1, 1))) if t_ is not None else None  # 双侧
        rows.append({'batch': 'batch2', 'variant_id': vid, 'family': family,
                     'pool': 'full144', 'axis': 'D1', 'domain': d,
                     'n_days': n, 'n_sig': None,
                     'win_rate_pct': None, 'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
                     'ic_mean': None if iv.empty else round(float(iv.mean()), 6),
                     'ic_t': None if t_ is None else round(t_, 6), 'n_ic': n,
                     'spread_net_pp': None,
                     'avoid_pp': None, 'mdd_red_pct': None,
                     'cushion_x': None if cushion is None else round(cushion, 2),
                     'fdr_q': None,
                     'ci95_low': None if not ci.size else round(float(np.percentile(ci, 2.5)), 6),
                     'ci95_high': None if not ci.size else round(float(np.percentile(ci, 97.5)), 6),
                     'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                     'evidence_tag': '【实证】', 'anchor_ref': 'new',
                     'notes': notes + '；Q2 非截面族：ic_mean 字段承载域内统计量均值（字段复用'
                                      '登记），ic_t=该均值 t 统计（df=n−1），p=双侧（结构统计'
                                      '量无预注册方向）；C5/格级判定统一 Batch 3 收口'})
        cells.append({'batch': 'batch2', 'variant_id': vid, 'family': family,
                      'pool': 'full144', 'domain': d, 'p': p,
                      'p_kind': 't 双侧(df=n-1)（Q2 结构统计量，无预注册方向）'})
    return rows, cells


def ts_full_row(vid, family, sr, axis, notes=''):
    v = sr.dropna()
    n = len(v)
    t_ = float(v.mean() / v.std(ddof=1) * np.sqrt(n)) if n >= 3 and v.std(ddof=1) else None
    return {'batch': 'batch2', 'variant_id': vid, 'family': family, 'pool': 'full144',
            'axis': axis, 'domain': 'all', 'n_days': n, 'n_sig': None,
            'win_rate_pct': None, 'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
            'ic_mean': round(float(v.mean()), 6) if n else None,
            'ic_t': None if t_ is None else round(t_, 6), 'n_ic': n,
            'spread_net_pp': None, 'avoid_pp': None, 'mdd_red_pct': None,
            'cushion_x': None, 'fdr_q': None, 'ci95_low': None, 'ci95_high': None,
            'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
            'evidence_tag': '【实证】', 'anchor_ref': 'new', 'notes': notes}


# ================================================================ Q2 时序统计族（8，优先）
def hurst_rs(w):
    """R/S 法 Hurst（窗 n=len(w)）。"""
    m = w.mean()
    z = np.cumsum(w - m)
    R = float(z.max() - z.min())
    S = float(w.std(ddof=1))
    if S <= 0 or R <= 0:
        return np.nan
    return float(np.log(R / S) / np.log(len(w)))


def run_q2(win, smoke):
    t0 = time.time()
    c = ctx()
    P0 = c['full144']
    idx = P0['idx']
    r1 = idx.pct_change()
    W = 60
    # v1/v2：idx 级自相关 lag1/lag5（60 日窗滚动）
    ac1 = r1.rolling(W, min_periods=W).corr(r1.shift(1))
    ac5 = r1.rolling(W, min_periods=W).corr(r1.shift(5))
    # v3/v4：池个股中位 AR1 半衰期（收益口径 / 对数价格口径，60 日窗逐股 OLS 斜率）
    C = P0['close']
    r = C.pct_change()
    x = r.shift(1)
    phi = r.rolling(W, min_periods=W).cov(x) / x.rolling(W, min_periods=W).var()
    phi_med = phi.median(axis=1).where(phi.notna().sum(axis=1) >= 30)

    def hl(pm):
        base = 1.0 + pm
        return (-np.log(2.0) / np.log(base)).where((base > 0) & (pm != 0) & pm.notna())
    hl_ret = hl(phi_med)
    # 【审计修正·OU 口径】水平 AR1 半衰期公式改 HL=−log2/log(φ)（φ∈(0,1)）——
    # 原实现误用 −log2/log(1+φ)，φ_p≈1 时分母 log(2) 使读数恒≈−1（量级失真，作废）。
    # 交易分析团队审计终裁②引用公式。缺陷修复配额 1/1。
    def hl_ou(pm):
        return (-np.log(2.0) / np.log(pm)).where((pm > 0) & (pm < 1) & pm.notna())
    lp = np.log(C)
    xp = lp.shift(1)
    phi_p = lp.rolling(W, min_periods=W).cov(xp) / xp.rolling(W, min_periods=W).var()
    phi_p_med = phi_p.median(axis=1).where(phi_p.notna().sum(axis=1) >= 30)
    hl_lev = hl_ou(phi_p_med)
    # v5/v6：Hurst 60 日（水平=日收益 / 趋势=5 日收益）
    r5 = idx.pct_change(5)
    def hurst_series(s):
        arr = s.values
        out = {}
        for i in range(W, len(arr)):
            w = arr[i - W + 1:i + 1]
            w = w[np.isfinite(w)]
            if len(w) == W:
                out[s.index[i]] = hurst_rs(w)
        return pd.Series(out)
    h_lvl = hurst_series(r1)
    h_trd = hurst_series(r5)
    # v7/v8：半衰期×域交互记账（速度记账 / 相对离散记账）
    iqr = (hl(phi).quantile(0.75, axis=1) - hl(phi).quantile(0.25, axis=1))
    hl_disp = (iqr / hl_ret.abs()).where(hl_ret.abs() > 0)
    VS = {
        'Q2-ac-lag1': (ac1, 'idx 日收益 60 日窗滚动 lag1 自相关'),
        'Q2-ac-lag5': (ac5, 'idx 日收益 60 日窗滚动 lag5 自相关'),
        'Q2-ar1-hl-ret': (hl_ret, '池个股 AR1(60 日, r_t~r_t-1) 斜率中位→半衰期 '
                                  '−log2/log(1+φ)（φ>0 为负值=趋势延续读数；分母池内自算）'
                                  '【口径存疑·量级失真·审计终裁③登记不重算：OU 口径 '
                                  '−log2/log(φ) 下 φ_ret→0 使半衰期量级不可比，原式量级'
                                  '亦不可作日数直读，仅保序使用】'),
        'Q2-ar1-hl-lev': (hl_lev, '池个股对数价格 AR1(60 日) 斜率中位→半衰期 −log2/log(φ)'
                                  '（OU 口径·审计修正版重算，原 −log2/log(1+φ) 恒≈−1 读数作废；'
                                  '水平/趋势口径对）'),
        'Q2-hurst-level': (h_lvl, 'idx 日收益 60 日 R/S Hurst（水平）'),
        'Q2-hurst-trend': (h_trd, 'idx 5 日收益 60 日 R/S Hurst（趋势）'),
        'Q2-hl-xdom-speed': (-hl_ret, '半衰期×域交互记账①：回归速度=−HL（中位）'),
        'Q2-hl-xdom-disp': (hl_disp, '半衰期×域交互记账②：截面 IQR/|中位| 相对离散度'),
    }
    rows, cells, detail = [], [], {}
    for vid, (sr, desc) in VS.items():
        sr = sr.sort_index()
        # §2.4：合成段（2024-01-24→2025-05-31）只作低权重佐证——主判读一律截 FULL 窗
        w0, w1 = win or FULL
        sr_w = sr[(sr.index >= w0) & (sr.index <= w1)].dropna()
        nt = desc + f'；{_OPS}'
        r1_, c_ = ts_domain_rows(vid, 'Q2', sr_w, notes=nt)
        rows += r1_
        rows.append(ts_full_row(vid, 'Q2', sr_w, 'FULL', nt))
        if not smoke:
            rc = sr.dropna()
            rc = rc[rc.index >= REALC[0]]
            rows.append(ts_full_row(vid, 'Q2', rc, 'REALC', nt))
            plc = B1.placebo_factor(sr_w.dropna())
            plc['statistic'] = '四域效应极差（Q2 统计量日值，MS_REALA 窗内，cond2 冻结口径）'
            detail[vid] = {'placebo': plc}
            if plc['map_invalid']:
                for r in r1_:
                    r['notes'] += ' MAP-INVALID'
        cells += c_
        detail.setdefault(vid, {})['n_full'] = int(len(sr_w))
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, cells, detail


# ================================================================ Q1 量价结构族（8）
def run_q1(win, smoke):
    t0 = time.time()
    P = panels()
    C, H, L, O, V = P['C'], P['H'], P['L'], P['O'], P['V']
    HH20, LL20 = H.rolling(20).max(), L.rolling(20).min()
    pos = (C - LL20) / (HH20 - LL20).replace(0.0, np.nan)      # Donchian 20 箱体位置
    sig = sig_days(C)
    sig_w = sig[(sig >= (win or FULL)[0]) & (sig <= (win or FULL)[1])]

    def bounce_rate(N):
        # 【审计修正·去前视】原实现 nxt_up=C.shift(-1)>C 使 t 日因子值包含当日 touch
        # 的反弹结果（依赖 t+1 收盘，与 fwd5 前视窗重叠）。修正：touch/good 整体后移
        # 1 日再滚动——t 日因子只用 t−N..t−1 的触及，最近一次反弹结果 C(t)vsC(t−1)
        # 当日已知，无前视。缺陷修复配额 1/1（Batch 2/3 审计终裁①）。
        sup = L.rolling(N).min().shift(1)
        touch = L <= sup
        nxt_up = C.shift(-1) > C
        good = (touch & nxt_up).shift(1).rolling(N).sum()
        hits = touch.shift(1).rolling(N).sum()
        return (good / hits.where(hits > 0))

    def crowd_inv(N):
        HH, LL = H.rolling(N).max(), L.rolling(N).min()
        near = ((C - HH).abs() / HH <= 0.01) | ((C - LL).abs() / LL <= 0.01)
        dens = near.rolling(N).sum()
        return 1.0 / dens.where(dens > 0)

    def brk(N):
        return C / H.rolling(N).max().shift(1) - 1.0

    VS = [
        ('Q1-boxpos-p75', pos.where(pos >= 0.75), P['fwd5'],
         '箱体位置（Donchian N=20 分位）入场变体：仅 position≥P75 标的入截面（入场掩码语义）'),
        ('Q1-boxpos-p90', pos.where(pos >= 0.90), P['fwd5'],
         '箱体位置入场变体：仅 position≥P90 标的入截面'),
        ('Q1-touch-bounce-5', bounce_rate(5), P['fwd5'],
         '触及支撑（N=5 日低点）次日反弹率【去前视修正版重算：剔除当日 touch 重叠，'
         '原前视读数作废】；窗内零触及=NaN'),
        ('Q1-touch-bounce-20', bounce_rate(20), P['fwd5'],
         '触及支撑（N=20 日低点）次日反弹率【去前视修正版重算：剔除当日 touch 重叠，'
         '原前视读数作废】'),
        ('Q1-brk-pos-20', brk(20), P['fwd5'],
         '区间突破纯位置强度（C/20 日 high 前值−1，非放量条件化，brk 判线换轨）'),
        ('Q1-brk-pos-60', brk(60), P['fwd5'], '区间突破纯位置强度（N=60）'),
        ('Q1-crowdinv-20', crowd_inv(20), P['fwd5'],
         '触及密度倒数（拥挤度代理）：±1% 边界触及计数倒数，零触及=NaN'),
        ('Q1-crowdinv-60', crowd_inv(60), P['fwd5'], '触及密度倒数（N=60）'),
    ]
    rows, cells, detail = [], [], {}
    for vid, fa, fwd, desc in VS:
        fa = fa.sort_index()
        w0, w1 = win or FULL
        ic = MC.xsec_ic_series(fa[(fa.index >= w0) & (fa.index <= w1)], fwd)
        sp_day = B1.daily_spread(fa.loc[sig_w], fwd.loc[sig_w].reindex(fa.loc[sig_w].index))
        hrz = 'fwd5' if fwd is P['fwd5'] else 'fwd20'
        nt = desc + f'；IC=逐日截面 Spearman（vs {hrz}）；{_OPS}'
        if not len(ic):
            ic = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
            nt += '；口径卡点：当日截面有效样本恒<30（min_names=30 谱系门），IC 不可测【数据受限·R5 登记·非死】'
        r1_, c_ = f_domain_rows(vid, 'Q1', ic, sp_day, notes=nt)
        rows += r1_ + [f_full_row(vid, 'Q1', ic, sp_day, 'FULL', nt)]
        if not smoke:
            rc = ic[ic.index >= REALC[0]]
            rows.append(f_full_row(vid, 'Q1', ic, sp_day, 'REALC', nt))
            plc = B1.placebo_factor(ic)
            detail[vid] = {'placebo': plc, 't_full': MC.tstat(ic)[0], 'n_full': int(len(ic))}
            if plc['map_invalid']:
                for r in r1_:
                    r['notes'] += ' MAP-INVALID'
        else:
            detail[vid] = {'t_full': MC.tstat(ic)[0], 'n_full': int(len(ic))}
        cells += c_
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, cells, detail


# ================================================================ Q3 横截面族（10）
def run_q3(win, smoke):
    t0 = time.time()
    P = panels()
    C, V = P['C'], P['V']
    ret20, vol20, turn20 = P['ret20'], P['vol20'], P['turn20']
    den_ew = ret20.mean(axis=1)
    den_med = ret20.median(axis=1)
    lowv = zrow(-vol20) + zrow(ret20)                       # 低波+动量复合（等权 z）
    q20 = vol20.quantile(0.20, axis=1)
    q33 = vol20.quantile(1 / 3, axis=1)
    liq_med = turn20.median(axis=1)
    VS = [
        ('Q3-rs-ew-fwd5', ret20.sub(den_ew, axis=0), P['fwd5'],
         '池内 RS（分母=池等权 ret20），IC horizon=fwd5'),
        ('Q3-rs-ew-fwd20', ret20.sub(den_ew, axis=0), P['fwd20'],
         '池内 RS（分母=池等权 ret20），IC horizon=fwd20'),
        ('Q3-rs-med-fwd5', ret20.sub(den_med, axis=0), P['fwd5'],
         '池内 RS（分母=同池中位 ret20），IC horizon=fwd5'),
        ('Q3-rs-med-fwd20', ret20.sub(den_med, axis=0), P['fwd20'],
         '池内 RS（分母=同池中位 ret20），IC horizon=fwd20'),
        ('Q3-lowvol-p20', (-vol20).where(vol20.le(q20, axis=0)), P['fwd20'],
         '低波选股：仅 vol20≤当日截面 P20 标的入截面（因子=−vol20）'),
        ('Q3-lowvol-p33', (-vol20).where(vol20.le(q33, axis=0)), P['fwd20'],
         '低波选股：vol20≤当日截面 P33 掩码'),
        ('Q3-lowvol-mom', lowv, P['fwd20'],
         '低波+动量复合：z(−vol20)+z(ret20) 等权（截面 z，clip±3，c5 谱系）'),
        ('Q3-rev-5', -P['ret5'], P['fwd5'], '短期反转（−ret5）'),
        ('Q3-rev-10', -P['ret10'], P['fwd5'], '短期反转（−ret10）'),
        ('Q3-rev-liq', (-P['ret5']).where(turn20.gt(liq_med, axis=0)), P['fwd5'],
         '反转+流动性过滤：−ret5 限 turn20>当日中位标的'),
    ]
    rows, cells, detail = [], [], {}
    sig = sig_days(C)
    w0, w1 = win or FULL
    sig_w = sig[(sig >= w0) & (sig <= w1)]
    for vid, fa, fwd, desc in VS:
        fa = fa.sort_index()
        ic = MC.xsec_ic_series(fa[(fa.index >= w0) & (fa.index <= w1)], fwd)
        sp_day = B1.daily_spread(fa.loc[sig_w], fwd.loc[sig_w].reindex(fa.loc[sig_w].index))
        hrz = 'fwd5' if fwd is P['fwd5'] else 'fwd20'
        nt = desc + f'；IC=逐日截面 Spearman（vs {hrz}）；{_OPS}'
        if not len(ic):
            ic = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
            nt += '；口径卡点：当日截面有效样本恒<30（min_names=30 谱系门），IC 不可测【数据受限·R5 登记·非死】'
        r1_, c_ = f_domain_rows(vid, 'Q3', ic, sp_day, notes=nt)
        rows += r1_ + [f_full_row(vid, 'Q3', ic, sp_day, 'FULL', nt)]
        if not smoke:
            rc = ic[ic.index >= REALC[0]]
            rows.append(f_full_row(vid, 'Q3', ic, sp_day, 'REALC', nt))
            plc = B1.placebo_factor(ic)
            detail[vid] = {'placebo': plc, 't_full': MC.tstat(ic)[0], 'n_full': int(len(ic))}
            if plc['map_invalid']:
                for r in r1_:
                    r['notes'] += ' MAP-INVALID'
        else:
            detail[vid] = {'t_full': MC.tstat(ic)[0], 'n_full': int(len(ic))}
        cells += c_
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, cells, detail


# ================================================================ Q4 微观结构族（8）
def run_q4(win, smoke):
    t0 = time.time()
    P = panels()
    C, H, L, O, V = P['C'], P['H'], P['L'], P['O'], P['V']
    HH20 = H.rolling(20).max()
    vr = V.rolling(20).mean() / V.rolling(60).mean()
    vr5 = V.rolling(5).mean() / V.rolling(20).mean()
    up = C.pct_change() > 0
    vd = V > V.shift(1)
    divcnt = ((up & ~vd) | (~up & vd)).rolling(20).mean()
    # 跳空未回补/回补计数（20 日回看，k=距缺口日 1..20 交易日）
    upgap = (O / C.shift(1) - 1 > 0.01)
    dngap = (O / C.shift(1) - 1 < -0.01)
    unfill = pd.DataFrame(0.0, index=C.index, columns=C.columns)
    refill = pd.DataFrame(0.0, index=C.index, columns=C.columns)
    for k in range(1, 21):
        lo_k = L.rolling(k, min_periods=k).min()
        hi_k = H.rolling(k, min_periods=k).max()
        unfill += (upgap.shift(k) & (lo_k > O.shift(k))).astype(float)
        refill += (dngap.shift(k) & (hi_k >= O.shift(k))).astype(float)
    gapden = (O / C.shift(1) - 1).abs().gt(0.01).rolling(20).sum()
    rng = H - L
    shadow = ((rng - (C - O).abs()) / rng.where(rng > 0)).rolling(20).mean()
    closeloc = ((C - L) / rng.where(rng > 0)).rolling(20).mean()
    VS = [
        ('Q4-div-vshrink-newhigh', P['ret20'].where((C >= HH20) & (vr < 1)), P['fwd5'],
         '量价背离①量缩价新高：20 日新高 ∧ 量比(V20/V60)<1 时 ret20 入截面'),
        ('Q4-div-vsurge-stall', vr5.where(P['ret5'].abs() < 0.01), P['fwd5'],
         '量价背离②量增价滞：量比(V5/V20) 值，限 |ret5|<1% 标的；方向不预设'),
        ('Q4-div-count', divcnt, P['fwd5'],
         '量价背离③背离计数：20 日内(价涨量缩∨价跌量增)日占比；方向不预设'),
        ('Q4-gap-unfilled-mom', unfill, P['fwd5'],
         '缺口①跳空未回补动量：20 日内向上跳空>1% 且至今未回补计数'),
        ('Q4-gap-fillrev', refill, P['fwd5'],
         '缺口②跳空回补反转：20 日内向下跳空>1% 且已回补计数；方向不预设'),
        ('Q4-gap-density', gapden, P['fwd5'], '缺口③缺口密度：20 日内 |跳空|>1% 计数；方向不预设'),
        ('Q4-shadow-ratio', shadow, P['fwd5'],
         '影线比：20 日均 (H−L−|C−O|)/(H−L)；方向不预设'),
        ('Q4-close-loc', closeloc, P['fwd5'], '收位：20 日均 (C−L)/(H−L)（高收位=买盘强）'),
    ]
    rows, cells, detail = [], [], {}
    sig = sig_days(C)
    w0, w1 = win or FULL
    sig_w = sig[(sig >= w0) & (sig <= w1)]
    for vid, fa, fwd, desc in VS:
        fa = fa.sort_index()
        ic = MC.xsec_ic_series(fa[(fa.index >= w0) & (fa.index <= w1)], fwd)
        sp_day = B1.daily_spread(fa.loc[sig_w], fwd.loc[sig_w].reindex(fa.loc[sig_w].index))
        hrz = 'fwd5' if fwd is P['fwd5'] else 'fwd20'
        nt = desc + f'；IC=逐日截面 Spearman（vs {hrz}）；{_OPS}'
        if not len(ic):
            ic = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
            nt += '；口径卡点：当日截面有效样本恒<30（min_names=30 谱系门），IC 不可测【数据受限·R5 登记·非死】'
        r1_, c_ = f_domain_rows(vid, 'Q4', ic, sp_day, notes=nt)
        rows += r1_ + [f_full_row(vid, 'Q4', ic, sp_day, 'FULL', nt)]
        if not smoke:
            rc = ic[ic.index >= REALC[0]]
            rows.append(f_full_row(vid, 'Q4', ic, sp_day, 'REALC', nt))
            plc = B1.placebo_factor(ic)
            detail[vid] = {'placebo': plc, 't_full': MC.tstat(ic)[0], 'n_full': int(len(ic))}
            if plc['map_invalid']:
                for r in r1_:
                    r['notes'] += ' MAP-INVALID'
        else:
            detail[vid] = {'t_full': MC.tstat(ic)[0], 'n_full': int(len(ic))}
        cells += c_
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, cells, detail


# ================================================================ 主流程
RUNNERS = {'Q1': run_q1, 'Q2': run_q2, 'Q3': run_q3, 'Q4': run_q4}
BUDGET = {'Q1': 8, 'Q2': 8, 'Q3': 10, 'Q4': 8}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'smoke'
    fam = sys.argv[2] if len(sys.argv) > 2 else 'Q2'
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
        print(f'[full] {fam} 全量（预算 {BUDGET[fam]} 变体）', flush=True)
    elif mode == 'assemble':
        assemble()
        return
    else:
        raise SystemExit(f'unknown mode {mode}')
    rows, cells, detail = RUNNERS[fam](win, smoke)
    n_v = len({r['variant_id'] for r in rows})
    print(f'      变体={n_v}/{BUDGET[fam]} 行={len(rows)} D1 格 p={len(cells)} '
          f'{detail["wall_secs"]}s', flush=True)
    if mode == 'full':
        json.dump({'family': fam, 'rows': rows, 'cells': cells, 'detail': detail,
                   'ts': time.strftime('%F %T')},
                  open(os.path.join(OUT, f'batch2_partial_{fam}.json'), 'w'),
                  ensure_ascii=False, indent=1, default=str)
        print(f'      → batch2_partial_{fam}.json', flush=True)
    print(f'done {round(time.time() - t0, 1)}s', flush=True)


def assemble():
    t0 = time.time()
    print('[assemble] 合并四族 + FDR m=86 合并表 + FACTBOOK 落盘 …', flush=True)
    rows, cells, details = [], [], {}
    for fam in ('Q2', 'Q1', 'Q3', 'Q4'):
        part = json.load(open(os.path.join(OUT, f'batch2_partial_{fam}.json')))
        rows += part['rows']
        cells += part['cells']
        details[fam] = part['detail']
        print(f"      {fam}: 变体 {len(set(r['variant_id'] for r in part['rows']))} "
              f"行 {len(part['rows'])}", flush=True)
    # 双实现对拍结果登记（batch2_repl.py 产出；缺件如实登记）
    repl_path = os.path.join(OUT, 'batch2_repl_result.json')
    dual = json.load(open(repl_path)) if os.path.exists(repl_path) else \
        {'status': 'MISSING', 'note': 'batch2_repl_result.json 缺件，如实登记'}
    # ---- FDR m=86 合并表：batch1 因子格（FACTBOOK 复算 p）+ batch1 框架格（终裁重放 p）
    #      + batch2 全部 D1 格 → BH（MC.bh_fdr_q, m_total=86）→ 全纲领一张表逐批补入
    b1_cells = []
    for l in open(os.path.join(OUT, 'FACTBOOK_BATCH1.jsonl')):
        r = json.loads(l)
        if r['axis'] == 'D1' and r.get('ic_t') is not None:
            b1_cells.append({'batch': 'batch1', 'variant_id': r['variant_id'],
                             'pool': r['pool'], 'domain': r['domain'],
                             'p': float(sst.t.sf(r['ic_t'], max(r['n_ic'] - 2, 1))),
                             'p_kind': 't.sf(ic_t, n_ic-2) 上尾（batch1 PF-5 同式）'})
    rul = json.load(open(os.path.join(OUT, 'ruling3_rerun.json')))
    b1_cells += [cc for cc in rul['fdr_cells'] if cc.get('p') is not None]
    all_cells = b1_cells + [cc for cc in cells if cc.get('p') is not None]
    qs = MC.bh_fdr_q([cc['p'] for cc in all_cells], m_total=MC.BATCH_BUDGET_M)
    qmap = {}
    with open(os.path.join(OUT, 'FDR_MERGED_M86.jsonl'), 'w') as f:
        for cc, q in zip(all_cells, qs):
            cc2 = dict(cc, q_merged=round(float(q), 6))
            qmap[(cc2['batch'], cc2['variant_id'], cc2['pool'], cc2['domain'])] = cc2['q_merged']
            f.write(json.dumps(cc2, ensure_ascii=False) + '\n')
    # FACTBOOK_BATCH2（fdr_q=合并表 q；无 _judge，只补表不判死）
    for r in rows:
        if r['axis'] == 'D1':
            r['fdr_q'] = qmap.get(('batch2', r['variant_id'], r['pool'], r['domain']))
    with open(os.path.join(OUT, 'FACTBOOK_BATCH2.jsonl'), 'w') as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in COLS}, ensure_ascii=False) + '\n')
    # FACTBOOK_BATCH1：old131 K1 行按终裁条件①替换（fdr_q=合并表 q），其余行不动
    fb1 = [json.loads(l) for l in open(os.path.join(OUT, 'FACTBOOK_BATCH1.jsonl'))]
    rul_rows = {r['variant_id'] + '|' + r['axis'] + '|' + r['domain']: r
                for r in rul['rows'] if r['pool'] == 'old131'}
    n_rep = 0
    for i, r in enumerate(fb1):
        if r['pool'] == 'old131' and r['family'] == 'K1':
            nr = rul_rows.get(r['variant_id'] + '|' + r['axis'] + '|' + r['domain'])
            if nr is not None:
                nr = dict(nr)
                nr['fdr_q'] = qmap.get(('batch1', nr['variant_id'], 'old131', nr['domain']))
                fb1[i] = nr
                n_rep += 1
    with open(os.path.join(OUT, 'FACTBOOK_BATCH1.jsonl'), 'w') as f:
        for r in fb1:
            f.write(json.dumps({k: r.get(k) for k in COLS}, ensure_ascii=False) + '\n')
    d0g = json.load(open(os.path.join(OUT, 'd0_gate_batch2.json')))
    out = {'ts': time.strftime('%F %T'),
           'budget': {'Q1': 8, 'Q2': 8, 'Q3': 10, 'Q4': 8, 'total': 34,
                      'note': 'MINE_SPEC §3.7 冻结预算 48 之子集；86=全纲领（Batch1 16+本批 34+Batch3 38）'},
           'n_factbook_rows_batch2': len(rows),
           'n_d1_cells': len([r for r in rows if r['axis'] == 'D1']),
           'fdr_merged': {'m_total': MC.BATCH_BUDGET_M,
                          'n_cells_batch1_factor': len([c for c in b1_cells if c['batch'] == 'batch1']) - len([c for c in rul['fdr_cells'] if c.get('p') is not None]),
                          'n_cells_batch1_framework': len([c for c in rul['fdr_cells'] if c.get('p') is not None]),
                          'n_cells_batch2': len([c for c in cells if c.get('p') is not None]),
                          'n_cells_total': len(all_cells),
                          'n_q_le_010': int(sum(1 for q in qs if q <= 0.10)),
                          'note': 'BH 合并族 m=86（MC.bh_fdr_q）；格级 p 沿用 batch1 既有实现'
                                  '（因子=IC t 上尾 / 框架=域内日超额 boot p_one / Q2=双侧 t），'
                                  'm=86 为变体冻结预算、格级补表为 batch1 先例，如实登记'},
           'd0_gate': d0g,
           'dual_impl_check': dual,
           'ruling3_cond1_note': 'FACTBOOK_BATCH1 old131 K1 行已按终裁条件①替换'
                                 f'（{n_rep} 行）；格级胜任判定统一 Batch 3 收口',
           'r10_note': '本运行不产出任何「域读数→仓位」映射（R10）',
           'detail': details, 'runtime_sec': round(time.time() - t0, 1)}
    json.dump(out, open(os.path.join(OUT, 'batch2_result.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    print(f'      FACTBOOK_BATCH2 行={len(rows)}；FDR 合并表 {len(all_cells)} 格'
          f'（q≤0.10 共 {out["fdr_merged"]["n_q_le_010"]}）', flush=True)
    print(f'      FACTBOOK_BATCH1 old131 替换 {n_rep} 行；dual_impl={dual.get("status")}', flush=True)
    print(f'done {out["runtime_sec"]}s', flush=True)


if __name__ == '__main__':
    main()
