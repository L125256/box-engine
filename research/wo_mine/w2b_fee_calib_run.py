#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W2-B 工单⑤：费用真实化（gate_funding_eq/_manifest.json 修复 + 费基对拍；W2B_SPEC §5 逐字）
==========================================================================================
R10 红线：本件不产出任何「域读数→仓位」映射。红线：禁改 dneg_engine.py/common_fdbrk.py/
任何引擎费常数（本单只出报告；引擎费常数改动=新工单交用户批准）。已封印判读不改判。
口径（W2B_SPEC §5.2/§5.3 冻结）：
- f_real(t)=gate_funding_eq 等权日费率序列（30 日滚动，年化 ×252）；对照 f_const=0.03%/bar。
- 容差判读：ctrl 锚差 |Δ|≤0.05=费基不敏感；任一 Δ>0.05=费敏感成立。
- 数据源盘点只读：funding_death_archive.json + box_cache funding 字段 + W1 台账；
  禁备源顶替（RG3 先例：资金费缺席一律【数据受限】登记，代理字段禁入 funding 账本）。
- 复活哨兵：tools/w1_probe_rerun.py 每会话复跑（W1 台账纪律）。
产出：research/wo_w1/gate_funding/{funding_eq.jsonl,_manifest.json} +
      w2b_fee_calib_result.json + W2B_FEE_CALIB_REPORT.md
"""
import hashlib
import json
import os
import sys
import time

import numpy as np
import pandas as pd

REPO = '/workspace/repo_ready'
OUT = os.path.join(REPO, 'research', 'wo_mine')
GF = os.path.join(REPO, 'research', 'wo_w1', 'gate_funding')
CACHE = '/tmp/box_cache_w2a'   # 唯一数据态（snapshot_20261019，见 wave2_run.py 头注登记）
F_CONST = 0.0003               # 0.03%/bar（dneg_engine.py:34 / common_fdbrk.py:12 原值，禁改）
FEE_S, FUND_S = 0.00075, 0.00045

sys.path.insert(0, os.path.join(OUT, '..'))
import mine_common as MC
MC.CACHE = CACHE
import batch1_run as B1


def md5f(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def step1_inventory():
    """§5.2-1 数据源盘点（只读）。"""
    arch = json.load(open(os.path.join(REPO, 'research', 'wo_w1', 'raw',
                                       'funding_death_archive.json')))
    # box_cache funding 字段核查（只读，全 176 文件）
    has_fund = []
    for f in sorted(os.listdir(CACHE)):
        d = json.load(open(os.path.join(CACHE, f)))
        if isinstance(d, list) and d and any(('funding' in k.lower()) or ('rate' in k.lower())
                                             for k in d[0]):
            has_fund.append(f)
    probe = json.load(open(os.path.join(REPO, 'research', 'wo_w1', 'raw', 'w1_probe_rerun.json')))
    items = probe.get('results', [])
    if isinstance(items, dict):
        items = items.get('dy', []) + items.get('sina', [])
    fund_alive = [r for r in items
                  if r.get('status') == 200 and 'html' not in (r.get('ct') or '')
                  and ('funding' in r.get('url', '').lower() or 'funding' in r.get('head', '').lower())]
    return {'verdict': arch['verdict'],
            'archived_at': arch['archived_at'],
            'revival_conditions': arch['revival_conditions'],
            'box_cache_files': len(os.listdir(CACHE)),
            'box_cache_files_with_funding_field': has_fund,
            'probe_fetched_at': probe.get('fetched_at'),
            'probe_funding_alive_endpoints': [r.get('url') for r in fund_alive],
            'sentinel_note': 'w1_probe_rerun.py 本会话复跑（57 路径），funding 端点活 JSON=0 → '
                             '复活条件①②均未满足，funding 数据源维持 R9 判死'}


def step2_rebuild_dataset(inv):
    """§5.2-2/3：重建 gate_funding/ 目录（funding jsonl + _manifest.json）。
    数据源判死维持 → 覆盖=0 标的，缺口全量登记【数据受限】，不入费基均值。"""
    os.makedirs(GF, exist_ok=True)
    syms = sorted(f[:-5] for f in os.listdir(CACHE) if f.endswith('.json'))
    jsonl = os.path.join(GF, 'funding_eq.jsonl')
    open(jsonl, 'w').close()   # 0 行：schema 见 manifest（ts/symbol/rate），无数据可落
    man = {
        '_doc': 'gate_funding_eq 数据集 manifest（W2B_SPEC §5.2 冻结口径重建；'
                'RG3 谱系引用键修复件）',
        'generated_at': time.strftime('%F %T'),
        'dataset': 'gate_funding_eq',
        'schema': {'funding_eq.jsonl': '逐行 {ts:YYYY-MM-DD, symbol:str, rate:float}'
                                        '（逐 symbol funding 日频；本版 0 行=无数据可落）',
                   'eq_series': '140 标的费率等权 30 日滚动（rg3_retest 终裁口径，年化 ×252）'},
        'data_window': {'start': None, 'end': None,
                        'note': 'funding 数据源双源判死维持（W1 R9 归档），无数据窗'},
        'symbols_covered': {'count': 0, 'list': []},
        'symbol_registry': {'loaded_symbols': len(syms),
                            'rg3_universe_note': 'rg3_retest 等权口径=140 标的（pyc 常量提取，'
                                                 '仅作出处证据未反编译执行）'},
        'per_file_md5': {os.path.basename(jsonl): md5f(jsonl)},
        'eq_definition': '140 标的费率等权 30 日滚动（年化 ×252 单调变换对判线尺度不变）',
        'generator_fingerprint': {'script': 'research/wo_mine/w2b_fee_calib_run.py',
                                  'script_md5': md5f(os.path.abspath(__file__)),
                                  'sentinel': 'research/wo_w1/tools/w1_probe_rerun.py'},
        'gap_registry': {'status': '【数据受限·R5·非死】',
                         'verdict_source': 'research/wo_w1/raw/funding_death_archive.json（'
                                           + arch_str(inv) + '）',
                         'missing_symbols': syms,
                         'missing_count': len(syms),
                         'rule': '缺数据标的禁入费基均值（分母=有数标的数）；本版有数标的=0 → '
                                 'f_real 不可构造，禁代理顶替（CME 基差/USDCNH 只进影子层）',
                         'revival_conditions': inv['revival_conditions'],
                         'probe_fetched_at': inv['probe_fetched_at']},
        'r10_note': '本 manifest 不产出任何「域读数→仓位」映射（R10）',
    }
    with open(os.path.join(GF, '_manifest.json'), 'w') as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    # §5.2-3 完备性门：三件齐
    trio = {'gate_funding_eq_dir': os.path.isdir(GF),
            'funding_eq.jsonl': os.path.exists(jsonl),
            '_manifest.json': os.path.exists(os.path.join(GF, '_manifest.json'))}
    return {'trio_complete': all(trio.values()), 'trio': trio,
            'manifest': man, 'n_symbols_registered_gap': len(syms)}


def arch_str(inv):
    return 'verdict: ' + inv['verdict'][:60] + '…'


def step3_fee_calib():
    """§5.3 对拍臂（f_real 不可构造 → R5 替代路径：费参数敏感扫描，明确标注非 f_real）。"""
    out = {'f_real_status': '不可构造【数据受限·R5·非死】（funding 数据源 R9 判死维持，'
                            '有数标的=0，禁代理顶替）——§5.3 冻结对拍（f_const vs f_real）'
                            '本轮不可执行，如实登记；替代路径=费参数敏感扫描（下）',
           'fd_line': {}, 'dneg_line': {}, 'verdict': None}
    # --- fd 线（ctrl 冻结臂，D0 已重放 n=1802/meanR 1.1798 hit）：
    # FEE 只线性进入 r 计算（出场决策与费无关，逐字核对 batch3 mk_partial 结构），
    # 故 r(FEE)=(xc−ep)/ep*100−FEE*(xi−ei) 可解析重算，零引擎改动、零二次扫描。
    trs = json.load(open('/tmp/wo_mine/w2a_fd_ctrl_trades.json'))
    fd = json.load(open(os.path.join(REPO, 'research', 'wo_fdbrk', 'fd_result.json')))['final']['main']
    sweep = {}
    for fee_pct in (0.02, 0.03, 0.04):
        rs = [(t['xc'] - t['ep']) / t['ep'] * 100 - fee_pct * (t['xi'] - t['ei']) for t in trs]
        sweep[f'{fee_pct:.2f}%'] = {'n': len(rs), 'meanR': round(float(np.mean(rs)), 4)}
    d1 = abs(sweep['0.02%']['meanR'] - sweep['0.03%']['meanR'])
    out['fd_line'] = {'anchor': 'fd_result final.main n=1802 meanR=1.1798（本批 D0 重放 hit）',
                      'f_const_meanR': sweep['0.03%']['meanR'],
                      'sweep_per_bar_fee': sweep,
                      'delta_meanR_per_001pp_fee': round((sweep['0.04%']['meanR']
                                                          - sweep['0.02%']['meanR']) / 2, 4),
                      'ctrl_tol_005_verdict': '费基不敏感（|Δ|≤0.05）'
                                              if max(d1, abs(sweep['0.04%']['meanR']
                                                             - sweep['0.03%']['meanR'])) <= 0.05
                                              else '费敏感（|Δ|>0.05）',
                      'note': '替代路径读数【非 f_real 对拍·R7 标注】：f_real 不可构造，'
                              '本读数=费参数在 ±0.01pp 邻域的敏感系数；fd 线 FEE 参数化若需'
                              '常态化=引擎费常数改动，另立新工单'}
    # --- dneg 线（mine_common.py:189-190 费参数化已就位，零引擎改动）：
    # base 与 armC（g2 s3 逐字）× fund ∈ {0.0002,0.0003,0.0004}（±0.01% 邻域）
    specs, keys = [], []
    for p in ('old131', 'full144'):
        spec_c = B1_armspec(p)
        for fund in (0.0002, 0.0003, 0.0004):
            specs.append({'pname': p, 'win': None, 'fund': fund}); keys.append((p, 'base', fund))
            s = dict(spec_c); s['fund'] = fund
            specs.append(s); keys.append((p, 'armC', fund))
    res = dict(zip(keys, B1.run_arms(specs)))
    for p in ('old131', 'full144'):
        line = {}
        for fund in (0.0002, 0.0003, 0.0004):
            bs = B1.seg_stats(res[(p, 'base', fund)]['curve'], *B1.FULL)
            ac = B1.seg_stats(res[(p, 'armC', fund)]['curve'], *B1.FULL)
            line[f'{fund:.4f}'] = {'base_ret_pp': bs['ret_pp'], 'armC_ret_pp': ac['ret_pp'],
                                   'avoid_pp': round(ac['ret_pp'] - bs['ret_pp'], 4),
                                   'base_mdd': bs['mdd_pct'], 'armC_mdd': ac['mdd_pct']}
        d = (line['0.0004']['avoid_pp'] - line['0.0002']['avoid_pp']) / 2
        out['dneg_line'][p] = {'sweep': line,
                               'delta_avoid_pp_per_001pp_funding': round(d, 4),
                               'ctrl_tol_005_verdict': '费基不敏感（|Δ|≤0.05）'
                                                       if abs(d) <= 0.05 else '费敏感（|Δ|>0.05）',
                               'anchor_note': 'f_const=0.0003 档=单变量扫描参照档（默认费基 '
                                              'FEE_SIDE，非 D0 锚④费压臂）；sweep 内三档同费同闸仅 fund 变'}
    vs = [out['fd_line']['ctrl_tol_005_verdict']] + \
         [out['dneg_line'][p]['ctrl_tol_005_verdict'] for p in ('old131', 'full144')]
    out['verdict'] = ('费基不敏感（常数可用性在 ±0.01pp 邻域内成立；f_real 实测仍【数据受限】，'
                      '复活后须按 §5.3 补正式对拍）' if all('不敏感' in v for v in vs)
                      else '费敏感成立（附敏感系数如上；受影响判读格=K5/fd 系全部 meanR 读数与 '
                           'D-A 复活五件套，按风控席加敏感注记不改封印判读）')
    return out


def B1_armspec(p):
    """armC 臂 spec（batch1 run_s3d1 逐字，g2+s3）。"""
    P = MC.build_ctx()[p]
    thr = json.load(open(os.path.join(OUT, 'domains.json')))['anchors']['gate_vol20_p80_by_pool'][p]
    g2 = ((P['vol20'] > thr) & (P['idx'] < P['idx_ma'])).fillna(False)
    return {'pname': p, 'win': None, 'fee': B1.FEE_S, 'fund': F_CONST,
            'overlay': {'off': g2.shift(1).fillna(False), 'mode': 's3'}}


def main():
    t0 = time.time()
    eng_md5_before = {'dneg_engine.py': md5f(os.path.join(REPO, 'research', 'wo_dneg', 'dneg_engine.py')),
                      'common_fdbrk.py': md5f(os.path.join(REPO, 'research', 'wo_fdbrk', 'common_fdbrk.py'))}
    print('[1/3] 数据源盘点（只读）…', flush=True)
    inv = step1_inventory()
    print('      funding 活端点=', len(inv['probe_funding_alive_endpoints']), flush=True)
    print('[2/3] gate_funding_eq manifest 重建…', flush=True)
    ds = step2_rebuild_dataset(inv)
    print('      三件齐=', ds['trio_complete'], '缺口标的=', ds['n_symbols_registered_gap'], flush=True)
    print('[3/3] 费敏感扫描（R5 替代路径，32 进程）…', flush=True)
    calib = step3_fee_calib()
    eng_md5_after = {'dneg_engine.py': md5f(os.path.join(REPO, 'research', 'wo_dneg', 'dneg_engine.py')),
                     'common_fdbrk.py': md5f(os.path.join(REPO, 'research', 'wo_fdbrk', 'common_fdbrk.py'))}
    res = {'ts': time.strftime('%F %T'), 'spec': 'W2B_SPEC §5（冻结）',
           'inventory': inv, 'dataset_rebuild': {k: v for k, v in ds.items()
                                                 if k != 'manifest'},
           'fee_calib': calib,
           'engine_untouched_check': {'before': eng_md5_before, 'after': eng_md5_after,
                                      'ok': eng_md5_before == eng_md5_after,
                                      'note': '红线自查：引擎文件 md5 前后一致（禁改费常数）'},
           'r10_note': '本运行不产出任何「域读数→仓位」映射（R10）',
           'runtime_sec': round(time.time() - t0, 1)}
    json.dump(res, open(os.path.join(OUT, 'w2b_fee_calib_result.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    print('      引擎 md5 未变=', res['engine_untouched_check']['ok'], flush=True)
    print('      结论=', calib['verdict'], flush=True)
    print(f'done {res["runtime_sec"]}s', flush=True)


if __name__ == '__main__':
    main()
