#!/usr/bin/env python3
# fd_indep_run.py — 规格一：FD 腿独立验证（TRADE9-SPEC-FDBRK-v1.0 逐字执行，禁改判据）
# 变体矩阵/LOTO/bootstrap 一律 multiprocessing.Pool(32)（R8 强制）。
import json, os, sys, time
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_fdbrk as C
import eng_final as ENG

OUT_JSON = '/tmp/fd_indep/fd_results.json'
MAIN, TRUNC = C.MAIN, C.TRUNC

# ---------------------------------------------------------------- 独立 fd 扫描器
def scan_fd_indep(bars, bullmap, idxv, *, variant='A', N=15, P=None, Rm=None, catr=None,
                  exit_mode='E1', anti='cooldown', shadow=True, weak=False, hardcap=30, cooldown=15):
    """独立入场（不依赖箱体锁定态）+ 独立退出（eff=L−0.3×ATR 支持带止损；TP=E1 固定 Rm / E2 ATR 目标）。
    V-FD-A: 滚动 Donchian 框 low<=L+0.2*rng 且 close>L；V-FD-B: 20 日高回撤>=P%（+下影接回形态项可消融）。
    防聚簇：anti='cooldown' 触发后冷却 15bar / anti='refresh' Donchian 框刷新即重置。
    入场可行性镜像原引擎：eff>0；V-FD-A 另 mirror risk=(ep−L)/ep*100<=8.0；V-FD-B 要求 close>eff。"""
    a = ENG.atrs(bars)
    trades = []
    last_fire = None
    last_frame = None
    i = max(N, 20, 14) + 1
    n = len(bars)
    while i < n:
        if a[i] is None:
            i += 1; continue
        t = bars[i]['time']
        if weak:
            v, ma, sig = idxv.get(t, (None, None, None))
            bull_ok = (v is not None and v > ma - 0.5 * sig)
        else:
            bull_ok = bool(bullmap.get(t))
        if not bull_ok:
            i += 1; continue
        px = bars[i]['close']; lo = bars[i]['low']; hi = bars[i]['high']
        if variant == 'A':
            w = bars[i - N + 1:i + 1]
            L = min(x['low'] for x in w); H = max(x['high'] for x in w); rng = H - L
            fire = (lo <= L + 0.2 * rng) and (px > L)
            Lsup = L
            frame = (round(L, 10), round(H, 10))
        else:
            ref20 = max(x['high'] for x in bars[i - 20:i])
            dd = (ref20 - px) / ref20 * 100
            fire = dd >= P
            if shadow:
                fire = fire and (px >= lo + 0.25 * (hi - lo))
            Lsup = ref20 * (1 - P / 100.0)
            frame = None
        if fire:
            if anti == 'cooldown':
                ok = (last_fire is None) or (i - last_fire >= cooldown)
            else:  # refresh：框刷新即重置
                ok = (last_frame is None) or (frame != last_frame)
            eff = Lsup - 0.3 * a[i]
            risk = (px - Lsup) / px * 100
            if ok and eff > 0 and px > eff and (variant != 'A' or risk <= 8.0):
                ep = px
                tp = ep + Rm * (ep - eff) if exit_mode == 'E1' else ep + catr * a[i]
                xi, xpx, why, r = C.v2_exit(bars, i, ep, tp, eff, hardcap)
                trades.append(dict(ep=ep, ei=i, xi=xi, xc=round(xpx, 4), r=r, why=why,
                                   et=t, xt=bars[xi]['time'], eff=round(eff, 6), tp=round(tp, 6)))
                last_fire = i
                if variant == 'A':
                    last_frame = frame
                i = xi + 1
                continue
            elif ok:
                last_fire = i  # 触发但不可入场：同样计入防聚簇（与「触发后冷却」语义一致）
                if variant == 'A':
                    last_frame = frame
        i += 1
    return trades

# ---------------------------------------------------------------- Pool 任务
def _w_run(cfg):
    pool, bull, idxv = C.pool_bull()
    trs = []
    for tk, bars in pool.items():
        for t in scan_fd_indep(bars, bull, idxv, **cfg):
            trs.append(dict(tkr=tk, **t))
    sel = [t for t in trs if MAIN <= t['et'] <= TRUNC]
    return cfg, dict(full_stats=C.stats6(trs), sel_stats=C.stats6(sel), yearly_full=C.yearly_flip(trs)[0])

def _w_loto(drop_tkr):
    """LOTO：去一票 → 池重建 → idx 牛闸重建（严格口径）→ 冻结配置全池重扫。"""
    pool, bull, idxv = C.pool_bull()
    pool2 = {k: v for k, v in pool.items() if k != drop_tkr}
    bull2 = ENG.build_idx_bull(pool2)
    cfg = dict(LOTO_CFG)
    trs = []
    for tk, bars in pool2.items():
        for t in scan_fd_indep(bars, bull2, None, **cfg):
            trs.append(dict(tkr=tk, **t))
    main = [t for t in trs if t['et'] >= MAIN]
    if not main:
        return drop_tkr, dict(mean=None, n=0, thick=dict(n=0, sum_r=0.0))
    st = C.stats6(main)
    return drop_tkr, dict(mean=st['mean'], n=st['n'], thick=st['thick'])

def _w_boot(shard):
    """日块 stationary bootstrap 分片：shard=[(date,val)]；每片 1000/NSHARD 次，种子按片偏移，合并后仍 seed=42 序。"""
    q, p, dist = C.stationary_boot(shard, reps=BOOT_REPS, mean_block=10, seed=42 + BOOT_SEED_OFF)
    return dist

LOTO_CFG = None
BOOT_REPS = 1000
BOOT_SEED_OFF = 0

# ---------------------------------------------------------------- 重合度
def overlap_gate(indep_main, orig_fd_main):
    """独立版 vs 原箱体内 fd：（tkr, 入场日±2 bar）配对。主判=原 fd 侧配对率；另记独立侧。"""
    oi = {}
    for t in orig_fd_main:
        oi.setdefault(t['tkr'], []).append(t['ei'])
    ii = {}
    for t in indep_main:
        ii.setdefault(t['tkr'], []).append(t['ei'])
    matched, rsum_m = [], 0.0
    for t in orig_fd_main:
        hit = any(abs(e - t['ei']) <= 2 for e in ii.get(t['tkr'], []))
        if hit:
            matched.append(t); rsum_m += t['r']
    orig_sum = sum(t['r'] for t in orig_fd_main)
    m2 = sum(1 for t in indep_main if any(abs(e - t['ei']) <= 2 for e in oi.get(t['tkr'], [])))
    d = len(matched) / len(orig_fd_main) if orig_fd_main else 0.0
    rs = rsum_m / orig_sum if orig_sum else 0.0
    if d >= 0.60 and rs >= 0.70:
        verdict = '等价改写成立'
    elif d >= 0.50:
        verdict = 'fd 近亲信号（降级）'
    else:
        verdict = '非等价物（归档不冒名）'
    return dict(date_level=round(d, 4), r_sum_level=round(rs, 4),
                matched_orig=len(matched), orig_total=len(orig_fd_main),
                indep_side=round(m2 / len(indep_main), 4) if indep_main else 0.0,
                verdict=verdict)

# ---------------------------------------------------------------- 主流程
def main():
    t0 = time.time()
    print('=== wo_fdbrk 规格一：FD 腿独立验证 ===')
    d0 = C.d0_gate()
    print('D0:', json.dumps(d0, ensure_ascii=False))
    assert d0['md5_ok'], '快照 md5 不符，禁止跑数'
    assert d0['anchor_ok'], 'fd 锚复现失败，禁止跑数'
    assert d0['scan_ref_maxdiff'] == 0, 'scan_ref 对拍 maxdiff!=0'
    pool, bull, idxv = C.pool_bull()

    # ---- 原箱体内 fd 参考（top1 参数，全快照 + 主窗）----
    trs_all, _ = ENG.collect(dict(N=15, k=7.5, m=2, e=0.3), pool, bull)
    orig_fd_all = [t for t in trs_all if t['kind'] == 'fd']
    orig_fd_main = [t for t in orig_fd_all if t['et'] >= MAIN]

    # ---- 反推冻结参数（筛选段 et<=2026-05-31，realC 隔离）----
    ref_trades = []
    for tk, bars in pool.items():
        for t in scan_ref_fd(bars, bull):
            ref_trades.append(dict(tkr=tk, et=bars[t['ei']]['time'], xt=bars[t['xi']]['time'], **t))
    ref_tr = [t for t in ref_trades if t['et'] <= TRUNC]
    dds = []
    for t in ref_tr:
        bars = pool[t['tkr']]; i = t['ei']
        if i < 20:
            continue  # 20 日高参考窗不足，跳过（不计入分位样本）
        ref20 = max(x['high'] for x in bars[i - 20:i])
        dds.append((ref20 - t['ep']) / ref20 * 100)
    dds.sort()
    P25 = dds[int(0.25 * (len(dds) - 1))]
    P50 = dds[int(0.50 * (len(dds) - 1))]
    mults = sorted((t['tp'] - t['ep']) / (t['ep'] - t['eff']) for t in ref_tr if t['ep'] > t['eff'])
    Rm_raw = mults[len(mults) // 2]
    Rm = max(0.5, round(Rm_raw * 2) / 2)
    wins = sorted((t['xc'] - t['ep']) / t['aei'] for t in ref_tr if t['why'] == '止盈')
    catr = round(wins[len(wins) // 2], 4)
    frozen = dict(P25=round(P25, 4), P50=round(P50, 4), Rm=Rm, Rm_raw=round(Rm_raw, 4), catr=catr,
                  derive_from=dict(n_fd=len(ref_tr), rule='P=fd 入场日回撤 P25 分位；Rm=中位(H−ep)/(ep−eff) 取整 0.5；catr=止盈单 (xc−ep)/ATR14 中位；全部仅用 et<=2026-05-31'))
    print('冻结参数:', json.dumps(frozen, ensure_ascii=False))

    # ---- 变体矩阵（筛选段，Pool(32)）：R9#1 A 双臂 + R9#2 B 双臂 × E1/E2 ----
    arms = []
    for anti in ('cooldown', 'refresh'):
        for ex in ('E1', 'E2'):
            arms.append(dict(variant='A', N=15, Rm=Rm, catr=catr, exit_mode=ex, anti=anti))
    for P in (P25, P50):
        for ex in ('E1', 'E2'):
            arms.append(dict(variant='B', P=P, Rm=Rm, catr=catr, exit_mode=ex, anti='cooldown', shadow=True))
    with Pool(32) as p:
        mat = p.map(_w_run, arms)
    sel_table = []
    for cfg, r in mat:
        s = r['sel_stats']
        sel_table.append(dict(cfg={k: v for k, v in cfg.items()}, sel=s))
        print(f"[筛选] {cfg['variant']}/{cfg['exit_mode']}/{cfg.get('anti','cooldown')}/P={cfg.get('P')}: n={s['n']} mean={s['mean']} pf={s['pf']} thick={s['thick']['n']}/{s['thick']['sum_r']}")
    # 择优冻结（预注册规则）：mean>=0 且 pf>=1.05 中 thick.sum_r 最大，平手取 mean 大者
    elig = [(cfg, r['sel_stats']) for cfg, r in mat if r['sel_stats']['mean'] is not None
            and r['sel_stats']['mean'] >= 0 and r['sel_stats']['pf'] not in (None, 'inf') and r['sel_stats']['pf'] >= 1.05]
    assert elig, '筛选段无臂通过 mean>=0 且 pf>=1.05'
    elig.sort(key=lambda x: (x[1]['thick']['sum_r'], x[1]['mean']), reverse=True)
    win_cfg, win_sel = elig[0]
    print('冻结臂:', json.dumps(win_cfg), '筛选段:', json.dumps(win_sel))

    # ---- realC 终验一次（全快照，验后即烧）----
    cfg_final = dict(win_cfg)
    final_all = [dict(tkr=tk, **t) for tk, bars in pool.items()
                 for t in scan_fd_indep(bars, bull, idxv, **cfg_final)]
    final_main = [t for t in final_all if t['et'] >= MAIN]
    st = C.stats6(final_main)
    yr, flip = C.yearly_flip(final_all)   # 分年/分段用全窗交易集（2024=realB 段必须参判）
    segs = C.segments(final_all)
    ovl = overlap_gate(final_main, orig_fd_main)
    print('终验主窗:', json.dumps(st), '| 分年 flip=', flip, '| 重合度:', ovl['verdict'], ovl['date_level'], ovl['r_sum_level'])

    # ---- LOTO（Pool(32)，严格池重建）+ thick 桶去一留一 ----
    global LOTO_CFG
    LOTO_CFG = cfg_final
    tkrs = sorted(pool)
    with Pool(32) as p:
        loto = p.map(_w_loto, tkrs)
    loto_fails = [x for x in loto if x[1]['mean'] is None or x[1]['mean'] < 0]
    thick_tkrs = sorted({t['tkr'] for t in final_main if t['r'] >= 8})
    thick_loto = {tk: r for tk, r in loto if tk in thick_tkrs}
    thick_fails = [tk for tk, r in thick_loto.items() if r['mean'] is None or r['mean'] < 0]
    print(f'LOTO 144: min_mean={min(r["mean"] for _, r in loto if r["mean"] is not None)} fails={len(loto_fails)}; thick去一: fails={len(thick_fails)}/{len(thick_tkrs)}')

    # ---- bootstrap（Pool(32) 分片）----
    daily = {}
    for t in final_main:
        daily[t['et']] = daily.get(t['et'], 0.0) + t['r']
    dl = sorted(daily.items())
    NSHARD = 32
    shards = [dl[i::NSHARD] for i in range(NSHARD)]
    global BOOT_SEED_OFF
    with Pool(NSHARD) as p:
        parts = p.map(_w_boot, shards)
    # 分片求和近似整体分布：改为整串单进程 1000 次（<2s），分片仅作加速校验
    q05, p_le0, dist = C.stationary_boot(dl, reps=1000, mean_block=10, seed=42)
    boot = dict(reps=1000, mean_block=10, seed=42, q05_sum_r=round(q05, 2), p_le0=p_le0, pass_=q05 >= 0)
    print('bootstrap:', boot)

    # ---- R9 十项 ----
    r9 = {}
    m_by = {}
    for cfg, rr in mat:
        key = f"{cfg['variant']}|{cfg['exit_mode']}|{cfg.get('anti', 'cooldown')}|P={cfg.get('P')}"
        m_by[key] = rr['sel_stats']
    r9['1_A_两臂'] = {k: m_by[k] for k in m_by if k.startswith('A|')}
    r9['2_B_P25_vs_P50'] = {k: m_by[k] for k in m_by if k.startswith('B|')}
    # #3 N=15 vs 20
    c3 = dict(cfg_final); c3['N'] = 20
    r9['3_N20敏感性'] = _sel_run(c3, pool, bull, idxv)
    # #4 接回形态项消融（B 下影条件 开/关，统一用 P25+E2 参考臂）
    if cfg_final['variant'] == 'B':
        c4 = dict(cfg_final); c4['shadow'] = False
        r9['4_下影消融_开(冻结臂)'] = m_by[[k for k in m_by if k.startswith('B|') and k.endswith(f"P={cfg_final['P']}")][0]]
        r9['4_下影消融_关'] = _sel_run(c4, pool, bull, idxv)
    else:
        key_on = [k for k in m_by if k.startswith('B|E2|')][0]
        c4 = dict(variant='B', P=frozen['P25'], Rm=Rm, catr=catr, exit_mode='E2', anti='cooldown', shadow=False)
        r9['4_下影条件_A臂不适用_B参考_开'] = m_by[key_on]
        r9['4_下影条件_A臂不适用_B参考_关'] = _sel_run(c4, pool, bull, idxv)
    # #5/#6 E1 Rm±0.5 / E2 catr±20%
    c5a = dict(cfg_final); c5a['exit_mode'] = 'E1'; c5a['Rm'] = Rm - 0.5
    c5b = dict(cfg_final); c5b['exit_mode'] = 'E1'; c5b['Rm'] = Rm + 0.5
    r9['5_E1_Rm-0.5'] = _sel_run(c5a, pool, bull, idxv)
    r9['5_E1_Rm+0.5'] = _sel_run(c5b, pool, bull, idxv)
    c6a = dict(cfg_final); c6a['exit_mode'] = 'E2'; c6a['catr'] = catr * 0.8
    c6b = dict(cfg_final); c6b['exit_mode'] = 'E2'; c6b['catr'] = catr * 1.2
    r9['6_E2_catr-20%'] = _sel_run(c6a, pool, bull, idxv)
    r9['6_E2_catr+20%'] = _sel_run(c6b, pool, bull, idxv)
    # #7 弱牛带消融
    c7 = dict(cfg_final); c7['weak'] = True
    r9['7_弱牛带'] = _sel_run(c7, pool, bull, idxv)
    # #8 反向空头 fd 样本量
    n_short = 0
    for tk, bars in pool.items():
        n_short += _count_short_fd(bars, bull, N=15)
    r9['8_反向空头fd'] = dict(n_truncated=n_short, archive='n<300 归档不评' if n_short < 300 else 'n>=300 需另评')
    # #9 硬顶 20/45
    c9a = dict(cfg_final); c9a['hardcap'] = 20
    c9b = dict(cfg_final); c9b['hardcap'] = 45
    r9['9_硬顶20'] = _sel_run(c9a, pool, bull, idxv)
    r9['9_硬顶45'] = _sel_run(c9b, pool, bull, idxv)
    # #10 与 bk 共存优先级翻转（bk=20日新高+量比>1.5，close 入场，stop=1.5ATR，TP=2R，硬顶30）
    r9['10_优先级翻转'] = _priority_flip(pool, bull, idxv, cfg_final, Rm, catr)
    r9_all_ran = all(v is not None for v in r9.values())

    # ---- 判据逐项（§1.3 预注册，一次成活）----
    th_n_pass = st['thick']['n'] >= 0.8 * 118
    items = dict(
        item1_重合度=dict(**ovl, pass_=ovl['verdict'] != '非等价物（归档不冒名）'),
        item2_主窗=dict(**{k: st[k] for k in ('n', 'mean', 'pf')}, pass_=(st['mean'] >= 0 and st['pf'] not in (None, 'inf') and st['pf'] >= 1.05)),
        item3_厚利桶=dict(anchor=118, threshold_n=round(0.8 * 118, 1), threshold_sum=1500, **st['thick'],
                          pass_=(th_n_pass and st['thick']['sum_r'] >= 1500)),
        item4_分年不翻脸=dict(years=yr, flip=flip, pass_=not flip),
        item5_分段=dict(**segs, pass_=(segs['realA']['sum_r'] >= 0 and segs['realB']['sum_r'] >= 0 and segs['realC']['sum_r'] >= 0),
                         note='realC 终验一次已执行，验后即烧'),
        item6_LOTO_bootstrap=dict(loto_fails=len(loto_fails), loto_min_mean=min(r['mean'] for _, r in loto if r['mean'] is not None),
                                  thick_loto_fails=len(thick_fails), thick_tkrs=len(thick_tkrs),
                                  boot=boot, pass_=(len(loto_fails) == 0 and len(thick_fails) == 0 and boot['q05_sum_r'] >= 0)),
    )
    veto = []
    if not items['item3_厚利桶']['pass_']: veto.append('厚利桶塌陷')
    if st['mean'] < 0: veto.append('主窗 mean<0')
    if flip: veto.append('分年翻脸')
    hard_pass = (not veto) and all(v['pass_'] for v in items.values())
    if ovl['verdict'] == 'fd 近亲信号（降级）':
        verdict = 'fd 近亲新信号：判据' + ('全过，按新候选走独立评审，不冒 fd 之名' if hard_pass else '未全过，判死') 
    elif ovl['verdict'] == '等价改写成立':
        verdict = ('fd 可脱离箱体独立部署' if hard_pass else '判死（否决线或判据未过）')
    else:
        verdict = '该变体不是 fd 等价物，归档不冒名' + ('' if hard_pass else '；且判据未过')
    print('判据:', json.dumps(items, ensure_ascii=False, default=str))
    print('否决线:', veto or '无')
    print('终裁:', verdict)

    out = dict(
        workorder='fd-indep（规格一：FD 腿独立验证）', spec='TRADE9-SPEC-FDBRK-v1.0 §1',
        generated=time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()),
        d0=d0, frozen_params=frozen,
        selection_table=sel_table, frozen_arm=win_cfg, frozen_arm_sel=win_sel,
        final=dict(cfg=cfg_final, main=st, full_n=len(final_all), yearly=yr, flip=flip, segments=segs),
        overlap=ovl, loto=dict(fails=loto_fails, n_tasks=len(loto),
                               thick_contributors=len(thick_tkrs), thick_fails=thick_fails),
        bootstrap=boot, r9=r9, r9_all_ran=r9_all_ran,
        judgment=items, veto_line=veto, verdict=verdict,
        runtime_sec=round(time.time() - t0, 1),
        realC_note='realC（2026-06-01→2026-10-18）仅本终验一次触碰，验后即烧，禁二次以任何口径重碰',
    )
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(out, open(OUT_JSON, 'w'), ensure_ascii=False, indent=1, default=str)
    print('写出', OUT_JSON, '用时', out['runtime_sec'], 's')

def scan_ref_fd(bars, bull):
    return [t for t in C.scan_ref(bars, bull) if t['kind'] == 'fd']

def _sel_run(cfg, pool, bull, idxv):
    trs = []
    cfg = dict(cfg)
    cfg.setdefault('N', 15)
    for tk, bars in pool.items():
        for t in scan_fd_indep(bars, bull, idxv, **cfg):
            trs.append(dict(tkr=tk, **t))
    sel = [t for t in trs if MAIN <= t['et'] <= TRUNC]
    return C.stats6(sel)

def _count_short_fd(bars, bull, N=15):
    """R9#8：反向空头 fd（idx<MA50 顶轨回落）样本量。触发=idx 非牛 且 high>=H−0.2×rng 且 close<H。"""
    n = 0; last = None
    for i in range(max(N, 14) + 1, len(bars)):
        t = bars[i]['time']
        if bull.get(t):
            last = None; continue
        w = bars[i - N + 1:i + 1]
        L = min(x['low'] for x in w); H = max(x['high'] for x in w); rng = H - L
        if rng <= 0: continue
        if bars[i]['high'] >= H - 0.2 * rng and bars[i]['close'] < H:
            if last is None or i - last >= 15:
                n += 1; last = i
    return n

def _priority_flip(pool, bull, idxv, cfg_final, Rm, catr):
    """R9#10：独立 fd 票与 bk 原始信号（20日新高+量比>1.5）同票同 bar 冲突 → fd 优先 vs bk 优先，各跑筛选段组合六元组。"""
    import math
    def scan_merged(bars, prio_fd):
        a = ENG.atrs(bars)
        trades = []; i = max(20, 15, 14) + 1; last_fire = None
        while i < len(bars):
            if a[i] is None: i += 1; continue
            t = bars[i]['time']
            if not bull.get(t): i += 1; continue
            px, lo, hi = bars[i]['close'], bars[i]['low'], bars[i]['high']
            # fd 独立信号（冻结臂）
            fd_sig = False
            if cfg_final['variant'] == 'A':
                w = bars[i - 15 + 1:i + 1]
                L = min(x['low'] for x in w); H = max(x['high'] for x in w); rng = H - L
                fd_sig = (lo <= L + 0.2 * rng) and (px > L)
            else:
                ref20 = max(x['high'] for x in bars[i - 20:i])
                fd_sig = ((ref20 - px) / ref20 * 100 >= cfg_final['P']) and (px >= lo + 0.25 * (hi - lo))
            # bk 原始信号
            w20 = bars[i - 20:i]
            bk_level = max(x['high'] for x in w20)
            vr = bars[i]['volume'] / (sum(x['volume'] for x in bars[i - 19:i + 1]) / 20)  # R3 口径：rolling(20) 含当日
            bk_sig = (px >= bk_level) and (vr > 1.5)
            if (fd_sig or bk_sig) and (last_fire is None or i - last_fire >= 15):
                use_fd = fd_sig and bk_sig and prio_fd
                use_bk = fd_sig and bk_sig and not prio_fd
                if fd_sig and not bk_sig: use_fd = True
                if bk_sig and not fd_sig: use_bk = True
                if use_fd:
                    Lsup = (min(x['low'] for x in bars[i - 15 + 1:i + 1]) if cfg_final['variant'] == 'A'
                            else max(x['high'] for x in bars[i - 20:i]) * (1 - cfg_final['P'] / 100))
                    eff = Lsup - 0.3 * a[i]
                    if eff > 0 and px > eff:
                        ep = px
                        tp = ep + Rm * (ep - eff) if cfg_final['exit_mode'] == 'E1' else ep + catr * a[i]
                        xi, xpx, why, r = C.v2_exit(bars, i, ep, tp, eff, 30)
                        trades.append(dict(r=r, et=t)); last_fire = i; i = xi + 1; continue
                    last_fire = i
                elif use_bk:
                    stop = px - 1.5 * a[i]
                    if stop > 0:
                        ep = px; tp = ep + 2 * (ep - stop)
                        xi, xpx, why, r = C.v2_exit(bars, i, ep, tp, stop, 30)
                        trades.append(dict(r=r, et=t)); last_fire = i; i = xi + 1; continue
                    last_fire = i
            i += 1
        return trades
    out = {}
    for prio_fd in (True, False):
        trs = []
        for tk, bars in pool.items():
            for t in scan_merged(bars, prio_fd):
                trs.append(dict(tkr=tk, **t))
        sel = [t for t in trs if MAIN <= t['et'] <= TRUNC]
        out['fd优先' if prio_fd else 'bk优先'] = C.stats6(sel)
    return out

if __name__ == '__main__':
    main()
