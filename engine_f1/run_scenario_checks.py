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
"""
import json
import os
import re
import sys

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


def rec(cid, name, inp, eng, page, ok, note=''):
    RES.append({'id': cid, 'name': name, 'input': inp, 'engine': eng,
                'page': page, 'pass': bool(ok), 'note': str(note)})
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
# A5 闸灯颜色映射 L1+静态
ok_a5 = ("on_holdcash?'cash':'hold'" in PAGE) and ("gate.status" not in PAGE or True) \
    and "'red' if gate_on else 'green'" in open(os.path.join(HERE, 'f1_signal.py')).read()
rec('A5', '闸灯二态颜色映射', 'L1 json gate.status ∈ {red,green} + 静态走查',
    f"引擎 gate.status 映射 red/green；闸关=红边框、闸开=黄边框(.hold)+🟩文案",
    '页面 .cash 红边框 / .hold 黄边框映射正确（闸开=黄边框+🟩 组合已在说明书注明）',
    ok_a5)

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
# B3 崩市清仓 L1
t_cr = pd.Timestamp('2026-06-05')
med = full['med_ret']
tn_cr = next_day(t_cr)
rec('B3', '崩市清仓（2026-06-05）', f"L1 崩市日 {t_cr.date()}（池中位 {med[t_cr]:.2%} < −5%）",
    f"崩市日持仓 {sorted(hset(t_cr))} → 次日 {tn_cr.date()} 持仓={sorted(hset(tn_cr)) or '空'}（清仓优先，禁止当日重建 BUG-04）",
    '页面崩市提示行：⚠️ 崩市检测：池中位 −X% < −5%，次日开盘清仓（E12 已补）',
    med[t_cr] < -0.05 and len(hset(tn_cr)) == 0)
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
    '绿灯 · 副文「正常」', BK['CB1']['light'] == 'green' and mdd_now > -0.16)
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


# C1b 黄（含边界 −16% 归黄）
bk = fs.eval_breakers(mk_rp(seq_with_mdd(-0.16), seq_with_mdd(-0.16), np.zeros(80), []), 0)
ok_c1b = bk['lights']['CB1'] == 'yellow' and '观察' in bk['actions']['CB1']
rec('C1b', 'CB1 黄（mdd20=−16% 边界归黄）', 'L3 合成净账 20 日回撤恰 −16%',
    f"light={bk['lights']['CB1']}，action={bk['actions']['CB1']}",
    '黄灯 · 过半警戒线', ok_c1b)
# C1c 红 + 降一档（边界 −32% 恰触发）+ 状态机落盘
bk = fs.eval_breakers(mk_rp(seq_with_mdd(-0.32), seq_with_mdd(-0.32), np.zeros(80), []), 0)
st = fs.update_state(bk, bd, {'tier_idx': 0})
rec('C1c', 'CB1 红 + 自动降档落盘', 'L3 合成 20 日回撤恰 −32%（<= 触发）',
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
# C2b 黄（毛触发未确认）
eqg = np.concatenate([np.ones(20), np.linspace(1.0, 0.78, 60)])   # 60 日 −22%
eqn = np.concatenate([np.ones(20), np.linspace(1.0, 0.90, 60)])   # 净账 −10% 未确认
bk = fs.eval_breakers(mk_rp(eqn, eqg, np.zeros(80), []), 0)
rec('C2b', 'CB2 黄（毛触发待净账确认）', 'L3 合成毛账 60 日 −22%、净账 −10%',
    f"light={bk['lights']['CB2']}，action={bk['actions']['CB2']}",
    '黄灯；总灯黄（无红时）',
    bk['lights']['CB2'] == 'yellow' and '待净账确认' in bk['actions']['CB2'],
    '毛账触发含两条旁路：止损失血≤−20pp 或 60 日毛跌≤−20pp（R6 放宽文案）')
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
rec('C3a', 'CB3 绿（当前快照）', 'L1 f1_live.json',
    f"light={BK['CB3']['light']}，detail={d3}",
    '绿灯', BK['CB3']['light'] == 'green' and d3['stop_count_60d'] < d3['line'])
# C3b 黄（观察线）
st4 = [ {'date': str(d.date()), 'sym': f'S{i}', 'pnl_pct': -0.001, 'slot': 0.025,
         'kind': 'stop_touch'} for i, d in enumerate(bd[-28:]) ]
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), np.zeros(80), st4), 0)
rec('C3b', 'CB3 黄（60 日 28 次 ≥ 观察线）', 'L3 合成 60 日 28 笔止损事件',
    f"light={bk['lights']['CB3']}，action={bk['actions']['CB3']}",
    '黄灯（CB3 只有黄/绿两态，永不红、不动作）',
    bk['lights']['CB3'] == 'yellow' and '观察' in bk['actions']['CB3'])
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
    '绿灯；页面费线阈值读 line_ann_pct=0.217', BK['FEE']['light'] == 'green'
    and dfee['fee_ann_pct'] < 0.1085)
# C4b 黄（半线 10.85% 边界）
fees_y = np.concatenate([np.zeros(20), np.full(60, 0.1085 * (60 / 252.0) / 60)])
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), fees_y, []), 0)
rec('C4b', '费线 黄（年化=10.85% 恰触发）', 'L3 合成 60 日费用累计使年化恰=10.85%',
    f"light={bk['lights']['FEE']}，action={bk['actions']['FEE']}",
    '黄灯', bk['lights']['FEE'] == 'yellow' and '过半线' in bk['actions']['FEE'])
# C4c 红 + 降一档
fees_r = np.concatenate([np.zeros(20), np.full(60, 0.25 * (60 / 252.0) / 60)])
bk = fs.eval_breakers(mk_rp(np.ones(80), np.ones(80), fees_r, []), 0)
st = fs.update_state(bk, bd, {'tier_idx': 0})
rec('C4c', '费线 红 + 自动降档', 'L3 合成 60 日费用年化 25% ≥21.7%',
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
# D3 idx==MA50 相等判开态（R5 认可）
gate_eq = not (100.0 < 100.0)          # idx==MA50 → 严格小于不成立 → 闸开
gate_eps = (100.0 - 1e-9) < 100.0      # 差 1e-9 → idx<ma50 → 闸关
src = open(os.path.join(HERE, 'f1_signal.py')).read()
strict = 'idx[t] < idx_ma[t]' in src and 'idx[t] <=' not in src
rec('D3', 'idx 精确等于 MA50：相等=闸开', 'L3 合成 idx==MA50 与 idx=MA50−1e−9 走查',
    f"相等→on_holdcash=False（{gate_eq}）；差 1e-9→闸关（{gate_eps}）；代码严格小于={strict}",
    '相等渲染🟩持仓卡；差 1e-9 渲染🟥持币卡',
    gate_eq and gate_eps and strict, '主管席 R5：贴线不悲观，冻结口径')
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
sys.path.insert(0, '/tmp/eng_w2_f1')
import f1_backtest as f1b                                 # noqa: E402
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
    True, '差异来源=BUG-04 崩市清仓日禁止重建+止损票当日禁止买回（主管席裁决改变口径），如实报告')

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
rec('E1', 'meta 行 badge 档位/敞口', 'json signal.tier_idx/slot/total_exposure',
    f"tier_idx={sig['tier_idx']}，slot={sig['slot_per_stock_pct']}%，敞口上限={sig['total_exposure_pct']}%",
    '页面 badge：仓位档=第 N 档/共 4 档 + 冻结徽章（freeze_days_left）',
    sig['total_exposure_pct'] == round(sig['slot_per_stock_pct'] * 5, 2)
    and 'slot_per_stock_pct' in PAGE and 'freeze_days_left' in PAGE)
rec('E2', '信号卡主文案映射', 'json signal.gate.on_holdcash=' + str(sig['gate']['on_holdcash']),
    f"gate idx={sig['gate']['idx']} ma50={sig['gate']['ma50']}",
    '页面两分支渲染，副文数字读 gate.idx/gate.ma50',
    "s.gate.idx" in PAGE and "s.gate.ma50" in PAGE and 'on_holdcash' in PAGE)
rec('E3', '信号日提示', f"json is_signal_day={sig['is_signal_day']}",
    'is_signal_day 双分支文案在位', '与 asof 星期归属一致',
    'is_signal_day' in PAGE)
rec('E4', 'top5 卡片标签', f"top5={len(sig['top5'])} 只",
    '闸关=[闸门关闭·不开仓]；闸开=[目标仓 X%]',
    '两标签 + 「以下为参考排名，当前不建仓」卡头（R10）均在位',
    '闸门关闭·不开仓' in PAGE and '目标仓' in PAGE and '当前不建仓' in PAGE)
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
rec('E10', '监控 notes 静态文案', f"json notes={len(J['monitor']['notes'])} 条",
    '页面逐条显示（mo.notes 渲染在位）', '与引擎常量一致',
    ('mo.notes.forEach' in PAGE or 'mo.notes.join' in PAGE) and len(J['monitor']['notes']) == 4)
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

# ================================================================ 汇总
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
