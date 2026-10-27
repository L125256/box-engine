#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload the two v2 artifacts to GitHub through the Contents API.

Only api.github.com is used (the cloud sandbox blocks github.com and
raw.githubusercontent.com). The token is read from the environment and is
never written to disk, printed, or included in any report.

Gates before any write (fail-closed):
  - artifact exists and is larger than its minimum size
  - artifact mtime >= .start (the timestamp written before this run)
  - build_report.page_sha256 equals sha256(index.html)
  - build_report.asof is non-empty
Unchanged files are skipped by comparing the local git blob sha with the
remote content sha, so a no-op run creates no commit.

Usage:
  GITHUB_TOKEN=... python3 put_artifacts.py --dir out --start .start
  python3 put_artifacts.py --dir out --start .start --dry-run
"""
import os, sys, json, base64, hashlib, argparse, urllib.request, urllib.error, urllib.parse

REPO_DEFAULT = 'L125256/box-engine'
BRANCH_DEFAULT = 'main'
PAIRS = [
    ('index.html', 'v2/index.html', 200),
    ('build_report.json', 'v2/build_report.json', 100),
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def blob_sha(data):
    """Git blob id, identical to the sha returned by the Contents API."""
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def gh(url, token=None, data=None, method=None):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'v2-3step'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(
        url, data=json.dumps(data).encode() if data is not None else None,
        method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def remote_sha(api, repo, path, branch, token):
    url = '%s/repos/%s/contents/%s?ref=%s' % (
        api, repo, urllib.parse.quote(path), branch)
    try:
        return gh(url, token)['sha']
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='out')
    ap.add_argument('--start', default='.start')
    ap.add_argument('--repo', default=REPO_DEFAULT)
    ap.add_argument('--branch', default=BRANCH_DEFAULT)
    ap.add_argument('--api-base', default='https://api.github.com')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    api = a.api_base.rstrip('/')

    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('T') or ''
    if not token and not a.dry_run:
        print('ABORT: GITHUB_TOKEN is not set')
        return 2

    start = int(open(a.start).read().strip()) if os.path.exists(a.start) else 0
    if not start:
        print('ABORT: missing or empty %s (mtime gate would be disabled)' % a.start)
        return 2

    local = {}
    for name, _rp, min_size in PAIRS:
        p = os.path.join(a.dir, name)
        if not os.path.exists(p) or os.path.getsize(p) < min_size:
            print('ABORT: missing or tiny %s' % p)
            return 3
        if int(os.path.getmtime(p)) < start:
            print('ABORT: stale artifact %s (older than this run)' % p)
            return 3
        local[name] = open(p, 'rb').read()

    report = json.loads(local['build_report.json'].decode('utf-8'))
    if not report.get('asof'):
        print('ABORT: build_report.asof is empty')
        return 3
    if report.get('page_sha256') != sha256_file(os.path.join(a.dir, 'index.html')):
        print('ABORT: build_report.page_sha256 does not match index.html')
        return 3

    written, unchanged = [], []
    for name, rp, _min_size in PAIRS:
        data = local[name]
        cur = remote_sha(api, a.repo, rp, a.branch, token)
        if cur and cur == blob_sha(data):
            unchanged.append(rp)
            print('SKIP identical', rp)
            continue
        if a.dry_run:
            print('WOULD_PUT', rp, 'sha', blob_sha(data)[:10], 'remote', (cur or 'none')[:10])
            written.append(rp)
            continue
        payload = {
            'message': 'v2 3-step: %s asof=%s' % (rp, report['asof']),
            'content': base64.b64encode(data).decode('ascii'),
            'branch': a.branch,
        }
        if cur:
            payload['sha'] = cur
        url = '%s/repos/%s/contents/%s' % (api, a.repo, urllib.parse.quote(rp))
        r = gh(url, token, payload, 'PUT')
        print('PUT_OK', rp, 'commit=' + r['commit']['sha'][:10])
        written.append(rp)

    if not written:
        print('NO_CHANGE asof=%s' % report['asof'])
    else:
        print('UPLOAD PASS asof=%s files=%s' % (report['asof'], ','.join(written)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
