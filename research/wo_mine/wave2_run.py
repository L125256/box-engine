#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WAVE2 · W2-A 四方向 36 变体（工程唯一施工依据=METHOD_BOOK_W2A.md 预注册冻结稿，逐字照抄零发挥）
================================================================================================
R10 红线：本件域标签只作离线研究分层，任何函数不产出「域读数→仓位」映射（MINE_SPEC §5.4）。
预算声明（§七 冻结）：36 变体=方向①16（V01–V16）+方向③8（V17–V24）+方向②8（V25–V32）
+方向④4（V33–V36，读数件）。运行期加一格=该方向整方向判无效（MINE_SPEC §3.7）。
判线：MINE_SPEC §五 六腿 C1–C6 逐字承继，本批唯一适配=批内 FDR m=36（BH q=0.10，
36 变体一次性登记，禁分批放宽）；D4 四读数点无 p 值不入拒绝域；探针/邻域格只记账不判生死。
烧窗禁触（§一.6）：fd/brk realC 窗（2026-06-01→2026-10-18）不入判线，输出禁出现 realC 判线列。
饱和禁重复清单（§二 六条）开工前挂账，逐变体 notes 携带查重标注。
用法：
  python3 wave2_run.py d0                # D0 五锚对拍（一发验证，不过禁跑）
  python3 wave2_run.py smoke D1|D2|D3|D4 # 每方向冒烟（截断窗，R8）
  python3 wave2_run.py full  D1|D2|D3|D4 # 全量分方向（R8 分块）
  python3 wave2_run.py assemble          # FACTBOOK_WAVE2 + FDR m=36 + 判定 + 报告数据
产出：wave2_partial_D*.json / FACTBOOK_WAVE2.jsonl / FDR_W2_M36.jsonl / wave2_result.json
"""
import json
import os
import sys
import time
from multiprocessing import get_context

import numpy as np
import pandas as pd
import scipy.stats as sst

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mine_common as MC
import batch1_run as B1
import batch3_run as B3

OUT = MC.OUT_DIR
# 【数据态事件·R7 登记】2026-10-20 11:48 /tmp/box_cache 顶层被外部刷新为 20261020 vintage
# （177 文件全部变更），覆盖了工作快照。经 batch0_domains.py 冻结的 perfile-agg md5
# （D0_RESULT.workdir_perfile_agg=2b2c9572…）逐目录实测定位：唯一命中=/tmp/box_cache_fresh
# （snapshot_20261019，asof 2026-10-18，176 文件）。处置：复制为 /tmp/box_cache_w2a
# （非破坏，各候选目录均不删除），本运行唯一数据态=/tmp/box_cache_w2a；
# 注意 /tmp/box_cache/box_cache 与 repo .cache/box_cache=10-17 vintage（0e4c4fb9…，
# RESCUE 登记口径）≠本批锚 vintage，勿混用（首轮 D0 armC 0.0513pp 漂移即误用该副本所致）。
MC.CACHE = '/tmp/box_cache_w2a'
FULL = B1.FULL
REALC = B1.REALC
SMOKE_WIN = B1.SMOKE_WIN
N_PROC = 32
BATCH = 'W2A'
D1N = MC.D1_NAMES
BUDGET = {'D1': 16, 'D2': 8, 'D3': 8, 'D4': 4, 'total': 36}
M_W2 = 36                      # 批内 FDR 冻结 m
MAIN = '2025-06-01'            # fd/brk 谱系主窗起点（入场日口径，K3/K5 同）
COLS = B3.COLS
DOM_EN = {'牛稳': 'niuwen', '牛躁': 'niunao', '弱稳': 'ruowen', '弱躁': 'ruozao'}


# ================================================================ D0 五锚（§七，一发验证，不过禁跑）
def d0_gate():
    t0 = time.time()
    checks = {}
    # ① fd ctrl meanR 1.1798（n=1802）重放（batch3 K5 machinery 逐字复用）
    trs_ctrl = _fd_trades('K5-fd-exit-ctrl')
    fd = json.load(open('/workspace/repo_ready/research/wo_fdbrk/fd_result.json'))
    want = fd['final']['main']
    m1 = float(np.mean([t['r'] for t in trs_ctrl]))
    checks['fd_ctrl_meanR'] = {'got': {'n': len(trs_ctrl), 'meanR': round(m1, 4)},
                               'want': {'n': want['n'], 'meanR': want['mean']},
                               'tol': 'n 逐位 / mean ±0.05', 'verdict': B1.av(m1, want['mean'], 0.05)
                               if len(trs_ctrl) == want['n'] else 'MISS'}
    # 落盘 ctrl 交易供工单⑤费敏感解析复用（ep/ei/xi/xpx，零二次扫描）
    json.dump([{'tkr': t['tkr'], 'et': t['et'], 'ep': t['ep'], 'ei': t['ei'],
                'xi': t['xi'], 'xc': t['xc']} for t in trs_ctrl],
              open('/tmp/wo_mine/w2a_fd_ctrl_trades.json', 'w'))
    # ② D-A 语义重放 1.4930（n=1816）（batch3 mk_partial(True) 逐字复用）
    trs_da = _fd_trades('K5-fd-exit-partial3r-breakeven')
    m2 = float(np.mean([t['r'] for t in trs_da]))
    checks['fd_DA_meanR'] = {'got': {'n': len(trs_da), 'meanR': round(m2, 4)},
                             'want': {'n': 1816, 'meanR': 1.4930},
                             'tol': 'n 逐位 / mean ±0.05',
                             'verdict': B1.av(m2, 1.4930, 0.05) if len(trs_da) == 1816 else 'MISS'}
    # ③ c4 IC 序列 vs batch1 lineage maxdiff=0（batch1 run_c4 谱系代码路径逐字复用）
    ic20 = _c4_ic20()
    lin = B1.c4_lineage_check(ic20)
    checks['c4_lineage'] = {'got': {'maxdiff': lin.get('ic_series_maxdiff'),
                                    'identical': lin.get('identical'),
                                    'ref_t': lin.get('ref_t_extended'), 'ref_n': lin.get('ref_n'),
                                    'mine_n': lin.get('mine_n')},
                            'want': {'maxdiff': 0, 'identical': True},
                            'tol': 'maxdiff=0 且 n 逐位',
                            'verdict': 'hit' if lin.get('identical') is True else 'MISS'}
    # ④ armC FULL_avoid 43.7883/69.7292 重放 ±0.05（batch1 run_s3d1 骨架逐字复用）
    got4 = _armc_avoid()
    ok4 = all(abs(got4[p] - w) <= 0.05 for p, w in
              (('old131', 43.7883), ('full144', 69.7292)))
    checks['armC_FULL_avoid'] = {'got': got4, 'want': {'old131': 43.7883, 'full144': 69.7292},
                                 'tol': '±0.05', 'verdict': 'hit' if ok4 else 'MISS'}
    # ⑤ k1p70 grid 六点逐位（数据已在盘，零新回测；V36 重放逐位 D0 已 hit 承继）
    g = json.load(open(os.path.join(OUT, 'k1p70_result.json')))
    grid = {(r['pool'], r['tier']): r for r in g['grid']}
    WANT5 = {('old131', 'p70'): (128.2103, 13.04, 237), ('old131', 'p75'): (111.2115, 11.04, 177),
             ('old131', 'p80'): (-8.7673, 49.08, 155), ('full144', 'p70'): (100.7821, 19.46, 237),
             ('full144', 'p75'): (128.8728, 28.88, 155), ('full144', 'p80'): (189.6599, 27.9, None)}
    det5, ok5 = {}, True
    for k, w in WANT5.items():
        r = grid[k]
        got = (r['avoid_pp'], r['mdd_red_pct'], r['n_off_exec_days'])
        ok = abs(got[0] - w[0]) <= 0.0001 and abs(got[1] - w[1]) <= 0.01 and \
            (w[2] is None or got[2] == w[2])
        det5['%s|%s' % k] = {'got': got, 'want': w, 'verdict': 'hit' if ok else 'MISS'}
        ok5 = ok5 and ok
    d0_hits = all(c['verdict'] == 'hit' for c in g['d0']['checks'])
    checks['k1p70_grid6'] = {'detail': det5, 'k1p70_own_d0': 'hit' if d0_hits else 'MISS',
                             'tol': 'avoid ±0.0001 / mdd_red ±0.01 / OFF_days 逐位',
                             'verdict': 'hit' if (ok5 and d0_hits) else 'MISS'}
    res = {'ts': time.strftime('%F %T'), 'spec': 'METHOD_BOOK_W2A §七 D0 五锚（一发验证，不过禁跑）',
           'checks': checks,
           'all_pass': all(c['verdict'] == 'hit' for c in checks.values()),
           'runtime_sec': round(time.time() - t0, 1)}
    json.dump(res, open(os.path.join(OUT, 'd0_gate_wave2.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    for k, c in checks.items():
        print(f"  D0 {k}: {c['verdict']}", flush=True)
    print(f"D0 五锚：all_pass={res['all_pass']} → {'放行' if res['all_pass'] else '停工'}", flush=True)
    return res


def _fd_trades(vid):
    """batch3 K5 逐字路径（_fd_worker 同构）：fd 冻结臂入场一行不动，仅出场经 exit_fn 注入。"""
    sys.path.insert(0, '/workspace/repo_ready/research/wo_fdbrk')
    sys.path.insert(0, '/tmp/eng_wt_rc')
    import common_fdbrk as CF
    CF.CACHE = MC.CACHE          # 数据态事件：唯一数据态=snapshot_20261019（见头注登记）
    pool, bull, _ = CF.pool_bull()
    fns = B3._fd_exit_fns()
    trs = []
    for tk, bars in pool.items():
        for t in B3.scan_fd_exit(bars, bull, fns[vid]):
            trs.append(dict(tkr=tk, **t))
    return [t for t in trs if t['et'] >= CF.MAIN]


def _c4_ic20():
    """batch1 run_c4 核心（PC-4 冻结，无 LOTO）——lineage 对拍输入。"""
    ctx = MC.build_ctx()
    data, pools = ctx['data'], ctx['pools']
    old131, full144 = pools['old131'], pools['full144']
    new13 = sorted(set(full144) - set(old131))
    C = pd.concat({s: data[s]['close'] for s in sorted(data)}, axis=1).sort_index()
    fwd20 = C.shift(-20) / C - 1
    ret20 = C / C.shift(20) - 1
    idx_old, idx_new = ret20[old131].mean(axis=1), ret20[new13].mean(axis=1)
    rs = pd.DataFrame(index=C.index, columns=C.columns, dtype=float)
    for s in C.columns:
        rs[s] = ret20[s] - (idx_new if s in old131 else idx_old)
    ic = MC.xsec_ic_series(rs, fwd20)
    return ic[(ic.index >= FULL[0]) & (ic.index <= FULL[1])]


def _armc_spec(pname, win):
    """batch1 run_s3d1 armC 臂 spec 逐字（g2 门 + s3 语义 + PB-5 费压）。"""
    P = MC.build_ctx()[pname]
    thr = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool'][pname]
    vol_hi = (P['vol20'] > thr).fillna(False)
    down = (P['idx'] < P['idx_ma']).fillna(False)
    g2 = (vol_hi & down).fillna(False)
    return {'pname': pname, 'win': win, 'fee': B1.FEE_S, 'fund': B1.FUND_S,
            'overlay': {'off': g2.shift(1).fillna(False), 'mode': 's3'}}


def _armc_avoid():
    specs, keys = [], []
    for p in ('old131', 'full144'):
        specs.append({'pname': p, 'win': None, 'fee': B1.FEE_S, 'fund': B1.FUND_S})
        keys.append((p, 'base'))
        specs.append(_armc_spec(p, None))
        keys.append((p, 'armC'))
    res = dict(zip(keys, B1.run_arms(specs)))
    out = {}
    for p in ('old131', 'full144'):
        gs = B1.seg_stats(res[(p, 'armC')]['curve'], *FULL)
        bs = B1.seg_stats(res[(p, 'base')]['curve'], *FULL)
        out[p] = round(gs['ret_pp'] - bs['ret_pp'], 4)
    return out


# ================================================================ 行构建（22 字段同格式，batch=W2A）
def _fix(rows):
    for r in rows:
        r['batch'] = BATCH
    return rows


def fw_rows_w2(vid, family, pname, arm_curve, base_curve, win, band_wins=None,
               lag_ok=None, anchor_ref='new', notes=''):
    """B1.framework_variant_rows 逐字复用，仅 batch 改 W2A（零逻辑 diff 登记）。"""
    return _fix(B1.framework_variant_rows(vid, family, pname, arm_curve, base_curve, win,
                                          band_wins=band_wins, lag_ok=lag_ok,
                                          anchor_ref=anchor_ref, notes=notes))


def factor_rows_w2(vid, family, ic, sp_day, anchor_ref='new', notes=''):
    """B1.factor_domain_rows/factor_full_row 逐字复用，仅 batch 改 W2A。"""
    rows = _fix(B1.factor_domain_rows(vid, family, ic, sp_day, anchor_ref=anchor_ref, notes=notes))
    rows.append(_fix([B1.factor_full_row(vid, family, ic, sp_day, 'FULL', anchor_ref, notes)])[0])
    return rows


def event_rows_w2(trades, sig_base, family, notes='', full_note=''):
    """方向①事件式行（B3.trade_rows 逐字同构，两处 diff 登记：batch=W2A、
    vid=ex-<sig>-<域> 逐域命名——方法书 §3.1 变体=信号×域过滤）。"""
    lab = B1.d1_labels('full144')
    rows = []
    by_dom = {d: {'days': set(), 'rs': [], 'daily': {}} for d in D1N}
    all_daily = {}
    for tr in trades:
        t = pd.Timestamp(tr['et'])
        g = lab.get(str(t.date()))
        r = float(tr['r'])
        all_daily[t] = all_daily.get(t, 0.0) + r
        if g in by_dom:
            by_dom[g]['days'].add(t)
            by_dom[g]['rs'].append(r)
            by_dom[g]['daily'][t] = by_dom[g]['daily'].get(t, 0.0) + r
    for d in D1N:
        if d not in by_dom:
            continue
        rs = by_dom[d]['rs']
        if not rs:
            continue
        dv = np.array([v for _, v in sorted(by_dom[d]['daily'].items())], dtype=float)
        ci = MC.stationary_boot(dv) if len(dv) >= 5 else np.array([])
        cushion = None
        if len(dv) >= 5 and len(all_daily) > len(dv):
            bmed = float(np.median(MC.perm_baseline(np.array(list(all_daily.values())), len(dv))))
            if bmed != 0:
                cushion = float(dv.mean()) / bmed
        p = B1.boot_p_one_sided(dv) if len(dv) >= 5 else 1.0
        vid = f'ex-{sig_base}-{DOM_EN[d]}'
        rows.append({'batch': BATCH, 'variant_id': vid, 'family': family, 'pool': 'full144',
                     'axis': 'D1', 'domain': d,
                     'n_days': int(len(by_dom[d]['days'])), 'n_sig': int(len(rs)),
                     'win_rate_pct': round(float(np.mean([r > 0 for r in rs]) * 100), 2),
                     'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
                     'ic_mean': round(float(np.mean(rs)), 4), 'ic_t': None, 'n_ic': None,
                     'spread_net_pp': None, 'avoid_pp': None, 'mdd_red_pct': None,
                     'cushion_x': None if cushion is None else round(cushion, 2),
                     'fdr_q': None,
                     'ci95_low': None if not ci.size else round(float(np.percentile(ci, 2.5)), 6),
                     'ci95_high': None if not ci.size else round(float(np.percentile(ci, 97.5)), 6),
                     'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                     'evidence_tag': '【实证】', 'anchor_ref': 'new',
                     'notes': notes + '；事件式族：ic_mean 字段=单笔 R 均值%（字段复用），'
                                      'n_sig=入场笔数，win=笔胜率，CI/p=域内日 R 合计序列',
                     '_meta': {'p_one': p, 'sum_r': round(float(np.sum(rs)), 2)}})
    rs_all = [float(t['r']) for t in trades]
    dv = np.array([v for _, v in sorted(all_daily.items())], dtype=float)
    ci = MC.stationary_boot(dv) if len(dv) >= 5 else np.array([])
    rows.append({'batch': BATCH, 'variant_id': f'ex-{sig_base}', 'family': family,
                 'pool': 'full144', 'axis': 'FULL', 'domain': 'all',
                 'n_days': int(len(all_daily)), 'n_sig': int(len(rs_all)),
                 'win_rate_pct': round(float(np.mean([r > 0 for r in rs_all]) * 100), 2),
                 'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
                 'ic_mean': round(float(np.mean(rs_all)), 4), 'ic_t': None, 'n_ic': None,
                 'spread_net_pp': None, 'avoid_pp': None, 'mdd_red_pct': None,
                 'cushion_x': None, 'fdr_q': None,
                 'ci95_low': None if not ci.size else round(float(np.percentile(ci, 2.5)), 4),
                 'ci95_high': None if not ci.size else round(float(np.percentile(ci, 97.5)), 4),
                 'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                 'evidence_tag': '【实证】', 'anchor_ref': 'new',
                 'notes': notes + '；' + full_note,
                 '_meta': {'p_one': B1.boot_p_one_sided(dv) if len(dv) else 1.0}})
    return rows


# ================================================================ 方向①：信号×出场×域（V01–V16）
DUP_D1 = ('查重标注：vs Q3 信号本体四域 IC 格（FACTBOOK 592 行已判）轴不同——本臂为 '
          'D-A 出场轴（信号×分批+保本出场），不重判信号本体 IC（§二禁重复#1）')

_BARS = {}
_ATRS = {}


def _bars_of(data, s):
    if s not in _BARS:
        df = data[s].dropna(subset=['close'])
        _BARS[s] = ([{**df.iloc[i].to_dict(), 'time': df.index[i]} for i in range(len(df))],
                    {t: i for i, t in enumerate(df.index)})
    return _BARS[s]


def _atrs_of(data, s):
    if s not in _ATRS:
        import eng_final as ENG
        _ATRS[s] = ENG.atrs(_bars_of(data, s)[0])
    return _ATRS[s]


def _d1_signal_worker(job):
    """方向①臂（方法书 §3.0 适配层预注册冻结）：信号日 t 收盘判定截面 top5 等权各开一笔
    独立跟踪仓（同票在仓去重）；ep=t 收盘、eff=t low−0.3×ATR14(t)（fd eff 结构逐字）；
    eff≤0 或 ep≤eff 跳过；不加 risk≤8% 门；出场= batch3 mk_partial(True) D-A 五件逐字复用。
    信号日=全部交易日（fd 谱系逐日入场同构；【口径操作化·R7】登记）。"""
    sig, = job
    sys.path.insert(0, '/workspace/repo_ready/research/wo_fdbrk')
    sys.path.insert(0, '/tmp/eng_wt_rc')
    ctx = MC.build_ctx()
    data = ctx['data']
    P = ctx['full144']
    cal = P['cal']
    syms = P['syms']
    C, L = P['close'], P['low']
    V = pd.DataFrame({s: data[s]['volume'] for s in syms}).reindex(cal)
    H = pd.DataFrame({s: data[s]['high'] for s in syms}).reindex(cal)
    turn20 = np.log((C * V).rolling(20).mean())
    liq_med = turn20.median(axis=1)
    ret5 = C / C.shift(5) - 1
    brk20 = C / H.rolling(20).max().shift(1) - 1
    thr = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool']['full144']
    vol20_pool = P['vol20']
    exit_fn = B3._fd_exit_fns()['K5-fd-exit-partial3r-breakeven']
    open_until = {}
    trades = []
    for i, t in enumerate(cal):
        if str(t)[:10] < MAIN:
            continue
        if sig == 'g80':
            if pd.isna(vol20_pool.get(t, np.nan)) or vol20_pool[t] > thr:
                continue
            sc = MC.DE.cross_scores(ctx['F'], syms, t, MC.DE.FACTORS_4)
            top = list(sc.index[:5])
        else:
            if sig == 'rev5':
                sc = -ret5.loc[t]
            elif sig == 'revliq':
                sc = (-ret5.loc[t]).where(turn20.loc[t] > liq_med[t])
            elif sig == 'brk20':
                sc = brk20.loc[t]
            else:
                raise SystemExit(f'unknown sig {sig}')
            sc = sc.dropna()
            if len(sc) < 5:
                continue
            top = list(sc.sort_values(ascending=False).index[:5])
        for s in top:
            if pd.isna(C.at[t, s]) or pd.isna(L.at[t, s]):
                continue
            ou = open_until.get(s)
            if ou is not None and ou >= t:
                continue
            bars, bidx = _bars_of(data, s)
            bi = bidx.get(t)
            if bi is None:
                continue
            A = _atrs_of(data, s)[bi]
            if A is None:
                continue
            ep = float(C.at[t, s])
            eff = float(L.at[t, s]) - 0.3 * A
            if eff <= 0 or ep <= eff:
                continue
            xi, xpx, why, r = exit_fn(bars, bi, ep, eff, A)
            trades.append(dict(tkr=s, et=t, xt=bars[xi]['time'], ep=ep, ei=bi, xi=xi,
                               xc=round(xpx, 4), r=r, why=why))
            open_until[s] = pd.Timestamp(bars[xi]['time'])   # 同票在仓去重：占用至出场 bar 日
    return sig, trades


def run_d1(win=None, smoke=False):
    t0 = time.time()
    sigs = ['rev5', 'revliq', 'brk20', 'g80']
    SIG_META = {
        'rev5': ('s=−ret5（batch2_run.py:440 逐字；ret5=:91）', 'Q3-rev-5 弱躁 0.10875/82.05×/q=0.000725（ATLAS:293）'),
        'revliq': ('s=(−ret5)∧turn20>当日截面中位（batch2_run.py:442-443,424 逐字；turn20=:95）',
                   'Q3-rev-liq 弱躁 0.133685/11.14×/q=0.000464（ATLAS:301）'),
        'brk20': ('s=C/H.rolling(20).max().shift(1)−1（batch2_run.py:360-362 逐字）',
                  'Q1-brk-pos-20 牛躁 0.1126/3.26×/q=7.8e-05（ATLAS:247）'),
        'g80': ('s=现行引擎四因子 cross_scores（DE 谱系，mine_common.py:167-191）；门内掩码=池 vol20≤p80 阈（未触发 pause）',
                'K1-p80 弱稳 99.81/4.78×/q=0.0（ATLAS:172）'),
    }
    DOM_EN = {'牛稳': 'niuwen', '牛躁': 'niunao', '弱稳': 'ruowen', '弱躁': 'ruozao'}
    with get_context('fork').Pool(min(N_PROC, len(sigs))) as pool:
        out = pool.map(_d1_signal_worker, [(s,) for s in sigs])
    rows, detail = [], {}
    for sig, trades in out:
        trs = [t for t in trades if pd.Timestamp(t['et']) >= SMOKE_WIN[0]] if smoke else trades
        desc, anchor = SIG_META[sig]
        nt = (f'方向①信号×出场×域（§3.0 适配层冻结：ep=收盘/eff=low−0.3×ATR14/出场=D-A 五件'
              f' batch3 mk_partial(True) 逐字复用；不加 risk 门）；信号={desc}；复现锚={anchor}；'
              f'{DUP_D1}；部署开关/参数邻域禁触（§二#2#3）')
        rows += event_rows_w2(trs, sig, 'D1', notes=nt,
                              full_note='FULL=记账行不判生死；realC 窗数字=图谱记账引用'
                                        '（fd realC 已烧，禁二次终验，MINE_SPEC §六）')
        detail[sig] = {'n_trades': len(trs)}
        lab = B1.d1_labels('full144')
        detail[sig]['placebo'] = {
            d: round(float(np.mean([t['r'] for t in trs
                                    if lab.get(str(pd.Timestamp(t['et']).date())) == d])), 4)
            for d in D1N
            if any(lab.get(str(pd.Timestamp(t['et']).date())) == d for t in trs)}
    pcells = [{'variant_id': r['variant_id'], 'pool': r['pool'], 'domain': r['domain'],
               'p': r['_meta']['p_one'],
               'p_kind': 'boot_p_one_sided（域内日 R 合计 ≤0 频率，块长10 B1000 seed42）',
               'note': '方向①锚定域格（§3.1：16 变体入批内 FDR）'}
              for r in rows if r['axis'] == 'D1']
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, detail, pcells


# ================================================================ 方向③：c4 邻域 2×2×2（V17–V24）
DUP_D3 = ('查重标注：c4 原 w=20 格已判（ext t=+4.7764 n=317/batch1 谱系 maxdiff=0），本格只测'
          ' w×分母×horizon 新格（§二禁重复#1）；vs Q3-rs-ew-fwd20 池内 RS 不同截面不可混写；'
          'c4 realC 全窗翻转未翻案，产出=分域图谱证据非部署通道（§3.5 差异化承继）')


def _d3_worker(job):
    """方向③臂（§4.1 基础定义逐字）：RS_w^den = ret_w − 异池 den；截面域=严格 full144
    （W2W3 §2.1 谱系）；IC 逐日（FULL 窗全部日历日）+ 十分位价差按 ISO 周信号日费后。"""
    vid, w, den, hz = job
    ctx = MC.build_ctx()
    data, pools = ctx['data'], ctx['pools']
    full144, old131 = pools['full144'], pools['old131']
    new13 = sorted(set(full144) - set(old131))
    C = pd.DataFrame({s: data[s]['close'] for s in full144}).sort_index()
    retw = C / C.shift(w) - 1
    agg = (lambda df: df.mean(axis=1)) if den == 'ew' else (lambda df: df.median(axis=1))
    den_old, den_new = agg(retw[new13]), agg(retw[old131])   # 异池互指（c4.def 逐字）
    rs = pd.DataFrame(index=C.index, columns=full144, dtype=float)
    for s in full144:
        rs[s] = retw[s] - (den_new if s in old131 else den_old)
    fwd = C.shift(-hz) / C - 1
    ic = MC.xsec_ic_series(rs[(rs.index >= FULL[0]) & (rs.index <= FULL[1])],
                           fwd[(fwd.index >= FULL[0]) & (fwd.index <= FULL[1])])
    iso = C.index.isocalendar()
    sig_all = pd.DatetimeIndex(C.index.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)
    sig_w = sig_all[(sig_all >= FULL[0]) & (sig_all <= FULL[1])]
    sp_day = B1.daily_spread(rs.loc[sig_w], fwd.loc[sig_w].reindex(rs.loc[sig_w].index))
    rows = factor_rows_w2(vid, 'D3', ic, sp_day,
                          notes='方向③ c4 邻域（§4.1 一次冻结 2×2×2 禁扩）；'
                                + DUP_D3)
    # REALC 记账行（c4 谱系 batch1 同构；记账引用非判线）
    ic_rc = ic[ic.index >= REALC[0]]
    sp_rc = sp_day[sp_day.index >= REALC[0]] if len(sp_day) else sp_day
    rows.append(_fix([B1.factor_full_row(vid, 'D3', ic_rc, sp_rc, 'REALC',
                                         'c4 realC 记账引用（batch1 c4 同构，非判线）')])[0])
    # C5 稳健：LOTO full144 去一 20 次 / 分年 / lag1（batch1 run_c4 逐字口径）
    rng = np.random.default_rng(MC.SEED)
    loto_signs = []
    t_ext = MC.tstat(ic)[0]
    for _ in range(20):
        drop = full144[int(rng.integers(len(full144)))]
        keep = [s for s in full144 if s != drop]
        old_k = [s for s in old131 if s != drop]
        new_k = [s for s in new13 if s != drop]
        rk = pd.DataFrame(index=C.index, columns=keep, dtype=float)
        do_, dn_ = agg(retw[new_k]) if new_k else None, agg(retw[old_k])
        for s in keep:
            rk[s] = retw[s] - (dn_ if s in old131 else do_)
        ick = MC.xsec_ic_series(rk[(rk.index >= FULL[0]) & (rk.index <= FULL[1])],
                                fwd[(fwd.index >= FULL[0]) & (fwd.index <= FULL[1])])
        tk, _ = MC.tstat(ick)
        if tk is not None and t_ext is not None:
            loto_signs.append(np.sign(tk) == np.sign(t_ext))
    loto_pass = bool(np.sum(loto_signs) >= 19) if len(loto_signs) == 20 else None
    yr = {}
    for y in sorted(set(ic.index.year)):
        tt, nn = MC.tstat(ic[ic.index.year == y])
        yr[int(y)] = {'t': None if tt is None else round(tt, 4), 'n': int(nn)}
    yearly_flip = bool(len({np.sign(v['t']) for v in yr.values() if v['t'] is not None}) > 1)
    ic_lag = MC.xsec_ic_series(rs.shift(1)[(rs.index >= FULL[0]) & (rs.index <= FULL[1])],
                               fwd[(fwd.index >= FULL[0]) & (fwd.index <= FULL[1])])
    t_lag, _ = MC.tstat(ic_lag)
    lag_flip = bool(t_lag is not None and t_ext is not None and np.sign(t_lag) != np.sign(t_ext))
    for r in rows:
        if r['axis'] == 'D1':
            r['loto_pass'], r['yearly_flip'], r['lag_flip'] = loto_pass, yearly_flip, lag_flip
    plc = B1.placebo_factor(ic)
    t_, n_ = MC.tstat(ic)
    detail = {'vid': vid, 'w': w, 'den': den, 'hz': f'fwd{hz}', 't_ext': t_ext, 'n_ext': n_,
              'loto_pass': loto_pass, 'yearly': yr, 'yearly_flip': yearly_flip,
              't_lag1': t_lag, 'lag_flip': lag_flip, 'placebo': plc}
    p = float(sst.t.sf(t_, max(n_ - 2, 1))) if t_ is not None else None
    return rows, detail, p


def run_d3(win=None, smoke=False):
    t0 = time.time()
    jobs = []
    for w in (60, 120):
        for den in ('ew', 'med'):
            for hz in (5, 20):
                vid = f'c4-w{w}-{den}-fwd{hz}'
                jobs.append((vid, w, den, hz))
    with get_context('fork').Pool(min(N_PROC, len(jobs))) as pool:
        out = pool.map(_d3_worker, jobs)
    rows, detail, pcells = [], {}, []
    for (rows_v, det, p) in out:
        rows += rows_v
        detail[det['vid']] = det
        if p is not None:
            pcells.append({'variant_id': det['vid'], 'pool': 'full144', 'domain': '牛稳',
                           'p': p, 'p_kind': 'ic_t 上尾 t.sf（PF-5 同式）',
                           'note': '锚定域=牛稳格（§4.1）；其余三域=邻域补全记账不入 FDR'})
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, detail, pcells


# ================================================================ 方向②：armC×域×slot（V25–V32）
DUP_D2 = ('查重标注：vs ATLAS armC 8 格——彼无域过滤（全窗门），此域内生效；'
          'vs K1-d-downweight-slot05——彼为孤立降权，此为 armC 门×降权×域过滤组合轴，'
          '两标记并行不混写（§二禁重复#2#6）；K1-p70 谱系 MAP-INVALID 不混写')


def _d2_specs(win):
    """方向② spec 集：{slot1.0/0.5}×{4 域过滤} armC + base + lag 重放 + C1 随机带（§5.2 冻结）。"""
    thr = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool']
    dom_en = {'牛稳': 'niuwen', '牛躁': 'niunao', '弱稳': 'ruowen', '弱躁': 'ruozao'}
    specs, keys = [], []
    for p in ('old131', 'full144'):
        P = MC.build_ctx()[p]
        vol_hi = (P['vol20'] > thr[p]).fillna(False)
        down = (P['idx'] < P['idx_ma']).fillna(False)
        g2 = (vol_hi & down).fillna(False)
        lab = B1.d1_labels(p)
        specs.append({'pname': p, 'win': win, 'fee': B1.FEE_S, 'fund': B1.FUND_S})
        keys.append((p, 'base'))
        for s in range(42, 62):
            specs.append({'pname': p, 'win': win, 'random_seed': s})
            keys.append((p, f'band{s}'))
        for sm, smtag in ((1.0, 's10'), (0.5, 's05')):
            for d in D1N:
                cond = (g2 & pd.Series([lab.get(str(t.date())) == d for t in P['cal']],
                                       index=P['cal'])).fillna(False)
                specs.append({'pname': p, 'win': win, 'fee': B1.FEE_S, 'fund': B1.FUND_S,
                              'slot_mult': sm,
                              'overlay': {'off': cond.shift(1).fillna(False), 'mode': 's3'}})
                keys.append((p, f'{smtag}-{dom_en[d]}'))
                specs.append({'pname': p, 'win': win, 'fee': B1.FEE_S, 'fund': B1.FUND_S,
                              'slot_mult': sm,
                              'overlay': {'off': cond.shift(2).fillna(False), 'mode': 's3'}})
                keys.append((p, f'{smtag}-{dom_en[d]}-lag'))
    return specs, keys, g2


def _d2_sim(spec):
    return B1._w_sim(spec)


def run_d2(win=None, smoke=False):
    t0 = time.time()
    specs, keys, _ = _d2_specs(win)
    with get_context('fork').Pool(N_PROC) as pool:
        res = dict(zip(keys, pool.map(_d2_sim, specs)))
    rows, detail, pcells = [], {}, []
    W = win or FULL
    for p in ('old131', 'full144'):
        P = MC.build_ctx()[p]
        base_c = res[(p, 'base')]['curve']
        dd = B1.dom_dates(p, W)
        band_wins = B1.band_wins_of(res, p, win)
        g2 = ((P['vol20'] > json.load(open(os.path.join(OUT, 'domains.json')))
               ['anchors']['gate_vol20_p80_by_pool'][p]) &
              (P['idx'] < P['idx_ma'])).fillna(False)
        ret_b = base_c.pct_change() * 100
        for sm, smtag in ((1.0, 's10'), (0.5, 's05')):
            for d in D1N:
                en = {'牛稳': 'niuwen', '牛躁': 'niunao', '弱躁': 'ruozao', '弱稳': 'ruowen'}[d]
                vid = f'armc-{smtag}-{en}'
                c = res[(p, f'{smtag}-{en}')]['curve']
                cl = res[(p, f'{smtag}-{en}-lag')]['curve']
                lag_ok = bool(B1.seg_stats(cl, *W)['ret_pp'] > B1.seg_stats(base_c, *W)['ret_pp'] and
                              B1.seg_stats(cl, *B1.HOLD)['ret_pp'] > B1.seg_stats(base_c, *B1.HOLD)['ret_pp'])
                nt = (f'方向② S3×D1 臂C 扩展（§5.1 armC 逐字+域掩码 lag1 + slot_mult={sm}）；'
                      f'费压 PB-5 ×1.5 伴行，base 同费对比；{DUP_D2}')
                rows += fw_rows_w2(vid, 'D2', p, c, base_c, W, band_wins=band_wins,
                                   lag_ok=lag_ok, notes=nt)
                # 判读专节：T1'/T3'（batch1_run.py:1026-1032 逐字口径）+ lag 重放
                dc = {'FULL_avoid': round(B1.seg_stats(c, *W)['ret_pp'] - B1.seg_stats(base_c, *W)['ret_pp'], 4),
                      'FULL_mdd_red': round((abs(B1.seg_stats(base_c, *W)['mdd_pct']) -
                                             abs(B1.seg_stats(c, *W)['mdd_pct']))
                                            / abs(B1.seg_stats(base_c, *W)['mdd_pct']) * 100, 2),
                      'HOLDOUT_avoid': round(B1.seg_stats(c, *B1.HOLD)['ret_pp']
                                             - B1.seg_stats(base_c, *B1.HOLD)['ret_pp'], 4),
                      'lag_FULL_avoid': round(B1.seg_stats(cl, *W)['ret_pp']
                                              - B1.seg_stats(base_c, *W)['ret_pp'], 4),
                      'lag_HOLDOUT_avoid': round(B1.seg_stats(cl, *B1.HOLD)['ret_pp']
                                                 - B1.seg_stats(base_c, *B1.HOLD)['ret_pp'], 4)}
                for sn, (a, b) in (('realB', B1.REALB), ('realC', B1.REALC)):
                    o = g2[(g2.index >= a) & (g2.index <= b)]
                    x = ret_b.reindex(o[o].index).dropna()
                    dc[f'T1_off_mean_{sn}_pp'] = round(float(x.mean()), 4) if len(x) else None
                    dc[f'T1_off_n_{sn}'] = int(len(x))
                orb = g2[(g2.index >= B1.REALB[0]) & (g2.index <= B1.REALB[1])]
                dc['T3_realB_off_share_pct'] = round(float(orb.mean()) * 100, 2)
                detail[f'{vid}|{p}'] = dc
                if p == 'full144':
                    ex = B1.daily_excess(c, base_c).reindex(dd[d]).dropna()
                    pcells.append({'variant_id': vid, 'pool': p, 'domain': d,
                                   'p': B1.boot_p_one_sided(ex.values) if len(ex) >= 5 else 1.0,
                                   'p_kind': 'boot_p_one_sided（域内日超额 ≤0 频率，块长10 B1000 seed42）',
                                   'note': '主口径 full144（§5.4 双池纪律：old131 伴行记账不入预算）'})
        detail[f'{p}|base_realC'] = B1.seg_stats(base_c, *B1.REALC)
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, detail, pcells


# ================================================================ 方向④：K1 换门交换曲线（V33–V36，读数件）
DUP_D4 = ('查重标注：p70 格 MAP-INVALID 不混写（ATLAS:6）；p65/p60 扩档禁做（K1P70 §4-1）；'
          '读数件不改部署（R10）；§二禁重复#3#6')


def run_d4(win=None, smoke=False):
    t0 = time.time()
    g = json.load(open(os.path.join(OUT, 'k1p70_result.json')))
    grid = {(r['pool'], r['tier']): r for r in g['grid']}
    rows, detail = [], {'slope': {}}
    for p in ('old131', 'full144'):
        for tier, vid in (('p70', 'gc-p70-point'), ('p75', 'gc-p75-point'), ('p80', 'gc-p80-point')):
            r = grid[(p, tier)]
            rows.append({'batch': BATCH, 'variant_id': vid, 'family': 'D4', 'pool': p,
                         'axis': 'FULL', 'domain': 'all',
                         'n_days': None, 'n_sig': int(r['n_off_exec_days']),
                         'win_rate_pct': None, 'ann_pct': None, 'excess_pp': None,
                         'mdd_pct': None, 'ic_mean': None, 'ic_t': None, 'n_ic': None,
                         'spread_net_pp': None,
                         'avoid_pp': round(float(r['avoid_pp']), 4),
                         'mdd_red_pct': round(float(r['mdd_red_pct']), 2),
                         'cushion_x': None, 'fdr_q': None, 'ci95_low': None, 'ci95_high': None,
                         'loto_pass': None, 'yearly_flip': None, 'lag_flip': None,
                         'evidence_tag': '【读数件】', 'anchor_ref': 'k1p70_result.json grid（重放逐位 D0 hit）',
                         'notes': f'K1 换门交换曲线 {tier} 点四数：avoid_pp={r["avoid_pp"]}/'
                                  f'mdd_red%={r["mdd_red_pct"]}/OFF_exec_days={r["n_off_exec_days"]}/'
                                  f'净差={r["net_vs_base_wan"]} 万（只算不裁，K1P70 §3-4）；{DUP_D4}'})
        pts = sorted([(grid[(p, t)]['n_off_exec_days'], grid[(p, t)]['mdd_red_pct'],
                       grid[(p, t)]['avoid_pp']) for t in ('p80', 'p75', 'p70')])
        off = np.array([x[0] for x in pts], dtype=float)
        mr = np.array([x[1] for x in pts], dtype=float)
        av = np.array([x[2] for x in pts], dtype=float)
        k_mr = float(np.polyfit(off, mr, 1)[0])
        k_av = float(np.polyfit(off, av, 1)[0])
        seg = {'p80->p75': {'d_OFF': int(off[1] - off[0]),
                            'dmdd_per_day': round((mr[1] - mr[0]) / (off[1] - off[0]), 4),
                            'davoid_per_day': round((av[1] - av[0]) / (off[1] - off[0]), 4)},
               'p75->p70': {'d_OFF': int(off[2] - off[1]),
                            'dmdd_per_day': round((mr[2] - mr[1]) / (off[2] - off[1]), 4),
                            'davoid_per_day': round((av[2] - av[1]) / (off[2] - off[1]), 4)}}
        detail['slope'][p] = {'points': [{'tier': t, 'OFF': grid[(p, t)]['n_off_exec_days'],
                                          'mdd_red': grid[(p, t)]['mdd_red_pct'],
                                          'avoid_pp': grid[(p, t)]['avoid_pp']}
                                         for t in ('p80', 'p75', 'p70')],
                              'ols_slope_mddred_per_day': round(k_mr, 4),
                              'ols_slope_avoid_per_day': round(k_av, 4),
                              'segments': seg}
        rows.append({'batch': BATCH, 'variant_id': 'gc-slope-mddred', 'family': 'D4', 'pool': p,
                     'axis': 'FULL', 'domain': 'all', 'n_days': None, 'n_sig': None,
                     'win_rate_pct': None, 'ann_pct': None, 'excess_pp': None, 'mdd_pct': None,
                     'ic_mean': None, 'ic_t': None, 'n_ic': None, 'spread_net_pp': None,
                     'avoid_pp': None, 'mdd_red_pct': None, 'cushion_x': None, 'fdr_q': None,
                     'ci95_low': None, 'ci95_high': None, 'loto_pass': None,
                     'yearly_flip': None, 'lag_flip': None,
                     'evidence_tag': '【读数件】', 'anchor_ref': 'k1p70_result.json grid 六点逐位',
                     'notes': f'交换曲线斜率（§六 V36 定义）：OLS 三点 k_mddred={k_mr:.4f} pp/日、'
                              f'k_avoid={k_av:.4f} pp/日；边际比 {json.dumps(seg, ensure_ascii=False)}；'
                              f'斜率表只报状态不报观点（风控席），为影子期与 TR 人工切换提供引用读数；{DUP_D4}'})
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, detail, []


# ================================================================ assemble：FDR m=36 + 判定 + 落盘
def apply_fdr_and_judgment(rows, pcells):
    """C6：BH 批内 m=36（32 个登记假设格：D1 16 + D3 8 + D2 8；D4 读数件无 p 不入拒绝域）。
    补全/探针/邻域格只记账不入 FDR 拒绝域（方法书 §3.1/§一.3）。"""
    qs = MC.bh_fdr_q([c['p'] for c in pcells], m_total=M_W2)
    qmap = {}
    with open(os.path.join(OUT, 'FDR_W2_M36.jsonl'), 'w') as f:
        for c, q in zip(pcells, qs):
            c['q'] = round(float(q), 6)
            qmap[(c['variant_id'], c['pool'], c['domain'])] = c['q']
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    for r in rows:
        m = r.pop('_meta', None)
        r['fdr_q'] = qmap.get((r['variant_id'], r['pool'], r['domain']))
        if r['axis'] != 'D1':
            continue
        n = r['n_days'] or 0
        if n < 60:
            r['notes'] = (r['notes'] + ' INSUFFICIENT(n<60)').strip()
        if r['family'] == 'D2':
            c1 = (r['win_rate_pct'] is not None and m and m.get('band_median_win') is not None
                  and r['win_rate_pct'] >= m['band_median_win'])
            c2 = (r['excess_pp'] is not None and r['excess_pp'] > 0
                  and r['ci95_low'] is not None and r['ci95_low'] > 0)
            c3 = (r['mdd_pct'] is not None and m and m.get('mdd_base') is not None
                  and abs(r['mdd_pct']) <= abs(m['mdd_base']))
            c4 = r['cushion_x'] is not None and r['cushion_x'] >= 3.0
            c6 = r['fdr_q'] is not None and r['fdr_q'] <= 0.10
            r['_judge'] = {'C1': c1, 'C2': c2, 'C3': c3, 'C4': c4, 'C6': c6,
                           'domain_competent': bool(n >= 60 and c2 and c4 and c6 and c1 and c3),
                           'n_ge_60': n >= 60}
        elif r['family'] == 'D1':
            c2 = (r['ic_mean'] is not None and r['ic_mean'] > 0
                  and r['ci95_low'] is not None and r['ci95_low'] > 0)
            c4 = r['cushion_x'] is not None and r['cushion_x'] >= 3.0
            c6 = r['fdr_q'] is not None and r['fdr_q'] <= 0.10
            r['_judge'] = {'C2': c2, 'C4': c4, 'C6': c6,
                           'domain_competent': bool(n >= 60 and c2 and c4 and c6),
                           'n_ge_60': n >= 60,
                           'note': 'C1/C3 事件式族无净值曲线未计算（batch3 K5 同先例，如实登记）'}
        else:
            c2 = (r['ic_mean'] is not None and r['ic_mean'] > 0
                  and r['ci95_low'] is not None and r['ci95_low'] > 0)
            c4 = r['cushion_x'] is not None and r['cushion_x'] >= 3.0
            c6 = r['fdr_q'] is not None and r['fdr_q'] <= 0.10
            r['_judge'] = {'C2': c2, 'C4': c4, 'C6': c6,
                           'domain_competent_ic': bool(n >= 60 and c2 and c4 and c6),
                           'n_ge_60': n >= 60}
    # 变体成活（§5.3）：D3 附 C5（loto/分年/lag1）
    d3_c5 = {}
    return rows, qmap


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'smoke'
    d = sys.argv[2] if len(sys.argv) > 2 else 'D1'
    t0 = time.time()
    if mode == 'd0':
        res = d0_gate()
        sys.exit(0 if res['all_pass'] else 3)
    if mode == 'smoke':
        win, smoke = SMOKE_WIN, True
        print(f'[smoke] {d} 截断窗 {win[0].date()}~{win[1].date()}（R8 冒烟）', flush=True)
    elif mode == 'full':
        dg = json.load(open(os.path.join(OUT, 'd0_gate_wave2.json')))
        if not dg.get('all_pass'):
            print('D0 五锚未过——禁跑（一发验证禁令）', flush=True)
            sys.exit(3)
        win, smoke = None, False
        print(f'[full] {d} 全量（预算 {BUDGET[d]} 变体）', flush=True)
    elif mode == 'assemble':
        assemble()
        return
    else:
        raise SystemExit(f'unknown mode {mode}')
    RUNNERS = {'D1': run_d1, 'D2': run_d2, 'D3': run_d3, 'D4': run_d4}
    rows, detail, pcells = RUNNERS[d](win, smoke)
    n_v = len({r['variant_id'] for r in rows})
    print(f'      变体={n_v} 行={len(rows)} {detail["wall_secs"]}s', flush=True)
    if mode == 'full':
        json.dump({'dir': d, 'rows': rows, 'detail': detail, 'pcells': pcells,
                   'ts': time.strftime('%F %T')},
                  open(os.path.join(OUT, f'wave2_partial_{d}.json'), 'w'),
                  ensure_ascii=False, indent=1, default=str)
        print(f'      → wave2_partial_{d}.json', flush=True)
    print(f'done {round(time.time() - t0, 1)}s', flush=True)


def assemble():
    t0 = time.time()
    print('[assemble] 合并四方向 + FDR m=36 + 判定 + FACTBOOK …', flush=True)
    rows, pcells, details = [], [], {}
    for d in ('D1', 'D2', 'D3', 'D4'):
        path = os.path.join(OUT, f'wave2_partial_{d}.json')
        if not os.path.exists(path):
            print(f'      {d}: MISSING（如实登记，未跑）', flush=True)
            details[d] = {'status': 'MISSING'}
            continue
        part = json.load(open(path))
        rows += part['rows']
        pcells += part.get('pcells', [])
        details[d] = part['detail']
        print(f"      {d}: 变体 {len(set(r['variant_id'] for r in part['rows']))} 行 {len(part['rows'])}",
              flush=True)
    rows, qmap = apply_fdr_and_judgment(rows, pcells)
    judge = [{'variant_id': r['variant_id'], 'pool': r['pool'], 'domain': r['domain'],
              **r['_judge']} for r in rows if r['axis'] == 'D1' and '_judge' in r]
    for r in rows:
        r.pop('_judge', None)
    fb = os.path.join(OUT, 'FACTBOOK_WAVE2.jsonl')
    with open(fb, 'w') as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in COLS}, ensure_ascii=False) + '\n')
    n_q = int(sum(1 for c in pcells if c['q'] <= 0.10))
    res = {'ts': time.strftime('%F %T'), 'budget': {**BUDGET,
           'note': 'METHOD_BOOK_W2A §七 冻结预算逐字；36 变体一次性登记禁加号'},
           'n_factbook_rows': len(rows),
           'fdr': {'m_total': M_W2, 'n_registered_cells': len(pcells),
                   'n_q_le_010': n_q,
                   'registered': [{'vid': c['variant_id'], 'pool': c['pool'],
                                   'domain': c['domain'], 'p': c['p'], 'q': c['q']}
                                  for c in pcells],
                   'note': '批内 FDR m=36（BH q=0.10）：登记假设格=方向①16 锚定域 + 方向③8 牛稳格 '
                           '+ 方向②8 full144 主口径格=32；D4 四读数件无 p 不入拒绝域；'
                           '探针/邻域/old131 伴行格只记账（§3.1 预算登记+§5.4 双池纪律）'},
           'd0_gate': json.load(open(os.path.join(OUT, 'd0_gate_wave2.json'))),
           'judgment': judge,
           'r10_note': '本运行不产出任何「域读数→仓位」映射（R10）',
           'ruling_note': '本批只出图谱证据与影子候选资格，正式生死判读待首席终裁（R7 强弱同屏）',
           'detail': details, 'runtime_sec': round(time.time() - t0, 1)}
    json.dump(res, open(os.path.join(OUT, 'wave2_result.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    print(f'      FACTBOOK_WAVE2 行={len(rows)}；FDR m=36 登记格={len(pcells)}（q≤0.10 共 {n_q}）',
          flush=True)
    print(f'done {res["runtime_sec"]}s', flush=True)


if __name__ == '__main__':
    main()
