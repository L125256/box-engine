#!/usr/bin/env python3
"""W1 每日校验流水线（常设件）。
- 每日 3 只轮换对照：1 CRYPTO + 1 高量 EQUITY + 1 低量 EQUITY（首日固定 BTCUSDT/AAPLUSDT/AAOIUSDT）
- 对齐判据（规格八-4 冻结）：最近同步快照 + 日期标签偏移探测（0/+1/-1 天取最小 |dev|）；
  禁逐日硬对齐；禁用导演站周日合成 bar 作对照锚。
- 容差：默认 ±1%，CRYPTO ±1.5%（计入 USDT 基差）。
- 超差两级：①口径复查（偏移探测已含）→ 仍超差 → 报警 + 冻结该源当日数据标记。
- 影子回填：CME 基差（hf_BTC vs BTCUSDT）+ fx_susdcnh，血缘四元组齐备；funding 列不动（0.03%/bar 常数记账）。
用法: python3 w1_xval_pipeline.py [YYYY-MM-DD]   # 缺省=今天(UTC)
"""
import json, ssl, sys, time, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone

HERE = os_dir = __import__('os').path.dirname(__file__)
RAW = __import__('os').path.join(HERE, '..', 'raw')
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
      'Referer': 'https://finance.sina.com.cn/', 'Accept': '*/*', 'Accept-Language': 'zh-CN,zh;q=0.9'}
DY = 'https://www.kxiandaoyan.com'
SINA = 'https://hq.sinajs.cn/list='
TOL = {'default': 1.0, 'CRYPTO': 1.5}
# 轮换池（逐代码经新浪实测验证可用；hf_ETH/hf_SOL、gb_hanmi/gb_mvizy 实测空 -> 登记缺口，
# 依 R9 纪律穷举变体后方可判死，此处仅登记不判死）
ROT = {'CRYPTO': ['BTCUSDT'],   # 仅 hf_BTC 验证可用 -> CRYPTO 线轮换退化为固定 BTC
       'EQUITY_HI': ['AAPLUSDT', 'NVDAUSDT', 'TSLAUSDT'],
       'EQUITY_LO': ['AAOIUSDT', 'VKTXUSDT', 'RDWUSDT']}
SINA_MAP = {'BTCUSDT': 'hf_BTC',
            'AAPLUSDT': 'gb_aapl', 'NVDAUSDT': 'gb_nvda', 'TSLAUSDT': 'gb_tsla',
            'AAOIUSDT': 'gb_aaoi', 'VKTXUSDT': 'gb_vktx', 'RDWUSDT': 'gb_rdw'}
SINA_GAPS = ['hf_ETH', 'hf_SOL', 'gb_hanmi', 'gb_mvizy']  # 实测 200 空串，字段缺口


def http(url, binary=False, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            r = urllib.request.urlopen(req, timeout=15, context=ctx)
            b = r.read()
            return b.decode('gbk', 'replace') if not binary else b
        except urllib.error.HTTPError as e:
            if e.code == 403 and i < tries - 1:
                time.sleep(2.5 * (i + 1))   # 新浪反爬限频：串行降频重试
                continue
            raise


def is_sunday(ds):
    return datetime.strptime(ds, '%Y-%m-%d').weekday() == 6


def dy_last_bars(sym, n=8):
    d = json.loads(http(f'{DY}/api/kline/{sym}'))
    return d['bars'][-n:]


def pick_anchor(bars):
    """最近非周日合成 bar 作对照锚。"""
    for b in reversed(bars):
        if not is_sunday(b['time']):
            return b
    raise RuntimeError('无非周日 bar')


def sina_quote(code):
    s = http(SINA + code)
    vals = s.split('"')[1].split(',')
    if code.startswith('hf_'):
        return {'close': float(vals[0]), 'time': vals[6], 'date_label': vals[12]}
    if code.startswith('fx_'):
        return {'close': float(vals[8]), 'time': vals[0], 'date_label': vals[17]}
    # gb_: name,price,chg%,datetime(北京)
    return {'close': float(vals[1]), 'time': vals[3], 'date_label': vals[3][:10]}


def xval_one(dy_sym, sina_code):
    bars = dy_last_bars(dy_sym)
    anchor = pick_anchor(bars)
    sq = sina_quote(sina_code)
    sina_d = datetime.strptime(sq['date_label'], '%Y-%m-%d').date()
    # 偏移探测：0/+1/-1 天，取最小 |dev|
    trials = []
    for off in (0, 1, -1):
        target = (sina_d - timedelta(days=off)).isoformat()
        bar = next((b for b in bars if b['time'] == target and not is_sunday(target)), None)
        if bar:
            dev = (float(bar['close']) - sq['close']) / sq['close'] * 100
            trials.append({'offset_days': off, 'dy_bar_date': target, 'dy_close': bar['close'], 'dev_pct': round(dev, 3)})
    best = min(trials, key=lambda t: abs(t['dev_pct'])) if trials else None
    return {'dy_symbol': dy_sym, 'sina_symbol': sina_code,
            'anchor_bar_date': anchor['time'], 'anchor_close': anchor['close'],
            'sina_close': sq['close'], 'sina_quote_time': sq['time'], 'sina_date_label': sq['date_label'],
            'offset_trials': trials, 'chosen': best}


def run(day_utc=None):
    # 轮换与业务日按北京日期（导演站 bar/新浪 gb_ 时间戳均为北京时区）
    bj = datetime.now(timezone(timedelta(hours=8)))
    day = day_utc or bj.strftime('%Y-%m-%d')
    # 轮换：日序号在候选池中的偏移；首日(D0)=BTCUSDT/AAPLUSDT/AAOIUSDT
    d0 = date(2026, 10, 19)
    idx = max((date.fromisoformat(day) - d0).days, 0)
    trio = [('CRYPTO', ROT['CRYPTO'][idx % len(ROT['CRYPTO'])]),
            ('EQUITY_HI', ROT['EQUITY_HI'][idx % len(ROT['EQUITY_HI'])]),
            ('EQUITY_LO', ROT['EQUITY_LO'][idx % len(ROT['EQUITY_LO'])])]
    fetched_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    results, alarms = [], []
    for tier, sym in trio:
        try:
            r = xval_one(sym, SINA_MAP[sym])
        except Exception as e:
            alarms.append({'symbol': sym, 'level': 'FETCH_FAIL', 'error': str(e)[:120]})
            continue
        r['tier'] = tier
        tol = TOL['CRYPTO'] if tier == 'CRYPTO' else TOL['default']
        r['tolerance_pct'] = tol
        if r['chosen'] and abs(r['chosen']['dev_pct']) <= tol:
            r['verdict'] = 'PASS'
        else:
            r['verdict'] = 'ALARM_FREEZE_SOURCE'   # 口径复查(偏移探测)后仍超差
            alarms.append({'symbol': sym, 'level': 'OVER_TOLERANCE_AFTER_CALIBER_CHECK',
                           'dev_pct': r['chosen']['dev_pct'] if r['chosen'] else None, 'tolerance_pct': tol})
        results.append(r)
    # 影子回填（仅影子层，血缘四元组）
    shadow = {'_lineage_rule': '{source,path,fetched_at,raw_snapshot} 四元组强制；sina 加 headers_required；dy 加 bar_date_convention',
              'fetched_at': fetched_at, 'rows': []}
    try:
        btc_dy = pick_anchor(dy_last_bars('BTCUSDT'))
        hf = sina_quote('hf_BTC')
        basis = (hf['close'] - btc_dy['close']) / btc_dy['close'] * 100
        json.dump({'hf_BTC_raw': hf, 'BTCUSDT_dy': btc_dy}, open(f'{RAW}/shadow_cme_basis_raw_{day}.json', 'w'), ensure_ascii=False, indent=1)
        shadow['rows'].append({'shadow_field': 'cme_basis_pct', 'value': round(basis, 3), 'asof_date': day,
                               'source': 'sina+kxiandaoyan', 'path': 'hq.sinajs.cn/list=hf_BTC + /api/kline/BTCUSDT',
                               'fetched_at': fetched_at, 'raw_snapshot': f'raw/shadow_cme_basis_raw_{day}.json',
                               'headers_required': 'full-UA+Referer+Accept(sina)',
                               'bar_date_convention': '北京日期+盘后延伸+周日合成bar(dy)',
                               'ledger_isolation': '影子层，禁入 funding 账本'})
    except Exception as e:
        shadow['rows'].append({'shadow_field': 'cme_basis_pct', 'error': str(e)[:120]})
    try:
        cnh = sina_quote('fx_susdcnh')
        json.dump({'fx_susdcnh_raw': cnh}, open(f'{RAW}/shadow_usdcnh_raw_{day}.json', 'w'), ensure_ascii=False, indent=1)
        shadow['rows'].append({'shadow_field': 'usdcnh_close', 'value': cnh['close'], 'asof_date': cnh['date_label'],
                               'source': 'sina', 'path': 'hq.sinajs.cn/list=fx_susdcnh',
                               'fetched_at': fetched_at, 'raw_snapshot': f'raw/shadow_usdcnh_raw_{day}.json',
                               'headers_required': 'full-UA+Referer+Accept(sina)',
                               'ledger_isolation': '影子层，禁入 funding 账本'})
    except Exception as e:
        shadow['rows'].append({'shadow_field': 'usdcnh_close', 'error': str(e)[:120]})
    out = {'run_date_utc': day, 'rotation_index': idx, 'trio': [s for _, s in trio],
           'xval': results, 'alarms': alarms,
           'funding_ledger': {'status': '常数记账不变', 'value_per_bar': 0.0003,
                              'note': 'FUNDING=0.0003 @ engine_f1/f1_signal.py:68 未改动；代理字段禁入'},
           'shadow_backfill': shadow}
    json.dump(out, open(f'{RAW}/w1_xval_run_{day}.json', 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({'day': day, 'trio': out['trio'],
                      'verdicts': [{k: r.get(k) for k in ('dy_symbol', 'verdict', 'chosen', 'tolerance_pct')} for r in results],
                      'alarms': alarms, 'shadow_rows': shadow['rows']}, ensure_ascii=False, indent=1))
    return out


if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else None)
