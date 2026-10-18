#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_archive.py — R13 归档同步器
把权威副本（engine_f1/）与线上服务副本（/workspace/f1_web/）逐文件对齐到归档目录
/workspace/repo_ready/f1/，并做 sha256 校验。

用法：PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/sync_archive.py
"""
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARCH = '/workspace/repo_ready/f1'
WEB = '/workspace/f1_web'

# (归档文件名, 权威源路径)
PAIRS = []
# ① 引擎与运行资产（权威源 = engine_f1/）
for _n in ('f1_signal.py', 'f1_datasource.py', 'AUTHORITY_SHA.json',
           'replay_breakers_r13.py',
           'sync_archive.py', 'run_checks.py', 'run_scenario_checks.py',
           'run_r13_selftest.py', 'render_harness.cjs', 'f1_crontab.txt',
           'f1_rounds_r13.md', 'F1_台账口径_v1.md', 'f1_live.example.json',
           'checks_result.json', 'scenario_checks_result.json',
           'r13_selftest_result.json', 'r13_failover_drill.json',
           'breaker_stats_r13.json'):
    PAIRS.append((_n, os.path.join(HERE, _n)))
# ② 线上页面与数据（权威源 = /workspace/f1_web/）
for _n in ('index.html', 'manual.html', 'f1_live.json', 'f1_state.json',
           'f1_live_intraday.json'):
    PAIRS.append((_n, os.path.join(WEB, _n)))


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else None


def main():
    os.makedirs(ARCH, exist_ok=True)
    rows, bad = [], []
    for name, src in PAIRS:
        dst = os.path.join(ARCH, name)
        if not os.path.exists(src):
            rows.append({'file': name, 'status': 'SKIP(源缺失)'})
            continue
        if sha(src) != sha(dst):
            shutil.copyfile(src, dst)
        ok = sha(src) == sha(dst)
        rows.append({'file': name, 'status': 'OK' if ok else 'MISMATCH', 'sha': sha(dst)[:16]})
        if not ok:
            bad.append(name)
    for r in rows:
        print(f"{r['file']:26s} {r['status']:14s} {r.get('sha', '')}")
    print('\n归档同步：', 'ALL ALIGNED' if not bad else f'不一致={bad}')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
