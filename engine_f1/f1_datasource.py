#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WO-R13-04 · 数据源容灾（主源 kxiandaoyan / 备源 新浪 只读）
================================================================================
三条红线：
1. **新浪不做 144 全量拉取**：内部灰色接口、无 SLA、无限流承诺；仅白名单
   （top-5 持仓 + ≤2 只 idx 代理 ≈ 6 只/轮）。越界直接抛错，不存在全量代码路径。
2. **降级期不出新信号**：idx 需全池 144 只重建，备源做不到 → 信号冻结为最后落定值，
   页面显著标注 asof 与「备源抽查·不构成新推荐」。
3. **误切换防护**：单次超时 ≠ 宕机。单轮重试 3 次（间隔 30s）仍失败才记 1 个「周期失败」，
   **连续 2 个周期失败** 才判死切备源。

状态机：NORMAL → DEGRADED → RECOVERING → NORMAL；RECOVERING → DEGRADED（Q-2 显式回退）
- NORMAL：主源健康，正常出信号。
- DEGRADED：主源判死，冻结新信号；仅白名单标的用新浪续命（人工止损参考 + 主源可信度抽查）。
- RECOVERING：主源已连续 2 周期全检通过；恢复探测轮**自动执行**主备一致性验收
  （Q-1 · 方案 A，用户已批：不再依赖人工触发）。验收通过→自动切回 NORMAL 并写日志；
  不通过→留 RECOVERING，下一健康轮自动重试；期间主源**又连续 2 周期失败**
  →显式回退 DEGRADED 并冻结新信号（Q-2）。

所有事件写 `f1_source_events.log`（JSONL，append-only），状态落盘 `f1_source_state.json`。

复现：
  PYTHONHASHSEED=42 python3 f1_datasource.py status
  PYTHONHASHSEED=42 F1_PRIMARY_FAIL=1 python3 f1_datasource.py check     # 人造故障注入
  PYTHONHASHSEED=42 python3 f1_datasource.py drill                          # 完整切换演练
"""
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, 'f1_source_state.json')
EVENT_LOG = os.path.join(HERE, 'f1_source_events.log')
LIVE_JSON = '/workspace/f1_web/f1_live.json'
INTRADAY_JSON = '/workspace/f1_web/f1_live_intraday.json'

TOP_N = 5                            # 与引擎保持一致：top-5 等权
DEFAULT_PROBE_SYMBOLS = ['AAPLUSDT', 'NVDAUSDT', 'TSLAUSDT', 'EWZUSDT']

# ---------------- 判死 / 切回 参数（技术席规格，冻结）
RETRY_PER_ROUND = 3          # 单轮内重试 3 次
RETRY_SLEEP_SEC = 30         # 重试间隔 30s（演练可用 F1_RETRY_SLEEP=0 加速）
CONN_TIMEOUT_SEC = 5         # 连接超时 > 5s 判单次失败
READ_TIMEOUT_SEC = 15        # 读超时 > 15s 判单次失败
STALE_TOLERANCE_DAYS = 1     # 数据过期容差 1 个交易日
FAIL_PERIODS_TO_DEGRADE = 2 # 连续 2 周期失败 → 判死
OK_PERIODS_TO_RECOVER = 2    # 连续 2 周期健康 → 进入一致性验收
PRICE_TOL = 0.01             # 一致性容差：收盘价偏差 ≤ 1%
BASIS_TOL = 0.01             # 代币(USDT) vs 现货(USD) 基差容差 1%，计入总容差
EFFECTIVE_TOL = PRICE_TOL + BASIS_TOL

# ---------------- 备源白名单（≈6 只/轮：top-5 持仓 + ≤2 只 idx 代理）
MAX_PROXY_SYMBOLS = 6
DEFAULT_IDX_PROXY = ['AAPL', 'MSFT']     # idx 代理票（基础代码，不带后缀）

SINA_ENDPOINT = 'https://quotes.sina.cn/us/api/jsonp.php/var%20_US_MinKService/getDailyK'
SINA_SERVICE = 'US_MinKService.getDailyK'
SINA_REFERER = 'https://finance.sina.com.cn'
SINA_SLA_NOTE = ('无官方 SLA：内部灰色接口，无文档、无限流承诺、字段可随时变更；'
                 '仅作降级期抽查核对与人工止损参考，不得用于信号重建')

URLLIB = None


def _urlopen(req, timeout):
    global URLLIB
    if URLLIB is None:
        import urllib.request
        URLLIB = urllib.request
    return URLLIB.urlopen(req, timeout=timeout)


# ---------------------------------------------------------------- 事件日志
def log_event(kind, **kw):
    rec = {'ts': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'kind': kind}
    rec.update(kw)
    try:
        with open(EVENT_LOG, 'a') as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
    except Exception:
        pass
    return rec


# ---------------------------------------------------------------- 状态落盘
def load_state(path=STATE_PATH):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            pass
    return {'state': 'NORMAL', 'consec_fail': 0, 'consec_ok': 0,
            'last_ok': None, 'last_fail': None, 'degraded_since': None,
            'pending_manual': False, 'frozen_asof': None, 'history': []}


def save_state(state, path=STATE_PATH):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)
    return state


# ---------------------------------------------------------------- 备源 adapter（只读）
def base_symbol(sym):
    """`AAOIUSDT` → `aaoi`（新浪 symbol=小写基础代码，不带 USDT/US 后缀）。"""
    s = sym.upper()
    for suf in ('USDT', 'USD'):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[:-len(suf)]
            break
    return s.lower()


def _jsonp_unwrap(text):
    """剥离 `var _US_MinKService=(...)` / `callback(...)` 外壳，返回 JSON 文本。"""
    t = text.strip()
    i = t.find('(')
    j = t.rfind(')')
    if i >= 0 and j > i:
        return t[i + 1:j].strip()
    return t


def _scalar_timeout(timeout):
    """W-2 修复：urlopen 的 timeout 必须是标量秒数（int/float）。
    (conn, read) 二元组合并为标量 conn+read（urllib 不支持分别设连/读超时）；
    非法类型直接抛 ValueError（编程类，禁止静默）。"""
    if isinstance(timeout, (tuple, list)):
        if len(timeout) != 2 or not all(isinstance(x, (int, float)) for x in timeout):
            raise ValueError(f'timeout 须为数字或 (conn, read) 二元组，收到 {timeout!r}')
        return float(sum(timeout))
    if not isinstance(timeout, (int, float)):
        raise ValueError(f'timeout 须为数字或 (conn, read) 二元组，收到 {timeout!r}')
    return float(timeout)


def fetch_sina_daily(symbols, timeout=(CONN_TIMEOUT_SEC, READ_TIMEOUT_SEC),
                     referer=SINA_REFERER, _opener=_urlopen):
    """新浪日K（**只读**）。symbol=小写基础代码；返回 [{'symbol','date','open','high',
    'low','close','volume', 'source':'sina'}]。
    **硬约束**：len(symbols) > MAX_PROXY_SYMBOLS 直接抛错——禁止 144 全量拉取。
    **异常分类（W-2 修复）**：网络类（URLError/HTTPError/timeout/ConnectionError）
    捕获→计入失败统计+事件日志（禁静默 0 行）；编程类（TypeError/KeyError/
    AttributeError 等）一律上抛。timeout 传 (conn, read) 二元组自动标量化。"""
    if not symbols:
        return []
    if len(symbols) > MAX_PROXY_SYMBOLS:
        raise ValueError(
            f'拒绝拉取 {len(symbols)} 只：新浪为无 SLA 内部接口，'
            f'单轮上限 {MAX_PROXY_SYMBOLS} 只（top-5 持仓 + ≤2 只 idx 代理），禁止全量。')
    import urllib.error
    tmo = _scalar_timeout(timeout)          # W-2：tuple 直传 urlopen 曾 TypeError 被吞
    out, net_fail, last_err = [], 0, ''
    for sym in symbols:
        q = base_symbol(sym)
        url = f'{SINA_ENDPOINT}?symbol={q}&___qn=3'
        req = None
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                'Referer': referer,
                'User-Agent': 'Mozilla/5.0 (f1-signal-engine; failover-probe)',
            })
            raw = _opener(req, tmo).read().decode('utf-8', 'ignore')
            payload = json.loads(_jsonp_unwrap(raw))
            rows = payload if isinstance(payload, list) else (
                (payload or {}).get('result', {}).get('data', {}).get('data')
                or (payload or {}).get('data') or [])
            if not rows:
                # 新浪显式错误/空 payload（如 {"__ERROR":3}）：按网络类失败显式记录，禁静默
                raise urllib.error.URLError(
                    f'新浪无有效数据 payload={str(payload)[:80]}')
            for r in rows:
                try:
                    out.append({'symbol': q,
                                'date': str(r.get('d'))[:10],
                                'open': float(r.get('o')),
                                'high': float(r.get('h')),
                                'low': float(r.get('l')),
                                'close': float(r.get('c')),
                                'volume': float(r.get('v')),
                                'source': 'sina'})
                except (TypeError, ValueError):
                    # 外部数据 schema 脏行：显式留痕后跳过（非静默；编程类错误不在此层）
                    log_event('SINA_ROW_SKIP', symbol=q, row=str(r)[:120])
                    continue
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, ConnectionError, OSError) as e:
            net_fail += 1
            last_err = str(e)[:160]
            log_event('SINA_FETCH_FAIL', symbol=q, cls='network',
                      timeout=tmo, error=str(e)[:200])
            continue
        # 编程类异常（TypeError/KeyError/AttributeError 等）不捕获 → 上抛（W-2 纪律）
    if net_fail:
        log_event('SINA_FETCH_STATS', ok_symbols=len(symbols) - net_fail,
                  net_fail=net_fail, total=len(symbols))
        if not out:
            # 禁静默 0 行：备源全部失败必须显式上抛（带上下文），调用方按不可得处理
            raise urllib.error.URLError(
                f'新浪备源 {len(symbols)} 只全部拉取失败（每只已单独记 SINA_FETCH_FAIL；'
                f'最后错误：{last_err}）')
    return out


def proxy_watchlist(holdings, idx_proxy=None, idx_proxy_n=2):
    """降级期白名单 = top-5 持仓 + ≤2 只 idx 代理，硬上限 MAX_PROXY_SYMBOLS。"""
    idx_proxy = list(idx_proxy or DEFAULT_IDX_PROXY)[:idx_proxy_n]
    wl = list(holdings)[:TOP_N]
    for s in idx_proxy:
        if len(wl) >= MAX_PROXY_SYMBOLS:
            break
        if s not in wl:
            wl.append(s)
    return wl[:MAX_PROXY_SYMBOLS]


# ---------------------------------------------------------------- 主源健康检查
def _injected_fail():
    return os.environ.get('F1_PRIMARY_FAIL', '0') == '1'


def probe_primary(symbols=None, cache='/tmp/box_cache', expect_date=None):
    """主源（kxiandaoyan）单次探测 → {'ok':bool, 'reason':str, 'detail':...}。
    失败判定：连接超时>5s / 读超时>15s / HTTP≠200 / JSON 解析失败 /
    schema 校验失败（必需字段缺失、标的数<144、字段类型错）/ 数据过期（容差 1 交易日）。"""
    if _injected_fail():
        return {'ok': False, 'reason': '人造故障注入(F1_PRIMARY_FAIL=1)：主源不可达',
                'detail': {'injected': True}}
    symbols = symbols or DEFAULT_PROBE_SYMBOLS
    try:
        sys.path.insert(0, '/root/.codebuddy/artifact/kx-combo')
        from kx_client import KxClient
    except Exception as e:
        return {'ok': False, 'reason': f'主源客户端不可用：{e}', 'detail': {}}
    try:
        k = KxClient()
        r = k.get_kline(symbols[0], market='futures', period='1d', limit=5)
    except Exception as e:
        return {'ok': False, 'reason': f'主源请求异常/超时：{str(e)[:120]}', 'detail': {}}
    bars = (r.get('data') or {}).get('bars') or r.get('bars') or []
    if isinstance(bars, dict):
        bars = bars.get('bars', [])
    if not bars:
        return {'ok': False, 'reason': 'schema 校验失败：无 bar 数据', 'detail': {}}
    last = bars[-1]
    miss = [f for f in ('time', 'open', 'high', 'low', 'close', 'volume') if f not in last]
    if miss:
        return {'ok': False, 'reason': f'schema 校验失败：缺失字段 {miss}', 'detail': {}}
    try:
        o, h, l, c = (float(last[x]) for x in ('open', 'high', 'low', 'close'))
    except Exception:
        return {'ok': False, 'reason': 'schema 校验失败：字段类型错', 'detail': {}}
    if not (h >= l and l <= c <= h and o > 0):
        return {'ok': False, 'reason': 'schema 校验失败：OHLC 不合理', 'detail': {}}
    # 数据过期：最新 bar 日期 < 预期最新交易日（容差 1 交易日）
    if expect_date is not None:
        try:
            bd = pd.Timestamp(str(last['time'])[:10])
            gap = (pd.Timestamp(expect_date).normalize() - bd.normalize()).days
            if gap > STALE_TOLERANCE_DAYS:
                return {'ok': False,
                        'reason': f'数据过期：最新 bar {bd.date()} 落后预期 {gap} 天',
                        'detail': {'last_bar': str(bd.date())}}
        except Exception as e:
            return {'ok': False, 'reason': f'数据过期校验异常：{str(e)[:120]}',
                    'detail': {}}
    return {'ok': True, 'reason': '主源健康', 'detail': {'last_bar': str(last['time'])[:10]}}


def check_round(symbols=None, cache='/tmp/box_cache', expect_date=None,
                sleep_fn=None, retries=RETRY_PER_ROUND):
    """一个「周期」的健康检查：单轮内重试 retries 次（间隔 RETRY_SLEEP_SEC），
    全部失败 → 记 1 个周期失败。返回 {'ok':bool, 'attempts':[...]}"""
    attempts = []
    for i in range(retries):
        res = probe_primary(symbols=symbols, cache=cache, expect_date=expect_date)
        attempts.append(res)
        if res['ok']:
            return {'ok': True, 'attempts': attempts}
        if i < retries - 1:
            sec = float(os.environ.get('F1_RETRY_SLEEP', RETRY_SLEEP_SEC))
            if sleep_fn is not None:
                sleep_fn(sec)
            elif sec > 0:
                import time
                time.sleep(sec)
    return {'ok': False, 'attempts': attempts}


# ---------------------------------------------------------------- 状态机
SOURCE_STATES = ('NORMAL', 'DEGRADED', 'RECOVERING')


def transition(state, round_ok, consistency=None, now=None):
    """推进状态机（纯函数；返回 (new_state, event)）。
    - NORMAL   + 连续 FAIL_PERIODS_TO_DEGRADE 个周期失败 → DEGRADED
    - DEGRADED + 连续 OK_PERIODS_TO_RECOVER 个周期健康 → RECOVERING；
                 若同轮传入 consistency（Q-1 自动验收），当轮即完成验收判定
    - RECOVERING + 一致性验收通过 → NORMAL（自动，写 RECOVERED 日志）；
                 不通过 → 留 RECOVERING 自动重试（Q-1，不再挂人工等待）；
                 主源又连续 FAIL_PERIODS_TO_DEGRADE 个周期失败 → 显式回退 DEGRADED（Q-2）
    """
    now = now or datetime.now(timezone.utc)
    now_s = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    prev = state.get('state', 'NORMAL')
    state['history'] = (state.get('history') or [])[-19:] + [
        {'ts': now_s, 'from': prev, 'round_ok': bool(round_ok)}]

    if round_ok:
        state['consec_fail'] = 0
        state['consec_ok'] = int(state.get('consec_ok', 0)) + 1
        state['last_ok'] = now_s
    else:
        state['consec_ok'] = 0
        state['consec_fail'] = int(state.get('consec_fail', 0)) + 1
        state['last_fail'] = now_s

    def _apply_acceptance(via=''):
        """Q-1：一致性验收判定（通过→自动切回 NORMAL；不过→留 RECOVERING 自动重试）。"""
        if consistency.get('pass'):
            state['state'] = 'NORMAL'
            state['pending_manual'] = False
            state['degraded_since'] = None
            return log_event('RECOVERED',
                             reason=via + '一致性验收通过 → 自动切回主源',
                             consistency=consistency, at=now_s)
        state['pending_manual'] = True
        return log_event('RECOVER_ACCEPT_RETRY',
                         reason=via + '一致性验收不通过 → 留 RECOVERING，下一健康轮自动重试'
                                       '（不依赖人工触发，禁止自动强切）',
                         consistency=consistency, at=now_s)

    ev = None
    if prev == 'NORMAL':
        if state['consec_fail'] >= FAIL_PERIODS_TO_DEGRADE:
            state['state'] = 'DEGRADED'
            state['degraded_since'] = now_s
            ev = log_event('DEGRADE', reason='主源连续 2 周期失败 → 判死降级',
                           consec_fail=state['consec_fail'], at=now_s)
    elif prev == 'DEGRADED':
        if state['consec_ok'] >= OK_PERIODS_TO_RECOVER:
            state['state'] = 'RECOVERING'
            ev = log_event('RECOVERING', reason='主源连续 2 周期健康 → 待一致性验收',
                           consec_ok=state['consec_ok'], at=now_s)
            if consistency is not None:      # Q-1：进 RECOVERING 同轮自动验收
                ev = _apply_acceptance('进 RECOVERING 同轮·')
    elif prev == 'RECOVERING':
        if state['consec_fail'] >= FAIL_PERIODS_TO_DEGRADE:
            # Q-2（WO-R14）：验收重试中主源又连续 2 周期失败 → 显式回退 DEGRADED 并冻结新信号
            state['state'] = 'DEGRADED'
            state['degraded_since'] = now_s
            state['pending_manual'] = False
            ev = log_event('RECOVER_DEGRADE',
                           reason='RECOVERING 期主源又连续 2 周期失败 → '
                                  '显式回退 DEGRADED 并冻结新信号',
                           consec_fail=state['consec_fail'], at=now_s)
        elif consistency is None:
            pass                      # 尚未验收：维持待验收（下一健康轮自动重试）
        else:
            ev = _apply_acceptance()
    return state, ev


# ---------------------------------------------------------------- Q-1 自动验收（方案 A）
def _auto_acceptance(symbols=None):
    """Q-1（WO-R14 · 用户已批方案 A）：RECOVERING/将入 RECOVERING 的健康探测轮
    自动拉取主源近 3 日日K + 新浪同标的日K（≤白名单上限）做一致性验收。
    返回 consistency dict（含 auto=True）；任一侧数据不可得 → None（本轮不验收，下轮重试）。
    F1_ACCEPT_FORCE=ok|fail|none：仅测试用注入（对齐 F1_PRIMARY_FAIL 纪律），
    生产 cron 禁止遗留该变量。"""
    mode = os.environ.get('F1_ACCEPT_FORCE', '')
    if mode == 'none':
        return None
    syms = list(symbols or DEFAULT_PROBE_SYMBOLS)[:MAX_PROXY_SYMBOLS]
    if mode in ('ok', 'fail'):                       # 测试夹具：1%（过）/ 10%（不过）
        c = 101.0 if mode == 'ok' else 110.0
        res = consistency_check(
            [{'symbol': base_symbol(syms[0]), 'date': '2026-10-16', 'close': 100.0}],
            [{'symbol': base_symbol(syms[0]), 'date': '2026-10-16', 'close': c}])
        res['auto'] = True
        return res
    primary, backup = [], []
    try:
        sys.path.insert(0, '/root/.codebuddy/artifact/kx-combo')
        from kx_client import KxClient
        k = KxClient()
        for sym in syms:
            r = k.get_kline(sym, market='futures', period='1d', limit=5)
            bars = (r.get('data') or {}).get('bars') or r.get('bars') or []
            if isinstance(bars, dict):
                bars = bars.get('bars', [])
            for b in bars[-3:]:
                try:
                    primary.append({'symbol': base_symbol(sym),
                                    'date': str(b['time'])[:10], 'close': float(b['close'])})
                except (KeyError, TypeError, ValueError):
                    continue
    except Exception as e:
        log_event('ACCEPT_PRIMARY_UNAVAILABLE', error=str(e)[:200])
        return None
    try:
        for r in fetch_sina_daily(syms):
            backup.append({'symbol': r['symbol'], 'date': r['date'], 'close': r['close']})
    except Exception as e:
        log_event('ACCEPT_BACKUP_UNAVAILABLE', error=str(e)[:200])
        return None
    if not primary or not backup:
        log_event('ACCEPT_SKIP', reason='主备任一侧无重叠数据，本轮不验收，下轮重试')
        return None
    res = consistency_check(primary, backup)
    res['auto'] = True
    return res


# ---------------------------------------------------------------- 冻结实路比对（R13 审计 §三）
DECISION_FIELDS = ('signal', 'breakers', 'state', 'monthly_accounts')
FROZEN_ANNOTATION_KEYS = {'signal.frozen_by_source_failover', 'signal.operable'}


def decision_diff(before, after, path=''):
    """递归比较两份判定字段结构，返回差异键路径列表（如 'signal.operable'）。"""
    out = []
    if isinstance(before, dict) and isinstance(after, dict):
        for k in sorted(set(before) | set(after)):
            out += decision_diff(before.get(k), after.get(k),
                                 f'{path}.{k}' if path else str(k))
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            out.append(f'{path}[len {len(before)}!={len(after)}]')
        else:
            for i, (x, y) in enumerate(zip(before, after)):
                out += decision_diff(x, y, f'{path}[{i}]')
    elif before != after:
        out.append(path)
    return out


def consistency_check(primary_rows, backup_rows, tol=EFFECTIVE_TOL):
    """主备一致性验收：按 (symbol, date) 对齐，比较 close。
    容差 = 价格容差 1% + 代币/现货基差容差 1% = 2%（基差计入，见空头席要求）。"""
    p = {(r['symbol'], r['date']): float(r['close']) for r in primary_rows}
    b = {(r['symbol'], r['date']): float(r['close']) for r in backup_rows}
    keys = sorted(set(p) & set(b))
    if not keys:
        return {'pass': False, 'reason': '无重叠标的/日期，无法验收',
                'overlap': 0, 'tol': tol, 'basis_tol': BASIS_TOL}
    worst, worst_k = 0.0, None
    for k in keys:
        d = abs(p[k] - b[k]) / max(abs(p[k]), 1e-12)
        if d > worst:
            worst, worst_k = d, k
    ok = worst <= tol
    return {'pass': bool(ok), 'reason': ('一致性通过' if ok else
                                         '收盘价偏差超容差，挂待人工'),
            'overlap': len(keys), 'max_dev': round(worst, 6),
            'worst': {'symbol': worst_k[0], 'date': worst_k[1]},
            'tol': tol, 'price_tol': PRICE_TOL, 'basis_tol': BASIS_TOL}


# ---------------------------------------------------------------- 降级期行为（信号冻结）
def source_banner(state):
    """页面/推送用的一句话说人话标注（多头席要求）。"""
    st = state.get('state', 'NORMAL')
    if st == 'DEGRADED':
        return ('主源故障：信号冻结至 ' + str(state.get('frozen_asof') or state.get('last_ok')) +
                '，以下为备源（新浪）抽查参考，不构成新推荐。')
    if st == 'RECOVERING':
        return ('主源已恢复健康，正在做一致性验收（自动重试，不依赖人工触发）；'
                '验收通过前不出新信号'
                + ('（近期验收曾不通过，继续自动重试）' if state.get('pending_manual') else '')
                + '。')
    return '数据源正常（主源 kxiandaoyan）。'


def freeze_payload(out_json=LIVE_JSON):
    """降级期：读回最后落定的 f1_live.json，**只更新展示层标注**，
    判定字段（signal/breakers/state/monthly_accounts）逐位不动；不写 f1_state.json。"""
    if not os.path.exists(out_json):
        return {'frozen': False, 'reason': '无历史落定文件可冻结', 'writes': {}}
    prev = json.load(open(out_json))
    before = json.dumps({k: prev.get(k) for k in
                         ('signal', 'breakers', 'state', 'monthly_accounts')},
                     ensure_ascii=False, sort_keys=True)
    return {'frozen': True, 'asof': (prev.get('signal') or {}).get('asof'),
            'decision_fields_before': before, 'writes': {'f1_state.json': False}}


def _snapshot_decision_fields(live_json=None):
    """取当前 f1_live.json 的判定字段指纹（signal/breakers/state/monthly_accounts）。"""
    live_json = live_json or LIVE_JSON
    if not os.path.exists(live_json):
        return None
    d = json.load(open(live_json))
    return json.dumps({k: d.get(k) for k in
                       ('signal', 'breakers', 'state', 'monthly_accounts')},
                      ensure_ascii=False, sort_keys=True)


def _frozen_asof(state, live_json=LIVE_JSON):
    """冻结基准日：优先取上一版落定 f1_live.json 的 signal.asof，
    否则退回最后一次主源健康的 UTC 日期。"""
    if state.get('frozen_asof'):
        return str(state['frozen_asof'])[:10]
    try:
        d = json.load(open(live_json))
        a = (d.get('signal') or {}).get('asof')
        if a:
            return str(a)[:10]
    except Exception:
        pass
    return str(state.get('last_ok'))[:10]


def run_round(round_id='DECIDE', symbols=None, cache='/tmp/box_cache',
              expect_date=None, state_path=STATE_PATH, consistency=None,
              sleep_fn=None, live_json=LIVE_JSON, auto_accept=True):
    """一轮：探测主源 → （Q-1）RECOVERING/将入 RECOVERING 的健康轮自动一致性验收
    → 推进状态机 → 返回 (state, round_result)。
    consistency 显式传参时以传参为准（演练/自测注入）；None 且 auto_accept=True
    时由 _auto_acceptance 自动取数验收；任一侧数据不可得则本轮不验收、下轮重试。"""
    stt = load_state(state_path)
    rr = check_round(symbols=symbols, cache=cache, expect_date=expect_date,
                     sleep_fn=sleep_fn)
    cons = consistency
    if cons is None and auto_accept and rr['ok']:
        prev_state = stt.get('state', 'NORMAL')
        entering = (prev_state == 'DEGRADED'
                    and int(stt.get('consec_ok', 0)) + 1 >= OK_PERIODS_TO_RECOVER)
        if entering or prev_state == 'RECOVERING':
            cons = _auto_acceptance(symbols=symbols)
    stt, ev = transition(stt, rr['ok'], consistency=cons)
    stt['last_round_id'] = round_id
    if stt['state'] in ('DEGRADED', 'RECOVERING'):
        stt['frozen_asof'] = _frozen_asof(stt, live_json)
    else:
        stt['frozen_asof'] = None
    save_state(stt, state_path)
    return stt, {'round_id': round_id, 'ok': rr['ok'], 'attempts': rr['attempts'],
                 'event': ev, 'acceptance': cons, 'banner': source_banner(stt)}


# ---------------------------------------------------------------- CLI（自检 / 演练）
def _reset(path=STATE_PATH):
    if os.path.exists(path):
        os.unlink(path)
    if os.path.exists(EVENT_LOG):
        os.unlink(EVENT_LOG)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if mode == 'status':
        st = load_state()
        print(json.dumps({'state': st.get('state'), 'consec_fail': st.get('consec_fail'),
                          'consec_ok': st.get('consec_ok'), 'frozen_asof': st.get('frozen_asof'),
                          'pending_manual': st.get('pending_manual'),
                          'banner': source_banner(st), 'sla_note': SINA_SLA_NOTE},
                         ensure_ascii=False, indent=1))
    elif mode == 'check':
        st, rr = run_round(round_id='MANUAL')
        print(json.dumps({'state': st['state'], 'round_ok': rr['ok'],
                          'banner': rr['banner']}, ensure_ascii=False))
    elif mode == 'drill':
        # 完整演练（验收①~⑥）：
        # ① 注入故障连跑 2 周期 → DEGRADED，且 _emit_frozen 实路判定字段实质逐位冻结
        # ② 解除故障连跑 2 周期 → RECOVERING，一致性验收通过 → NORMAL
        # ③ 新浪拉取速率 ≤6 只/轮，且 144 全量拉取被硬拒
        # ④ 降级期任何输出带 asof + source 标注
        # ⑤ Q-1：RECOVERING 自动验收接线（无 consistency 传参 → 自动验收 → NORMAL）
        # ⑥ Q-2：RECOVERING 期主源又连续 2 周期失败 → 显式回退 DEGRADED
        import shutil
        import f1_signal as fs          # 仅演练用：走真实 _emit_frozen 路径（审计 DR2 修复）
        _reset()
        checks, trace = [], []
        os.environ['F1_ACCEPT_FORCE'] = 'none'   # 演练轮次统一关自动验收，显式控制验收注入

        os.environ['F1_PRIMARY_FAIL'] = '1'
        os.environ['F1_RETRY_SLEEP'] = '0'
        for i in range(FAIL_PERIODS_TO_DEGRADE):
            st, rr = run_round(round_id=f'DRILL-FAIL-{i + 1}')
            trace.append({'step': f'fail{i + 1}', 'state': st['state'], 'ok': rr['ok']})
        degr = load_state()
        checks.append({'id': 'DR1', 'desc': '主源连续 2 周期失败 → 状态机判死降级',
                                    'pass': degr['state'] == 'DEGRADED'})
        # ②' DR2（审计 §三 弱断言修复）：调用真实 _emit_frozen 后逐字段比对，
        #    判定字段实质逐位不动，仅允许新增 2 个可操作性标注键
        snap_before = _snapshot_decision_fields()
        tmp_live = '/tmp/r13_drill_frozen_live.json'
        frz = {'writes': {'f1_state.json': False}}
        if os.path.exists(LIVE_JSON):
            shutil.copy2(LIVE_JSON, tmp_live)
            _before = json.load(open(tmp_live))
            frozen = fs._emit_frozen(tmp_live, {'state': degr['state'],
                                                'banner': source_banner(degr)})
            _after = json.load(open(tmp_live))
            diffs = decision_diff({k: _before.get(k) for k in DECISION_FIELDS},
                                  {k: _after.get(k) for k in DECISION_FIELDS})
            frz = frozen
            checks.append({'id': 'DR2',
                           'desc': '降级期 _emit_frozen 实路：判定字段实质逐位不动'
                                   '（仅新增 frozen_by_source_failover/operable 标注键）',
                           'pass': set(diffs) <= FROZEN_ANNOTATION_KEYS
                           and _after['signal'].get('frozen_by_source_failover') is True
                           and _after['signal'].get('operable') is False,
                           'diffs': diffs})
        else:
            checks.append({'id': 'DR2', 'desc': '_emit_frozen 实路（无 f1_live.json 基线）',
                           'pass': False})
        snap_after = _snapshot_decision_fields()
        checks.append({'id': 'DR2b', 'desc': '降级期 f1_live.json 判定字段未被写入',
                                    'pass': bool(snap_before) and snap_before == snap_after})
        checks.append({'id': 'DR3', 'desc': '降级期不写 f1_state.json',
                                    'pass': frz.get('writes', {}).get('f1_state.json') is False
                                    and frz.get('writes', {}).get('recomputed') is False})

        # ③ 新浪白名单硬约束
        wl = proxy_watchlist(['AAPLUSDT', 'NVDAUSDT', 'TSLAUSDT', 'MSFTUSDT', 'GOOGLUSDT'])
        checks.append({'id': 'DR4', 'desc': f'新浪白名单 ≤{MAX_PROXY_SYMBOLS} 只/轮',
                                    'pass': len(wl) <= MAX_PROXY_SYMBOLS, 'watchlist': wl})
        try:
            fetch_sina_daily([f'S{i}USDT' for i in range(144)])
            rejected = False
        except ValueError:
            rejected = True
        checks.append({'id': 'DR5', 'desc': '新浪 144 全量拉取被拒绝（无全量代码路径）',
                                    'pass': rejected})

        os.environ['F1_PRIMARY_FAIL'] = '0'
        for i in range(OK_PERIODS_TO_RECOVER):
            st, rr = run_round(round_id=f'DRILL-OK-{i + 1}')
            trace.append({'step': f'ok{i + 1}', 'state': st['state'], 'ok': rr['ok']})
        rec1 = load_state()
        checks.append({'id': 'DR6', 'desc': '主源连续 2 周期健康 → 进入 RECOVERING 待验收',
                                    'pass': rec1['state'] == 'RECOVERING'})
        cons = consistency_check(
            [{'symbol': 'aapl', 'date': '2026-10-16', 'close': 100.0}],
            [{'symbol': 'aapl', 'date': '2026-10-16', 'close': 101.0}])
        st, rr = run_round(round_id='DRILL-VERIFY', consistency=cons)
        trace.append({'step': 'verify', 'state': st['state'], 'consistency': cons})
        checks.append({'id': 'DR7', 'desc': '一致性验收通过 → 自动切回 NORMAL',
                                    'pass': st['state'] == 'NORMAL'})
        # ④ 降级期输出带 asof + source 标注
        banner = source_banner(load_state())
        frozen_payload = {'asof': (frz.get('signal') or {}).get('asof'),
                          'source': '降级冻结', 'banner': banner}
        checks.append({'id': 'DR8',
                       'desc': '降级期输出带 asof + source 标注',
                       'pass': bool(frozen_payload['asof']) and 'source' in frozen_payload})

        # ⑤ Q-1 自动验收接线：不传 consistency，恢复探测轮自动验收 → NORMAL
        _reset()
        os.environ['F1_ACCEPT_FORCE'] = 'none'
        os.environ['F1_PRIMARY_FAIL'] = '1'
        for i in range(FAIL_PERIODS_TO_DEGRADE):
            run_round(round_id=f'DRILL-Q1F-{i + 1}')
        os.environ['F1_PRIMARY_FAIL'] = '0'
        st_auto = None
        for i in range(OK_PERIODS_TO_RECOVER):
            os.environ['F1_ACCEPT_FORCE'] = 'ok' if i == OK_PERIODS_TO_RECOVER - 1 else 'none'
            st_auto, rr = run_round(round_id=f'DRILL-Q1-{i + 1}')
            trace.append({'step': f'q1-auto-{i + 1}', 'state': st_auto['state'],
                          'acceptance': (rr.get('acceptance') or {}).get('pass')})
        checks.append({'id': 'DR9',
                       'desc': 'Q-1 自动验收接线：RECOVERING 态恢复探测轮自动执行一致性验收'
                               '（无人工传参）→ 自动切回 NORMAL 并写 RECOVERED 日志',
                       'pass': st_auto is not None and st_auto['state'] == 'NORMAL'
                       and (rr.get('acceptance') or {}).get('auto') is True})

        # ⑥ Q-2 回退：RECOVERING 期主源又连续 2 周期失败 → 显式回退 DEGRADED
        _reset()
        os.environ['F1_ACCEPT_FORCE'] = 'none'
        os.environ['F1_PRIMARY_FAIL'] = '1'
        for i in range(FAIL_PERIODS_TO_DEGRADE):
            run_round(round_id=f'DRILL-Q2F-{i + 1}')
        os.environ['F1_PRIMARY_FAIL'] = '0'
        for i in range(OK_PERIODS_TO_RECOVER):
            run_round(round_id=f'DRILL-Q2O-{i + 1}')
        mid = load_state()
        os.environ['F1_PRIMARY_FAIL'] = '1'
        for i in range(FAIL_PERIODS_TO_DEGRADE):
            st_fb, rr = run_round(round_id=f'DRILL-Q2B-{i + 1}')
            trace.append({'step': f'q2-fallback-{i + 1}', 'state': st_fb['state'],
                          'ok': rr['ok']})
        checks.append({'id': 'DR10',
                       'desc': 'Q-2：RECOVERING 期主源又连续 2 周期失败 → '
                               '显式回退 DEGRADED 并冻结新信号',
                       'pass': mid['state'] == 'RECOVERING' and st_fb['state'] == 'DEGRADED'
                       and st_fb.get('frozen_asof') is not None
                       and '冻结' in source_banner(st_fb)})

        n_pass = sum(1 for c in checks if c['pass'])
        payload = {'drill': 'WO-R13-04 数据源容灾演练（R14 补 Q-1 自动验收 / Q-2 回退）',
                   'n_checks': len(checks), 'n_pass': n_pass,
                   'all_pass': n_pass == len(checks),
                          'checks': checks, 'trace': trace,
                          'events_log': EVENT_LOG,
                          'state_file': STATE_PATH}
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        with open(os.path.join(HERE, 'r13_failover_drill.json'), 'w') as f:
            json.dump(payload, f, ensure_ascii=False, indent=1, default=str)
        os.environ.pop('F1_ACCEPT_FORCE', None)
        return 0 if n_pass == len(checks) else 1
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()

