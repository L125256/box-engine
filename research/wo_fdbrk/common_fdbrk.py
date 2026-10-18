#!/usr/bin/env python3
# common_fdbrk.py — wo_fdbrk 共用件（D0 对拍门 + 状态变量库 + V2 出场引擎 + bootstrap/LOTO）
# D0 强制：import/复用 /tmp/eng_wt_rc/eng_final.py 的 load_pool/build_idx_bull/scan/collect/atrs。
# 唯一数据态 /tmp/box_cache（snapshot_20261019, md5=33c8b9ec54d17537c3b7f1f6d8d47463）。
import json, os, sys, random, statistics
sys.path.insert(0, '/tmp/eng_wt_rc')
import eng_final as ENG  # 权威引擎（V2 可实现口径）

CACHE = '/tmp/box_cache'
SNAP_MD5 = '33c8b9ec54d17537c3b7f1f6d8d47463'
SNAP_VER = 'snapshot_20261019'
FEE = 0.03                      # %/bar，口径基线承接
MAIN = '2025-06-01'             # 主窗=入场日 et>=2025-06-01
TRUNC = '2026-05-31'            # 筛选段截断线（realC 隔离）
REALA = ('2025-06-02', '2026-05-31')
REALB = ('2024-04-01', '2025-06-01')
REALC0 = '2026-06-01'

_pool, _bull, _idxv = None, None, None

def pool_bull():
    """复用 eng_final.load_pool / build_idx_bull（D0 逐字要求）。另存 idx 数值序列供弱牛带消融。"""
    global _pool, _bull, _idxv
    if _pool is None:
        _pool, _dropped = ENG.load_pool(CACHE)
        _bull = ENG.build_idx_bull(_pool)
        # idx 数值序列（与 build_idx_bull 同式：池等权收盘均价 + MA50），用于 σ/弱牛带
        all_dates = sorted({b['time'] for bars in _pool.values() for b in bars})
        idxv = {}
        for dt in all_dates:
            vals = [b['close'] for bars in _pool.values() for b in bars if b['time'] == dt]
            if vals:
                idxv[dt] = sum(vals) / len(vals)
        dts = sorted(idxv)
        idxm = {}
        for i, dt in enumerate(dts):
            w = dts[max(0, i - 49):i + 1]
            ma = sum(idxv[d] for d in w) / len(w)
            sig = (sum((idxv[d] - ma) ** 2 for d in w) / len(w)) ** 0.5
            idxm[dt] = (idxv[dt], ma, sig)   # (值, MA50, σ50)
        _idxv = idxm
    return _pool, _bull, _idxv

# ---------------------------------------------------------------- scan_ref：eng_final.scan 逐字拷贝（仅加日志字段 tp/eff/disp/aei，信号与 R 零改动）
def scan_ref(bars, idx_above_ma):
    N, K, M, B, X, E, Q, AMAX = ENG.N, ENG.K, ENG.M, ENG.B, ENG.X, ENG.E, ENG.Q, ENG.AMAX
    a = ENG.atrs(bars)
    state = 'seek'; streak = 0; box = None; pos = None; trades = []
    for i in range(max(N, 14) + 1, len(bars)):
        if a[i] is None: continue
        px = bars[i]['close']
        if pos:
            hold = i - pos['ei']
            if px <= pos['eff'] or px >= pos['tp'] or hold >= Q:
                if px >= pos['tp']:
                    xpx = max(pos['tp'], bars[i]['open'])
                elif px <= pos['eff']:
                    xpx = min(pos['eff'], bars[i]['open'])
                else:
                    xpx = px
                j = i
                while j < len(bars) - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                    j += 1; xpx = bars[j]['open']
                r = (xpx - pos['ep']) / pos['ep'] * 100 - FEE * (j - pos['ei'])
                trades.append(dict(ep=pos['ep'], ei=pos['ei'], xi=j, xc=round(xpx, 4), kind=pos['kind'], r=r,
                                   why='止盈' if px >= pos['tp'] else ('止损' if px <= pos['eff'] else '30天期满'),
                                   tp=pos['tp'], eff=pos['eff'], disp=pos['disp'], aei=pos['aei']))
                pos = None
            continue
        if state == 'seek':
            w = bars[i - N + 1:i + 1]
            Hh = max(x['high'] for x in w); Ll = min(x['low'] for x in w); rng = Hh - Ll
            if rng > 0 and rng < K * a[i]: streak += 1
            else: streak = 0
            if streak >= M: state = 'locked'; box = [Ll, Hh, i, '']; streak = 0
            continue
        L, H, li, fired = box; rng = H - L; age = i - li
        sig = None
        if 'L' not in fired and px > H + B * a[i]: sig = ('bk', px)
        elif ('L' not in fired and idx_above_ma.get(bars[i]['time']) and bars[i]['low'] <= L + E * rng): sig = ('fd', px)
        if sig is None and (px > H + X * a[i] or px < L - X * a[i] or age > AMAX): state = 'seek'; box = None; continue
        if sig:
            kind, ep = sig; box[3] += 'L'
            tp = H + a[i] if kind == 'bk' else H
            disp = ep - 1.5 * a[i] if kind == 'bk' else L
            eff = disp - 0.3 * a[i]
            risk = (ep - disp) / ep * 100
            if eff > 0 and risk <= 8.0:
                pos = dict(ep=ep, tp=tp, disp=disp, eff=eff, ei=i, kind=kind, aei=a[i])
    return trades

def d0_gate():
    """D0 对拍门：①引擎复用声明 ②fd 锚复现 ③3 标的×3 交易日 scan_ref vs eng_final.scan maxdiff ④快照 md5。"""
    import hashlib
    h = hashlib.md5()
    for f in sorted(os.listdir(CACHE)):   # 账本口径 = md5sum * | md5sum（逐文件 hex+两空格+文件名+换行）
        h.update((hashlib.md5(open(os.path.join(CACHE, f), 'rb').read()).hexdigest() + '  ' + f + '\n').encode())
    md5 = h.hexdigest()
    pool, bull, idxv = pool_bull()
    # 锚复现：top1 参数 fd 腿主窗
    trs, _ = ENG.collect(dict(N=15, k=7.5, m=2, e=0.3), pool, bull)
    fd = [t for t in trs if t['kind'] == 'fd' and t['et'] >= MAIN]
    fd_sum = sum(t['r'] for t in fd)
    thick = [t for t in fd if t['r'] >= 8]
    anchor = dict(n=len(fd), sum_r=round(fd_sum, 2), thick_n=len(thick), thick_sum=round(sum(t['r'] for t in thick), 2))
    anchor_ok = (len(fd) == 673 and abs(fd_sum - 723.64) < 0.05 and len(thick) == 118 and abs(sum(t['r'] for t in thick) - 2019.76) < 0.05)
    # scan_ref 对拍：3 标的 × 各取 3 个交易日
    maxdiff = 0.0
    tkrs = sorted(pool)[:3]
    for tk in tkrs:
        t_ref = scan_ref(pool[tk], bull)
        t_eng = ENG.scan(pool[tk], bull)['trades']
        k1 = {(t['ei'], t['kind']): t['r'] for t in t_ref}
        k2 = {(t['ei'], t['kind']): t['r'] for t in t_eng}
        assert k1.keys() == k2.keys(), f'{tk} 键集不一致'
        for k in k1:
            maxdiff = max(maxdiff, abs(k1[k] - k2[k]))
    return dict(snapshot_ver=SNAP_VER, snapshot_md5=md5, md5_ok=(md5 == SNAP_MD5),
                pool_n=len(pool), fd_anchor=anchor, anchor_ok=anchor_ok,
                scan_ref_maxdiff=maxdiff, reused=['load_pool', 'build_idx_bull', 'scan', 'collect', 'atrs'])

# ---------------------------------------------------------------- V2 出场引擎（eng_final 口径逐字：V1 收盘判定触发 + V2 可实现价顺延 + 费 0.03%/bar）
def v2_exit(bars, ei, ep, tp, eff, hardcap=30):
    n = len(bars)
    for i in range(ei + 1, n):
        px = bars[i]['close']; hold = i - ei
        if px <= eff or px >= tp or hold >= hardcap:
            if px >= tp: xpx = max(tp, bars[i]['open'])
            elif px <= eff: xpx = min(eff, bars[i]['open'])
            else: xpx = px
            j = i
            while j < n - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                j += 1; xpx = bars[j]['open']
            r = (xpx - ep) / ep * 100 - FEE * (j - ei)
            return j, xpx, ('止盈' if px >= tp else ('止损' if px <= eff else '硬顶')), r
    i = n - 1; px = bars[i]['close']
    return i, px, '数据末', (px - ep) / ep * 100 - FEE * (i - ei)

# ---------------------------------------------------------------- 六元组/分年/分段/判据工具
def stats(trades):
    rs = [t['r'] for t in trades]; n = len(rs)
    if n == 0:
        return dict(n=0, median=None, win_pct=None, mean=None, pf=None, sum_r=0.0, thick=dict(n=0, sum_r=0.0))
    wins = [r for r in rs if r > 0]; losses = [r for r in rs if r <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None
    th = [r for r in rs if r >= 8]
    return dict(n=n, median=round(statistics.median(rs), 4), win_pct=round(len(wins) / n * 100, 2),
                mean=round(sum(rs) / n, 4), pf=round(pf, 4) if pf is not None else 'inf',
                sum_r=round(sum(rs), 2), thick=dict(n=len(th), sum_r=round(sum(th), 2)))

def stats6(trades, thick_r=8):
    rs = [t['r'] for t in trades]; n = len(rs)
    if n == 0:
        return dict(n=0, median=None, win_pct=None, mean=None, pf=None, sum_r=0.0, thick=None)
    wins = [r for r in rs if r > 0]; losses = [r for r in rs if r <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None
    th = [r for r in rs if r >= thick_r]
    return dict(n=n, median=round(statistics.median(rs), 4), win_pct=round(len(wins) / n * 100, 2),
                mean=round(sum(rs) / n, 4), pf=round(pf, 4) if pf is not None else 'inf',
                sum_r=round(sum(rs), 2),
                thick=dict(r_ge=thick_r, n=len(th), sum_r=round(sum(th), 2)))

def yearly_flip(trades):
    """分年（按 et 归年）：任一 n>=30 的年份 mean<0 → 翻脸"""
    out = {}
    for y in ('2024', '2025', '2026'):
        rs = [t['r'] for t in trades if t['et'][:4] == y]
        out[y] = dict(n=len(rs), mean=round(sum(rs) / len(rs), 4) if rs else None, sum_r=round(sum(rs), 2))
    flip = any(v['n'] >= 30 and v['mean'] is not None and v['mean'] < 0 for v in out.values())
    return out, flip

def segments(trades):
    def seg(a, b):
        rs = [t['r'] for t in trades if a <= t['et'] <= b]
        return dict(n=len(rs), sum_r=round(sum(rs), 2))
    return dict(realA=seg(*REALA), realB=seg(*REALB), realC=seg(REALC0, '9999-12-31'))

def stationary_boot(daily, reps=1000, mean_block=10, seed=42):
    """日块 stationary bootstrap（平均块长 10，循环缠绕）。daily=[(date,val)] 按日排序。
    返回 (q05, p_le0, dist)。"""
    vals = [v for _, v in daily]; n = len(vals)
    if n == 0: return None, None, []
    rnd = random.Random(seed)
    dist = []
    for _ in range(reps):
        tot = 0.0; pos = rnd.randrange(n)
        while pos < n:
            L = max(1, int(rnd.expovariate(1.0 / mean_block)))
            for k in range(L):
                tot += vals[(pos + k) % n]
            pos += L
        dist.append(tot)
    dist.sort()
    q05 = dist[int(0.05 * len(dist))]
    p = sum(1 for x in dist if x <= 0) / len(dist)
    return q05, p, dist

def loto_mean(main_trades, key='tkr'):
    """去一留一（按 key 分组重聚合）：返回 (min_mean, fails, n_groups)。"""
    groups = {}
    for t in main_trades:
        groups.setdefault(t[key], []).append(t['r'])
    if not groups: return None, [], 0
    tot = sum(t['r'] for t in main_trades); n = len(main_trades)
    fails = []; means = []
    for g, rs in groups.items():
        m = (tot - sum(rs)) / (n - len(rs))
        means.append(m)
        if m < 0: fails.append(dict(group=g, mean=round(m, 4)))
    return round(min(means), 4), fails, len(groups)
