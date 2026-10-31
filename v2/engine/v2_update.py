#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot v2 update: refresh data -> rebuild page -> write index.html.

Pipeline (all deterministic, no secrets, no Gate price data):
  1. refresh_fresh.refresh()     pull 144 symbols from 导演 (public kline API)
  2. v2_diag.main()              full backtest -> v2_page.json
  3. v2_addendum.main()          merge breadth / bases / funding audit
  4. v2_live_board.main()        merge today's board + health
  5. v2_page.build(outdir/index.html)

Usage:
  python3 v2_update.py --cache /workspace/v2_cache --outdir /workspace/repo_ready/v2
  python3 v2_update.py --skip-refresh --cache ./cache_fresh --outdir ./dist

Exit code 0 only if every stage succeeded and the page passed sanity checks.
A partial pull (any of the 144 missing) aborts before the page is rebuilt, so a
half-refreshed cache can never overwrite a good published page.
"""
import os, sys, json, time, argparse, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)          # parent of v2/ (holds refresh_fresh.py, cache_fresh/)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def stage(name, fn):
    t = time.time()
    print('\n== %s' % name, flush=True)
    r = fn()
    print('-- %s done in %.1fs' % (name, time.time() - t), flush=True)
    return r


def default_pool():
    # engine bundle keeps its own copy; local research tree keeps it one level up
    for p in (os.path.join(HERE, 'engine_snapshot', 'cleaned_pool.json'),
              os.path.join(WORK, 'engine_snapshot', 'cleaned_pool.json')):
        if os.path.exists(p):
            return p
    return os.path.join(HERE, 'engine_snapshot', 'cleaned_pool.json')


def main():
    for stream in (sys.stdout, sys.stderr):     # keep logs readable on GBK hosts
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default=os.environ.get('V2_CACHE') or os.path.join(WORK, 'cache_fresh'))
    ap.add_argument('--pool', default=os.environ.get('V2_POOL') or default_pool())
    ap.add_argument('--outdir', default=os.path.join(HERE, 'dist'))
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--skip-refresh', action='store_true')
    ap.add_argument('--allow-partial', action='store_true',
                    help='build even if some symbols failed to refresh (default: abort)')
    a = ap.parse_args()

    cache = os.path.abspath(a.cache)
    outdir = os.path.abspath(a.outdir)
    os.makedirs(outdir, exist_ok=True)

    # v2_lib reads V2_CACHE at import time; set it before importing the engine.
    os.environ['V2_CACHE'] = cache
    os.environ['V2_POOL'] = os.path.abspath(a.pool)
    sys.path.insert(0, WORK)
    sys.path.insert(0, HERE)

    t0 = time.time()
    rep = None
    if not a.skip_refresh:
        import refresh_fresh
        rep = stage('refresh 144 symbols', lambda: refresh_fresh.refresh(cache, a.workers, a.pool))
        if rep['fail'] and not a.allow_partial:
            print('ABORT: %d symbols failed to refresh: %s' % (len(rep['fail']), rep['fail']))
            return 2
    else:
        print('skip refresh, cache=%s' % cache)

    # The page must always be built from the full 144-name pool, whether the
    # cache was refreshed now or reused. A missing file would silently change
    # the universe, so treat it as a hard failure unless explicitly allowed.
    with open(a.pool, encoding='utf-8') as f:
        pool = [x['tkr'] for x in json.load(f)['kept']]
    missing = [s for s in pool if not os.path.exists(os.path.join(cache, s + '.json'))]
    if missing and not a.allow_partial:
        print('ABORT: %d/%d symbols missing from cache: %s' % (len(missing), len(pool), missing[:10]))
        return 2
    print('cache complete: %d/%d symbols' % (len(pool) - len(missing), len(pool)))

    import v2_diag, v2_bases, v2_addendum, v2_live_board, v2_page
    stage('backtest (v2_diag)', v2_diag.main)
    stage('bases (v2_bases)', v2_bases.main)
    stage('addendum (v2_addendum)', v2_addendum.main)
    stage('live board (v2_live_board)', v2_live_board.main)
    out = stage('render page', lambda: v2_page.build(os.path.join(outdir, 'index.html')))

    with open(os.path.join(HERE, 'v2_page.json'), encoding='utf-8') as f:
        page = json.load(f)

    # sanity: the page must carry a dated board for the execution base (v2.1)
    problems = []
    if not page.get('asof'):
        problems.append('missing asof')
    if not page.get('board', {}).get('v', {}).get('cand'):
        problems.append('missing board.v.cand')
    if len(page.get('profiles', {})) < 3:
        problems.append('profiles < 3')
    if len(page.get('curves', {})) < 3:
        problems.append('curves < 3')
    if len(page.get('trades', {}).get('C', [])) < 50:
        problems.append('trades.C < 50')
    if problems:
        print('ABORT: page sanity failed: %s' % ', '.join(problems))
        return 3

    build_rep = dict(
        asof=page['asof'],
        built_at=page.get('board', {}).get('built_at'),
        next_entry=page.get('board', {}).get('next_entry'),
        active=page.get('board', {}).get('active'),
        refresh=None if rep is None else dict(
            ok=rep['ok'], fail=rep['fail'],
            last_bar=sorted((d, c) for d, c in rep['last_bar'])),
        page=os.path.basename(out),
        page_bytes=os.path.getsize(out),
        page_sha256=sha256(out),
        page_json_sha256=sha256(os.path.join(HERE, 'v2_page.json')),
    )
    with open(os.path.join(outdir, 'build_report.json'), 'w', encoding='utf-8') as f:
        json.dump(build_rep, f, ensure_ascii=False, indent=1)

    print('\nOK asof=%s next=%s active=%s page=%.1f KB sha=%s total=%.1fs'
          % (build_rep['asof'], build_rep['next_entry'], build_rep['active'],
             build_rep['page_bytes'] / 1024, build_rep['page_sha256'][:12],
             time.time() - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
