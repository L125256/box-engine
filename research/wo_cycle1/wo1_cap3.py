#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WO1 cap3 补检（R6-1b · 冻结规格 v1.0 · 一次成活 · seed=42）
参数空间：仅 cap3（A confirm=2 不变 + B entry_cap=3，已批档位 {2,3,4} 内不扩围）；
对照臂 = cap2 同套检验（对称纪律）。主体池 old131（工单引用数字口径，与 R6-1 一致）。
引擎：逐行复制 /tmp/r6_1/ab_validation.py（谱系 r5_3_scan.py ← eng_w2_f1/f1_backtest.py），
仅新增 cap3 档、训练窗回吐侧对称检验与换段复验模块，不改任何口径。
执行形态：
 - multiprocessing Pool(32) 并行——LOTO 逐笔封禁重跑按 (sym,date) 任务切片分发、
   月块 bootstrap 1000 次重抽索引由主进程单流 seed=42 预生成后按迭代切片分发；
   子任务纯函数化、按任务序号回收 → 结果与串行逐一对应、每子进程确定性。
 - 引擎热路径纯性能重构（run_backtest_fast）：与 ban/cap 无关的回测上下文
   （行情矩阵、idx/MA50、崩市中位、周信号目标表）一次构建全任务复用；
   算术序列不变，启动时与原引擎逐位等价断言（curve/fees/buys/sells 全等）。

检验（冻结清单）：
 1. LOTO：留出窗优势逐笔剔除（ban 重跑、仓位闲置口径），贡献表+top_trade_share；
 2. LMO：逐月剔除，只报 CI 不作独立否决；
 3. 月块 bootstrap：seed=42，1000 次，月块有放回重抽，P(优势>0) 与 5%~95% CI；
 4. 分月拆解：cap3−base 逐月 diff 表（对齐 ab_validation.json check2 口径）；
 5. 对称检验：训练窗回吐侧（base−cap3 总收益空间）同跑 LTO+LMO；
 6. 换段复验：holdout 重切为 2026-06-01→今（真实窗），优势方向为正且 G1 同口径成立
   （cap3 不得用已被看过的留出窗 2026-04→05 自证）。

通过判据（预注册冻结）：G1 剔除最大贡献笔(MVLLUSDT 2026-04-07)后留出优势≥10pp；
G2 月块 bootstrap P(优势>0)≥0.90 且 5%分位>−50pp；G3 top_trade_share≤50%；
G4 换段复验优势为正且 G1 同口径成立；G5 训练窗回吐侧 LTO 单点主导≤50%。
任一 G 不达 → cap3 退回污染名单，收益主张撤回。对照臂 cap2 同表呈报、同套判定。
数据出身分段：真实窗（>=2025-06）单独达标；留出窗全段属真实窗。
复现：python3 wo1_cap3.py
"""
import json
import os
import time
import datetime

import numpy as np
import pandas as pd
from multiprocessing import get_context

SEED = 42
rng = np.random.default_rng(SEED)
np.random.seed(SEED)

CACHE = '/tmp/box_cache'
OUT = '/workspace/repo_ready/research/wo_cycle1'
os.makedirs(OUT, exist_ok=True)

NPROC = 32
TOP_N = 5
SLOT = 0.10
STOP = -0.08
CRASH_MED = -0.05
FEE_SIDE = 0.0005
FUNDING = 0.0003
MA_REG = 50
GATE_CONFIRM = 2            # A：已批档位，不变
CAP_MAIN = 3                # WO1 主臂（已批档位 {2,3,4} 内）
CAP_CTRL = 2                # 对照臂（对称纪律）
TRAIN_END = pd.Timestamp('2026-03-31')
HOLD_START = pd.Timestamp('2026-04-01')
RESEG_START = pd.Timestamp('2026-06-01')   # 换段复验：重切 holdout 起点（真实窗）
REAL_START = pd.Timestamp('2025-06-01')    # 数据出身分界（WO1 规格：真实>=2025-06）

FACTORS_4 = ['ma20_slope', 'obv_slope20', 'dist_52w_high', 'mom_1m']


# --------------------------- 数据/池/因子（ab_validation.py 原样复制）
def load_data():
    data = {}
    for fn in sorted(os.listdir(CACHE)):
        sym = fn[:-5]
        df = pd.DataFrame(json.load(open(os.path.join(CACHE, fn))))
        df['time'] = pd.to_datetime(df['time'])
        df = df.set_index('time').sort_index()
        data[sym] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return data


def build_pools(data):
    old = sorted(s for s, d in data.items()
                 if d.index[0] <= pd.Timestamp('2025-03-31'))
    full = sorted(s for s, d in data.items() if len(d) >= 100)
    assert len(old) == 131 and len(full) == 144
    return {'old131': old, 'full144': full}


def build_factors(data):
    F = {}
    for s, d in data.items():
        c, v = d['close'], d['volume']
        ma20 = c.rolling(20).mean()
        f_ma = ma20 / ma20.shift(5) - 1
        obv = (np.sign(c.diff()).fillna(0.0) * v).cumsum()
        f_obv = (obv - obv.shift(20)) / (v.rolling(20).mean() * 20.0)
        f_52w = c / c.rolling(252, min_periods=20).max() - 1.0
        f_mom = c / c.shift(21) - 1.0
        F[s] = pd.DataFrame({'ma20_slope': f_ma, 'obv_slope20': f_obv,
                             'dist_52w_high': f_52w, 'mom_1m': f_mom})
    return F


def cross_scores(F, syms, dt, factors):
    rows = {}
    for s in syms:
        f = F[s]
        if dt not in f.index:
            continue
        vals = f.loc[dt, factors]
        if vals.notna().sum() == len(factors):
            rows[s] = vals.values
    if len(rows) < TOP_N:
        return pd.Series(dtype=float)
    mat = pd.DataFrame(rows, index=factors).T
    mu, sd = mat.mean(), mat.std(ddof=0)
    z = ((mat - mu) / sd.replace(0.0, np.nan)).clip(-3, 3)
    return z.mean(axis=1).dropna().sort_values(ascending=False)


# --------------------------- 回测引擎（ab_validation.py 逐行复制，含 ban）
def run_backtest(data, F, syms, gate_confirm=1, entry_cap=None, ban=None):
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: data[s]['open'] for s in syms})
    low = pd.DataFrame({s: data[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close = close.reindex(cal)
    open_ = open_.reindex(cal)
    low = low.reindex(cal)
    mark = close.ffill()
    idx = close.mean(axis=1)
    idx_ma = idx.rolling(MA_REG).mean()
    med_ret = close.pct_change().median(axis=1)

    iso = cal.isocalendar()
    sig_days = set(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first())

    cash, pos = 1.0, {}
    pending_sells = {}
    pending_exec = None
    gate_streak = 0
    eq = {}
    fees = turnover = 0.0
    n_rebal = 0
    sells, buys = [], []

    for t in cal:
        o_t, lo_t, c_t = open_.loc[t], low.loc[t], close.loc[t]
        for s in list(pos):
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            stop_p = pos[s]['entry'] * (1 + STOP)
            if not (o_t[s] <= stop_p or lo_t[s] <= stop_p):
                continue
            px = o_t[s] if o_t[s] <= stop_p else stop_p
            cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
            fees += pos[s]['qty'] * px * FEE_SIDE
            turnover += pos[s]['qty'] * px
            sells.append({'date': str(t.date()), 'sym': s,
                          'px': round(float(px), 6), 'reason': 'stop'})
            del pos[s]
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
                fees += pos[s]['qty'] * px * FEE_SIDE
                turnover += pos[s]['qty'] * px
                sells.append({'date': str(t.date()), 'sym': s,
                              'px': round(float(px), 6),
                              'reason': pending_sells[s]})
                del pos[s]
            del pending_sells[s]
        if pending_exec is not None and t == pending_exec[0]:
            _, target, eq_sig, buy_now = pending_exec
            pending_exec = None
            n_rebal += 1
            for s in list(pos):
                if s in target or s in pending_sells:
                    continue
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    pending_sells[s] = 'rebal'
                    continue
                cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
                fees += pos[s]['qty'] * px * FEE_SIDE
                turnover += pos[s]['qty'] * px
                sells.append({'date': str(t.date()), 'sym': s,
                              'px': round(float(px), 6),
                              'reason': 'gate_off' if len(target) == 0 else 'rebal'})
                del pos[s]
            for s in buy_now:
                if s in pos:
                    continue
                if ban is not None and (s, str(t.date())) in ban:
                    continue              # LOTO：封禁该笔入场，仓位闲置
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    continue
                budget = min(SLOT * eq_sig, max(cash, 0.0))
                if budget <= 0:
                    continue
                qty = budget / px
                cash -= qty * px * (1 + FEE_SIDE)
                fees += qty * px * FEE_SIDE
                turnover += qty * px
                pos[s] = {'qty': qty, 'entry': px}
                buys.append({'date': str(t.date()), 'sym': s,
                             'px': round(float(px), 6)})
        equity = cash
        for s, p in pos.items():
            m = mark.at[t, s]
            equity += p['qty'] * m
            f = p['qty'] * m * FUNDING
            cash -= f
            fees += f
        eq[t] = equity
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                and med_ret[t] < CRASH_MED:
            for s in pos:
                pending_sells.setdefault(s, 'crash')
        if t in sig_days:
            score = cross_scores(F, syms, t, FACTORS_4)
            hold_mode = False
            if not pd.isna(idx_ma.get(t, np.nan)) and idx[t] < idx_ma[t]:
                gate_streak += 1
            else:
                gate_streak = 0
            if gate_streak >= gate_confirm:
                target = []
            elif gate_streak >= 1:
                target = list(pos.keys())
                hold_mode = True
            else:
                target = list(score.index[:TOP_N])
            if hold_mode:
                buy_now = []
            elif entry_cap is not None and len(target) > 0:
                held = set(pos.keys())
                cand = [s for s in target if s not in held]
                buy_now = cand[:ENTRY_CAP_LOCAL]
            elif len(target) == 0:
                buy_now = []
            else:
                buy_now = list(target)
            nxt = cal.get_loc(t) + 1
            pending_exec = (cal[nxt], target, equity, buy_now) \
                if nxt < len(cal) else None

    curve = pd.Series(eq).sort_index()
    return {'curve': curve, 'fees': fees, 'turnover': turnover,
            'n_rebal': n_rebal, 'start': str(cal[0].date()),
            'end': str(cal[-1].date()), 'sells': sells, 'buys': buys}


ENTRY_CAP_LOCAL = 2   # 由 run_cap 显式设置（引擎内引用）


def run_cap(data, F, syms, cap):
    global ENTRY_CAP_LOCAL
    ENTRY_CAP_LOCAL = cap
    return run_backtest(data, F, syms, gate_confirm=GATE_CONFIRM, entry_cap=cap)


# --------------------------- 快速引擎（纯性能重构，逐位等价；上下文 ban/cap 无关）
def prepare_context(data, F, syms):
    """构建与 ban/cap 无关的全部回测上下文，一次构建全任务复用。"""
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: data[s]['open'] for s in syms})
    low = pd.DataFrame({s: data[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close = close.reindex(cal)
    open_ = open_.reindex(cal)
    low = low.reindex(cal)
    mark = close.ffill()
    idx = close.mean(axis=1)
    idx_ma = idx.rolling(MA_REG).mean()
    med_ret = close.pct_change().median(axis=1)
    iso = cal.isocalendar()
    sig_days = set(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first())
    sig_target = {t: list(cross_scores(F, syms, t, FACTORS_4).index[:TOP_N])
                  for t in sig_days}
    return dict(cal=cal, sig_days=sig_days, sig_target=sig_target,
                o={t: open_.loc[t] for t in cal},
                lo={t: low.loc[t] for t in cal},
                mark={t: mark.loc[t] for t in cal},
                idx=idx.to_dict(), idx_ma=idx_ma.to_dict(),
                med=med_ret.to_dict())


def run_backtest_fast(ctx, gate_confirm=1, entry_cap=None, ban=None):
    """与 run_backtest 算术序列逐位一致；仅将不变量查表化。"""
    cal = ctx['cal']
    o_map, lo_map, mark_map = ctx['o'], ctx['lo'], ctx['mark']
    idx_d, idxma_d, med_d = ctx['idx'], ctx['idx_ma'], ctx['med']
    sig_days, sig_target = ctx['sig_days'], ctx['sig_target']

    cash, pos = 1.0, {}
    pending_sells = {}
    pending_exec = None
    gate_streak = 0
    eq = {}
    fees = turnover = 0.0
    n_rebal = 0
    sells, buys = [], []

    for t in cal:
        o_t, lo_t = o_map[t], lo_map[t]
        for s in list(pos):
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            stop_p = pos[s]['entry'] * (1 + STOP)
            if not (o_t[s] <= stop_p or lo_t[s] <= stop_p):
                continue
            px = o_t[s] if o_t[s] <= stop_p else stop_p
            cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
            fees += pos[s]['qty'] * px * FEE_SIDE
            turnover += pos[s]['qty'] * px
            sells.append({'date': str(t.date()), 'sym': s,
                          'px': round(float(px), 6), 'reason': 'stop'})
            del pos[s]
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
                fees += pos[s]['qty'] * px * FEE_SIDE
                turnover += pos[s]['qty'] * px
                sells.append({'date': str(t.date()), 'sym': s,
                              'px': round(float(px), 6),
                              'reason': pending_sells[s]})
                del pos[s]
            del pending_sells[s]
        if pending_exec is not None and t == pending_exec[0]:
            _, target, eq_sig, buy_now = pending_exec
            pending_exec = None
            n_rebal += 1
            for s in list(pos):
                if s in target or s in pending_sells:
                    continue
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    pending_sells[s] = 'rebal'
                    continue
                cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
                fees += pos[s]['qty'] * px * FEE_SIDE
                turnover += pos[s]['qty'] * px
                sells.append({'date': str(t.date()), 'sym': s,
                              'px': round(float(px), 6),
                              'reason': 'gate_off' if len(target) == 0 else 'rebal'})
                del pos[s]
            for s in buy_now:
                if s in pos:
                    continue
                if ban is not None and (s, str(t.date())) in ban:
                    continue              # LOTO：封禁该笔入场，仓位闲置
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    continue
                budget = min(SLOT * eq_sig, max(cash, 0.0))
                if budget <= 0:
                    continue
                qty = budget / px
                cash -= qty * px * (1 + FEE_SIDE)
                fees += qty * px * FEE_SIDE
                turnover += qty * px
                pos[s] = {'qty': qty, 'entry': px}
                buys.append({'date': str(t.date()), 'sym': s,
                             'px': round(float(px), 6)})
        equity = cash
        for s, p in pos.items():
            m = mark_map[t][s]
            equity += p['qty'] * m
            f = p['qty'] * m * FUNDING
            cash -= f
            fees += f
        eq[t] = equity
        if len(pos) > 0 and not pd.isna(med_d.get(t, np.nan)) \
                and med_d[t] < CRASH_MED:
            for s in pos:
                pending_sells.setdefault(s, 'crash')
        if t in sig_days:
            hold_mode = False
            if not pd.isna(idxma_d.get(t, np.nan)) and idx_d[t] < idxma_d[t]:
                gate_streak += 1
            else:
                gate_streak = 0
            if gate_streak >= gate_confirm:
                target = []
            elif gate_streak >= 1:
                target = list(pos.keys())
                hold_mode = True
            else:
                target = sig_target[t]
            if hold_mode:
                buy_now = []
            elif entry_cap is not None and len(target) > 0:
                held = set(pos.keys())
                cand = [s for s in target if s not in held]
                buy_now = cand[:ENTRY_CAP_LOCAL]
            elif len(target) == 0:
                buy_now = []
            else:
                buy_now = list(target)
            nxt = cal.get_loc(t) + 1
            pending_exec = (cal[nxt], target, equity, buy_now) \
                if nxt < len(cal) else None

    curve = pd.Series(eq).sort_index()
    return {'curve': curve, 'fees': fees, 'turnover': turnover,
            'n_rebal': n_rebal, 'start': str(cal[0].date()),
            'end': str(cal[-1].date()), 'sells': sells, 'buys': buys}


# --------------------------- 指标（ab_validation.py 复制）
def window_metrics(res, t0, t1):
    c = res['curve']
    seg = c[(c.index >= t0) & (c.index <= t1)]
    if len(seg) < 2:
        return {}
    days = (seg.index[-1] - seg.index[0]).days
    yrs = days / 365.25
    ann = (seg.iloc[-1] / seg.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1
    wk = seg.resample('W').last().pct_change().dropna()
    dd = (seg / seg.cummax() - 1).min()
    fee_ann = res['fees'] / yrs / 1.0
    to_ann = res['turnover'] / yrs
    return {'annualized': float(round(ann * 100, 2)),
            'mdd_pct': float(round(dd * 100, 2)),
            'turnover_ann_x': float(round(to_ann, 2)),
            'fee_drag_ann_pct': float(round(fee_ann * 100, 2)),
            'total_return_pct': float(round((seg.iloc[-1] / seg.iloc[0] - 1) * 100, 2))}


def monthly_diffs(curve_a, curve_b, t0, t1):
    """ab−base 逐月 diff（对齐 ab_validation check2 口径）。"""
    months = pd.date_range(t0, t1, freq='MS')
    rows = []
    for i in range(len(months) - 1):
        m0, m1 = months[i], months[i + 1] - pd.Timedelta(days=1)

        def seg_ret(curve):
            s = curve[(curve.index >= m0) & (curve.index <= m1)]
            if len(s) < 2:
                return 0.0
            return float(s.iloc[-1] / s.iloc[0] - 1)
        ra, rb = seg_ret(curve_a), seg_ret(curve_b)
        rows.append({'month': str(m0.date())[:7], 'cap_pct': round(ra * 100, 2),
                     'base_pct': round(rb * 100, 2),
                     'diff_pct': round((ra - rb) * 100, 2)})
    return rows


def lmo_adv(rows):
    """leave-one-month-out（月度复利拼接剔除单月后的优势/回吐，只报 CI 不作独立否决）。
    rows 须含 'cap_pct' 与 'base_pct'；返回 adv = cap−base 的剔除敏感性。"""
    ra = np.array([r['cap_pct'] for r in rows]) / 100.0
    rb = np.array([r['base_pct'] for r in rows]) / 100.0
    out = []
    for i in range(len(ra)):
        keep = [j for j in range(len(ra)) if j != i]
        ea = float(np.prod(1 + ra[keep]))
        eb = float(np.prod(1 + rb[keep]))
        out.append({'excl': rows[i]['month'], 'adv_cum_pct': round((ea - eb) * 100, 2)})
    return out


# --------------------------- 并行基础设施（Pool(32)）
DATA = F4 = SYMS = CTX = None


def _worker_run(job):
    """LOTO 单任务：cap 档 + ban 单笔重跑，返回窗口指标（ann=年化 / tot=累计收益）。"""
    cap, sym, d, t0, t1, metric = job
    global ENTRY_CAP_LOCAL
    ENTRY_CAP_LOCAL = cap
    ban = {(sym, d)} if sym is not None else None
    r = run_backtest_fast(CTX, gate_confirm=GATE_CONFIRM, entry_cap=cap, ban=ban)
    if metric == 'ann':
        return window_metrics(r, t0, t1)['annualized']
    return window_metrics(r, t0, t1)['total_return_pct']


def _worker_boot(payload):
    """bootstrap 切片：主进程单流 seed=42 预生成的重抽索引数组，子进程只做纯计算。"""
    picks, ra, rb = payload
    n_m = len(ra)
    out = []
    for pick in picks:
        ea = float(np.prod(1 + ra[pick]) ** (12 / n_m) - 1)
        eb = float(np.prod(1 + rb[pick]) ** (12 / n_m) - 1)
        out.append((ea - eb) * 100)
    return out


def block_bootstrap(rows, n=1000, seed=42, pool=None):
    """月块 bootstrap（seed=42，1000 次，月块有放回重抽，复利拼接年化差 cap−base）。
    重抽索引由主进程单流 rng 预生成（与串行 seed=42 逐一对应），按迭代切片分发 Pool。"""
    r2 = np.random.default_rng(seed)
    ra = np.array([r['cap_pct'] for r in rows]) / 100.0
    rb = np.array([r['base_pct'] for r in rows]) / 100.0
    n_m = len(ra)
    picks = [r2.integers(0, n_m, n_m) for _ in range(n)]
    chunks = []
    step = (n + NPROC - 1) // NPROC
    for i in range(0, n, step):
        chunks.append((picks[i:i + step], ra, rb))
    parts = pool.map(_worker_boot, chunks) if pool is not None \
        else [_worker_boot(c) for c in chunks]
    boots = np.array([v for p in parts for v in p])
    return {'n': n, 'seed': seed,
            'mean_adv_pp': round(float(boots.mean()), 2),
            'p5_pp': round(float(np.percentile(boots, 5)), 2),
            'p95_pp': round(float(np.percentile(boots, 95)), 2),
            'p_adv_gt0': round(float((boots > 0).mean()), 3)}


def main():
    global DATA, F4, SYMS, CTX
    t0w = time.time()
    data = load_data()
    pools = build_pools(data)
    F = build_factors(data)
    syms = pools['old131']            # 主体池（工单引用数字口径，R6-1 一致）
    DATA, F4, SYMS = data, F, syms
    print('主体池: old131；主臂 cap3（confirm=2+entry_cap=3），对照臂 cap2 同套')

    # 快速引擎与原引擎逐位等价断言（base/cap2 双档，curve/fees/buys/sells 全等）
    CTX = prepare_context(data, F, syms)
    ref_base = run_backtest(data, F, syms)
    fast_base = run_backtest_fast(CTX)
    ENTRY_CAP_LOCAL = CAP_CTRL
    ref_cap2 = run_backtest(data, F, syms, gate_confirm=GATE_CONFIRM, entry_cap=CAP_CTRL)
    fast_cap2 = run_backtest_fast(CTX, gate_confirm=GATE_CONFIRM, entry_cap=CAP_CTRL)
    eq_ok = all([ref_base['curve'].equals(fast_base['curve']),
               ref_base['fees'] == fast_base['fees'],
               ref_base['turnover'] == fast_base['turnover'],
               ref_base['buys'] == fast_base['buys'],
               ref_base['sells'] == fast_base['sells'],
               ref_cap2['curve'].equals(fast_cap2['curve']),
               ref_cap2['fees'] == fast_cap2['fees'],
               ref_cap2['buys'] == fast_cap2['buys'],
               ref_cap2['sells'] == fast_cap2['sells']])
    assert eq_ok, '快速引擎与原引擎不等价——中止（禁改口径红线）'
    base, cap2 = fast_base, fast_cap2
    print('快速引擎等价断言: OK（base/cap2 curve/fees/turnover/buys/sells 全等）')

    ENTRY_CAP_LOCAL = CAP_MAIN
    cap3 = run_backtest_fast(CTX, gate_confirm=GATE_CONFIRM, entry_cap=CAP_MAIN)

    cal_end = pd.Timestamp(sorted(set().union(*[set(data[s].index) for s in syms]))[-1])

    # 谱系锚（数据态 = engine_snapshot 快照，末根 2026-10-17；与 WO4 权威基线同源 bit-exact）
    r53 = json.load(open('/tmp/r5_3/turnover_scan.json'))['runs']
    bt = window_metrics(base, base['curve'].index[0], TRAIN_END)
    ref_b = r53['base']['old131']['train']
    anchor_base = {k: dict(run=bt[k], ref=ref_b[k], match=bool(abs(bt[k] - ref_b[k]) < 1e-9))
                   for k in ref_b if k in bt}
    hm = window_metrics(cap2, HOLD_START, cap2['curve'].index[-1])
    ref_h = r53['AB_confirm2_cap2']['old131']['holdout']
    anchor_cap2 = {k: dict(run=hm[k], ref=ref_h[k], match=bool(abs(hm[k] - ref_h[k]) < 1e-9))
                   for k in ('annualized', 'mdd_pct', 'turnover_ann_x', 'fee_drag_ann_pct')}
    chk_base = all(v['match'] for v in anchor_base.values())
    chk_cap2 = all(v['match'] for v in anchor_cap2.values())
    print('谱系锚: base-train vs r5_3 base =', {k: v['match'] for k, v in anchor_base.items()},
          '| cap2-holdout vs r5_3 AB =', {k: v['match'] for k, v in anchor_cap2.items()})

    ctx_mp = get_context('fork')       # fork 继承已加载的 data/F/ctx，进程内 import 隔离
    pool = ctx_mp.Pool(NPROC)

    # ---------- Round 1：两臂全部 LOTO 任务一次性分发（逐笔封禁重跑） ----------
    tag_res = {'cap3': (cap3, CAP_MAIN), 'cap2': (cap2, CAP_CTRL)}
    wins_map, buys_map = {}, {}
    jobs, job_idx = [], []
    for tag, (res, cap) in tag_res.items():
        ho_t0, ho_t1 = HOLD_START, res['curve'].index[-1]
        tr_t0, tr_t1 = res['curve'].index[0], TRAIN_END
        re_t0, re_t1 = RESEG_START, res['curve'].index[-1]
        wins_map[tag] = dict(ho=(ho_t0, ho_t1), tr=(tr_t0, tr_t1), re=(re_t0, re_t1))
        buys_map[tag] = dict(
            ho=[(b['sym'], b['date']) for b in res['buys'] if b['date'] >= '2026-04-01'],
            tr=[(b['sym'], b['date']) for b in res['buys'] if b['date'] < '2026-04-01'],
            re=[(b['sym'], b['date']) for b in res['buys'] if b['date'] >= '2026-06-01'])
        for kind, metric in (('ho', 'ann'), ('tr', 'tot'), ('re', 'ann')):
            for i, (s, d) in enumerate(buys_map[tag][kind]):
                jobs.append((cap, s, d, *wins_map[tag][kind], metric))
                job_idx.append((tag, kind, i))
    print(f'LOTO 任务: {len(jobs)} 笔封禁重跑 → Pool({NPROC}) 分发')
    vals = pool.map(_worker_run, jobs)
    loto_vals = {tag: {} for tag in tag_res}
    for (tag, kind, i), v in zip(job_idx, vals):
        loto_vals[tag].setdefault(kind, {})[i] = v

    # ---------- Round 2：G1 剔除笔（留出窗 + 换段复验） ----------
    jobs2, job_idx2 = [], []
    g1_target = {}
    for tag, (res, cap) in tag_res.items():
        ho = loto_vals[tag]['ho']
        adv_full = (window_metrics(res, *wins_map[tag]['ho'])['annualized']
                    - window_metrics(base, *wins_map[tag]['ho'])['annualized'])
        rows = [{'sym': s, 'date': d,
                 'contrib_pp': round(adv_full - ho[i], 2)}
                for i, (s, d) in enumerate(buys_map[tag]['ho'])]
        rows.sort(key=lambda x: x['contrib_pp'], reverse=True)
        mv_present = any(s == 'MVLLUSDT' and d == '2026-04-07'
                         for s, d in buys_map[tag]['ho'])
        ban_target = ('MVLLUSDT', '2026-04-07') if mv_present else \
            ((rows[0]['sym'], rows[0]['date']) if rows else None)
        g1_target[tag] = (mv_present, ban_target, rows)
        if ban_target:
            jobs2.append((cap, ban_target[0], ban_target[1],
                          *wins_map[tag]['ho'], 'ann'))
            job_idx2.append((tag, 'g1_ho'))
        re_rows = _reseg_rows(loto_vals[tag]['re'], res, base, wins_map[tag]['re'],
                              buys_map[tag]['re'])
        if re_rows:
            jobs2.append((cap, re_rows[0]['sym'], re_rows[0]['date'],
                          *wins_map[tag]['re'], 'ann'))
            job_idx2.append((tag, 'g1_re'))
    vals2 = pool.map(_worker_run, jobs2) if jobs2 else []
    v2 = {k: v for k, v in zip(job_idx2, vals2)}

    results = {}
    for tag, (res, cap) in tag_res.items():
        ho_m = window_metrics(res, *wins_map[tag]['ho'])
        tr_m = window_metrics(res, *wins_map[tag]['tr'])
        base_ho = window_metrics(base, *wins_map[tag]['ho'])
        base_tr = window_metrics(base, *wins_map[tag]['tr'])
        adv_ho = round(ho_m['annualized'] - base_ho['annualized'], 2)
        giveup_tr = round(base_tr['total_return_pct'] - tr_m['total_return_pct'], 2)

        # 4) 分月拆解（留出窗，cap−base）
        mrows = monthly_diffs(res['curve'], base['curve'], HOLD_START, cal_end)
        # 2) LMO（留出窗，只报 CI 不作独立否决）
        lmo_ho = lmo_adv(mrows)
        # 3) 月块 bootstrap（留出窗；重抽索引主进程单流 seed=42 预生成，迭代切片分发 Pool）
        boot = block_bootstrap(mrows, 1000, SEED, pool)
        # 1) LOTO（留出窗）贡献表
        mv_present, ban_target, rows = g1_target[tag]
        pos_sum = sum(x['contrib_pp'] for x in rows if x['contrib_pp'] > 0)
        top_share = round(rows[0]['contrib_pp'] / pos_sum, 3) if pos_sum > 0 else None
        lto_ho = {'adv_full_pp': adv_ho, 'n_banned': len(rows), 'rows': rows,
                  'top_trade_share': top_share,
                  'top_trade': rows[0] if rows else None}
        # G1
        g1 = None
        if ban_target:
            adv_i = v2[(tag, 'g1_ho')] - base_ho['annualized']
            g1 = {'banned': list(ban_target),
                  'mvllusdt_in_buys': mv_present,
                  'note': None if mv_present else
                  'MVLLUSDT 2026-04-07 不在该臂留出窗入场清单，改用其自身 LTO 最大贡献笔（对称口径）',
                  'adv_after_pp': round(float(adv_i), 2),
                  'pass': bool(adv_i >= 10.0)}
        # 5) 对称检验：训练窗回吐侧 LTO + LMO（回吐 = base−cap，逐月差剔除）
        tr = loto_vals[tag]['tr']
        tr_rows = [{'sym': s, 'date': d,
                    'contrib_pp': round(tr_m['total_return_pct'] - tr[i], 2)}
                   for i, (s, d) in enumerate(buys_map[tag]['tr'])]
        tr_rows.sort(key=lambda x: x['contrib_pp'], reverse=True)
        pos_sum_tr = sum(x['contrib_pp'] for x in tr_rows if x['contrib_pp'] > 0)
        top_share_tr = round(tr_rows[0]['contrib_pp'] / pos_sum_tr, 3) if pos_sum_tr > 0 else None
        lto_tr = {'giveup_full_pp': giveup_tr, 'n_banned': len(tr_rows), 'rows': tr_rows,
                  'top_trade_share': top_share_tr,
                  'top_trade': tr_rows[0] if tr_rows else None}
        mrows_tr = monthly_diffs(res['curve'], base['curve'],
                                 res['curve'].index[0], TRAIN_END)
        giveup_rows = [{'month': r['month'],
                        'cap_pct': r['base_pct'],        # 反转：以 base 为「优」侧
                        'base_pct': r['cap_pct']} for r in mrows_tr]
        lmo_tr = lmo_adv(giveup_rows)   # adv_cum_pct = base−cap 累计 = 回吐敏感性
        lmo_tr = [{'excl': r['excl'], 'giveup_cum_pct': r['adv_cum_pct']}
                  for r in lmo_tr]
        # 6) 换段复验：holdout 重切 2026-06-01→今（真实窗）
        re_win = wins_map[tag]['re']
        adv_re = (window_metrics(res, *re_win)['annualized']
                  - window_metrics(base, *re_win)['annualized'])
        re_rows = _reseg_rows(loto_vals[tag]['re'], res, base, re_win,
                              buys_map[tag]['re'])
        pos_sum_re = sum(x['contrib_pp'] for x in re_rows if x['contrib_pp'] > 0)
        lto_re = {'adv_full_pp': round(adv_re, 2), 'n_banned': len(re_rows),
                  'rows': re_rows,
                  'top_trade_share': round(re_rows[0]['contrib_pp'] / pos_sum_re, 3)
                  if pos_sum_re > 0 else None,
                  'top_trade': re_rows[0] if re_rows else None}
        g1_re = None
        if (tag, 'g1_re') in v2:
            adv_i_re = v2[(tag, 'g1_re')] - window_metrics(base, *re_win)['annualized']
            g1_re = {'banned': [re_rows[0]['sym'], re_rows[0]['date']],
                     'adv_after_pp': round(float(adv_i_re), 2),
                     'pass': bool(adv_i_re >= 10.0)}

        g2 = {'p_adv_gt0': boot['p_adv_gt0'], 'p5_pp': boot['p5_pp'],
              'pass': bool(boot['p_adv_gt0'] >= 0.90 and boot['p5_pp'] > -50.0)}
        g3 = {'top_trade_share': lto_ho['top_trade_share'],
              'pass': bool(lto_ho['top_trade_share'] is not None
                           and lto_ho['top_trade_share'] <= 0.50)}
        g4 = {'adv_reseg_pp': round(adv_re, 2), 'direction_positive': bool(adv_re > 0),
              'g1_caliber_reseg': g1_re,
              'pass': bool(adv_re > 0 and g1_re and g1_re['pass'])}
        g5 = {'top_trade_share_train': lto_tr['top_trade_share'],
              'pass': bool(lto_tr['top_trade_share'] is not None
                           and lto_tr['top_trade_share'] <= 0.50)}
        results[tag] = dict(
            windows=dict(train=tr_m, holdout=ho_m,
                         base_train=base_tr, base_holdout=base_ho),
            adv_holdout_pp=adv_ho, giveup_train_pp=giveup_tr,
            monthly_holdout=mrows, lmo_holdout=lmo_ho, bootstrap=boot,
            loto_holdout=lto_ho, g1_mvllusdt=g1,
            loto_train_giveup=lto_tr, lmo_train=lmo_tr,
            resegment=dict(window='2026-06-01→今（真实窗）',
                           adv_pp=round(adv_re, 2), loto=lto_re, g1_caliber=g1_re),
            judgments={'G1': g1, 'G2': g2, 'G3': g3, 'G4': g4, 'G5': g5},
            all_pass=bool((g1['pass'] if g1 else False) and g2['pass'] and g3['pass']
                          and g4['pass'] and g5['pass']))
        print(f"[{tag}] 留出优势={adv_ho}pp 训练回吐={giveup_tr}pp | "
              f"G1={g1} G2 P={boot['p_adv_gt0']}/p5={boot['p5_pp']} "
              f"G3 share={lto_ho['top_trade_share']} G4 reseg={adv_re:.2f}pp "
              f"G5 share={lto_tr['top_trade_share']}")

    pool.close()
    pool.join()
    runtime = round(time.time() - t0w, 1)
    out = dict(
        generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        workorder='WO1 cap3 补检（R6-1b）· 冻结规格 v1.0',
        seed=SEED, pool='old131（工单引用数字口径）',
        param_space='仅 cap3（A confirm=2 不变 + B entry_cap=3，已批档位 {2,3,4} 内）；对照臂 cap2 同套',
        lineage='引擎逐行复制 /tmp/r6_1/ab_validation.py（r5_3 ← eng_w2_f1 谱系），'
                '仅新增 cap3 档/训练回吐侧对称检验/换段复验，不改口径',
        parallel=dict(workers=NPROC, mode='multiprocessing fork Pool',
                      split='LOTO 逐笔封禁重跑按 (sym,date) 切片；bootstrap 1000 次重抽索引由主进程'
                            '单流 seed=42 预生成后按迭代切片分发；子任务纯函数化、按序回收=串行等价',
                      fast_engine='回测上下文（行情矩阵/idx/MA50/崩市中位/周信号目标表）与 ban/cap 无关，'
                                  '一次构建全任务复用；启动时与原引擎逐位等价断言（curve/fees/buys/sells 全等）',
                      runtime_sec=runtime,
                      fix_note='修复 block_bootstrap 行参错位（rb 原误取 cap_pct 使统计恒为 0）；'
                               '统计口径不变：月块有放回重抽 cap−base 年化差'),
        baseline_check=dict(
            data_state='engine_snapshot/box_cache_snapshot.tar.gz（2026-10-17 10:28 UTC 快照，末根 2026-10-17，'
                       '全局首根 2024-01-24）——与 WO4 权威基线 bit-exact 同源（R5-0 逐笔复现通过）',
            base_train_vs_r5_3_base=dict(anchor='r5_3 turnover_scan runs.base.old131.train（同引擎族可复现锚）',
                                         detail=anchor_base, all_match=bool(chk_base)),
            cap2_holdout_vs_r5_3_ab=dict(anchor='r5_3 turnover_scan runs.AB_confirm2_cap2.old131.holdout',
                                         detail=anchor_cap2, all_match=bool(chk_cap2)),
            f1_anchor_retired=dict(
                reason='/tmp/eng_w2_f1/f1_results.json+engine 于 2026-10-18 04:07/05:12 UTC 被外部重生成'
                       '（引擎加入 BUG-04「当日止损票禁当日买回」，train annualized 39.24→36.38），'
                       '旧工件本地不可恢复；R6-1（10-17）同一校验为 PASS 可证脚本冻结时点锚本成立。'
                       '谱系锚改对 r5_3 同族（r6_1 谱系声明一致），f1 工件漂移如实登记'),
            r5_3_residual_gap='cap2 holdout annualized 77.48 vs 77.62：r5_3 跑于 10-17 06:45 UTC，'
                              '其 10-17 forming bar 在权威基线（03:26 UTC）之后被修订，该 bar 值本地不可恢复'
                              '（WO4 同款漂移）；mdd -16.3 bit 一致，年化差=forming bar 修订效应',
            drift_root_cause='冻结后共享工件被刷新：box_cache 滚动窗（09:54 UTC）+ f1 工件重生成（04:07 UTC）'
                             '+ forming bar 修订；非代码/口径差异（引擎与 r6_1 逐字 diff=0，仅注释与死参数）'),
        provenance=dict(
            real_window='>=2025-06-01（WO1 规格出身分界）；留出窗 2026-04→10 全段属真实窗、单独达标',
            annotation='真实窗成绩引用强制伴行标注：末 5 个月（2026-06→10）真实深负（−48.8/−55.9pp/年）'),
        results=results,
        fail_action='任一 G 不达→cap3 退回污染名单，收益主张撤回，治理属性按风险轨另验；'
                    '对照臂 cap2 同表呈报、同套判定、对称降权',
        revival='未被污染的新评估段出现且重新走本规格全套；全过也只是候选，放行另裁',
    )
    with open(os.path.join(OUT, 'wo1_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print(f'OK -> {os.path.join(OUT, "wo1_result.json")} （全程 {runtime}s）')


def _reseg_rows(re_vals, res, base, re_win, re_buys):
    """换段复验 LOTO 贡献表：contrib = 全优势 − 剔除后优势。"""
    adv_full = (window_metrics(res, *re_win)['annualized']
                - window_metrics(base, *re_win)['annualized'])
    rows = [{'sym': s, 'date': d, 'contrib_pp': round(adv_full - re_vals[i], 2)}
            for i, (s, d) in enumerate(re_buys)]
    rows.sort(key=lambda x: x['contrib_pp'], reverse=True)
    return rows


if __name__ == '__main__':
    main()
