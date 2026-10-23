#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_refresh_fix.py — SINA429-FIX-20261024 修复批单测
覆盖（工单验收①）：T1 请求头注入存在性 / T2 退避逻辑（模拟 429 序列）/ T3 并发参数可配置
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


# ---------------- T1 请求头注入存在性 ----------------
def t1_headers():
    h = rc.SINA_HEADERS
    check('T1.1 SINA_HEADERS 常量存在且含 Referer',
          h.get('Referer') == 'https://finance.sina.com.cn', f"Referer={h.get('Referer')}")
    check('T1.2 SINA_HEADERS 含浏览器 UA',
          'Mozilla/5.0' in h.get('User-Agent', '') and 'Chrome/126' in h.get('User-Agent', ''))

    # kx_client.probe_sina_alive：mock requests.get 捕获实参 headers
    import kx_client
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured['url'] = url
        captured['headers'] = dict(headers or {})
        req = io.BytesIO(b'ok')

        class R:
            status_code = 200
            def __iter__(self):
                return iter([b'ok'])
        return R()

    orig_get = kx_client.requests.get
    kx_client.requests.get = fake_get
    try:
        alive = kx_client.KxClient.probe_sina_alive()
    finally:
        kx_client.requests.get = orig_get
    ck = captured.get('headers', {})
    check('T1.3 kx_client.probe_sina_alive 注入 Referer',
          ck.get('Referer') == 'https://finance.sina.com.cn', f"headers={ck}")
    check('T1.4 kx_client.probe_sina_alive 注入浏览器 UA',
          'Mozilla/5.0' in ck.get('User-Agent', ''))
    check('T1.5 probe_sina_alive 命中新浪端点', 'hq.sinajs.cn' in captured.get('url', ''))

    # refresh_cache.probe_sina：mock urlopen 捕获实参 headers
    cap2 = {}

    class FakeResp(io.BytesIO):
        status = 200
        def read(self, n=-1):
            return b'ok'

    def fake_urlopen(req, timeout=None, context=None):
        cap2['url'] = req.full_url
        cap2['headers'] = {k.lower(): v for k, v in req.header_items()}
        return FakeResp(b'ok')

    orig_open = rc.urllib.request.urlopen if hasattr(rc, 'urllib') else None
    import urllib.request as _ur
    _orig = _ur.urlopen
    _ur.urlopen = fake_urlopen
    try:
        p = rc.probe_sina('gb_aapl')
    finally:
        _ur.urlopen = _orig
    ck2 = cap2.get('headers', {})
    check('T1.6 refresh_cache.probe_sina 注入 Referer',
          ck2.get('referer') == 'https://finance.sina.com.cn', f"headers={ck2}")
    check('T1.7 refresh_cache.probe_sina 注入浏览器 UA',
          'Mozilla/5.0' in ck2.get('user-agent', ''))
    check('T1.8 probe_sina 命中新浪端点', 'hq.sinajs.cn' in cap2.get('url', ''))
    # 源码级存在性：刷新器源文件包含 SINA_HEADERS 引用（防后续裸写 requests.get）
    src = open(os.path.join(HERE, 'refresh_cache.py'), encoding='utf-8').read()
    check('T1.9 刷新器源码无裸 requests.get 直调（新浪触点全走 probe_sina 带 SINA_HEADERS）',
          'requests.get' not in src)


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
        sym, n, lb = rc.pull(k, 'AAPLUSDT')
    finally:
        rc.time.sleep = orig_sleep
    check('T2.1 429 全败：单轮请求次数 == 3（REFRESH_ATTEMPTS）',
          k.calls == 3, f'calls={k.calls}')
    check('T2.2 429 全败：退避序列 == [2.0, 8.0]（2s→8s 档；32s 为第 3 档备用）',
          sleeps == [2.0, 8.0], f'sleeps={sleeps}')
    check('T2.3 429 全败：返回失败三元组不写缓存', (sym, n, lb) == ('AAPLUSDT', 0, None))

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
        sym2, n2, lb2 = rc.pull(k2, 'NVDAUSDT')
    finally:
        rc.time.sleep = orig_sleep
        rc.CACHE_DIR = orig_cd
    check('T2.4 首败次成：请求 2 次、退避 [2.0]、成功 1 根',
          k2.calls == 2 and sleeps2 == [2.0] and n2 == 1,
          f'calls={k2.calls} sleeps={sleeps2} n={n2}')
    check('T2.5 成功路径返回末根时间', lb2 == '2026-10-23 00:00:00', f'lb={lb2}')

    # 配置放大：BOX_REFRESH_ATTEMPTS=4 时退避序列用到第 3 档 32s
    code = (
        "import sys, os\n"
        "sys.path.insert(0, %r)\n" % HERE
        + "os.environ['BOX_REFRESH_ATTEMPTS']='4'\n"
        "import refresh_cache as rc\n"
        "rc.time.sleep = lambda s: print('SLEEP', round(s), flush=True)\n"
        "class K429:\n"
        "    def get_kline(self, *a, **kw): raise ConnectionError('429')\n"
        "rc.pull(K429(), 'XUSDT')\n")
    import subprocess
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    got = [ln.split()[1] for ln in p.stdout.splitlines() if ln.startswith('SLEEP')]
    check('T2.6 attempts=4 时退避序列完整走 2→8→32 三档',
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
    t1_headers()
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
