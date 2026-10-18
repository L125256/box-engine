#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H-A 因子替换研究轨 · 执行脚本（工程保障团队 · 2026-10-18）
================================================================
规格（冻结，禁改判据）：/tmp/trade9_specs/HA_SPEC.md + ha_spec.json
产出：/workspace/repo_ready/research/wo_ha/stage{0..3}_*.json + HA_REPORT.md
      镜像 /tmp/ha_factor/ha_results.json

【开工即冻结的操作性定义（预注册声明，跑后禁改）】
OD1 C1 mom_12m = close_{t-21}/close_{t-252} - 1（规格字面 12-1 动量，非 12-0）。
OD2 C3 obv_slope60 = OBV 的 60 日 OLS 线性回归斜率（对日序 t=0..59）÷ 60 日总成交量
    （=60日均量×60，与引擎 obv_slope20 分母同构放大）。
OD3 C6 brk_vol_score：事件 = 收盘 >= 前 20 日收盘最高（rolling(20).max().shift(1)，
    run_screen break20_high 同构）且 量比(5日均量/20日均量, C5 冻结公式)>1.5；
    计分 = Σ_{k=0..19} (1 - k/20)·event_{t-k}（20 日线性衰减）。
OD4 C7 rev_10d 弱市条件臂：信号日池 idx<MA50（引擎同源 idx/idx_ma）时合成中
    ma20_slope 槽位取 rev_10d，否则沿用 ma20_slope 原值；牛态不出轨、全窗判 P1-P3。
OD5 S5 相关 = 候选与被替换旧因子逐日截面 Spearman ρ 的时间均值（最大值伴行呈报）。
OD6 S3 分位单调 = 五分位 fwd 均值的秩排序恰为升序或降序（argsort∈{[0..4],[4..0]}），
    且 (Q5-Q1) 符号与主 horizon IC 同号。
OD7 Stage2 基线臂 = 带闸 gated F1（生产口径，regime 闸 ON），替换臂同 gated；
    段净年化 = 段内曲线 (末/首)^(365.25/自然日) - 1（wo_hd seg_metrics 谱系）。
OD8 P3 合成信号 IC（D2 口径）= 信号日（每周首个交易日）合成 z-score 截面 Spearman
    vs 前向 5 交易日收盘收益，realC 段（2026-06-01→2026-10-17）逐日均值。
OD9 随机带 = dneg_engine target_fn 谱系（D3 同构：随机 top-5，绕过 regime 闸），
    500 seeds 42..541，双池对称呈报。
OD10 Stage1 数据截断：因子与前向收益面板一律截至 2026-05-31（realC 零接触）；
     fwd20 由截断面内 shift(-20) 计算，末端 20 个交易日自动无 IC（run_screen 谱系）。

【谱系】引擎 = research/wo_dneg/dneg_engine.py（f1_backtest_v2 逐行 + 仪表化，
D0 对拍 maxdiff=0 权威谱系）；筛选对拍 = /tmp/factor_screen/run_screen.py（R3 谱系，
因子计算段逐字复制为 /tmp/ha_factor/r3_factor_ref.py）。
数据态：/tmp/dneg/box_cache（engine_snapshot 解包，与 /tmp/box_cache 逐文件 md5
Stage0 记账核验）。
"""
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, '/workspace/repo_ready/research/wo_dneg')
import dneg_engine as DE

SEED = 42
CUT = pd.Timestamp('2026-05-31')          # Stage1 数据截断（realC 零接触）
REALA = (pd.Timestamp('2025-06-02'), pd.Timestamp('2026-03-31'))
REALB = (pd.Timestamp('2026-04-01'), pd.Timestamp('2026-05-31'))
REALC = (pd.Timestamp('2026-06-01'), pd.Timestamp('2026-10-17'))
CACHE = '/tmp/dneg/box_cache'
CACHE_ALT = '/tmp/box_cache'
OUT = '/workspace/repo_ready/research/wo_ha'
TMP = '/tmp/ha_factor'
os.makedirs(OUT, exist_ok=True)
os.makedirs(TMP, exist_ok=True)

FACTORS_4 = DE.FACTORS_4                  # ma20_slope/obv_slope20/dist_52w_high/mom_1m
# 替换映射（规格§二冻结，禁跑后改）
REPLACE_MAP = {
    'C1': ('mom_12m', 'mom_1m'),
    'C2': ('mom_6m', 'mom_1m'),
    'C3': ('obv_slope60', 'obv_slope20'),
    'C4': ('atr_ratio_chg10', 'dist_52w_high'),
    'C6': ('brk_vol_score', 'dist_52w_high'),
    'C7': ('rev_10d', 'ma20_slope'),      # 弱市条件臂（OD4）
    'C8': ('gap_freq20', 'dist_52w_high'),
}
CAND_ARMS = ['C1', 'C2', 'C3', 'C4', 'C6', 'C7', 'C8']   # 有替换臂者
EVID_ONLY = ['C5', 'C9', 'C10']

D0_DAYS = ['2024-06-03', '2025-06-02', '2026-05-29']     # 对拍 3 交易日（≤05-31）
D0_FACTORS = [('mom_6m', 'mom_6m'), ('atr_ratio_chg10', 'atr_ratio_chg10'),
              ('rev_10d', 'rev_10d')]                    # (新模块名, R3 参照名)


# ================================================================ 数据与新因子
def load_data():
    return DE.load_data(CACHE)


def new_factor_series(d):
    """逐标的自身序列（引擎 build_factors 同构），返回新候选因子 dict[Series]。
    OD1/OD2/OD3 冻结公式。"""
    c, v, o, h, l = d['close'], d['volume'], d['open'], d['high'], d['low']
    pc = c.shift(1)
    out = {}
    out['mom_12m'] = c.shift(21) / c.shift(252) - 1.0                       # C1 (OD1)
    out['mom_6m'] = c / c.shift(126) - 1.0                                  # C2
    obv = (np.sign(c.diff()).fillna(0.0) * v).cumsum()
    w = 60
    tt = np.arange(w, dtype=float)
    tmean, tvar = tt.mean(), tt.var()
    def _slope(win):                                                        # (OD2)
        y = win - win.mean(axis=1, keepdims=True)
        return (y * (tt - tmean)).sum(axis=1) / tvar
    arr = obv.to_numpy(dtype=float)
    n = len(arr)
    sl = np.full(n, np.nan)
    if n >= w:
        sw = np.lib.stride_tricks.sliding_window_view(arr, w)
        sl[w - 1:] = _slope(sw)
    denom = v.rolling(w).mean() * float(w)
    out['obv_slope60'] = pd.Series(sl, index=obv.index) / denom
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    ratio = atr / c
    out['atr_ratio_chg10'] = ratio / ratio.shift(10) - 1.0                  # C4
    vr = v.rolling(5).mean() / v.rolling(20).mean()                          # C5 冻结公式
    out['vol_ratio'] = vr
    brk = (c >= c.rolling(20).max().shift(1)) & (vr > 1.5)
    score = pd.Series(0.0, index=c.index)
    for k in range(20):
        score = score + (1.0 - k / 20.0) * brk.shift(k).fillna(False).astype(float)
    out['brk_vol_score'] = score                                              # C6 (OD3)
    out['rev_10d'] = -(c / c.shift(10) - 1.0)                                # C7
    gap = (o / pc - 1.0).abs()
    out['gap_freq20'] = (gap > 0.01).rolling(20).sum() / 20.0                # C8（冻结 1% 口径）
    return out


def old_factor_series_r3(d):
    """旧四因子，run_screen（R3 谱系）公式，逐标的自身序列（Stage1 S5/IC 用）。"""
    c, v = d['close'], d['volume']
    ma20 = c.rolling(20).mean()
    obv = (np.sign(c.diff()).fillna(0.0) * v).cumsum()
    return {
        'mom_1m': c / c.shift(21) - 1.0,
        'obv_slope20': (obv - obv.shift(20)) / v.rolling(20).sum(),
        'dist_52w_high': c / c.rolling(252, min_periods=200).max() - 1.0,
        'ma20_slope': ma20 / ma20.shift(10) - 1.0,
    }


def panel(series_by_sym, syms):
    return pd.concat({s: series_by_sym[s] for s in syms}, axis=1).sort_index()


# ================================================================ Stage 0 对拍门
def stage0():
    t0 = time.time()
    res = {'stage': 'stage0_gate', 'ts': time.strftime('%F %T'),
           'caches': {}, 'd0_pairing': {}, 'c10_availability': {}, 'gate': None}

    # 1) box_cache md5 记账（唯一快照，双路径逐文件核验）
    import hashlib
    def md5_dir(path):
        rec = {}
        for fn in sorted(os.listdir(path)):
            h = hashlib.md5()
            with open(os.path.join(path, fn), 'rb') as f:
                for chunk in iter(lambda: f.read(1 << 20), b''):
                    h.update(chunk)
            rec[fn] = h.hexdigest()
        return rec
    rec_main = md5_dir(CACHE)
    rec_alt = md5_dir(CACHE_ALT)
    drift = [k for k in rec_main if rec_main.get(k) != rec_alt.get(k)]
    agg = hashlib.md5(json.dumps(rec_main, sort_keys=True).encode()).hexdigest()
    res['caches'] = {'primary': CACHE, 'alt': CACHE_ALT, 'n_files': len(rec_main),
                     'per_file_aggregate_md5': agg, 'drift_files': drift,
                     'note': 'engine_snapshot 解包态，与 /tmp/box_cache 逐文件 md5 一致=零漂移'}

    # 2) C10 funding_pct60 可得性检查（禁换源）
    keys = set()
    for fn in sorted(os.listdir(CACHE)):
        d = json.load(open(os.path.join(CACHE, fn)))
        if isinstance(d, list) and d:
            keys |= set(d[0].keys())
    has_funding = any('funding' in k.lower() or 'rate' in k.lower() for k in keys)
    res['c10_availability'] = {'fields': sorted(keys), 'funding_daily': bool(has_funding),
                               'verdict': 'C10 出局归档（无逐日资金费，禁换源）' if not has_funding
                               else '字段存在，进入 Stage1'}

    # 3) 对拍：新因子模块 vs run_screen.py（R3 谱系）3 因子×3 交易日 maxdiff=0
    sys.path.insert(0, TMP)
    import r3_factor_ref as R3          # run_screen.py 因子计算段逐字复制（谱系）
    data = load_data()
    rows = {}
    for fn in sorted(os.listdir(CACHE)):
        df = pd.DataFrame(json.load(open(os.path.join(CACHE, fn))))
        df['time'] = pd.to_datetime(df['time'])
        rows[fn[:-5]] = df.set_index('time')
    days = [pd.Timestamp(x) for x in D0_DAYS]
    day_keys = [x for x in D0_DAYS]      # run_screen 面板索引为字符串日期（未 to_datetime）
    for new_name, ref_name in D0_FACTORS:
        md = 0.0
        ref_panel = R3.F[ref_name]
        for s in sorted(set(rows) & set(ref_panel.columns)):
            mine = new_factor_series(rows[s])[new_name]
            ref = ref_panel[s] if new_name != 'rev_10d' else -ref_panel[s]
            for t, tk in zip(days, day_keys):
                a, b = mine.get(t, np.nan), ref.get(tk, np.nan)
                if pd.isna(a) and pd.isna(b):
                    continue
                if pd.isna(a) != pd.isna(b):
                    md = np.inf
                    break
                md = max(md, abs(float(a) - float(b)))
            if md == np.inf:
                break
        rev_note = '（rev_10d 取负后对拍：冻结公式=反转符号，R3 原值为 +收益）' \
            if new_name == 'rev_10d' else ''
        res['d0_pairing'][new_name] = {'ref': f'run_screen.py F[{ref_name}]{rev_note}',
                                       'days': D0_DAYS, 'maxdiff': float(md)}
    ok = all(v['maxdiff'] == 0 for v in res['d0_pairing'].values())
    ok = ok and not drift and not has_funding
    res['gate'] = 'PASS' if ok else 'FAIL'
    res['wall_secs'] = round(time.time() - t0, 1)
    json.dump(res, open(f'{OUT}/stage0_gate.json', 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ('d0_pairing', 'c10_availability', 'gate', 'wall_secs')},
                     ensure_ascii=False, indent=1))
    print('aggregate_md5 =', agg, '| drift =', drift)
    return ok


# ================================================================ Stage 1 离线筛选
def _xsec_spearman(fa, fb):
    """run_screen.py xsec_spearman 逐行复制。"""
    a, b = fa.align(fb, join='inner')
    out = {}
    for dt in a.index:
        x, y = a.loc[dt], b.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() < 30:
            continue
        rx, ry = x[m].rank(), y[m].rank()
        if rx.std() == 0 or ry.std() == 0:
            continue
        out[dt] = np.corrcoef(rx, ry)[0, 1]
    return pd.Series(out)


def _stationary_ci(ic, n_boot=1000, mean_len=10, seed=SEED):
    """日块 stationary bootstrap（平均块长10）IC 均值 CI（伴行呈报，非闸门）。"""
    x = ic.to_numpy(dtype=float)
    n = len(x)
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_len
    means = np.empty(n_boot)
    for b in range(n_boot):
        idx, cur, ln = [], int(rng.integers(n)), max(1, rng.geometric(p))
        while len(idx) < n:
            idx.extend((cur + np.arange(ln)) % n)
            cur = int(rng.integers(n))     # stationary bootstrap：新块起点独立均匀重抽
            ln = max(1, rng.geometric(p))
        means[b] = x[np.array(idx[:n])].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def stage1():
    t0 = time.time()
    data = load_data()
    syms = sorted(data)
    names_new = ['mom_12m', 'mom_6m', 'obv_slope60', 'atr_ratio_chg10', 'vol_ratio',
                 'brk_vol_score', 'rev_10d', 'gap_freq20']
    F_new, F_old = {}, {k: {} for k in FACTORS_4}
    for s in syms:
        nf = new_factor_series(data[s])
        for k in names_new:
            F_new.setdefault(k, {})[s] = nf[k]
        of = old_factor_series_r3(data[s])
        for k in FACTORS_4:
            F_old[k][s] = of[k]
    # 面板 + 截断 2026-05-31（realC 零接触，OD10）
    P = {k: panel(v, syms).loc[:CUT] for k, v in F_new.items()}
    Pold = {k: panel(v, syms).loc[:CUT] for k, v in F_old.items()}
    C = panel({s: data[s]['close'] for s in syms}, syms).loc[:CUT]
    O = panel({s: data[s]['open'] for s in syms}, syms).loc[:CUT]
    V = panel({s: data[s]['volume'] for s in syms}, syms).loc[:CUT]

    def colwise(df, func):
        out = pd.DataFrame(np.nan, index=df.index, columns=df.columns, dtype=float)
        for col in df.columns:
            ss = df[col].dropna()
            if len(ss) < 5:
                continue
            out.loc[ss.index, col] = np.asarray(func(ss), dtype=float)
        return out

    fwd = {k: colwise(C, lambda s, k=k: s.shift(-k) / s - 1) for k in (10, 20)}
    # regime（run_screen 谱系）
    ret1 = colwise(C, lambda s: s / s.shift(1) - 1)
    pool_ret = ret1.mean(axis=1)
    idx = (1 + pool_ret.fillna(0)).cumprod()
    idx_ma50 = idx.rolling(50, min_periods=30).mean()
    bull = (idx > idx_ma50)
    vol20 = pool_ret.rolling(20, min_periods=15).std()
    regime_hv = vol20 > vol20.expanding(min_periods=100).median()

    out = {'stage': 'stage1_screen', 'ts': time.strftime('%F %T'),
           'cutoff': str(CUT.date()), 'gates': 'S1-S5 冻结（HA_SPEC §三）',
           'od': 'OD1-OD6/OD10（见 wo_ha_run.py 头注）', 'candidates': {}, 'evidence': {}}

    def screen_one(name, fa, main_hz=20, old_key=None, discount=False, extra=None,
                   rho_against=None):
        e = {}
        s20 = _xsec_spearman(fa, fwd[20]).dropna()
        s10 = _xsec_spearman(fa, fwd[10]).dropna()
        e['n_ic_days_fwd20'] = int(len(s20))
        e['n_ic_days_fwd10'] = int(len(s10))
        if len(s20) >= 30:
            e['fwd20'] = {'ic_mean': float(s20.mean()), 'icir': float(s20.mean() / s20.std()),
                          'ci95': _stationary_ci(s20)}
            yrs = {'2024': ('2024-01-01', '2024-12-31'), '2025': ('2025-01-01', '2025-12-31'),
                   '2026H1': ('2026-01-01', '2026-05-31')}
            e['fwd20']['by_year'] = {y: {'ic_mean': float(s20.loc[a:b].mean()),
                                         'n': int(len(s20.loc[a:b]))}
                                     for y, (a, b) in yrs.items() if len(s20.loc[a:b])}
            e['fwd20']['by_regime'] = {
                'bull': {'ic_mean': float(s20[bull.reindex(s20.index).fillna(False)].mean()),
                         'n': int(bull.reindex(s20.index).fillna(False).sum())},
                'weak': {'ic_mean': float(s20[~bull.reindex(s20.index).fillna(False)].mean()),
                         'n': int((~bull.reindex(s20.index).fillna(False)).sum())}}
        e['fwd10'] = ({'ic_mean': float(s10.mean()), 'icir': float(s10.mean() / s10.std())}
                      if len(s10) >= 30 else None)
        # S1 主 horizon
        f20 = e.get('fwd20')
        s1 = bool(f20 and abs(f20['ic_mean']) >= 0.03 and abs(f20['icir']) >= 0.20)
        # S2 分年同号率 ≥2/3（只计有样本年份；C1 无 2024 为规格预写折扣，非缺年惩罚）
        signs = [np.sign(v['ic_mean']) for v in f20['by_year'].values()] if f20 else []
        nyr = len(signs)
        same = sum(1 for g in signs if g == np.sign(f20['ic_mean']) and g != 0)
        s2 = bool(f20 and nyr > 0 and same / nyr >= 2 / 3)
        e['s2_rate'] = {'same': same, 'n_years': nyr} if f20 else None
        # S3 分位单调（主 horizon，run_screen qcut 谱系）
        qmean = {q: [] for q in range(1, 6)}
        a, b = fa.align(fwd[main_hz], join='inner')
        for dt in a.index:
            x, y = a.loc[dt], b.loc[dt]
            m = x.notna() & y.notna()
            if m.sum() < 50:
                continue
            lab = pd.qcut(x[m].rank(method='first'), 5, labels=False) + 1
            for q in range(1, 6):
                qmean[q].append(y[m][lab == q].mean())
        qm = {q: float(np.mean(v)) for q, v in qmean.items() if len(v) >= 50}
        e['quintile_means_fwd20'] = qm
        s3 = False
        if len(qm) == 5 and f20:
            qv = [qm[q] for q in range(1, 6)]
            order = list(np.argsort(qv))
            mono = order in ([0, 1, 2, 3, 4], [4, 3, 2, 1, 0])
            s3 = bool(mono and np.sign(qv[4] - qv[0]) == np.sign(f20['ic_mean']))
        # S4 有效 IC 日
        n24 = int((s20.index < '2025-01-01').sum()) if len(s20) else 0
        e['n_ic_days_2024'] = n24
        thr = 400 if n24 > 0 else 250
        s4 = bool(e['n_ic_days_fwd20'] >= thr)
        e['s4_threshold'] = thr
        e['discount'] = bool(discount or n24 == 0)
        # S5 与被替换旧因子 |ρ|<=0.9（OD5）
        s5v = None
        if old_key:
            sa, sb = fa.align(Pold[old_key], join='inner')
            rhos = []
            for dt in sa.index:
                x, y = sa.loc[dt], sb.loc[dt]
                m = x.notna() & y.notna()
                if m.sum() < 30:
                    continue
                rhos.append(np.corrcoef(x[m].rank(), y[m].rank())[0, 1])
            if rhos:
                s5v = {'rho_mean': float(np.mean(rhos)), 'rho_max_abs': float(np.max(np.abs(rhos)))}
        s5 = bool(s5v and abs(s5v['rho_mean']) <= 0.9) if old_key else None
        # 候选自身失效边界（规格§二预写）：如 C1 与 dist_52w_high ρ>0.9 出局
        rho_bnd = None
        if rho_against:
            sa2, sb2 = fa.align(Pold[rho_against], join='inner')
            rhos2 = []
            for dt in sa2.index:
                x2, y2 = sa2.loc[dt], sb2.loc[dt]
                m2 = x2.notna() & y2.notna()
                if m2.sum() < 30:
                    continue
                rhos2.append(np.corrcoef(x2[m2].rank(), y2[m2].rank())[0, 1])
            if rhos2:
                rho_bnd = {'vs': rho_against, 'rho_mean': float(np.mean(rhos2)),
                           'rho_max_abs': float(np.max(np.abs(rhos2))),
                           'pass': bool(abs(np.mean(rhos2)) <= 0.9)}
        e.update({'S1': s1, 'S2': s2, 'S3': s3, 'S4': s4, 'S5': s5v,
                  'S5_pass': s5, 'rho_boundary': rho_bnd, 'extra': extra or {}})
        e['OVERALL'] = 'PASS' if (s1 and s2 and s3 and s4
                                  and (s5 is not False if old_key else True)
                                  and (rho_bnd['pass'] if rho_bnd else True)) else 'FAIL'
        return e

    # C6 事件计数（冻结：样本按事件数计，≥500；量比=5日均量/20日均量）
    vr5 = colwise(V, lambda s: s.rolling(5).mean() / s.rolling(20).mean())
    brk = (C >= colwise(C, lambda s: s.rolling(20).max().shift(1)))
    ev = (brk & (vr5 > 1.5)).fillna(False)
    fwd5 = colwise(C, lambda s: s.shift(-5) / s - 1)
    n_ev = int((ev & fwd5.notna()).to_numpy().sum())

    for cid in CAND_ARMS:
        nm, old_key = REPLACE_MAP[cid]
        extra = {}
        if cid == 'C6':
            extra['n_events_fwd5_valid'] = n_ev
            e = screen_one(nm, P[nm], old_key=old_key, extra=extra,
                           rho_against='dist_52w_high' if cid == 'C1' else None)
            e['S4'] = bool(n_ev >= 500)
            e['S4_note'] = 'C6 事件型：S4 按预注册失效边界改用事件数≥500（规格§二 C6）'
            e['OVERALL'] = 'PASS' if (e['S1'] and e['S2'] and e['S3'] and e['S4']
                                      and e['S5_pass'] is not False
                                      and (e['rho_boundary']['pass'] if e['rho_boundary'] else True)) else 'FAIL'
        else:
            e = screen_one(nm, P[nm], old_key=old_key,
                           discount=(cid == 'C1'), extra=extra,
                           rho_against='dist_52w_high' if cid == 'C1' else None)
        out['candidates'][cid] = {'name': nm, 'replaces': old_key, **e}

    # 证据轨：C5 vol_ratio（如实筛）/ C9 breadth（状态因子，移交 H-D）/ C10 已归档
    out['evidence']['C5_vol_ratio'] = screen_one('vol_ratio', P['vol_ratio'])
    out['evidence']['C5_vol_ratio']['note'] = '无替换臂（仅 C6 突破确认形式生效）'
    above50 = colwise(C, lambda s: (s > s.rolling(50, min_periods=40).mean()).astype(float))
    breadth = above50.mean(axis=1)
    pf20 = fwd[20].mean(axis=1)

    def ts_corr(a, b):
        j = pd.concat([a.rename('a'), b.rename('b')], axis=1).dropna()
        if len(j) < 60:
            return None
        return float(np.corrcoef(j['a'].rank(), j['b'].rank())[0, 1])
    out['evidence']['C9_breadth_above_ma50'] = {
        'pool_fwd20_spearman': ts_corr(breadth.shift(1), pf20), 'n': int(len(pf20)),
        'note': '状态因子非选票因子，不进四因子合成；证据移交 H-D 状态门轨（规格§二 C9）'}
    out['evidence']['C10_funding_pct60'] = 'D0 可得性检查出局（box_cache 无逐日资金费，禁换源）'

    surv = [cid for cid in CAND_ARMS if out['candidates'][cid]['OVERALL'] == 'PASS']
    out['survivors'] = surv
    out['wall_secs'] = round(time.time() - t0, 1)
    json.dump(out, open(f'{OUT}/stage1_screen.json', 'w'), ensure_ascii=False, indent=1)
    print('Stage1 survivors =', surv, f"({out['wall_secs']}s)")
    for cid, e in out['candidates'].items():
        print(cid, e['name'], e['OVERALL'],
              'IC=%.4f ICIR=%.3f' % (e['fwd20']['ic_mean'], e['fwd20']['icir'])
              if e.get('fwd20') else '', 'S:', e['S1'], e['S2'], e['S3'], e['S4'], e['S5_pass'])
    return surv, out


# ================================================================ Stage 2 替换回测
_DATA = None
_POOLS = None
_FBASE = None
_FARM = None        # {(cid,pname): F dict}
_C7WEAK = None      # {pname: weak Series}


def _seg_ann(curve, t0, t1):
    seg = curve[(curve.index >= t0) & (curve.index <= t1)]
    if len(seg) < 2:
        return None
    yrs = (seg.index[-1] - seg.index[0]).days / 365.25
    return float((seg.iloc[-1] / seg.iloc[0]) ** (1 / max(yrs, 1e-9)) - 1) * 100.0


def _weak_mask(syms):
    close = pd.DataFrame({s: _DATA[s]['close'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(_DATA[s].index) for s in syms])))
    close = close.reindex(cal)
    idx = close.mean(axis=1)
    return (idx < idx.rolling(DE.MA_REG).mean()).fillna(False)


def _build_F():
    """F_base + 各候选臂 F（含 C7 弱市条件臂 OD4，逐池注入）。"""
    global _FBASE, _FARM, _C7WEAK
    _FBASE = DE.build_factors(_DATA)
    _FARM, _C7WEAK = {}, {}
    for cid in CAND_ARMS:
        nm, old = REPLACE_MAP[cid]
        for pname, syms in _POOLS.items():
            F = DE.build_factors(_DATA)
            if cid == 'C7':
                weak = _weak_mask(syms)
                _C7WEAK[pname] = weak
                for s, df in F.items():
                    rev = new_factor_series(_DATA[s])['rev_10d']
                    w = weak.reindex(df.index).fillna(False).to_numpy()
                    df['ma20_slope'] = np.where(w, rev.to_numpy(), df['ma20_slope'].to_numpy())
            else:
                for s, df in F.items():
                    df[old] = new_factor_series(_DATA[s])[nm]
            _FARM[(cid, pname)] = F


def _w2run(task):
    cid, pname = task
    syms = _POOLS[pname]
    F = _FBASE if cid == 'base' else _FARM[(cid, pname)]
    t0 = time.time()
    r = DE.run_instr(_DATA, F=F, syms=syms, gated=True, factors=FACTORS_4, record=False)
    curve = r['curve']
    return {'cid': cid, 'pname': pname, 'wall': round(time.time() - t0, 1),
            'ann': {sn: _seg_ann(curve, a, b)
                    for sn, (a, b) in {'realA': REALA, 'realB': REALB, 'realC': REALC}.items()},
            'curve_realC': {str(k.date()): float(v) for k, v in curve.items()
                            if REALC[0] <= k <= REALC[1]}}


def composite_ic(F, syms, t0, t1):
    """P3：合成信号 fwd5 IC（D2 口径，OD8）。"""
    close = pd.DataFrame({s: _DATA[s]['close'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(_DATA[s].index) for s in syms])))
    close = close.reindex(cal)
    fwd5 = close.shift(-5) / close - 1
    iso = cal.isocalendar()
    sig = pd.DatetimeIndex(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)
    sig = sig[(sig >= t0) & (sig <= t1)]
    ics = []
    for t in sig:
        score = DE.cross_scores(F, syms, t, FACTORS_4)
        y = fwd5.loc[t]
        m = score.index.intersection(y.dropna().index)
        if len(m) < 30 or score.std() == 0:
            continue
        ics.append(np.corrcoef(score[m].rank(), y[m].rank())[0, 1])
    return {'mean': float(np.mean(ics)) if ics else None, 'n_days': len(ics)}


def _w2ic(task):
    cid, pname = task
    syms = _POOLS[pname]
    F = _FBASE if cid == 'base' else _FARM[(cid, pname)]
    return {'cid': cid, 'pname': pname, 'ic_realC': composite_ic(F, syms, *REALC)}


def stage2(surv):
    t0 = time.time()
    global _DATA, _POOLS
    _DATA = load_data()
    _POOLS = DE.build_pools(_DATA)
    _build_F()
    arms = ['base'] + surv
    tasks = [(c, p) for c in arms for p in _POOLS]
    with Pool(32) as pool:
        runs = {(r['cid'], r['pname']): r for r in pool.map(_w2run, tasks)}
        ics = {(r['cid'], r['pname']): r for r in pool.map(_w2ic, tasks)}
    # realC 烧毁记账（一次即烧）
    burn = [{'cid': c, 'pname': p, 'touched': ['backtest_realC', 'composite_IC_realC'],
             'burned_at': time.strftime('%F %T')}
            for c in surv for p in _POOLS]

    out = {'stage': 'stage2_backtest', 'ts': time.strftime('%F %T'),
           'baseline': '带闸 gated F1（OD7），dneg_engine 权威谱系，seed=42',
           'gates': 'P1 X=realC净年化改善>=+10pp；P2 Y=realA净年化降幅<=5pp；P3 realC合成fwd5 IC>=基线+0.02；双池分别判定、双池全过才算过',
           'realC_burn_ledger': burn, 'runs': {}, 'p3': {}, 'criteria': {}, 'passers': []}
    for p in _POOLS:
        base = runs[('base', p)]['ann']
        for c in surv:
            a = runs[(c, p)]['ann']
            x = round(a['realC'] - base['realC'], 2)
            y = round(a['realA'] - base['realA'], 2)
            ic_a = ics[(c, p)]['ic_realC']
            ic_b = ics[('base', p)]['ic_realC']
            p3 = (ic_a['mean'] - ic_b['mean']) if (ic_a['mean'] is not None and ic_b['mean'] is not None) else None
            p3v = round(p3, 4) if p3 is not None else None
            ok = (x >= 10.0) and (y >= -5.0) and (p3v is not None and p3v >= 0.02)
            out['runs'][f'{c}|{p}'] = {'arm': a, 'baseline': base, 'X_pp': x, 'Y_pp': y}
            out['p3'][f'{c}|{p}'] = {'arm_ic': ic_a, 'base_ic': ic_b, 'diff': p3v}
            out['criteria'][f'{c}|{p}'] = {
                'P1_X_ge_10pp': {'value': x, 'pass': bool(x >= 10.0)},
                'P2_Y_ge_minus5pp': {'value': y, 'pass': bool(y >= -5.0)},
                'P3_ic_diff_ge_0.02': {'value': p3v, 'pass': bool(p3v is not None and p3v >= 0.02)},
                'OVERALL': 'PASS' if ok else 'FAIL'}
            if ok:
                out['passers'].append(f'{c}|{p}')
    # 双池全过才算过
    final = [c for c in surv if all(out['criteria'][f'{c}|{p}']['OVERALL'] == 'PASS' for p in _POOLS)]
    out['passers_both_pools'] = final
    out['wall_secs'] = round(time.time() - t0, 1)
    json.dump(out, open(f'{OUT}/stage2_backtest.json', 'w'), ensure_ascii=False, indent=1)
    print('Stage2 done (%.0fs)' % out['wall_secs'])
    for k, v in out['criteria'].items():
        print(k, v['OVERALL'], 'X=%+.2f Y=%+.2f P3=%s' % (v['P1_X_ge_10pp']['value'],
              v['P2_Y_ge_minus5pp']['value'], v['P3_ic_diff_ge_0.02']['value']))
    print('双池全过:', final)
    return final, out


# ================================================================ Stage 3 组合 + 闸门
def _combo_F(slots):
    """slots: {old_factor: (cid, new_name)}。F = 四因子合成，替换槽位换新因子。"""
    F = DE.build_factors(_DATA)
    for s, df in F.items():
        nf = new_factor_series(_DATA[s])
        for old, (cid, nm) in slots.items():
            df[old] = nf[nm]
    return F


def _w3run(task):
    key, pname = task
    syms = _POOLS[pname]
    F = _FARM3[key][pname]
    r = DE.run_instr(_DATA, F=F, syms=syms, gated=True, factors=FACTORS_4, record=False)
    return {'key': key, 'pname': pname,
            'ann': {sn: _seg_ann(r['curve'], a, b)
                    for sn, (a, b) in {'realA': REALA, 'realB': REALB, 'realC': REALC}.items()},
            'curve': {str(k.date()): float(v) for k, v in r['curve'].items()}}


def _w3rand(task):
    pname, seed = task
    syms = _POOLS[pname]

    def tf(rng, ss):
        return list(rng.choice(ss, DE.TOP_N, replace=False))
    r = DE.run_instr(_DATA, F=None, syms=syms, gated=False, factors=FACTORS_4,
                     target_fn=tf, record=False, rng_seed=seed)
    return {'pname': pname, 'seed': seed, 'ann_realC': _seg_ann(r['curve'], *REALC)}


def stage3(final2, stage1_out):
    t0 = time.time()
    out = {'stage': 'stage3_combo', 'ts': time.strftime('%F %T'),
           'rule': 'Stage2 通过者按筛选窗 fwd20 ICIR 降序取<=3 等权 z-score 合成替换，重跑 P1-P3；'
                   'LOTO（逐因子去一/留一）+ 日块/月块 stationary bootstrap 1000 + 随机带 500 seeds(42..541) 同表呈报'}
    if not final2:
        out['verdict'] = 'NOT_RUN：Stage2 无双池全过候选 → 组合替换不触发（HA_SPEC 失败路径：H-A 归档，复活条件=新评估段累积或制度性新证据）'
        out['wall_secs'] = 0.0
        json.dump(out, open(f'{OUT}/stage3_combo.json', 'w'), ensure_ascii=False, indent=1)
        print('Stage3 NOT_RUN（Stage2 全灭）')
        return out

    global _FARM3
    cands = sorted(final2, key=lambda c: -stage1_out['candidates'][c]['fwd20']['icir'])[:3]
    slots = {}
    for c in cands:
        nm, old = REPLACE_MAP[c]
        if old not in slots:
            slots[old] = (c, nm)
        else:
            print(f'同槽位冲突 {c} vs {slots[old][0]}：取筛选窗 ICIR 更高者（{slots[old][0]}）')
    out['combo'] = {'candidates': cands, 'slots': {k: v[0] + ':' + v[1] for k, v in slots.items()},
                    'weights': '等权 z-score（引擎 cross_scores 冻结语义）'}
    _FARM3 = {'combo': {p: _combo_F(slots) for p in _POOLS}}
    for old in slots:                                   # LOTO 去一：槽位回退原旧因子
        s2 = {k: v for k, v in slots.items() if k != old}
        _FARM3[f'drop_{old}'] = {p: _combo_F(s2) if s2 else DE.build_factors(_DATA) for p in _POOLS}
    for old, (c, nm) in slots.items():                  # LOTO 留一：仅该因子替换
        _FARM3[f'only_{old}'] = {p: _combo_F({old: (c, nm)}) for p in _POOLS}
    keys = list(_FARM3)
    tasks = [(k, p) for k in keys for p in _POOLS]
    with Pool(32) as pool:
        res = pool.map(_w3run, tasks)
        ics = pool.map(_w3ic, [(k, p) for k in keys for p in _POOLS])
    R = {(r['key'], r['pname']): r for r in res}
    I = {(r['key'], r['pname']): r for r in ics}
    # 基线复用 Stage2（base 已烧，禁重跑 realC；直接引用 stage2 json 的曲线不重算）
    st2 = json.load(open(f'{OUT}/stage2_backtest.json'))
    base_ann = {p: st2['runs'][f'base|{p}']['arm'] for p in _POOLS}
    base_ic = {p: st2['p3'][f'base|{p}']['base_ic'] for p in _POOLS}

    crit = {}
    for p in _POOLS:
        a, b = R[('combo', p)]['ann'], base_ann[p]
        x = round(a['realC'] - b['realC'], 2)
        y = round(a['realA'] - b['realA'], 2)
        p3 = round(I[('combo', p)]['ic_realC']['mean'] - base_ic[p]['mean'], 4)
        ok = x >= 10.0 and y >= -5.0 and p3 >= 0.02
        crit[f'combo|{p}'] = {'P1_X': x, 'P2_Y': y, 'P3': p3, 'OVERALL': 'PASS' if ok else 'FAIL'}
    both = all(v['OVERALL'] == 'PASS' for v in crit.values())
    out['criteria'] = crit
    out['combo_ann'] = {p: R[('combo', p)]['ann'] for p in _POOLS}
    out['combo_ic_realC'] = {p: I[('combo', p)]['ic_realC'] for p in _POOLS}

    # LOTO 同表呈报（P1-P3 重算，伴行）
    loto = {}
    for k in keys:
        if k == 'combo':
            continue
        loto[k] = {}
        for p in _POOLS:
            a = R[(k, p)]['ann']
            p3 = round(I[(k, p)]['ic_realC']['mean'] - base_ic[p]['mean'], 4) \
                if I[(k, p)]['ic_realC']['mean'] is not None else None
            loto[k][p] = {'X_pp': round(a['realC'] - base_ann[p]['realC'], 2),
                          'Y_pp': round(a['realA'] - base_ann[p]['realA'], 2), 'P3': p3}
    out['loto'] = loto

    # bootstrap：realC 日净收益 日块(10)/月块(21) stationary bootstrap 1000 → 年化 CI
    bt = {}
    for p in _POOLS:
        curve = pd.Series({pd.Timestamp(k): v for k, v in R[('combo', p)]['curve'].items()}).sort_index()
        r = curve.pct_change().dropna()
        r = r[(r.index >= REALC[0]) & (r.index <= REALC[1])]
        yrs = (r.index[-1] - r.index[0]).days / 365.25
        row = {}
        for blk, ml in (('daily_block10', 10), ('monthly_block21', 21)):
            anns = _boot_ann(r, ml, yrs)
            row[blk] = {'ann_p2.5_pct': round(float(np.percentile(anns, 2.5)) * 100, 2),
                        'ann_p97.5_pct': round(float(np.percentile(anns, 97.5)) * 100, 2),
                        'ci_excludes_zero': bool(np.percentile(anns, 2.5) > 0 or np.percentile(anns, 97.5) < 0)}
        bt[p] = row
    out['bootstrap_realC'] = bt

    # 随机带 500 seeds（OD9，D3 target_fn 谱系）
    with Pool(32) as pool:
        rand = pool.map(_w3rand, [(p, s) for p in _POOLS for s in range(42, 542)])
    rb = {}
    for p in _POOLS:
        v = np.array([x['ann_realC'] for x in rand if x['pname'] == p], dtype=float)
        combo_x = R[('combo', p)]['ann']['realC']
        rb[p] = {'n': int(len(v)), 'p5': round(float(np.percentile(v, 5)), 2),
                 'p50': round(float(np.percentile(v, 50)), 2),
                 'p95': round(float(np.percentile(v, 95)), 2),
                 'combo_realC_ann': combo_x,
                 'combo_above_p95': bool(combo_x > float(np.percentile(v, 95)))}
    out['random_band_500seeds'] = rb
    out['verdict'] = ('PASS' if both else 'FAIL') + '（组合替换 P1-P3 双池判定）'
    out['wall_secs'] = round(time.time() - t0, 1)
    json.dump(out, open(f'{OUT}/stage3_combo.json', 'w'), ensure_ascii=False, indent=1)
    print('Stage3 done (%.0fs)' % out['wall_secs'], out['verdict'])
    for k, v in crit.items():
        print(k, v)
    return out


def _w3ic(task):
    key, pname = task
    return {'key': key, 'pname': pname,
            'ic_realC': composite_ic(_FARM3[key][pname], _POOLS[pname], *REALC)}


def _boot_ann(r, mean_len, yrs, n_boot=1000, seed=SEED):
    x = r.to_numpy(dtype=float)
    n = len(x)
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_len
    out = np.empty(n_boot)
    for b in range(n_boot):
        idx, cur, ln = [], int(rng.integers(n)), max(1, rng.geometric(p))
        while len(idx) < n:
            idx.extend((cur + np.arange(ln)) % n)
            cur = int(rng.integers(n))     # 新块起点独立均匀重抽
            ln = max(1, rng.geometric(p))
        out[b] = (np.prod(1 + x[np.array(idx[:n])]) ** (1 / max(yrs, 1e-9)) - 1)
    return out


# ================================================================ main
if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which == 'stage0':
        ok = stage0()
        sys.exit(0 if ok else 2)
    if which == 'stage1':
        surv, _ = stage1()
        sys.exit(0)
    if which == 'stage2':
        s1 = json.load(open(f'{OUT}/stage1_screen.json'))
        surv = s1['survivors']
        final2, _ = stage2(surv)
        sys.exit(0)
    if which == 'stage3':
        s1 = json.load(open(f'{OUT}/stage1_screen.json'))
        s2 = json.load(open(f'{OUT}/stage2_backtest.json'))
        s3 = stage3(s2['passers_both_pools'], s1)
        sys.exit(0)
    # all：顺序执行（Stage0 不过全停）
    ok = stage0()
    if not ok:
        print('!! Stage0 对拍门 FAIL —— 全线停，报告已落盘')
        sys.exit(2)
    surv, s1 = stage1()
    final2, s2 = ([] , None)
    if surv:
        final2, s2 = stage2(surv)
    else:
        print('Stage1 全灭 → 失败路径归档')
    s3 = stage3(final2, s1)
    agg = {'ticket': 'H-A', 'ts': time.strftime('%F %T'),
           'stage0_gate': json.load(open(f'{OUT}/stage0_gate.json'))['gate'],
           'stage1_survivors': surv, 'stage2_passers_both_pools': final2,
           'stage3_verdict': s3.get('verdict')}
    json.dump(agg, open(f'{TMP}/ha_results.json', 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(agg, ensure_ascii=False, indent=1))
