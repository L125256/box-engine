# -*- coding: utf-8 -*-
"""U 平衡 + 集群≥3 · 当日/最近信号扫描（只研究，不下单）。

跑法：
  V2_CACHE=<work>/cache_fresh python scan.py
输出：
  最近 21 根内的信号；没有就打印“当前空仓”。
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import u_engine as U


def main():
    A, F, RG, cal = U.FD.load()
    sig, meta = U.build_signals(A, F, RG, cal)
    last_i = len(cal) - 1
    recent = [z for z in sig if z['i'] >= last_i - 20]
    print('asof %s | A raw %d | B raw %d | U %d | %s' % (
        meta['asof'], meta['nA_raw'], meta['nB_raw'], meta['nU'],
        '最近 21 根有信号' if recent else '当前空仓'))
    if not recent:
        last = max(sig, key=lambda z: z['i']) if sig else None
        if last:
            print('最后一个信号：%s %s（信号日）-> %s（入场）' % (
                last['sym'], last['date'], last['entry_date']))
        return
    print('\n最近信号：')
    for z in sorted(recent, key=lambda z: (z['i'], z['sym'])):
        print('  %-9s %s -> %s | %s | entry %.4f | stop %.4f | risk %.1f%% | range %.1f%% | ret1 %+.1f%% | concA %d' % (
            z['sym'], z['date'], z['entry_date'], z['tag'], z['entry'], z['stop'],
            z['risk'] * 100, z['range_pct'] * 100, z['ret1'] * 100, z['concA']))


if __name__ == '__main__':
    main()
