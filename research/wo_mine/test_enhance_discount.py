#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_enhance_discount.py — 分域增强插件层·测试席五组测试（工单件⑤验收）
================================================================================
① 折扣档位表五态单测（构造影子读数逐档断言：T0/T1/T2(单池封顶50)/T3/T4 + S5/S4）
② 旁路异常不阻断断言（enhance_discount 对残缺输入不抛出 + subprocess 挂接 check=False）
③ 页面本地渲染无 JS 报错 + 无字段兜底（render_harness.cjs）
④ 双手册章节渲染断言
⑤ 资金费降级回归（信号零变化断言：S1-S3/S5 判定管线资金费前置过滤=零命中；
   引擎 f1_signal.py 费常数 0.03%/bar 行不动；本单 diff 仅 main() 挂接段）
运行：python3 research/wo_mine/test_enhance_discount.py
"""
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

# ---------------- ① 折扣档位表五态单测（构造影子读数逐档断言） ----------------
print('==== ① 折扣档位表五态单测 ====')
# T0 25%：n<10
t = make_tree({'S1': shadow_cell(n=5), 'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False, 'replenish': {'fw_old131_weak_days': 0}},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 5, 'sealed': False}, fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
c = o['cells']['S1']
check('①T0 n<10 → 观察档 25%', c['tier'] == 'T0' and c['coef'] == 25, str(c['coef']))
check('①S4 SUSPENDED 灰态不部署', o['cells']['S4']['deployed'] is False and o['cells']['S4']['coef'] == 0)
check('①linkage 闸开灯绿不冻结', o['linkage']['enhanced_frozen'] is False)
shutil.rmtree(t)

# T1 50%：n≥10 且早死未触发（IC>0）
t = make_tree({'S1': shadow_cell(n=12, ic_mean=0.05, ic_t=1.0, hit_rate=0.55),
               'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 12, 'sealed': False, 'delta_mean': 0.1},
              fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('①T1 n≥10 无早死 → 试运行档 50%',
      o['cells']['S1']['tier'] == 'T1' and o['cells']['S1']['coef'] == 50)
check('①S5 n≥10 → T1（J5 n≥20 未至只累计）', o['cells']['S5']['tier'] == 'T1')
shutil.rmtree(t)

# T2 100%→单池封顶 50%：sealed PASS
t = make_tree({'S1': shadow_cell(n=20, ic_mean=0.08, ic_t=3.0, hit_rate=0.7, sealed=True, verdict='PASS'),
               'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 20, 'sealed': True, 'verdict': 'PASS', 'delta_mean': 0.2},
              fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('①T2 单池封顶：S1 sealed PASS → T2 但 coef=50%',
      o['cells']['S1']['tier'] == 'T2' and o['cells']['S1']['coef'] == 50,
      str(o['cells']['S1']['coef']))
check('①S5 全域格 T2 满档 100%',
      o['cells']['S5']['tier'] == 'T2' and o['cells']['S5']['coef'] == 100)
shutil.rmtree(t)

# T3 25%：sealed NOT_PASS（主腿过辅助腿弱同型）+ 未封印命中率<60 防御分支
t = make_tree({'S1': shadow_cell(n=20, ic_mean=0.08, ic_t=3.0, hit_rate=0.5, sealed=True, verdict='NOT_PASS'),
               'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 5, 'sealed': False}, fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('①T3 sealed NOT_PASS → 降档 25%',
      o['cells']['S1']['tier'] == 'T3' and o['cells']['S1']['coef'] == 25)
check('①T3 未封印 n≥20 主腿过命中<60 → T3（防御分支同表）',
      ED.tier_factor_cell(20, 0.08, 3.0, 0.5, False, None)[0] == 'T3')
shutil.rmtree(t)

# T4 0%：早死线（n≥10 ∧ t≤−2 ∧ IC<0）+ sealed FAIL + S5 J5 判死
t = make_tree({'S1': shadow_cell(n=10, ic_mean=-0.05, ic_t=-2.5, hit_rate=0.3),
               'S2': shadow_cell(n=20, ic_mean=-0.02, ic_t=-1.0, hit_rate=0.4, sealed=True, verdict='FAIL'),
               'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False},
               'S5': shadow_cell(n=20)},
              fd_state={'n_matured': 20, 'sealed': False, 'delta_mean': -0.1},
              fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('①T4 早死线 → 0%',
      o['cells']['S1']['tier'] == 'T4' and o['cells']['S1']['coef'] == 0)
check('①T4 sealed FAIL → 0%', o['cells']['S2']['tier'] == 'T4')
check('①S5 n≥20 Δ≤0 → T4（J5 判死）', o['cells']['S5']['tier'] == 'T4')
shutil.rmtree(t)

# 早死防御：n≥10 但 t>−2 → 不判死（T1）
check('①n≥10 但 t>−2 不触发早死',
      ED.tier_factor_cell(12, -0.01, -1.0, 0.4, False, None)[0] == 'T1')
# §2.5 单向让位联动
lk = ED.build_linkage({'signal': {'gate': {'on_holdcash': True}},
                       'breakers': {'overall': {'light': 'green'}}})
check('①§2.5-1 闸关 → 冻结开新仓', lk['enhanced_frozen'] is True)
lk = ED.build_linkage({'signal': {'gate': {'on_holdcash': False}},
                       'breakers': {'overall': {'light': 'red'}}})
check('①§2.5-2 红灯 → 整体冻结', lk['enhanced_frozen'] is True)
# §5-⑦ 连续 5 轮失败安全侧默认
t = make_tree(None, live=LIVE_OK, out_prev={'inputs_ok': False, 'fail_streak': 4})
o = run_in(t)
check('①§5-⑦ 连续 5 轮输入失败 → 全降 T0 + 冻结',
      o['safe_default'] is True and o['linkage']['enhanced_frozen'] is True
      and all(c['tier'] == 'T0' for cid, c in o['cells'].items() if c['deployed']))
shutil.rmtree(t)

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

# ---------------- ③ 页面本地渲染无 JS 报错 + 无字段兜底 ----------------
print('==== ③ 页面渲染（render_harness）====')
rh = subprocess.run(['node', os.path.join(ROOT, 'f1', 'render_harness.cjs'),
                     os.path.join(ROOT, 'f1', 'index.html'),
                     os.path.join(ROOT, 'f1', 'f1_live.json')],
                    capture_output=True, text=True, timeout=60)
check('③渲染执行零 JS 报错（stderr 无 Error）', rh.returncode == 0 and 'Error' not in rh.stderr,
      rh.stderr[:120])
out = rh.stdout[rh.stdout.index('RENDER_JSON_START') + 17:]
d = json.loads(out)
enh = d['enh']['innerHTML']
check('③区块渲染：档位/免责/灰态逐字在页',
      '折扣 25%' in enh and '观察档' in enh
      and '分域增强=F1 主引擎之外的实验插件层' in enh
      and '未部署·不占用仓位' in enh and '高波停门·弱稳域' in enh)
_no = json.load(open(os.path.join(ROOT, 'f1', 'f1_live.json')))
_no.get('meta', {}).pop('enhancement', None)   # 旧 JSON：仅缺 enhancement 字段
tmp = os.path.join(tempfile.mkdtemp(), 'noenh.json')
json.dump(_no, open(tmp, 'w'), ensure_ascii=False)
rh2 = subprocess.run(['node', os.path.join(ROOT, 'f1', 'render_harness.cjs'),
                      os.path.join(ROOT, 'f1', 'index.html'), tmp],
                     capture_output=True, text=True, timeout=60)
d2 = json.loads(rh2.stdout[rh2.stdout.index('RENDER_JSON_START') + 17:])
check('③旧 JSON 无 enhancement 字段 → 「增强层未上线」不报错',
      '增强层未上线' in d2['enh']['innerHTML'] and rh2.returncode == 0)

# ---------------- ④ 双手册章节渲染 ----------------
print('==== ④ 双手册章节 ====')
m1 = open(os.path.join(ROOT, 'f1', 'manual.html')).read()
m2 = open(os.path.join(ROOT, 'box', 'manual.html')).read()
check('④f1 手册「分域增强插件」章节（四问逐字）',
      '<h2>8. 分域增强插件' in m1 and '这是什么</b>：F1 主引擎之外，我们另外开了几张很小的'
      and '折扣越低=证据越弱；显示 ⚠ = 已停用' in m1
      and '绝不能因此少买或不买 F1 榜单' in m1 and '任何冲突听 F1。' in m1)
check('④f1 手册术语词典编号顺延 §8→§9', '<h2>9. 术语小词典' in m1)
check('④box 手册「与 F1 分域增强的关系」短节（§6.2 逐字）',
      '与 F1 分域增强的关系' in m2
      and 'fd 出场结构已被选为 F1 页『分域增强』实验格 S5' in m2
      and '箱体页本身<b>不部署任何仓位</b>' in m2 and '操作依据唯一=F1' in m2)

# ---------------- ⑤ 资金费降级回归（信号零变化断言） ----------------
print('==== ⑤ 资金费降级回归 ====')
# 5a：S1-S3 IC 判定管线（mine_common.xsec_ic_series / batch2_run）资金费前置过滤=零命中
ic_src = open(os.path.join(HERE, 'mine_common.py')).read()
ic_fn = ic_src[ic_src.index('def xsec_ic_series'):ic_src.index('def tstat')]
check('⑤a S1-S3 IC 管线（xsec_ic_series）无资金费过滤步骤',
      not re.search(r'fund|funding|资金费', ic_fn, re.I))
b2 = open(os.path.join(HERE, 'batch2_run.py')).read()
check('⑤a batch2 面板/因子管线零资金费引用', not re.search(r'fund|funding|资金费', b2, re.I))
# 5b：S5 Δ meanR 管线（fd_revive_run 判定路径）资金费前置过滤=零命中
fd = open(os.path.join(ROOT, 'research', 'wo_fddual', 'fd_revive_run.py')).read()
check('⑤b S5 Δ meanR 管线无资金费过滤（仅双边费 0.03%/bar 出场记账）',
      not re.search(r'funding|资金费', fd, re.I) and 'FEE' in fd)
# 5c：引擎 f1_signal.py 费常数 0.03%/bar 一行不动（本单 diff 不触及费常数行）
# 基线缺陷随手修（UX 修复批 2026-10-21）：原 `git diff`（工作区 vs index）在已 commit
# 场景恒为空、测不到上批提交的引擎改动——基线改 HEAD~1（本单 commit 前后对比）。
git = subprocess.run(['git', '-C', ROOT, 'diff', 'HEAD~1', '--',
                      'f1/f1_signal.py', 'engine_f1/f1_signal.py'],
                     capture_output=True, text=True).stdout
removed_fee = [l for l in git.splitlines() if l.startswith('-') and '0.03' in l]
added_fee = [l for l in git.splitlines() if l.startswith('+') and '0.03' in l]
check('⑤c 引擎费常数 0.03%/bar 零改动（diff 无费常数行增删）', not removed_fee and not added_fee)
# 5d：本单 f1_signal.py diff 仅 main() CLI 挂接段（四因子/闸/熔断主逻辑零改动）
# （HEAD~1 基线下豁免 FW-READOUT-PATH-20261021 已备案的 forward_readout 绝对路径
#   →__file__ 相对解析替换块（6 删除行：路径 2 + subprocess.run 调用行 4），
#   sha 8a53b252→7da41c80 已登记，零判定逻辑改动）
_fw_replaced = ('forward_readout.py', 'subprocess.run([sys.executable,')
removed_logic = [l for l in git.splitlines()
                 if l.startswith('-') and l.strip() and not l.startswith('---')
                 and not any(k in l for k in _fw_replaced)]
check('⑤d f1_signal.py 判定主逻辑零删除（diff 仅新增挂接行）', not removed_logic,
      f'删除行数={len(removed_logic)}')
# 5e：判线数字承继断言（零新判线——本件常量=SHADOW_SPEC/J5 冻结值）
check('⑤e 判线冻结承继（t=2.0/命中 0.60/n20/早死 10 = SHADOW_SPEC §3 数字）',
      ED.TIERS == {'T0': ('观察档', 25), 'T1': ('试运行档', 50), 'T2': ('转正档', 100),
                   'T3': ('降档', 25), 'T4': ('下线', 0)} and ED.SINGLE_POOL_CAP == 50)

print(f"\n==== 汇总：PASS={len(PASS)} FAIL={len(FAIL)} ====")
if FAIL:
    print('失败项：', FAIL)
    sys.exit(1)
print('ALL PASS')
