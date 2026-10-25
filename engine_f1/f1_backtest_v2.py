#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W2 工单 F1 权威对账脚本 · v2（WO-R14-G4 升版 · 2026-10-18）
================================================================
【升版记录】
- 升版依据（规格文档层，防循环论证）：《F1 台账口径》v1（/workspace/repo_ready/engine_f1/
  F1_台账口径_v1.md，2026-10-18 起生效）§一.8 BUG-04 条款原文：
  「崩市：池单日中位跌幅 < -5% → 次日清仓；且当日禁止重建仓、止损票当日禁止买回」；
  终版语义=R13 交易四席复分析会空头席裁定（/tmp/reanalyze_r13/verdict.md 事项一）：
  当日对该票的止损出场为终态；同日一切入场路径（周调仓买入、崩市次日重建仓等）跳过该票；
  次日起若信号名单仍含该票，按正常调仓恢复买入；止损日恰逢执行日且该票在买入名单
  → 跳过买入，不视为换仓失败、不补买、不顺延。崩市清仓日「禁止当日重建仓」为全池口径（既有，不变）。
- 本版改动：仅新增 stopped_today 集合（当日止损出场记录）并在调仓买入环跳过该票，
  与引擎 f1_signal.py BUG-04 语义逐字一致（独立实现，未引用引擎任何函数）。
- 未改动：费/因子/调仓/闸/崩市/记账/池口径等一切其他逻辑（回归红线）。
- 升版动因：W2 版无 BUG-04 口径，2025-08-12 GPROUSDT、2026-01-06 AAOIUSDT 止损日恰逢
  调仓执行日照常买回，与引擎产生 11/767 天持仓偏差（/tmp/r13_test/TEST_REPORT.md §六①）。
- 验收（冻结判据）：升版后 vs 引擎 f1_signal.py 逐日持仓 diff 全窗=0；升版前后对照
  仅该 11 天持仓改变，其余 756 天不变。双跑归档见 /tmp/g4/G4_report.md。

【W2 工单原说明（v1，主管席 R3 终裁版）】
- seed=42，一次成活；改参数=新工单，禁止调参重跑
- 双池口径：old131 老票池（首K<=2025-03-31，缓存为滚动700根、起点2024-01-24，
  无法直接判别"2024-01-24前上市"，此为可复现代理口径，数量=工单131）
  / full144 全池（截至2026-10-17有>=100根日K，约上市满5个月，数量=工单144）
- 指数 idx = 池内等权收盘均价；regime 闸 = idx < MA50 清仓持币（对照实验核心）
- 因子：ma20_slope / obv_slope20 / dist_52w_high / mom_1m，横截面 z-score 等权合成
- 调仓：每周首个交易日（多为周一，节假日顺延）收盘出信号，次日开盘成交；
  持 top-5 各 10%（50% 敞口上限）；跌出 top-15 换仓；-8% 硬止损；
  崩市（池单日中位跌幅<-5%）清仓
- 成本：换仓双边 0.05%/边 + 资金费 0.03%/bar（按持仓名义）
- 记账：V2 可实现口径（成交价取当根 open，天然落在 [low,high] 内；止损价
  触发时若开盘已跳空按开盘、否则按止损价，均落在当根 [low,high] 内）
- 切分：训练 2024-01~2026-03（含因子预热，前期现金），留出 2026-04~10（只报告）
- 消融：去掉 obv_slope20 的三因子版一并跑（W1/W2 共用），带闸变体双池
"""
import json
import os

import numpy as np
import pandas as pd

SEED = 42
np.random.seed(SEED)

CACHE = '/tmp/box_cache'
OUT = '/tmp/eng_w2_f1'
os.makedirs(OUT, exist_ok=True)

TOP_N = 5            # 持仓数
SLOT = 0.10          # 每仓名义 10%（5仓=50%敞口上限）
# 周换仓口径（v1 锁定，主管席 BUG-02 裁决）：每周全量 top-5 重选，跌出榜单即换出；
# 原 KEEP_RANK=15 死参数已删除（未引用，删除不影响回测结果）
STOP = -0.08         # -8% 硬止损
CRASH_MED = -0.05    # 崩市：池单日中位跌幅 < -5%
FEE_SIDE = 0.0005    # 换仓双边 0.05%/边
FUNDING = 0.0003     # 资金费 0.03%/bar 按持仓名义
MA_REG = 50          # idx MA50 regime 闸
TRAIN_END = pd.Timestamp('2026-03-31')
HOLD_START = pd.Timestamp('2026-04-01')

FACTORS_4 = ['ma20_slope', 'obv_slope20', 'dist_52w_high', 'mom_1m']
FACTORS_3 = ['ma20_slope', 'dist_52w_high', 'mom_1m']  # 消融：去 obv_slope20


# ---------------------------------------------------------------- 数据与池
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
    assert len(old) == 131, f'老票池={len(old)} != 131'
    assert len(full) == 144, f'全池={len(full)} != 144'
    return {'old131': old, 'full144': full}


# ---------------------------------------------------------------- 因子
def build_factors(data):
    """逐标的四因子，全部基于自身历史，池无关。"""
    F = {}
    for s, d in data.items():
        c, v = d['close'], d['volume']
        ma20 = c.rolling(20).mean()
        f_ma = ma20 / ma20.shift(5) - 1                                   # ma20_slope
        obv = (np.sign(c.diff()).fillna(0.0) * v).cumsum()
        f_obv = (obv - obv.shift(20)) / (v.rolling(20).mean() * 20.0)     # obv_slope20
        f_52w = c / c.rolling(252, min_periods=20).max() - 1.0            # dist_52w_high
        f_mom = c / c.shift(21) - 1.0                                     # mom_1m
        F[s] = pd.DataFrame({'ma20_slope': f_ma, 'obv_slope20': f_obv,
                             'dist_52w_high': f_52w, 'mom_1m': f_mom})
    return F


def cross_scores(F, syms, dt, factors):
    """信号日横截面：各因子 z-score（|z|截断3）后等权平均。"""
    rows = {}
    for s in syms:
        f = F[s]
        if dt not in f.index:
            continue
        vals = f.loc[dt, factors]
        if vals.notna().sum() == len(factors):        # 四/三因子齐备才入池打分
            rows[s] = vals.values
    if len(rows) < TOP_N:
        return pd.Series(dtype=float)
    mat = pd.DataFrame(rows, index=factors).T
    mu, sd = mat.mean(), mat.std(ddof=0)
    z = ((mat - mu) / sd.replace(0.0, np.nan)).clip(-3, 3)
    return z.mean(axis=1).dropna().sort_values(ascending=False)


# ---------------------------------------------------------------- 回测引擎
def run_backtest(data, F, syms, gated, factors):
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: data[s]['open'] for s in syms})
    low = pd.DataFrame({s: data[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close = close.reindex(cal)
    open_ = open_.reindex(cal)
    low = low.reindex(cal)
    mark = close.ffill()                                   # 停牌日按最近收盘记账
    # idx 采样日历（IDX-POLLUTION-20261026 同步）：本件为对账红线夹具，按设计独立实现
    # （不引用引擎函数），此处按《idx周末污染-取证修复上会记录-2026-10-26.md》§1.3 独立重写：
    # 采样日 = 当日有收盘标的数 >= 0.90 × 该日为中心 ±30 个在册日的中位数；idx 仅采样日
    # 取值，MA50=采样日序列 rolling(MA_REG)（50 个观测）；非采样日 idx/MA50 前向携带。
    cnt = close.notna().sum(axis=1)
    med = cnt.rolling(61, center=True, min_periods=1).median()
    keep = cnt >= 0.90 * med
    idx = close[keep].mean(axis=1)                         # 池等权收盘均价（仅采样日）
    idx_ma = idx.rolling(MA_REG).mean()
    idx = idx.reindex(cal).ffill()
    idx_ma = idx_ma.reindex(cal).ffill()
    med_ret = close.pct_change().median(axis=1)            # 池单日中位收益

    iso = cal.isocalendar()
    sig_days = set(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first())

    cash, pos = 1.0, {}          # pos: sym -> dict(qty, entry)
    pending_sells = set()        # 止损/崩市 → 次根可用K线开盘卖出
    pending_exec = None          # (次日, target_list, equity_at_signal)
    eq, hold = {}, {}            # G4 插桩：hold=逐日持仓（仅记录，不改任何逻辑）
    fees = turnover = 0.0
    n_rebal = 0

    for t in cal:
        o_t, lo_t, c_t = open_.loc[t], low.loc[t], close.loc[t]
        stopped_today = set()   # BUG-04：当日止损出场票（禁止当日买回，次日起恢复）
        # 1) 盘中断价止损（V2：跳空按开盘，否则按止损价，均在 [low,high] 内）
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
            cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
            fees += pos[s]['qty'] * px * FEE_SIDE
            turnover += pos[s]['qty'] * px
            stopped_today.add(s)          # BUG-04：止损出场为终态，记入当日禁买回名单
            del pos[s]
        # 2) 止损/崩市挂出的清仓单：当根有K线则开盘卖出
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
                fees += pos[s]['qty'] * px * FEE_SIDE
                turnover += pos[s]['qty'] * px
                del pos[s]
            pending_sells.discard(s)
        # 3) 周调仓执行（信号次日开盘）
        if pending_exec is not None and t == pending_exec[0]:
            _, target, eq_sig = pending_exec
            pending_exec = None
            n_rebal += 1
            for s in list(pos):                        # 不在目标内 → 开盘卖出
                if s in target or s in pending_sells:
                    continue
                px = o_t.get(s, np.nan)
                if pd.isna(px):
                    pending_sells.add(s)
                    continue
                cash += pos[s]['qty'] * px * (1 - FEE_SIDE)
                fees += pos[s]['qty'] * px * FEE_SIDE
                turnover += pos[s]['qty'] * px
                del pos[s]
            for s in target:                           # 新开仓各 10% 信号日权益
                if s in pos or s in stopped_today:     # BUG-04：止损票当日禁止买回（不补买、不顺延）
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
        # 4) 收盘记账 + 资金费 0.03%/bar 按持仓名义
        equity = cash
        for s, p in pos.items():
            m = mark.at[t, s]
            equity += p['qty'] * m
            f = p['qty'] * m * FUNDING
            cash -= f
            fees += f
        eq[t] = equity
        hold[t] = ','.join(sorted(pos))          # G4 插桩：逐日持仓快照
        # 5) 崩市检查（信号日崩市则当周直接空仓）
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                and med_ret[t] < CRASH_MED:
            pending_sells.update(pos.keys())
        # 6) 周信号：算分、闸门、定目标
        if t in sig_days:
            score = cross_scores(F, syms, t, factors)
            if gated and not pd.isna(idx_ma.get(t, np.nan)) and idx[t] < idx_ma[t]:
                target = []
            else:
                target = list(score.index[:TOP_N])
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity) \
                if cal.get_loc(t) + 1 < len(cal) else None

    curve = pd.Series(eq).sort_index()
    return {'curve': curve, 'holdings': pd.Series(hold).sort_index(),
            'fees': fees, 'turnover': turnover,
            'n_rebal': n_rebal, 'start': str(cal[0].date()),
            'end': str(cal[-1].date()), 'n_sig': len(sig_days)}


# ---------------------------------------------------------------- 指标
def window_metrics(res, t0, t1):
    c = res['curve']
    seg = c[(c.index >= t0) & (c.index <= t1)]
    if len(seg) < 2:
        return {}
    days = (seg.index[-1] - seg.index[0]).days
    yrs = days / 365.25
    ann = (seg.iloc[-1] / seg.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1
    wk = seg.resample('W').last().pct_change().dropna()
    cash_wk = wk[wk.round(10) == 0]                       # 纯现金周（闸门/崩市清仓）
    act = wk[wk.round(10) != 0]                           # 实际持仓周
    dd = (seg / seg.cummax() - 1).min()
    fee_ann = res['fees'] / yrs / 1.0            # 权益基数为1，年化费拖累
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


def yearly_returns(curve):
    y = curve.resample('YE').last()
    r = y.pct_change().dropna()
    out = {str(k.year): round(v * 100, 2) for k, v in r.items()}
    first = y.index[0].year
    seg0 = curve[curve.index.year == first]
    out[str(first)] = round((seg0.iloc[-1] / seg0.iloc[0] - 1) * 100, 2)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- 主流程
def main():
    data = load_data()
    pools = build_pools(data)
    F = build_factors(data)
    print(f"池口径: old131={len(pools['old131'])}, full144={len(pools['full144'])}, "
          f"新增={len(set(pools['full144']) - set(pools['old131']))}")

    variants = [
        ('gated', True, FACTORS_4),
        ('ungated', False, FACTORS_4),
        ('gated_3factor_ablation', True, FACTORS_3),
    ]
    runs = {}
    for name, gated, factors in variants:
        runs[name] = {}
        for pname, syms in pools.items():
            r = run_backtest(data, F, syms, gated, factors)
            tr = window_metrics(r, r['curve'].index[0], TRAIN_END)
            ho = window_metrics(r, HOLD_START, r['curve'].index[-1])
            runs[name][pname] = {
                'meta': {'start': r['start'], 'end': r['end'],
                         'signal_days': r['n_sig'], 'rebalances': r['n_rebal']},
                'train': tr, 'holdout': ho,
                'yearly_return_pct': yearly_returns(r['curve']),
            }
            print(f"{name:24s} {pname:8s} train: ann={tr['annualized']:+7.2f}% "
                  f"win={tr['weekly_winrate_pct']:5.2f}% mdd={tr['mdd_pct']:6.2f}% | "
                  f"holdout: ann={ho['annualized']:+7.2f}% mdd={ho['mdd_pct']:6.2f}%")

    g, u = runs['gated'], runs['ungated']
    # 回撤差 = 带闸MDD - 无闸MDD（MDD为负值，差为正即带闸更浅）
    gate_dd = {p: round(g[p]['train']['mdd_pct'] - u[p]['train']['mdd_pct'], 2)
               for p in pools}
    gate_dd_ho = {p: round(g[p]['holdout']['mdd_pct'] - u[p]['holdout']['mdd_pct'], 2)
                  for p in pools}
    surv_gap = {w: round(g['old131'][w]['annualized'] - g['full144'][w]['annualized'], 2)
                for w in ('train', 'holdout')}
    crit = {
        'weekly_winrate_ge53_train_gated_old131': {
            'value_all_weeks': g['old131']['train']['weekly_winrate_pct'],
            'value_active_weeks': g['old131']['train']['weekly_winrate_active_pct'],
            'cash_weeks': g['old131']['train']['cash_weeks'],
            'note': '带闸清仓周收益恒为0，计入分母会机械压低胜率；以持仓周口径判pass',
            'pass': bool(g['old131']['train']['weekly_winrate_active_pct'] >= 53)},
        'annualized_ge10_train_gated_old131': {
            'value': g['old131']['train']['annualized'], 'pass':
            bool(g['old131']['train']['annualized'] >= 10)},
        'gate_mdd_diff_ge5pp_train': {'value': gate_dd, 'holdout': gate_dd_ho,
            'pass': bool(gate_dd['old131'] >= 5)},
        'yearly_consistency_gated_old131': runs['gated']['old131']['yearly_return_pct'],
        'survivorship_gap_old_minus_full_ann_pct': surv_gap,
        'survivorship_flag': ('幸存者偏差>=+14pp' if surv_gap['train'] >= 14
                              else f"幸存者偏差+{surv_gap['train']}pp(<14pp)"),
    }

    meta = {
        'workorder': 'W2-F1 多因子轮动框架首次回测 + 无闸门对照组（主管席R3终裁）',
        'seed': SEED,
        'data': '/tmp/box_cache/*.json 日K（time/open/high/low/close/volume），滚动700根缓存，起点2024-01-24',
        'pool_defs': {
            'old131': '首根K线<=2025-03-31（滚动缓存无法直接判别2024-01-24前上市，可复现代理口径，数量=工单131老票）',
            'full144': '截至2026-10-17有>=100根日K（约上市满5个月），数量=工单144全池',
        },
        'index_def': 'idx = 池内当日有K线标的的等权收盘均价（各池各自计算）',
        'factors': 'ma20_slope(MA20五日变化)/obv_slope20(OBV20日变化/均量归一)/dist_52w_high(距52周高点)/mom_1m(21日动量)；信号日横截面z-score(|z|<=3)等权合成',
        'rebalance': '每周首个交易日（多为周一，节假日顺延）收盘信号，次日开盘成交；top-5各10%（50%敞口）；跌出top-15保留其余换仓',
        'exits': '止损-8%硬截断（盘中触发，V2口径）；崩市=池单日中位跌幅<-5%次日开盘清仓；带闸变体另在信号日idx<MA50清仓持币',
        'costs': '换仓双边0.05%/边 + 资金费0.03%/bar按持仓名义',
        'accounting': 'V2可实现口径：成交价取当根open（天然在[low,high]内），止损跳空按open、触发按stop价',
        'split': '训练2024-01~2026-03（含因子/MA50预热，前期现金）；留出2026-04~2026-10只报告',
        'metrics_note': 'median=周收益中位数；周胜率=周收益>0占比；MDD=日内权益峰谷；换手=年化单边名义/权益；费拖累=年化总费用/权益',
    }
    out = {'meta': meta, 'runs': runs, 'criteria': crit}
    with open(os.path.join(OUT, 'f1_results.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if hasattr(o, 'item') else str(o))
    print('\n判据:', json.dumps(crit, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
