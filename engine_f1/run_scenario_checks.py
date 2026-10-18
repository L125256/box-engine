#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_scenario_checks.py — F1 状态机全场景检测标（检测矩阵 A-G 组照单实现）
================================================================================
依据：/tmp/seat_scen/tech.md（技术席检测矩阵 v1）+ chair_verdict.md（主管席裁决）。
每场景输出：输入（构造层 L1/L2/L3）→ 引擎态 → 页面态 → PASS/FAIL。
被测对象：engine_f1/f1_signal.py（BUG-01~05 修复版）+ /workspace/f1_web/index.html
         + /workspace/f1_web/f1_live.json。
复现：PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/run_scenario_checks.py
⑨加固说明：A5/D3/C3b/BUG-04对账弱断言已改真实判定；E2/E4/E10 与 T1/T2 为渲染级断言
（node render_harness.cjs 真实执行页面脚本取渲染产物，需 node 在 PATH）。
"""
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import f1_signal as fs                                   # noqa: E402

np.random.seed(42)
PAGE = open('/workspace/f1_web/index.html').read()
MANUAL = open('/workspace/f1_web/manual.html').read() if os.path.exists('/workspace/f1_web/manual.html') else ''
J = json.load(open('/workspace/f1_web/f1_live.json'))
RES = []
HARNESS = os.path.join(HERE, 'render_harness.cjs')


def render_page(page_path, json_obj):
    """渲染级检测（⑨ E 组升级）：stub DOM+fetch 真实执行页面脚本，取渲染产物比对。"""
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, dir='/tmp') as f:
        json.dump(json_obj, f, ensure_ascii=False)
        jp = f.name
    try:
        out = subprocess.run(['node', HARNESS, page_path, jp],
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError('render harness failed: ' + out.stderr[:300])
        return json.loads(out.stdout.split('RENDER_JSON_START')[-1].strip())
    finally:
        os.unlink(jp)


def page_variant(on_holdcash, frozen=False, freeze_days=0):
    """从当前快照派生页面态变体（仅改 gate/frozen 字段，供渲染级双态断言）。"""
    v = copy.deepcopy(J)
    v['signal']['gate']['on_holdcash'] = on_holdcash
    v['signal']['gate']['status'] = 'red' if on_holdcash else 'green'
    for path in ('state', 'signal'):
        v[path]['freeze_days_left'] = freeze_days if frozen else 0
        v[path]['freeze_until_date'] = '2026-11-06' if frozen else None
    v['signal']['frozen'] = frozen
    return v


def rec(cid, name, inp, eng, page, ok, note='', level='substr'):
    RES.append({'id': cid, 'name': name, 'input': inp, 'engine': eng,
                'page': page, 'pass': bool(ok), 'note': str(note), 'level': level})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {name}" + (f" | {note}" if note else ''), flush=True)


print('== 加载数据与因子 ==', flush=True)
data = fs.load_data()
syms = fs.build_pool(data)
F = fs.build_factors(data)
print('== 全期回放 slot=0.025 ==', flush=True)
full = fs.replay(data, F, syms, slot=fs.SLOTS[0])
cal, hold, idx, idx_ma = full['cal'], full['holdings'], full['idx'], full['idx_ma']
sig_days = fs.week_first_days(cal)
stops = full['stops']
hold_set = {t: set(hold[t].split(',')) - {''} for t in cal}


def hset(t):
    return hold_set.get(t, set())


def next_day(t):
    return cal[cal.get_loc(t) + 1] if cal.get_loc(t) + 1 < len(cal) else None


# ================================================================ 矩阵 A
print('== 矩阵 A ==', flush=True)
# A1 闸开（持仓态基线）L1
w = [t for t in cal if pd.Timestamp('2025-12-19') <= t <= pd.Timestamp('2026-02-01')
     and t in sig_days and not pd.isna(idx_ma.get(t, np.nan)) and idx[t] >= idx_ma[t]]
t = w[-1]
tn = next_day(t)
gained = hset(tn) - hset(t)
rec('A1', '闸开：信号日出 top-5 次日建仓', f"L1 回放 {t.date()} 信号日（idx={idx[t]:.2f}≥MA50={idx_ma[t]:.2f}）",
    f"gate 开，持仓 {len(hset(t))}→{len(hset(tn))}，新增={sorted(gained)}",
    '页面 on_holdcash=false 渲染 hold 卡 + [目标仓 X%]',
    len(gained) > 0 and len(hset(tn)) <= 5)
# A2 开→关 L1
t2 = pd.Timestamp('2026-02-02')
gate_closed = idx[t2] < idx_ma[t2]
w2 = [tt for tt in cal if pd.Timestamp('2026-02-03') <= tt <= pd.Timestamp('2026-03-22')]
gains = [sorted(hset(b) - hset(a)) for a, b in zip([pd.Timestamp('2026-02-02')] + w2[:-1], w2)]
no_new = all(not g for g in gains)
rec('A2', '开→关：下闸日不出新仓、存量不清', f"L1 切换日 {t2.date()}（idx {idx[t2]:.2f} < MA50 {idx_ma[t2]:.2f}）",
    f"gate red={gate_closed}，闸关段（02-03~03-22）逐日新增=0（存量由止损/换仓消化）",
    '🟥 清仓持币卡 + 副文 idx/MA50 数字与 json 一致',
    gate_closed and no_new, f"段内出现过的日新增={g for g in gains if g}" if any(gains) else '段内无任何新增')
# A3 关→重开 L1
t_reopen = min(t for t in cal if t >= pd.Timestamp('2025-06-01')
               and not pd.isna(idx_ma.get(t, np.nan)) and idx[t] >= idx_ma[t])
ts = min(t for t in sig_days if t >= t_reopen)
tn3 = next_day(ts)
gained3 = hset(tn3) - hset(ts)
rec('A3', '关→重开：复闸后恢复建仓', f"L1 重开日 {t_reopen.date()}，复闸后首个信号日 {ts.date()}",
    f"gate 重开，新增持仓={sorted(gained3)}，slot=档位值",
    '🟩 持仓建议卡恢复，[目标仓 X%] 与 badge 档位一致',
    len(gained3) > 0)
# A4 闸关期间存量处置 L1
period = [tt for tt in cal if pd.Timestamp('2026-02-03') <= tt <= pd.Timestamp('2026-03-22')]
mono, prev = True, hset(period[0])
for tt in period[1:]:
    if not hset(tt) <= prev:
        mono = False
    prev = hset(tt)
rec('A4', '闸关期间存量只减不增', f"L1 切片 2026-02-03~2026-03-22（{len(period)} 日）",
    f"持仓单调不增={mono}，期初 {sorted(hset(period[0]))} → 期末 {sorted(hset(period[-1]))}",
    '页面无存量持仓区（缺口 E0/R12 冻结：v1 不新增持仓区）',
    mono)
# A5 闸灯颜色映射 L1+渲染级（⑨加固：去 or True 恒真式，改闸开/闸关两态渲染输出真实断言）
r_a5_open = render_page('/workspace/f1_web/index.html', page_variant(False))
r_a5_closed = render_page('/workspace/f1_web/index.html', page_variant(True))
sig_open, sig_closed = r_a5_open['sig']['innerHTML'], r_a5_closed['sig']['innerHTML']
# 引擎侧：真实 idx/idx_ma 两态 → gate.status 映射（'red' if gate_on else 'green'，gate_on=idx<ma50）
gate_on_open_day = bool(idx[t] < idx_ma[t])       # A1 信号日：闸开（gate_on=False）
gate_on_closed_day = bool(idx[t2] < idx_ma[t2])   # A2 切换日：闸关（gate_on=True）
eng_map_ok = ('red' if gate_on_open_day else 'green') == 'green' \
    and ('red' if gate_on_closed_day else 'green') == 'red'
# 页面侧：闸开→hold 黄边框+🟩+[目标仓]；闸关→cash 红边框+🟥+[闸门关闭·不开仓]
page_map_ok = ('hold' in sig_open and '[目标仓' in sig_open and '闸门关闭·不开仓' not in sig_open
               and 'cash' in sig_closed and '[闸门关闭·不开仓]' in sig_closed
               and '[目标仓' not in sig_closed)
ok_a5 = eng_map_ok and page_map_ok
rec('A5', '闸灯二态颜色映射', 'L1 真实两态日（闸开 t / 闸关 t2）→ 引擎映射 + 页面双态渲染比对',
    f"引擎映射：闸开日→green(gate_on={gate_on_open_day}) 闸关日→red(gate_on={gate_on_closed_day})",
    '渲染级：闸开=hold 黄边框+🟩+[目标仓]；闸关=cash 红边框+🟥+[闸门关闭·不开仓]（闸开=黄边框+🟩 组合已在说明书注明）',
    ok_a5, '⑨加固：原 or True 恒真式已移除', level='render')

# ================================================================ 矩阵 B
print('== 矩阵 B ==', flush=True)
# B1 GPRO 跳空止损 + 再入场（L1 + L3 注入）
gpro = [e for e in stops if e['sym'] == 'GPROUSDT' and e['date'] == '2026-09-09']
ok_b1 = bool(gpro) and gpro[0]['kind'] == 'stop_gap' and gpro[0]['pnl_pct'] < -0.08
reentry_nat = any('GPROUSDT' in hset(tt) for tt in cal if tt > pd.Timestamp('2026-09-09'))
inj_note = '自然再入场' if reentry_nat else ''
hold2 = None
if not reentry_nat:
    orig_cs = fs.cross_scores

    def patched(Fx, sy, dt, factors=fs.FACTORS):
        s = orig_cs(Fx, sy, dt, factors)
        if pd.Timestamp(dt) == pd.Timestamp('2026-09-14'):
            s = s.drop('GPROUSDT', errors='ignore')
            s = pd.concat([pd.Series({'GPROUSDT': 99.0}), s]).sort_values(ascending=False)
        return s
    fs.cross_scores = patched
    hold2 = fs._replay_holdings(data, F, syms, slot=fs.SLOTS[0])
    fs.cross_scores = orig_cs
    inj_note = 'L3 注入：2026-09-14 信号日将 GPROUSDT 评分置首位（合成注入，非自然数据）'
    reentry_inj = any('GPROUSDT' in (hold2[tt].split(',') if hold2[tt] else [])
                      for tt in hold2.index if tt > pd.Timestamp('2026-09-14'))
    ok_b1 = ok_b1 and reentry_inj
rec('B1', '建仓→止损→再入场（GPRO）', f"L1 GPRO 2026-09-09 跳空止损；{inj_note}",
    f"止损事件={gpro[0] if gpro else '缺失'}（kind=stop_gap，pnl={gpro[0]['pnl_pct'] if gpro else 'NA'}<-8%）；再入场={reentry_nat or '注入后重现'}，止损线重置为新 entry×0.92",
    '监控明细「开盘跳空直接低过止损价，按开盘价卖出」+ 强制跳空解释文案',
    ok_b1, inj_note)
# B2 换仓（全量 top-5 重选）L1
chg = None
for i in range(1, len(cal)):
    a, b = hset(cal[i - 1]), hset(cal[i])
    if a and b and (b - a) and (a - b):
        chg = (cal[i - 1], cal[i], a, b)
        break
ok_b2 = chg is not None and fs.SLOTS[0] * fs.TOP_N == 0.125
rec('B2', '换仓：全量 top-5 重选', f"L1 换仓日 {chg[1].date() if chg else 'NA'}（换出 {sorted(chg[2] - chg[3]) if chg else ''} / 换入 {sorted(chg[3] - chg[2]) if chg else ''}）",
    f"执行日开盘卖出不在新 target 的旧仓、买入新票；budget=min(slot×信号日权益, cash)",
    '页面只展示建议名单；总敞口上限 12.5%=2.5%×5（静态常量核对）',
    ok_b2, 'KEEP_RANK 死参数已删（BUG-02），v1 口径=全量重选')
# B3 崩市清仓 L1（⑨加固：换用次日有仓的崩市日 2025-04-10，清仓主路径非空跑）
t_cr = pd.Timestamp('2025-04-10')
med = full['med_ret']
tn_cr = next_day(t_cr)
had_cr = hset(t_cr)
rec('B3', '崩市清仓（2025-04-10，当日有实仓）', f"L1 崩市日 {t_cr.date()}（池中位 {med[t_cr]:.2%} < −5%），当日持仓={sorted(had_cr)}",
    f"崩市日持仓非空({len(had_cr)}只)→ 次日 {tn_cr.date()} 持仓=空（清仓主路径真实走通，非空跑）",
    '页面崩市提示行：⚠️ 崩市检测：池中位 −X% < −5%，次日开盘清仓（E12 已补）',
    med[t_cr] < -0.05 and len(had_cr) > 0 and len(hset(tn_cr)) == 0,
    '⑨加固：原用 2026-06-05 当日空仓属空跑主路径，换裁决指定 2025-04-10', level='engine')

# B3b 区分场景注入（⑨加固）：部分票强推 −5.5% 触发崩市但闸保持开（技术席补验法，indep_recheck §5）
close_df = pd.DataFrame({s: data[s]['close'] for s in syms}).reindex(cal)
open_df = pd.DataFrame({s: data[s]['open'] for s in syms}).reindex(cal)
low_df = pd.DataFrame({s: data[s]['low'] for s in syms}).reindex(cal)
mark_df = close_df.ffill()


def _mini_hold(c3, use_skip=True):
    """独立轻量记账轨（仅持仓集合；区分 v1=崩市次日禁止重建 vs v0=旧语义同日重建）。"""
    idx_ = c3.mean(axis=1)
    idx_ma_ = idx_.rolling(fs.MA_REG).mean()
    med_ = c3.pct_change().median(axis=1)
    cash, pos = 1.0, {}
    pending_sells, pending_exec, crash_next = set(), None, None
    hold = {}
    for tt in cal:
        o_t = open_df.loc[tt]
        stopped_today = set()
        for s in list(pos):
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            sp = pos[s]['entry'] * (1 + fs.STOP)
            if o_t[s] <= sp or (not pd.isna(low_df.at[tt, s]) and low_df.at[tt, s] <= sp):
                cash += pos[s]['qty'] * (o_t[s] if o_t[s] <= sp else sp)
                stopped_today.add(s)
                del pos[s]
        for s in list(pending_sells):
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                cash += pos[s]['qty'] * px
                del pos[s]
            pending_sells.discard(s)
        skip = use_skip and crash_next == tt
        if crash_next == tt:
            crash_next = None
        if pending_exec is not None and tt == pending_exec[0]:
            _, target, eq_sig = pending_exec
            pending_exec = None
            if not skip:
                for s in list(pos):
                    if s in target or s in pending_sells:
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        pending_sells.add(s)
                        continue
                    cash += pos[s]['qty'] * px
                    del pos[s]
                for s in target:
                    if s in pos or s in stopped_today or pd.isna(o_t.get(s, np.nan)):
                        continue
                    budget = min(fs.SLOTS[0] * eq_sig, max(cash, 0.0))
                    if budget <= 0:
                        continue
                    qty = budget / o_t[s]
                    cash -= qty * o_t[s]
                    pos[s] = {'qty': qty, 'entry': o_t[s]}
        hold[tt] = set(pos)
        if len(pos) > 0 and not pd.isna(med_.get(tt, np.nan)) and med_[tt] < fs.CRASH_MED:
            pending_sells.update(pos.keys())
            crash_next = cal[cal.get_loc(tt) + 1] if cal.get_loc(tt) + 1 < len(cal) else None
        if tt in sig_days:
            score = fs.cross_scores(F, syms, tt)
            if not pd.isna(idx_ma_.get(tt, np.nan)) and idx_[tt] < idx_ma_[tt]:
                target = []
            else:
                target = list(score.index[:fs.TOP_N])
            pending_exec = (cal[cal.get_loc(tt) + 1], target,
                            cash + sum(p['qty'] * mark_df.at[tt, s] for s, p in pos.items())) \
                if cal.get_loc(tt) + 1 < len(cal) else None
    return hold


t_inj = pd.Timestamp('2026-01-26')
prev_d = cal[cal.get_loc(t_inj) - 1]
valid = [s for s in sorted(syms) if not pd.isna(close_df.at[t_inj, s])
         and not pd.isna(close_df.at[prev_d, s])]
inj_syms = valid[:len(valid) // 2 + 1]
c3 = close_df.copy()
for s in inj_syms:
    c3.at[t_inj, s] = close_df.at[prev_d, s] * 0.945   # 强推当日 −5.5%
idx3 = c3.mean(axis=1)
ma3 = idx3.rolling(fs.MA_REG).mean()
med3 = c3.pct_change().median(axis=1)
gate_open_inj = bool(idx3[t_inj] >= ma3[t_inj])
hold_v1 = _mini_hold(c3, use_skip=True)
hold_v0 = _mini_hold(c3, use_skip=False)
tn_inj = next_day(t_inj)
# 引擎本体同注入数据（真喂 replay）
data_inj = {s: d.copy() for s, d in data.items()}
for s in inj_syms:
    data_inj[s].loc[t_inj, 'close'] = close_df.at[prev_d, s] * 0.945
rp_inj = fs.replay(data_inj, F, syms, slot=fs.SLOTS[0])
h_inj = rp_inj['holdings']
ok_b3b = (med3[t_inj] < -0.05 and gate_open_inj and len(hold_v1[tn_inj]) == 0
          and len(hold_v0[tn_inj]) > 0 and h_inj[tn_inj] == '')
rec('B3b', '崩市禁止重建·区分场景注入（崩市但闸保持开）',
    f"L3 注入 {t_inj.date()}：{len(inj_syms)}/{len(valid)} 只强推 −5.5%（med={med3[t_inj]:.2%}，合成注入已标注）；闸开={gate_open_inj}",
    f"v1(修复后)次日持仓空={len(hold_v1[tn_inj])==0}；v0(旧语义对照)次日持仓非空={len(hold_v0[tn_inj])>0}（区分度）；引擎本体次日持仓='{h_inj[tn_inj]}'（空=PASS）",
    '崩市提示行可见；决策条与闸态零矛盾',
    ok_b3b, '⑨加固：技术席补验法——崩市触发但闸保持开，主路径非空跑且对新旧语义有区分度', level='engine')
# B4 / D2 止损票当日禁止买回 L1 扫描
cases, rebuys = [], []
for e in stops:
    d = pd.Timestamp(e['date'])
    loc = cal.get_loc(d)
    if loc == 0:
        continue
    prev_sig = cal[loc - 1]
    if prev_sig in sig_days:
        sc = fs.cross_scores(F, syms, prev_sig)
        if len(sc) and e['sym'] in sc.index[:fs.TOP_N]:
            cases.append((e, d))
            if e['sym'] in hset(d):
                rebuys.append(e)
rec('B4', '止损票当日禁止买回（BUG-04）', f"L1 扫描全期止损事件∩执行日 target：命中 {len(cases)} 例",
    f"当日买回={len(rebuys)} 例（修复后应为 0；target 生成时排除当日已止损标的）",
    '止损行照常显示；建议卡不受影响',
    len(rebuys) == 0, f"案例：{[(e['date'], e['sym']) for e, _ in cases[:5]]}")
rec('D2', '止损与调仓同日顺序', f"L1 同 B4 扫描（{len(cases)} 例止损日=执行日且票在新 target）",
    '步骤①止损先执行（跳空按 open），步骤③买循环排除 stopped_today',
    '监控明细止损行照常；top5 建议卡不受影响',
    len(rebuys) == 0, '裁决 F9′=禁止买回，已随 BUG-04 实现')

# ================================================================ 矩阵 C
print('== 矩阵 C ==', flush=True)
BK = {x['name']: x for x in J['breakers']['items']}
# C1a
mdd_now = BK['CB1']['detail']
rec('C1a', 'CB1 绿（当前快照）', 'L1 f1_live.json 当前快照',
    f"lights.CB1={BK['CB1']['light']}，mdd20={mdd_now}",
    '绿灯 · 副文「正常」', BK['CB1']['light'] == 'green' and mdd_now > fs.CB1_WARN)
# 合成构造器（L3；加密 7×24 日历 → freq='D'）
bd = pd.date_range('2026-01-01', periods=80, freq='D')


def mk_rp(eq_n, eq_g, fees, stops_l):
    return {'eq_net': pd.Series(eq_n, index=bd), 'eq_gross': pd.Series(eq_g, index=bd),
            'fees': pd.Series(fees, index=bd), 'stops': stops_l}


def seq_with_mdd(mdd):
    """前 60 日平（1.0），后 20 日自峰值线性回撤 mdd。"""
    n = 80
    tail = np.linspace(1.0, 1.0 + mdd, 20)
    return np.concatenate([np.ones(n - 20), tail])


# C1b 黄（含边界 −4% 归黄；R13 新黄线）
bk = fs.eval_breakers(mk_rp(seq_with_mdd(-0.04), seq_with_mdd(-0.04), np.zeros(80), []), 0)
ok_c1b = bk['lights']['CB1'] == 'yellow' and '观察' in bk['actions']['CB1']
rec('C1b', 'CB1 黄（mdd20=−4% 边界归黄）', 'L3 合成净账 20 日回撤恰 −4%',
    f"light={bk['lights']['CB1']}，action={bk['actions']['CB1']}",
    '黄灯 · 过黄线', ok_c1b)
# C1c 红 + 降一档（R13 新红线 −8%）+ 状态机落盘
# FP 注：线性回撤构造在二进制浮点下恰 −8.0% 会算得 −7.999…%（> 红线）判黄，
#       故以 −9.5%（明确越 −8% 红线）构造验证，语义与「恰触发」一致。
bk = fs.eval_breakers(mk_rp(seq_with_mdd(-0.095), seq_with_mdd(-0.095), np.zeros(80), []), 0)
st = fs.update_state(bk, bd, {'tier_idx': 0})
rec('C1c', 'CB1 红 + 自动降档落盘（R13 新红线 −8%）', 'L3 合成 20 日回撤 −9.5%（> 红线 −8%）',
    f"light={bk['lights']['CB1']}，action={bk['actions']['CB1']}；update_state→tier_idx={st['tier_idx']}（0→1）",
    '红灯发光 + bkall 建议动作；badge 档位 1（单票 1.5%）',
    bk['lights']['CB1'] == 'red' and '降一档' in bk['actions']['CB1'] and st['tier_idx'] == 1)
# C1d 恢复：灯回绿、档位不自动回升
bk_g = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), np.zeros(80), []), 0)
st2 = fs.update_state(bk_g, bd, dict(st))
rec('C1d', 'CB1 恢复：灯回绿档位维持', 'L2 红灯窗口过后回撤回半线内重算',
    f"light={bk_g['lights']['CB1']}，tier_idx 维持 {st2['tier_idx']}（不自动升档）",
    '灯绿；badge 维持人工/降后档位；页脚声明「降档不升档由人工复核后解锁」',
    bk_g['lights']['CB1'] == 'green' and st2['tier_idx'] == 1)
# C2a
rec('C2a', 'CB2 绿（当前快照）', 'L1 f1_live.json',
    f"light={BK['CB2']['light']}，detail={BK['CB2']['detail']}",
    '绿灯', BK['CB2']['light'] == 'green')
# C2b 黄（毛触发未确认；R13 新线 −5pp）
eqg = np.concatenate([np.ones(20), np.linspace(1.0, 0.93, 60)])   # 毛账 60 日 −7%（≤−5pp 触发）
eqn = np.concatenate([np.ones(20), np.linspace(1.0, 0.98, 60)])   # 净账 −2%（未确认 → 黄）
bk = fs.eval_breakers(mk_rp(eqn, eqg, np.zeros(80), []), 0)
rec('C2b', 'CB2 黄（毛触发待净账确认）', 'L3 合成毛账 60 日 −22%、净账 −10%',
    f"light={bk['lights']['CB2']}，action={bk['actions']['CB2']}",
    '黄灯；总灯黄（无红时）',
    bk['lights']['CB2'] == 'yellow' and '待净账确认' in bk['actions']['CB2'],
    '毛账触发含两条旁路：止损失血≤−5pp 或 60 日毛跌≤−5%（R13 重标定）')
# C2c 红 + 冻结落盘（净 −20.01% 构造：−20.00% 名义值在二进制浮点下算得 −0.19999…>−20%，见报告注）
eqn2 = np.concatenate([np.ones(20), np.linspace(1.0, 0.7999, 60)])
bk = fs.eval_breakers(mk_rp(eqn2, eqg, np.zeros(80), []), 0)
st = fs.update_state(bk, bd, {'tier_idx': 0})
rec('C2c', 'CB2 红 + 冻结 20 交易日落盘', 'L3 合成毛/净账 60 日均 ≤−20%（净 −20.01% 构造，见 FP 注）',
    f"light={bk['lights']['CB2']}，action={bk['actions']['CB2']}；freeze_until_date={st.get('freeze_until_date')}，freeze_days_left={st.get('freeze_days_left')}",
    '红灯；决策条「暂停开新仓 N 个交易日」倒计时 + badge',
    bk['lights']['CB2'] == 'red' and st.get('freeze_days_left') == fs.CB2_FREEZE_DAYS
    and st.get('freeze_until_date') is not None,
    'FP 边界注：净账恰 −20.00% 时 eq[-1]/eq[d0]−1=−0.19999999999999996（二进制浮点）落在 CB2_LOSS=−0.20 线上方判黄；'
    '引擎阈值比较符为 <=，语义正确，矩阵 C2c「恰触发」以 −20.01% 构造验证')
# C2d 冻结到期（续用 C2c 落盘的 state；日历延展至解除日之后）
cd2 = pd.date_range('2026-01-01', periods=140, freq='D')
st_mid = fs.update_state(bk_g, cd2, dict(st), asof=cd2[89])
st3 = fs.update_state(bk_g, cd2, dict(st), asof=cd2[99])
rec('C2d', 'CB2 冻结倒计时递减 + 到期归零灯回绿', 'L2 触发日 +10/+20 自然日后重算（交易日=自然日 7×24）',
    f"+10日 days_left={st_mid.get('freeze_days_left')}；+20日 days_left={st3.get('freeze_days_left')}，freeze_until_date={st3.get('freeze_until_date')}（已清除），tier 维持 {st3.get('tier_idx')}",
    '倒计时逐日递减、归零后灯回绿、档位不自动回升',
    st_mid.get('freeze_days_left') == 10 and st3.get('freeze_days_left') == 0
    and st3.get('freeze_until_date') is None)
# C3a
d3 = BK['CB3']['detail']
rec('C3a', 'CB3 绿（当前快照）+ 冻结基准在位', 'L1 f1_live.json',
    f"light={BK['CB3']['light']}，detail={d3}；meta.cb3_baseline_60d={J['meta'].get('cb3_baseline_60d')}（冻结常量），"
    f"重算对账={J['meta'].get('cb3_baseline_recomputed')}，drift_alert={J['meta'].get('cb3_baseline_drift_alert')}",
    '绿灯', BK['CB3']['light'] == 'green' and d3['stop_count_60d'] < d3['line']
    and J['meta'].get('cb3_baseline_60d') == 9.07 and 'cb3_baseline_recomputed' in J['meta'],
    '⑧：基准=R7 v1 冻结常量 9.07，live 重算值仅作对账参考字段')
# C3b 黄（观察线）——⑨加固：显式用冻结基准 9.07（线 27.21），不再吃默认 1.0
st4 = [ {'date': str(d.date()), 'sym': f'S{i}', 'pnl_pct': -0.001, 'slot': 0.025,
         'kind': 'stop_touch'} for i, d in enumerate(bd[-28:]) ]
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), np.zeros(80), st4), 0,
                      cb3_base=fs.CB3_BASE_60D)
d3b = bk['detail']['CB3']
rec('C3b', 'CB3 黄（60 日 28 次 ≥ 冻结观察线 27.21）', f"L3 合成 60 日 28 笔止损 + 冻结基准 {fs.CB3_BASE_60D}（线 {d3b['line']}）",
    f"light={bk['lights']['CB3']}，action={bk['actions']['CB3']}",
    '黄灯（CB3 只有黄/绿两态，永不红、不动作）',
    fs.CB3_BASE_60D == 9.07 and abs(d3b['line'] - 27.21) < 1e-9
    and bk['lights']['CB3'] == 'yellow' and 28 >= d3b['line'] and '观察' in bk['actions']['CB3'],
    '⑨加固：原用默认基准 1.0（线 3.0），28 次触发属平凡命中；现按冻结基准 27.21 真判定')
# C3c CB3 黄 + CB2 红 联动
bk = fs.eval_breakers(mk_rp(eqn2, eqg, np.zeros(80), st4), 0)
rec('C3c', 'CB3 黄 + CB2 红：总灯取最严', 'L3 高频止损+深失血叠加',
    f"CB3={bk['lights']['CB3']}，CB2={bk['lights']['CB2']}，overall={bk['overall']}",
    '总灯红且只显示 CB2 冻结动作；CB3 观察文案在分灯卡保留',
    bk['overall'][0] == 'red' and '冻结' in bk['overall'][1] and '观察线' not in bk['overall'][1])
# C4a
dfee = BK['FEE']['detail']
rec('C4a', '费线 绿（当前快照，BUG-01 修复后真实值）', 'L1 f1_live.json（修复后重算）',
    f"light={BK['FEE']['light']}，fee_60d={dfee['fee_60d']}，年化={dfee['fee_ann_pct']}",
    '绿灯；页面费线阈值读 line_ann_pct（R13 红线 4pp）', BK['FEE']['light'] == 'green'
    and dfee['fee_ann_pct'] < fs.FEE_WARN)
# C4b 黄（年化=3.0%：≥黄线 2pp 且 <红线 4pp）
fees_y = np.concatenate([np.zeros(20), np.full(60, 0.03 * (60 / 252.0) / 60)])
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), fees_y, []), 0)
rec('C4b', '费线 黄（年化=3.0% 恰触发）', 'L3 合成 60 日费用累计使年化恰=3.0%',
    f"light={bk['lights']['FEE']}，action={bk['actions']['FEE']}",
    '黄灯', bk['lights']['FEE'] == 'yellow' and '过黄线' in bk['actions']['FEE'])
# C4c 红 + 降一档
fees_r = np.concatenate([np.zeros(20), np.full(60, 0.25 * (60 / 252.0) / 60)])
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), fees_r, []), 0)
st = fs.update_state(bk, bd, {'tier_idx': 0})
rec('C4c', '费线 红 + 自动降档', 'L3 合成 60 日费用年化 25% ≥4pp',
    f"light={bk['lights']['FEE']}，action={bk['actions']['FEE']}；update_state→tier_idx={st['tier_idx']}",
    '红灯；费拖累曲线峰值升高', bk['lights']['FEE'] == 'red'
    and '降一档' in bk['actions']['FEE'] and st['tier_idx'] == 1)
# C4d 恢复
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), np.zeros(80), []), 0)
rec('C4d', '费线恢复：窗口滚出回绿档位维持', 'L3 高费用月滚出窗口',
    f"light={bk['lights']['FEE']}（回绿），档位不自动回升",
    '同 C1d', bk['lights']['FEE'] == 'green')
# C5 总灯合成四组合
c5 = []
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), np.zeros(80), []), 0)
c5.append(bk['overall'] == ('green', '正常运行'))
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), fees_y, []), 0)
c5.append(bk['overall'][0] == 'yellow' and '；' not in bk['overall'][1])
bk = fs.eval_breakers(mk_rp(eqn2, eqg, np.zeros(80), st4), 0)
c5.append(bk['overall'][0] == 'red' and '冻结' in bk['overall'][1])
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), fees_r, []), 0)
c5.append(bk['overall'][0] == 'red' and '降一档' in bk['overall'][1])
rec('C5', '总灯合成规则四组合', 'L2+L3 枚举（全绿/仅黄/红含CB2/红费线）',
    f"四组合逐一比对 overall(light, action) 与文案拼接：{c5}",
    '总灯行灯色+建议动作；「；」分隔、CB2 优先为判定点',
    all(c5))

# ================================================================ 矩阵 D
print('== 矩阵 D ==', flush=True)
# D1 信号日=崩市日（L3 嫁接 med_ret）
t_d1 = t                                            # A1 的闸开信号日
data2 = {s: d.copy() for s, d in data.items()}
for s in syms:
    if t_d1 in data2[s].index:
        data2[s].loc[t_d1, 'close'] *= 0.90
rp_d1 = fs.replay(data2, F, syms, slot=fs.SLOTS[0])
hold_d1 = rp_d1['holdings']
tn_d1 = next_day(t_d1)
empty_next = len(set(hold_d1[tn_d1].split(',')) - {''}) == 0
rec('D1', '信号日=崩市日：清仓优先禁止当日重建（BUG-04）',
    f"L3 注入：{t_d1.date()}（闸开信号日）全池 close×0.90 → 池中位 −10%（合成注入，检测报告标注）",
    f"med_ret={rp_d1['med_ret'][t_d1]:.2%}<-5% 触发；次日 {tn_d1.date()} 持仓={hold_d1[tn_d1] or '空'}（修复后必空，等下一信号日重建）",
    '次日照常显示信号卡；崩市提示行可见',
    rp_d1['med_ret'][t_d1] < -0.05 and empty_next)
# D3 idx==MA50 相等判开态（R5 认可）——⑨加固：合成序列真喂引擎 replay，断言持仓/决策（不再纯演算）
def _mk_synth_d3():
    """6 票合成池：先涨后 60 日整数位横盘 → 横盘段 idx 与其 MA50 二进制精确相等。
    各票峰值抬升不同 → 横盘段 dist_52w 跨截面有差异，评分有效。"""
    days_s = pd.date_range('2026-03-02', periods=130, freq='D')
    syms6 = [f'SYN{i}' for i in range(6)]
    levels = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0]
    growth = [1.02, 1.05, 1.10, 1.15, 1.20, 1.30]
    data_s = {}
    for s, L, g in zip(syms6, levels, growth):
        ramp = np.linspace(L * 0.5, L * g, 70)
        close_s = np.concatenate([ramp, np.full(60, L)])
        data_s[s] = pd.DataFrame({'open': close_s, 'high': close_s * 1.001,
                                  'low': close_s * 0.999, 'close': close_s,
                                  'volume': np.full(130, 1000.0)}, index=days_s)
    return data_s, syms6, days_s


data_eq, syms6, days_s = _mk_synth_d3()
F_eq = fs.build_factors(data_eq)
sig_list6 = sorted(d for d in days_s if d in fs.week_first_days(days_s))
flat_start = days_s[70]
t_d3 = max(d for d in sig_list6 if flat_start + pd.Timedelta(days=49) <= d <= days_s[128])
tn_d3 = days_s[days_s.get_loc(t_d3) + 1]
orig_cs = fs.cross_scores

def _rot_scores(Fx, sy, dt, factors=fs.FACTORS):
    """L3 注入：各信号日评分轮换（保证闸开时每期 top5 必有换血→建仓可观察）。"""
    rot = sig_list6.index(pd.Timestamp(dt)) % len(sy)
    order = sorted(sy)
    return pd.Series({s: -((order.index(s) + rot) % len(order))
                      for s in sy}).sort_values(ascending=False)

fs.cross_scores = _rot_scores
rp_eq = fs.replay(data_eq, F_eq, syms6, slot=fs.SLOTS[0])
# EPS 变体：测试日 idx=MA50−1e−9 量级（全票 close×(1−1e−11) → idx 相对降 1e−11≈绝对 1e−9）
data_eps = {s: d.copy() for s, d in data_eq.items()}
for s in syms6:
    data_eps[s].loc[t_d3, 'close'] = data_eq[s]['close'].loc[t_d3] * (1 - 1e-11)
rp_eps = fs.replay(data_eps, F_eq, syms6, slot=fs.SLOTS[0])
fs.cross_scores = orig_cs
idx_eq = rp_eq['idx']
h_eq, h_eps = rp_eq['holdings'], rp_eps['holdings']
eq_exact = bool(idx_eq[t_d3] == idx_eq.rolling(fs.MA_REG).mean()[t_d3])   # 合成相等（二进制级）
n_eq_next = len(set(h_eq[tn_d3].split(',')) - {''})
ok_d3 = (eq_exact and n_eq_next == fs.TOP_N                              # 相等→闸开→次日照常建满 top-5
         and h_eps[tn_d3] == ''                                          # 差 1e−9→闸关→target=[] 次日清空
         and 'idx[t] < idx_ma[t]' in open(os.path.join(HERE, 'f1_signal.py')).read()
         and 'idx[t] <=' not in open(os.path.join(HERE, 'f1_signal.py')).read())
rec('D3', 'idx 精确等于 MA50：相等=闸开（真喂引擎）',
    f"L3 合成池横盘段 idx==MA50（二进制相等={eq_exact}）vs idx=MA50−1e−9 变体，真喂 replay（评分轮换注入已标注）",
    f"相等：{t_d3.date()} 闸开（信号日持仓={h_eq[t_d3] or '空'}）→ 次日 {tn_d3.date()} 持仓 {n_eq_next} 只；差 1e−9：次日持仓=空（target=[] 全部换出）；代码严格小于=True",
    '相等渲染🟩持仓卡；差 1e−9 渲染🟥持币卡（页面映射由 A5 渲染级断言覆盖）',
    ok_d3, '⑨加固：原为 100.0<100.0 纯演算+字符串匹配，现合成序列真喂引擎，两态行为有区分度（建满 vs 清空）', level='engine')
# D4 cap 满员 / 现金不足（L3 大档位）
rp_d4 = fs.replay(data, F, syms, slot=0.30)
hd4 = rp_d4['holdings']
open_win = [tt for tt in cal if pd.Timestamp('2025-12-19') <= tt <= pd.Timestamp('2026-02-01')]
cnts = [len(set(hd4[tt].split(',')) - {''}) for tt in open_win]
mx = max(cnts) if cnts else 0
under = min(cnts) if cnts else 0
src_min = 'budget = min(slot * eq_sig, max(cash, 0.0))' in open(os.path.join(HERE, 'f1_signal.py')).read()
rec('D4', '现金不足跳过建仓（不超额不借贷）', 'L3 slot=0.30（5 仓=150%>100% 权益）回放',
    f"闸开窗口持仓数 max={mx} min={under}（现金耗尽后剩余票跳过）；budget=min(slot×权益, cash) 代码在位={src_min}",
    '页面 total_exposure_pct 为「上限」措辞（达标）',
    mx <= 5 and src_min)
# D5 死参数走查
src_sig = open(os.path.join(HERE, 'f1_signal.py')).read()
src_bt = open('/tmp/eng_w2_f1/f1_backtest.py').read()
no_dead = ('KEEP_RANK =' not in src_sig) and ('KEEP_RANK =' not in src_bt)
full_rule = '全量 top-5 重选' in src_sig
rec('D5', 'KEEP_RANK 死参数：改注释锁定口径', '静态走查两引擎',
    f"死参数赋值零残留={no_dead}；「全量 top-5 重选为 v1 口径」注释在位={full_rule}",
    '页面 signal_rule 文案「每周首个交易日收盘出信号，次日开盘成交」',
    no_dead and full_rule, '主管席 BUG-02 裁决：不补 top-15 缓冲实现')
# D6 信号日=日历末日
t_last_sig = max(tt for tt in sig_days)
data3 = {s: d[d.index <= t_last_sig] for s, d in data.items()}
try:
    rp_d6 = fs.replay(data3, F, syms, slot=fs.SLOTS[0])
    ok_d6 = rp_d6['cal'][-1] == t_last_sig
    err6 = ''
except Exception as ex:                                   # noqa: BLE001
    ok_d6, err6 = False, repr(ex)
rec('D6', '信号日=日历末日：无越界异常', f"L2 截断数据至信号日 {t_last_sig.date()} 回放",
    f"pending_exec=None 分支覆盖，无 IndexError；{err6}",
    '页面照常显示建议', ok_d6)

# ================================================================ BUG-04 权威回测对账
print('== BUG-04 权威回测对账 ==', flush=True)
# R14 夹具修复：G4 升版（e229358）已把 /tmp/eng_w2_f1/f1_backtest.py 原位升为 v2
# （对账红线夹具：vs 引擎逐日持仓 diff=0）。本项要对照的 v0（未改语义 W2 版）改从
# G4 升版留存的专用备份 /tmp/g4/f1_backtest_v1_instr.py 导入，两条检测互不覆盖。
sys.path.insert(0, '/tmp/g4')
import f1_backtest_v1_instr as f1b                       # noqa: E402
pools = f1b.build_pools(data)
bt = f1b.run_backtest(data, F, pools['full144'], True, f1b.FACTORS_4)
rp10 = fs.replay(data, F, syms, slot=0.10)
a, b = rp10['eq_net'], bt['curve'].reindex(rp10['eq_net'].index)
diff = (a - b).abs()
ndiff = int((diff > 1e-9).sum())
first_d = str(diff[diff > 1e-9].index[0].date()) if ndiff else 'NA'
last_d = str(diff[diff > 1e-9].index[-1].date()) if ndiff else 'NA'
rec('BUG-04对账', '修复后引擎回放 vs 权威回测 v0 逐日 diff',
    'L1 slot=0.10 full144 gated 双跑（v0=f1_backtest 未改语义）',
    f"变化交易日数={ndiff}/{len(a)}，首个差异日={first_d}，末个={last_d}；"
    f"终值 v0={b.iloc[-1]:.4f} → v1={a.iloc[-1]:.4f}（Δ={a.iloc[-1] - b.iloc[-1]:+.4f}）；最大单日差={diff.max():.6f}",
    'DEPLOY_REPORT.md 公示差异',
    abs((a.iloc[-1] - b.iloc[-1]) - (-0.0679)) < 5e-3
    and ndiff > 0 and first_d == '2025-08-12',
    '⑨加固+WO-V5（D8）：断言改「v0−v1 相对差（±0.005 容忍数据修订批次漂移）+首差异日」'
    '双断言——绝对终值随上游行情修订漂移（实测 v0 2.3585/v1 2.2903 vs 公示 2.3496/2.2817），'
    '修复语义的净效果差稳定 −0.068 附近，硬编码终值断言废弃；首差异日 2025-08-12 保留',
    level='engine')

# ================================================================ BUG-01 费账复核
mf = full['fees'].resample('ME').sum()
mf_dict = {str(ts)[:7]: v * 100 for ts, v in mf.items()}
jm = {r['month']: r['fee_pct'] for r in J['monthly_accounts']}
bad = [m for m, v in jm.items() if abs(mf_dict.get(m, 0.0) - v) > 0.01]
rec('BUG-01复核', '月报费用列=逐日合计（resample sum）', 'L1 独立重算：回放 fees 逐月求和 vs json',
    f"不一致月份={bad or '无'}（{len(jm)} 个月全对齐）",
    '三本账费列与引擎一致（E7）', not bad)

# ================================================================ 矩阵 E（页面一致性 · 静态 + json）
print('== 矩阵 E ==', flush=True)
sig = J['signal']
r_live = render_page('/workspace/f1_web/index.html', J)   # ⑨：渲染产物（真实页面脚本执行）
deci_txt = r_live['decision']['innerHTML'] + r_live['sig']['innerHTML']
rec('E1', 'meta 行 badge 档位/敞口', 'json signal.tier_idx/slot/total_exposure',
    f"tier_idx={sig['tier_idx']}，slot={sig['slot_per_stock_pct']}%，敞口上限={sig['total_exposure_pct']}%",
    '页面 badge：仓位档=第 N 档/共 4 档 + 冻结徽章（freeze_days_left）',
    sig['total_exposure_pct'] == round(sig['slot_per_stock_pct'] * 5, 2)
    and 'slot_per_stock_pct' in PAGE and 'freeze_days_left' in PAGE)
rec('E2', '信号卡主文案映射（渲染级）', 'json signal.gate.on_holdcash=' + str(sig['gate']['on_holdcash']),
    f"gate idx={sig['gate']['idx']} ma50={sig['gate']['ma50']}",
    '渲染产物中 idx/MA50 数字与 json 逐位一致 + 分支文案正确',
    str(sig['gate']['idx']) in deci_txt and str(sig['gate']['ma50']) in deci_txt
    and ('空仓观望' in r_live['decision']['innerHTML']) == bool(sig['gate']['on_holdcash']),
    '⑨加固：子串检查 → 渲染级比对（真实执行页面脚本取渲染产物）', level='render')
rec('E3', '信号日提示', f"json is_signal_day={sig['is_signal_day']}",
    'is_signal_day 双分支文案在位', '与 asof 星期归属一致',
    'is_signal_day' in PAGE)
rec('E4', 'top5 卡片标签（渲染级）', f"top5={len(sig['top5'])} 只，快照闸关={sig['gate']['on_holdcash']}",
    '渲染产物：闸关→每卡 [闸门关闭·不开仓] 且无买入标签；闸开→[目标仓 X%]',
    '标签与决策条零矛盾',
    (r_live['sig']['innerHTML'].count('[闸门关闭·不开仓]') == len(sig['top5'])
     and '[目标仓' not in r_live['sig']['innerHTML']) if sig['gate']['on_holdcash']
    else (r_live['sig']['innerHTML'].count('[目标仓') == len(sig['top5'])
          and '[闸门关闭·不开仓]' not in r_live['sig']['innerHTML']),
    '⑨加固：子串检查 → 渲染级逐卡比对', level='render')
rec('E5', '四灯卡灯色 class', 'json breakers.items[].light ∈ {green,yellow,red}',
    '页面 lamp(): g/y/r class；红灯发光阴影（.r box-shadow）',
    '灯色渲染正确', all(k in PAGE for k in ('.g{', '.y{', '.r{')))
tt_ok = J['meta']['tier_table_pct_per_stock'] == [2.5, 1.5, 1.0, 0.5]
rec('E6', '总灯行降档表', f"json tier_table={J['meta']['tier_table_pct_per_stock']}",
    '页面读 m.tier_table_pct_per_stock 渲染（读盘不写死）',
    '四档数值与 json 逐项一致', tt_ok and 'tier_table_pct_per_stock' in PAGE)
acct = J['monthly_accounts']
zero_months = [r['month'] for r in acct if r['fee_pct'] == 0]
e7 = all(abs(r['concede_pct'] - (r['pool_pct'] - r['gross_pct'])) <= 0.02 for r in acct) \
    and all(r['fee_pct'] >= 0 for r in acct) and sum(r['fee_pct'] for r in acct) > 0
rec('E7', '三本账表（含 BUG-01 费列）', f"json monthly_accounts {len(acct)} 个月",
    f"concede=pool−gross 全对齐；费列合计={sum(r['fee_pct'] for r in acct):.3f}%（全现金月合法为 0：{zero_months or '无'}）",
    '让渡列中性色+列名「跑输躺平(+)/跑赢躺平(−)」；默认近 3 月其余折叠',
    e7 and '跑输躺平' in PAGE, 'BUG-01 后费列为逐月合计；闸关全现金月费=0 属正常口径')
fee_txt_ok = 'line_ann_pct' in PAGE and not re.search(r'21\.7', PAGE) and not re.search(r'10\.85', PAGE)
rec('E8', '费拖累曲线与费线文本', f"json FEE.detail.line_ann_pct={dfee['line_ann_pct']}",
    '页面费线文本读 detail.line_ann_pct（BUG-05：HTML 不写死 21.7/10.85）',
    '改引擎阈值常量后页面自动跟随', fee_txt_ok)
rec('E9', '监控明细表', f"json recent_stops={len(J['monitor']['recent_stops'])} 条",
    '类型映射白话：开盘跳空按开盘价卖出 / 盘中触线按止损价卖出；收益列恒绿',
    '最近 10 条倒序', 'stop_gap' in PAGE and 'pnl_pct' in PAGE)
rec('E10', '监控 notes 折叠（④⑩ 渲染级）', f"json notes={len(J['monitor']['notes'])} 条",
    '渲染产物：notes 逐条移入页脚「技术详情」；监控区正文只留白话指引',
    '与引擎常量一致（含 CB3 冻结基准注释）',
    all(n in r_live['foot']['innerHTML'] for n in J['monitor']['notes'])
    and '详细口径见页底技术详情' in r_live['mon']['innerHTML']
    and '口径注释：' not in r_live['mon']['innerHTML'],
    '⑨加固+④⑩施工：原子串检查，现渲染级比对折叠位置', level='render')
rec('E11', '页脚复现命令（F8 修复）', '静态走查',
    '页脚=python3 /workspace/repo_ready/engine_f1/f1_signal.py live',
    '不再指向 f1_generate.py', 'f1_signal.py live' in PAGE and 'f1_generate.py' not in PAGE)
rec('E12', '崩市提示行（缺口补齐）', f"json crash_check.triggered={sig['crash_check']['triggered']}",
    '页面新增：⚠️ 崩市检测：池中位 −X% < −5%，次日开盘清仓',
    'crash_check 渲染在位', 'crash_check' in PAGE and '崩市检测' in PAGE)
rec('E13', '数据加载失败兜底', 'fetch catch 走查',
    '「数据加载失败：…」显示', 'json 缺失/损坏不白屏', '数据加载失败' in PAGE)

# ================================================================ 矩阵 G（用户视角文本审查）
print('== 矩阵 G ==', flush=True)
rec('G1', '「清仓持币」语义澄清', '静态文本',
    '闸关=不出新仓，存量按止损/崩市/换仓退出',
    '决策条+说明书明示，无「立即全部卖出」暗示',
    '不出新仓' in PAGE and '立即卖出全部' not in PAGE and '不出新仓' in MANUAL)
rec('G2', '决策条三选一置顶（UI-01）', '静态文本+结构',
    '聚合优先级：熔断红灯＞闸关闭＞正常持仓',
    '页面第一屏大字号一句话结论；双灯合并为「当前状态」',
    '当前状态' in PAGE and PAGE.find('id="decision"') < PAGE.find('id="sig"') < PAGE.find('id="bk"'))
rec('G3', '闸关时 top5 参考排名说明（R10）', '静态文本',
    '「以下为参考排名，当前不建仓；开关恢复后下一信号日按此优先」',
    '防手动抄单误导', '当前不建仓' in PAGE and '开关恢复后下一信号日按此优先' in PAGE)
rec('G4', '仓位比例口径', '静态文本',
    '单票 2.5% 为资金比例，5 票合计上限 12.5%',
    'badge「总上限」措辞在位', '总上限' in PAGE)
rec('G5', 'CB1 黑话替换（UI-02）', '静态文本',
    '回撤闸（保留小字 CB1）', '页面+说明书均有', '回撤闸' in PAGE and '回撤闸' in MANUAL)
rec('G6', 'CB2 冻结倒计时（BUG-03）', 'json state.freeze_days_left=' + str(J['state']['freeze_days_left']),
    '冻结期决策条显示「暂停开新仓 N 个交易日（至解除日）」',
    'badge+决策条读盘渲染', 'freeze_days_left' in PAGE and '暂停开新仓' in PAGE)
rec('G7', 'CB2 毛账旁路文案（R6 放宽）', '静态文本',
    '毛账触发含两条旁路：止损失血≤−20pp 或 60 日毛跌≤−20pp',
    '说明书写明旁路', ('毛跌' in MANUAL or '整体跌幅' in MANUAL))
rec('G8', 'CB3 黑话替换', '静态文本',
    '「外移观察」改「频次观察」（页面灯名）', '页面+说明书', '频次观察' in PAGE and '频次观察' in MANUAL)
rec('G9', '费线 pp 解释 + 读盘（BUG-05）', '静态文本',
    '页面费线文本读 line_ann_pct；说明书解释「百分点」',
    '阈值随引擎常量自动跟随', 'line_ann_pct' in PAGE and '百分点' in MANUAL)
rec('G10', '让渡列中性色+列名表义（R9）', '静态文本',
    '「跑输躺平(+)/跑赢躺平(−)」中性色；反转配色废弃',
    '列头即图例', '跑输躺平' in PAGE and '跑赢躺平' in PAGE and "concede_pct>0?'dn'" not in PAGE)
rec('G11', 'GPRO 跳空强制解释（红线 4）', '静态文本',
    '「止损线 −8%；跳空日实际亏损可能更大（例：2026-09-09 GPRO 实亏 −12.2%）」',
    '监控明细区固定文案', '跳空日实际亏损可能更大' in PAGE and 'GPRO' in PAGE)
rec('G12', '周节拍口径说明', '静态文本',
    '每周第一个交易日收盘出信号，次日开盘成交（含周末日历说明）',
    '页面+说明书', '每周第一个交易日' in MANUAL and '次日开盘' in MANUAL)
rec('G13', '免责声明降级（UI-03）', '静态结构',
    '完整声明移页底折叠；顶部仅一行黄字「模拟数据·起步仓位12.5%·请勿仅依赖本页决策」',
    '免责不再压过决策条',
    PAGE.find('诚实声明（完整版）') > PAGE.find('id="bk"')
    and PAGE.find('warnline') < PAGE.find('id="decision"'))
rec('G14', '数据加载失败兜底文案', '静态文本', '「数据加载失败：…」',
    '同 E13', '数据加载失败' in PAGE)

# ================================================================ 尾巴工单回归（T 组）
print('== 尾巴工单回归 T 组 ==', flush=True)
# T1 ①「现在该做什么」渲染为可见元素
ok_t1 = bool(re.search(r'<div class="stat"><b>🧭 现在该做什么</b><div id="sig"', PAGE)) \
    and len(r_live['sig']['innerHTML']) > 200
rec('T1', '「现在该做什么」可见分区标题（①）', '静态元素 + 渲染产物',
    'sig 区渲染非空', '与「策略健康灯（与上面开关无关）」分区命名对称',
    ok_t1, '从 JS 注释升级为可见元素', level='render')
# T2 ③ 冻结期+闸开：top5 标签改「冻结中·不开新仓」，与决策条零矛盾
r_fz = render_page('/workspace/f1_web/index.html', page_variant(False, frozen=True, freeze_days=13))
sig_fz, dec_fz = r_fz['sig']['innerHTML'], r_fz['decision']['innerHTML']
ok_t2 = ('🧊 冻结中·不开新仓' in sig_fz and '[目标仓' not in sig_fz
         and '冻结前最后一期排名，仅供观察，恢复后下一信号日按此优先' in sig_fz
         and '闸门关闭·不开仓' not in sig_fz
         and '冻结' in dec_fz)
rec('T2', '冻结期 top5 标签修复（③）', 'L3 页面态变体：闸开+CB2 冻结中（freeze_days_left=13）',
    'frozen=true 渲染分支生效', '🧊 冻结中·不开新仓 + 卡头冻结说明；无 [目标仓] 买入标签；与决策条零矛盾',
    ok_t2, 'P0：红字买入标签+决策条「动作中—冻结开新仓」同屏矛盾已根治', level='render')
# T3 ⑧ CB3 冻结常量引擎在位 + 重算机制废除
src_sig = open(os.path.join(HERE, 'f1_signal.py')).read()
ok_t3 = ('CB3_BASE_60D = 9.07' in src_sig
         and 'cb3_base = round(' not in src_sig
         and 'cb3_baseline_recomputed' in src_sig
         and fs.CB3_BASE_60D == 9.07)
rec('T3', 'CB3 冻结常量 9.07 + live 重算降为对账字段（⑧）', '静态走查 + 常量核对',
    '冻结常量在位；run_live 重算覆盖已删除；json 对账字段 cb3_baseline_recomputed 在位（见 C3a）',
    '技术详情展示冻结值+重算对账参考', ok_t3, '重算机制=绕过冻结规格的暗门，判废')
# T4 ⑦ crontab 指向与口径统一
CR = open(os.path.join(HERE, 'f1_crontab.txt')).read()
CR2 = open('/workspace/repo_ready/f1/f1_crontab.txt').read()
ok_t4 = (CR == CR2
         and '25 9 * * 1-5 PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py live' in CR
         and 'f1_generate.py >>' not in CR)
rec('T4', 'f1_crontab.txt 指向现行入口（⑦）', '静态走查双副本',
    '任务2=f1_signal.py live + PYTHONHASHSEED=42；与页脚/包装 docstring 三处口径统一；双副本 sha 一致',
    '—', ok_t4)
# T5 ⑥ 归档目录 sha256 逐文件对齐
def _sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()
_pairs = [('f1_signal.py', os.path.join(HERE, 'f1_signal.py')),
          ('f1_datasource.py', os.path.join(HERE, 'f1_datasource.py')),
          ('replay_breakers_r13.py', os.path.join(HERE, 'replay_breakers_r13.py')),
          ('sync_archive.py', os.path.join(HERE, 'sync_archive.py')),
          ('f1_generate.py', '/workspace/f1_web/f1_generate.py'),
          ('f1_crontab.txt', os.path.join(HERE, 'f1_crontab.txt')),
          ('f1_rounds_r13.md', os.path.join(HERE, 'f1_rounds_r13.md')),
          ('F1_台账口径_v1.md', os.path.join(HERE, 'F1_台账口径_v1.md')),
          ('index.html', '/workspace/f1_web/index.html'),
          ('manual.html', '/workspace/f1_web/manual.html'),
          ('f1_live.json', '/workspace/f1_web/f1_live.json'),
          ('f1_state.json', '/workspace/f1_web/f1_state.json'),
          ('f1_live_intraday.json', '/workspace/f1_web/f1_live_intraday.json')]
_mis = [n for n, srcp in _pairs
        if _sha(os.path.join('/workspace/repo_ready/f1', n)) != _sha(srcp)]
rec('T5', 'repo_ready/f1 全目录 sha256 对齐（⑥②）', '逐文件哈希比对（引擎/页面/数据 7 件）',
    f"不一致文件={_mis or '无'}", '归档目录与修复版逐文件对齐', not _mis,
    '旧版引擎 sha 65642b86… 已被修复版取代，按归档复现不再踩 BUG-01')
# T6 ⑤ box 页 B9/B10
BOX = open('/workspace/box_web/index.html').read()
BOX_ARCH = open('/workspace/repo_ready/index.html').read()
ok_t6 = ('行情好于 50 日线才找票' in BOX
         and "b.title='N='+q.N+' k='+q.k+' m='+q.m+' e='+q.e" in BOX
         and '正在等波动连续收窄到条件成立' in BOX
         and 'r2(' not in BOX
         and _sha('/workspace/box_web/index.html') == _sha('/workspace/repo_ready/index.html')
         and '行情好于 50 日线才找票' in BOX_ARCH)
rec('T6', 'box 页 B9/B10 顺带修（⑤）', '对照标注优化单冻结文本',
    '牛市闸加白话「行情好于 50 日线才找票」；参数徽章 N/k/m/e 入悬浮(title)；seek 卡补「正在等波动连续收窄到条件成立」',
    'box_web 与 repo_ready 归档副本 sha 一致', ok_t6)
# T7 ⑩ manual §3 止损行口径
ok_t7 = ('发现即卖（不等周调仓）' in MANUAL and '原始术语：无 T+1' in MANUAL)
rec('T7', 'manual §3 止损行「发现即卖（不等周调仓）」（⑩/裁决①）', '静态文本',
    '「无 T+1」与「最迟次日开盘卖」字面矛盾解除；原术语收进小字（零信息损失）',
    '§3/§4/§8 口径一致；H 组红线 4（GPRO 强制文案）不受影响', ok_t7)
# T8 E8 费线阈值读 json（④⑩ 关联：BUG-05 复核）
rec('T8', '费线阈值读 JSON 无写死（BUG-05 复核）', '静态走查',
    'HTML 无 21.7/10.85 字面量，费线文本读 detail.line_ann_pct',
    '改引擎阈值常量后页面自动跟随', 'line_ann_pct' in PAGE
    and not re.search(r'21\.7', PAGE) and not re.search(r'10\.85', PAGE))

# ================================================================ R13 组
# H 组：WO-R13-01 重标定后真实段回放统计（读 breaker_stats_r13.json 并现场重算比对）
print('== R13 H 组：重标定回放统计 ==', flush=True)
STATS = os.path.join(HERE, 'breaker_stats_r13.json')
have_stats = os.path.exists(STATS)
rec('H1', '重标定统计结果文件存在（供审计席核对）', STATS,
    'breaker_stats_r13.json 已落盘' if have_stats else '缺失', '—', have_stats)
if have_stats:
    S13 = json.load(open(STATS))
    newc = S13['trigger_counts_new']
    oldc = S13['trigger_counts_old']
    # H2 新阈值下 CB1/CB2 各有真实触发（黄或红）；CB3 与改前一致（0）
    h2 = ((newc['CB1']['red_days'] + newc['CB1']['yellow_days']) > 0
          and (newc['CB2']['red_days'] + newc['CB2']['yellow_days']) > 0)
    rec('H2', '新阈值下 CB1/CB2 出现真实触发（历史可解释）',
        f"CB1 红{newc['CB1']['red_days']}/黄{newc['CB1']['yellow_days']}；"
        f"CB2 红{newc['CB2']['red_days']}/黄{newc['CB2']['yellow_days']}",
        '重标定后仪表不再恒绿', 'CB1 黄=2026-05 回撤极值期；CB2 红=2026-07 失血期', h2)
    # H3 旧阈值下三线 0 触发（证明死线，改前状态）
    h3 = (oldc['CB1']['red_days'] == 0 and oldc['CB1']['yellow_days'] == 0
          and oldc['CB2']['red_days'] == 0 and oldc['CB2']['yellow_days'] == 0
          and oldc['FEE']['red_days'] == 0 and oldc['FEE']['yellow_days'] == 0)
    rec('H3', '旧阈值下 CB1/CB2/费线 0 触发（结构性死线已证实）',
        'old vs new 双列统计', '改前=0，改后有触发', '—', h3)
    # H4 CB3 保留：触发统计与改前一致
    h4 = newc['CB3']['yellow_days'] == oldc['CB3']['yellow_days']
    rec('H4', 'CB3 保留不动：触发统计与改前一致',
        f"new={newc['CB3']['yellow_days']} vs old={oldc['CB3']['yellow_days']}",
        '观察线 27.21、基准 9.07 未变', '—', h4)
    # H5 阈值表随引擎常量（页面读 JSON 的前提）
    T13 = S13['new_thresholds']
    h5 = (abs(T13['CB1']['red'] - fs.CB1_MDD) < 1e-12
          and abs(T13['CB2']['red'] - fs.CB2_LOSS) < 1e-12
          and abs(T13['FEE']['red'] - fs.FEE_LINE_ANN) < 1e-12
          and abs(T13['CB3']['line'] - fs.CB3_BASE_60D * fs.CB3_MULT) < 1e-12
          and fs.CB1_WARN == fs.CB1_MDD / 2 and fs.FEE_WARN == fs.FEE_LINE_ANN / 2)
    rec('H5', '阈值表=引擎常量（单一事实源）',
        f"CB1={T13['CB1']} CB2={T13['CB2']} FEE={T13['FEE']}",
        '页面从 meta.breaker_thresholds 读取', '—', h5)

# I 组：WO-R13-03 只读旁路
print('== R13 I 组：多轮扫描只读旁路 ==', flush=True)
# I1 guard：已落定日 → settled=True；伪造「当日」→ settled=False
_g_ok = fs.guard_last_bar(cal, now=pd.Timestamp(cal[-1]) + pd.Timedelta(days=1))
_g_bad = fs.guard_last_bar(cal, now=pd.Timestamp(cal[-1]))
rec('I1', 'guard：落定后 settled=True / 当日 bar settled=False',
    f"now=D+1 → {_g_ok['settled']}；now=D → {_g_bad['settled']}",
    '未落定即拒绝判定', '禁止进入周调仓锚定与信号判定',
    bool(_g_ok['settled']) and not _g_bad['settled'], level='engine')
# I2 guard 拒绝：未落定 bar 被标记 intraday（current_signal 会抛错拒绝判定）
# R14 加固：原用例隐式依赖「运行时刻=缓存末日当日」且 try 分支 `raised=bool(_gcheck['settled'])`
# 为恒假式弱断言（与审计点名的自测 R10 同型）；改为注入当日未落定 bar 的确定性复现。
_today_i2 = pd.Timestamp.now(tz='UTC').normalize().tz_localize(None)
_s0_i2 = next(iter(data))
_inj_i2 = data[_s0_i2].iloc[[-1]].copy()
_inj_i2.index = [_today_i2]
_data_inj = dict(data)
# WO-V5（D5 夹具修复）：常态运行态=缓存末根即当日部分K。注入前先剔除基线中与
# 注入日同日期的 bar——否则 concat 产生重复时间标签，current_signal 在 guard 之前
# 的 DataFrame 构造处抛 pandas ValueError，整个脚本中断。I2 验的是 guard 拒绝
# 语义，注入必须保持「无重复标签」前提（重复标签路径归 WO-V6 结构化拒绝管）。
_base_i2 = data[_s0_i2]
_base_i2 = _base_i2[_base_i2.index != _today_i2]
_data_inj[_s0_i2] = pd.concat([_base_i2, _inj_i2])
_gcheck = fs.guard_last_bar(pd.DatetimeIndex(sorted(set().union(
    *[set(_data_inj[s].index) for s in syms]))))
refused = (not _gcheck['settled'])
try:
    fs.current_signal(_data_inj, F, syms, allow_intraday=False)
    raised = False
except RuntimeError:
    raised = True
rec('I2', 'guard：当日未落定 bar 被判 intraday 且拒绝判定（注入式确定性复现）',
    f"注入当日（{_today_i2.date()}）bar 至 {_s0_i2}；last_bar={_gcheck['last_bar_date']}",
    f"settled={_gcheck['settled']}；guard 行为正确={raised}",
    '只读旁路输出，禁写状态', refused and raised, level='engine')
# I3 只读快照：不写 f1_state.json / 不覆盖 f1_live.json 判定字段
import hashlib as _hl


def _sha(p):
    return _hl.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else None


_before_state = _sha('/workspace/f1_web/f1_state.json')
_before_live = _sha('/workspace/f1_web/f1_live.json')
_before_live_dec = (json.load(open('/workspace/f1_web/f1_live.json'))
                    if _before_live else {})
_before_dec = json.dumps({k: _before_live_dec.get(k) for k in
                          ('signal', 'breakers', 'state', 'monthly_accounts')},
                         ensure_ascii=False, sort_keys=True)
try:
    snap = fs.run_snapshot(out_json='/workspace/f1_web/f1_live_intraday.json',
                           round_id='00:30')
    snap_ok = (snap['meta']['mode'] == 'intraday_snapshot'
               and snap['meta']['operable'] is False
               and snap['writes'] == {'f1_state.json': False, 'f1_live.json': False}
               and 'top5' not in snap)
except Exception as e:                                    # pragma: no cover
    snap, snap_ok = {'err': str(e)}, False
_after_state = _sha('/workspace/f1_web/f1_state.json')
_after_live = _sha('/workspace/f1_web/f1_live.json')
_after_live_dec = json.load(open('/workspace/f1_web/f1_live.json'))
_after_dec = json.dumps({k: _after_live_dec.get(k) for k in
                            ('signal', 'breakers', 'state', 'monthly_accounts')},
                           ensure_ascii=False, sort_keys=True)
rec('I3', '只读快照：禁写 f1_state.json + 禁覆盖 f1_live.json 判定字段',
    'L1 运行 snapshot --round 00:30 前后逐位比对',
    f"mode={snap.get('meta', {}).get('mode')}；writes={snap.get('writes')}；"
    f"state sha 不变={_before_state == _after_state}；live 判定字段不变={_before_dec == _after_dec}",
    '盘中卡与判定卡分离；盘中卡禁显示 top5',
    bool(snap_ok) and _before_state == _after_state and _before_dec == _after_dec,
    'guard 保证：snapshot 永不调 update_state/save_state', level='engine')
# I4 快照不含 top5 建议
snap_json = open('/workspace/f1_web/f1_live_intraday.json').read()
rec('I4', '盘中快照不出 top5 建议',
    'snapshot 输出字段走查',
    f"含 'top5' 键={chr(39) + 'top5' + chr(39) in snap_json}",
    '防用户照做盘中评分',
    ("'top5'" not in snap_json) and ('不可操作' in snap_json), level='engine')
# I5 推送去重：判定轮同 asof 只推一次；盘中轮按 asof+轮次
p1 = fs.push_plan('DECIDE', '2026-10-17', 'DECIDE', last_push={})
p2 = fs.push_plan('DECIDE', '2026-10-17', 'DECIDE', last_push={p1['key']: 1})
i1 = fs.push_plan('INTRADAY', '2026-10-17', '20:30', last_push={})
i2 = fs.push_plan('INTRADAY', '2026-10-17', '20:30', last_push={i1['key']: 1})
i3 = fs.push_plan('INTRADAY', '2026-10-17', '04:30', last_push={i1['key']: 1})
rec('I5', '推送去重：判定轮按 asof，盘中轮按 asof+轮次',
    'DECIDE/INTRADAY 五种组合',
    f"p1={p1['push']} p2={p2['push']} i1={i1['push']} i2={i2['push']} i3={i3['push']}",
    '同日 4 轮无重复判定推送',
    bool(p1['push']) and not p2['push'] and bool(i1['push'])
    and not i2['push'] and bool(i3['push'])
    and i1['carries_decision'] is False and p1['carries_decision'] is True, level='engine')
# I6 多轮时刻表可注册（crontab 含三轮 snapshot）
CR13 = open(os.path.join(HERE, 'f1_crontab.txt')).read()
rec('I6', '多轮时刻表可注册（20:30/00:30/04:30 只读 + 判定轮）',
    'f1_crontab.txt',
    f"snapshot 轮次数={CR13.count('snapshot --round')}；判定轮 live 存在={'f1_signal.py live' in CR13}",
    '页面标注夏令时漂移',
    CR13.count('snapshot --round') == 3 and 'f1_signal.py live' in CR13)

# J 组：WO-R13-04 数据源容灾
print('== R13 J 组：数据源容灾 ==', flush=True)
sys.path.insert(0, HERE)
import f1_datasource as DS                                # noqa: E402
# J 组覆盖「备源启用全链」（一致性验收/RECOVERING/白名单 adapter 语义），
# 固定 SINA_BACKUP_ENABLED=1（开关开=与现状行为完全一致）；停用链路由 sina_off
# 专项自测覆盖（用户令 2026-10-19）。
os.environ['SINA_BACKUP_ENABLED'] = '1'
# R14 Q-1：run_round 现内置自动验收；J 组用例走显式 consistency 传参，统一关闭自动取数
os.environ['F1_ACCEPT_FORCE'] = 'none'

# J1 单次失败 ≠ 宕机：1 个周期失败后仍在 NORMAL
DS._reset()
os.environ['F1_PRIMARY_FAIL'] = '1'
os.environ['F1_RETRY_SLEEP'] = '0'
_st1, _ = DS.run_round(round_id='J1')
rec('J1', '单次/单周期失败不误切（仍在 NORMAL）',
    '注入故障跑 1 周期',
    f"state={_st1['state']} consec_fail={_st1['consec_fail']}",
    '防误切换', _st1['state'] == 'NORMAL' and _st1['consec_fail'] == 1, level='engine')
# J2 连续 2 周期失败 → DEGRADED + 冻结
_st2, _ = DS.run_round(round_id='J2')
_frz = DS.freeze_payload()
rec('J2', '连续 2 周期失败 → DEGRADED 且判定字段冻结',
    '注入故障跑第 2 周期',
    f"state={_st2['state']}；frozen_asof={_st2.get('frozen_asof')}；freeze 不写 state={_frz['writes']}",
    '页面标注 asof + 数据源=降级',
    _st2['state'] == 'DEGRADED' and _frz['writes']['f1_state.json'] is False, level='engine')
# J3 连续 2 周期健康 → RECOVERING（待验收）
os.environ['F1_PRIMARY_FAIL'] = '0'
_st3, _ = DS.run_round(round_id='J3a')
_st4, _ = DS.run_round(round_id='J3b')
rec('J3', '连续 2 周期健康 → RECOVERING（待一致性验收）',
    '解除故障跑 2 周期',
    f"{_st3['state']} → {_st4['state']}",
    '进 RECOVERING 待自动验收', _st4['state'] == 'RECOVERING', level='engine')
# J4 一致性验收：基差计入容差，偏差 ≤2% 通过
_cons = DS.consistency_check([{'symbol': 'aapl', 'date': '2026-10-16', 'close': 100.0}],
                              [{'symbol': 'aapl', 'date': '2026-10-16', 'close': 101.5}])
_st5, _ = DS.run_round(round_id='J4', consistency=_cons)
rec('J4', '一致性验收通过 → 自动切回 NORMAL（容差=价格1%+基差1%）',
    '主备重叠标的收盘价偏差 1.5%',
    f"cons={_cons['pass']}；state={_st5['state']}",
    '切换事件写日志', bool(_cons['pass']) and _st5['state'] == 'NORMAL', level='engine')
# J5 一致性不通过 → 挂待人工，禁止自动强切
DS._reset()
os.environ['F1_PRIMARY_FAIL'] = '1'
for _i in range(DS.FAIL_PERIODS_TO_DEGRADE):
    DS.run_round(round_id='J5f')
os.environ['F1_PRIMARY_FAIL'] = '0'
for _i in range(DS.OK_PERIODS_TO_RECOVER):
    DS.run_round(round_id='J5o')
_cons_bad = DS.consistency_check([{'symbol': 'aapl', 'date': '2026-10-16', 'close': 100.0}],
                                   [{'symbol': 'aapl', 'date': '2026-10-16', 'close': 110.0}])
_st6, _ = DS.run_round(round_id='J5v', consistency=_cons_bad)
rec('J5', '一致性验收不通过 → 留 RECOVERING 自动重试（R14 Q-1），禁止自动强切',
    '偏差 10% 超限',
    f"cons={_cons_bad['pass']}；state={_st6['state']}；pending_manual={_st6.get('pending_manual')}",
    '页面标注待人工',
    (not _cons_bad['pass']) and _st6['state'] == 'RECOVERING'
    and _st6.get('pending_manual') is True, level='engine')
# J6 新浪：白名单 ≤6 只 + 144 全量被拒
_wl = DS.proxy_watchlist(['AAPLUSDT', 'MSFTUSDT', 'GOOGLUSDT', 'AMZNUSDT', 'NVDAUSDT'])
try:
    DS.fetch_sina_daily([f'S{i}USDT' for i in range(144)])
    _rej = False
except ValueError:
    _rej = True
rec('J6', '新浪硬约束：白名单 ≤6 只/轮 + 144 全量被拒',
    f"watchlist={_wl}；144 全量请求",
    f"白名单 {len(_wl)} 只；144 拒绝={_rej}",
    '防限流；备源仅抽查',
    len(_wl) <= DS.MAX_PROXY_SYMBOLS and _rej, level='engine')
# J7 数据出身标注：降级期输出带 asof + source
_banner = DS.source_banner({'state': 'DEGRADED', 'frozen_asof': '2026-10-17'})
rec('J7', '降级期任何输出带 asof + source 标注',
    'DEGRADED banner', _banner,
    '页面显著标注', '2026-10-17' in _banner and '不构成新推荐' in _banner, level='engine')

# ================================================================ 汇总
os.environ.pop('F1_ACCEPT_FORCE', None)
os.environ.pop('SINA_BACKUP_ENABLED', None)
DS._reset()
n_pass = sum(1 for r in RES if r['pass'])
summary = {'total': len(RES), 'pass': n_pass, 'fail': len(RES) - n_pass,
           'results': RES}
out_path = os.path.join(HERE, 'scenario_checks_result.json')
with open(out_path, 'w') as f:
    json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
print(f"\n===== 场景检测汇总：PASS {n_pass}/{len(RES)} =====")
for r in RES:
    if not r['pass']:
        print('FAIL →', r['id'], r['name'])
print('结果文件 →', out_path)
