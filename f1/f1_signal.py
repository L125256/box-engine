#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R11' 工单 · F1 信号引擎（f1_signal.py）— F1 base 裸奔四因子带闸版 上线运营引擎
================================================================================
seed=42 一次成活；改参数=新工单，禁止调参重跑。

口径（与 /tmp/eng_w2_f1/f1_backtest.py 同源，v1 锁定）：
- 池：cleaned_pool.json kept 144 标的（权威清洗池）；idx = 池内当日有K线标的等权收盘均价
- 因子：ma20_slope / obv_slope20 / dist_52w_high / mom_1m，横截面 z-score(|z|<=3) 等权合成
- 周调仓：每周首个交易日（多为周一）收盘出信号，次日开盘成交；top-5 等权
- regime 闸：idx < MA50 清仓持币；止损 −8% 硬截断（V2 可实现口径）；崩市（池单日中位跌幅<−5%）清仓
- 费：滑点 0.05%/边 + 资金费 0.03%/bar（持仓名义）
- 仓位档位：起步 12.5%（单票 2.5%）；CB1/CB费线 触发降一档（2.5→1.5→1.0→0.5%/票）

熔断器（R11' 上线方案）：
- CB1  MDD−32%/20交易日：滚动 20 交易日窗口内净账 MDD ≤ −32% → 降一档
- CB2  滚动60日止损失血：毛账滚动 60 交易日止损单合计亏损 ≤ −20pp 触发（黄灯），
       净账确认（同期净账亏损 ≤ −20pp）→ 红灯，动作=冻结开新仓 20 交易日（首月暂定）
- CB3  频次外移观察线：滚动 60 交易日止损次数 ≥ 基准(60日1次)×3 → 黄灯观察（外移观察线，不动作）
- 费线 21.7pp×2月：滚动 60 交易日费用年化拖累 ≥ 21.7pp → 降一档；≥50%线(10.85pp)黄灯

三本账（月报）：
- 毛账：不含任何费用的策略收益
- 费账：滑点+资金费逐月合计与年化拖累
- 让渡账：池等权买入持有收益 − 策略毛账收益（正值=策略让渡给市场的机会成本）

用法：
  python3 f1_signal.py live  [--out /workspace/f1_web/f1_live.json]   # 每日生成信号+熔断+月报
  python3 f1_signal.py replay [--slot 0.10] [--holdings-out FILE]     # 历史回放（G4 对账用）
复现：PYTHONHASHSEED=42 python3 f1_signal.py live（数据 /tmp/box_cache/*.json，刷缓存用 /tmp/wtc/refresh_cache.py）
"""
import json
import os
import sys
import hashlib

import numpy as np
import pandas as pd

SEED = 42
np.random.seed(SEED)

CACHE = '/tmp/box_cache'
CLEANED_POOL = '/tmp/eng_wt/cleaned_pool.json'

TOP_N = 5
SLOTS = [0.025, 0.015, 0.010, 0.005]   # 仓位档位表（单票），起步档=0.025 → 12.5% 敞口
KEEP_RANK = 15
STOP = -0.08
CRASH_MED = -0.05
FEE_SIDE = 0.0005
FUNDING = 0.0003
MA_REG = 50

CB1_MDD = -0.32          # CB1：滚动窗口 MDD 线
CB1_WINDOW = 20          # CB1：20 交易日
CB2_LOSS = -0.20         # CB2：止损失血线（毛账触发/净账确认）
CB2_WINDOW = 60          # CB2：滚动 60 交易日
CB2_FREEZE_DAYS = 20     # CB2 动作：冻结开新仓 20 交易日（首月暂定）
CB3_BASE_60D = 1.0       # CB3：回放基准 60 日止损次数（G4 回放统计后锁定）
CB3_MULT = 3             # CB3：观察线 = 基准×3
FEE_LINE_ANN = 0.217     # 费线：年化费拖累 21.7pp
FEE_WINDOW = 60          # 费线：滚动 60 交易日（≈2月）

FACTORS = ['ma20_slope', 'obv_slope20', 'dist_52w_high', 'mom_1m']


# ---------------------------------------------------------------- 数据与池
def load_data(cache=CACHE):
    data = {}
    for fn in sorted(os.listdir(cache)):
        if not fn.endswith('.json'):
            continue
        sym = fn[:-5]
        df = pd.DataFrame(json.load(open(os.path.join(cache, fn))))
        df['time'] = pd.to_datetime(df['time'])
        df = df.set_index('time').sort_index()
        data[sym] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return data


def build_pool(data):
    """权威池 = cleaned_pool kept 144（缺失缓存的标的自动剔除）。"""
    pool = [x['tkr'] for x in json.load(open(CLEANED_POOL))['kept']]
    syms = sorted(s for s in pool if s in data and len(data[s]) >= 100)
    assert len(syms) == 144, f'权威池={len(syms)} != 144'
    return syms


# ---------------------------------------------------------------- 因子（与 f1_backtest 同源）
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


def cross_scores(F, syms, dt, factors=FACTORS):
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


def week_first_days(cal):
    iso = cal.isocalendar()
    return set(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first())


# ---------------------------------------------------------------- 回放（双账本，同源逻辑）
def replay(data, F, syms, slot=0.025):
    """历史回放：净账（含费）+ 毛账（零费）双轨；逐日持仓/权益/费用/止损事件。
    逻辑与 f1_backtest.run_backtest（gated 四因子）逐行同源，v1 锁定。"""
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: data[s]['open'] for s in syms})
    low = pd.DataFrame({s: data[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close, open_, low = (x.reindex(cal) for x in (close, open_, low))
    mark = close.ffill()
    idx = close.mean(axis=1)
    idx_ma = idx.rolling(MA_REG).mean()
    med_ret = close.pct_change().median(axis=1)
    sig_days = week_first_days(cal)

    def one_pass(with_fees):
        cash, pos = 1.0, {}
        pending_sells, pending_exec = set(), None
        eq, fees_d, stops = {}, {}, []
        for t in cal:
            o_t, lo_t, c_t = open_.loc[t], low.loc[t], close.loc[t]
            for s in list(pos):                                   # 1) 盘中断价止损
                if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                    continue
                stop_p = pos[s]['entry'] * (1 + STOP)
                if o_t[s] <= stop_p:
                    px = o_t[s]
                elif lo_t[s] <= stop_p:
                    px = stop_p
                else:
                    continue
                fee = pos[s]['qty'] * px * FEE_SIDE if with_fees else 0.0
                cash += pos[s]['qty'] * px - fee
                if with_fees:
                    stops.append({'date': str(t.date()), 'sym': s, 'px': round(px, 6),
                                  'pnl_pct': round(px / pos[s]['entry'] - 1, 6),
                                  'slot': slot,
                                  'kind': 'stop_gap' if o_t[s] <= stop_p else 'stop_touch'})
                del pos[s]
            for s in list(pending_sells):                         # 2) 挂单清仓
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    continue
                if s in pos:
                    fee = pos[s]['qty'] * px * FEE_SIDE if with_fees else 0.0
                    cash += pos[s]['qty'] * px - fee
                    del pos[s]
                pending_sells.discard(s)
            if pending_exec is not None and t == pending_exec[0]:  # 3) 周调仓执行
                _, target, eq_sig = pending_exec
                pending_exec = None
                for s in list(pos):
                    if s in target or s in pending_sells:
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        pending_sells.add(s)
                        continue
                    fee = pos[s]['qty'] * px * FEE_SIDE if with_fees else 0.0
                    cash += pos[s]['qty'] * px - fee
                    del pos[s]
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
                    fee = qty * px * FEE_SIDE if with_fees else 0.0
                    cash -= qty * px + fee
                    pos[s] = {'qty': qty, 'entry': px}
            equity = cash                                          # 4) 收盘记账
            f_bar = 0.0
            for s, p in pos.items():
                m = mark.at[t, s]
                equity += p['qty'] * m
                if with_fees:
                    f_bar = p['qty'] * m * FUNDING
                    cash -= f_bar
            eq[t] = equity
            fees_d[t] = f_bar
            if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                    and med_ret[t] < CRASH_MED:                    # 5) 崩市清仓
                pending_sells.update(pos.keys())
            if t in sig_days:                                      # 6) 周信号
                score = cross_scores(F, syms, t)
                if not pd.isna(idx_ma.get(t, np.nan)) and idx[t] < idx_ma[t]:
                    target = []
                else:
                    target = list(score.index[:TOP_N])
                pending_exec = (cal[cal.get_loc(t) + 1], target, equity) \
                    if cal.get_loc(t) + 1 < len(cal) else None
        return pd.Series(eq).sort_index(), pd.Series(fees_d).sort_index(), stops

    eq_n, fees_n, stops_n = one_pass(True)
    eq_g, _, _ = one_pass(False)
    holdings = {}          # 逐日持仓（净账轨=毛账轨，决策一致）
    # 重跑轻量一遍只为持仓记录：改用净账轨在循环内记录会更贵，这里以独立快照循环实现
    hold = _replay_holdings(data, F, syms, slot)
    return {'cal': cal, 'idx': idx, 'idx_ma': idx_ma, 'med_ret': med_ret,
            'eq_net': eq_n, 'eq_gross': eq_g, 'fees': fees_n,
            'stops': stops_n, 'holdings': hold}


def _replay_holdings(data, F, syms, slot=0.025):
    """逐日持仓集合（与回放同源，仅记录 pos.keys()）。"""
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: data[s]['open'] for s in syms})
    low = pd.DataFrame({s: data[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close, open_, low = (x.reindex(cal) for x in (close, open_, low))
    mark = close.ffill()
    idx = close.mean(axis=1)
    idx_ma = idx.rolling(MA_REG).mean()
    med_ret = close.pct_change().median(axis=1)
    sig_days = week_first_days(cal)
    cash, pos = 1.0, {}
    pending_sells, pending_exec = set(), None
    hold = {}
    for t in cal:
        o_t, lo_t = open_.loc[t], low.loc[t]
        for s in list(pos):
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            stop_p = pos[s]['entry'] * (1 + STOP)
            if o_t[s] <= stop_p or lo_t[s] <= stop_p:
                cash += pos[s]['qty'] * o_t[s] if o_t[s] <= stop_p else pos[s]['qty'] * stop_p
                del pos[s]
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                cash += pos[s]['qty'] * px
                del pos[s]
            pending_sells.discard(s)
        if pending_exec is not None and t == pending_exec[0]:
            _, target, eq_sig = pending_exec
            pending_exec = None
            for s in list(pos):
                if s in target or s in pending_sells:
                    continue
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    pending_sells.add(s)
                    continue
                cash += pos[s]['qty'] * px
                del pos[s]
            for s in target:
                if s in pos or pd.isna(o_t.get(s, np.nan)):
                    continue
                budget = min(slot * eq_sig, max(cash, 0.0))
                if budget <= 0:
                    continue
                qty = budget / o_t[s]
                cash -= qty * o_t[s]
                pos[s] = {'qty': qty, 'entry': o_t[s]}
        hold[t] = ','.join(sorted(pos))
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) and med_ret[t] < CRASH_MED:
            pending_sells.update(pos.keys())
        if t in sig_days:
            score = cross_scores(F, syms, t)
            if not pd.isna(idx_ma.get(t, np.nan)) and idx[t] < idx_ma[t]:
                target = []
            else:
                target = list(score.index[:TOP_N])
            eq_sig = cash + sum(p['qty'] * mark.at[t, s] for s, p in pos.items())
            pending_exec = (cal[cal.get_loc(t) + 1], target, eq_sig) \
                if cal.get_loc(t) + 1 < len(cal) else None
    return pd.Series(hold).sort_index()


# ---------------------------------------------------------------- 熔断器评估
def _roll_mdd(series, window):
    """滚动窗口 MDD（逐日窗口尾值）。"""
    out = pd.Series(index=series.index, dtype=float)
    v = series.values
    dts = series.index
    for i in range(len(v)):
        lo = max(0, i - window + 1)
        seg = v[lo:i + 1]
        peak = np.maximum.accumulate(seg)
        out.iloc[i] = ((seg / peak) - 1.0).min()
    return out


def eval_breakers(rp, tier_idx, asof=None, cb3_base=CB3_BASE_60D):
    """输入回放结果，输出各熔断器状态灯与建议动作。
    灯：green=正常 / yellow=预警观察 / red=触发动作。"""
    eq_n, eq_g, fees = rp['eq_net'], rp['eq_gross'], rp['fees']
    if asof is not None:
        eq_n, eq_g, fees = eq_n[:asof], eq_g[:asof], fees[:asof]
    cal = eq_n.index
    lights, actions = {}, {}

    # CB1：滚动20交易日净账 MDD
    mdd20 = _roll_mdd(eq_n, CB1_WINDOW)
    cur_mdd = float(mdd20.iloc[-1]) if len(mdd20) else 0.0
    if cur_mdd <= CB1_MDD:
        lights['CB1'] = 'red'
        actions['CB1'] = f'降一档（滚动{CB1_WINDOW}日MDD={cur_mdd:.1%}≤{CB1_MDD:.0%}）'
    elif cur_mdd <= CB1_MDD / 2:
        lights['CB1'] = 'yellow'
        actions['CB1'] = f'观察（滚动{CB1_WINDOW}日MDD={cur_mdd:.1%}，过半警戒线）'
    else:
        lights['CB1'] = 'green'
        actions['CB1'] = '正常'
    cb1_detail = round(cur_mdd, 4)

    # CB2：滚动60日止损失血（毛账触发+净账确认）
    stop_ev = [e for e in rp['stops'] if asof is None or pd.Timestamp(e['date']) <= asof]
    d0 = cal[-CB2_WINDOW] if len(cal) >= CB2_WINDOW else cal[0]
    # 止损单失血：以毛账轨逐笔重估（pnl 相对毛账权益，名义用止损时点毛账×单票slot近似不可得，
    # 改用事件级口径：毛账滚动窗口跌幅中的止损贡献 = 窗口内止损单 pnl 合计（相对1.0名义已归一在 stops 里）
    gross_60 = float(eq_g.iloc[-1] / eq_g[eq_g.index >= d0].iloc[0] - 1)
    net_60 = float(eq_n.iloc[-1] / eq_n[eq_n.index >= d0].iloc[0] - 1)
    stop_cnt_60 = sum(1 for e in stop_ev if pd.Timestamp(e['date']) >= d0)
    stop_pnl_60 = sum(e['pnl_pct'] * e.get('slot', SLOTS[0]) for e in stop_ev
                      if pd.Timestamp(e['date']) >= d0)   # 名义加权 ≈ 占权益 pp
    gross_trigger = stop_pnl_60 <= CB2_LOSS or gross_60 <= CB2_LOSS
    net_confirm = net_60 <= CB2_LOSS
    if gross_trigger and net_confirm:
        lights['CB2'] = 'red'
        actions['CB2'] = f'冻结开新仓{CB2_FREEZE_DAYS}交易日（首月暂定）：60日毛账失血触发+净账确认'
    elif gross_trigger:
        lights['CB2'] = 'yellow'
        actions['CB2'] = '预警：毛账触发待净账确认'
    else:
        lights['CB2'] = 'green'
        actions['CB2'] = '正常'
    cb2_detail = {'gross_60d_pct': round(gross_60, 4), 'net_60d_pct': round(net_60, 4),
                  'stop_count_60d': stop_cnt_60,
                  'stop_pnl_sum_60d': round(stop_pnl_60, 4)}

    # CB3：止损频次外移观察线
    line = cb3_base * CB3_MULT
    if stop_cnt_60 >= line:
        lights['CB3'] = 'yellow'
        actions['CB3'] = f'外移观察：60日止损{stop_cnt_60}次≥观察线{line:.0f}次'
    else:
        lights['CB3'] = 'green'
        actions['CB3'] = '正常'
    cb3_detail = {'stop_count_60d': stop_cnt_60, 'baseline_60d': cb3_base, 'line': line}

    # 费线：滚动60日费用年化拖累（60交易日≈0.238年）
    fee_60 = float(fees.iloc[-min(CB2_WINDOW, len(cal)):].sum())
    fee_ann = fee_60 / (CB2_WINDOW / 252.0)
    if fee_ann >= FEE_LINE_ANN:
        lights['FEE'] = 'red'
        actions['FEE'] = f'降一档（滚动60日费拖累年化={fee_ann:.1%}≥{FEE_LINE_ANN:.1%}）'
    elif fee_ann >= FEE_LINE_ANN / 2:
        lights['FEE'] = 'yellow'
        actions['FEE'] = f'预警：费拖累年化={fee_ann:.1%}过半线'
    else:
        lights['FEE'] = 'green'
        actions['FEE'] = '正常'
    fee_detail = {'fee_60d': round(fee_60, 6), 'fee_ann_pct': round(fee_ann, 4),
                  'line_ann_pct': FEE_LINE_ANN}

    # 汇总建议：任一红灯 → 执行对应动作；多红灯取最严（冻结 > 降档 > 观察）
    reds = [k for k, v in lights.items() if v == 'red']
    if 'CB2' in reds:
        overall = ('red', actions['CB2'])
    elif reds:
        overall = ('red', '；'.join(actions[k] for k in reds))
    elif any(v == 'yellow' for v in lights.values()):
        overall = ('yellow', '；'.join(actions[k] for k, v in lights.items() if v == 'yellow'))
    else:
        overall = ('green', '正常运行')
    return {'lights': lights, 'actions': actions, 'overall': overall,
            'detail': {'CB1': cb1_detail, 'CB2': cb2_detail,
                       'CB3': cb3_detail, 'FEE': fee_detail},
            'tier_idx': tier_idx, 'slot_now': SLOTS[tier_idx]}


# ---------------------------------------------------------------- 三本账月报
def monthly_accounts(rp, months=12):
    eq_g, eq_n, fees = rp['eq_gross'], rp['eq_net'], rp['fees']
    idx = rp['idx'].reindex(eq_g.index).ffill()
    mg, mn, mf, mi = (x.resample('ME').last() for x in (eq_g, eq_n, fees, idx))
    rows = []
    for i in range(1, len(mg)):
        m = str(mg.index[i])[:7]
        rows.append({'month': m,
                     'gross_pct': round((mg.iloc[i] / mg.iloc[i - 1] - 1) * 100, 2),
                     'net_pct': round((mn.iloc[i] / mn.iloc[i - 1] - 1) * 100, 2),
                     'fee_pct': round(mf.iloc[i] * 100, 3),
                     'pool_pct': round((mi.iloc[i] / mi.iloc[i - 1] - 1) * 100, 2),
                     'concede_pct': round(((mi.iloc[i] / mi.iloc[i - 1])
                                           - (mg.iloc[i] / mg.iloc[i - 1])) * 100, 2)})
    return rows[-months:]


# ---------------------------------------------------------------- 实时信号
def current_signal(data, F, syms, tier_idx=0):
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close = pd.DataFrame({s: data[s]['close'] for s in syms}).reindex(cal)
    idx = close.mean(axis=1)
    idx_ma = idx.rolling(MA_REG).mean()
    med_ret = close.pct_change().median(axis=1)
    t = cal[-1]
    gate_on = bool(not pd.isna(idx_ma.iloc[-1]) and idx.iloc[-1] < idx_ma.iloc[-1])
    sig_days = week_first_days(cal)
    is_sig_day = bool(t in sig_days)
    score = cross_scores(F, syms, t)
    top5 = [{'sym': s, 'score': round(float(score[s]), 4)} for s in score.index[:TOP_N]]
    slot = SLOTS[tier_idx]
    crash_yest = bool(not pd.isna(med_ret.iloc[-1]) and med_ret.iloc[-1] < CRASH_MED)
    return {
        'asof': str(t.date()),
        'is_signal_day': is_sig_day,
        'signal_rule': '每周首个交易日收盘出信号，次日开盘成交；本表为最新横截面评分参考',
        'gate': {'idx': round(float(idx.iloc[-1]), 4),
                 'ma50': round(float(idx_ma.iloc[-1]), 4),
                 'on_holdcash': gate_on,
                 'status': 'red' if gate_on else 'green'},
        'crash_check': {'pool_med_ret': round(float(med_ret.iloc[-1]), 4),
                        'line': CRASH_MED, 'triggered': crash_yest},
        'top5': top5,
        'slot_per_stock_pct': round(slot * 100, 2),
        'total_exposure_pct': round(slot * TOP_N * 100, 2),
        'tier_idx': tier_idx,
    }


# ---------------------------------------------------------------- live 主入口
def engine_sha256(path=None):
    path = path or os.path.abspath(__file__)
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def run_live(out_json='/workspace/f1_web/f1_live.json', cache=CACHE):
    data = load_data(cache)
    syms = build_pool(data)
    F = build_factors(data)
    rp = replay(data, F, syms, slot=SLOTS[0])

    # 由 CB3 基准回填：回放期（2024 全期）止损次数 → 60日期望基准
    n_years = max((rp['cal'][-1] - rp['cal'][0]).days / 365.25, 1e-9)
    cb3_base = round(len(rp['stops']) / n_years * (60 / 252.0), 2)

    sig = current_signal(data, F, syms, tier_idx=0)
    bk = eval_breakers(rp, tier_idx=0, cb3_base=cb3_base)
    acct = monthly_accounts(rp)
    fee_curve = [{'month': r['month'], 'fee_pct': r['fee_pct']} for r in acct]
    recent_stops = rp['stops'][-10:]
    out = {
        'meta': {'workorder': "R11' F1 上线运营 · f1_signal.py v1",
                 'seed': SEED, 'generated': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'engine_sha256': engine_sha256(), 'pool_n': len(syms),
                 'caliber': 'V2可实现出场（成交价=当根open，止损跳空按open否则按stop价）+滑点0.05%/边+资金费0.03%/bar',
                 'tier_table_pct_per_stock': [round(s * 100, 2) for s in SLOTS],
                 'cb3_baseline_60d': cb3_base,
                 'replay': {'start': str(rp['cal'][0].date()),
                            'end': str(rp['cal'][-1].date()),
                            'eq_net': round(float(rp['eq_net'].iloc[-1]), 4),
                            'eq_gross': round(float(rp['eq_gross'].iloc[-1]), 4),
                            'stop_events_total': len(rp['stops'])}},
        'signal': sig,
        'breakers': {'overall': {'light': bk['overall'][0], 'action': bk['overall'][1]},
                     'items': [{'name': k, 'light': bk['lights'][k],
                                'action': bk['actions'][k], 'detail': bk['detail'][k]}
                               for k in ('CB1', 'CB2', 'CB3', 'FEE')]},
        'monthly_accounts': acct,
        'fee_curve': fee_curve,
        'monitor': {'recent_stops': recent_stops,
                    'notes': ['止损−8%硬截断(V2口径)', '崩市=池单日中位跌幅<−5%次日清仓',
                              'regime闸=idx<MA50清仓持币', 'CB3频次基准由回放期统计回填']},
    }
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    tmp = out_json + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_json)
    return out


# ---------------------------------------------------------------- CLI
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'live'
    if mode == 'live':
        out = run_live()
        bk = out['breakers']['overall']
        print(f"live ok: asof={out['signal']['asof']} gate={'持币' if out['signal']['gate']['on_holdcash'] else '持仓'} "
              f"top5={[x['sym'] for x in out['signal']['top5']]} "
              f"breaker={bk['light']} action={bk['action']}")
    elif mode == 'replay':
        slot = float(sys.argv[sys.argv.index('--slot') + 1]) if '--slot' in sys.argv else SLOTS[0]
        data = load_data()
        syms = build_pool(data)
        F = build_factors(data)
        rp = replay(data, F, syms, slot=slot)
        print(f"replay ok: {rp['cal'][0].date()}~{rp['cal'][-1].date()} "
              f"eq_net={rp['eq_net'].iloc[-1]:.4f} eq_gross={rp['eq_gross'].iloc[-1]:.4f} "
              f"stops={len(rp['stops'])}")
        if '--holdings-out' in sys.argv:
            ho = sys.argv[sys.argv.index('--holdings-out') + 1]
            rp['holdings'].to_csv(ho, header=['holdings'])
            print('holdings ->', ho)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
