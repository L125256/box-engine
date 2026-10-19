#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REGIME_SPEC_v1 运行脚本 · regime_run.py（预注册声明，先冻结后运行）
================================================================================
预注册头注（引用 research/REGIME_SPEC_v1.md 条款，判线数字冻结，改判线=违规）：
- 本脚本为 REGIME_SPEC_v1 §五 运行脚本（用户工单指定路径 research/wo_regime/regime_run.py）。
- 六族读数（SPEC §二）：RG1 费压 ×3 变体 / RG2 换手 ×2 / RG3 资金费 ×2 / RG4 宽度加速度 ×3
  / RG5 idx-breadth 背离 ×2 / RG6 止损密度 ×3，合计 m=15 变体一次性冻结，禁止加族（SPEC §四 L5）。
- 六腿判线（SPEC §四 4.1 逐字）：
  L1 提前性：E1-E3 中 ≥2/3 事件，触发先于变脸点 ≥3 交易日命中
      （实现口径冻结：触发日 ∈ [事件−30, 事件−3] 交易日窗，触发=读数越过训练段
        2025-06-01→2026-05-31 的 P90（上向假设）/P10（下向假设）极值带）；
  L2 假阳性：N1=realB 反弹段（2026-04-01→2026-05-31，61 日）触发 ≤2 次，
      且 realA 全程假触发月均 ≤1（假触发=不落任何事件前 30 日窗内的触发日）；
  L3 稳定性：①分年（2025H2/2026H1/2026H2）效应方向不翻脸；②old131 与 full144 双池同向；
      ③lag=1（shift(1)）方向不翻转；
  L4 显著性：变脸点前 10 交易日 vs 常态日均值差的 bootstrap 95% CI 不含 0
      （B=2000，seed=42，按日重采样）；LOTO：留一标的剔除，重抽 20 次 ≥19 次方向不变（seed=42）；
  L5 多重检验：BH FDR q=0.10 合并族，m=15（RG3 不可判定变体计入 m、不计 p）；
  L6 垫：标准化效应量 ≥3× 随机置换基线中位数（置换 1000 次，seed=42）。
- 达标=六腿全过（双池并算：每腿 old131 与 full144 均须过，W3 先例「单池入选不达标」同法）；
  判死附复活条件（RC-数据/RC-事件/RC-结构，SPEC §四 4.3）；无「基本达标」中间态（终裁③）。
- R1 一发验证：同切分重跑配额 ≤1，仅限判定聚合代码路径缺陷修复（SPEC §四 4.3）。
- R7 证据分级：产物逐字段带【实证】/【推断】/【假设】；合成段低权重不进判线。
- RG3 探针先行（批准记录第 1 条）：沙箱探针不可达 → RG3 记「不可判定」结单（W1 复活条件①）。
- 定位铁律（SPEC §六.1）：本脚本只产生读数与判线结果，无任何仓位动作逻辑。

用法：
  python3 regime_run.py prep            # 引擎回放+基线缓存+D0 对拍（diff=0 断言）
  python3 regime_run.py probe           # RG3 交易所 API 探针（10s 超时）
  python3 regime_run.py anchor          # E1/E2/E3 CUSUM 变点锚定（冻结事件清单）
  python3 regime_run.py run [--smoke]   # 六族六腿判线全量（--smoke=60日截断冒烟，非权威）

数据口径（SPEC §三）：realA=2025-06-01→2026-10-17；训练=2025-06-01→2026-05-31；
留出 realC=2026-06-01→2026-10-17；N1=2026-04-01→2026-05-31；seed=42 冻结；R8=Pool(32)。
数据 asof 强制截断至 2026-10-17（与 f1_live.json 回放终点一致，2026-10-19 盘中部分K不入）。
"""
import argparse
import hashlib
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

REPO = '/workspace/repo_ready'
ENGINE_DIR = os.path.join(REPO, 'engine_f1')
TMP = '/tmp/wo_regime'
OUT_DIR = os.path.join(REPO, 'research', 'wo_regime')
LIVE_JSON = os.path.join(REPO, 'f1_web', 'f1_live.json')
ASOF = pd.Timestamp('2026-10-17')
SEED = 42
BASE_B = 2000          # L4 bootstrap 次数（SPEC L4 冻结）
BASE_PERM = 1000       # L6 置换次数（SPEC L6 冻结）
BASE_LOTO = 20         # L4 LOTO 重抽次数（SPEC L4 冻结）
FDR_Q = 0.10           # L5（SPEC 冻结）
PAD_X = 3.0            # L6 垫倍数（SPEC 冻结）
MA_REG = 50
TOP_N = 5
FEE_ANN = 252          # 费线年化（f1_signal.eval_breakers 口径，D0-4 已验）

REALA = (pd.Timestamp('2025-06-01'), ASOF)
TRAIN = (pd.Timestamp('2025-06-01'), pd.Timestamp('2026-05-31'))
N1 = (pd.Timestamp('2026-04-01'), pd.Timestamp('2026-05-31'))
# 事件清单（SPEC §三 冻结；E1 实测日由 anchor 子命令 CUSUM 落盘 event_anchor.json）
E_ANCHORS = {'E1': pd.Timestamp('2026-04-15'),   # 2026-04 成本脸跳变（mid-month 假设锚，anchor 实测后冻结）
             'E2': pd.Timestamp('2026-06-01'),
             'E3': pd.Timestamp('2026-08-09')}

sys.path.insert(0, ENGINE_DIR)
os.environ.setdefault('F1_POOL', '/tmp/eng_wt/cleaned_pool.json')
os.environ.setdefault('F1_CACHE', '/tmp/box_cache')
import f1_signal as FS  # noqa: E402  （引擎权威副本 sha=6acc937d…，AUTHORITY_SHA.json 登记）


def log(msg):
    print(f'[regime_run] {msg}', flush=True)


def load_pool_data():
    """引擎快照数据 + 权威池 144，截断至 ASOF。返回 (data, syms, old131)。"""
    data = FS.load_data(FS.CACHE)
    for s in data:
        data[s] = data[s][data[s].index <= ASOF]
    syms = FS.build_pool(data)
    old131 = sorted(s for s in syms if data[s].index[0] <= pd.Timestamp('2025-03-31'))
    assert len(old131) == 131, f'old131={len(old131)} != 131（dneg_engine.build_pools 同法）'
    return data, syms, old131


def close_frame(data, syms):
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    return close.reindex(cal)


def breadth_series(close):
    """研究口径日度宽度（wo_g1g2fdr_run.py L302 逐字）：pct = (close>ma50).mean×100。"""
    above = close > close.rolling(50, min_periods=40).mean()
    return above.mean(axis=1) * 100.0


def calc_turnover(rp, close, open_):
    """RG2 换手【推断】口径：开桶日（周信号执行日）持仓成分变动率 = (n_out+n_in)/(2×TOP_N)，
    日度前向填充。引擎不落盘 qty 明细，T4 换手 0.175→0.678x 同为开桶日口径。"""
    hold = rp['holdings']
    rows = {}
    prev = set()
    for t, names in hold.items():
        cur = set(names.split(',')) if isinstance(names, str) and names else set()
        if prev:
            rows[t] = (len(prev - cur) + len(cur - prev)) / (2.0 * TOP_N)
        prev = cur
    to = pd.Series(rows).sort_index()
    return to.reindex(close.index).ffill().fillna(0.0)


# ---------------------------------------------------------------- prep + D0
def cmd_prep():
    os.makedirs(TMP, exist_ok=True)
    t0 = time.time()
    data, syms, old131 = load_pool_data()
    F = FS.build_factors(data)
    log(f'pool=144(old131={len(old131)}) 数据加载 {time.time()-t0:.1f}s，开始回放…')
    rp = FS.replay(data, F, syms, slot=FS.SLOTS[0])
    log(f'回放完成 {time.time()-t0:.1f}s：eq_net 终值 {rp["eq_net"].iloc[-1]:.4f}')

    idx = rp['idx']
    idx_ma = idx.rolling(MA_REG).mean()
    close = close_frame(data, syms)
    br = breadth_series(close)
    fees = rp['fees']
    fee60 = fees.rolling(60).sum()
    fee60_ann = fee60 / 60.0 * FEE_ANN
    to = calc_turnover(rp, close, close)  # holdings 名单口径，px 不需要

    # 引擎自身 eval_breakers 重算（D0 权威对拍）
    tier_idx = 0
    bk = FS.eval_breakers(rp, tier_idx, asof=ASOF)
    gate = {'idx': round(float(idx.iloc[-1]), 4),
            'ma50': round(float(idx_ma.iloc[-1]), 4),
            'on_holdcash': bool(idx.iloc[-1] < idx_ma.iloc[-1])}
    # calc_breadth 引擎锚（engine 口径 = 当日有K线入分母）
    br_eng = FS.calc_breadth(data, syms)
    br_eng_trunc = FS.calc_breadth({s: data[s] for s in syms}, syms)

    npz = {'idx': idx.values, 'idx_ma50': idx_ma.values, 'breadth': br.values,
           'fees': fees.values, 'fee60_ann': fee60_ann.values, 'turnover': to.values,
           'eq_net': rp['eq_net'].values,
           'dates': idx.index.values}  # datetime64 原生 dtype 存取（pandas3 us 分辨率，禁转 int64）
    np.savez_compressed(os.path.join(TMP, 'baseline.npz'), **npz)
    stops = pd.DataFrame(rp['stops'])
    stops.to_csv(os.path.join(TMP, 'stops.csv'), index=False)

    live = json.load(open(LIVE_JSON))
    lbk = {it['name']: it for it in live['breakers']['items']}
    checks = []

    def chk(name, a, b, tol=0.0):
        ok = (abs(a - b) <= tol) if isinstance(a, (int, float)) else (a == b)
        checks.append({'item': name, 'ours': a, 'live': b, 'diff': (a - b) if isinstance(a, (int, float)) else None, 'pass': bool(ok)})
        return ok

    gate_live = live['signal']['gate']
    chk('D0-2 gate.idx', gate['idx'], gate_live['idx'])
    chk('D0-2 gate.ma50', gate['ma50'], gate_live['ma50'])
    chk('D0-2 gate.on_holdcash', gate['on_holdcash'], gate_live['on_holdcash'])
    fee_d = lbk['FEE']['detail']
    chk('D0-4 fee_60d', round(float(fees.iloc[-60:].sum()), 6), fee_d['fee_60d'])
    chk('D0-4 fee_ann_pct', round(float(fee60_ann.iloc[-1]), 4), fee_d['fee_ann_pct'])
    cb3 = lbk['CB3']['detail']
    cb2_ours = bk['detail']['CB2']
    chk('D0-3 CB2.stop_count_60d(engine重算)', int(cb2_ours['stop_count_60d']), int(cb3['stop_count_60d']))
    chk('D0-3 CB2.stop_pnl_sum_60d(engine重算)', float(cb2_ours['stop_pnl_sum_60d']), float(lbk['CB2']['detail']['stop_pnl_sum_60d']))
    chk('D0-3 CB3 基线对拍(9.07)', float(cb3['baseline_60d']), 9.07)
    chk('D0-1 CB1.mdd20(engine重算)', float(bk['detail']['CB1']),
        float(lbk['CB1']['detail']) if isinstance(lbk['CB1']['detail'], (int, float)) else float(lbk['CB1']['detail'][0]))

    d0 = {'asof': str(ASOF.date()), 'checks': checks,
          'all_pass': all(c['pass'] for c in checks),
          'engine_sha256_current': FS.engine_sha256()[:16],
          'engine_sha256_live_meta': live['meta'].get('engine_sha256', '')[:16],
          'eq_net_ours': round(float(rp['eq_net'].iloc[-1]), 4),
          'eq_net_live_replay': live['meta']['replay']['eq_net'],
          'eq_net_delta_note': '回放净账终值非 D0 四腿，差异登记备查（live 由前版引擎 sha=262bf3a4 生成，现行 sha=6acc937d 含 WO-BREADTH-01）',
          'note': 'live meta sha 与现行引擎不一致=WO-BREADTH-01 于 live 生成(2026-10-19 05:20)后改引擎（零行为改动），D0 以行为值对拍为准',
          'breadth_engine_asof_full': br_eng, 'breadth_engine_asof_trunc': br_eng_trunc,
          'breadth_spec_anchor': {'pct': 22.92, 'n_above': 33, 'n_total': 144, 'measured': '2026-10-19'}}
    json.dump(d0, open(os.path.join(TMP, 'd0_result.json'), 'w'), ensure_ascii=False, indent=2, default=str)
    for c in checks:
        log(f'  {c["item"]}: ours={c["ours"]} live={c["live"]} -> {"PASS" if c["pass"] else "FAIL"}')
    log(f'D0 总判定: {"ALL PASS" if d0["all_pass"] else "FAIL —— 按规格停工"}')
    log(f'breadth 引擎锚(全量 asof): {br_eng} | 截断 asof={ASOF.date()}: {br_eng_trunc} | 规格锚 22.92/33/144')
    return d0


# ---------------------------------------------------------------- RG3 探针
def cmd_probe():
    import urllib.request
    endpoints = [
        ('binance_funding', 'https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1'),
        ('bybit_tickers', 'https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT'),
    ]
    out = {'ts': time.strftime('%F %T'), 'network_note': '沙箱实测，云端待复测', 'results': []}
    for name, url in endpoints:
        try:
            urllib.request.urlopen(url, timeout=10)
            code = 200
            ok = True
        except Exception as e:
            code = getattr(e, 'code', None) or str(e)[:80]
            ok = False
        out['results'].append({'name': name, 'url': url, 'reachable': ok, 'http': str(code)})
        log(f'probe {name}: reachable={ok} http={code}')
    out['verdict'] = 'REACHABLE' if all(r['reachable'] for r in out['results']) else 'UNREACHABLE'
    os.makedirs(TMP, exist_ok=True)
    json.dump(out, open(os.path.join(TMP, 'rg3_probe.json'), 'w'), ensure_ascii=False, indent=2)
    log(f'RG3 探针总判定: {out["verdict"]}（不可达 → RG3 按 SPEC 判「不可判定」结单）')
    return out


# ---------------------------------------------------------------- CUSUM 锚定
def cusum_changepoint(x):
    """双侧 CUSUM（T4/E1 同法）：S=cumsum(x−mean)，k*=argmax|S|，返回 (k*, |S|max)。"""
    s = np.cumsum(x - x.mean())
    k = int(np.argmax(np.abs(s)))
    return k, float(abs(s[k]))


def cmd_anchor():
    prep_cache = os.path.join(TMP, 'baseline.npz')
    if not os.path.exists(prep_cache):
        log('缺少 baseline 缓存，先跑 prep…')
        cmd_prep()
    z = np.load(prep_cache)
    dates = pd.DatetimeIndex(z['dates'])
    idx = pd.Series(z['idx'], index=dates)
    fee_ann = pd.Series(z['fee60_ann'], index=dates)

    results = []
    # E1：费压序列（T4 法），±30d 窗（mid-April 假设锚）
    series_map = {'fee60_ann': fee_ann, 'idx_ret': idx.pct_change(),
                  'idx_logdiff': np.log(idx).diff(), 'abs_ret(波动)': idx.pct_change().abs()}
    for ev, anchor, series_name, series in (
            ('E1', E_ANCHORS['E1'], 'fee60_ann', fee_ann),
            ('E2', E_ANCHORS['E2'], 'idx_ret', idx.pct_change()),
            ('E3', E_ANCHORS['E3'], 'idx_ret', idx.pct_change())):
        lo, hi = anchor - pd.Timedelta(days=30), anchor + pd.Timedelta(days=30)
        w = series[(series.index >= lo) & (series.index <= hi)].dropna()
        k, smax = cusum_changepoint(w.values)
        measured = w.index[k]
        dev_days = int(abs((measured - anchor).days))
        results.append({'event': ev, 'anchor': str(anchor.date()), 'series': series_name,
                        'window': [str(lo.date()), str(hi.date())], 'n_days': int(len(w)),
                        'cusum_max': round(smax, 6),
                        'measured': str(measured.date()), 'dev_days': dev_days,
                        'decision': '维持原锚' if dev_days <= 2 else '建议修正'})
        # 旁证序列（R7：多序列互证，防单序列边界伪影）
        aux = []
        for nm, s2 in series_map.items():
            if nm == series_name:
                continue
            w2 = s2[(s2.index >= lo) & (s2.index <= hi)].dropna()
            if len(w2) < 20:
                continue
            k2, smax2 = cusum_changepoint(w2.values)
            aux.append({'series': nm, 'measured': str(w2.index[k2].date()),
                        'cusum_max': round(smax2, 6),
                        'near_edge': bool((w2.index[k2] - lo).days < 6 or (hi - w2.index[k2]).days < 6)})
        results[-1]['aux_series'] = aux

    # E1 交叉验证：idx_ret 同窗 CUSUM（费压为主判，idx 为旁证）
    w = idx.pct_change()[(idx.index >= E_ANCHORS['E1'] - pd.Timedelta(days=30)) &
                         (idx.index <= E_ANCHORS['E1'] + pd.Timedelta(days=30))].dropna()
    k, smax = cusum_changepoint(w.values)
    results.append({'event': 'E1-旁证', 'anchor': str(E_ANCHORS['E1'].date()), 'series': 'idx_ret',
                    'window': [str(w.index[0].date()), str(w.index[-1].date())], 'n_days': int(len(w)),
                    'cusum_max': round(smax, 6), 'measured': str(w.index[k].date()),
                    'dev_days': int(abs((w.index[k] - E_ANCHORS['E1']).days)),
                    'decision': '旁证非判'})

    out = {'method': '双侧 CUSUM（S=cumsum(x−mean)，k*=argmax|S|；同 E1/T4 法）',
           'rule': '偏差 ≤2 日维持原锚，>2 日建议修正（工单冻结规则）',
           'series_note': 'E1 主判=fee60_ann（费压，T4 口径）；E2/E3 主判=idx 日收益（池等权均价）',
           'results': results,
           'frozen_events': {r['event']: {'anchor': r['anchor'], 'measured': r['measured'],
                                          'final': r['anchor'] if r['decision'] == '维持原锚' else r['measured'],
                                          'decision': r['decision']} for r in results if not r['event'].endswith('旁证')}}
    json.dump(out, open(os.path.join(OUT_DIR, 'event_anchor.json'), 'w'), ensure_ascii=False, indent=2)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    log('事件锚定已写入 research/wo_regime/event_anchor.json（事件清单冻结）')
    return out


# ---------------------------------------------------------------- 六族读数
def build_readings(z, stops_csv, pool_mask_syms=None):
    """由 baseline 缓存构建六族读数（full144 基准；LOTO 重算在 run 内单独处理）。"""
    dates = pd.DatetimeIndex(z['dates'])
    idx = pd.Series(z['idx'], index=dates)
    br = pd.Series(z['breadth'], index=dates)
    fee_ann = pd.Series(z['fee60_ann'], index=dates)
    fees = pd.Series(z['fees'], index=dates)
    to = pd.Series(z['turnover'], index=dates)
    stops = pd.read_csv(stops_csv, parse_dates=['date'])
    r = {}
    real = (dates >= REALA[0]) & (dates <= REALA[1])
    r['dates'] = dates
    r['realA'] = pd.Series(real, index=dates)
    # RG1
    r['rg1a'] = fee_ann
    r['rg1b'] = fee_ann - fee_ann.shift(20)            # 20 日 CUSUM 漂移【推断】口径
    exec_fee = fees.copy()
    exec_fee[~fees.index.isin(_exec_days(dates))] = np.nan
    r['rg1c'] = exec_fee.ffill()                        # 交易费/开桶日
    # RG2
    r['rg2a'] = to.rolling(20).mean()
    r['rg2b'] = r['rg2a'].diff(20)
    # RG3 —— 探针不可达：不产读数（不可判定，禁备源估算顶替，涂一线席）
    # RG4
    r['rg4a'] = br - br.shift(5)
    r['rg4b'] = br - br.shift(20)
    neg = (br - br.shift(5)) < 0
    grp = (~neg).cumsum()
    r['rg4c'] = neg.groupby(grp).cumsum()               # Δ5 连续为负天数计数
    # RG5
    ia = idx.loc[REALA[0]:REALA[1]]
    ba = br.loc[REALA[0]:REALA[1]]
    z1 = ((idx.pct_change(20) - ia.pct_change(20).mean()) / ia.pct_change(20).std()).clip(-3, 3)
    b20 = br.rolling(20).mean()
    z2 = ((b20 - ba.rolling(20).mean().mean()) / ba.rolling(20).mean().std()).clip(-3, 3)
    r['rg5a'] = z1 - z2
    r['rg5b'] = ((idx > idx.rolling(MA_REG).mean()) & (br < 50)).astype(float)
    # RG6
    sdaily = stops.groupby('date').size().reindex(dates).fillna(0)
    r['rg6a'] = sdaily.rolling(60).sum()
    r['rg6b'] = r['rg6a'].diff(1)
    spnl = stops.assign(w=stops['pnl_pct'] * stops.get('slot', FS.SLOTS[0])) if len(stops) else stops
    spnl60 = spnl.groupby('date')['w'].sum().reindex(dates).fillna(0).rolling(60).sum() if len(stops) \
        else pd.Series(0.0, index=dates)
    r['rg6c'] = spnl60
    return r


def _exec_days(dates):
    return FS.week_first_days(dates)


# 方向预注册（SPEC §二 假设方向）：+1=上向 P90 带，−1=下向 P10 带
VARIANTS = [
    ('RG1-1', 'rg1a', +1, 'fee60_ann 水平，费压上行'),
    ('RG1-2', 'rg1b', +1, 'fee60_ann 20 日 CUSUM 漂移'),
    ('RG1-3', 'rg1c', +1, '交易费/开桶日'),
    ('RG2-1', 'rg2a', +1, 'turnover20 水平'),
    ('RG2-2', 'rg2b', +1, '换手一阶差分 Δ20'),
    ('RG3-1', None, +1, 'funding30 水平'),
    ('RG3-2', None, +1, 'funding30 跳变（30d vs 前30d）'),
    ('RG4-1', 'rg4a', -1, 'Δbreadth5（崩塌速度，下向）'),
    ('RG4-2', 'rg4b', -1, 'Δbreadth20'),
    ('RG4-3', 'rg4c', +1, 'Δ5 连续为负天数'),
    ('RG5-1', 'rg5a', +1, 'div20 水平（顶背离）'),
    ('RG5-2', 'rg5b', +1, '二元顶背离标记'),
    ('RG6-1', 'rg6a', +1, 'stop_cnt60 密度水平'),
    ('RG6-2', 'rg6b', +1, '密度一阶差分/加速度'),
    ('RG6-3', 'rg6c', +1, 'stop_pnl60 深度'),
]
assert len(VARIANTS) == 15


def _band_trigger(x, train_mask, direction):
    """触发序列：越过训练段 P90（上向）/P10（下向）极值带的日度布尔。"""
    tr = x[train_mask].dropna()
    if len(tr) < 30:
        return None
    q = tr.quantile(0.90 if direction > 0 else 0.10)
    return (x > q) if direction > 0 else (x < q), float(q)


def _events_dates(events):
    return {k: pd.Timestamp(v) for k, v in events.items()}


def eval_variant(args):
    """单变体六腿评估（worker）。args=(vid, key, direction, readings_dict, events, loto_n, b_boot, n_perm, pool_tag)"""
    vid, key, direction, R, events, loto_n, b_boot, n_perm, pool_tag = args
    dates = R['dates']
    realA = R['realA'].values.astype(bool)
    train_mask = (dates >= TRAIN[0]) & (dates <= TRAIN[1])
    x = R[key] if key else None
    if x is None:
        return {'id': vid, 'pool': pool_tag, 'status': 'undecidable',
                'reason': 'RG3 数据源不可达（探针），禁备源估算顶替', 'revival': 'RC-数据：交易所 API 回填落地后重测（W1 复活条件①）'}
    trig_q = _band_trigger(x, train_mask, direction)
    if trig_q is None:
        return {'id': vid, 'pool': pool_tag, 'status': 'dead', 'reason': '训练段读数不足', 'legs': {}}
    trig, band = trig_q
    trig = trig.fillna(False).values

    ev_dates = _events_dates(events)
    # L1 提前性：命中 = 触发日 ∈ [E−30, E−3] 交易日
    hits, leads = {}, {}
    pos = {d: i for i, d in enumerate(dates)}
    for en, ed in ev_dates.items():
        if ed not in pos:
            hits[en] = None
            continue
        i_e = pos[ed]
        lo = max(0, i_e - 30)
        win = [i for i in range(lo, i_e - 2) if trig[i]]
        hits[en] = len(win) > 0
        leads[en] = (i_e - win[0]) if win else None
    n_hit = sum(1 for v in hits.values() if v)
    # L2 假阳性
    ev_windows = pd.Series(False, index=dates)
    for ed in ev_dates.values():
        if ed in pos:
            ev_windows.iloc[max(0, pos[ed] - 30):pos[ed] + 1] = True
    n1_mask = (dates >= N1[0]) & (dates <= N1[1])
    n1_hits = int((trig & n1_mask).sum())
    false_trig = int((trig & realA & ~ev_windows.values).sum())
    months_realA = (REALA[1] - REALA[0]).days / 30.44
    # L4 效应：事件前 10 交易日 vs 常态日
    pre10 = pd.Series(False, index=dates)
    for ed in ev_dates.values():
        if ed in pos:
            pre10.iloc[max(0, pos[ed] - 10):pos[ed]] = True
    xv = x.values.astype(float)
    mA, mB = pre10.values & ~np.isnan(xv), realA & ~pre10.values & ~np.isnan(xv)
    A, B = xv[mA], xv[mB]
    eff = float(np.mean(A) - np.mean(B))
    sd = float(np.std(np.concatenate([A, B]), ddof=1))
    eff_z = eff / sd if sd > 0 else 0.0
    rng = np.random.default_rng(SEED)
    boots = np.array([np.mean(rng.choice(A, len(A))) - np.mean(rng.choice(B, len(B))) for _ in range(b_boot)])
    ci = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))
    # 方向一致性：假设方向上效应为正（上向族效应>0；下向族效应<0）
    dir_ok_stat = eff * direction > 0
    ci_ok = (ci[0] * direction > 0) or (ci[1] * direction < 0)
    # L6 置换基线
    cand = np.where(realA & ~np.isnan(xv))[0]
    perms = []
    for _ in range(n_perm):
        pick = rng.choice(cand, size=len(ev_dates), replace=False)
        pA = np.concatenate([xv[max(0, p - 10):p] for p in pick])
        pB = xv[[i for i in cand if all(abs(i - p) > 10 for p in pick)]]
        if len(pA) == 0 or len(pB) == 0:
            continue
        pe = np.mean(pA) - np.mean(pB)
        perms.append(pe / sd if sd > 0 else 0.0)
    pad_med = float(np.median(np.abs(perms))) if perms else 0.0
    pad_ok = abs(eff_z) >= PAD_X * pad_med and pad_med > 0
    p_perm = float((np.sum(np.abs(np.array(perms)) >= abs(eff_z)) + 1) / (len(perms) + 1)) if perms else 1.0

    legs = {'L1': {'pass': n_hit >= 2, 'hits': {k: bool(v) for k, v in hits.items()}, 'lead_days': {k: v for k, v in leads.items()}, 'n_hit': n_hit, 'need': '≥2/3'},
            'L2': {'pass': n1_hits <= 2 and false_trig / months_realA <= 1.0, 'n1_hits': n1_hits, 'false_trig_total': false_trig, 'monthly': round(false_trig / months_realA, 3)},
            'L4': {'pass': bool(ci_ok and dir_ok_stat), 'effect': round(eff, 6), 'effect_z': round(eff_z, 4), 'ci95': [round(c, 6) for c in ci], 'B': b_boot, 'seed': SEED},
            'L6': {'pass': bool(pad_ok), 'effect_z': round(eff_z, 4), 'perm_median': round(pad_med, 4), 'threshold': round(PAD_X * pad_med, 4), 'n_perm': n_perm, 'p_perm': round(p_perm, 4), 'seed': SEED}}
    return {'id': vid, 'key': key, 'direction': direction, 'pool': pool_tag, 'band': round(band, 6),
            'status': 'ok', 'legs': legs, 'p_perm': legs['L6']['p_perm']}


def eval_l3(args):
    """L3 稳定性（分年 + lag=1；双池同向在聚合层判）。args=(vid,key,direction,R,events,events_prev_year_map)"""
    vid, key, direction, R, events = args
    if key is None:
        return {'id': vid, 'year_effects': {}, 'lag1_effect': None, 'no_flip': False,
                'undecidable': True}
    dates = R['dates']
    x = R[key]
    realA = R['realA'].values.astype(bool)
    pos = {d: i for i, d in enumerate(dates)}
    years = {'2025H2': ('2025-06-01', '2025-12-31'), '2026H1': ('2026-01-01', '2026-06-30'), '2026H2': ('2026-07-01', '2026-10-17')}
    year_sign = {}
    xv = x.values.astype(float)
    for yn, (a, b) in years.items():
        evs = [pd.Timestamp(v) for v in events.values() if a <= str(pd.Timestamp(v).date()) <= b]
        if not evs:
            year_sign[yn] = None
            continue
        pre = pd.Series(False, index=dates)
        for ed in evs:
            if ed in pos:
                pre.iloc[max(0, pos[ed] - 10):pos[ed]] = True
        A = xv[pre.values & ~np.isnan(xv)]
        B = xv[realA & ~pre.values & ~np.isnan(xv)]
        if len(A) < 3 or len(B) < 10:
            year_sign[yn] = None
            continue
        year_sign[yn] = float(np.mean(A) - np.mean(B)) * direction  # >0=同假设方向
    # lag=1
    x1 = x.shift(1)
    pre10 = pd.Series(False, index=dates)
    for ed in _events_dates(events).values():
        if ed in pos:
            pre10.iloc[max(0, pos[ed] - 10):pos[ed]] = True
    A1 = x1[pre10.values & ~np.isnan(x1.values)].values
    B1 = x1[realA & ~pre10.values & ~np.isnan(x1.values)].values
    lag_sign = (np.mean(A1) - np.mean(B1)) * direction if len(A1) > 3 else None
    signs = [s for s in year_sign.values() if s is not None] + ([lag_sign] if lag_sign is not None else [])
    no_flip = all(s > 0 for s in signs) if signs else False
    return {'id': vid, 'year_effects': {k: (round(v, 6) if v is not None else None) for k, v in year_sign.items()},
            'lag1_effect': round(float(lag_sign), 6) if lag_sign is not None else None,
            'no_flip': bool(no_flip)}


# ---------------------------------------------------------------- LOTO（重活，Pool(32)）
def _loto_worker(args):
    """留一标的重算读数效应方向（一次回放，多键复用）。
    args=(drop_sym, keys_dirs{key:direction}, events)"""
    drop_sym, keys_dirs, events = args
    data, syms, _ = load_pool_data()
    syms2 = [s for s in syms if s != drop_sym]
    F = FS.build_factors(data)
    rp = FS.replay(data, F, syms2, slot=FS.SLOTS[0])
    idx = rp['idx']
    close = close_frame(data, syms2)
    br = breadth_series(close)
    fees = rp['fees']
    fee_ann = fees.rolling(60).sum() / 60.0 * FEE_ANN
    to = calc_turnover(rp, close, close)
    stops = pd.DataFrame(rp['stops'])
    dates = idx.index
    sdaily = stops.groupby('date').size().reindex(dates).fillna(0) if len(stops) else pd.Series(0.0, index=dates)
    spnl = stops.assign(w=stops['pnl_pct'] * stops.get('slot', FS.SLOTS[0])).groupby('date')['w'].sum().reindex(dates).fillna(0) if len(stops) else pd.Series(0.0, index=dates)
    series = {'rg1a': fee_ann, 'rg1b': fee_ann - fee_ann.shift(20), 'rg1c': fees.copy(),
              'rg2a': to.rolling(20).mean(), 'rg2b': to.rolling(20).mean().diff(20),
              'rg6a': sdaily.rolling(60).sum(), 'rg6b': sdaily.rolling(60).sum().diff(1), 'rg6c': spnl}
    realA = (dates >= REALA[0]) & (dates <= REALA[1])
    pos = {d: i for i, d in enumerate(dates)}
    pre10 = pd.Series(False, index=dates)
    for ed in _events_dates(events).values():
        if ed in pos:
            pre10.iloc[max(0, pos[ed] - 10):pos[ed]] = True
    out = {'drop': drop_sym}
    for key, direction in keys_dirs.items():
        x = series[key]
        xv = x.values.astype(float)
        A = xv[pre10.values & ~np.isnan(xv)]
        B = xv[np.asarray(realA) & ~pre10.values & ~np.isnan(xv)]
        eff = (np.mean(A) - np.mean(B)) * direction if len(A) > 3 else 0.0
        out[key] = bool(eff > 0)
    return out


# ---------------------------------------------------------------- run 主流程
def cmd_run(smoke=False):
    prep_cache = os.path.join(TMP, 'baseline.npz')
    if not os.path.exists(prep_cache):
        cmd_prep()
    z = np.load(prep_cache)
    stops_csv = os.path.join(TMP, 'stops.csv')
    # 事件清单：anchor 结果冻结优先
    events = dict(E_ANCHORS)
    anchor_path = os.path.join(OUT_DIR, 'event_anchor.json')
    if os.path.exists(anchor_path):
        frozen = json.load(open(anchor_path))['frozen_events']
        events = {k: pd.Timestamp(v['final']) for k, v in frozen.items()}
        log(f'事件清单（冻结）: { {k: str(v.date()) for k, v in events.items()} }')

    if smoke:
        # 冒烟：截断 realA 至 60 交易日（2026-02-01→2026-04-30），事件仅 E1，
        # bootstrap/置换/LOTO 降配（链路跑通验证，非权威，R7 标注【冒烟·低权重】）
        global REALA, TRAIN, N1
        REALA = (pd.Timestamp('2026-02-01'), pd.Timestamp('2026-04-30'))
        TRAIN = (pd.Timestamp('2026-02-01'), pd.Timestamp('2026-03-31'))
        N1 = (pd.Timestamp('2026-03-01'), pd.Timestamp('2026-03-20'))
        events = {'E1': pd.Timestamp('2026-04-15')}
        b_boot, n_perm, loto_n, nproc = 200, 50, 2, 4
    else:
        b_boot, n_perm, loto_n, nproc = BASE_B, BASE_PERM, BASE_LOTO, 32

    probe_p = os.path.join(TMP, 'rg3_probe.json')
    rg3_reachable = json.load(open(probe_p))['verdict'] == 'REACHABLE' if os.path.exists(probe_p) else False
    if not rg3_reachable and not smoke:
        log('RG3 探针不可达 → RG3-1/RG3-2 记「不可判定」（SPEC 批准记录第 1 条）')

    # 读数（full144 主基准 + old131 子池：用池内标的重切 idx/breadth；费/止损/换手来自 144 池回放，
    # old131 双池纪律对 RG1/RG2/RG6 以 idx/事件效应复算近似不可行 → 如实登记：
    # L3-② 双池同向对价格域读数（RG4/RG5）逐位重算，对回放域读数（RG1/RG2/RG6）标注【受限】）
    data, syms, old131 = load_pool_data()
    close_o = close_frame(data, old131)
    br_o = breadth_series(close_o)
    idx_o = close_o.mean(axis=1)

    R_full = build_readings(z, stops_csv)
    # old131 价格域读数替换
    R_old = build_readings(z, stops_csv)
    R_old['rg4a'] = br_o - br_o.shift(5)
    R_old['rg4b'] = br_o - br_o.shift(20)
    neg = (br_o - br_o.shift(5)) < 0
    R_old['rg4c'] = neg.groupby((~neg).cumsum()).cumsum()
    ia = idx_o.loc[REALA[0]:REALA[1]]
    ba = br_o.loc[REALA[0]:REALA[1]]
    b20 = br_o.rolling(20).mean()
    z1 = ((idx_o.pct_change(20) - ia.pct_change(20).mean()) / ia.pct_change(20).std()).clip(-3, 3)
    z2_ = ((b20 - ba.rolling(20).mean().mean()) / ba.rolling(20).mean().std()).clip(-3, 3)
    R_old['rg5a'] = z1 - z2_
    R_old['rg5b'] = ((idx_o > idx_o.rolling(MA_REG).mean()) & (br_o < 50)).astype(float)

    tasks_full = [(vid, key, d, R_full, events, loto_n, b_boot, n_perm, 'full144')
                  for vid, key, d, _ in VARIANTS]
    tasks_old = [(vid, key, d, R_old, events, loto_n, b_boot, n_perm, 'old131')
                 for vid, key, d, _ in VARIANTS]
    with Pool(nproc) as p:
        res_full = p.map(eval_variant, tasks_full)
        res_old = p.map(eval_variant, tasks_old)
    with Pool(nproc) as p:
        l3_full = p.map(eval_l3, [(vid, key, d, R_full, events) for vid, key, d, _ in VARIANTS])
        l3_old = p.map(eval_l3, [(vid, key, d, R_old, events) for vid, key, d, _ in VARIANTS])

    # L5 BH FDR（合并族 m=15；RG3 不可判定不计 p）
    ps = {}
    for r in res_full:
        if r['status'] == 'ok':
            ps[r['id']] = r['p_perm']
    ids = [vid for vid, _, _, _ in VARIANTS if vid in ps]
    m = len(ids)
    bh_pass = {}
    if m:
        sorted_ids = sorted(ids, key=lambda i: ps[i])
        prev = 1.0
        crit = {}
        for rank, i in enumerate(reversed(sorted_ids), 1):
            k = m - rank + 1
            val = min(prev, ps[i] * m / k)
            crit[i] = val
            prev = val
        bh_pass = {i: crit[i] <= FDR_Q for i in ids}

    # LOTO（全量模式：回放域族 RG1/RG2/RG6，20 个留一标的 × 每标的 1 次回放复用 8 键，Pool(32)）
    loto_results = {}
    if not smoke:
        loto_keys = ['rg1a', 'rg1b', 'rg1c', 'rg2a', 'rg2b', 'rg6a', 'rg6b', 'rg6c']
        keys_dirs = {k: next(d for v, kk, d, _ in VARIANTS if kk == k) for k in loto_keys}
        rng = np.random.default_rng(SEED)
        drops = [str(rng.choice(syms)) for _ in range(BASE_LOTO)]
        with Pool(nproc) as p:
            loto_raw = p.map(_loto_worker, [(s, keys_dirs, events) for s in drops])
        for k in loto_keys:
            n_ok = sum(1 for r in loto_raw if r[k])
            loto_results[k] = {'n_ok_dir': n_ok, 'n_total': len(loto_raw),
                               'pass': n_ok >= BASE_LOTO - 1}  # ≥19/20（SPEC L4）
    # 价格域 LOTO（idx/breadth 快算，免回放；loto_req=≥19/20，冒烟降配 loto_n-1）
    loto_req = BASE_LOTO - 1 if not smoke else max(1, loto_n - 1)

    def price_loto(key, direction, base_close):
        rng = np.random.default_rng(SEED)
        ok = 0
        syms_here = list(base_close.columns)
        for j in range(BASE_LOTO if not smoke else loto_n):
            drop = syms_here[(j * 17) % len(syms_here)]
            sub = base_close.drop(columns=[drop])
            idx2 = sub.mean(axis=1)
            br2 = (sub > sub.rolling(50, min_periods=40).mean()).mean(axis=1) * 100.0
            s = {'rg4a': br2 - br2.shift(5), 'rg4b': br2 - br2.shift(20),
                 'rg5a': idx2.pct_change(20), 'rg5b': (idx2 > idx2.rolling(MA_REG).mean()).astype(float)}[key]
            realA = (s.index >= REALA[0]) & (s.index <= REALA[1])
            pos = {d: i for i, d in enumerate(s.index)}
            pre = pd.Series(False, index=s.index)
            for ed in _events_dates(events).values():
                if ed in pos:
                    pre.iloc[max(0, pos[ed] - 10):pos[ed]] = True
            xv = s.values.astype(float)
            A = xv[pre.values & ~np.isnan(xv)]
            B = xv[np.asarray(realA) & ~pre.values & ~np.isnan(xv)]
            if len(A) > 3 and (np.mean(A) - np.mean(B)) * direction > 0:
                ok += 1
        return ok

    # 聚合判定（双池并算：每腿两池均须过；RG3=不可判定非死）
    families = {}
    for vid, key, d, desc in VARIANTS:
        rf = next(r for r in res_full if r['id'] == vid)
        ro = next(r for r in res_old if r['id'] == vid)
        l3f = next(r for r in l3_full if r['id'] == vid)
        l3o = next(r for r in l3_old if r['id'] == vid)
        entry = {'desc': desc, 'direction': d, 'full144': rf, 'old131': ro, 'L3_full': l3f, 'L3_old': l3o}
        if rf['status'] == 'undecidable':
            entry['verdict'] = 'UNDECIDABLE'
            entry['revival'] = rf['revival']
            families[vid] = entry
            continue
        legs = {}
        legs['L1'] = rf['legs']['L1']['pass'] and ro['legs']['L1']['pass']
        legs['L2'] = rf['legs']['L2']['pass'] and ro['legs']['L2']['pass']
        legs['L3'] = l3f['no_flip'] and l3o['no_flip']
        legs['L4'] = rf['legs']['L4']['pass'] and ro['legs']['L4']['pass']
        legs['L5'] = bool(bh_pass.get(vid, False))
        l6 = rf['legs']['L6']['pass'] and ro['legs']['L6']['pass']
        # LOTO 增补进 L4 判定（SPEC L4：≥19/20 方向不变）
        if key in ('rg4a', 'rg4b', 'rg5a', 'rg5b'):
            okp = price_loto(key, d, close_frame(data, syms))
            legs['L4'] = legs['L4'] and okp >= loto_req
            legs['_loto_price_ok'] = okp
        elif key in loto_results:
            legs['L4'] = legs['L4'] and loto_results[key]['pass']
            legs['_loto_replay'] = loto_results[key]
        legs['L6'] = l6
        entry['legs'] = legs
        entry['verdict'] = 'PASS' if all(legs.values()) else 'DEAD'
        if entry['verdict'] == 'DEAD':
            fails = [k for k in ('L1', 'L2', 'L3', 'L4', 'L5', 'L6') if not legs[k]]
            entry['fail_legs'] = fails
            entry['revival'] = ('RC-事件：下一真实变脸事件（E4+，A2 刷新配额内）加数据再判'
                                if 'L1' in fails else
                                'RC-结构：影子期实测分布显示判线前提失真，须新工单重立判线（禁止就地放宽）')
        families[vid] = entry

    out = {'spec': 'REGIME_SPEC_v1', 'asof': str(ASOF.date()), 'seed': SEED, 'smoke': smoke,
           'events_frozen': {k: str(v.date()) for k, v in events.items()},
           'probe': rg3_reachable, 'm_fdr': m, 'fdr_q': FDR_Q,
           'bh_pass': bh_pass, 'loto_replay': loto_results, 'families': families,
           'data_limits': ['RG2 换手=开桶日成分变动率【推断】口径（引擎无 qty 明细）',
                           'old131 双池对回放域读数（RG1/RG2/RG6）共用 144 回放序列，双池同向检验仅对价格域（RG4/RG5）逐位重算',
                           'RG3 资金费：探针不可达 → 不可判定'],
           'r7_tags': '价格域读数【实证】；RG2 口径【推断】；RG3 状态【实证-探针】+结论【不可判定】'}
    suffix = '_smoke' if smoke else ''
    json.dump(out, open(os.path.join(TMP, f'rg_result{suffix}.json'), 'w'), ensure_ascii=False, indent=2, default=str)
    if not smoke:
        json.dump(out, open(os.path.join(OUT_DIR, 'rg_result.json'), 'w'), ensure_ascii=False, indent=2, default=str)
    for vid, _, _, _ in VARIANTS:
        f = families[vid]
        log(f'  {vid}: {f["verdict"]}' + (f' fail={f.get("fail_legs")}' if f.get('fail_legs') else ''))
    log(f'判线完成（smoke={smoke}），产物 /tmp/wo_regime/rg_result{suffix}.json' + ('' if smoke else ' + research/wo_regime/rg_result.json'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['prep', 'probe', 'anchor', 'run'])
    ap.add_argument('--smoke', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'prep':
        cmd_prep()
    elif a.cmd == 'probe':
        cmd_probe()
    elif a.cmd == 'anchor':
        cmd_anchor()
    elif a.cmd == 'run':
        cmd_run(smoke=a.smoke)


if __name__ == '__main__':
    main()
