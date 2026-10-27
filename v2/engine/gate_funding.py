# -*- coding: utf-8 -*-
"""Pull Gate USDT-perp funding history for the 导演 US-stock universe.

Public endpoints only; no API key is required or stored.
Price standard stays 导演; Gate is used only to calibrate funding cost.
"""
import os, sys, json, time, glob, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'cache_fresh')
OUT = os.path.join(HERE, 'gate_funding.json')
CONTRACTS = os.path.join(HERE, 'gate_contracts.json')
BASE = 'https://api.gateio.ws/api/v4'


def get(url, tries=2):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'qoder/1.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last = e
            time.sleep(0.4)
    raise last


def one(sym, meta, now):
    launch = int(meta.get('launch_time') or 0)
    if launch <= 0:
        return sym, None
    rows = []
    frm = launch
    for _ in range(6):
        url = ('%s/futures/usdt/funding_rate?contract=%s_USDT&from=%d&to=%d&limit=1000'
               % (BASE, sym, frm, now))
        part = get(url)
        if not part:
            break
        rows.extend(part)
        mx = max(int(x['t']) for x in part)
        if mx <= frm or len(part) < 900:
            break
        frm = mx + 1
    if not rows:
        return sym, None
    seen = {}
    for x in rows:
        seen[int(x['t'])] = float(x['r'])
    daily = {}
    for t, r in sorted(seen.items()):
        d = dt.datetime.fromtimestamp(t, dt.UTC).strftime('%Y-%m-%d')
        daily[d] = daily.get(d, 0.0) + r
    vals = sorted(daily.values())
    n = len(vals)
    if not n:
        return sym, None
    avg = sum(vals) / n
    med = vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])
    return sym, dict(contract=sym + '_USDT', launch=launch, points=len(seen), days=n,
                     first=min(daily), last=max(daily), avg_daily=avg, med_daily=med,
                     p95_daily=vals[min(n - 1, int(n * 0.95))], max_daily=max(vals),
                     min_daily=min(vals), ann_avg=avg * 365,
                     interval=int(meta.get('funding_interval') or 28800),
                     mark=float(meta.get('mark_price') or 0),
                     oi=float(meta.get('position_size') or 0), daily=daily)


def main():
    cache = {os.path.basename(p)[:-9] for p in glob.glob(os.path.join(CACHE, '*.json'))
             if not os.path.basename(p).startswith('_')}
    if os.path.exists(CONTRACTS):
        contracts = json.load(open(CONTRACTS, encoding='utf-8'))
    else:
        contracts = get(BASE + '/futures/usdt/contracts')
        json.dump(contracts, open(CONTRACTS, 'w', encoding='utf-8'))
    by_base = {x['name'][:-5]: x for x in contracts if x['name'].endswith('_USDT')}
    syms = sorted(cache & set(by_base))
    now = int(time.time())
    out = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = {ex.submit(one, s, by_base[s], now): s for s in syms}
        for k, f in enumerate(as_completed(fut), 1):
            s = fut[f]
            try:
                sym, rec = f.result()
            except Exception as e:
                print('ERR', s, e)
                continue
            if rec:
                out[sym] = rec
            if k % 25 == 0:
                print('done', k)
    if not out:
        raise SystemExit('no funding rows')
    avg_all = sum(v['avg_daily'] for v in out.values()) / len(out)
    med_sym = sorted(v['avg_daily'] for v in out.values())[len(out) // 2]
    pos = sum(1 for v in out.values() if v['avg_daily'] > 0)
    summary = dict(n=len(out), avg_daily=avg_all, ann=avg_all * 365, positive=pos,
                   median_symbol=med_sym,
                   span=[min(v['first'] for v in out.values()), max(v['last'] for v in out.values())])
    json.dump(dict(summary=summary, symbols=out), open(OUT, 'w', encoding='utf-8'), indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print('backtest assumption 0.0003/day -> annual %.1f%%' % (0.0003 * 365 * 100))
    hi = sorted(out.items(), key=lambda kv: -kv[1]['avg_daily'])[:6]
    for s, v in hi:
        print('high %s avg %.4f%%/d ann %.1f%% p95 %.4f%%' % (
            s, v['avg_daily'] * 100, v['ann_avg'] * 100, v['p95_daily'] * 100))


if __name__ == '__main__':
    main()
