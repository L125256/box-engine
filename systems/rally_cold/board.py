# -*- coding: utf-8 -*-
"""冷启动 · 全历史起涨 · 本地看板（只本地生成，不发布）。

规则：
  - 季度走前训练：每季度只用该季度之前的数据训练，预测下一季度；
  - 2025-03 冷启动只用 <2025-03-01 的数据；
  - 模型分门槛全程 0.75（2026-11-05 改甲：取消「2025-03/04 用 0.75、之后 0.65」的
    日历特权，改成一条当天可算、不含日期的统一门槛。研究依据见
    work/COLD_DODGE_2026-11-05.md：2025-03 信号最高分 0.742，全部落在门外；
    2025-03 起组合 58 笔/77.6%/PF3.64/+44.17%/−9.33% 变为 49 笔/81.6%/PF4.07/
    +38.99%/−9.33%，逐笔 128 笔变为 106 笔）；
  - 结构闸门：宽度≤35%、同日 A≥3、个股振幅≥7% 或涨幅≥7%；
  - 出场/仓位沿用 U：60 日低 3 连收、12/30、−30%、60 根、1%/5x/16 仓/5 仓日/2.5x。
只研究，不下单。
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
WORK = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
for _p in (os.path.join(WORK, 'repo_new', 'v2', 'engine'),
           os.path.join(WORK, 'v2'),
           os.path.join(WORK, 'repo_new', 'systems', 'fd1'),
           os.path.join(WORK, 'repo_new', 'systems', 'rally_u'),
           os.path.join(WORK, 'gate_lab'),
           HERE):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import numpy as np
import strategy as FD
import v2_lib as L
import u_engine as UE
from rally_segments import build_segments
from rally_all_model import (build_panel, FEATS, matrix, fit_scaler,
                             apply_scaler, fit_logit, predict, event_weights)

EQ = 100000.0
THR = 0.75                    # 全程统一模型分门槛（2026-11-05 改甲，无日历分支）
THR_EARLY = THR_MAIN = THR    # 兼容旧调用名，两段已同值
QUARTERS = [('2025-04-01', '2025-07-01'), ('2025-07-01', '2025-10-01'),
            ('2025-10-01', '2026-01-01'), ('2026-01-01', '2026-04-01'),
            ('2026-04-01', '2026-07-01'), ('2026-07-01', '2026-10-01'),
            ('2026-10-01', '9999')]

HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>冷启动 · 全历史起涨 本地看板</title>
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
<h1>冷启动 · 全历史起涨 <span style="font-size:12px;color:var(--dim)">本地看板 · 未上线</span></h1>
<div class="sub">数据截至 __ASOF__ ｜ 生成于 __BUILT__ ｜ 季度走前模型 + 模型分≥__THR__（全程统一，无日历）+ 宽度≤35% + 同日 A≥3 + 振幅/涨幅≥7%</div>
<div class="row">
  <div class="kv"><b class="__GCLS__">__GATE__</b><span>市场宽度 __BR__（闸门 ≤35%）</span></div>
  <div class="kv"><b>__NQ__</b><span>本季度信号</span></div>
  <div class="kv"><b>__FULL__</b><span>全历史组合（笔 / 胜率 / PF）</span></div>
  <div class="kv"><b>__Y26__</b><span>2026 组合（笔 / 胜率 / PF）</span></div>
  <div class="kv"><b>__QTR__</b><span>本季度模型（训练截止 / 行 / 正）</span></div>
</div>
<p class="hint">逐笔统计（不受同日 5 仓上限）：__TRADE__。组合统计见下表。</p>

<h2>本季度候选 / 最近信号</h2>
__TABLE_RECENT__

<h2>实盘组合（100,000 起始，1% 风险/笔，5 仓日，16 仓）</h2>
__TABLE_WINDOWS__

<h2>最近成交（模拟，12/30 两段 + 60 日低 3 连收）</h2>
__TABLE_TRADES__

<h2>规则</h2>
<ul>
<li><b>模型</b>：22 个因果特征（深回撤、ATR、RSI14、振幅、cpos、量比、宽度、同日反转/创新低家数、同日 A 信号数、市场 20 日收益等），L2 逻辑回归，起涨事件日等权；每季度只用之前的数据重训。</li>
<li><b>门槛</b>：2025-03 那批分数只用 &lt;2025-03-01 的数据训练得到；模型分全程 ≥__THR__，2026-11-05 起取消「2025-03/04 用 0.75、之后 0.65」的日历特权。2025-03 的信号最高只有 0.742，统一门槛即可把它们全部挡在门外（研究：work/COLD_DODGE_2026-11-05.md）。</li>
<li><b>结构闸门</b>：120 只个股宽度≤35%；同日 A 信号≥3；个股当日振幅≥7% 或涨幅≥7%。</li>
<li><b>出场/仓位</b>：与 U 完全相同，60 日低 3 连收、50% +12%、50% +30%、−30% 上限、60 根；1% 风险/笔、5x、16 仓、同日 5 仓、毛敞口≤2.5x。</li>
<li>本页只本地生成，不提交、不发布；每天收盘后重跑一次。</li>
<li><b>对照</b>：真实段严格版（只用 2025-06+ 训练、2026-01-26 窗口）是 21 笔 / 90.5% / PF17.57 / +22.77% / 回撤 −4.80%，那是另一套模型；本页是全历史季度走前 + 全程 0.75 门槛的版本，两者不要混用。</li>
</ul>
<p class="hint">全程 0.75 是收盘当天就能算的规则，不再依赖日期；但它挡掉 2025-03 的依据目前只有一次事件，与 3 月最高分 0.742 之间只有 0.008 的余量，所以门槛的任何调整都走前向判据复核，不用日期补丁。</p>
</div></body></html>"""


def dedup5(rows):
    cand = sorted(rows, key=lambda r: (r['sym'], r['i']))
    keep = []
    for r in cand:
        if any(q['sym'] == r['sym'] and abs(q['i'] - r['i']) <= 5 for q in keep):
            continue
        keep.append(r)
    return sorted(keep, key=lambda r: (r['i'], r['sym']))


def prep_all(A, cal, rows):
    out = []
    for r in rows:
        z = UE._prep(A, cal, dict(sym=r['sym'], i=r['i'], date=r['date'],
                                  atr=r['atrp'], range_pct=r['range_pct'], ret1=r['ret1']))
        if z is None:
            continue
        z['score'] = float(r['score'])
        z['breadth'] = float(r['breadth'])
        z['concA'] = int(round(np.expm1(r['concA_log'])))
        z['range_pct'] = float(r['range_pct'])
        out.append(z)
    return out


def select(rows, lo, hi, thr=THR):
    """模型分 >= thr（全程同一个门槛，无日历分支）+ 结构闸门 + 5 根去重。"""
    sub = []
    for r in rows:
        if not (lo <= r['date'] < hi):
            continue
        if not np.isfinite(r['score']):
            continue
        if r['score'] < thr:
            continue
        if r['breadth'] > 0.35 or r['concA_log'] < np.log1p(3):
            continue
        if r['range_pct'] < 0.07 and r['ret1'] < 0.07:
            continue
        sub.append(r)
    return dedup5(sub)


def main():
    A, F, RG, cal = FD.load()
    i0 = next(i for i, d in enumerate(cal) if d >= '2024-06-01')
    segs = build_segments(A, cal, rev=0.20, min_gain=0.30, start_date='2024-06-01')
    rows = build_panel(A, F, RG, cal, segs, i0)
    dates = np.array([r['date'] for r in rows])
    X = matrix(rows, FEATS)
    y = np.array([r['label_post'] for r in rows], int)
    score = np.full(len(rows), np.nan)

    # 2025-03 冷启动
    tr = np.where(dates < '2025-03-01')[0]
    te = np.where((dates >= '2025-03-01') & (dates < '2025-04-01'))[0]
    if y[tr].sum() >= 10 and len(te):
        sc = fit_scaler(X[tr])
        beta = fit_logit(apply_scaler(X[tr], sc), y[tr],
                         sw=event_weights(rows, tr), l2=5.0)
        score[te] = predict(X[te], sc, beta)

    # 季度走前
    for lo, hi in QUARTERS:
        tr = np.where(dates < lo)[0]
        te = np.where((dates >= lo) & (dates < hi))[0]
        if len(tr) < 500 or y[tr].sum() < 30 or len(te) == 0:
            continue
        sc = fit_scaler(X[tr])
        beta = fit_logit(apply_scaler(X[tr], sc), y[tr],
                         sw=event_weights(rows, tr), l2=2.0)
        score[te] = predict(X[te], sc, beta)

    for k, r in enumerate(rows):
        r['score'] = float(score[k])

    asof = cal[-1]
    core = {s: b for s, b in A.items() if s not in L.ETF and s not in L.LEV}
    BR = L.breadth(core, F, cal)[0]

    # 全程 0.75 门槛 · 全历史
    sig_mix = prep_all(A, cal, select(rows, '2025-03-01', '9999'))
    rows_tr = []
    for z in sig_mix:
        r = UE.simulate(A, z)
        if r:
            rows_tr.append(dict(z, **r))
    full = UE.stats(rows_tr)
    y26 = UE.stats([r for r in rows_tr if r['entry_date'] >= '2026-01-01'])

    # 最近信号：最近 21 根
    last_i = len(cal) - 1
    cur = [z for z in sig_mix if z['i'] >= last_i - 20]
    cur = sorted(cur, key=lambda z: (z['i'], z['sym']))
    last = max(sig_mix, key=lambda z: z['i']) if sig_mix else None

    if cur:
        head = ('<table><thead><tr><th>信号日</th><th>入场日</th><th>标的</th><th>模型分</th>'
                '<th>入场 E</th><th>止损</th><th>风险</th><th>止盈1</th><th>止盈2</th>'
                '<th>数量</th><th>保证金</th><th>名义</th><th>止损占权益</th><th>宽度</th><th>同日 A</th></tr></thead><tbody>')
        body = []
        for z in cur:
            notional = min(EQ * UE.RISK_PCT / max(z['risk'], 1e-9), EQ * UE.MAX_NOTIONAL)
            margin = notional / UE.LEV
            qty = notional / z['entry']
            risk_eq = notional * z['risk'] / EQ * 100
            body.append('<tr><td>%s</td><td>%s</td><td>%s</td><td class="acc">%.3f</td>'
                        '<td>%.2f</td><td class="neg">%.2f</td><td class="neg">%.1f%%</td>'
                        '<td class="pos">%.2f</td><td class="pos">%.2f</td><td>%.2f</td>'
                        '<td>%.0f</td><td>%.0f</td><td class="neg">%.2f%%</td><td>%.1f%%</td><td>%d</td></tr>' % (
                            z['date'], z['entry_date'], z['sym'], z['score'], z['entry'], z['stop'],
                            z['risk'] * 100, z['entry'] * 1.12, z['entry'] * 1.30, qty,
                            margin, notional, risk_eq, z['breadth'] * 100, z['concA']))
        table_recent = head + ''.join(body) + '</tbody></table>'
    else:
        extra = ''
        if last:
            extra = ' 最后一个信号：<b>%s</b> %s（信号日）→ %s（入场）。' % (
                last['sym'], last['date'], last['entry_date'])
        table_recent = ('<p class="hint">最近 21 根没有新信号，当前空仓。' + extra +
                        ' 需要同时满足「模型分≥__THR__ + 宽度≤35% + 同日 A≥3 + 振幅/涨幅≥7%」。</p>')

    # 组合窗口
    wb = ['<table><thead><tr><th>窗口</th><th>信号</th><th>成交</th><th>被 5 仓日挡</th>'
          '<th>胜率</th><th>PF</th><th>区间收益</th><th>年化</th><th>最大回撤</th><th>期末权益</th></tr></thead><tbody>']
    wins = []
    for w in ('2025-03-01', '2025-06-01', '2026-01-01', '2026-01-26', '2026-05-01'):
        r = UE.run_window(A, cal, sig_mix, w)
        s = r['stats']
        wins.append(dict(window=w, taken=r['taken'], signals=r['signals'],
                         skipped=r['skipped_cap'], **s))
        wb.append('<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%.1f%%</td>'
                  '<td>%.2f</td><td class="%s">%+.2f%%</td><td>%.1f%%</td><td class="neg">%.2f%%</td>'
                  '<td>%.0f</td></tr>' % (
                      w, r['signals'], r['taken'], r['skipped_cap'], s['win'], s['pf'],
                      'pos' if s['ret'] >= 0 else 'neg', s['ret'], s['cagr'], s['mdd'], s['final_eq']))
    table_windows = ''.join(wb) + '</tbody></table>'

    # 最近成交
    rb = ['<table><thead><tr><th>信号日</th><th>标的</th><th>入场</th><th>止损</th>'
          '<th>结果</th><th>退出 1</th><th>退出 2</th><th>持有</th></tr></thead><tbody>']
    for t in sorted(rows_tr, key=lambda x: x['entry_date'])[-12:]:
        cls = 'pos' if t['ret'] > 0 else 'neg'
        rb.append('<tr><td>%s</td><td>%s</td><td>%.2f</td><td class="neg">%.2f</td>'
                  '<td class="%s">%+.2f%%</td><td>%s</td><td>%s</td><td>%d 根</td></tr>' % (
                      t['date'], t['sym'], t['entry'], t['stop'], cls, t['ret'] * 100,
                      t['why1'], t['why2'], t['bars']))
    table_trades = ''.join(rb) + '</tbody></table>'

    gate = '闸门开' if BR[-1] <= 0.35 else '闸门关'
    gcls = 'pos' if BR[-1] <= 0.35 else 'neg'
    cur_tr = int(np.sum(dates < '2026-10-01'))
    cur_pos = int(y[dates < '2026-10-01'].sum()) if cur_tr else 0
    wfull = next((w for w in wins if w['window'] == '2025-03-01'), None)
    w26 = next((w for w in wins if w['window'] == '2026-01-01'), None)
    html = (HTML.replace('__ASOF__', asof)
            .replace('__THR__', '%.2f' % THR)
            .replace('__BUILT__', datetime.now().strftime('%Y-%m-%d %H:%M'))
            .replace('__GATE__', gate).replace('__GCLS__', gcls)
            .replace('__BR__', '%.1f%%' % (BR[-1] * 100))
            .replace('__NQ__', str(len(cur)))
            .replace('__FULL__', '%d 笔 / %.1f%% / %.2f' % (
                wfull['taken'], wfull['win'], wfull['pf']) if wfull else '—')
            .replace('__Y26__', '%d 笔 / %.1f%% / %.2f' % (
                w26['taken'], w26['win'], w26['pf']) if w26 else '—')
            .replace('__TRADE__', '全样本 %d 笔 / %.1f%% / PF %.2f；2026 %d 笔 / %.1f%% / PF %.2f' % (
                full['n'], full['win'], full['pf'], y26['n'], y26['win'], y26['pf']))
            .replace('__QTR__', '2026-10-01 / %d 行 / %d 正' % (cur_tr, cur_pos))
            .replace('__TABLE_RECENT__', table_recent)
            .replace('__TABLE_WINDOWS__', table_windows)
            .replace('__TABLE_TRADES__', table_trades))
    # 表格片段里也可能带 __THR__，插在页面后再统一替换一次
    html = html.replace('__THR__', '%.2f' % THR)
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
                                  stop=round(z['stop'], 4), score=round(z['score'], 4)) for z in cur]))
    recs.sort(key=lambda r: r['asof'])
    with open(logp, 'w', encoding='utf-8') as fh:
        for row in recs:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')

    rep = dict(asof=asof, built_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
               thr=THR, calendar_hack=None,
               breadth=round(float(BR[-1]), 4), gate=gate,
               model_cut='2026-10-01', model_rows=cur_tr, model_pos=cur_pos,
               recent=[z['sym'] for z in cur],
               stats=dict(full=full, y26=y26), windows=wins,
               page_sha256=hashlib.sha256(html.encode('utf-8')).hexdigest(),
               page_bytes=len(html.encode('utf-8')))
    json.dump(rep, open(os.path.join(HERE, 'build_report.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('wrote', out, rep['page_bytes'], 'bytes ｜ asof', asof,
          '｜ breadth %.1f%% %s ｜ current %d ｜ signals %d' % (
              BR[-1] * 100, gate, len(cur), len(sig_mix)))
    print('stats full %d/%.1f/%.2f | 2026 %d/%.1f/%.2f' % (
        full['n'], full['win'], full['pf'], y26['n'], y26['win'], y26['pf']))


if __name__ == '__main__':
    main()
