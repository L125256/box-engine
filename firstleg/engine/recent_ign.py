# -*- coding: utf-8 -*-
"""批量点火：最近逐日点火家数（全部 / 站上 MA50 / 是否成批）。

从 2026-09-01 起逐根打印，用来核对「一个月没有单子」期间是
完全没有点火，还是有个别点火但不足 3 只的批次门槛。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import strategy as S


def main():
    A, F, RG, cal = S.load()
    n = len(cal)
    rows = []
    for i in range(n):
        if cal[i] < '2026-09-01':
            continue
        ign = S._eligible(A, F, i, n)
        above = [x for x in ign if x['above50']]
        rows.append((cal[i], ign, above))

    print('逐日点火（2026-09-01 → %s）' % cal[-1])
    for d, ign, above in rows:
        if not ign:
            continue
        flag = '批次开火' if len(above) >= S.MIN_BATCH else ('未成批' if above else '全在 MA50 下')
        names = '、'.join('%s %+.1f%%' % (x['sym'], x['ret1'] * 100) for x in ign)
        print('  %s  全部 %d ｜ 站上 MA50 %d ｜ %s ｜ %s' % (d, len(ign), len(above), flag, names))

    batch = [r for r in rows if len(r[2]) >= S.MIN_BATCH]
    ign_days = [r for r in rows if r[1]]
    above_days = [r for r in rows if r[2]]
    print('\n汇总：%d 个交易日，%d 天有点火，%d 天有站上 MA50 的点火，%d 天成批' % (
        len(rows), len(ign_days), len(above_days), len(batch)))
    if batch:
        print('最近成批：%s（%d 只）' % (batch[-1][0], len(batch[-1][2])))
    if above_days:
        print('最近有站上 MA50 点火：%s（%d 只）' % (above_days[-1][0], len(above_days[-1][2])))
    if ign_days:
        print('最近有点火（不论 MA50）：%s（%d 只）' % (ign_days[-1][0], len(ign_days[-1][1])))


if __name__ == '__main__':
    main()
