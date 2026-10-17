#!/usr/bin/env python3
# refresh_cache.py — WT-C 影子双轨 · 32 线程行情缓存刷新
# 复用 /tmp/build_cache.py 逻辑：kx_client 拉日线 limit=700，失败跳过（保留旧缓存）。
# 池 = 存档面板标的（剔除稀疏标的） ∪ 清洗池 144 标的（保证权威池完整）。
# 只写 /tmp/box_cache/*.json 与 /tmp/wtc/refresh_report.json，不改其他目录。
import sys, os, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/root/.codebuddy/artifact/kx-combo")
from kx_client import KxClient

CACHE_DIR = "/tmp/box_cache"
REPORT = "/tmp/wtc/refresh_report.json"
EXCLUDE_SPARSE = ['BSPUSDT', 'FWDIUSDT', 'BBXUSDT', 'BITOUSDT', 'STRCUSDT']
WORKERS = 32


def build_pool():
    pool = set()
    try:
        d = json.load(open('/root/.codebuddy/artifact/kx-combo/archive/2026-10-10.json'))
        pool |= {r['sym'] for r in d['rows']}
    except Exception as e:
        print(f'[warn] 存档面板读取失败({e})，仅用清洗池', flush=True)
    pool -= set(EXCLUDE_SPARSE)
    try:
        cp = json.load(open('/tmp/eng_wt/cleaned_pool.json'))
        pool |= {x['tkr'] for x in cp['kept']}
    except Exception as e:
        print(f'[warn] cleaned_pool 读取失败({e})', flush=True)
    return sorted(pool)


def pull(k, sym):
    for attempt in range(3):
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
        except Exception:
            time.sleep(2)
    return sym, 0, None


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    pool = build_pool()
    print(f'池: {len(pool)} 标的, 线程: {WORKERS}', flush=True)
    k = KxClient()
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
    with open(REPORT, 'w') as f:
        json.dump(dict(ts=time.strftime('%Y-%m-%d %H:%M:%S'),
                       pool=len(pool), ok=ok, fail=fail,
                       cache_files=len(os.listdir(CACHE_DIR)),
                       last_bar_max=max(last_bar.values()) if last_bar else None), f,
                  ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
