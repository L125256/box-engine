#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主轨精确切分件（DUAL_VERDICT §一-2 逐字 · 双轨制主轨即时判读）
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/DUAL_VERDICT.md：
- §〇 主轨=现有已记录数据即时判读，一切判读带「口径变更重判」标注，原判数字封印
  另立命名空间（*_orig，原数字不覆盖、不混写），重判数字一律写 dual_*；
- §一-2 替代切分（未进原判据，杜绝挑数字）：realC（2026-06-01→10-17，139 交易日）内切
  realC1（06-01→08-08）/ realC2（08-09→10-17）互验；判据=F6 判据①②逐字不放宽
  （①子段逐日 IC≥0 且 t≥2；②费后 fwd20 价差>0 且 ≥5 显著日）；单段过=「段态登记」，
  双段同向才算主轨重判结论，分歧=「态依赖/衰减」登记；同一切分最多重跑一次；
- §一-1 封印清单：F6 原数字（realC IC 0.0240/t=0.83、费后 fwd20 价差 0.7665pp/n_sig=8）、
  S3×D1 原数字（full144 p=0.023、old131 p=0.091）、B1 原数字（p=0.001/0.008 四件套）
  ——全部封印为 *_orig，引用必须带口径变更重判标注；
- §五-2 切分后验风险控制：切点=窗中点（08-08）一次性冻结；
- R8=Pool(32)；seed=42；144 池定版；FR-5 早判死线（t≤−2）承继核查。

【切分执行协议（DC-1..DC-7，先冻结后运行；冻结时点 2026-10-19，数据尾日 2026-10-17）】
DC-1 切分冻结：realC1=(2026-06-01, 2026-08-08)，realC2=(2026-08-09, 2026-10-17)；
  切点 08-08=窗中点，一次性冻结，禁改（防切分后验挑点）。
DC-2 F6 重判（A 臂域限定 PCX-B1 逐字：full144 × RS_momentum|fwd20 × F6|lo）：
  复用 wo_crossf6.f6_state 同尺（零漂移已回拍）与 state_stats 同构件，逐子段算
  ①lo 态日逐日截面 Spearman IC 均值≥0 且 t≥2；②lo 态信号日费后 fwd20 十分位价差>0
  且价差观测数≥5（SPREAD_MIN_N 承继）。FR-5 早判死线逐子段核查（t≤−2 且 IC<0）。
DC-3 S3×D1 重判（第一优先格 open_half_nosell×g2_ma，费压 PB-5 承继）：逐池逐子段
  avoid_pp=臂段净收益−base 段净收益；mdd_red=(|base MDD|−|臂 MDD|)/|base MDD|×100；
  lag=1 同切分重跑不翻转。子段过线=avoid>0 ∧ mdd_red≥10 ∧ lag 子段 avoid>0
  （三阈值逐字承继 PCX-A6/A7/A9，不放宽；FDR/realB 腿属 FULL 窗项不随切分重算，
  其原判数字封印不变）。
DC-4 B1 重判（PCX-B7 vol_hi∧F6|lo→S3 半额开门）：同 DC-3 口径逐池逐子段。
DC-5 结论规则：每件逐子段出「段态」（过/不过）；双段同向过=主轨重判结论「过」；
  双段同向不过=「不过」；一过一不过=互验分歧→「态依赖/衰减」登记——衰减态=
  不放行、不判死（FR-5 早判死线未触发时）。
DC-6 同一切分最多重跑一次（防 p-hacking 硬条款）：本件首次运行即用掉该配额 1 次，
  之后只能加新数据再判；配额状态落盘 dual_result.json.rerun_quota。
DC-7 标注纪律：本件全部数字均属「口径变更重判」，任何引用必须携带本标注；
  原判数字只从 *_orig 封印块读，禁止与 dual_* 混写。

挂接：判定轮日调搭车（DUAL_VERDICT §六：dual_readout 每日判定轮搭车，异常不阻断）。
用法：python3 dual_readout.py [--rerun]
产出：dual_result.json（主轨精确切分结果，机器可读）
"""
import json
import os
import sys
import time
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
for p in ('/workspace/repo_ready/research/wo_dneg',
          '/workspace/repo_ready/research/wo_rescue',
          '/workspace/repo_ready/research/wo_g1g2fdr',
          '/workspace/repo_ready/research/wo_crossf6'):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd

SEED = 42
OUT_F = os.path.join(_HERE, 'dual_result.json')

# DC-1 切分冻结（切点=窗中点 08-08 一次性冻结，禁改）
REALC = (pd.Timestamp('2026-06-01'), pd.Timestamp('2026-10-17'))
REALC1 = (pd.Timestamp('2026-06-01'), pd.Timestamp('2026-08-08'))
REALC2 = (pd.Timestamp('2026-08-09'), pd.Timestamp('2026-10-17'))
SEGMENTS = {'realC1': REALC1, 'realC2': REALC2}
DUAL_TAG = '口径变更重判'          # DC-7：本件全部数字的强制标注
RERUN_QUOTA_MAX = 1               # DC-6：同一切分最多重跑一次

# DC-3/DC-4 子段过线阈值（逐字承继，不放宽）
AVOID_GT = 0.0
MDD_RED_MIN = 10.0
FEE_RT_PP = 0.10                  # c4 费后价差谱系（双边 0.10pp，forward_readout 承继）


# ------------------------------------------------------------- F6 同构判读件
_F6C = None


def _f6_ctx():
    """wo_crossf6.f6_state 同尺 + RS/fwd20/信号日谱系件（PCX-B1 逐字域）。"""
    global _F6C
    if _F6C is not None:
        return _F6C
    import wo_rescue_run as WR
    import wo_g1g2fdr_run as WG
    import wo_crossf6_run as XF
    WR._init()
    st = XF.f6_state()
    C, lo = st['C'], st['lo']
    names = st['names']
    old131 = WR._POOLS['old131']
    new13 = sorted(set(names) - set(old131))
    ret20 = C / C.shift(20) - 1
    idx_old = ret20[old131].mean(axis=1)
    idx_new = ret20[new13].mean(axis=1)
    rs_cross = pd.DataFrame(index=C.index, columns=names, dtype=float)
    for s in names:
        rs_cross[s] = ret20[s] - (idx_new if s in old131 else idx_old)   # PC-4 逐字
    fwd20 = C.shift(-20) / C - 1
    sigs = WG._sig_days(C.index)
    _F6C = {'st': st, 'rs_cross': rs_cross, 'fwd20': fwd20, 'sigs': sigs}
    return _F6C


def f6_state_stats(a, b):
    """wo_crossf6.state_stats 同构（lo 态域限定逐字），限定子段 [a,b]。"""
    import wo_rescue_run as WR
    import wo_g1g2fdr_run as WG
    ctx = _f6_ctx()
    C, lo = ctx['st']['C'], ctx['st']['lo']
    sigs = ctx['sigs']
    days = C.index[(C.index >= a) & (C.index <= b) & lo.values]
    ic = WR._xsec_ic_series(ctx['rs_cross'].loc[days], ctx['fwd20'].loc[days])
    t_, n_ic = WR._tstat(ic)
    sw = sigs[(sigs >= a) & (sigs <= b)]
    sw = sw[sw.map(lambda d: bool(lo.at[d]))]
    if len(sw) >= WG.SPREAD_MIN_N:
        _, net, ns = WR._decile_spread_fee(ctx['rs_cross'].loc[sw], ctx['fwd20'].loc[sw])
    else:
        net, ns = None, None
    return {'n_days': int(len(days)),
            'ic_mean': round(float(ic.mean()), 6) if len(ic) else None,
            't_stat': round(t_, 4) if t_ is not None else None, 'n_ic_days': n_ic,
            'fwd20_decile_pp_net': (round(net, 4) if net is not None else None), 'n_sig': ns}


def f6_dual():
    """DC-2：F6 判据①②逐字不放宽，realC1/realC2 互验重判。"""
    rows = {}
    for sn, (a, b) in SEGMENTS.items():
        s = f6_state_stats(a, b)
        c1 = bool(s['ic_mean'] is not None and s['ic_mean'] >= 0
                  and s['t_stat'] is not None and s['t_stat'] >= 2)
        c2_insufficient = bool(s['n_sig'] is None)   # 价差观测 <5，②不可判（非判死）
        c2 = bool(s['fwd20_decile_pp_net'] is not None and s['fwd20_decile_pp_net'] > 0
                  and s['n_sig'] is not None and s['n_sig'] >= 5)
        early_death = bool(s['ic_mean'] is not None and s['ic_mean'] < 0
                           and s['t_stat'] is not None and s['t_stat'] <= -2)   # FR-5 承继
        if early_death:
            seg_state = '早判死命中'
        elif c1 and c2:
            seg_state = '过'
        elif c2_insufficient:
            seg_state = '样本不足（②价差观测<5 不可判；①读数另注）'
        else:
            seg_state = '不过'
        rows[sn] = {**s, 'dual_clause1_ic_ge0_t_ge2': c1,
                    'dual_clause2_insufficient_n_sig_lt5': c2_insufficient,
                    'dual_clause2_spread_gt0_sig5': c2,
                    'dual_fr5_early_death_hit': early_death,
                    'dual_segment_state': seg_state}
    p1, p2 = rows['realC1'], rows['realC2']
    if p1['dual_segment_state'] == '过' and p2['dual_segment_state'] == '过':
        verdict, note = '双段同向过（主轨重判结论=过）', '双段同向才算主轨结论——达成'
    elif p1['dual_segment_state'] == '早判死命中' or p2['dual_segment_state'] == '早判死命中':
        verdict, note = '早判死命中（判死线触发）', 'FR-5 承继：t≤−2 且 IC<0 → 判死上报'
    elif p1['dual_segment_state'] == '不过' and p2['dual_segment_state'] == '不过':
        verdict, note = '双段同向不过（主轨重判结论=不过）', '双段同向（两段判据①②均完整判出不过）'
    else:
        verdict, note = '互验分歧（衰减态：不放行、不判死）', \
            '前段与后段态不一致或后段错向——单段过/不可判仅段态登记，' \
            '双段同向才算主轨结论；FR-5 早判死线未触发 → 衰减态登记'
    return {'definition': 'DC-2：F6 判据①②逐字不放宽，realC 内切 realC1/realC2 互验'
                          '（A 臂域 PCX-B1 逐字：full144 × RS_momentum|fwd20 × F6|lo）',
            'annotation': DUAL_TAG, 'segments': rows, 'dual_verdict': verdict, 'note': note}


# ------------------------------------------------------------- 门臂回测 worker
def _worker(task):
    import wo_rescue_run as WR
    import wo_g1g2fdr_run as WG
    import wo_crossf6_run as XF
    WR._init()
    pname, arm, lag = task
    syms = WR._POOLS[pname]
    fee, fund = WR.FEE_SIDE_S, WR.FUNDING_S          # PB-5 费压承继（主判口径）
    if arm == 'base':
        g = XF.run_gate_x(syms, gate_map=None, off_mode='v2_full_stop',
                          off_mode_map=None, fee=fee, fund=fund)
    elif arm == 's3xd1':
        gmap = WG.gate_maps(pname, lag)['g2_ma'].to_dict()
        g = WG.run_gate_g(syms, gate_map=gmap, off_mode='open_half_nosell',
                          fee=fee, fund=fund)
    elif arm == 'B1':
        gmap = WG.gate_maps(pname, lag)['v2'].to_dict()   # 门信号=纯 vol_hi（PCX-B7）
        omm = XF.b_off_mode_map('B1_lo_open_half')
        g = XF.run_gate_x(syms, gate_map=gmap, off_mode='v2_full_stop',
                          off_mode_map=omm, fee=fee, fund=fund)
    else:
        raise ValueError(arm)
    return {'pname': pname, 'arm': arm, 'lag': lag, 'n_gate_off': g['n_gate_off'],
            'curve': {str(k.date()): float(v) for k, v in g['curve'].items()}}


def _tcurve(curve_d):
    """日期字符串键 → DatetimeIndex 曲线（seg_stats 需 Timestamp 比较）。"""
    return pd.Series({pd.Timestamp(k): v for k, v in curve_d.items()}).sort_index()


def _seg_metrics(arm_curve, base_curve, a, b):
    """DC-3：子段 avoid/mdd_red/lag 子段三腿（PCX-A6/A7 阈值逐字）。"""
    import wo_rescue_run as WR
    am = WR.seg_stats(arm_curve, a, b)
    bm = WR.seg_stats(base_curve, a, b)
    if am is None or bm is None:
        return None
    avoid = round(am['ret_pp'] - bm['ret_pp'], 4)
    mdd_red = (round((abs(bm['mdd_pct']) - abs(am['mdd_pct']))
                     / abs(bm['mdd_pct']) * 100, 2) if bm['mdd_pct'] != 0 else None)
    return {'dual_seg_arm': am, 'dual_seg_base': bm, 'dual_avoid_pp': avoid,
            'dual_mdd_red_pct': mdd_red,
            'dual_pass_segment': bool(avoid > AVOID_GT and mdd_red is not None
                                      and mdd_red >= MDD_RED_MIN)}


def gate_dual(runs):
    """DC-3/DC-4：S3×D1 与 B1 的 realC1/realC2 互验重判。"""
    out = {}
    for arm_name, label, seal in (
            ('s3xd1', 'S3×D1 第一优先格（open_half_nosell×g2_ma）',
             '原判封印 *_orig：full144 p=0.023 / old131 p=0.091（合并族 m=14 BH，FULL 窗）'),
            ('B1', 'B1_lo_open_half（vol_hi∧F6|lo→S3 半额开门）',
             '原判封印 *_orig：p=0.001(full144)/0.008(old131) 四件套（FDR∧双窗 avoid>0'
             '∧双窗 mdd_red≥10∧lag 不翻转）')):
        pools = {}
        for pname in ('old131', 'full144'):
            arm0 = runs[(pname, arm_name, 0)]
            arm1 = runs[(pname, arm_name, 1)]
            base = runs[(pname, 'base', 0)]
            ac0 = _tcurve(arm0['curve'])
            ac1 = _tcurve(arm1['curve'])
            bc = _tcurve(base['curve'])
            segs = {}
            for sn, (a, b) in SEGMENTS.items():
                m = _seg_metrics(ac0, bc, a, b)
                lm = _seg_metrics(ac1, bc, a, b)
                m['dual_lag1_avoid_pp'] = lm['dual_avoid_pp'] if lm else None
                m['dual_pass_segment'] = bool(
                    m['dual_pass_segment']
                    and m['dual_lag1_avoid_pp'] is not None
                    and m['dual_lag1_avoid_pp'] > AVOID_GT)       # lag 不翻转逐字
                segs[sn] = m
            s1, s2 = segs['realC1'], segs['realC2']
            if s1['dual_pass_segment'] and s2['dual_pass_segment']:
                v, note = '双段同向过（主轨重判结论=过）', '双段同向'
            elif not s1['dual_pass_segment'] and not s2['dual_pass_segment']:
                v, note = '双段同向不过（主轨重判结论=不过）', '双段同向'
            else:
                v, note = '互验分歧（态依赖/衰减登记）', '一过一不过——单段过仅段态登记'
            pools[pname] = {'segments': segs, 'dual_verdict': v, 'note': note,
                            'n_gate_off_full': runs[(pname, arm_name, 0)]['n_gate_off'],
                            'n_gate_off_full_lag1': runs[(pname, arm_name, 1)]['n_gate_off'],
                            'orig_sealed': seal}
        out[arm_name] = {'definition': f'DC-3/DC-4：{label}，realC1/realC2 互验重判'
                                       f'（avoid>0 ∧ mdd_red≥10 ∧ lag 子段不翻转，逐字不放宽；'
                                       f'FDR/realB 腿属 FULL 窗项不随切分重算，原判封印）',
                         'annotation': DUAL_TAG, 'pools': pools}
    return out


# ------------------------------------------------------------- 封印块（*_orig，只读存档）
def seal_orig():
    """DC-7：原判数字封印登记（从已落定存档原样拷贝，不覆盖不混写）。"""
    f6 = json.load(open('/workspace/repo_ready/research/wo_crossf6/f6_result.json'))
    a = f6['A_arm_deep_verify']['criteria']
    monthly = f6['A_arm_deep_verify']['realC_monthly_rolling_ic_registered']
    b1o = f6['B_arm_s3xf6']['cells']['B1_lo_open_half']['pools']
    s3_orig = {}
    for p in ('old131', 'full144'):
        s3_orig[p] = {'p_full_avoid_gt0':
                      f6['fdr_merged']['pvals'][f'{p}|open_half_nosell__x__g2_ma'],
                      'fdr_reject_full': f6['fdr_merged']['reject'][
                          f'{p}|open_half_nosell__x__g2_ma']}
    return {
        'rule': 'DUAL_VERDICT §一-1 封印清单：原数字不覆盖、不混写，引用必须带'
                '「口径变更重判」标注（引用不带标注视为违规——DUAL_VERDICT §五-1）',
        'F6_realC_orig': {'ic_mean': a['c1']['ic_mean_realC'], 't_stat': a['c1']['t_realC'],
                          'fwd20_decile_pp_net': a['c2']['realC_spread_pp'],
                          'n_sig': a['c2']['n_sig'],
                          'monthly_rolling_registered': monthly,
                          'note': 'F6 原判数字封印（CROSSF6 f6_result.json 原样）'},
        'S3xD1_orig': {'pools': s3_orig,
                       'note': 'S3×D1 原判数字封印（full144 p=0.023 / old131 p=0.091）'},
        'B1_orig': {'pools': {p: {'p_full_avoid_gt0': b1o[p]['p_full_avoid_gt0'],
                                  'fdr_reject_full': b1o[p]['fdr_reject_full'],
                                  'FULL_avoid_pp': b1o[p]['FULL']['avoid_pp'],
                                  'HOLDOUT_avoid_pp': b1o[p]['HOLDOUT']['avoid_pp']}
                              for p in ('old131', 'full144')},
                    'note': 'B1 原判数字封印（四件套，PCX-B8）'},
    }


# ------------------------------------------------------------- 主流程
def main():
    t0 = time.time()
    state = {'rerun_used': 0}
    if os.path.exists(OUT_F):
        prev = json.load(open(OUT_F))
        state['rerun_used'] = int(prev.get('rerun_quota', {}).get('used', 0))
    if '--rerun' in sys.argv:
        if state['rerun_used'] >= RERUN_QUOTA_MAX:
            print('DC-6：同一切分重跑配额已用尽（最多 1 次）——只能加新数据再判，退出')
            return
        state['rerun_used'] += 1
    used_now = state['rerun_used']

    tasks = [(p, 'base', 0) for p in ('old131', 'full144')] \
        + [(p, 's3xd1', lag) for p in ('old131', 'full144') for lag in (0, 1)] \
        + [(p, 'B1', lag) for p in ('old131', 'full144') for lag in (0, 1)]
    with Pool(32) as pool:
        raw = pool.map(_worker, tasks)
    runs = {(r['pname'], r['arm'], r['lag']): r for r in raw}

    f6 = f6_dual()
    gates = gate_dual(runs)

    # 主轨总读数（三件合议；F6 为主轨即时判读主件，门域两件并读）
    v_f6 = f6['dual_verdict']
    main_read = {'F6': v_f6,
                 'S3xD1': {p: gates['s3xd1']['pools'][p]['dual_verdict']
                           for p in ('old131', 'full144')},
                 'B1': {p: gates['B1']['pools'][p]['dual_verdict']
                        for p in ('old131', 'full144')}}
    if '衰减' in v_f6:
        overall = '衰减态——不放行、不判死（主轨行动依据=维持空仓观望与门域监测不变）'
    elif '早判死' in v_f6:
        overall = '早判死命中——判死上报（FR-5 承继）'
    elif '同向过' in v_f6:
        overall = '主轨重判结论=过——转部署评审待办（须新预注册，前瞻段新数字）'
    else:
        overall = '主轨重判结论=不过'

    # 段天数登记
    import wo_rescue_run as WR
    cal = pd.DatetimeIndex(sorted(set().union(
        *[set(r['curve']) for r in [runs[('full144', 'base', 0)]]])))
    seg_days = {sn: int(WR.seg_stats(_tcurve(runs[('full144', 'base', 0)]['curve']),
                                     a, b)['n_days'])
                for sn, (a, b) in SEGMENTS.items()}

    result = {
        'stage': 'dual_precise_split_readout（DUAL_VERDICT §一-2 主轨精确切分件）',
        'frozen_at': '2026-10-19',
        'annotation': DUAL_TAG + '（本文件除 *_orig 封印块外全部数字均属口径变更重判，'
                                '引用必须携带本标注）',
        'split': {'realC': [str(REALC[0].date()), str(REALC[1].date())],
                  'realC1': [str(REALC1[0].date()), str(REALC1[1].date())],
                  'realC2': [str(REALC2[0].date()), str(REALC2[1].date())],
                  'cut_rule': '切点=窗中点（08-08）一次性冻结（DUAL_VERDICT §五-2）',
                  'seg_trading_days': seg_days,
                  'seg_days_note': 'realC 池日历 139 交易日；realC1+realC2=139（08-08 归前段）'},
        'rerun_quota': {'max': RERUN_QUOTA_MAX, 'used': used_now,
                        'rule': 'DC-6：同一切分最多重跑一次，之后只能加新数据再判'},
        'dual_f6': f6,
        'dual_s3xd1': gates['s3xd1'],
        'dual_B1': gates['B1'],
        'main_track_read': main_read,
        'overall': overall,
        'conflict_rule': '两轨结论冲突时：辅轨为最终确认、主轨为当下行动依据'
                         '（DUAL_VERDICT §〇）',
        'aux_track_pointer': 'forward_readout.py n≥20 前瞻管线照挂（不删不停）；'
                             '并排日报见 daily_track_compare.jsonl（dual_daily.py）',
        'seal_orig': seal_orig(),
        'wall_secs': round(time.time() - t0, 1),
        'ts': time.strftime('%F %T'),
    }
    with open(OUT_F, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f'dual_readout 完成：F6={v_f6} | S3xD1={main_read["S3xD1"]} | '
          f'B1={main_read["B1"]}')
    print(f'主轨总读数：{overall}')
    print(f'重跑配额：{used_now}/{RERUN_QUOTA_MAX}；wall={result["wall_secs"]}s')


if __name__ == '__main__':
    main()
