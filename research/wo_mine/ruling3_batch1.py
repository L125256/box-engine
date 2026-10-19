#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch 1 终裁三条件前置施工件（2026-10-20 终裁指令逐字执行，统计件修正不占重跑配额）
====================================================================================
条件① old131 域标签轴 B 阈值改「分母池内自算」：old131 自身 vol_med 在 MS_REALA
       (2025-06-01~2026-10-17) 的 P50 重切 old131 D1 标签（lag1），重出框架域格
       （K1 全部 old131 行；full144 不受影响仅作确定性对照——重跑 full144 数字须与
       batch1 已登记值逐位一致，证明重跑=纯复算非口径漂移）。
条件② D3 安慰剂统计量操作化口径冻结：四域效应极差（因子族=四域逐日 IC 均值极差；
       框架族=四域逐日超额(臂−base)均值极差；Q2 时序族(batch2)=变体统计量逐日值
       四域均值极差），MS_REALA 窗内置换 100 次 seed=42..141，
       P(安慰剂极差≥观测极差)>0.05 → MAP-INVALID。
条件③ 锚 vintage 双锚注记落盘：batch1 全部 21 项 vintage-miss 逐项登记
       「旧锚历史坐标（不改）+ 当前 vintage 复算基线（got）」双锚并行，禁挑一；
       复算基线以三组独立谱系逐位对拍为证（batch1_result.json lineage_check）。
R10 红线：本件不产出任何「域读数→仓位」映射。
产出：BATCH1_RULING_3COND.json / ruling3_rerun.json（重出域格行+逐格 p 值，供
      FDR m=86 合并表与 FACTBOOK old131 行替换用）
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mine_common as MC
import batch1_run as B1

OUT = MC.OUT_DIR
D1N = MC.D1_NAMES


def main():
    t0 = time.time()
    print('[1/6] 装载上下文 …', flush=True)
    c = B1.ctx()
    P_old = c['old131']
    print('[2/6] 条件①：old131 轴B 阈值=分母池内自算（MS_REALA vol_med P50）…', flush=True)
    vm = P_old['vol_med']
    own_p50 = float(vm[(vm.index >= MC.MS_REALA[0]) & (vm.index <= MC.MS_REALA[1])
                       ].dropna().quantile(0.5))
    vag_frozen = 0.4202424305853871                      # §0.3 冻结锚（full144 分母）
    print(f'      old131 own P50={own_p50!r}（full144 冻结锚={vag_frozen!r}）', flush=True)
    # 重切 old131 D1（轴A=old131 idx/MA50 不变；轴B=own P50；lag1 同 §2.4-2）
    trend = pd.Series(np.where(P_old['idx_ma'].isna(), None,
                      np.where(P_old['idx'] >= P_old['idx_ma'], '牛', '弱')), index=P_old['cal'])
    mood = pd.Series(np.where(P_old['vol_med'].isna(), None,
                     np.where(P_old['vol_med'] > own_p50, '躁', '稳')), index=P_old['cal'])
    d1_new = (trend + mood).shift(1)
    lab_new = {str(t.date()): (v if isinstance(v, str) else None) for t, v in d1_new.items()}
    mask = (P_old['cal'] >= MC.MS_REALA[0]) & (P_old['cal'] <= MC.MS_REALA[1])
    cnt_new = pd.Series(d1_new[mask]).value_counts().to_dict()
    lab_old = B1.pool_d1('old131')                       # 旧口径（共用冻结锚）作对照
    changed = sum(1 for k in lab_new if lab_new[k] != lab_old.get(k))
    print(f'      重切后 MS_REALA 域计数={cnt_new}；与旧口径标签逐日差异={changed} 天', flush=True)
    # 注入重切标签：full144 保持 domains.json 冻结标签不变
    dom = json.load(open(os.path.join(OUT, 'domains.json')))
    B1._D1 = {'full144': dom['labels']['d1'], 'old131': lab_new}

    print('[3/6] 条件①：框架域格重出（K1 三变体全量重放，32 进程）…', flush=True)
    rerun_rows, rerun_anchors, det = [], {}, {}
    for fn, nm in ((B1.run_downweight, 'downweight'), (B1.run_gate_vol, 'gate_vol'),
                   (B1.run_s3d1, 's3d1')):
        r, a, d = fn(win=None, n_proc=32)
        rerun_rows += r
        rerun_anchors[nm] = a
        det[nm] = d
        print(f'      {nm} done {d["wall_secs"]}s', flush=True)
    # full144 确定性对照：重跑锚值 vs batch1_result.json 已登记 got 逐位一致
    b1res = json.load(open(os.path.join(OUT, 'batch1_result.json')))
    dev, n_cmp = [], 0
    for nm, aa in rerun_anchors.items():
        for k, v in aa.items():
            g0 = b1res['anchors'].get(k)
            if g0 is None:
                continue
            n_cmp += 1
            x0, x1 = v[0], g0['got']
            if isinstance(x0, (list, tuple)):
                dev.extend(abs(a - b) for a, b in zip(x0, x1 if isinstance(x1, (list, tuple)) else [x1]))
            else:
                dev.append(abs(x0 - x1))
    maxdev = max(dev) if dev else None
    det_identical = bool(maxdev == 0.0)
    print(f'      full144 确定性对照：{n_cmp} 项锚值 maxdev={maxdev} → '
          f'{"逐位一致" if det_identical else "不一致（停工上报）"}', flush=True)
    if not det_identical:
        json.dump({'stop': True, 'maxdev': maxdev}, open(os.path.join(OUT, 'ruling3_rerun.json'), 'w'))
        sys.exit(3)
    # old131 行数核对：重出行与 FACTBOOK 已登记 old131 K1 行 variant_id 集合一致
    fb1 = [json.loads(l) for l in open(os.path.join(OUT, 'FACTBOOK_BATCH1.jsonl'))]
    old_ids = {r['variant_id'] for r in fb1 if r['pool'] == 'old131' and r['family'] == 'K1'}
    new_ids = {r['variant_id'] for r in rerun_rows if r['pool'] == 'old131'}
    assert old_ids == new_ids, f'variant_id 集合不一致: {old_ids ^ new_ids}'

    print('[4/6] 条件①：old131 安慰剂按重切标签重算（downweight 臂）…', flush=True)
    dd = B1.dom_dates('old131', B1.FULL)
    base_c = MC.simulate(c, 'old131')['curve']
    dw_c = MC.simulate(c, 'old131', slot_mult=0.5)['curve']
    plc_old131 = {'downweight': B1.placebo_framework(
        B1.daily_excess(dw_c, base_c), {d: dd[d] for d in D1N})}
    print(f"      p={plc_old131['downweight']['placebo_p']}", flush=True)

    print('[5/6] 条件③：锚 vintage 双锚注记（旧锚坐标+当前 vintage 复算基线并行）…', flush=True)
    misses = {k: v for k, v in b1res['anchors'].items() if v['verdict'] == 'MISS'}
    dual = []
    for k, v in sorted(misses.items()):
        dual.append({'anchor_key': k, 'old_anchor': v['want'],
                     'old_anchor_source': 'METHOD_BOOK_BATCH1 §一~§五 复现锚表（不改）',
                     'cur_vintage_baseline': v['got'],
                     'proof': '三组独立谱系逐位对拍（c4/c5=wo_rescue_run PC-4/PC-5 冻结代码'
                              '同数据只读复算；框架族=dneg_engine.run_instr 权威谱系），'
                              '见 batch1_result.json detail.*.lineage_check',
                     'verdict': '双锚并行登记，禁挑一；锚数字不改，引用时注明 vintage'})
    print(f'      vintage-miss 双锚登记 {len(dual)} 项', flush=True)

    print('[6/6] 落盘 …', flush=True)
    # 逐格 p 值（D1 格，供 FDR m=86 合并表）：框架族=域内日超额 boot p_one
    cells = []
    for r in rerun_rows:
        if r['axis'] != 'D1':
            continue
        p = r.get('_meta', {}).get('p_one')
        cells.append({'batch': 'batch1', 'variant_id': r['variant_id'], 'pool': r['pool'],
                      'domain': r['domain'], 'p': None if p is None else float(p),
                      'p_kind': 'boot_p_one_sided(域内日超额)',
                      'label_axisB': 'own_p50' if r['pool'] == 'old131' else 'frozen_anchor'})
    rows_pub = []
    for r in rerun_rows:
        r2 = {k: v for k, v in r.items() if k != '_meta'}
        if r2['pool'] == 'old131':
            r2['notes'] = (r2['notes'] +
                           ' 终裁条件①重切（轴B=old131 自身 MS_REALA P50，统计件修正不占重跑配额）').strip()
        rows_pub.append(r2)
    payload = {
        'spec': 'Batch 1 终裁三条件前置（2026-10-20 用户终裁指令，统计件修正不占重跑配额）',
        'ts': time.strftime('%F %T'),
        'cond1': {
            'rule': 'old131 域标签轴 B 阈值=分母池内自算：old131 自身 vol_med 在 '
                    'MS_REALA(2025-06-01~2026-10-17) 的 P50（MINE_SPEC §2.4 域锚窗）',
            'old131_own_vol_med_p50': own_p50,
            'full144_frozen_anchor_unchanged': vag_frozen,
            'old131_d1_counts_realA_recut': {k: int(v) for k, v in cnt_new.items()},
            'label_diff_days_vs_shared_anchor': int(changed),
            'full144_determinism_check': {'n_anchor_cmp': n_cmp, 'maxdev': maxdev,
                                          'identical': det_identical},
            'framework_rows_reissued': len([r for r in rows_pub if r['pool'] == 'old131']),
            'rerun_quota_note': '同切分重跑配额不受影响：本件为终裁统计件修正（域格重切重出），'
                                '复现锚与全窗数字未改判',
            'old131_placebo_downweight_recomputed': plc_old131['downweight'],
        },
        'cond2_d3_statistic_freeze': {
            'statistic': '四域效应极差（four-domain effect range）',
            'per_family': {
                'factor(Q1/Q3/Q4/Q5/Q6)': '四域逐日 IC 均值极差（MS_REALA 窗内）',
                'framework(K1~K5)': '四域逐日超额（臂−base）均值极差（MS_REALA 窗内）',
                'timeseries(Q2)': '变体时序统计量逐日值四域均值极差（MS_REALA 窗内）',
            },
            'placebo': 'D1 标签 MS_REALA 窗内逐日随机打乱 ×100（seed=42..141）；'
                       'P(安慰剂极差≥观测极差)>0.05 → MAP-INVALID（MINE_SPEC §2.3）',
            'status': 'FROZEN 2026-10-20 终裁，先于 Batch 2 任何运行',
        },
        'cond3_anchor_vintage_dual_registry': {
            'rule': '旧锚历史坐标（不改）+ 当前 vintage 复算基线（got）双锚并行，禁挑一',
            'n_miss_registered': len(dual),
            'items': dual,
        },
        'wall_secs': round(time.time() - t0, 1),
    }
    json.dump(payload, open(os.path.join(OUT, 'BATCH1_RULING_3COND.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    json.dump({'rows': rows_pub, 'fdr_cells': cells,
               'cond1': payload['cond1']},
              open(os.path.join(OUT, 'ruling3_rerun.json'), 'w'),
              ensure_ascii=False, indent=1, default=str)
    print(f'      BATCH1_RULING_3COND.json + ruling3_rerun.json 落盘'
          f'（重出行 {len(rows_pub)}，D1 格 p 值 {len(cells)}）', flush=True)
    print(f'done {payload["wall_secs"]}s', flush=True)


if __name__ == '__main__':
    main()
