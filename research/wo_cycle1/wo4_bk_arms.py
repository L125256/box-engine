#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WO4 bk 腿修复 D3 三臂（冻结规格 v1.0 · 一次成活 · seed=42）
前置硬门槛 R5-0：top1_ref 复跑与 authoritative_baseline.json + d3_rerun.json
三方逐位一致（full n=2415 / main n=1440 / main median=0.2405）——不过整单打回。
权威口径：Top1=N15/k7.5/m2/e0.3；V2 可实现出场；池=144；fd 腿禁动；闸仅进 bk 信号侧。
三臂（不扩围）：a) 拦 volr<0.5；b) 拦 volr<0.65；c) 带通 [0.5,0.8)（拦 <0.5 与 ≥0.8）。
引擎复用：import /tmp/eng_wt_rc/eng_final.py（atrs/load_pool/build_idx_bull/collect/stats/
yearly/FEE 逐字复用）；闸实现与反事实出场逐字复制 /tmp/r4_1/eng_r41.py（cf_exit 与
eng_final 出场分支逐字一致），仅将固定阈值 0.8 参数化为冻结三臂判据。
判据 J1-J6 为预注册冻结，逐项判定；单臂独立判定（允许单臂过单臂归档）。
样本内边界选定属打折范畴，强制标注【推断】。
复现：python3 wo4_bk_arms.py
"""
import json
import os
import sys
import datetime
import statistics

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, '/tmp/eng_wt_rc')
import eng_final as EF

SEED = 42
rng = np.random.default_rng(SEED)
np.random.seed(SEED)

FEE = EF.FEE
MAIN = '2025-06-01'
X, Q, AMAX = 0.75, 30, 60
TOP1 = dict(N=15, k=7.5, m=2, e=0.3)
OUT = '/workspace/repo_ready/research/wo_cycle1'

ARMS = {
    'a': dict(label='volr<0.5 单边', blocked=lambda v: v < 0.5),
    'b': dict(label='volr<0.65 单边', blocked=lambda v: v < 0.65),
    'c': dict(label='[0.5,0.8) 带通（拦 <0.5 与 >=0.8）',
              blocked=lambda v: (v < 0.5) or (v >= 0.8)),
}


# ------------------------------------------------ 闸引擎（eng_r41.scan_r41 逐字，阈值参数化）
def scan_gate(bars, idx_above_ma, blocked_fn):
    """与 eng_final.scan 状态机逐字一致；bk 触发日按 blocked_fn(volr) 拦截：
    被拦则不进 bk、箱体保持 live 不标 fired、fd 不受影响（eng_r41 逐字语义）。"""
    N = TOP1['N']
    a = EF.atrs(bars)
    state = 'seek'; streak = 0; box = None; pos = None; trades = []
    stat = dict(defer=0, gap_stop=0, gap_tp=0, hardcap=0, gated_volm=0)
    gated = []; bkevents = []
    for i in range(max(N, 14) + 1, len(bars)):
        if a[i] is None:
            continue
        px = bars[i]['close']
        if pos:
            hold = i - pos['ei']
            if px <= pos['eff'] or px >= pos['tp'] or hold >= Q:
                if px >= pos['tp']:
                    xpx = max(pos['tp'], bars[i]['open'])
                    if bars[i]['open'] >= pos['tp']: stat['gap_tp'] += 1
                elif px <= pos['eff']:
                    xpx = min(pos['eff'], bars[i]['open'])
                    if bars[i]['open'] <= pos['eff']: stat['gap_stop'] += 1
                else:
                    xpx = px; stat['hardcap'] += 1
                j = i
                while j < len(bars) - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                    j += 1; xpx = bars[j]['open']; stat['defer'] += 1
                r = (xpx - pos['ep']) / pos['ep'] * 100 - FEE * (j - pos['ei'])
                trades.append(dict(ep=pos['ep'], ei=pos['ei'], xi=j, xc=round(xpx, 4),
                                   kind=pos['kind'], r=r,
                                   why='止盈' if px >= pos['tp'] else ('止损' if px <= pos['eff'] else '30天期满')))
                pos = None
            continue
        if state == 'seek':
            w = bars[i - N + 1:i + 1]
            Hh = max(x['high'] for x in w); Ll = min(x['low'] for x in w); rng_ = Hh - Ll
            if rng_ > 0 and rng_ < TOP1['k'] * a[i]: streak += 1
            else: streak = 0
            if streak >= TOP1['m']: state = 'locked'; box = [Ll, Hh, i, '']; streak = 0
            continue
        L, H, li, fired = box; rng_ = H - L; age = i - li
        sig = None
        if 'L' not in fired and px > H + 0.25 * a[i]:   # B=0.25 冻结口径
            pv = bars[i - N:i]
            vmean = sum(x['volume'] for x in pv) / len(pv) if pv else 0
            volr = (bars[i]['volume'] / vmean) if vmean > 0 else 0.0
            ok = not blocked_fn(volr)
            if not ok:
                stat['gated_volm'] += 1
            if ok:
                sig = ('bk', px)
            bkevents.append(dict(i=i, t=bars[i]['time'], px=px, volr=round(volr, 4),
                                 gated=not ok, L=L, H=H, atr=a[i]))
            if not ok:
                gated.append(dict(i=i, t=bars[i]['time'], px=px, volr=round(volr, 4),
                                  L=L, H=H, atr=a[i]))
        elif ('L' not in fired and idx_above_ma.get(bars[i]['time'])
              and bars[i]['low'] <= L + TOP1['e'] * rng_):
            sig = ('fd', px)
        if sig is None and (px > H + X * a[i] or px < L - X * a[i] or age > AMAX):
            state = 'seek'; box = None; continue
        if sig:
            kind, ep = sig; box[3] += 'L'
            tp = H + a[i] if kind == 'bk' else H
            disp = ep - 1.5 * a[i] if kind == 'bk' else L
            eff = disp - 0.3 * a[i]
            risk = (ep - disp) / ep * 100
            if eff > 0 and risk <= 8.0:
                pos = dict(ep=ep, tp=tp, disp=disp, eff=eff, ei=i, kind=kind)
    return dict(trades=trades, stat=stat, gated=gated, bkevents=bkevents)


# ------------------------------------------------ 反事实出场（eng_r41.cf_exit 逐字）
def cf_exit(bars, i, ep, tp, disp):
    eff = disp - 0.3 * ((ep - disp) / 1.5)
    if eff <= 0:
        return None
    risk = (ep - disp) / ep * 100
    if risk > 8.0:
        return None
    for j in range(i + 1, len(bars)):
        px = bars[j]['close']; hold = j - i
        if px <= eff or px >= tp or hold >= Q:
            if px >= tp: xpx = max(tp, bars[j]['open'])
            elif px <= eff: xpx = min(eff, bars[j]['open'])
            else: xpx = px
            k = j
            while k < len(bars) - 1 and not (bars[k]['low'] <= xpx <= bars[k]['high']):
                k += 1; xpx = bars[k]['open']
            return dict(xi=k, xt=bars[k]['time'], xc=round(xpx, 4),
                        r=(xpx - ep) / ep * 100 - FEE * (k - i),
                        why='止盈' if px >= tp else ('止损' if px <= eff else '30天期满'),
                        open=False)
    return dict(xi=None, xt=None, xc=None, r=None, why='数据末尾未出场', open=True)


def run_arm(pool, bull, blocked_fn):
    N = TOP1['N']
    trades = []; agg = dict(defer=0, gap_stop=0, gap_tp=0, hardcap=0, gated_volm=0)
    gated_all = []
    for tkr, bars in pool.items():
        res = scan_gate(bars, bull, blocked_fn)
        for t in res['trades']:
            trades.append(dict(tkr=tkr, **t, et=bars[t['ei']]['time'], xt=bars[t['xi']]['time']))
        for k in agg:
            agg[k] += res['stat'][k]
        for g in res['gated']:
            cf = cf_exit(bars, g['i'], g['px'], g['H'] + g['atr'], g['px'] - 1.5 * g['atr'])
            gated_all.append(dict(tkr=tkr, et=g['t'], px=g['px'], volr=g['volr'], cf=cf))
    return (sorted(trades, key=lambda t: (t['xi'], t['tkr'])), agg,
            sorted(gated_all, key=lambda g: g['et']))


def ev_stats(evs):
    """被拦事件统计：只计 tradeable（构成交易）且已出场（非 open）的 cf。"""
    ok = [e for e in evs if e['cf'] and not e['cf']['open']]
    op = [e for e in evs if e['cf'] and e['cf']['open']]
    ff = [e for e in evs if e['cf'] is None]
    rs = [e['cf']['r'] for e in ok]
    if not rs:
        return dict(n=len(evs), tradeable=0, open=len(op), filter_fail=len(ff),
                    mean=None, median=None, win_pct=None, sum_r=0.0)
    wins = [r for r in rs if r > 0]
    return dict(n=len(evs), tradeable=len(rs), open=len(op), filter_fail=len(ff),
                mean=round(sum(rs) / len(rs), 4),
                median=round(statistics.median(rs), 4),
                win_pct=round(len(wins) / len(rs) * 100, 2),
                sum_r=round(sum(rs), 2))


def ev_yearly(evs):
    out = {}
    for y in ('2024', '2025', '2026'):
        out[y] = ev_stats([e for e in evs if e['et'][:4] == y])
    return out


def ev_bucket(evs, lo, hi):
    return ev_stats([e for e in evs if lo <= e['volr'] < hi])


def bootstrap_improve_ci(rs, n=1000, seed=42):
    """J6：笔块重采样（有放回），拦截收益改善 = -cf_r，95% CI。"""
    r2 = np.random.default_rng(seed)
    if not rs:
        return dict(n=0, ci95_low=None, ci95_high=None, pass_=False)
    arr = np.array([-r for r in rs])
    means = []
    for _ in range(n):
        pick = r2.integers(0, len(arr), len(arr))
        means.append(float(arr[pick].mean()))
    lo, hi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    return dict(n=len(rs), n_boot=n, seed=seed,
                mean_improve_r=round(float(arr.mean()), 4),
                ci95_low=round(lo, 4), ci95_high=round(hi, 4),
                pass_=bool(lo > 0))


def main():
    os.makedirs(OUT, exist_ok=True)
    pool144, dropped = EF.load_pool('/tmp/box_cache')
    assert len(pool144) == 144, f'池={len(pool144)} != 144'
    bull = EF.build_idx_bull(pool144)

    # ---------- 前置硬门槛 R5-0：top1_ref 三方对账 ----------
    trs_ref, agg_ref = EF.collect(dict(N=15, k=7.5, m=2, e=0.3), pool144, bull, v1=False)
    st_full, st_main = EF.stats(trs_ref), EF.stats([t for t in trs_ref if t['et'] >= MAIN])

    auth = json.load(open('/tmp/eng_wt_rc/authoritative_baseline.json'))
    d3 = json.load(open('/tmp/r4_1/d3_rerun.json'))
    at = auth['runs']['top1']; dt = d3['runs']['full144|top1_ref']

    recon = {}
    recon['vs_auth_full'] = all(st_full[k] == at['full'][k]
                                for k in ('n', 'median', 'mean', 'win_pct', 'sum_r'))
    recon['vs_auth_main'] = all(st_main[k] == at['main'][k]
                                for k in ('n', 'median', 'mean', 'win_pct', 'sum_r'))
    recon['vs_auth_exit'] = {k: agg_ref[k] == at['exit_stat'][k] for k in agg_ref}
    recon['vs_auth_trades'] = (
        [(t['tkr'], t['et'], t['ei'], t['xi'], t['xc'], t['kind'], round(t['r'], 10))
         for t in trs_ref] ==
        [(t['tkr'], t['et'], t['ei'], t['xi'], t['xc'], t['kind'], round(t['r'], 10))
         for t in at['trades']])
    recon['vs_d3_full'] = all(st_full[k] == dt['full'][k]
                              for k in ('n', 'median', 'mean', 'win_pct', 'sum_r'))
    recon['vs_d3_main'] = all(st_main[k] == dt['main'][k]
                              for k in ('n', 'median', 'mean', 'win_pct', 'sum_r'))
    recon['hard_numbers'] = dict(full_n=st_full['n'], main_n=st_main['n'],
                                 main_median=st_main['median'])
    recon['target'] = dict(full_n=2415, main_n=1440, main_median=0.2405)
    recon['pass'] = bool(all([recon['vs_auth_full'], recon['vs_auth_main'],
                              all(recon['vs_auth_exit'].values()), recon['vs_auth_trades'],
                              recon['vs_d3_full'], recon['vs_d3_main']]))
    print('R5-0 三方对账:', json.dumps(recon, ensure_ascii=False))
    if not recon['pass']:
        # 漂移诊断（如实登记，不编数据）：逐笔 diff 定位差异来源
        k_new = {(t['tkr'], t['et'], t['kind']): round(t['r'], 6) for t in trs_ref}
        k_old = {(t['tkr'], t['et'], t['kind']): round(t['r'], 6)
                 for t in at['trades']}
        only_new = {f'{k[0]}|{k[1]}|{k[2]}': v for k, v in k_new.items() if k not in k_old}
        only_old = {f'{k[0]}|{k[1]}|{k[2]}': v for k, v in k_old.items() if k not in k_new}
        diff_r = {f'{k[0]}|{k[1]}|{k[2]}': (k_old[k], k_new[k])
                  for k in k_new if k in k_old and k_old[k] != k_new[k]}
        cache_d = json.load(open('/tmp/box_cache/AAOIUSDT.json'))
        if isinstance(cache_d, dict):
            cache_d = cache_d.get('bars_d', cache_d)
        diagnosis = dict(
            root_cause='数据缓存滚动漂移（非代码差异）：box_cache 为滚动 700 根缓存，'
                       '当前 mtime=2026-10-18 09:54 UTC（首根 2024-03-04/末根 2026-10-18），'
                       '而权威基线生成于 2026-10-17 03:26 UTC、d3_rerun 于 05:46 UTC，'
                       '对账所需的同时点缓存快照（滚动窗起点 2024-01-24）已被刷新覆盖，'
                       '头部 bar（2024-01-24~03-03）本地不可恢复；2026-09/10 bar 亦有修订。',
            cache_now=dict(first_bar=cache_d[0]['time'], last_bar=cache_d[-1]['time'],
                           n_bars=len(cache_d)),
            main_window_diff=dict(
                n_diff=st_main['n'] - at['main']['n'],
                new_main_trades={k: v for k, v in only_new.items() if k.split('|')[1] >= MAIN}),
            full_window_diff=dict(n_new=len(only_new), n_lost=len(only_old),
                                  r_revised=len(diff_r),
                                  new_trades=only_new, lost_trades=only_old,
                                  revised_r=diff_r),
            code_lineage='eng_final.py 逐字复用未改（与 R4 复审「当前磁盘代码 bit-exact 复现权威基线」'
                         '时点同一代码；差异全部可归因于数据漂移）')
        out = dict(generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
                   workorder='WO4 bk 腿 D3 三臂', reconciliation=recon,
                   drift_diagnosis=diagnosis,
                   hard_gate='FAIL——R5-0 三方对账不过，整单打回（冻结规格前置条款：不过就停，未跑三臂）',
                   revival_condition='提供 2026-10-17 03:26 UTC 时点缓存快照或重新冻结缓存并'
                                     '重生成权威基线后，按本规格全套重跑（禁用任何重构/插值数据）')
        with open(os.path.join(OUT, 'wo4_result.json'), 'w') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print('HARD GATE FAIL -> 整单打回，未跑三臂')
        return

    base_yearly_main = EF.yearly([t for t in trs_ref if t['et'] >= MAIN])
    base_yearly_full = EF.yearly(trs_ref)

    # ---------- 三臂（完整引擎重跑，计路径效应） ----------
    arms_out = {}
    for aid, adef in ARMS.items():
        trs, agg, gated = run_arm(pool144, bull, adef['blocked'])
        stf = EF.stats(trs)
        stm = EF.stats([t for t in trs if t['et'] >= MAIN])
        ym = EF.yearly([t for t in trs if t['et'] >= MAIN])
        yf = EF.yearly(trs)
        bl = ev_stats(gated)
        bl_y = ev_yearly(gated)
        bl_thick = ev_bucket(gated, 0.65, 0.8)
        rs = [e['cf']['r'] for e in gated if e['cf'] and not e['cf']['open']]
        j6 = bootstrap_improve_ci(rs, 1000, SEED)

        j1 = bool(stm['median'] is not None and st_main['median'] is not None
                  and stm['median'] >= st_main['median'])
        j2_delta = round((ym['2026']['mean'] or 0) - (base_yearly_main['2026']['mean'] or 0), 4)
        j2 = bool(j2_delta >= 0.05)
        # J3：被拦笔正期望即 FAIL；厚利桶 0.65-0.8 无新误杀
        j3_overall_ok = bl['mean'] is not None and bl['mean'] < 0
        j3_thick_ok = (bl_thick['tradeable'] == 0) or \
                      (bl_thick['mean'] is not None and bl_thick['mean'] <= 0)
        j3 = bool(j3_overall_ok and j3_thick_ok)
        # J4：分年反事实 mean 逐年 <0（三年，均有被拦笔才判；空年记 None）
        j4_years = {y: (bl_y[y]['mean'] if bl_y[y]['tradeable'] else None)
                    for y in ('2024', '2025', '2026')}
        j4 = bool(all(v is not None and v < 0 for v in j4_years.values()))
        # J5：2024 全窗 OOS 前置——被拦 2024 反事实 mean<0 且臂 2024 全窗 mean 不降于基线
        j5a = j4_years['2024'] is not None and j4_years['2024'] < 0
        j5b = (yf['2024']['mean'] is not None and base_yearly_full['2024']['mean'] is not None
               and yf['2024']['mean'] >= base_yearly_full['2024']['mean'])
        j5 = bool(j5a and j5b)

        arms_out[aid] = dict(
            label=adef['label'],
            full=stf, main=stm, yearly_main=ym, yearly_full=yf,
            exit_stat=agg,
            delta_main=dict(median=round(stm['median'] - st_main['median'], 4),
                            mean=round(stm['mean'] - st_main['mean'], 4),
                            n_removed=st_main['n'] - stm['n']),
            blocked=dict(all=bl, thick_065_080=bl_thick, yearly=bl_y),
            blocked_list=[dict(tkr=e['tkr'], et=e['et'], px=e['px'], volr=e['volr'],
                               cf_r=(e['cf']['r'] if e['cf'] else None),
                               cf_why=(e['cf']['why'] if e['cf'] else 'filter_fail(eff<=0/risk>8)'),
                               cf_open=(e['cf']['open'] if e['cf'] else None)) for e in gated],
            judgments=dict(
                J1=dict(criterion='主窗 median 不降（对账后基线）',
                        value=stm['median'], baseline=st_main['median'], verdict='PASS' if j1 else 'FAIL'),
                J2=dict(criterion='2026 段改善 ≥0.05/笔（对账后基线）',
                        value=j2_delta, baseline_2026_mean=base_yearly_main['2026']['mean'],
                        verdict='PASS' if j2 else 'FAIL'),
                J3=dict(criterion='厚利桶保全线：被拦笔正期望即 FAIL；0.65-0.8 桶无新误杀',
                        blocked_mean=bl['mean'], blocked_tradeable=bl['tradeable'],
                        thick_065_080_blocked=bl_thick, verdict='PASS' if j3 else 'FAIL'),
                J4=dict(criterion='分年反事实 mean 逐年<0（2024/2025/2026）',
                        value=j4_years, verdict='PASS' if j4 else 'FAIL'),
                J5=dict(criterion='2024 全窗 OOS 前置：被拦 2024 mean<0 且臂 2024 全窗 mean 不降',
                        blocked_2024_mean=j4_years['2024'],
                        arm_2024_mean=yf['2024']['mean'],
                        base_2024_mean=base_yearly_full['2024']['mean'],
                        verdict='PASS' if j5 else 'FAIL'),
                J6=dict(criterion='bootstrap 95%CI（seed=42,1000,笔块）拦截收益改善下界>0',
                        **{k: v for k, v in j6.items()},
                        verdict='PASS' if j6['pass_'] else 'FAIL'),
            ),
            arm_pass=bool(j1 and j2 and j3 and j4 and j5 and j6['pass_']))
        print(f"臂{aid} {adef['label']}: main n={stm['n']} med={stm['median']} "
              f"(基线 {st_main['median']}) 2026mean Δ={j2_delta} | 被拦 {bl['n']} 笔 "
              f"(tradeable {bl['tradeable']}, mean {bl['mean']}) | "
              f"J={[arms_out[aid]['judgments'][j]['verdict'] for j in ('J1','J2','J3','J4','J5','J6')]}")

    out = dict(
        generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        workorder='WO4 bk 腿修复（D3 三臂）· 冻结规格 v1.0',
        seed=SEED,
        caliber=dict(authoritative='Top1=N15/k7.5/m2/e0.3；V2 可实现出场；池=144；fd 腿禁动；闸仅进 bk 信号侧',
                     trigger='V1 收盘判定（信号序列零改动）',
                     fill='V2 可实现出场价 + 费 0.03%/bar（eng_final 逐字）',
                     volr='量比=当根volume/前N根volume均值，N=15（eng_w3/eng_r41 逐字）',
                     gate='被拦 bk 不进、箱体保持 live 不标 fired、fd 不受影响（eng_r41 逐字）',
                     cf='反事实出场与引擎出场分支逐字一致；eff<=0 或 risk>8 不构成交易（filter_fail）',
                     main_window='et>=2025-06-01', forming_bar='末根 bar 参与回测'),
        param_space_note='三臂边界均在样本内同窗选定，属打折范畴【推断】；N2/N3 对照组按授权条款不跑',
        reconciliation=recon,
        baseline=dict(full=st_full, main=st_main,
                      yearly_main=base_yearly_main, yearly_full=base_yearly_full),
        arms=arms_out,
        fail_action='任一 J 不达→该臂归档（a/b/c 独立判定）；复活条件=新评估段数据或闸形态换设计另立新单',
    )
    with open(os.path.join(OUT, 'wo4_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('OK ->', os.path.join(OUT, 'wo4_result.json'))


if __name__ == '__main__':
    main()
