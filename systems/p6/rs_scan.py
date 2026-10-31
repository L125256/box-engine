# -*- coding: utf-8 -*-
"""单兵相对强度 · 当前扫描（P6 原型）。

规则（仅个股条件，无市场闸门、无批次要求）：
  站上 MA50 且 MA50>MA100；MA50 10 日斜率 >=0；MA100 20 日斜率 >=0
  20 日收益 > 0（绝对强度，不要求跑赢指数）
  回踩：收盘相对 MA20 偏离 <= -2%；RSI2 <= 40
  过滤：价格 >=5、20 日均额 >=30M、ATR% <=6%
出场：+0.8 ATR 止盈、-1.5 ATR 止损、最多 5 根日线
仓位：5x、单笔保证金 3% 权益、最多 16 仓、毛敞口 2.5 倍（回测另测 5%×10）
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
ROOT = os.path.dirname(WORK)
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'),
           os.path.join(ROOT, 'v2', 'engine'),
           os.path.join(HERE, 'fastdip'), os.path.join(WORK, 'fastdip'),
           os.path.join(WORK, 'fd1'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import v2_lib as L
from strategy import load

EQUITY = 10000
MARGIN = 0.03
LEV = 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-dv', action='store_true', help='去掉 20 日均额 30M 门槛')
    a = ap.parse_args()
    min_dv = 0 if a.no_dv else 30e6
    A, F, RG, cal = load()
    i = len(cal) - 1
    print('asof %s ｜ 额门槛 %s ｜ 指数 %.3f / MA50 %.3f（%+.2f%%）—— 本策略不看这个'
          % (cal[i], '无' if not min_dv else '30M', RG['idx'][i], RG['ma50'][i],
             (RG['idx'][i] / RG['ma50'][i] - 1) * 100))
    out = []
    watch = []
    for s, b in A.items():
        if s in L.ETF or s in L.LEV:
            continue
        if not b['real'][i] or i - b['first'] < 220 or b['jump'][i]:
            continue
        f = F[s]
        c = float(b['c'][i])
        if c < 5 or f['dv20'][i] < min_dv:
            continue
        if np.isnan(f['atrp'][i]) or f['atrp'][i] > 0.06:
            continue
        ma50, ma100 = f['ma50'][i], f['ma100'][i]
        if np.isnan(ma50) or np.isnan(ma100) or np.isnan(f['slope100'][i]):
            continue
        ms50 = ma50 / f['ma50'][i - 10] - 1 if i >= 10 and not np.isnan(f['ma50'][i - 10]) else np.nan
        if np.isnan(ms50) or not (c > ma50 > ma100) or ms50 < 0 or f['slope100'][i] < 0:
            continue
        if f['ret20'][i] <= 0:
            continue
        row = dict(sym=s, close=c, atr=float(f['atr'][i]), rsi2=float(f['rsi2'][i]),
                   dev20=float(f['dev20'][i]), ret20=float(f['ret20'][i]),
                   atrp=float(f['atrp'][i]), ma20=float(f['ma20'][i]),
                   ma50=float(ma50), ma100=float(ma100))
        if f['dev20'][i] > -0.02 or f['rsi2'][i] > 40:
            watch.append(row)
            continue
        out.append(row)
    out.sort(key=lambda x: x['rsi2'])
    print('当前候选：%d 只' % len(out))
    for x in out:
        e = x['close']
        stop = e - 1.5 * x['atr']
        tp = e + 0.8 * x['atr']
        notional = EQUITY * MARGIN * LEV
        qty = notional / e
        print('  %-9s E %.2f  止损 %.2f  止盈 %.2f  数量 %.2f  保证金 %.0f ｜ RSI2 %.1f  偏离 %+.1f%%  20日 %+.1f%%  ATR%% %.1f%%  MA50 %.2f / MA100 %.2f'
              % (x['sym'], e, stop, tp, qty, EQUITY * MARGIN, x['rsi2'], x['dev20'] * 100,
                 x['ret20'] * 100, x['atrp'] * 100, x['ma50'], x['ma100']))

    watch.sort(key=lambda x: -x['ret20'])
    print('\n强势观察（趋势/强度都过，但还没回踩到 -2%% / RSI2 40）：%d 只' % len(watch))
    for x in watch[:10]:
        print('  %-9s 收盘 %.2f  20日 %+5.1f%%  偏离 %+5.1f%%  RSI2 %4.1f  ATR%% %.1f%% ｜ 参考回踩价 %.2f 下方'
              % (x['sym'], x['close'], x['ret20'] * 100, x['dev20'] * 100, x['rsi2'],
                 x['atrp'] * 100, x['ma20'] * 0.98))


if __name__ == '__main__':
    main()
