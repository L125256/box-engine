#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W2（状态条件化 RS 深验）+ W3（门 v2 深验）工单 · 144 池定版
================================================================
【规格出处（冻结，禁改判据）】
- /tmp/trade9_specs/RESCUE_VERDICT.md：c4 池间 RS 动量 t=+4.78 主判进深验 +
  裸上禁令（未条件化前禁止任何实盘暴露）+ realC 翻转标注；d 换门 vol20 p80
  pause 进门 v2 深验；研究主管 W2 判线=「条件化后双窗费后价差>0 且 realC 子段
  不翻转」+ 技术保留两项（fwd5/fwd20 价差口径、extended⊆realC 核对）。
- /tmp/trade9_specs/RESCUE_PACK.md：b 单新预注册 PB-5..PB-9（费压×1.5、avoid/MDD
  操作性定义、达标线、stationary bootstrap p、BH FDR q=0.10）承继为 W3 主判口径。
- 既有实现复用：/workspace/repo_ready/research/wo_rescue/wo_rescue_run.py（run_gate
  门引擎、IC/价差判据件、bootstrap、BH）；wo_hd/wo_hd_run.py（八列段指标公式谱系）；
  dneg_engine（D0 权威谱系）。
- 池纪律：严格 144 池（old131 + new13），禁碰 97 个新标的；R8=Pool(32)；seed=42。

【W2 预注册（PW2-1..PW2-10，先冻结后运行）】
PW2-1 因子=PC-4 逐字：RS20=个股 20 日收益−异池等权 20 日收益（144 池内
  old131/new13 互指）；主判假设=RS 动量（多高 RS），horizon=fwd20 主判、fwd5 伴行。
PW2-2 截面域=严格 full144 成员（原 c4 在全部 176 只加载标的上算 IC，本单收窄到
  144 池并重算基线，差异如实登记=池域对拍）。
PW2-3 状态门变量（复用 wo_rescue _GV，full144 池口径，市场态逐日唯一）：
  vol20>realA p80 → 高波动态；breadth(close>MA50 占比)<50% → 窄广度态。
  2×2 四态：calm_broad / calm_narrow / hot_broad / hot_narrow。
PW2-4 评估窗（信号日=ISO 周首日，与 c4 同构）：extended=2025-06-02→2026-10-17；
  realA=→2026-03-31；realB=2026-04-01→05-31；realC=2026-06-01→10-17；
  holdout=2026-04-01→10-17；extended_excl_realC=→2026-05-31（技术保留②核对）。
PW2-5 逐态统计：Spearman IC（mean/t/n）+ 十分位 TopBottom 价差（raw 与费后
  0.10pp 双边，逐 horizon 各算各的——技术保留①口径澄清）。
PW2-6 判线（研究主管冻结原文操作性化）：某态通过=该态费后 fwd20 价差 extended>0
  且 realC>0（价差按周信号日，c4 谱系口径；价差腿周信号日<5 → 不判定），且
  realC 子段逐日 IC 均值≥0（不翻转）；IC 腿逐日样本<15 → INSUFFICIENT_N。
PW2-7 裸上禁令：全部结论必须条件化表述（「在 S 态下…」），禁写无条件结论位。
PW2-8 失效边界实测：①池依赖（old131-only 截面 vs 144 截面；同池分母 vs 异池
  分母）；②翻转机制假设（realC 信号日的态构成占比+逐态 realC IC——若逐态
  realC IC 全负则态条件化不能解释翻转，条件化部署在该态失效）。
PW2-9 技术保留②核对：extended 窗与 realC 窗为包含关系（按日期构造），报
  n_extended、n_realC、n_excl、extended_excl_realC t 值。
PW2-10 空头席「翻转后 N 日退出成本」：登记为边界预写项（需成对数据管线排期，
  本工单范围外，见报告失效边界节）。

【W3 预注册（PW3-1..PW3-10，先冻结后运行）】
PW3-1 门配置=唯一冻结点：vol20>realA p80（逐池阈值，仅 realA 估计）→ OFF
  pause（停开新仓，语义=wo_rescue run_gate 冻结插入，禁清仓扩大）；禁面扫描。
PW3-2 主判口径（新预注册=PB-5..PB-9 承继）：费压 FEE_SIDE×1.5/FUNDING×1.5；
  avoid_pp=门臂段净收益(pp)−base 臂段净收益(pp)；mdd_red=(|baseMDD|−|门MDD|)/
  |baseMDD|×100；双窗=FULL+HOLDOUT；达标=avoid>0 且 mdd_red≥10% 双窗同满足。
PW3-3 p 值=PB-9 同构：FULL 窗日净收益差（门−base）stationary bootstrap
  （块长均10，1000 次，seed=42）单侧 p=P(boot mean≤0)。
PW3-4 FDR：BH q=0.10，族 m=4（2 池 × {FULL,HOLDOUT} 单侧 p），如实记 m。
  入选（逐池）=FDR 幸存 ∧ 双窗 avoid>0 ∧ 双窗 mdd_red≥10。
PW3-5 三项针对性检验（H-D FAIL 教训）：
  T1 方向盲：OFF 日（vol20>阈值日）base 臂净日收益分布双侧检验
  （t 检验+Wilcoxon，H0: mean=0）——若 OFF 日均值不显著<0 即坐实方向盲；
  T2 1 日滞后稳健性：gate_map=cond.shift(1) 全指标重跑（八列+主判），
  FULL/HOLDOUT avoid>0 不翻转为稳健；
  T3 realB 反弹段锁死量化：realB OFF 占比（日/次）+踏空成本=base realB 净收益
  −门 realB 净收益（pp 与年化差）。
PW3-6 八列段指标（双池 × base/gate × realA/realB/realC，wo_hd seg_metrics 谱系
  逐行复用）：年化/MDD/周胜率/换手/费拖累/肥尾(r≥8% 单笔)/让渡/OFF 诊断。
PW3-7 谱系对拍（披露用）：默认费率臂 base/gate 与 wo_hd 八列 realA/realC 数字
  对拍（≤0.01pp 容差，四舍五入谱系）；主判数字以费压臂为准，两套不混。
PW3-8 总判定 PASS = 双池 PW3-4 入选 ∧ T2 双池 FULL/HOLDOUT avoid>0（滞后不
  翻转）；T1/T3 为机制披露项，不进总判定（预注册声明，防事后挑口径）。
PW3-9 止损避损台账（承继 H-D C3 口径）：realC 段 base vs 门 stop 笔数/金额/占比。
PW3-10 D0 对拍先过：①门禁用+默认费 vs dneg_engine.run_instr 曲线 maxdiff=0、
  fees=0；②run_gate_dr（记账快照增强版）vs wo_rescue.run_gate 逐位一致；
  ③默认费门臂 realA/realC 段指标 vs wo_hd 八列 ≤0.01pp。任一不过即停工。

用法：python3 wo_w2w3_run.py w2|w3|all
产出：w2_result.json / w3_result.json /（报告另手写 W2W3_REPORT.md）
"""
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy import stats as sst

sys.path.insert(0, '/workspace/repo_ready/research/wo_rescue')
sys.path.insert(0, '/workspace/repo_ready/research/wo_dneg')
import wo_rescue_run as WR
import dneg_engine as DE

SEED = 42
OUT = '/workspace/repo_ready/research/wo_w2w3'
os.makedirs(OUT, exist_ok=True)

REALB = (pd.Timestamp('2026-04-01'), pd.Timestamp('2026-05-31'))
FEE_SIDE_S = WR.FEE_SIDE_S
FUNDING_S = WR.FUNDING_S
FAT_R = 0.08
BR_THR = 50.0          # PW2-3 冻结：广度态界（b 单网格 20..60 的中位档）
MIN_N_STATE = 15       # PW2-6 最小态样本（逐日 IC 日数）
SPREAD_MIN_N = 5       # PW2-6 价差腿最小周信号日数

STATES = ['calm_broad', 'calm_narrow', 'hot_broad', 'hot_narrow']
WINDOWS_W2 = {
    'extended': (WR.REALA[0], WR.REALC[1]),
    'realA': (WR.REALA[0], WR.REALA[1]),
    'realB': REALB,
    'realC': (WR.REALC[0], WR.REALC[1]),
    'holdout': (WR.HOLD[0], WR.HOLD[1]),
    'extended_excl_realC': (WR.REALA[0], REALB[1]),
}
# 【口径修正注记】首跑误用周信号日算 IC（n=50/17，与 c4 谱系 n=317/119 不可比）；
# c4 谱系=逐日 IC（全部日历日）+ 周信号日十分位价差。本版对齐谱系口径：
# IC 逐日、价差按 ISO 周信号日（c4 同构）。修正属实现对齐规格，非改判据。


# ============================================================ D0 增强版门引擎
def run_gate_dr(syms, gate_map=None, fee=None, fund=None):
    """逐行复制 wo_rescue.run_gate（D0 谱系，冻结插入见其头注），仅加逐日
    fees/turnover 累计快照 day_cum（记账用，不改任何逻辑分支）。"""
    fee = DE.FEE_SIDE if fee is None else fee
    fund = DE.FUNDING if fund is None else fund
    close = pd.DataFrame({s: WR._DATA[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: WR._DATA[s]['open'] for s in syms})
    low = pd.DataFrame({s: WR._DATA[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(WR._DATA[s].index) for s in syms])))
    close = close.reindex(cal)
    open_ = open_.reindex(cal)
    low = low.reindex(cal)
    mark = close.ffill()
    idx = close.mean(axis=1)
    idx_ma = idx.rolling(DE.MA_REG).mean()
    med_ret = close.pct_change().median(axis=1)
    iso = cal.isocalendar()
    sig_days = set(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)

    cash, pos = 1.0, {}
    pending_sells, pending_reason = set(), {}
    pending_exec = None
    eq, hold = {}, {}
    fees = turnover = 0.0
    n_rebal = n_gate_off = 0
    stopped_today = set()
    trades = {}
    tid_seq = [0]
    last_mark, tid_of = {}, {}
    day_cum = []

    for t in cal:
        o_t, lo_t = open_.loc[t], low.loc[t]
        stopped_today = set()
        for s in list(pos):
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            stop_p = pos[s]['entry'] * (1 + DE.STOP)
            if o_t[s] <= stop_p:
                px = o_t[s]
            elif lo_t[s] <= stop_p:
                px = stop_p
            else:
                continue
            q = pos[s]['qty']
            cash += q * px * (1 - fee)
            fees += q * px * fee
            turnover += q * px
            stopped_today.add(s)
            tid = tid_of[s]
            trades[tid]['gap_loss'] = float(q * (stop_p - o_t[s])) if o_t[s] < stop_p else 0.0
            trades[tid]['stop_type'] = 'gap' if o_t[s] < stop_p else 'intraday'
            trades[tid].update(close_date=str(t.date()), exit_px=float(px),
                               exit_reason='stop', exit_fee=float(q * px * fee))
            del pos[s]
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                q = pos[s]['qty']
                cash += q * px * (1 - fee)
                fees += q * px * fee
                turnover += q * px
                trades[tid_of[s]].update(close_date=str(t.date()), exit_px=float(px),
                                         exit_reason=pending_reason.get(s, 'crash'),
                                         exit_fee=float(q * px * fee))
                del pos[s]
            pending_sells.discard(s)
            pending_reason.pop(s, None)
        if pending_exec is not None and t == pending_exec[0]:
            _, target, eq_sig, off_next = pending_exec
            pending_exec = None
            n_rebal += 1
            if off_next:
                n_gate_off += 1
            if not (off_next and True):
                for s in list(pos):
                    if s in target or s in pending_sells:
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        pending_sells.add(s)
                        pending_reason[s] = 'rebal'
                        continue
                    q = pos[s]['qty']
                    cash += q * px * (1 - fee)
                    fees += q * px * fee
                    turnover += q * px
                    trades[tid_of[s]].update(close_date=str(t.date()), exit_px=float(px),
                                             exit_reason='rebal', exit_fee=float(q * px * fee))
                    del pos[s]
            if not off_next:
                for s in target:
                    if s in pos or s in stopped_today:
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        continue
                    budget = min(DE.SLOT * eq_sig, max(cash, 0.0))
                    if budget <= 0:
                        continue
                    qty = budget / px
                    cash -= qty * px * (1 + fee)
                    fees += qty * px * fee
                    turnover += qty * px
                    pos[s] = {'qty': qty, 'entry': px}
                    last_mark[s] = float(px)
                    tid = tid_seq[0]; tid_seq[0] += 1
                    trades[tid] = {'sym': s, 'open_date': str(t.date()), 'open_px': float(px),
                                   'qty': float(qty), 'entry_fee': float(qty * px * fee),
                                   'exit_fee': 0.0, 'funding': 0.0, 'price_pnl': 0.0,
                                   'gap_loss': 0.0, 'close_date': None, 'exit_px': None,
                                   'exit_reason': None, 'stop_type': None}
                    tid_of[s] = tid
        equity = cash
        for s, p in pos.items():
            m = mark.at[t, s]
            equity += p['qty'] * m
            f = p['qty'] * m * fund
            cash -= f
            fees += f
            tid = tid_of[s]
            trades[tid]['funding'] -= float(f)
            trades[tid]['price_pnl'] += float(p['qty'] * (m - last_mark[s]))
            last_mark[s] = m
        eq[t] = equity
        hold[t] = ','.join(sorted(pos))
        day_cum.append((t, fees, turnover))
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) and med_ret[t] < DE.CRASH_MED:
            for s in pos:
                pending_reason.setdefault(s, 'crash')
            pending_sells.update(pos.keys())
        if t in sig_days:
            score = DE.cross_scores(WR._F, syms, t, DE.FACTORS_4)
            off_next = bool(gate_map is not None and gate_map.get(t, False))
            target = [] if (off_next and False) else list(score.index[:DE.TOP_N])
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity, off_next) \
                if cal.get_loc(t) + 1 < len(cal) else None

    curve = pd.Series(eq).sort_index()
    end = cal[-1]
    for s, p in pos.items():
        trades[tid_of[s]].update(close_date=str(end.date()), exit_px=float(mark.at[end, s]),
                                 exit_reason='eow')
    return {'curve': curve, 'fees': fees, 'turnover': turnover, 'n_rebal': n_rebal,
            'n_gate_off': n_gate_off, 'trades': trades, 'day_cum': day_cum}


def gate_cond(pname, lag=0):
    """PW3-1 冻结门：vol20>realA p80 → OFF；lag=1 → shift(1)。"""
    gv = WR._GV[pname]
    cond = gv['vol'] > gv['vol_thr'][80]
    if lag:
        cond = cond.shift(lag)
    return cond.fillna(False)


# ============================================================ W2：状态条件化 RS
def _sig_days(cal):
    iso = cal.isocalendar()
    return pd.DatetimeIndex(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)


def _ic_stats(fa, fb):
    ic = WR._xsec_ic_series(fa, fb)
    t_, n = WR._tstat(ic)
    return {'ic_mean': float(ic.mean()) if len(ic) else None,
            't_stat': t_, 'n_days': n}


def _spread(fa, fb, h):
    raw, net, n = WR._decile_spread_fee(fa, fb)
    return {'fwd' + str(h) + '_decile_pp_raw': round(raw, 4) if raw is not None else None,
            'fwd' + str(h) + '_decile_pp_net': round(net, 4) if net is not None else None,
            'n_sig': n}


def stage_w2():
    t0 = time.time()
    WR._init()
    names144 = WR._POOLS['full144']
    old131 = WR._POOLS['old131']
    new13 = sorted(set(names144) - set(old131))
    assert len(names144) == 144 and len(old131) == 131 and len(new13) == 13

    C = pd.DataFrame({s: WR._DATA[s]['close'] for s in names144}).sort_index()
    ret20 = C / C.shift(20) - 1
    idx_old = ret20[old131].mean(axis=1)
    idx_new = ret20[new13].mean(axis=1)
    rs_cross = pd.DataFrame(index=C.index, columns=names144, dtype=float)
    rs_same = pd.DataFrame(index=C.index, columns=names144, dtype=float)
    for s in names144:
        if s in old131:
            rs_cross[s] = ret20[s] - idx_new      # PC-4 异池互指
            rs_same[s] = ret20[s] - idx_old       # 边界①同池分母
        else:
            rs_cross[s] = ret20[s] - idx_old
            rs_same[s] = ret20[s] - idx_new
    fwd = {h: C.shift(-h) / C - 1 for h in (5, 20)}

    sigs = _sig_days(C.index)
    gv = WR._GV['full144']
    vol_hi = (gv['vol'] > gv['vol_thr'][80]).reindex(C.index).fillna(False)
    br_lo = (gv['breadth'] < BR_THR).reindex(C.index).fillna(False)
    state_of = pd.Series(index=C.index, dtype=object)
    state_of[~vol_hi & ~br_lo] = 'calm_broad'
    state_of[~vol_hi & br_lo] = 'calm_narrow'
    state_of[vol_hi & ~br_lo] = 'hot_broad'
    state_of[vol_hi & br_lo] = 'hot_narrow'

    out = {'stage': 'w2_rs_state_conditional', 'ts': time.strftime('%F %T'),
           'od': 'PW2-1..PW2-10（见头注，冻结）',
           'factor_def': 'RS20=个股20日收益−异池等权20日收益（144 池 old131/new13 互指）；'
                         '主判=RS_momentum fwd20（RESCUE_VERDICT M1）',
           'state_def': {'vol': 'full144 池等权 idx vol20>realA p80',
                         'breadth': f'full144 breadth(<MA50 占比)<{BR_THR}%',
                         'states': STATES},
           'pool_scope_note': '原 c4 IC 截面=全部加载标的(176 只)；本单收窄到严格 144 池'
                              '（工单纪律），基线重算差异如实登记',
           'windows': {k: [str(a.date()), str(b.date())] for k, (a, b) in WINDOWS_W2.items()},
           'bare_upload_ban': '裸上禁令：所有结论条件化表述；未通过状态条件化前禁止任何仓位'
                              '（RESCUE_VERDICT 空头席/首席终裁）',
           'baseline_144pool': {}, 'c4_lineage_check': {},
           'states': {}, 'boundary': {}, 'verdict': {}}

    # ---- 基线（无条件，144 池重算）+ c4 谱系对拍
    # 口径=c4 谱系：IC 逐日（全部日历日），十分位价差按 ISO 周信号日
    c4 = json.load(open('/workspace/repo_ready/research/wo_rescue/c_new_candidates.json')
                   )['directions']['c4']['hypotheses']
    for wn, (a, b) in WINDOWS_W2.items():
        days_all = C.index[(C.index >= a) & (C.index <= b)]
        sig_w = sigs[(sigs >= a) & (sigs <= b)]
        r = {'ic': _ic_stats(rs_cross.loc[days_all], fwd[20].loc[days_all])}
        r.update(_spread(rs_cross.loc[sig_w], fwd[20].loc[sig_w], 20))
        r.update(_spread(rs_cross.loc[sig_w], fwd[5].loc[sig_w], 5))
        out['baseline_144pool'][wn] = r
    reg = c4['RS_momentum|fwd20']
    out['c4_lineage_check'] = {
        'registered_c4_176cs': {'t_extended': reg['t_extended'], 'n_extended': reg['n_extended'],
                                't_realC': reg['t_realC'], 'n_realC': reg['n_realC'],
                                'spread_net_f20': reg['decile_spread_pp_net_of_fee']},
        'recomputed_144cs': {'t_extended': out['baseline_144pool']['extended']['ic']['t_stat'],
                             'n_extended': out['baseline_144pool']['extended']['ic']['n_days'],
                             't_realC': out['baseline_144pool']['realC']['ic']['t_stat'],
                             'n_realC': out['baseline_144pool']['realC']['ic']['n_days'],
                             'spread_net_f20': out['baseline_144pool']['extended']['fwd20_decile_pp_net']},
        'spread_caliber_note': '原 c4 fwd5/fwd20 价差同为 1.4616pp=价差按单一 horizon '
                               '计算的技术保留①；本单逐 horizon 各算各的（PW2-5）'}

    # ---- 逐态统计（PW2-5/6）：IC 逐日、价差按周信号日（c4 谱系口径）
    for st in STATES:
        row = {}
        for wn, (a, b) in WINDOWS_W2.items():
            days_all = C.index[(C.index >= a) & (C.index <= b)]
            days_all = days_all[days_all.map(lambda d: state_of.at[d] == st)]
            sig_w = sigs[(sigs >= a) & (sigs <= b)]
            sig_w = sig_w[sig_w.map(lambda d: state_of.at[d] == st)]
            if len(days_all) < MIN_N_STATE:
                row[wn] = {'n_days': int(len(days_all)), 'n_sig': int(len(sig_w)),
                           'status': 'INSUFFICIENT_N'}
                continue
            r = {'n_days': int(len(days_all)), 'n_sig': int(len(sig_w)),
                 'ic': _ic_stats(rs_cross.loc[days_all], fwd[20].loc[days_all])}
            if len(sig_w) >= SPREAD_MIN_N:
                r.update(_spread(rs_cross.loc[sig_w], fwd[20].loc[sig_w], 20))
                r.update(_spread(rs_cross.loc[sig_w], fwd[5].loc[sig_w], 5))
            else:
                r['spread_status'] = 'INSUFFICIENT_N_SIG(<%d)' % SPREAD_MIN_N
            row[wn] = r
        ic_rc = row['realC'].get('ic', {}).get('ic_mean') if 'ic' in row.get('realC', {}) else None
        sp_ext = row['extended'].get('fwd20_decile_pp_net')
        sp_rc = row['realC'].get('fwd20_decile_pp_net')
        if (row['extended'].get('status') == 'INSUFFICIENT_N'
                or row['realC'].get('status') == 'INSUFFICIENT_N'
                or 'spread_status' in row.get('extended', {})
                or 'spread_status' in row.get('realC', {})):
            row['judgment'] = 'INSUFFICIENT_N（PW2-6 不判定）'
        else:
            ok = bool(sp_ext is not None and sp_rc is not None and sp_ext > 0 and sp_rc > 0
                      and ic_rc is not None and ic_rc >= 0)
            row['judgment'] = ('PASS（条件化判线：双窗费后 fwd20 价差>0 ∧ realC 子段不翻转）'
                               if ok else
                               'FAIL（条件化判线不过：' +
                               f'extended 费后价差={sp_ext}pp, realC 费后价差={sp_rc}pp, '
                               f'realC IC mean={ic_rc}）')
        out['states'][st] = row

    # ---- 失效边界实测（PW2-8/9）
    bnd = {}
    for wn in ('extended', 'realC'):
        a, b = WINDOWS_W2[wn]
        days_all = C.index[(C.index >= a) & (C.index <= b)]
        bnd[wn] = {
            'old131_only_cs': _ic_stats(rs_cross[old131].loc[days_all],
                                        fwd[20][old131].loc[days_all]),
            'same_pool_denom': _ic_stats(rs_same.loc[days_all], fwd[20].loc[days_all]),
            'cross_pool_144': _ic_stats(rs_cross.loc[days_all], fwd[20].loc[days_all])}
    n_ext = out['baseline_144pool']['extended']['ic']['n_days']
    n_rc = out['baseline_144pool']['realC']['ic']['n_days']
    n_excl = out['baseline_144pool']['extended_excl_realC']['ic']['n_days']
    bnd['extended_realC_inclusion'] = {
        'n_extended': n_ext, 'n_realC': n_rc, 'n_excl_realC': n_excl,
        'n_ext_minus_n_realC': n_ext - n_rc,
        'note': 'extended 窗按日期构造包含 realC（技术保留②坐实：extended⊆realC 成立，'
                'n_extended−n_realC 应=pre-realC 信号日数）；t_excl 见 extended_excl_realC 窗',
        't_extended_excl_realC': out['baseline_144pool']['extended_excl_realC']['ic']['t_stat']}
    rc_days = C.index[(C.index >= WINDOWS_W2['realC'][0]) & (C.index <= WINDOWS_W2['realC'][1])]
    bnd['realC_state_composition'] = {
        st: round(float(pd.Series([state_of.at[d] == st for d in rc_days]).mean()) * 100, 2)
        for st in STATES}
    bnd['flip_mechanism'] = {
        'per_state_realC_ic': {st: out['states'][st]['realC'].get('ic', {}).get('ic_mean')
                               for st in STATES},
        'assumption_note': '翻转机制假设=态切换（高波动/窄广度）解释 realC 反号；'
                           '若逐态 realC IC 仍全负，则态条件化不能拯救该态，条件化部署在该态失效'}
    out['boundary'] = bnd

    # ---- 条件化结论（裸上禁令：逐态表述）
    passed = [st for st in STATES if out['states'][st].get('judgment', '').startswith('PASS')]
    out['verdict'] = {
        'conditional_conclusions': {
            st: (f'在态 {st} 下：extended IC={out["states"][st]["extended"].get("ic", {}).get("ic_mean")}，'
                 f'realC IC={out["states"][st]["realC"].get("ic", {}).get("ic_mean")}，'
                 f'费后 fwd20 价差 extended={out["states"][st]["extended"].get("fwd20_decile_pp_net")}pp / '
                 f'realC={out["states"][st]["realC"].get("fwd20_decile_pp_net")}pp → '
                 + out['states'][st]['judgment'])
            for st in STATES},
        'states_passing_line': passed,
        'deployment_statement': '裸因子禁上（禁令维持）；仅当状态分类器实时可判且落在通过态时，'
                                '方可在该态条件化暴露；态外一律禁止',
        'n_day_exit_cost': '空头席「翻转后 N 日退出成本」：登记为边界预写项，需池间成对'
                           '数据管线排期，本工单未跑（PW2-10，非判死）'}
    out['wall_secs'] = round(time.time() - t0, 1)
    with open(os.path.join(OUT, 'w2_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('W2 完成', out['wall_secs'], 's；通过态：', passed)
    return out


# ============================================================ W3：门 v2 深验
def _w3_worker(task):
    arm, pname, fmode = task
    WR._init()
    syms = WR._POOLS[pname]
    if arm == 'base':
        gmap = None
    elif arm == 'gate':
        gmap = gate_cond(pname).to_dict()
    elif arm == 'gate_lag':
        gmap = gate_cond(pname, lag=1).to_dict()
    fee, fund = (FEE_SIDE_S, FUNDING_S) if fmode == 'stress' else (DE.FEE_SIDE, DE.FUNDING)
    g = run_gate_dr(syms, gate_map=gmap, fee=fee, fund=fund)
    return {'arm': arm, 'pname': pname, 'fmode': fmode,
            'n_gate_off': g['n_gate_off'],
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()},
            'fees': float(g['fees']), 'turnover': float(g['turnover']),
            'day_cum': [(str(t.date()), float(f), float(tv)) for t, f, tv in g['day_cum']],
            'trades': g['trades']}


def _seg_metrics(res, t0, t1):
    """wo_hd seg_metrics 谱系逐行复用（day_cum 增强版费/换手切窗）。"""
    curve = pd.Series({pd.Timestamp(k): v for k, v in res['curve'].items()}).sort_index()
    seg = curve[(curve.index >= t0) & (curve.index <= t1)]
    if len(seg) < 2:
        return {}
    yrs = (seg.index[-1] - seg.index[0]).days / 365.25
    ann = (seg.iloc[-1] / seg.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1
    wk = seg.resample('W').last().pct_change().dropna()
    act = wk[wk.abs() > 1e-10]
    mdd = (seg / seg.cummax() - 1).min()
    eq0 = float(seg.iloc[0])
    cum = pd.Series({pd.Timestamp(d): (f, tv) for d, f, tv in res['day_cum']}).sort_index()
    prior = cum[cum.index < t0]
    f0 = float(prior.iloc[-1][0]) if len(prior) else 0.0
    tv0 = float(prior.iloc[-1][1]) if len(prior) else 0.0
    fees_seg = float(cum[cum.index <= t1].iloc[-1][0]) - f0
    notional = float(cum[cum.index <= t1].iloc[-1][1]) - tv0
    t0d, t1d = str(t0.date()), str(t1.date())
    fat_sum = stop_n = 0
    stop_pp = gap_pp = 0.0
    for tr in res['trades'].values():
        cd = tr['close_date']
        if cd is None or not (t0d <= cd <= t1d):
            continue
        pnl_pp = (tr['price_pnl'] + tr['entry_fee'] + tr['exit_fee'] + tr['funding']) * 100
        ret = tr['exit_px'] / tr['open_px'] - 1
        if ret >= FAT_R:
            fat_sum += pnl_pp
        if tr['exit_reason'] == 'stop':
            stop_n += 1
            stop_pp += pnl_pp
            gap_pp += tr['gap_loss'] * 100
    return {'annualized_pct': round(ann * 100, 2), 'mdd_pct': round(mdd * 100, 2),
            'weekly_winrate_pct': round((wk > 0).mean() * 100, 2),
            'weekly_winrate_active_pct': round((act > 0).mean() * 100, 2),
            'cash_weeks': int((wk.abs() <= 1e-10).sum()),
            'turnover_ann_x': round(notional / yrs / eq0, 2),
            'fee_drag_ann_pp': round(fees_seg / yrs / eq0 * 100, 2),
            'fat_tail_sum_pp': round(fat_sum, 2),
            'stop_trades_n': stop_n, 'stop_realized_pp': round(stop_pp, 2),
            'stop_gap_loss_pp': round(gap_pp, 2),
            'total_return_pct': round((seg.iloc[-1] / seg.iloc[0] - 1) * 100, 2),
            'n_days': int(len(seg))}


def _off_diag(pname, base_res, t0, t1):
    off = gate_cond(pname)
    curve = pd.Series({pd.Timestamp(k): v for k, v in base_res['curve'].items()}).sort_index()
    ret = curve.pct_change()
    o = off[(off.index >= t0) & (off.index <= t1)]
    r = ret[(ret.index >= t0) & (ret.index <= t1)]
    od = o[o]
    flips = int((o.astype(int).diff().abs() == 1).sum())
    eps = int((o.astype(int).diff() == 1).sum() + (1 if len(o) and o.iloc[0] else 0))
    return {'off_days': int(len(od)), 'off_share_pct': round(len(od) / max(len(o), 1) * 100, 2),
            'off_episodes': eps, 'flips': flips,
            'off_hit_rate_pct': (round(float((r[od.index] < 0).mean()) * 100, 2)
                                 if len(od) else None), 'n_days': int(len(o))}


def _direction_blind(pname, base_res, t0, t1):
    """T1 方向盲：OFF 日 base 净日收益分布双侧检验。"""
    off = gate_cond(pname)
    curve = pd.Series({pd.Timestamp(k): v for k, v in base_res['curve'].items()}).sort_index()
    ret = curve.pct_change() * 100.0
    o = off[(off.index >= t0) & (off.index <= t1)]
    x = ret[o[o].index].dropna()
    if len(x) < 5:
        return {'n': int(len(x)), 'status': 'INSUFFICIENT_N'}
    tt = sst.ttest_1samp(x, 0.0)
    try:
        wx = sst.wilcoxon(x)
        w_p = float(wx.pvalue)
    except Exception:
        w_p = None
    return {'n': int(len(x)), 'mean_pp': round(float(x.mean()), 4),
            'median_pp': round(float(x.median()), 4), 'std_pp': round(float(x.std(ddof=1)), 4),
            'p_lt0_pct': round(float((x < 0).mean()) * 100, 2),
            'ttest_two_sided': {'t': round(float(tt.statistic), 4), 'p': round(float(tt.pvalue), 4)},
            'wilcoxon_two_sided_p': round(w_p, 4) if w_p is not None else None,
            'mean_significant_neg_5pct': bool(tt.pvalue < 0.05 and x.mean() < 0)}


def stage_w3():
    t0 = time.time()
    WR._init()
    pools = list(WR._POOLS)
    tasks = [(a, p, 'stress') for p in pools for a in ('base', 'gate', 'gate_lag')] \
        + [(a, p, 'default') for p in pools for a in ('base', 'gate')]
    with Pool(32) as pool:
        runs_raw = pool.map(_w3_worker, tasks)
    R = {(r['pname'], r['arm'], r['fmode']): r for r in runs_raw}

    # ---- D0 对拍（PW3-10）
    d0 = {}
    for p in pools:
        ref = DE.run_instr(WR._DATA, F=WR._F, syms=WR._POOLS[p], gated=False, record=True)
        mine = R[(p, 'base', 'default')]
        mc = pd.Series({pd.Timestamp(k): v for k, v in mine['curve'].items()}).sort_index()
        md = float((mc - ref['curve']).abs().max())
        fd = float(abs(mine['fees'] - ref['fees']))
        wr = WR.run_gate(WR._POOLS[p], gate_map=None, fee=DE.FEE_SIDE, fund=DE.FUNDING)
        md2 = float((mc - wr['curve']).abs().max())
        fd2 = float(abs(mine['fees'] - wr['fees']))
        d0[p] = {'vs_dneg_engine_maxdiff': md, 'vs_dneg_engine_fees_absdiff': fd,
                 'vs_wo_rescue_run_gate_maxdiff': md2, 'vs_wo_rescue_fees_absdiff': fd2}
        assert md == 0 and fd == 0 and md2 == 0 and fd2 == 0, f'D0 FAIL {p}: {d0[p]}'
    thr_chk = {p: {'w2w3_thr_ann_pct': round(float(WR._GV[p]['vol_thr'][80]) * 100, 2),
                   'wo_hd_thr_ann_pct': json.load(open(
                       '/workspace/repo_ready/research/wo_hd/wo_hd_result.json'
                   ))['meta']['thresholds_ann_vol_pct'][p]} for p in pools}

    segs = {'realA': WR.REALA, 'realB': REALB, 'realC': WR.REALC}
    eight, lineage = {}, {}
    for p in pools:
        for arm in ('base', 'gate'):
            eight[f'{p}|{arm}'] = {sn: _seg_metrics(R[(p, arm, 'stress')], a, b)
                                   for sn, (a, b) in segs.items()}
        for arm in ('base', 'gate'):
            lineage[f'{p}|{arm}'] = {sn: _seg_metrics(R[(p, arm, 'default')], a, b)
                                     for sn, (a, b) in segs.items()}
    hd = json.load(open('/workspace/repo_ready/research/wo_hd/wo_hd_result.json'))['eight_col_table']
    for p in pools:
        for arm in ('base', 'gate_pause'):
            for sn in ('realA', 'realC'):
                ref = hd[f'{p}|{arm}'][sn]
                mine = lineage[f'{p}|{"base" if arm == "base" else "gate"}'][sn]
                dann = abs(ref['annualized_pct'] - mine['annualized_pct'])
                dmdd = abs(ref['mdd_pct'] - mine['mdd_pct'])
                lineage[f'{p}|{arm}|{sn}|vs_wo_hd'] = {
                    'ann_absdiff': round(dann, 4), 'mdd_absdiff': round(dmdd, 4),
                    'within_0.01pp': bool(dann <= 0.01 and dmdd <= 0.01)}
                assert dann <= 0.01 and dmdd <= 0.01, f'D0-3 FAIL {p} {arm} {sn}'

    # ---- 主判（PW3-2/3/4）
    primary, pvals = {}, []
    for p in pools:
        gc = pd.Series({pd.Timestamp(k): v
                        for k, v in R[(p, 'gate', 'stress')]['curve'].items()}).sort_index()
        lc = pd.Series({pd.Timestamp(k): v
                        for k, v in R[(p, 'gate_lag', 'stress')]['curve'].items()}).sort_index()
        bc = pd.Series({pd.Timestamp(k): v
                        for k, v in R[(p, 'base', 'stress')]['curve'].items()}).sort_index()
        row = {}
        for arm, cv in (('gate', gc), ('gate_lag', lc)):
            for wn, (a, b) in (('FULL', WR.FULL), ('HOLDOUT', WR.HOLD)):
                gs, bs = WR.seg_stats(cv, a, b), WR.seg_stats(bc, a, b)
                avoid = round(gs['ret_pp'] - bs['ret_pp'], 4)
                mdd_red = round((abs(bs['mdd_pct']) - abs(gs['mdd_pct']))
                                / abs(bs['mdd_pct']) * 100, 2) if bs['mdd_pct'] != 0 else None
                row[f'{arm}|{wn}'] = {'gated': gs, 'base': bs,
                                      'avoid_pp': avoid, 'mdd_red_pct': mdd_red}
        diff = (gc.pct_change() - bc.pct_change()).dropna()
        diff = diff[(diff.index >= WR.FULL[0]) & (diff.index <= WR.FULL[1])]
        pv = WR.boot_p_one_sided(diff.values)
        row['p_full_avoid_gt0'] = pv
        pvals.append(pv)
        primary[p] = row
    rej = WR.bh_fdr(pvals, q=0.10)
    selected = {}
    for (p, rj) in zip(pools, rej):
        f, h = primary[p]['gate|FULL'], primary[p]['gate|HOLDOUT']
        primary[p]['fdr_reject_full'] = bool(rj)
        selected[p] = bool(rj and f['avoid_pp'] > 0 and h['avoid_pp'] > 0
                           and f['mdd_red_pct'] >= 10 and h['mdd_red_pct'] >= 10)
        primary[p]['selected'] = selected[p]

    # ---- T1/T2/T3
    t1, t2, t3 = {}, {}, {}
    for p in pools:
        t1[p] = {sn: _direction_blind(p, R[(p, 'base', 'stress')], a, b)
                 for sn, (a, b) in (('realB', REALB), ('realC', WR.REALC),
                                    ('holdout', WR.HOLD))}
        row = {}
        for wn in ('FULL', 'HOLDOUT'):
            g = primary[p][f'gate|{wn}']
            l = primary[p][f'gate_lag|{wn}']
            row[wn] = {'gate_avoid_pp': g['avoid_pp'], 'lag_avoid_pp': l['avoid_pp'],
                       'gate_mdd_red': g['mdd_red_pct'], 'lag_mdd_red': l['mdd_red_pct'],
                       'avoid_sign_flip': bool(g['avoid_pp'] > 0) != bool(l['avoid_pp'] > 0)}
        t2[p] = {**row, 'lag_robust': bool(
            primary[p]['gate_lag|FULL']['avoid_pp'] > 0
            and primary[p]['gate_lag|HOLDOUT']['avoid_pp'] > 0)}
        # T3 realB 锁死量化
        b_r = R[(p, 'base', 'stress')]
        g_r = R[(p, 'gate', 'stress')]
        bs, gs = WR.seg_stats(pd.Series({pd.Timestamp(k): v for k, v in b_r['curve'].items()}
                                        ).sort_index(), *REALB), \
            WR.seg_stats(pd.Series({pd.Timestamp(k): v for k, v in g_r['curve'].items()}
                                   ).sort_index(), *REALB)
        diag_b = _off_diag(p, b_r, *REALB)
        yrs = (REALB[1] - REALB[0]).days / 365.25
        t3[p] = {'off_diag_realB': diag_b,
                 'base_realB': bs, 'gate_realB': gs,
                 'missed_cost_pp': round(bs['ret_pp'] - gs['ret_pp'], 4),
                 'missed_cost_ann_pp': round(bs['ret_pp'] / yrs - gs['ret_pp'] / yrs, 4)}
        # PW3-9 止损避损台账（realC）
        def stop_pp(res, w):
            a, b_ = w
            tot, n = 0.0, 0
            for tr in res['trades'].values():
                cd = tr['close_date']
                if cd is None or not (str(a.date()) <= cd <= str(b_.date())):
                    continue
                if tr['exit_reason'] == 'stop':
                    n += 1
                    tot += (tr['price_pnl'] + tr['entry_fee'] + tr['exit_fee']
                            + tr['funding']) * 100
            return {'stop_n': n, 'stop_pp': round(tot, 2)}
        sb, sg = stop_pp(b_r, WR.REALC), stop_pp(g_r, WR.REALC)
        t3[p]['stop_ledger_realC'] = {
            'base': sb, 'gate': sg,
            'avoided_pp': round(sb['stop_pp'] - sg['stop_pp'], 2),
            'avoided_amt_pct': round((sb['stop_pp'] - sg['stop_pp'])
                                     / abs(sb['stop_pp']) * 100, 2) if sb['stop_pp'] < 0 else None,
            'avoided_n_pct': round((sb['stop_n'] - sg['stop_n']) / sb['stop_n'] * 100, 2)
            if sb['stop_n'] else None}

    overall = bool(all(selected.values()) and all(t2[p]['lag_robust'] for p in pools))
    out = {'stage': 'w3_gate_v2', 'ts': time.strftime('%F %T'),
           'od': 'PW3-1..PW3-10（见头注，冻结）',
           'gate_config': 'vol20>realA p80 → OFF pause（唯一冻结配置，禁面扫描）',
           'fee_calibers': {'stress(主判)': {'FEE_SIDE': FEE_SIDE_S, 'FUNDING': FUNDING_S},
                            'default(谱系对拍)': {'FEE_SIDE': DE.FEE_SIDE, 'FUNDING': DE.FUNDING}},
           'd0': d0, 'threshold_check_vs_wo_hd': thr_chk,
           'eight_col_stress': eight, 'eight_col_default_lineage': lineage,
           'primary': primary, 'fdr': {'method': 'BH', 'q': 0.10, 'm': 4,
                                       'family': '2 池 × {FULL,HOLDOUT} 单侧 p'},
           'T1_direction_blind': t1, 'T2_lag_robustness': t2, 'T3_realB_lock': t3,
           'selected': selected,
           'overall': 'PASS' if overall else 'FAIL',
           'wall_secs': round(time.time() - t0, 1)}
    for r in runs_raw:
        r.pop('day_cum', None)
        r.pop('trades', None)
    with open(os.path.join(OUT, 'w3_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('W3 完成', out['wall_secs'], 's；总判定', out['overall'],
          '；selected=', selected)
    return out


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which in ('w2', 'all'):
        stage_w2()
    if which in ('w3', 'all'):
        stage_w3()
