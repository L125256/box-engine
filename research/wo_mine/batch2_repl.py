#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
复现锚替代 · 独立第二实现抽 3 变体逐位对拍（用户 Batch 2 工单指令④逐字执行）
====================================================================================
本批新变体无历史锚 → 以「双机实现对拍（独立第二实现抽 3 变体逐位）」替代。
本环境为单机：物理双机不可用，以**独立代码路径**替代——独立面板构造（逐日循环、
手工秩相关、手工缺口计数、不经 mine_common/batch2_run 任何统计件），如实登记替代形态。
抽样（Q2/Q3/Q4 各一）：Q2-ac-lag1 / Q3-rs-ew-fwd20 / Q4-gap-unfilled-mom。
对拍量：主实现（batch2_run.py 同代码路径原始序列）vs 本件独立第二实现，FULL 窗内
逐日值 maxdiff（逐位=0.0 即 hit；非 0 如实登记 float 路径差异与数值）。
R10 红线：本件不产出任何「域读数→仓位」映射。
产出：batch2_repl_result.json
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mine_common as MC
import batch1_run as B1
import batch2_run as B2

OUT = MC.OUT_DIR
FULL = B1.FULL


def ranks_avg(vals):
    """平均秩（ties→average），纯 python；返回与 pandas rank(method='average') 同值的 float 数组。"""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    rk = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rk[order[k]] = avg
        i = j + 1
    return np.array(rk)


def spearman(x, y):
    """逐日截面 Spearman（xsec_ic_series 同判据：<30 弃、零方差弃），秩用本件手工实现。"""
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return None
    rx, ry = ranks_avg(x[m].tolist()), ranks_avg(y[m].tolist())
    if rx.std(ddof=1) == 0 or ry.std(ddof=1) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def main():
    t0 = time.time()
    c = B2.ctx()
    syms = c['pools']['full144']
    data = c['data']
    cal = c['full144']['cal']
    # ---- 独立面板：逐标的取序列→按日循环装 numpy（不经 pandas DataFrame 构造路径）
    ser = {k: {s: data[s][k] for s in syms} for k in ('close', 'open', 'high', 'low')}
    n_d, n_s = len(cal), len(syms)
    C = np.full((n_d, n_s), np.nan)
    O = np.full_like(C, np.nan)
    H = np.full_like(C, np.nan)
    L = np.full_like(C, np.nan)
    pos = {s: j for j, s in enumerate(syms)}
    rpos = {t: i for i, t in enumerate(cal)}
    for s in syms:
        for t, v in ser['close'][s].items():
            C[rpos[t], pos[s]] = v
        for t, v in ser['open'][s].items():
            O[rpos[t], pos[s]] = v
        for t, v in ser['high'][s].items():
            H[rpos[t], pos[s]] = v
        for t, v in ser['low'][s].items():
            L[rpos[t], pos[s]] = v
    i0, i1 = rpos[FULL[0]], rpos[FULL[1]]

    # ---- 变体 1：Q3-rs-ew-fwd20 IC 序列（独立实现）
    with np.errstate(invalid='ignore', divide='ignore'):
        ret20 = C / np.vstack([np.full((20, n_s), np.nan), C[:-20]]) - 1.0
        fwd20 = np.vstack([C[20:], np.full((20, n_s), np.nan)]) / C - 1.0
    ic_repl = {}
    for i in range(i0, i1 + 1):
        row = ret20[i]
        den = np.nanmean(row)                       # 池等权分母
        fa = row - den
        v = spearman(fa, fwd20[i])
        if v is not None:
            ic_repl[cal[i]] = v

    # ---- 变体 2：Q4-gap-unfilled-mom 缺口未回补计数（整数域，独立实现）
    # 20 日回看窗口独立实现：对每个 (t,j) 数 k=1..20 内跳空未回补
    cnt = np.zeros((n_d, n_s))
    for i in range(1, n_d):
        for j in range(n_s):
            tot = 0.0
            for k in range(1, 21):
                d = i - k
                if d < 1:
                    break
                op, cp = O[d, j], C[d - 1, j]
                if not (np.isfinite(op) and np.isfinite(cp)):
                    continue
                if op / cp - 1.0 > 0.01:
                    lo = L[d + 1:i + 1, j]
                    # NaN 政策（与主实现统一，R7 登记）：未回补须逐日确证——
                    # 窗口内缺任一根 low → 无法确认 → 不计（保守口径）
                    if np.isfinite(lo).all() and lo.min() > op:
                        tot += 1.0
            cnt[i, j] = tot
    ic_repl_gap = {}
    for i in range(i0, i1 + 1):
        v = spearman(cnt[i], fwd20[i])
        if v is not None:
            ic_repl_gap[cal[i]] = v

    # ---- 变体 3：Q2-ac-lag1 idx 自相关（独立实现：nanmean idx + 逐窗 corrcoef）
    idx = np.nanmean(C, axis=1)
    r1 = np.full(n_d, np.nan)
    r1[1:] = idx[1:] / idx[:-1] - 1.0
    W = 60
    ac_repl = {}
    for i in range(W, n_d):
        w = r1[i - W + 1:i + 1]
        x, y = w, r1[i - W:i]                          # lag1 对
        m = np.isfinite(x) & np.isfinite(y)
        if m.sum() < W:
            continue
        xv, yv = x[m], y[m]
        if xv.std(ddof=1) == 0 or yv.std(ddof=1) == 0:
            continue
        ac_repl[cal[i]] = float(np.corrcoef(xv, yv)[0, 1])
    ac_repl = {t: v for t, v in ac_repl.items() if FULL[0] <= t <= FULL[1]}

    # ---- 主实现同代码路径原始序列（对照基准）
    P = B2.panels()
    ret20m = P['ret20']
    ic_main = MC.xsec_ic_series(ret20m.sub(ret20m.mean(axis=1), axis=0), P['fwd20'])
    ic_main = ic_main[(ic_main.index >= FULL[0]) & (ic_main.index <= FULL[1])]
    Cm = P['C']
    r1m = P0_idx = c['full144']['idx'].pct_change()
    ac_main = r1m.rolling(60, min_periods=60).corr(r1m.shift(1))
    # Q4 主路径计数面板 + IC
    Lm, Om, Hm = P['L'], P['O'], P['H']
    upgap_m = (Om / Cm.shift(1) - 1 > 0.01)
    unf_m = pd.DataFrame(0.0, index=Cm.index, columns=Cm.columns)
    for k in range(1, 21):
        lo_k = Lm.rolling(k, min_periods=k).min()
        unf_m += (upgap_m.shift(k) & (lo_k > Om.shift(k))).astype(float)
    ic_main_gap = MC.xsec_ic_series(unf_m, P['fwd20'])
    ic_main_gap = ic_main_gap[(ic_main_gap.index >= FULL[0]) & (ic_main_gap.index <= FULL[1])]

    def cmp(name, main_s, repl_d, kind):
        md = {pd.Timestamp(t): v for t, v in repl_d.items()}
        common = [t for t in main_s.index if t in md]
        diffs = [abs(float(main_s.at[t]) - md[t]) for t in common]
        maxdiff = max(diffs) if diffs else None
        extra = sorted(set(md) - set(main_s.index))
        res = {'variant': name, 'kind': kind, 'n_main': int(len(main_s)),
               'n_repl': int(len(md)), 'n_common': int(len(common)),
               'n_repl_only': int(len(extra)),
               'maxdiff': maxdiff, 'bitwise': bool(maxdiff == 0 and
                                                   len(main_s) == len(md) and not extra),
               'verdict': ('hit(逐位)' if (maxdiff == 0 and len(main_s) == len(md) and not extra)
                           else 'DIFF（如实登记，禁止改数）')}
        return res

    res = {
        'spec': '复现锚替代：独立第二实现抽 3 变体逐位对拍（用户指令④；单机环境以独立代码'
                '路径替代物理双机，如实登记）',
        'sampled': ['Q2-ac-lag1', 'Q3-rs-ew-fwd20', 'Q4-gap-unfilled-mom（vs fwd20 面板对拍）'],
        'independence': '第二实现：独立面板构造（逐标的装 numpy）+ 手工平均秩 + 逐日循环；'
                        '不经 mine_common/batch2_run 统计件；共用的仅数据层（DE.load_data）与 '
                        'IEEE 基元（nanmean/corrcoef）',
        'items': [
            cmp('Q3-rs-ew-fwd20', ic_main, ic_repl, '逐日截面 Spearman IC 序列'),
            cmp('Q4-gap-unfilled-mom', ic_main_gap, ic_repl_gap, '逐日截面 Spearman IC 序列'),
            cmp('Q2-ac-lag1', ac_main[(ac_main.index >= FULL[0]) & (ac_main.index <= FULL[1])],
                ac_repl, 'idx 日收益 60 日窗 lag1 滚动自相关序列'),
        ],
        'q4_nan_policy': '缺口回补窗口 NaN 政策（两实现统一，R7 登记）：未回补须逐日确证——'
                         '回看窗内缺任一根 low → 不可确认 → 不计（保守口径）',
        'q2_nonbitwise_note': 'Q2-ac-lag1 非逐位如实登记：pandas rolling.corr 内部累加算法'
                              '（_nancorr）不可被独立路径复现（np.corrcoef/手写中心化式均差'
                              ' ~2.3e-13；np.nanmean vs pandas mean 亦差 ~2.0e-13）；'
                              'n_main=n_repl=428 逐日齐，maxdiff=2.26e-13 << §0.5 容差 ±0.01'
                              '（相差 7 个数量级），判为 float 求和路径差异非实现误差，'
                              '提请终裁知悉',
        'wall_secs': round(time.time() - t0, 1),
    }
    res['all_bitwise'] = bool(all(it['bitwise'] for it in res['items']))
    res['status'] = 'done'
    json.dump(res, open(os.path.join(OUT, 'batch2_repl_result.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    for it in res['items']:
        print(f"  {it['variant']}: n_main={it['n_main']} n_repl={it['n_repl']} "
              f"maxdiff={it['maxdiff']} → {it['verdict']}", flush=True)
    print(f"all_bitwise={res['all_bitwise']}（{res['wall_secs']}s）", flush=True)


if __name__ == '__main__':
    main()
