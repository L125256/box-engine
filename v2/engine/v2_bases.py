# -*- coding: utf-8 -*-
"""Compare non-MA50 regime bases with the frozen v2 entry/exit.

Same universe, same entry (deep pullback + RSI2 + ATR + liquidity),
same contract sizing (C profile). Only the regime base changes.
"""
import os, sys, json, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v2_lib as L
from v2_final import A_RULES, dedupe, START

C_PROFILE = dict(lev=5, margin_pct=0.04, max_pos=12, gross_cap=2.5)


def roll_max(a, w):
    return L._roll(a, w, 'max')


def shift(a, k):
    out = np.full(len(a), np.nan)
    if k < len(a):
        out[k:] = a[:-k]
    return out


def pct_rank_trailing(a, win=252, min_n=60):
    n = len(a)
    out = np.full(n, np.nan)
    for i in range(n):
        w = a[max(0, i - win + 1):i + 1]
        w = w[~np.isnan(w)]
        if len(w) >= min_n and not np.isnan(a[i]):
            out[i] = float((w <= a[i]).mean())
    return out


def main():
    raw, cal, g = L.load_all(include_lev=False, include_etf=False)
    A = L.align(raw, cal, g)
    F = L.features(A)
    RG = L.build_regime(A, cal)
    BR, _ = L.breadth(A, F, cal)
    idx = RG['idx']
    n = len(cal)

    ma50, ma80, ma100, ma200 = RG['ma50'], L._roll(idx, 80), RG['ma100'], L._roll(idx, 200)
    ret = np.concatenate(([np.nan], idx[1:] / idx[:-1] - 1))
    vol20 = np.sqrt(L._roll(np.nan_to_num(ret, nan=0.0) ** 2, 20))
    volp = pct_rank_trailing(vol20, 252, 60)
    slope50 = ma50 / shift(ma50, 10) - 1
    slope100 = ma100 / shift(ma100, 10) - 1
    dd60 = idx / roll_max(idx, 60) - 1
    BR0 = np.where(np.isnan(BR), 0.0, BR)
    br5 = L._roll(BR0, 5)
    br10 = L._roll(BR0, 10)

    def gt(a, b):
        return np.asarray(a) > np.asarray(b)

    variants = [
        ('ma50', '指数 > MA50（现行）', gt(idx, ma50)),
        ('ma80', '指数 > MA80', gt(idx, ma80)),
        ('ma100', '指数 > MA100', gt(idx, ma100)),
        ('ma200', '指数 > MA200', gt(idx, ma200)),
        ('ma50_slope', 'MA50 上方 且 MA50 斜率>0', gt(idx, ma50) & gt(slope50, 0)),
        ('ma100_slope', 'MA100 上方 且 MA100 斜率>0', gt(idx, ma100) & gt(slope100, 0)),
        ('ma100_dd8', 'MA100 上方 且 距60日高点 > -8%', gt(idx, ma100) & gt(dd60, -0.08)),
        ('br50', '广度 ≥ 50%（单一地基）', gt(br5, 0.50)),
        ('br55', '广度 ≥ 55%（单一地基）', gt(br5, 0.55)),
        ('br60', '广度 ≥ 60%（单一地基）', gt(br5, 0.60)),
        ('ma100_br50', 'MA100 上方 且 广度 ≥ 50%', gt(idx, ma100) & gt(br5, 0.50)),
        ('ma50_br50', 'MA50 上方 且 广度 ≥ 50%', gt(idx, ma50) & gt(br5, 0.50)),
        ('vol80', '20日波动 < 252日 80分位（单一地基）', gt(volp, -1) & (volp < 0.80)),
        ('ma100_vol80', 'MA100 上方 且 波动 < 80分位', gt(idx, ma100) & (volp < 0.80)),
        ('ma50_vol80', 'MA50 上方 且 波动 < 80分位', gt(idx, ma50) & (volp < 0.80)),
        ('br50_vol80', '广度 ≥ 50% 且 波动 < 80分位', gt(br5, 0.50) & (volp < 0.80)),
        ('ma80_br50', 'MA80 上方 且 广度 ≥ 50%', gt(idx, ma80) & gt(br5, 0.50)),
        ('ma200_br50', 'MA200 上方 且 广度 ≥ 50%', gt(idx, ma200) & gt(br5, 0.50)),
        ('slope_only', '仅 MA100 斜率>0（不看价格位置）', gt(slope100, 0)),
        ('none', '不设地基（始终可开仓）', np.ones(n, dtype=bool)),
    ]

    # 2025 / 2026 slices
    def slice_i(y0, y1):
        a = next(i for i in range(START, n) if cal[i] >= y0)
        b = max(i for i in range(n) if cal[i] <= y1)
        return a, b

    out = []
    for key, desc, gate in variants:
        RGx = dict(RG)
        RGx['gate'] = gate
        sig = L.make_signals(A, F, RGx, BR, A_RULES)
        sig = dedupe(sig)
        p = dict(C_PROFILE)
        sim = L.simulate(A, F, RGx, sig, p)
        st = L.stats(sim, START, n - 1)
        y = L.yearly(sim, START)
        a25, b25 = slice_i('2025-01-01', '2025-12-31')
        a26, b26 = slice_i('2026-01-01', '2026-12-31')
        s25 = L.stats(sim, a25, b25)
        s26 = L.stats(sim, a26, b26)
        # days where the base allows new entries
        on = float(np.mean(gate[START:n - 1]) * 100)
        out.append(dict(key=key, desc=desc, final=st['final'], cagr=st['cagr'], mdd=st['mdd'],
                        sharpe=st['sharpe'], n=st['n'], win=st['win'], payoff=st['payoff'],
                        pf=st['pf'], expo=st['expo'], top5=st['top5'], liq=st['liq'],
                        y2025=round(float(y.get('2025', 0)), 1),
                        y2026=round(float(y.get('2026', 0)), 1),
                        pf2025=round(s25['pf'], 2), pf2026=round(s26['pf'], 2),
                        win2025=round(s25['win'], 1), win2026=round(s26['win'], 1),
                        n2025=s25['n'], n2026=s26['n'], gate_on=round(on, 1)))

    out.sort(key=lambda r: -r['pf'])
    hdr = ('%-14s %6s %6s %6s %6s %4s %6s %5s %5s %5s %5s %5s %4s' %
           ('base', 'final', 'cagr', 'mdd', 'pf', 'n', 'win', 'pay', '2025', '2026', 'pf25', 'pf26', 'on%'))
    print(hdr)
    print('-' * len(hdr))
    for r in out:
        print('%-14s %6.2f %6.1f %6.1f %6.2f %4d %6.1f %5.2f %5.1f %5.1f %5.2f %5.2f %4.0f' % (
            r['key'], r['final'], r['cagr'], r['mdd'], r['pf'], r['n'], r['win'], r['payoff'],
            r['y2025'], r['y2026'], r['pf2025'], r['pf2026'], r['gate_on']))
    json.dump(out, open(os.path.join(HERE, 'v2_bases.json'), 'w', encoding='utf-8'), indent=1)
    print('\nwrote v2_bases.json')


if __name__ == '__main__':
    main()
