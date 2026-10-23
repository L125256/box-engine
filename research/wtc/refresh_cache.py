#!/usr/bin/env python3
# refresh_cache.py — WT-C 影子双轨 · 行情缓存刷新（v2 限流修复版）
#
# 修复批 SINA429-FIX-20261024（用户 2026-10-24 01:11 拍板「修吧」）：
#   ① 新浪触点统一带头：SINA_HEADERS（Referer+浏览器 UA）。实测带头 5/5 200、
#      裸请求 0/5 403（2026-10-24 01:19，AAPL 346.20 活数据）——反爬升级强制要求请求头。
#      探活件 probe_sina() 只测可达性，价格数据不入库（规矩第 13 条口径）。
#   ② 导演源指数退避：失败后按 BACKOFF_SEQ 2s→8s→32s 等待，单轮内最多
#      REFRESH_ATTEMPTS=3 次请求，禁连续硬打（原 3 次固定 2s 硬打疑似把导演
#      后端打进限流池）。KxClient(retries=1) 收敛客户端内部重试，防双层放大
#      （原单标最多 3×2=6 次请求 → 现最多 3 次）。
#   ③ 降并发：对外请求并发默认 32→8（BOX_WORKERS 可配置）。取值依据=对齐
#      kx_client S3 降级专用 8 线程既有工程裁决（Q2），降低 IP 级限流风险。
#   路径 fallback 链：KX_CLIENT_DIR/PANEL_FILE/BOX_POOL env > 仓库相对路径 >
#      云端 artifact/eng_wt 路径——同一份文件在仓库内与 /tmp/wtc/ 两布局皆可跑
#      （统一「同名同源」前提）。
# 池 = 存档面板标的（剔除稀疏标的） ∪ 清洗池 144 标的（保证权威池完整）。
# 只写 BOX_CACHE_DIR（默认 /tmp/box_cache）/*.json 与 refresh_report.json，不改其他目录。
import sys, os, json, time, logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
log = logging.getLogger('wtc')

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(_HERE, '..', '..'))


def _first_dir(cands):
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[-1]


def _first_file(cands):
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return cands[-1]


# 自足性 WO：KX_CLIENT_DIR env > 仓库内 lib/ > 云端 artifact kx-combo
# 判据=目录内实际存在 kx_client.py（防 /lib 等同名系统目录误命中）
_KX_DIR = _first_dir([c for c in [os.environ.get('KX_CLIENT_DIR'),
                                  os.path.join(_REPO, 'lib'),
                                  '/root/.codebuddy/artifact/kx-combo']
                      if c and os.path.isfile(os.path.join(c, 'kx_client.py'))]
                     or ['/root/.codebuddy/artifact/kx-combo'])
sys.path.insert(0, _KX_DIR)
from kx_client import KxClient  # noqa: E402

# 存档面板默认：env PANEL_FILE > 随仓快照 > 云端 artifact 副本
PANEL_FILE = os.environ.get('PANEL_FILE') or _first_file([
    os.path.join(_REPO, 'engine_snapshot', 'archive', '2026-10-10.json'),
    '/root/.codebuddy/artifact/kx-combo/archive/2026-10-10.json'])
# 清洗池默认：env BOX_POOL > 随仓快照 > 云端 /tmp/eng_wt 副本
POOL_FILE = os.environ.get('BOX_POOL') or _first_file([
    os.path.join(_REPO, 'engine_snapshot', 'cleaned_pool.json'),
    '/tmp/eng_wt/cleaned_pool.json'])
CACHE_DIR = os.environ.get('BOX_CACHE_DIR', '/tmp/box_cache')
REPORT = os.environ.get('BOX_REFRESH_REPORT', '/tmp/wtc/refresh_report.json')
EXCLUDE_SPARSE = ['BSPUSDT', 'FWDIUSDT', 'BBXUSDT', 'BITOUSDT', 'STRCUSDT']

# —— 修复③：降并发（BOX_WORKERS 可配置；默认 8，依据见文件头注释）——
WORKERS = int(os.environ.get('BOX_WORKERS', '8'))
# —— 修复②：导演源指数退避（可配置；单轮内最多 REFRESH_ATTEMPTS 次请求）——
BACKOFF_SEQ = tuple(float(x) for x in
                    os.environ.get('BOX_BACKOFF_SEQ', '2,8,32').split(',') if x.strip())
if not BACKOFF_SEQ:
    BACKOFF_SEQ = (2.0, 8.0, 32.0)
REFRESH_ATTEMPTS = max(1, int(os.environ.get('BOX_REFRESH_ATTEMPTS', '3')))

# —— 修复①：刷新器全部新浪触点统一带头（反爬升级，2026-10-24 实测）——
SINA_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://finance.sina.com.cn",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def probe_sina(symbol='gb_aapl', timeout=8):
    """新浪存活探活（强制带头）。只测可达性，返回 {'alive','status'}；价格数据一律不入库。"""
    try:
        import urllib.request
        import urllib.error
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            f'https://hq.sinajs.cn/list={symbol}', headers=dict(SINA_HEADERS))
        r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return {'alive': r.status == 200, 'status': int(r.status)}
    except Exception as e:  # noqa: BLE001 - 探活失败仅记录，不中断刷新
        code = getattr(e, 'code', None)
        return {'alive': False, 'status': int(code) if code else None,
                'error': str(e)[:80]}


def build_pool():
    pool = set()
    try:
        d = json.load(open(PANEL_FILE))
        pool |= {r['sym'] for r in d['rows']}
    except FileNotFoundError:
        # 路径不存在属预期回退场景（无随仓快照），info 级记录，仅用清洗池，不中断
        log.info('存档面板不存在(%s)，仅用清洗池回退', PANEL_FILE)
    except Exception as e:
        log.warning('存档面板读取异常(%s)，仅用清洗池回退', e)
    pool -= set(EXCLUDE_SPARSE)
    try:
        cp = json.load(open(POOL_FILE))
        pool |= {x['tkr'] for x in cp['kept']}
    except Exception as e:
        print(f'[warn] cleaned_pool 读取失败({e})', flush=True)
    return sorted(pool)


def pull(k, sym):
    """单标拉取：单轮内最多 REFRESH_ATTEMPTS 次请求，失败按 BACKOFF_SEQ 指数退避。"""
    last_err = None
    for attempt in range(REFRESH_ATTEMPTS):
        try:
            r = k.get_kline(sym, market='futures', period='1d', limit=700)
            bars = (r.get('data') or {}).get('bars') or r.get('bars') or []
            if isinstance(bars, dict):
                bars = bars.get('bars', [])
            if bars:
                tmp = os.path.join(CACHE_DIR, f'.{sym}.tmp')
                with open(tmp, 'w') as f:
                    json.dump(bars, f)
                os.replace(tmp, os.path.join(CACHE_DIR, f'{sym}.json'))
                return sym, len(bars), bars[-1]['time']
            last_err = RuntimeError('empty bars')
        except Exception as e:  # noqa: BLE001 - 网络/429/超时统一按退避重试
            last_err = e
        if attempt < REFRESH_ATTEMPTS - 1:
            wait = BACKOFF_SEQ[attempt % len(BACKOFF_SEQ)]
            log.warning('pull 重试(%d/%d) %s 退避%.0fs: %s',
                        attempt + 1, REFRESH_ATTEMPTS - 1, sym, wait,
                        str(last_err)[:120])
            time.sleep(wait)
    log.warning('pull 最终失败 %s: %s', sym, str(last_err)[:160])
    return sym, 0, None


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    pool = build_pool()
    print(f'池: {len(pool)} 标的, 线程: {WORKERS}, 退避: {BACKOFF_SEQ}, '
          f'单标最多尝试: {REFRESH_ATTEMPTS}', flush=True)
    # retries=1：收敛 kx_client 内部重试，单轮请求次数=REFRESH_ATTEMPTS，防双层放大
    k = KxClient(retries=1)
    ok, fail, last_bar = 0, [], {}
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(pull, k, s): s for s in pool}
        for f in as_completed(futs):
            sym, n, lb = f.result()
            if n:
                ok += 1
                last_bar[sym] = lb
            else:
                fail.append(sym)
            done = ok + len(fail)
            if done % 40 == 0:
                print(f'进度 {done}/{len(pool)}', flush=True)
    print(f'完成: 成功{ok} 失败{len(fail)} {fail[:10]}', flush=True)
    probe = probe_sina()   # 轮末新浪探活（带头）；纯增补键，下游 shadow_run 只读 ok/fail/cache_files/ts
    _rdir = os.path.dirname(REPORT)
    if _rdir:
        os.makedirs(_rdir, exist_ok=True)   # B1：真 runner /tmp/wtc 不存在，写报告前自建
    with open(REPORT, 'w') as f:
        json.dump(dict(ts=time.strftime('%Y-%m-%d %H:%M:%S'),
                       pool=len(pool), ok=ok, fail=fail,
                       cache_files=len(os.listdir(CACHE_DIR)),
                       last_bar_max=max(last_bar.values()) if last_bar else None,
                       workers=WORKERS, backoff_seq=list(BACKOFF_SEQ),
                       attempts=REFRESH_ATTEMPTS, source_probe=probe), f,
                  ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
