#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_ux_fix_batch.py — 工程保障团队 UX 审查修复批·测试席五组测试（2026-10-21）
================================================================================
① 箱体 trim 回归锚（A-01）：10-19 dirty 输入→BULL_OPEN=false/BULL_ASOF=2026-10-17；
   正常输入→与 F1 trim_and_guard（METHOD_BOOK_DECBAR.md §二）逐例 parity
② S5 三行渲染+兜底（B-01）：实时信号/满额白话/实际仓位金额 + 缺字段兜底「—」
③ §7.9 五场景在位 + 版本 v1.6 + 双副本逐字节一致
④ f1 manual §3 标题（f1/ 与 f1_web/ 双副本）
⑤ f1_signal.py 本批 diff=0 + AUTHORITY_SHA 登记值与实际文件 sha256 同步（不动引擎不改 sha）
运行：python3 research/wo_uxfix/test_ux_fix_batch.py
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else FAIL}] {name}" + (f' —— {detail}' if detail else ''))


def load_generate_page():
    spec = importlib.util.spec_from_file_location('gp_uxfix', os.path.join(ROOT, 'generate_page.py'))
    m = importlib.util.module_from_spec(spec)
    sys.modules['gp_uxfix'] = m
    spec.loader.exec_module(m)
    return m


def mk_pool(times):
    return {'X': [{'time': t, 'open': 1, 'high': 1, 'low': 1, 'close': 1} for t in times]}


# ---------------- ① 箱体 trim 回归锚 ----------------
print('==== ① 箱体 trim 回归锚（A-01 / DECBAR 口径移植）====')
import datetime  # noqa: E402
gp = load_generate_page()
# 主锚：10-19 dirty 输入（10-19 forming 盘中K，最后完整日=10-17 周六）
p, g = gp.trim_and_guard_pool(
    mk_pool(['2026-10-15', '2026-10-16', '2026-10-17', '2026-10-19']),
    now=datetime.datetime(2026, 10, 19, 0, 57))
check('①主锚 10-19 dirty：trim=[10-19] 且最后完整日=10-17',
      g['trimmed'] == ['2026-10-19'] and g['last_complete'] == '2026-10-17', str(g['trimmed']))
check('①主锚 R-错位 fail-closed → BULL_OPEN=false',
      g['settled'] is False and g['check'] == 'R_MISALIGN', g['check'])
check('①主锚 BULL_ASOF=2026-10-17（最后完整日语义）',
      g['last_complete'] == '2026-10-17')
# 正常输入：10-20 完整 + 10-21 forming，now=10-21 00:57（判定级轮实况）
p2, g2 = gp.trim_and_guard_pool(
    mk_pool(['2026-10-16', '2026-10-17', '2026-10-20', '2026-10-21']),
    now=datetime.datetime(2026, 10, 21, 0, 57))
check('①正常输入：trim=[10-21]、asof=10-20、闸开放判定可用',
      g2['trimmed'] == ['2026-10-21'] and g2['settled'] and g2['asof'] == '2026-10-20')
# 反例锚（METHOD_BOOK §四）
_, gs = gp.trim_and_guard_pool(mk_pool(['2026-10-12']),
                               now=datetime.datetime(2026, 10, 20, 0, 30))
_, gm = gp.trim_and_guard_pool(mk_pool(['2026-10-14']),
                               now=datetime.datetime(2026, 10, 20, 0, 30))
check('①反例锚 R-陈旧（8 日>7）拒绝', gs['check'] == 'R_STALE' and not gs['settled'])
check('①反例锚 R-错位（6 日>4）拒绝', gm['check'] == 'R_MISALIGN' and not gm['settled'])
# 与 F1 trim_and_guard 逐例 parity（闸与 F1 同步）
sys.path.insert(0, os.path.join(ROOT, 'f1'))
import f1_signal  # noqa: E402
cases = [(['2026-10-15', '2026-10-16', '2026-10-17', '2026-10-19'], datetime.datetime(2026, 10, 19, 0, 57)),
         (['2026-10-16', '2026-10-17', '2026-10-20', '2026-10-21'], datetime.datetime(2026, 10, 21, 0, 57)),
         (['2026-10-12'], datetime.datetime(2026, 10, 20, 0, 30)),
         (['2026-10-14'], datetime.datetime(2026, 10, 20, 0, 30))]
ok = True
for cal, now in cases:
    gf = f1_signal.trim_and_guard(cal, now)
    _, gb = gp.trim_and_guard_pool(mk_pool(cal), now)
    ok &= (gf['settled'] == gb['settled'] and gf.get('check') == gb.get('check')
           and gf['trimmed'] == gb['trimmed']
           and gf.get('asof', gf.get('last_complete')) == gb.get('asof', gb.get('last_complete')))
check('①四例 parity：箱体移植版 == F1 trim_and_guard（settled/check/trimmed/asof）', ok)
check('①模板文案：牛闸快照（落定K）标注在页（meta 行+温度计行）',
      gp.HTML_TMPL.count('BULL_ASOF+BULL_NOTE') == 2)

# ---------------- ② S5 三行渲染 + 兜底 ----------------
print('==== ② S5 三行渲染+兜底（B-01）====')


def harness(json_path, state_path=None):
    cmd = ['node', os.path.join(ROOT, 'f1', 'render_harness.cjs'),
           os.path.join(ROOT, 'f1', 'index.html'), json_path]
    if state_path:
        cmd.append(state_path)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    out = json.loads(r.stdout[r.stdout.index('RENDER_JSON_START') + 17:])
    return r, out['enh']['innerHTML']


r, h = harness(os.path.join(ROOT, 'f1', 'f1_live.json'))
check('②渲染零 JS 报错', r.returncode == 0 and 'Error' not in r.stderr)
# ②S5 三行断言（新制口径，方法书 v1.1 §二·补遗/A4-3：S5 满额=FULL 100%·pos_pct=0.5%/格；
# 旧 0.125%=旧制 25% 档过渡态实测，自 v1.1 起不得再作期望值）。渲染输入用本批新制
# enhance_discount 产物构造（仓库内 f1_live.json 为旧制云端轮回传件，待下轮云端刷新）。
sys.path.insert(0, os.path.join(ROOT, 'research', 'wo_mine'))
import enhance_discount as ED   # noqa: E402
_t = tempfile.mkdtemp(prefix='uxfix_s5_')
os.makedirs(os.path.join(_t, 'f1'))
json.dump({'cells': {'S1': {'status': 'ACCUMULATING', 'sealed': False,
                            'accumulation': {'n_days': 12, 'ic_mean': 0.05, 'ic_t': 1.0, 'hit_rate': 0.55}},
                     'S2': {'status': 'ACCUMULATING', 'sealed': False,
                            'accumulation': {'n_days': 8}},
                     'S3': {'status': 'ACCUMULATING', 'sealed': False,
                            'accumulation': {'n_days': 15, 'ic_mean': 0.03, 'ic_t': 1.5, 'hit_rate': 0.58}},
                     'S4': {'gate_state': 'SUSPENDED', 'sealed': False,
                            'replenish': {'fw_old131_weak_days': 1}},
                     'S5': {'status': 'ACCUMULATING', 'sealed': False, 'n_matured': 0,
                            'accumulation': {'n_days': 0}}},
           'round_asof': '2026-10-20'}, open(os.path.join(_t, 'f1', 'shadow_state.json'), 'w'))
json.dump({'n_matured': 0, 'sealed': False}, open(os.path.join(_t, 'f1', 'fd_revive_state.json'), 'w'))
open(os.path.join(_t, 'f1', 'fd_revive_days.jsonl'), 'w').close()
json.dump({'signal': {'asof': '2026-10-20', 'gate': {'on_holdcash': False}},
           'breakers': {'overall': {'light': 'green'}}},
          open(os.path.join(_t, 'f1', 'f1_live.json'), 'w'))
for _cid, _dom in (('S1', '弱躁'), ('S2', '弱躁'), ('S3', '牛躁')):
    with open(os.path.join(_t, 'f1', f'shadow_reg_{_cid}.jsonl'), 'w') as _f:
        _f.write(json.dumps({'domain_label': _dom, 'cell_domain': _dom}, ensure_ascii=False) + '\n')
_ED_OLD = (ED.ROOT, ED.STATEDIR, ED.SHADOW_STATE_F, ED.FD_STATE_F, ED.FD_DAYS_F, ED.ROUND_F, ED.OUT_F)
ED.ROOT = _t; ED.STATEDIR = os.path.join(_t, 'f1')
ED.SHADOW_STATE_F = os.path.join(ED.STATEDIR, 'shadow_state.json')
ED.FD_STATE_F = os.path.join(ED.STATEDIR, 'fd_revive_state.json')
ED.FD_DAYS_F = os.path.join(ED.STATEDIR, 'fd_revive_days.jsonl')
ED.ROUND_F = os.path.join(ED.STATEDIR, 'f1_live.json')
ED.OUT_F = os.path.join(ED.STATEDIR, 'enhancement_state.json')
_enh = ED.run(auto=True)
ED.ROOT, ED.STATEDIR, ED.SHADOW_STATE_F, ED.FD_STATE_F, ED.FD_DAYS_F, ED.ROUND_F, ED.OUT_F = _ED_OLD
import shutil as _sh
_sh.rmtree(_t, ignore_errors=True)
_d = json.load(open(os.path.join(ROOT, 'f1', 'f1_live.json')))
_d.setdefault('meta', {})['enhancement'] = _enh
_tmp_new = os.path.join(tempfile.mkdtemp(), 'new_enh.json')
json.dump(_d, open(_tmp_new, 'w'), ensure_ascii=False)
_rn, _hn = harness(_tmp_new)
check('②S5 实时信号行（无出场事件·新制措辞，无 n=X/20 模板）',
      'S5 今日实时信号：无出场事件（配对累计 n=0）' in _hn
      and 'n=0/20' not in _hn)
check('②S5 满额白话行（新制逐字：FULL 100%·0.5%/格）',
      '本格满额=FULL 100%（0.5%/格）；与 S1-S3 单池封顶 50%（0.25%/格）不同' in _hn)
check('②S5 实际仓位金额行（0.5%=0.5%/格×系数 100%，新制期望值）',
      '实际仓位金额=0.5%（=基线 0.5%/格×系数 100%）' in _hn)
check('②新制渲染零 JS 报错', _rn.returncode == 0 and 'Error' not in _rn.stderr)
d = json.load(open(os.path.join(ROOT, 'f1', 'f1_live.json')))
e = d['meta']['enhancement']
for c in e['cells'].values():
    for k in ('realtime', 'full_note', 'pos_pct'):
        c.pop(k, None)
tmp = os.path.join(tempfile.mkdtemp(), 'old.json')
json.dump(d, open(tmp, 'w'), ensure_ascii=False)
_, h2 = harness(tmp)
check('②缺字段兜底「—」且零报错',
      '📊 —' in h2 and '💰 —' in h2 and '实际仓位金额=—' in h2)

# ---------------- ②b 缓存免疫三态（2026-10-22）----------------
print('==== ②b 缓存免疫三态（双保险：state?ts 独立通道+择新渲染+🎯兜底行）====')
_d3 = json.load(open(os.path.join(ROOT, 'f1', 'f1_live.json')))
# 新制 state 构造（含 symbols 三字段，与本批 enhancement_state.json 同制）
_new_state = {'generated': '2026-10-21 23:20:00', 'asof': '2026-10-20',
              'cells': {'S1': {'name': 'S1 反转·弱躁域', 'domain': '弱躁域', 'tier': 'POOL_CAP',
                               'coef': 50, 'n_days': 0, 'deployed': True, 'domain_active': False,
                               'symbols_scope': '模拟池内', 'symbols_note': '本期读数分前 5（参考）',
                               'symbols_top': [{'sym': 'SOXSUSDT', 'val': 0.124},
                                               {'sym': 'UVXYUSDT', 'val': 0.091}]},
                        'S5': {'name': 'S5 fd 出场增强', 'domain': '全域', 'tier': 'FULL',
                               'tier_name': '满额档',
                               'coef': 100, 'n_days': 0, 'deployed': True, 'domain_active': True,
                               'pos_pct': 0.5, 'realtime': {'has_event': False, 'text': 'S5 今日实时信号：无出场事件（配对累计 n=0）'},
                               'full_note': '本格满额=FULL 100%（0.5%/格）'}}}
_state_f = os.path.join(tempfile.mkdtemp(), 'state_new.json')
json.dump(_new_state, open(_state_f, 'w'), ensure_ascii=False)
# 态1：新 JSON（meta.enhancement=新制）→ 🎯 行+新档位正常渲染
_d3.setdefault('meta', {})['enhancement'] = json.loads(json.dumps(_new_state))
_t1 = os.path.join(tempfile.mkdtemp(), 't1.json'); json.dump(_d3, open(_t1, 'w'), ensure_ascii=False)
_r1, _h1 = harness(_t1, _state_f)
check('②b 态1 新 JSON：🎯 行+POOL_CAP 档位+标的名单在场，零 JS 报错',
      '🎯 本格标的' in _h1 and 'SOXSUSDT' in _h1 and '单池封顶' in _h1
      and _r1.returncode == 0 and 'Error' not in _r1.stderr)
# 态2：旧缓存 JSON（meta.enhancement=旧制 T0/25% 无 symbols）+ state 独立通道=新制 → 兜底渲染新制
_old = json.loads(json.dumps(_d3))
_old['meta']['enhancement'] = {'generated': '2026-10-20 08:30:00', 'asof': '2026-10-19',
                               'cells': {'S1': {'name': 'S1 反转·弱躁域', 'domain': '弱躁域', 'tier': 'T0',
                                                'coef': 25, 'n_days': 0, 'deployed': True, 'domain_active': False},
                                         'S5': {'name': 'S5 fd 出场增强', 'domain': '全域', 'tier': 'T0',
                                                'coef': 25, 'n_days': 0, 'deployed': True, 'domain_active': True}}}
_t2 = os.path.join(tempfile.mkdtemp(), 't2.json'); json.dump(_old, open(_t2, 'w'), ensure_ascii=False)
_r2, _h2b = harness(_t2, _state_f)
check('②b 态2 旧缓存 JSON：state 通道择新兜底，渲染新制 FULL/POOL_CAP+🎯 名单，零 JS 报错',
      'SOXSUSDT' in _h2b and '满额档' in _h2b and 'T0' not in _h2b
      and _r2.returncode == 0 and 'Error' not in _r2.stderr)
# 态3：双通道都缺 symbols → 提示行「🎯 本格标的：本轮回传未含名单（asof=…）」
_miss = json.loads(json.dumps(_d3))
for _c in _miss['meta']['enhancement']['cells'].values():
    for _k in ('symbols_note', 'symbols_top', 'symbols_scope'):
        _c.pop(_k, None)
_t3 = os.path.join(tempfile.mkdtemp(), 't3.json'); json.dump(_miss, open(_t3, 'w'), ensure_ascii=False)
_r3, _h3 = harness(_t3)   # 不传三参 → state 通道 404 模拟双缺
check('②b 态3 双缺 symbols：提示行在场（禁止静默空白），零 JS 报错',
      '🎯 本格标的' in _h3 and '本轮回传未含名单（asof=' in _h3
      and _r3.returncode == 0 and 'Error' not in _r3.stderr)

# ---------------- ③ §7.9 五场景 + v1.6 + 双副本 ----------------
print('==== ③ 台账 §7.9 五场景 + v1.6（军规补丁）====')
led_e = open(os.path.join(ROOT, 'engine_f1', 'F1_台账口径_v1.md')).read()
led_f = open(os.path.join(ROOT, 'f1', 'F1_台账口径_v1.md')).read()
check('③双副本逐字节一致', led_e == led_f)
five = ['「箱体闸和 F1 闸为什么不一致」', '「影子期呢」', '「S5 仓位多少」',
        '「温度计怎么关了但 fd 激活」', '「牛闸准不准」']
check('③§7.9 五场景全部在位', all(s in led_e for s in five),
      str([s for s in five if s not in led_e]))
check('③§7.9 章节在位（v1.6 增补）', '### 7.9 双闸与温度计新场景（v1.6 增补）' in led_e)
check('③§7.11 随批检查清单第 4 条（v1.8 缓存免疫教训）在位',
      '所有数据文件取数必须带防缓存参数' in led_e)
check('③版本头 v1.8 行在位（随批次同步更新）', '- 版本：v1.8（' in led_e)

# ---------------- ④ manual §3 标题 ----------------
print('==== ④ f1 manual §3 标题（F-01）====')
m1 = open(os.path.join(ROOT, 'f1', 'manual.html')).read()
m2 = open(os.path.join(ROOT, 'f1_web', 'manual.html')).read()
check('④f1/manual §3 标题=「怎么卖：只有这几种卖出」',
      '<h2>3. 怎么卖：只有这几种卖出</h2>' in m1 and '只有三种卖出' not in m1)
check('④f1_web/manual 同步', '<h2>3. 怎么卖：只有这几种卖出</h2>' in m2)
bw = os.path.join(os.path.dirname(ROOT), 'box_web')
if os.path.isdir(bw):
    bi = open(os.path.join(bw, 'index.html')).read()
    br = open(os.path.join(bw, 'README.md')).read()
    check('④box_web 旧副本退役标注在位',
          '已退役' in bi and '已退役·以仓库权威页为准' in br)

# ---------------- ⑤ f1_signal diff=0 + sha 同步 ----------------
print('==== ⑤ 引擎零改动 + sha 闸门同步 ====')
d0 = subprocess.run(['git', '-C', ROOT, 'diff', 'HEAD', '--',
                     'f1/f1_signal.py', 'engine_f1/f1_signal.py',
                     'f1/f1_datasource.py', 'engine_f1/f1_datasource.py'],
                    capture_output=True, text=True).stdout
check('⑤f1_signal/f1_datasource 本批 diff=0（不动引擎）', d0.strip() == '', f'{len(d0)} chars')
ok_sha = True
for sub in ('engine_f1', 'f1'):
    reg = json.load(open(os.path.join(ROOT, sub, 'AUTHORITY_SHA.json')))
    for fn, want in reg['files'].items():
        fp = os.path.join(ROOT, sub, fn)
        if not os.path.exists(fp):
            continue   # f1/ 布局不含 f1_backtest_v2.py（仅 engine_f1 全量），缺文件跳过
        got = hashlib.sha256(open(fp, 'rb').read()).hexdigest()
        ok_sha &= (got == want)
check('⑤AUTHORITY_SHA 登记值 == 实际文件 sha256（双布局在位文件全对表）', ok_sha)

print(f"\n==== 汇总：PASS={len(PASS)} FAIL={len(FAIL)} ====")
if FAIL:
    print('失败项：', FAIL)
    sys.exit(1)
print('ALL PASS')
