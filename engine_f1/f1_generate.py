#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
f1_generate.py — F1 状态页生成器（幂等，可 cron）
数据引擎：/workspace/repo_ready/engine_f1/f1_signal.py（BUG-01~05 修复版，seed=42，sha256 见 f1_live.json）
输出：/workspace/f1_web/f1_live.json + f1_state.json（BUG-03 冻结/档位状态机落盘）
页面：/workspace/f1_web/index.html（消费 f1_live.json）+ manual.html（使用说明）
复现：PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py live
cron 建议：25 9 * * * PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py live >> /workspace/f1_web/cron.log 2>&1
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


def merge_enhancement(out_json):
    """DEPLOY_SPEC_v1 §3.1-③ 渲染并入：若存在 f1/enhancement_state.json 则并入
    f1_live.json → meta.enhancement（渲染层拼接，学 meta.breadth 先例；f1_signal.py
    引擎主逻辑零改动；无该文件时 meta.enhancement=null，页面显示「增强层未上线」）。"""
    import json
    root = os.path.dirname(HERE)                       # 仓库根（engine_f1/ 或 f1/ 的上级）
    state_f = os.path.join(root, 'f1', 'enhancement_state.json')
    try:
        with open(out_json) as f:
            live = json.load(f)
    except Exception as _e:
        print(f'enhancement 并入跳过（f1_live.json 读取失败，不阻断）: {_e}')
        return
    try:
        with open(state_f) as f:
            live.setdefault('meta', {})['enhancement'] = json.load(f)
    except Exception:
        live.setdefault('meta', {})['enhancement'] = None
    tmp = out_json + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(live, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_json)
    print(f"enhancement 并入: meta.enhancement={'有' if live['meta']['enhancement'] else 'null（增强层未上线）'}")


def main():
    out = f1_signal.run_live(out_json=OUT)
    merge_enhancement(OUT)
    bk = out['breakers']['overall']
    sig = out['signal']
    st = out['state']
    print(f"f1_generate ok: asof={sig['asof']} "
          f"gate={'持币(总开关关)' if sig['gate']['on_holdcash'] else '持仓'} "
          f"top5={[x['sym'] for x in sig['top5']]} "
          f"breaker={bk['light']} action={bk['action']} "
          f"tier={st['tier_idx']} freeze_left={st['freeze_days_left']}"
          + (f"(至{st['freeze_until_date']})" if st['freeze_until_date'] else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
