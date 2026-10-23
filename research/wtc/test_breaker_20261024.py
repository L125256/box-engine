#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_breaker_20261024.py — SOURCE-DOWN-20261024 快速熔断批单测（v4 双探针+预算封顶版）
覆盖（工单验收⑥）：T1 双探针逻辑 / T2 熔断计数器与阈值邻域(8/12/16) /
T3 与 PULL-CHECK 硬闸协同（report 字段独立回报）/ T4 预算封顶 /
T5 运行链新浪零残留。纯 python3 断言，无 pytest。
用法：python3 test_breaker_20261024.py
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import refresh_cache as rc  # noqa: E402

RES = []


def check(name, cond, detail=''):
    RES.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ''))


# ---------------- T1 双探针逻辑 ----------------
def t1_probes():
    # T1.1 probe_stooq 200 → alive；带 UA
    cap = {}
    def fake_get(url, headers=None, timeout=None):
        cap['url'], cap['headers'] = url, dict(headers or {})
        class R: status_code = 200
        return R()
    orig = rc.requests.get
    rc.requests.get = fake_get
    try:
        p = rc.probe_stooq()
    finally:
        rc.requests.get = orig
    check('T1.1 probe_stooq 200→alive 且带浏览器 UA',
          p['alive'] and 'Mozilla/5.0' in cap['headers'].get('User-Agent', ''),
          f"status={p.get('status')}")

    class FakeK:
        class session:
            @staticmethod
            def get(url, params=None, timeout=None):
                raise ConnectionError('refused')
        base = 'https://x/api'
    p_d = rc.probe_director(FakeK())
    check('T1.2 probe_director 异常→dead 且不触 get_kline',
          p_d['alive'] is False and p_d['status'] is None, f'{p_d}')
    # T1.3 probe_all 双源并发聚合 + 全挂判定（无 sina 键）
    def fake_get2(url, headers=None, timeout=None):
        raise ConnectionError('refused')
    rc.requests.get = fake_get2
    try:
        pa = rc.probe_all(FakeK())
    finally:
        rc.requests.get = orig
    check('T1.3 probe_all 双探针全挂→全 dead（SOURCE-DOWN 判定输入，无 sina 键）',
          set(pa) == {'director', 'stooq'}
          and not any(x['alive'] for x in pa.values()), f'{pa}')


# ---------------- T2 熔断计数器 ----------------
def t2_breaker():
    # err_kind 分类
    check('T2.1 err_kind: ConnectionError→net',
          rc.err_kind(ConnectionError('refused')) == 'net')
    check('T2.2 err_kind: Timeout→net',
          rc.err_kind(TimeoutError('timed out')) == 'net'
          and rc.err_kind(rc.requests.exceptions.Timeout('t')) == 'net')
    check('T2.3 err_kind: HTTP 429/4xx→net',
          rc.err_kind(rc.requests.exceptions.HTTPError(response=type('R', (), {'status_code': 429}))) == 'net')
    check('T2.4 err_kind: empty bars（RuntimeError）→data（不计连败）',
          rc.err_kind(RuntimeError('empty bars')) == 'data')

    # 子进程整轮熔断：20 只票全 net 失败、阈值 8 → 熔断 + skipped>0 + status=SOURCE-DOWN
    runner = r'''
import sys, os, json, time
sys.path.insert(0, HERE)
import refresh_cache as rc
from concurrent.futures import ThreadPoolExecutor

PROBE = {"director": {"alive": True, "status": 200},
         "stooq": {"alive": False, "status": None}}
rc.probe_all = lambda k, timeout=(3, 5): json.loads(json.dumps(PROBE))
rc.CACHE_DIR = '/tmp/test_breaker_cache'
os.makedirs(rc.CACHE_DIR, exist_ok=True)
rc.REPORT = '/tmp/test_breaker_cache/report.json'

class FakeK:
    base = 'https://x/api'
    class session:
        @staticmethod
        def get(*a, **kw): raise ConnectionError('refused')

MODE = os.environ.get('BREAKER_TEST_MODE', 'net')
_ctr = {'i': 0}

def fake_pull(k, sym):
    if rc.BREAKER.is_set():
        return sym, 0, None, 'skip'
    _ctr['i'] += 1
    if MODE == 'net':
        return sym, 0, None, 'net'
    if MODE == 'mix':          # 每 5 只插入 1 只数据类失败，workers=1 完成序确定：
        return sym, 0, None, 'data' if _ctr['i'] % 5 == 0 else 'net'   # 连败至多 4 < 阈值
    return sym, 700, '2026-10-23 00:00:00', 'ok'

rc.pull = fake_pull
t0 = time.time()
rc.main()
print('ELAPSED', round(time.time() - t0, 2))
'''
    runner = runner.replace('HERE', repr(HERE))
    tmp = '/tmp/test_breaker_runner.py'
    with open(tmp, 'w') as f:
        f.write(runner)

    for thresh, workers in ((8, '4'), (12, '4'), (16, '4')):
        env = dict(os.environ, BOX_BREAKER_AFTER=str(thresh), BREAKER_TEST_MODE='net',
                   BOX_WORKERS=workers)
        p = subprocess.run([sys.executable, tmp], capture_output=True, text=True, env=env,
                           timeout=120)
        r = json.load(open('/tmp/test_breaker_cache/report.json'))
        trig = r['breaker'].get('triggered')
        check(f'T2.5 阈值={thresh}: 全 net 失败恰在阈值熔断（邻域 8/12/16）',
              p.returncode == 0 and trig and r['status'] == 'SOURCE-DOWN'
              and r['breaker']['threshold'] == thresh
              and r['breaker']['consecutive_net_fails'] == thresh
              and r['skipped'] > 0,
              f"ok={r['ok']} skipped={r['skipped']} streak={r['breaker']['consecutive_net_fails']}")

    env = dict(os.environ, BOX_BREAKER_AFTER='8', BREAKER_TEST_MODE='mix', BOX_WORKERS='1')
    p = subprocess.run([sys.executable, tmp], capture_output=True, text=True, env=env,
                       timeout=120)
    r = json.load(open('/tmp/test_breaker_cache/report.json'))
    check('T2.6 数据类失败打断连败：mix 模式（workers=1 序确定，连败至多 4）不熔断',
          not r['breaker'].get('triggered') and r['status'] == 'PARTIAL'
          and r['ok'] == 0, f"status={r['status']} breaker={r['breaker']}")

    env = dict(os.environ, BOX_BREAKER_AFTER='8', BREAKER_TEST_MODE='ok')
    p = subprocess.run([sys.executable, tmp], capture_output=True, text=True, env=env,
                       timeout=120)
    r = json.load(open('/tmp/test_breaker_cache/report.json'))
    check('T2.7 全成功轮：status=OK 且无熔断、无 skipped',
          r['status'] == 'OK' and r['ok'] == r['pool'] and r['skipped'] == 0
          and not r['breaker'].get('triggered'), f"ok={r['ok']}/{r['pool']}")


# ---------------- T3 与 PULL-CHECK 硬闸协同 + report 契约 ----------------
def t3_gate():
    # report 契约：shadow_run 只读 4 键 + 新增键独立回报
    r = json.load(open('/tmp/test_breaker_cache/report.json'))
    check('T3.1 report 含 shadow_run 必需 4 键（ok/fail/cache_files/ts）',
          all(k in r for k in ('ok', 'fail', 'cache_files', 'ts')))
    src = open(os.path.join(HERE, 'refresh_cache.py'), encoding='utf-8').read()
    code_hits = [ln for ln in src.splitlines()
                 if 'PULL-CHECK' in ln and not ln.lstrip().startswith('#')]
    check('T3.2 SOURCE-DOWN 管数据源（status/source_probe）与 PULL-CHECK 管代码版本互不耦合'
          '（PULL-CHECK 仅存在于头注释说明，代码逻辑零引用，两开关独立回报）',
          not code_hits and 'status' in r and 'source_probe' in r,
          f'代码级引用行={len(code_hits)}')
    check('T3.3 breaker/skipped/breaker_after/total_budget/elapsed_sec 增补键在位',
          all(k in r for k in ('breaker', 'skipped', 'breaker_after',
                               'total_budget', 'elapsed_sec')))

    # 探针全挂路径（子进程整轮）：立即 SOURCE-DOWN、ok=0、fail=[]、不写任何缓存
    runner2 = r'''
import sys, os, json, time
sys.path.insert(0, HERE)
import refresh_cache as rc
PROBE = {"director": {"alive": False, "status": None, "error": "refused"},
         "stooq": {"alive": False, "status": None, "error": "refused"}}
rc.probe_all = lambda k, timeout=(3, 5): json.loads(json.dumps(PROBE))
rc.build_pool = lambda: ['AAAUSDT', 'BBBUSDT']
rc.CACHE_DIR = '/tmp/test_breaker_cache2'
os.makedirs(rc.CACHE_DIR, exist_ok=True)
rc.REPORT = '/tmp/test_breaker_cache2/report.json'
t0 = time.time()
rc.main()
print('ELAPSED', round(time.time() - t0, 2))
'''
    runner2 = runner2.replace('HERE', repr(HERE))
    tmp2 = '/tmp/test_breaker_runner2.py'
    with open(tmp2, 'w') as f:
        f.write(runner2)
    p = subprocess.run([sys.executable, tmp2], capture_output=True, text=True, timeout=60)
    r = json.load(open('/tmp/test_breaker_cache2/report.json'))
    elapsed = float([ln.split()[1] for ln in p.stdout.splitlines()
                     if ln.startswith('ELAPSED')][0])
    check('T3.4 探针全挂：立即 SOURCE-DOWN（<5s），ok=0 fail=[] 缓存零写入',
          p.returncode == 0 and r['status'] == 'SOURCE-DOWN' and r['ok'] == 0
          and r['fail'] == [] and elapsed < 5
          and r['breaker']['reason'] == 'probe-all-down'
          and len(os.listdir('/tmp/test_breaker_cache2')) == 1,
          f'elapsed={elapsed}s files={os.listdir("/tmp/test_breaker_cache2")}')


# ---------------- T4 预算封顶（BOX_TOTAL_BUDGET） ----------------
def t4_budget():
    runner = r'''
import sys, os, json, time
sys.path.insert(0, HERE)
import refresh_cache as rc
PROBE = {"director": {"alive": True, "status": 200},
         "stooq": {"alive": False, "status": None}}
rc.probe_all = lambda k, timeout=(3, 5): json.loads(json.dumps(PROBE))
rc.CACHE_DIR = '/tmp/test_budget_cache'
os.makedirs(rc.CACHE_DIR, exist_ok=True)
rc.REPORT = '/tmp/test_budget_cache/report.json'

def slow_pull(k, sym):
    if rc.BREAKER.is_set() or rc.budget_exceeded():
        return sym, 0, None, 'skip'
    time.sleep(0.4)   # 单标 0.4s：预算 1s 内约完成 2-3 只后超时
    return sym, 700, '2026-10-23 00:00:00', 'ok'

rc.pull = slow_pull
rc.main()
'''
    runner = runner.replace('HERE', repr(HERE))
    tmp = '/tmp/test_budget_runner.py'
    with open(tmp, 'w') as f:
        f.write(runner)
    env = dict(os.environ, BOX_TOTAL_BUDGET='1', BOX_WORKERS='1')
    p = subprocess.run([sys.executable, tmp], capture_output=True, text=True, env=env,
                       timeout=60)
    r = json.load(open('/tmp/test_budget_cache/report.json'))
    check('T4.1 预算 1s：超时立即熔断，status=BUDGET-EXCEEDED、reason=budget-exceeded、'
          'elapsed>1s 且 <20s（未经 180s 陪跑）',
          p.returncode == 0 and r['status'] == 'BUDGET-EXCEEDED'
          and r['breaker'].get('reason') == 'budget-exceeded'
          and r['breaker'].get('elapsed_sec', 0) > 1
          and r['elapsed_sec'] < 20 and r['skipped'] > 0,
          f"elapsed={r['elapsed_sec']} ok={r['ok']} skipped={r['skipped']}")

    # 预算默认值与不误触发
    import re
    src = open(os.path.join(HERE, 'refresh_cache.py'), encoding='utf-8').read()
    m = re.search(r"BOX_TOTAL_BUDGET', '(\d+)'", src)
    check('T4.2 预算默认 150s（150+在途~15s+退避残余~10s < 180s 判线；BOX_TOTAL_BUDGET env 可调）',
          m and m.group(1) == '150' and rc.TOTAL_BUDGET == 150.0,
          f"default={m.group(1) if m else None}")
    check('T4.3 budget_exceeded 未启用（T0 未设）→False',
          rc.budget_exceeded() is False)


# ---------------- T5 运行链新浪零残留 ----------------
def t5_no_sina():
    root = os.path.join(HERE, '..', '..')
    runtime = [
        os.path.join(HERE, 'refresh_cache.py'),
        os.path.join(HERE, 'shadow_run.py'),
        os.path.join(root, 'lib', 'kx_client.py'),
        os.path.join(root, 'f1', 'f1_signal.py'),
        os.path.join(root, 'f1', 'f1_datasource.py'),
        os.path.join(root, 'engine_f1', 'f1_signal.py'),
        os.path.join(root, 'engine_f1', 'f1_datasource.py'),
        os.path.join(root, 'generate_page.py'),
    ]
    bad = []
    for p in runtime:
        if os.path.isfile(p) and 'hq.sinajs' in open(p, encoding='utf-8').read():
            bad.append(os.path.relpath(p, root))
    check('T5.1 运行链代码集 grep hq.sinajs == 0 命中',
          not bad, f'命中文件={bad}')


def main():
    t1_probes()
    t2_breaker()
    t3_gate()
    t4_budget()
    t5_no_sina()
    n_pass = sum(1 for _, ok, _ in RES if ok)
    print(f"\n==== 单测汇总: {n_pass}/{len(RES)} PASS ====")
    with open(os.path.join(HERE, 'test_breaker_result.json'), 'w') as fj:
        json.dump({'n': len(RES), 'n_pass': n_pass,
                   'cases': [{'name': n, 'pass': ok, 'detail': d} for n, ok, d in RES]},
                  ensure_ascii=False, indent=1, fp=fj)
    return 0 if n_pass == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
