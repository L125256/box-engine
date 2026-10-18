#!/usr/bin/env python3
"""W1 心跳探测器（常设件，规格七-1 冻结：每次会话开工先跑 3 端点心跳）。
端点：dy /api/symbols、sina gb_aapl、sina hf_BTC。
- 顺带充当 funding 复活哨兵：导演站若新增 funding 端点，由每次会话的 57 路径全量探测（w1_probe_rerun.py）发现；
  心跳发现 /api/symbols 不可达即视为导演站心跳告警。
- 产出追加写入 raw/w1_heartbeat_log.jsonl（每行含 fetched_at + 血缘）。
用法: python3 w1_heartbeat.py
"""
import json, ssl, time, urllib.request, urllib.error, os

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, '..', 'raw')
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
      'Referer': 'https://finance.sina.com.cn/', 'Accept': '*/*', 'Accept-Language': 'zh-CN,zh;q=0.9'}
CHECKS = [
    {'name': 'dy_symbols', 'url': 'https://www.kxiandaoyan.com/api/symbols', 'expect': 'total==241(基线2026-10-19)',
     'source': 'kxiandaoyan', 'bar_date_convention': '北京日期+盘后延伸+周日合成bar'},
    {'name': 'sina_gb_aapl', 'url': 'https://hq.sinajs.cn/list=gb_aapl', 'expect': 'status=200 且字段非空',
     'source': 'sina', 'headers_required': 'full-UA+Referer+Accept'},
    {'name': 'sina_hf_BTC', 'url': 'https://hq.sinajs.cn/list=hf_BTC', 'expect': 'status=200 且字段非空',
     'source': 'sina', 'headers_required': 'full-UA+Referer+Accept'},
]


def check(c):
    t0 = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(c['url'], headers=UA), timeout=15, context=ctx)
        b = r.read(400)
        body = b.decode('gbk', 'replace')
        ok = r.status == 200 and body.strip('"; \n') != ''
        detail = body[:90].replace('\n', ' ')
        if c['name'] == 'dy_symbols' and ok:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(c['url'], headers=UA), timeout=15, context=ctx).read())
            ok = d.get('total') == 241
            detail = f"total={d.get('total')}"
        return {'name': c['name'], 'ok': ok, 'status': r.status, 'detail': detail, 'latency_ms': int((time.time() - t0) * 1000)}
    except Exception as e:
        return {'name': c['name'], 'ok': False, 'status': None, 'detail': str(e)[:90], 'latency_ms': int((time.time() - t0) * 1000)}


def main():
    fetched_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    results = [check(c) for c in CHECKS]
    rec = {'fetched_at': fetched_at,
           'heartbeat_endpoints': [{'source': c['source'], 'path': c['url']} for c in CHECKS],
           'results': results, 'all_ok': all(r['ok'] for r in results)}
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, 'w1_heartbeat_log.jsonl'), 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps(rec, ensure_ascii=False, indent=1))
    return 0 if rec['all_ok'] else 1


if __name__ == '__main__':
    sys_exit = main()
    raise SystemExit(sys_exit)
