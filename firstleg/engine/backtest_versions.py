# -*- coding: utf-8 -*-
"""把 versions/*.json 里保存过的点火变体，统一用「个股口径」重跑。

个股口径 = 剔除 ETF / 杠杆 ETF，其余信号完全一致：
  当日涨幅≥4% 且量≥2×20日中位、站上MA50、价格≥5、dv20≥30M、ATR%≤6%、
  同一天≥3只点火、取涨幅前5、次日开盘入场。

退出/仓位变体来自早前冻结的 versions/*.json；同一批信号、同一套账本，
只换退出或过滤条件，用来判断「有没有哪一版在个股池上胜率和收益都更好」。

  python versions_stock.py
"""
import os
import sys
import json
import inspect
import numpy as np

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
ROOT = os.path.dirname(WORK)
for _p in (os.path.join(ROOT, 'v2'), os.path.join(ROOT, 'v2', 'engine'),
           os.path.join(WORK, 'v2'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
import v2_lib as L  # noqa: E402

START_DATE = '2025-04-01'


def make_sim():
    """在 v2_lib.simulate 上注入：分批止盈 / 保本 / 剩余封顶 / 关火全平。"""
    src = inspect.getsource(L.simulate)
    src = src.replace('def simulate(A, F, RG, sig, p):', 'def sim_x(A, F, RG, sig, p):')
    src = src.replace(
        "    start_i = p.get('start_i', 0)",
        "    start_i = p.get('start_i', 0)\n"
        "    tp1 = p.get('tp1'); f1 = p.get('tp1_frac', 0.5); be1 = p.get('be_after_tp1', False)\n"
        "    tp2 = p.get('tp2'); f2 = p.get('tp2_frac', 0.5)\n"
        "    cap_atr = p.get('cap_atr')\n"
        "    force = p.get('force_days') or set()")
    marker = "            lo, hi = b['l'][i], b['h'][i]\n"
    inject = """            lo, hi = b['l'][i], b['h'][i]
            if i > q['ei'] and lo > q['stop']:
                if cap_atr and q.get('t1') and hi >= q['ep'] + cap_atr * q['atr']:
                    px = q['ep'] + cap_atr * q['atr']
                    pnl_h = q['notional'] * (px / q['ep'] - 1) - q['notional'] * 2 * cost - q['fund']
                    trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl_h / q['eq0'],
                                       why='cap', bars=i - q['ei'], margin=q['margin'],
                                       ret=px / q['ep'] - 1, tier=q.get('tier', 'A')))
                    realized += pnl_h
                    del pos[s]
                    continue
                if tp1 and not q.get('t1') and hi >= q['ep'] + tp1 * q['atr']:
                    px = q['ep'] + tp1 * q['atr']
                    part = q['notional'] * f1
                    fr = part / max(q['notional'], 1e-9)
                    pnl_h = part * (px / q['ep'] - 1) - part * 2 * cost - q['fund'] * fr
                    trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl_h / q['eq0'],
                                       why='tp1', bars=i - q['ei'], margin=q['margin'] * fr,
                                       ret=px / q['ep'] - 1, tier=q.get('tier', 'A')))
                    realized += pnl_h
                    q['fund'] *= (1 - fr)
                    q['notional'] -= part
                    q['margin'] *= (1 - fr)
                    q['t1'] = True
                    if be1:
                        q['stop'] = max(q['stop'], q['ep'])
                if tp2 and not q.get('t2') and hi >= q['ep'] + tp2 * q['atr']:
                    px = q['ep'] + tp2 * q['atr']
                    part = q['notional'] * f2
                    fr = part / max(q['notional'], 1e-9)
                    pnl_h = part * (px / q['ep'] - 1) - part * 2 * cost - q['fund'] * fr
                    trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl_h / q['eq0'],
                                       why='tp2', bars=i - q['ei'], margin=q['margin'] * fr,
                                       ret=px / q['ep'] - 1, tier=q.get('tier', 'A')))
                    realized += pnl_h
                    q['fund'] *= (1 - fr)
                    q['notional'] -= part
                    q['margin'] *= (1 - fr)
                    q['t2'] = True
"""
    assert marker in src
    src = src.replace(marker, inject, 1)
    marker2 = "        # ---- 4. mark to market"
    inject2 = """        # ---- 3b. 关火：按收盘价全部平仓
        if i in force and pos:
            for s in list(pos):
                q = pos[s]; b = A[s]
                px = b['c'][i]
                pnl = q['notional'] * (px / q['ep'] - 1) - q['notional'] * 2 * cost - q['fund']
                trades.append(dict(sym=s, entry=q['ei'], exit=i, pnl=pnl / q['eq0'],
                                   why='shutoff', bars=i - q['ei'], margin=q['margin'],
                                   ret=px / q['ep'] - 1, tier=q.get('tier', 'A')))
                realized += pnl
                del pos[s]
            equity = realized

"""
    assert marker2 in src
    src = src.replace(marker2, inject2 + marker2, 1)
    ns = dict(L.__dict__)
    exec(src, ns)
    return ns['sim_x']


def dd_window(curve, dates, i0):
    peak, best, pi, ti = -1e9, 0.0, i0, i0
    pk = i0
    for i in range(i0, len(curve)):
        if curve[i] > peak:
            peak, pk = curve[i], i
        d = curve[i] / peak - 1
        if d < best:
            best, pi, ti = d, pk, i
    return best * 100


def main():
    sim = make_sim()
    L.CACHE = os.environ.get('V2_CACHE') or os.path.join(ROOT, 'cache_fresh')
    raw, cal, gi = L.load_all(include_lev=True, include_etf=True)
    A = L.align(raw, cal, gi)
    F = L.features(A)
    core = {s: b for s, b in A.items() if s not in L.ETF and s not in L.LEV}
    RG = L.build_regime(core, cal)
    n = len(cal)
    i0 = next(i for i, d in enumerate(cal) if d >= START_DATE)
    months = (np.datetime64(cal[-1]) - np.datetime64(cal[i0])).astype(int) / 30.44

    # 关火信号（个股口径），用于复跑保存过的关火变体
    dec = np.zeros(n); tot = np.zeros(n)
    for s, b in core.items():
        prev = np.concatenate(([np.nan], b['c'][:-1]))
        r = b['c'] / prev - 1
        ok = b['real'] & ~np.isnan(r)
        dec[ok] += (r[ok] < 0); tot[ok] += 1
    decf = np.where(tot > 0, dec / np.maximum(tot, 1), np.nan)
    idx_ret = np.concatenate(([0.0], RG['idx'][1:] / RG['idx'][:-1] - 1))
    shut = (decf >= 0.70) & (idx_ret <= -0.015)
    block5 = np.zeros(n, dtype=bool)
    for i in range(n):
        if any(shut[max(0, i - 5):i]):
            block5[i] = True
    force_days = {i for i in range(n) if shut[i]}

    # 信号池：只做个股，不做 jump[i+1] 未来过滤
    pool = {}
    for i in range(i0, n - 1):
        rows = []
        for s, b in A.items():
            if s in L.ETF or s in L.LEV:
                continue
            f = F[s]
            if not b['real'][i] or i - b['first'] < 210:
                continue
            if b['jump'][i]:
                continue
            if b['c'][i] < 5 or f['dv20'][i] < 30e6:
                continue
            if np.isnan(f['atrp'][i]) or f['atrp'][i] > 0.06:
                continue
            if f['ret1'][i] < 0.04:
                continue
            vm = float(np.median(b['v'][max(0, i - 20):i]))
            if vm <= 0 or b['v'][i] < 2.0 * vm:
                continue
            if not (b['c'][i] > f['ma50'][i]):
                continue
            rows.append((float(f['ret1'][i]), s, float(f['atr'][i])))
        rows.sort(reverse=True)
        pool[i] = rows

    def not_at_high(s, i, gap=0.02):
        c = A[s]['c'][i]
        hi = max(A[s]['c'][max(0, i - 60):i])
        return c <= hi * (1 - gap)

    def make_sig(cfg):
        out = []
        flt = cfg.get('filter')
        for i, rows in pool.items():
            if len(rows) < 3:
                continue
            if cfg.get('block5') and block5[i]:
                continue
            picked = [r for r in rows if flt(r[1], i)] if flt else rows
            for _, s, atr in picked[:5]:
                out.append(dict(sym=s, i=i, score=0.0, atr=atr, close=float(A[s]['c'][i]),
                                ex=dict(sl_atr=cfg.get('sl', 2.5), tp_atr=cfg.get('full_tp'),
                                        hold=cfg.get('hold', 20)),
                                tier='B'))
        return out

    def run(label, cfg):
        sig = make_sig(cfg)
        p = dict(lev=5, margin_pct=0.03, max_pos=8, gross_cap=2.4, start_i=i0)
        for k in ('tp1', 'tp1_frac', 'be_after_tp1', 'tp2', 'tp2_frac', 'cap_atr', 'trail_atr'):
            if k in cfg:
                p[k] = cfg[k]
        if cfg.get('force'):
            p['force_days'] = force_days
        sm = sim(A, F, RG, sig, p)
        tr = [t for t in sm['trades'] if t['entry'] >= i0]
        grp = {}
        for t in tr:
            grp.setdefault((t['sym'], t['entry']), []).append(t)
        pos = {k: sum(x['pnl'] for x in v) for k, v in grp.items()}
        x = np.array(list(pos.values())) if pos else np.array([0.0])
        gp = x[x > 0].sum(); gl = -x[x < 0].sum()
        st = L.stats(sm, i0, n - 1)
        dd = dd_window(sm['curve'], cal, i0)
        top3 = sum(sorted(x, reverse=True)[:3]) / max(gp, 1e-9) * 100
        hit1 = sum(1 for v in grp.values() if any(t['why'] in ('tp1', 'tp2') for t in v))
        r = dict(label=label, n=len(x), per_month=len(x) / months,
                 win=float((x > 0).mean() * 100), pf=float(gp / max(gl, 1e-9)),
                 avg=float(x.mean() * 100), cum=float((st['final'] - 1) * 100),
                 cagr=float(st['cagr']), mdd=float(dd), liq=int(sm['liq']),
                 expo=float(np.nanmean(sm['exposure'][i0:]) * 100),
                 top3=float(top3), hit1=hit1, sig=len(sig), n_sig=sm['n_sig'],
                 cfg={k: v for k, v in cfg.items() if k != 'filter'})
        print('%-30s 仓位%3d %4.1f/月　胜率 %5.1f%%　PF %5.2f　均值 %+5.2f%%　累计 %+7.1f%%'
              '　年化 %6.1f%%　回撤 %5.2f%%　爆仓%d　暴露 %4.1f%%　top3 %4.1f%%'
              % (label, r['n'], r['per_month'], r['win'], r['pf'], r['avg'], r['cum'],
                 r['cagr'], r['mdd'], r['liq'], r['expo'], r['top3']))
        return r

    variants = [
        ('现役 tp2.5平半+余8ATR封顶', dict(tp1=2.5, tp1_frac=0.5, be_after_tp1=False,
                                       cap_atr=8.0, hold=20)),
        ('A3 不止盈（sl2.5/h20）', dict(hold=20)),
        ('A3 + 关火5日', dict(hold=20, block5=True)),
        ('A3S + 关火当日全平+停5日', dict(hold=20, block5=True, force=True)),
        ('C3S sl3.0 + 关火全平+停5日', dict(sl=3.0, hold=20, block5=True, force=True)),
        ('tp1 1.5 平半+保本', dict(tp1=1.5, tp1_frac=0.5, be_after_tp1=True, hold=20)),
        ('tp1 2.0 平半+保本', dict(tp1=2.0, tp1_frac=0.5, be_after_tp1=True, hold=20)),
        ('tp1 2.5 平半+保本', dict(tp1=2.5, tp1_frac=0.5, be_after_tp1=True, hold=20)),
        ('tp1 3.0 平半+保本', dict(tp1=3.0, tp1_frac=0.5, be_after_tp1=True, hold=20)),
        ('tp1 2.0平半 + tp2 4.0平半 + 保本', dict(tp1=2.0, tp1_frac=0.5, be_after_tp1=True,
                                              tp2=4.0, tp2_frac=0.5, hold=20)),
        ('tp2.5 平半（不保本、无封顶）', dict(tp1=2.5, tp1_frac=0.5, be_after_tp1=False, hold=20)),
        ('tp3.0 平半（不保本、无封顶）', dict(tp1=3.0, tp1_frac=0.5, be_after_tp1=False, hold=20)),
        ('tp3.0 平1/3（不保本、持30）', dict(tp1=3.0, tp1_frac=1 / 3, be_after_tp1=False, hold=30)),
        ('全止盈2.5 + sl3.0（点火v1原退出）', dict(full_tp=2.5, sl=3.0, hold=20)),
        ('全止盈2.5 + sl3.0 + 关火5日', dict(full_tp=2.5, sl=3.0, hold=20, block5=True)),
        ('防追高(离60日高≥2%) + 原v1退出 + 关火5日',
         dict(full_tp=2.5, sl=3.0, hold=20, block5=True, filter=not_at_high)),
        ('防追高(离60日高≥2%) + 现役退出',
         dict(tp1=2.5, tp1_frac=0.5, be_after_tp1=False, cap_atr=8.0, hold=20,
              filter=not_at_high)),
    ]

    print('区间 %s → %s（%.1f 个月）　个股口径（剔除 ETF/LEV）　关火日 %d 天'
          % (cal[i0], cal[-1], months, sum(1 for i in range(i0, n) if shut[i])))
    out = [run(label, cfg) for label, cfg in variants]

    # 排序：先看胜率，再看累计
    best_win = max(out, key=lambda r: (r['win'], r['cum']))
    best_cum = max(out, key=lambda r: (r['cum'], r['win']))
    base = out[0]
    print()
    print('胜率最高：%s（%.1f%%，累计 %+.1f%%，回撤 %.2f%%）'
          % (best_win['label'], best_win['win'], best_win['cum'], best_win['mdd']))
    print('累计最高：%s（%+.1f%%，胜率 %.1f%%，回撤 %.2f%%）'
          % (best_cum['label'], best_cum['cum'], best_cum['win'], best_cum['mdd']))
    print('现役基准：%s（%.1f%%，累计 %+.1f%%，回撤 %.2f%%）'
          % (base['label'], base['win'], base['cum'], base['mdd']))

    json.dump(dict(period=[cal[i0], cal[-1]], months=months, results=out),
              open(os.path.join(HERE, 'backtest_versions.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
