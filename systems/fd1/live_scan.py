# -*- coding: utf-8 -*-
"""FD-1 盘中/收盘预演：对指定缓存最后一根做条件检查。

  python live_scan.py [cache_dir]        # 默认用 cache_live_merged（含未收盘尾根）
  python live_scan.py ../cache_fresh     # 只看已收全的日线

输出：严格通过六组条件的候选（含 E/止损/止盈/数量/保证金/到期），
以及差 1–2 项条件的最近名单。盘中尾根不是正式信号，收盘定稿才算。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import strategy
import v2_lib as L
from board import fmt_row, EQUITY0

CST = timezone(timedelta(hours=8))


def is_closed(day):
    d = datetime.strptime(day[:10], '%Y-%m-%d').replace(tzinfo=CST)
    return datetime.now(CST) >= d + timedelta(days=1, hours=8)


def fmt_atrp(v):
    return 'NA' if np.isnan(v) else '%.1f%%' % (v * 100)


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WORK, 'cache_live_merged')
    A, F, RG, cal = strategy.load(cache)
    i = len(cal) - 1
    day = cal[i]
    print('缓存 %s ｜ 最后一根 %s ｜ %s' % (
        os.path.basename(cache.rstrip('\\/')), day,
        '已收全' if is_closed(day) else '未收盘（盘中预演，收盘定稿为准）'))

    cand = strategy._eligible(A, F, i)
    print('\n严格通过：%d 只' % len(cand))
    for x in cand:
        r = fmt_row(x, EQUITY0, day)
        print('  %-9s E %.2f  止损 %.2f  止盈 %.2f  数量 %.2f  保证金 %.0f  到期 %s ｜ RSI2 %.1f  偏离 %+.1f%%  ATR%% %s'
              % (r['sym'], r['close'], r['stop'], r['tp'], r['qty'], r['margin'], r['expiry'],
                 r['rsi2'], r['dev20'] * 100, fmt_atrp(x['atrp'])))

    rows = []
    for s, b in A.items():
        if s in L.ETF or s in L.LEV:
            continue
        if not b['real'][i] or i - b['first'] < 210 or b['jump'][i]:
            continue
        f = F[s]
        c = float(b['c'][i])
        miss = []
        if not (c > f['ma100'][i]):
            miss.append('未站上MA100')
        if f['slope100'][i] < 0:
            miss.append('MA100斜率<0')
        if f['dev20'][i] > strategy.DEV20_MAX:
            miss.append('偏离 %+.1f%%（需≤-5%%）' % (f['dev20'][i] * 100))
        if f['rsi2'][i] > strategy.RSI2_MAX:
            miss.append('RSI2 %.1f（需≤30）' % f['rsi2'][i])
        if np.isnan(f['atrp'][i]) or f['atrp'][i] > strategy.ATR_MAX:
            miss.append('ATR%% %s（需≤6%%）' % fmt_atrp(f['atrp'][i]))
        if c < strategy.MIN_PX or f['dv20'][i] < strategy.MIN_DV:
            miss.append('价格/流动性')
        if len(miss) <= 2:
            rows.append((len(miss), float(f['dev20'][i]), s, c,
                         float(f['rsi2'][i]), float(f['atrp'][i]), miss))
    rows.sort(key=lambda r: (r[0], r[1]))
    print('\n最近名单（差 1–2 项）：%d 只' % len(rows))
    for n, dev, s, c, rsi, atrp, miss in rows[:12]:
        print('  %-9s 差%d项  收盘 %.2f  RSI2 %4.1f  偏离 %+5.1f%%  ATR%% %-6s ｜ %s'
              % (s, n, c, rsi, dev * 100, fmt_atrp(atrp), '、'.join(miss)))


if __name__ == '__main__':
    main()
