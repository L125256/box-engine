#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资费覆盖分级台账（USERWORD_VERDICT 终裁执行件 · 常设）
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/USERWORD_VERDICT.md：
- §八 分级判据（定死）：利润垫倍数=最差侧年化费后利润÷43.8pp/年（5× 漂移上限档）；
  ≥5× 全额免检 / ≥3× 带资费可跑 / <3× 冻结挂账；适用域=成本用途，信号用途除外；
- §八「G4 与敏感性」+ §七 判据重写清单第 4 条：影子序列兼作费率不确定性上界的标定源，
  ≥20 交易日后重算 43.8pp/年 上限并刷新分级表（三触发器之一）；
- §五 风险盘点：5×/43.8pp 是估计上限非保证上限；垫厚=样本内数字，前瞻打折另计。

【台账协议（CG-1..CG-6，先冻结后运行；冻结时点 2026-10-19）】
CG-1 台账=coverage_grades.jsonl（逐行 JSON，首行 _meta），供追加/重算；权威快照
  coverage_grades.json（meta+汇总+全行）。
CG-2 分级算法=g4_run.grade_rows 逐字复用（UG-1..UG-4；24/58/9 复现断言不过即停）。
CG-3 适用域表头写死：本表仅适用「成本用途」变体（b 单 82 可运行行）；168 个信号用途
  变体（fu/c1 族）不在适用域内，任何席位不得把利润垫外推到信号用途（§五-1 最重风险）。
CG-4 重标定触发器：影子基差序列≥20 交易日 → 重算费率漂移上限并全表重算。
  标定公式（方向性、保守、只升不降）：
    m̂ = clip( P95(|基差|)/median(|基差|), 1.0, 5.0 )（影子成本代理的分布漂移读数）
    上限' = 43.8 × m̂（pp/年，日历日口径）
  保守条款：m̂<1 一律取 1（影子禁反推费率数字 → 不允许下调上限；W1 终裁①）；
  标定值标 PROXY，真实费率数据（复活哨兵触发）方可替换为实测上限。
CG-5 每次重算均落库（全表覆盖+历史批次号保留在 _meta.recalc_history）。
CG-6 前瞻衰减折扣（登记不计算）：所有垫厚为样本内数字，realC 轨迹警示按「未来打折」
  解读，带资费可跑≠可部署，部署另走新预注册评审（§五-3）。

用法：
  python3 coverage_ledger.py build    # 建/重建台账（断言 24/58/9 复现）
  python3 coverage_ledger.py check    # 检查影子天数与重标定触发条件（常设日调项）
  python3 coverage_ledger.py recalc   # 触发重标定（仅影子≥20 交易日时生效）
"""
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/workspace/repo_ready/research/wo_dneg')
sys.path.insert(0, '/workspace/repo_ready/research/wo_rescue')

import wo_rescue_run as WR
from g4_run import grade_rows, UPPER_PP

HERE = os.path.dirname(os.path.abspath(__file__))
ARCH = '/workspace/repo_ready/research/wo_rescue/b_gate_sweep.json'
SHADOW_DIR = '/workspace/repo_ready/research/wo_w1/raw'
JL = os.path.join(HERE, 'coverage_grades.jsonl')
JS = os.path.join(HERE, 'coverage_grades.json')
DOMAIN_HEADER = ('适用域=成本用途变体（b 单 82 可运行行） ONLY；'
                 '168 个信号用途变体（fu/c1 族）不适用利润垫分级（USERWORD §五-1）')


def shadow_basis_series():
    out = {}
    for fn in sorted(glob.glob(os.path.join(SHADOW_DIR, 'shadow_cme_basis_raw_*.json'))):
        day = re.search(r'(\d{4}-\d{2}-\d{2})', fn).group(1)
        d = json.load(open(fn))
        try:
            hf, dy = d['hf_BTC_raw']['close'], d['BTCUSDT_dy']['close']
            out[day] = abs((hf - dy) / dy * 100)
        except (KeyError, TypeError):
            continue
    return out


def build_rows(upper_pp=UPPER_PP):
    """CG-2/CG-4：按当前上限重算 82 行分级。"""
    arch = json.load(open(ARCH))
    rows = [r for r in arch['rows'] if r.get('runnable')]
    grades, g24, av9 = grade_rows_with_upper(rows, upper_pp)
    out = []
    for r in rows:
        if not r.get('runnable'):
            continue
        g = grades[(r['id'], r['pname'])]
        out.append({'id': r['id'], 'vars': r['vars'], 'pname': r['pname'],
                    'grade': g['grade'], 'cushion_x_full_side': g['x_full_side'],
                    'cushion_x_holdout_side': g['x_holdout_side'],
                    'cushion_x_min_both': g['x_min_both'],
                    'cushion_x_avoid_caliber': g['x_avoid_caliber'],
                    'avoid_intersection_priority': g['priority'],
                    'full_avoid_pp': r['FULL']['avoid_pp'],
                    'holdout_avoid_pp': r['HOLDOUT']['avoid_pp'],
                    'disposition': ('带常数资费继续跑；G4 对应子面解锁；部署另走评审'
                                    if g['grade'] == '带资费可跑'
                                    else '维持挂账，等真实费率或影子标定后重算')})
    return out, g24, av9


def grade_rows_with_upper(rows, upper_pp):
    """g4_run.grade_rows 同构，但上限可参数化（重标定用）。"""
    import g4_run as G
    saved = G.UPPER_PP
    G.UPPER_PP = upper_pp
    try:
        return G.grade_rows(rows)
    finally:
        G.UPPER_PP = saved


def write_ledger(rows, meta):
    with open(JL, 'w') as f:
        f.write(json.dumps({'_meta': meta, 'domain': DOMAIN_HEADER},
                           ensure_ascii=False) + '\n')
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    grades_n = {'带资费可跑': sum(1 for r in rows if r['grade'] == '带资费可跑'),
                '冻结挂账': sum(1 for r in rows if r['grade'] == '冻结挂账')}
    snap = {**meta, 'domain': DOMAIN_HEADER, 'grade_counts': grades_n,
            'full_exempt_count': sum(1 for r in rows if r['cushion_x_full_side'] >= 5.0),
            'rows': rows}
    with open(JS, 'w') as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    return grades_n


def do_build():
    WR._init()
    rows, g24, av9 = build_rows()
    assert len(g24) == 24 and len(av9) == 9, (len(g24), len(av9))
    meta = {'ledger': '资费覆盖分级台账（USERWORD_VERDICT §八 定死判据）',
            'built_at': time.strftime('%F %T'),
            'fee_drift_upper_pp_per_year': UPPER_PP,
            'upper_basis': '常数 0.03%/bar×日历日年化 10.95pp×(5-1) 漂移档（估计上限非保证）',
            'batch': 'B0-初始', 'recalc_history': []}
    n = write_ledger(rows, meta)
    print(f"台账落库：82 行（免检 {snap_rows('full_exempt')}，带资费可跑 {n['带资费可跑']}，"
          f"冻结挂账 {n['冻结挂账']}）；avoid 口径交集 9 行 priority 标注")


def snap_rows(_=None):
    d = json.load(open(JS)) if os.path.exists(JS) else {'full_exempt_count': 0}
    return d['full_exempt_count']


def do_check():
    s = shadow_basis_series()
    n = len(s)
    status = 'TRIGGERED' if n >= 20 else 'WAITING'
    print(json.dumps({'shadow_days': n, 'required': 20, 'recalc': status,
                      'trigger_note': 'USERWORD §七-4：影子序列≥20 交易日重算 43.8pp/年 上限并刷新分级表'},
                     ensure_ascii=False))
    return n


def do_recalc():
    s = shadow_basis_series()
    n = len(s)
    if n < 20:
        print(f'影子序列 {n}/20 交易日，未达重标定门槛（CG-4）——不做任何改动')
        return
    import statistics
    vals = sorted(s.values())
    med = statistics.median(vals)
    p95 = vals[int(0.95 * (len(vals) - 1))]
    m_hat = min(5.0, max(1.0, (p95 / med) if med > 0 else 1.0))
    upper = round(UPPER_PP * m_hat, 2)
    WR._init()
    rows, g24, av9 = build_rows(upper_pp=upper)
    prev = json.load(open(JS)) if os.path.exists(JS) else {'batch': 'B0-初始',
                                                           'recalc_history': []}
    hist = prev.get('recalc_history', [])
    hist.append({'batch': prev.get('batch'), 'at': prev.get('built_at'),
                 'upper_pp': prev.get('fee_drift_upper_pp_per_year'),
                 'thick_rows': prev.get('grade_counts', {}).get('带资费可跑')})
    meta = {'ledger': '资费覆盖分级台账（USERWORD_VERDICT §八 定死判据）',
            'built_at': time.strftime('%F %T'),
            'fee_drift_upper_pp_per_year': upper,
            'upper_basis': (f'影子标定 PROXY：P95/median={p95:.3f}/{med:.3f} → m̂={m_hat:.3f}'
                            f'（clip[1,5]，只升不降，CG-4）；真实费率方可下调'),
            'batch': f'B{len(hist)}-影子标定', 'recalc_history': hist,
            'shadow_days': n}
    nc = write_ledger(rows, meta)
    print(f'重标定完成：上限 {UPPER_PP}→{upper} pp/年，全表重算 '
          f'（带资费可跑 {nc["带资费可跑"]} / 冻结挂账 {nc["冻结挂账"]}）')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'build'
    {'build': do_build, 'check': do_check, 'recalc': do_recalc}[cmd]()
