# -*- coding: utf-8 -*-
"""单兵 P6 · 本地看板：生成 index.html（只研究，不下单，不发布）。

规则与 rs_scan.py / rs_lab.py 完全一致：
  趋势：收盘 > MA50 > MA100，MA50 10 日斜率 >= 0，MA100 20 日斜率 >= 0
  强度：20 日收益 > 0（绝对强度，不要求跑赢指数）
  量能：信号日成交量 >= 1.5 × 20 日中位量
  过滤：价格 >= 5、20 日均额 >= 30M、ATR% <= 6%
  出场：+0.8 ATR 止盈、-1.8 ATR 止损（跳空按开盘）、最多 7 根日线
  仓位：5x、单笔保证金 3% 权益、最多 16 仓、毛敞口 2.5 倍、同日最多 5 仓

统计口径：组合持仓（不是信号），补止盈/止损跳空开盘价、逐日盯市回撤、日历日年化。
"""
import os
import sys
import json
import hashlib
import datetime
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
ROOT = os.path.dirname(WORK)
if not os.environ.get('V2_CACHE'):
    for _cand in (os.path.join(ROOT, 'cache_fresh'),
                  os.path.join(os.path.dirname(ROOT), 'cache_fresh')):
        if os.path.isdir(_cand):
            os.environ['V2_CACHE'] = _cand
            break
for _p in (os.path.join(ROOT, 'v2', 'engine'), os.path.join(WORK, 'fd1'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import rs_lab as RS

COST, FUND, LEV = 0.001, 0.0003, 5.0
MARGIN, MAXPOS, GROSS, CAPDAY = 0.03, 16, 2.5, 5
SL_ATR, TP_ATR, HOLD = 1.8, 0.8, 7
VOLX = 1.5
MIN_DV = 30e6
ATR_MAX = 0.06
EQUITY0 = 10000
START_REAL = '2025-06-01'

CSS = """
:root{--bg:#0d1117;--panel:#161b22;--line:#26303d;--txt:#d7dee8;--dim:#8b98a9;--pos:#3fb950;--neg:#f85149;--acc:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:26px 22px 60px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:26px 0 10px;color:#c9d4e2}
.sub{color:var(--dim);font-size:12px;margin-bottom:18px}
.row{display:flex;gap:22px;flex-wrap:wrap}.kv b{display:block;font-size:18px}.kv span{font-size:12px;color:var(--dim)}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{color:var(--dim);font-weight:500;text-align:right}td:first-child,th:first-child{text-align:left}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.hint{color:var(--dim);font-size:12px;margin-top:8px}
ul{margin:6px 0 0;padding-left:20px;color:#c7d1dc;font-size:13px}li{margin:3px 0}
input{background:#0b0f14;border:1px solid var(--line);color:var(--txt);padding:4px 8px;border-radius:6px;width:110px}
"""

HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>单兵 P6 · 本地看板</title>
<style>__CSS__</style></head><body><div class="wrap">
<h1>单兵 P6 v2 · 本地看板 <span style="font-size:12px;color:var(--dim)">只研究 · 不下单 · 未上线</span></h1>
<div class="sub">数据截至 __ASOF__ ｜ 生成于 __BUILT__ ｜ 趋势 + 20 日强度 + 量比≥1.5 ｜ 止损 1.8 ATR / 止盈 0.8 ATR / 持有 7 根 ｜ 收盘出信号，次日开盘成交；E 用收盘价预估</div>
<div class="row">
  <div class="kv"><b>__NCAND__</b><span>今日候选</span></div>
  <div class="kv"><b>__FULL__</b><span>全样本（笔 / 胜率 / PF）</span></div>
  <div class="kv"><b>__REAL__</b><span>2025-06-01 起（笔 / 胜率 / PF）</span></div>
  <div class="kv"><b><input id="eq" value="__EQUITY__" inputmode="decimal"></b><span>权益 USDT（可改）</span></div>
</div>

__TABLE__

<h2>统计（组合持仓口径）</h2>
__STATS__

<h2>量能未达标（趋势和强度都过，但成交量 &lt; 1.5×20 日中位量）</h2>
__WATCH__

<h2>最近成交</h2>
__RECENT__

<h2>规则（与 rs_scan.py 一致）</h2>
<ul>
<li>趋势：收盘 &gt; MA50 &gt; MA100；MA50 10 日斜率 ≥ 0；MA100 20 日斜率 ≥ 0；20 日收益 &gt; 0（绝对强度，不要求跑赢指数）。</li>
<li>量能：信号日成交量 ≥ 1.5 × 20 日中位量。</li>
<li>过滤：价格 ≥ 5、20 日均额 ≥ 3000 万、ATR% ≤ 6%。无市场闸门、无批次要求。</li>
<li>出场：+0.8 ATR 止盈、−1.8 ATR 止损（跳空按开盘价），最多持有 7 根日线。</li>
<li>仓位：5x 逐仓、单笔保证金 3% 权益、最多 16 仓、毛敞口 2.5 倍、同日最多 5 仓。</li>
<li>本页只本地生成，不提交、不发布；P6 仍是研究项，不进入实盘执行。</li>
</ul>
<p class="hint">止损 = E − 1.8×ATR；止盈 = E + 0.8×ATR；数量 = 名义 / E，名义 = 权益 × 3% × 5；持有 7 根日线后按收盘平。统计含止盈/止损跳空和逐日盯市。</p>
</div>
<script>
var eq=document.getElementById('eq');
function calc(){var v=parseFloat(eq.value)||0;document.querySelectorAll('tr[data-e]').forEach(function(tr){
 var e=parseFloat(tr.getAttribute('data-e'));if(!e)return;var n=v*0.15;
 tr.querySelector('.qty').textContent=(n/e).toFixed(2);
 tr.querySelector('.margin').textContent=(v*0.03).toFixed(0);
 tr.querySelector('.notional').textContent=n.toFixed(0);});}
eq.addEventListener('input',calc);calc();
</script>
</body></html>"""


def sim_gap(b, i, atr, sl=SL_ATR, tp=TP_ATR, hold=HOLD):
    n = len(b['c']); e = i + 1
    if e >= n or not b['real'][e] or b['jump'][e]:
        return None
    ep = b['o'][e]
    if ep <= 0:
        return None
    stop, tgt = ep - sl * atr, ep + tp * atr
    end = min(n - 1, e + hold)
    fund = 0.0
    for k in range(e, end + 1):
        if b['jump'][k]:
            continue
        fund += FUND
        if k > e:
            if b['o'][k] <= stop:
                return dict(pnl=b['o'][k] / ep - 1 - 2 * COST - fund, why='stop_gap', bars=k - e, entry=e, exitp=b['o'][k])
            if b['o'][k] >= tgt:
                return dict(pnl=b['o'][k] / ep - 1 - 2 * COST - fund, why='tp_gap', bars=k - e, entry=e, exitp=b['o'][k])
        if b['l'][k] <= stop:
            return dict(pnl=stop / ep - 1 - 2 * COST - fund, why='stop', bars=k - e, entry=e, exitp=stop)
        if b['h'][k] >= tgt:
            return dict(pnl=tgt / ep - 1 - 2 * COST - fund, why='tp', bars=k - e, entry=e, exitp=tgt)
    return dict(pnl=b['c'][end] / ep - 1 - 2 * COST - fund, why='time', bars=end - e, entry=e, exitp=b['c'][end])


def run_port(A, cal, events, start_i):
    by = {}
    for x in events:
        if x['i'] >= start_i:
            by.setdefault(x['i'], []).append(x)
    eq = 1.0
    curve = np.full(len(cal), np.nan)
    pos = {}
    trades = []
    skips = Counter()
    for i in range(start_i, len(cal)):
        for s in list(pos):
            q = pos[s]; b = A[s]
            if i < q['e'] or b['jump'][i]:
                continue
            ep, stop, tgt = q['ep'], q['stop'], q['tgt']
            done = None
            if i > q['e'] and b['o'][i] <= stop:
                done = (b['o'][i] / ep - 1, 'stop_gap', b['o'][i])
            elif i > q['e'] and b['o'][i] >= tgt:
                done = (b['o'][i] / ep - 1, 'tp_gap', b['o'][i])
            elif b['l'][i] <= stop:
                done = (stop / ep - 1, 'stop', stop)
            elif b['h'][i] >= tgt:
                done = (tgt / ep - 1, 'tp', tgt)
            elif i >= q['e'] + HOLD:
                done = (b['c'][i] / ep - 1, 'time', b['c'][i])
            if done:
                r, why, xp = done
                pnl = q['notional'] * r - q['notional'] * 2 * COST - q['notional'] * FUND * (i - q['e'])
                eq += pnl
                trades.append(dict(sym=s, e=q['e'], x=i, ep=q['ep'], xp=xp, pnl=pnl, why=why))
                pos.pop(s)
        mtm = 0.0
        for s, q in pos.items():
            b = A[s]; cp = b['c'][i]
            mtm += q['notional'] * (cp / q['ep'] - 1) - q['notional'] * 2 * COST - q['notional'] * FUND * (i - q['e'])
        curve[i] = eq + mtm
        if i in by:
            used = 0
            for x in sorted(by[i], key=lambda z: z['score']):
                if len(pos) >= MAXPOS:
                    skips['maxpos'] += 1; break
                if used >= CAPDAY:
                    skips['capday'] += 1; break
                s = x['sym']
                if s in pos:
                    skips['already'] += 1; continue
                e = i + 1
                if e >= len(cal) or not A[s]['real'][e] or A[s]['jump'][e]:
                    skips['invalid'] += 1; continue
                ep = A[s]['o'][e]
                if ep <= 0:
                    skips['badpx'] += 1; continue
                notional = MARGIN * eq * LEV
                if sum(q['notional'] for q in pos.values()) + notional > GROSS * eq:
                    skips['gross'] += 1; continue
                pos[s] = dict(e=e, ep=ep, stop=ep - SL_ATR * x['atr'], tgt=ep + TP_ATR * x['atr'], notional=notional)
                used += 1
    if pos:
        i = len(cal) - 1
        for s, q in list(pos.items()):
            cp = A[s]['c'][i]
            pnl = q['notional'] * (cp / q['ep'] - 1) - q['notional'] * 2 * COST - q['notional'] * FUND * (i - q['e'])
            eq += pnl
            trades.append(dict(sym=s, e=q['e'], x=i, ep=q['ep'], xp=cp, pnl=pnl, why='eod'))
            pos.pop(s)
        curve[i] = eq
    cv = curve[start_i:]
    final = float(cv[-1])
    peak = np.maximum.accumulate(cv)
    mdd = float((cv / peak - 1).min() * 100)
    days = (datetime.date.fromisoformat(cal[-1]) - datetime.date.fromisoformat(cal[start_i])).days
    cagr = (final ** (365.0 / days) - 1) * 100
    p = np.array([t['pnl'] for t in trades]) if trades else np.array([0.0])
    w, l = p[p > 0], p[p <= 0]
    return dict(
        n=len(trades), win=round(float((p > 0).mean() * 100), 1) if trades else 0.0,
        pf=round(float(w.sum() / max(-l.sum(), 1e-9)), 2) if trades else 0.0,
        cagr=round(float(cagr), 1), mdd=round(mdd, 2), final=round(final, 4),
        total=round((final - 1) * 100, 1), pm=round(len(trades) / (days / 30.44), 1),
        payoff=round(float(w.mean() / abs(l.mean())), 2) if len(w) and len(l) else 0.0,
        exit=dict(Counter(t['why'] for t in trades)), trades=trades)


def _row_at(A, F, s, i):
    b = A[s]
    if s in RS.L.ETF or s in RS.L.LEV:
        return None
    if not b['real'][i] or i - b['first'] < 220 or b['jump'][i]:
        return None
    f = F[s]
    c = float(b['c'][i])
    if c < 5 or f['dv20'][i] < MIN_DV:
        return None
    if np.isnan(f['atrp'][i]) or f['atrp'][i] > ATR_MAX:
        return None
    ma50, ma100 = f['ma50'][i], f['ma100'][i]
    if np.isnan(ma50) or np.isnan(ma100) or np.isnan(f['slope100'][i]):
        return None
    if i < 10 or np.isnan(f['ma50'][i - 10]):
        return None
    ms50 = ma50 / f['ma50'][i - 10] - 1
    if np.isnan(ms50) or not (c > ma50 > ma100) or ms50 < 0 or f['slope100'][i] < 0:
        return None
    if f['ret20'][i] <= 0:
        return None
    vm = float(np.median(b['v'][max(0, i - 20):i]))
    if vm <= 0:
        return None
    vr = float(b['v'][i] / vm)
    return dict(sym=s, close=c, atr=float(f['atr'][i]), rsi2=float(f['rsi2'][i]),
                dev20=float(f['dev20'][i]), ret20=float(f['ret20'][i]),
                atrp=float(f['atrp'][i]), ma20=float(f['ma20'][i]), volx=vr)


def scan_now(A, F, RG, cal):
    i = len(cal) - 1
    out, watch = [], []
    for s in A:
        row = _row_at(A, F, s, i)
        if row is None:
            continue
        if row['volx'] < VOLX:
            watch.append(row)
            continue
        prev = _row_at(A, F, s, i - 1) if i >= 1 else None
        if prev is not None and prev['volx'] >= VOLX:
            continue
        out.append(row)
    out.sort(key=lambda x: x['rsi2'])
    watch.sort(key=lambda x: -x['volx'])
    return out, watch


def build_events_v2(A, F, RG, cal):
    """P6 v2: first day the trend + ret20 + volume state turns true.

    One trade per up-episode; no re-entry until the state resets.
    """
    n = len(cal)
    out = []
    prev = {}
    for i in range(230, n - 1):
        for s, b in A.items():
            ok = False
            if (s not in RS.L.ETF and s not in RS.L.LEV and b['real'][i]
                    and i - b['first'] >= 220 and not b['jump'][i]):
                f = F[s]
                c = float(b['c'][i])
                if c >= 5 and f['dv20'][i] >= MIN_DV:
                    if not np.isnan(f['atrp'][i]) and f['atrp'][i] <= ATR_MAX:
                        ma50, ma100 = f['ma50'][i], f['ma100'][i]
                        if (not np.isnan(ma50) and not np.isnan(ma100)
                                and not np.isnan(f['slope100'][i])
                                and i >= 10 and not np.isnan(f['ma50'][i - 10])):
                            ms50 = ma50 / f['ma50'][i - 10] - 1
                            if (c > ma50 > ma100 and ms50 >= 0 and f['slope100'][i] >= 0
                                    and f['ret20'][i] > 0):
                                vm = float(np.median(b['v'][max(0, i - 20):i]))
                                if vm > 0 and b['v'][i] >= VOLX * vm:
                                    ok = True
            was = prev.get(s, False)
            prev[s] = ok
            if ok and not was:
                f = F[s]
                out.append(dict(i=i, sym=s, score=float(f['rsi2'][i]), atr=float(f['atr'][i])))
    return out


def fmt_pct(x, digits=1):
    return ('%+.' + str(digits) + 'f%%') % (x * 100)


def main():
    A, F, RG, cal = RS.load()
    asof = cal[-1]
    built = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    ev = build_events_v2(A, F, RG, cal)
    i_real = next(i for i, d in enumerate(cal) if d >= START_REAL)
    full = run_port(A, cal, ev, 220)
    real = run_port(A, cal, ev, i_real)
    cand, watch = scan_now(A, F, RG, cal)

    rows = []
    for x in cand:
        e = x['close']
        stop, tp = e - SL_ATR * x['atr'], e + TP_ATR * x['atr']
        rows.append(dict(sym=x['sym'], close=e, atr=x['atr'], volx=x['volx'], rsi2=x['rsi2'],
                         dev20=x['dev20'], stop=stop, tp=tp,
                         risk_pct=(1 - stop / e) * LEV * MARGIN * 100))
    if rows:
        tb = ['<table><thead><tr><th>标的</th><th>收盘 / E</th><th>ATR</th><th>量比</th>'
              '<th>止损</th><th>止盈</th><th>数量</th><th>保证金</th>'
              '<th>名义</th><th>止损占权益</th><th>持有</th></tr></thead><tbody>']
        for r in rows:
            tb.append('<tr data-e="%.6f"><td>%s</td><td>%.2f</td><td>%.2f</td><td>%.1f×</td>'
                      '<td class="neg">%.2f</td><td class="pos">%.2f</td>'
                      '<td class="qty">%.2f</td><td class="margin">%.0f</td>'
                      '<td class="notional">%.0f</td><td class="neg">%.2f%%</td><td>7 根日线</td></tr>' % (
                          r['close'], r['sym'], r['close'], r['atr'], r['volx'],
                          r['stop'], r['tp'], EQUITY0 * 0.15 / r['close'], EQUITY0 * 0.03,
                          EQUITY0 * 0.15, r['risk_pct']))
        table = ''.join(tb) + '</tbody></table>'
    else:
        table = '<p class="hint">今日无候选：没有同时满足「趋势 + 20 日绝对强度 + 量比≥1.5」的标的。</p>'

    if watch:
        wb = ['<table><thead><tr><th>标的</th><th>收盘</th><th>20日</th><th>20日偏离</th>'
              '<th>RSI2</th><th>ATR%</th><th>量比</th></tr></thead><tbody>']
        for x in watch[:12]:
            wb.append('<tr><td>%s</td><td>%.2f</td><td class="pos">%s</td><td>%s</td><td>%.1f</td>'
                      '<td>%.1f%%</td><td class="neg">%.2f×</td></tr>' % (
                          x['sym'], x['close'], fmt_pct(x['ret20']), fmt_pct(x['dev20']),
                          x['rsi2'], x['atrp'] * 100, x['volx']))
        watch_html = ''.join(wb) + '</tbody></table>'
    else:
        watch_html = '<p class="hint">当前没有量能不足的观察标的。</p>'

    recent = sorted(real['trades'], key=lambda t: (t['x'], t['sym']))[-10:][::-1]
    if recent:
        rb = ['<table><thead><tr><th>信号日</th><th>入场日</th><th>标的</th><th>入场价</th>'
              '<th>出场日</th><th>出场价</th><th>净收益</th><th>退出</th><th>持有</th></tr></thead><tbody>']
        for t in recent:
            cls = 'pos' if t['pnl'] > 0 else 'neg'
            why = {'tp': '止盈', 'tp_gap': '跳空止盈', 'stop': '止损', 'stop_gap': '跳空止损',
                   'time': '到期', 'eod': '期末平'}.get(t['why'], t['why'])
            rb.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%.2f</td><td>%s</td><td>%.2f</td>'
                      '<td class="%s">%+.2f%%</td><td>%s</td><td>%d 根</td></tr>' % (
                          cal[t['e'] - 1], cal[t['e']], t['sym'], t['ep'], cal[t['x']], t['xp'],
                          cls, t['pnl'] * 100, why, t['x'] - t['e']))
        recent_html = ''.join(rb) + '</tbody></table>'
    else:
        recent_html = '<p class="hint">该窗口内没有已平仓交易。</p>'

    sb = ['<table><thead><tr><th>口径</th><th>笔数</th><th>笔/月</th><th>胜率</th><th>PF</th>'
          '<th>区间收益</th><th>年化</th><th>最大回撤</th><th>平均盈亏比</th></tr></thead><tbody>']
    for label, s in (('全样本', full), ('2025-06-01 起', real)):
        sb.append('<tr><td>%s</td><td>%d</td><td>%.1f</td><td>%.1f%%</td><td>%.2f</td>'
                  '<td class="%s">%+.1f%%</td><td>%+.1f%%</td><td class="neg">%.2f%%</td><td>%.2f</td></tr>' % (
                      label, s['n'], s['pm'], s['win'], s['pf'], 'pos' if s['total'] > 0 else 'neg',
                      s['total'], s['cagr'], s['mdd'], s['payoff']))
    stats_html = ''.join(sb) + '</tbody></table>'

    html = (HTML.replace('__CSS__', CSS).replace('__ASOF__', asof).replace('__BUILT__', built)
            .replace('__NCAND__', str(len(rows)))
            .replace('__FULL__', '%d 笔 / %.1f%% / %.2f' % (full['n'], full['win'], full['pf']))
            .replace('__REAL__', '%d 笔 / %.1f%% / %.2f' % (real['n'], real['win'], real['pf']))
            .replace('__EQUITY__', '%.0f' % EQUITY0)
            .replace('__TABLE__', table).replace('__STATS__', stats_html)
            .replace('__WATCH__', watch_html).replace('__RECENT__', recent_html))
    out = os.path.join(HERE, 'index.html')
    with open(out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(html)
    blob = html.encode('utf-8')
    rep = dict(asof=asof, built_at=built, n_candidates=len(rows),
               candidates=[x['sym'] for x in rows],
               stats=dict(full={k: full[k] for k in ('n', 'win', 'pf', 'cagr', 'mdd', 'pm', 'total')},
                          since202506={k: real[k] for k in ('n', 'win', 'pf', 'cagr', 'mdd', 'pm', 'total')}),
               page_sha256=hashlib.sha256(blob).hexdigest(), page_bytes=len(blob))
    with open(os.path.join(HERE, 'build_report.json'), 'w', encoding='utf-8') as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    logp = os.path.join(HERE, 'forward_log.jsonl')
    recs = []
    if os.path.exists(logp):
        for line in open(logp, encoding='utf-8'):
            line = line.strip()
            if line:
                r0 = json.loads(line)
                if r0.get('asof') != asof:
                    recs.append(r0)
    recs.append(dict(asof=asof, built_at=built,
                     candidates=[dict(sym=x['sym'], e=round(x['close'], 4), stop=round(x['stop'], 4),
                                      tp=round(x['tp'], 4), atr=round(x['atr'], 4),
                                      volx=round(x['volx'], 2)) for x in rows]))
    recs.sort(key=lambda r: r['asof'])
    with open(logp, 'w', encoding='utf-8') as fh:
        for r0 in recs:
            fh.write(json.dumps(r0, ensure_ascii=False) + '\n')
    print('wrote %s %d bytes | asof %s | 候选 %d | 全样本 %d 笔 / %.1f%% / PF %.2f | 2025-06 起 %d 笔 / %.1f%% / PF %.2f / CAGR %.1f%% / MDD %.2f%%'
          % (out, len(blob), asof, len(rows), full['n'], full['win'], full['pf'],
             real['n'], real['win'], real['pf'], real['cagr'], real['mdd']))


if __name__ == '__main__':
    main()
