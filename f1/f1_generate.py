#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
f1_generate.py — F1 状态页生成器（幂等，可 cron）
数据引擎：/workspace/repo_ready/engine_f1/f1_signal.py（v1 锁定，sha256 见 f1_live.json）
输出：/workspace/f1_web/f1_live.json（index.html 消费）
复现：PYTHONHASHSEED=42 python3 f1_generate.py
cron 建议：25 9 * * 1-5 python3 /workspace/f1_web/f1_generate.py >> /workspace/f1_web/cron.log 2>&1
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (HERE, '/workspace/repo_ready/engine_f1'):
    if os.path.exists(os.path.join(cand, 'f1_signal.py')):
        sys.path.insert(0, cand)
        break

import f1_signal  # noqa: E402

OUT = os.path.join(HERE, 'f1_live.json')


def main():
    out = f1_signal.run_live(out_json=OUT)
    bk = out['breakers']['overall']
    sig = out['signal']
    print(f"f1_generate ok: asof={sig['asof']} "
          f"gate={'持币(regime闸)' if sig['gate']['on_holdcash'] else '持仓'} "
          f"top5={[x['sym'] for x in sig['top5']]} "
          f"breaker={bk['light']} action={bk['action']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
