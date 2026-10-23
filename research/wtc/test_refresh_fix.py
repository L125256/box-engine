#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_refresh_fix.py — SINA429-FIX-20261024 + KUXIN-BREAKER-20261024 修复批单测
覆盖：T1 新浪代码零残留与双探针 / T2 退避逻辑（模拟 429 序列）/ T3 并发参数可配置
纯 python3 断言，无 pytest 依赖。用法：python3 test_refresh_fix.py
"""
import inspect
import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import refresh_cache as rc  # noqa: E402

RES = []


def check(name, cond, detail=''):
    RES.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ''))


# ---------------- T1 新浪零残留 + 双探针 ----------------
RUNTIME_FILES = [
    os.path.join(HERE, 'refresh_cache.py'),
    os.path.join(HERE, '..', '..', 'lib', 'kx_client.py'),
]


def t1_no_sina():
    srcs = {p: open(p, encoding='utf-8').read() for p in RUNTIME_FILES}
    for p, src in srcs.items():
        base = os.path.basename(p)
        check(f'T1.1 {base} 零新浪触点（hq.sinajs 0 命中）',
              'hq.sinajs' not in src, f'文件={base}')
    rc_src = srcs[RUNTIME_FILES[0]]
    kx_src = srcs[RUNTIME_FILES[1]]
    check('T1.2 refresh_cache 无新浪探活/请求头/探针端点标识符（代码级移除）',
          all(x not in rc_src for x in
              ('probe_sina', 'SINA_HEADERS', 'SINA_PROBE_URL', "'sina'", '"sina"')))
    check('T1.3 kx_client 无新浪心跳件（probe_sina_alive 已删）',
          'probe_sina_alive' not in kx_src and 'sinajs' not in kx_src)
    check('T1.4 refresh_cache.probe_stooq 存在且带浏览器 UA',
          'User-Agent' in inspect.getsource(rc.probe_stooq)
          and 'Mozilla/5.0' in rc.BROWSER_UA)

    # probe_stooq：200→alive / 异常→dead（mock requests.get）
    def fake_ok(url, **kw):
        class R: status_code = 200
        return R()
    orig = rc.requests.get
    rc.requests.get = fake_ok
    try:
        p_ok = rc.probe_stooq()
    finally:
        rc.requests.get = orig
    check('T1.5 probe_stooq 200→alive', p_ok == {'alive': True, 'status': 200}, f'{p_ok}')

    # probe_director：异常→dead 且不触 get_kline
    class FakeK:
        class session:
            @staticmethod
            def get(url, params=None, timeout=None):
                raise ConnectionError('refused')
        base = 'https://x/api'
    p_d = rc.probe_director(FakeK())
    check('T1.6 probe_director 异常→dead 且不触 get_kline',
          p_d['alive'] is False and p_d['status'] is None, f'{p_d}')

    # probe_all：双探针聚合（director+stooq），无 sina 键
    def fake_refused(url, **kw):
        raise ConnectionError('refused')
    rc.requests.get = fake_refused
    try:
        pa = rc.probe_all(FakeK())
    finally:
        rc.requests.get = orig
    check('T1.7 probe_all 双探针聚合（director/stooq，无 sina 键）+全挂→全 dead',
          set(pa) == {'director', 'stooq'}
          and not any(x['alive'] for x in pa.values()), f'{pa}')
    # 源码级：requests.get 直调仅存在于探针函数内
    ps, pq = inspect.getsource(rc.probe_stooq), inspect.getsource(rc.probe_director)
    others = rc_src.replace(ps, '').replace(pq, '')
    check('T1.8 requests.get 直调仅存在于探针内（数据路径走 kx_client 单一路径）',
          'requests.get' not in others, f'探针外直调={"requests.get" in others}')


# ---------------- T2 退避逻辑（模拟 429 序列） ----------------
def t2_backoff():
    class Always429:
        """模拟导演源连续 429：每次调用抛 ConnectionError(429)。"""
        def __init__(self):
            self.calls = 0

        def get_kline(self, *a, **kw):
            self.calls += 1
            raise ConnectionError('API 请求最终失败: 429 Too Many Requests')

    sleeps = []
    orig_sleep = rc.time.sleep
    rc.time.sleep = lambda s: sleeps.append(float(s))
    try:
        k = Always429()
        sym, n, lb, ek = rc.pull(k, 'AAPLUSDT')
    finally:
        rc.time.sleep = orig_sleep
    check('T2.1 429 全败：单轮请求次数 == 3（REFRESH_ATTEMPTS）',
          k.calls == 3, f'calls={k.calls}')
    check('T2.2 429 全败：退避序列 == [2.0, 8.0]（v3 默认两档）',
          sleeps == [2.0, 8.0], f'sleeps={sleeps}')
    check('T2.3 429 全败：返回失败四元组且错误分类=net，不写缓存',
          (sym, n, lb) == ('AAPLUSDT', 0, None) and ek == 'net', f'ek={ek}')

    # 第 2 次成功：退避只发生 1 次
    class Retry2Ok:
        def __init__(self):
            self.calls = 0

        def get_kline(self, *a, **kw):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError('429')
            return {'bars': [{'time': '2026-10-23 00:00:00', 'open': 1, 'high': 2,
                              'low': 0.5, 'close': 1.5, 'volume': 9}]}
    sleeps2 = []
    rc.time.sleep = lambda s: sleeps2.append(float(s))
    tmpdir = '/tmp/test_refresh_fix_cache'
    os.makedirs(tmpdir, exist_ok=True)
    orig_cd = rc.CACHE_DIR
    rc.CACHE_DIR = tmpdir
    try:
        k2 = Retry2Ok()
        sym2, n2, lb2, ek2 = rc.pull(k2, 'NVDAUSDT')
    finally:
        rc.time.sleep = orig_sleep
        rc.CACHE_DIR = orig_cd
    check('T2.4 首败次成：请求 2 次、退避 [2.0]、成功 1 根',
          k2.calls == 2 and sleeps2 == [2.0] and n2 == 1,
          f'calls={k2.calls} sleeps={sleeps2} n={n2}')
    check('T2.5 成功路径返回末根时间且分类=ok',
          lb2 == '2026-10-23 00:00:00' and ek2 == 'ok', f'lb={lb2} ek={ek2}')

    # 配置放大：BOX_REFRESH_ATTEMPTS=4 + BOX_BACKOFF_SEQ=2,8,32（env 覆盖）时退避用第 3 档
    code = (
        "import sys, os\n"
        "sys.path.insert(0, %r)\n" % HERE
        + "os.environ['BOX_REFRESH_ATTEMPTS']='4'\n"
        "os.environ['BOX_BACKOFF_SEQ']='2,8,32'\n"
        "import refresh_cache as rc\n"
        "rc.time.sleep = lambda s: print('SLEEP', round(s), flush=True)\n"
        "class K429:\n"
        "    def get_kline(self, *a, **kw): raise ConnectionError('429')\n"
        "rc.pull(K429(), 'XUSDT')\n")
    import subprocess
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    got = [ln.split()[1] for ln in p.stdout.splitlines() if ln.startswith('SLEEP')]
    check('T2.6 attempts=4 + env 三档时退避完整走 2→8→32（向后兼容）',
          got == ['2', '8', '32'], f'sleeps={got}')
    src = open(os.path.join(HERE, 'refresh_cache.py'), encoding='utf-8').read()
    check('T2.7 无固定 2s 硬打残留（旧版 time.sleep(2) 已移除）', 'time.sleep(2)' not in src)


# ---------------- T3 并发参数可配置 ----------------
def t3_workers():
    check('T3.1 默认并发 == 8（降并发 32→8）', rc.WORKERS == 8, f'WORKERS={rc.WORKERS}')
    import subprocess
    code = ("import sys; sys.path.insert(0, %r); import refresh_cache as rc; print(rc.WORKERS)" % HERE)
    for env_val, expect in (('5', 5), ('16', 16)):
        env = dict(os.environ, BOX_WORKERS=env_val)
        p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env)
        got = int(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else -1
        check(f'T3.{2 + ("16" == env_val)} BOX_WORKERS={env_val} 生效', got == expect, f'got={got}')
    # 池构建不受 env 影响（回归护栏）
    pool = rc.build_pool()
    check('T3.4 build_pool 池=176（与 10-22 基线一致）', len(pool) == 176, f'pool={len(pool)}')
    check('T3.5 稀疏标的剔除生效', not (set(pool) & set(rc.EXCLUDE_SPARSE)))


def main():
    t1_no_sina()
    t2_backoff()
    t3_workers()
    n_pass = sum(1 for _, ok, _ in RES if ok)
    print(f"\n==== 单测汇总: {n_pass}/{len(RES)} PASS ====")
    with open(os.path.join(HERE, 'test_refresh_fix_result.json'), 'w') as fj:
        json.dump({'n': len(RES), 'n_pass': n_pass,
                   'cases': [{'name': n, 'pass': ok, 'detail': d} for n, ok, d in RES]},
                  ensure_ascii=False, indent=1, fp=fj)
    return 0 if n_pass == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
