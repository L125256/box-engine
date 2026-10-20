#!/usr/bin/env python3
# fd_revive_run.py — FD_REVIVE_SPEC_v1（已冻结批准 2026-10-20 13:24）逐字执行运行件
# 研究问题：fd 入场信号（一行不动）在更换出场规则后能否通过全套判线复活。
# 两方向（终裁④冻结，禁第三方向）：
#   D-A = K5-fd-exit-partial3r-breakeven（分批+保本，batch3_run.py L844-882 逐字）
#   D-B = K5-fd-exit-time45（hardcap 30→45bar，batch3_run.py L884-888 逐字）
# 对照臂 ctrl = K5-fd-exit-ctrl（原出场：tp=ep+3.5669×ATR14(入场日冻结)/eff/hardcap30，逐字）
# 红线登记（工程席）：
#   ① 入场 scan_fd_exit = batch3_run.py L797-832 逐字拷贝，零改动（审计红线）；
#   ② 出场函数 = batch3_run.py L835-913 中 ctrl / mk_partial(True) / mk_time(45) 逐字摘录，零改动；
#   ③ realC 烧窗（2026-06-01→2026-10-18）不入判线；唯一触碰=对照臂 D0 锚 n=1802 复现
#      （窗口 et>=MAIN 全窗，图谱记账引用，K5/k5_ctrl_anchor 同先例）；任何判线表无 realC 列；
#   ④ 判线 §4 五件套冻结（J1-J5），无中间态；判线对象=同信号 (tkr,et) 配对 ΔR，配对率门 85% 前置。
# 数据离线：唯一数据态=/tmp/box_cache_fresh（冻结快照内容副本，末根 K 线 2026-10-18）。
# md5 偏差登记（dual_check.py L17-22 在库先例逐字承继）：现存 ledger=f3f790a6e873e01b1966f8d5b996e0d3
# 与冻结 33c8b9ec54d17537c3b7f1f6d8d47463 不符，但①fd 锚逐位复现（673/+723.64/thick 118/2019.76）
# ②scan_ref maxdiff=0 ③pool_n=144 ④末根 K 线 2026-10-18 与 snapshot_20261019 一致
# → 判定为冻结后重序列化、数据内容未变；实质对拍（锚+scan_ref）作硬闸，md5 作偏差披露。
# （/tmp/box_cache 已被追加 2026-10-20 实时 bar=实质内容漂移，fd 锚漂至 674/+732.74，禁用；禁静默换口径，本披露即登记。）
import json, os, sys, time, statistics
from multiprocessing import get_context

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'wo_fdbrk'))
sys.path.insert(0, '/tmp/eng_wt_rc')
import common_fdbrk as CF
import eng_final as ENG

CF.CACHE = '/tmp/box_cache_fresh'      # 冻结快照内容副本（实质对拍硬闸见头注）

OUT_JSON = os.path.join(HERE, 'fd_revive_result.json')
OUT_MD = os.path.join(HERE, 'FD_REVIVE_REPORT.md')
CATR_FROZEN = 3.5669
REALB = ('2024-04-01', '2025-05-31')      # §3.1② 主窗前历史段（→2025-05-31）
SHADOW_START = '2026-10-20'               # §3.1④ 影子窗=快照尾日 2026-10-19 次日起
YEARS = ('2024', '2025', '2026')
PAIR_GATE = 0.85
BOOT_REPS, BOOT_BLOCK, BOOT_SEED = 2000, 10, 42
DISCOUNT = ('诚实折扣（规格 §3.3-4 强制，随一切结论携带）：realA/realB 数字 K5 已看过（数据已存在），'
            '窗内主判不是真样本外，替代方案强度严格小于 realC 一次成活；达标结论=「fd 出场结构增量成立，'
            '转影子候选」，不等于 fd 复活上线；放行仍走部署三道门+新预注册（R10 红线永不重开）。')

# ================================================================ ① 入场（batch3_run.py L797-832 逐字，零改动）
def scan_fd_exit(bars, bullmap, exit_fn, N=15):
    """fd 冻结臂入场逐字（fd_indep_run.scan_fd_indep V-FD-A/N15/refresh 路径；审计红线：
    入场逻辑一行不动），仅出场经 exit_fn 注入。exit_fn(bars, ei, ep, eff, a)→(xi, xpx, why, r)。"""
    import eng_final as ENG
    a = ENG.atrs(bars)
    trades = []
    last_frame = None
    i = max(N, 20, 14) + 1
    n = len(bars)
    while i < n:
        if a[i] is None:
            i += 1; continue
        t = bars[i]['time']
        if not bool(bullmap.get(t)):
            i += 1; continue
        px = bars[i]['close']; lo = bars[i]['low']
        w = bars[i - N + 1:i + 1]
        L_ = min(x['low'] for x in w); H_ = max(x['high'] for x in w); rng = H_ - L_
        fire = (lo <= L_ + 0.2 * rng) and (px > L_)
        frame = (round(L_, 10), round(H_, 10))
        if fire:
            ok = (last_frame is None) or (frame != last_frame)      # refresh 语义
            eff = L_ - 0.3 * a[i]
            risk = (px - L_) / px * 100
            if ok and eff > 0 and px > eff and risk <= 8.0:
                ep = px
                xi, xpx, why, r = exit_fn(bars, i, ep, eff, a[i])
                trades.append(dict(ep=ep, ei=i, xi=xi, xc=round(xpx, 4), r=r, why=why,
                                   et=t, xt=bars[xi]['time']))
                last_frame = frame
                i = xi + 1
                continue
            elif ok:
                last_frame = frame
        i += 1
    return trades

# ================================================================ ② 出场（batch3_run.py L835-913 逐字摘录，零改动）
def _fd_exit_fns(catr_frozen=3.5669):
    """8 个出场变体的出场函数（V2 可实现口径逐字：收盘判定触发+触发价与 open 顺延+费 0.03%/bar，
    common_fdbrk.v2_exit 谱系；审计红线：仅出场结构改动，入场零改动）。（本单只取 3 只，其余禁入判线 §5-2）"""
    import common_fdbrk as CF
    FEE = CF.FEE

    def v2(bars, ei, ep, tp, eff, hardcap):
        return CF.v2_exit(bars, ei, ep, tp, eff, hardcap)

    def mk_partial(breakeven):
        def fn(bars, ei, ep, eff, A):
            n = len(bars)
            half_done = False
            r_acc = 0.0
            w = [1.0, 1.0]   # 两半仓权重记账（各按各自出场 R）
            eff2 = ep if breakeven else eff   # 余仓 eff（保本上移【_OPS】）
            tp = ep + catr_frozen * A
            i = ei
            while i < n:
                i += 1
                if i >= n:
                    break
                px = bars[i]['close']
                if not half_done and px >= ep + 3.0 * (ep - eff):   # +3R 出半（收盘判定）
                    xpx = px
                    j = i
                    while j < n - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                        j += 1; xpx = bars[j]['open']
                    r1 = (xpx - ep) / ep * 100 - FEE * (j - ei)
                    r_acc += 0.5 * r1
                    half_done = True
                    i = j
                    continue
                if px <= (eff2 if half_done else eff) or px >= tp or i - ei >= 30:
                    if px >= tp: xpx = max(tp, bars[i]['open'])
                    elif px <= (eff2 if half_done else eff): xpx = min(eff2 if half_done else eff, bars[i]['open'])
                    else: xpx = px
                    j = i
                    while j < n - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                        j += 1; xpx = bars[j]['open']
                    r2 = (xpx - ep) / ep * 100 - FEE * (j - ei)
                    r = r_acc + (0.5 * r2 if half_done else r2)
                    return j, xpx, ('分批+3R' + ('/保本' if breakeven else '') +
                                    ('/止盈' if px >= tp else ('/止损' if px <= (eff2 if half_done else eff) else '/硬顶'))), r
            i = n - 1
            r2 = (bars[i]['close'] - ep) / ep * 100 - FEE * (i - ei)
            return i, bars[i]['close'], '数据末', r_acc + (0.5 * r2 if half_done else r2)
        return fn

    def mk_time(hardcap):
        def fn(bars, ei, ep, eff, A):
            tp = ep + catr_frozen * A
            return v2(bars, ei, ep, tp, eff, hardcap)
        return fn

    def ctrl(bars, ei, ep, eff, A):
        return v2(bars, ei, ep, ep + catr_frozen * A, eff, 30)   # 出场不变对照（冻结臂 E2）

    return {
        'K5-fd-exit-ctrl': ctrl,
        'K5-fd-exit-partial3r-breakeven': mk_partial(True),
        'K5-fd-exit-time45': mk_time(45),
    }

ARM_KEYS = {'ctrl': 'K5-fd-exit-ctrl', 'DA': 'K5-fd-exit-partial3r-breakeven', 'DB': 'K5-fd-exit-time45'}

# ================================================================ Pool 任务
def _w_main(job):
    arm, tk = job
    pool, bull, _ = CF.pool_bull()
    fns = _fd_exit_fns()
    return arm, tk, [dict(tkr=tk, **t) for t in scan_fd_exit(pool[tk], bull, fns[ARM_KEYS[arm]])]

def _w_loto(drop_tkr):
    """LOTO 去一票：严格池重建 + idx 牛闸重建（fd_indep_run._w_loto 同口径），ctrl 与两方向臂同池重扫，
    主窗（realA）同信号配对 Δ meanR。"""
    pool, bull, _ = CF.pool_bull()
    pool2 = {k: v for k, v in pool.items() if k != drop_tkr}
    bull2 = ENG.build_idx_bull(pool2)
    fns = _fd_exit_fns()
    trs = {}
    for arm in ARM_KEYS:
        lst = []
        for tk, bars in pool2.items():
            for t in scan_fd_exit(bars, bull2, fns[ARM_KEYS[arm]]):
                lst.append(dict(tkr=tk, **t))
        trs[arm] = lst
    out = {}
    for arm in ('DA', 'DB'):
        c = {(t['tkr'], t['et']): t['r'] for t in trs['ctrl'] if CF.MAIN <= t['et'] <= CF.TRUNC}
        a = {(t['tkr'], t['et']): t['r'] for t in trs[arm] if CF.MAIN <= t['et'] <= CF.TRUNC}
        keys = c.keys() & a.keys()
        mean = (sum(a[k] - c[k] for k in keys) / len(keys)) if keys else None
        out[arm] = dict(mean=round(mean, 6) if mean is not None else None,
                        n_paired=len(keys), n_ctrl=len(c), n_arm=len(a))
    return drop_tkr, out

# ================================================================ 配对与判线工具
def pair_stats(ctrl_trs, arm_trs, lo, hi):
    """配对键=(tkr, et) 精确匹配；Δ=arm−ctrl。返回配对 Δ 列表与配对率（分母取两侧较小 n，保守）。"""
    c = {(t['tkr'], t['et']): t['r'] for t in ctrl_trs if lo <= t['et'] <= hi}
    a = {(t['tkr'], t['et']): t['r'] for t in arm_trs if lo <= t['et'] <= hi}
    keys = sorted(c.keys() & a.keys())
    d = [(k[0], k[1], a[k] - c[k]) for k in keys]
    rate = (len(d) / min(len(c), len(a))) if (c and a) else 0.0
    return d, dict(n_paired=len(d), n_ctrl=len(c), n_arm=len(a), pair_rate=round(rate, 4))

def delta_summary(d):
    rs = sorted(x[2] for x in d)
    n = len(rs)
    if n == 0:
        return dict(n=0, mean=None, sum_r=0.0)
    def q(p):
        return round(rs[min(n - 1, int(p * (n - 1)))], 4)
    return dict(n=n, mean=round(sum(rs) / n, 4), sum_r=round(sum(rs), 2),
                median=round(rs[n // 2], 4), min=round(rs[0], 4), max=round(rs[-1], 4),
                p10=q(0.10), p25=q(0.25), p75=q(0.75), p90=q(0.90),
                share_gt0=round(sum(1 for x in rs if x > 0) / n * 100, 2))

def daily_series(d):
    agg = {}
    for _, et, dv in d:
        agg[et] = agg.get(et, 0.0) + dv
    return sorted(agg.items())

def judge_arm(arm, ctrl_trs, arm_trs):
    """§4 五件套判线（J5 影子期本单不采集，n<20 只累计不判）。"""
    # J1 realA 配对主判
    dA, pA = pair_stats(ctrl_trs, arm_trs, CF.MAIN, CF.TRUNC)
    sA = delta_summary(dA)
    q05, p_le0, _ = CF.stationary_boot(daily_series(dA), reps=BOOT_REPS, mean_block=BOOT_BLOCK, seed=BOOT_SEED)
    j1 = dict(realA=pA, delta=sA, bootstrap=dict(reps=BOOT_REPS, mean_block=BOOT_BLOCK, seed=BOOT_SEED,
                                                 q05_sum_r=round(q05, 2) if q05 is not None else None,
                                                 p_le0=p_le0),
              pass_=(sA['mean'] is not None and sA['mean'] > 0 and q05 is not None and q05 > 0))
    # J2 realB 同向门
    dB, pB = pair_stats(ctrl_trs, arm_trs, *REALB)
    sB = delta_summary(dB)
    j2 = dict(realB=pB, delta=sB, pass_=(sB['mean'] is not None and sB['mean'] > 0))
    # J3 分年（realA∪realB 窗，et<=TRUNC；2024 仅 realB 段覆盖自 2024-04-01）
    dU, _ = pair_stats(ctrl_trs, arm_trs, REALB[0], CF.TRUNC)
    yr = {}
    for y in YEARS:
        rs = [x[2] for x in dU if x[1][:4] == y]
        yr[y] = dict(n=len(rs), sum_r=round(sum(rs), 2))
    j3 = dict(years=yr, pass_=all(v['sum_r'] > 0 for v in yr.values()))
    return dict(J1=j1, J2=j2, J3=j3), dict(dA=dA, dB=dB, dU=dU)

# ================================================================ 主流程
def main():
    t0 = time.time()
    print('=== fd 复活专测（FD_REVIVE_SPEC_v1 逐字） ===')
    # ---- D0 三重门：md5（偏差披露）/ fd 锚 / scan_ref maxdiff（dual_check 先例：实质对拍作硬闸）----
    d0 = CF.d0_gate()
    d0['md5_deviation'] = ('f3f790a6e873e01b1966f8d5b996e0d3 != frozen 33c8b9ec54d17537c3b7f1f6d8d47463; '
                           'anchor/scan_ref/pool_n/last-bar 全对 → 重序列化假设，偏差披露不禁跑（dual_check.py 先例）')
    # 末根 K 线一致性（④）：全部文件尾 bar=2026-10-18（与 snapshot_20261019 一致）
    tails = {json.load(open(os.path.join(CF.CACHE, f)))[-1]['time'] for f in sorted(os.listdir(CF.CACHE))}
    d0['last_bar_consistent'] = (tails == {'2026-10-18'})
    print('D0 门①③:', json.dumps(d0, ensure_ascii=False))
    assert d0['anchor_ok'], 'fd 原版臂锚（673/+723.64/thick118/2019.76）复现失败，停工'
    assert d0['scan_ref_maxdiff'] == 0, 'scan_ref 对拍 maxdiff!=0，停工'
    assert d0['pool_n'] == 144 and d0['last_bar_consistent'], 'pool_n 或末根 K 线一致性不过，停工'
    pool, bull, idxv = CF.pool_bull()

    # ---- D0 锚②：对照臂（原出场）主窗 et>=MAIN 复现 n=1802/mean=1.1798/sum=2125.96 ----
    fns = _fd_exit_fns()
    jobs = [(arm, tk) for arm in ARM_KEYS for tk in sorted(pool)]
    arms_trs = {arm: [] for arm in ARM_KEYS}
    with get_context('fork').Pool(32) as p:
        for arm, tk, lst in p.map(_w_main, jobs, chunksize=4):
            arms_trs[arm].extend(lst)
    ctrl_main = [t for t in arms_trs['ctrl'] if t['et'] >= CF.MAIN]
    st2 = CF.stats6(ctrl_main)
    anchor2 = dict(anchor='K5 ctrl 语义=冻结臂 V-FD-A/E2/refresh，主窗 et>=2025-06-01',
                   got=dict(n=st2['n'], mean=st2['mean'], sum_r=st2['sum_r']),
                   want=dict(n=1802, mean=1.1798, sum_r=2125.96),
                   tol='笔数逐位 / mean ±0.05 / sum_r ±0.05×n（§0.5 换算先例）',
                   ok=(st2['n'] == 1802 and abs(st2['mean'] - 1.1798) <= 0.05
                       and abs(st2['sum_r'] - 2125.96) <= 0.05 * 1802))
    print('D0 锚②对照臂:', json.dumps(anchor2, ensure_ascii=False))
    if not anchor2['ok']:
        out = dict(workorder='fd_revive（FD_REVIVE_SPEC_v1）', status='停工', d0=d0, anchor2=anchor2,
                   note='对照臂锚复现失败=数据谱系异常，按规格停工重锚，不跑判线',
                   runtime_sec=round(time.time() - t0, 1))
        json.dump(out, open(OUT_JSON, 'w'), ensure_ascii=False, indent=1, default=str)
        write_md(out, None)
        print('停工：对照臂锚 MISS，报告已写', OUT_MD)
        return

    # ---- thick 去一基准票集：fd 原版臂锚 thick(r>=8) 118 票谱系 ----
    trs_all, _ = ENG.collect(dict(N=15, k=7.5, m=2, e=0.3), pool, bull)
    orig_fd_main = [t for t in trs_all if t['kind'] == 'fd' and t['et'] >= CF.MAIN]
    thick_tkrs = sorted({t['tkr'] for t in orig_fd_main if t['r'] >= 8})

    # ---- 全臂全窗记账（含未配对绝对 sumR，次要记账列）----
    book = {}
    for arm in ARM_KEYS:
        full = [t for t in arms_trs[arm]]
        ra = [t for t in full if CF.MAIN <= t['et'] <= CF.TRUNC]
        rb = [t for t in full if REALB[0] <= t['et'] <= REALB[1]]
        book[arm] = dict(full=dict(n=len(full), sum_r=round(sum(t['r'] for t in full), 2)),
                         realA=dict(n=len(ra), sum_r=round(sum(t['r'] for t in ra), 2)),
                         realB=dict(n=len(rb), sum_r=round(sum(t['r'] for t in rb), 2)))

    # ---- LOTO 144 去一（严格池重建+牛闸重建），两方向同批 ----
    tkrs = sorted(pool)
    with get_context('fork').Pool(32) as p:
        loto = p.map(_w_loto, tkrs, chunksize=4)
    loto_map = dict(loto)

    # ---- 逐方向判线 ----
    results, deltas = {}, {}
    for arm, label in (('DA', 'D-A 分批+保本（partial3r-breakeven）'), ('DB', 'D-B hardcap 45bar（time45）')):
        legs, dl = judge_arm(arm, arms_trs['ctrl'], arms_trs[arm])
        # J4 LOTO：144 去一配对 Δ meanR 全>0；thick 去一（fd 锚 thick 118 票谱系）同步全>0
        l_arm = {tk: loto_map[tk][arm] for tk in tkrs}
        fails = [dict(tkr=tk, **v) for tk, v in l_arm.items() if v['mean'] is None or v['mean'] <= 0]
        thick_loto = {tk: l_arm[tk] for tk in thick_tkrs}
        thick_fails = [tk for tk, v in thick_loto.items() if v['mean'] is None or v['mean'] <= 0]
        legs['J4'] = dict(loto_n=len(tkrs), fails=fails[:10], n_fails=len(fails),
                          min_mean=min(v['mean'] for v in l_arm.values() if v['mean'] is not None),
                          thick_ref='fd 原版臂锚 thick(r>=8) 118 笔谱系票集 n=' + str(len(thick_tkrs)),
                          thick_fails=thick_fails,
                          pass_=(len(fails) == 0 and len(thick_fails) == 0))
        # J5 影子期：本单不采集（挂判定轮每日旁路属部署侧），n=0<20 只累计不判
        legs['J5'] = dict(shadow_start=SHADOW_START, n=0, status='只累计不判（n<20）',
                          note='影子采集未挂接（达标才挂）；n>=20 后按同判线判读一次封印',
                          pass_=None)
        hard = all(legs[k]['pass_'] for k in ('J1', 'J2', 'J3', 'J4'))
        pair_ok = legs['J1']['realA']['pair_rate'] >= PAIR_GATE
        verdict = ('达标（fd 出场结构增量成立，转影子候选；J5 影子期 n<20 只累计不判，n>=20 后判读一次封印终审）'
                   if (hard and pair_ok) else '判死（J1–J4 任一不满足即维持 fd 原判死，归档附复活条件）')
        results[arm] = dict(label=label, legs=legs, verdict=verdict,
                            pair_gate=dict(gate=PAIR_GATE, realA_rate=legs['J1']['realA']['pair_rate'],
                                           ok=pair_ok))
        deltas[arm] = dl
        print(f'[{arm}]', json.dumps({k: legs[k]['pass_'] for k in ('J1', 'J2', 'J3', 'J4')},
                                     ensure_ascii=False), '→', verdict)

    # ---- 全样本（含未配对）绝对 sumR 差（次要记账）----
    diff_book = {arm: dict(realA=round(book[arm]['realA']['sum_r'] - book['ctrl']['realA']['sum_r'], 2),
                           realB=round(book[arm]['realB']['sum_r'] - book['ctrl']['realB']['sum_r'], 2))
                 for arm in ('DA', 'DB')}

    out = dict(
        workorder='fd_revive（fd 复活专测，FD_REVIVE_SPEC_v1 冻结批准 2026-10-20 13:24）',
        spec='FD_REVIVE_SPEC_v1 §2/§4/§5 逐字；运行件=research/wo_fddual/fd_revive_run.py（运行单指定路径；§6 原文 wo_fdbrk 以运行单为准）',
        generated=time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()),
        discount=DISCOUNT,
        d0=dict(snapshot_ver=d0['snapshot_ver'], snapshot_md5=d0['snapshot_md5'], md5_ok=d0['md5_ok'],
                md5_deviation=d0['md5_deviation'], last_bar_consistent=d0['last_bar_consistent'],
                pool_n=d0['pool_n'], anchor1_fd=d0['fd_anchor'], anchor1_ok=d0['anchor_ok'],
                scan_ref_maxdiff=d0['scan_ref_maxdiff'],
                reused=['load_pool', 'build_idx_bull', 'scan', 'collect', 'atrs']),
        anchor2_ctrl=anchor2,
        arms_book=book, abs_sumR_diff=diff_book,
        thick_tkrs_n=len(thick_tkrs),
        results=results,
        loto_detail={arm: {tk: loto_map[tk][arm] for tk in tkrs} for arm in ('DA', 'DB')},
        realC_note='realC（2026-06-01→2026-10-18）烧窗禁触：不入判线，任何判线表无 realC 列；对照臂锚② et>=MAIN 全窗复现属图谱记账引用（K5 先例）',
        runtime_sec=round(time.time() - t0, 1),
    )
    json.dump(out, open(OUT_JSON, 'w'), ensure_ascii=False, indent=1, default=str)
    write_md(out, deltas)
    print('写出', OUT_JSON, '| 用时', out['runtime_sec'], 's')

# ================================================================ 报告
def write_md(out, deltas):
    L = []
    L.append('# FD_REVIVE_REPORT — fd 复活专测判线报告\n')
    L.append('>' + out.get('discount', DISCOUNT) + '\n')
    if out.get('status') == '停工':
        L.append('## 结论：**停工**\n')
        L.append('- ' + out['note'])
        L.append('- D0 锚②对照臂 got=' + json.dumps(out['anchor2']['got']) +
                 ' want=' + json.dumps(out['anchor2']['want']) + '\n')
        open(OUT_MD, 'w').write('\n'.join(L))
        return
    L.append(f"- 运行件：`research/wo_fddual/fd_revive_run.py`（FD_REVIVE_SPEC_v1 逐字；出场函数 batch3_run.py L835-913 逐字摘录+登记，入场 scan_fd_exit L797-832 逐字零改动）")
    L.append(f"- 生成：{out['generated']} | 用时 {out['runtime_sec']}s | Pool(32)\n")

    L.append('## D0 双锚 + md5 三重门\n')
    a1 = out['d0']['anchor1_fd']
    L.append(f"- 锚①fd 原版臂（eng_final.collect top1 N15/k7.5/m2/e0.3, kind=fd）：n={a1['n']} / sum_r={a1['sum_r']} / thick(r≥8)={a1['thick_n']} 笔 {a1['thick_sum']}R → **复现 OK**")
    a2 = out['anchor2_ctrl']
    g = a2['got']
    L.append(f"- 锚②对照臂（原出场，主窗 et≥2025-06-01）：n={g['n']} / mean={g['mean']} / sum_r={g['sum_r']}（want 1802/1.1798/2125.96，tol {a2['tol']}）→ **复现 OK**")
    L.append(f"- md5 三重门：snapshot ledger={out['d0']['snapshot_md5']}（≠冻结 33c8b9ec…，重序列化偏差按 dual_check.py L17-22 在库先例披露登记；fd 锚逐位复现+maxdiff=0+pool_n=144+末根 2026-10-18 全对 → 实质对拍硬闸过）/ scan_ref maxdiff={out['d0']['scan_ref_maxdiff']}（=0 ✓）/ 双锚 ✓")
    L.append('')

    L.append('## 臂记账（全窗/realA/realB，含未配对绝对 sumR=次要记账列）\n')
    L.append('| 臂 | 全窗 n/sumR | realA n/sumR | realB n/sumR |')
    L.append('|---|---|---|---|')
    for arm, nm in (('ctrl', 'ctrl（原出场对照）'), ('DA', 'D-A 分批+保本'), ('DB', 'D-B 45bar')):
        b = out['arms_book'][arm]
        L.append(f"| {nm} | {b['full']['n']} / {b['full']['sum_r']} | {b['realA']['n']} / {b['realA']['sum_r']} | {b['realB']['n']} / {b['realB']['sum_r']} |")
    for arm in ('DA', 'DB'):
        d = out['abs_sumR_diff'][arm]
        L.append(f"- {arm} 绝对 sumR 差（含未配对，仅记账不入判线）：realA {d['realA']:+}R / realB {d['realB']:+}R")
    L.append('')

    for arm, title in (('DA', 'D-A「分批止盈+保本」（partial3r-breakeven）'), ('DB', 'D-B「放宽时间上限」（hardcap 45bar）')):
        r = out['results'][arm]
        L.append(f"## {arm} 判线（{title}，独立成案）\n")
        legs = r['legs']
        j1, j2, j3, j4, j5 = legs['J1'], legs['J2'], legs['J3'], legs['J4'], legs['J5']
        L.append('| 腿 | 判线 | 读数 | 判定 |')
        L.append('|---|---|---|---|')
        b = j1['bootstrap']
        L.append(f"| J1 | realA 配对 Δ meanR>0 且 bootstrap(块10,B=2000,seed=42) q05(ΔsumR)>0 | Δ meanR={j1['delta']['mean']}（n={j1['delta']['n']}，配对率={j1['realA']['pair_rate']}）；q05={b['q05_sum_r']}R，p(≤0)={b['p_le0']} | {'PASS' if j1['pass_'] else 'FAIL'} |")
        L.append(f"| J2 | realB 配对 Δ meanR>0（同向门，样本薄如实标注） | Δ meanR={j2['delta']['mean']}（n={j2['delta']['n']}，配对率={j2['realB']['pair_rate']}） | {'PASS' if j2['pass_'] else 'FAIL'} |")
        ys = '；'.join(f"{y}: ΔsumR={j3['years'][y]['sum_r']}(n={j3['years'][y]['n']})" for y in ('2024', '2025', '2026'))
        L.append(f"| J3 | 分年不翻脸 2024/2025/2026 ΔsumR 均>0 | {ys} | {'PASS' if j3['pass_'] else 'FAIL'} |")
        L.append(f"| J4 | LOTO 144 去一配对 Δ meanR 全>0；thick 去一（fd 锚 thick 118 票谱系，{j4['thick_ref']}）同步全>0 | min_mean={j4['min_mean']}，fails={j4['n_fails']}/144；thick fails={len(j4['thick_fails'])}/{out['thick_tkrs_n']} | {'PASS' if j4['pass_'] else 'FAIL'} |")
        L.append(f"| J5 | 影子期 n≥20 配对 Δ meanR>0 | n=0（影子窗自 {j5['shadow_start']} 起，采集未挂接——达标才挂） | 只累计不判（n<20，按规格不构成不满足） |")
        if deltas and arm in deltas:
            s = j1['delta']
            L.append(f"- realA 配对差值分布：min={s['min']} / p10={s['p10']} / p25={s['p25']} / 中位={s['median']} / p75={s['p75']} / p90={s['p90']} / max={s['max']}；Δ>0 占比={s['share_gt0']}%；ΔsumR={s['sum_r']}R")
            L.append(f"- realB 配对差值分布：mean={j2['delta']['mean']} / 中位={j2['delta']['median']} / min={j2['delta']['min']} / max={j2['delta']['max']}；ΔsumR={j2['delta']['sum_r']}R")
            L.append(f"- 分年明细（realA∪realB 配对，2024 仅覆盖 realB 段自 2024-04-01）：")
            for y in ('2024', '2025', '2026'):
                v = j3['years'][y]
                L.append(f"  - {y}: n={v['n']}, ΔsumR={v['sum_r']}R")
        L.append(f"- 配对率门（≥85% 前置数据完整性门）：realA={j1['realA']['pair_rate']}（ctrl {j1['realA']['n_ctrl']} / {arm} {j1['realA']['n_arm']} → 配对 {j1['realA']['n_paired']}）→ {'OK' if r['pair_gate']['ok'] else '规格执行异常'}")
        L.append(f"\n**{arm} 最终判定：{r['verdict']}**\n")

    L.append('## 诚实标注\n')
    L.append('- ' + DISCOUNT)
    L.append('- realB 段样本薄，只作同向门无显著性要求（§3.1② 口径）；2024 年仅覆盖 2024-04-01 起的 realB 窗。')
    L.append('- D-A/D-B 分案记账禁合并表述（记账席）；两方向互不合并、互不择优。')
    L.append('- realC 烧窗（2026-06-01→2026-10-18）不入判线，本报告无 realC 判线列；对照臂锚②全窗复现属图谱记账引用（K5 先例）。')
    L.append('- 判线无中间态：达标/判死二值，无「降级/接近达标」表述资格。')
    L.append('')
    L.append('## 影子期待接入清单（登记，不实现挂接——达标才挂，SHADOW_SPEC SH-1 同款）\n')
    da_ok = out['results']['DA']['verdict'].startswith('达标')
    L.append(f"- D-A 判定：{'达标 → 以下清单生效待挂' if da_ok else '未达标 → 本清单仅登记不生效'}")
    for item in (
        '挂点：判定轮后每日旁路采集（只读+异常不阻断，执行席口径），与 FR-1 同源挂点；',
        '影子窗起点：2026-10-20（规格 §3.1④ 冻结文本「快照尾日次日，当前=2026-10-19」；快照内容末根实为 2026-10-18，起点 2026-10-20 晚于任一尾日且晚于规格冻结时刻，合规）；',
        '采集内容：前瞻 fd 信号（入场一行不动）× D-A 出场 vs 对照臂同信号配对 ΔR，旁路落盘；',
        '判读纪律：n≥20 必经判读，判读一次封印 sealed=true，不因 realC 已烧而豁免；',
        '方向维持门：n≥20 配对 Δ meanR>0；n<20 只累计不判；影子读数不回写部署姿态（R10）；',
        '每自然季至多一次机械复判（判死后复活路径 a）；达标=影子候选资格，放行仍走部署三道门+新预注册。'):
        L.append('- [ ] ' + item)
    L.append('')
    L.append('## 判死册（若判死，附复活条件）\n')
    for arm in ('DA', 'DB'):
        v = out['results'][arm]['verdict']
        if v.startswith('判死'):
            L.append(f"- {arm}：{v}。复活条件（预写）：(a) 影子窗样本自然滚动累计至 n≥20，按本规格同判线机械复判（每自然季至多一次）；或 (b) 用户批准 v2 新预注册新预算。禁以任何「差一点」叙述复活。")
    open(OUT_MD, 'w').write('\n'.join(L))

if __name__ == '__main__':
    main()
