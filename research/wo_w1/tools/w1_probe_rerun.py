#!/usr/bin/env python3
"""W1 探测复现：导演站 37 路径 + 新浪 20 端点，Pool(32)，完整 UA+Referer。
产出 raw/w1_probe_rerun.json（含 fetched_at，供可达性矩阵对拍）。"""
import json, time, concurrent.futures as cf, urllib.request, urllib.error, ssl, os

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
      'Referer': 'https://finance.sina.com.cn/'}
DY = 'https://www.kxiandaoyan.com'
# 与冻结规格 1.1 完全一致的 37 路径
DY_PATHS = ['/api/signals', '/api/kline/MVLLUSDT', '/api/funding', '/api/fundingRate', '/api/funding_rate',
            '/api/fundingRates', '/api/funding/history', '/api/fundingRate/history', '/api/funding_history',
            '/api/markPrice', '/api/premiumIndex', '/api/ticker', '/api/ticker/24hr', '/api/depth', '/api/trades',
            '/api/openInterest', '/api/oi', '/api/longShortRatio', '/api/interestHistory', '/api/income',
            '/api/exchangeInfo', '/api/symbols', '/api/markets', '/api/status', '/api/version', '/api/index',
            '/api/v1/funding', '/api/v1/kline/BTCUSDT', '/api/klines/BTCUSDT', '/api/quote', '/api/rate',
            '/funding', '/openapi/v1/funding', '/swagger.json', '/api/docs', '/api', '/api/positions', '/api/history']
# 与冻结规格 1.2 完全一致的 20 端点
SINA = ['https://hq.sinajs.cn/list=gb_aapl', 'https://hq.sinajs.cn/list=usAAPL_OQ', 'https://hq.sinajs.cn/list=hf_CL',
        'https://hq.sinajs.cn/list=hf_GC', 'https://hq.sinajs.cn/list=hf_BTC', 'https://hq.sinajs.cn/list=hf_SI',
        'https://hq.sinajs.cn/list=fx_susdcnh', 'https://hq.sinajs.cn/list=fx_seurusd', 'https://hq.sinajs.cn/list=DINIW',
        'https://hq.sinajs.cn/list=gb_$ndx', 'https://hq.sinajs.cn/list=op_aapl', 'https://hq.sinajs.cn/list=of_gb_aapl',
        'https://hq.sinajs.cn/list=bt_aapl', 'https://hq.sinajs.cn/list=SHIBOR', 'https://hq.sinajs.cn/list=sofr',
        'https://hq.sinajs.cn/list=hl_usd', 'https://money.finance.sina.com.cn/ftp/chyyshb.html',
        'https://hq.sinajs.cn/list=s_sh000001', 'https://hq.sinajs.cn/list=hf_CAD', 'https://hq.sinajs.cn/list=fx_susdjpy']

def get(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        r = urllib.request.urlopen(req, timeout=12, context=ctx)
        b = r.read(600)
        try: t = b.decode('gbk', 'replace')
        except Exception: t = b.decode('utf-8', 'replace')
        return {'url': url, 'status': r.status, 'ct': r.headers.get('Content-Type'), 'len': len(b),
                'head': t[:250].replace('\n', ' ')}
    except urllib.error.HTTPError as e:
        return {'url': url, 'status': e.code}
    except Exception as e:
        return {'url': url, 'error': type(e).__name__ + ': ' + str(e)[:80]}

t0 = time.time()
with cf.ThreadPoolExecutor(32) as ex:
    dy = list(ex.map(get, [DY + p for p in DY_PATHS]))
    si = list(ex.map(get, SINA))
out = {'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
       'pool': 32, 'dy_path_count': len(DY_PATHS), 'sina_endpoint_count': len(SINA), 'dy': dy, 'sina': si}
os.makedirs(os.path.dirname(RAW := os.path.join(os.path.dirname(__file__), '..', 'raw')), exist_ok=True)
json.dump(out, open(RAW + '/w1_probe_rerun.json', 'w'), ensure_ascii=False, indent=1)

print(f'== 导演站 {len(dy)} 路径 ==')
for r in dy:
    s = r.get('status', r.get('error', '?'))
    ct = r.get('ct', '')
    kind = 'JSON' if 'json' in ct else ('HTML兜底' if r.get('status') == 200 and 'html' in ct else '')
    print(f"{r['url'].replace(DY, ''):34s} {str(s):55s} {kind}")
print(f'== 新浪 {len(si)} 端点 ==')
for r in si:
    s = r.get('status', r.get('error', '?'))
    h = r.get('head', '')[:80]
    print(f"{r['url'].split('cn/')[-1].split('cn?')[-1]:40s} {str(s):4s} {h}")
print(f'elapsed {time.time()-t0:.1f}s -> raw/w1_probe_rerun.json')
