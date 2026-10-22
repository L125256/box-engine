#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_enhance_discount.py — 分域增强插件层·测试席五组测试（工单件⑤验收）
================================================================================
① 档位表新制映射单测（方法书 v1.1 §二·补遗，构造读数逐格断言：FULL/POOL_CAP/FROZEN；
   OFFLINE=保留值部署态不出现 + S5/S4 + pos_pct 新制 0.5/0.25/0）
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

# ---------------- ① 档位表新制映射单测（方法书 v1.1 §二·补遗，构造影子读数逐格断言） ----------------
print('==== ① 档位表新制映射单测 ====')
# 未封印观察（n<10，域激活）→ POOL_CAP 50%（单池封顶）
t = make_tree({'S1': shadow_cell(n=5), 'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False, 'replenish': {'fw_old131_weak_days': 0}},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 5, 'sealed': False}, fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
c = o['cells']['S1']
check('①新制 n<10 观察 → POOL_CAP 50%（单池封顶）', c['tier'] == 'POOL_CAP' and c['coef'] == 50,
      str(c['coef']))
check('①新制 pos_pct：S1=0.25/格（=0.5×50/100）', c['pos_pct'] == 0.25, str(c['pos_pct']))
check('①新制 S5 满额终裁生效 → FULL 100% · pos_pct=0.5/格',
      o['cells']['S5']['tier'] == 'FULL' and o['cells']['S5']['coef'] == 100
      and o['cells']['S5']['pos_pct'] == 0.5,
      f"tier={o['cells']['S5']['tier']} pos_pct={o['cells']['S5']['pos_pct']}")
check('①S4 SUSPENDED 灰态 → FROZEN 0% 不部署（新制映射）',
      o['cells']['S4']['deployed'] is False and o['cells']['S4']['coef'] == 0
      and o['cells']['S4']['tier'] == 'FROZEN')
check('①n 计数字段逐格保留（执照复审数据源，A0-5）',
      all('n_days' in o['cells'][cid] for cid in ('S1', 'S2', 'S3', 'S4', 'S5')))
check('①linkage 闸开灯绿不冻结', o['linkage']['enhanced_frozen'] is False)
shutil.rmtree(t)

# 域未激活 → FROZEN（新制映射：域未激活=FROZEN）
t = make_tree({'S1': shadow_cell(n=12, ic_mean=0.05, ic_t=1.0, hit_rate=0.55),
               'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 12, 'sealed': False, 'delta_mean': 0.1},
              fd_days=[], live=LIVE_OK,
              regs={'S1': [{'domain_label': '牛躁', 'cell_domain': '弱躁'}],   # 域标签不匹配=未激活
                    'S2': [{'domain_label': '弱躁', 'cell_domain': '弱躁'}],
                    'S3': [{'domain_label': '牛躁', 'cell_domain': '牛躁'}]})
o = run_in(t)
check('①新制 域未激活 → FROZEN 0%',
      o['cells']['S1']['tier'] == 'FROZEN' and o['cells']['S1']['coef'] == 0
      and o['cells']['S1']['pos_pct'] == 0)
shutil.rmtree(t)

# 封印 PASS：S1 → POOL_CAP（单池封顶 50%）；S5 → FULL 满档 100%
t = make_tree({'S1': shadow_cell(n=20, ic_mean=0.08, ic_t=3.0, hit_rate=0.7, sealed=True, verdict='PASS'),
               'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 20, 'sealed': True, 'verdict': 'PASS', 'delta_mean': 0.2},
              fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('①封印 PASS：S1 → POOL_CAP 50%（单池封顶）',
      o['cells']['S1']['tier'] == 'POOL_CAP' and o['cells']['S1']['coef'] == 50,
      str(o['cells']['S1']['coef']))
check('①封印 PASS：S5 全域格 FULL 满档 100%',
      o['cells']['S5']['tier'] == 'FULL' and o['cells']['S5']['coef'] == 100)
shutil.rmtree(t)

# 判死与未达标封印 → FROZEN 0%（新制无 25% 观察档）
t = make_tree({'S1': shadow_cell(n=20, ic_mean=0.08, ic_t=3.0, hit_rate=0.5, sealed=True, verdict='NOT_PASS'),
               'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 5, 'sealed': False}, fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('①封印 NOT_PASS → FROZEN 0%（安全侧）',
      o['cells']['S1']['tier'] == 'FROZEN' and o['cells']['S1']['coef'] == 0)
check('①未封印 n≥20 主腿过命中<60 → POOL_CAP（观察态非判死）',
      ED.tier_factor_cell(20, 0.08, 3.0, 0.5, False, None)[0] == 'POOL_CAP')
shutil.rmtree(t)

# 判死三路：早死线 / sealed FAIL / S5 J5（n≥20 Δ≤0）→ 一律 FROZEN 0%
t = make_tree({'S1': shadow_cell(n=10, ic_mean=-0.05, ic_t=-2.5, hit_rate=0.3),
               'S2': shadow_cell(n=20, ic_mean=-0.02, ic_t=-1.0, hit_rate=0.4, sealed=True, verdict='FAIL'),
               'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False},
               'S5': shadow_cell(n=20)},
              fd_state={'n_matured': 20, 'sealed': False, 'delta_mean': -0.1},
              fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('①早死线 → FROZEN 0%',
      o['cells']['S1']['tier'] == 'FROZEN' and o['cells']['S1']['coef'] == 0)
check('①sealed FAIL → FROZEN 0%', o['cells']['S2']['tier'] == 'FROZEN')
check('①S5 n≥20 Δ≤0 → FROZEN（J5 判死）', o['cells']['S5']['tier'] == 'FROZEN')
check('①部署态五格 tier∈{FULL,POOL_CAP,FROZEN}（OFFLINE 不出现，A3-5）',
      all(c['tier'] in ('FULL', 'POOL_CAP', 'FROZEN') for c in o['cells'].values()))
shutil.rmtree(t)

# 早死防御：n≥10 但 t>−2 → 不判死（POOL_CAP）
check('①n≥10 但 t>−2 不触发早死',
      ED.tier_factor_cell(12, -0.01, -1.0, 0.4, False, None)[0] == 'POOL_CAP')
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
check('①§5-⑦ 连续 5 轮输入失败 → 全降 FROZEN + 冻结',
      o['safe_default'] is True and o['linkage']['enhanced_frozen'] is True
      and all(c['tier'] == 'FROZEN' for cid, c in o['cells'].items() if c['deployed']))
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
# A4-6（方法书 v1.1 字面集）：页面模板与渲染产物禁「折扣档位」「折扣 <系数>%」「n=X/20」
_src = open(os.path.join(ROOT, 'f1', 'index.html')).read()
check('③A4-6 模板层：index.html 源码无「折扣档位/折扣 X%/n=X/20/影子」',
      '折扣档位' not in _src and not re.search(r"折扣 '?\+?", _src)
      and "'/20'" not in _src and '影子' not in _src,
      f"折扣档位={'折扣档位' in _src} 影子={'影子' in _src}")
check('③区块渲染：档位/免责/灰态逐字在页',
      '档位：' in enh and '系数 ' in enh
      and '分域增强=F1 主引擎之外的实验插件层' in enh
      and '未部署·不占用仓位' in enh and '高波停门·弱稳域' in enh)
# A4-6 渲染层正测：用本件新制代码产物构造 enhancement 输入（仓库内 f1_live.json 为旧制
# 云端轮回传件，其文案属旧代码产物，待下轮云端刷新——不作为新制渲染断言依据）
_live = json.load(open(os.path.join(ROOT, 'f1', 'f1_live.json')))
t_new = make_tree({'S1': shadow_cell(n=12, ic_mean=0.05, ic_t=1.0, hit_rate=0.55),
                   'S2': shadow_cell(), 'S3': shadow_cell(),
                   'S4': {'gate_state': 'SUSPENDED', 'sealed': False, 'replenish': {'fw_old131_weak_days': 1}},
                   'S5': shadow_cell(n=5)},
                  fd_state={'n_matured': 5, 'sealed': False}, fd_days=[],
                  live=LIVE_OK, regs=REG_OK)
_enh_new = run_in(t_new)
shutil.rmtree(t_new)
_live.setdefault('meta', {})['enhancement'] = _enh_new
tmp_new = os.path.join(tempfile.mkdtemp(), 'newenh.json')
json.dump(_live, open(tmp_new, 'w'), ensure_ascii=False)
rh3 = subprocess.run(['node', os.path.join(ROOT, 'f1', 'render_harness.cjs'),
                      os.path.join(ROOT, 'f1', 'index.html'), tmp_new],
                     capture_output=True, text=True, timeout=60)
d3 = json.loads(rh3.stdout[rh3.stdout.index('RENDER_JSON_START') + 17:])
enh3 = d3['enh']['innerHTML']
check('③A4-6 渲染层（新制产物输入）：渲染产物无「折扣档位/折扣 X%/n=X/20/影子」',
      all(x not in enh3 for x in ('折扣档位', '影子'))
      and not re.search(r'折扣 \d+(\.\d+)?%', enh3)
      and not re.search(r'n=\d+/20', enh3))
check('③A4-2/A4-3：新制 S5 三行非占位符 + 满额 0.5%/格 渲染',
      '📊 ' in enh3 and '—</div>' not in enh3.split('📊 ')[1][:60]
      and '0.5%' in enh3 and '满额=FULL' in enh3, enh3[enh3.find('💵'):enh3.find('💵') + 80])
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
      and '旧制的「25% 观察档 / 0.125% 折扣仓」已废除，页面上不再出现' in m1
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
# （HEAD~1 基线下豁免已备案的「挂接行替换」类安全删除：
#   FW-READOUT-PATH-20261021：forward_readout 绝对路径→__file__ 相对解析替换块
#     （6 删除行：路径 2 + subprocess.run 调用行 4），sha 8a53b252→7da41c80 已登记；
#   ENHANCE-PATH-20261022：判定轮/快照轮两处 enhance_discount subprocess 补传
#     F1_OUT_JSON（env=_env 参数并入调用行，每处 1 删除行：
#     '--auto'], timeout=300, check=False) → +env=_env），判定主逻辑零删除）
_fw_replaced = ('forward_readout.py', 'subprocess.run([sys.executable,',
                "'--auto'], timeout=300, check=False)")
removed_logic = [l for l in git.splitlines()
                 if l.startswith('-') and l.strip() and not l.startswith('---')
                 and not any(k in l for k in _fw_replaced)]
check('⑤d f1_signal.py 判定主逻辑零删除（diff 仅新增挂接行）', not removed_logic,
      f'删除行数={len(removed_logic)}')
# 5e：判线数字承继断言（零新判线——本件常量=SHADOW_SPEC/J5 冻结值）
# ⑤e：判线数字承继断言（零新判线——判线数字=SHADOW_SPEC/J5 冻结值；档位表=新制映射 v1.1 §二补遗）
check('⑤e 判线冻结承继（t=2.0/命中 0.60/n20/早死 10 = SHADOW_SPEC §3 数字）',
      ED.TIERS == {'FULL': ('满额档', 100), 'POOL_CAP': ('单池封顶', 50),
                   'FROZEN': ('冻结', 0), 'OFFLINE': ('下线', 0)}
      and ED.SINGLE_POOL_CAP == 50 and ED.BASELINE_PCT == 0.5)

# ---------------- ⑥ 本格标的可见性（整改 2026-10-21：用户立法准绳「重要信息页面肉眼可见」） ----------------
print('\n==== ⑥ 本格标的可见性（symbols 字段整改） ====')
# 6a：S1-S3 最新登记行因子降序前 5 → symbols_top（零新判线：转述 shadow_reg 已有读数）
_reg_factor = {'AAOIUSDT': 0.07, 'BBBUSDT': 0.21, 'CCCUSDT': -0.1, 'DDDUSDT': 0.15,
               'EEEUSDT': 0.03, 'FFFUSDT': 0.99, 'GGGUSDT': 0.0}
_regs6 = {cid: [{'domain_label': '弱躁', 'cell_domain': '弱躁' if cid != 'S3' else '牛躁',
                 'date': '2026-10-21', 'n_names': 7, 'factor': _reg_factor}]
          for cid in ('S1', 'S2', 'S3')}
t = make_tree({'S1': shadow_cell(n=5), 'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False, 'replenish': {'fw_old131_weak_days': 0}},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 5, 'sealed': False}, fd_days=[], live=LIVE_OK, regs=_regs6)
o = run_in(t)
check('⑥a S1 symbols_top=因子值降序前 5（数量封顶 5）',
      [x['sym'] for x in o['cells']['S1']['symbols_top']] ==
      ['FFFUSDT', 'BBBUSDT', 'DDDUSDT', 'AAOIUSDT', 'EEEUSDT'],
      str([x['sym'] for x in o['cells']['S1']['symbols_top']]))
check('⑥b S1-S3 三格 symbols_note/scope 均存在且含「因子记分牌格」与读数日期',
      all('因子记分牌格' in o['cells'][cid]['symbols_note']
          and '2026-10-21' in o['cells'][cid]['symbols_note']
          and o['cells'][cid]['symbols_scope'] for cid in ('S1', 'S2', 'S3')))
# 6c：登记行缺 factor 字段（旧夹具/残行）→ symbols_top=[] 兜底不抛错
t = make_tree({'S1': shadow_cell(n=5), 'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False, 'replenish': {'fw_old131_weak_days': 0}},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 5, 'sealed': False}, fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('⑥c 登记行缺 factor → symbols_top=[] 兜底不抛错',
      o['cells']['S1']['symbols_top'] == [] and '暂无当日因子读数' in o['cells']['S1']['symbols_note'])
# 6d：S4 纪律格=不买任何标的；S5 服务对象=增强层自身小仓（不动 F1 持仓）
t = make_tree({'S1': shadow_cell(n=5), 'S2': shadow_cell(), 'S3': shadow_cell(),
               'S4': {'gate_state': 'SUSPENDED', 'sealed': False, 'replenish': {'fw_old131_weak_days': 0}},
               'S5': shadow_cell(n=5)},
              fd_state={'n_matured': 5, 'sealed': False}, fd_days=[], live=LIVE_OK, regs=REG_OK)
o = run_in(t)
check('⑥d S4 纪律格标注「不买任何标的」',
      '不买任何标的' in (o['cells']['S4'].get('symbols_note') or ''))
check('⑥e S5 服务对象标注=增强层自身持仓 + 不动 F1 持仓',
      '增强层' in (o['cells']['S5'].get('targets_note') or '')
      and 'F1' in (o['cells']['S5'].get('targets_note') or ''))
# 6f：页面渲染含「本格标的」行（读 JSON 不写死标的；缺字段兜底）
html = open(os.path.join(ROOT, 'f1', 'index.html')).read()
check('⑥f index.html 卡片含「🎯 本格标的」渲染行（数据源 symbols_*，无写死标的名）',
      '本格标的' in html and 'symbols_note' in html and 'symbols_top' in html
      and 'NVDAUSDT' not in html.split('renderEnhancement')[1].split('function acctRow')[0])

print(f"\n==== 汇总：PASS={len(PASS)} FAIL={len(FAIL)} ====")
if FAIL:
    print('失败项：', FAIL)
    sys.exit(1)
print('ALL PASS')
