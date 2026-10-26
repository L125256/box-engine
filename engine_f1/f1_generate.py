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

import pandas as pd  # noqa: E402  （牛闸倒计时 idx 序列推演用；引擎已依赖 pandas）

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


# ---- 牛闸开闸倒计时（工单 2026-10-23 · 蔡定锋提案用户拍板；纯渲染层字段，引擎零改动）----
# 字段命名登记：f1_live.json → meta.bullgate_countdown（唯一写入入口=merge_gate_countdown，
# 不碰 signal.gate 引擎判定字段；异常/对账失败=字段降级 note，页面降级显示不报错）。
GATE_COUNTDOWN_MAX_BARS = 250   # 横盘推演视野上限（≈一年交易日量级；超出=封顶标注，非预测承诺）


def compute_gate_countdown(live):
    """牛闸开闸倒计时计算（纯读：load_data/build_pool/trim_and_guard 只读复用引擎函数，
    零引擎改动、零状态机写入）。
    idx 序列口径与 f1_signal.current_signal 逐字镜像：cal 并集 → trim_and_guard →
    剔 forming → f1_signal.idx_gate_series（IDX-POLLUTION-20261026 采样日历+前向携带，
    与判定轮同源同函数）→ rolling(MA_REG)。
    对账闸（fail-closed 宁缺勿错）：镜像序列在 live.signal.asof 日的 idx/ma50（4 位舍入）
    必须与 signal.gate 完全一致——保证倒计时与页面展示的闸值同源同 vintage；不一致 → 停发。
    X=(ma50−idx)/idx×100（路径 A·涨指数开闸）；Y=(ma50−idx)/ma50×100（路径 B·降均线开闸）。
    横盘推演=idx 恒定、ma50 每日滚动（机械推演非预测，反弹则随时提前）：从 asof vintage
    起逐日追加 idx 恒定值，找首个 ma50<=idx 的 bar 序号=flat_trade_days；
    超出 GATE_COUNTDOWN_MAX_BARS → flat_capped=True 封顶标注。
    ma50 NaN（不足 MA_REG 根）/status≠red → 不出倒计时（green 态页面显示「闸开中」）。"""
    import numpy as np
    sig = live.get('signal') or {}
    g = sig.get('gate') or {}
    asof = sig.get('asof')
    out = dict(asof=asof, status=g.get('status'),
               x_gap_pct=None, y_gap_pct=None, flat_trade_days=None,
               flat_capped=False, note=None,
               method='idx 恒定、ma50 每日滚动机械推演（非预测）',
               max_bars=GATE_COUNTDOWN_MAX_BARS,
               computed_at=pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC'))
    try:
        data = f1_signal.load_data()
        syms = f1_signal.build_pool(data)
        cal_raw = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
        _g = f1_signal.trim_and_guard(cal_raw)
        if not _g['settled']:
            out['note'] = f"数据守卫拒绝（{_g.get('check')}），倒计时停发"
            return out
        cal = (pd.DatetimeIndex([d for d in cal_raw
                                 if d < pd.Timestamp(_g['today_utc_date'])])
               if _g['trimmed'] else cal_raw)
        close = pd.DataFrame({s: data[s]['close'] for s in syms}).reindex(cal)
        idx, ma = f1_signal.idx_gate_series(close)   # IDX-POLLUTION-20261026：与判定同源镜像
        t_asof = pd.Timestamp(asof) if asof else None
        if t_asof is None or t_asof not in idx.index:
            out['note'] = f'asof {asof} 不在镜像序列（数据 vintage 异常），倒计时停发'
            return out
        i_idx, i_ma = float(idx.loc[t_asof]), float(ma.loc[t_asof])
        if pd.isna(i_idx) or pd.isna(i_ma):
            out['note'] = f"ma50 未满 {f1_signal.MA_REG} 日（NaN），倒计时不可算"
            return out
        if round(i_idx, 4) != g.get('idx') or round(i_ma, 4) != g.get('ma50'):
            out['note'] = (f'镜像对账不一致（mirror idx/ma50={round(i_idx, 4)}/{round(i_ma, 4)} '
                           f'vs gate {g.get("idx")}/{g.get("ma50")}），倒计时停发')
            return out
        if g.get('status') != 'red':
            out['note'] = '闸开中（green），无倒计时'
            return out
        if not (i_idx < i_ma):
            out['note'] = '闸值矛盾（status=red 但镜像 idx≥ma50），倒计时停发'
            return out
        out['x_gap_pct'] = round((i_ma - i_idx) / i_idx * 100, 2)
        out['y_gap_pct'] = round((i_ma - i_idx) / i_ma * 100, 2)
        vals = idx.loc[:t_asof].values.astype(float)
        ext = np.concatenate([vals, np.full(GATE_COUNTDOWN_MAX_BARS, i_idx)])
        ma_ext = pd.Series(ext).rolling(f1_signal.MA_REG).mean().values[len(vals):]
        hit = [k for k, v in enumerate(ma_ext) if not np.isnan(v) and v <= i_idx]
        if hit:
            out['flat_trade_days'] = int(hit[0]) + 1
        else:
            out['flat_capped'] = True
            out['flat_trade_days'] = GATE_COUNTDOWN_MAX_BARS
            out['note'] = '横盘推演超视野上限仍未翻绿（封顶标注）'
        return out
    except Exception as e:                     # 任何异常=降级停发，不阻断判定轮产出
        out['note'] = f'倒计时计算异常（{type(e).__name__}: {e}），倒计时停发'
        return out


def merge_gate_countdown(out_json):
    """牛闸倒计时并入（学 merge_enhancement 先例：渲染层拼接、异常不阻断判定轮产出，
    缺字段=页面降级显示「倒计时未上线」）。"""
    import json
    try:
        with open(out_json) as f:
            live = json.load(f)
    except Exception as _e:
        print(f'gate_countdown 并入跳过（f1_live.json 读取失败，不阻断）: {_e}')
        return
    try:
        live.setdefault('meta', {})['bullgate_countdown'] = compute_gate_countdown(live)
    except Exception as e:
        live.setdefault('meta', {})['bullgate_countdown'] = None
        print(f'gate_countdown 计算失败（页面降级显示，不阻断）: {e!r}')
    tmp = out_json + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(live, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_json)
    print('gate_countdown 并入: '
          + json.dumps(live['meta']['bullgate_countdown'], ensure_ascii=False))


def main():
    out = f1_signal.run_live(out_json=OUT)
    merge_enhancement(OUT)
    merge_gate_countdown(OUT)
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
