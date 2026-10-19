#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch 3 · 独立第二实现抽 2 变体逐位对拍（复现锚替代，用户指令④；batch2_repl.py 同谱系）
====================================================================================
单机环境，物理双机不可用 → 以独立代码路径替代，如实登记。抽样（新实现各抽 1）：
  ① K2-mr-d5-h5：独立事件回测（逐标的 numpy 数组 + 独立触发/止损/时间出场/费记路径，
     不经 batch3_run.k2_simulate / mine_common.simulate；共用仅数据层 json 读取与 IEEE 基元）。
  ② K5-fd-exit-time20：独立出场核算（主件产出入场点 (ep, ei, eff)，出场 bar/价/R 由
     独立循环重算——入场信号引用主件、R 值独立复算，独立性边界如实登记）。
判据：n 逐日齐 + maxdiff==0 → 逐位 hit；非逐位按 R7 如实登记禁改数。
R10 红线：本件不产出「域读数→仓位」映射。
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = '/workspace/repo_ready/research/wo_mine'
CACHE = '/tmp/box_cache'
FEE_SIDE, FUNDING, STOP = 0.0005, 0.0003, -0.08


def load_bars():
    """独立数据装载（不经 dneg_engine）：逐标的 json → 按 time 排序 dict 列表。"""
    bars = {}
    for f in sorted(os.listdir(CACHE)):
        d = json.load(open(os.path.join(CACHE, f)))
        rows = sorted(d, key=lambda b: b['time']) if isinstance(d, list) else None
        if rows is None:
            continue
        bars[f.replace('.json', '')] = rows
    return bars


# ================================================================ ① K2-mr-d5-h5 独立回测
def k2_repl(pname_syms, bars, depth=0.05, hold=5):
    """独立实现：每股独立扫描事件 → (入场日, ep, ei, 止损线)；合成日频权益曲线。
    口径与主件一致（K2 工单 _OPS 冻结）：昨日触发今日开盘入场、10% 权益预算、
    −8% 开盘/盘中止损、持有 5 根 K 后开盘时间出场、双边费+日资金费。"""
    # 全日历（union）
    all_t = sorted({b['time'] for bs in bars.values() for b in bs})
    tidx = {t: i for i, t in enumerate(all_t)}
    n = len(all_t)
    # 独立面板（numpy，缺 K 线=NaN）
    px_o = {s: np.full(n, np.nan) for s in pname_syms}
    px_c = {s: np.full(n, np.nan) for s in pname_syms}
    px_l = {s: np.full(n, np.nan) for s in pname_syms}
    for s in pname_syms:
        for b in bars.get(s, []):
            i = tidx.get(b['time'])
            if i is not None:
                px_o[s][i], px_c[s][i], px_l[s][i] = b['open'], b['close'], b['low']
    ret1 = {}
    px_c_pad = {}
    for s in pname_syms:
        # 语义对拍定案（R7 登记）：触发收益=raw（pandas 3.0 pct_change 默认无填充，触发集
        # 已证 main==raw 逐位）；marking/资金费/时间出场兜底=ffill 收盘（mark 谱系）
        c = px_c[s]
        cp = np.full(n, np.nan)
        last = np.nan
        for i in range(n):
            if np.isfinite(c[i]):
                last = c[i]
            cp[i] = last
        px_c_pad[s] = cp
        prev = np.concatenate([[np.nan], c[:-1]])
        with np.errstate(invalid='ignore', divide='ignore'):
            ret1[s] = c / prev - 1
    cash, pos, curve = 1.0, {}, np.full(n, np.nan)
    for i, t in enumerate(all_t):
        for s, pp in list(pos.items()):
            stop_p = pp['entry'] * (1 + STOP)
            px = None
            if np.isfinite(px_o[s][i]) and px_o[s][i] <= stop_p:
                px = px_o[s][i]
            elif np.isfinite(px_l[s][i]) and px_l[s][i] <= stop_p:
                px = stop_p
            elif i - pp['ei'] >= hold:
                px = px_o[s][i] if np.isfinite(px_o[s][i]) else px_c_pad[s][i]
            if px is not None and np.isfinite(px):
                cash += pp['qty'] * px * (1 - FEE_SIDE)
                del pos[s]
        if i > 0:
            eq_prev = curve[i - 1] if np.isfinite(curve[i - 1]) else 1.0
            for s in pname_syms:
                if s in pos or not np.isfinite(px_o[s][i]):
                    continue
                r_y = ret1[s][i - 1]
                if not (np.isfinite(r_y) and r_y < -depth):
                    continue
                budget = min(0.10 * eq_prev, max(cash, 0.0))
                if budget <= 0:
                    continue
                qty = budget / px_o[s][i]
                cash -= qty * px_o[s][i] * (1 + FEE_SIDE)
                pos[s] = {'qty': qty, 'entry': px_o[s][i], 'ei': i}
        eq = cash
        for s, pp in pos.items():
            if np.isfinite(px_c_pad[s][i]):
                eq += pp['qty'] * px_c_pad[s][i]
                cash -= pp['qty'] * px_c_pad[s][i] * FUNDING
        curve[i] = eq
    return all_t, curve


def repl_k2():
    import batch3_run as B3
    import batch1_run as B1
    c = B3.ctx()
    out = {}
    for p in ('old131', 'full144'):
        main = B3.k2_simulate(p, depth=0.05, hold=5)      # 主件曲线（复算，确定性）
        syms = c['pools'][p]
        bars = {}
        for s in syms:
            df = c['data'][s]
            bars[s] = [{'time': str(t), 'open': row['open'], 'close': row['close'],
                        'low': row['low']} for t, row in df.iterrows()]
        ts, crv = k2_repl(syms, bars)
        s_main = main.reindex(pd_DatetimeIndex(ts))
        d = np.nanmax(np.abs(s_main.values - crv))
        out[p] = {'n_main': int(s_main.notna().sum()), 'n_repl': int(np.isfinite(crv).sum()),
                  'maxdiff': float(d) if np.isfinite(d) else None,
                  'bitwise': bool(d == 0), 'verdict': 'hit(逐位)' if d == 0 else 'DIFF(如实登记)'}
    return out


pd_DatetimeIndex = None   # 延迟到 repl_k2 内初始化（见 main）


# ================================================================ ② K5-fd-exit-time20 独立出场核算
def repl_k5():
    sys.path.insert(0, OUT)
    sys.path.insert(0, '/workspace/repo_ready/research/wo_fdbrk')
    sys.path.insert(0, '/tmp/eng_wt_rc')
    import batch3_run as B3
    import common_fdbrk as CF
    pool, bull, idxv = CF.pool_bull()
    fns = B3._fd_exit_fns()
    # 主件 time20 交易（确定性复算）
    main = []
    for tk, bs in pool.items():
        for t in B3.scan_fd_exit(bs, bull, fns['K5-fd-exit-time20']):
            main.append(dict(tkr=tk, **t))
    # 独立出场：硬顶 20 bar——首达 bar=min(首个 close<=eff 日, 首个 close>=tp 日, ei+20)
    a_eng = __import__('eng_final').atrs
    n_match, n_only, maxd_r, maxd_x = 0, 0, 0.0, 0
    for tr in main:
        bars = pool[tr['tkr']]
        ei, ep = tr['ei'], tr['ep']
        A = a_eng(bars)[ei]
        # eff 独立重算（N=15 Donchian 低点 − 0.3×ATR，入场逻辑谱系逐字；不经主件中间量）
        L_ = min(b['low'] for b in bars[ei - 14:ei + 1])
        eff = L_ - 0.3 * A
        tp = ep + 3.5669 * A
        xi, xpx = None, None
        for i in range(ei + 1, len(bars)):
            px = bars[i]['close']
            hold = i - ei
            if px <= eff or px >= tp or hold >= 20:
                if px >= tp:
                    x = max(tp, bars[i]['open'])
                elif px <= eff:
                    x = min(eff, bars[i]['open'])
                else:
                    x = px
                j = i
                while j < len(bars) - 1 and not (bars[j]['low'] <= x <= bars[j]['high']):
                    j += 1
                    x = bars[j]['open']
                xi, xpx = j, x
                break
        if xi is None:
            xi, xpx = len(bars) - 1, bars[-1]['close']
        r = (xpx - ep) / ep * 100 - CF.FEE * (xi - ei)
        if xi == tr['xi']:
            n_match += 1
            maxd_r = max(maxd_r, abs(r - tr['r']))
        else:
            n_only += 1
        maxd_x = max(maxd_x, abs(xi - tr['xi']))
    return {'variant': 'K5-fd-exit-time20', 'kind': '出场 bar/R 独立重算（入场点引用主件）',
            'n_trades': len(main), 'n_exit_bar_match': n_match, 'n_mismatch': n_only,
            'max_xi_diff': int(maxd_x), 'max_r_diff': float(maxd_r),
            'bitwise': bool(n_only == 0 and maxd_r == 0.0),
            'verdict': 'hit(逐位)' if (n_only == 0 and maxd_r == 0.0) else 'DIFF(如实登记)',
            'independence_note': '入场信号/eff/ATR 引用主件产出；出场判定、顺延取价、费与 R '
                                 '由独立循环重算（共用仅数据层与 IEEE 基元）'}


def main():
    global pd_DatetimeIndex
    import pandas as pd
    pd_DatetimeIndex = pd.DatetimeIndex
    t0 = time.time()
    print('=== Batch 3 独立第二实现对拍（抽 2 新实现变体）===', flush=True)
    k2 = repl_k2()
    print('K2-mr-d5-h5:', json.dumps(k2, ensure_ascii=False), flush=True)
    k5 = repl_k5()
    print('K5:', json.dumps(k5, ensure_ascii=False), flush=True)
    items = [{'variant': f'K2-mr-d5-h5|{p}', **v} for p, v in k2.items()] + [k5]
    out = {'ts': time.strftime('%F %T'),
           'spec': '独立第二实现抽 2 新实现变体逐位对拍（复现锚替代；单机环境以独立代码路径'
                   '替代物理双机，batch2_repl 同谱系，如实登记）',
           'items': items,
           'all_bitwise': all(i.get('bitwise') for i in items),
           'wall_secs': round(time.time() - t0, 1), 'status': 'done',
           'r10_note': '本运行不产出任何「域读数→仓位」映射（R10）'}
    json.dump(out, open(os.path.join(OUT, 'batch3_repl_result.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    print(f"all_bitwise={out['all_bitwise']} → batch3_repl_result.json", flush=True)


if __name__ == '__main__':
    main()
