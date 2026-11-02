# -*- coding: utf-8 -*-
"""把 K 线数据转换成 FD-1 / P6 引擎可读的 cache_fresh 格式。

引擎读取的格式（每个标的一个 JSON 文件）：
  cache_fresh/AAPLUSDT.json = [
    {"time": "2026-11-01", "open": 345.1, "high": 348.0,
     "low": 342.2, "close": 346.5, "volume": 1234567.0},
    ...
  ]

支持输入：
  1. 一个 CSV 文件，列名大小写不敏感：
     symbol/time/open/high/low/close/volume
     （time 可以是 YYYY-MM-DD、ISO 时间或 Unix 秒；同一天多根会聚合成日线）
  2. 一个目录，里面是 *.csv / *.json / *.jsonl
  3. 已经是 cache 格式的 JSON 列表（每文件一个标的）
  4. JSONL：每行一个 bar，含 symbol 字段

用法：
  python systems/prepare_data.py --input /path/to/kline.csv --out cache_fresh
  python systems/prepare_data.py --input /path/to/kline_dir --out cache_fresh
  python systems/prepare_data.py --input /path/to/cache_fresh --out cache_fresh  # 只校验

然后：
  V2_CACHE=/abs/path/cache_fresh python systems/fd1/strategy.py
  V2_CACHE=/abs/path/cache_fresh python systems/p6/rs_scan.py

只依赖标准库，不需要 pandas。
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

FIELDS = ('open', 'high', 'low', 'close', 'volume')
ALIASES = {
    'symbol': ('symbol', 'ticker', 'sym', 'code', 'instrument'),
    'time': ('time', 'date', 'datetime', 'timestamp', 'ts', 'open_time'),
    'open': ('open', 'o'),
    'high': ('high', 'h'),
    'low': ('low', 'l'),
    'close': ('close', 'c'),
    'volume': ('volume', 'vol', 'v', 'basevolume', 'base_volume'),
}


def _pick(row, names):
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for n in names:
        if n in lower and lower[n] not in (None, ''):
            return lower[n]
    return None


def norm_symbol(raw):
    s = str(raw).strip().upper().replace('/', '').replace('-', '').replace('_', '')
    if not s:
        return None
    if s.endswith('USDT.P'):
        s = s[:-2]
    if not s.endswith('USDT'):
        s += 'USDT'
    return s


def parse_time(raw):
    """返回 (date_str, sort_key)。"""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    # Unix 秒 / 毫秒
    if s.replace('.', '', 1).isdigit():
        try:
            v = float(s)
            if v > 1e12:
                v /= 1000.0
            d = datetime.fromtimestamp(v, tz=timezone.utc)
            return d.strftime('%Y-%m-%d'), v
        except Exception:
            return None, None
    s2 = s.replace('T', ' ').replace('Z', '')
    head = s2[:10].replace('/', '-')
    try:
        d = datetime.strptime(head, '%Y-%m-%d')
    except Exception:
        return None, None
    return d.strftime('%Y-%m-%d'), s2


def norm_bar(row, symbol=None):
    sym = symbol or _pick(row, ALIASES['symbol'])
    sym = norm_symbol(sym) if sym else None
    t, sk = parse_time(_pick(row, ALIASES['time']))
    if not sym or not t:
        return None
    vals = {}
    for f in FIELDS:
        v = _pick(row, ALIASES[f])
        try:
            vals[f] = float(v)
        except Exception:
            return None
    if vals['close'] <= 0 or vals['open'] <= 0:
        return None
    if vals['high'] < max(vals['open'], vals['close'], vals['low']):
        vals['high'] = max(vals['open'], vals['close'], vals['low'])
    if vals['low'] > min(vals['open'], vals['close'], vals['high']):
        vals['low'] = min(vals['open'], vals['close'], vals['high'])
    vals['volume'] = max(vals['volume'], 0.0)
    return dict(symbol=sym, time=t, _sk=sk, **vals)


def aggregate(bars):
    """同一天多根 → 日线 OHLCV；不同天保持一根。"""
    by = {}
    for b in sorted(bars, key=lambda x: (x['time'], x['_sk'])):
        d = b['time']
        if d not in by:
            by[d] = dict(time=d, open=b['open'], high=b['high'],
                         low=b['low'], close=b['close'], volume=b['volume'])
        else:
            x = by[d]
            x['high'] = max(x['high'], b['high'])
            x['low'] = min(x['low'], b['low'])
            x['close'] = b['close']
            x['volume'] += b['volume']
    return [by[d] for d in sorted(by)]


def read_csv(path):
    out = defaultdict(list)
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            b = norm_bar(row)
            if b:
                out[b['symbol']].append(b)
    return out


def read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get('data') or data.get('bars') or data.get('klines') or []
    if not isinstance(data, list):
        return {}
    stem = os.path.splitext(os.path.basename(path))[0]
    out = defaultdict(list)
    for row in data:
        if isinstance(row, (list, tuple)) and len(row) >= 6:
            # [time, open, high, low, close, volume]
            row = dict(time=row[0], open=row[1], high=row[2], low=row[3],
                       close=row[4], volume=row[5])
        if not isinstance(row, dict):
            continue
        b = norm_bar(row, symbol=stem if not _pick(row, ALIASES['symbol']) else None)
        if b:
            out[b['symbol']].append(b)
    return out


def read_jsonl(path):
    out = defaultdict(list)
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                b = norm_bar(row)
                if b:
                    out[b['symbol']].append(b)
    return out


def collect(path):
    if os.path.isfile(path):
        low = path.lower()
        if low.endswith('.csv'):
            return read_csv(path)
        if low.endswith('.jsonl'):
            return read_jsonl(path)
        return read_json(path)
    merged = defaultdict(list)
    for name in sorted(os.listdir(path)):
        p = os.path.join(path, name)
        if not os.path.isfile(p):
            continue
        low = name.lower()
        if low.endswith('.csv'):
            part = read_csv(p)
        elif low.endswith('.jsonl'):
            part = read_jsonl(p)
        elif low.endswith('.json'):
            part = read_json(p)
        else:
            continue
        for k, v in part.items():
            merged[k].extend(v)
    return merged


def main():
    ap = argparse.ArgumentParser(description='K-line -> cache_fresh adapter')
    ap.add_argument('--input', required=True, help='CSV / JSON / JSONL / 目录')
    ap.add_argument('--out', default='cache_fresh', help='输出目录（默认 cache_fresh）')
    ap.add_argument('--min-bars', type=int, default=0, help='少于该根数的标的丢弃；0=保留')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print('ERROR: input not found:', args.input)
        return 2
    raw = collect(args.input)
    if not raw:
        print('ERROR: no valid bars found')
        return 2

    os.makedirs(args.out, exist_ok=True)
    total, kept = 0, 0
    counts = []
    for sym in sorted(raw):
        bars = aggregate(raw[sym])
        if len(bars) < args.min_bars:
            continue
        out = os.path.join(args.out, sym + '.json')
        with open(out, 'w', encoding='utf-8', newline='') as f:
            json.dump(bars, f, ensure_ascii=False, separators=(',', ':'))
        counts.append((sym, len(bars), bars[0]['time'], bars[-1]['time']))
        total += len(bars)
        kept += 1

    if not counts:
        print('ERROR: all symbols were filtered by --min-bars')
        return 2
    print('wrote %d symbols / %d bars -> %s' % (kept, total, os.path.abspath(args.out)))
    print('date range: %s .. %s' % (
        min(c[2] for c in counts), max(c[3] for c in counts)))
    short = [c for c in counts if c[1] < 260]
    for sym, n, d0, d1 in counts[:8]:
        print('  %-14s %5d bars  %s .. %s' % (sym, n, d0, d1))
    if len(counts) > 8:
        print('  ... %d more symbols' % (len(counts) - 8))
    if short:
        print('WARN: %d symbols have < 260 bars (warmup 210/220); '
              'they will produce no or few signals: %s' % (
                  len(short), ', '.join('%s(%d)' % (s, n) for s, n, _, _ in short[:8])))
    print('\nnext:')
    print('  V2_CACHE=%s python systems/fd1/strategy.py' % os.path.abspath(args.out))
    print('  V2_CACHE=%s python systems/p6/rs_scan.py' % os.path.abspath(args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
