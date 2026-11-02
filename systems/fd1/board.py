# -*- coding: utf-8 -*-
"""深踩快打 · 本地看板：生成 fastdip/index.html（不上线，只本地打开）。"""
import os, sys, json, hashlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(WORK, 'v2'), os.path.join(WORK, 'v2', 'engine'), HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
import v2_lib as L
from strategy import (load, state_today, recent_combined, levels,
                      SL_ATR, TP_ATR, HOLD, MARGIN_PCT, MAX_POS, LEV,
                      breakout_signals)

EQUITY0 = 10000


def stats_line(A, F, RG, cal):
    core = {s: b for s, b in A.items() if s not in L.ETF and s not in L.LEV}
    RGx = dict(RG); RGx['gate'] = np.ones(len(cal), bool); RGx['gate100'] = RGx['gate']
    p = dict(require_gate=False, gate_mode='ma50', trend_ma=100, slope_min=0.0,
             dev20_max=-0.05, rsi2_max=30, ret3_max=9.9, atrp_max=0.06,
             min_dv=30e6, min_price=5, warmup=210, score='rsi', tier='F',
             sig_exit=dict(sl_atr=SL_ATR, tp_atr=TP_ATR, hold=HOLD))
    BR = L.breadth(core, F, cal)[0]
    sig0 = L.make_signals(core, F, RGx, BR, p)
    brk = breakout_signals(core, F, cal)
    sig = [dict(x) for x in sig0]
    for x in sig:
        x['score'] += 1000.0
    combo = sorted(sig + brk, key=lambda x: (x['i'], -x['score']))
    simd = L.simulate(core, F, RGx, combo,
                      dict(lev=LEV, margin_pct=MARGIN_PCT, max_pos=MAX_POS, gross_cap=2.5,
                           sl_atr=SL_ATR, tp_atr=TP_ATR, hold=HOLD))
    simo = L.simulate(core, F, RGx, sig0,
                      dict(lev=LEV, margin_pct=MARGIN_PCT, max_pos=MAX_POS, gross_cap=2.5,
                           sl_atr=SL_ATR, tp_atr=TP_ATR, hold=HOLD))
    i0 = next(i for i, d in enumerate(cal) if d >= '2026-01-26')

    def b(s):
        return dict(n=s['n'], win=round(s['win'], 1), pf=round(s['pf'], 2),
                    cagr=round(s['cagr'], 1), mdd=round(s['mdd'], 2))

    return dict(full=b(L.stats(simd, 220)), real=b(L.stats(simd, i0)),
                orig_full=b(L.stats(simo, 220)), orig_real=b(L.stats(simo, i0)),
                n_brk=len(brk))


def fmt_row(x, equity, asof, channel):
    atr = x['atr']
    e = x['close']
    stop, tp = e - SL_ATR * atr, e + TP_ATR * atr
    notional = equity * MARGIN_PCT * LEV
    qty = notional / e
    expiry = (date.fromisoformat(asof) + timedelta(days=HOLD)).isoformat()
    d = dict(sym=x['sym'], close=e, atr=atr, stop=stop, tp=tp, qty=qty,
             margin=equity * MARGIN_PCT, notional=notional, expiry=expiry,
             risk_pct=(stop / e - 1) * 100 * LEV * MARGIN_PCT * -1, channel=channel)
    if channel == 'deep':
        d.update(rsi2=x['rsi2'], dev20=x['dev20'])
    else:
        d.update(volx=x['volx'], hi20=x['hi20'])
    return d


HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>深踩快打 · FD-1 双通道 本地看板</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--line:#26303d;--txt:#d7dee8;--dim:#8b98a9;--pos:#3fb950;--neg:#f85149;--acc:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:26px 22px 60px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:26px 0 10px;color:#c9d4e2}
.sub{color:var(--dim);font-size:12px;margin-bottom:18px}
.row{display:flex;gap:22px;flex-wrap:wrap}.kv b{display:block;font-size:18px}.kv span{font-size:12px;color:var(--dim)}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{color:var(--dim);font-weight:500;text-align:right}td:first-child,th:first-child{text-align:left}
.pos{color:var(--pos)}.neg{color:var(--neg)}.ch{color:var(--acc)}
.hint{color:var(--dim);font-size:12px;margin-top:8px}
ul{margin:6px 0 0;padding-left:20px;color:#c7d1dc;font-size:13px}li{margin:3px 0}
input{background:#0b0f14;border:1px solid var(--line);color:var(--txt);padding:4px 8px;border-radius:6px;width:110px}
</style></head><body><div class="wrap">
<h1>深踩快打 · FD-1 双通道 <span style="font-size:12px;color:var(--dim)">本地看板 · 未上线</span></h1>
<div class="sub">数据截至 __ASOF__ ｜ 生成于 __BUILT__ ｜ 通道 A 深踩 + 通道 B 20 日新高放量突破，共用 0.8/1.5/5 出口</div>
<div class="row">
  <div class="kv"><b>__NDEEP__ / __NBRK__</b><span>今日候选（深踩 / 突破）</span></div>
  <div class="kv"><b>__FULL__</b><span>双通道全样本（笔 / 胜率 / PF）</span></div>
  <div class="kv"><b>__REAL__</b><span>双通道 2026-01-26 起</span></div>
  <div class="kv"><b>__ORIG__</b><span>原版深踩对照（笔 / 胜率 / PF）</span></div>
  <div class="kv"><b>__EQUITY__</b><span>权益（可改）</span></div>
</div>

<h2>通道 A · 深踩候选</h2>
__TABLE_DEEP__

<h2>通道 B · 20 日新高放量突破</h2>
__TABLE_BRK__

<h2>最近成交</h2>
__RECENT__

<h2>规则（2026-11-03 双通道版）</h2>
<ul>
<li><b>通道 A 深踩</b>：收盘 &gt; MA100 且 MA100 20 日斜率 ≥ 0；20 日偏离 ≤ −5%；RSI2 ≤ 30；价格 ≥ 5、20 日均额 ≥ 3000 万、ATR% ≤ 6%。</li>
<li><b>通道 B 突破</b>：收盘 &gt; 过去 20 根收盘最高（不含当日）；当日量 ≥ 2.0 × 过去 20 日中位量；收盘 &gt; MA100 且斜率 ≥ 0；价格 ≥ 5、20 日均额 ≥ 3000 万、ATR% ≤ 6%；同一标的 10 根内只取第一次。</li>
<li><b>出场</b>：+0.8 ATR 止盈、−1.5 ATR 止损（跳空按开盘价）、最多 5 根日线。</li>
<li><b>仓位</b>：5x 逐仓、单笔保证金 3% 权益、最多 16 仓、毛敞口 2.5 倍。</li>
<li><b>统计</b>：双通道 __NP__ 笔 / 胜率 __WIN__ / PF __PF__ / 年化 __CAGR__ / 回撤 __MDD__；2026 段 __R26__；原版深踩对照 __O26__。</li>
<li>本页只本地生成，不提交、不发布；每天收盘后重跑一次。</li>
</ul>
<p class="hint">止损 = E − 1.5×ATR；止盈 = E + 0.8×ATR；数量 = 名义 / E，名义 = 权益 × 3% × 5；到期 = 入场日 + 5 天按收盘平。</p>
</div></body></html>"""


def main():
    A, F, RG, cal = load()
    st = state_today(A, F, RG, cal)
    stats = stats_line(A, F, RG, cal)
    equity = EQUITY0

    rows_deep = [fmt_row(x, equity, st['asof'], 'deep') for x in st['deep']]
    rows_brk = [fmt_row(x, equity, st['asof'], 'brk') for x in st['brk']]

    if rows_deep:
        head = ('<table><thead><tr><th>标的</th><th>收盘 / E</th><th>ATR</th><th>RSI2</th>'
                '<th>20日偏离</th><th>止损</th><th>止盈</th><th>数量</th><th>保证金</th>'
                '<th>名义</th><th>止损占权益</th><th>到期</th></tr></thead><tbody>')
        body = []
        for r in rows_deep:
            body.append('<tr><td>%s</td><td>%.2f</td><td>%.2f</td><td>%.1f</td><td class="neg">%+.1f%%</td>'
                        '<td class="neg">%.2f</td><td class="pos">%.2f</td><td>%.2f</td><td>%.0f</td>'
                        '<td>%.0f</td><td class="neg">%.2f%%</td><td>%s</td></tr>' % (
                            r['sym'], r['close'], r['atr'], r['rsi2'], r['dev20'] * 100,
                            r['stop'], r['tp'], r['qty'], r['margin'], r['notional'],
                            r['risk_pct'], r['expiry']))
        table_deep = head + ''.join(body) + '</tbody></table>'
    else:
        table_deep = ('<p class="hint">今日无深踩候选：没有同时满足「站上 MA100 + 20 日偏离≤−5%'
                      ' + RSI2≤30 + 30M 成交额」的标的。</p>')

    if rows_brk:
        head = ('<table><thead><tr><th>标的</th><th>收盘 / E</th><th>ATR</th><th>量比</th>'
                '<th>20日高</th><th>止损</th><th>止盈</th><th>数量</th><th>保证金</th>'
                '<th>名义</th><th>止损占权益</th><th>到期</th></tr></thead><tbody>')
        body = []
        for r in rows_brk:
            body.append('<tr><td>%s</td><td>%.2f</td><td>%.2f</td><td class="pos">%.2fx</td>'
                        '<td>%.2f</td><td class="neg">%.2f</td><td class="pos">%.2f</td><td>%.2f</td>'
                        '<td>%.0f</td><td>%.0f</td><td class="neg">%.2f%%</td><td>%s</td></tr>' % (
                            r['sym'], r['close'], r['atr'], r['volx'], r['hi20'],
                            r['stop'], r['tp'], r['qty'], r['margin'], r['notional'],
                            r['risk_pct'], r['expiry']))
        table_brk = head + ''.join(body) + '</tbody></table>'
    else:
        table_brk = ('<p class="hint">今日无突破候选：没有同时满足「20 日新高 + 2 倍量能'
                     ' + MA100/斜率 + 30M 成交额」的标的。</p>')

    rec = recent_combined(A, F, RG, cal, 12, per_channel=True)
    rb = ['<table><thead><tr><th>信号日</th><th>通道</th><th>标的</th><th>入场</th><th>止损</th>'
          '<th>止盈</th><th>结果</th><th>退出</th><th>持有</th></tr></thead><tbody>']
    for t in rec:
        cls = 'pos' if t['pnl'] > 0 else 'neg'
        rb.append('<tr><td>%s</td><td class="ch">%s</td><td>%s</td><td>%.2f</td><td>%.2f</td>'
                  '<td>%.2f</td><td class="%s">%+.2f%%</td><td>%s</td><td>%d 根</td></tr>' % (
                      t['date'], t['channel'], t['sym'], t['entry'], t['levels']['stop'],
                      t['levels']['tp'], cls, t['pnl'] * 100, t['why'], t['bars']))
    recent = ''.join(rb) + '</tbody></table>'

    f = stats['full']; r = stats['real']; o = stats['orig_full']
    html = (HTML.replace('__ASOF__', st['asof']).replace('__BUILT__', __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'))
            .replace('__NDEEP__', str(st['n_deep'])).replace('__NBRK__', str(st['n_brk']))
            .replace('__FULL__', '%d 笔 / %.1f%% / %.2f' % (f['n'], f['win'], f['pf']))
            .replace('__REAL__', '%d 笔 / %.1f%% / %.2f' % (r['n'], r['win'], r['pf']))
            .replace('__ORIG__', '%d 笔 / %.1f%% / %.2f' % (o['n'], o['win'], o['pf']))
            .replace('__EQUITY__', '%.0f' % equity)
            .replace('__TABLE_DEEP__', table_deep).replace('__TABLE_BRK__', table_brk)
            .replace('__RECENT__', recent)
            .replace('__NP__', str(f['n'])).replace('__WIN__', '%.1f%%' % f['win'])
            .replace('__PF__', '%.2f' % f['pf']).replace('__CAGR__', '%.1f%%' % f['cagr'])
            .replace('__MDD__', '%.2f%%' % f['mdd'])
            .replace('__R26__', '%d 笔 / %.1f%% / PF %.2f / 年化 %.1f%% / 回撤 %.2f%%' % (
                r['n'], r['win'], r['pf'], r['cagr'], r['mdd']))
            .replace('__O26__', '%d 笔 / %.1f%% / PF %.2f / 年化 %.1f%% / 回撤 %.2f%%' % (
                o['n'], o['win'], o['pf'], o['cagr'], o['mdd'])))
    out = os.path.join(HERE, 'index.html')
    open(out, 'w', encoding='utf-8', newline='').write(html)

    # 前向记录：同一 asof 只保留最后一次
    logp = os.path.join(HERE, 'forward_log.jsonl')
    recs = []
    if os.path.exists(logp):
        for line in open(logp, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get('asof') != st['asof']:
                recs.append(row)
    recs.append(dict(asof=st['asof'],
                     built_at=__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
                     deep=[dict(sym=r['sym'], e=round(r['close'], 4), stop=round(r['stop'], 4),
                                tp=round(r['tp'], 4), atr=round(r['atr'], 4)) for r in rows_deep],
                     brk=[dict(sym=r['sym'], e=round(r['close'], 4), stop=round(r['stop'], 4),
                               tp=round(r['tp'], 4), atr=round(r['atr'], 4)) for r in rows_brk]))
    recs.sort(key=lambda r: r['asof'])
    with open(logp, 'w', encoding='utf-8') as fh:
        for row in recs:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')

    rep = dict(asof=st['asof'],
               built_at=__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
               n_deep=st['n_deep'], n_brk=st['n_brk'],
               deep_candidates=[x['sym'] for x in st['deep']],
               brk_candidates=[x['sym'] for x in st['brk']],
               stats=stats, page_sha256=hashlib.sha256(html.encode('utf-8')).hexdigest(),
               page_bytes=len(html.encode('utf-8')))
    json.dump(rep, open(os.path.join(HERE, 'build_report.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('wrote', out, rep['page_bytes'], 'bytes ｜ asof', st['asof'],
          '｜ 深踩', st['n_deep'], '突破', st['n_brk'])


if __name__ == '__main__':
    main()
