#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W3 · WAVE3 窄路小批两方向 4 变体（工程唯一施工依据=METHOD_BOOK_W3.md 预注册冻结稿，逐字照抄零发挥）
================================================================================================
R10 红线：本件域标签只作离线研究分层，任何函数不产出「域读数→仓位」映射（MINE_SPEC §5.4）。
预算声明（方法书 §六 冻结）：4 变体=方向 A 3（w3a-g80/w3a-rev5/w3a-brk20-ruowen-arm）+方向 B 1
（armc-s10-ruowen-nofee）。运行期加一格=该方向整方向判无效（MINE_SPEC §3.7）。
判线：MINE_SPEC §五 六腿 C1–C6 逐字承继，本批唯一适配=批内 FDR m=4（BH q=0.10，4 变体一次性
登记，禁分批放宽）；合并参考列 m=126（86+36+4）只作多重度量披露，禁跑数后择优引用（§一.4）。
保守席三闸（头注强制项，任一缺失=废单）：①双口径并排（事件式垫值/PB-5 败绩在案禁隐藏）
②主判口径唯一+一次成活禁择优 ③口径变更达标格一律降级【打折】并图谱标注。
首行诚实折扣（红队席，随报告首行携带）：①窗内非真样本外，达标≠部署，全部产出=研究坐标+
影子候选资格；②本批两方向均为口径层变更达成的复活验证，达标资格一律【打折】并双口径并排；
③K5 系 5.69× 先例格 n_days=9<60 INSUFFICIENT，先例等级=弱证据指向。
烧窗禁触（§一.7）：fd/brk realC 窗（2026-06-01→2026-10-18）不入判线，输出禁出现 realC 判线列。
R1 一发验证：w3a-/nofee 前缀全新格；已注册 ex-*/armc-s10-ruowen(PB-5) 格不重跑不覆盖，两标记并行。
三源逐字拷贝+diff 登记：见 COPY_DIFF_LOG（mine_common.simulate 费参数路径 / batch3 D-A 出场
mk_partial(True) / K2 仓位骨架 / batch1 armC overlay / wave2 信号定义与事件式锚机器）。
用法：
  python3 w3_run.py d0        # D0 五锚对拍（一发验证，不过禁跑）
  python3 w3_run.py smoke     # 冒烟（截断窗，R8）
  python3 w3_run.py full      # 全量（预估 <10 分钟；超时只冒烟+报告分块清单）
产出：d0_gate_w3.json / w3_partial.json / FACTBOOK_W3.jsonl / FDR_W3_M4.jsonl / w3_result.json
"""
import json
import os
import sys
import time
import hashlib
from multiprocessing import get_context

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, '/workspace/repo_ready/research/eng_wt_rc')   # G7：/tmp/eng_wt_rc 缺失→仓库内同 md5 副本
sys.path.insert(0, '/workspace/repo_ready/research/wo_fdbrk')
import mine_common as MC
import batch1_run as B1
import batch3_run as B3

MC.CACHE = '/tmp/box_cache_w2a'      # 唯一数据态（方法书 §〇 快照行；10-17 与 10-18 vintage 严禁混写）
OUT = MC.OUT_DIR
DE = MC.DE
FULL = B1.FULL                       # (2025-06-02, 2026-10-17) 判线窗
SMOKE_WIN = B1.SMOKE_WIN
N_PROC = 32                          # Pool(32)（§六运行单）
BATCH = 'W3'
M_W3 = 4                             # 批内 FDR 冻结 m=4
M_MERGED_REF = 126                   # 合并参考列 m=86+36+4（只披露不判读）
COLS = B3.COLS
D1N = MC.D1_NAMES
DOM_EN = {'牛稳': 'niuwen', '牛躁': 'niunao', '弱稳': 'ruowen', '弱躁': 'ruozao'}
MAIN = '2025-06-01'                  # fd 谱系入场日窗（W2 事件式锚重放逐字用）

# D-A 五件语义（batch3_run.py:844-882 mk_partial(True) 逐字拷贝声明；出场结构零改动，diff 见 COPY_DIFF_LOG D1-D4）：
#   ①close≥ep+3.0×R 收盘判定出半（触发价成交，low≤px≤high 不成立顺延下一满足 bar 的 open）
#   ②触发后 eff 一次性上移 eff2=ep（非跟踪）
#   ③余仓三条件先到先出：close≤eff2 / close≥tp / i−ei≥30
#   ④tp=ep+3.5669×ATR14(入场日) 冻结
#   ⑤FUNDING=0.0003/bar 逐半仓计（≡D-A 内嵌 FEE=0.03%/bar，同值不改）
_DA_SEMANTICS_VERBATIM = 'batch3_run.py mk_partial(True)（_fd_exit_fns 注入 K5-fd-exit-partial3r-breakeven）'

COPY_DIFF_LOG = [
    {'id': 'G1', 'item': 'mine_common.simulate 费参数路径（fee/fund=None→DE.FEE_SIDE=0.0005/FUNDING=0.0003 默认路径逐字，§4.2 spec）',
     'diff': '零改动（import 复用）'},
    {'id': 'G2', 'item': 'D-A 出场 batch3_run.py:844-882 mk_partial(True) 逐字拷贝（' + _DA_SEMANTICS_VERBATIM + '）',
     'diff': 'D1 拆日推进：离线 while→逐 bar 状态机（half_done/eff2/pending），逐 bar 语义逐字；'
             'D2 内嵌 FEE=0.03%/bar（按入场名义、入 r）→臂级现金资金费 FUNDING=0.0003/bar 逐半仓（同值不改，基=逐 bar 实价，登记）；'
             'D3 逐笔 r 额外计提 FEE_SIDE=0.0005（平仓侧，§3.1 逐字）；'
             'D4 出场结构四件（3R 收盘判定出半/eff2=ep/tp=ep+3.5669×ATR14(入场日) 冻结/30bar 硬顶/触发价出域顺延下一 bar open）逐字未动'},
    {'id': 'G3', 'item': 'K2 仓位骨架 batch3_run.py:384-398（k2_simulate）逐字：budget=min(DE.SLOT×权益, max(cash,0))、'
             '缺开盘价顺延有价日、mark=close.ffill 估值、FEE_SIDE 双边',
     'diff': '入场时点=信号日收盘 ep=close[t]（§3.1 规定；K2 原为次日开盘）；权益基=当日收盘权益（§3.1 权益(t)；K2 原为 eq_prev）'},
    {'id': 'G4', 'item': 'armC 定义 batch1_run.py:930-959（g2=(vol20>thr80)&(idx<idx_ma) + mode=s3）'
             '+ W2A §5.1 域掩码（wave2_run.py:524-536 cond=(g2&lab==域).shift(1)）逐字',
     'diff': '唯二差异=费参数（PB-5→现行 None，§4.2）与域掩码锚定弱稳（§4.2 域掩码承继 W2 V27 逐字）'},
    {'id': 'G5', 'item': '信号定义 wave2_run.py:326-343 逐字：g80=现行引擎四因子 cross_scores+门内掩码 vol20[t]≤thr80（p80 未触发 pause）；'
             'rev5=−ret5；brk20=C/H.rolling(20).max().shift(1)−1；top5 非 NaN',
     'diff': '零改动（唯一域过滤差异按 §3.1）'},
    {'id': 'G6', 'item': '§3.1 伪代码「if lab[t−1日]≠弱稳: continue」操作化（R7 登记）',
     'diff': '域过滤=唯一开仓域：开新仓仅弱稳（lab=d1_labels lag=1，lab[t] 即 t−1 日状态，k2_simulate:419 同读法）；'
             '持仓 D-A 推进与逐日净值全窗执行——§一.1 要求各臂产 D1 四域格，邻域格需全窗净值，字面 continue 将使三域无产出'},
    {'id': 'G7', 'item': 'eng_final 权威引擎加载路径',
     'diff': '/tmp/eng_wt_rc 本环境缺失→research/eng_wt_rc（eng_final.py md5=f59ddf73c18dcc2adcd3f5e374748631，'
             '与 engine_snapshot/eng_final.py 逐位同，wave2 同源）'},
    {'id': 'G8', 'item': 'C5-lag 操作化（R7 登记）',
     'diff': 'lag 臂（方向 A=域过滤 lab.shift 多一天；方向 B=off.shift(2) §4.2 逐字）弱稳日超额方向与主臂同向'
             '（MINE_SPEC §5.2-C5「结论方向不翻转」）；lag_FULL_avoid 另存披露'},
    {'id': 'G9', 'item': '快照 md5 账本口径',
     'diff': 'ledger md5=33c8b9ec…（fdbrk 冻结）在本数据态账本不复现——在库先例：D0_RESULT.json md5_clarification'
             '（verdict：计算范围+聚合公式双重差异，数据态实质一致以锚逐位复现为准）+ dual_check.py L17-22'
             '（md5 偏差披露、实质对拍硬闸）。本件硬闸=perfile_agg 逐位=2b2c9572…（batch0 workdir 冻结锚）+fd 双锚逐位复现'},
]

_WANT_ANCH3 = {   # §六 D0 锚③：W2 弱稳事件式三锚（FACTBOOK_WAVE2.jsonl + FDR_W2_M36.jsonl 在案）
    'g80':   {'cushion': 2.43, 'n_days': 20, 'n_sig': 38, 'p': 0.0},
    'rev5':  {'cushion': 2.58, 'n_days': 48, 'n_sig': 127, 'p': 0.0},
    'brk20': {'cushion': 2.95, 'n_days': 31, 'n_sig': 83, 'p': 0.001},
}


# ================================================================ bars/ATR（wave2_run.py:283-295 逐字，路径 G7）
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


# ================================================================ 子池构造（LOTO 检验件；build_ctx:76-105 同式逐字减一票，G3 登记）
def subset_pool(pname, drop):
    ctx = MC.build_ctx()
    data = ctx['data']
    syms = [s for s in ctx[pname]['syms'] if s != drop]
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close = pd.DataFrame({s: data[s]['close'] for s in syms}).reindex(cal)
    open_ = pd.DataFrame({s: data[s]['open'] for s in syms}).reindex(cal)
    low = pd.DataFrame({s: data[s]['low'] for s in syms}).reindex(cal)
    mark = close.ffill()
    idx = close.mean(axis=1)
    idx_ma = idx.rolling(DE.MA_REG).mean()
    med_ret = close.pct_change().median(axis=1)
    iso = cal.isocalendar()
    sig_days = set(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)
    vol20 = idx.pct_change().rolling(20).std(ddof=1) * np.sqrt(252)
    return dict(syms=syms, close=close, open_=open_, low=low, mark=mark, cal=cal,
                idx=idx, idx_ma=idx_ma, med_ret=med_ret, sig_days=sig_days, vol20=vol20)


def _pool_like(pname, drop):
    """drop=None→标准 ctx 池；否则子池（LOTO）。返回 (P, ctx_like)。"""
    ctx = MC.build_ctx()
    if drop is None:
        return ctx[pname], ctx
    P = subset_pool(pname, drop)
    return P, {'F': ctx['F'], pname: P}


# ================================================================ 方向 B overlay（G4 逐字：batch1 armC+W2A §5.1 域掩码）
def b_overlay(pname, P, lag=1, drop=None):
    thr = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool'][pname]
    vol_hi = (P['vol20'] > thr).fillna(False)
    down = (P['idx'] < P['idx_ma']).fillna(False)          # NaN 方向=不 OFF（gate_maps 同式）
    g2 = (vol_hi & down).fillna(False)
    lab = B1.d1_labels('full144' if drop is not None else pname)   # LOTO 域标签冻结（G6 同源登记）
    cond = (g2 & pd.Series([lab.get(str(t.date())) == '弱稳' for t in P['cal']],
                           index=P['cal'])).fillna(False)
    return {'off': cond.shift(lag).fillna(False), 'mode': 's3'}    # 主臂 lag=1（W2 V27 逐字）/lag 臂 shift(2)（§4.2）


# ================================================================ 方向 A 臂（§3.1 共用骨架；K2 骨架+D-A 五件注入，COPY_DIFF_LOG G2/G3/G6）
def w3a_arm(pname, sig, win, lag=1, drop=None):
    ctx = MC.build_ctx()
    data = ctx['data']
    P, _ = _pool_like(pname, drop)
    syms = list(P['syms'])
    cal_all = P['cal']
    cal = cal_all[(cal_all >= win[0]) & (cal_all <= win[1])]
    C, L, mark = P['close'], P['low'], P['mark']
    H = pd.DataFrame({s: data[s]['high'] for s in syms}).reindex(cal_all)
    ret5 = C / C.shift(5) - 1
    brk20 = C / H.rolling(20).max().shift(1) - 1
    lab = B1.d1_labels('full144' if drop is not None else pname)
    if lag > 1:   # G8：域过滤再 lag（k−1）个交易日
        dates = list(cal_all)
        lab = {str(t.date()): (lab.get(str(dates[i - (lag - 1)].date())) if i - (lag - 1) >= 0 else None)
               for i, t in enumerate(dates)}
    thr = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool'][pname]
    vol20_pool = P['vol20']
    fee, fund = DE.FEE_SIDE, DE.FUNDING      # 0.0005 / 0.0003（现行引擎费线，G1）
    cash, pos, eq = 1.0, {}, {}
    open_until = {}
    trade_rs = []
    bidx_cache = {}

    def _bidx(s):
        if s not in bidx_cache:
            bidx_cache[s] = _bars_of(data, s)
        return bidx_cache[s]

    for t in cal:
        # ---- 1) 持仓 D-A 五件推进（全窗逐日，G6；出场结构 G2-D4 逐字） ----
        for s in list(pos):
            pp = pos[s]
            bars, bidx = _bidx(s)
            if t not in bidx:
                continue                                   # 停牌顺延（K2 骨架缺价顺延逐字）
            ci = bidx[t]
            n = len(bars)
            if pp.get('pending'):                          # D-A 顺延语义：j+=1; xpx=下一 bar open（G2-D4）
                xpx = bars[ci]['open']
                qh = pp['q']
                cash += qh * xpx * (1 - fee)
                cash -= qh * xpx * fund                    # 出场 bar 资金费（⑤逐半仓计至出场 bar）
                r2 = (xpx - pp['ep']) / pp['ep'] * 100 - 0.03 * (ci - pp['ei']) - 0.05
                trade_rs.append(pp['r_acc'] + (0.5 * r2 if pp['half_done'] else r2))
                del pos[s]
                open_until[s] = t                          # 同票在仓去重：占用至出场 bar 日（W2 逐字）
                continue
            px = bars[ci]['close']
            R = pp['ep'] - pp['eff']
            if not pp['half_done'] and px >= pp['ep'] + 3.0 * R:      # ①+3R 收盘判定出半
                xpx = px
                j = ci
                while j < n - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                    j += 1
                    xpx = bars[j]['open']                  # close 恒在当日 bar 域内→j==ci（保留校验语义）
                if j == ci:
                    qh = pp['q'] / 2.0
                    cash += qh * xpx * (1 - fee)
                    cash -= qh * xpx * fund
                    r1 = (xpx - pp['ep']) / pp['ep'] * 100 - 0.03 * (ci - pp['ei']) - 0.05   # G2-D3 平仓侧 FEE_SIDE
                    pp['r_acc'] += 0.5 * r1
                    pp['q'] -= qh
                    pp['half_done'] = True                 # ②eff2=ep（保本上移，非跟踪）
                else:
                    pp['pending'] = True
                continue
            effX = pp['ep'] if pp['half_done'] else pp['eff']         # ③②余仓 eff2/原 eff
            if px >= pp['tp'] or px <= effX or (ci - pp['ei']) >= 30:  # 三条件先到先出（④tp 冻结/30bar 硬顶）
                if px >= pp['tp']:
                    xpx = max(pp['tp'], bars[ci]['open'])
                elif px <= effX:
                    xpx = min(effX, bars[ci]['open'])
                else:
                    xpx = px
                j = ci
                while j < n - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                    j += 1
                    xpx = bars[j]['open']
                if j == ci:
                    qh = pp['q']
                    cash += qh * xpx * (1 - fee)
                    cash -= qh * xpx * fund
                    r2 = (xpx - pp['ep']) / pp['ep'] * 100 - 0.03 * (ci - pp['ei']) - 0.05
                    trade_rs.append(pp['r_acc'] + (0.5 * r2 if pp['half_done'] else r2))
                    del pos[s]
                    open_until[s] = t
                else:
                    pp['pending'] = True
                continue
        # ---- 2) 开仓（唯一域过滤：弱稳，lag=1；G6） ----
        if lab.get(str(t.date())) == '弱稳':
            if sig == 'g80':
                v = vol20_pool.get(t, np.nan)
                if pd.isna(v) or v > thr:
                    top = []
                else:
                    sc = DE.cross_scores(ctx['F'], syms, t, DE.FACTORS_4)
                    top = list(sc.index[:5])
            else:
                sc = (-ret5.loc[t]) if sig == 'rev5' else brk20.loc[t]
                sc = sc.dropna()
                top = [] if len(sc) < 5 else list(sc.sort_values(ascending=False).index[:5])
            eq_t = cash + sum(pp['q'] * (0.0 if pd.isna(mark.at[t, s2]) else mark.at[t, s2])
                              for s2, pp in pos.items())       # 权益(t)（K2 mark 估值逐字，G3）
            for s in top:
                if s in pos:
                    continue
                ou = open_until.get(s)
                if ou is not None and ou >= t:
                    continue
                if pd.isna(C.at[t, s]) or pd.isna(L.at[t, s]):
                    continue
                budget = min(DE.SLOT * eq_t, max(cash, 0.0))   # K2 骨架逐字（G3）
                if budget <= 0:
                    continue
                bars, bidx = _bidx(s)
                bi = bidx.get(t)
                if bi is None:
                    continue
                A = _atrs_of(data, s)[bi]
                if A is None:
                    continue
                ep = float(C.at[t, s])
                eff = float(L.at[t, s]) - 0.3 * A
                if eff <= 0 or ep <= eff:                      # 数值有效性门（§3.1 逐字；不加 risk 门）
                    continue
                qty = budget / ep
                cash -= qty * ep * (1 + fee)                   # FEE_SIDE 入场侧
                pos[s] = dict(q=qty, ep=ep, eff=eff, tp=ep + 3.5669 * A, ei=bi,
                              half_done=False, r_acc=0.0, pending=False)   # ④tp 冻结（catr=3.5669）
        # ---- 3) 收盘记账 + 资金费（⑤FUNDING=0.0003/bar 逐半仓，逐「有价 bar」计，G2-D2） ----
        equity = cash
        for s, pp in pos.items():
            bars, bidx = _bidx(s)
            if t in bidx:
                m = mark.at[t, s]
                if pd.isna(m):
                    m = 0.0
                f = pp['q'] * m * fund
                cash -= f
                equity -= f
            m2 = mark.at[t, s]
            equity += pp['q'] * (0.0 if pd.isna(m2) else m2)
        eq[t] = equity
    # ---- 4) 数据末强平（mk_partial「数据末」分支逐字语义） ----
    last_t = cal[-1]
    for s, pp in list(pos.items()):
        bars, bidx = _bidx(s)
        xpx = bars[-1]['close']
        cash += pp['q'] * xpx * (1 - fee)
        cash -= pp['q'] * xpx * fund
        r2 = (xpx - pp['ep']) / pp['ep'] * 100 - 0.03 * (len(bars) - 1 - pp['ei']) - 0.05
        trade_rs.append(pp['r_acc'] + (0.5 * r2 if pp['half_done'] else r2))
        del pos[s]
    eq[last_t] = cash
    return {'curve': pd.Series(eq).sort_index(), 'n_trades': len(trade_rs),
            'mean_r': round(float(np.mean(trade_rs)), 4) if trade_rs else None}


# ================================================================ worker（Pool(32) 分发）
def _w3_worker(job):
    kind = job['kind']
    if kind == 'A':
        return w3a_arm(job['pname'], job['sig'], job['win'], job.get('lag', 1), job.get('drop'))
    ctx = MC.build_ctx()
    if kind == 'sim':       # band/base（B1._w_sim 逐字同构，drop=LOTO 检验件）
        P, cl = _pool_like(job['pname'], job.get('drop'))
        tf = B1.rand_target_fn(job['seed']) if job.get('seed') is not None else None
        return MC.simulate(cl, job['pname'], slot_mult=job.get('slot_mult', 1.0),
                           overlay=job.get('overlay'), lineage='gate', win=job.get('win'),
                           fee=job.get('fee'), fund=job.get('fund'), target_fn=tf)
    if kind == 'B':         # armC-nofee 臂（G4；overlay 在 worker 内按（子）池面板构建）
        pname = job['pname']
        P, cl = _pool_like(pname, job.get('drop'))
        ov = b_overlay(pname, P, job.get('lag', 1), job.get('drop'))
        return MC.simulate(cl, pname, slot_mult=1.0, overlay=ov, lineage='gate', win=job.get('win'),
                           fee=job.get('fee'), fund=job.get('fund'))
    raise SystemExit(f'unknown kind {kind}')


def run_jobs(jobs):
    MC.build_ctx()   # fork COW：父进程先建上下文
    with get_context('fork').Pool(min(N_PROC, len(jobs))) as pool:
        return pool.map(_w3_worker, jobs)


# ================================================================ D0 五锚（§六，一发验证，不过禁跑）
def _fd_trades(vid):
    """wave2_run.py:127-139 逐字（唯一 diff=G7 eng_final 路径）。"""
    import common_fdbrk as CF
    CF.CACHE = MC.CACHE
    pool, bull, _ = CF.pool_bull()
    fns = B3._fd_exit_fns()
    trs = []
    for tk, bars in pool.items():
        for t in B3.scan_fd_exit(bars, bull, fns[vid]):
            trs.append(dict(tkr=tk, **t))
    return [t for t in trs if t['et'] >= CF.MAIN]


def _d1_signal_worker(job):
    """wave2_run.py:298-365 逐字拷贝（事件式锚重放专用；零逻辑 diff）。"""
    sig, = job
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
            open_until[s] = pd.Timestamp(bars[xi]['time'])
    return sig, trades


def _event_weak_stats(trades):
    """wave2 event_rows_w2 弱稳格核心逐字（cushion/p/n）。"""
    lab = B1.d1_labels('full144')
    days, rs, daily = set(), [], {}
    all_daily = {}
    for tr in trades:
        t = pd.Timestamp(tr['et'])
        g = lab.get(str(t.date()))
        r = float(tr['r'])
        all_daily[t] = all_daily.get(t, 0.0) + r
        if g == '弱稳':
            days.add(t)
            rs.append(r)
            daily[t] = daily.get(t, 0.0) + r
    dv = np.array([v for _, v in sorted(daily.items())], dtype=float)
    bmed = float(np.median(MC.perm_baseline(np.array(list(all_daily.values())), len(dv))))
    cushion = float(dv.mean()) / bmed if bmed != 0 else None
    p = B1.boot_p_one_sided(dv)
    return {'n_days': len(days), 'n_sig': len(rs), 'mean_r': round(float(np.mean(rs)), 4),
            'cushion': None if cushion is None else round(cushion, 2), 'p': p}


def _armc_avoid():
    """wave2_run.py:170-183 逐字（D0 锚④a：batch1 run_s3d1 armC PB-5 全窗 avoid 重放）。"""
    specs, keys = [], []
    for p in ('old131', 'full144'):
        specs.append({'pname': p, 'win': None, 'fee': B1.FEE_S, 'fund': B1.FUND_S})
        keys.append((p, 'base'))
        P = MC.build_ctx()[p]
        thr = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool'][p]
        vol_hi = (P['vol20'] > thr).fillna(False)
        down = (P['idx'] < P['idx_ma']).fillna(False)
        g2 = (vol_hi & down).fillna(False)
        specs.append({'pname': p, 'win': None, 'fee': B1.FEE_S, 'fund': B1.FUND_S,
                      'overlay': {'off': g2.shift(1).fillna(False), 'mode': 's3'}})
        keys.append((p, 'armC'))
    res = dict(zip(keys, B1.run_arms(specs)))
    out = {}
    for p in ('old131', 'full144'):
        gs = B1.seg_stats(res[(p, 'armC')]['curve'], *FULL)
        bs = B1.seg_stats(res[(p, 'base')]['curve'], *FULL)
        out[p] = round(gs['ret_pp'] - bs['ret_pp'], 4)
    return out


def _armc_pb5_weak_row():
    """D0 锚④b：armc-s10-ruowen(PB-5) full144 弱稳格重放（W2 V27 机器逐字：G4 overlay+framework 行）。"""
    P = MC.build_ctx()['full144']
    specs = [{'pname': 'full144', 'win': None, 'fee': B1.FEE_S, 'fund': B1.FUND_S},
             {'pname': 'full144', 'win': None, 'fee': B1.FEE_S, 'fund': B1.FUND_S,
              'overlay': b_overlay('full144', P, 1)}]
    base_c, arm_c = B1.run_arms(specs)
    rows = B1.framework_variant_rows('armc-s10-ruowen', 'D2', 'full144', arm_c['curve'],
                                     base_c['curve'], FULL)
    wk = [r for r in rows if r['axis'] == 'D1' and r['domain'] == '弱稳'][0]
    return wk


def d0_gate():
    t0 = time.time()
    checks = {}
    # ① D-A 语义重放（§六锚1）
    trs_da = _fd_trades('K5-fd-exit-partial3r-breakeven')
    m2 = float(np.mean([t['r'] for t in trs_da]))
    checks['fd_DA_meanR'] = {'got': {'n': len(trs_da), 'meanR': round(m2, 4)},
                             'want': {'n': 1816, 'meanR': 1.4930},
                             'tol': 'n 逐位 / mean ±0.05',
                             'verdict': B1.av(m2, 1.4930, 0.05) if len(trs_da) == 1816 else 'MISS'}
    # ② fd ctrl（§六锚2）
    trs_ctrl = _fd_trades('K5-fd-exit-ctrl')
    m1 = float(np.mean([t['r'] for t in trs_ctrl]))
    fd = json.load(open('/workspace/repo_ready/research/wo_fdbrk/fd_result.json'))['final']['main']
    checks['fd_ctrl_meanR'] = {'got': {'n': len(trs_ctrl), 'meanR': round(m1, 4)},
                               'want': {'n': fd['n'], 'meanR': fd['mean']},
                               'tol': 'n 逐位 / mean ±0.05',
                               'verdict': B1.av(m1, fd['mean'], 0.05)
                               if len(trs_ctrl) == fd['n'] else 'MISS'}
    # ③ W2 弱稳事件式三锚重放（§六锚3；_d1_signal_worker 逐字）
    with get_context('fork').Pool(3) as pool:
        out3 = pool.map(_d1_signal_worker, [('g80',), ('rev5',), ('brk20',)])
    det3 = {}
    ok3 = True
    for sig, trades in out3:
        st = _event_weak_stats(trades)
        w = _WANT_ANCH3[sig]
        ok = (st['n_days'] == w['n_days'] and st['n_sig'] == w['n_sig']
              and st['cushion'] is not None and abs(st['cushion'] - w['cushion']) <= 0.05
              and round(st['p'], 6) == w['p'])
        det3[f'ex-{sig}-ruowen'] = {'got': st, 'want': w, 'verdict': 'hit' if ok else 'MISS'}
        ok3 = ok3 and ok
    checks['w2_weak_event_anchors'] = {'detail': det3, 'tol': 'n 逐位 / 垫 ±0.05 / p 逐位',
                                       'verdict': 'hit' if ok3 else 'MISS'}
    # ④a armC PB-5 FULL_avoid（§六锚4）
    got4 = _armc_avoid()
    ok4a = all(abs(got4[p] - w) <= 0.05 for p, w in (('old131', 43.7883), ('full144', 69.7292)))
    # ④b armc-s10-ruowen(PB-5) 弱稳格 CI/q 重放
    wk = _armc_pb5_weak_row()
    ci_lo, ci_hi, p_replay = wk['ci95_low'], wk['ci95_high'], wk['_meta']['p_one']
    f36 = [json.loads(l) for l in open(os.path.join(OUT, 'FDR_W2_M36.jsonl'))]
    ps = [c['p'] for c in f36]
    ok4b = (wk['n_days'] == 64 and wk['n_sig'] == 12
            and wk['cushion_x'] is not None and abs(wk['cushion_x'] - 170.32) <= 0.05
            and abs(ci_lo - (-3.6e-05)) <= 1e-6 and abs(ci_hi - 0.004968) <= 1e-6)
    qs_stored = MC.bh_fdr_q(ps, m_total=36)
    idx_cell = [i for i, c in enumerate(f36)
                if c['variant_id'] == 'armc-s10-ruowen' and c['pool'] == 'full144'
                and c['domain'] == '弱稳'][0]
    q_stored = round(float(qs_stored[idx_cell]), 6)
    ps_replay = list(ps)
    ps_replay[idx_cell] = p_replay
    q_replay = round(float(MC.bh_fdr_q(ps_replay, m_total=36)[idx_cell]), 6)
    ok4b = ok4b and q_stored == 0.065647 and q_replay == 0.065647 \
        and round(p_replay, 6) == f36[idx_cell]['p']
    checks['armC_pb5'] = {
        'FULL_avoid': {'got': got4, 'want': {'old131': 43.7883, 'full144': 69.7292},
                       'tol': '±0.05', 'verdict': 'hit' if ok4a else 'MISS'},
        's10_ruowen_weak_cell': {'got': {'n_days': wk['n_days'], 'n_sig': wk['n_sig'],
                                         'cushion_x': wk['cushion_x'], 'ci': [ci_lo, ci_hi],
                                         'p': round(p_replay, 6), 'q_replay': q_replay},
                                 'want': {'n_days': 64, 'n_sig': 12, 'cushion_x': 170.32,
                                          'ci': [-3.6e-05, 0.004968], 'p': f36[idx_cell]['p'],
                                          'q': 0.065647},
                                 'tol': 'n 逐位 / 垫 ±0.05 / CI ±1e-6 / p,q 逐位',
                                 'verdict': 'hit' if ok4b else 'MISS'},
        'verdict': 'hit' if (ok4a and ok4b) else 'MISS'}
    # ⑤ 门阈值逐位 + 数据态（§六锚5；md5 偏差按 G9 在库先例披露，perfile_agg+实质锚为硬闸）
    gate = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool']
    ok_thr = (gate['old131'] == 1.0359095406560563 and gate['full144'] == 1.2266534247386358)
    pf = {f: hashlib.md5(open(os.path.join(MC.CACHE, f), 'rb').read()).hexdigest()
          for f in sorted(os.listdir(MC.CACHE))}
    agg = hashlib.md5(json.dumps(pf, sort_keys=True).encode()).hexdigest()
    h = hashlib.md5()
    for f in sorted(pf):
        h.update((pf[f] + '  ' + f + '\n').encode())
    ledger = h.hexdigest()
    ok_data = (agg == '2b2c9572e054bfac04ad77444277c65c')   # batch0 workdir 冻结锚（vintage 同一性）
    checks['gate_and_snapshot'] = {
        'gate_thr': {'got': gate,
                     'want': {'old131': 1.0359095406560563, 'full144': 1.2266534247386358},
                     'tol': '逐位', 'verdict': 'hit' if ok_thr else 'MISS'},
        'snapshot': {'got': {'ledger_md5': ledger, 'perfile_agg': agg, 'n_files': len(pf)},
                     'want': {'ledger_md5_frozen': '33c8b9ec54d17537c3b7f1f6d8d47463',
                              'perfile_agg_frozen': '2b2c9572e054bfac04ad77444277c65c'},
                     'verdict': 'hit_with_registered_deviation' if (ok_data and ledger != '33c8b9ec54d17537c3b7f1f6d8d47463')
                     else ('hit' if ok_data else 'MISS'),
                     'note': 'G9：ledger≠冻结值=在库先例重序列化偏差（D0_RESULT.json md5_clarification + '
                             'dual_check.py L17-22），perfile_agg 逐位命中=batch0 workdir 冻结 vintage 同一性，'
                             'fd 双锚逐位复现为实质硬闸；perfile_agg 不符即停机'},
        'verdict': 'hit' if (ok_thr and ok_data) else 'MISS'}
    res = {'ts': time.strftime('%F %T'),
           'spec': 'METHOD_BOOK_W3 §六 D0 五锚（一发验证，不过禁跑）',
           'cache': MC.CACHE, 'checks': checks,
           'all_pass': all(c['verdict'].startswith('hit') for c in checks.values()),
           'runtime_sec': round(time.time() - t0, 1)}
    json.dump(res, open(os.path.join(OUT, 'd0_gate_w3.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    for k, c in checks.items():
        print(f"  D0 {k}: {c['verdict']}", flush=True)
    print(f"D0 五锚：all_pass={res['all_pass']} → {'放行' if res['all_pass'] else '停工'}", flush=True)
    return res


# ================================================================ 行构建（batch=W3，B1.framework_variant_rows 逐字复用）
def fw_rows_w3(vid, family, pname, arm_curve, base_curve, win, band_wins=None, lag_ok=None, notes=''):
    rows = B1.framework_variant_rows(vid, family, pname, arm_curve, base_curve, win,
                                     band_wins=band_wins, lag_ok=lag_ok, anchor_ref='new',
                                     notes=notes)
    for r in rows:
        r['batch'] = BATCH
    return rows


# ================================================================ 全量（§六运行单）
SIG_META = {
    'g80': ('w3a-g80-ruowen-arm',
            's=现行引擎四因子 cross_scores，门内掩码=vol20[t]≤thr80[p]（p80 未触发 pause），top5'
            '（mine_common.py:167-191；METHOD_BOOK_W2A.md:82 逐字）',
            'ex-g80-ruowen 9.4931/垫2.43/q=0.0（n20/n38）；K1-p80 弱稳✔ 99.81/4.78×/q=0.0',
            'vs ex-g80-ruowen（事件式格）：族口径不同（臂级 vs 事件式），两标记并行；'
            'vs K1-d-gate-vol20p80-pause：彼为门语义 FULL avoid 轴，此为门内信号臂'),
    'rev5': ('w3a-rev5-ruowen-arm', 's=−ret5，top5（batch2_run.py:440 逐字）',
             'ex-rev5-ruowen 6.1842/垫2.58/q=0.0（n48/n127）',
             'vs Q3-rev-5 四域 IC 格与 ex-rev5-ruowen：出场轴+族口径不同'),
    'brk20': ('w3a-brk20-ruowen-arm',
              's=C/H.rolling(20).max().shift(1)−1，top5（batch2_run.py:360-362,374 逐字）',
              'ex-brk20-ruowen 4.666/垫2.95/q=0.0026（n31/n83）',
              'vs Q1-brk-pos-20 与 K3-brk：连续位置强度+D-A 出场+臂级，非放量条件化事件'),
}
EV_CUSHION = {'g80': 2.43, 'rev5': 2.58, 'brk20': 2.95}   # 事件式已注册垫值（双口径并排闸①）
REVIVE_A = ('复活条件（§五 预写，R4 非空判）：(a) 影子窗样本自然滚动——域日 n≥60 且影子配对信号 n≥20 后，'
            '按本规格同判线机械复判（每自然季至多一次）；(b) 用户批准 v2 新预注册新预算；'
            '(c) RC-数据：f_real 真实费基回填（RG3 联动）之日以真实费基复核，只补数据不改判线。'
            '禁以任何「差一点」叙述复活。')
REVIVE_B = ('复活条件（§五 预写，R4 非空判）：败因假设证伪归档（现行费率 C2 仍败=「PB-5×1.5 费压吃掉超额」'
            '证伪，armc-s10-ruowen 归档「费压不敏感·超额不足」判死维持）；复活=(a) RC-数据 f_real 回填复核；'
            '(b) v2 新预注册。CI 贴零（|CI 低|<1e-4）不构成复活理由——贴零=赔率不利，预注册于此。')


def run_full(win):
    t0 = time.time()
    dom = json.load(open(os.path.join(OUT, 'domains.json')))
    jobs, tags = [], []
    # 共享件：band 40（C1 随机带共享 band42..61，§3.1/§4.2）+ base 4（现行/PB-5 × 两池）
    for p in ('full144', 'old131'):
        for s in range(42, 62):
            jobs.append({'kind': 'sim', 'pname': p, 'win': win, 'seed': s})
            tags.append(('band', p, f'band{s}'))
        jobs.append({'kind': 'sim', 'pname': p, 'win': win})
        tags.append(('base', p, 'base'))
        jobs.append({'kind': 'sim', 'pname': p, 'win': win, 'fee': B1.FEE_S, 'fund': B1.FUND_S})
        tags.append(('base_pb5', p, 'base_pb5'))
    # 方向 A：3 变体 × 两池 × lag{1,2}（检验件）；A 臂为显式窗事件臂，win=None→FULL（§3.1 判线窗）
    W_A = win or FULL
    for sig in ('g80', 'rev5', 'brk20'):
        for p in ('full144', 'old131'):
            for lag in (1, 2):
                jobs.append({'kind': 'A', 'pname': p, 'sig': sig, 'win': W_A, 'lag': lag})
                tags.append(('A', p, f'{sig}-lag{lag}'))
    # 方向 A LOTO：20 去一臂（full144 主池；C5 检验件不入预算）
    rng = np.random.default_rng(MC.SEED)
    drops = [sorted(MC.build_ctx()['pools']['full144'])[int(rng.integers(144))] for _ in range(20)]
    for sig in ('g80', 'rev5', 'brk20'):
        for d in drops:
            jobs.append({'kind': 'A', 'pname': 'full144', 'sig': sig, 'win': W_A, 'drop': d})
            tags.append(('A_loto', 'full144', f'{sig}|{d}'))
    # LOTO base（现行费率，方向 A/B 共享）
    for d in drops:
        jobs.append({'kind': 'sim', 'pname': 'full144', 'win': win, 'drop': d})
        tags.append(('base_loto', 'full144', d))
    # 方向 B：nofee 两池 × lag{1,2} + PB-5 对照臂 full144（闸①双口径并排）+ B LOTO 20
    for p in ('full144', 'old131'):
        for lag in (1, 2):
            jobs.append({'kind': 'B', 'pname': p, 'win': win, 'lag': lag})
            tags.append(('B', p, f'nofee-lag{lag}'))
        jobs.append({'kind': 'B', 'pname': p, 'win': win, 'fee': B1.FEE_S, 'fund': B1.FUND_S, 'lag': 1})
        tags.append(('B_pb5', p, 'pb5-lag1'))
    for d in drops:
        jobs.append({'kind': 'B', 'pname': 'full144', 'win': win, 'drop': d})
        tags.append(('B_loto', 'full144', d))
    print(f'[w3] jobs={len(jobs)}（band40/base4/A12/A_LOTO60/base_LOTO20/B4/B_PB5_2/B_LOTO20）…', flush=True)
    out = run_jobs(jobs)
    res = dict(zip(tags, out))
    detail = {'drops': drops}

    # ---- C1 随机带（B1.band_wins_of 逐字） ----
    band_res = {(p, k): v for (kk, p, k), v in res.items() if kk == 'band'}
    band_wins = {p: B1.band_wins_of(band_res, p, win) for p in ('full144', 'old131')}
    weak_dates = {p: B1.dom_dates(p, win or FULL)['弱稳'] for p in ('full144', 'old131')}

    rows, judge, detail_c5 = [], [], {}
    # 主臂行 + 主方向登记
    arm_curves = {}
    for sig in ('g80', 'rev5', 'brk20'):
        vid, desc, anchor, dup = SIG_META[sig]
        for p in ('full144', 'old131'):
            c = res[('A', p, f'{sig}-lag1')]['curve']
            cl = res[('A', p, f'{sig}-lag2')]['curve']
            bc = res[('base', p, 'base')]['curve']
            arm_curves[(sig, p)] = c
            nt = (f'方向 A 弱稳域×信号臂（§3.1 共用骨架：K2 仓位骨架+D-A 五件出场逐字，预算 4 变体冻结）；'
                  f'信号={desc}；复现锚（事件式已注册）={anchor}；查重标注：{dup}；'
                  f'费口径声明：臂费=FEE_SIDE 双边+FUNDING 0.03%/bar，与 base（现行引擎费线）结构对齐，'
                  f'费不轻于 base（§3.1 防虚增声明）；双口径并排：事件式垫值 {EV_CUSHION[sig]}×（在案）'
                  f'vs 本行臂级 cushion_x（C4 单位=域内日超额，族归位 §3.0，两单位不可互换比较）；'
                  f'部署开关/参数邻域禁触（§二#3#4）；revliq 样本门放弃登记（§3.0）不占预算')
            lag_ok = bool(B1.seg_stats(cl, *FULL)['ret_pp'] > B1.seg_stats(bc, *FULL)['ret_pp'])
            rows += fw_rows_w3(vid, 'W3A', p, c, bc, win or FULL, band_wins=band_wins[p],
                               lag_ok=lag_ok, notes=nt)
    # B 主臂行
    for p in ('full144', 'old131'):
        c = res[('B', p, 'nofee-lag1')]['curve']
        cl = res[('B', p, 'nofee-lag2')]['curve']
        bc = res[('base', p, 'base')]['curve']
        c5 = res[('B_pb5', p, 'pb5-lag1')]['curve']
        nt = ('方向 B 无费压对照臂（§4.1 团队裁决：只动臂费参数，主判读线不变，C2 腿重设计否决）；'
              'vid=armc-s10-ruowen-nofee；spec={pname,win,FULL,fee:None→DE.FEE_SIDE=0.0005,'
              'fund:None→DE.FUNDING=0.0003,slot_mult:1.0,overlay=armC 定义 batch1_run.py:930-959 '
              '+W2A §5.1 域掩码 W2 V27 逐字，mode=s3}；唯二差异=费参数与域掩码（§4.2）；'
              '主判口径唯一=现行费率格，一次成活禁择优（闸②）；双口径并排（闸①）：PB-5 原格 '
              'CI[-3.6e-05,0.004968]/q=0.065647/垫170.32（wave2_result.json 在案，本运行 PB-5 对照臂行同表披露）；'
              '费敏感注记（W2B 工单⑤）：fd 线 ΔmeanR=−0.105/+0.01pp、dneg 线 Δavoid=−0.63/−1.54pp 量级；'
              'f_real 数据回填（RG3）前无部署通道；查重标注：vs armc-s10-ruowen(PB-5) 仅费参数一维差异，'
              'vid 全新；vs ATLAS armC 8 格（全窗门无域过滤）：域内生效轴；vs K1-d-downweight：孤立降权轴不混写')
        lag_ok = bool(B1.seg_stats(cl, *FULL)['ret_pp'] > B1.seg_stats(bc, *FULL)['ret_pp'])
        rows += fw_rows_w3('armc-s10-ruowen-nofee', 'W3B', p, c, bc, win or FULL,
                           band_wins=band_wins[p], lag_ok=lag_ok, notes=nt)
        # PB-5 对照行（只披露，不判读）
        rows += fw_rows_w3('armc-s10-ruowen-PB5-对照列', 'W3B', p, c5, res[('base_pb5', p, 'base_pb5')]['curve'],
                           win or FULL, band_wins=band_wins[p], lag_ok=lag_ok,
                           notes='PB-5 费压对照臂（闸①双口径并排专用披露行，非登记变体不入 FDR 不判生死；'
                                 '在案锚=armc-s10-ruowen CI[-3.6e-05,0.004968]/q=0.065647/垫170.32）')
    # ---- C5（LOTO/分年/lag）装配 ----
    for sig in ('g80', 'rev5', 'brk20'):
        vid, *_ = SIG_META[sig]
        c = arm_curves[(sig, 'full144')]
        bc = res[('base', 'full144', 'base')]['curve']
        cl = res[('A', 'full144', f'{sig}-lag2')]['curve']
        ex_full = B1.daily_excess(c, bc).reindex(weak_dates['full144']).dropna()
        full_mean = float(ex_full.mean())
        yr = {int(y): round(float(ex_full[ex_full.index.year == y].mean()), 6)
              for y in sorted(set(ex_full.index.year))}
        yearly_flip = bool(len({np.sign(v) for v in yr.values() if v != 0}) > 1)
        signs = []
        for d in drops:
            a_l = res[('A_loto', 'full144', f'{sig}|{d}')]['curve']
            b_l = res[('base_loto', 'full144', d)]['curve']
            ex_l = B1.daily_excess(a_l, b_l).reindex(weak_dates['full144']).dropna()
            signs.append(np.sign(float(ex_l.mean())) == np.sign(full_mean) and full_mean != 0)
        loto_pass = bool(np.sum(signs) >= 19) if len(signs) == 20 else None
        ex_lag = B1.daily_excess(cl, bc).reindex(weak_dates['full144']).dropna()
        lag_same = bool(np.sign(float(ex_lag.mean())) == np.sign(full_mean) and full_mean != 0)
        detail_c5[vid] = {'full_weak_mean_excess': round(full_mean, 6), 'yearly_mean': yr,
                          'yearly_flip': yearly_flip, 'loto_pass_n': int(np.sum(signs)),
                          'loto_pass': loto_pass, 'lag_same_direction': lag_same,
                          'lag_FULL_avoid_pp': round(B1.seg_stats(cl, *FULL)['ret_pp']
                                                     - B1.seg_stats(bc, *FULL)['ret_pp'], 4)}
        for r in rows:
            if r['variant_id'] == vid and r['axis'] == 'D1' and r['pool'] == 'full144':
                r['loto_pass'], r['yearly_flip'] = loto_pass, yearly_flip
    # B C5
    c = res[('B', 'full144', 'nofee-lag1')]['curve']
    bc = res[('base', 'full144', 'base')]['curve']
    cl = res[('B', 'full144', 'nofee-lag2')]['curve']
    ex_full = B1.daily_excess(c, bc).reindex(weak_dates['full144']).dropna()
    full_mean = float(ex_full.mean())
    yr = {int(y): round(float(ex_full[ex_full.index.year == y].mean()), 6)
          for y in sorted(set(ex_full.index.year))}
    yearly_flip = bool(len({np.sign(v) for v in yr.values() if v != 0}) > 1)
    signs = []
    for d in drops:
        a_l = res[('B_loto', 'full144', d)]['curve']
        b_l = res[('base_loto', 'full144', d)]['curve']
        ex_l = B1.daily_excess(a_l, b_l).reindex(weak_dates['full144']).dropna()
        signs.append(np.sign(float(ex_l.mean())) == np.sign(full_mean) and full_mean != 0)
    loto_pass = bool(np.sum(signs) >= 19) if len(signs) == 20 else None
    ex_lag = B1.daily_excess(cl, bc).reindex(weak_dates['full144']).dropna()
    lag_same = bool(np.sign(float(ex_lag.mean())) == np.sign(full_mean) and full_mean != 0)
    detail_c5['armc-s10-ruowen-nofee'] = {
        'full_weak_mean_excess': round(full_mean, 6), 'yearly_mean': yr, 'yearly_flip': yearly_flip,
        'loto_pass_n': int(np.sum(signs)), 'loto_pass': loto_pass,
        'lag_same_direction': lag_same,
        'lag_FULL_avoid_pp': round(B1.seg_stats(cl, *FULL)['ret_pp']
                                   - B1.seg_stats(bc, *FULL)['ret_pp'], 4)}
    for r in rows:
        if r['variant_id'] == 'armc-s10-ruowen-nofee' and r['axis'] == 'D1' and r['pool'] == 'full144':
            r['loto_pass'], r['yearly_flip'] = loto_pass, yearly_flip
    detail['c5'] = detail_c5

    # ---- FDR m=4 + 合并参考列 m=126 + 判定（§一.3/.4；无中间态） ----
    pcells = []
    for r in rows:
        if r['axis'] == 'D1' and r['pool'] == 'full144' and r['domain'] == '弱稳' \
                and r['family'] in ('W3A', 'W3B') and not r['variant_id'].endswith('对照列'):
            pcells.append({'variant_id': r['variant_id'], 'pool': r['pool'], 'domain': r['domain'],
                           'p': r['_meta']['p_one'],
                           'p_kind': 'boot_p_one_sided（域内日超额 ≤0 频率，块长10 B1000 seed42）',
                           'note': '锚定域=弱稳格（§一.1：仅弱稳入批内 FDR m=4；其余三域=邻域补全记账不入拒绝域）'})
    assert len(pcells) == 4, f'预算 4 变体冻结，实得 {len(pcells)} 格'
    qs4 = MC.bh_fdr_q([c['p'] for c in pcells], m_total=M_W3)
    merged_p = [json.loads(l)['p'] for l in open(os.path.join(OUT, 'FDR_MERGED_M86.jsonl'))]
    merged_p += [json.loads(l)['p'] for l in open(os.path.join(OUT, 'FDR_W2_M36.jsonl'))]
    merged_p += [c['p'] for c in pcells]
    qs_ref = MC.bh_fdr_q(merged_p, m_total=M_MERGED_REF)[-4:]
    qmap = {}
    with open(os.path.join(OUT, 'FDR_W3_M4.jsonl'), 'w') as f:
        for c, q4, qr in zip(pcells, qs4, qs_ref):
            c['q_m4'] = round(float(q4), 6)
            c['q_merged_ref_m126'] = round(float(qr), 6)
            c['fdr_note'] = ('批内 m=4 为判读口径（§一.4 预注册）；q_merged_ref_m126=合并参考列'
                             '（86+36+4，只作多重度量披露，禁择优引用）')
            qmap[(c['variant_id'], c['pool'], c['domain'])] = c['q_m4']
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    # 六腿判定（§5.3 逐字；判线无中间态）——在 _meta pop 前判（C3 需本行 mdd_base；C6 用 qmap）
    band_w = band_wins['full144']['弱稳']
    for r in rows:
        if r['axis'] != 'D1' or r['pool'] != 'full144' or r['domain'] != '弱稳':
            continue
        if r['family'] not in ('W3A', 'W3B') or r['variant_id'].endswith('对照列'):
            continue
        n = r['n_days'] or 0
        mt = r.get('_meta') or {}
        q_v = qmap.get((r['variant_id'], r['pool'], r['domain']))
        c1 = (r['win_rate_pct'] is not None and band_w is not None
              and r['win_rate_pct'] >= band_w)
        c2 = (r['excess_pp'] is not None and r['excess_pp'] > 0
              and r['ci95_low'] is not None and r['ci95_low'] > 0)
        c3 = (r['mdd_pct'] is not None and mt.get('mdd_base') is not None
              and abs(r['mdd_pct']) <= abs(mt['mdd_base']))
        c4 = r['cushion_x'] is not None and r['cushion_x'] >= 3.0
        c6 = q_v is not None and q_v <= 0.10
        c5d = detail_c5[r['variant_id']]
        c5 = bool(c5d['loto_pass']) and not c5d['yearly_flip'] and c5d['lag_same_direction']
        competent = bool(n >= 60 and c2 and c4 and c6 and c1 and c3)
        alive = bool(competent and c5)
        r['_judge'] = {'C1': c1, 'C2': c2, 'C3': c3, 'C4': c4, 'C5': c5, 'C6': c6,
                       'n_ge_60': n >= 60, 'domain_competent': competent,
                       'mdd_base_weak': mt.get('mdd_base'),
                       'final': '达标（转影子候选【打折】）' if alive else '判死',
                       'revive_condition': '' if alive else (REVIVE_B if r['family'] == 'W3B' else REVIVE_A),
                       'discount_note': '达标=口径变更格【打折】资格：影子候选（窗内非真样本外），'
                                        '图谱标注「口径变更」，影子期 n≥20 判读一次封印后终审，'
                                        '放行走部署三道门+新预注册，本单单次达标不生效放行权（§五/§七 终裁③）'
                       if alive else ''}
    judge = [dict(variant_id=r['variant_id'], pool=r['pool'], domain=r['domain'], **r['_judge'])
             for r in rows if '_judge' in r]
    for r in rows:
        m = r.pop('_meta', None)
        r['fdr_q'] = qmap.get((r['variant_id'], r['pool'], r['domain']))
        if r['axis'] != 'D1':
            continue
        n = r['n_days'] or 0
        if n < 60:
            r['notes'] = (r['notes'] + ' INSUFFICIENT(n<60)——old131 伴行=同向计数列'
                          '（§一.5：只报方向一致性计数，不作胜任判定，预注册）').strip()
    # old131 弱稳同向计数列（§一.5）
    cnt = []
    for r in rows:
        if r['axis'] == 'D1' and r['pool'] == 'old131' and r['domain'] == '弱稳' \
                and r['family'] in ('W3A', 'W3B') and not r['variant_id'].endswith('对照列'):
            rf = [x for x in rows if x['variant_id'] == r['variant_id']
                  and x['pool'] == 'full144' and x['domain'] == '弱稳' and x['axis'] == 'D1'][0]
            cnt.append({'variant_id': r['variant_id'],
                        'old131_weak_excess_pp': r['excess_pp'],
                        'full144_weak_excess_pp': rf['excess_pp'],
                        'same_direction': bool(np.sign(r['excess_pp'] or 0) == np.sign(rf['excess_pp'] or 0))})
    # FACTBOOK 落盘
    with open(os.path.join(OUT, 'FACTBOOK_W3.jsonl'), 'w') as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in COLS}, ensure_ascii=False) + '\n')
    detail['band_wins'] = band_wins
    detail['n_jobs'] = len(jobs)
    detail['wall_secs'] = round(time.time() - t0, 1)
    return rows, pcells, judge, cnt, detail


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'smoke'
    t0 = time.time()
    if mode == 'd0':
        r = d0_gate()
        sys.exit(0 if r['all_pass'] else 3)
    if mode == 'full':
        dg = json.load(open(os.path.join(OUT, 'd0_gate_w3.json')))
        if not dg.get('all_pass'):
            print('D0 五锚未过——禁跑判线（一发验证禁令），停下报告', flush=True)
            sys.exit(3)
        win = None
        print('[full] 全量（预算 4 变体冻结；Pool(32)）', flush=True)
    else:
        win = SMOKE_WIN
        print(f'[smoke] 截断窗 {win[0].date()}~{win[1].date()}（R8 冒烟）', flush=True)
    rows, pcells, judge, cnt, detail = run_full(win)
    print(f'      行={len(rows)} pcells={len(pcells)} {detail["wall_secs"]}s', flush=True)
    if mode == 'full':
        # 引擎零改动 md5 自查
        eng_md5 = {}
        for root in ('/workspace/repo_ready/engine_f1', '/workspace/repo_ready/f1'):
            if os.path.isdir(root):
                for fn in sorted(os.listdir(root)):
                    if fn.endswith('.py'):
                        p = os.path.join(root, fn)
                        eng_md5[p] = hashlib.md5(open(p, 'rb').read()).hexdigest()
        res = {'ts': time.strftime('%F %T'), 'spec': 'METHOD_BOOK_W3 §六运行单（Pool(32)，预算 4 变体冻结）',
               'cache': MC.CACHE, 'n_factbook_rows': len(rows),
               'fdr': {'m_batch': M_W3, 'm_merged_ref': M_MERGED_REF, 'registered': pcells,
                       'note': '批内 FDR m=4 为判读口径；合并参考列 m=126 只披露（§一.4 预注册）'},
               'd0_gate': json.load(open(os.path.join(OUT, 'd0_gate_w3.json'))),
               'judgment': judge, 'old131_direction_count': cnt,
               'copy_diff_log': COPY_DIFF_LOG, 'detail': detail,
               'engine_md5_unchanged': eng_md5,
               'r10_note': '本运行不产出任何「域读数→仓位」映射（R10 红线全程）',
               'ruling_note': '判线结果交交易分析团队终裁（用户工单）；本件只产图谱证据与影子候选资格',
               'runtime_sec': round(time.time() - t0, 1)}
        json.dump(res, open(os.path.join(OUT, 'w3_result.json'), 'w'),
                  ensure_ascii=False, indent=1, default=str)
        print(f'      FACTBOOK_W3 行={len(rows)} → 判定 {len(judge)} 格', flush=True)
        for j in judge:
            print(f"      {j['variant_id']}: C1={j['C1']} C2={j['C2']} C3={j['C3']} C4={j['C4']} "
                  f"C5={j['C5']} C6={j['C6']} → {j['final']}", flush=True)
    print(f'done {round(time.time() - t0, 1)}s', flush=True)


if __name__ == '__main__':
    main()
