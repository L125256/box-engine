#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H-D 复活工单 · T2 vol20 状态门（首席终裁立项 · 2026-10-18）
================================================================
【规格出处（预注册，禁改判据）】
- /tmp/trade9_specs/DNEG_SPEC.md D4 H-D 条款：T2 状态变量=池等权 20 日已实现波动率
  （开工时预注册二选一已定，禁跑后换）；判据：后段 OFF 命中率 ≥80% 且 realA 误伤 ≤20%。
- /tmp/trade9_specs/DNEG_VERDICT.md 首席条 5 + 激进风险席条款：H-D 复活通道=以 realC
  伴行口径重判 D3（已坐实：<随机带 p5）+ T2 回测判据；判据不过同样归档。
- /workspace/repo_ready/research/wo_dneg/dneg_engine.py 文档头开工冻结：
  「T2 状态变量取『池等权 20 日已实现波动率』；阈值=realA 段该序列 80 分位（仅用
  realA 数据估计）；OFF=vol20>阈值；后段 OFF 命中率 = OFF 日中 F1 净日收益<0 占比
  ≥80%；realA 误伤率 = realA OFF 日占比 ≤20%。」

【本单冻结口径（开工即写死）】
- vol20 = 池等权收盘均价 idx（=引擎同源 idx）日收益的 20 日滚动标准差（ddof=1）
  × sqrt(252) 年化；逐池计算（old131 / full144 各自 idx 与各自阈值）。
- 阈值 = vol20 在 realA 段（2025-06-02→2026-03-31）的 80 分位，仅用 realA 数据。
- 门语义（停开新仓，不动引擎其他逻辑）：信号日收盘 vol20>阈值 → 次日执行跳过
  全部新开仓；账面冻结（不做换仓卖出，防「停开新仓」被扩大为清仓）——止损、
  崩市清仓、BUG-04 语义照常；门 ON 周引擎逐行原样。
- 判定（本单三判据，全部预注册/操作性定义显式声明）：
  C1【预注册·realC 伴行口径】realC OFF 命中率 = realC OFF 日中 base F1 净日收益<0
     占比 ≥80%（后段混合口径同表伴行呈报，不替代）。
  C2【预注册】realA 误伤率 = realA OFF 日占比 ≤20%。
  C3【工单·操作性定义显式声明】realC 避开止损绞肉主体：避损金额占比与避损笔数
     占比均 ≥50%（「主体」无预注册数值线，取多数，如实标注为操作性定义）。
  总判定 PASS = C1 ∧ C2 ∧ C3。
- 肥尾让渡账本（R5 终裁一普适义务）：肥尾=单笔实现收益率 r≥+8%，肥尾sum=段内
  平仓肥尾笔实现 pp 之和；让渡 = base 肥尾sum − 臂肥尾sum。
- 敏感性（披露用，不进判定）：①滞后门 vol20.shift(1)（决策滞后+1日）；
  ②清仓语义门（OFF 周清仓持币，MA50 闸同构）——标注「敏感性，非预注册门」。

【纪律】seed=42 冻结；数据 /tmp/box_cache 唯一快照禁换源；R8 全程 Pool(32)
并行（10 run ≈ 1 分钟）；一次成活禁调参；烧窗声明：本单未跑任何已烧毁止损参数。
"""
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, '/workspace/repo_ready/research/wo_dneg')
import dneg_engine as DE  # D0 已对拍 maxdiff=0 的仪表化引擎（权威谱系）

SEED = 42
CACHE = '/tmp/box_cache'
OUT = '/workspace/repo_ready/research/wo_hd'
os.makedirs(OUT, exist_ok=True)

REALA_START = pd.Timestamp('2025-06-02')
REALA_END = pd.Timestamp('2026-03-31')
HOLD_START = pd.Timestamp('2026-04-01')   # 后段起点
REALB_END = pd.Timestamp('2026-05-31')
REALC_START = pd.Timestamp('2026-06-01')

VOL_WIN = 20
VOL_Q = 0.80
FAT_R = 0.08            # 肥尾：单笔实现收益率 ≥ +8%（R5 终裁一 r≥8 口径）
FEE_SIDE = DE.FEE_SIDE

POOLS = ['old131', 'full144']

DATA = None
F = None
POOL_SYMS = None
VOL = None              # {pname: vol20 Series}
THR = None              # {pname: threshold}


# ------------------------------------------------------------- vol20 状态变量
def compute_vol20(data, syms):
    """池等权收盘均价 idx 的 20 日已实现波动率（年化）。idx 与引擎同源逐行一致。"""
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close = close.reindex(cal)
    idx = close.mean(axis=1)
    ret = idx.pct_change()
    vol = ret.rolling(VOL_WIN).std(ddof=1) * np.sqrt(252)
    return vol


# ------------------------------------------------------------- 门引擎（逐行复制+门）
def run_instr_gate(data, F=None, syms=None, vol20=None, thr=None, mode='pause',
                   lag=0):
    """逐行复制 dneg_engine.run_instr（W2-R14-G4 升版谱系），仅加 T2 vol20 状态门：
    【插入 1】信号日（步 6）：off_next = bool(vol20[t] > thr)（NaN→False，门开），
              pending_exec 携带 off_next（lag>0 时用 vol20.shift(lag)）。
    【插入 2】执行日（步 3）：off_next=True 时
              - mode='pause'（预注册门语义=停开新仓）：跳过换仓卖出环与开仓环，
                存量持仓不动，止损/崩市/BUG-04 照常（步 1/2/5 原样）；
              - mode='liquidate'（敏感性，非预注册）：target=[]，卖出环照跑=清仓持币。
    其余逐行未动；关闭门（vol20=None）时与 dneg_engine.run_instr 完全同构（D0 自检）。"""
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
    idx_ma = idx.rolling(DE.MA_REG).mean()
    med_ret = close.pct_change().median(axis=1)

    iso = cal.isocalendar()
    wk_groups = cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values()
    sig_days = set(wk_groups.values)

    if vol20 is not None:
        gser = vol20.shift(lag) if lag else vol20
        gate_map = (gser > thr).to_dict()          # NaN→False（门开）
    else:
        gate_map = None

    cash, pos = 1.0, {}
    pending_sells = set()
    pending_reason = {}
    pending_exec = None
    eq, hold = {}, {}
    fees = turnover = 0.0
    n_rebal = 0
    n_gate_off = 0
    stopped_today = set()

    trades = {}
    tid_seq = [0]
    last_mark = {}
    tid_of = {}
    day_rows = []
    rng = np.random.default_rng(SEED)

    def rec_open(s, t, px, qty):
        tid = tid_seq[0]; tid_seq[0] += 1
        trades[tid] = {'sym': s, 'open_date': str(t.date()), 'open_px': float(px),
                       'qty': float(qty), 'stop_px': float(px * (1 + DE.STOP)),
                       'entry_fee': float(qty * px * FEE_SIDE), 'exit_fee': 0.0,
                       'funding': 0.0, 'price_pnl': 0.0, 'gap_loss': 0.0,
                       'close_date': None, 'exit_px': None, 'exit_reason': None,
                       'stop_type': None}
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
            cash += q * px * (1 - FEE_SIDE)
            fees += q * px * FEE_SIDE
            turnover += q * px
            stopped_today.add(s)
            tid = tid_of[s]
            trades[tid]['gap_loss'] = float(q * (stop_p - o_t[s])) if o_t[s] < stop_p else 0.0
            trades[tid]['stop_type'] = 'gap' if o_t[s] < stop_p else 'intraday'
            rec_close(s, t, px, 'stop', q)
            del pos[s]
        # 2) 挂单清仓（原样）
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                q = pos[s]['qty']
                cash += q * px * (1 - FEE_SIDE)
                fees += q * px * FEE_SIDE
                turnover += q * px
                rec_close(s, t, px, pending_reason.get(s, 'crash'), q)
                del pos[s]
            pending_sells.discard(s)
            pending_reason.pop(s, None)
        # 3) 周调仓执行（原样 + 仅门插入 2）
        if pending_exec is not None and t == pending_exec[0]:
            _, target, eq_sig, off_next = pending_exec
            pending_exec = None
            n_rebal += 1
            if off_next:
                n_gate_off += 1
            if not (off_next and mode == 'pause'):     # 【门插入 2a】pause：跳过换仓卖出
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
                    rec_close(s, t, px, 'rebal', q)
                    del pos[s]
            if not off_next:                            # 【门插入 2b】OFF：停开新仓
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
                    cash -= qty * px * (1 + FEE_SIDE)
                    fees += qty * px * FEE_SIDE
                    turnover += qty * px
                    pos[s] = {'qty': qty, 'entry': px}
                    last_mark[s] = float(px)
                    rec_open(s, t, px, qty)
        # 4) 收盘记账 + 资金费（原样）
        equity = cash
        for s, p in pos.items():
            m = mark.at[t, s]
            equity += p['qty'] * m
            f = p['qty'] * m * DE.FUNDING
            cash -= f
            fees += f
            tid = tid_of[s]
            trades[tid]['funding'] -= float(f)
            trades[tid]['price_pnl'] += float(p['qty'] * (m - last_mark[s]))
            day_rows.append((t, s, tid, float(p['qty'] * (m - last_mark[s])),
                             0.0, -float(f), None, 0.0))
            last_mark[s] = m
        eq[t] = equity
        hold[t] = ','.join(sorted(pos))
        # 5) 崩市检查（原样）
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                and med_ret[t] < DE.CRASH_MED:
            for s in pos:
                pending_reason.setdefault(s, 'crash')
            pending_sells.update(pos.keys())
        # 6) 周信号（原样 + 仅门插入 1）
        if t in sig_days:
            score = DE.cross_scores(F, syms, t, DE.FACTORS_4)
            if gate_map is not None and gate_map.get(t, False):
                off_next = True
                target = [] if mode == 'liquidate' else list(score.index[:DE.TOP_N])
            else:
                off_next = False
                target = list(score.index[:DE.TOP_N])
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity, off_next) \
                if cal.get_loc(t) + 1 < len(cal) else None

    curve = pd.Series(eq).sort_index()
    end = cal[-1]
    for s, p in pos.items():        # eow 伪平仓（仅记录）
        tid = tid_of[s]
        trades[tid]['close_date'] = str(end.date())
        trades[tid]['exit_px'] = float(mark.at[end, s])
        trades[tid]['exit_reason'] = 'eow'
    return {'curve': curve, 'holdings': pd.Series(hold).sort_index(),
            'fees': fees, 'turnover': turnover, 'n_rebal': n_rebal,
            'n_gate_off': n_gate_off, 'start': str(cal[0].date()),
            'end': str(cal[-1].date()), 'n_sig': len(sig_days),
            'trades': trades, 'day_rows': day_rows}


# ------------------------------------------------------------- worker
def worker(task):
    pname, arm = task
    t0 = time.time()
    syms = POOL_SYMS[pname]
    if arm == 'base':
        res = DE.run_instr(DATA, F=F, syms=syms, gated=False, record=True)
        vol20 = thr = None
        lag = 0
    else:
        arm_map = {'gate_pause': ('pause', 0), 'gate_pause_lag': ('pause', 1),
                   'gate_liq': ('liquidate', 0), 'd0_check': (None, 0)}
        mode, lag = arm_map[arm]
        vol20, thr = VOL[pname], THR[pname]
        if mode is None:      # d0_check：门禁用，须与权威 run_instr 逐位一致
            res = run_instr_gate(DATA, F=F, syms=syms, vol20=None, thr=None)
            ref = DE.run_instr(DATA, F=F, syms=syms, gated=False, record=True)
            md = float((res['curve'] - ref['curve']).abs().max())
            fd = float(abs(res['fees'] - ref['fees']))
            return {'pname': pname, 'arm': arm, 'd0_maxdiff': md,
                    'd0_fees_absdiff': fd, 'secs': round(time.time() - t0, 1)}
        res = run_instr_gate(DATA, F=F, syms=syms, vol20=vol20, thr=thr,
                             mode=mode, lag=lag)
    out = {'pname': pname, 'arm': arm, 'secs': round(time.time() - t0, 1),
           'curve': {str(k.date()): float(v) for k, v in res['curve'].items()},
           'fees': float(res['fees']), 'turnover': float(res['turnover']),
           'n_rebal': int(res['n_rebal']), 'n_gate_off': int(res.get('n_gate_off', 0)),
           'trades': res['trades'],
           'day_rows': [(str(t.date()), s, tid, pp, fe, fu, ev, gp)
                        for (t, s, tid, pp, fe, fu, ev, gp) in res['day_rows']]}
    return out


# ------------------------------------------------------------- 段指标（八列）
def seg_metrics(r, t0, t1):
    curve = pd.Series({pd.Timestamp(k): v for k, v in r['curve'].items()}).sort_index()
    seg = curve[(curve.index >= t0) & (curve.index <= t1)]
    if len(seg) < 2:
        return {}
    yrs = (seg.index[-1] - seg.index[0]).days / 365.25
    ann = (seg.iloc[-1] / seg.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1
    wk = seg.resample('W').last().pct_change().dropna()
    act = wk[wk.abs() > 1e-10]
    mdd = (seg / seg.cummax() - 1).min()
    eq0 = float(seg.iloc[0])
    t0d, t1d = str(t0.date()), str(t1.date())
    rows = [x for x in r['day_rows'] if t0d <= x[0] <= t1d]
    fees_seg = sum(x[4] + x[5] for x in rows)
    notional = sum(x[4] / FEE_SIDE for x in rows
                   if x[6] == 'open' or str(x[6]).startswith('close:'))
    # 逐笔（按段内平仓归属）
    fat_sum = stop_n = 0
    stop_pp = gap_pp = 0.0
    for tr in r['trades'].values():
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
    return {'annualized_pct': round(ann * 100, 2),
            'mdd_pct': round(mdd * 100, 2),
            'weekly_winrate_pct': round((wk > 0).mean() * 100, 2),
            'weekly_winrate_active_pct': round((act > 0).mean() * 100, 2),
            'cash_weeks': int((wk.abs() <= 1e-10).sum()),
            'turnover_ann_x': round(notional / yrs / eq0, 2),
            'fee_drag_ann_pp': round(fees_seg / yrs / eq0 * 100, 2),
            'fat_tail_sum_pp': round(fat_sum, 2),
            'stop_trades_n': stop_n,
            'stop_realized_pp': round(stop_pp, 2),
            'stop_gap_loss_pp': round(gap_pp, 2),
            'total_return_pct': round((seg.iloc[-1] / seg.iloc[0] - 1) * 100, 2),
            'n_days': int(len(seg))}


# ------------------------------------------------------------- 门诊断
def gate_diag(pname, base_r):
    vol = VOL[pname]
    thr = THR[pname]
    off = (vol > thr).fillna(False)
    curve = pd.Series({pd.Timestamp(k): v for k, v in base_r['curve'].items()}).sort_index()
    ret = curve.pct_change()

    def seg_diag(t0, t1):
        o = off[(off.index >= t0) & (off.index <= t1)]
        r = ret[(ret.index >= t0) & (ret.index <= t1)]
        flips = int((o.astype(int).diff().abs() == 1).sum())
        eps = int((o.astype(int).diff() == 1).sum() + (1 if len(o) and o.iloc[0] else 0))
        off_days = o[o]
        hit = float((r[off_days.index] < 0).mean()) if len(off_days) else None
        return {'off_days': int(len(off_days)),
                'off_share_pct': round(len(off_days) / max(len(o), 1) * 100, 2),
                'off_episodes': eps,
                'flips': flips,
                'off_hit_rate_pct': None if hit is None else round(hit * 100, 2),
                'n_days': int(len(o))}

    return {'vol20_def': '池等权 idx 日收益 20 日滚动 std(ddof=1)×sqrt(252) 年化',
            'threshold_ann_vol_pct': round(float(thr) * 100, 2),
            'threshold_def': f'realA({REALA_START.date()}~{REALA_END.date()}) 段 p{int(VOL_Q*100)}，仅 realA 数据估计',
            'realA': seg_diag(REALA_START, REALA_END),
            'realB': seg_diag(HOLD_START, REALB_END),
            'realC': seg_diag(REALC_START, curve.index[-1]),
            'holdout': seg_diag(HOLD_START, curve.index[-1]),
            'full': seg_diag(curve.index[0], curve.index[-1])}


# ------------------------------------------------------------- 主流程
def main():
    global DATA, F, POOL_SYMS, VOL, THR
    t_start = time.time()
    DATA = DE.load_data(CACHE)
    pools = DE.build_pools(DATA)
    POOL_SYMS = pools
    F = DE.build_factors(DATA)

    VOL, THR = {}, {}
    for pname, syms in pools.items():
        v = compute_vol20(DATA, syms)
        VOL[pname] = v
        reala = v[(v.index >= REALA_START) & (v.index <= REALA_END)]
        THR[pname] = float(reala.quantile(VOL_Q))
        print(f"vol20[{pname}] realA p80 阈值 = {THR[pname]*100:.2f}% (年化) "
              f"realA n={len(reala.dropna())}")

    tasks = [(p, a) for p in POOLS
             for a in ('base', 'gate_pause', 'gate_pause_lag', 'gate_liq', 'd0_check')]
    with Pool(32) as pool:
        results = pool.map(worker, tasks)

    d0 = [r for r in results if r['arm'] == 'd0_check']
    runs = {(r['pname'], r['arm']): r for r in results if r['arm'] != 'd0_check'}
    for d in d0:
        print(f"D0 自检 {d['pname']}: 曲线 maxdiff={d['d0_maxdiff']} "
              f"fees |diff|={d['d0_fees_absdiff']}  {'PASS' if d['d0_maxdiff']==0 and d['d0_fees_absdiff']==0 else 'FAIL'}")

    segs = {'realA': (REALA_START, REALA_END),
            'realB': (HOLD_START, REALB_END),
            'realC': (REALC_START, pd.Timestamp('2026-10-17')),
            'holdout': (HOLD_START, pd.Timestamp('2026-10-17'))}
    table = {}
    for (pname, arm), r in runs.items():
        table[f'{pname}|{arm}'] = {sn: seg_metrics(r, t0, t1) for sn, (t0, t1) in segs.items()}

    # 门诊断（用 base 曲线的净日收益）
    diag = {p: gate_diag(p, runs[(p, 'base')]) for p in POOLS}

    # 让渡（肥尾账本）+ 避损台账
    ledger = {}
    for p in POOLS:
        b, g = table[f'{p}|base'], table[f'{p}|gate_pause']
        gl = table[f'{p}|gate_pause_lag']
        ledger[p] = {}
        for sn in segs:
            bb, gg, ll = b[sn], g[sn], gl[sn]
            # 避损 = base 损失 − gated 损失（gg − bb，正值=少亏；bb 为负损失额）
            avoid_pp = round(gg['stop_realized_pp'] - bb['stop_realized_pp'], 2)
            avoid_n = bb['stop_trades_n'] - gg['stop_trades_n']
            ledger[p][sn] = {
                'fat_tail_concession_pp': round(bb['fat_tail_sum_pp'] - gg['fat_tail_sum_pp'], 2),
                'avoided_stop_pp': avoid_pp,
                'avoided_stop_n': avoid_n,
                'avoided_stop_amount_share_pct':
                    round(avoid_pp / abs(bb['stop_realized_pp']) * 100, 2)
                    if bb['stop_realized_pp'] < 0 else None,
                'avoided_stop_count_share_pct':
                    round(avoid_n / bb['stop_trades_n'] * 100, 2) if bb['stop_trades_n'] else None,
                'lag_variant_avoided_stop_pp':
                    round(ll['stop_realized_pp'] - bb['stop_realized_pp'], 2),
                'lag_variant_avoided_stop_n': bb['stop_trades_n'] - ll['stop_trades_n']}

    # 预注册判定
    criteria = {}
    for p in POOLS:
        d = diag[p]
        led = ledger[p]['realC']
        c1_realC = d['realC']['off_hit_rate_pct'] is not None and d['realC']['off_hit_rate_pct'] >= 80
        c1_holdout = d['holdout']['off_hit_rate_pct'] is not None and d['holdout']['off_hit_rate_pct'] >= 80
        c2 = d['realA']['off_share_pct'] <= 20
        c3 = (led['avoided_stop_amount_share_pct'] or 0) >= 50 and \
             (led['avoided_stop_count_share_pct'] or 0) >= 50
        criteria[p] = {
            'C1_realC_off_hit_rate_ge80': {'value': d['realC']['off_hit_rate_pct'], 'pass': bool(c1_realC),
                                           'criterion': '预注册：OFF 日中 F1 净日收益<0 占比 ≥80%（realC 伴行口径）'},
            'C1_holdout_off_hit_rate_ge80_伴行': {'value': d['holdout']['off_hit_rate_pct'], 'pass': bool(c1_holdout),
                                                  'criterion': '后段混合口径伴行呈报（不替代 realC 口径）'},
            'C2_realA_false_trigger_le20': {'value': d['realA']['off_share_pct'],
                                            'off_days': d['realA']['off_days'],
                                            'off_episodes': d['realA']['off_episodes'],
                                            'pass': bool(c2),
                                            'criterion': '预注册：realA OFF 日占比 ≤20%'},
            'C3_realC_avoid_grinding_majority': {'value': {'amount_share_pct': led['avoided_stop_amount_share_pct'],
                                                           'count_share_pct': led['avoided_stop_count_share_pct']},
                                                 'pass': bool(c3),
                                                 'criterion': '工单：避开止损绞肉主体（避损金额与笔数占比均≥50%，操作性定义显式声明）'},
        }
        criteria[p]['OVERALL'] = 'PASS' if (c1_realC and c2 and c3) else 'FAIL'

    out = {'meta': {
        'workorder': 'H-D 复活工单：T2 vol20 状态门（首席终裁立项，判据预注册未烧毁）',
        'spec': '/tmp/trade9_specs/DNEG_SPEC.md D4-H-D + DNEG_VERDICT.md 首席条5/激进风险席/保守风险席条款',
        'preregistered_gate': 'dneg_engine.py 文档头开工冻结：T2=池等权20日已实现波动率；阈值=realA p80；OFF=vol20>阈值；后段OFF命中率≥80% 且 realA 误伤率≤20%',
        'gate_semantics': 'OFF=停开新仓（pause：跳过开仓与换仓卖出，存量仓止损/崩市/BUG-04 照常；非清仓）',
        'seed': SEED, 'data': CACHE, 'engine_lineage': 'research/wo_dneg/dneg_engine.py（D0 对拍 maxdiff=0 权威谱系）',
        'parallel': 'Pool(32)，10 run', 'wall_secs': round(time.time() - t_start, 1),
        'thresholds_ann_vol_pct': {p: round(THR[p] * 100, 2) for p in POOLS},
        'd0_selfcheck': d0,
        'burn_note': '本单未触碰已烧毁止损参数（无止损/-12%/trailing）；判据一次成活禁调参',
    }, 'gate_diag': diag, 'eight_col_table': table,
        'avoid_fat_ledger': ledger, 'criteria': criteria}

    with open(os.path.join(OUT, 'wo_hd_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if hasattr(o, 'item') else str(o))

    # 逐笔台账 CSV（base / gate_pause 双池）
    hdr = ['sym', 'open_date', 'open_px', 'qty', 'stop_px', 'close_date', 'exit_px',
           'exit_reason', 'stop_type', 'gap_loss', 'realized_pp']
    for (pname, arm), r in runs.items():
        if arm not in ('base', 'gate_pause'):
            continue
        with open(os.path.join(OUT, f'trade_ledger_{arm}_{pname}.csv'), 'w') as f:
            f.write(','.join(hdr) + '\n')
            for tr in sorted(r['trades'].values(), key=lambda x: (x['close_date'] or 'z', x['sym'])):
                pnl = (tr['price_pnl'] + tr['entry_fee'] + tr['exit_fee'] + tr['funding']) * 100
                f.write(f"{tr['sym']},{tr['open_date']},{tr['open_px']:.6g},{tr['qty']:.6g},"
                        f"{tr['stop_px']},{tr['close_date']},{tr['exit_px']},{tr['exit_reason']},"
                        f"{tr['stop_type']},{tr['gap_loss']:.6g},{pnl:.4f}\n")

    print(f"\n总耗时 {out['meta']['wall_secs']}s")
    for p in POOLS:
        print(f"\n===== {p}（阈值 {THR[p]*100:.2f}% 年化）=====")
        d = diag[p]
        print(f"realA 误伤率 OFF={d['realA']['off_share_pct']}% ({d['realA']['off_days']}天/"
              f"{d['realA']['off_episodes']}次) | realC OFF命中率={d['realC']['off_hit_rate_pct']}% "
              f"(OFF {d['realC']['off_days']}天) | 后段 OFF命中率={d['holdout']['off_hit_rate_pct']}%")
        for arm in ('base', 'gate_pause'):
            for sn in ('realA', 'realC'):
                m = table[f'{p}|{arm}'][sn]
                print(f"{arm:11s} {sn:6s} ann={m['annualized_pct']:+8.2f}% mdd={m['mdd_pct']:7.2f}% "
                      f"win={m['weekly_winrate_pct']:6.2f}% stop_n={m['stop_trades_n']:3d} "
                      f"stop_pp={m['stop_realized_pp']:+8.2f} fat={m['fat_tail_sum_pp']:+8.2f}")
        print(f"判定: {criteria[p]['OVERALL']}  {json.dumps({k: v for k, v in criteria[p].items() if k != 'OVERALL'}, ensure_ascii=False)}")


if __name__ == '__main__':
    main()
