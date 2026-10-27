# -*- coding: utf-8 -*-
"""
v2 contract-basis research library. Independent of c1.

Conventions
-----------
- US stock *token perpetuals*, 24/7 daily bars from 导演站.
- Long only. Isolated margin. Funding 0.03%/bar on notional (long pays).
- Fee 0.05% + slippage 0.05% per side (0.20% round trip).
- Liquidation modelled at entry*(1 - 1/lev + MMR), MMR=1.0%, liq fee 0.6% notional.
- Signal at close t -> entry next open. All indicators use only data <= t.

Data hygiene
------------
- Round-trip price-scale artifacts (e.g. 167 -> 658 -> 195) are masked.
- One-way *up* jumps > 40% are back-adjusted (erases fake right-tail gain).
- Down jumps are kept (real crashes must hurt).
- Bars with |ret|>35% are non-enterable; stop/TP is not triggered on that bar.
"""
import json
import os
import math
import numpy as np

CACHE = os.environ.get('V2_CACHE') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'cache_fresh')

# ---------------------------------------------------------------- classification
LEV = {s + 'USDT' for s in (
    'SOXL', 'SOXS', 'TQQQ', 'SQQQ', 'UVXY', 'SPXU', 'SPXS', 'TZA', 'TNA',
    'LABU', 'LABD', 'YINN', 'YANG', 'FNGU', 'FNGD', 'TMF', 'TMV', 'SVIX', 'VIXY',
    'MUU', 'MVLL', 'SNXX', 'KORU', 'KSTR')}
ETF = {s + 'USDT' for s in (
    'SPY', 'QQQ', 'IWM', 'DIA', 'SMH', 'XBI', 'XLE', 'GDX',
    'EWJ', 'EWT', 'EWY', 'EWZ', 'URNM')}

# ---------------------------------------------------------------- loading
def _read(sym):
    with open(os.path.join(CACHE, sym + '.json'), 'r', encoding='utf-8') as f:
        b = json.load(f)
    b = [x for x in b if x.get('close') and x.get('open')]
    b.sort(key=lambda x: x['time'])
    return b


def _repair(dates, o, h, l, c, v):
    """Mask round-trip scale artifacts; make one-way up jumps continuous."""
    n = len(c)
    valid = np.ones(n, dtype=bool)
    lr = np.zeros(n)
    lr[1:] = np.diff(np.log(np.maximum(c, 1e-12)))
    i = 1
    while i < n:
        if not valid[i]:
            i += 1
            continue
        r = lr[i]
        if r > 0.50:
            pre = c[i - 1]
            hit = -1
            for j in range(i + 1, min(n, i + 31)):
                if 0.75 * pre <= c[j] <= 1.25 * pre:
                    hit = j
                    break
            if hit > 0:
                seg = c[i:hit + 1]
                if np.median(seg) / pre > 1.5 or np.median(seg) / pre < 0.67:
                    valid[i:hit] = False          # drop the wrong-scale segment
                    i = hit
                    continue
            # one-way up jump: back-adjust all history before it
            f = c[i] / c[i - 1]
            o[:i] *= f
            h[:i] *= f
            l[:i] *= f
            c[:i] *= f
            lr[1:i + 1] = np.diff(np.log(np.maximum(c[:i + 1], 1e-12)))
            lr[i] = 0.0
        i += 1
    jump = np.abs(lr) > 0.35
    jump[0] = True
    return o, h, l, c, v, valid, jump


def load_all(include_lev=False, include_etf=True):
    files = [f for f in os.listdir(CACHE) if f.endswith('.json') and not f.startswith('_')]
    syms = sorted(f[:-5] for f in files)
    raw = {}
    alld = set()
    for s in syms:
        if not include_lev and s in LEV:
            continue
        if not include_etf and s in ETF:
            continue
        b = _read(s)
        d = [x['time'] for x in b]
        o = np.array([x['open'] for x in b], float)
        h = np.array([x['high'] for x in b], float)
        l = np.array([x['low'] for x in b], float)
        c = np.array([x['close'] for x in b], float)
        v = np.array([x['volume'] for x in b], float)
        o, h, l, c, v, ok, jump = _repair(d, o, h, l, c, v)
        raw[s] = dict(dates=d, o=o, h=h, l=l, c=c, v=v, ok=ok, jump=jump)
        alld.update(d)
    cal = sorted(alld)
    g = {d: i for i, d in enumerate(cal)}
    return raw, cal, g


def align(raw, cal, g):
    """Forward/back-fill each series onto the global calendar."""
    n = len(cal)
    out = {}
    for s, b in raw.items():
        di = np.array([g[d] for d in b['dates']])
        o = np.full(n, np.nan); h = np.full(n, np.nan)
        l = np.full(n, np.nan); c = np.full(n, np.nan); v = np.full(n, 0.0)
        real = np.zeros(n, dtype=bool); jump = np.zeros(n, dtype=bool)
        o[di] = b['o']; h[di] = b['h']; l[di] = b['l']; c[di] = b['c']
        v[di] = b['v']; real[di] = b['ok']; jump[di] = b['jump']
        # fill: backfill head, ffill rest
        first = int(di[0])
        for arr, fill in ((o, np.nan), (h, np.nan), (l, np.nan), (c, np.nan)):
            idx = np.where(~np.isnan(arr))[0]
            if len(idx) == 0:
                continue
            arr[:idx[0]] = arr[idx[0]]
            for k in range(idx[0] + 1, n):
                if np.isnan(arr[k]):
                    arr[k] = arr[k - 1]
        for k in range(n):
            if np.isnan(o[k]):
                o[k] = o[k - 1] if k else 0
            if np.isnan(h[k]):
                h[k] = h[k - 1] if k else 0
            if np.isnan(l[k]):
                l[k] = l[k - 1] if k else 0
            if np.isnan(c[k]):
                c[k] = c[k - 1] if k else 0
        out[s] = dict(o=o, h=h, l=l, c=c, v=v, real=real, jump=jump,
                      first=first, nreal=int(real.sum()), di=di)
    return out


# ---------------------------------------------------------------- indicators
def _roll(a, w, fn='mean'):
    n = len(a)
    out = np.full(n, np.nan)
    if n < w:
        return out
    if fn == 'mean':
        cs = np.concatenate(([0.0], np.cumsum(a)))
        out[w - 1:] = (cs[w:] - cs[:-w]) / w
    elif fn == 'max':
        for i in range(w - 1, n):
            out[i] = a[i - w + 1:i + 1].max()
    elif fn == 'median':
        for i in range(w - 1, n):
            out[i] = np.median(a[i - w + 1:i + 1])
    return out


def _rsi(c, w):
    d = np.diff(c, prepend=c[0])
    up = np.maximum(d, 0.0); dn = np.maximum(-d, 0.0)
    au = _roll(up, w); ad = _roll(dn, w)
    rs = au / np.maximum(ad, 1e-12)
    r = 100 - 100 / (1 + rs)
    r[np.isnan(au)] = np.nan
    return r


def features(A):
    out = {}
    for s, b in A.items():
        o, h, l, c, v = b['o'], b['h'], b['l'], b['c'], b['v']
        n = len(c)
        f = {}
        for w in (5, 10, 20, 50, 80, 100, 200):
            f['ma%d' % w] = _roll(c, w)
        pc = np.concatenate(([c[0]], c[:-1]))
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        f['atr'] = _roll(tr, 14)
        f['atrp'] = f['atr'] / np.maximum(c, 1e-9)
        f['rsi2'] = _rsi(c, 2)
        f['rsi3'] = _rsi(c, 3)
        f['rsi14'] = _rsi(c, 14)
        f['ret1'] = c / np.concatenate(([c[0]], c[:-1])) - 1
        for w in (2, 3, 5, 10, 20, 60):
            f['ret%d' % w] = c / np.concatenate((np.full(w, c[0]), c[:-w])) - 1
        f['dev20'] = c / f['ma20'] - 1
        f['dev50'] = c / f['ma50'] - 1
        f['dev100'] = c / f['ma100'] - 1
        f['hi20'] = _roll(c, 20, 'max')
        f['hi60'] = _roll(c, 60, 'max')
        f['dd20'] = c / f['hi20'] - 1
        f['slope100'] = f['ma100'] / np.concatenate((np.full(20, f['ma100'][0]), f['ma100'][:-20])) - 1
        f['dv20'] = _roll(c * v, 20, 'median')
        f['vol20'] = _roll(f['ret1'] ** 2, 20) ** 0.5
        f['green'] = (c > o).astype(float)
        out[s] = f
    return out


# ---------------------------------------------------------------- regime
def build_regime(A, cal):
    """Equal-weight return index of tradable stocks + breadth."""
    n = len(cal)
    syms = list(A)
    R = np.full((n, len(syms)), np.nan)
    for j, s in enumerate(syms):
        b = A[s]
        c = b['c']; real = b['real']
        prev = np.concatenate(([np.nan], c[:-1]))
        r = c / prev - 1
        r[~real] = np.nan
        r[b['first']] = np.nan
        R[:, j] = r
    cnt = np.sum(~np.isnan(R), axis=1)
    with np.errstate(all='ignore'):
        ew = np.nanmean(R, axis=1)
    ew = np.where(np.isnan(ew), 0.0, ew)
    # chain only when coverage is decent
    idx = np.full(n, np.nan)
    lvl = 1.0
    started = False
    for i in range(n):
        if cnt[i] >= 60:
            if not started:
                started = True
                idx[i] = lvl
            else:
                lvl *= (1 + ew[i])
                idx[i] = lvl
        elif started:
            idx[i] = lvl
    # forward fill
    last = np.nan
    for i in range(n):
        if np.isnan(idx[i]):
            idx[i] = last
        else:
            last = idx[i]
    idx = np.where(np.isnan(idx), 1.0, idx)
    ma50 = _roll(idx, 50)
    ma100 = _roll(idx, 100)
    gate = idx > ma50
    gate100 = idx > ma100
    return dict(idx=idx, ma50=ma50, ma100=ma100, gate=gate, gate100=gate100,
                cnt=cnt, ew=ew, dates=cal)


# breadth computed separately (needs features)
def breadth(A, F, cal):
    n = len(cal)
    up = np.zeros(n); tot = np.zeros(n)
    for s in A:
        b = A[s]; ma = F[s]['ma50']
        ok = b['real'] & (np.arange(n) - b['first'] >= 60) & ~np.isnan(ma)
        up[ok] += (b['c'][ok] > ma[ok])
        tot[ok] += 1
    br = np.where(tot > 0, up / np.maximum(tot, 1), np.nan)
    return br, tot


# ---------------------------------------------------------------- signal generation
def make_signals(A, F, RG, BR, p, start_i=None, end_i=None):
    """
    p keys:
      trend_ma (100/200), slope_min, dev20_max, rsi2_max, ret3_max,
      atrp_max, min_dv, min_price, require_gate, use_breadth,
      ma_touch (None/50), touch_tol
    Returns list of dict(sym, i, score, atr, close).
    """
    cal = RG['dates']; n = len(cal)
    gate = RG['gate100'] if p.get('gate_mode', 'ma50') == 'ma100' else RG['gate']
    sig = []
    start_i = 200 if start_i is None else start_i
    end_i = n - 2 if end_i is None else end_i
    trend = p.get('trend_ma', 100)
    slope_min = p.get('slope_min', 0.0)
    dev_max = p.get('dev20_max', 0.0)
    rsi_max = p.get('rsi2_max', 25.0)
    ret3_max = p.get('ret3_max', 9.9)
    atrp_max = p.get('atrp_max', 0.06)
    min_dv = p.get('min_dv', 5e6)
    min_px = p.get('min_price', 3.0)
    use_gate = p.get('require_gate', True)
    use_br = p.get('use_breadth', False)
    br_min = p.get('breadth_min', 0.40)
    ma_touch = p.get('ma_touch', None)
    tol = p.get('touch_tol', 0.01)
    score_mode = p.get('score', 'rsi')
    green_only = p.get('green_only', False)
    rev_confirm = p.get('rev_confirm', False)
    min_drop5 = p.get('min_drop5', None)
    ma50_gt_ma100 = p.get('ma50_gt_ma100', False)
    max_dev50 = p.get('max_dev50', 9.9)
    crash_thr = p.get('regime_ret5_min', None)
    idx = RG['idx']
    for i in range(start_i, end_i + 1):
        if use_gate and not gate[i]:
            continue
        if use_br and (np.isnan(BR[i]) or BR[i] < br_min):
            continue
        if crash_thr is not None and i >= 5 and idx[i] / max(idx[i - 5], 1e-9) - 1 < crash_thr:
            continue
        for s, b in A.items():
            if not b['real'][i]:
                continue
            if i - b['first'] < p.get('warmup', 210):
                continue
            if b['jump'][i] or b['jump'][i + 1]:
                continue
            f = F[s]
            c = b['c'][i]
            if c < min_px:
                continue
            if f['dv20'][i] < min_dv:
                continue
            if f['atrp'][i] > atrp_max or np.isnan(f['atrp'][i]):
                continue
            if c < f['ma%d' % trend][i]:
                continue
            if f['slope100'][i] < slope_min:
                continue
            if f['dev20'][i] > dev_max:
                continue
            if f['rsi2'][i] > rsi_max:
                continue
            if f['ret3'][i] > ret3_max:
                continue
            if green_only and not (c > b['o'][i]):
                continue
            if rev_confirm and not (c > b['c'][i - 1]):
                continue
            if min_drop5 is not None and f['ret5'][i] > min_drop5:
                continue
            if ma50_gt_ma100 and not (f['ma50'][i] > f['ma100'][i]):
                continue
            if f['dev50'][i] > max_dev50:
                continue
            if ma_touch == 50:
                if not (f['ma50'][i] * (1 - tol) <= c <= f['ma50'][i] * (1 + tol)):
                    continue
            if score_mode == 'rsi':
                sc = -f['rsi2'][i]
            elif score_mode == 'dev':
                sc = -f['dev20'][i]
            elif score_mode == 'depth':
                sc = -f['ret5'][i]
            else:
                sc = 0.0
            sig.append(dict(sym=s, i=i, score=float(sc), atr=float(f['atr'][i]),
                            close=float(c), rsi2=float(f['rsi2'][i]),
                            dev20=float(f['dev20'][i]), ex=p.get('sig_exit'), tier=p.get('tier', 'A')))
    sig.sort(key=lambda x: (x['i'], -x['score']))
    return sig


# ---------------------------------------------------------------- single-trade eval
def eval_trade(b, i, entry_i, atr, sl_atr, tp_atr, hold, ma_exit=None, f=None):
    """Return pct pnl (before costs), exit reason, bars held, MFE/MAE."""
    n = len(b['c'])
    ep = b['o'][entry_i]
    if ep <= 0:
        return None
    stop = ep - sl_atr * atr
    tp = ep + tp_atr * atr if tp_atr else None
    mfe = 0.0; mae = 0.0
    end = min(n - 1, entry_i + hold)
    for k in range(entry_i, end + 1):
        if b['jump'][k]:
            continue
        lo, hi = b['l'][k], b['h'][k]
        mfe = max(mfe, hi / ep - 1)
        mae = min(mae, lo / ep - 1)
        if k > entry_i:
            if b['o'][k] <= stop:
                return dict(pnl=b['o'][k] / ep - 1, why='stop_gap', bars=k - entry_i,
                            mfe=mfe, mae=mae)
            if tp and b['o'][k] >= tp:
                return dict(pnl=b['o'][k] / ep - 1, why='tp_gap', bars=k - entry_i,
                            mfe=mfe, mae=mae)
        if lo <= stop and (tp is None or hi < tp):
            return dict(pnl=stop / ep - 1, why='stop', bars=k - entry_i, mfe=mfe, mae=mae)
        if tp and hi >= tp and lo > stop:
            return dict(pnl=tp / ep - 1, why='tp', bars=k - entry_i, mfe=mfe, mae=mae)
        if tp and lo <= stop and hi >= tp:
            return dict(pnl=stop / ep - 1, why='stop_both', bars=k - entry_i, mfe=mfe, mae=mae)
        if ma_exit and k > entry_i and b['c'][k] > f['ma%d' % ma_exit][k]:
            return dict(pnl=b['c'][k] / ep - 1, why='ma', bars=k - entry_i, mfe=mfe, mae=mae)
    return dict(pnl=b['c'][end] / ep - 1, why='time', bars=end - entry_i, mfe=mfe, mae=mae)


def agg_trades(rows):
    if not rows:
        return dict(n=0)
    p = np.array([r['pnl'] for r in rows])
    w = p[p > 0]; l = p[p <= 0]
    gp = float(w.sum()); gl = float(-l.sum())
    top = np.sort(p)[::-1]
    k = max(1, int(math.ceil(0.05 * len(p))))
    return dict(
        n=len(p), win=float((p > 0).mean() * 100),
        avg=float(p.mean() * 100), med=float(np.median(p) * 100),
        payoff=float(w.mean() / max(1e-9, -l.mean())) if len(l) else 99.0,
        pf=float(gp / max(1e-9, gl)),
        avg_win=float(w.mean() * 100) if len(w) else 0.0,
        avg_loss=float(l.mean() * 100) if len(l) else 0.0,
        top5=float(top[:k].sum() / max(1e-9, gp) * 100),
        bars=float(np.mean([r['bars'] for r in rows])),
        mfe=float(np.mean([r['mfe'] for r in rows]) * 100),
        mae=float(np.mean([r['mae'] for r in rows]) * 100),
    )


# ---------------------------------------------------------------- portfolio sim
def simulate(A, F, RG, sig, p):
    """
    Contract-style portfolio sim.
    p: lev, margin_pct, max_pos, gross_cap, sl_atr, tp_atr, hold, ma_exit
    """
    cal = RG['dates']; n = len(cal)
    lev = p.get('lev', 5.0)
    margin_pct = p.get('margin_pct', 0.02)
    max_pos = p.get('max_pos', 10)
    gross_cap = p.get('gross_cap', 1.5)
    cost = p.get('cost_side', 0.001)
    funding = p.get('funding', 0.0003)
    mmr = p.get('mmr', 0.01)
    liq_fee = p.get('liq_fee', 0.006)
    sl_atr = p.get('sl_atr', 2.5); tp_atr = p.get('tp_atr', None); hold = p.get('hold', 10)
    ma_exit = p.get('ma_exit', None)
    be_trigger = p.get('be_trigger', None)
    trail_atr = p.get('trail_atr', None)
    start_i = p.get('start_i', 0)

    by_day = {}
    for s in sig:
        by_day.setdefault(s['i'], []).append(s)

    equity = 1.0
    realized = 1.0
    pos = {}            # sym -> dict
    pending = []        # entries for tomorrow
    trades = []
    curve = np.full(n, np.nan)
    liquidations = 0
    exposure = np.zeros(n)
    n_sig = 0
    dbg = dict(pending=0, dup=0, bad=0, slots=0, stopdist=0, room=0, exec=0)

    for i in range(start_i, n):
        # ---- 1. gap exits / liquidation at open
        for s in list(pos):
            q = pos[s]; b = A[s]
            if b['jump'][i]:
                continue
            op = b['o'][i]
            if op <= q['liq']:
                pnl = -q['margin'] - q['notional'] * liq_fee
                trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl / equity,
                                   why='liq', bars=i - q['ei'], margin=q['margin'], ret=-1.0/lev-liq_fee, tier=q.get('tier','A')))
                realized += pnl; equity = realized
                liquidations += 1
                del pos[s]
                continue
            if op <= q['stop']:
                pnl = q['notional'] * (op / q['ep'] - 1) - q['notional'] * 2 * cost - q['fund']
                trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl / q['eq0'],
                                   why='stop_gap', bars=i - q['ei'], margin=q['margin'], ret=op/q['ep']-1, tier=q.get('tier','A')))
                realized += pnl; equity = realized
                del pos[s]
                continue
            if q['tp'] and op >= q['tp']:
                pnl = q['notional'] * (op / q['ep'] - 1) - q['notional'] * 2 * cost - q['fund']
                trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl / q['eq0'],
                                   why='tp_gap', bars=i - q['ei'], margin=q['margin'], ret=op/q['ep']-1, tier=q.get('tier','A')))
                realized += pnl; equity = realized
                del pos[s]

        # ---- 2. entries at open (signals may wait 1-2 bars for a weekday)
        todays = [x for x in pending if x['ei'] == i]
        pending = [x for x in pending if x['ei'] > i]
        if todays:
            dbg['pending'] += len(todays)
            cand = [x for x in todays if x['sym'] not in pos]
            cand.sort(key=lambda x: -x['score'])
            for x in cand:
                if len(pos) >= max_pos:
                    dbg['slots'] += 1
                    break
                s = x['sym']; b = A[s]
                if s in pos:
                    dbg['dup'] += 1
                    continue
                if b['jump'][i] or not b['real'][i]:
                    dbg['bad'] += 1
                    continue
                ep = b['o'][i]
                if ep <= 0:
                    dbg['bad'] += 1
                    continue
                ex = x.get('ex') or {}
                slx = ex.get('sl_atr', sl_atr)
                tpx = ex.get('tp_atr', tp_atr)
                holdx = ex.get('hold', hold)
                maxx = ex.get('ma_exit', ma_exit)
                stop = ep - slx * x['atr']
                if stop <= 0 or (ep - stop) / ep > 0.5:
                    dbg['stopdist'] += 1
                    continue
                notional = margin_pct * equity * lev
                gross = sum(q['notional'] for q in pos.values())
                room = gross_cap * equity - gross
                if room <= 1e-9:
                    dbg['room'] += 1
                    continue
                notional = min(notional, room)
                if notional < 0.01 * equity:
                    dbg['room'] += 1
                    continue
                margin = notional / lev
                liq = ep * (1 - 1.0 / lev + mmr)
                pos[s] = dict(ei=i, ep=ep, stop=stop, tp=(ep + tpx * x['atr']) if tpx else None,
                              notional=notional, margin=margin, eq0=equity, fund=0.0,
                              atr=x['atr'], liq=liq, sig=x, hold=holdx, ma_exit=maxx, tier=x.get('tier','A'))
                n_sig += 1
                dbg['exec'] += 1
            dbg['dup'] += len(pending) - len(cand)

        # ---- 3. intraday stop/tp, time/ma exit
        for s in list(pos):
            q = pos[s]; b = A[s]
            if i == q['ei']:
                q['fund'] += q['notional'] * funding
            else:
                q['fund'] += q['notional'] * funding
            if b['jump'][i]:
                continue
            lo, hi = b['l'][i], b['h'][i]
            exit_px = None; why = None
            if lo <= q['stop']:
                exit_px = q['stop']; why = 'stop'
            elif q['tp'] and hi >= q['tp']:
                exit_px = q['tp']; why = 'tp'
            elif q.get('ma_exit') and i > q['ei'] and b['c'][i] > F[s]['ma%d' % q['ma_exit']][i]:
                exit_px = b['c'][i]; why = 'ma'
            elif i >= q['ei'] + q['hold']:
                exit_px = b['c'][i]; why = 'time'
            if exit_px is not None:
                pnl = q['notional'] * (exit_px / q['ep'] - 1) - q['notional'] * 2 * cost - q['fund']
                trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl / q['eq0'],
                                   why=why, bars=i - q['ei'], margin=q['margin'], ret=exit_px/q['ep']-1, tier=q.get('tier','A')))
                realized += pnl
                del pos[s]
            else:
                # ratchet stop at bar close, effective next bar (conservative)
                if trail_atr and hi >= q['ep'] + 1.0 * q['atr']:
                    q['stop'] = max(q['stop'], hi - trail_atr * q['atr'])
                elif be_trigger and hi >= q['ep'] + be_trigger * q['atr']:
                    q['stop'] = max(q['stop'], q['ep'])

        # ---- 4. mark to market
        mtm = 0.0
        for s, q in pos.items():
            mtm += q['notional'] * (A[s]['c'][i] / q['ep'] - 1) - q['notional'] * 2 * cost - q['fund']
        equity = realized + mtm
        curve[i] = equity
        exposure[i] = sum(q['notional'] for q in pos.values()) / max(equity, 1e-9)

        # ---- 5. queue today's signals for the next weekday open
        if i < n - 1:
            for x in by_day.get(i, []):
                b = A[x['sym']]
                e = -1
                for k in range(i + 1, min(n, i + 4)):
                    if b['real'][k] and not b['jump'][k]:
                        import datetime
                        if datetime.date.fromisoformat(cal[k]).weekday() < 5:
                            e = k
                            break
                if e < 0:
                    continue
                if any(y['sym'] == x['sym'] and y['ei'] == e for y in pending):
                    continue
                pending.append(dict(sym=x['sym'], ei=e, atr=x['atr'], score=x['score'], ex=x.get('ex'), tier=x.get('tier','A')))

    # close remaining at last close
    if pos:
        i = n - 1
        for s, q in list(pos.items()):
            cp = A[s]['c'][i]
            pnl = q['notional'] * (cp / q['ep'] - 1) - q['notional'] * 2 * cost - q['fund']
            trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl / q['eq0'],
                               why='eod', bars=i - q['ei'], margin=q['margin'], ret=cp/q['ep']-1, tier=q.get('tier','A')))
            realized += pnl
        equity = realized
        curve[i] = equity

    # fill curve
    last = 1.0
    for i in range(n):
        if np.isnan(curve[i]):
            curve[i] = last
        else:
            last = curve[i]
    return dict(curve=curve, trades=trades, liq=liquidations, exposure=exposure,
                n_sig=n_sig, dates=cal, dbg=dbg)


# ---------------------------------------------------------------- metrics
def stats(sim, start_i=None, end_i=None):
    cal = sim['dates']
    cv = sim['curve']
    n = len(cv)
    s = 0 if start_i is None else start_i
    e = n - 1 if end_i is None else end_i
    eq = cv[s:e + 1]
    final = eq[-1] / eq[0]
    days = max(1, (np.datetime64(cal[e]) - np.datetime64(cal[s])).astype(int))
    cagr = final ** (365.0 / days) - 1
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    mdd = float(-dd.min() * 100)
    dr = np.diff(eq) / eq[:-1]
    sharpe = float(dr.mean() / max(1e-9, dr.std()) * math.sqrt(365)) if len(dr) > 1 else 0.0
    tr = [t for t in sim['trades'] if t['entry'] >= s and t['exit'] <= e]
    ex = np.array([t['pnl'] for t in tr]) if tr else np.array([0.0])
    wins = ex[ex > 0]; losses = ex[ex <= 0]
    gp = float(wins.sum()); gl = float(-losses.sum())
    top = np.sort(ex)[::-1]
    k = max(1, int(math.ceil(0.05 * len(ex))))
    return dict(
        final=float(final), cagr=float(cagr * 100), mdd=mdd, sharpe=sharpe,
        n=len(tr), win=float((ex > 0).mean() * 100) if tr else 0.0,
        payoff=float(wins.mean() / max(1e-9, -losses.mean())) if len(losses) and len(wins) else 0.0,
        pf=float(gp / max(1e-9, gl)), avg=float(ex.mean() * 100) if tr else 0.0,
        top5=float(top[:k].sum() / max(1e-9, gp) * 100) if gp > 0 else 0.0,
        liq=sim['liq'], expo=float(np.nanmean(sim['exposure'][s:e + 1]) * 100),
        days=days,
    )


def yearly(sim, start_i=None):
    cal = sim['dates']; cv = sim['curve']; n = len(cv)
    s = 0 if start_i is None else start_i
    out = {}
    years = sorted({cal[i][:4] for i in range(s, n)})
    for y in years:
        idx = [i for i in range(s, n) if cal[i][:4] == y]
        i0, i1 = idx[0], idx[-1]
        base = cv[i0 - 1] if i0 > 0 else 1.0
        out[y] = (cv[i1] / base - 1) * 100
    return out


if __name__ == '__main__':
    raw, cal, g = load_all(include_lev=False, include_etf=False)
    print('symbols', len(raw), 'calendar', len(cal), cal[0], cal[-1])
    A = align(raw, cal, g)
    F = features(A)
    RG = build_regime(A, cal)
    print('gate days', int(RG['gate'][300:].sum()), '/', len(cal) - 300)
