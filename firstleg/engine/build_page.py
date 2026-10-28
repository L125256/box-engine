# -*- coding: utf-8 -*-
"""生成「批量点火 · 第一段」独立看板 index.html。

  python build_page.py             # 用已收全日线（cache_fresh）
  python build_page.py --live      # 含未收盘那根（cache_live_merged）
"""
import os, sys, argparse, datetime, html, json
import strategy as S

HERE = os.path.dirname(os.path.abspath(__file__))


def fmt(x, nd=2):
    return ('%.' + str(nd) + 'f') % x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--equity', type=float, default=10000)
    ap.add_argument('--asof', default=None)
    ap.add_argument('--out', default='index.html')
    a = ap.parse_args()
    cache = 'cache_live_merged' if a.live else 'cache_fresh'
    A, F, RG, cal = S.load(cache)
    st = S.state_today(A, F, RG, cal, asof=a.asof)
    recent = S.recent_signals(A, F, RG, cal, k=6)

    equity = a.equity
    notional = equity * S.MARGIN_PCT * S.LEV
    margin = equity * S.MARGIN_PCT

    def expiry(d):
        # 数据是逐日线（含周末），20 根 = 20 个自然日
        return (datetime.date.fromisoformat(d) + datetime.timedelta(days=S.HOLD)).isoformat()

    nxt = (datetime.date.fromisoformat(st['asof']) + datetime.timedelta(days=1)).isoformat()

    rows = ''
    for x in st['candidates']:
        lv = S.levels(x['close'], x['atr'])
        qty = notional / x['close']
        rows += ('<tr class="cand" data-atr="%.6f">'
                 '<td><b>%s</b><span class="sub">涨 %.2f%% · 量 %.1f 倍</span></td>'
                 '<td><input class="px" value="%s" inputmode="decimal"></td>'
                 '<td class="stop">%s</td><td class="tp1">%s</td><td class="tp2">%s</td>'
                 '<td class="qty">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>') % (
            x['atr'], x['sym'], x['ret1'] * 100, x['volx'], fmt(x['close'], 2),
            fmt(lv['stop'], 2), fmt(lv['tp1'], 2), fmt(lv['cap'], 2),
            fmt(qty, 2), fmt(margin, 0), fmt(notional, 0), expiry(nxt))

    if st['candidates']:
        table = ('<table id="tbl"><thead><tr><th>标的</th><th>成交价 E（可改）</th>'
                 '<th>止损</th><th>止盈1 · 平一半</th><th>止盈2 · 封顶</th>'
                 '<th>数量</th><th>保证金</th><th>名义</th><th>到期日</th></tr></thead><tbody>%s</tbody></table>'
                 '<p class="hint">改 E 后止损/止盈/数量自动重算；E 默认取信号日收盘，实盘以次日开盘为准。</p>') % rows
        verdict = '开火：今日 %d 只点火（门槛 %d），取前 %d' % (st['n_above'], S.MIN_BATCH, S.TOP_K)
        cls = 'on'
    else:
        table = ('<div class="empty"><b>今日不开仓</b><p>点火 %d 只，未达到批次门槛 %d 只。'
                 '没有批量点火就不做——这正是这套策略天然的震荡/下跌过滤。</p></div>') % (
            st['n_ign'], S.MIN_BATCH)
        verdict = '停火：点火 %d / 门槛 %d' % (st['n_ign'], S.MIN_BATCH)
        cls = 'off'

    rrows = ''
    for r in recent:
        pnl_cls = 'pos' if r['pnl'] > 0 else 'neg'
        rrows += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                  '<td class="%s">%+.2f%%</td><td>%s</td></tr>') % (
            r['date'], r['sym'], fmt(r['entry'], 2), fmt(r['levels']['stop'], 2),
            fmt(r['levels']['tp1'], 2), fmt(r['levels']['cap'], 2),
            pnl_cls, r['pnl'] * 100, r['why'])

    tpl = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>批量点火 · 第一段（独立策略）</title>
<style>
:root{--bg:#0f1216;--card:#171c22;--line:#252c35;--txt:#e8edf3;--dim:#8b97a5;--up:#2ecc71;--down:#e74c3c;--acc:#4da3ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:26px 22px 60px}
h1{font-size:21px;margin:0 0 6px}.pill{display:inline-block;font-size:12px;padding:2px 9px;border-radius:99px;border:1px solid var(--line);color:var(--dim);vertical-align:3px}
.sub{display:block;font-size:11px;color:var(--dim);margin-top:2px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:14px 0;overflow-x:auto}
.row{display:flex;gap:22px;flex-wrap:wrap}.kv{min-width:120px}.kv b{display:block;font-size:18px}.kv span{font-size:12px;color:var(--dim)}
.on{color:var(--up)}.off{color:var(--down)}.warn{color:#f0b429}.ok{color:var(--up)}
table{width:100%;border-collapse:collapse;margin-top:8px}th,td{border-bottom:1px solid var(--line);padding:9px 6px;text-align:left;font-size:13px}
th{color:var(--dim);font-weight:600;font-size:12px}
input.px{width:92px;background:#0f1419;border:1px solid #2b3440;color:var(--txt);border-radius:6px;padding:4px 6px;font:inherit}
.empty{border:1px dashed #33404d;border-radius:10px;padding:18px;color:var(--dim)}.empty b{color:var(--txt);font-size:15px}
.hint{color:var(--dim);font-size:12px;margin:8px 0 0}.pos{color:var(--up)}.neg{color:var(--down)}
ul{margin:6px 0 0;padding-left:20px;color:#c7d1dc;font-size:13px}li{margin:3px 0}
.foot{color:#6f7a88;font-size:12px;margin-top:18px;line-height:1.7}
@media(max-width:720px){h1{font-size:18px}.kv{min-width:44%}th,td{font-size:12px;padding:7px 5px}}
</style>
<div class="wrap">
<h1>批量点火 · 第一段 <span class="pill">独立策略 · 已上线 · 手动刷新 · 与 v2.1/HF-1 分开记账</span></h1>
<div class="row" style="margin-top:10px">
  <div class="kv"><b>__ASOF__</b><span>数据截至</span></div>
  <div class="kv"><b class="__CLS__">__VERDICT__</b><span>今日状态</span></div>
  <div class="kv"><b>__NIGN__</b><span>点火家数（门槛 __MINB__）</span></div>
  <div class="kv"><b><input id="eq" value="__EQUITY__" inputmode="decimal" style="width:86px;background:#0f1419;border:1px solid #2b3440;color:#e8edf3;border-radius:6px;padding:3px 6px;font-size:14px;font-weight:400"></b><span>权益 USDT</span></div>
  <div class="kv"><b>__NABOVE__ / __NIGN__</b><span>站上 MA50 / 全部点火</span></div>
</div>
<div class="card">__TABLE__</div>
<div class="card">
  <b>最近触发日（实际结果）</b>
  <table><thead><tr><th>信号日</th><th>标的</th><th>入场 E</th><th>止损</th><th>止盈1</th><th>止盈2</th><th>净收益</th><th>退出</th></tr></thead>
  <tbody>__RECENT__</tbody></table>
  <p class="hint">按名义计净收益（双边 0.20% + 资金费 0.03%/日）。同一信号日多只属于同一波，不能当独立样本。</p>
</div>
<div class="card">
  <b>规则（2026-10-28 修订：去掉关火）</b>
  <ul>
    <li>点火：当日涨幅 ≥4% 且成交量 ≥2×20 日中位；个股站上 MA50；价格≥5、20 日成交额≥30M、ATR%≤6%。</li>
    <li>批次：同一天 ≥3 只点火才开火，取涨幅前 5；同一天不足 3 只不做。</li>
    <li>仓位：5x 逐仓，单笔保证金 3% 权益（名义 15%），最多 8 仓，毛敞口 ≤2.4 倍。</li>
    <li>退出：止损 = 入场 −2.5 ATR；+2.5 ATR 平一半；剩下一半 +8 ATR 全平；否则持有 20 根日线（约 20 个自然日）按收盘平。</li>
    <li>不设关火：2026-10-28 实测，5 日停新仓把年化从 56.5% 降到 37.2%，回撤反而从 12.33% 升到 13.10%，被挡掉的那批 PF 1.54 是正期望。</li>
  </ul>
</div>
<div class="card">
  <b>下单口径示例（权益 __EQUITY__ USDT）</b>
  <table><thead><tr><th>假设成交价 E</th><th>ATR</th><th>止损</th><th>止盈1 · 平一半</th><th>止盈2 · 封顶</th><th>数量</th><th>保证金</th><th>名义</th></tr></thead>
  <tbody><tr><td>100.00</td><td>3.00</td><td>92.50</td><td>107.50</td><td>124.00</td><td>__EQ15__</td><td>__MARGIN__</td><td>__NOTIONAL__</td></tr></tbody></table>
  <p class="hint">止损 = E − 2.5×ATR；止盈1 = E + 2.5×ATR（平一半）；止盈2 = E + 8×ATR（剩余全平）。数量 = 名义 / E，名义 = 权益 × 3% × 5 倍。</p>
</div>
<div class="card">
  <b>历史结果（2025-04-01 → 2026-10-26，代理数据）</b>
  <div class="row" style="margin-top:8px">
    <div class="kv"><b>113</b><span>成交仓位</span></div>
    <div class="kv"><b>61.1%</b><span>胜率</span></div>
    <div class="kv"><b>2.44</b><span>PF</span></div>
    <div class="kv"><b>+113.4%</b><span>累计</span></div>
    <div class="kv"><b>11.6%</b><span>最大回撤</span></div>
    <div class="kv"><b>0</b><span>爆仓</span></div>
  </div>
  <p class="hint">前 3 仓占总盈利 10%；去掉前 3 仓累计仍 +67.5%。2026-10-28 同引擎复核：不关火 117 仓 / +102.1% / 回撤 12.33%；5 日关火 86 仓 / +64.3% / 13.10%，已去掉（笔数与 113 的差异来自滚动窗口边界）。</p>
</div>
<div class="foot">
数据源：导演站日线（2026-01-26 之前为回填段，非 Gate 合约成交）。E 默认取信号日收盘，实盘以次日开盘为准；改 E 会重算止损止盈与数量。
本页为独立策略，不影响 v2.1 执行口径与 HF-1；未获批准不发布。<br>重建：python build_page.py（加 --live 用未收盘数据）。
</div>
</div>
<script>
document.querySelectorAll('#tbl tr.cand').forEach(function(tr){
  var atr=parseFloat(tr.dataset.atr);
  var inp=tr.querySelector('input.px');
  function calc(){
    var e=parseFloat(inp.value); if(!isFinite(e)||e<=0) return;
    tr.querySelector('.stop').textContent=(e-2.5*atr).toFixed(2);
    tr.querySelector('.tp1').textContent=(e+2.5*atr).toFixed(2);
    tr.querySelector('.tp2').textContent=(e+8*atr).toFixed(2);
    var eq=parseFloat(document.getElementById('eq').value)||0;
    tr.querySelector('.qty').textContent=(eq*0.15/e).toFixed(2);
  }
  inp.addEventListener('input',calc);
  document.getElementById('eq').addEventListener('input',calc); calc();
});
</script></html>"""

    doc = (tpl.replace('__ASOF__', html.escape(st['asof']))
              .replace('__CLS__', cls)
              .replace('__VERDICT__', html.escape(verdict))
              .replace('__NIGN__', str(st['n_ign']))
              .replace('__MINB__', str(S.MIN_BATCH))
              .replace('__NABOVE__', str(st['n_above']))
              .replace('__TABLE__', table)
              .replace('__RECENT__', rrows)
              .replace('__NOTIONAL__', '%.2f' % notional)
              .replace('__EQUITY__', '%.0f' % equity)
              .replace('__EQ15__', '%.2f' % (equity * 0.15 / 100))
              .replace('__MARGIN__', '%.0f' % margin))

    p = os.path.join(HERE, a.out)
    open(p, 'w', encoding='utf-8', newline='').write(doc)
    import hashlib
    rep = dict(asof=st['asof'], built_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
               state=('open' if st['candidates'] else 'off'), n_ign=st['n_ign'],
               candidates=[x['sym'] for x in st['candidates']],
               page_sha256=hashlib.sha256(doc.encode('utf-8')).hexdigest(),
               page_bytes=len(doc.encode('utf-8')))
    json.dump(rep, open(os.path.join(HERE, 'build_report.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('写出 %s（%d 字节）　状态：%s　候选 %d 只　最近信号 %d 条'
          % (p, len(doc.encode('utf-8')), verdict, len(st['candidates']), len(recent)))


if __name__ == '__main__':
    main()
