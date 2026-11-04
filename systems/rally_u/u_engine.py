# -*- coding: utf-8 -*-
"""U 平衡 + 集群≥3 · 独立起涨点系统引擎（只研究，不下单，不发布）

入场（信号日收盘出信号，次日开盘）：
  A 质量版：dev20 <= -8%、RSI2 <= 40、ATR >= 6%、最低价跌破前 10 日低、
            量比 >= 0.8、dv20 >= 3000 万、价格 >= 5；5 根内收回前 10 日低，
            收盘位置 >= 0.4；同标的 5 根内只取一次。
  B+ 覆盖版：dev20 <= -5%、RSI2 <= 50、ATR >= 4%、量比 >= 0.5、
            8 根内收回、收阳；其余相同。
  市场层：120 只个股中收盘在 MA50 上方的比例 <= 34%。
  个股层：A 信号要求当日振幅 >= 7%；B 信号要求当日涨幅 >= 7%。
  合并：A/B 合并，同标的 5 根内只留一个，A 优先。
  集群确认（2026-11-05 加严）：同日 A 信号 >= 3 且 同日 B 信号 >= 20。
  有效止损：60 日低点到入场价 2%-60%。

出场：
  50% +12%、50% +30%，+30% 是最终硬止盈；
  连续 3 根收盘跌破 60 日低点，第 3 根收盘走；
  -30% 灾难上限；最多 60 根；跳空按开盘；先止损后止盈（保守）。
  成本单边 0.10%，资金费 0.03%/日。

仓位：
  1% 权益风险/笔，名义 = 1% / 结构止损距离；单仓名义上限 20% 权益；
  5x，保证金 = 名义/5；最多 16 仓；同日最多 5 仓；毛敞口 <= 2.5x。
"""
import os
import sys
import numpy as np
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # repo_new/systems/rally_u -> work
if not os.environ.get('V2_CACHE'):
    os.environ['V2_CACHE'] = os.path.join(WORK, 'cache_fresh')
for _p in (os.path.join(WORK, 'v2', 'engine'),
           os.path.join(WORK, 'v2'),
           os.path.join(WORK, 'repo_new', 'systems', 'fd1'),
           HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import v2_lib as L
import strategy as FD

START_DATE = '2025-06-01'
MIN_PX = 5.0
MIN_DV = 30e6
DEV_A, RSI_A, ATR_A, VOL_A, WIN_A = -0.08, 40.0, 0.06, 0.8, 5
DEV_B, RSI_B, ATR_B, VOL_B, WIN_B = -0.05, 50.0, 0.04, 0.5, 8
BREADTH_MAX = 0.34
RANGE_MIN = 0.07
RET1_MIN = 0.07
CLUSTER_MIN = 3
# 集群家数的固定扫描起点（根）：保证「同日 A/B 家数」是与 start_date 无关的收盘可复现值
FIX_SCAN_I0 = 220
# 2026-11-05 加严：同日 B 层（宽松弹簧）家数下限。U 没有模型分，这是它唯一
# 能挡住 2025-03 型阴跌的市场级条件；A≥3 单独用挡不住（3 月留下 20-33 笔，
# 组合回撤仍 -24%~-29%），B≥20 只漏 2 笔。依据 work/COLD_DODGE_2026-11-05.md 第 14 节。
CLUSTER_B_MIN = 20
MIN_RISK, MAX_RISK = 0.02, 0.60
TP1, TP2 = 0.12, 0.30
CONFIRM, HARD, HOLD = 3, 0.30, 60
COST, FUND = 0.001, 0.0003
RISK_PCT, MAX_NOTIONAL = 0.01, 0.20
LEV, MAX_POS, MAX_DAY, GROSS = 5.0, 16, 5, 2.5
START_EQ = 100000.0

TIERS = ('A', 'B')


def spring_scan(A, F, cal, i0, dev_max, rsi_max, atr_min, vol_min, win,
                cpos_min=0.4, green=False):
    """洗盘弹簧扫描；返回信号日 i，不做到次日开盘的映射。"""
    out = []
    for s, b in A.items():
        if s in L.ETF or s in L.LEV:
            continue
        c, o, h, l, v = b['c'], b['o'], b['h'], b['l'], b['v']
        n = len(c); f = F[s]
        lo10 = np.full(n, np.nan); vm = np.full(n, np.nan)
        for i in range(i0, n):
            if i >= 11:
                lo10[i] = np.min(l[i - 10:i])
            if i >= 21:
                vm[i] = np.median(v[i - 20:i])
        lw = -99; ls = -99
        for i in range(i0, n):
            if not b['real'][i] or i - b['first'] < 220 or b['jump'][i]:
                continue
            if c[i] < MIN_PX or f['dv20'][i] < MIN_DV:
                continue
            if not np.isfinite(lo10[i]) or not np.isfinite(vm[i]) or vm[i] <= 0:
                continue
            isw = (f['dev20'][i] <= dev_max and f['rsi2'][i] <= rsi_max
                   and f['atrp'][i] >= atr_min and l[i] < lo10[i]
                   and v[i] / vm[i] >= vol_min)
            if isw:
                lw = i
            cpos = (c[i] - l[i]) / max(h[i] - l[i], 1e-9)
            if 0 <= i - lw <= win and c[i] > lo10[i] and cpos >= cpos_min and i - ls >= 5:
                if green and not (c[i] > o[i]):
                    continue
                ls = i
                out.append(dict(sym=s, i=i, date=cal[i], atr=float(f['atrp'][i]),
                                volx=float(v[i] / vm[i]), dev=float(f['dev20'][i]),
                                rsi=float(f['rsi2'][i]), cpos=float(cpos),
                                gap_wash=int(i - lw)))
    return out


def enrich(A, z, tag, breadth, concA, concB=None):
    i = z['i']; b = A[z['sym']]
    c, h, l = b['c'], b['h'], b['l']
    z['tag'] = tag
    z['range_pct'] = float((h[i] - l[i]) / max(c[i], 1e-9))
    z['ret1'] = float(c[i] / c[i - 1] - 1) if i >= 1 else 0.0
    z['breadth'] = float(breadth[i]) if np.isfinite(breadth[i]) else 1.0
    z['concA'] = int(concA.get(z['date'], 0))
    if concB is not None:
        z['concB'] = int(concB.get(z['date'], 0))
    return z


def _prep(A, cal, z):
    """信号日 -> 次日开盘、60 日低点、止损距离；无效结构返回 None。"""
    b = A[z['sym']]; i = z['i']; n = len(b['c']); e = i + 1
    while e < n and (not b['real'][e] or b['jump'][e]):
        e += 1
    if e >= n:
        return None
    ep = float(b['o'][e])
    if ep <= 0:
        return None
    stop = float(np.min(b['l'][max(0, i - 60):i]))
    risk = (ep - stop) / ep
    if not (MIN_RISK <= risk <= MAX_RISK):
        return None
    z = dict(z)
    z.update(e=e, entry=ep, entry_date=cal[e], stop=stop, risk=float(risk))
    return z


def build_signals(A, F, RG, cal, start_date=START_DATE, scan_i0=FIX_SCAN_I0):
    """返回 (signals, meta)。signals 为 U 平衡 + 集群 A>=3 且 B>=CLUSTER_B_MIN。

    集群家数（concA/concB）固定从 scan_i0 起算，不随 start_date 变化：
    否则同一天在「研究起点」和「页面起点」下会算出不同的家数，闸门就不是一个
    收盘可复现的数了。交易清单仍然只取 i >= start_date 对应根。
    """
    core = {s: b for s, b in A.items() if s not in L.ETF and s not in L.LEV}
    gr = next(i for i, d in enumerate(cal) if d >= start_date)
    i0 = min(scan_i0, gr)
    BR = L.breadth(core, F, cal)[0]
    sigA_all = spring_scan(A, F, cal, i0, DEV_A, RSI_A, ATR_A, VOL_A, WIN_A)
    sigB_all = spring_scan(A, F, cal, i0, DEV_B, RSI_B, ATR_B, VOL_B, WIN_B, green=True)
    concA = Counter(z['date'] for z in sigA_all)
    concB = Counter(z['date'] for z in sigB_all)
    sigA = [z for z in sigA_all if z['i'] >= gr]
    sigB = [z for z in sigB_all if z['i'] >= gr]
    for z in sigA:
        enrich(A, z, 'A', BR, concA, concB)
    for z in sigB:
        enrich(A, z, 'B', BR, concA, concB)

    # 先做有效止损，再做合并去重；否则 2% 以下的无效 A 会挡住有效的 B
    candA = [z for z in sigA if z['breadth'] <= BREADTH_MAX and z['range_pct'] >= RANGE_MIN]
    candB = [z for z in sigB if z['breadth'] <= BREADTH_MAX and z['ret1'] >= RET1_MIN]
    candA = [z for z in ( _prep(A, cal, x) for x in candA ) if z is not None]
    candB = [z for z in ( _prep(A, cal, x) for x in candB ) if z is not None]

    keep = sorted(candA, key=lambda z: (z['sym'], z['i']))
    for z in sorted(candB, key=lambda z: (z['sym'], z['i'])):
        if any(q['sym'] == z['sym'] and abs(q['i'] - z['i']) <= 5 for q in keep):
            continue
        keep.append(z)
    n_pre_cluster = len(keep)
    keep = [z for z in keep if z['concA'] >= CLUSTER_MIN and z['concB'] >= CLUSTER_B_MIN]
    keep.sort(key=lambda z: (z['i'], z['sym']))

    meta = dict(asof=cal[-1], nA_raw=len(sigA), nB_raw=len(sigB),
                nA_scan=len(sigA_all), nB_scan=len(sigB_all), scan_i0=int(i0),
                nA_tier=len(candA), nB_tier=len(candB), nU=len(keep),
                n_pre_cluster=n_pre_cluster,
                cluster_min=CLUSTER_MIN, cluster_b_min=CLUSTER_B_MIN,
                start_date=start_date)
    return keep, meta


def simulate(A, z, gap_open=True):
    """单笔两段式出场；gap_open=True 时跳空止盈按开盘价成交。"""
    b = A[z['sym']]; e = z['e']; ep = z['entry']; n = len(b['c'])
    end = min(n - 1, e + HOLD)
    tp1 = ep * (1 + TP1); tp2 = ep * (1 + TP2); stop = z['stop']
    r1 = r2 = None; w1 = w2 = None; b1 = b2 = None; below = 0
    for k in range(e, end + 1):
        if k > e:
            op = float(b['o'][k])
            if op <= ep * (1 - HARD):
                if r1 is None:
                    r1 = op / ep - 1 - 2 * COST - FUND * (k - e); w1 = 'hard_gap'; b1 = k - e
                if r2 is None:
                    r2 = op / ep - 1 - 2 * COST - FUND * (k - e); w2 = 'hard_gap'; b2 = k - e
                break
            if r1 is None and op >= tp1:
                fill = op / ep - 1 if gap_open else TP1
                r1 = fill - 2 * COST - FUND * (k - e); w1 = 'tp1_gap'; b1 = k - e
            if r2 is None and op >= tp2:
                fill = op / ep - 1 if gap_open else TP2
                r2 = fill - 2 * COST - FUND * (k - e); w2 = 'tp2_gap'; b2 = k - e
        lo, hi, cl = float(b['l'][k]), float(b['h'][k]), float(b['c'][k])
        if lo <= ep * (1 - HARD):
            if r1 is None:
                r1 = -HARD - 2 * COST - FUND * (k - e); w1 = 'hard'; b1 = k - e
            if r2 is None:
                r2 = -HARD - 2 * COST - FUND * (k - e); w2 = 'hard'; b2 = k - e
            break
        if r1 is None and hi >= tp1:
            r1 = TP1 - 2 * COST - FUND * (k - e); w1 = 'tp1'; b1 = k - e
        if r2 is None and hi >= tp2:
            r2 = TP2 - 2 * COST - FUND * (k - e); w2 = 'tp2'; b2 = k - e
        if cl < stop:
            below += 1
        else:
            below = 0
        if below >= CONFIRM:
            if r1 is None:
                r1 = cl / ep - 1 - 2 * COST - FUND * (k - e); w1 = 'stop_close'; b1 = k - e
            if r2 is None:
                r2 = cl / ep - 1 - 2 * COST - FUND * (k - e); w2 = 'stop_close'; b2 = k - e
            break
        if k == end:
            if r1 is None:
                r1 = cl / ep - 1 - 2 * COST - FUND * (k - e); w1 = 'time'; b1 = k - e
            if r2 is None:
                r2 = cl / ep - 1 - 2 * COST - FUND * (k - e); w2 = 'time'; b2 = k - e
            break
    if r1 is None or r2 is None:
        return None
    return dict(ret=0.5 * r1 + 0.5 * r2, why1=w1, why2=w2, bars=max(b1, b2))


def stats(rows):
    if not rows:
        return dict(n=0, win=0.0, avg=0.0, med=0.0, pf=0.0, payoff=0.0,
                    avgR=0.0, worst=0.0, best=0.0, sum=0.0)
    p = np.array([r['ret'] for r in rows], float)
    w = p[p > 0]; l = p[p <= 0]
    rm = np.array([r['ret'] / r['risk'] for r in rows if r['risk'] > 0], float)
    return dict(n=len(rows), win=round(float((p > 0).mean() * 100), 1),
                avg=round(float(p.mean() * 100), 2),
                med=round(float(np.median(p) * 100), 2),
                pf=round(float(w.sum() / max(-l.sum(), 1e-9)), 2),
                payoff=round(float(w.mean() / abs(l.mean())), 2) if len(w) and len(l) else 0.0,
                avgR=round(float(rm.mean()), 2) if len(rm) else 0.0,
                worst=round(float(p.min() * 100), 1),
                best=round(float(p.max() * 100), 1),
                sum=round(float(p.sum() * 100), 1))


def run_window(A, cal, sig, start_date, rank='range', max_day=MAX_DAY,
               max_pos=MAX_POS, max_notional=MAX_NOTIONAL, risk_pct=RISK_PCT,
               gross_cap=GROSS):
    """三窗口实盘组合模拟；窗口首个交易日空仓。"""
    n = len(cal)
    start_i = next(i for i, d in enumerate(cal) if d >= start_date)
    keyf = {
        'range': lambda z: (-z['range_pct'], -z['ret1'], z['sym']),
        'ret1': lambda z: (-z['ret1'], -z['range_pct'], z['sym']),
        'risk': lambda z: (z['risk'], -z['range_pct'], z['sym']),
        'sym': lambda z: (z['sym'],),
        'atr': lambda z: (-z['atr'], -z['range_pct'], z['sym']),
    }[rank]
    by = defaultdict(list)
    for x in sig:
        if x['e'] >= start_i:
            by[x['e']].append(x)
    for k in by:
        by[k].sort(key=keyf)

    eq = 1.0
    curve = np.full(n, np.nan)
    curve[:start_i] = 1.0
    pos = {}
    trades = []
    skipped_cap = skipped_gross = skipped_dup = 0
    taken = 0

    for i in range(start_i, n):
        for s in list(pos):
            q = pos[s]; b = A[s]
            if i <= q['e'] or b['jump'][i]:
                continue
            op = float(b['o'][i]); lo = float(b['l'][i]); hi = float(b['h'][i]); cl = float(b['c'][i])
            q['fund'] += q['notional'] * FUND * (q['wt1'] * q['o1'] + q['wt2'] * q['o2'])
            if op <= q['ep'] * (1 - HARD):
                for leg in (1, 2):
                    if q['o%d' % leg]:
                        q['pnl'] += q['wt%d' % leg] * q['notional'] * (op / q['ep'] - 1) - q['wt%d' % leg] * q['notional'] * COST
                        q['o%d' % leg] = False; q['w%d' % leg] = 'hard_gap'; q['b%d' % leg] = i - q['e']
            if q['o1'] and op >= q['ep'] * (1 + TP1):
                q['pnl'] += q['wt1'] * q['notional'] * (op / q['ep'] - 1) - q['wt1'] * q['notional'] * COST
                q['o1'] = False; q['w1'] = 'tp1_gap'; q['b1'] = i - q['e']
            if q['o2'] and op >= q['ep'] * (1 + TP2):
                q['pnl'] += q['wt2'] * q['notional'] * (op / q['ep'] - 1) - q['wt2'] * q['notional'] * COST
                q['o2'] = False; q['w2'] = 'tp2_gap'; q['b2'] = i - q['e']
            if lo <= q['ep'] * (1 - HARD):
                for leg in (1, 2):
                    if q['o%d' % leg]:
                        q['pnl'] += q['wt%d' % leg] * q['notional'] * (-HARD) - q['wt%d' % leg] * q['notional'] * COST
                        q['o%d' % leg] = False; q['w%d' % leg] = 'hard'; q['b%d' % leg] = i - q['e']
            if q['o1'] and hi >= q['ep'] * (1 + TP1):
                q['pnl'] += q['wt1'] * q['notional'] * TP1 - q['wt1'] * q['notional'] * COST
                q['o1'] = False; q['w1'] = 'tp1'; q['b1'] = i - q['e']
            if q['o2'] and hi >= q['ep'] * (1 + TP2):
                q['pnl'] += q['wt2'] * q['notional'] * TP2 - q['wt2'] * q['notional'] * COST
                q['o2'] = False; q['w2'] = 'tp2'; q['b2'] = i - q['e']
            if cl < q['stop']:
                q['below'] += 1
            else:
                q['below'] = 0
            if q['below'] >= CONFIRM:
                for leg in (1, 2):
                    if q['o%d' % leg]:
                        q['pnl'] += q['wt%d' % leg] * q['notional'] * (cl / q['ep'] - 1) - q['wt%d' % leg] * q['notional'] * COST
                        q['o%d' % leg] = False; q['w%d' % leg] = 'stop_close'; q['b%d' % leg] = i - q['e']
            if i >= q['e'] + HOLD:
                for leg in (1, 2):
                    if q['o%d' % leg]:
                        q['pnl'] += q['wt%d' % leg] * q['notional'] * (cl / q['ep'] - 1) - q['wt%d' % leg] * q['notional'] * COST
                        q['o%d' % leg] = False; q['w%d' % leg] = 'time'; q['b%d' % leg] = i - q['e']
            if not q['o1'] and not q['o2']:
                q['pnl'] -= q['fund']
                eq += q['pnl']
                trades.append(dict(
                    sym=s, signal_date=q['sig'], entry_date=cal[q['e']], exit_date=cal[i],
                    entry=q['ep'], stop=q['stop'], risk_pct=q['risk'] * 100,
                    notional_pct=q['notional'] / q['eq_entry'] * 100,
                    pnl_eq_pct=q['pnl'] / q['eq_entry'] * 100,
                    ret_notional_pct=q['pnl'] / q['notional'] * 100,
                    bars=max(q['b1'], q['b2']), w1=q['w1'], w2=q['w2']))
                del pos[s]

        mtm = 0.0
        for s, q in pos.items():
            rem = q['wt1'] * q['o1'] + q['wt2'] * q['o2']
            mtm += q['pnl'] + rem * q['notional'] * (float(A[s]['c'][i]) / q['ep'] - 1) - q['fund']
        eq_cur = eq + mtm

        new_today = 0
        for x in by.get(i, []):
            s = x['sym']
            if s in pos:
                skipped_dup += 1
                continue
            if len(pos) >= max_pos or new_today >= max_day:
                skipped_cap += 1
                continue
            b = A[s]
            if not b['real'][i] or b['jump'][i]:
                continue
            ep = float(b['o'][i])
            if ep <= 0:
                continue
            risk = (ep - x['stop']) / ep
            if risk <= 0:
                continue
            gross_now = sum(q['notional'] for q in pos.values())
            notional = min(risk_pct * eq_cur / risk, max_notional * eq_cur, gross_cap * eq_cur - gross_now)
            if notional < 0.01 * eq_cur:
                skipped_gross += 1
                continue
            pos[s] = dict(e=i, ep=ep, notional=notional, risk=risk, stop=x['stop'],
                          wt1=0.5, wt2=0.5, w1=None, w2=None, o1=True, o2=True, below=0,
                          pnl=-notional * COST, fund=0.0, b1=None, b2=None,
                          sig=x['date'], eq_entry=eq_cur)
            taken += 1
            new_today += 1

        mtm = 0.0
        for s, q in pos.items():
            rem = q['wt1'] * q['o1'] + q['wt2'] * q['o2']
            mtm += q['pnl'] + rem * q['notional'] * (float(A[s]['c'][i]) / q['ep'] - 1) - q['fund']
        curve[i] = eq + mtm

    if pos:
        i = n - 1
        for s, q in list(pos.items()):
            rem = q['wt1'] * q['o1'] + q['wt2'] * q['o2']
            q['pnl'] += rem * q['notional'] * (float(A[s]['c'][i]) / q['ep'] - 1) - rem * q['notional'] * COST - q['fund']
            eq += q['pnl']
            if q['o1']:
                q['o1'] = False; q['w1'] = 'eow'
            if q['o2']:
                q['o2'] = False; q['w2'] = 'eow'
            trades.append(dict(
                sym=s, signal_date=q['sig'], entry_date=cal[q['e']], exit_date=cal[i],
                entry=q['ep'], stop=q['stop'], risk_pct=q['risk'] * 100,
                notional_pct=q['notional'] / q['eq_entry'] * 100,
                pnl_eq_pct=q['pnl'] / q['eq_entry'] * 100,
                ret_notional_pct=q['pnl'] / q['notional'] * 100,
                bars=max(q['b1'] or (i - q['e']), q['b2'] or (i - q['e'])),
                w1=q['w1'], w2=q['w2']))
            del pos[s]
        curve[i] = eq

    last = 1.0
    for i in range(n):
        if np.isnan(curve[i]):
            curve[i] = last
        else:
            last = curve[i]

    ret = float(curve[n - 1] / curve[start_i - 1] - 1) if start_i > 0 else float(curve[n - 1] - 1)
    days = max((np.datetime64(cal[n - 1]) - np.datetime64(cal[start_i])).astype(int), 1)
    cagr = (1 + ret) ** (365.0 / days) - 1 if ret > -1 else -1
    peak = np.maximum.accumulate(curve[start_i:])
    mdd = float(np.min(curve[start_i:] / peak - 1))
    p = np.array([t['pnl_eq_pct'] for t in trades], float) / 100
    wins = p[p > 0]; losses = p[p <= 0]
    st = dict(n=len(trades), win=round(float((p > 0).mean() * 100), 1) if len(p) else 0.0,
              avg=round(float(p.mean() * 100), 2) if len(p) else 0.0,
              pf=round(float(wins.sum() / max(-losses.sum(), 1e-9)), 2) if len(p) else 0.0,
              ret=round(ret * 100, 2), cagr=round(cagr * 100, 1), mdd=round(mdd * 100, 2),
              final_eq=round(float(curve[n - 1] * START_EQ), 2))
    months = {}
    for m in sorted({cal[i][:7] for i in range(start_i, n)}):
        idx = [i for i in range(start_i, n) if cal[i][:7] == m]
        if idx:
            base = curve[idx[0] - 1] if idx[0] > 0 else 1.0
            months[m] = round((curve[idx[-1]] / base - 1) * 100, 2)
    return dict(start=cal[start_i], end=cal[n - 1],
                signals=sum(len(v) for v in by.values()), taken=taken,
                skipped_cap=skipped_cap, skipped_gross=skipped_gross,
                skipped_dup=skipped_dup, stats=st, monthly=months,
                trades=trades, final_curve=round(float(curve[n - 1]), 4))
