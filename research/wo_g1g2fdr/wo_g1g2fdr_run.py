#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G1 半开门 + G2 方向叠加（门域合并预注册工单）+ 因子域 FDR 收官扫描 · 144 池定版
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/W2W3_VERDICT.md 首席终裁条款：
- 门域下轮 = G1 半开门 + G2 方向叠加合并预注册（1 张工单）；
- W2 死亡证明 = 分类器族 FDR 扫描收官工单（b 族之外 6-8 族全扫 + 跨族 BH
  q=0.10，预期无幸存者则颁发因子域合法死亡证明，含穷举清单+复活条件）；
- 144 池定版（扩容已否决不再列变体，禁碰新标的）；R8=Pool(32)；seed=42；
- R9：每个「死」字必须附穷举证据；D0 对拍先过（maxdiff=0），任一不过即停工。
- 既有实现复用：wo_rescue/wo_rescue_run.py（run_gate/seg_stats/boot_p_one_sided/
  bh_fdr/IC 判据件）；wo_w2w3/wo_w2w3_run.py（run_gate_dr 记账增强、W2 判线口径、
  T1/T2/T3 检验件、八列谱系对拍）；wo_hd 八列谱系；dneg_engine 权威谱系。

【G1 预注册（PG1-1..PG1-9，先冻结后运行）】
PG1-1 门信号=唯一冻结配置 vol20>realA p80（W3 PW3-1 承继，禁面扫描）；本单
  扫描的参数空间仅限 OFF 语义（首席条款「半开门」细化），门信号不扫。
PG1-2 OFF 语义参数空间（写死 4 档，全覆盖首席条款两个方向，禁止事后加档）：
  S0 v2_full_stop=W3 现状（OFF 停开仓+停换仓，存量止损/崩市照常）——参照臂非新变体；
  S1 risk_half=降险 50%（OFF 时 rebalance 照常执行但开仓 slot×0.5——「保留部分敞口」）；
  S2 open_full_nosell=只停换仓/减仓、不止开仓（OFF 时新开仓照常全额 slot，停换仓卖出）；
  S3 open_half_nosell=S2×降险复合（OFF 时停换仓卖出、新开仓半额 slot）。
PG1-3 费压口径=PB-5 承继（FEE_SIDE×1.5/FUNDING×1.5），base 臂同费对比；主判数字
  以费压臂为准；default 费仅用于 D0 谱系对拍，两套不混。
PG1-4 双窗=FULL+HOLDOUT（PB-6 承继）；主判据=PB-7/8 承继：avoid_pp=臂段净收益(pp)
  −base 臂段净收益(pp)；mdd_red=(|base MDD|−|臂 MDD|)/|base MDD|×100；
  达标=avoid>0 且 mdd_red≥10% 双窗同满足。
PG1-5 p 值=PB-9 承继：FULL 窗日净收益差（臂−base）stationary bootstrap（块长均10、
  1000 次、seed=42）单侧 p=P(boot mean≤0)。
PG1-6 FDR（合并预注册族）：BH q=0.10，族=新变体全集 {G1:S1/S2/S3 + G2:3 变体}
  ×2 池=12 个单侧 p（m=12 如实记账；v2 参照臂与 base 不进族——非本轮新变体）。
PG1-7 三教训针对性检验（W3 T1/T2/T3 承继，逐变体）：
  T2' 滞后稳健：gate_map=cond.shift(1) 全指标重跑，FULL/HOLDOUT avoid>0 不翻转；
  T3' 反弹锁死：realB 段臂净收益 vs v2 参照臂（踏空改善=臂 realB ret_pp>v2 realB
      ret_pp）+ realC 避损保持（臂 realC ret_pp−base realC ret_pp>0）；
  T1' 方向盲：OFF 日 base 净日收益双侧检验（v2 map vs G2 map 对照——G2 判定增益）。
PG1-8 八列段指标（双池×臂×realA/realB/realC，wo_hd seg_metrics 谱系逐行复用）。
PG1-9 D0 对拍先过（任一不过即停工）：①门禁用+default 费 vs dneg_engine.run_instr
  maxdiff=0、fees 差=0；②本单引擎（v2_full_stop+gate on）vs wo_rescue.run_gate
  逐位一致；③default 费 base 臂 realA/realC 段指标 vs wo_hd 八列 ≤0.01pp；
  ④费压 v2 参照臂 FULL avoid_pp vs W3 存档值 ≤0.01pp（跨单谱系对拍）。

【G2 预注册（PG2-1..PG2-7，先冻结后运行）】
PG2-1 机制=方向叠加门：OFF = vol_hi ∧ 方向向下（T1 方向盲的对冲件，首席条款
  「OFF 时若 idx/广度方向仍向上则不停，向下才停」）。
PG2-2 方向定义参数空间（写死 3 变体，禁止事后加档）：
  D1 g2_ma：方向向下=池等权 idx<MA50（dneg MA_REG=50 谱系）；
  D2 g2_mom：方向向下=idx 20 日收益<0；
  D3 g2_br：广度方向向下=breadth<其 20 日均值（覆盖「idx/广度方向」的广度侧）。
PG2-3 OFF 语义=v2_full_stop（方向叠加只改门触发条件，不与 G1 语义交叉——
  交叉格 3×3=9 不跑，登记为边界预写项，若 G1/G2 单独任一过审再立交叉工单）。
PG2-4/5/6/7 = PG1-3..PG1-9 逐字承继（同费压/同双窗/同判据/同 FDR 族/同 D0）。

【因子域 FDR 收官预注册（PF-1..PF-10，先冻结后运行）】
PF-1 因子=PC-4 逐字（RS20 异池互指、full144 截面、RS_momentum|fwd20 主判，
  与 W2 同构同口径）；裸上禁令维持。
PF-2 分类器族清单（b 族 vol×breadth 门域之外，写死 10 族 35 态，禁止事后加族）：
  F1 趋势态 idx vs MA{50,100,200}（3 变体×2 态=6）；F2 动量态 idx ret{20,60} 符号
  （2×2=4）；F3 波动率分位态 vol20 tercile realA p33/p66（1×3=3）；F4 vol-of-vol 态
  {vol20 20 日变化符号, vol20 realA p50 水平}（2×2=4）；F5 宽度态 {breadth tercile
  realA p33/p66, breadth<其 MA20}（1×3+1×2=5）；F6 相关态=池内 20 日滚动平均两两
  相关 realA p50（1×2=2）；F7 流动性态=池成交额 20 日均值 realA p50（1×2=2）；
  F8 kmeans 态=[vol20,breadth,ret20] realA 内 z 标准化、KMeans k=3 seed=42 仅 realA
  拟合（1×3=3）；F9 logistic 态=特征[vol20,breadth,ret20,ret60]、目标=idx 未来 5 日
  收益<0、仅 realA 训练（t≤realA 末−5 日防泄漏）、预测概率 realA p33/p66 分态
  （1×3=3）；F10 随机森林态=同 F9 管线 RF(n=200,seed=42)（1×3=3）。
PF-3 态样本门槛：extended 态日数<30 → NOT_TESTABLE（附数登记非判死）；realC 态
  日数<10 → realC 腿 NOT_TESTABLE（附数）。
PF-4 逐态统计（W2 口径承继）：逐日截面 Spearman IC（extended 窗内该态日）+
  十分位 TopBottom 价差（ISO 周信号日∩态日，费后 0.10pp，n_sig<5 不判定）。
PF-5 FDR：BH q=0.10，p=extended 逐日 IC t 统计量单侧上尾 P(T≥t)（df=n−2），
  在全部可测态（n_ext≥30）上施行，m=可测态数如实记账。
PF-6 幸存判线=W2 判线逐字承继：FDR 拒绝 ∧ extended 费后 fwd20 价差>0 ∧ realC
  费后 fwd20 价差>0 ∧ realC 逐日 IC 均值≥0（不翻转）。
PF-7 死亡证明：幸存者=0 → 颁发「因子域合法死亡证明」，须含：①逐族变体计数与
  逐变体证据（n/IC/t/p/BH/判线四项）；②域限定声明（=full144 池 RS_momentum|fwd20
  的状态条件化部署，不外溢到其他因子/池/horizon）；③复活条件。
PF-8 负尾披露：extended IC 显著为负的态如实登记（RS 回归属 c4 双假设中已单独
  判死的另一假设，不构成本因子动量方向的幸存路径，防偷换假设）。
PF-9 边界预写项：hot_broad 型空象限（样本内不可测态）逐态登记；交叉格
  （G1×G2）与 W2 PW2-10 退出成本不在本单范围。
PF-10 D0/谱系：因子侧对拍=无条件 extended IC t/n 与 W2 存档 baseline_144pool
  逐位一致（≤1e-9）；引擎侧同 PG1-9。

用法：python3 wo_g1g2fdr_run.py gate|fdr|all
产出：g1_result.json / g2_result.json / fdr_result.json /（报告另手写 G1G2FDR_REPORT.md）
"""
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy import stats as sst

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根（云端化：禁绝对路径）
sys.path.insert(0, os.path.join(_ROOT, 'research', 'wo_rescue'))
sys.path.insert(0, os.path.join(_ROOT, 'research', 'wo_dneg'))
import wo_rescue_run as WR
import dneg_engine as DE

SEED = 42
OUT = os.path.join(_ROOT, 'research', 'wo_g1g2fdr')
os.makedirs(OUT, exist_ok=True)

REALB = (pd.Timestamp('2026-04-01'), pd.Timestamp('2026-05-31'))
FEE_SIDE_S = WR.FEE_SIDE_S
FUNDING_S = WR.FUNDING_S
FAT_R = 0.08
SLOT_HALF = 0.5         # PG1-2 S1/S3 冻结：降险 50%
MIN_EXT_DAYS = 30       # PF-3 态样本门槛
MIN_RC_DAYS = 10
SPREAD_MIN_N = 5        # PF-4 周信号日门槛（W2 承继）

G1_ARMS = ['g1_risk_half', 'g1_open_full_nosell', 'g1_open_half_nosell']
G2_ARMS = ['g2_ma', 'g2_mom', 'g2_br']
NEW_ARMS = G1_ARMS + G2_ARMS          # FDR 族=6 变体×2 池=12（PG1-6）

SEGS = {'realA': WR.REALA, 'realB': REALB, 'realC': WR.REALC}


# ============================================================ D0 增强版门引擎（G1 语义扩展）
def run_gate_g(syms, gate_map=None, off_mode='v2_full_stop', fee=None, fund=None):
    """逐行复制 wo_w2w3.run_gate_dr（D0 谱系），仅扩展 OFF 语义参数 off_mode
    （PG1-2 四档冻结）。off_mode='v2_full_stop' 且 gate_map=None 时与
    dneg_engine.run_instr / wo_rescue.run_gate 逐位一致（D0 断言强制）。"""
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
            # ---- PG1-2 OFF 语义四档（唯一新增分支，其余逐行不动）----
            if off_next and off_mode == 'v2_full_stop':
                sell_skip, do_open, slot_mult = True, False, 1.0
            elif off_next and off_mode == 'risk_half':
                sell_skip, do_open, slot_mult = False, True, SLOT_HALF
            elif off_next and off_mode == 'open_full_nosell':
                sell_skip, do_open, slot_mult = True, True, 1.0
            elif off_next and off_mode == 'open_half_nosell':
                sell_skip, do_open, slot_mult = True, True, SLOT_HALF
            else:
                sell_skip, do_open, slot_mult = False, True, 1.0
            if not sell_skip:
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
            if do_open:
                for s in target:
                    if s in pos or s in stopped_today:
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        continue
                    budget = min(DE.SLOT * slot_mult * eq_sig, max(cash, 0.0))
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
            target = [] if (off_next and off_mode == 'v2_full_stop') else list(score.index[:DE.TOP_N])
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity, off_next) \
                if cal.get_loc(t) + 1 < len(cal) else None

    curve = pd.Series(eq).sort_index()
    end = cal[-1]
    for s, p in pos.items():
        trades[tid_of[s]].update(close_date=str(end.date()), exit_px=float(mark.at[end, s]),
                                 exit_reason='eow')
    return {'curve': curve, 'fees': fees, 'turnover': turnover, 'n_rebal': n_rebal,
            'n_gate_off': n_gate_off, 'trades': trades, 'day_cum': day_cum}


# ============================================================ 门信号（PG1-1/PG2-1/2 冻结）
def _pool_idx(pname):
    close = pd.DataFrame({s: WR._DATA[s]['close'] for s in WR._POOLS[pname]})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(WR._DATA[s].index) for s in WR._POOLS[pname]])))
    return close.reindex(cal).mean(axis=1)


def gate_maps(pname, lag=0):
    """PG1-1/PG2-2 冻结门信号：v2=vol_hi；G2=vol_hi∧方向向下（3 变体）。"""
    gv = WR._GV[pname]
    vol_hi = gv['vol'] > gv['vol_thr'][80]
    idx = _pool_idx(pname)
    above = (pd.DataFrame({s: WR._DATA[s]['close'] for s in WR._POOLS[pname]})
             .reindex(gv['vol'].index))
    breadth = (above > above.rolling(50, min_periods=40).mean()).mean(axis=1) * 100.0
    dirs = {
        'v2': pd.Series(True, index=vol_hi.index),
        'g2_ma': idx < idx.rolling(DE.MA_REG).mean(),          # PG2-2 D1
        'g2_mom': idx.pct_change(20) < 0,                      # PG2-2 D2
        'g2_br': breadth < breadth.rolling(20).mean(),         # PG2-2 D3
    }
    out = {}
    for k, d in dirs.items():
        cond = (vol_hi & d.fillna(False))
        if lag:
            cond = cond.shift(lag)
        out[k] = cond.fillna(False)
    return out


ARM_DEF = {  # arm -> (gate_key, off_mode)
    'v2': ('v2', 'v2_full_stop'),
    'g1_risk_half': ('v2', 'risk_half'),
    'g1_open_full_nosell': ('v2', 'open_full_nosell'),
    'g1_open_half_nosell': ('v2', 'open_half_nosell'),
    'g2_ma': ('g2_ma', 'v2_full_stop'),
    'g2_mom': ('g2_mom', 'v2_full_stop'),
    'g2_br': ('g2_br', 'v2_full_stop'),
}
LAG_ARMS = ['v2'] + G1_ARMS + G2_ARMS


# ============================================================ 工件（谱系复用）
def _seg_metrics(res, t0, t1):
    """wo_hd seg_metrics 谱系逐行复用（= wo_w2w3 同款）。"""
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


def _off_diag(gate, base_res, t0, t1):
    o = gate[(gate.index >= t0) & (gate.index <= t1)]
    curve = pd.Series({pd.Timestamp(k): v for k, v in base_res['curve'].items()}).sort_index()
    ret = curve.pct_change()
    r = ret[(ret.index >= t0) & (ret.index <= t1)]
    od = o[o]
    flips = int((o.astype(int).diff().abs() == 1).sum())
    eps = int((o.astype(int).diff() == 1).sum() + (1 if len(o) and o.iloc[0] else 0))
    return {'off_days': int(len(od)), 'off_share_pct': round(len(od) / max(len(o), 1) * 100, 2),
            'off_episodes': eps, 'flips': flips,
            'off_hit_rate_pct': (round(float((r[od.index] < 0).mean()) * 100, 2)
                                 if len(od) else None), 'n_days': int(len(o))}


def _direction_blind(gate, base_res, t0, t1):
    """T1' 方向盲（W3 T1 承继，gate 作为入参以对照 v2 vs G2）。"""
    curve = pd.Series({pd.Timestamp(k): v for k, v in base_res['curve'].items()}).sort_index()
    ret = curve.pct_change() * 100.0
    o = gate[(gate.index >= t0) & (gate.index <= t1)]
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


def _gate_worker(task):
    pname, arm, fmode = task
    WR._init()
    syms = WR._POOLS[pname]
    lag = 1 if arm.endswith('_lag') else 0
    base_arm = arm[:-4] if lag else arm
    if base_arm == 'base':
        gmap = None
        off_mode = 'v2_full_stop'
    else:
        gk, off_mode = ARM_DEF[base_arm]
        gmap = gate_maps(pname, lag=lag)[gk].to_dict()
    fee, fund = (FEE_SIDE_S, FUNDING_S) if fmode == 'stress' else (DE.FEE_SIDE, DE.FUNDING)
    g = run_gate_g(syms, gate_map=gmap, off_mode=off_mode, fee=fee, fund=fund)
    return {'arm': arm, 'pname': pname, 'fmode': fmode,
            'n_gate_off': g['n_gate_off'],
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()},
            'fees': float(g['fees']), 'turnover': float(g['turnover']),
            'day_cum': [(str(t.date()), float(f), float(tv)) for t, f, tv in g['day_cum']],
            'trades': g['trades']}


def _curve(res):
    return pd.Series({pd.Timestamp(k): v for k, v in res['curve'].items()}).sort_index()


def _primary(arm_curve, base_curve):
    """PG1-4/5 主判件（PB-7/8/9 承继）。返回双窗 avoid/mdd_red + FULL 单侧 p。"""
    row = {}
    for wn, (a, b) in (('FULL', WR.FULL), ('HOLDOUT', WR.HOLD)):
        gs, bs = WR.seg_stats(arm_curve, a, b), WR.seg_stats(base_curve, a, b)
        avoid = round(gs['ret_pp'] - bs['ret_pp'], 4)
        mdd_red = round((abs(bs['mdd_pct']) - abs(gs['mdd_pct']))
                        / abs(bs['mdd_pct']) * 100, 2) if bs['mdd_pct'] != 0 else None
        row[wn] = {'arm': gs, 'base': bs, 'avoid_pp': avoid, 'mdd_red_pct': mdd_red}
    diff = (arm_curve.pct_change() - base_curve.pct_change()).dropna()
    diff = diff[(diff.index >= WR.FULL[0]) & (diff.index <= WR.FULL[1])]
    row['p_full_avoid_gt0'] = WR.boot_p_one_sided(diff.values)
    return row


# ============================================================ 门域阶段（G1+G2 合并预注册）
def stage_gate():
    t0 = time.time()
    WR._init()
    pools = list(WR._POOLS)
    arms = ['base', 'v2'] + G1_ARMS + G2_ARMS
    tasks = [(p, a, 'stress') for p in pools for a in arms] \
        + [(p, a + '_lag', 'stress') for p in pools for a in LAG_ARMS] \
        + [(p, 'base', 'default') for p in pools] \
        + [(p, 'v2', 'default') for p in pools]
    with Pool(32) as pool:
        runs_raw = pool.map(_gate_worker, tasks)
    R = {(r['pname'], r['arm'], r['fmode']): r for r in runs_raw}

    # ---- D0 对拍先过（PG1-9，任一不过即停工）
    d0 = {}
    for p in pools:
        ref = DE.run_instr(WR._DATA, F=WR._F, syms=WR._POOLS[p], gated=False, record=True)
        mc = _curve(R[(p, 'base', 'default')])
        md = float((mc - ref['curve']).abs().max())
        fd = float(abs(R[(p, 'base', 'default')]['fees'] - ref['fees']))
        v2map = gate_maps(p)['v2'].to_dict()
        wr = WR.run_gate(WR._POOLS[p], gate_map=v2map, fee=DE.FEE_SIDE, fund=DE.FUNDING)
        md2 = float((_curve(R[(p, 'v2', 'default')]) - wr['curve']).abs().max())
        fd2 = float(abs(R[(p, 'v2', 'default')]['fees'] - wr['fees']))
        hd = json.load(open(os.path.join(_ROOT, 'research', 'wo_hd', 'wo_hd_result.json')))['eight_col_table']
        e8 = _seg_metrics(R[(p, 'base', 'default')], *WR.REALA)
        e8c = _seg_metrics(R[(p, 'base', 'default')], *WR.REALC)
        r8 = hd[f'{p}|base']['realA']
        d_ann = abs(e8['annualized_pct'] - r8['annualized_pct'])
        d_mdd = abs(e8['mdd_pct'] - r8['mdd_pct'])
        c_ann = abs(e8c['annualized_pct'] - hd[f'{p}|base']['realC']['annualized_pct'])
        c_mdd = abs(e8c['mdd_pct'] - hd[f'{p}|base']['realC']['mdd_pct'])
        w3 = json.load(open(os.path.join(_ROOT, 'research', 'wo_w2w3', 'w3_result.json')))
        w3_avoid = w3['primary'][p]['gate|FULL']['avoid_pp']
        mine_avoid = _primary(_curve(R[(p, 'v2', 'stress')]), _curve(R[(p, 'base', 'stress')]))['FULL']['avoid_pp']
        d_w3 = abs(mine_avoid - w3_avoid)
        d0[p] = {'vs_dneg_maxdiff': md, 'vs_dneg_fees_absdiff': fd,
                 'vs_wo_rescue_run_gate_maxdiff': md2, 'vs_wo_rescue_fees_absdiff': fd2,
                 'vs_wo_hd_realA_ann_mdd_absdiff': [round(d_ann, 4), round(d_mdd, 4)],
                 'vs_wo_hd_realC_ann_mdd_absdiff': [round(c_ann, 4), round(c_mdd, 4)],
                 'v2_stress_FULL_avoid_vs_w3_absdiff': round(d_w3, 4)}
        assert md == 0 and fd == 0, f'D0-1 FAIL {p}: {d0[p]}'
        assert md2 == 0 and fd2 == 0, f'D0-2 FAIL {p}: {d0[p]}'
        assert d_ann <= 0.01 and d_mdd <= 0.01 and c_ann <= 0.01 and c_mdd <= 0.01, \
            f'D0-3 FAIL {p}: {d0[p]}'
        assert d_w3 <= 0.01, f'D0-4 FAIL {p}: {d0[p]}'

    # ---- 八列段指标（PG1-8，费压臂）
    eight = {}
    for p in pools:
        for arm in arms:
            eight[f'{p}|{arm}'] = {sn: _seg_metrics(R[(p, arm, 'stress')], a, b)
                                   for sn, (a, b) in SEGS.items()}

    # ---- 主判 + FDR（PG1-4/5/6 合并族 m=12）
    primary, pvals, keys = {}, [], []
    for p in pools:
        bc = _curve(R[(p, 'base', 'stress')])
        primary[p] = {'v2_ref': _primary(_curve(R[(p, 'v2', 'stress')]), bc)}
        for arm in NEW_ARMS:
            row = _primary(_curve(R[(p, arm, 'stress')]), bc)
            lrow = _primary(_curve(R[(p, arm + '_lag', 'stress')]), bc)
            row['lag_FULL_avoid_pp'] = lrow['FULL']['avoid_pp']
            row['lag_HOLDOUT_avoid_pp'] = lrow['HOLDOUT']['avoid_pp']
            row['lag_robust'] = bool(lrow['FULL']['avoid_pp'] > 0 and lrow['HOLDOUT']['avoid_pp'] > 0)
            row['fdr_reject_full'] = None
            primary[p][arm] = row
            pvals.append(row['p_full_avoid_gt0'])
            keys.append((p, arm))
    rej = WR.bh_fdr(pvals, q=0.10)

    # ---- 三教训针对性检验 + 幸存判线（PG1-7）
    t_checks, selected = {}, {}
    for (p, arm), rj in zip(keys, rej):
        row = primary[p][arm]
        row['fdr_reject_full'] = bool(rj)
        gmap_lag0 = gate_maps(p)[ARM_DEF[arm][0]]
        # T3' 反弹锁死：realB 踏空改善 vs v2 参照 + realC 避损保持
        realb_arm = WR.seg_stats(_curve(R[(p, arm, 'stress')]), *REALB)
        realb_v2 = WR.seg_stats(_curve(R[(p, 'v2', 'stress')]), *REALB)
        realc_arm = WR.seg_stats(_curve(R[(p, arm, 'stress')]), *WR.REALC)
        realc_base = WR.seg_stats(_curve(R[(p, 'base', 'stress')]), *WR.REALC)
        t3 = {'realB_arm_ret_pp': realb_arm['ret_pp'], 'realB_v2_ret_pp': realb_v2['ret_pp'],
              'realB_improve_vs_v2_pp': round(realb_arm['ret_pp'] - realb_v2['ret_pp'], 4),
              'realC_avoid_pp': round(realc_arm['ret_pp'] - realc_base['ret_pp'], 4),
              'realB_off_diag': _off_diag(gmap_lag0, R[(p, 'base', 'stress')], *REALB)}
        # T1' 方向盲（G2 对照：OFF 日均值 v2 vs 本臂门）
        t1 = {}
        for sn, (a, b) in (('realB', REALB), ('realC', WR.REALC), ('holdout', WR.HOLD)):
            t1[sn] = _direction_blind(gmap_lag0, R[(p, 'base', 'stress')], a, b)
        sel = bool(rj
                   and row['FULL']['avoid_pp'] > 0 and row['HOLDOUT']['avoid_pp'] > 0
                   and row['FULL']['mdd_red_pct'] >= 10 and row['HOLDOUT']['mdd_red_pct'] >= 10
                   and row['lag_robust']
                   and t3['realB_improve_vs_v2_pp'] > 0 and t3['realC_avoid_pp'] > 0)
        row['selected'] = sel
        selected[f'{p}|{arm}'] = sel
        t_checks[f'{p}|{arm}'] = {'T1_direction_blind': t1, 'T3_realB_unlock': t3}
    # v2 参照臂的 T1 对照（方向过滤增益的基线读数）
    for p in pools:
        t_checks[f'{p}|v2_ref'] = {
            sn: _direction_blind(gate_maps(p)['v2'], R[(p, 'base', 'stress')], a, b)
            for sn, (a, b) in (('realB', REALB), ('realC', WR.REALC), ('holdout', WR.HOLD))}

    fdr_block = {'method': 'BH', 'q': 0.10, 'm': len(pvals),
                 'family': '合并预注册新变体 {G1:S1/S2/S3 + G2:D1/D2/D3} × 2 池 '
                           '= 12 个 FULL 窗单侧 p（v2 参照臂/base 不进族）',
                 'pvals': {f'{p}|{a}': v for (p, a), v in zip(keys, pvals)},
                 'reject': {f'{p}|{a}': bool(v) for (p, a), v in zip(keys, rej)}}

    common = {'ts': time.strftime('%F %T'), 'pool': '严格 144 池定版（old131+new13，禁碰新标的）',
              'seed': SEED, 'fee_calibers': {'stress(主判)': {'FEE_SIDE': FEE_SIDE_S, 'FUNDING': FUNDING_S},
                                             'default(谱系对拍)': {'FEE_SIDE': DE.FEE_SIDE, 'FUNDING': DE.FUNDING}},
              'd0': d0, 'fdr': fdr_block, 'selected': selected,
              'verdict_rule': 'PG1-7：FDR 幸存 ∧ 双窗 avoid>0 ∧ 双窗 mdd_red≥10 ∧ '
                              'T2 滞后不翻转 ∧ T3 realB 踏空改善 vs v2>0 ∧ realC 避损保持>0',
              'wall_secs': round(time.time() - t0, 1)}

    # ---- g1_result.json / g2_result.json
    for fname, arm_set, od in (('g1_result.json', G1_ARMS,
                                'PG1-1..PG1-9（见头注，冻结）：OFF 语义 4 档参数空间写死，门信号不扫'),
                               ('g2_result.json', G2_ARMS,
                                'PG2-1..PG2-7（见头注，冻结）：方向定义 3 变体写死，'
                                'OFF 语义=v2_full_stop；交叉格 3×3 登记为边界预写项（PF-9）')):
        arms_r = ['v2'] + arm_set
        pr = {p: {'v2_ref': primary[p]['v2_ref'],
                  **{a: primary[p][a] for a in arm_set}} for p in pools}
        e8r = {k: v for k, v in eight.items() if k.split('|')[1] in arms_r}
        tc = {k: v for k, v in t_checks.items()
              if k.endswith('v2_ref') or k.split('|')[1] in arm_set}
        sel = {k: v for k, v in selected.items() if k.split('|')[1] in arm_set}
        out = {'stage': fname.split('.')[0], 'od': od, **common,
               'eight_col_stress': e8r, 'primary': pr, 'T_checks': tc, 'selected': sel}
        n_sel = sum(sel.values())
        out['overall'] = ('PASS_DEPLOY_CANDIDATE' if n_sel == len(arm_set) * len(pools)
                          else ('PARTIAL' if n_sel > 0 else 'FAIL'))
        with open(os.path.join(OUT, fname), 'w') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(fname, '完成；overall=', out['overall'], '; selected=', sel)

    for r in runs_raw:
        r.pop('day_cum', None)
        r.pop('trades', None)
    return common


# ============================================================ 因子域 FDR 收官（PF-1..PF-10）
def _state_vars(pname='full144'):
    """PF-2 十族 35 态的全部状态变量（realA 内估计阈值/拟合，无前瞻）。"""
    names = WR._POOLS[pname]
    C = pd.DataFrame({s: WR._DATA[s]['close'] for s in names}).sort_index()
    V = pd.DataFrame({s: WR._DATA[s]['volume'] for s in names}).reindex(C.index)
    idx = C.mean(axis=1)
    gv = WR._GV[pname]
    vol20 = gv['vol'].reindex(C.index)
    breadth = gv['breadth'].reindex(C.index)
    ret20 = idx.pct_change(20)
    ret60 = idx.pct_change(60)
    ra_mask = (C.index >= WR.REALA[0]) & (C.index <= WR.REALA[1])
    ra = C.index[ra_mask]

    def ra_q(sr, q):
        return float(sr[ra].quantile(q))

    # F6 相关态：池内 20 日滚动平均两两相关（逐日 corr 矩阵，仅 extended 日计算）
    R = C.pct_change()
    ext_mask = (C.index >= WR.FULL[0]) & (C.index <= WR.FULL[1])
    pos = {d: i for i, d in enumerate(C.index)}
    avg_corr = pd.Series(np.nan, index=C.index)
    arr = R.values
    n_s = len(names)
    for d in C.index[ext_mask]:
        i = pos[d]
        if i < 19:
            continue
        w = arr[i - 19:i + 1]
        ok = np.isfinite(w).all(axis=0)
        if ok.sum() < 30:
            continue
        cm = np.corrcoef(w[:, ok], rowvar=False)
        k = cm.shape[0]
        avg_corr[d] = float((cm.sum() - k) / (k * (k - 1)))
    # F7 流动性态：池成交额 20 日均值
    dvol = (C * V).sum(axis=1)
    liq20 = dvol.rolling(20).mean()

    feats_km = pd.DataFrame({'vol20': vol20, 'breadth': breadth, 'ret20': ret20})
    mu, sd = feats_km.loc[ra].mean(), feats_km.loc[ra].std(ddof=1).replace(0, 1)
    z_km = (feats_km - mu) / sd
    from sklearn.cluster import KMeans
    ok_km = z_km.notna().all(axis=1)
    km = KMeans(n_clusters=3, n_init=10, random_state=SEED).fit(z_km[ok_km & ra_mask])
    km_lab = pd.Series(np.nan, index=C.index, dtype=object)
    km_lab[ok_km] = km.predict(z_km[ok_km]).astype(object)

    # F9/F10 监督态：仅 realA 训练（t ≤ realA 末−5 日防泄漏），目标=idx 未来 5 日收益<0
    y = (idx.shift(-5) / idx - 1 < 0).astype(float)
    feats_sup = pd.DataFrame({'vol20': vol20, 'breadth': breadth, 'ret20': ret20, 'ret60': ret60})
    train_mask = ra_mask & (C.index <= ra[-1] - pd.Timedelta(days=7)) \
        & feats_sup.notna().all(axis=1) & y.notna()
    Xtr, ytr = feats_sup[train_mask], y[train_mask]
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    sc = StandardScaler().fit(Xtr)
    probs = {}
    for nm, mdl in (('logistic', LogisticRegression(max_iter=1000, random_state=SEED)),
                    ('rf', RandomForestClassifier(n_estimators=200, random_state=SEED, n_jobs=1))):
        m = mdl.fit(sc.transform(Xtr), ytr)
        pr_all = pd.Series(m.predict_proba(sc.transform(feats_sup.fillna(feats_sup.loc[ra].mean())))
                           [:, 1], index=C.index)
        pr_all[feats_sup.isna().any(axis=1)] = np.nan
        p33, p66 = pr_all[ra].quantile(1 / 3), pr_all[ra].quantile(2 / 3)
        probs[nm] = (pr_all, p33, p66)

    SV = {'idx': idx, 'vol20': vol20, 'breadth': breadth, 'ret20': ret20, 'ret60': ret60,
          'avg_corr': avg_corr, 'liq20': liq20, 'ra': ra,
          'km_lab': km_lab, 'probs': probs}
    # 族清单（PF-2 写死 10 族 35 态）
    fam = {}
    for ma in (50, 100, 200):
        fam[f'F1_trend_ma{ma}'] = pd.Series(np.where(idx > idx.rolling(ma).mean(), 'above', 'below'),
                                            index=C.index)
    for h in (20, 60):
        fam[f'F2_mom_ret{h}'] = pd.Series(np.where(idx.pct_change(h) > 0, 'up', 'down'), index=C.index)
    p33v, p66v = ra_q(vol20, 1 / 3), ra_q(vol20, 2 / 3)
    fam['F3_vol_tercile'] = pd.Series(np.select([vol20 <= p33v, vol20 <= p66v], ['low', 'mid'], 'high'),
                                      index=C.index)
    vov_chg = vol20.pct_change(20)
    fam['F4_volofvol_chg'] = pd.Series(np.where(vov_chg > 0, 'rising', 'falling'), index=C.index)
    p50v = ra_q(vol20, 0.5)
    fam['F4_volofvol_lvl'] = pd.Series(np.where(vol20 > p50v, 'hi', 'lo'), index=C.index)
    b33, b66 = ra_q(breadth, 1 / 3), ra_q(breadth, 2 / 3)
    fam['F5_breadth_tercile'] = pd.Series(np.select([breadth <= b33, breadth <= b66], ['low', 'mid'], 'high'),
                                          index=C.index)
    fam['F5_breadth_ma20'] = pd.Series(np.where(breadth < breadth.rolling(20).mean(), 'below', 'above'),
                                       index=C.index)
    p50c = ra_q(avg_corr, 0.5)
    fam['F6_corr_p50'] = pd.Series(np.where(avg_corr > p50c, 'hi', 'lo'), index=C.index)
    p50l = ra_q(liq20, 0.5)
    fam['F7_liq_p50'] = pd.Series(np.where(liq20 > p50l, 'hi', 'lo'), index=C.index)
    for k in range(3):
        fam[f'F8_kmeans_c{k}'] = (km_lab == k)
    for nm in ('logistic', 'rf'):
        pr_all, p33, p66 = probs[nm]
        lab = pd.Series(np.select([pr_all <= p33, pr_all <= p66], ['lo', 'mid'], 'hi'),
                        index=C.index).astype(object)
        lab[pr_all.isna()] = None
        for st in ('lo', 'mid', 'hi'):
            fam[f'F9_{nm}_p{st}' if nm == 'logistic' else f'F10_rf_p{st}'] = (lab == st)
    SV['families'] = fam
    return SV


def _sig_days(cal):
    iso = cal.isocalendar()
    return pd.DatetimeIndex(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)


def stage_fdr():
    t0 = time.time()
    WR._init()
    names = WR._POOLS['full144']
    old131 = WR._POOLS['old131']
    new13 = sorted(set(names) - set(old131))
    C = pd.DataFrame({s: WR._DATA[s]['close'] for s in names}).sort_index()
    ret20 = C / C.shift(20) - 1
    idx_old = ret20[old131].mean(axis=1)
    idx_new = ret20[new13].mean(axis=1)
    rs_cross = pd.DataFrame(index=C.index, columns=names, dtype=float)
    for s in names:
        rs_cross[s] = ret20[s] - (idx_new if s in old131 else idx_old)   # PF-1 PC-4 逐字
    fwd20 = C.shift(-20) / C - 1

    # 谱系对拍（PF-10）：无条件 extended IC vs W2 存档
    w2 = json.load(open(os.path.join(_ROOT, 'research', 'wo_w2w3', 'w2_result.json')))
    ic_ext = WR._xsec_ic_series(rs_cross, fwd20)
    t_ext, n_ext = WR._tstat(ic_ext[(ic_ext.index >= WR.REALA[0]) & (ic_ext.index <= WR.REALC[1])])
    reg = w2['baseline_144pool']['extended']['ic']
    lineage_chk = {'recomputed_t_extended': t_ext, 'w2_archived_t_extended': reg['t_stat'],
                   'recomputed_n': n_ext, 'w2_archived_n': reg['n_days'],
                   'absdiff_t': abs(t_ext - reg['t_stat'])}
    assert lineage_chk['absdiff_t'] < 1e-6 and n_ext == reg['n_days'], f'PF-10 FAIL: {lineage_chk}'

    SV = _state_vars()
    sigs = _sig_days(C.index)
    ext0, ext1 = WR.REALA[0], WR.REALC[1]
    rc0, rc1 = WR.REALC

    variants, pmap = {}, []
    for fam_name, lab in SV['families'].items():
        # 【修正注记】pandas 3.x 字符串 Series dtype='str'（非 object），首跑曾致
        # F1..F7 态划分坍缩为全样本单态（对拍证据=其 t 全等于无条件基线 4.9057）；
        # 改用 is_bool_dtype 判定：布尔掩码→in_state；标签序列→逐态拆分。
        if pd.api.types.is_bool_dtype(lab):
            v = {'in_state': lab}
        else:
            states = sorted(set(lab.dropna().unique()))
            v = {st: (lab == st) for st in states}
        for st, mask in v.items():
            mask = mask.reindex(C.index).fillna(False).astype(bool)
            key = f'{fam_name}|{st}'
            days_ext = C.index[(C.index >= ext0) & (C.index <= ext1) & mask]
            row = {'family': fam_name.split('_')[0], 'variant': key,
                   'n_ext_days': int(len(days_ext))}
            if len(days_ext) < MIN_EXT_DAYS:
                row['status'] = 'NOT_TESTABLE_LOW_N(PF-3)'
                variants[key] = row
                continue
            ic = WR._xsec_ic_series(rs_cross.loc[days_ext], fwd20.loc[days_ext])
            t_, n_ic = WR._tstat(ic)
            df = max(n_ic - 2, 1)
            p_one = float(sst.t.sf(t_, df)) if t_ is not None else 1.0
            sig_w = sigs[(sigs >= ext0) & (sigs <= ext1)]
            sig_w = sig_w[sig_w.map(lambda d: mask.at[d])]
            row.update({'status': 'TESTED', 'ic_mean': round(float(ic.mean()), 6),
                        't_stat': round(t_, 4), 'n_ic_days': n_ic,
                        'p_one_sided_upper': round(p_one, 6)})
            if len(sig_w) >= SPREAD_MIN_N:
                raw, net, nsp = WR._decile_spread_fee(rs_cross.loc[sig_w], fwd20.loc[sig_w])
                row['ext_fwd20_decile_pp_net'] = round(net, 4)
                row['n_ext_sig'] = int(nsp)
            else:
                row['ext_fwd20_decile_pp_net'] = None
                row['spread_status'] = f'INSUFFICIENT_N_SIG(<{SPREAD_MIN_N})'
            days_rc = C.index[(C.index >= rc0) & (C.index <= rc1) & mask]
            row['n_realC_days'] = int(len(days_rc))
            if len(days_rc) < MIN_RC_DAYS:
                row['realC_status'] = 'NOT_TESTABLE_LOW_N(PF-3)'
            else:
                ic_rc = WR._xsec_ic_series(rs_cross.loc[days_rc], fwd20.loc[days_rc])
                t_rc, n_rc_ic = WR._tstat(ic_rc)
                row.update({'realC_ic_mean': round(float(ic_rc.mean()), 6),
                            'realC_t_stat': (round(t_rc, 4) if t_rc is not None else None),
                            'realC_n_ic_days': n_rc_ic})
                sig_rc = sigs[(sigs >= rc0) & (sigs <= rc1)]
                sig_rc = sig_rc[sig_rc.map(lambda d: mask.at[d])]
                if len(sig_rc) >= SPREAD_MIN_N:
                    _, net_rc, _ = WR._decile_spread_fee(rs_cross.loc[sig_rc], fwd20.loc[sig_rc])
                    row['realC_fwd20_decile_pp_net'] = round(net_rc, 4)
                else:
                    row['realC_fwd20_decile_pp_net'] = None
                    row['realC_spread_status'] = f'INSUFFICIENT_N_SIG(<{SPREAD_MIN_N})'
            variants[key] = row
            pmap.append((key, p_one))

    # ---- PF-5 跨族 BH FDR
    keys = [k for k, _ in pmap]
    rej = WR.bh_fdr([p for _, p in pmap], q=0.10)
    rej_map = dict(zip(keys, rej))

    # ---- PF-6 幸存判线（W2 判线逐字）+ PF-7/8 判定
    # R9 分级：四腿全齐且至少一腿不过 → FAIL（附数）；腿缺失 → NOT_JUDGABLE（附数登记，
    # 属外推区非「测过且死」）；绝不给无证据的「死」。
    n_testable = 0
    for key, row in variants.items():
        if row['status'] != 'TESTED':
            continue
        n_testable += 1
        row['bh_reject_q010'] = bool(rej_map[key])
        legs_ok = (row.get('ext_fwd20_decile_pp_net') is not None
                   and row.get('realC_fwd20_decile_pp_net') is not None
                   and row.get('realC_ic_mean') is not None)
        if not legs_ok:
            row['w2_line_candidate'] = None
            row['judgment'] = 'NOT_JUDGABLE_INSUFFICIENT_N(判线腿缺失，附数登记 PF-3)'
        else:
            cand = (row['ext_fwd20_decile_pp_net'] > 0
                    and row['realC_fwd20_decile_pp_net'] > 0
                    and row['realC_ic_mean'] >= 0)
            row['w2_line_candidate'] = bool(cand)
            row['judgment'] = 'SURVIVOR' if (row['bh_reject_q010'] and cand) else 'FAIL'
        if row['t_stat'] < 0 and row['p_one_sided_upper'] > 0.5:
            # PF-8 负尾披露（RS 回归为已单独判死的另一假设，不构成动量幸存路径）
            row['note_neg_ext_ic'] = 'PF-8 负尾披露（不构成动量幸存路径）'

    survivors = [k for k, r in variants.items() if r.get('judgment') == 'SURVIVOR']
    # 幸存态分段画像（披露用，realA/realB/realC 逐段 IC/价差）
    surv_profile = {}
    for k in survivors:
        fam_name, st = k.split('|')
        lab = SV['families'][fam_name]
        mask = (lab == st).reindex(C.index).fillna(False).astype(bool) \
            if not pd.api.types.is_bool_dtype(lab) else lab
        prof = {}
        for seg, (a, b) in (('realA', WR.REALA), ('realB', REALB), ('realC', WR.REALC)):
            m = (C.index >= a) & (C.index <= b) & mask.values
            ic = WR._xsec_ic_series(rs_cross.loc[m], fwd20.loc[m])
            t_seg, n_seg = WR._tstat(ic)
            sw = sigs[(sigs >= a) & (sigs <= b)]
            sw = sw[sw.map(lambda d: bool(mask.at[d]))]
            _, net_seg, ns_seg = (WR._decile_spread_fee(rs_cross.loc[sw], fwd20.loc[sw])
                                  if len(sw) >= SPREAD_MIN_N else (None, None, None))
            prof[seg] = {'n_days': int(m.sum()),
                         'ic_mean': round(float(ic.mean()), 4) if len(ic) else None,
                         't_stat': round(t_seg, 4) if t_seg is not None else None,
                         'n_ic_days': n_seg,
                         'fwd20_decile_pp_net': round(net_seg, 4) if net_seg is not None else None,
                         'n_sig': ns_seg}
        surv_profile[k] = prof
    by_family = {}
    for key, r in variants.items():
        f = r['family']
        d = by_family.setdefault(f, {'variants_total': 0, 'tested': 0, 'not_testable': 0,
                                     'not_judgable': 0, 'fail': 0, 'survivor': 0})
        d['variants_total'] += 1
        if r['status'] != 'TESTED':
            d['not_testable'] += 1
        elif r['judgment'] == 'SURVIVOR':
            d['tested'] += 1; d['survivor'] += 1
        elif r['judgment'] == 'FAIL':
            d['tested'] += 1; d['fail'] += 1
        else:
            d['not_judgable'] += 1

    cert = None
    final_verdict = None
    if not survivors:
        cert = {
            'issued': True,
            'title': '因子域合法死亡证明（分类器族状态条件化）',
            'scope': '域限定：full144 池 PC-4 RS_momentum|fwd20 的「分类器族状态条件化部署」'
                     '（b 门域 4 态已由 W2 判死 + 本单 b 族之外 10 族 35 态收官）；'
                     '不外溢到其他因子、其他池、其他 horizon、无条件裸上（裸上禁令独立维持）',
            'evidence': {'families_total': len(by_family), 'variants_total': len(variants),
                         'tested': n_testable, 'not_testable_registered': len(variants) - n_testable,
                         'survivors': 0, 'fdr': {'method': 'BH', 'q': 0.10,
                                                 'm_testable': n_testable},
                         'per_family': by_family},
            'revival_conditions': [
                'R1 新数据段：realC 之后的留出段若 RS_momentum 无条件或某态条件下 '
                'FDR(q=0.10) 幸存且 realC 型翻转不再现，证明可重启（触发器=PB-9 型 p 值轨迹常设）',
                'R2 新分类器族：本单 10 族之外的合法新族（预注册+跨族 BH）若出现幸存态',
                'R3 数据解锁：W1 资金费数据到位后，资金费维度分类族（PB-2 卡 171 变体）'
                '并入扫描，若幸存则证明重启',
                'R4 机制变更：PW2-10 退出成本管线建成后，若「翻转后 N 日退出成本」'
                '实测表明翻转可实时分类且费后可部署'],
            'not_testable_note': '样本内不可测态（空象限/低样本）按 PF-3/PF-9 附数登记为'
                                 '外推区，非「测过且死」，属证明的边界条件而非漏洞'}
    else:
        final_verdict = {
            'death_certificate_issued': False,
            'reason': f'幸存者 {len(survivors)} 个（R9 双向纪律：既禁无证据判死，也禁'
                      '对过线幸存者强行判死），死亡证明不颁发',
            'survivor_disposition': {
                k: {'status': 'SURVIVOR_CANDIDATE_FOR_DEEP_VERIFY（登记深验候选，不部署，'
                              '裸上禁令不因此松动）',
                    'caveat': 'realC 腿证据弱（IC t=0.83 不显著、费后价差仅 0.77pp），'
                              '「不翻转」按冻结判线字面达标（≥0），部署级证据不足',
                    'segment_profile': surv_profile[k]} for k in survivors},
            'domain_note': '本单收官后因子域状态：b 门域 4 态（W2 判死）+ b 族之外 '
                           '10 族 35 态（本单：26 判死附数 + 7 不可判定附数 + 1 幸存 + '
                           '1 样本不足登记）；无幸存者才可结案的全域死亡证明暂停颁发'}
    out = {'stage': 'fdr_final_scan', 'ts': time.strftime('%F %T'),
           'od': 'PF-1..PF-10（见头注，冻结）：b 族之外 10 族 35 态全扫 + 跨族 BH q=0.10',
           'factor': 'PC-4 RS_momentum|fwd20（full144 异池互指，W2 谱系逐字）',
           'lineage_check_vs_w2': lineage_chk,
           'variants': variants,
           'per_family_counts': by_family,
           'survivors': survivors,
           'survivor_segment_profile': surv_profile,
           'fdr_final_verdict': final_verdict,
           'death_certificate': cert,
           'boundary_preregistered': {
               'g1xg2_cross': 'G1 语义×G2 方向交叉格 3×3=9 未跑（PG2-3 登记，单独过审再立单）',
               'pw2_10_exit_cost': '翻转后 N 日退出成本：需成对管线排期（W2 PW2-10 承继）',
               'empty_quadrants': '空象限/低样本态为样本内外推区（PF-3 附数登记）'},
           'wall_secs': round(time.time() - t0, 1)}
    with open(os.path.join(OUT, 'fdr_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('fdr_result.json 完成；幸存者=', survivors, '；死亡证明=',
          '颁发' if cert else '不颁发', '；', out['wall_secs'], 's')
    return out


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which in ('gate', 'all'):
        stage_gate()
    if which in ('fdr', 'all'):
        stage_fdr()
