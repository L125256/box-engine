#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从导演站刷新 144 定版池日线到本地缓存（只读 API，不改仓库）。
用法: python refresh_fresh.py <cache_dir> [workers]
"""
import os, sys, json, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://www.kxiandaoyan.com/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


class KxClient:
    """stdlib-only client; public kline endpoint, no auth, no key."""
    def __init__(self, timeout=10, retries=1, connect_timeout=5):
        self.timeout, self.retries, self.connect_timeout = timeout, retries, connect_timeout

    def get_kline(self, symbol, market="futures", period="1d", limit=700):
        qs = urllib.parse.urlencode({"market": market, "period": period,
                                     "limit": max(50, limit)})
        req = urllib.request.Request("%s/kline/%s?%s" % (BASE_URL, symbol, qs),
                                     headers={"User-Agent": UA,
                                              "Referer": "https://www.kxiandaoyan.com/"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode('utf-8'))


def pull(k, sym, cache_dir):
    for attempt in range(3):
        try:
            r = k.get_kline(sym, market="futures", period="1d", limit=700)
            bars = r.get("bars") or []
            if bars:
                tmp = os.path.join(cache_dir, f".{sym}.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(bars, f)
                os.replace(tmp, os.path.join(cache_dir, f"{sym}.json"))
                return sym, len(bars), bars[-1]["time"]
        except Exception as e:
            time.sleep(2)
    return sym, 0, None


def pool_file():
    return os.environ.get("V2_POOL") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "engine_snapshot", "cleaned_pool.json")


def refresh(cache_dir, workers=32, pool_path=None):
    """Pull all 144 symbols; returns dict(ok, fail, last_bar, seconds)."""
    cache_dir = os.path.abspath(cache_dir)
    os.makedirs(cache_dir, exist_ok=True)
    pool = [x["tkr"] for x in json.load(open(pool_path or pool_file(), encoding="utf-8"))["kept"]]
    assert len(pool) == 144, len(pool)
    k = KxClient()
    ok, fail, last = 0, [], {}
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(pull, k, s, cache_dir): s for s in pool}
        for f in as_completed(futs):
            sym, n, lb = f.result()
            if n:
                ok += 1; last[sym] = lb
            else:
                fail.append(sym)
            done = ok + len(fail)
            if done % 40 == 0:
                print(f"progress {done}/{len(pool)}  ok={ok} fail={len(fail)}  {time.time()-t0:.1f}s", flush=True)
    print(f"DONE ok={ok} fail={len(fail)} elapsed={time.time()-t0:.1f}s", flush=True)
    if fail:
        print("FAILED:", fail)
    from collections import Counter
    print("last_bar:", Counter(last.values()).most_common(5))
    # 记录拉取时间与覆盖
    rep = dict(pulled_at=time.strftime("%Y-%m-%d %H:%M:%S"), ok=ok, fail=fail,
               last_bar=Counter(last.values()).most_common(10),
               seconds=round(time.time() - t0, 1))
    json.dump(rep, open(os.path.join(cache_dir, "_refresh_report.json"), "w"),
              ensure_ascii=False, indent=1)
    return rep


def main():
    cache_dir = sys.argv[1] if len(sys.argv) > 1 else "cache_fresh"
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    refresh(cache_dir, workers)


if __name__ == "__main__":
    main()
