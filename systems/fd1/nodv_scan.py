# -*- coding: utf-8 -*-
"""FD-1 去掉 20 日均额门槛的对照：当前候选 + 全样本/真实段统计。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import strategy
import board


def main():
    strategy.MIN_DV = 0.0
    A, F, RG, cal = strategy.load()
    st = strategy.state_today(A, F, RG, cal)
    print('FD-1 去掉 dv20 门槛（min_dv=0）｜ asof %s ｜ 深踩 %d ｜ 突破 %d' % (
        st['asof'], st['n_deep'], st['n_brk']))
    for x in st['deep']:
        lv = strategy.levels(x['close'], x['atr'])
        print('  %-9s E %.2f  ATR %.2f  RSI2 %.1f  偏离 %+.1f%%  ATR%% %.1f%%  → 止损 %.2f  止盈 %.2f'
              % (x['sym'], x['close'], x['atr'], x['rsi2'], x['dev20'] * 100, x['atrp'] * 100,
                 lv['stop'], lv['tp']))

    print('  双通道正式统计固定 30M，见 board.py / build_report.json。')


if __name__ == '__main__':
    main()
