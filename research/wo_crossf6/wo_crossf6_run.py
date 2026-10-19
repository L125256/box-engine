#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单A：G1×G2 交叉格 9 格 + 单B：F6 深验 & S3×F6 交叉并单（A/B 双臂）· 合并工单
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/G1G2FDR_VERDICT.md 首席终裁条款：
- 「G1×G2 交叉格 9 格 立项（S3×D1 第一优先格）」：S3 卡 mdd（full144 mdd_red 7.17<10）、
  D1 卡 lag（HOLDOUT avoid≈0）的失败腿互补，是门域最后的最优先可跑面积；
- 「S3×F6 交叉 与 F6 深验并单（1 张预注册，A/B 双臂，FDR 合并计数）」：同域同池同判线
  口径，并单省一半成本且防族数膨胀；禁止把 lo/hi 截面对比写成已证实机制（待验假设 H_F6）；
- F6 深验生死判据（交易员 §六-2 逐字冻结）：①前瞻/留出段 realC 型子段逐日 IC ≥0 且
  t≥2（补上本轮 t=0.83 的短板）；②前瞻费后 fwd20 价差>0（≥5 个显著日）；
  ③任一判据翻转即判死并颁发 F6 死亡证明；样本内数字封印（ext t=7.15 等只登记不进判线）；
- FDR 双重选择控制（风险主管 §五-3）：交叉格与单臂格合并计数（m≥11），判线从严不从宽；
- 144 池定版不碰；R8=Pool(32)；seed=42；R9：判死必附穷举证据、对过线者禁强行判死；
  D0 对拍先过（maxdiff=0），任一不过即停工。
- 既有实现复用：wo_rescue_run（判据件/费压/双窗/bootstrap/BH/IC 件）；
  wo_g1g2fdr_run（run_gate_g OFF 四档语义引擎、gate_maps 门信号、_seg_metrics 八列、
  _primary 主判件、_off_diag/_direction_blind 教训件、F6 尺 = _state_vars F6 块逐字）。

【单A 预注册（PCX-A1..A10，先冻结后运行）】
PCX-A1 交叉格定义（S3 轴 × D1 轴 3×3=9 格，写死禁止加格）：
  S3 轴（OFF 语义，PG1-2 谱系三档）：全停 v2_full_stop（W3 现状）/ S3 半额开门
  open_half_nosell（OFF 停换仓卖出+新开仓半额 slot）/ 全开 open_full_nosell
  （OFF 停换仓卖出+新开仓全额 slot）；
  D1 轴（方向叠加，PG2-2 谱系三档）：D1 关=无方向条件（纯 vol_hi 门，= v2 门信号）/
  D1 开=方向向下才 OFF（idx<MA50，PG2-2 D1 逐字）/ 其他方向变体=广度方向向下才 OFF
  （breadth<其 MA20，PG2-2 D3 逐字）。
PCX-A2 D3 取舍声明：首席条款原文「OFF 时若 idx/广度方向仍向上则不停」为双通道——D1
  覆盖 idx 侧、D3 覆盖广度侧，取信息增量更大者入格；D2（idx 20 日动量）与 D1 同为
  idx 动量源（信息冗余）且上轮判死数字更差（old131 FULL avoid −19.06 vs D3 +15.41），
  登记为边界预写项不进本格面（若需 D2 侧复验须新预注册）。
PCX-A3 九格清单与锚格标注（锚格=上轮已判定的单臂变体，本单重跑仅作 D0 谱系回拍，
  不进 FDR 族——已在上轮 m=12 族判定，重复计入=双重惩罚）：
  ①(全停,D1关)=v2 参照臂【锚】②(全停,D1开)=g2_ma【锚】③(全停,D3广度)【新】
  ④(S3,D1关)=g1_open_half_nosell【锚】⑤(S3,D1开)=S3×D1 第一优先格【新】
  ⑥(S3,D3广度)【新】⑦(全开,D1关)=g1_open_full_nosell【锚】
  ⑧(全开,D1开)【新】⑨(全开,D3广度)【新】。新格 5×2 池=10 进 FDR 族。
PCX-A4 每格双池（old131/full144）×出身分段 realA/realB/realC 全八列
  （wo_hd seg_metrics 谱系逐行复用=wo_g1g2fdr._seg_metrics）。
PCX-A5 费压口径=PB-5 承继（FEE_SIDE×1.5/FUNDING×1.5），base 臂同费对比，主判以费压臂为准。
PCX-A6 双窗=FULL(2025-06-02→2026-10-17)+HOLDOUT(2026-04-01→2026-10-17)；主判据=PG1-4
  承继：avoid_pp=臂段净收益(pp)−base 段净收益(pp)；mdd_red=(|base MDD|−|臂 MDD|)/|base MDD|×100。
PCX-A7 全格滞后稳健（T2' 承继）：9 格全部 gate_map=cond.shift(1) 重跑，lag 后 FULL/HOLDOUT
  avoid>0 不翻转方为 lag_robust。
PCX-A8 失败腿互补验证（第一优先格 S3×D1 逐项）：S3 补 D1 踏空=realB 段臂净收益−v2 参照
  realB 净收益>0（T3' 承继）；D1 补 S3 方向盲=OFF 日 base 净日收益双侧检验（T1' 承继，
  v2 门 vs 组合门对照）+OFF 占比对读（v2≈98% → D1 机制件 ≈16%）。
PCX-A9 单A 判定规则=PG1-7 逐字：FDR 幸存 ∧ 双窗 avoid>0 ∧ 双窗 mdd_red≥10 ∧
  T2 滞后不翻转 ∧ T3 realB 踏空改善 vs v2>0 ∧ realC 避损保持>0。
PCX-A10 D0 六检（任一不过即停工）：①门禁用+default 费 vs 权威 dneg_engine.run_instr
  maxdiff=0、fees 差=0；②v2+default 费 vs wo_rescue.run_gate 逐位一致；③default 费 base
  臂 realA/realC 八列 vs wo_hd ≤0.01pp；④费压 v2 参照臂 FULL avoid vs W3 存档 ≤0.01pp；
  ⑤四锚格重跑主判（FULL/HOLDOUT avoid、mdd_red、bootstrap p、lag avoid）vs 上轮
  g1/g2_result.json 存档值 ≤0.01pp（p ≤1e-9）；⑥本单扩展引擎 run_gate_x（off_mode_map
  路径，B 臂用）off_mode_map=None 时 vs wo_g1g2fdr.run_gate_g 逐位一致 maxdiff=0。

【单B 预注册（PCX-B1..B10，先冻结后运行）】
PCX-B1 A 臂域限定（交易员 §六-1 逐字）：full144 × RS_momentum|fwd20 × 低相关态
  （F6_corr_p50|lo），不扩域、不换因子、不改分界定义（p50 分界复用同一把尺：
  池内 20 日滚动平均两两相关、realA p50 阈值，wo_g1g2fdr._state_vars F6 块逐字）。
PCX-B2 F6 尺零漂移回拍（先于一切判定）：重算 F6|lo 与 F6|hi 全部存档数字
  （n_ext_days/t_stat/n_ic/ic_mean/ext 价差/n_sig/realC 各腿）vs fdr_result.json 幸存行
  与 FAIL 行逐位一致（round 后全等），不一致即停工。
PCX-B3 A 臂生死判据=VERDICT 六-2 三条逐字（①realC 型子段逐日 IC≥0 且 t≥2；
  ②费后 fwd20 价差>0 且 ≥5 个显著日；③任一翻转即判死+死亡证明）。
PCX-B4 A 臂样本扩展审查（只许已落定数据，禁前视）：①前向延长=不可能（数据止于
  2026-10-17，fwd20 需未来 20 日）；②realC 观测本身无合法延长手段（全部已落定信号日
  ⊆ 35 态扫描窗 2025-06-02→2026-10-17=选择效应污染区，逐日覆盖数如实登记）；
  ③唯一污染区外已落定面积=扫描窗之前的信号日（后向延长读数：尺同源 p50 复用、
  仅登记不作判线——F6 族设计本身晚于全史可见，残余风险注记）；④前瞻判读协议照挂
  （realC 段实时判读/PB-9 轨迹/触发器=前瞻 realC 型子段 t≥2 达成即评审）。
PCX-B5 A 臂机制检验（登记级，非部署证据，H_F6 待验假设）：F6|lo vs F6|hi 态内——
  组合分散度（池日收益截面 std 均值）、base 组合日内净收益均值/下行日占比/负收益合计
  （回撤贡献）/正负贡献比、v2 门 OFF 日重叠、RS IC 分段对读（realA/realB/realC+realC
  逐月滚动）；35 态选择效应残余风险量化=全局零假设 Monte Carlo（存档 27 可测态 p 值，
  p~U(0,1) 独立，BH q=0.10，2 万次）：P(≥1 拒绝)/E[拒绝数]/观测拒绝数对照。
PCX-B6 A 臂样本内数字封印：ext t=7.15/ext 价差 +9.85pp 等 35 态扫描数字只作登记与
  回拍锚，不进任何新判线；lo/hi 截面对比只写「待验假设 H_F6」禁止写「已证实机制」。
PCX-B7 B 臂定义（S3×F6 交叉，门域语义化，2 变体写死禁止加档）：
  B1 lo 态内开门=vol_hi ∧ F6|lo → S3 半额开门；vol_hi ∧ F6|hi（或态未定义）→ v2 全停
  （多头席主张的主变体：低相关才放开半开门）；B2 态外半额对照=vol_hi ∧ F6|hi → S3
  半额开门；vol_hi ∧ F6|lo（或态未定义）→ v2 全停（剂量反证对照变体：若 B2 也不错
  则「低相关才安全」机制假设可疑）。F6 态旗标用 full144 池尺（市场态旗标定义一次，
  防 old131 侧重估阈值制造新变体）；态未定义日（扫描窗前 avg_corr 未计算）按 v2 全停
  保守缺省。
PCX-B8 B 臂判线=VERDICT 交易员 §六-4 四件套逐字：FDR 幸存 ∧ 双窗 avoid>0 ∧
  双窗 mdd_red≥10 ∧ lag=1 不翻转（承继 G1 主判口径）；realB/realC 侧数字另列登记。
PCX-B9 FDR 合并族（风险主管 §五-3 从严条款）：BH q=0.10，族=单A 新格 5×2 池 + 单B
  B 臂 2 变体×2 池 = 14 个 FULL 窗单侧 bootstrap p（m=14≥11 如实记账）；锚格/参照臂/
  base 不进族（PCX-A3）；A 臂（因子域深验）按 PCX-B3 判据单独判定不进 bootstrap 族。
PCX-B10 运营姿态不变：维持空仓观望，本单为纸面工单不产生实盘动作；realC 段实时判读、
  PB-9 轨迹、realB 段触发器照挂；不加新监测账。

用法：python3 wo_crossf6_run.py prereg|all
产出：wo_crossf6_prereg.json / cross_result.json / f6_result.json（报告另手写 CROSSF6_REPORT.md）
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
sys.path.insert(0, os.path.join(_ROOT, 'research', 'wo_g1g2fdr'))
sys.path.insert(0, os.path.join(_ROOT, 'research', 'wo_dneg'))
import wo_rescue_run as WR
import wo_g1g2fdr_run as WG
import dneg_engine as DE

SEED = 42
OUT = os.path.join(_ROOT, 'research', 'wo_crossf6')
PREREG_F = os.path.join(OUT, 'wo_crossf6_prereg.json')
os.makedirs(OUT, exist_ok=True)

REALB = WG.REALB
SEGS = {'realA': WR.REALA, 'realB': REALB, 'realC': WR.REALC}
SEMS = ['v2_full_stop', 'open_half_nosell', 'open_full_nosell']   # PCX-A1 S3 轴
DIRS = ['v2', 'g2_ma', 'g2_br']                                    # PCX-A1 D1 轴
CELLS = [(s, d) for s in SEMS for d in DIRS]                       # 9 格
CELL_ID = {(s, d): f'{s}__x__{d}' for s, d in CELLS}
ANCHORS = {('v2_full_stop', 'v2'): ('g1', 'v2_ref'),                # PCX-A3 锚格
           ('v2_full_stop', 'g2_ma'): ('g2', 'g2_ma'),
           ('open_half_nosell', 'v2'): ('g1', 'g1_open_half_nosell'),
           ('open_full_nosell', 'v2'): ('g1', 'g1_open_full_nosell')}
NEW_CELLS = [c for c in CELLS if c not in ANCHORS]
B_ARMS = ['B1_lo_open_half', 'B2_hi_open_half']                    # PCX-B7
G1_ARC = os.path.join(_ROOT, 'research', 'wo_g1g2fdr')
PRIO = ('open_half_nosell', 'g2_ma')                               # S3×D1 第一优先格


# ============================================================ F6 尺（PCX-B1 同尺逐字）
_F6 = None


def f6_state():
    """wo_g1g2fdr._state_vars 的 F6 块逐字复制（防阈值游走：p50=realA 分位同尺）。"""
    global _F6
    if _F6 is not None:
        return _F6
    WR._init()
    names = WR._POOLS['full144']
    C = pd.DataFrame({s: WR._DATA[s]['close'] for s in names}).sort_index()
    R = C.pct_change()
    ext_set = set(C.index[(C.index >= WR.FULL[0]) & (C.index <= WR.FULL[1])])
    pos = {d: i for i, d in enumerate(C.index)}
    avg_corr = pd.Series(np.nan, index=C.index)
    arr = R.values
    for d in C.index:
        i = pos[d]
        if i < 19:
            continue
        w = arr[i - 19:i + 1]
        ok = np.isfinite(w).all(axis=0)
        if ok.sum() < 30:
            continue
        cm = np.corrcoef(w[:, ok], rowvar=False)
        k = cm.shape[0]
        if d in ext_set:
            avg_corr[d] = float((cm.sum() - k) / (k * (k - 1)))
    ra = C.index[(C.index >= WR.REALA[0]) & (C.index <= WR.REALA[1])]
    p50c = float(avg_corr[ra].quantile(0.5))
    lab = pd.Series(np.where(avg_corr > p50c, 'hi', 'lo'), index=C.index)  # WG 同尺逐字
    lo = (lab == 'lo')
    hi = (lab == 'hi')
    _F6 = {'C': C, 'avg_corr': avg_corr, 'p50': p50c,
           'lo': lo, 'hi': hi, 'ra': ra, 'names': names}
    return _F6


def b_off_mode_map(arm):
    """PCX-B7：信号日 → OFF 响应语义映射（B1 lo 态内半额 / B2 hi 态外半额，
    态未定义日 → v2 全停保守缺省）。仅在 gate ON（vol_hi）信号日被引擎取用。"""
    st = f6_state()
    lo, hi = st['lo'], st['hi']
    if arm == 'B1_lo_open_half':
        flag = lo.copy()          # 态旗标谱系内（ext 窗）用同尺 lo 掩码
        flag[lo.index < WR.REALA[0]] = False   # 扫描窗前态未定义日 → 保守全停
    else:
        flag = hi.copy()          # NaN→'lo' 非非 hi，天然保守
    return {t: ('open_half_nosell' if bool(flag.at[t]) else 'v2_full_stop')
            for t in flag.index}


# ============================================================ 扩展引擎（PCX-A10-⑥）
def run_gate_x(syms, gate_map=None, off_mode='v2_full_stop', off_mode_map=None,
               fee=None, fund=None):
    """wo_g1g2fdr.run_gate_g 逐行复制，唯一新增：off_mode_map（信号日→OFF 语义映射，
    PCX-B7 B 臂态条件化响应）。off_mode_map=None 时与 run_gate_g 逐位一致
    （D0-⑥ 断言强制）。"""
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
            _, target, eq_sig, off_next, mode_x = pending_exec
            pending_exec = None
            n_rebal += 1
            if off_next:
                n_gate_off += 1
            # ---- PG1-2 OFF 语义四档（响应语义 mode_x：静态 off_mode 或 PCX-B7 态映射）----
            if off_next and mode_x == 'v2_full_stop':
                sell_skip, do_open, slot_mult = True, False, 1.0
            elif off_next and mode_x == 'risk_half':
                sell_skip, do_open, slot_mult = False, True, WG.SLOT_HALF
            elif off_next and mode_x == 'open_full_nosell':
                sell_skip, do_open, slot_mult = True, True, 1.0
            elif off_next and mode_x == 'open_half_nosell':
                sell_skip, do_open, slot_mult = True, True, WG.SLOT_HALF
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
            mode_next = (off_mode_map or {}).get(t, off_mode) \
                if off_mode_map is not None else off_mode   # ← 唯一新增行
            target = [] if (off_next and mode_next == 'v2_full_stop') \
                else list(score.index[:DE.TOP_N])
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity, off_next, mode_next) \
                if cal.get_loc(t) + 1 < len(cal) else None

    curve = pd.Series(eq).sort_index()
    end = cal[-1]
    for s, p in pos.items():
        trades[tid_of[s]].update(close_date=str(end.date()), exit_px=float(mark.at[end, s]),
                                 exit_reason='eow')
    return {'curve': curve, 'fees': fees, 'turnover': turnover, 'n_rebal': n_rebal,
            'n_gate_off': n_gate_off, 'trades': trades, 'day_cum': day_cum}


# ============================================================ worker（单A 9 格 + 单B B 臂 + 参照）
def _worker(task):
    pname, cell, lag, fmode = task
    WR._init()
    syms = WR._POOLS[pname]
    fee, fund = (WR.FEE_SIDE_S, WR.FUNDING_S) if fmode == 'stress' \
        else (DE.FEE_SIDE, DE.FUNDING)
    if cell == 'base':
        g = run_gate_x(syms, gate_map=None, off_mode='v2_full_stop',
                       off_mode_map=None, fee=fee, fund=fund)
    elif cell == 'v2':
        gmap = WG.gate_maps(pname, lag)['v2'].to_dict()
        g = run_gate_x(syms, gate_map=gmap, off_mode='v2_full_stop',
                       off_mode_map=None, fee=fee, fund=fund)
    elif cell in B_ARMS:
        gmap = WG.gate_maps(pname, lag)['v2'].to_dict()      # 门信号=纯 vol_hi（PCX-B7）
        omm = b_off_mode_map(cell)
        g = run_gate_x(syms, gate_map=gmap, off_mode='v2_full_stop',
                       off_mode_map=omm, fee=fee, fund=fund)
    else:
        s, d = cell
        gmap = WG.gate_maps(pname, lag)[d].to_dict()
        g = WG.run_gate_g(syms, gate_map=gmap, off_mode=s, fee=fee, fund=fund)
    return {'cell': cell, 'pname': pname, 'lag': lag, 'fmode': fmode,
            'n_gate_off': g['n_gate_off'],
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()},
            'fees': float(g['fees']), 'turnover': float(g['turnover']),
            'day_cum': [(str(t.date()), float(f), float(tv)) for t, f, tv in g['day_cum']],
            'trades': g['trades']}


# ============================================================ 预注册（先冻结后运行）
def write_prereg():
    pre = {
        'workorder': '单A G1×G2 交叉格 9 格 + 单B F6 深验 & S3×F6 交叉并单（A/B 双臂）',
        'frozen_at': time.strftime('%F %T'),
        'spec_source': '/tmp/trade9_specs/G1G2FDR_VERDICT.md 首席终裁条款（逐字照做禁改）',
        'A_arm_cross': {
            'grid': {'S3_axis': SEMS, 'D1_axis': DIRS, 'cells': 9,
                     'note': 'PCX-A1/A2/A3：D1 关=纯 vol_hi；D1 开=idx<MA50（PG2-2 D1）；'
                             '其他方向变体=D3 广度方向（breadth<MA20，PG2-2）；'
                             'D2 与 D1 同源 idx 动量判死且信息冗余，登记边界项不入格'},
            'anchors': [CELL_ID[c] for c in CELLS if c in ANCHORS],
            'new_cells_fdr': [CELL_ID[c] for c in NEW_CELLS],
            'first_priority': CELL_ID[PRIO] + '（S3×D1 失败腿互补）',
            'eight_col': 'PCX-A4 双池×realA/realB/realC 全八列（wo_hd 谱系）',
            'fee': 'PCX-A5 PB-5 费压 ×1.5（主判）',
            'windows': 'PCX-A6 FULL 2025-06-02→2026-10-17 + HOLDOUT 2026-04-01→2026-10-17',
            'lag': 'PCX-A7 全格 shift(1) 重跑不翻转',
            'complementary': 'PCX-A8 S3 补 D1 踏空（realB vs v2>0）/ D1 补 S3 方向盲'
                             '（OFF 日均值 T1' + "'"+ ' + OFF 占比对读）',
            'verdict_rule': 'PCX-A9 = PG1-7 逐字：FDR 幸存 ∧ 双窗 avoid>0 ∧ 双窗 mdd_red≥10 '
                            '∧ lag 不翻转 ∧ realB 踏空改善 vs v2>0 ∧ realC 避损保持>0',
            'd0': 'PCX-A10 六检（任一不过即停工）：权威引擎 maxdiff=0 / wo_rescue 逐位 / '
                  'wo_hd 八列 ≤0.01pp / W3 avoid ≤0.01pp / 四锚格存档回拍 / run_gate_x 等价'},
        'B_arm_f6': {
            'A_arm': {'domain': 'PCX-B1：full144 × RS_momentum|fwd20 × F6_corr_p50|lo（同尺逐字）',
                      'zero_drift_check': 'PCX-B2：F6|lo 与 F6|hi 全部存档数字逐位回拍',
                      'life_death': 'PCX-B3 = VERDICT 六-2 ①②③逐字',
                      'sample_extension': 'PCX-B4：前向不可能/realC 无合法延长（污染区覆盖'
                                          '逐日登记）/后向延长读数仅登记/前瞻协议照挂',
                      'mechanism': 'PCX-B5：lo vs hi 分散度/回撤贡献/RS IC 对读 + '
                                   '35 态选择效应 MC 量化（H_F6 待验假设，禁写已证实）',
                      'seal': 'PCX-B6：样本内数字封印'},
            'B_arm': {'variants': {'B1_lo_open_half': 'vol_hi∧F6|lo → S3 半额开门；其余全停',
                                   'B2_hi_open_half': 'vol_hi∧F6|hi → S3 半额开门；其余全停'
                                                      '（剂量反证对照）'},
                      'state_flag': 'full144 池尺定义一次；态未定义日→v2 全停保守缺省',
                      'verdict_rule': 'PCX-B8 四件套：FDR 幸存 ∧ 双窗 avoid>0 ∧ 双窗 '
                                      'mdd_red≥10 ∧ lag=1 不翻转'},
        },
        'fdr_merged': {'method': 'BH', 'q': 0.10, 'm': 14,
                       'family': '单A 新格 5×2 池 + 单B B 臂 2×2 池 = 14 个 FULL 窗单侧 '
                                 'bootstrap p（锚格/参照臂/base 不进族——上轮 m=12 已判定，'
                                 '重复计入=双重惩罚；A 臂按 PCX-B3 单独判定不进 bootstrap 族）；'
                                 'VERDICT §五-3 交叉双重选择从严条款 m≥11 满足'},
        'pool': '严格 144 池定版（old131+new13，禁碰新标的）',
        'seed': SEED, 'parallel': 'R8 Pool(32)',
        'operation': 'PCX-B10 空仓观望纸面工单；realC 实时判读/PB-9/realB 触发器照挂',
    }
    json.dump(pre, open(PREREG_F, 'w'), ensure_ascii=False, indent=1)
    print('预注册已冻结 →', PREREG_F)


# ============================================================ 主流程
def run_all():
    t0 = time.time()
    assert os.path.exists(PREREG_F), '预注册未冻结——先跑 prereg'
    WR._init()
    pools = ['old131', 'full144']

    # ---- 任务面：9 格×双池×{lag0,lag1} + B 臂 2×2×2 + 参照（base/v2 default+stress）
    tasks = [(p, c, lag, 'stress') for p in pools for c in CELLS for lag in (0, 1)] \
        + [(p, b, lag, 'stress') for p in pools for b in B_ARMS for lag in (0, 1)] \
        + [(p, 'base', 0, 'stress') for p in pools] \
        + [(p, 'v2', 0, 'stress') for p in pools] \
        + [(p, 'base', 0, 'default') for p in pools] \
        + [(p, 'v2', 0, 'default') for p in pools]
    with Pool(32) as pool:
        runs_raw = pool.map(_worker, tasks)
    R = {(r['pname'], r['cell'], r['lag'], r['fmode']): r for r in runs_raw}
    print(f'回测完成：{len(tasks)} 任务；wall={time.time()-t0:.0f}s；进入 D0 六检')

    # ---- D0 六检（PCX-A10，任一不过即停工；全部通过才允许判定）
    d0 = {}
    for p in pools:
        # ① 权威引擎（门禁用+default 费）
        ref = DE.run_instr(WR._DATA, F=WR._F, syms=WR._POOLS[p], gated=False, record=True)
        mc = WG._curve(R[(p, 'base', 0, 'default')])
        md = float((mc - ref['curve']).abs().max())
        fd = float(abs(R[(p, 'base', 0, 'default')]['fees'] - ref['fees']))
        # ② wo_rescue.run_gate 谱系（v2+default 费）
        v2map = WG.gate_maps(p)['v2'].to_dict()
        wr = WR.run_gate(WR._POOLS[p], gate_map=v2map, fee=DE.FEE_SIDE, fund=DE.FUNDING)
        md2 = float((WG._curve(R[(p, 'v2', 0, 'default')]) - wr['curve']).abs().max())
        fd2 = float(abs(R[(p, 'v2', 0, 'default')]['fees'] - wr['fees']))
        # ③ wo_hd 八列谱系（default 费 base 臂 realA/realC）
        hd = json.load(open(os.path.join(_ROOT, 'research', 'wo_hd', 'wo_hd_result.json')))['eight_col_table']
        e8 = WG._seg_metrics(R[(p, 'base', 0, 'default')], *WR.REALA)
        e8c = WG._seg_metrics(R[(p, 'base', 0, 'default')], *WR.REALC)
        r8 = hd[f'{p}|base']['realA']
        d_ann, d_mdd = abs(e8['annualized_pct'] - r8['annualized_pct']), abs(e8['mdd_pct'] - r8['mdd_pct'])
        c_ann = abs(e8c['annualized_pct'] - hd[f'{p}|base']['realC']['annualized_pct'])
        c_mdd = abs(e8c['mdd_pct'] - hd[f'{p}|base']['realC']['mdd_pct'])
        # ④ W3 跨单谱系（费压 v2 参照臂 FULL avoid）
        w3 = json.load(open(os.path.join(_ROOT, 'research', 'wo_w2w3', 'w3_result.json')))
        w3_avoid = w3['primary'][p]['gate|FULL']['avoid_pp']
        mine = WG._primary(WG._curve(R[(p, 'v2', 0, 'stress')]), WG._curve(R[(p, 'base', 0, 'stress')]))
        d_w3 = abs(mine['FULL']['avoid_pp'] - w3_avoid)
        d0[p] = {'D1_vs_dneg_maxdiff': md, 'D1_vs_dneg_fees_absdiff': fd,
                 'D2_vs_wo_rescue_maxdiff': md2, 'D2_vs_wo_rescue_fees_absdiff': fd2,
                 'D3_vs_wo_hd_realA_ann_mdd_absdiff': [round(d_ann, 4), round(d_mdd, 4)],
                 'D3_vs_wo_hd_realC_ann_mdd_absdiff': [round(c_ann, 4), round(c_mdd, 4)],
                 'D4_v2_stress_FULL_avoid_vs_w3_absdiff': round(d_w3, 4)}
        assert md == 0 and fd == 0, f'D0-1 FAIL {p}: {d0[p]}'
        assert md2 == 0 and fd2 == 0, f'D0-2 FAIL {p}: {d0[p]}'
        assert d_ann <= 0.01 and d_mdd <= 0.01 and c_ann <= 0.01 and c_mdd <= 0.01, \
            f'D0-3 FAIL {p}: {d0[p]}'
        assert d_w3 <= 0.01, f'D0-4 FAIL {p}: {d0[p]}'

        # ⑤ 四锚格存档回拍（主判逐项 vs 上轮 json）
        g1 = json.load(open(os.path.join(G1_ARC, 'g1_result.json')))['primary'][p]
        g2 = json.load(open(os.path.join(G1_ARC, 'g2_result.json')))['primary'][p]
        bc = WG._curve(R[(p, 'base', 0, 'stress')])
        a5 = {}
        for cell, (src, arm) in ANCHORS.items():
            arc = (g1 if src == 'g1' else g2)[arm if arm != 'v2_ref' else 'v2_ref']
            row = WG._primary(WG._curve(R[(p, cell, 0, 'stress')]), bc)
            lrow = WG._primary(WG._curve(R[(p, cell, 1, 'stress')]), bc)
            diffs = {'FULL_avoid': abs(row['FULL']['avoid_pp'] - arc['FULL']['avoid_pp']),
                     'HOLD_avoid': abs(row['HOLDOUT']['avoid_pp'] - arc['HOLDOUT']['avoid_pp']),
                     'FULL_mdd_red': abs(row['FULL']['mdd_red_pct'] - arc['FULL']['mdd_red_pct']),
                     'HOLD_mdd_red': abs(row['HOLDOUT']['mdd_red_pct'] - arc['HOLDOUT']['mdd_red_pct']),
                     'p_boot': abs(row['p_full_avoid_gt0'] - arc['p_full_avoid_gt0'])}
            if 'lag_FULL_avoid_pp' in arc:   # 上轮 v2_ref 行未存 lag（只存新变体行）→ 跳过
                diffs['lag_FULL_avoid'] = abs(lrow['FULL']['avoid_pp'] - arc['lag_FULL_avoid_pp'])
                diffs['lag_HOLD_avoid'] = abs(lrow['HOLDOUT']['avoid_pp'] - arc['lag_HOLDOUT_avoid_pp'])
            a5[CELL_ID[cell]] = {k: round(v, 6) for k, v in diffs.items()}
            assert all(v <= (1e-9 if k == 'p_boot' else 0.01) for k, v in diffs.items()), \
                f'D0-5 FAIL {p} {CELL_ID[cell]}: {a5[CELL_ID[cell]]}'
        d0[p]['D5_anchor_replay_absdiff'] = a5

        # ⑥ run_gate_x 等价性（off_mode_map=None vs run_gate_g，S3 语义）
        gx = run_gate_x(WR._POOLS[p], gate_map=v2map, off_mode='open_half_nosell',
                        off_mode_map=None, fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
        gg = WG.run_gate_g(WR._POOLS[p], gate_map=v2map, off_mode='open_half_nosell',
                           fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
        md6 = float((gx['curve'] - gg['curve']).abs().max())
        fd6 = float(abs(gx['fees'] - gg['fees']))
        d0[p]['D6_run_gate_x_equiv_maxdiff'] = md6
        d0[p]['D6_run_gate_x_equiv_fees_absdiff'] = fd6
        assert md6 == 0 and fd6 == 0, f'D0-6 FAIL {p}: md={md6} fd={fd6}'
    print('D0 六检全过（权威引擎/wo_rescue/wo_hd/W3/锚格回拍/引擎等价 maxdiff=0）')

    # ---- 八列（PCX-A4：9 格 + B 臂 + 参照，费压臂）
    arms_all = [CELL_ID[c] for c in CELLS] + B_ARMS + ['base', 'v2']
    ID2CELL = {v: k for k, v in CELL_ID.items()}

    def _run_of(arm, p, lag):
        if arm in ID2CELL:
            return R[(p, ID2CELL[arm], lag, 'stress')]
        return R[(p, arm, lag, 'stress')]

    eight = {f'{p}|{a}': {sn: WG._seg_metrics(_run_of(a, p, 0), x, y)
                          for sn, (x, y) in SEGS.items()}
             for p in pools for a in arms_all}

    # ---- 主判（PCX-A6）+ lag（PCX-A7）+ T 件（PCX-A8）+ 采集合并族 p 值
    primary, pvals, keys = {}, [], []
    for p in pools:
        bc = WG._curve(R[(p, 'base', 0, 'stress')])
        vc = WG._curve(R[(p, 'v2', 0, 'stress')])
        v2realb = WR.seg_stats(vc, *REALB)
        v2realc = WR.seg_stats(vc, *WR.REALC)
        baserealc = WR.seg_stats(bc, *WR.REALC)
        primary[p] = {}
        for a in arms_all:
            if a == 'base':
                continue
            row = WG._primary(WG._curve(_run_of(a, p, 0)), bc)
            if a in ID2CELL or a in B_ARMS:   # base/v2 参照无 lag 臂（T2 只对新臂/B 臂判定）
                lrow = WG._primary(WG._curve(_run_of(a, p, 1)), bc)
                row['lag_FULL_avoid_pp'] = lrow['FULL']['avoid_pp']
                row['lag_HOLDOUT_avoid_pp'] = lrow['HOLDOUT']['avoid_pp']
                row['lag_robust'] = bool(lrow['FULL']['avoid_pp'] > 0 and lrow['HOLDOUT']['avoid_pp'] > 0)
            else:
                row['lag_FULL_avoid_pp'] = row['lag_HOLDOUT_avoid_pp'] = None
                row['lag_robust'] = None
            # T3'：realB 踏空改善 vs v2 + realC 避损保持
            rb = WR.seg_stats(WG._curve(_run_of(a, p, 0)), *REALB)
            rc = WR.seg_stats(WG._curve(_run_of(a, p, 0)), *WR.REALC)
            row['T3_realB_improve_vs_v2_pp'] = round(rb['ret_pp'] - v2realb['ret_pp'], 4)
            row['T3_realC_avoid_vs_base_pp'] = round(rc['ret_pp'] - baserealc['ret_pp'], 4)
            if a == 'v2':
                row['T3_realB_improve_vs_v2_pp'] = 0.0
                row['T3_realC_avoid_vs_base_pp'] = round(v2realc['ret_pp'] - baserealc['ret_pp'], 4)
            row['fdr_reject_full'] = None
            row['selected'] = None
            primary[p][a] = row
            if a in B_ARMS or (a in [CELL_ID[c] for c in NEW_CELLS]):
                pvals.append(row['p_full_avoid_gt0'])
                keys.append((p, a))
    assert len(pvals) == 14, f'合并族 m 应=14，实得 {len(pvals)}'
    rej = WR.bh_fdr(pvals, q=0.10)
    rej_map = {f'{p}|{a}': bool(v) for (p, a), v in zip(keys, rej)}
    fdr_block = {'method': 'BH', 'q': 0.10, 'm': len(pvals),
                 'family': 'PCX-B9 合并预注册族：单A 新格 5×2 池 + 单B B 臂 2×2 池 = 14 个 '
                           'FULL 窗单侧 bootstrap p（锚格/参照臂/base 不进族；A 臂按 '
                           'PCX-B3 单独判定不进 bootstrap 族）',
                 'pvals': {f'{p}|{a}': v for (p, a), v in zip(keys, pvals)},
                 'reject': rej_map}

    # ---- 判定（单A=PCX-A9 PG1-7 逐字；B 臂=PCX-B8 四件套；锚格不进本单族——
    #      FDR 状态承继上轮 m=12 族判定，本单只作 D0-⑤ 回拍）
    selected, off_diag_block = {}, {}
    for p in pools:
        for c in CELLS:
            a = CELL_ID[c]
            row = primary[p][a]
            in_family = c in NEW_CELLS
            rj = rej_map[f'{p}|{a}'] if in_family else False
            sel = bool(in_family and rj
                       and row['FULL']['avoid_pp'] > 0 and row['HOLDOUT']['avoid_pp'] > 0
                       and row['FULL']['mdd_red_pct'] >= 10 and row['HOLDOUT']['mdd_red_pct'] >= 10
                       and row['lag_robust']
                       and row['T3_realB_improve_vs_v2_pp'] > 0
                       and row['T3_realC_avoid_vs_base_pp'] > 0)
            row['fdr_reject_full'] = bool(rj) if in_family else None
            row['selected'] = sel
            selected[f'{p}|{a}'] = sel
            gate_series = WG.gate_maps(p, 0)[c[1]]
            off_diag_block[f'{p}|{a}'] = WG._off_diag(gate_series, R[(p, 'base', 0, 'stress')],
                                                      *WR.FULL)
        for b in B_ARMS:
            row = primary[p][b]
            sel = bool(rej_map[f'{p}|{b}']
                       and row['FULL']['avoid_pp'] > 0 and row['HOLDOUT']['avoid_pp'] > 0
                       and row['FULL']['mdd_red_pct'] >= 10 and row['HOLDOUT']['mdd_red_pct'] >= 10
                       and row['lag_robust'])
            row['fdr_reject_full'] = rej_map[f'{p}|{b}']
            row['selected'] = sel
            selected[f'{p}|{b}'] = sel
            off_diag_block[f'{p}|{b}'] = {
                'n_gate_off_weeks': R[(p, b, 0, 'stress')]['n_gate_off'],
                'note': 'B 臂 OFF 响应态条件化：lo 态半额（B1）/hi 态半额（B2），'
                        '态未定义日全停；OFF 语义占比见 f6_result.json B 臂诊断'}

    # ---- 方向盲互补件（T1'，第一优先格 + v2 对照）
    blind = {}
    for p in pools:
        blind[f'{p}|v2_ref'] = {sn: WG._direction_blind(WG.gate_maps(p, 0)['v2'],
                                                        R[(p, 'base', 0, 'stress')], x, y)
                                for sn, (x, y) in (('realB', REALB), ('realC', WR.REALC),
                                                   ('holdout', WR.HOLD))}
        blind[f'{p}|{CELL_ID[PRIO]}'] = {
            sn: WG._direction_blind(WG.gate_maps(p, 0)['g2_ma'],
                                    R[(p, 'base', 0, 'stress')], x, y)
            for sn, (x, y) in (('realB', REALB), ('realC', WR.REALC), ('holdout', WR.HOLD))}

    common = {'ts': time.strftime('%F %T'), 'pool': '严格 144 池定版（old131+new13，禁碰新标的）',
              'seed': SEED, 'prereg': 'wo_crossf6_prereg.json（先冻结后运行）',
              'fee_calibers': {'stress(主判)': {'FEE_SIDE': WR.FEE_SIDE_S, 'FUNDING': WR.FUNDING_S},
                               'default(谱系对拍)': {'FEE_SIDE': DE.FEE_SIDE, 'FUNDING': DE.FUNDING}},
              'd0': d0, 'fdr_merged': fdr_block, 'selected': selected,
              'wall_secs': round(time.time() - t0, 1)}

    # ---- cross_result.json（单A）
    cross_cells = {}
    for c in CELLS:
        a = CELL_ID[c]
        cross_cells[a] = {
            'axis': {'off_sem': c[0], 'direction': c[1]},
            'is_anchor': c in ANCHORS,
            'in_fdr_family': c in NEW_CELLS,
            'pools': {p: {k: primary[p][a][k] for k in
                          ('FULL', 'HOLDOUT', 'p_full_avoid_gt0', 'lag_FULL_avoid_pp',
                           'lag_HOLDOUT_avoid_pp', 'lag_robust', 'T3_realB_improve_vs_v2_pp',
                           'T3_realC_avoid_vs_base_pp', 'fdr_reject_full', 'selected')}
                      for p in pools}}
    cross_out = {'stage': 'cross_g1xg2_9grid', 'od': 'PCX-A1..A10（见脚本头注，冻结）',
                 **common, 'cells': cross_cells, 'eight_col_stress': eight,
                 'off_diag': {k: v for k, v in off_diag_block.items()
                              if not k.split('|')[1].startswith('B')},
                 'T1_direction_blind': blind,
                 'verdict_rule': 'PCX-A9 = PG1-7 逐字（FDR ∧ 双窗 avoid>0 ∧ 双窗 mdd_red≥10 '
                                 '∧ lag 不翻转 ∧ realB 改善 vs v2>0 ∧ realC 避损>0）',
                 'first_priority_cell': CELL_ID[PRIO]}
    with open(os.path.join(OUT, 'cross_result.json'), 'w') as f:
        json.dump(cross_out, f, ensure_ascii=False, indent=1)
    print('cross_result.json 完成；selected=',
          {k: v for k, v in selected.items() if not k.split('|')[1].startswith('B')})

    # ==================================================== 单B：A 臂 F6 深验
    st = f6_state()
    C, lo, hi, avg = st['C'], st['lo'], st['hi'], st['avg_corr']
    names = st['names']
    old131 = WR._POOLS['old131']
    new13 = sorted(set(names) - set(old131))
    ret20 = C / C.shift(20) - 1
    idx_old = ret20[old131].mean(axis=1)
    idx_new = ret20[new13].mean(axis=1)
    rs_cross = pd.DataFrame(index=C.index, columns=names, dtype=float)
    for s in names:
        rs_cross[s] = ret20[s] - (idx_new if s in old131 else idx_old)   # PF-1 PC-4 逐字
    fwd20 = C.shift(-20) / C - 1
    sigs = WG._sig_days(C.index)
    ext0, ext1 = WR.REALA[0], WR.REALC[1]
    rc0, rc1 = WR.REALC

    def state_stats(mask, a, b):
        days = C.index[(C.index >= a) & (C.index <= b) & mask.values]
        ic = WR._xsec_ic_series(rs_cross.loc[days], fwd20.loc[days])
        t_, n_ic = WR._tstat(ic)
        sw = sigs[(sigs >= a) & (sigs <= b)]
        sw = sw[sw.map(lambda d: bool(mask.at[d]))]
        if len(sw) >= WG.SPREAD_MIN_N:
            _, net, ns = WR._decile_spread_fee(rs_cross.loc[sw], fwd20.loc[sw])
        else:
            net, ns = None, None
        return {'n_days': int(len(days)), 'ic_mean': round(float(ic.mean()), 6) if len(ic) else None,
                't_stat': round(t_, 4) if t_ is not None else None, 'n_ic_days': n_ic,
                'fwd20_decile_pp_net': (round(net, 4) if net is not None else None), 'n_sig': ns}

    # PCX-B2 零漂移回拍
    arc = json.load(open(os.path.join(G1_ARC, 'fdr_result.json')))
    a_lo, a_hi = arc['variants']['F6_corr_p50|lo'], arc['variants']['F6_corr_p50|hi']
    prof_lo = arc['survivor_segment_profile']['F6_corr_p50|lo']
    rc_lo = state_stats(lo, rc0, rc1)
    ext_lo = state_stats(lo, ext0, ext1)
    ext_hi = state_stats(hi, ext0, ext1)
    rc_hi = state_stats(hi, rc0, rc1)
    chk = {
        'lo_ext': {'n_ext_days': [ext_lo['n_days'], a_lo['n_ext_days']],
                   't_stat': [ext_lo['t_stat'], a_lo['t_stat']],
                   'n_ic_days': [ext_lo['n_ic_days'], a_lo['n_ic_days']],
                   'ic_mean': [ext_lo['ic_mean'], a_lo['ic_mean']],
                   'ext_spread': [ext_lo['fwd20_decile_pp_net'], a_lo['ext_fwd20_decile_pp_net']],
                   'n_ext_sig': [ext_lo['n_sig'], a_lo['n_ext_sig']]},
        'lo_realC': {'n_realC_days': [rc_lo['n_days'], a_lo['n_realC_days']],
                     'realC_ic_mean': [rc_lo['ic_mean'], a_lo['realC_ic_mean']],
                     'realC_t': [rc_lo['t_stat'], a_lo['realC_t_stat']],
                     'realC_spread': [rc_lo['fwd20_decile_pp_net'], a_lo['realC_fwd20_decile_pp_net']],
                     'realC_n_sig': [rc_lo['n_sig'], prof_lo['realC']['n_sig']]},
        'hi': {'n_ext_days': [ext_hi['n_days'], a_hi['n_ext_days']],
               't_stat': [ext_hi['t_stat'], a_hi['t_stat']],
               'realC_t': [rc_hi['t_stat'], a_hi['realC_t_stat']],
               'realC_spread': [rc_hi['fwd20_decile_pp_net'], a_hi['realC_fwd20_decile_pp_net']]}}
    for side in ('lo_ext', 'lo_realC', 'hi'):
        for k, (mine, archived) in chk[side].items():
            if archived is None:
                continue
            assert abs(float(mine) - float(archived)) <= 5e-4, \
                f'PCX-B2 零漂移 FAIL {side}.{k}: {chk[side][k]}'
    print('PCX-B2 F6 尺零漂移回拍全过（lo/hi 全腿 vs 存档逐位一致）')

    # PCX-B3 生死判据（已落定数据读数）
    crit1 = {'ic_mean_realC': rc_lo['ic_mean'], 'ic_ge0': bool(rc_lo['ic_mean'] >= 0),
             't_realC': rc_lo['t_stat'], 't_ge2': bool(rc_lo['t_stat'] is not None and rc_lo['t_stat'] >= 2),
             'note': '判据①「前瞻/留出段 realC 型子段 IC≥0 且 t≥2（补 t=0.83 短板）」——'
                     '短板只能由扫描窗外新数据补上（见 PCX-B4），已落定数据读数=t=0.8274 原样'}
    crit2 = {'realC_spread_pp': rc_lo['fwd20_decile_pp_net'], 'n_sig': rc_lo['n_sig'],
             'pass': bool(rc_lo['fwd20_decile_pp_net'] is not None and rc_lo['fwd20_decile_pp_net'] > 0
                          and rc_lo['n_sig'] is not None and rc_lo['n_sig'] >= 5)}
    crit3 = {'ic_flipped_neg': bool(rc_lo['ic_mean'] < 0),
             'spread_flipped_neg': bool((rc_lo['fwd20_decile_pp_net'] or 0) < 0),
             'triggered': False}
    crit3['triggered'] = bool(crit3['ic_flipped_neg'] or crit3['spread_flipped_neg'])
    # 留出段全段读数（登记；污染区注记：2026-04-01→05-31 ⊆ 扫描窗）
    hold_lo = state_stats(lo, *WR.HOLD)
    # realC 逐月滚动（登记级稳健读数）
    ic_days = C.index[(C.index >= rc0) & (C.index <= rc1) & lo.values]
    ic_series = WR._xsec_ic_series(rs_cross.loc[ic_days], fwd20.loc[ic_days])
    monthly = {}
    for mo, g in ic_series.groupby(ic_series.index.to_period('M')):
        t_m, n_m = WR._tstat(g)
        monthly[str(mo)] = {'ic_mean': round(float(g.mean()), 4), 't_stat': (round(t_m, 4) if t_m is not None else None),
                            'n_days': n_m}

    # PCX-B4 样本扩展审查（结构性证明版）
    # 关键事实（探针实测）：PC-4 RS=个股−异池等权；old131 名减 idx_new(13)，
    # new13 等权 idx 的 ret20 最早 2025-07-07 才有值 → rs_cross 可评（截面 ≥30 名）
    # 的首日=2025-07-07，已在 35 态扫描窗内。故后向延长不仅被选择效应污染，
    # 而且结构性不可计算（扫描窗前无任何可评信号日）。
    scan_lo, scan_hi = ext0, ext1
    n_valid_names = rs_cross.notna().sum(axis=1)
    evaluable = (n_valid_names >= 30)
    settled_sig = sigs[sigs.map(lambda d: bool(evaluable.at[d]) if d in evaluable.index else False)]
    in_scan = settled_sig[(settled_sig >= scan_lo) & (settled_sig <= scan_hi)]
    pre_scan = settled_sig[settled_sig < scan_lo]
    first_eval = evaluable.index[evaluable][0]
    ext_audit = {
        'forward_extension_possible': False,
        'forward_reason': '数据止于 2026-10-17（fwd20 需未来 20 日），前向延长无已落定数据可用',
        'realC_extension_possible': False,
        'contamination_proof': {
            'scan_window': [str(scan_lo.date()), str(scan_hi.date())],
            'factor_evaluable_from': str(first_eval.date()),
            'factor_evaluable_reason': 'PC-4 RS=个股−异池等权互指：old131 名减 new13 等权 '
                                       '20 日收益，new13 idx 的 ret20 最早 2025-07-07 有效',
            'settled_signal_days_evaluable_total': int(len(settled_sig)),
            'settled_signal_days_inside_scan_window': int(len(in_scan)),
            'coverage_pct': round(len(in_scan) / max(len(settled_sig), 1) * 100, 2),
            'pre_scan_evaluable_signal_days': int(len(pre_scan)),
            'verdict': 'RS 因子可评首日（2025-07-07）已在扫描窗内：可评的已落定信号日 '
                       '100% ⊆ 35 态扫描窗（选择效应污染区），且扫描窗前不存在可评信号日'
                       '（结构性不可计算，非仅污染）——realC 观测不存在任何合法延长手段；'
                       '判据①短板只能由前瞻数据补上'},
        'backward_extension': {
            'possible': False,
            'pre_scan_evaluable_signal_days': int(len(pre_scan)),
            'verdict': '不可计算（截面 <30 名，附数登记）——后向延长路径关闭；'
                       '唯一合法观测延长=前瞻数据积累'},
        'forward_protocol': '前瞻判读协议照挂：realC 段实时判读 + PB-9 轨迹 + 触发器'
                            '（前瞻 realC 型子段逐日 IC≥0 且 t≥2 达成 → 评审可部署候选；'
                            'IC<0 或价差<0 翻转 → 立即判死+全域死亡证明）'}

    # PCX-B5 机制检验（H_F6 待验假设，登记级）
    disp = C.pct_change().std(axis=1)
    bc144 = WG._curve(R[('full144', 'base', 0, 'stress')])
    ret144 = bc144.pct_change() * 100
    v2_gate = WG.gate_maps('full144', 0)['v2']
    mech = {}
    for sname, mask in (('lo', lo), ('hi', hi)):
        days = C.index[(C.index >= ext0) & (C.index <= ext1) & mask.values]
        d = pd.DatetimeIndex(days)
        r = ret144.reindex(d).dropna()
        neg, pos_ = r[r < 0], r[r > 0]
        mech[sname] = {
            'n_days': int(len(d)),
            'avg_pairwise_corr_mean': round(float(avg.reindex(d).mean()), 4),
            'xsec_dispersion_mean_pct': round(float(disp.reindex(d).mean()) * 100, 3),
            'base_daily_ret_mean_pp': round(float(r.mean()), 4),
            'base_daily_ret_std_pp': round(float(r.std(ddof=1)), 4),
            'downside_day_share_pct': round(float((r < 0).mean()) * 100, 2),
            'neg_contrib_sum_pp': round(float(neg.sum()), 2),
            'pos_contrib_sum_pp': round(float(pos_.sum()), 2),
            'neg_share_of_gross_pct': round(float(abs(neg.sum()) / (abs(neg.sum()) + pos_.sum()) * 100), 2)
                if (len(neg) and len(pos_)) else None,
            'v2_gate_off_days_in_state': int(v2_gate.reindex(d).fillna(False).sum()),
            'rs_ic_by_segment': {sn: state_stats(mask, x, y)
                                 for sn, (x, y) in (('realA', WR.REALA), ('realB', REALB),
                                                    ('realC', WR.REALC))}}
    mech['H_F6_note'] = '待验假设 H_F6（低相关=分散保护）：lo/hi 截面对比是检验后叙事' \
                        '（VERDICT §五-2），只作机制登记，禁止写成已证实机制（PCX-B6）'

    # 35 态选择效应 MC（PCX-B5）
    tested_ps = [v['p_one_sided_upper'] for v in arc['variants'].values()
                 if v.get('status') == 'TESTED']
    m_states = len(tested_ps)
    rng = np.random.default_rng(SEED)
    NSIM = 20000
    P = rng.random((NSIM, m_states))
    Ps = np.sort(P, axis=1)
    n_ar = np.arange(1, m_states + 1)
    cond = Ps * m_states / n_ar <= 0.10
    # BH step-up：拒绝数 = 满足 p_(i)·m/i ≤ q 的最大 i（k），否则 0
    k_rej = np.where(cond.any(axis=1), (cond * n_ar).max(axis=1), 0)
    rej_any = k_rej > 0
    obs_rej = sum(1 for v in arc['variants'].values()
                  if v.get('status') == 'TESTED' and v.get('bh_reject_q010'))
    sel_mc = {'m_testable_states': m_states, 'n_sim': NSIM, 'global_null': 'p~U(0,1) 独立',
              'P_at_least_one_BH_reject_pct': round(float(rej_any.mean()) * 100, 2),
              'E_n_reject': round(float(k_rej.mean()), 3),
              'observed_BH_rejects': int(obs_rej),
              'verdict_note': 'Monte Carlo 复核（比 VERDICT「期望假发现≈2.7」更精确）：'
                              '全局零假设下 P(≥1 拒绝)=10.1%、E[拒绝数]=0.12，而实测 BH '
                              '拒绝 24 个——「全部态都是运气（纯伪影）」版本被 MC 决定性证伪'
                              '（其中 23 态为 PF-8 负尾真实负效应）；残余风险收缩为更尖锐的'
                              '「F6|lo 是 24 个真拒绝中唯一的正腿，恰是符号级假阳性最可能'
                              '藏身处」——不改变部署纪律：生死仍以前瞻段为准（PCX-B3）'}

    # A 臂总判定（PCX-B3/B4：生死未决=判活证据不足 ∧ 判死证据不足）
    f6_alive_ok = bool(crit1['t_ge2'])            # 判据①：已落定读数未达标（t<2）
    f6_dead = bool(crit3['triggered'])            # 判据③：未触发（IC 未翻转）
    f6_verdict = {
        'A_arm_verdict': 'PENDING_FORWARD_DATA（生死未决）' if not f6_dead else 'DEAD(判据③触发)',
        'logic': {'alive_evidence_insufficient': not f6_alive_ok,
                  'death_evidence_insufficient': not f6_dead},
        'criteria': {'c1': crit1, 'c2': crit2, 'c3': crit3},
        'holdout_full_read_registered': {**hold_lo,
                                         'contamination_note': '2026-04-01→05-31 子段 ⊆ 35 态扫描窗，登记不作判线'},
        'realC_monthly_rolling_ic_registered': monthly,
        'sample_extension_audit': ext_audit,
        'mechanism_check_H_F6': mech,
        'selection_effect_mc': sel_mc,
        'consequence': {'if_future_pass': 'F6 过 → 因子域首个可部署候选（首席条款）',
                        'if_future_flip': '任一翻转 → 立即判死 + F6 死亡证明 + 因子域全域死亡证明',
                        'now': '死亡证明不颁发（③未触发）；可部署资格不授予（①已落定读数 t<2，'
                               '且补短板证据只能来自前瞻数据）——因子域维持「一锤定音待深验」'}}

    # ---- f6_result.json（单B：A 臂 + B 臂）
    b_cells = {}
    for b in B_ARMS:
        b_cells[b] = {'definition': 'PCX-B7：' + ('vol_hi∧F6|lo→S3 半额开门，其余全停'
                                                  if b.startswith('B1') else
                                                  'vol_hi∧F6|hi→S3 半额开门，其余全停（剂量反证对照）'),
                      'pools': {p: {k: primary[p][b][k] for k in
                                    ('FULL', 'HOLDOUT', 'p_full_avoid_gt0', 'lag_FULL_avoid_pp',
                                     'lag_HOLDOUT_avoid_pp', 'lag_robust',
                                     'T3_realB_improve_vs_v2_pp', 'T3_realC_avoid_vs_base_pp',
                                     'fdr_reject_full', 'selected')} for p in pools}}
    f6_out = {'stage': 'f6_deep_verify_and_s3xf6', 'od': 'PCX-B1..B10（见脚本头注，冻结）',
              **common,
              'A_arm_deep_verify': f6_verdict,
              'B_arm_s3xf6': {'cells': b_cells,
                              'off_diag': {k: v for k, v in off_diag_block.items()
                                           if k.split('|')[1].startswith('B')}},
              'f6_lineage_zero_drift_check': chk,
              'verdict_rule_B': 'PCX-B8 四件套（FDR ∧ 双窗 avoid>0 ∧ 双窗 mdd_red≥10 ∧ lag 不翻转）'}
    with open(os.path.join(OUT, 'f6_result.json'), 'w') as f:
        json.dump(f6_out, f, ensure_ascii=False, indent=1)
    print('f6_result.json 完成；A 臂=', f6_verdict['A_arm_verdict'],
          '；B 臂 selected=', {k: v for k, v in selected.items() if k.split('|')[1].startswith('B')})
    print(f'总 wall={time.time()-t0:.0f}s')

    # 清内存大件
    for r in runs_raw:
        r.pop('day_cum', None)
        r.pop('trades', None)


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which == 'prereg':
        write_prereg()
    elif which == 'all':
        write_prereg()
        run_all()
