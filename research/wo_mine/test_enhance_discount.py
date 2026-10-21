#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_enhance_discount.py — 分域增强插件层·测试席五组测试（PLAN_FINAL_20261021 新制版）
================================================================================
① 新制档位单测（构造影子读数逐档断言：S5 满额 FULL/S1-S3 POOL_CAP 50/劣化线归零
   OFFLINE/域未激活 FROZEN/S4 灰态 + 无爬档断言）
② 旁路异常不阻断断言（enhance_discount 对残缺输入不抛出 + subprocess 挂接 check=False）
③ 页面本地渲染无 JS 报错 + 新口径逐字 + 无字段兜底（render_harness.cjs）
④ 双手册章节渲染断言（新制白话）
⑤ 引擎回归（f1_signal.py diff 删除行=0 断言[meta 展示行除外] + sha 闸门双登记同步 +
   资金费降级回归承继）
运行：python3 research/wo_mine/test_enhance_discount.py
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f' —— {detail}' if detail else ''))


sys.path.insert(0, HERE)
import enhance_discount as ED   # noqa: E402


def make_tree(cells, fd_state=None, fd_days=None, live=None, regs=None, out_prev=None):
    d = tempfile.mkdtemp(prefix='enh_test_')
    os.makedirs(os.path.join(d, 'f1'))
    if cells is not None:
        json.dump({'cells': cells, 'round_asof': '2026-10-19'},
                  open(os.path.join(d, 'f1', 'shadow_state.json'), 'w'))
    if fd_state is not None:
        json.dump(fd_state, open(os.path.join(d, 'f1', 'fd_revive_state.json'), 'w'))
    if fd_days is not None:
        with open(os.path.join(d, 'f1', 'fd_revive_days.jsonl'), 'w') as f:
            for r in fd_days:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    if live is not None:
        json.dump(live, open(os.path.join(d, 'f1', 'f1_live.json'), 'w'))
    for cid, rows in (regs or {}).items():
        with open(os.path.join(d, 'f1', f'shadow_reg_{cid}.jsonl'), 'w') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    if out_prev is not None:
        json.dump(out_prev, open(os.path.join(d, 'f1', 'enhancement_state.json'), 'w'))
    return d


def run_in(tree):
    old = ED.ROOT
    ED.ROOT = tree
    ED.STATEDIR = os.path.join(tree, 'f1')
    ED.SHADOW_STATE_F = os.path.join(ED.STATEDIR, 'shadow_state.json')
    ED.FD_STATE_F = os.path.join(ED.STATEDIR, 'fd_revive_state.json')
    ED.FD_DAYS_F = os.path.join(ED.STATEDIR, 'fd_revive_days.jsonl')
    ED.ROUND_F = os.path.join(ED.STATEDIR, 'f1_live.json')
    ED.OUT_F = os.path.join(ED.STATEDIR, 'enhancement_state.json')
    try:
        return ED.run(auto=True)
    finally:
        ED.ROOT, ED.STATEDIR = old, os.path.join(old, 'f1')
        ED.SHADOW_STATE_F = os.path.join(ED.STATEDIR, 'shadow_state.json')
        ED.FD_STATE_F = os.path.join(ED.STATEDIR, 'fd_revive_state.json')
        ED.FD_DAYS_F = os.path.join(ED.STATEDIR, 'fd_revive_days.jsonl')
        ED.ROUND_F = os.path.join(ED.STATEDIR, 'f1_live.json')
        ED.OUT_F = os.path.join(ED.STATEDIR, 'enhancement_state.json')


def shadow_cell(n=0, ic_mean=None, ic_t=None, hit_rate=None, sealed=False, verdict=None):
    return {'status': 'ACCUMULATING', 'sealed': sealed, 'verdict': verdict,
            'n_registered': n, 'n_matured': n,
            'accumulation': {'n_days': n, 'ic_mean': ic_mean, 'ic_t': ic_t,
                             'hit_rate': hit_rate, 'target': 20, 'early_death_line': 10}}


LIVE_OK = {'signal': {'asof': '2026-10-19', 'gate': {'on_holdcash': False}},
           'breakers': {'overall': {'light': 'green'}}}
REG_OK = {'S1': [{'domain_label': '弱躁', 'cell_domain': '弱躁'}],
          'S2': [{'domain_label': '弱躁', 'cell_domain': '弱躁'}],
          'S3': [{'domain_label': '弱躁', 'cell_domain': '牛躁'}]}
S4_SUSP = {'gate_state': 'SUSPENDED', 'sealed': False,
           'replenish': {'fw_old131_weak_days': 0}}

# ---------------- ① 新制档位单测（S5 满额/单池 50/劣化线归零/域未激活 FROZEN） ----------------
print('==== ① 新制档位单测 ====')
# S5 满额：sealed PASS → FULL 100%（0.5% 基线×100%，即刻无等待）
t = make_tree({'S1': shadow_cell(n=20, ic_mean=0.08, ic_t=3.0, hit_rate=0.7, sealed=True, verdict='PASS'),
               'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': S4_SUSP, 'S5': shadow_cell(n=20)},
              fd_state={'n_matured': 20, 'sealed': True, 'verdict': 'PASS', 'delta_mean': 0.2},
              fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
c5 = o['cells']['S5']
check('①S5 满额：sealed PASS → FULL 100%（0.5% 基线×100%，即刻 T2→FULL）',
      c5['tier'] == 'FULL' and c5['coef'] == 100 and c5['deployed'] is True,
      f"{c5['tier']}/{c5['coef']}")
check('①S5 执照复审到期日=2027-04-21（满额部署日 2026-10-21+6 个月）',
      c5.get('review_due') == '2027-04-21', str(c5.get('review_due')))
c1 = o['cells']['S1']
check('①S1-S3 单池满额：sealed PASS → POOL_CAP 50%（证据折扣保留）',
      c1['tier'] == 'POOL_CAP' and c1['coef'] == 50 and c1['deployed'] is True)
check('①S2 未封印 → FROZEN 0%（重重检测未收口不部署，无 T0/T1 爬档）',
      o['cells']['S2']['tier'] == 'FROZEN' and o['cells']['S2']['coef'] == 0)
check('①n 计数保留（执照复审数据源）', c1['n_days'] == 20 and c5['n_days'] == 20)
shutil.rmtree(t)

# 实盘劣化线归零：n≥10 ∧ t≤−2 ∧ IC<0 → OFFLINE 0%（未封印也当日归零）
t = make_tree({'S1': shadow_cell(n=10, ic_mean=-0.05, ic_t=-2.5, hit_rate=0.3),
               'S2': shadow_cell(n=20, ic_mean=-0.02, ic_t=-1.0, hit_rate=0.4, sealed=True, verdict='FAIL'),
               'S3': shadow_cell(), 'S4': S4_SUSP, 'S5': shadow_cell(n=20)},
              fd_state={'n_matured': 20, 'sealed': False, 'delta_mean': -0.1},
              fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('①劣化线 n≥10∧t≤−2∧IC<0 → OFFLINE 当日归零（早死线承继改造）',
      o['cells']['S1']['tier'] == 'OFFLINE' and o['cells']['S1']['coef'] == 0)
check('①sealed FAIL → OFFLINE', o['cells']['S2']['tier'] == 'OFFLINE')
check('①S5 n≥20 Δ≤0 → OFFLINE（J5 判死）', o['cells']['S5']['tier'] == 'OFFLINE')
shutil.rmtree(t)

# 边界：n≥10 但 t>−2 → 不归零（FROZEN 非 OFFLINE）；NOT_PASS → FROZEN；域未激活 → FROZEN
check('①n≥10 但 t>−2 不触发劣化线（数字冻结逐字）',
      ED.tier_factor_cell(12, -0.01, -1.0, 0.4, False, None) == ('FROZEN', ED.TIERS['FROZEN'][0]) or
      ED.tier_factor_cell(12, -0.01, -1.0, 0.4, False, None)[0] == 'FROZEN')
check('①sealed NOT_PASS → FROZEN（三腿未全过，复审窗重读）',
      ED.tier_factor_cell(20, 0.08, 3.0, 0.5, True, 'NOT_PASS')[0] == 'FROZEN')
t = make_tree({'S1': shadow_cell(n=20, ic_mean=0.08, ic_t=3.0, hit_rate=0.7, sealed=True, verdict='PASS'),
               'S2': shadow_cell(), 'S3': shadow_cell(), 'S4': S4_SUSP, 'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 5, 'sealed': False},
              fd_days=[], live=LIVE_OK,
              regs={'S1': [{'domain_label': '牛躁', 'cell_domain': '弱躁'}],  # 域标签≠本格域
                    'S2': [{'domain_label': '弱躁', 'cell_domain': '弱躁'}],
                    'S3': [{'domain_label': '弱躁', 'cell_domain': '牛躁'}]})
o = run_in(t)
check('①域未激活=FROZEN（S1 sealed PASS 但域标签不符 → FROZEN 0% 仅展示）',
      o['cells']['S1']['tier'] == 'FROZEN' and o['cells']['S1']['coef'] == 0
      and o['cells']['S1']['deployed'] is False)
check('①S4 SUSPENDED 灰态 FROZEN 不部署（样本门非影子期，新制不解）',
      o['cells']['S4']['tier'] == 'FROZEN' and o['cells']['S4']['coef'] == 0
      and o['cells']['S4']['deployed'] is False)
shutil.rmtree(t)

# §2.5 单向让位联动 + §5-⑦ 安全侧默认
lk = ED.build_linkage({'signal': {'gate': {'on_holdcash': True}},
                       'breakers': {'overall': {'light': 'green'}}})
check('①§2.5-1 闸关 → 冻结开新仓', lk['enhanced_frozen'] is True)
lk = ED.build_linkage({'signal': {'gate': {'on_holdcash': False}},
                       'breakers': {'overall': {'light': 'red'}}})
check('①§2.5-2 红灯 → 整体冻结', lk['enhanced_frozen'] is True)
t = make_tree(None, live=LIVE_OK, out_prev={'inputs_ok': False, 'fail_streak': 4})
o = run_in(t)
check('①§5-⑦ 连续 5 轮输入失败 → 全降 FROZEN + 冻结（新制保守化承继）',
      o['safe_default'] is True and o['linkage']['enhanced_frozen'] is True
      and all(c['tier'] == 'FROZEN' for cid, c in o['cells'].items() if c['deployed']))
shutil.rmtree(t)

# 无爬档断言：旧 T0-T4 查表废除 + 输出 tier 域收敛
check('①旧 T0-T4 档位表废除，新表 tier ∈ {FULL,POOL_CAP,FROZEN,OFFLINE}',
      set(ED.TIERS) == {'FULL', 'POOL_CAP', 'FROZEN', 'OFFLINE'}
      and 'PLAN_FINAL_20261021' in ED.TIER_TABLE_VERSION)
check('①总敞口上限口径不变（0.5% 基线/2% 总帽分母承继）',
      ED.BASELINE_PCT == 0.5 and ED.TOTAL_CAP_PCT == 2.0)

# ---------------- ② 旁路异常不阻断断言 ----------------
print('==== ② 旁路异常不阻断 ====')
d = tempfile.mkdtemp(prefix='enh_test2_')
os.makedirs(os.path.join(d, 'f1'))   # 空输入目录：全部文件缺失
try:
    o = run_in(d)                    # 不抛出即不阻断
    check('②全输入缺失不抛异常且仍落盘', os.path.exists(os.path.join(d, 'f1', 'enhancement_state.json'))
          and o['inputs_ok'] is False and o['fail_streak'] == 1)
finally:
    shutil.rmtree(d)
src = open(os.path.join(ROOT, 'engine_f1', 'f1_signal.py')).read()
check('②挂接为 subprocess check=False（异常不阻断）',
      src.count("enhance_discount.py'") == 2 and 'check=False' in src
      and src.count("enhance_discount 挂接异常（不阻断）") == 1
      and src.count("enhance_discount 快照轮挂接异常（不阻断）") == 1)

# ---------------- ③ 页面本地渲染无 JS 报错 + 新口径逐字 + 无字段兜底 ----------------
print('==== ③ 页面渲染（render_harness）====')
# 构造新制口径合成 enhancement（覆盖 FULL/POOL_CAP/FROZEN/OFFLINE/S4 灰态五分支）
SYNTH_ENH = {
    'generated': '2026-10-21 09:30:00', 'asof': '2026-10-20',
    'deploy_rule': '重重检测四层全过=当日满额部署（无任何时间等待）',
    'cells': {
        'S1': {'tier': 'POOL_CAP', 'tier_name': '单池满额档', 'coef': 50, 'n_days': 20,
               'sealed': True, 'verdict': 'PASS', 'domain': '弱躁', 'name': 'S1 反转',
               'domain_active': True, 'deployed': True, 'review_due': '2027-04-21',
               'status': '单池满额档（重重检测四层全过）'},
        'S2': {'tier': 'FROZEN', 'tier_name': '冻结档', 'coef': 0, 'n_days': 8,
               'sealed': False, 'verdict': None, 'domain': '弱躁', 'name': 'S2 反转粗筛',
               'domain_active': False, 'deployed': False, 'review_due': None,
               'status': '冻结档（重重检测未收口）'},
        'S3': {'tier': 'OFFLINE', 'tier_name': '下线', 'coef': 0, 'n_days': 10,
               'sealed': False, 'verdict': None, 'domain': '牛躁', 'name': 'S3 突破回踩',
               'domain_active': True, 'deployed': False, 'review_due': None,
               'status': '下线（实盘劣化线触发）'},
        'S5': {'tier': 'FULL', 'tier_name': '满额档', 'coef': 100, 'n_days': 20,
               'sealed': True, 'verdict': 'PASS', 'domain': '全域', 'name': 'S5 fd 出场增强',
               'domain_active': True, 'deployed': True, 'review_due': '2027-04-21',
               'status': '满额档（重重检测四层全过）'},
        'S4': {'tier': 'FROZEN', 'tier_name': '冻结档', 'coef': 0, 'n_days': 56, 'n_need': 60,
               'sealed': False, 'verdict': None, 'domain': '弱稳', 'name': 'S4 高波停门',
               'domain_active': False, 'deployed': False,
               'status': 'SUSPENDED（补样未达 60 日样本门）'},
    },
    'linkage': {'f1_gate': 'open', 'f1_breaker_light': 'green', 'enhanced_frozen': False},
    'fee_note': '资金费=背景常数 0.03%/bar 仅事后披露，不参与判定',
}
_live = json.load(open(os.path.join(ROOT, 'f1', 'f1_live.json')))
_live.setdefault('meta', {})['enhancement'] = SYNTH_ENH
tmp = os.path.join(tempfile.mkdtemp(), 'synth.json')
json.dump(_live, open(tmp, 'w'), ensure_ascii=False)
rh = subprocess.run(['node', os.path.join(ROOT, 'f1', 'render_harness.cjs'),
                     os.path.join(ROOT, 'f1', 'index.html'), tmp],
                    capture_output=True, text=True, timeout=60)
check('③渲染执行零 JS 报错（stderr 无 Error）', rh.returncode == 0 and 'Error' not in rh.stderr,
      rh.stderr[:120])
out = rh.stdout[rh.stdout.index('RENDER_JSON_START') + 17:]
d = json.loads(out)
enh = d['enh']['innerHTML']
check('③S5 新口径逐字：满额运行·执照复审 2027-04-21 到期',
      '满额运行·执照复审 2027-04-21 到期' in enh)
check('③S1-S3 新口径逐字：单池满额 50%·双池解锁另议', '单池满额 50%·双池解锁另议' in enh)
check('③劣化线下线分支：当日归零+负事实展示+季度复判',
      '当日归零下线' in enh and '负事实展示' in enh and '季度机械复判' in enh)
check('③S4 灰态不变：样本门·未部署·不占用仓位', '样本门·未部署·不占用仓位' in enh)
check('③总免责声明新口径逐字（重重检测满额部署/劣化线自动降停/6 个月强制复审）',
      '按重重检测满额部署' in enh and '实盘劣化线自动降停' in enh and '6 个月强制复审' in enh)
check('③旧字样零残留（折扣/影子//20 爬档）',
      '折扣' not in enh and '影子' not in enh and '/20' not in enh)
# 无字段兜底
_no = json.load(open(os.path.join(ROOT, 'f1', 'f1_live.json')))
_no.get('meta', {}).pop('enhancement', None)   # 旧 JSON：仅缺 enhancement 字段
tmp2 = os.path.join(tempfile.mkdtemp(), 'noenh.json')
json.dump(_no, open(tmp2, 'w'), ensure_ascii=False)
rh2 = subprocess.run(['node', os.path.join(ROOT, 'f1', 'render_harness.cjs'),
                      os.path.join(ROOT, 'f1', 'index.html'), tmp2],
                     capture_output=True, text=True, timeout=60)
d2 = json.loads(rh2.stdout[rh2.stdout.index('RENDER_JSON_START') + 17:])
check('③旧 JSON 无 enhancement 字段 → 「增强层未上线」不报错',
      '增强层未上线' in d2['enh']['innerHTML'] and rh2.returncode == 0)

# ---------------- ④ 双手册章节渲染 ----------------
print('==== ④ 双手册章节 ====')
m1 = open(os.path.join(ROOT, 'f1', 'manual.html')).read()
m2 = open(os.path.join(ROOT, 'box', 'manual.html')).read()
check('④f1 手册分域增强章节新制白话（重重检测当日满额/劣化线/复审）',
      '<h2>8. 分域增强插件' in m1 and '当日满额部署' in m1
      and 'n≥10 且 t≤−2 且方向翻转' in m1 and '6 个月强制复审硬期限' in m1
      and '绝不能因此少买或不买 F1 榜单' in m1 and '任何冲突听 F1。' in m1)
check('④f1 手册旧字样零残留（影子/折扣/爬坡档位）',
      '影子' not in m1 and '折扣' not in m1 and '爬档' not in m1)
check('④f1 手册术语词典编号顺延 §8→§9', '<h2>9. 术语小词典' in m1)
check('④box 手册双闸分离段（收盘/盘中+三道门+四要素怎么看）',
      '双闸分离' in m2 and '收盘纪律' in m2 and '盘中实时' in m2
      and '混格式拒载' in m2 and '覆盖率门 ≥80%' in m2
      and '闸名｜池口径｜数据日期｜样本数' in m2)
check('④box 手册 fd 关系节新口径（满额部署·非试运行）',
      '重重检测四层全过当日满额部署' in m2)

# ---------------- ⑤ 引擎回归（f1_signal.py 若动：删除行=0 断言 + sha 双登记同步） ----------------
print('==== ⑤ 引擎回归 ====')
git = subprocess.run(['git', '-C', ROOT, 'diff', '--',
                      'f1/f1_signal.py', 'engine_f1/f1_signal.py'],
                     capture_output=True, text=True).stdout
removed = [l for l in git.splitlines()
           if l.startswith('-') and l.strip() and not l.startswith('---')]
# D4 允许的唯一删除=两条旧 generated meta 展示行 ×双副本（engine_f1+f1 各 2 条）；
# 判定主逻辑删除行必须=0
allowed = [l for l in removed if "'generated': pd.Timestamp.now()" in l]
check('⑤引擎删除行=0（仅允许 D4 generated meta 展示行替换，判定主逻辑零删除）',
      len(removed) == len(allowed) and len(removed) == 4,
      f'删除行数={len(removed)} 允许={len(allowed)}')
added_generated = [l for l in git.splitlines()
                   if l.startswith('+') and '北京时间' in l]
check('⑤D4 generated=utcnow+8+「北京时间」后缀（判定轮+快照轮两处×双副本）',
      len(added_generated) == 4)
check('⑤D10 快照轮入口挂 check_engine_authority（fail-closed exit=2）',
      "snapshot REFUSED" in src and src.count('check_engine_authority') == 3)  # 1 def+run_live+snapshot
# sha 双登记同步：登记表值 == 实际文件 sha == 双副本一致
reg = json.load(open(os.path.join(ROOT, 'engine_f1', 'AUTHORITY_SHA.json')))
sha_authority = hashlib.sha256(
    open(os.path.join(ROOT, 'engine_f1', 'f1_signal.py'), 'rb').read()).hexdigest()
sha_archive = hashlib.sha256(
    open(os.path.join(ROOT, 'f1', 'f1_signal.py'), 'rb').read()).hexdigest()
check('⑤sha 闸门双登记同步（登记表值=实际 sha=归档副本 sha）',
      reg['files']['f1_signal.py'] == sha_authority == sha_archive,
      f"registry={reg['files']['f1_signal.py'][:12]} actual={sha_authority[:12]}")
check('⑤sha 登记批次=PLANFINAL-PATCH-20261021', reg['batch'] == 'PLANFINAL-PATCH-20261021')
# 资金费降级回归承继（信号零变化断言）
ic_src = open(os.path.join(HERE, 'mine_common.py')).read()
ic_fn = ic_src[ic_src.index('def xsec_ic_series'):ic_src.index('def tstat')]
check('⑤a S1-S3 IC 管线（xsec_ic_series）无资金费过滤步骤',
      not re.search(r'fund|funding|资金费', ic_fn, re.I))
# ⑤c：引擎费常数 0.03%/bar 一行不动
removed_fee = [l for l in git.splitlines() if l.startswith('-') and '0.03' in l]
added_fee = [l for l in git.splitlines() if l.startswith('+') and '0.03' in l]
check('⑤c 引擎费常数 0.03%/bar 零改动（diff 无费常数行增删）', not removed_fee and not added_fee)
# ⑤e：新制判线数字承继断言（零新判线）
check('⑤e 判线冻结承继（t=−2.0 劣化线/J5 n20/POOL_CAP 50 = SHADOW_SPEC/J5/终裁数字）',
      ED.TIERS['POOL_CAP'] == ('单池满额档', 50) and ED.TIERS['FULL'] == ('满额档', 100)
      and ED.REVIEW_DUE == '2027-04-21')

print(f"\n==== 汇总：PASS={len(PASS)} FAIL={len(FAIL)} ====")
if FAIL:
    print('失败项：', FAIL)
    sys.exit(1)
print('ALL PASS')
