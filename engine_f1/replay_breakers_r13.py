#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WO-R13-01 · 熔断线重标定后的真实段回放触发统计
================================================================================
用途：用真实缓存全量回放，逐日重算四条线的指标序列，分别在「旧阈值（R11' 满仓遗产）」
      与「新阈值（R13 重标定）」下统计触发次数，供审计席核对。

口径（与引擎 eval_breakers 同源）：
- CB1：滚动 20 交易日「净账」最大回撤（_roll_mdd，窗口尾值）
- CB2：滚动 60 交易日「毛账」触发（止损单名义加权合计 ≤ 线 或 60 日毛跌 ≤ 线）
       + 「净账」确认（同期净跌 ≤ 线）；毛触发未确认=黄，确认=红
- CB3：滚动 60 交易日止损次数 ≥ 9.07×3=27.21（只黄不红）
- 费线：滚动 60 交易日费用合计 / (60/252) 折年化 ≥ 线

复现：PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/replay_breakers_r13.py
输出：/workspace/repo_ready/engine_f1/breaker_stats_r13.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import f1_signal as eng  # noqa: E402

np.random.seed(eng.SEED)

# 旧阈值（R11' 满仓时代口径遗产，已废）
OLD = {'CB1': (-0.32, -0.16), 'CB2': (-0.20, -0.10), 'FEE': (0.217, 0.1085), 'CB3': 27.21}
# 新阈值（R13 重标定，取引擎常量，单一事实源）
T = eng.breaker_thresholds()
NEW = {'CB1': (T['CB1']['red'], T['CB1']['yellow']),
       'CB2': (T['CB2']['red'], T['CB2']['yellow']),
       'FEE': (T['FEE']['red'], T['FEE']['yellow']),
       'CB3': T['CB3']['line']}

FOCUS_START = pd.Timestamp('2025-06-02')


def build():
    data = eng.load_data()
    syms = eng.build_pool(data)
    F = eng.build_factors(data)
    rp = eng.replay(data, F, syms, slot=eng.SLOTS[0])
    return data, syms, F, rp


def series(rp):
    eq_n, eq_g, fees = rp['eq_net'], rp['eq_gross'], rp['fees']
    cal = eq_n.index
    mdd20 = eng._roll_mdd(eq_n, eng.CB1_WINDOW)
    stop_df = pd.DataFrame(rp['stops'])
    cnt60 = pd.Series(0.0, index=cal)
    pnl60 = pd.Series(0.0, index=cal)
    if len(stop_df):
        stop_df['date'] = pd.to_datetime(stop_df['date'])
        stop_df['pnl_pp'] = stop_df['pnl_pct'] * stop_df['slot']
        daily_cnt = stop_df.groupby('date').size().reindex(cal, fill_value=0)
        daily_pnl = stop_df.groupby('date')['pnl_pp'].sum().reindex(cal, fill_value=0.0)
        cnt60 = daily_cnt.rolling(eng.CB2_WINDOW).sum()
        pnl60 = daily_pnl.rolling(eng.CB2_WINDOW).sum()
    ret_g60 = eq_g / eq_g.shift(eng.CB2_WINDOW) - 1
    ret_n60 = eq_n / eq_n.shift(eng.CB2_WINDOW) - 1
    fee60 = fees.rolling(eng.CB2_WINDOW).sum()
    fee_ann = fee60 / (eng.CB2_WINDOW / 252.0)
    return dict(mdd20=mdd20, cnt60=cnt60, pnl60=pnl60, ret_g60=ret_g60,
                ret_n60=ret_n60, fee_ann=fee_ann, cal=cal)


def count(th, S, mask):
    """按 (红线, 黄线) 统计 CB1/CB2/FEE；CB3 单独。"""
    out = {}
    mdd = S['mdd20'][mask]
    out['CB1'] = dict(red_days=int((mdd <= th['CB1'][0]).sum()),
                      yellow_days=int(((mdd <= th['CB1'][1]) & (mdd > th['CB1'][0])).sum()))
    g_trig = ((S['pnl60'] <= th['CB2'][0]) | (S['ret_g60'] <= th['CB2'][0]))[mask]
    net_ok = (S['ret_n60'] <= th['CB2'][0])[mask]
    out['CB2'] = dict(red_days=int((g_trig & net_ok).sum()),
                      yellow_days=int((g_trig & ~net_ok).sum()))
    fa = S['fee_ann'][mask]
    out['FEE'] = dict(red_days=int((fa >= th['FEE'][0]).sum()),
                      yellow_days=int(((fa >= th['FEE'][1]) & (fa < th['FEE'][0])).sum()))
    c3 = S['cnt60'][mask]
    out['CB3'] = dict(yellow_days=int((c3 >= th['CB3']).sum()))
    return out


def dates_of(series, mask, cond, limit=5):
    s = series[mask]
    idx = s[cond(s)].index
    return [str(d.date()) for d in idx[:limit]]


def main():
    data, syms, F, rp = build()
    S = series(rp)
    cal = S['cal']
    focus = cal >= FOCUS_START
    mdd = S['mdd20'][focus]

    res = {
        'CB1': {
            'metric': '滚动20交易日净账MDD',
            'old_line': {'red': OLD['CB1'][0], 'yellow': OLD['CB1'][1]},
            'new_line': {'red': NEW['CB1'][0], 'yellow': NEW['CB1'][1]},
            'extreme': round(float(mdd.min()), 4),
            'extreme_date': str(mdd.idxmin().date()),
            'new_red_days': int((mdd <= NEW['CB1'][0]).sum()),
            'new_yellow_days': int(((mdd <= NEW['CB1'][1]) & (mdd > NEW['CB1'][0])).sum()),
            'new_red_dates': dates_of(S['mdd20'], focus, lambda x: x <= NEW['CB1'][0]),
            'new_yellow_dates': dates_of(S['mdd20'], focus,
                                         lambda x: (x <= NEW['CB1'][1]) & (x > NEW['CB1'][0]), 8),
            'basis': '实测极值 −6.64%（2026-05-19）×1.20 ≈ −8%（红线），黄线取红线之半',
        },
        'CB2': {
            'metric': '滚动60日止损失血（毛账触发/净账确认）',
            'old_line': {'red': OLD['CB2'][0], 'yellow': OLD['CB2'][1]},
            'new_line': {'red': NEW['CB2'][0], 'yellow': NEW['CB2'][1]},
            'extreme_stop_pnl60': round(float(S['pnl60'][focus].min()), 4),
            'extreme_gross60': round(float(S['ret_g60'][focus].min()), 4),
            'extreme_net60': round(float(S['ret_n60'][focus].min()), 4),
            'basis': '实测 stop_pnl60 最深 −4.73pp×1.06 ≈ −5pp（红线）',
        },
        'CB3': {
            'metric': '滚动60日止损次数',
            'line': NEW['CB3'],
            'baseline': eng.CB3_BASE_60D,
            'mult': eng.CB3_MULT,
            'max_cnt60': int(S['cnt60'][focus].max()),
            'basis': 'R13 保留不动：唯一活线，冻结基准 9.07 与 live 重算一致（无漂移）',
        },
        'FEE': {
            'metric': '滚动60日费用折年化',
            'old_line': {'red': OLD['FEE'][0], 'yellow': OLD['FEE'][1]},
            'new_line': {'red': NEW['FEE'][0], 'yellow': NEW['FEE'][1]},
            'max_fee_ann': round(float(S['fee_ann'][focus].max()), 4),
            'p99_fee_ann': round(float(S['fee_ann'][focus].quantile(0.99)), 4),
            'basis': '红线 4pp ≈ 满周转手结构上限（12.5%×0.13%×252≈4.1pp）；黄线取半 2pp',
        },
    }
    res['CB2']['new_red_days'] = int((((S['pnl60'] <= NEW['CB2'][0])
                                       | (S['ret_g60'] <= NEW['CB2'][0]))[focus]
                                      & (S['ret_n60'] <= NEW['CB2'][0])[focus]).sum())
    res['CB2']['new_yellow_days'] = int((((S['pnl60'] <= NEW['CB2'][0])
                                          | (S['ret_g60'] <= NEW['CB2'][0]))[focus]
                                        & ~((S['ret_n60'] <= NEW['CB2'][0])[focus])).sum())
    res['CB3']['new_yellow_days'] = int((S['cnt60'][focus] >= NEW['CB3']).sum())
    res['FEE']['new_red_days'] = int((S['fee_ann'][focus] >= NEW['FEE'][0]).sum())
    res['FEE']['new_yellow_days'] = int(((S['fee_ann'][focus] >= NEW['FEE'][1])
                                          & (S['fee_ann'][focus] < NEW['FEE'][0])).sum())

    g_trig_all = ((S['pnl60'] <= NEW['CB2'][0]) | (S['ret_g60'] <= NEW['CB2'][0]))[focus]
    net_ok_all = (S['ret_n60'] <= NEW['CB2'][0])[focus]
    trigger_dates = {
        'CB1_red': dates_of(S['mdd20'], focus, lambda x: x <= NEW['CB1'][0]),
        'CB1_yellow': dates_of(S['mdd20'], focus,
                               lambda x: (x <= NEW['CB1'][1]) & (x > NEW['CB1'][0]), 50),
        'CB2_red': [str(d.date()) for d in (g_trig_all & net_ok_all)[g_trig_all & net_ok_all].index],
        'CB2_yellow': [str(d.date()) for d in (g_trig_all & ~net_ok_all)[g_trig_all & ~net_ok_all].index],
        'CB3_yellow': dates_of(S['cnt60'], focus, lambda x: x >= NEW['CB3']),
        'FEE_red': dates_of(S['fee_ann'], focus, lambda x: x >= NEW['FEE'][0]),
        'FEE_yellow': dates_of(S['fee_ann'], focus,
                               lambda x: (x >= NEW['FEE'][1]) & (x < NEW['FEE'][0])),
    }

    out = {
        'workorder': 'WO-R13-01 熔断线重标定后的真实段回放统计',
        'seed': eng.SEED,
        'engine_sha256': eng.engine_sha256(),
        'calib_epoch': eng.CALIB_EPOCH,
        'window': {'full_start': str(cal[0].date()), 'focus_start': str(FOCUS_START.date()),
                   'end': str(cal[-1].date()), 'focus_days': int(focus.sum()),
                   'full_days': int(len(cal))},
        'old_thresholds': {'CB1': {'red': OLD['CB1'][0], 'yellow': OLD['CB1'][1]},
                           'CB2': {'red': OLD['CB2'][0], 'yellow': OLD['CB2'][1]},
                           'FEE': {'red': OLD['FEE'][0], 'yellow': OLD['FEE'][1]},
                           'CB3': {'line': OLD['CB3']}},
        'new_thresholds': {'CB1': {'red': NEW['CB1'][0], 'yellow': NEW['CB1'][1]},
                           'CB2': {'red': NEW['CB2'][0], 'yellow': NEW['CB2'][1]},
                           'FEE': {'red': NEW['FEE'][0], 'yellow': NEW['FEE'][1]},
                           'CB3': {'line': NEW['CB3']}},
        'trigger_counts_new': count(NEW, S, focus),
        'trigger_counts_old': count(OLD, S, focus),
        'trigger_dates_new': trigger_dates,
        'detail': res,
        'note': ('统计口径与引擎 eval_breakers 同源；旧阈值列用于证明「改前 0 触发」，'
                 '新阈值列为重标定后的真实触发次数。'),
    }
    out_path = os.path.join(HERE, 'breaker_stats_r13.json')
    with open(out_path, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({'window': out['window'],
                      'new': out['trigger_counts_new'],
                      'old': out['trigger_counts_old'],
                      'extremes': {k: {kk: vv for kk, vv in v.items() if 'extreme' in kk or k == 'CB3'}
                                   for k, v in res.items()}},
                     ensure_ascii=False, indent=1, default=str))
    print('结果文件 →', out_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
