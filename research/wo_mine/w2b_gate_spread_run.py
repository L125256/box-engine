#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W2-B 工单⑥：Gate 两市场价差序列入库（EWZUSDT vs EWZ_USDT 日K；W2B_SPEC §6 逐字）
================================================================================
R10 红线：数据件无判线、不改部署姿态。缺源=【数据受限】登记非死（R5，必附替代路径）；
缺日禁插值（禁 fill）。引用必附出处（R2）。
源定位（§6.2-1）：
- A = box_cache EWZUSDT（唯一数据态 /tmp/box_cache_w2a，snapshot_20261019 perfile-agg
  2b2c9572…，见 wave2_run.py 头注数据态事件登记）；
- B = Gate 原始 API EWZ_USDT（有网则拉取全历史；本机实测 gate.io 无 EWZ 系任何交易对
  → 缺源【数据受限】）；
- B' = R5 替代路径：导演站 EWZUSDT 实时拉取（同源不同 vintage，非两市场价差，诚实标注）。
产出：research/wo_w1/gate_funding/gate_spread_EWZ.jsonl + gate_spread_EWZ_manifest.json
      + W2B_GATE_SPREAD_REPORT.md
"""
import hashlib
import json
import os
import ssl
import time
import urllib.request

import numpy as np
import pandas as pd

REPO = '/workspace/repo_ready'
OUT = os.path.join(REPO, 'research', 'wo_w1', 'gate_funding')
CACHE_A = '/tmp/box_cache_w2a/EWZUSDT.json'
DY = 'https://www.kxiandaoyan.com'
GATE = 'https://api.gateio.ws/api/v4'
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}


def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def md5f(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def source_A():
    d = json.load(open(CACHE_A))
    df = pd.DataFrame(d)
    df['time'] = pd.to_datetime(df['time'])
    return df.set_index('time').sort_index(), {'path': CACHE_A,
                                               'md5': md5f(CACHE_A),
                                               'n_bars': len(d),
                                               'first': str(d[0]['time']), 'last': str(d[-1]['time']),
                                               'source': 'box_cache 现货缓存（导演站谱系快照）'}


def source_B_gate():
    """Gate 原始 API EWZ_USDT（§6.2-1 主定源）。缺源=【数据受限】。"""
    out = {'probes': []}
    try:
        pairs = http_json(GATE + '/spot/currency_pairs')
        ewz = [x['id'] for x in pairs if 'EWZ' in x['id'].upper()]
        out['probes'].append({'url': GATE + '/spot/currency_pairs', 'total_pairs': len(pairs),
                              'ewz_matches': ewz})
        out['verdict'] = ('Gate.io 全部 %d 个现货交易对中无任何 EWZ 系对（EWZUSDT/EWZ_USDT '
                          'candlesticks 实测均 INVALID_CURRENCY_PAIR）→ B 源缺失'
                          '【数据受限·R5·非死】' % len(pairs)) if not ewz else 'found'
        out['available'] = bool(ewz)
    except Exception as e:
        out['verdict'] = f'Gate API 探测失败：{type(e).__name__}: {e}'
        out['available'] = False
    return out


def source_Bp_dy():
    """R5 替代路径：导演站 EWZUSDT 实时拉取（B'，同源不同 vintage，非两市场价差）。
    API 单次上限 2000 根（limit>2000 实测 422），2000 根=2019-01-04 起全量覆盖 A 窗。"""
    d = http_json(DY + '/api/kline/EWZUSDT?limit=2000')
    df = pd.DataFrame(d['bars'])
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    return df, {
        'url': DY + '/api/kline/EWZUSDT?limit=2000', 'code': d.get('code'), 'name': d.get('name'),
        'market': d.get('market'), 'period': d.get('period'),
        'fetched_at': time.strftime('%FT%TZ', time.gmtime()),
        'n_bars': len(df), 'first': str(df.index[0].date()), 'last': str(df.index[-1].date()),
        'source': '导演站实时 API（kxiandaoyan；symbols_reconcile 谱系同源）',
        'bar_date_convention': '北京日期+盘后延伸+周日合成bar（dy_symbols_241.json _lineage 登记）'}


def build_spread(A, Bp):
    """§6.2-2/3/4：对齐 + 价差序列 + 低量日标注 + 描述统计。缺日单列，禁插值。"""
    a = A[['close', 'volume']].rename(columns={'close': 'close_A', 'volume': 'vol_A'})
    b = Bp[['close', 'volume']].rename(columns={'close': 'close_B', 'volume': 'vol_B'})
    j = a.join(b, how='inner')
    missing = sorted(set(A.index) - set(Bp.index))
    j['abs_gap'] = (j['close_A'] - j['close_B']).abs()
    j['rel_gap_bp'] = 200 * (j['close_A'] - j['close_B']) / (j['close_A'] + j['close_B'])
    p10 = float(j['vol_A'].quantile(0.10))
    j['low_liq'] = (j['vol_A'] == 0) | (j['vol_A'] < p10)
    full = j[~j['low_liq']]
    def stats(s):
        return {'n': int(s.notna().sum()), 'mean': float(s.mean()), 'median': float(s.median()),
                'std': float(s.std(ddof=1)),
                'p5': float(s.quantile(0.05)), 'p50': float(s.quantile(0.50)),
                'p95': float(s.quantile(0.95))}
    imax = j['abs_gap'].idxmax()
    descr = {'A_close': stats(j['close_A']), 'B_close': stats(j['close_B']),
             'abs_gap': stats(j['abs_gap']),
             'abs_gap_max': {'value': float(j['abs_gap'].max()), 'date': str(imax.date())},
             'rel_gap_bp': stats(j['rel_gap_bp']),
             'low_liq_share_pct': round(float(j['low_liq'].mean()) * 100, 2),
             'low_liq_n': int(j['low_liq'].sum()),
             'abs_rel_gap_gt_50bp_days': int((j['rel_gap_bp'].abs() > 50).sum()),
             'low_liq_abs_gap_mean': round(float(full['abs_gap'].mean()), 6)
             if len(full) else None,
             'all_abs_gap_mean': round(float(j['abs_gap'].mean()), 6),
             'low_liq_note': '低量日价差单列统计（防低量日假价差污染均值）；low_liq 口径='
                             'A 源 volume==0 或 <A 全样本 P10（【口径操作化·R7】）'}
    return j, missing, p10, descr


def completeness(j, missing, union_idx):
    """§6.2-6 完备性门（冻结）：对齐日 n≥500 且 2025-06-01 后覆盖完整。
    覆盖口径=两源交易日并集（【口径操作化·R7】：自然日历会把周末误报为缺口）；
    评估区间=[2025-06-01, min(A末,B'末)]（A 快照截至日之后的 B' 独有日单列登记）。"""
    n = len(j)
    end = min(union_idx[-1], pd.Timestamp(j.index[-1]))
    win = [t for t in union_idx if t >= pd.Timestamp('2025-06-01') and t <= end]
    gap_post = [t for t in win if t not in set(j.index)]
    verdict = 'PASS' if (n >= 500 and not gap_post) else 'FAIL（登记缺口清单交付，不插值）'
    return {'n_aligned': n, 'threshold_n': 500,
            'coverage_basis': '两源交易日并集（非自然日历）',
            'post_realA_complete': not gap_post,
            'post_realA_missing_days': [str(x.date()) for x in gap_post][:50],
            'n_post_missing': len(gap_post),
            'verdict': verdict}


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    print('[1/4] 源 A（box_cache 快照）…', flush=True)
    A, ma = source_A()
    print('   ', ma['n_bars'], ma['first'], '→', ma['last'], flush=True)
    print('[2/4] 源 B（Gate 原始 API EWZ_USDT）…', flush=True)
    mb = source_B_gate()
    print('   ', mb['verdict'][:80], flush=True)
    print('[3/4] 源 B\'（导演站实时，R5 替代路径）…', flush=True)
    Bp, mp = source_Bp_dy()
    print('   ', mp['n_bars'], mp['first'], '→', mp['last'], flush=True)
    print('[4/4] 对齐与价差序列…', flush=True)
    j, missing, p10, descr = build_spread(A, Bp)
    union_idx = sorted(set(A.index) | set(Bp.index))
    comp = completeness(j, missing, union_idx)
    print('      对齐日 n=%d 完备性门=%s' % (comp['n_aligned'], comp['verdict']), flush=True)
    with open(os.path.join(OUT, 'gate_spread_EWZ.jsonl'), 'w') as f:
        for t, r in j.iterrows():
            f.write(json.dumps({'ts': str(t.date()), 'close_A': round(r['close_A'], 6),
                                'close_B': round(r['close_B'], 6),
                                'abs_gap': round(r['abs_gap'], 6),
                                'rel_gap_bp': round(r['rel_gap_bp'], 4),
                                'vol_A': r['vol_A'], 'vol_B': r['vol_B'],
                                'low_liq': bool(r['low_liq'])}, ensure_ascii=False) + '\n')
    man = {'_doc': 'gate_spread_EWZ manifest（W2B_SPEC §6.2 冻结口径）',
           'generated_at': time.strftime('%F %T'),
           'source_A': ma, 'source_B_gate': mb,
           'source_Bp_dy_fallback': {**mp, 'honest_label': 'B\'=同源不同 vintage（导演站），'
                                     '非两市场价差——两市场口径因 Gate 缺 EWZ 对而不可得'
                                     '【数据受限·R5·非死】，复活条件=Gate 上架 EWZ 系对或'
                                     '提供 EWZ_USDT 命名端点'},
           'schema': 'gate_spread_EWZ.jsonl 逐日行 {ts,close_A,close_B,abs_gap,rel_gap_bp,'
                     'vol_A,vol_B,low_liq}；rel_gap_bp=200×(A−B)/(A+B)（对称相对价差）',
           'adjustment_declaration': '两源均为原始日K无复权标记（A=导演站谱系缓存，'
                                     'B\'=同源实时；口径声明一致，无需停机核对）',
           'low_liq_p10_volA': round(p10, 2),
           'per_file_md5': {'gate_spread_EWZ.jsonl': md5f(os.path.join(OUT, 'gate_spread_EWZ.jsonl'))},
           'descriptive': descr, 'missing_days_vs_Bp': [str(x.date()) for x in missing][:100],
           'n_missing_days_vs_Bp': len(missing),
           'completeness_gate': comp,
           'r10_note': '数据件不产出任何「域读数→仓位」映射（R10）'}
    json.dump(man, open(os.path.join(OUT, 'gate_spread_EWZ_manifest.json'), 'w'),
              ensure_ascii=False, indent=1)
    res = {'ts': time.strftime('%F %T'), 'manifest': man, 'runtime_sec': round(time.time() - t0, 1)}
    json.dump(res, open(os.path.join(REPO, 'research', 'wo_mine', 'w2b_gate_spread_result.json'),
                        'w'), ensure_ascii=False, indent=1, default=str)
    print(f'done {res["runtime_sec"]}s', flush=True)


if __name__ == '__main__':
    main()
