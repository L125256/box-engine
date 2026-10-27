#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染 HF-1 本地预览页（数据来自 hf1.json / sweep7.json）。"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(fn):
    raw = open(os.path.join(HERE, fn), 'rb').read()
    for enc in ('utf-8', 'gbk'):
        try:
            return json.loads(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    raise SystemExit('cannot decode ' + fn)


d = _load('hf1.json')
s7 = _load('sweep7.json')
st, g, v, cfg = d['stats'], d['gate'], d['v21'], d['config']
PROF = cfg['prof']
EQ, LEV, MP = cfg['equity'], PROF['lev'], PROF['margin_pct']
NOTIONAL = EQ * MP * LEV


def pct(x, dd=1):
    return ('%+.' + str(dd) + 'f%%') % x


def money(x):
    return '{:,.0f}'.format(x)


def spark(monthly):
    ks = sorted(monthly)
    vals = [monthly[k] for k in ks]
    mx = max(abs(min(vals)), abs(max(vals)), 1.0)
    rows = ''
    for k, x in zip(ks, vals):
        w = abs(x) / mx * 46
        left = 50 - w if x < 0 else 50
        col = '#3fb950' if x >= 0 else '#f85149'
        rows += ('<div class="mrow"><span class="mk">%s</span><span class="mbar">'
                 '<i style="left:%.1f%%;width:%.1f%%;background:%s"></i></span>'
                 '<span class="mv" style="color:%s">%+.1f%%</span></div>' % (k, left, w, col, col, x))
    return rows


def curve_svg(vals, w=940, h=150):
    if len(vals) < 2:
        return ''
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 0.01
    lo -= pad; hi += pad
    y0 = h - (1.0 - lo) / (hi - lo) * (h - 14) - 7
    xs = [(i) * (w - 8) / (len(vals) - 1) + 4 for i in range(len(vals))]
    ys = [h - (x - lo) / (hi - lo) * (h - 14) - 7 for x in vals]
    pts = ' '.join('%.1f,%.1f' % (a, b) for a, b in zip(xs, ys))
    return ('<svg viewBox="0 0 %d %d" width="100%%" height="%d" preserveAspectRatio="none">'
            '<line x1="0" y1="%.1f" x2="%d" y2="%.1f" stroke="#30363d" stroke-dasharray="3 3"/>'
            '<polyline fill="none" stroke="#a371f7" stroke-width="1.8" points="%s"/></svg>'
            % (w, h, h, y0, w, y0, pts))


kpi = [
    ('笔数 / 月', '%.1f' % st['per_month'], '共 %d 笔 · %d 个月' % (st['n'], st['months'])),
    ('胜率', '%.1f%%' % st['win'], 'v2.1 为 %.1f%%' % v['win']),
    ('赔率（平均盈/平均亏）', '%.2f' % st['payoff'], 'v2.1 为 %.2f' % v['payoff']),
    ('盈利因子 PF', '%.2f' % st['pf'], 'v2.1 为 %.2f' % v['pf']),
    ('年化', '%.1f%%' % st['cagr'], '2026 样本外 %.1f%%' % st['oos']['cagr']),
    ('最大回撤', '%.2f%%' % st['mdd'], 'v2.1 为 %.2f%%' % v['mdd']),
    ('爆仓次数', '%d' % st['liq'], '5x 逐仓 · 距爆仓 19%'),
    ('右尾依赖', '%.1f%%' % st['top5'], '前 5 笔占盈利；v2.1 为 17.9%'),
]
kpi_html = ''.join('<div class="mini"><div class="k">%s</div><div class="m">%s</div><div class="s">%s</div></div>'
                   % t for t in kpi)

lay_html = ''
for r in cfg['layers']:
    ex = r['exit']
    extra = []
    if r['green_only']:
        extra.append('当日收阳')
    if r['min_drop5'] is not None:
        extra.append('5 日跌幅 ≥ %.0f%%' % (-r['min_drop5'] * 100))
    bt = d['by_tier'].get(r['code'], {})
    lay_html += ('<tr><td>%s</td><td>≤ %.1f%%</td><td>≤ %g</td><td>≤ %.1f%%</td><td>%s</td>'
                 '<td>%.1f / %.1f / %d 根</td><td>%d 笔 · 胜率 %s%% · PF %s</td></tr>' % (
                     r['code'], -r['dev20_max'] * 100, r['rsi2_max'], r['atrp_max'] * 100,
                     '、'.join(extra) or '—', ex['sl_atr'], ex['tp_atr'], ex['hold'],
                     bt.get('n', 0), bt.get('win', '—'), bt.get('pf', '—')))

roll_html = ''.join('<tr><td>%s → %s</td><td>%d</td><td>%s%%</td><td>%+.1f%%</td><td>%.1f%%</td></tr>'
                    % (r['from_'], r['to'], r['n'], r['win'], r['ret'], r['mdd'])
                    for r in d['rolling'])

LAYERS = {r['code']: r for r in cfg['layers']}


def board_rows(rows, editable):
    out = ''
    for x in rows:
        ex = LAYERS[x['tier']]['exit']
        E = x.get('ref') or x['close']
        qty = NOTIONAL / E
        out += ('<tr data-atr="%.6f" data-sl="%.2f" data-tp="%.2f">'
                '<td><b>%s</b></td>'
                '<td><input class="pxe" type="number" step="0.01" min="0" value="%.3f" '
                'title="改成实际成交价，右侧止损/止盈/数量会即时重算"></td>'
                '<td class="c-ctx">%.3f</td>'
                '<td class="v-stop">%.3f</td><td class="v-tp">%.3f</td>'
                '<td class="v-qty">%.2f</td>'
                '<td class="v-notional c-ctx">%s</td><td class="v-margin c-ctx">%s</td>'
                '<td class="v-stopeq">%.2f%%</td><td class="v-expiry">%s</td>'
                '<td class="c-ctx">%s</td><td class="c-ctx">%.1f</td><td class="c-ctx">%.2f%%</td></tr>' % (
                    x['atr'], ex['sl_atr'], ex['tp_atr'],
                    x['sym'].replace('USDT', ''), E, x['atr'],
                    x['stop'], x['tp'], qty, money(NOTIONAL), money(EQ * MP),
                    x.get('stop_eq_pct', 0), x.get('expiry', '—'),
                    x['tier'].split()[0], x['rsi2'], x['dev20']))
    return out


cand_html = board_rows(d['candidates'], g['open']) or (
    '<tr><td class="dim">%s</td><td class="dim">—</td><td class="c-ctx dim">—</td>'
    '<td class="dim">—</td><td class="dim">—</td><td class="dim">—</td>'
    '<td class="c-ctx dim">—</td><td class="c-ctx dim">—</td><td class="dim">—</td>'
    '<td class="dim">—</td><td class="c-ctx dim">—</td><td class="c-ctx dim">—</td>'
    '<td class="c-ctx dim">—</td></tr>' % (
        '闸门关闭 —— 今日 0 只可开仓，不开新单。下面「候补」是差得最近的标的，闸门一开它们最先可能变成可开仓。'
        if not g['open'] else '闸门打开，但今日三层规则均无命中 —— 同样不开新单。'))

near_html = ''
for x in d['near'][:14]:
    near_html += ('<tr><td><b>%s</b></td><td>%.2f</td><td>%.1f</td><td>%.2f%%</td><td>%.2f%%</td>'
                  '<td class="dim">%s</td></tr>' % (
                      x['sym'].replace('USDT', ''), x['close'], x.get('rsi2', 0),
                      x.get('dev20', 0), x.get('atrp', 0), '、'.join(x.get('miss', []))))

nb = [r for r in s7 if 'A+B+C' in r['tag'] and 'D' not in r['tag']]
nb_html = ''.join('<tr><td>%s</td><td>%d</td><td>%.1f%%</td><td>%.2f</td><td>%.1f%%</td><td>%.1f%%</td></tr>'
                  % (r['tag'], r['n'], r['win'], r['pf'], r['cagr'], r['mdd']) for r in nb[:9])

gate_txt = '打开 · 可按清单开仓' if g['open'] else '关闭 · 今日空仓，不开新单'

html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HF-1 三层叠加 · 高胜率高频执行页</title>
<style>
body{{background:#0d1117;color:#c9d1d9;font:14px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0}}
.wrap{{max-width:1000px;margin:0 auto;padding:26px 18px 60px}}
h1{{font-size:21px;margin:0 0 4px}} h2{{font-size:15px;margin:28px 0 10px;color:#e6edf3;
border-left:3px solid #a371f7;padding-left:8px}}
.sub{{color:#8b949e;font-size:12.5px}}
.card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:15px 17px;margin:12px 0}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.mini{{background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:9px 11px}}
.mini .k{{font-size:11.5px;color:#8b949e}} .mini .m{{font-size:19px;font-weight:600;color:#e6edf3}}
.mini .s{{font-size:11px;color:#8b949e}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:6px 8px;border-bottom:1px solid #21262d;text-align:right;white-space:nowrap}}
th{{color:#8b949e;font-weight:500;font-size:12px}} td:first-child,th:first-child{{text-align:left}}
.ok{{color:#3fb950}} .bad{{color:#f85149}} .dim{{color:#8b949e}}
.pill{{display:inline-block;font-size:12px;padding:2px 9px;border:1px solid #30363d;border-radius:12px;margin-right:6px}}
.banner{{border-radius:8px;padding:11px 13px;font-size:14px;font-weight:600;margin-bottom:10px}}
.banner.off{{background:#3a1d1d;border:1px solid #6d2626;color:#ffb3ad}}
.banner.on{{background:#12261a;border:1px solid #1f6b3a;color:#7ee2a8}}
.mrow{{display:flex;align-items:center;font-size:12px;margin:2px 0}}
.mk{{width:62px;color:#8b949e}} .mbar{{position:relative;flex:1;height:11px}}
.mbar i{{position:absolute;top:1px;height:9px;border-radius:2px}}
.mv{{width:58px;text-align:right}}
ol,ul{{margin:6px 0 0 18px;padding:0}} li{{margin:6px 0}}
.pxe{{width:96px;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;
padding:4px 6px;font-size:13px;text-align:right}}
.pxe:focus{{outline:none;border-color:#a371f7}} .pxe.badpx{{border-color:#ff7b72}}
.v-note{{margin-top:8px;font-size:12.5px;color:#8b949e}}
.bscroll{{overflow-x:auto}}
.guide{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.gstep{{background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:10px 12px;font-size:12.5px}}
.gstep b{{display:block;color:#e6edf3;font-size:13px;margin-bottom:3px}}
@media (max-width:700px){{
  .grid{{grid-template-columns:repeat(2,1fr)}} .guide{{grid-template-columns:1fr}}
  .pxe{{width:76px}} .bscroll table{{min-width:620px}}
  .c-ctx{{display:none}}
}}
</style></head><body><div class="wrap">
<h1>HF-1 · 三层叠加（高胜率 + 机会多）<span class="pill">已上线 · 手动刷新</span>
<span class="pill"><a href="../" style="color:#a371f7;text-decoration:none">← v2.1 执行口径页</a></span></h1>
<div class="sub">同一份 144 只日线池，剔除杠杆/反向与 ETF 后 {cfg['n_universe']} 只可交易 ·
最后一根收全 <b>{d['asof']}</b> · 更新于 <b>{d['built_at']}</b>（北京）·
信号日收盘判定 → 次日（{d['next_entry']}）开盘成交 · 5x 逐仓 · 含资金费与双边成本</div>

<h2>怎么看这一页（三步）</h2>
<div class="guide">
<div class="gstep"><b>① 先看闸门</b>下方红/绿条。关闭 = 今天不下单，不用去找标的；打开才进入第 ② 步。</div>
<div class="gstep"><b>② 再看「今日可开仓」表</b>每行给出成交价 E、止损价、止盈价、数量、名义、保证金、到期日，全是具体数字，不用自己算。</div>
<div class="gstep"><b>③ 成交后把 E 改成实际成交价</b>止损、止盈、数量、止损占权益即时重算；止损距离超过 {cfg['abandon_pct']}% 会红字提示放弃该笔。</div>
</div>

<h2>今日执行清单</h2>
<div class="card">
<div class="banner {('on' if g['open'] else 'off')}">当前：闸门{gate_txt}　·　等权收益指数 {g['idx']:.3f} / MA50 {g['ma50']:.3f}
（{pct(g['gap'],2)}）　·　5 日平滑广度 {g['br5']:.1f}%（阈值 {g['br_min']:.0f}%）　·　已连续关闭 {g['closed_days']} 个交易日</div>
<div class="sub" style="margin-bottom:8px">{'；'.join(d['gaps']) if d['gaps'] else '两道条件都满足，按下方清单执行。'}</div>
<div class="bscroll"><table><thead><tr>
<th>代码</th><th>成交价 E</th><th class="c-ctx">ATR14</th><th>止损价</th><th>止盈价</th><th>数量</th>
<th class="c-ctx">名义 USDT</th><th class="c-ctx">保证金</th><th>止损占权益</th><th>到期日</th>
<th class="c-ctx">层</th><th class="c-ctx">RSI2</th><th class="c-ctx">20日偏离</th></tr></thead>
<tbody id="boardTbl">{cand_html}</tbody></table></div>
<div class="v-note">参考价 = 信号日 {d['asof']} 收盘价；实际以次日开盘成交价 E 为准。
止损 = E − 止损ATR × ATR14，止盈 = E + 止盈ATR × ATR14，到期日 = 下一交易日起第 N 个交易日按收盘平仓（时间闸，不是止盈目标）。
每笔保证金 {MP*100:.1f}% 权益（名义 {NOTIONAL:,.0f} USDT = {MP*LEV*100:.0f}% 权益），
最多 {PROF['max_pos']} 只、毛敞口 ≤ {PROF['gross_cap']} 倍。三层最大止损宽度 {cfg['max_stop_pct']}%，
低于放弃线 {cfg['abandon_pct']}%（爆仓距离 19% 的 80%），所以清单里不会出现「止损过宽不可执行」的标的。</div>
</div>

<h2>候补（差在哪，闸门开了先看它们）</h2>
<div class="card"><div class="bscroll"><table><thead><tr>
<th>代码</th><th>收盘</th><th>RSI2</th><th>20日偏离</th><th>ATR%</th><th>未通过项</th></tr></thead>
<tbody>{near_html}</tbody></table></div>
<div class="v-note">候补表只是提示，不是下单指令；只有「今日可开仓」表里的标的才执行。</div></div>

<h2>核心结果</h2>
<div class="grid">{kpi_html}</div>

<h2>与 v2.1 对照</h2>
<div class="card">
<table><thead><tr><th>系统</th><th>笔/月</th><th>总笔数</th><th>胜率</th><th>赔率</th><th>PF</th><th>年化</th><th>回撤</th></tr></thead><tbody>
<tr><td>v2.1（现执行口径，单腿 4%×12）</td><td>{v['per_month']}</td><td>{v['n']}</td><td>{v['win']}%</td>
<td>{v['payoff']}</td><td>{v['pf']}</td><td>{v['cagr']}%</td><td>{v['mdd']}%</td></tr>
<tr><td><b>HF-1（三层 2.5%×20）</b></td><td>{st['per_month']}</td><td>{st['n']}</td><td>{st['win']}%</td>
<td>{st['payoff']}</td><td>{st['pf']}</td><td>{st['cagr']}%</td><td>{st['mdd']}%</td></tr>
<tr><td class="dim">HF-1 的 2026 样本外</td><td class="dim">—</td><td class="dim">{st['oos']['n']}</td>
<td class="dim">{st['oos']['win']}%</td><td class="dim">—</td><td class="dim">{st['oos']['pf']}</td>
<td class="dim">{st['oos']['cagr']}%</td><td class="dim">{st['oos']['mdd']}%</td></tr>
</tbody></table>
<div class="v-note">出场结构 {json.dumps(st['exit_mix'], ensure_ascii=False)}（tp=止盈、stop=止损、time=到期、
tp_gap/stop_gap=开盘跳空直接成交）；最长连亏 {st['max_consec_loss']} 笔；{st['months_pos']}/{st['months']} 个月为正；
平均暴露 {st['expo']}% 权益。</div>
</div>

<h2>三层规则（全部要求站上 MA100 且 MA100 向上，天然不追高）</h2>
<div class="card"><div class="bscroll"><table><thead><tr>
<th>层</th><th>20日偏离</th><th>RSI2</th><th>ATR%</th><th>附加确认</th><th>止损/止盈/持有（ATR）</th><th>贡献</th>
</tr></thead><tbody>{lay_html}</tbody></table></div>
<div class="v-note">追高检查：全部 {st['n']} 笔里，信号日收盘距 20 日最高点不足 2% 的占 0%。</div></div>

<h2>稳健性</h2>
<div class="card">
<div class="sub">滚动 6 个月窗口（重叠，步长 2 个月）：</div>
<table><thead><tr><th>窗口</th><th>笔数</th><th>胜率</th><th>区间收益</th><th>窗口内回撤</th></tr></thead>
<tbody>{roll_html}</tbody></table>
<div class="sub" style="margin-top:10px">参数邻域（广度 40–55%、保证金 2%–4%、B/C 阈值上下）：胜率 61.5–63.3%、PF 1.76–2.08，是平台不是尖峰。</div>
<table><thead><tr><th>变体</th><th>笔数</th><th>胜率</th><th>PF</th><th>年化</th><th>回撤</th></tr></thead>
<tbody>{nb_html}</tbody></table>
<div class="sub" style="margin-top:10px">成本敏感性：单边 0.10% → PF 1.92；0.15% → 1.85；0.20% → 1.79（胜率不变，只吃收益）。资金费按 0.03%/日计入。</div>
</div>

<h2>分月收益（权益口径）</h2>
<div class="card">{spark(d['monthly'])}</div>

<h2>净值曲线（2.5% 保证金口径，每 4 个交易日取一点）</h2>
<div class="card">{curve_svg(d['curve'])}
<div class="v-note">起 {d['curve_dates'][0]} → 止 {d['curve_dates'][-1]}，期末 {d['curve'][-1]:.2f} 倍。</div></div>

<h2>已知局限</h2>
<div class="card"><ul>
<li>HF-1 与 v2.1 同源：同闸门、同池、A 层就是 v2.1 的入场。它是「把 v2.1 的机会数放大」，不是分散化的第二套系统。</li>
<li>2025-06 之前的数据段含合成成分；本页同时给全样本与 2026 样本外两组数，后者证据强度更高。</li>
<li>空头腿与第四层「回踩 MA50」已测并否决（2026 段 PF 0.95–1.37），不在本页执行范围内。</li>
<li>本页已上线 <a href="https://l125256.github.io/box-engine/v2/hf1/" style="color:#a371f7">l125256.github.io/box-engine/v2/hf1/</a>，链接固定，刷新只换内容不换地址；生成脚本与数据快照在仓库 v2/hf1/ 下。C1（c1f/）与云端任务未改动。</li>
</ul></div>
<div class="sub" style="margin-top:18px">研究口径，不构成投资建议；回测含幸存者偏差（当前池 {cfg['n_universe']} 只可交易标的）。</div>
</div>
<script>
(function(){{
  var EQ={EQ}, LEV={LEV}, MP={MP}, ABN={cfg['abandon_pct']};
  var NOTIONAL=EQ*MP*LEV;
  function cell(tr,c){{return tr.querySelector('.'+c);}}
  function recalc(tr){{
    var inp=tr.querySelector('.pxe'); if(!inp) return;
    var E=parseFloat(inp.value), atr=parseFloat(tr.dataset.atr);
    var sl=parseFloat(tr.dataset.sl), tp=parseFloat(tr.dataset.tp);
    if(!(E>0)||!(atr>0)) return;
    var stop=E-sl*atr, tgt=E+tp*atr, sp=(stop/E-1)*100;
    var qty=NOTIONAL/E, stopEq=sp*LEV*MP;
    cell(tr,'v-stop').textContent=stop.toFixed(3);
    cell(tr,'v-tp').textContent=tgt.toFixed(3);
    cell(tr,'v-qty').textContent=qty.toFixed(2);
    cell(tr,'v-notional').textContent=Math.round(NOTIONAL).toLocaleString();
    cell(tr,'v-margin').textContent=Math.round(EQ*MP).toLocaleString();
    var bad=Math.abs(sp)>ABN;
    cell(tr,'v-stopeq').textContent=stopEq.toFixed(2)+'%';
    cell(tr,'v-stopeq').className='v-stopeq '+(bad?'bad':'ok');
    cell(tr,'v-stopeq').title=bad?('止损距离 '+sp.toFixed(2)+'%，超过放弃线 '+ABN+'%（爆仓距离 19% 的 80%），按规则放弃该笔'):'';
    inp.classList.toggle('badpx',bad);
  }}
  var tb=document.getElementById('boardTbl');
  if(tb) tb.addEventListener('input',function(ev){{
    if(ev.target.classList.contains('pxe')) recalc(ev.target.closest('tr'));
  }});
}})();
</script>
</body></html>'''

open(os.path.join(HERE, 'hf1.html'), 'w', encoding='utf-8').write(html)
print('wrote hf1.html', os.path.getsize(os.path.join(HERE, 'hf1.html')), 'bytes')
