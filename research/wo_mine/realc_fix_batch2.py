#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REALC 修复重落件（SHADOW_SPEC_v1 §5 随工单 · 登记级）
================================================================
缺陷：batch2_run.py Q1/Q3/Q4 三处 REALC 行误传全窗 ic（rc 已算未用，行号 396/458/529，
工单行号 518 系审计修正后漂移）；Q2 同型写法本来就正确（ts_full_row 传 rc）。
修复：batch2_run.py 三处改显式传 REALC 窗序列（默认值不动），价差列同步限窗。
本件：重跑三族（win=None, smoke=False 谱系参数），只取 axis=REALC 行，
合并替换 FACTBOOK_BATCH2.jsonl 对应 26 行（Q2 8 行本就正确，不动）。
用法：
  python3 realc_fix_batch2.py Q1|Q3|Q4    # 单族重跑 → realc_fix_<FAM>.json
  python3 realc_fix_batch2.py merge       # 三族合并替换 FACTBOOK_BATCH2 REALC 行
R8：三族并行跑（本件只承载单族，并行由调用方三进程实现）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch2_run as B2

FAMS = ('Q1', 'Q3', 'Q4')


def run_one(fam):
    runner = {'Q1': B2.run_q1, 'Q3': B2.run_q3, 'Q4': B2.run_q4}[fam]
    rows, cells, detail = runner(None, False)
    rc = [r for r in rows if r['axis'] == 'REALC']
    with open(os.path.join(B2.OUT, f'realc_fix_{fam}.json'), 'w') as f:
        json.dump(rc, f, ensure_ascii=False, indent=1)
    print(f'{fam}: REALC 行 {len(rc)} 条已落 realc_fix_{fam}.json')
    return rc


def merge():
    fixed = {}
    for fam in FAMS:
        for r in json.load(open(os.path.join(B2.OUT, f'realc_fix_{fam}.json'))):
            fixed[(r['family'], r['variant_id'])] = r
    path = os.path.join(B2.OUT, 'FACTBOOK_BATCH2.jsonl')
    rows = [json.loads(l) for l in open(path)]
    n_replaced, n_kept = 0, 0
    out = []
    for r in rows:
        if r['axis'] == 'REALC' and r.get('batch') == 'batch2' \
                and (r['family'], r['variant_id']) in fixed:
            out.append(fixed[(r['family'], r['variant_id'])])
            n_replaced += 1
        else:
            if r['axis'] == 'REALC':
                n_kept += 1
            out.append(r)
    assert n_replaced == 26, f'预期替换 26 行（Q1 8+Q3 10+Q4 8），实际 {n_replaced}'
    with open(path, 'w') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'merge: 替换 {n_replaced} 行，保留（Q2 等）{n_kept} 行，总行数 {len(out)}')


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == 'merge':
        merge()
    elif arg in FAMS:
        run_one(arg)
    else:
        print(__doc__)
        sys.exit(2)
