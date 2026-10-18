#!/usr/bin/env python3
# brk_cond_run.py — 规格二：放量突破信号条件化（TRADE9-SPEC-FDBRK-v1.0 §2 逐字执行，禁改判据）
# 入场=20日新高+量比>1.5（R3 口径）；条件化四状态门；Pool(32)（R8 强制）。
import json, os, sys, time, random, statistics
from multiprocessing import Pool
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_fdbrk as C
import eng_final as ENG

OUT_JSON = '/tmp/brk_cond/brk_results.json'
MAIN, TRUNC = C.MAIN, C.TRUNC
F6_FULL0 = '2025-06-02'   # F6 尺：ext 窗起点（PCX-A6 FULL），窗前态未定义=不放行（保守）

_G = {}   # 进程内缓存（fork 继承）

# ---------------------------------------------------------------- 数据面板与状态变量
def panels():
    if 'pan' in _G:
        return _G['pan']
    pool, bull, idxv = C.pool_bull()
    rows = {c: pd.DataFrame({t: {b['time']: b[c] for b in bars} for t, bars in pool.items()}).sort_index()
            for c in ('open', 'high', 'low', 'close', 'volume')}
    pan = dict(O=rows['open'], H=rows['high'], L=rows['low'], C=rows['close'], V=rows['volume'])
    pan['bull'] = pd.Series({d: bull.get(d, False) for d in pan['C'].index})
    ma50 = pan['C'].rolling(50, min_periods=50).mean()
    pan['breadth'] = (pan['C'] > ma50).sum(axis=1) / pan['C'].notna().sum(axis=1)
    # F6 尺（wo_g1g2fdr/wo_crossf6 同尺逐字）：池内 20 日滚动平均两两相关，p50=realA 分位
    R = pan['C'].pct_change()
    arr = R.values
    dates = pan['C'].index
    pos = {d: i for i, d in enumerate(dates)}
    avg_corr = pd.Series(np.nan, index=dates)
    for d in dates:
        i = pos[d]
        if i < 19 or d < F6_FULL0:
            continue
        w = arr[i - 19:i + 1]
        ok = np.isfinite(w).all(axis=0)
        if ok.sum() < 30:
            continue
        cm = np.corrcoef(w[:, ok], rowvar=False)
        k = cm.shape[0]
        avg_corr[d] = float((cm.sum() - k) / (k * (k - 1)))
    ra = dates[(dates >= C.REALA[0]) & (dates <= C.REALA[1])]
    p50c = float(avg_corr[ra].quantile(0.5))
    pan['f6'] = dict(avg_corr=avg_corr, p50=p50c,
                     lo=(avg_corr <= p50c) & (dates >= F6_FULL0) & avg_corr.notna())
    # 费档 PROXY 候选：vol20 分位 / 量能分位（逐票截面），IC 前段检验
    ret1 = pan['C'].pct_change()
    pan['vol20'] = ret1.rolling(20, min_periods=20).std()
    pan['energy'] = pan['V'].rolling(20, min_periods=20).mean()
    _G['pan'] = pan
    return pan

def fwd_ret(pan, k):
    return pan['C'].shift(-k) / pan['C'] - 1

def fee_gate_eval(pan):
    """G-费档 PROXY：IC 前段（2024-04-01→2026-05-31 截面 rank IC vs fwd5）不达 0.02 → 剔除该门并归档，禁换源。"""
    f5 = fwd_ret(pan, 5)
    front = pan['C'].index[(pan['C'].index >= C.REALB[0]) & (pan['C'].index <= TRUNC)]
    out = {}
    for nm, df in (('vol20', pan['vol20']), ('energy', pan['energy'])):
        ics = []
        for d in front:
            x = df.loc[d]; y = f5.loc[d]
            m = x.notna() & y.notna()
            if m.sum() < 30:
                continue
            rx = x[m].rank(); ry = y[m].rank()
            ics.append(np.corrcoef(rx, ry)[0, 1])
        ic = float(np.mean(ics)) if ics else 0.0
        out[nm] = dict(mean_ic=round(ic, 4), n_days=len(ics), pass_=abs(ic) >= 0.02)
    best = max(out, key=lambda k: abs(out[k]['mean_ic']))
    survive = out[best]['pass_']
    gate = None
    if survive:
        mkt = pan[{'vol20': 'vol20', 'energy': 'energy'}[best]].median(axis=1)  # 市场态=池中位
        front_med = float(mkt[(mkt.index >= C.REALB[0]) & (mkt.index <= TRUNC)].median())
        gate = (mkt <= front_med)   # 预注册方向：低量能/低波动=低费档环境放行（PROXY 假设，如实记账）
    return dict(proxies=out, chosen=best if survive else None, survive=survive,
                direction='市场中位<=前段中位（低费档半区放行）' if survive else None, gate=gate)

def gates(pan, fee):
    g = dict(idx=pan['bull'], breadth=(pan['breadth'] >= 0.40), f6=pan['f6']['lo'])
    if fee['survive']:
        g['fee'] = fee['gate']
    return g

GATE_KEYS_ALL = ('idx', 'breadth', 'f6', 'fee')

# ---------------------------------------------------------------- 信号与扫描
def sig_arrs(pan, win=20, vr_thr=1.5):
    key = f'sig{win}_{vr_thr}'
    if key in _G:
        return _G[key]
    brk = pan['C'] >= pan['H'].rolling(win, min_periods=win).max().shift(1)
    vr = pan['V'] / pan['V'].rolling(win, min_periods=win).mean()
    sig = brk & (vr > vr_thr)
    _G[key] = (sig, vr)
    return sig, vr

def scan_brk_tk(bars, sig_i, gate_dates, *, entry='close', tp_mode='R2', stop_mode='atr',
                hardcap=30, confirm=0, win=20, vr=1.5, short=False):
    """单票突破扫描（只做多，V2 可实现出场口径，费 0.03%/bar）。gate_dates=该票放行日期集合。"""
    a = ENG.atrs(bars)
    n = len(bars)
    trades = []
    lvl_prev = None
    i0 = max(win, 20, 14) + 1
    i = i0
    # 逐 bar 信号
    highs = [b['high'] for b in bars]
    vols = [b['volume'] for b in bars]
    pend = None  # 回踩确认待入场 (signal_i, level, deadline)
    while i < n:
        if a[i] is None:
            i += 1; continue
        t = bars[i]['time']
        # 待确认回踩入场
        if pend is not None:
            si, level, dl = pend
            if bars[i]['low'] <= level:
                ep = bars[i]['close']; ei = i
                tr = _open(bars, a, si, ei, ep, tp_mode, stop_mode, hardcap)
                pend = None
                if tr is not None:
                    trades.append(tr)
                    i = tr['xi'] + 1
                    continue
            if i > dl:
                pend = None
        if t not in gate_dates:
            i += 1; continue
        if short:
            fire = bars[i]['close'] <= min(highs[max(0, i - win):i]) and (vols[i] / (sum(vols[i - win + 1:i + 1]) / win) > vr)
            if fire:
                pass  # 只记录样本量，不交易
            i += 1; continue
        level = max(highs[i - win:i])
        fire = (bars[i]['close'] >= level) and (vols[i] / (sum(vols[i - win + 1:i + 1]) / win) > vr)
        if not fire:
            i += 1; continue
        if confirm:
            pend = (i, level, i + confirm)
            i += 1; continue
        if entry == 'close':
            ei = i; ep = bars[i]['close']
        else:
            if i + 1 >= n: break
            ei = i + 1; ep = bars[i + 1]['open']
        tr = _open(bars, a, i, ei, ep, tp_mode, stop_mode, hardcap)
        if tr is None:
            i += 1; continue
        trades.append(tr)
        i = tr['xi'] + 1
    return trades

def _open(bars, a, si, ei, ep, tp_mode, stop_mode, hardcap):
    A = a[si]
    if A is None or A <= 0:
        return None
    if stop_mode == 'atr':
        stop = ep - 1.5 * A
    else:
        stop = bars[si]['low']
    if stop <= 0 or ep <= stop:
        return None
    if tp_mode in ('R2', 'R3'):
        tp = ep + (2.0 if tp_mode == 'R2' else 3.0) * (ep - stop)
    else:
        tp = ep + (2.0 if tp_mode == 'A2' else 3.0) * A
    xi, xpx, why, r = C.v2_exit(bars, ei, ep, tp, stop, hardcap)
    return dict(ep=ep, ei=ei, xi=xi, xc=round(xpx, 4), r=r, why=why,
                et=bars[ei]['time'], xt=bars[xi]['time'], st=si)

def gate_dates_for_tkr(g, dts, combos=None):
    """返回 combos: dict[name]->set(dates)。name=f'{combo}'"""
    out = {}
    df = pd.DataFrame({k: g[k].reindex(dts).fillna(False).astype(bool) for k in g}, index=dts)
    for name, keys in combos.items():
        m = pd.Series(True, index=dts)
        for k in keys:
            m &= df[k]
        out[name] = set(df.index[m])
    return out

# ---------------------------------------------------------------- Pool 任务
BASE_CFG = None
GATE_COMBO = None
SURV_KEYS = None

def _w_backtest(task):
    """task=dict(cfg, combo_keys or None, trunc: bool, drop: tkr or None)"""
    pool, bull, idxv = C.pool_bull()
    pan = panels()
    fee = _G.get('fee') or fee_gate_eval(pan)
    g = gates(pan, fee)
    cfg = task['cfg']
    keys = task['keys']
    sig, vr = sig_arrs(pan, cfg.get('win', 20), cfg.get('vr', 1.5))
    pool2 = {k: v for k, v in pool.items() if k != task['drop']} if task.get('drop') else pool
    if task.get('drop'):
        bull2 = ENG.build_idx_bull(pool2)
        g2 = dict(g)
        g2['idx'] = pd.Series({d: bull2.get(d, False) for d in pan['C'].index})
        ma50 = pan['C'][list(pool2)].rolling(50, min_periods=50).mean()
        g2['breadth'] = ((pan['C'][list(pool2)] > ma50).sum(axis=1) / pan['C'][list(pool2)].notna().sum(axis=1)) >= 0.40
        g = g2
    combos = {'c': tuple(keys)} if keys else None
    trs = []
    for tk, bars in pool2.items():
        dts = [b['time'] for b in bars]
        if combos:
            gd = gate_dates_for_tkr(g, dts, combos)['c']
        else:
            gd = set(dts)
        for t in scan_brk_tk(bars, None, gd, win=cfg.get('win', 20), vr=cfg.get('vr', 1.5),
                             **{k: v for k, v in cfg.items() if k not in ('win', 'vr')}):
            trs.append(dict(tkr=tk, **t))
    return task, trs

def _sel_stats(trs):
    sel = [t for t in trs if MAIN <= t['et'] <= TRUNC]
    return C.stats6(sel, thick_r=6)

# ---------------------------------------------------------------- 事件研究
def event_study(pan, mask_sig, upto=None, keys=('fwd5', 'fwd20')):
    """mask_sig=DataFrame bool（信号∧门）。fwd=close-to-close（R3 对拍口径）。日块 stationary bootstrap CI。"""
    out = {}
    for k in keys:
        kk = int(k[3:])
        f = fwd_ret(pan, kk)
        m = mask_sig.copy()
        if upto:
            m.loc[m.index > upto, :] = False
        sums, cnts = [], []
        for d in m.index:
            row = m.loc[d]
            if not row.any():
                continue
            v = f.loc[d][row].dropna()
            if len(v):
                sums.append(float(v.sum())); cnts.append(int(len(v)))
        n_ev = sum(cnts); tot = sum(sums)
        if n_ev == 0:
            out[k] = dict(n=0, mean=None, ci=None, p=None, pass_=False)
            continue
        mean = tot / n_ev
        rnd = random.Random(42)
        nd = len(sums)
        dist = []
        for _ in range(1000):
            s = 0.0; c = 0; pos = rnd.randrange(nd)
            while pos < nd:
                L = max(1, int(rnd.expovariate(0.1)))
                for j in range(L):
                    idx = (pos + j) % nd
                    s += sums[idx]; c += cnts[idx]
                pos += L
            dist.append(s / c if c else 0.0)
        dist.sort()
        lo, hi = dist[int(0.025 * len(dist))], dist[int(0.975 * len(dist))]
        p = sum(1 for x in dist if x <= 0) / len(dist)
        out[k] = dict(n=n_ev, mean=round(mean, 6), ci=[round(lo, 6), round(hi, 6)], p=p,
                      pass_=(n_ev >= 500 and mean > 0 and lo > 0))
    return out

def bh_fdr(pvals, q=0.10):
    """Benjamini-Hochberg：返回每项是否显著。"""
    items = sorted(pvals.items(), key=lambda x: x[1])
    m = len(items)
    thr_cum = 0.0
    rej = {k: False for k in pvals}
    kmax = 0
    for i, (k, p) in enumerate(items, 1):
        if p <= q * i / m:
            kmax = i
    for i, (k, p) in enumerate(items, 1):
        rej[k] = i <= kmax
    return rej

# ---------------------------------------------------------------- 主流程
def main():
    t0 = time.time()
    print('=== wo_fdbrk 规格二：放量突破条件化 ===')
    d0 = C.d0_gate()
    print('D0:', json.dumps({k: v for k, v in d0.items() if k != 'reused'}, ensure_ascii=False))
    assert d0['md5_ok'] and d0['anchor_ok'] and d0['scan_ref_maxdiff'] == 0
    pan = panels()

    # ---- D0 附加对拍：量比/突破模块 vs R3 pandas 公式（3 标的×3 交易日 maxdiff=0）----
    sig20, vr = sig_arrs(pan, 20, 1.5)
    brk_ref = pan['C'] >= pan['H'].rolling(20).max().shift(1)
    vr_ref = pan['V'] / pan['V'].rolling(20).mean()
    tkrs3 = sorted(pan['C'].columns)[:3]
    md = 0.0
    for tk in tkrs3:
        bars = C.pool_bull()[0][tk]
        highs = [b['high'] for b in bars]; vols = [b['volume'] for b in bars]
        for i in range(25, 28):   # 3 个采样交易日
            # 内联公式（扫描器逐字口径）
            v_inline = vols[i] / (sum(vols[i - 19:i + 1]) / 20)
            b_inline = bars[i]['close'] >= max(highs[i - 20:i])
            d = bars[i]['time']
            md = max(md, abs(float(v_inline) - float(vr_ref.at[d, tk])),
                     abs(float(b_inline) - float(brk_ref.at[d, tk])))
    xval = dict(sample=sorted(tkrs3), n_dates=3, maxdiff=md, ok=(md == 0.0),
                caliber='brk=C>=H.rolling(20).max().shift(1); vr=V/V.rolling(20).mean()（R3 run_screen.py 逐字）')
    print('量比对拍:', xval)

    # ---- G-费档 PROXY IC 前段检验 ----
    fee = fee_gate_eval(pan)
    _G['fee'] = fee   # fork 继承，worker 免重算
    print('G-费档:', json.dumps({k: v for k, v in fee.items() if k != 'gate'}, ensure_ascii=False))
    g = gates(pan, fee)
    surv = [k for k in GATE_KEYS_ALL if k in g]

    # ---- 基础配置网格（筛选段，四门全开态，Pool(32)）：2 入场×4 TP×2 止损 ----
    grid = []
    for entry in ('close', 'next_open'):
        for tp in ('R2', 'R3', 'A2', 'A3'):
            for stop in ('atr', 'low'):
                grid.append(dict(cfg=dict(entry=entry, tp_mode=tp, stop_mode=stop, hardcap=30), keys=tuple(surv)))
    with Pool(32) as p:
        grid_res = p.map(_w_backtest, grid)
    sel_table = []
    for task, trs in grid_res:
        s = _sel_stats(trs)
        sel_table.append(dict(cfg=task['cfg'], sel=s))
        print(f"[网格] {task['cfg']}: n={s['n']} mean={s['mean']} pf={s['pf']} win={s['win_pct']} thick6={s['thick']['n']}/{s['thick']['sum_r']}")
    # 冻结规则（预注册）：mean>=0 且 pf>=1.05 且 win_pct>=48 中 mean 最大，平手 pf 大者
    elig = [x for x in sel_table if x['sel']['mean'] is not None and x['sel']['mean'] >= 0
            and x['sel']['pf'] not in (None, 'inf') and x['sel']['pf'] >= 1.05 and x['sel']['win_pct'] >= 48]
    assert elig, '网格无配置通过基础判线'
    elig.sort(key=lambda x: (x['sel']['mean'], x['sel']['pf']), reverse=True)
    base = elig[0]
    print('冻结基础配置:', json.dumps(base))

    # ---- 四门组合事件研究（筛选段截断）+ FDR q=0.10，2^4−1=15 组合 ----
    import itertools
    combos = {}
    for r in range(1, len(surv) + 1):
        for ks in itertools.combinations(surv, r):
            combos['+'.join(ks)] = ks
    ev_sel = {}
    sig_all, _ = sig_arrs(pan, 20, 1.5)
    for name, ks in combos.items():
        m = sig_all.copy()
        for k in ks:   # 日期级门广播到全部列（Series 索引=日期，须手动对齐行）
            m = m & pd.DataFrame({c: g[k] for c in m.columns})
        ev_sel[name] = event_study(pan, m, upto=TRUNC)
    fdr5 = bh_fdr({k: v['fwd5']['p'] for k, v in ev_sel.items() if v['fwd5']['p'] is not None})
    fdr20 = bh_fdr({k: v['fwd20']['p'] for k, v in ev_sel.items() if v['fwd20']['p'] is not None})
    for name, ev in ev_sel.items():
        print(f"[事件研究·筛选段] {name}: fwd5 n={ev['fwd5']['n']} mean={ev['fwd5']['mean']} CI={ev['fwd5']['ci']} FDR5={fdr5.get(name)} | fwd20 n={ev['fwd20']['n']} CI={ev['fwd20']['ci']} FDR20={fdr20.get(name)}")

    # ---- 门组合回测（冻结基础配置，筛选段，Pool(32)）→ 选型 ----
    tasks = [dict(cfg=base['cfg'], keys=ks) for ks in combos.values()]
    with Pool(32) as p:
        combo_bt = p.map(_w_backtest, tasks)
    combo_stats = {}
    for task, trs in combo_bt:
        combo_stats['+'.join(task['keys'])] = _sel_stats(trs)
    # 选型规则（预注册）：事件研究 fwd5&fwd20 均 pass（含 FDR）且回测六元组过（mean>=0,pf>=1.05,win>=48）的组合中，
    # 优先全门组合（存活门全开），否则 thick6 sum_r 最大者
    cand = [nm for nm in combos if ev_sel[nm]['fwd5']['pass_'] and ev_sel[nm]['fwd20']['pass_']
            and fdr5.get(nm) and fdr20.get(nm)
            and combo_stats[nm]['mean'] is not None and combo_stats[nm]['mean'] >= 0
            and combo_stats[nm]['pf'] not in (None, 'inf') and combo_stats[nm]['pf'] >= 1.05
            and combo_stats[nm]['win_pct'] >= 48]
    full_combo = '+'.join(surv)
    gate_pick = full_combo if full_combo in cand else (max(cand, key=lambda nm: combo_stats[nm]['thick']['sum_r']) if cand else None)
    print('门选型:', gate_pick, '| 候选:', cand)
    assert gate_pick, '无门组合通过筛选段判线'

    # ---- realC 终验一次（全快照）----
    final_task = dict(cfg=base['cfg'], keys=tuple(gate_pick.split('+')), drop=None)
    _, final_trs = _w_backtest(final_task)
    final_main = [t for t in final_trs if t['et'] >= MAIN]
    st = C.stats6(final_main, thick_r=6)
    yr, flip = C.yearly_flip(final_trs)
    segs = C.segments(final_trs)
    # 事件研究终验（全窗）
    m = sig_all.copy()
    for k in gate_pick.split('+'):
        m = m & pd.DataFrame({c: g[k] for c in m.columns})
    ev_fin = event_study(pan, m)
    print('终验主窗:', json.dumps(st), '| 分年 flip=', flip)
    print('终验事件研究:', json.dumps(ev_fin))

    # ---- LOTO（Pool(32)，池重建严格口径）----
    tasks_l = [dict(cfg=base['cfg'], keys=tuple(gate_pick.split('+')), drop=tk) for tk in sorted(pan['C'].columns)]
    with Pool(32) as p:
        loto = p.map(_w_backtest, tasks_l)
    loto_stats = []
    for task, trs in loto:
        mm = [t for t in trs if t['et'] >= MAIN]
        s = C.stats6(mm, thick_r=6)
        loto_stats.append((task['drop'], s))
    loto_fails = [x for x in loto_stats if x[1]['mean'] is None or x[1]['mean'] < 0]
    print(f'LOTO 144: fails={len(loto_fails)} min_mean={min(s["mean"] for _, s in loto_stats if s["mean"] is not None)}')

    # ---- bootstrap（主窗日块）----
    daily = {}
    for t in final_main:
        daily[t['et']] = daily.get(t['et'], 0.0) + t['r']
    q05, p_le0, _ = C.stationary_boot(sorted(daily.items()), reps=1000, mean_block=10, seed=42)
    boot = dict(reps=1000, mean_block=10, seed=42, q05_sum_r=round(q05, 2), p_le0=p_le0, pass_=q05 >= 0)
    print('bootstrap:', boot)

    # ---- 与 fd 腿重叠度（三级判定 + ρ）----
    pool, bull, idxv = C.pool_bull()
    trs_all, _ = ENG.collect(dict(N=15, k=7.5, m=2, e=0.3), pool, bull)
    fd_main = [t for t in trs_all if t['kind'] == 'fd' and t['et'] >= MAIN]
    fd_by = {}
    for t in fd_main:
        fd_by.setdefault(t['tkr'], []).append(t['ei'])
    brk_by = {}
    for t in final_main:
        brk_by.setdefault(t['tkr'], []).append(t['ei'])
    ov_events = 0
    ov_fd_side = 0
    for tk, eis in brk_by.items():
        for e in eis:
            if any(abs(x - e) <= 3 for x in fd_by.get(tk, [])):
                ov_events += 1
    for tk, eis in fd_by.items():
        for e in eis:
            if any(abs(x - e) <= 3 for x in brk_by.get(tk, [])):
                ov_fd_side += 1
    ratio = ov_events / len(final_main) if final_main else 0.0
    # ρ：非重叠样本逐周 fwd5 汇总相关
    f5 = fwd_ret(pan, 5)
    ov_set = set()
    for tk in brk_by:
        for e in brk_by[tk]:
            if any(abs(x - e) <= 3 for x in fd_by.get(tk, [])):
                ov_set.add((tk, e))
    wk_fd, wk_brk = {}, {}
    for t in fd_main:
        tk, e = t['tkr'], t['ei']
        d = pool[tk][e]['time']
        if any(abs(x - e) <= 3 for x in brk_by.get(tk, [])):
            continue
        v = f5.at[d, tk] if (d in f5.index and tk in f5.columns and np.isfinite(f5.at[d, tk])) else None
        if v is not None:
            wk_fd[pd.Timestamp(d).to_period('W')] = wk_fd.get(pd.Timestamp(d).to_period('W'), 0.0) + v
    for t in final_main:
        tk, e = t['tkr'], t['ei']
        if (tk, e) in ov_set:
            continue
        d = pool[tk][e]['time']
        v = f5.at[d, tk] if (d in f5.index and tk in f5.columns and np.isfinite(f5.at[d, tk])) else None
        if v is not None:
            wk_brk[pd.Timestamp(d).to_period('W')] = wk_brk.get(pd.Timestamp(d).to_period('W'), 0.0) + v
    common = sorted(set(wk_fd) & set(wk_brk))
    if len(common) >= 10:
        a = np.array([wk_fd[w] for w in common]); b = np.array([wk_brk[w] for w in common])
        rho = float(np.corrcoef(a, b)[0, 1])
    else:
        rho = None
    if (ratio >= 0.30) or (rho is not None and rho >= 0.6):
        ov_verdict = '同质信号：两票合并管理（共用风险预算、同票禁止双重持仓）'
    elif ratio >= 0.15:
        ov_verdict = '部分同质：风险主管 0.5 相关折扣计入组合'
    else:
        ov_verdict = '独立票'
    overlap = dict(brk_events=len(final_main), fd_events=len(fd_main), overlap_events=ov_events,
                   overlap_ratio=round(ratio, 4), fd_side=ov_fd_side,
                   rho_weekly_fwd5=None if rho is None else round(rho, 4),
                   n_weeks=len(common), verdict=ov_verdict,
                   rule='≥30% 或 ρ≥0.6 同质合并；15–30% 部分同质 0.5 折扣；<15% 独立票')
    print('重叠度:', json.dumps(overlap))

    # ---- R9 十项（筛选段截断）----
    r9 = {}
    # #1 突破窗 20 vs 55
    for w in (20, 55):
        cfg = dict(base['cfg']); cfg['win'] = w
        _, trs = _w_backtest(dict(cfg=cfg, keys=tuple(gate_pick.split('+'))))
        r9[f'1_窗{w}'] = _sel_stats(trs)
    # #2 量比 1.5/2.0/1.2
    for v in (1.2, 1.5, 2.0):
        cfg = dict(base['cfg']); cfg['vr'] = v
        _, trs = _w_backtest(dict(cfg=cfg, keys=tuple(gate_pick.split('+'))))
        r9[f'2_量比{v}'] = _sel_stats(trs)
    # #3 入场时点（网格已双臂）
    r9['3_入场时点'] = {x['cfg']['entry']: x['sel'] for x in sel_table if x['cfg']['tp_mode'] == base['cfg']['tp_mode'] and x['cfg']['stop_mode'] == base['cfg']['stop_mode']}
    # #4 15 组合（已全跑）
    r9['4_门组合15'] = {nm: dict(fwd5=ev_sel[nm]['fwd5'], fwd20=ev_sel[nm]['fwd20'],
                                 fdr5=fdr5.get(nm), fdr20=fdr20.get(nm),
                                 bt={k: combo_stats[nm][k] for k in ('n', 'mean', 'pf', 'win_pct', 'sum_r')})
                        for nm in combos}
    # #5 TP 网格 / #6 止损双臂（网格已含）
    r9['5_TP网格'] = {x['cfg']['tp_mode']: x['sel'] for x in sel_table if x['cfg']['entry'] == base['cfg']['entry'] and x['cfg']['stop_mode'] == base['cfg']['stop_mode']}
    r9['6_止损双臂'] = {x['cfg']['stop_mode']: x['sel'] for x in sel_table if x['cfg']['entry'] == base['cfg']['entry'] and x['cfg']['tp_mode'] == base['cfg']['tp_mode']}
    # #7 空头镜像样本量
    n_short = 0
    lows = pan['L']
    dn = lows <= lows.shift(1).rolling(20, min_periods=20).min()
    n_short = int((dn & (vr > 1.5)).sum().sum())
    r9['7_空头镜像'] = dict(n=n_short, archive='n<300 归档不评' if n_short < 300 else 'n>=300 需另评')
    # #8 回踩确认
    cfg8 = dict(base['cfg']); cfg8['confirm'] = 2
    _, trs8 = _w_backtest(dict(cfg=cfg8, keys=tuple(gate_pick.split('+'))))
    r9['8_回踩确认'] = _sel_stats(trs8)
    # #9 硬顶移除
    cfg9 = dict(base['cfg']); cfg9['hardcap'] = 10 ** 9
    _, trs9 = _w_backtest(dict(cfg=cfg9, keys=tuple(gate_pick.split('+'))))
    r9['9_硬顶移除'] = _sel_stats(trs9)
    # #10 与 fd 同票冲突规则（fd 持仓中忽略 vs 平仓换仓）
    r9['10_冲突规则'] = _conflict_rules(pool, fd_main, final_trs)
    r9_all = all(v is not None for v in r9.values())

    # ---- 判据逐项（§2.3 预注册）----
    thick_neg = st['thick']['sum_r'] < 0
    items = dict(
        item1_事件研究=dict(fwd5=ev_fin['fwd5'], fwd20=ev_fin['fwd20'],
                            pass_=(ev_fin['fwd5']['pass_'] and ev_fin['fwd20']['pass_'])),
        item2_主窗六元组=dict(**{k: st[k] for k in ('n', 'median', 'win_pct', 'mean', 'pf', 'sum_r')},
                               pass_=(st['mean'] >= 0 and st['pf'] not in (None, 'inf') and st['pf'] >= 1.05 and st['win_pct'] >= 48)),
        item3_分年分段=dict(years=yr, flip=flip, segments=segs,
                            pass_=(not flip and segs['realA']['sum_r'] >= 0 and segs['realB']['sum_r'] >= 0 and segs['realC']['sum_r'] >= 0),
                            note='realC 终验一次已执行，验后即烧'),
        item4_LOTO_bootstrap=dict(loto_fails=len(loto_fails), boot=boot,
                                   pass_=(len(loto_fails) == 0 and boot['q05_sum_r'] >= 0)),
        item5_否决线=dict(thick_r6=st['thick'], mean=st['mean'], flip=flip,
                           veto=bool(thick_neg or st['mean'] < 0 or flip),
                           rule='厚利桶 r>=6 不得为负贡献 且 mean>=0 且 分年不翻脸——任一触发即死'),
    )
    verdict = 'brk-cond 票存活（判据全过）' if all(v['pass_'] for v in items.values()) else 'brk-cond 票判死（判据未全过/否决线触发）'
    print('判据:', json.dumps(items, ensure_ascii=False, default=str))
    print('终裁:', verdict)

    out = dict(
        workorder='brk-cond（规格二：放量突破信号条件化）', spec='TRADE9-SPEC-FDBRK-v1.0 §2',
        generated=time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()),
        d0=d0, xval_volratio=xval,
        fee_gate=dict(proxies=fee['proxies'], chosen=fee['chosen'], survive=fee['survive'],
                      direction=fee['direction'],
                      note='box_cache 无逐日资金费（C10 先例可得性检查）；PROXY IC 前段不达 0.02 即剔除禁换源'),
        gates=dict(surviving=surv, breadth_rule='breadth_above_ma50>=0.40（HA_SPEC C9 移交）',
                   f6_rule=f"池内 20 日滚动平均两两相关 <= realA p50({round(pan['f6']['p50'],4)}) 低相关态放行；窗前态未定义不放行；衰减态只记录不放行"),
        base_grid=sel_table, frozen_base=base,
        gate_event_study_sel=ev_sel, fdr=dict(q=0.10, fwd5=fdr5, fwd20=fdr20),
        gate_backtest_sel=combo_stats, gate_pick=gate_pick,
        final=dict(cfg=base['cfg'], gates=gate_pick, main=st, yearly=yr, flip=flip, segments=segs,
                   event_study=ev_fin),
        loto=dict(fails=loto_fails, n_tasks=len(loto_stats)), bootstrap=boot,
        overlap_with_fd=overlap,
        r9=r9, r9_all_ran=r9_all, judgment=items, verdict=verdict,
        runtime_sec=round(time.time() - t0, 1),
        realC_note='realC（2026-06-01→2026-10-18）仅本终验一次触碰，验后即烧',
    )
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(out, open(OUT_JSON, 'w'), ensure_ascii=False, indent=1, default=str)
    print('写出', OUT_JSON, '用时', out['runtime_sec'], 's')

def _conflict_rules(pool, fd_main, brk_trs):
    """R9#10：fd 持仓中突破信号忽略 vs 平仓换仓（筛选段截断，冻结门组合）。
    离线重放：fd 交易区间 [ei,xi]；brk 交易若 ei 落入 fd 持仓 → ignore: 丢弃该笔 brk；
    switch: fd 该笔以 brk 入场日收盘价强平（重算 r），brk 照入。"""
    brk_tr = [t for t in brk_trs if t['et'] <= TRUNC and t['et'] >= MAIN]
    fd_tr = [t for t in fd_main if t['et'] <= TRUNC]
    fd_iv = {}
    for t in fd_tr:
        fd_iv.setdefault(t['tkr'], []).append((t['ei'], t['xi'], t['r'], t['ep']))
    def replay(mode):
        fd_adj = {tk: [list(x) for x in v] for tk, v in fd_iv.items()}
        kept = 0; dropped = 0; tot = 0.0
        for t in sorted(brk_tr, key=lambda x: (x['tkr'], x['ei'])):
            ivs = fd_adj.get(t['tkr'], [])
            hit = None
            for iv in ivs:
                if iv[0] <= t['ei'] <= iv[1]:
                    hit = iv; break
            if hit is None:
                kept += 1; tot += t['r']; continue
            if mode == 'ignore':
                dropped += 1
            else:
                bars = pool[t['tkr']]
                px = bars[t['ei']]['close']
                hit[2] = (px - hit[3]) / hit[3] * 100 - 0.03 * (t['ei'] - hit[0])
                hit[1] = t['ei'] - 1
                kept += 1; tot += t['r']
        fd_sum = sum(iv[2] for v in fd_adj.values() for iv in v)
        return dict(brk_kept=kept, brk_dropped=dropped, brk_sum_r=round(tot, 2), fd_sum_r=round(fd_sum, 2),
                    total=round(tot + fd_sum, 2))
    return dict(ignore=replay('ignore'), switch=replay('switch'))

if __name__ == '__main__':
    main()
