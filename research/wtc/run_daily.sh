#!/bin/bash
# run_daily.sh — WT-C 影子双轨一键入口（refresh 32线程 + shadow 三轨回放 + 落盘）
# 可被 cron 调用；建议：10 9 * * * /tmp/wtc/run_daily.sh >> /tmp/wtc/logs/cron.log 2>&1
set -u
mkdir -p /tmp/wtc/ledger /tmp/wtc/logs
LOG=/tmp/wtc/logs/$(date +%F).log
{
  echo "===== run_daily start $(date '+%F %T') ====="
  python3 /tmp/wtc/refresh_cache.py && \
  python3 /tmp/wtc/shadow_run.py
  rc=$?
  echo "===== run_daily end rc=$rc $(date '+%F %T') ====="
  exit $rc
} >> "$LOG" 2>&1
