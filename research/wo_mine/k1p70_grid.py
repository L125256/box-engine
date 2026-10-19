#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K1 换门 p70 深化网格（K1P70_SPEC_v1 照抄施工件 · 三档×双池 · 箱体换门工程读数）
================================================================================
【规格出处（冻结，禁改判据）】research/wo_mine/K1P70_SPEC_v1.md（2026-10-20 预注册
冻结，首席策略官·何执舟终裁批准）。
- 网格：p70/p75/p80 三档 × 双池（full144/old131）共 6 读数点，禁扩档（拒绝清单①）。
- 语义逐字承继：pause=停开新仓非清仓，复开按原规则；出场/复开三档逐字相同，
  只 diff 阈值一个参数（复用 K1 换门原实现=MC.simulate overlay pause，batch3 逐字同构）。
- 判线（§3 数字冻结，无中间态，只裁 p70 vs p80；p75 只算不裁）：
  ① 净差为正：A_p70−A_p80 > C_p70−C_p80（两边费后折钱，名义 100 万）；
  ② 双池同向：两池净差同为正（单池为正=登记不放行）；
  ③ 分年不翻脸：按自然年逐段算净差，任一年净差<0 即不通过；
  ④ p75 同法单独算（交换曲线完整性），不在本判线内。
  钱化口径：收益_A=Σ(触发段内基线回撤深度−该档回撤深度)×100 万（费后）；
  错过成本_C=Σ(OFF 段内基线上行收益−该档 OFF 段收益)×100 万（费后）。
- 费压口径承继 PB-5/PCX-A5（×1.5）：主判线用现行费率臂（与 FACTBOOK 锚同口径），
  ×1.5 费压臂伴行输出（_OPS 登记，承继 batch1/3 费压交叉先例）。
- 拒绝清单：禁扩网格/禁改出场/禁动 F1 部署（产出不改 f1/ 任何姿态）。
- 性质声明：本深化=箱体换门工程读数，非 F1 改造、非域胜任判定；p70 谱系
  MAP-INVALID（安慰剂不守恒）标记不适用于本工单判线，两标记并行不混写；
  产出不改部署姿态（R10）。
- R8=Pool(32)、seed=42、144 池定版；old131 按 ATLAS 替换 25 行口径（DE.build_pools）。
- D0 延续：gate70 臂重放 vs FACTBOOK_BATCH3 FULL 行、gate80 臂重放 vs
  FACTBOOK_BATCH1 FULL 行（±0.01，batch3 replay 同款），MISS 即停工。

【口径操作化·R7 登记·K1P70_SPEC 未逐字定义处提请终裁】
- _OPS1 触发段/OFF 段=该档门信号（vol20>thr，执行日读 shift(1)）连续为真段
  （episode），段边界裁剪至 FULL 窗 [2025-06-02, 2026-10-17]；段收益=段首前一
  交易日收盘净值→段末日收盘净值（费后，两臂同窗）。
- _OPS2 段回撤深度/段上行收益=段内净值净变化（费后）：基线段净变化<0 记 avoid 侧
  （A+=臂段−基线段），>0 记错过成本侧（C+=基线段−臂段）；折钱=pp×1 万元（100 万×1pp）。
- _OPS3 逐年归属=episode 段末日所在自然年；分年净差按池分别计算，任一池任一年<0
  即翻脸不通过（双池从严）。
- _OPS4 阈值锚：p80=domains.json anchors.gate_vol20_p80_by_pool（冻结）；
  p70=batch3_partial_K1.json detail.gate_p70_by_pool_frozen（2026-10-20 冻结，
  先落盘后回放）；p75=LN_REALA 谱系窗逐池 quantile(0.75) 本件先落盘后回放
  （同 batch3 p70 先例）。

用法：python3 research/wo_mine/k1p70_grid.py [--smoke]
产出：research/wo_mine/k1p70_result.json + research/wo_mine/k1p70_verdict.json
"""
import json
import os
import sys
import tarfile
import time
from multiprocessing import get_context

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

FULL = None          # 载入后取 B1.FULL
N_PROC = 32
SMOKE = False


def _cache_dir():
    """env 覆盖 > /tmp/box_cache（OD-R1 唯一数据态，锚复现实测）> .cache 解包。"""
    env = (os.environ.get('K1P70_BOX_CACHE') or os.environ.get('SHADOW_BOX_CACHE')
           or os.environ.get('FORWARD_BOX_CACHE'))
    if env:
        return env
    d = '/tmp/box_cache'
    if os.path.isdir(d) and os.listdir(d):
        return d
    d = os.path.join(ROOT, '.cache', 'box_cache')
    if not os.path.isdir(d) or not os.listdir(d):
        os.makedirs(d, exist_ok=True)
        with tarfile.open(os.path.join(ROOT, 'engine_snapshot',
                                       'box_cache_snapshot.tar.gz'), 'r:gz') as tf:
            tf.extractall(os.path.dirname(d))
    return d


_MC = None
_B1 = None


def _eng():
    global _MC, _B1
    import mine_common as MC
    import batch1_run as B1
    if _MC is None:
        MC.CACHE = _cache_dir()
        _MC, _B1 = MC, B1
    return _MC, _B1


# ------------------------------------------------------------- 臂（batch3 逐字同构，只 diff 阈值）
def _sim(spec):
    MC, B1 = _eng()
    p, thr, fee, fund = spec['pname'], spec['thr'], spec.get('fee'), spec.get('fund')
    P = MC.build_ctx()[p]
    cond = (P['vol20'] > thr).fillna(False)
    kw = {}
    if fee is not None:
        kw['fee'], kw['fund'] = fee, fund
    r = MC.simulate(MC.build_ctx(), p, lineage='gate',
                    overlay={'off': cond.shift(1).fillna(False), 'mode': 'pause'}, **kw) \
        if not spec.get('base') else \
        MC.simulate(MC.build_ctx(), p, lineage='gate', **kw)
    return r


def run_arms(specs):
    with get_context('fork').Pool(min(N_PROC, len(specs))) as pool:
        return pool.map(_sim, specs)


# ------------------------------------------------------------- 钱化（§3 冻结口径 + _OPS1/2）
def episode_money(arm_curve, base_curve, cond_exec, win, cal):
    """触发段逐段折钱。返回 (A_wan, C_wan, episodes 明细)。
    A=Σ(基线回撤深度−该档回撤深度)（基线段<0 时）；C=Σ(基线上行−该段收益)（基线段>0 时）；
    单位=万元（100 万名义×1pp）。"""
    import pandas as pd
    pos = {d: i for i, d in enumerate(cal)}
    s = cond_exec[(cond_exec.index >= win[0]) & (cond_exec.index <= win[1])]
    eps, cur = [], None
    for t, v in s.items():
        if bool(v):
            cur = [t, t] if cur is None else [cur[0], t]
        else:
            if cur is not None:
                eps.append(cur)
                cur = None
    if cur is not None:
        eps.append(cur)
    A, C, det = 0.0, 0.0, []
    for d0, d1 in eps:
        i0 = pos[d0] - 1                     # 段首前一交易日（_OPS1）
        if i0 < 0:
            continue
        t0 = cal[i0]

        def seg_ret(curve):
            seg = curve[(curve.index >= t0) & (curve.index <= d1)]
            return float(seg.iloc[-1] / seg.iloc[0] - 1) * 100 if len(seg) >= 2 else None
        rb, ra = seg_ret(base_curve), seg_ret(arm_curve)
        if rb is None or ra is None:
            continue
        delta = round(ra - rb, 4)            # pp，费后
        year = d1.year
        if rb < 0:
            A += delta
            det.append({'t0': str(t0.date()), 't1': str(d1.date()), 'year': year,
                        'side': 'avoid', 'base_ret_pp': round(rb, 4),
                        'arm_ret_pp': round(ra, 4), 'delta_pp': delta,
                        'money_wan': delta})
        elif rb > 0:
            c = round(rb - ra, 4)
            C += c
            det.append({'t0': str(t0.date()), 't1': str(d1.date()), 'year': year,
                        'side': 'cost', 'base_ret_pp': round(rb, 4),
                        'arm_ret_pp': round(ra, 4), 'delta_pp': delta,
                        'money_wan': round(-c, 4)})
    return round(A, 4), round(C, 4), det


# ------------------------------------------------------------- 主流程
def main():
    t0 = time.time()
    MC, B1 = _eng()
    global FULL
    FULL = B1.FULL
    ctx = MC.build_ctx()
    # ---- 阈值锚（_OPS4：先落盘后回放）----
    thr80 = json.load(open(os.path.join(_HERE, 'domains.json')))[
        'anchors']['gate_vol20_p80_by_pool']
    thr70 = json.load(open(os.path.join(_HERE, 'batch3_partial_K1.json'))
                      )['detail']['gate_p70_by_pool_frozen']
    thr70 = {k: float(v) for k, v in thr70.items()}
    thr75 = {p: float(ctx[p]['vol20'][(ctx[p]['vol20'].index >= MC.LN_REALA[0]) &
                                      (ctx[p]['vol20'].index <= MC.LN_REALA[1])].quantile(0.75))
             for p in ('old131', 'full144')}
    # ---- 臂（16：三档×双池×{现行费率, ×1.5 费压伴行} + base×2）----
    specs, keys = [], []
    for p in ('old131', 'full144'):
        specs.append({'pname': p, 'thr': thr80[p], 'base': True}); keys.append((p, 'base', 'fee0'))
        for tag, thr in (('g70', thr70[p]), ('g75', thr75[p]), ('g80', thr80[p])):
            specs.append({'pname': p, 'thr': thr}); keys.append((p, tag, 'fee0'))
        specs.append({'pname': p, 'thr': thr80[p], 'base': True,
                      'fee': B1.FEE_S, 'fund': B1.FUND_S}); keys.append((p, 'base', 'fee15'))
        for tag, thr in (('g70', thr70[p]), ('g75', thr75[p]), ('g80', thr80[p])):
            specs.append({'pname': p, 'thr': thr, 'fee': B1.FEE_S, 'fund': B1.FUND_S})
            keys.append((p, tag, 'fee15'))
    res = dict(zip(keys, run_arms(specs)))
    # ---- D0 重放（工单件⑥延续）：gate70 vs FB3 / gate80 vs FB1，±0.01 ----
    def replay(variant, ref_file, tag):
        ref = {r['pool']: r for r in (json.loads(l) for l in
                                      open(os.path.join(_HERE, ref_file)))
               if r['variant_id'] == variant and r['axis'] == 'FULL'}
        out = {}
        ok_all = True
        for p in ('old131', 'full144'):
            gs = B1.seg_stats(res[(p, tag, 'fee0')]['curve'], *FULL)
            bs = B1.seg_stats(res[(p, 'base', 'fee0')]['curve'], *FULL)
            a = round(gs['ret_pp'] - bs['ret_pp'], 4)
            mr = round((abs(bs['mdd_pct']) - abs(gs['mdd_pct']))
                       / abs(bs['mdd_pct']) * 100, 2)
            r = ref.get(p)
            ok = (r is not None and abs(a - r['avoid_pp']) <= 0.01
                  and abs(mr - r['mdd_red_pct']) <= 0.01)
            ok_all = ok_all and ok
            out[p] = {'replay_avoid': a, 'replay_mdd_red': mr,
                      'ref_avoid': None if r is None else r['avoid_pp'],
                      'ref_mdd_red': None if r is None else r['mdd_red_pct'],
                      'verdict': 'hit' if ok else 'MISS'}
        return {'name': f'replay_{variant}_vs_{ref_file}', 'pools': out,
                'verdict': 'hit' if ok_all else 'MISS'}
    d0 = {'ran_at': time.strftime('%F %T'),
          'checks': [replay('K1-d-gate-vol20p70-pause', 'FACTBOOK_BATCH3.jsonl', 'g70'),
                     replay('K1-d-gate-vol20p80-pause', 'FACTBOOK_BATCH1.jsonl', 'g80')]}
    d0['all_pass'] = all(c['verdict'] == 'hit' for c in d0['checks'])
    print(f"k1p70 D0: all_pass={d0['all_pass']}")
    if not d0['all_pass']:
        json.dump({'d0': d0}, open(os.path.join(_HERE, 'k1p70_result.json'), 'w'),
                  ensure_ascii=False, indent=1)
        raise SystemExit('k1p70 D0 重放校验 MISS——停工（batch 谱系停工条款，禁带病出数）')

    # ---- 四数表（每档：avoid/mdd_red/OFF 扩大量/费后折钱）----
    cal = {p: ctx[p]['cal'] for p in ('old131', 'full144')}
    grid, episodes = [], {}
    for p in ('old131', 'full144'):
        base_c = res[(p, 'base', 'fee0')]['curve']
        base_s = res[(p, 'base', 'fee15')]['curve']
        bs = B1.seg_stats(base_c, *FULL)
        n_off = {}
        for tag, thr, name in (('g70', thr70[p], 'p70'), ('g75', thr75[p], 'p75'),
                               ('g80', thr80[p], 'p80')):
            arm_c = res[(p, tag, 'fee0')]['curve']
            gs = B1.seg_stats(arm_c, *FULL)
            mdd_red = round((abs(bs['mdd_pct']) - abs(gs['mdd_pct']))
                            / abs(bs['mdd_pct']) * 100, 2)
            cond = (ctx[p]['vol20'] > thr).fillna(False).shift(1).fillna(False)
            A, C, det = episode_money(arm_c, base_c, cond, FULL, cal[p])
            n_off[name] = int(cond[(cond.index >= FULL[0]) & (cond.index <= FULL[1])].sum())
            episodes[f'{p}|{name}'] = det
            # ×1.5 费压伴行臂（同法）
            arm_s = res[(p, tag, 'fee15')]['curve']
            gs_s = B1.seg_stats(arm_s, *FULL)
            bs_s = B1.seg_stats(base_s, *FULL)
            mdd_red_s = round((abs(bs_s['mdd_pct']) - abs(gs_s['mdd_pct']))
                              / abs(bs_s['mdd_pct']) * 100, 2)
            A_s, C_s, _ = episode_money(arm_s, base_s, cond, FULL, cal[p])
            grid.append({'pool': p, 'tier': name, 'threshold': round(thr, 6),
                         'avoid_pp': round(gs['ret_pp'] - bs['ret_pp'], 4),
                         'mdd_red_pct': mdd_red,
                         'n_off_exec_days': n_off[name],
                         'A_wan': A, 'C_wan': C,
                         'net_vs_base_wan': round(A - C, 4),
                         'fee15': {'avoid_pp': round(gs_s['ret_pp'] - bs_s['ret_pp'], 4),
                                   'mdd_red_pct': mdd_red_s, 'A_wan': A_s, 'C_wan': C_s}})
    # OFF 扩大量（相对 p80，§2-③）
    for g in grid:
        p80 = next(x for x in grid if x['pool'] == g['pool'] and x['tier'] == 'p80')
        g['off_expand_vs_p80_days'] = g['n_off_exec_days'] - p80['n_off_exec_days']
    # ---- 判线（§3 四条，无中间态，只裁 p70 vs p80；p75 只算不裁）----
    def money_of(pool, tier):
        g = next(x for x in grid if x['pool'] == pool and x['tier'] == tier)
        return g['A_wan'], g['C_wan']
    yearly = {}
    for p in ('old131', 'full144'):
        det70 = episodes[f'{p}|p70']
        det80 = episodes[f'{p}|p80']
        years = sorted({e['year'] for e in det70} | {e['year'] for e in det80})
        for y in years:
            a70 = sum(e['money_wan'] for e in det70 if e['year'] == y and e['side'] == 'avoid')
            c70 = sum(-e['money_wan'] for e in det70 if e['year'] == y and e['side'] == 'cost')
            a80 = sum(e['money_wan'] for e in det80 if e['year'] == y and e['side'] == 'avoid')
            c80 = sum(-e['money_wan'] for e in det80 if e['year'] == y and e['side'] == 'cost')
            yearly.setdefault(y, {})[p] = {
                'A70_wan': round(a70, 4), 'C70_wan': round(c70, 4),
                'A80_wan': round(a80, 4), 'C80_wan': round(c80, 4),
                'net_70vs80_wan': round((a70 - a80) - (c70 - c80), 4)}
    nets = {}
    for p in ('old131', 'full144'):
        a70, c70 = money_of(p, 'p70')
        a80, c80 = money_of(p, 'p80')
        nets[p] = {'dA_wan': round(a70 - a80, 4), 'dC_wan': round(c70 - c80, 4),
                   'net_wan': round((a70 - a80) - (c70 - c80), 4)}
    cond1 = all(nets[p]['dA_wan'] > nets[p]['dC_wan'] for p in nets)
    cond2 = all(nets[p]['net_wan'] > 0 for p in nets)
    neg_years = {f'{y}|{p}': v['net_70vs80_wan'] for y, pv in yearly.items()
                 for p, v in pv.items() if v['net_70vs80_wan'] < 0}
    cond3 = not neg_years
    cond4_note = 'p75 同法已算（交换曲线完整性），本工单只裁 p70 vs p80（§3-4，只算不裁）'
    all_pass = bool(cond1 and cond2 and cond3)
    verdict = ('p70 优于 p80' if all_pass else 'p70 不优于 p80，维持 p80 锚')
    result = {
        'ts': time.strftime('%F %T'), 'spec': 'K1P70_SPEC_v1（2026-10-20 预注册冻结）',
        'runtime_sec': round(time.time() - t0, 1),
        'thresholds_frozen': {'p80_from_domains_anchors': thr80,
                              'p70_from_batch3_frozen': thr70,
                              'p75_computed_this_run_LN_REALA_q075': {k: round(v, 6)
                                                                      for k, v in thr75.items()},
                              'p75_freeze_note': '先落盘后回放（同 batch3 p70 先例）'},
        'd0': d0,
        'grid': grid, 'episodes': episodes,
        'episodes_note': '_OPS1/_OPS2：episode=执行日读门信号连续段（FULL 窗内）；'
                         '段收益=段首前一交易日收盘→段末日收盘（费后）；money 单位=万元'
                         '（名义 100 万×1pp）；episode 明细全量入册',
        'yearly_net': yearly,
    }
    verdict_json = {
        'ts': result['ts'], 'spec': result['spec'],
        'judgment_line': '§3 冻结：①净差为正 ΔA>ΔC ∧ ②双池同向 ∧ ③分年不翻脸；'
                         '④p75 只算不裁；无中间态',
        'money_caliber': '名义 100 万、费后、单位万元（_OPS2）；主判线=现行费率臂，'
                         '×1.5 费压臂伴行（grid[].fee15）',
        'p70_vs_p80': nets,
        'conditions': {'cond1_net_positive': bool(cond1),
                       'cond2_dual_pool_same_direction': bool(cond2),
                       'cond3_yearly_no_flip': bool(cond3),
                       'negative_years': neg_years,
                       'cond4_p75_computed_not_judged': cond4_note},
        'verdict': verdict,
        'verdict_nature': '无中间态（§3）；结果入册（负结果同权）；不触发任何 F1/部署改动'
                          '（拒绝清单③）；p70 谱系 MAP-INVALID 标记不混写（性质声明）',
        'sealed': True, 'sealed_at': result['ts'],
        'r10_note': '本深化产出不改部署姿态（R10）',
    }
    json.dump(result, open(os.path.join(_HERE, 'k1p70_result.json'), 'w'),
              ensure_ascii=False, indent=1)
    json.dump(verdict_json, open(os.path.join(_HERE, 'k1p70_verdict.json'), 'w'),
              ensure_ascii=False, indent=1)
    print(f"k1p70 verdict: {verdict}（净差万元："
          + ", ".join(f"{p}={nets[p]['net_wan']}" for p in nets) + "）")
    print(f"墙钟 {result['runtime_sec']}s；产出 k1p70_result.json / k1p70_verdict.json")


if __name__ == '__main__':
    main()
