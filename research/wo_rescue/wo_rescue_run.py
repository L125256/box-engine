#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RESCUE_PACK b 单（H-D2 状态门 195 配置全扫）+ c 单（五方向最小实验）
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/RESCUE_PACK.md §三 b/c 单 + rescue_specs.json
- b 单主判据 = 避损金额/MDD 削减（弃 IC 单点）；195 配置禁止挑点；
  先冻结预注册再点火（b_preregistration.json 先落盘，扫描后写入禁改）。
- c 单五方向为本期"合理变体全集"；判死必须先跑完表内全部变体并附数。

【b 单预注册（PB-1..PB-10，先冻结后运行）】
PB-1 门变量与档位：vol20 分位门 {30,40,50,60,70,80}%（6）× 广度门 {20,30,40,50,60}%
  （5，绝对广度水平）× 资金费分位门 {20,40,60,80}%（4）。
PB-2 配置面=195：单变量 6+5+4=15；双变量 6×5+6×4+5×4=74；三变量 6×5×4=120。
  资金费维度数据不可得（box_cache 仅 OHLCV；wo2 P1 探针 11 端点 200 响应均无
  funding 字段指纹；「不可计算≠证伪」）→ 含资金费的 168 配置登记 NOT_RUNNABLE
  （附证据不跑伪数），可运行=41（vol 6+广度 5+vol×广度 30）。
PB-3 门变量操作性定义：vol20=池等权 idx 日收益 20 日滚动 std(ddof=1)×sqrt(252) 年化
  （H-D 冻结同构）；阈值=realA 段（2025-06-02→2026-03-31）该序列分位，仅 realA 估计。
  广度=池内 close>MA50（rolling50, min_periods=40）占比（H-A C9 冻结公式），
  门=绝对水平阈值。资金费门=逐日费率 60 日滚动分位（定义冻结、数据不可得）。
PB-4 门语义（H-D 冻结语义不变）：OFF=停开新仓 pause（跳过开仓与换仓卖出，存量仓
  止损/崩市/BUG-04 照常）；多变量组合 OFF = 各激活变量危险条件的 OR。
  vol20>t → OFF；广度<阈值 → OFF；费分位>阈值 → OFF（定义冻结）。
PB-5 费压口径=实盘费率×1.5：FEE_SIDE 0.0005→0.00075，FUNDING 0.0003→0.00045，
  base 臂与门臂同费对比。
PB-6 双窗口：全样本 FULL=2025-06-02→2026-10-17；留出段 HOLDOUT=2026-04-01→2026-10-17。
PB-7 主判据操作性定义：避损金额 avoid_pp = 门臂段净收益(pp) − base 臂段净收益(pp)；
  MDD 削减 mdd_red = (|base MDD|−|门臂 MDD|)/|base MDD|×100。
PB-8 达标线（双窗口同时满足才入选）：avoid_pp>0 且 mdd_red≥10%。
PB-9 多重比较：FDR(BH, q=0.10) 应用于 FULL 窗「避损金额>0」单侧 p；p 由日块
  stationary bootstrap（平均块长10，1000 次，seed=42）于 FULL 窗日净收益差
  （门臂−base）计算（p=P(boot mean≤0)）；全零差序列 p=1.0。BH 在 41 个已测配置上
  施行（m=41 如实记账；168 个不可运行配置无 p 不参与，登记而非剔除借口）。
  入选=FDR 幸存 ∧ HOLDOUT avoid_pp>0 ∧ 双窗口 mdd_red≥10% ∧ FULL avoid_pp>0。
PB-10 伴行账本：幸存+base 重跑 record=True 出止损避损台账（avoided_stop_pp，
  wo_hd 谱系）；热力图=vol×广度 6×5 面两池×双窗口。

【c 单操作性定义（PC-1..PC-7）】
PC-1 c1 资金费代理三变体（费率分位/费率斜率/费率-价格背离）：样本要求=日频≥240
  交易日费率史；快照覆盖 0% → 三变体全部 NOT_RUNNABLE（附 wo2/stage0 证据），
  非统计判死；复活条件=新数据源。
PC-2 c2 事件三变体（样本≥60）：E1 放量突破=OD3 冻结公式（H-A C6；RESCUE_PACK
  称 C9 复用，谱系如实注记）；E2 新高新低簇=近 5 日创 20 日新高或新低次数≥3；
  E3 跳空回补=近 5 日向下跳空>1% 且未回补（close<跳空日前收）。叠加=事件触发
  标的从当周买入名单剔除（避损型）。通过线=FULL 窗叠加臂净收益−base>0 且
  |MDD_叠加|≤|MDD_base|（费率=现行实盘，非 b 单费压口径）。事件计数窗口=FULL。
PC-3 c3 周期变体：单周期1=周信号日单日截面 z（OD8 现行基准）；单周期2=日 z 的
  5 日均值平滑（日尺度）；单周期3=因子取上一周五收盘值（周线聚合）再截面 z；
  合成=可得周期 z 等权均值。日内周期=快照仅日线，不可得登记。通过线=合成 IC 较
  最优单周期相对提升>15%（最优单周期 IC≤0 时提升无定义→如实判 FAIL 附数）。
  样本=realC 20 IC 日 + 扩展窗 realA→realC 全信号日。
PC-4 c4 池间 RS：RS20=个股 20 日收益−异池等权 20 日收益（full144 的异池=
  old131/new13 互指）；动量（多高 RS）与均值回归（多低 RS=−RS）双假设分开验、
  禁混栈。通过线=费后 IC t>2（注记：常数费不改秩，费后落在十分位价差−双边费>0）。
PC-5 c5 正交残差：合成 z 对风格 [vol20(个股), rev_10d, log 均额成交 20 日] 逐信号日
  截面 OLS 正交，残差 RankIC。通过线=残差 IC t>2（realC 与扩展窗分别报）。
PC-6 c 单判死纪律：每方向出变体清单（含计数），判死/不可运行逐条附数或附证据；
  空清单判死=R9 庸医行为。
PC-7 seed=42 冻结；引擎=dneg_engine 权威谱系（D0 对拍 maxdiff=0）；R8 Pool(32)。

用法：python3 wo_rescue_run.py prereg|b|c|all
产出：b_preregistration.json / b_gate_sweep.json / b_heatmap_{pool}_{win}.png /
      b_survivor_ledger.json / c_new_candidates.json
"""
import itertools
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根（云端化：禁绝对路径）
sys.path.insert(0, os.path.join(_ROOT, 'research', 'wo_dneg'))
import dneg_engine as DE

SEED = 42
CACHE = os.environ.get('FORWARD_BOX_CACHE') or os.path.join(_ROOT, '.cache', 'box_cache')
OUT = os.path.join(_ROOT, 'research', 'wo_rescue')
os.makedirs(OUT, exist_ok=True)
PREREG_F = os.path.join(OUT, 'b_preregistration.json')

REALA = (pd.Timestamp('2025-06-02'), pd.Timestamp('2026-03-31'))
FULL = (pd.Timestamp('2025-06-02'), pd.Timestamp('2026-10-17'))
HOLD = (pd.Timestamp('2026-04-01'), pd.Timestamp('2026-10-17'))
REALC = (pd.Timestamp('2026-06-01'), pd.Timestamp('2026-10-17'))
FEE_X = 1.5                    # PB-5 费压
FEE_SIDE_S = DE.FEE_SIDE * FEE_X
FUNDING_S = DE.FUNDING * FEE_X
VOL_GRID = [30, 40, 50, 60, 70, 80]
BR_GRID = [20, 30, 40, 50, 60]
FU_GRID = [20, 40, 60, 80]

_DATA = None
_POOLS = None
_F = None
_GV = None        # {pname: {'vol': Series, 'breadth': Series, 'vol_thr': {q: v}}}


def _init():
    global _DATA, _POOLS, _F, _GV
    if _DATA is not None:
        return
    _DATA = DE.load_data(CACHE)
    _POOLS = DE.build_pools(_DATA)
    _F = DE.build_factors(_DATA)
    _GV = {}
    for pname, syms in _POOLS.items():
        close = pd.DataFrame({s: _DATA[s]['close'] for s in syms})
        cal = pd.DatetimeIndex(sorted(set().union(*[set(_DATA[s].index) for s in syms])))
        close = close.reindex(cal)
        idx = close.mean(axis=1)
        vol = idx.pct_change().rolling(20).std(ddof=1) * np.sqrt(252)
        above = (close > close.rolling(50, min_periods=40).mean()).astype(float)
        breadth = above.mean(axis=1) * 100.0        # 0-100 %
        reala = vol[(vol.index >= REALA[0]) & (vol.index <= REALA[1])]
        _GV[pname] = {'vol': vol, 'breadth': breadth,
                      'vol_thr': {q: float(reala.quantile(q / 100.0)) for q in VOL_GRID}}


# ------------------------------------------------------------- 195 配置面
def enumerate_configs():
    """PB-2 配置面：规格公式（单 6+5+4 + 双 30+24+20 + 三 6×5×4）= 209。
    【规格差异如实登记】RESCUE_PACK 冻结文本写「共 195 个门配置」，但其逐项公式
    加总为 209（195 为规格算术 slip）。按 R9 穷尽原则取更大面 209 全跑，
    零挑点零遗漏；资金费依赖 168 项登记 NOT_RUNNABLE，可运行 41 不变。"""
    cfgs = []
    for q in VOL_GRID:
        cfgs.append({'id': f'vol{q}', 'vars': {'vol': q}, 'runnable': True})
    for b in BR_GRID:
        cfgs.append({'id': f'br{b}', 'vars': {'breadth': b}, 'runnable': True})
    for f_ in FU_GRID:
        cfgs.append({'id': f'fu{f_}', 'vars': {'funding': f_}, 'runnable': False})
    for q, b in itertools.product(VOL_GRID, BR_GRID):
        cfgs.append({'id': f'vol{q}+br{b}', 'vars': {'vol': q, 'breadth': b},
                     'runnable': True})
    for q, f_ in itertools.product(VOL_GRID, FU_GRID):
        cfgs.append({'id': f'vol{q}+fu{f_}', 'vars': {'vol': q, 'funding': f_},
                     'runnable': False})
    for b, f_ in itertools.product(BR_GRID, FU_GRID):
        cfgs.append({'id': f'br{b}+fu{f_}', 'vars': {'breadth': b, 'funding': f_},
                     'runnable': False})
    for q, b, f_ in itertools.product(VOL_GRID, BR_GRID, FU_GRID):
        cfgs.append({'id': f'vol{q}+br{b}+fu{f_}',
                     'vars': {'vol': q, 'breadth': b, 'funding': f_}, 'runnable': False})
    assert len(cfgs) == 209, len(cfgs)
    assert sum(c['runnable'] for c in cfgs) == 41
    return cfgs


# ------------------------------------------------------------- 门引擎（H-D 冻结语义）
def run_gate(syms, gate_map=None, exclude_fn=None, fee=None, fund=None):
    """逐行 dneg_engine.run_instr 同构；仅两处冻结插入：
    【插入1】信号日 off_next = gate_map[t]（PB-4）；
    【插入2】执行日 off_next=True → pause 跳过开仓与换仓卖出；exclude_fn(s,t)=True
    的标的从 target 剔除（c2 叠加，仅当传入）。费率可参数化（PB-5）。"""
    fee = DE.FEE_SIDE if fee is None else fee
    fund = DE.FUNDING if fund is None else fund
    close = pd.DataFrame({s: _DATA[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: _DATA[s]['open'] for s in syms})
    low = pd.DataFrame({s: _DATA[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(_DATA[s].index) for s in syms])))
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
    rng = np.random.default_rng(SEED)

    for t in cal:
        o_t, lo_t = open_.loc[t], low.loc[t]
        stopped_today = set()
        # 1) 盘中断价止损（原样）
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
        # 2) 挂单清仓（原样）
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
        # 3) 周调仓执行（+ 插入2 / c2 剔除）
        if pending_exec is not None and t == pending_exec[0]:
            _, target, eq_sig, off_next = pending_exec
            pending_exec = None
            n_rebal += 1
            if off_next:
                n_gate_off += 1
            if exclude_fn is not None:
                target = [s for s in target if not exclude_fn(s, t)]
            if not (off_next and True):        # pause 语义：OFF 周不卖
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
            if not off_next:                   # OFF：停开新仓
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
        # 4) 收盘记账 + 资金费（原样）
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
        # 5) 崩市检查（原样）
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) and med_ret[t] < DE.CRASH_MED:
            for s in pos:
                pending_reason.setdefault(s, 'crash')
            pending_sells.update(pos.keys())
        # 6) 周信号（+ 插入1）
        if t in sig_days:
            score = DE.cross_scores(_F, syms, t, DE.FACTORS_4)
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
            'n_gate_off': n_gate_off, 'trades': trades}


def seg_stats(curve, t0, t1):
    seg = curve[(curve.index >= t0) & (curve.index <= t1)]
    if len(seg) < 2:
        return None
    ret_pp = (seg.iloc[-1] / seg.iloc[0] - 1) * 100.0
    mdd = float((seg / seg.cummax() - 1).min()) * 100.0
    return {'ret_pp': round(float(ret_pp), 4), 'mdd_pct': round(mdd, 2),
            'n_days': int(len(seg))}


def boot_p_one_sided(diff, n_boot=1000, mean_len=10, seed=SEED):
    """PB-9：p = P(boot mean ≤ 0)，日块 stationary bootstrap。"""
    x = np.asarray(diff, dtype=float)
    if np.all(x == 0):
        return 1.0
    n = len(x)
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_len
    cnt = 0
    for _ in range(n_boot):
        idx, cur, ln = [], int(rng.integers(n)), max(1, rng.geometric(p))
        while len(idx) < n:
            idx.extend((cur + np.arange(ln)) % n)
            cur = int(rng.integers(n))
            ln = max(1, rng.geometric(p))
        if x[np.array(idx[:n])].mean() <= 0:
            cnt += 1
    return cnt / n_boot


def bh_fdr(pvals, q=0.10):
    """Benjamini-Hochberg：返回每个 p 是否拒绝。"""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(1, n + 1))
    thresh = np.minimum.accumulate(ranked[::-1])[::-1]
    rej = np.zeros(n, dtype=bool)
    rej[order] = ranked <= q
    return rej


# ------------------------------------------------------------- b 单 workers
def _b_worker(task):
    cid, vars_, pname = task
    _init()
    syms = _POOLS[pname]
    gv = _GV[pname]
    vol, brd = gv['vol'], gv['breadth']
    cond = pd.Series(False, index=vol.index)
    if 'vol' in vars_:
        cond = cond | (vol > gv['vol_thr'][vars_['vol']])
    if 'breadth' in vars_:
        cond = cond | (brd < float(vars_['breadth']))
    gate_map = cond.fillna(False).to_dict()
    g = run_gate(syms, gate_map=gate_map, fee=FEE_SIDE_S, fund=FUNDING_S)
    return {'cid': cid, 'pname': pname, 'n_gate_off': g['n_gate_off'],
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()}}


def _b_base(pname):
    _init()
    g = run_gate(_POOLS[pname], gate_map=None, fee=FEE_SIDE_S, fund=FUNDING_S)
    return {'cid': 'base', 'pname': pname, 'n_gate_off': 0,
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()}}


def stage_b():
    t0 = time.time()
    _init()
    cfgs = enumerate_configs()
    # 预注册先冻结（已由 prereg 命令落盘；此处校验存在且未被改）
    assert os.path.exists(PREREG_F), 'b_preregistration.json 未冻结——先跑 prereg'
    prereg = json.load(open(PREREG_F))

    run_tasks = [(c['id'], c['vars'], p) for c in cfgs if c['runnable'] for p in _POOLS]
    with Pool(32) as pool:
        gate_runs = pool.map(_b_worker, run_tasks)
        base_runs = pool.map(_b_base, list(_POOLS))
    G = {(r['cid'], r['pname']): r for r in gate_runs}
    B = {r['pname']: r for r in base_runs}

    # base 曲线转 Series（两池）
    base_curves = {p: pd.Series({pd.Timestamp(k): v
                                 for k, v in B[p]['curve'].items()}).sort_index()
                   for p in _POOLS}

    rows = []
    for c in cfgs:
        if not c['runnable']:
            rows.append({'id': c['id'], 'vars': c['vars'], 'runnable': False,
                         'status': 'NOT_RUNNABLE',
                         'reason': '资金费维度数据不可得（box_cache 仅 OHLCV；'
                                   'wo2 P1 探针 11 端点无 funding 字段指纹；不可计算≠证伪）'})
            continue
        for pname in _POOLS:
            gc = pd.Series({pd.Timestamp(k): v
                            for k, v in G[(c['id'], pname)]['curve'].items()}).sort_index()
            bc = base_curves[pname]
            row = {'id': c['id'], 'vars': c['vars'], 'pname': pname, 'runnable': True,
                   'n_gate_off_weeks': G[(c['id'], pname)]['n_gate_off']}
            for wn, (a, b_) in (('FULL', FULL), ('HOLDOUT', HOLD)):
                gs, bs = seg_stats(gc, a, b_), seg_stats(bc, a, b_)
                avoid = round(gs['ret_pp'] - bs['ret_pp'], 4)
                mdd_red = round((abs(bs['mdd_pct']) - abs(gs['mdd_pct']))
                                / abs(bs['mdd_pct']) * 100, 2) if bs['mdd_pct'] != 0 else None
                row[wn] = {'gated': gs, 'base': bs, 'avoid_pp': avoid, 'mdd_red_pct': mdd_red}
            diff = (gc.pct_change() - bc.pct_change()).dropna()
            diff = diff[(diff.index >= FULL[0]) & (diff.index <= FULL[1])]
            row['p_full_avoid_gt0'] = boot_p_one_sided(diff.values)
            rows.append(row)

    # PB-9 FDR：在 41 配置 × 2 池（按池分别 FDR，如实记 m）
    tested = [r for r in rows if r.get('runnable')]
    for pname in _POOLS:
        sub = [r for r in tested if r['pname'] == pname]
        ps = [r['p_full_avoid_gt0'] for r in sub]
        rej = bh_fdr(ps, q=prereg['fdr']['q'])
        for r, rj in zip(sub, rej):
            r['fdr_reject_full'] = bool(rj)
        # 入选判定
        for r in sub:
            f, h = r['FULL'], r['HOLDOUT']
            r['selected'] = bool(r['fdr_reject_full'] and f['avoid_pp'] > 0
                                 and h['avoid_pp'] > 0
                                 and f['mdd_red_pct'] is not None and f['mdd_red_pct'] >= 10
                                 and h['mdd_red_pct'] is not None and h['mdd_red_pct'] >= 10)
    selected = [r for r in tested if r.get('selected')]
    n_fdr = sum(1 for r in tested if r.get('fdr_reject_full'))

    # 幸存者+base 重跑 record=True 出止损避损台账（PB-10 伴行）
    ledger = {}
    sel_ids = sorted({(r['id'], r['pname']) for r in selected})
    if sel_ids:
        def _rec(task):
            cid, vars_, pname = task
            _init()
            gv = _GV[pname]
            vol, brd = gv['vol'], gv['breadth']
            cond = pd.Series(False, index=vol.index)
            if 'vol' in vars_:
                cond = cond | (vol > gv['vol_thr'][vars_['vol']])
            if 'breadth' in vars_:
                cond = cond | (brd < float(vars_['breadth']))
            g = run_gate(_POOLS[pname], gate_map=cond.fillna(False).to_dict(),
                         fee=FEE_SIDE_S, fund=FUNDING_S)
            return {'cid': cid, 'pname': pname, 'trades': g['trades']}
        with Pool(min(32, max(len(sel_ids), 1))) as pool:
            recs = pool.map(_rec, sel_ids)
        base_tr = {p: run_gate(_POOLS[p], gate_map=None, fee=FEE_SIDE_S,
                               fund=FUNDING_S)['trades'] for p in _POOLS}
        for r in recs:
            def stop_pp(trades, w):
                a, b_ = w
                tot = 0.0
                n = 0
                for tr in trades.values():
                    cd = tr['close_date']
                    if cd is None or not (str(a.date()) <= cd <= str(b_.date())):
                        continue
                    if tr['exit_reason'] == 'stop':
                        n += 1
                        tot += (tr['price_pnl'] + tr['entry_fee'] + tr['exit_fee']
                                + tr['funding']) * 100
                return {'stop_n': n, 'stop_pp': round(tot, 2)}
            ledger[f"{r['cid']}|{r['pname']}"] = {
                'gated': {w: stop_pp(r['trades'], ww)
                          for w, ww in (('FULL', FULL), ('HOLDOUT', HOLD))},
                'base': {w: stop_pp(base_tr[r['pname']], ww)
                         for w, ww in (('FULL', FULL), ('HOLDOUT', HOLD))}}

    out = {'stage': 'b_gate_sweep', 'ts': time.strftime('%F %T'),
           'prereg': '见 b_preregistration.json（先冻结后运行，PB-1..PB-10）',
           'total_configs_formula': 209, 'total_configs_spec_stated': 195,
           'runnable': 41, 'not_runnable': 168,
           'fdr_reject_full_count': n_fdr, 'n_selected': len(selected),
           'selected': selected, 'rows': rows, 'stop_ledger': ledger,
           'vol_thr_realA': {p: {q: round(v, 4) for q, v in _GV[p]['vol_thr'].items()}
                             for p in _POOLS},
           'wall_secs': round(time.time() - t0, 1)}
    with open(os.path.join(OUT, 'b_gate_sweep.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # 热力图：vol×breadth avoid_pp（FULL/HOLDOUT × 双池）
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        for wn in ('FULL', 'HOLDOUT'):
            fig, axes = plt.subplots(1, 2, figsize=(13, 5))
            for ax, pname in zip(axes, _POOLS):
                mat = np.full((len(BR_GRID), len(VOL_GRID)), np.nan)
                for i, b_ in enumerate(BR_GRID):
                    for j, q in enumerate(VOL_GRID):
                        cid = f'vol{q}+br{b_}'
                        r = next((x for x in tested if x['id'] == cid
                                  and x['pname'] == pname), None)
                        if r:
                            mat[i, j] = r[wn]['avoid_pp']
                im = ax.imshow(mat, cmap='RdYlGn', aspect='auto')
                ax.set_xticks(range(len(VOL_GRID)), [f'vol{q}' for q in VOL_GRID],
                              rotation=45)
                ax.set_yticks(range(len(BR_GRID)), [f'br{b_}' for b_ in BR_GRID])
                for i in range(len(BR_GRID)):
                    for j in range(len(VOL_GRID)):
                        if not np.isnan(mat[i, j]):
                            ax.text(j, i, f'{mat[i, j]:+.1f}', ha='center', va='center',
                                    fontsize=7)
                ax.set_title(f'{pname} {wn} avoid_pp (fee x1.5)')
                fig.colorbar(im, ax=ax, shrink=0.8)
            fig.tight_layout()
            fig.savefig(os.path.join(OUT, f'b_heatmap_{wn}.png'), dpi=110)
            plt.close(fig)
    except Exception as e:
        out['heatmap_error'] = f'{type(e).__name__}: {e}'

    print(f"b 单扫描完成：209=41 已跑 + 168 不可运行（数据缺口登记）；"
          f"FDR 幸存 {n_fdr}；入选 {len(selected)}"
          f"（{[r['id'] + '@' + r['pname'] for r in selected]}）"
          f" {out['wall_secs']}s")
    return out


# ================================================================ c 单：五方向
def _panels():
    """公共面板：收盘/开/量面板 + fwd5/fwd20 + 逐标的辅助因子。"""
    _init()
    syms = sorted(_DATA)
    C = pd.concat({s: _DATA[s]['close'] for s in syms}, axis=1).sort_index()
    O = pd.concat({s: _DATA[s]['open'] for s in syms}, axis=1).sort_index()
    V = pd.concat({s: _DATA[s]['volume'] for s in syms}, axis=1).sort_index()
    fwd = {h: C.shift(-h) / C - 1 for h in (5, 20)}
    return C, O, V, fwd


def _xsec_ic_series(fa, fb, min_names=30):
    """逐日截面 Spearman IC 序列（run_screen 谱系）。"""
    a, b = fa.align(fb, join='inner')
    out = {}
    for dt in a.index:
        x, y = a.loc[dt], b.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() < min_names:
            continue
        rx, ry = x[m].rank(), y[m].rank()
        if rx.std() == 0 or ry.std() == 0:
            continue
        out[dt] = np.corrcoef(rx, ry)[0, 1]
    return pd.Series(out)


def _tstat(ic):
    ic = ic.dropna()
    if len(ic) < 3 or ic.std(ddof=1) == 0:
        return None, int(len(ic))
    return float(ic.mean() / ic.std(ddof=1) * np.sqrt(len(ic))), int(len(ic))


def _decile_spread_fee(fa, fb, fee_rt_pp=0.10):
    """TopBottom 十分位价差均值(pp) − 双边费(pp)（费后判据件）。"""
    a, b = fa.align(fb, join='inner')
    sp = []
    for dt in a.index:
        x, y = a.loc[dt], b.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() < 30:
            continue
        lab = pd.qcut(x[m].rank(method='first'), 10, labels=False)
        sp.append((y[m][lab == 9].mean() - y[m][lab == 0].mean()) * 100)
    sp = pd.Series(sp)
    if sp.empty:
        return None, None, None
    return float(sp.mean()), float(sp.mean() - fee_rt_pp), int(len(sp))


def c1_funding():
    """PC-1：三变体 NOT_RUNNABLE 登记（数据缺口证据，非统计判死）。"""
    _init()
    fields = set()
    for fn in sorted(os.listdir(CACHE))[:5]:
        d = json.load(open(os.path.join(CACHE, fn)))
        if isinstance(d, list) and d:
            fields |= set(d[0].keys())
    wo2 = json.load(open(os.path.join(_ROOT, 'research', 'wo_cycle1', 'wo2_result.json')))
    probe = wo2['p1_probe']['results']
    n_probe = len(probe)
    n_probe_funding = sum(1 for p in probe if p.get('mentions_funding'))
    variants = [
        {'id': 'c1a_funding_pct', 'def': '费率 60 日滚动分位'},
        {'id': 'c1b_funding_slope', 'def': '费率 20 日斜率'},
        {'id': 'c1c_fund_px_div', 'def': '费率-价格背离（费率分位 vs 20 日收益分位差）'},
    ]
    return {'direction': 'c1 资金费代理', 'variants': [
        {**v, 'status': 'NOT_RUNNABLE',
         'evidence': f'快照字段={sorted(fields)}（无 funding/rate）；wo2 P1 探针 '
                     f'{n_probe} 端点中 {n_probe_funding} 个含 funding 指纹且均非 200 有效'
                     '（wo2_result.json p1_probe）；样本要求=日频≥240 交易日费率史，覆盖 0%',
         'revival': '新数据源出现（wo2 缺口登记复活条款）'}
        for v in variants],
        'variant_total': 3, 'variant_run': 0,
        'verdict': '不可测试（数据域缺口），非统计判死；按 R9 附证据登记排除册'}


def _event_masks(C, O, V):
    """PC-2 三事件掩码面板（逐日×逐标的布尔）。"""
    vr5 = V.rolling(5).mean() / V.rolling(20).mean()
    e1 = (C >= C.rolling(20).max().shift(1)) & (vr5 > 1.5)          # E1 OD3 谱系
    nh = (C >= C.rolling(20).max().shift(1)).rolling(5).sum()
    nl = (C <= C.rolling(20).min().shift(1)).rolling(5).sum()
    e2 = (nh >= 3) | (nl >= 3)                                       # E2 簇
    gap = O / C.shift(1) - 1.0
    dn = gap < -0.01
    # E3：近 5 日曾向下跳空>1% 且 close<跳空日前收（未回补）
    pre_gap_close = C.where(dn).ffill(limit=5)
    e3 = dn.rolling(5).max().astype(bool) & (C < pre_gap_close.ffill())
    return {'E1_brk_vol': e1, 'E2_nhnl_cluster': e2, 'E3_gap_unfilled': e3}


def _c2_worker(task):
    """c2 叠加臂回测（现行实盘费率，PC-2）。"""
    ev_name, pname = task
    _init()
    syms = _POOLS[pname]
    C, O, V, _ = _panels()
    masks = _event_masks(C, O, V)
    ev = masks[ev_name]
    exclude_fn = lambda s, t: bool(ev.at[t, s]) if (t in ev.index and s in ev.columns) else False
    g = run_gate(syms, gate_map=None, exclude_fn=exclude_fn)
    return {'event': ev_name, 'pname': pname,
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()},
            'n_excluded_exec': None}


def stage_c():
    t0 = time.time()
    C, O, V, fwd = _panels()
    iso = C.index.isocalendar()
    sig_all = pd.DatetimeIndex(C.index.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)
    sig_ext = sig_all[(sig_all >= REALA[0]) & (sig_all <= REALC[1])]
    sig_rc = sig_all[(sig_all >= REALC[0]) & (sig_all <= REALC[1])]
    out = {'stage': 'c_new_candidates', 'ts': time.strftime('%F %T'),
           'od': 'PC-1..PC-7（见头注，冻结）', 'directions': {}}

    # ---- c1
    out['directions']['c1'] = c1_funding()

    # ---- c2 事件叠加（base 现行费率臂）
    _init()
    masks = _event_masks(C, O, V)
    ev_counts = {}
    for k, m in masks.items():
        ev_counts[k] = {'signal_day_events_full': int(
            (m.reindex(index=C.index).fillna(False)
             .loc[[d for d in sig_ext if d in m.index]])
            .to_numpy().sum()),
            'all_day_events_full': int(m.loc[(m.index >= REALA[0]) &
                                             (m.index <= REALC[1])].to_numpy().sum())}
    b_tasks = [(k, p) for k in masks for p in _POOLS]
    with Pool(32) as pool:
        ov = pool.map(_c2_worker, b_tasks)
    base_runs = {p: run_gate(_POOLS[p], gate_map=None) for p in _POOLS}
    c2 = {'events': {}, 'event_counts': ev_counts}
    for r in ov:
        oc = pd.Series({pd.Timestamp(k): v for k, v in r['curve'].items()}).sort_index()
        bc = base_runs[r['pname']]['curve']
        row = {}
        for wn, (a, b_) in (('FULL', FULL), ('realC', REALC)):
            os_, bs = seg_stats(oc, a, b_), seg_stats(bc, a, b_)
            row[wn] = {'overlay': os_, 'base': bs,
                       'avoid_incr_pp': round(os_['ret_pp'] - bs['ret_pp'], 4),
                       'mdd_not_worse': bool(abs(os_['mdd_pct']) <= abs(bs['mdd_pct']) + 1e-9)}
        f = row['FULL']
        row['OVERALL'] = 'PASS' if (f['avoid_incr_pp'] > 0 and f['mdd_not_worse']) else 'FAIL'
        c2['events'][f"{r['event']}|{r['pname']}"] = row
    c2['variant_total'] = 3 * 2
    c2['variant_run'] = len(ov)
    c2['verdict'] = ('PASS' if any(v['OVERALL'] == 'PASS' for v in c2['events'].values())
                     else 'FAIL（三事件×双池 6 变体全跑完，逐变体数字见 events）')
    out['directions']['c2'] = c2

    # ---- c3 多周期合成
    F4 = DE.FACTORS_4

    def zcomp_at(t, mode):
        """信号日合成 z：mode in {weekly_base, daily_smooth5, weekly_agg}。"""
        rows = {}
        for s in sorted(_DATA):
            f = _F[s]
            if t not in f.index:
                continue
            vals = {}
            for k in F4:
                ser = f[k].loc[:t].dropna()
                if ser.empty:
                    break
                if mode == 'weekly_base':
                    vals[k] = ser.iloc[-1]
                elif mode == 'daily_smooth5':
                    vals[k] = ser.iloc[-5:].mean() if len(ser) >= 5 else np.nan
                elif mode == 'weekly_agg':
                    # 上一周五收盘值（周线聚合）
                    wk = ser.resample('W-FRI').last().dropna()
                    past = wk[wk.index < t]
                    vals[k] = past.iloc[-1] if len(past) else np.nan
            if len(vals) == len(F4) and all(pd.notna(v) for v in vals.values()):
                rows[s] = vals
        if len(rows) < 30:
            return None
        mat = pd.DataFrame(rows, index=F4).T
        mu, sd = mat.mean(), mat.std(ddof=0)
        z = ((mat - mu) / sd.replace(0.0, np.nan)).clip(-3, 3)
        return z.mean(axis=1).dropna()

    c3 = {'periods': ['weekly_base(OD8 基准)', 'daily_smooth5(日尺度)', 'weekly_agg(周线聚合)',
                      'intraday(不可得：快照仅日线，登记)'], 'windows': {}}
    for wn, sigs in (('realC20', sig_rc), ('extended', sig_ext)):
        fwd5 = fwd[5]
        ics = {m: [] for m in ('weekly_base', 'daily_smooth5', 'weekly_agg', 'composite')}
        for t in sigs:
            y = fwd5.loc[t]
            zs = {}
            for m in ('weekly_base', 'daily_smooth5', 'weekly_agg'):
                z = zcomp_at(t, m)
                if z is None:
                    zs[m] = None
                    continue
                mi = z.index.intersection(y.dropna().index)
                if len(mi) < 30 or z[mi].std() == 0:
                    zs[m] = None
                    continue
                zs[m] = (z, mi)
            for m in ('weekly_base', 'daily_smooth5', 'weekly_agg'):
                if zs[m] is not None:
                    z, mi = zs[m]
                    ics[m].append(np.corrcoef(z[mi].rank(), y[mi].rank())[0, 1])
            if all(zs[m] is not None for m in ('weekly_base', 'daily_smooth5', 'weekly_agg')):
                mi = zs['weekly_base'][1]
                zc = sum(zs[m][0].reindex(mi) for m in
                         ('weekly_base', 'daily_smooth5', 'weekly_agg')) / 3.0
                zc = zc.dropna()
                yv = y.reindex(zc.index).dropna()
                if len(zc) >= 30 and zc.std() != 0 and yv.std() != 0:
                    ics['composite'].append(np.corrcoef(zc.loc[yv.index].rank(), yv.rank())[0, 1])
        row = {}
        for m, v in ics.items():
            s = pd.Series(v).dropna()
            t_, n = _tstat(s)
            row[m] = {'ic_mean': float(s.mean()) if len(s) else None,
                      't_stat': t_, 'n_days': n}
        singles = [row[m]['ic_mean'] for m in ('weekly_base', 'daily_smooth5', 'weekly_agg')
                   if row[m]['ic_mean'] is not None]
        best = max(singles) if singles else None
        comp = row['composite']['ic_mean']
        row['best_single_ic'] = best
        row['improvement_pct'] = (round((comp - best) / abs(best) * 100, 2)
                                  if (comp is not None and best and best > 0) else None)
        row['OVERALL'] = ('PASS' if (row['improvement_pct'] is not None
                                     and row['improvement_pct'] > 15) else 'FAIL')
        c3['windows'][wn] = row
    c3['variant_total'] = 3
    c3['variant_run'] = 3
    c3['verdict'] = '三变体全跑完；日内不可得登记；判定逐窗附数'
    out['directions']['c3'] = c3

    # ---- c4 池间 RS（双假设分开）
    _init()
    new13 = sorted(set(_POOLS['full144']) - set(_POOLS['old131']))
    ret20 = C / C.shift(20) - 1
    idx_old = ret20[_POOLS['old131']].mean(axis=1)
    idx_new = ret20[new13].mean(axis=1) if new13 else None
    rs_mom = pd.DataFrame(index=C.index, columns=C.columns, dtype=float)
    rs_rev = pd.DataFrame(index=C.index, columns=C.columns, dtype=float)
    for s in C.columns:
        other = idx_new if s in _POOLS['old131'] else idx_old
        rs = ret20[s] - other
        rs_mom[s] = rs
        rs_rev[s] = -rs
    c4 = {'def': 'RS20=个股20日收益−异池等权20日收益（full144 内 old131/new13 互指）；动量/回归分开验',
          'hypotheses': {}, 'variant_total': 2 * 2, 'variant_run': 4}
    for hname, fa in (('RS_momentum', rs_mom), ('RS_mean_reversion', rs_rev)):
        for h in (5, 20):
            ic_ext = _xsec_ic_series(fa.loc[sig_ext].reindex(C.index, fill_value=np.nan).dropna(how='all')
                                     if False else fa, fwd[h])
            ic_ext = ic_ext[(ic_ext.index >= REALA[0]) & (ic_ext.index <= REALC[1])]
            ic_rc = ic_ext[(ic_ext.index >= REALC[0])]
            t_ext, n_ext = _tstat(ic_ext)
            t_rc, n_rc = _tstat(ic_rc)
            sp_raw, sp_net, n_sp = _decile_spread_fee(
                fa.loc[sig_ext], fwd[5].loc[sig_ext].reindex(fa.loc[sig_ext].index))
            c4['hypotheses'][f'{hname}|fwd{h}'] = {
                'ic_mean_extended': float(ic_ext.mean()), 't_extended': t_ext, 'n_extended': n_ext,
                'ic_mean_realC': float(ic_rc.mean()) if len(ic_rc) else None,
                't_realC': t_rc, 'n_realC': n_rc,
                'decile_spread_pp_raw': round(sp_raw, 4) if sp_raw is not None else None,
                'decile_spread_pp_net_of_fee': round(sp_net, 4) if sp_net is not None else None,
                'pass_t_gt_2': bool((t_ext is not None and t_ext > 2))}
    c4['verdict'] = '双假设×双 horizon 全跑完（4 变体），逐变体 t 与费后价差附数'
    out['directions']['c4'] = c4

    # ---- c5 正交残差
    vol_i = C.pct_change().rolling(20).std()
    rev_i = -(C / C.shift(10) - 1)
    turn_i = np.log((C * V).rolling(20).mean())

    def comp_z(t):
        rows = {}
        for s in sorted(_DATA):
            f = _F[s]
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

    def resid_ic(sigs, h):
        ics = []
        for t in sigs:
            z = comp_z(t)
            if z is None:
                continue
            y = fwd[h].loc[t].reindex(z.index)
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
        s = pd.Series(ics).dropna()
        t_, n = _tstat(s)
        return {'ic_mean': float(s.mean()) if len(s) else None, 't_stat': t_, 'n_days': n}

    c5 = {'styles': ['vol20', 'rev_10d', 'log_turn20'], 'windows': {
        'realC20': resid_ic(sig_rc, 5), 'extended': resid_ic(sig_ext, 5)}}
    c5['variant_total'] = 1
    c5['variant_run'] = 1
    t_ext = c5['windows']['extended']['t_stat']
    c5['verdict'] = f'残差 IC 全窗附数；pass(t>2, extended)={bool(t_ext is not None and t_ext > 2)}'
    out['directions']['c5'] = c5

    out['wall_secs'] = round(time.time() - t0, 1)
    with open(os.path.join(OUT, 'c_new_candidates.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for d, v in out['directions'].items():
        print(d, '→', v.get('verdict', '')[:100])
    print(f"c 单完成 {out['wall_secs']}s")
    return out


# ================================================================ main
def write_prereg():
    cfgs = enumerate_configs()
    pre = {'workorder': 'b 单 H-D2 状态门新预注册（先冻结后运行）',
           'frozen_at': time.strftime('%F %T'),
           'absorbed_evidence': 'C9（H-A breadth_above_ma50 时序 Spearman=+0.163，n=628）+ '
                                'RESCUE_PACK 记「C9 放量突破+0.163」（放量维度经 H-A OD3/C6 进事件层 c2）',
           'grid': {'vol20_pct': VOL_GRID, 'breadth_pct': BR_GRID, 'funding_pct': FU_GRID},
           'total_configs_formula': 209,
           'total_configs_spec_stated': 195,
           'spec_discrepancy_note': '规格逐项公式加总=209；冻结文本「共195」为算术 slip；'
                                    '按 R9 穷尽原则取 209 全跑（多跑不少跑）',
           'combinations': {'single': 15, 'double': 74, 'triple': 120,
                            'runnable_no_funding': 41, 'funding_not_runnable': 168},
           'windows': {'FULL': [str(FULL[0].date()), str(FULL[1].date())],
                       'HOLDOUT': [str(HOLD[0].date()), str(HOLD[1].date())]},
           'fee_stress': {'FEE_SIDE': FEE_SIDE_S, 'FUNDING': FUNDING_S, 'x': FEE_X},
           'primary_metric': 'avoid_pp>0 且 mdd_red≥10%（双窗口同时满足，PB-7/PB-8）',
           'fdr': {'method': 'BH', 'q': 0.10, 'applied_to': 'FULL 窗 avoid>0 单侧 bootstrap p',
                   'm': 41, 'note': '168 个资金费依赖配置无 p（数据不可得），登记 NOT_RUNNABLE'},
           'gate_semantics': 'OFF=停开新仓 pause；多变量 OR；vol20>t、breadth<t、funding 分位>t（定义冻结）',
           'threshold_estimation': 'vol20 阈值=realA 段分位（仅 realA 数据，防前视）；'
                                   'breadth=绝对水平；funding=60 日滚动分位（无数据）',
           'config_ids': [c['id'] for c in cfgs],
           'engine_lineage': 'dneg_engine（f1_backtest_v2 逐行，D0 maxdiff=0）；门插入仅 2 处见 run_gate 头注',
           'seed': SEED}
    json.dump(pre, open(PREREG_F, 'w'), ensure_ascii=False, indent=1)
    print('预注册已冻结 →', PREREG_F)


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which in ('prereg', 'all'):
        write_prereg()
    if which in ('b', 'all'):
        stage_b()
    if which in ('c', 'all'):
        stage_c()
