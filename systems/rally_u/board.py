# -*- coding: utf-8 -*-
"""U 平衡 + 集群 A≥3 且 B≥20 · 本地看板（只本地生成，不发布）。

跑法：
  V2_CACHE=<work>/cache_fresh python board.py
输出：
  index.html / build_report.json / forward_log.jsonl
"""
import os
import sys
import json
import hashlib
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import u_engine as U

EQ = 100000.0
WINDOWS = ['2026-01-26', '2026-05-01', '2026-08-01']

HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>U 平衡 · 起涨点 本地看板</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--line:#26303d;--txt:#d7dee8;--dim:#8b98a9;--pos:#3fb950;--neg:#f85149;--acc:#58a6ff;--warn:#d29922}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:26px 22px 60px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:26px 0 10px;color:#c9d4e2}
.sub{color:var(--dim);font-size:12px;margin-bottom:18px}
.row{display:flex;gap:22px;flex-wrap:wrap}.kv b{display:block;font-size:18px}.kv span{font-size:12px;color:var(--dim)}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{color:var(--dim);font-weight:500}td:first-child,th:first-child{text-align:left}
.pos{color:var(--pos)}.neg{color:var(--neg)}.acc{color:var(--acc)}.warn{color:var(--warn)}
.hint{color:var(--dim);font-size:12px;margin-top:8px}
ul{margin:6px 0 0;padding-left:20px;color:#c7d1dc;font-size:13px}li{margin:3px 0}
</style></head><body><div class="wrap">
<h1>U 平衡 · 集群 A≥__CA__ 且 B≥__CB__ <span style="font-size:12px;color:var(--dim)">本地看板 · 未上线</span></h1>
<div class="sub">数据截至 __ASOF__ ｜ 生成于 __BUILT__ ｜ A 质量版 + B+ 覆盖版，宽度≤34% + 振幅/涨幅≥7% + 同日 A≥__CA__ 且 B≥__CB__（2026-11-05 加严）</div>
<div class="row">
  <div class="kv"><b class="__GCLS__">__GATE__</b><span>市场宽度 __BR__（闸门 ≤34%）</span></div>
  <div class="kv"><b>__NRECENT__</b><span>最近 21 根信号</span></div>
  <div class="kv"><b>__FULL__</b><span>全样本（笔 / 胜率 / PF）</span></div>
  <div class="kv"><b>__Y26__</b><span>2026（笔 / 胜率 / PF）</span></div>
  <div class="kv"><b>__H2__</b><span>2025H2（笔 / 胜率 / PF）</span></div>
</div>

<h2>最近信号 / 当前候选</h2>
__TABLE_RECENT__

<h2>三窗口实盘组合（100,000 起始，1% 风险/笔，5 仓日，16 仓）</h2>
__TABLE_WINDOWS__

<h2>最近成交（模拟，12/30 两段 + 60 日低 3 连收）</h2>
__TABLE_TRADES__

<h2>规则</h2>
<ul>
<li><b>入场</b>：A 质量版 dev20≤−8%、RSI2≤40、ATR≥6%、跌破前 10 日低、量比≥0.8、dv20≥3000 万、价≥5、5 根内收回、cpos≥0.4；B+ 覆盖版 dev20≤−5%、RSI2≤50、ATR≥4%、量比≥0.5、8 根内收回、收阳。</li>
<li><b>市场层</b>：120 只个股收盘在 MA50 上方的比例 ≤34%；A 当日振幅≥7%，B 当日涨幅≥7%；同日 A 信号≥__CA__ 且同日 B 信号≥__CB__（B 层是宽松弹簧，当日家数收盘可算；加严依据 work/COLD_DODGE_2026-11-05.md 第 14 节：A≥3 单独用挡不住 2025-03 型阴跌）；同标的 5 根内只留一个，A 优先。</li>
<li><b>出场</b>：50% +12%、50% +30%、−30% 灾难上限、最多 60 根；连续 3 根收盘跌破 60 日低点，第 3 根收盘走。</li>
<li><b>仓位</b>：1% 权益风险/笔，名义=1%/止损距离，单仓名义上限 20%，5x，最多 16 仓，同日最多 5 仓，毛敞口≤2.5x。</li>
<li>本页只本地生成，不提交、不发布；每天收盘后重跑一次。</li>
</ul>
<p class="hint">止损 = 入场前 60 日最低价；止盈1 = 入场×1.12；止盈2 = 入场×1.30；数量 = 名义 / 入场；保证金 = 名义 / 5。</p>
</div></body></html>"""


def fmt_sig(z):
    notional = min(EQ * U.RISK_PCT / max(z['risk'], 1e-9), EQ * U.MAX_NOTIONAL)
    margin = notional / U.LEV
    qty = notional / z['entry']
    return dict(z, notional=notional, margin=margin, qty=qty,
                tp1=z['entry'] * (1 + U.TP1), tp2=z['entry'] * (1 + U.TP2))


def main():
    A, F, RG, cal = U.FD.load()
    sig, meta = U.build_signals(A, F, RG, cal)
    core = {s: b for s, b in A.items() if s not in U.L.ETF and s not in U.L.LEV}
    BR = U.L.breadth(core, F, cal)[0]
    asof = cal[-1]
    last_i = len(cal) - 1

    # 逐笔
    rows = []
    for z in sig:
        r = U.simulate(A, z, gap_open=False)
        if r is None:
            continue
        rows.append(dict(z, **r))
    full = U.stats(rows)
    h2 = U.stats([r for r in rows if '2025-06-01' <= r['entry_date'] < '2026-01-01'])
    y26 = U.stats([r for r in rows if r['entry_date'] >= '2026-01-01'])

    recent = [z for z in sig if z['i'] >= last_i - 20]
    recent = sorted(recent, key=lambda z: (z['i'], z['sym']))
    last = max(sig, key=lambda z: z['i']) if sig else None

    if recent:
        head = ('<table><thead><tr><th>信号日</th><th>入场日</th><th>标的</th><th>层</th>'
                '<th>入场 E</th><th>止损</th><th>风险</th><th>止盈1</th><th>止盈2</th>'
                '<th>数量</th><th>保证金</th><th>名义</th><th>止损占权益</th><th>宽度</th><th>同日 A/B</th></tr></thead><tbody>')
        body = []
        for z in recent:
            q = fmt_sig(z)
            risk_eq = q['notional'] * q['risk'] / EQ * 100
            body.append('<tr><td>%s</td><td>%s</td><td>%s</td><td class="acc">%s</td>'
                        '<td>%.2f</td><td class="neg">%.2f</td><td class="neg">%.1f%%</td>'
                        '<td class="pos">%.2f</td><td class="pos">%.2f</td><td>%.2f</td>'
                        '<td>%.0f</td><td>%.0f</td><td class="neg">%.2f%%</td><td>%.1f%%</td><td>%d/%d</td></tr>' % (
                            z['date'], z['entry_date'], z['sym'], z['tag'], z['entry'], z['stop'],
                            z['risk'] * 100, q['tp1'], q['tp2'], q['qty'], q['margin'],
                            q['notional'], risk_eq, z['breadth'] * 100, z['concA'], z['concB']))
        table_recent = head + ''.join(body) + '</tbody></table>'
    else:
        extra = ''
        if last:
            extra = ' 最后一个信号：<b>%s</b> %s（信号日）→ %s（入场）。' % (
                last['sym'], last['date'], last['entry_date'])
        table_recent = ('<p class="hint">最近 21 根没有新信号，当前空仓。' + extra +
                        ' 需要同时满足「宽度≤34% + 个股振幅/涨幅≥7% + 同日 A≥__CA__ 且 B≥__CB__」。</p>')

    # 三窗口
    wb = ['<table><thead><tr><th>窗口</th><th>信号</th><th>成交</th><th>被 5 仓日挡</th>'
          '<th>胜率</th><th>PF</th><th>区间收益</th><th>年化</th><th>最大回撤</th><th>期末权益</th></tr></thead><tbody>']
    wins = []
    for w in WINDOWS:
        r = U.run_window(A, cal, sig, w)
        s = r['stats']
        wins.append(dict(window=w, taken=r['taken'], signals=r['signals'],
                         skipped=r['skipped_cap'], **s))
        pf_s = '∞' if s['pf'] > 1000 else '%.2f' % s['pf']
        wb.append('<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%.1f%%</td>'
                  '<td>%s</td><td class="%s">%+.2f%%</td><td>%.1f%%</td><td class="neg">%.2f%%</td>'
                  '<td>%.0f</td></tr>' % (
                      w, r['signals'], r['taken'], r['skipped_cap'], s['win'], pf_s,
                      'pos' if s['ret'] >= 0 else 'neg', s['ret'], s['cagr'], s['mdd'], s['final_eq']))
    table_windows = ''.join(wb) + '</tbody></table>'

    # 最近成交
    rb = ['<table><thead><tr><th>信号日</th><th>标的</th><th>入场</th><th>止损</th>'
          '<th>结果</th><th>退出 1</th><th>退出 2</th><th>持有</th></tr></thead><tbody>']
    for t in sorted(rows, key=lambda x: x['entry_date'])[-12:]:
        cls = 'pos' if t['ret'] > 0 else 'neg'
        rb.append('<tr><td>%s</td><td>%s</td><td>%.2f</td><td class="neg">%.2f</td>'
                  '<td class="%s">%+.2f%%</td><td>%s</td><td>%s</td><td>%d 根</td></tr>' % (
                      t['date'], t['sym'], t['entry'], t['stop'], cls, t['ret'] * 100,
                      t['why1'], t['why2'], t['bars']))
    table_trades = ''.join(rb) + '</tbody></table>'

    gate = '闸门开' if BR[-1] <= U.BREADTH_MAX else '闸门关'
    gcls = 'pos' if BR[-1] <= U.BREADTH_MAX else 'neg'
    html = (HTML.replace('__ASOF__', asof)
            .replace('__BUILT__', datetime.now().strftime('%Y-%m-%d %H:%M'))
            .replace('__GATE__', gate).replace('__GCLS__', gcls)
            .replace('__BR__', '%.1f%%' % (BR[-1] * 100))
            .replace('__NRECENT__', str(len(recent)))
            .replace('__FULL__', '%d 笔 / %.1f%% / %.2f' % (full['n'], full['win'], full['pf']))
            .replace('__Y26__', '%d 笔 / %.1f%% / %.2f' % (y26['n'], y26['win'], y26['pf']))
            .replace('__H2__', '%d 笔 / %.1f%% / %.2f' % (h2['n'], h2['win'], h2['pf']))
            .replace('__TABLE_RECENT__', table_recent)
            .replace('__TABLE_WINDOWS__', table_windows)
            .replace('__TABLE_TRADES__', table_trades))
    # 表格片段里也带 __CA__/__CB__，插进页面后再统一替换一次
    html = (html.replace('__CA__', str(U.CLUSTER_MIN))
                .replace('__CB__', str(U.CLUSTER_B_MIN)))
    out = os.path.join(HERE, 'index.html')
    open(out, 'w', encoding='utf-8', newline='').write(html)

    # 前向记录
    logp = os.path.join(HERE, 'forward_log.jsonl')
    recs = []
    if os.path.exists(logp):
        for line in open(logp, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get('asof') != asof:
                recs.append(row)
    recs.append(dict(asof=asof, built_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
                     gate=gate, breadth=round(float(BR[-1]) * 100, 1),
                     recent=[dict(sym=z['sym'], date=z['date'], entry=round(z['entry'], 4),
                                  stop=round(z['stop'], 4), tag=z['tag']) for z in recent]))
    recs.sort(key=lambda r: r['asof'])
    with open(logp, 'w', encoding='utf-8') as fh:
        for row in recs:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')

    rep = dict(asof=asof, built_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
               breadth=round(float(BR[-1]), 4), gate=gate,
               cluster_min=meta['cluster_min'], cluster_b_min=meta['cluster_b_min'],
               n_pre_cluster=meta['n_pre_cluster'],
               nA_raw=meta['nA_raw'], nB_raw=meta['nB_raw'], nU=meta['nU'],
               nA_scan=meta['nA_scan'], nB_scan=meta['nB_scan'], scan_i0=meta['scan_i0'],
               recent=[z['sym'] for z in recent],
               stats=dict(full=full, h2=h2, y26=y26), windows=wins,
               page_sha256=hashlib.sha256(html.encode('utf-8')).hexdigest(),
               page_bytes=len(html.encode('utf-8')))
    json.dump(rep, open(os.path.join(HERE, 'build_report.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('wrote', out, rep['page_bytes'], 'bytes ｜ asof', asof,
          '｜ breadth %.1f%% %s ｜ recent %d ｜ U %d' % (
              BR[-1] * 100, gate, len(recent), meta['nU']))
    print('stats full %d/%.1f/%.2f | 2026 %d/%.1f/%.2f' % (
        full['n'], full['win'], full['pf'], y26['n'], y26['win'], y26['pf']))


if __name__ == '__main__':
    main()
