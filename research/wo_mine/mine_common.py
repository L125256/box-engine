#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wo_mine 共用件 · MINE_SPEC_v1 分域挖掘（预注册纲领逐字实现，禁发挥）
====================================================================
谱系声明（R2 出处）：
- 回测内核 = research/wo_rescue/wo_rescue_run.py run_gate 逐行同构
  （该谱系 D0 已证：wo_g1g2fdr g1_result.d0 vs_dneg_maxdiff=0 /
   vs_wo_rescue_run_gate_maxdiff=0 / vs_wo_hd 八列 0.0）；
  off_mode 扩展 = run_gate_g（wo_g1g2fdr）四档语义的 pause/s3 两档。
- ALPHA 锚复现 = wo_alpha/alpha_run.py simulate 逐行同构（A=4.7306 锚）。
- 因子件（IC/十分位价差/t 统计）= wo_rescue _xsec_ic_series/_decile_spread_fee/
  _tstat 逐行同构（c4 extended t=+4.78、c5 t=+2.18 锚复现用）。
- 域切分 = MINE_SPEC_v1 §二（D1 趋势×波动 / D2 宽×费 / D3 安慰剂 seed=42），
  分位锚 realA(2025-06-01→2026-10-17, MINE_SPEC §2.4) 先落盘后回放，标签 lag=1。
- 门阈值锚（换门/S3 vol20 分位）= 谱系窗 realA(2025-06-02→2026-03-31, W3/PB-3)，
  与 G1G2FDR/RESCUE 承接数可比——两套锚窗分离登记，不混写。
- R10 红线：域标签只作离线研究分层，本文件任何函数不产出「域→仓位」映射。
"""
import json
import os
import sys

import numpy as np
import pandas as pd

# 仓库根：env 覆盖优先，缺省 __file__ 相对解析（shadow_cells.py :83-85 同款：
# _HERE=research/wo_mine，上两级=仓库根；禁绝对路径硬编码——云端 /tmp/f1work
# 布局 SHADOW-PATH-20261020 遗留修复）
_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get('SHADOW_REPO_ROOT') or \
    os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(REPO, 'research', 'wo_dneg'))
import dneg_engine as DE

CACHE = '/tmp/box_cache'
OUT_DIR = os.path.join(REPO, 'research', 'wo_mine')
TMP_DIR = '/tmp/wo_mine'

# ---- 双锚窗（分离登记）----
MS_REALA = (pd.Timestamp('2025-06-01'), pd.Timestamp('2026-10-17'))   # MINE_SPEC §2.4 主判窗（域锚/FDR/图谱）
LN_REALA = (pd.Timestamp('2025-06-02'), pd.Timestamp('2026-03-31'))   # 谱系窗（门阈值锚，W3/PB-3 同源）
SYNTH = (pd.Timestamp('2024-01-24'), pd.Timestamp('2025-05-31'))      # 合成段（低权重佐证）
SEED = 42
D1_NAMES = ['牛稳', '牛躁', '弱稳', '弱躁']
D2_W = ['宽', '中', '窄']
D2_C = ['低费', '高费']
BATCH_BUDGET_M = 86          # §四.6 冻结：FDR 合并族 m=86


# ================================================================ 上下文
_CTX = None


def build_ctx():
    """数据/池/因子/面板（fork COW 只读）。full144 与引擎池一致性在此断言。"""
    global _CTX
    if _CTX is not None:
        return _CTX
    data = DE.load_data(CACHE)
    pools = DE.build_pools(data)
    F = DE.build_factors(data)
    # 引擎同源池一致性（f1_signal.build_pool=cleaned_pool kept 144）
    # 引擎目录：本地 engine_f1/ 优先（原行为），云端布局引擎在 f1/（SHADOW-PATH-20261020
    # 遗留修复：REPO 引用点云端可解析，禁绝对路径硬编码）
    _eng_dir = os.path.join(REPO, 'engine_f1')
    if not os.path.isfile(os.path.join(_eng_dir, 'f1_signal.py')):
        _eng_dir = os.path.join(REPO, 'f1')
    sys.path.insert(0, _eng_dir)
    os.environ.setdefault('F1_CACHE', CACHE)
    os.environ.setdefault('F1_POOL', os.path.join(REPO, 'engine_snapshot', 'cleaned_pool.json'))
    import f1_signal as eng
    eng_syms = eng.build_pool(eng.load_data(CACHE))
    assert set(eng_syms) == set(pools['full144']), 'full144 与引擎池不一致'
    ctx = {'data': data, 'pools': pools, 'F': F}
    for pname in ('old131', 'full144'):
        syms = pools[pname]
        close = pd.DataFrame({s: data[s]['close'] for s in syms})
        open_ = pd.DataFrame({s: data[s]['open'] for s in syms})
        low = pd.DataFrame({s: data[s]['low'] for s in syms})
        cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
        close, open_, low = (x.reindex(cal) for x in (close, open_, low))
        mark = close.ffill()
        idx = close.mean(axis=1)
        idx_ma = idx.rolling(DE.MA_REG).mean()
        med_ret = close.pct_change().median(axis=1)
        iso = cal.isocalendar()
        sig_days = set(cal.to_series().groupby(
            [iso['year'].values, iso['week'].values]).first().sort_values().values)
        # vol20 = 池等权 idx 日收益 20 日滚动 std(ddof=1)×sqrt(252)（PB-3 冻结同构）
        vol20 = idx.pct_change().rolling(20).std(ddof=1) * np.sqrt(252)
        # breadth = close>MA50(rolling50,min_periods=40) 占比%（g1g2fdr gate_maps 同式）
        above = (close > close.rolling(50, min_periods=40).mean())
        breadth = above.mean(axis=1) * 100.0
        # 个股级辅助（域切分 D1 轴B / D2 / c5 控制变量）
        ret1 = close.pct_change()
        vol_i = ret1.rolling(20).std(ddof=1) * np.sqrt(252)      # 个股 vol20 年化
        vol_med = vol_i.median(axis=1)                            # 池 vol20 中位（MINE_SPEC D1 轴B 逐字）
        V = pd.DataFrame({s: data[s]['volume'] for s in syms}).reindex(cal)
        dvol = (close * V)
        turn_med = np.log(dvol.rolling(20).mean()).median(axis=1)  # 换手代理（D2 轴B【推断】）
        ctx[pname] = dict(syms=syms, close=close, open_=open_, low=low, mark=mark,
                          cal=cal, idx=idx, idx_ma=idx_ma, med_ret=med_ret,
                          sig_days=sig_days, vol20=vol20, breadth=breadth,
                          vol_med=vol_med, turn_med=turn_med)
    _CTX = ctx
    return ctx


# ================================================================ 域切分（§二.4 冻结）
def quantile_anchors(ctx):
    """分位锚：先落盘后回放。域锚=MS_REALA；门锚=LN_REALA。"""
    full = ctx['full144']
    def q(sr, qlist, win, names):
        s = sr[(sr.index >= win[0]) & (sr.index <= win[1])].dropna()
        return {nm: float(s.quantile(p)) for nm, p in zip(names, qlist)}
    a = {
        'domain_anchor_window': 'MINE_SPEC realA 2025-06-01~2026-10-17',
        'gate_anchor_window': 'lineage realA 2025-06-02~2026-03-31（W3/PB-3，换门/S3 专用）',
        'vol_med_q50': q(full['vol_med'], [0.5], MS_REALA, ['p50']),          # D1 轴B
        'breadth_p33_p66': q(full['breadth'], [1/3, 2/3], MS_REALA, ['p33', 'p66']),  # D2 轴A
        'turn_med_q50': q(full['turn_med'], [0.5], MS_REALA, ['p50']),         # D2 轴B【推断】
        'vol20_p70_p80': q(full['vol20'], [0.7, 0.8], LN_REALA, ['p70', 'p80']),  # 门锚（谱系窗）
        # 【方法书 §6.1 domains.json 补项】逐池 vol20 门锚（变体 4-1/5-1 需逐池阈值，禁共用）
        'gate_vol20_p80_by_pool': {
            pname: float(ctx[pname]['vol20'][(ctx[pname]['vol20'].index >= LN_REALA[0])
                                             & (ctx[pname]['vol20'].index <= LN_REALA[1])].quantile(0.8))
            for pname in ('old131', 'full144')},
    }
    return a


def build_domain_labels(ctx, anchors):
    """D1/D2 域标签（lag=1）+ D3 安慰剂 100 次重排（seed=42 起）。"""
    full = ctx['full144']
    cal = full['cal']
    idx, idx_ma = full['idx'], full['idx_ma']
    # D1 轴A：idx vs MA50（f1_signal.py:638/639 同源；MA 不足=NaN→域未定义）
    trend = pd.Series(np.where(idx_ma.isna(), None,
                      np.where(idx >= idx_ma, '牛', '弱')), index=cal)
    vol_med = full['vol_med']
    vag = anchors['vol_med_q50']['p50']
    mood = pd.Series(np.where(vol_med.isna(), None,
                     np.where(vol_med > vag, '躁', '稳')), index=cal)
    st = trend + mood
    d1 = st.shift(1)                                               # lag=1 防前视（§2.4-2）
    # D2：宽/中/窄 × 低费/高费（lag=1）
    br = full['breadth']
    b33 = anchors['breadth_p33_p66']['p33']
    b66 = anchors['breadth_p33_p66']['p66']
    bw = pd.Series(np.where(br.isna(), None,
                   np.where(br >= b66, '宽', np.where(br >= b33, '中', '窄'))), index=cal)
    tn = full['turn_med']
    c50 = anchors['turn_med_q50']['p50']
    cost = pd.Series(np.where(tn.isna(), None,
                     np.where(tn > c50, '高费', '低费')), index=cal)
    d2 = (bw + cost).shift(1)
    # D3 安慰剂：D1 标签逐日随机打乱 ×100（seed=42..141），仅在 MS_REALA 评估窗内置换
    mask = (cal >= MS_REALA[0]) & (cal <= MS_REALA[1])
    vals = d1[mask].dropna()
    placebo = {}
    for k in range(100):
        rng = np.random.default_rng(SEED + k)
        perm = pd.Series(rng.permutation(vals.values), index=vals.index)
        placebo[k] = {str(t.date()): v for t, v in perm.items()}
    return {
        'd1': {str(t.date()): (v if isinstance(v, str) else None) for t, v in d1.items()},
        'd2': {str(t.date()): (v if isinstance(v, str) else None) for t, v in d2.items()},
        'd1_state_unlagged': {str(t.date()): (v if isinstance(v, str) else None)
                              for t, v in st.items()},   # 供 D0-① 与引擎 gate 对拍
        'placebo_d1_100': placebo,
        'note': 'D3 安慰剂=D1 标签逐日随机打乱 seed=42..141 ×100（MINE_SPEC §2.3）',
    }


# ================================================================ 回测内核（run_gate 谱系逐行 + off_mode）
def simulate(ctx, pname, slot_mult=1.0, slot_abs=None, overlay=None,
             lineage='gate', win=None, fee=None, fund=None, target_fn=None):
    """lineage='gate'：wo_rescue.run_gate 逐行（无闸清仓、无 crash 跳重建）；
    overlay={'off':Series(bool 信号日读), 'mode':'pause'|'s3'}：
      pause=OFF 跳过开仓与换仓卖出（PB-4 语义）；s3=OFF 跳过换仓卖出+半额 slot 开仓
      （run_gate_g open_half_nosell 语义）。
    lineage='alpha'：wo_alpha.simulate 逐行（闸清仓+crash 跳重建+slot_abs=0.2），
      仅用于 D0-④ ALPHA 锚复现。win=(start,end) 截断回放窗口。
    【Batch1 增补，默认值=原行为逐位不变】fee/fund 可参数化（PB-5 费压口径用，
    缺省=DE 常量）；target_fn(t, equity)->list 可注入选股（C1 随机带 B 臂法用，
    缺省=DE.cross_scores 四因子）。"""
    P = ctx[pname]
    cal_all = P['cal']
    if win is not None:
        s0, s1 = pd.Timestamp(win[0]), pd.Timestamp(win[1])
        cal = cal_all[(cal_all >= s0) & (cal_all <= s1)]
    else:
        cal = cal_all
    syms = P['syms']
    close, open_, low, mark = P['close'], P['open_'], P['low'], P['mark']
    idx, idx_ma, med_ret = P['idx'], P['idx_ma'], P['med_ret']
    sig_days = P['sig_days']
    fee = DE.FEE_SIDE if fee is None else fee
    fund = DE.FUNDING if fund is None else fund
    slot_base = slot_abs if slot_abs is not None else DE.SLOT * slot_mult

    cash, pos = 1.0, {}
    pending_sells, pending_reason = set(), {}
    pending_exec = None
    eq, fees = {}, 0.0
    n_gate_off = 0
    stopped_today = set()
    crash_next = None
    for t in cal:
        o_t, lo_t = open_.loc[t], low.loc[t]
        stopped_today = set()
        for s in list(pos):                                   # 1) 盘中断价止损
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            stop_p = pos[s]['entry'] * (1 + DE.STOP)
            if o_t[s] <= stop_p:
                px = o_t[s]
            elif pd.notna(lo_t.get(s, np.nan)) and lo_t[s] <= stop_p:
                px = stop_p
            else:
                continue
            q = pos[s]['qty']
            cash += q * px * (1 - fee)
            fees += q * px * fee
            stopped_today.add(s)
            del pos[s]
        for s in list(pending_sells):                          # 2) 挂单清仓
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                q = pos[s]['qty']
                cash += q * px * (1 - fee)
                fees += q * px * fee
                del pos[s]
            pending_sells.discard(s)
        skip_rebuild = (crash_next == t) if lineage == 'alpha' else False
        if skip_rebuild:
            crash_next = None
        if pending_exec is not None and t == pending_exec[0]:  # 3) 周调仓执行
            _, target, eq_sig = pending_exec
            pending_exec = None
            # 【方法书 §6.1 修复点】执行日闸开复核（alpha_run.py:138 谱系）：
            # alpha 谱系执行日整段重建（卖+买）以执行日闸开为前提，信号日闸开、
            # 执行日闸关的周不得建仓。gate 谱系无此语义（gate_exec 恒 True，原行为不变）。
            gate_exec = bool(pd.notna(idx_ma.at[t]) and idx.at[t] >= idx_ma.at[t]) \
                if lineage == 'alpha' else True
            off_next = bool(overlay is not None and overlay['off'].get(t, False))
            if off_next:
                n_gate_off += 1
            if off_next and overlay['mode'] in ('pause', 'full_stop'):
                sell_skip, do_open, smult = True, False, 1.0
            elif off_next and overlay['mode'] == 's3':
                sell_skip, do_open, smult = True, True, 0.5
            else:
                sell_skip, do_open, smult = False, True, 1.0
            if not skip_rebuild and not sell_skip and gate_exec:
                for s in list(pos):
                    if s in target or s in pending_sells:
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        pending_sells.add(s)
                        pending_reason[s] = 'rebal'
                        continue
                    q = pos[s]['qty']
                    cash += q * px * (1 - fee)
                    fees += q * px * fee
                    del pos[s]
            if not skip_rebuild and do_open and gate_exec:
                slot = slot_base * smult
                for s in target:
                    if s in pos or s in stopped_today:          # BUG-04 止损票当日禁买回
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        continue
                    budget = min(slot * eq_sig, max(cash, 0.0))
                    if budget <= 0:
                        continue
                    qty = budget / px
                    cash -= qty * px * (1 + fee)
                    fees += qty * px * fee
                    pos[s] = {'qty': qty, 'entry': px}
        equity = cash                                          # 4) 收盘记账+资金费
        for s, p in pos.items():
            m = mark.at[t, s]
            equity += p['qty'] * m
            f = p['qty'] * m * fund
            cash -= f
            fees += f
        eq[t] = equity
        if lineage == 'alpha':
            if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                    and med_ret[t] < DE.CRASH_MED:             # 5a) 崩市闸（alpha：次日跳重建）
                pending_sells.update(pos.keys())
                crash_next = cal[cal.get_loc(t) + 1] \
                    if cal.get_loc(t) + 1 < len(cal) else None
            if not bool(pd.notna(idx_ma.at[t]) and idx.at[t] >= idx_ma.at[t]) \
                    and len(pos) > 0:                          # 5b) 闸关逐日出清（alpha）
                pending_sells.update(pos.keys())
        else:
            if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                    and med_ret[t] < DE.CRASH_MED:             # 5) 崩市闸（gate 谱系：不跳重建）
                pending_sells.update(pos.keys())
        if t in sig_days:                                      # 6) 周信号
            if target_fn is not None:
                target = list(target_fn(t, equity))
            elif lineage == 'alpha':
                g_open = bool(not pd.isna(idx_ma.at[t]) and idx.at[t] >= idx_ma.at[t])
                target = [] if not g_open else list(
                    DE.cross_scores(ctx['F'], syms, t, DE.FACTORS_4).index[:DE.TOP_N])
            else:
                target = list(DE.cross_scores(ctx['F'], syms, t, DE.FACTORS_4).index[:DE.TOP_N])
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity) \
                if cal.get_loc(t) + 1 < len(cal) else None
    curve = pd.Series(eq).sort_index()
    return {'curve': curve, 'fees': fees, 'n_gate_off': n_gate_off}


# ================================================================ 统计件（RESCUE 谱系逐行）
def xsec_ic_series(fa, fb, min_names=30):
    """wo_rescue._xsec_ic_series 逐行同构：逐日截面 Spearman IC。"""
    a, b = fa.align(fb, join='inner')
    out = {}
    for dt in a.index:
        x, y = a.loc[dt], b.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() < min_names:
            continue
        rx, ry = x[m].rank(), y[m].rank()
        if rx.std() == 0 or ry.std() == 0:
            continue
        out[dt] = np.corrcoef(rx, ry)[0, 1]
    return pd.Series(out)


def tstat(ic):
    """wo_rescue._tstat 逐行同构。"""
    ic = ic.dropna()
    if len(ic) < 3 or ic.std(ddof=1) == 0:
        return None, int(len(ic))
    return float(ic.mean() / ic.std(ddof=1) * np.sqrt(len(ic))), int(len(ic))


def decile_spread_fee(fa, fb, fee_rt_pp=0.10):
    """wo_rescue._decile_spread_fee 逐行同构：Top-Bottom 十分位价差均值(pp)−双边费。"""
    a, b = fa.align(fb, join='inner')
    sp = []
    for dt in a.index:
        x, y = a.loc[dt], b.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() < 30:
            continue
        lab = pd.qcut(x[m].rank(method='first'), 10, labels=False)
        sp.append((y[m][lab == 9].mean() - y[m][lab == 0].mean()) * 100)
    sp = pd.Series(sp)
    if sp.empty:
        return None, None, None
    return float(sp.mean()), float(sp.mean() - fee_rt_pp), int(len(sp))


def stationary_boot(x, n_boot=2000, mean_len=10, seed=SEED):
    """日块 stationary bootstrap（平均块长 10，circular，PB-9 谱系）。返回均值数组。"""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n == 0:
        return np.array([])
    p = 1.0 / mean_len
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for b in range(n_boot):
        idxs = np.empty(n, dtype=int)
        i = rng.integers(n)
        for k in range(n):
            idxs[k] = i
            if rng.random() < p:
                i = rng.integers(n)
            else:
                i = (i + 1) % n
        means[b] = x[idxs].mean()
    return means


def perm_baseline(x, n_sub, n_perm=1000, seed=SEED):
    """C4 垫：随机置换基线——从全窗效应序列无放回抽 n_sub 的均值分布。"""
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    out = np.empty(n_perm)
    for k in range(n_perm):
        out[k] = x[rng.permutation(len(x))[:n_sub]].mean()
    return out


def mdd_of(r):
    """域内分段净值回撤（域日 cumprod 链接，近似口径【推断】登记）。"""
    nav = np.cumprod(1.0 + np.asarray(r, dtype=float))
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1.0
    return float(dd.min()) * 100.0 if len(dd) else None


def bh_fdr_q(pvals, m_total=BATCH_BUDGET_M):
    """BH 合并族 m=86：q_i = min_{j>=i} p_(j)*m/j。"""
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p)
    n = len(p)
    q = np.empty(n)
    prev = 1.0
    for rank in range(n, 0, -1):
        i = order[rank - 1]
        prev = min(prev, p[i] * m_total / rank)
        q[i] = prev
    return q
