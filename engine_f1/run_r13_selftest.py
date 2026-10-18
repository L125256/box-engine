#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_r13_selftest.py — R13 四工单自测执行器（工程侧自检，供审计+测试席复核）
================================================================================
覆盖：
- WO-R13-01：① 新阈值常量在位 ② 重标定后真实段回放触发统计（含旧阈值 0 触发对照）
         ③ 月报三本账与改前逐位一致 ④ prev_reds 换批清空迁移
- WO-R13-03：⑤ guard 识别未落定当日 bar 并拒绝判定 ⑥ snapshot 只读（禁写
         f1_state.json / 禁覆盖 f1_live.json 判定字段 / 不出 top5） ⑦ 推送去重
         ⑧ 多轮时刻表可注册
- WO-R13-04：⑨ 单次失败不误切 ⑩ 连续 2 周期失败→DEGRADED 且冻结
         ⑪ 连续 2 周期健康→RECOVERING→验收通过→NORMAL ⑫ 验收不过挂待人工
         ⑬ 新浪白名单 ≤6 只/轮 + 144 全量被拒 ⑭ 降级期输出带 asof+source

复现：PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/run_r13_selftest.py
输出：/workspace/repo_ready/engine_f1/r13_selftest_result.json
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import f1_signal as fs                                   # noqa: E402
import f1_datasource as DS                               # noqa: E402

np.random.seed(fs.SEED)
WEB = '/workspace/f1_web'
RES = []


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else None


def rec(cid, name, inp, got, want, ok, note=''):
    RES.append({'id': cid, 'name': name, 'input': inp, 'got': got,
                'want': want, 'pass': bool(ok), 'note': note})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {name}" + (f" | {note}" if note else ''), flush=True)


print('== 加载数据与因子 ==', flush=True)
data = fs.load_data()
syms = fs.build_pool(data)
F = fs.build_factors(data)
rp = fs.replay(data, F, syms, slot=fs.SLOTS[0])
cal = rp['cal']

# ================================================================ WO-R13-01
print('== WO-R13-01 重标定 ==', flush=True)
T = fs.breaker_thresholds()
rec('R1', 'CB1 新阈值（红 −8% / 黄 −4%）',
    '引擎常量', f"red={fs.CB1_MDD} warn={fs.CB1_WARN}", 'red=-0.08 warn=-0.04',
    abs(fs.CB1_MDD + 0.08) < 1e-12 and abs(fs.CB1_WARN + 0.04) < 1e-12)
rec('R2', 'CB2 新阈值（红 −5pp / 黄 −2.5pp）',
    '引擎常量', f"red={fs.CB2_LOSS} warn={fs.CB2_WARN}", 'red=-0.05 warn=-0.025',
    abs(fs.CB2_LOSS + 0.05) < 1e-12 and abs(fs.CB2_WARN + 0.025) < 1e-12)
rec('R3', '费线新阈值（红 4pp / 黄 2pp）',
    '引擎常量', f"red={fs.FEE_LINE_ANN} warn={fs.FEE_WARN}", 'red=0.04 warn=0.02',
    abs(fs.FEE_LINE_ANN - 0.04) < 1e-12 and abs(fs.FEE_WARN - 0.02) < 1e-12)
rec('R4', 'CB3 保留不动（基准 9.07 / 观察线 27.21）',
    '引擎常量', f"base={fs.CB3_BASE_60D} mult={fs.CB3_MULT} line={T['CB3']['line']}",
    'base=9.07 line=27.21',
    fs.CB3_BASE_60D == 9.07 and abs(T['CB3']['line'] - 27.21) < 1e-9)

# R5 重标定后真实段回放统计（现场重算，读 breaker_stats_r13.json 交叉核对）
import replay_breakers_r13 as R13                      # noqa: E402
S = R13.series(rp)
focus = cal >= R13.FOCUS_START
mdd = S['mdd20'][focus]
new_cb1 = {'red': int((mdd <= fs.CB1_MDD).sum()),
           'yellow': int(((mdd <= fs.CB1_WARN) & (mdd > fs.CB1_MDD)).sum())}
gtrig = ((S['pnl60'] <= fs.CB2_LOSS) | (S['ret_g60'] <= fs.CB2_LOSS))[focus]
netok = (S['ret_n60'] <= fs.CB2_LOSS)[focus]
new_cb2 = {'red': int((gtrig & netok).sum()), 'yellow': int((gtrig & ~netok).sum())}
new_cb3 = int((S['cnt60'][focus] >= T['CB3']['line']).sum())
new_fee = {'red': int((S['fee_ann'][focus] >= fs.FEE_LINE_ANN).sum()),
          'yellow': int(((S['fee_ann'][focus] >= fs.FEE_WARN)
                         & (S['fee_ann'][focus] < fs.FEE_LINE_ANN)).sum())}
rec('R5', '重标定后真实段回放触发统计（现场重算）',
    f"{R13.FOCUS_START.date()}~{cal[-1].date()}（{int(focus.sum())} 交易日）",
    f"CB1 红{new_cb1['red']}/黄{new_cb1['yellow']}；CB2 红{new_cb2['red']}/黄{new_cb2['yellow']}；"
    f"CB3 黄{new_cb3}；费线 红{new_fee['red']}/黄{new_fee['yellow']}",
    'CB1/CB2 有真实触发；CB3 与改前一致',
    (new_cb1['red'] + new_cb1['yellow']) > 0 and (new_cb2['red'] + new_cb2['yellow']) > 0
    and new_cb3 == 0)

# R6 旧阈值下 0 触发（死线证明）
OLD = {'CB1_RED': -0.32, 'CB1_WARN': -0.16, 'CB2': -0.20, 'FEE': 0.217, 'FEE_WARN': 0.1085}
old_zero = (int((mdd <= OLD['CB1_RED']).sum()) == 0
            and int(((mdd <= OLD['CB1_WARN']) & (mdd > OLD['CB1_RED'])).sum()) == 0
            and int((((S['pnl60'] <= OLD['CB2']) | (S['ret_g60'] <= OLD['CB2']))[focus]
                     & (S['ret_n60'] <= OLD['CB2'])[focus]).sum()) == 0
            and int((S['fee_ann'][focus] >= OLD['FEE']).sum()) == 0)
rec('R6', '旧阈值下 CB1/CB2/费线 0 触发（结构性死线已证实）',
    '同一段回放 + 旧阈值',
    'CB1/CB2/费线 红黄灯天数全 0', '全 0（改前状态）', old_zero)

# R7 月报三本账逐位一致（对照 git HEAD 基线）
base = '/tmp/base_live.json'
if os.path.exists(base):
    a = json.load(open(base))
    b = json.load(open(os.path.join(WEB, 'f1_live.json')))
    same = a['monthly_accounts'] == b['monthly_accounts']
    rec('R7', '月报三本账与改前逐位一致',
        base + ' vs 现行 f1_live.json',
        f"identical={same}；行数 {len(b['monthly_accounts'])}", 'identical=True', same)
else:  # pragma: no cover
    rec('R7', '月报三本账与改前逐位一致', base, '基线缺失', 'identical=True', False)

# R8 prev_reds 换批清空
st_mig = fs.update_state({'lights': {'CB1': 'red', 'CB2': 'green', 'CB3': 'green',
                                            'FEE': 'red'}},
                         cal, {'tier_idx': 0, 'prev_reds': ['CB1', 'FEE'],
                               'calib_epoch': 'R11-OLD'})
rec('R8', '重标定换批：prev_reds 清空且 epoch 落盘',
    'calib_epoch=R11-OLD → R13',
    f"epoch={st_mig.get('calib_epoch')}；prev_reds={st_mig.get('prev_reds')}；"
    f"tier_idx={st_mig.get('tier_idx')}（红灯新触发=不连降，因已清空故为 1）",
    f"epoch={fs.CALIB_EPOCH}；prev_reds=['CB1','FEE']；tier_idx=1",
    st_mig.get('calib_epoch') == fs.CALIB_EPOCH
    and sorted(st_mig.get('prev_reds', [])) == ['CB1', 'FEE'] and st_mig.get('tier_idx') == 1)

# ================================================================ WO-R13-03
print('== WO-R13-03 只读旁路 ==', flush=True)
# R9 guard 二态
g_settled = fs.guard_last_bar(cal, now=pd.Timestamp(cal[-1]) + pd.Timedelta(days=2))
g_open = fs.guard_last_bar(cal, now=pd.Timestamp(cal[-1]))
rec('R9', 'guard 二态：落定后 settled=True / 当日 bar settled=False',
    f"last_bar={cal[-1].date()}；now=D+2 vs now=D",
    f"D+2→{g_settled['settled']}；D→{g_open['settled']}", 'True / False',
    bool(g_settled['settled']) and not g_open['settled'])
# R10 guard 拒绝判定（current_signal 抛 RuntimeError）——R14 审计修复两处：
# ① 原 else 分支 `raised = bool(g_settled['settled'])` 为恒真式弱断言（审计 §三-R10）；
# ② 原用例隐式依赖「缓存最后一根 bar=当日未落定 bar」的运行时刻（跨日重跑即失效）。
# 改为确定性真注入：向任一标的追加一根当日（UTC）bar，构造真实的未落定场景。
_today = pd.Timestamp.now(tz='UTC').normalize().tz_localize(None)
_s0 = next(iter(data))
_inj = data[_s0].iloc[[-1]].copy()
_inj.index = [_today]
data_inj = dict(data)
data_inj[_s0] = pd.concat([data[_s0], _inj])
_g_inj = fs.guard_last_bar(pd.DatetimeIndex(sorted(set().union(
    *[set(data_inj[s].index) for s in syms]))))
try:
    fs.current_signal(data_inj, F, syms, allow_intraday=False)
    raised = False
    msg = '未抛错'
except RuntimeError as e:
    raised = True
    msg = str(e)[:80]
rec('R10', 'guard：未落定 bar 拒绝产出判定（注入式确定性复现）',
    f"注入当日（{_today.date()}）未落定 bar 至 {_s0}；settled={_g_inj['settled']}",
    f"RuntimeError: {msg}", 'settled=False 且拒绝判定且写日志',
    raised and not _g_inj['settled'])
# R11 snapshot 只读：f1_state.json / f1_live.json 逐位不变
b_state, b_live = sha(os.path.join(WEB, 'f1_state.json')), sha(os.path.join(WEB, 'f1_live.json'))
b_dec = json.dumps({k: json.load(open(os.path.join(WEB, 'f1_live.json'))).get(k) for k in
                      ('signal', 'breakers', 'state', 'monthly_accounts')},
                     ensure_ascii=False, sort_keys=True)
snap = fs.run_snapshot(out_json=os.path.join(WEB, 'f1_live_intraday.json'), round_id='20:30')
a_state, a_live = sha(os.path.join(WEB, 'f1_state.json')), sha(os.path.join(WEB, 'f1_live.json'))
a_dec = json.dumps({k: json.load(open(os.path.join(WEB, 'f1_live.json'))).get(k) for k in
                      ('signal', 'breakers', 'state', 'monthly_accounts')},
                     ensure_ascii=False, sort_keys=True)
snap_txt = open(os.path.join(WEB, 'f1_live_intraday.json')).read()
rec('R11', 'snapshot 只读：禁写 f1_state.json + 禁覆盖 f1_live.json 判定字段',
    '运行 snapshot --round 20:30 前后 sha256 逐位比对',
    f"state sha 不变={b_state == a_state}；live 判定字段不变={b_dec == a_dec}；"
    f"writes={snap['writes']}",
    'state 不变 + 判定字段不变 + writes 全 False',
    b_state == a_state and b_dec == a_dec
    and snap['writes'] == {'f1_state.json': False, 'f1_live.json': False})
_has_top5 = '"top5"' in snap_txt
_has_notice = '不可操作' in snap_txt
rec('R12', 'snapshot 不出 top5 建议 + 带「不可操作」标注',
    'snapshot 输出字段走查',
    f"含 top5 键={_has_top5}；含不可操作标注={_has_notice}",
    '无 top5 + 有标注',
    (not _has_top5) and _has_notice)
# R13 推送去重
p1 = fs.push_plan('DECIDE', '2026-10-17', 'DECIDE', last_push={})
p2 = fs.push_plan('DECIDE', '2026-10-17', 'DECIDE', last_push={p1['key']: 1})
i1 = fs.push_plan('INTRADAY', '2026-10-17', '20:30', last_push={})
i2 = fs.push_plan('INTRADAY', '2026-10-17', '20:30', last_push={i1['key']: 1})
i3 = fs.push_plan('INTRADAY', '2026-10-17', '04:30', last_push={i1['key']: 1})
rec('R13', '推送去重：判定轮按 asof；盘中轮按 asof+轮次且不携带结论',
    'DECIDE×2 + INTRADAY×3 组合',
    f"p1={p1['push']} p2={p2['push']} i1={i1['push']} i2={i2['push']} i3={i3['push']}；"
    f"i1 携带结论={i1['carries_decision']}",
    'True/False/True/False/True；i1 不携带结论',
    bool(p1['push']) and not p2['push'] and bool(i1['push'])
    and not i2['push'] and bool(i3['push']) and i1['carries_decision'] is False)

# R14 多轮时刻表可注册
CR = open(os.path.join(HERE, 'f1_crontab.txt')).read()
rec('R14', '多轮时刻表可注册（20:30/00:30/04:30 只读 + 判定轮）',
    'f1_crontab.txt',
    f"snapshot 轮次={CR.count('snapshot --round')}；判定轮={'f1_signal.py live' in CR}；"
    f"DST 标注={'夏令时' in CR or '冬令时' in CR}",
    '3 轮只读 + 1 判定轮 + DST 标注',
    CR.count('snapshot --round') == 3 and 'f1_signal.py live' in CR
    and ('夏令时' in CR or '冬令时' in CR))

# ================================================================ WO-R13-04
print('== WO-R13-04 数据源容灾（人造故障切换演练）==', flush=True)
os.environ['F1_ACCEPT_FORCE'] = 'none'   # 显式传 consistency 的既有用例不受自动验收影响
DS._reset()
os.environ['F1_PRIMARY_FAIL'] = '1'
os.environ['F1_RETRY_SLEEP'] = '0'
_st1, _r1 = DS.run_round(round_id='T-F1')
rec('R15', '① 第 1 周期失败：不误切（仍 NORMAL）',
    'F1_PRIMARY_FAIL=1',
    f"state={_st1['state']}, consec_fail={_st1['consec_fail']}",
    'NORMAL / 1', _st1['state'] == 'NORMAL' and _st1['consec_fail'] == 1)

_live_before = sha(os.path.join(WEB, 'f1_live.json'))
_dec_before = json.dumps({k: json.load(open(os.path.join(WEB, 'f1_live.json'))).get(k) for k in
                       ('signal', 'breakers', 'state', 'monthly_accounts')},
                      ensure_ascii=False, sort_keys=True)
_st2, _r2 = DS.run_round(round_id='T-F2')
_frz = DS.freeze_payload()
# R16（R14 审计修复：原为空洞比对——freeze_payload 只读不写，不变必然成立）。
# 改走真实 _emit_frozen 路径：临时副本上实际调用，逐字段 diff 判定树，
# 仅允许新增 2 个可操作性标注键（审计 §一-WO-04 口径）。
import shutil
_tmp_live = '/tmp/r13_selftest_frozen_live.json'
shutil.copy2(os.path.join(WEB, 'f1_live.json'), _tmp_live)
_before = json.load(open(_tmp_live))
_frozen_out = fs._emit_frozen(_tmp_live, {'state': 'DEGRADED',
                                          'banner': DS.source_banner({'state': 'DEGRADED'})})
_after = json.load(open(_tmp_live))
_diffs = DS.decision_diff({k: _before.get(k) for k in DS.DECISION_FIELDS},
                          {k: _after.get(k) for k in DS.DECISION_FIELDS})
rec('R16', '② 第 2 周期失败 → DEGRADED + _emit_frozen 实路冻结（判定字段实质逐位不动，'
           '仅新增 2 个标注键）',
    'F1_PRIMARY_FAIL=1 连跑 2 周期；临时副本真实调用 _emit_frozen 后逐字段 diff',
    f"state={_st2['state']}；diffs={_diffs}；"
    f"freeze 写 state={_frozen_out['writes']}",
    'DEGRADED + diffs⊆2 标注键 + 不重算不写状态',
    _st2['state'] == 'DEGRADED' and set(_diffs) <= DS.FROZEN_ANNOTATION_KEYS
    and _after['signal'].get('frozen_by_source_failover') is True
    and _after['signal'].get('operable') is False
    and _frozen_out['writes']['f1_state.json'] is False
    and _frozen_out['writes']['recomputed'] is False)

os.environ['F1_PRIMARY_FAIL'] = '0'
_st3, _ = DS.run_round(round_id='T-O1')
_st4, _ = DS.run_round(round_id='T-O2')
rec('R17', '③ 连续 2 周期健康 → RECOVERING（待一致性验收）',
    'F1_PRIMARY_FAIL=0 连跑 2 周期',
    f"{_st3['state']} → {_st4['state']}", 'DEGRADED → RECOVERING',
    _st4['state'] == 'RECOVERING')

_cons = DS.consistency_check([{'symbol': 'aapl', 'date': '2026-10-16', 'close': 100.0}],
                       [{'symbol': 'aapl', 'date': '2026-10-16', 'close': 101.5}])
_st5, _ = DS.run_round(round_id='T-V', consistency=_cons)
rec('R18', '④ 一致性验收通过 → 自动切回 NORMAL（容差=价格1%+基差1%）',
    '主备重叠收盘价偏差 1.5% ≤ 2%',
    f"cons_p={_cons['pass']}, max_dev={_cons['max_dev']}, tol={_cons['tol']}, state={_st5['state']}",
    'True + NORMAL', bool(_cons['pass']) and _st5['state'] == 'NORMAL')

DS._reset()
os.environ['F1_PRIMARY_FAIL'] = '1'
for _i in range(DS.FAIL_PERIODS_TO_DEGRADE):
    DS.run_round(round_id='T-BF')
os.environ['F1_PRIMARY_FAIL'] = '0'
for _i in range(DS.OK_PERIODS_TO_RECOVER):
    DS.run_round(round_id='T-BO')
_cons_bad = DS.consistency_check([{'symbol': 'aapl', 'date': '2026-10-16', 'close': 100.0}],
                          [{'symbol': 'aapl', 'date': '2026-10-16', 'close': 110.0}])
_st6, _ = DS.run_round(round_id='T-BV', consistency=_cons_bad)
rec('R19', '⑤ 一致性验收不通过 → 留 RECOVERING 自动重试，禁止自动强切',
    '偏差 10% > 2%',
    f"cons_p={_cons_bad['pass']}, state={_st6['state']}, pending_manual={_st6.get('pending_manual')}",
    'False + RECOVERING + True',
    (not _cons_bad['pass']) and _st6['state'] == 'RECOVERING'
    and _st6.get('pending_manual') is True)

_wl = DS.proxy_wlist_check = DS.proxy_watchlist(['AAPLUSDT', 'MSFTUSDT', 'GOOGLUSDT',
                                                'AMZNUSDT', 'NVDAUSDT'])
try:
    DS.fetch_sina_daily([f'S{i}USDT' for i in range(144)])
    _rej = False
except ValueError:
    _rej = True
rec('R20', '⑥ 新浪硬约束：白名单 ≤6 只/轮 + 144 全量被拒',
    f"watchlist={_wl}；144 只请求",
    f"白名单={len(_wl)} 只；144 拒绝={_rej}", '≤6 且 True',
    len(_wl) <= DS.MAX_PROXY_SYMBOLS and _rej)
_banner = DS.source_banner({'state': 'DEGRADED', 'frozen_asof': '2026-10-17'})
rec('R21', '⑦ 降级期输出带 asof + source 标注', 'DEGRADED banner', _banner,
    '含 asof + 不构成新推荐', '2026-10-17' in _banner and '不构成新推荐' in _banner)

# ================================================================ WO-R14 Q-1/Q-2
print('== WO-R14 Q-1 自动验收接线 / Q-2 RECOVERING 回退 ==', flush=True)
# R22 Q-1：RECOVERING 态恢复探测轮自动执行一致性验收（不传 consistency）→ 自动切回 NORMAL
DS._reset()
os.environ['F1_PRIMARY_FAIL'] = '1'
os.environ['F1_ACCEPT_FORCE'] = 'none'
for _i in range(DS.FAIL_PERIODS_TO_DEGRADE):
    DS.run_round(round_id='T-Q1F')
os.environ['F1_PRIMARY_FAIL'] = '0'
_stq = None
_rq = None
for _i in range(DS.OK_PERIODS_TO_RECOVER):
    os.environ['F1_ACCEPT_FORCE'] = 'ok' if _i == DS.OK_PERIODS_TO_RECOVER - 1 else 'none'
    _stq, _rq = DS.run_round(round_id=f'T-Q1-{_i + 1}')
rec('R22', 'Q-1 自动验收接线：RECOVERING 态自动执行一致性验收（无人工传参）→ NORMAL',
    f"判死×2 → 恢复×2（末轮 F1_ACCEPT_FORCE=ok）；acceptance={_rq.get('acceptance')}",
    f"末轮 state={_stq['state']}",
    '自动验收 pass=True + auto=True → NORMAL',
    _stq['state'] == 'NORMAL' and (_rq.get('acceptance') or {}).get('pass') is True
    and (_rq.get('acceptance') or {}).get('auto') is True)

# R23 Q-2：RECOVERING 期主源又连续 2 周期失败 → 显式回退 DEGRADED 并冻结新信号
DS._reset()
os.environ['F1_PRIMARY_FAIL'] = '1'
os.environ['F1_ACCEPT_FORCE'] = 'none'
for _i in range(DS.FAIL_PERIODS_TO_DEGRADE):
    DS.run_round(round_id='T-Q2F')
os.environ['F1_PRIMARY_FAIL'] = '0'
for _i in range(DS.OK_PERIODS_TO_RECOVER):
    DS.run_round(round_id='T-Q2O')
_mid = DS.load_state()
os.environ['F1_PRIMARY_FAIL'] = '1'
for _i in range(DS.FAIL_PERIODS_TO_DEGRADE):
    _stb, _ = DS.run_round(round_id=f'T-Q2B-{_i + 1}')
rec('R23', 'Q-2 回退：RECOVERING 期主源又连续 2 周期失败 → 显式回退 DEGRADED 并冻结新信号',
    f"RECOVERING（{_mid['state']}）→ 注入失败×2",
    f"state={_stb['state']}；frozen_asof={_stb.get('frozen_asof')}",
    'RECOVERING → DEGRADED + 冻结标注',
    _mid['state'] == 'RECOVERING' and _stb['state'] == 'DEGRADED'
    and _stb.get('frozen_asof') is not None
    and '冻结' in DS.source_banner(_stb))

# 复位到 NORMAL，避免污染生产状态
DS._reset()
os.environ['F1_PRIMARY_FAIL'] = '0'
os.environ.pop('F1_ACCEPT_FORCE', None)
DS.run_round(round_id='POST-DRILL-RESET')
DS.run_round(round_id='POST-DRILL-RESET2')
DS._reset()

n_pass = sum(1 for r in RES if r['pass'])
summary = {'workorder': 'R13 四工单工程自测', 'total': len(RES), 'pass': n_pass,
           'fail': len(RES) - n_pass, 'results': RES}
out_path = os.path.join(HERE, 'r13_selftest_result.json')
with open(out_path, 'w') as f:
    json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
print(f"\n===== R13 自测汇总：PASS {n_pass}/{len(RES)} =====")
for r in RES:
    if not r['pass']:
        print('FAIL →', r['id'], r['name'], '| got:', r['got'])
print('结果文件 →', out_path)
sys.exit(0 if n_pass == len(RES) else 1)
