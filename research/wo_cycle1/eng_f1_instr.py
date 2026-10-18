#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eng_f1_instr.py — 仪表化 ungated 引擎（WO3/WO2 共用）
run_instr 逐字复制自 /tmp/r9/r9_final.py（R9 已做 T1 三账同源校验：与
f1_backtest.run_backtest(ungated) 逐日 diff=0）。因 r9_final.py 顶部 import 的
KEEP_RANK 在现行 f1_backtest.py v2 中已删除（v2 升版记录：死参数删除不影响结果），
导致 import 链断裂，故将 run_instr 本体逐字落此共享模块，常量改从 v2 直接导入。
【G4 升版对齐（2026-10-18 生效的现行权威口径）】v2 f1_backtest.py 相对 r9 谱系
唯一语义差异 = BUG-04（当日止损出场为终态，止损票当日禁止买回；跳过买入不补买
不顺延）。本模块按 v2 逐字补入 stopped_today 集合，周/双周两臂统一 v2 口径；
补齐后 T1 同源校验须 weekly vs run_backtest(v2, ungated) 逐日 diff=0 方可采信。
口径红线：除此一处对齐外引擎逻辑零改动；KEEP_RANK 在 run_instr 内未被引用。
"""
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, '/tmp/eng_w2_f1')
from f1_backtest import (SEED, TOP_N, SLOT, STOP, CRASH_MED,   # noqa: F401
                         FEE_SIDE, FUNDING, FACTORS_4, cross_scores)

import numpy as np
import pandas as pd

REAL_START = pd.Timestamp('2026-06-01')   # 数据出身分界（R9 铁律：>=此日为真实窗）


def run_instr(data, F, syms, rebal_weeks=1):
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: data[s]['open'] for s in syms})
    low = pd.DataFrame({s: data[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close = close.reindex(cal)
    open_ = open_.reindex(cal)
    low = low.reindex(cal)
    mark = close.ffill()
    med_ret = close.pct_change().median(axis=1)

    iso = cal.isocalendar()
    if rebal_weeks == 1:
        sig_days = set(cal.to_series().groupby(
            [iso['year'].values, iso['week'].values]).first())
    else:  # r8_fee 参数化：每 rebal_weeks 个 ISO 周出一次信号
        wk_key = list(zip(iso['year'].values, iso['week'].values))
        uniq = sorted(set(wk_key))
        keep = set(w for i, w in enumerate(uniq) if i % rebal_weeks == 0)
        first_pos = {}
        for i, k in enumerate(wk_key):
            if k in keep and k not in first_pos:
                first_pos[k] = i
        sig_days = set(cal[i] for i in first_pos.values())

    cash, pos = 1.0, {}
    pending_sells = set()
    pending_exec = None
    eq = {}
    fees = turnover = 0.0
    last_mark = {}
    events = []          # 逐笔事件流水（含止损实现盈亏）
    fee_ledger = []      # 逐笔交易费流水
    funding_by_day = {}  # 逐日资金费

    def sell(s, t, px, kind):
        nonlocal cash, fees, turnover
        q = pos[s]['qty']
        realized = q * px * (1 - FEE_SIDE) - q * last_mark[s]
        cash += q * px * (1 - FEE_SIDE)
        fees += q * px * FEE_SIDE
        turnover += q * px
        fee_ledger.append({'date': str(t.date()), 'sym': s, 'kind': kind,
                           'notional': round(float(q * px), 6),
                           'fee': round(float(q * px * FEE_SIDE), 8)})
        del pos[s]
        last_mark.pop(s, None)
        events.append({'date': str(t.date()), 'kind': kind, 'sym': s,
                       'px': round(float(px), 6), 'qty': round(float(q), 6),
                       'pnl': round(float(realized), 8)})

    for t in cal:
        o_t, lo_t = open_.loc[t], low.loc[t]
        stopped_today = set()   # BUG-04：当日止损出场票（禁止当日买回，次日起恢复）
        # 1) 盘中断价止损（V2：跳空按开盘，否则按止损价）
        for s in list(pos):
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            stop_p = pos[s]['entry'] * (1 + STOP)
            if o_t[s] <= stop_p:
                px = o_t[s]
            elif lo_t[s] <= stop_p:
                px = stop_p
            else:
                continue
            stopped_today.add(s)          # BUG-04：止损出场为终态（v2 逐字）
            sell(s, t, px, 'stop')
        # 2) 止损/崩市挂单清仓
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                sell(s, t, px, 'sell_pending')
            pending_sells.discard(s)
        # 3) 调仓执行（信号次日开盘）
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
                sell(s, t, px, 'rebal_sell')
            for s in target:
                if s in pos or s in stopped_today:   # BUG-04：止损票当日禁止买回（v2 逐字）
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
                pos[s] = {'qty': qty, 'entry': px}
                last_mark[s] = px
                fee_ledger.append({'date': str(t.date()), 'sym': s, 'kind': 'buy',
                                   'notional': round(float(qty * px), 6),
                                   'fee': round(float(qty * px * FEE_SIDE), 8)})
        # 4) 收盘记账 + 资金费
        equity = cash
        f_day = 0.0
        for s, p in pos.items():
            m = mark.at[t, s]
            equity += p['qty'] * m
            f = p['qty'] * m * FUNDING
            cash -= f
            fees += f
            f_day += f
        funding_by_day[str(t.date())] = float(f_day)
        eq[t] = equity
        # 5) 崩市检查
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                and med_ret[t] < CRASH_MED:
            pending_sells.update(pos.keys())
        # 6) 信号（ungated：target 恒为 top-5）
        if t in sig_days:
            score = cross_scores(F, syms, t, FACTORS_4)
            target = list(score.index[:TOP_N])
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity) \
                if cal.get_loc(t) + 1 < len(cal) else None

    curve = pd.Series(eq).sort_index()
    return {'curve': curve, 'fees': fees, 'turnover': turnover,
            'events': events, 'fee_ledger': fee_ledger,
            'funding_by_day': funding_by_day, 'start': str(cal[0].date()),
            'end': str(cal[-1].date())}
