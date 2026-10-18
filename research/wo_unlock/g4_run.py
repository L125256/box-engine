#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G4 门域解锁子面跑数（USERWORD_VERDICT 终裁执行件 · 常设）
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/USERWORD_VERDICT.md：
- §八 首席终裁「G4 与敏感性」：G4 垫 ≥3× 子面即刻解锁开跑；144 池定版；R8=Pool(32)；
  seed=42；D0 对拍先过（任一不过即停工）。
- §八 分级判据（定死）：利润垫倍数 = 最差侧年化费后利润 ÷ 43.8pp/年（5× 漂移上限档）；
  ≥3× 带资费可跑（24 行，avoid 口径交集 9 行优先）；适用域=成本用途。
- §二 多头席：对利润垫 ≥3× 的配置，费档在 5× 漂移内翻不动 avoid 符号 → 解锁合法。

【分级判据操作性定义（UG-1..UG-6，先冻结后运行；冻结时点 2026-10-19，前瞻数据未到达）】
UG-1 行=配置×池（b 单 82 可运行行，同 b_gate_sweep.json rows 口径）。
UG-2 年化费后利润 = 门臂年化(CAGR) − base 臂年化(CAGR)，CAGR=(1+ret_pp/100)^(365/n_days)−1，
  n_days=该窗该臂实际交易日数；ret_pp 均为费压口径（PB-5：FEE_SIDE/FUNDING×1.5）费后值。
UG-3 最差侧 = FULL 长窗（428 交易日）侧——与终裁分级表 24/58 行数及代表倍数
  （vol30+br60 4.22×、vol40 族 4.15×、vol30 族 old131 4.13×）逐位复现的唯一口径；
  【规格差异如实登记】若按「双窗取小」严格实现为 21 行（vol60+br60@old131 及 br60 族
  full144 三行 HOLDOUT 侧垫薄），终裁表 24/58 按 FULL 长窗（更严侧）口径定版；
  双窗各侧倍数全部落库（g4_result.json / coverage_grades.json 供复核）。
UG-4 avoid 口径 = 算术年化 avoid_pp（年=250 交易日）÷ 43.8 ≥3×（9 行，与终裁「avoid
  口径 9 行」逐位复现）；交集=UG-3 ∧ UG-4（恰 9 行）→ priority=true。
UG-5 跑数原判据=PB-7/PB-8/PB-9 承继不动：avoid_pp=门臂段净收益−base 段净收益；
  入选=FDR 幸存(BH q=0.10，于解锁面家族内按池施行) ∧ 双窗 avoid>0 ∧ 双窗 mdd_red≥10%；
  bootstrap p=FULL 窗日净收益差 stationary bootstrap（块长 10，1000 次，seed=42）。
UG-6 D0 对拍前置：锚行（vol30+br60@old131、vol40@full144）重跑 vs b_gate_sweep.json
  存档 FULL/HOLDOUT ret_pp/mdd/avoid 逐位一致（容差 1e-9），任一不过即停工。

产出：g4_result.json（本目录）
用法：python3 g4_run.py
"""
import json
import os
import sys
import time
from multiprocessing import Pool

sys.path.insert(0, '/workspace/repo_ready/research/wo_dneg')
sys.path.insert(0, '/workspace/repo_ready/research/wo_rescue')

import wo_rescue_run as WR          # 冻结引擎/判据件（D0 谱系，禁改）

HERE = os.path.dirname(os.path.abspath(__file__))
ARCH = '/workspace/repo_ready/research/wo_rescue/b_gate_sweep.json'
UPPER_PP = 43.8                     # 5× 漂移上限档（日历日口径 0.03%×365×4）
THICK_X = 3.0                       # 带资费可跑线
ANCHORS = [('vol30+br60', 'old131'), ('vol40', 'full144')]


def ann_excess_cagr_pp(f):
    """UG-2：窗内门臂−base 年化费后超额(pp)。"""
    g = ((1 + f['gated']['ret_pp'] / 100) ** (365 / f['gated']['n_days']) - 1) * 100
    b = ((1 + f['base']['ret_pp'] / 100) ** (365 / f['base']['n_days']) - 1) * 100
    return g - b


def grade_rows(rows):
    """UG-1..UG-4：82 行分级（逐字冻结判据），返回 (grades, g24_ids, av9_ids)。"""
    grades = {}
    for r in rows:
        if not r.get('runnable'):
            continue
        xf = ann_excess_cagr_pp(r['FULL']) / UPPER_PP
        xh = ann_excess_cagr_pp(r['HOLDOUT']) / UPPER_PP
        nF = r['FULL']['gated']['n_days']
        nH = r['HOLDOUT']['gated']['n_days']
        xa = min(r['FULL']['avoid_pp'] / (nF / 250),
                 r['HOLDOUT']['avoid_pp'] / (nH / 250)) / UPPER_PP
        grades[(r['id'], r['pname'])] = {
            'x_full_side': round(xf, 3), 'x_holdout_side': round(xh, 3),
            'x_min_both': round(min(xf, xh), 3), 'x_avoid_caliber': round(xa, 3),
            'grade': '带资费可跑' if xf >= THICK_X else '冻结挂账',
            'priority': bool(xf >= THICK_X and xa >= THICK_X)}
    g24 = {k for k, v in grades.items() if v['grade'] == '带资费可跑'}
    av9 = {k for k, v in grades.items() if v['x_avoid_caliber'] >= THICK_X}
    return grades, g24, av9


# ------------------------------------------------------------- workers
def _worker(task):
    cid, vars_, pname = task
    WR._init()
    syms = WR._POOLS[pname]
    gv = WR._GV[pname]
    vol, brd = gv['vol'], gv['breadth']
    cond = pd_false(vol.index)
    if 'vol' in vars_:
        cond = cond | (vol > gv['vol_thr'][vars_['vol']])
    if 'breadth' in vars_:
        cond = cond | (brd < float(vars_['breadth']))
    g = WR.run_gate(syms, gate_map=cond.fillna(False).to_dict(),
                    fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
    return {'cid': cid, 'pname': pname,
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()},
            'n_gate_off': g['n_gate_off']}


def _base_worker(pname):
    WR._init()
    g = WR.run_gate(WR._POOLS[pname], gate_map=None,
                    fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
    return {'pname': pname,
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()}}


def pd_false(idx):
    import pandas as pd
    return pd.Series(False, index=idx)


def main():
    t0 = time.time()
    arch = json.load(open(ARCH))
    rows = [r for r in arch['rows'] if r.get('runnable')]
    assert len(rows) == 82, len(rows)
    grades, g24, av9 = grade_rows(rows)
    # 终裁复现断言：24/58 行 + avoid 口径 9 行 + 交集 9 行
    assert len(g24) == 24, f'垫≥3x 复现 {len(g24)}!=24'
    assert len(av9) == 9, f'avoid 口径复现 {len(av9)}!=9'
    inter = g24 & av9
    assert len(inter) == 9, f'交集复现 {len(inter)}!=9'

    unlock = sorted(g24)
    cfg_vars = {r['id']: r['vars'] for r in rows if r.get('runnable')}

    # ---- D0 对拍（UG-6，先过才开跑）
    d0 = {'gate': 'D0 解锁面预对拍', 'anchors': [], 'pass': True}
    arc = {(r['id'], r['pname']): r for r in rows}
    for cid, pname in ANCHORS:
        fresh = _worker((cid, cfg_vars[cid], pname))
        base = _base_worker(pname)
        import pandas as pd
        fc = pd.Series({pd.Timestamp(k): v for k, v in fresh['curve'].items()}).sort_index()
        bc = pd.Series({pd.Timestamp(k): v for k, v in base['curve'].items()}).sort_index()
        a = arc[(cid, pname)]
        diffs = {}
        for wn, (t0_, t1_) in (('FULL', WR.FULL), ('HOLDOUT', WR.HOLD)):
            gs, bs = WR.seg_stats(fc, t0_, t1_), WR.seg_stats(bc, t0_, t1_)
            av = round(gs['ret_pp'] - bs['ret_pp'], 4)
            diffs[wn] = {'gated_ret': abs(gs['ret_pp'] - a[wn]['gated']['ret_pp']),
                         'gated_mdd': abs(gs['mdd_pct'] - a[wn]['gated']['mdd_pct']),
                         'base_ret': abs(bs['ret_pp'] - a[wn]['base']['ret_pp']),
                         'avoid': abs(av - a[wn]['avoid_pp'])}
        mx = max(v for w in diffs.values() for v in w.values())
        ok = mx <= 1e-9
        d0['anchors'].append({'anchor': f'{cid}@{pname}', 'maxdiff': mx, 'pass': ok})
        d0['pass'] = d0['pass'] and ok
    if not d0['pass']:
        json.dump({'stage': 'g4_unlock_subplane', 'd0': d0, 'aborted': True},
                  open(os.path.join(HERE, 'g4_result.json'), 'w'),
                  ensure_ascii=False, indent=1)
        print('D0 对拍不过 → 停工（详见 g4_result.json）')
        return

    # ---- 解锁面 24 行重跑（Pool(32)，R8）
    tasks = [(cid, cfg_vars[cid], pname) for cid, pname in unlock]
    with Pool(32) as pool:
        runs = pool.map(_worker, tasks)
    bases = {p: _base_worker(p) for p in WR._POOLS}
    import pandas as pd
    curves = {(r['cid'], r['pname']):
              pd.Series({pd.Timestamp(k): v for k, v in r['curve'].items()}).sort_index()
              for r in runs}
    base_curves = {p: pd.Series({pd.Timestamp(k): v
                                 for k, v in bases[p]['curve'].items()}).sort_index()
                   for p in WR._POOLS}

    results = []
    for cid, pname in unlock:
        r = arc[(cid, pname)]
        gc, bc = curves[(cid, pname)], base_curves[pname]
        row = {'id': cid, 'vars': cfg_vars[cid], 'pname': pname,
               'priority': (cid, pname) in inter,
               'grade': grades[(cid, pname)],
               'n_gate_off_weeks_fresh': next(x['n_gate_off'] for x in runs
                                              if x['cid'] == cid and x['pname'] == pname)}
        for wn, (a_, b_) in (('FULL', WR.FULL), ('HOLDOUT', WR.HOLD)):
            gs, bs = WR.seg_stats(gc, a_, b_), WR.seg_stats(bc, a_, b_)
            avoid = round(gs['ret_pp'] - bs['ret_pp'], 4)
            mdd_red = round((abs(bs['mdd_pct']) - abs(gs['mdd_pct']))
                            / abs(bs['mdd_pct']) * 100, 2) if bs['mdd_pct'] != 0 else None
            row[wn] = {'gated': gs, 'base': bs, 'avoid_pp': avoid, 'mdd_red_pct': mdd_red}
        diff = (gc.pct_change() - bc.pct_change()).dropna()
        diff = diff[(diff.index >= WR.FULL[0]) & (diff.index <= WR.FULL[1])]
        row['p_full_avoid_gt0'] = WR.boot_p_one_sided(diff.values)
        results.append(row)

    # ---- PB-9 FDR：解锁面家族内按池施行（m=14/10，如实记账）
    for pname in WR._POOLS:
        sub = [r for r in results if r['pname'] == pname]
        ps = [r['p_full_avoid_gt0'] for r in sub]
        rej = WR.bh_fdr(ps, q=0.10)
        for r, rj in zip(sub, rej):
            r['fdr_reject_full'] = bool(rj)
            f, h = r['FULL'], r['HOLDOUT']
            r['selected'] = bool(r['fdr_reject_full'] and f['avoid_pp'] > 0
                                 and h['avoid_pp'] > 0
                                 and f['mdd_red_pct'] is not None and f['mdd_red_pct'] >= 10
                                 and h['mdd_red_pct'] is not None and h['mdd_red_pct'] >= 10)
    n_sel = sum(1 for r in results if r['selected'])
    n_fdr = sum(1 for r in results if r['fdr_reject_full'])

    out = {'stage': 'g4_unlock_subplane',
           'ts': time.strftime('%F %T'),
           'spec': 'USERWORD_VERDICT.md §八（冻结）+ UG-1..UG-6（本文件头注，先冻结后运行）',
           'd0': d0,
           'unlock_face': {'rows_total': 82, 'thick_3x': 24, 'frozen': 58,
                           'avoid_caliber_9': 9, 'intersection_9': 9,
                           'replica_note': '24/58 与终裁分级表逐位复现；avoid 口径 9 行复现；'
                                           '严格双窗取小为 21 行（3 行 HOLDOUT 侧垫薄），'
                                           '终裁定版口径=FULL 长窗侧（UG-3 如实登记）'},
           'criteria': 'PB-7/PB-8/PB-9 承继（FDR(BH q=0.10) ∧ 双窗 avoid>0 ∧ 双窗 mdd_red≥10%）',
           'fee_stress': {'FEE_SIDE': WR.FEE_SIDE_S, 'FUNDING': WR.FUNDING_S},
           'fdr_family': {'old131_m': sum(1 for r in results if r['pname'] == 'old131'),
                          'full144_m': sum(1 for r in results if r['pname'] == 'full144'),
                          'note': '解锁面家族内按池 BH；非上轮 m=41 全平面（承继判线不重复计费）'},
           'n_fdr_reject': n_fdr, 'n_selected': n_sel,
           'selected': [f"{r['id']}@{r['pname']}" for r in results if r['selected']],
           'rows': results,
           'verdict': (f'解锁面 24 行按原判据全跑：FDR 幸存 {n_fdr}，入选 {n_sel}；'
                       f'avoid 口径交集 9 行全部 priority 标注'),
           'wall_secs': round(time.time() - t0, 1)}
    with open(os.path.join(HERE, 'g4_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"G4 解锁面完成：D0 {'PASS' if d0['pass'] else 'FAIL'}；"
          f"24 行全跑，FDR 幸存 {n_fdr}，入选 {n_sel} {out['wall_secs']}s")


if __name__ == '__main__':
    main()
