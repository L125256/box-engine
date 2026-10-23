#!/usr/bin/env python3
# refresh_cache.py — WT-C 影子双轨 · 行情缓存刷新（v4 砍新浪+预算封顶版）
#
# 修复批 KUXIN-BREAKER-20261024（用户 2026-10-24 05:27 死命令：云端任务整轮 ≤10 分钟、
# 新浪彻底砍除、禁止庸医；十席审议冻结后一次成型）：
#   ① 砍新浪（代码级移除，非注释禁用）：刷新器内全部新浪探活件/请求头常量/探针分支
#      删除；lib/kx_client.py 的 S3 切换新浪心跳及其调用点同步删除（打印改不带新浪
#      字样）。任何路径不得再触新浪行情域名。数据源单一路径=导演（kx_client）。
#   ② 探针前置（第 0 步）：导演（会话单发）/ stooq 双探针并发（≤5s），任一通=继续
#      正常刷新；全挂=立即跳过整个刷缓存，report 标【SOURCE-DOWN】+双源状态码，
#      秒级结束整轮。
#   ③ 中途快速熔断：刷新进行中连续 BOX_BREAKER_AFTER(默认12) 只票全败且错误为网络类
#      （超时/连接失败/4xx/429）→ 熔断整轮刷缓存，report 标【SOURCE-DOWN】+导演状态码
#      +已成功数；未开始的标的 cancel/skip（skipped 计数），禁止 176 只挨个退避陪跑。
#      数据类失败（empty bars 等）不计连败且打断连败序列（防误杀短历史标的）。
#   ④ 退避收敛：BACKOFF_SEQ 默认 (2,8)——32s 档删除（十席表决：全败趋势下 32s 档
#      无意义且放大耗时）。BOX_BACKOFF_SEQ env 仍可覆盖（向后兼容）。
#   ⑤ 预算封顶（双保险）：BOX_TOTAL_BUDGET（默认 180s）= 刷缓存段总预算（探针起步
#      计时），超时立即熔断整轮，report 标【BUDGET-EXCEEDED】+已成功数（与
#      SOURCE-DOWN 独立状态字，防下游误读为数据源问题）。
#   ⑥ 与 PULL-CHECK 硬闸协同：PULL-CHECK 管代码版本（云端任务清单特征闸，本文件不涉），
#      SOURCE-DOWN 管数据源（本文件 report 的 status/source_probe 字段），两开关独立回报。
#
# 时间预算表（用户死命令：云端任务整轮 ≤10 分钟）：
#   拉代码 ~1min + 刷缓存（正常 ~1min / 全败熔断 ≤3min）+ 引擎 ~2min
#   + 上传验收 ~1min ≈ 正常 5min、全败 7min < 10min 死线。
#
#   诊断注入点（全败模拟/云端 IP 诊断共用）：KX_BASE_URL / STOOQ_PROBE_URL env 覆盖
#      目标端点；BOX_BREAKER_AFTER 调熔断阈值（8/12/16 邻域）；BOX_TOTAL_BUDGET 调预算。
#   shadow_run 只读 ok/fail/cache_files/ts 四键不变（v2/v3 已核），新增键纯增补。
# v3 修复批 SOURCE-DOWN-20261024（新浪件已按①砍除，熔断/探针/退避结构承继）。
# v2 修复批 SINA429-FIX-20261024（新浪触点已删，降并发 8 / KxClient(retries=1) /
#   路径 fallback 链保留）。
# 池 = 存档面板标的（剔除稀疏标的） ∪ 清洗池 144 标的（保证权威池完整）。
# 只写 BOX_CACHE_DIR（默认 /tmp/box_cache）/*.json 与 refresh_report.json，不改其他目录。
import sys, os, json, time, logging, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

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

# —— v2 修复③：降并发（BOX_WORKERS 可配置；默认 8）——
WORKERS = int(os.environ.get('BOX_WORKERS', '8'))
# —— v3 修复③：退避收敛为两档（2,8；BOX_BACKOFF_SEQ 可覆盖）——
BACKOFF_SEQ = tuple(float(x) for x in
                    os.environ.get('BOX_BACKOFF_SEQ', '2,8').split(',') if x.strip())
if not BACKOFF_SEQ:
    BACKOFF_SEQ = (2.0, 8.0)
REFRESH_ATTEMPTS = max(1, int(os.environ.get('BOX_REFRESH_ATTEMPTS', '3')))
# —— v3 修复②：熔断阈值（连续网络类全败只数；BOX_BREAKER_AFTER 可调 8/12/16）——
BREAKER_AFTER = max(1, int(os.environ.get('BOX_BREAKER_AFTER', '12')))
# —— v4 修复⑤：刷缓存段总预算秒数（超时立即熔断整轮；BOX_TOTAL_BUDGET 可调）。
#    默认 150s：150 预算 + 在途单请求最坏 ~15s + 退避残余 ~10s ≈ 175s < 180s 判线
#    （实弹校准：180s 预算落点 196s 超 3 分钟判线，故收紧到 150s 双保险闭合）。——
TOTAL_BUDGET = float(os.environ.get('BOX_TOTAL_BUDGET', '150'))
# —— v3 修复①：诊断注入点（默认不变；全败模拟/云端 IP 诊断时 env 覆盖）——
STOOQ_PROBE_URL = os.environ.get(
    'STOOQ_PROBE_URL', 'https://stooq.com/q/l/?s=aapl.us&f=sd2t2ohlcv&h&e=csv')
KX_BASE_URL = os.environ.get('KX_BASE_URL')   # None=导演默认 https://www.kxiandaoyan.com/api

# stooq 第三通道探活 UA（仅诊断探针用；数据路径不经过它）
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# v3 熔断开关：网络类连败达标或预算超时置位；置位后未开始的 pull 直接 skip
BREAKER = threading.Event()
# v4 预算计时起点（main() 探针前置前设置，monotonic 秒）
_T0 = None


def budget_exceeded():
    """总预算是否已耗尽（T0 未设=不启用）。"""
    return _T0 is not None and (time.monotonic() - _T0) > TOTAL_BUDGET


def probe_stooq(timeout=(3, 5)):
    """stooq 第三通道探活（工单实锤用户环境 200；本沙箱不可达环境据实回报）。"""
    try:
        r = requests.get(STOOQ_PROBE_URL,
                         headers={'User-Agent': BROWSER_UA},
                         timeout=timeout)
        return {'alive': r.status_code == 200, 'status': int(r.status_code)}
    except Exception as e:  # noqa: BLE001
        return {'alive': False, 'status': None, 'error': str(e)[:80]}


def probe_director(k, symbol='AAPLUSDT', timeout=(3, 5)):
    """导演源单发探活：直接打会话 /kline（绕过 get_kline，防触发 S3 切换副作用）。"""
    try:
        r = k.session.get(f'{k.base}/kline/{symbol}',
                          params={'market': 'futures', 'period': '1d', 'limit': 50},
                          timeout=timeout)
        return {'alive': r.status_code == 200, 'status': int(r.status_code)}
    except Exception as e:  # noqa: BLE001
        return {'alive': False, 'status': None, 'error': str(e)[:80]}


def probe_all(k, timeout=(3, 5)):
    """双探针并发；返回 {'director':..,'stooq':..}。任一通=继续，全挂=SOURCE-DOWN。"""
    out = {}
    with ThreadPoolExecutor(2) as ex:
        futs = {ex.submit(probe_director, k, timeout=timeout): 'director',
                ex.submit(probe_stooq, timeout=timeout): 'stooq'}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    return out


def err_kind(e):
    """错误分类：net=网络类（超时/连接失败/4xx/429，计熔断连败）；data=数据类（不计）。"""
    if isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                      ConnectionError)):
        return 'net'
    sc = getattr(getattr(e, 'response', None), 'status_code', None)
    if sc and (400 <= sc < 500 or sc == 429):
        return 'net'
    s = str(e)
    if any(x in s for x in ('timed out', 'Timeout', 'Connection', 'refused',
                            'unreachable', '429', 'Failed to establish')):
        return 'net'
    return 'data'


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
    """单标拉取：单轮内最多 REFRESH_ATTEMPTS 次请求，失败按 BACKOFF_SEQ 退避。
    BREAKER 置位或预算耗尽后未开始的标的直接 skip。返回 (sym, bars数, 末根, err_kind)。"""
    if BREAKER.is_set() or budget_exceeded():
        return sym, 0, None, 'skip'
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
                return sym, len(bars), bars[-1]['time'], 'ok'
            last_err = RuntimeError('empty bars')
        except Exception as e:  # noqa: BLE001 - 网络/429/超时统一按退避重试
            last_err = e
        if attempt < REFRESH_ATTEMPTS - 1:
            if BREAKER.is_set() or budget_exceeded():
                return sym, 0, None, 'skip'
            wait = BACKOFF_SEQ[attempt % len(BACKOFF_SEQ)]
            log.warning('pull 重试(%d/%d) %s 退避%.0fs: %s',
                        attempt + 1, REFRESH_ATTEMPTS - 1, sym, wait,
                        str(last_err)[:120])
            time.sleep(wait)
            if BREAKER.is_set() or budget_exceeded():   # v4：退避后二次检查，压短熔断尾巴
                return sym, 0, None, 'skip'
    log.warning('pull 最终失败 %s: %s', sym, str(last_err)[:160])
    return sym, 0, None, err_kind(last_err) if last_err else 'data'


def _write_report(pool_size, ok, fail, last_bar, status, probe0, probe_end=None,
                  breaker=None, skipped=0, elapsed=None):
    """报告落盘：增补 status/skipped/breaker_after/source_probe*/breaker/
    total_budget/elapsed_sec 键（纯增补，下游只读 4 键不受影响）。"""
    _rdir = os.path.dirname(REPORT)
    if _rdir:
        os.makedirs(_rdir, exist_ok=True)   # B1：真 runner /tmp/wtc 不存在，写报告前自建
    with open(REPORT, 'w') as f:
        json.dump(dict(ts=time.strftime('%Y-%m-%d %H:%M:%S'),
                       status=status, pool=pool_size, ok=ok, fail=fail,
                       skipped=skipped,
                       cache_files=len(os.listdir(CACHE_DIR)),
                       last_bar_max=max(last_bar.values()) if last_bar else None,
                       workers=WORKERS, backoff_seq=list(BACKOFF_SEQ),
                       attempts=REFRESH_ATTEMPTS, breaker_after=BREAKER_AFTER,
                       total_budget=TOTAL_BUDGET, elapsed_sec=elapsed,
                       source_probe=probe0, source_probe_end=probe_end,
                       breaker=breaker or {'triggered': False}), f,
                  ensure_ascii=False, indent=1)


def main():
    global _T0
    _T0 = time.monotonic()   # v4：预算计时起点=探针前置前
    os.makedirs(CACHE_DIR, exist_ok=True)
    pool = build_pool()
    print(f'池: {len(pool)} 标的, 线程: {WORKERS}, 退避: {BACKOFF_SEQ}, '
          f'单标最多尝试: {REFRESH_ATTEMPTS}, 熔断阈值: {BREAKER_AFTER}, '
          f'总预算: {TOTAL_BUDGET:.0f}s', flush=True)
    # retries=1：收敛 kx_client 内部重试，单轮请求次数=REFRESH_ATTEMPTS，防双层放大
    _kw = {'base_url': KX_BASE_URL} if KX_BASE_URL else {}
    k = KxClient(retries=1, **_kw)
    # —— v3 修复①：探针前置，双探针全挂 → 立即 SOURCE-DOWN，跳过整个刷缓存 ——
    probe0 = probe_all(k)
    print('探针:', json.dumps(probe0, ensure_ascii=False), flush=True)
    if not any(p['alive'] for p in probe0.values()):
        print('【SOURCE-DOWN】双探针全挂，跳过整个刷缓存', flush=True)
        _write_report(len(pool), 0, [], {}, 'SOURCE-DOWN', probe0,
                      breaker={'triggered': False, 'reason': 'probe-all-down'},
                      elapsed=round(time.monotonic() - _T0, 2))
        print('完成: 成功0 失败0 (SOURCE-DOWN)', flush=True)
        return
    ok, fail, last_bar = 0, [], {}
    streak = 0            # 连续网络类全败计数（成功或数据类失败清零）
    breaker_info = None
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(pull, k, s): s for s in pool}
        for f in as_completed(futs):
            sym, n, lb, ek = f.result()
            if n:
                ok += 1
                last_bar[sym] = lb
                streak = 0
            elif ek == 'net':
                streak += 1
            elif ek != 'skip':
                streak = 0
            if n == 0 and ek != 'skip':
                fail.append(sym)
            # —— v4 修复⑤：预算封顶（先查预算，再查连败）——
            if breaker_info is None and budget_exceeded():
                BREAKER.set()
                for uf in futs:
                    uf.cancel()
                breaker_info = {'triggered': True, 'reason': 'budget-exceeded',
                                'budget_sec': TOTAL_BUDGET,
                                'elapsed_sec': round(time.monotonic() - _T0, 2),
                                'ok': ok, 'fail_counted': len(fail),
                                'last_err_sym': sym}
                print(f'【BUDGET-EXCEEDED】预算封顶熔断: 已用{breaker_info["elapsed_sec"]}s'
                      f'/{TOTAL_BUDGET:.0f}s, 已成功{ok}, 跳过{len(pool) - ok - len(fail)}只',
                      flush=True)
                break
            if streak >= BREAKER_AFTER:
                # —— v3 修复②：中途熔断 ——
                BREAKER.set()
                for uf in futs:
                    uf.cancel()
                breaker_info = {'triggered': True, 'consecutive_net_fails': streak,
                                'threshold': BREAKER_AFTER, 'ok': ok,
                                'fail_counted': len(fail), 'last_err_sym': sym,
                                'reason': 'net-fail-streak'}
                print(f'【SOURCE-DOWN】中途熔断: 连续{streak}只网络类全败, '
                      f'导演状态码={probe0.get("director", {}).get("status")}, '
                      f'已成功{ok}, 跳过{len(pool) - ok - len(fail)}只', flush=True)
                break
            done = ok + len(fail)
            if done % 40 == 0:
                print(f'进度 {done}/{len(pool)}', flush=True)
    skipped = len(pool) - ok - len(fail)
    print(f'完成: 成功{ok} 失败{len(fail)} 跳过{skipped} {fail[:10]}', flush=True)
    probe_end = None if breaker_info else probe_all(k)   # 轮末探针复测（诊断；熔断时省一次探测）
    status = ('SOURCE-DOWN' if (breaker_info or {}).get('reason') == 'net-fail-streak'
              else 'BUDGET-EXCEEDED' if (breaker_info or {}).get('reason') == 'budget-exceeded'
              else 'OK' if not fail else 'PARTIAL')
    _write_report(len(pool), ok, fail, last_bar, status, probe0, probe_end,
                  breaker_info, skipped, elapsed=round(time.monotonic() - _T0, 2))


if __name__ == '__main__':
    main()
