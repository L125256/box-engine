# -*- coding: utf-8 -*-
"""Live Board: what to trade today, with stop/target/size, plus a drift check.

Computes both bases side by side:
  base = v2   : index > MA50
  cand = v2.1 : index > MA50 and 5-day smoothed breadth >= 45%
Reads the same frozen rules as v2_final.py, rebuilds the backtest, and writes
the 'board' and 'health' blocks into v2_page.json. Deterministic; no network.
"""
import os, sys, json, datetime
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v2_lib as L
from v2_final import A_RULES, dedupe, START, window

C_PROFILE = dict(lev=5, margin_pct=0.04, max_pos=12, gross_cap=2.5)
LEV = 5
MARGIN_PCT = 0.04
GROSS_CAP = 2.5
SL_ATR = 2.5
TP_ATR = 2.0
HOLD = 10
COST_RT = 0.002      # 0.05% fee + 0.05% slippage per side
FUND_DAY = 0.0003    # 0.03% per bar on notional
BR_MIN = 0.45
BR_WIN = 5
EQUITY_DEFAULT = 10000
MMR = 0.01                 # maintenance margin rate
LIQ_PCT = (1.0 / LEV - MMR) * 100      # 19% adverse move to the 5x isolated liq line
MAX_STOP_PCT = SL_ATR * A_RULES['atrp_max'] * 100  # 11.25% price stop at the ATR cap


def next_weekday(d):
    x = datetime.date.fromisoformat(d) + datetime.timedelta(days=1)
    while x.weekday() >= 5:
        x += datetime.timedelta(days=1)
    return x.isoformat()


def closed_streak(a, start):
    cur = 0
    for i in range(len(a) - 1, start - 1, -1):
        if not a[i]:
            cur += 1
        else:
            break
    best = cur2 = 0
    end = None
    for i in range(start, len(a)):
        if not a[i]:
            cur2 += 1
            if cur2 > best:
                best, end = cur2, i
        else:
            cur2 = 0
    return cur, best, end


def trade_stat(ts):
    if not ts:
        return dict(n=0, win=0.0, pf=0.0, avg=0.0, sum=0.0)
    p = np.array([t['pnl'] for t in ts])
    w = p[p > 0]; l = p[p < 0]
    pf = float(w.sum() / abs(l.sum())) if len(l) and abs(l.sum()) > 1e-12 else 99.0
    return dict(n=len(p), win=round(100 * float((p > 0).mean()), 1),
                pf=round(pf, 2), avg=round(float(p.mean() * 100), 2),
                sum=round(float(p.sum() * 100), 2))


def build_version(A, F, RG, BR, gate, i, cal):
    """One basis: simulation, entry rows, environment, drift check."""
    n = len(cal)
    RGx = dict(RG); RGx['gate'] = gate
    sig = dedupe(L.make_signals(A, F, RGx, BR, A_RULES))
    sig_last = [x for x in sig if x['i'] == i]
    sim = L.simulate(A, F, RGx, sig, dict(C_PROFILE))
    is_open = bool(gate[i])

    entry_rows = []
    if is_open:
        for x in sig_last:
            s = x['sym']
            entry_rows.append(row_common(s, float(x['atr']), float(A[s]['c'][i]), F, i))

    cur_closed, best_closed, best_end = closed_streak(gate, START)
    env = dict(
        idx=round(float(RG['idx'][i]), 3), ma50=round(float(RG['ma50'][i]), 3),
        gap=round(float(RG['idx'][i] / RG['ma50'][i] - 1) * 100, 2),
        idx_to_gate=round(float((RG['ma50'][i] / RG['idx'][i] - 1) * 100), 2),
        br=round(float(BR[i]) * 100, 1), br5=round(float(BR5[i]) * 100, 1),
        br_gap=round(BR_MIN * 100 - float(BR5[i]) * 100, 1),
        gate=is_open, base_gate=bool(base_gate[i]),
        closed_days=cur_closed, longest_closed=best_closed,
        longest_end=cal[best_end] if best_end is not None else None,
        participants=int(RG['cnt'][i]),
    )

    # ---- drift / health
    tr = sorted(sim['trades'], key=lambda t: t['exit'])
    h = dict(t10=trade_stat(tr[-10:]), t20=trade_stat(tr[-20:]), t40=trade_stat(tr[-40:]),
             last130=dict(ret=round(float(sim['curve'][n - 1] / sim['curve'][n - 130] - 1) * 100, 2),
                          n=window(sim, cal[n - 130], cal[n - 1])['n'],
                          expo=round(float(np.nanmean(sim['exposure'][n - 130:])) * 100, 1)),
             gate_pass60=round(float(gate[n - 60:].mean()) * 100, 1),
             gate_pass20=round(float(gate[n - 20:].mean()) * 100, 1),
             last_trade=dict(sym=tr[-1]['sym'], exit=cal[tr[-1]['exit']],
                             pnl=round(float(tr[-1]['pnl'] * 100), 2)) if tr else None)
    t20 = h['t20']
    if t20['n'] < 10:
        level, verdict = 'obs', '样本不足，继续观察'
    elif t20['win'] < 45 or t20['pf'] < 1.0:
        level, verdict = 'stop', '暂停开新仓，重新验证'
    else:
        level, verdict = 'ok', '正常'
    h['verdict'] = dict(level=level, text=verdict)

    st = [t for t in sim['trades'] if t['why'].startswith('stop')]
    risk = dict(n=len(sim['trades']), stop_exits=len(st), liq=int(sim['liq']),
                worst_price_pct=round(min(t['ret'] for t in st) * 100, 2) if st else None,
                worst_eq_pct=round(min(t['pnl'] for t in st) * 100, 2) if st else None,
                max_stop_pct=round(MAX_STOP_PCT, 2), liq_pct=round(LIQ_PCT, 1))

    # circuit-breaker audit: how often the hard line and watch line would have fired
    p = np.array([t['pnl'] for t in tr])
    hits = half = 0
    fwd_half = []
    for k in range(20, len(p)):
        seg = p[k - 20:k]
        w = float((seg > 0).mean())
        pf = float(seg[seg > 0].sum() / abs(seg[seg < 0].sum())) if (seg < 0).any() else 99.0
        if w < 0.45 or pf < 1.0:
            hits += 1
        elif w < 0.55 or pf < 1.3:
            half += 1
            fwd_half.append(float(p[k:k + 20].sum()) if len(p[k:k + 20]) else np.nan)
    fwd_half = [v for v in fwd_half if not np.isnan(v)]
    h['audit'] = dict(pause_hits=hits, half_hits=half,
                      half_fwd_avg=round(float(np.mean(fwd_half)) * 100, 2) if fwd_half else None,
                      half_fwd_pos=round(float((np.array(fwd_half) > 0).mean()) * 100, 0) if fwd_half else None,
                      n_all=len(p))

    return dict(env=env, entry=dict(n=len(entry_rows), rows=entry_rows), risk=risk), h


def lev_audit(A, F, RG, BR, gate, cal):
    """Same signals, fees and funding; only leverage / notional change.

    Group '名义 20%' holds notional per trade at 20% of equity and adjusts the
    margin rate, so every row should be identical. Group '保证金 4%' holds the
    margin rate and lets leverage scale notional, which is the real risk dial.
    """
    s0 = min(START, len(cal) - 2)
    RGx = dict(RG); RGx['gate'] = gate
    sig = dedupe(L.make_signals(A, F, RGx, BR, A_RULES))
    rows = []

    def one(group, lev, mp):
        sim = L.simulate(A, F, RGx, sig,
                         dict(lev=lev, margin_pct=mp, max_pos=12, gross_cap=2.5))
        st = L.stats(sim, s0, len(cal) - 1)
        rows.append(dict(group=group, lev=lev,
                         notional_pct=round(mp * lev * 100, 1),
                         n=st['n'], win=round(st['win'], 1), pf=round(st['pf'], 2),
                         cagr=round(st['cagr'], 1), mdd=round(st['mdd'], 2),
                         liq=st['liq']))

    for lev, mp in ((1, 0.20), (3, 0.20 / 3), (5, 0.04)):
        one('名义 20%', lev, mp)
    for lev, mp in ((1, 0.04), (3, 0.04), (5, 0.04)):
        one('保证金 4%', lev, mp)
    return dict(rows=rows)


def main():
    global BR5, base_gate
    raw, cal, g = L.load_all(include_lev=False, include_etf=False)
    A = L.align(raw, cal, g)
    F = L.features(A)
    RG = L.build_regime(A, cal)
    BR, _ = L.breadth(A, F, cal)
    BR0 = np.where(np.isnan(BR), 0.0, BR)
    BR5 = L._roll(BR0, BR_WIN)
    n = len(cal)
    i = n - 1
    asof = cal[i]

    base_gate = RG['idx'] > RG['ma50']
    cand_gate = base_gate & (BR5 >= BR_MIN)
    vb, hb = build_version(A, F, RG, BR, base_gate, i, cal)
    vc, hc = build_version(A, F, RG, BR, cand_gate, i, cal)

    la = lev_audit(A, F, RG, BR, cand_gate, cal)
    a0 = la['rows'][0]; b0 = la['rows'][3]; b2 = la['rows'][5]
    la['note'] = (f"同一批信号回放：名义固定 20% 时，1x / 3x / 5x 的 {a0['n']} 笔结果逐笔一致"
                  f"（胜率 {a0['win']:.1f}%、PF {a0['pf']:.2f}、年化 {a0['cagr']:.1f}%、"
                  f"回撤 {a0['mdd']:.2f}%、爆仓 {a0['liq']}）——杠杆只决定占用多少保证金，"
                  f"不改变盈亏；1x 那行需 20% 保证金/只，12 只时保证金不够，仅作口径对照。"
                  f"保证金固定 4% 时，杠杆把名义从 4% 抬到 20%，"
                  f"年化 {b0['cagr']:.1f}%→{b2['cagr']:.1f}%，"
                  f"回撤 {b0['mdd']:.2f}%→{b2['mdd']:.2f}%。"
                  f"10x 起爆仓距离 9%，已小于 {MAX_STOP_PCT:.2f}% 的最大止损，不进实盘。")

    # ---- funnel + near misses over the latest bar (shared by both bases)
    cond = ('price', 'liq', 'trend', 'slope', 'dev', 'rsi', 'atrp')
    pass_cnt = {k: 0 for k in cond}
    all_pass = 0
    near = []
    for s in A:
        b = A[s]; f = F[s]
        if not b['real'][i] or b['jump'][i]:
            continue
        c = float(b['c'][i]); atr = float(f['atr'][i])
        dv = float(f['dv20'][i]); r2 = float(f['rsi2'][i])
        dev = float(f['dev20'][i]); atrp = atr / c
        ma100 = float(f['ma100'][i]); slp = float(f['slope100'][i])
        if np.isnan(atr) or np.isnan(dv) or np.isnan(ma100) or np.isnan(slp):
            continue
        ok = dict(
            price=c >= 5,
            liq=dv >= 30e6,
            trend=c > ma100,
            slope=slp > 0,
            dev=dev <= A_RULES['dev20_max'],
            rsi=r2 <= A_RULES['rsi2_max'],
            atrp=atrp <= A_RULES['atrp_max'],
        )
        for k, v in ok.items():
            if v:
                pass_cnt[k] += 1
        misses = []
        if not ok['price']:
            misses.append('价格 %.2f（需 ≥ 5）' % c)
        if not ok['liq']:
            misses.append('20 日成交额 %.1fM（需 ≥ 30M）' % (dv / 1e6))
        if not ok['trend']:
            misses.append('未站上 MA100')
        if not ok['slope']:
            misses.append('MA100 斜率为负')
        if not ok['dev']:
            misses.append('20 日偏离 %+.2f%%（需 ≤ −4.00%%）' % (dev * 100))
        if not ok['rsi']:
            misses.append('RSI2 %.1f（需 ≤ 25）' % r2)
        if not ok['atrp']:
            misses.append('ATR%% %.2f%%（需 ≤ 4.50%%）' % (atrp * 100))
        if not misses:
            all_pass += 1
        # watchlist only shows tradable names: price and liquidity must already pass.
        # Setups that pass everything stay listed with an empty miss list; the page
        # labels them "waiting for the gate" or drops them when the gate is open.
        watch = bool(ok['price'] and ok['liq']) and len(misses) <= 2
        if watch:
            r = row_common(s, atr, c, F, i)
            r['miss'] = misses
            r['n_miss'] = len(misses)
            near.append(r)

    near.sort(key=lambda r: (r['n_miss'], r['rsi2'], r['dev20']))
    near = near[:10]

    funnel = dict(n=len(A), pass_counts=pass_cnt, all_pass=all_pass)

    board = dict(
        asof=asof, next_entry=next_weekday(asof), active='cand',
        near=dict(n=len(near), rows=near),
        funnel=funnel,
        v=dict(base=vb, cand=vc),
        lev_audit=la,
        rules=dict(lev=LEV, margin_pct=round(MARGIN_PCT * 100, 1),
                   gross_cap=GROSS_CAP, max_pos=C_PROFILE['max_pos'],
                   sl_atr=SL_ATR, tp_atr=TP_ATR, hold=HOLD,
                   cost_rt_pct=round(COST_RT * 100, 2),
                   fund_day_pct=round(FUND_DAY * 100, 3),
                   br_min=round(BR_MIN * 100, 1), br_win=BR_WIN,
                   mmr_pct=MMR * 100, liq_pct=round(LIQ_PCT, 1),
                   max_stop_pct=round(MAX_STOP_PCT, 2),
                   atrp_max_pct=round(A_RULES['atrp_max'] * 100, 2)),
        equity_default=EQUITY_DEFAULT,
    )
    health = dict(base=hb, cand=hc)

    with open(os.path.join(HERE, 'v2_page.json'), encoding='utf-8') as f:
        page = json.load(f)
    page['board'] = board
    page['health'] = health
    with open(os.path.join(HERE, 'v2_page.json'), 'w', encoding='utf-8') as f:
        json.dump(page, f, ensure_ascii=False, separators=(',', ':'))

    for tag, vv, hh in (('v2  ', vb, hb), ('v2.1', vc, hc)):
        e = vv['env']
        print(tag, 'gate', e['gate'], 'closed', e['closed_days'],
              'longest', e['longest_closed'], 'entry', vv['entry']['n'],
              't20', hh['t20'], 'pause_hits', hh['audit']['pause_hits'],
              'gate60', hh['gate_pass60'], 'last130', hh['last130'])
    print('asof', asof, 'next', board['next_entry'], 'near', len(near),
          'all_pass', all_pass, 'funnel', pass_cnt)
    print('near top', [(r['sym'], r['n_miss'], r['miss']) for r in near[:5]])


def row_common(sym, x_atr, close, F, i):
    stop = close - SL_ATR * x_atr
    tp = close + TP_ATR * x_atr
    stop_pct = (stop / close - 1) * 100
    atrp = x_atr / close
    liq_gap = LIQ_PCT - abs(stop_pct)
    return dict(sym=sym, close=round(close, 3), atr=round(x_atr, 3),
                stop=round(stop, 3), tp=round(tp, 3),
                stop_pct=round(stop_pct, 2),
                tp_pct=round((tp / close - 1) * 100, 2),
                rsi2=round(float(F[sym]['rsi2'][i]), 1),
                dev20=round(float(F[sym]['dev20'][i]) * 100, 2),
                dv20=round(float(F[sym]['dv20'][i]) / 1e6, 1),
                atrp_pct=round(atrp * 100, 2),
                stop_eq_pct=round(stop_pct * LEV * MARGIN_PCT, 2),
                liq_gap_pp=round(liq_gap, 1),
                liq_used_pct=round(abs(stop_pct) / LIQ_PCT * 100, 0),
                stop_exec=bool(atrp <= A_RULES['atrp_max'] and abs(stop_pct) < 0.8 * LIQ_PCT))


if __name__ == '__main__':
    main()
