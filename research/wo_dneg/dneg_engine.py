#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DNEG 仪表化引擎（工单 DNEG · 2026-10-18）
================================================================
- 逐行复制 /workspace/repo_ready/engine_f1/f1_backtest_v2.py 的 run_backtest
  （W2-R14-G4 升版，含 BUG-04 语义），仅加记录不改逻辑：
  · 逐笔流水（trade ledger）：open/close 价、日期、qty、止损价、跳空损耗、
    exit_reason（stop/rebal/crash/eow）、分摊费用（入场费/出场费/资金费）
  · 逐日逐票 PnL 三分量：price_pnl（毛）/ fee / funding（净=三者代数和）
  · 逐日持仓快照（D0 对拍用）
- 数据态：/tmp/dneg/box_cache（engine_snapshot 快照解包，与 /tmp/box_cache
  逐文件 md5 一致=零漂移，已核 176/176）
- 反事实开关（仅供 D4，跑过即烧窗）：stop=None（无止损）/stop=-0.12/
  trailing（12% 收盘价跟踪）/rebal_every_weeks=2（双周档）/target_fn（D3 随机带）
- 判定预注册（D4-H-D，开工即冻结、禁跑后换）：T2 状态变量取「池等权 20 日
  已实现波动率」（弃「资金费 60 日分位」，因后段仅 5.5 个月不足 60 日分位稳估）；
  阈值=realA 段该序列 80 分位（仅用 realA 数据估计）；OFF=vol20>阈值；
  后段 OFF 命中率 = OFF 日中 F1 净日收益<0 占比 ≥80%；realA 误伤率 =
  realA OFF 日占比 ≤20%。
"""
import json
import os

import numpy as np
import pandas as pd

SEED = 42
TOP_N = 5
SLOT = 0.10
STOP = -0.08
CRASH_MED = -0.05
FEE_SIDE = 0.0005
FUNDING = 0.0003
MA_REG = 50
TRAIN_END = pd.Timestamp('2026-03-31')
HOLD_START = pd.Timestamp('2026-04-01')
REALA_START = pd.Timestamp('2025-06-02')
REALB_END = pd.Timestamp('2026-05-31')
REALC_START = pd.Timestamp('2026-06-01')
FACTORS_4 = ['ma20_slope', 'obv_slope20', 'dist_52w_high', 'mom_1m']
FACTORS_3 = ['ma20_slope', 'dist_52w_high', 'mom_1m']

CACHE = '/tmp/dneg/box_cache'


# ---------------------------------------------------------------- 数据与池（=v2 逐行）
def load_data(cache=CACHE):
    data = {}
    for fn in sorted(os.listdir(cache)):
        sym = fn[:-5]
        df = pd.DataFrame(json.load(open(os.path.join(cache, fn))))
        df['time'] = pd.to_datetime(df['time'])
        df = df.set_index('time').sort_index()
        data[sym] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return data


def build_pools(data):
    old = sorted(s for s, d in data.items()
                 if d.index[0] <= pd.Timestamp('2025-03-31'))
    full = sorted(s for s, d in data.items() if len(d) >= 100)
    assert len(old) == 131, f'老票池={len(old)} != 131'
    assert len(full) == 144, f'全池={len(full)} != 144'
    return {'old131': old, 'full144': full}


# ---------------------------------------------------------------- 因子（=v2 逐行）
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


# ---------------------------------------------------------------- 仪表化引擎
def run_instr(data, F=None, syms=None, gated=False, factors=FACTORS_4,
              stop=STOP, trail=None, target_fn=None, rebal_every_weeks=1,
              record=True, rng_seed=SEED):
    """逐行复制 v2 run_backtest；仅加记录与 D4 反事实开关。
    stop=None → 无止损臂；trail=x → 12%x 收盘跟踪止损；target_fn(rng)->list[str]
    → D3 随机带（同费同闸口径， ungated 下 target 由 rng 决定）；
    rebal_every_weeks=2 → 双周档（ISO 周序号隔周信号）。
    """
    syms = syms if syms is not None else sorted(data)
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
    wk_groups = cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values()
    sig_days = set(wk_groups.values) if rebal_every_weeks == 1 else \
        set(wk_groups.values[::rebal_every_weeks])

    cash, pos = 1.0, {}
    pending_sells = set()
    pending_reason = {}          # sym -> 'crash'|'rebal'（v2 集合语义不变，仅记因）
    pending_exec = None
    eq, hold = {}, {}
    fees = turnover = 0.0
    n_rebal = 0
    stopped_today = set()

    # ---- 仅记录用状态（不改任何逻辑分支）----
    trades = {}                  # tid -> dict(sym, open_date, open_px, qty, stop_px, ...)
    tid_seq = [0]
    last_mark = {}               # sym -> 上次计价
    tid_of = {}                  # sym -> tid
    day_rows = []                # (t, sym, tid, price_pnl, fee, funding, event, gap)
    rng = np.random.default_rng(rng_seed)

    def rec_open(s, t, px, qty):
        tid = tid_seq[0]; tid_seq[0] += 1
        trades[tid] = {'sym': s, 'open_date': str(t.date()), 'open_px': float(px),
                       'qty': float(qty), 'stop_px': float(px * (1 + stop)) if stop is not None else None,
                       'entry_fee': float(qty * px * FEE_SIDE), 'exit_fee': 0.0,
                       'funding': 0.0, 'price_pnl': 0.0, 'gap_loss': 0.0,
                       'close_date': None, 'exit_px': None, 'exit_reason': None,
                       'stop_type': None, 'trail_px': None}
        tid_of[s] = tid
        day_rows.append((t, s, tid, 0.0, float(qty * px * FEE_SIDE), 0.0, 'open', 0.0))

    def rec_close(s, t, px, kind, q):
        tid = tid_of[s]
        tr = trades[tid]
        tr['close_date'] = str(t.date()); tr['exit_px'] = float(px)
        tr['exit_reason'] = kind
        tr['exit_fee'] = float(q * px * FEE_SIDE)
        day_rows.append((t, s, tid, float(q * px - q * last_mark[s]),
                         float(q * px * FEE_SIDE), 0.0, 'close:' + kind, 0.0))

    for t in cal:
        o_t, lo_t, c_t = open_.loc[t], low.loc[t], close.loc[t]
        stopped_today = set()
        # 1) 盘中断价止损（V2：跳空按开盘，否则按止损价；trail 臂改阈价来源，触发结构同构）
        for s in list(pos):
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            if trail is not None:
                stop_p = pos[s]['trail'] * (1 + trail)
            else:
                stop_p = pos[s]['entry'] * (1 + stop) if stop is not None else None
            if stop_p is None:
                continue
            if o_t[s] <= stop_p:
                px = o_t[s]
            elif lo_t[s] <= stop_p:
                px = stop_p
            else:
                continue
            q = pos[s]['qty']
            cash += q * px * (1 - FEE_SIDE)
            fees += q * px * FEE_SIDE
            turnover += q * px
            stopped_today.add(s)
            if record:
                tid = tid_of[s]
                if trail is not None:
                    trades[tid]['trail_px'] = float(stop_p)
                    trades[tid]['stop_type'] = 'trail'
                trades[tid]['gap_loss'] = float(q * (stop_p - o_t[s])) if o_t[s] < stop_p else 0.0
                if stop is not None and trail is None:
                    trades[tid]['stop_type'] = 'gap' if o_t[s] < stop_p else 'intraday'
                rec_close(s, t, px, 'stop', q)
            del pos[s]
        # 2) 止损/崩市挂出的清仓单：当根有K线则开盘卖出
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                q = pos[s]['qty']
                cash += q * px * (1 - FEE_SIDE)
                fees += q * px * FEE_SIDE
                turnover += q * px
                if record:
                    rec_close(s, t, px, pending_reason.get(s, 'crash'), q)
                del pos[s]
            pending_sells.discard(s)
            pending_reason.pop(s, None)
        # 3) 周调仓执行（信号次日开盘）
        if pending_exec is not None and t == pending_exec[0]:
            _, target, eq_sig = pending_exec
            pending_exec = None
            n_rebal += 1
            for s in list(pos):
                if s in target or s in pending_sells:
                    continue
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    pending_sells.add(s)
                    pending_reason[s] = 'rebal'
                    continue
                q = pos[s]['qty']
                cash += q * px * (1 - FEE_SIDE)
                fees += q * px * FEE_SIDE
                turnover += q * px
                if record:
                    rec_close(s, t, px, 'rebal', q)
                del pos[s]
            for s in target:
                if s in pos or s in stopped_today:
                    continue
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
                pos[s] = {'qty': qty, 'entry': px,
                          'trail': px if trail is not None else None}
                last_mark[s] = float(px)
                if record:
                    rec_open(s, t, px, qty)
        # 4) 收盘记账 + 资金费 0.03%/bar 按持仓名义
        equity = cash
        for s, p in pos.items():
            m = mark.at[t, s]
            equity += p['qty'] * m
            f = p['qty'] * m * FUNDING
            cash -= f
            fees += f
            if trail is not None and not pd.isna(c_t[s]):
                pos[s]['trail'] = max(pos[s]['trail'], float(c_t[s]))
            if record:
                tid = tid_of[s]
                trades[tid]['funding'] -= float(f)
                trades[tid]['price_pnl'] += float(p['qty'] * (m - last_mark[s]))
                day_rows.append((t, s, tid, float(p['qty'] * (m - last_mark[s])),
                                 0.0, -float(f), None, 0.0))
            last_mark[s] = m
        eq[t] = equity
        hold[t] = ','.join(sorted(pos))
        # 5) 崩市检查（信号日崩市则当周直接空仓）
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                and med_ret[t] < CRASH_MED:
            for s in pos:
                pending_reason.setdefault(s, 'crash')
            pending_sells.update(pos.keys())
        # 6) 周信号：算分、闸门、定目标
        if t in sig_days:
            if target_fn is not None:
                target = list(target_fn(rng, syms))
            else:
                score = cross_scores(F, syms, t, factors)
                if gated and not pd.isna(idx_ma.get(t, np.nan)) and idx[t] < idx_ma[t]:
                    target = []
                else:
                    target = list(score.index[:TOP_N])
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity) \
                if cal.get_loc(t) + 1 < len(cal) else None

    curve = pd.Series(eq).sort_index()
    if record:
        # 窗口末仍持仓 → eow 伪平仓（按末根 mark 计价，仅记录不改动权益）
        end = cal[-1]
        for s, p in pos.items():
            tid = tid_of[s]
            tr = trades[tid]
            tr['close_date'] = str(end.date())
            tr['exit_px'] = float(mark.at[end, s])
            tr['exit_reason'] = 'eow'
        return {'curve': curve, 'holdings': pd.Series(hold).sort_index(),
                'fees': fees, 'turnover': turnover, 'n_rebal': n_rebal,
                'start': str(cal[0].date()), 'end': str(cal[-1].date()),
                'n_sig': len(sig_days), 'trades': trades, 'day_rows': day_rows,
                'idx': idx, 'med_ret': med_ret}
    return {'curve': curve, 'fees': fees, 'turnover': turnover,
            'n_rebal': n_rebal, 'start': str(cal[0].date()),
            'end': str(cal[-1].date()), 'n_sig': len(sig_days)}


# ---------------------------------------------------------------- 指标（=v2 逐行）
def window_metrics(res, t0, t1):
    c = res['curve']
    seg = c[(c.index >= t0) & (c.index <= t1)]
    if len(seg) < 2:
        return {}
    days = (seg.index[-1] - seg.index[0]).days
    yrs = days / 365.25
    ann = (seg.iloc[-1] / seg.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1
    wk = seg.resample('W').last().pct_change().dropna()
    cash_wk = wk[wk.round(10) == 0]
    act = wk[wk.round(10) != 0]
    dd = (seg / seg.cummax() - 1).min()
    fee_ann = res['fees'] / yrs / 1.0
    to_ann = res['turnover'] / yrs
    return {'annualized': round(ann * 100, 2),
            'median_weekly_pct': round(wk.median() * 100, 3),
            'weekly_winrate_pct': round((wk > 0).mean() * 100, 2),
            'weekly_winrate_active_pct': round((act > 0).mean() * 100, 2),
            'cash_weeks': int(len(cash_wk)),
            'mdd_pct': round(dd * 100, 2),
            'turnover_ann_x': round(to_ann, 2),
            'fee_drag_ann_pct': round(fee_ann * 100, 2),
            'total_return_pct': round((seg.iloc[-1] / seg.iloc[0] - 1) * 100, 2),
            'n_weeks': int(len(wk))}
