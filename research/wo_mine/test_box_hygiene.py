#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_box_hygiene.py — 箱体数据卫生三道门 + 页面口径四要素·测试席测试
================================================================================
（PLAN_FINAL_20261021 §2.1#2/#3 验收：三道门逐门正负测 + 覆盖率 79%/81% 边界两测 +
 页面四要素渲染断言 + 无字段兜底）
运行：python3 research/wo_mine/test_box_hygiene.py
"""
import datetime
import importlib.util
import json
import os
import random
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


# 载入 generate_page 模块（仓库根）
spec = importlib.util.spec_from_file_location('gp', os.path.join(ROOT, 'generate_page.py'))
gp = importlib.util.module_from_spec(spec)
sys.modules['gp'] = gp
spec.loader.exec_module(gp)
# 载入权威引擎（清洗逻辑逐字复用）
spec2 = importlib.util.spec_from_file_location('eng', os.path.join(ROOT, 'engine_snapshot', 'eng_final.py'))
eng = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(eng)

random.seed(42)


def bar(d, base=100.0):
    c = round(base * (1 + random.uniform(-0.02, 0.02)), 4)
    h = round(c * 1.01, 4)
    l = round(c * 0.99, 4)
    o = round((h + l) / 2, 4)
    return {'time': d, 'open': o, 'high': max(h, o), 'low': min(l, o), 'close': c, 'volume': 1000}


def make_cache(sym_dates, fmt='date'):
    """sym_dates: {sym: [date,...]} → 临时缓存目录。fmt: date|datetime|mixed"""
    d = tempfile.mkdtemp(prefix='hyg_')
    for i, (sym, dates) in enumerate(sym_dates.items()):
        bars = []
        for j, dt in enumerate(dates):
            f = fmt
            if fmt == 'mixed':
                f = 'date' if (j % 7 == 0) else 'datetime'   # 每 7 根混入 datetime 格式
            t = dt if f == 'date' else dt + ' 00:00:00'
            bars.append(bar(t))
        json.dump(bars, open(os.path.join(d, sym + '.json'), 'w'))
    return d


DATES = [(datetime.date(2026, 1, 1) + datetime.timedelta(days=x)).isoformat() for x in range(150)]

# ---------------- 门1+门2：混格式拒载（正：统一格式可载；负：混格式拒载 exit≠0） ----------------
print('==== 门1/门2 混格式 ====')
syms = {f'S{i:03d}': DATES for i in range(150)}
c_ok = make_cache(syms, fmt='date')          # 全 date-only（也测 datetime 统一格式可载）
try:
    kept, dropped = gp.hygienic_load_pool(c_ok, eng)
    check('门正测：150 票统一格式归一化装载成功，池=150 ≥144',
          len(kept) == 150, f'kept={len(kept)}')
    check('门1 归一化生效：全部 bar time=date-only',
          all(len(b['time']) == 10 for bars in kept.values() for b in bars))
finally:
    shutil.rmtree(c_ok)
c_dt = make_cache(syms, fmt='datetime')      # 全 datetime：归一化后应同样可载（统一 else 归一）
try:
    kept2, _ = gp.hygienic_load_pool(c_dt, eng)
    check('门正测：全 datetime 格式归一化可载（归一 date-only）',
          len(kept2) == 150 and all(len(b['time']) == 10 for bars in kept2.values() for b in bars))
finally:
    shutil.rmtree(c_dt)
c_mix = make_cache(syms, fmt='mixed')        # 混格式 → 门2 拒载 exit≠0
try:
    gp.hygienic_load_pool(c_mix, eng)
    check('门2 负测：混格式样本拒载', False, '未抛出')
except AssertionError as e:
    check('门2 负测：混格式样本拒载（AssertionError exit≠0）',
          '混格式拒载' in str(e), str(e)[:60])
finally:
    shutil.rmtree(c_mix)
# 门1 负测：不可解析时间
c_bad = make_cache({f'S{i:03d}': DATES for i in range(150)})
p = os.path.join(c_bad, 'S000.json')
d0 = json.load(open(p))
d0[5]['time'] = 'not-a-date'
json.dump(d0, open(p, 'w'))
try:
    gp.hygienic_load_pool(c_bad, eng)
    check('门1 负测：不可解析时间拒载', False, '未抛出')
except (AssertionError, ValueError):
    check('门1 负测：不可解析时间拒载', True)
finally:
    shutil.rmtree(c_bad)

# ---------------- 门3：池样本数下限 ----------------
print('==== 门3 池下限 ====')
c_small = make_cache({f'S{i:03d}': DATES for i in range(100)})   # 100 < 144
try:
    gp.hygienic_load_pool(c_small, eng)
    check('门3 负测：池 100 < 144 拒载', False, '未抛出')
except AssertionError as e:
    check('门3 负测：池 100 < 144 拒载（exit≠0）', '池样本数下限' in str(e))
finally:
    shutil.rmtree(c_small)

# ---------------- 覆盖率门：79%/81% 边界两测 + 沿用上一收盘值标注 ----------------
print('==== 覆盖率门 ≥80% ====')
def make_pool(n_sym=144, last_date_syms=None):
    """构造 pool：末日在 last_date_syms 只票有 bar，其余票止于前一日。"""
    pool = {}
    prev = DATES[-2]
    last = DATES[-1]
    last_set = set(last_date_syms or [])
    for i in range(n_sym):
        s = f'S{i:03d}'
        ds = DATES[:-1] if s not in last_set else DATES
        pool[s] = [bar(dt) for dt in ds]
    return pool


# 79% 边界：144 票中 114 票（79.17%<80%）→ 沿用上一收盘值 inherited=True
cov = 114
pool79 = make_pool(last_date_syms=[f'S{i:03d}' for i in range(cov)])
gm79 = gp.gate_meta_for(pool79)
check('覆盖率 79% 负测：闸值作废沿用上一收盘值（inherited=True）',
      gm79['inherited'] is True and gm79['data_date'] == DATES[-2]
      and gm79['latest_coverage_pct'] < 80, str(gm79['latest_coverage_pct']))
check('沿用日样本数正确记录（上一收盘值日=全池 144）',
      gm79['n_samples'] == 144 and gm79['coverage_pct'] == 100.0)
# 81% 边界：144 票中 117 票（81.25%≥80%）→ 当日闸值有效
cov = 117
pool81 = make_pool(last_date_syms=[f'S{i:03d}' for i in range(cov)])
gm81 = gp.gate_meta_for(pool81)
check('覆盖率 81% 正测：当日闸值有效（inherited=False）',
      gm81['inherited'] is False and gm81['data_date'] == DATES[-1]
      and gm81['latest_coverage_pct'] >= 80, str(gm81['latest_coverage_pct']))
check('四要素齐备：闸名/池口径/数据日期/样本数',
      all(k in gm81 for k in ('gate_name', 'pool', 'data_date', 'n_samples'))
      and '箱体牛闸' in gm81['gate_name'] and 'clean 144' in gm81['pool'])
# 全日期 <80% → 拒载
pool_none = {f'S{i:03d}': [bar(dt) for dt in DATES if (i + DATES.index(dt)) % 5 < 2]
             for i in range(144)}
try:
    gp.gate_meta_for(pool_none)
    check('覆盖率负测：无合格日期拒载', False, '未抛出')
except AssertionError as e:
    check('覆盖率负测：无合格日期拒载（exit≠0）', '覆盖率' in str(e))

# ---------------- 页面四要素渲染 + 无字段兜底（render_harness） ----------------
print('==== 页面四要素渲染 ====')
html_path = os.path.join(ROOT, 'index.html')
box_json = {
    'generated': '2026-10-21 09:05 北京时间', 'version': 'box-web-test', 'seed': 42,
    'pool': {'n': 144, 'dropped': []},
    'caliber': {'main_window': '入场日 et>=2025-06-01', 'fill': 'V2', 'trigger': 'V1'},
    'runs': {'baseline': {'label': '冻结基线', 'params': {'N': 20, 'k': 6.0, 'm': 2, 'e': 0.2},
                          'cards': [
                              {'tkr': 'AAA', 'mode': '箱体锁定', 'top': 10.0, 'bot': 9.0,
                               'age': 5, 'last': 9.1, 'pos_in_box': 0.1},
                              {'tkr': 'BBB', 'mode': '箱体锁定', 'top': 20.0, 'bot': 19.0,
                               'age': 3, 'last': 19.8, 'pos_in_box': 0.8},
                          ],
                          'recent': [], 'stats': {'total': 0, 'wins': 0, 'mean': 0},
                          'main_stats': {'n': 10, 'pf': 1.1, 'mean': 0.5, 'win_pct': 60}},
             'top1': {'label': 'Top1', 'params': {'N': 15, 'k': 7.5, 'm': 2, 'e': 0.3},
                      'cards': [], 'recent': [], 'stats': {'total': 0, 'wins': 0, 'mean': 0},
                      'main_stats': {'n': 5, 'pf': 1.2, 'mean': 0.6, 'win_pct': 55}}},
}
GM = {'gate_name': '箱体牛闸（盘中实时·箱体闸）', 'pool': 'clean 144（混格式归一清洗后口径）',
      'data_date': '2026-10-20', 'n_samples': 144, 'coverage_pct': 100.0,
      'latest_date': '2026-10-21', 'latest_coverage_pct': 55.6, 'cover_min_pct': 80,
      'inherited': True}
j1 = os.path.join(tempfile.mkdtemp(), 'with_gm.json')
d1 = dict(box_json); d1['gate_meta'] = GM
json.dump(d1, open(j1, 'w'), ensure_ascii=False)
r1 = subprocess.run(['node', os.path.join(ROOT, 'f1', 'render_harness.cjs'), html_path, j1],
                    capture_output=True, text=True, timeout=60)
o1 = json.loads(r1.stdout[r1.stdout.index('RENDER_JSON_START') + 17:])
th1 = o1['thermo']['innerHTML']
check('页面渲染零 JS 报错', r1.returncode == 0 and 'Error' not in r1.stderr, r1.stderr[:100])
check('四要素渲染在页：闸名｜池口径｜数据日期｜样本数',
      '箱体牛闸（盘中实时·箱体闸）' in th1 and 'clean 144' in th1
      and '2026-10-20' in th1 and '样本数=144' in th1)
check('覆盖率 <80% 标注：闸值作废沿用上一收盘值',
      '闸值作废沿用上一收盘值 2026-10-20' in th1, '')
check('「关+fd 激活 N 只（观察区）」形态在页（双闸分离·fd 激活独立计数）',
      '关+fd 激活 1 只（观察区）' in th1, th1[th1.find('关+fd'):th1.find('关+fd') + 30])
check('温度计 clean 口径标注', '市况温度计（clean 口径）' in th1)
check('fd 区四要素标注在页（fdgate 行）',
      '闸口径四要素' in o1.get('fdgate', {}).get('textContent', ''))
# 无字段兜底
j2 = os.path.join(tempfile.mkdtemp(), 'no_gm.json')
json.dump(box_json, open(j2, 'w'), ensure_ascii=False)
r2 = subprocess.run(['node', os.path.join(ROOT, 'f1', 'render_harness.cjs'), html_path, j2],
                    capture_output=True, text=True, timeout=60)
o2 = json.loads(r2.stdout[r2.stdout.index('RENDER_JSON_START') + 17:])
th2 = o2['thermo']['innerHTML']
check('无 gate_meta 字段兜底：样本数=— 不报错',
      r2.returncode == 0 and '样本数=—' in th2 and 'Error' not in r2.stderr)

print(f"\n==== 汇总：PASS={len(PASS)} FAIL={len(FAIL)} ====")
if FAIL:
    print('失败项：', FAIL)
    sys.exit(1)
print('ALL PASS')
