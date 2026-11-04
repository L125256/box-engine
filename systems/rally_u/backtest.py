# -*- coding: utf-8 -*-
"""U 平衡 + 集群 A≥3 且 B≥20 · 回测入口（只研究，不下单，不发布）

跑法：
  V2_CACHE=<work>/cache_fresh python backtest.py
输出：
  backtest_report.json（逐笔口径；页面看板另由 board.py 写 build_report.json，两者不覆盖）
  signals.csv
"""
import os
import sys
import json
import csv
import hashlib

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import u_engine as U

WINDOWS = ['2026-01-26', '2026-05-01', '2026-08-01']


def win_stats(rows, lo, hi):
    return U.stats([r for r in rows if lo <= r['entry_date'] < hi])


def main():
    A, F, RG, cal = U.FD.load()
    sig, meta = U.build_signals(A, F, RG, cal)
    print('signals: A raw %d | B raw %d | U %d | asof %s' % (
        meta['nA_raw'], meta['nB_raw'], meta['nU'], meta['asof']))
    # 2026-11-05 加严后的基准（扫描起点固定 220 根，信号从 START_DATE 起）
    if meta['nU'] != 38:
        print('WARNING: nU=%s 与加严基准 38 不一致（改前 A>=3 基准为 49）' % meta['nU'])

    rows = []
    for z in sig:
        r = U.simulate(A, z, gap_open=False)
        if r is None:
            continue
        row = dict(z)
        row.update(r)
        rows.append(row)

    out = dict(asof=meta['asof'], meta=meta)
    out['full'] = U.stats(rows)
    out['h2'] = win_stats(rows, '2025-06-01', '2026-01-01')
    out['y26'] = win_stats(rows, '2026-01-01', '9999')
    print('\ntrade-level:')
    for k in ('full', 'h2', 'y26'):
        s = out[k]
        print('  %-4s n%3d win%5.1f avg%+6.2f pf%6.2f R%+5.2f' % (
            k, s['n'], s['win'], s['avg'], s['pf'], s['avgR']))

    print('\nsignals:')
    for z in rows:
        print('  %-9s %s -> %s risk%5.1f%% ret%+6.2f%% %s/%s' % (
            z['sym'], z['date'], z['entry_date'], z['risk'] * 100,
            z['ret'] * 100, z['why1'], z['why2']))

    out['windows'] = []
    print('\nwindows:')
    for w in WINDOWS:
        r = U.run_window(A, cal, sig, w)
        out['windows'].append(r)
        s = r['stats']
        print('  %s signals%2d taken%2d skipcap%2d | n%2d win%5.1f pf%6.2f ret%+6.2f%% cagr%5.1f%% mdd%5.2f%% eq%.0f' % (
            w, r['signals'], r['taken'], r['skipped_cap'], s['n'], s['win'], s['pf'],
            s['ret'], s['cagr'], s['mdd'], s['final_eq']))

    jp = os.path.join(HERE, 'backtest_report.json')
    blob = json.dumps(out, ensure_ascii=False, indent=1).encode('utf-8')
    open(jp, 'wb').write(blob)
    print('\nwrote %s %d bytes sha256 %s' % (jp, len(blob), hashlib.sha256(blob).hexdigest()))

    sp = os.path.join(HERE, 'signals.csv')
    keys = ['tag', 'sym', 'date', 'entry_date', 'entry', 'stop', 'risk', 'range_pct', 'ret1',
            'breadth', 'concA', 'concB', 'volx', 'dev', 'rsi', 'cpos', 'gap_wash', 'ret', 'why1', 'why2', 'bars']
    with open(sp, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(keys)
        for z in rows:
            w.writerow([round(z[k], 6) if isinstance(z[k], float) else z[k] for k in keys])
    sb = open(sp, 'rb').read()
    print('wrote %s %d bytes sha256 %s' % (sp, len(sb), hashlib.sha256(sb).hexdigest()))


if __name__ == '__main__':
    main()
