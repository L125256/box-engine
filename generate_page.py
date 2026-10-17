#!/usr/bin/env python3
# generate_page.py — 箱体引擎状态页一键生成器（幂等）
# 流程：32线程刷缓存 → import 本机权威引擎 eng_final.py（禁止修改，仅复用）跑两组冻结参数
#       → 状态机影子扫描输出当前箱体卡片（与引擎交易键集合断言一致）→ 渲染同款风格 HTML + JSON
# 复现：PYTHONHASHSEED=42 python3 /tmp/web_build/generate_page.py
import sys, os, json, importlib.util, random, datetime, shutil

SEED = 42
random.seed(SEED)

BUILD_DIR   = "/tmp/web_build"
OUT_DIR     = os.path.join(BUILD_DIR, "out")
CACHE_DIR   = "/tmp/box_cache"
ENG_DIR     = "/tmp/eng_wt_rc"
POOL_FILE   = "/tmp/eng_wt/cleaned_pool.json"
DELIVER_DIR = "/workspace/box_web"
REPO_DIR    = "/workspace/repo_ready"
MAIN_WINDOW = "2025-06-01"
RECENT_DAYS = 30

# 两组冻结参数（工单要求：N20/k6.0/m2 冻结参数 + Top1 参数）
RUNS = {
    "baseline": dict(label="冻结基线", params=dict(N=20, k=6.0, m=2, e=0.2)),
    "top1":     dict(label="Top1",     params=dict(N=15, k=7.5, m=2, e=0.3)),
}
# eng_final.py 模块级常量（逐字引用，勿改）
B, X, Q, AMAX, FEE = 0.25, 0.75, 30, 60, 0.03


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def step1_refresh_cache():
    """复用 /tmp/wtc/refresh_cache.py 逻辑：32 线程拉最新日线，失败保留旧缓存。"""
    rc = load_module("refresh_cache", "/tmp/wtc/refresh_cache.py")
    rc.main()


def scan_state(eng, bars, bull, params):
    """状态机影子扫描：逻辑与 eng_final.scan 逐字一致，额外记录末根状态与锁定位置。
    返回 (state_info, trades)。trades 用于与引擎 scan 输出做键集合断言。"""
    N, K, M, E = params['N'], params['k'], params['m'], params['e']
    a = eng.atrs(bars)
    state = 'seek'; streak = 0; box = None; pos = None; trades = []
    for i in range(max(N, 14) + 1, len(bars)):
        if a[i] is None:
            continue
        px = bars[i]['close']
        if pos:
            hold = i - pos['ei']
            if px <= pos['eff'] or px >= pos['tp'] or hold >= Q:
                if px >= pos['tp']:
                    xpx = max(pos['tp'], bars[i]['open'])
                elif px <= pos['eff']:
                    xpx = min(pos['eff'], bars[i]['open'])
                else:
                    xpx = px
                j = i
                while j < len(bars) - 1 and not (bars[j]['low'] <= xpx <= bars[j]['high']):
                    j += 1; xpx = bars[j]['open']
                r = (xpx - pos['ep']) / pos['ep'] * 100 - FEE * (j - pos['ei'])
                trades.append(dict(ep=pos['ep'], ei=pos['ei'], xi=j, xc=round(xpx, 4),
                                   kind=pos['kind'], r=r,
                                   why='止盈' if px >= pos['tp'] else ('止损' if px <= pos['eff'] else '30天期满')))
                pos = None
            continue
        if state == 'seek':
            w = bars[i - N + 1:i + 1]
            Hh = max(x['high'] for x in w); Ll = min(x['low'] for x in w); rng = Hh - Ll
            if rng > 0 and rng < K * a[i]:
                streak += 1
            else:
                streak = 0
            if streak >= M:
                state = 'locked'; box = [Ll, Hh, i, '']; streak = 0
            continue
        L, H, li, fired = box; rng = H - L; age = i - li
        sig = None
        if 'L' not in fired and px > H + B * a[i]:
            sig = ('bk', px)
        elif ('L' not in fired and bull.get(bars[i]['time']) and bars[i]['low'] <= L + E * rng):
            sig = ('fd', px)
        if sig is None and (px > H + X * a[i] or px < L - X * a[i] or age > AMAX):
            state = 'seek'; box = None; continue
        if sig:
            kind, ep = sig; box[3] += 'L'
            tp = H + a[i] if kind == 'bk' else H
            disp = ep - 1.5 * a[i] if kind == 'bk' else L
            eff = disp - 0.3 * a[i]
            risk = (ep - disp) / ep * 100
            if eff > 0 and risk <= 8.0:
                pos = dict(ep=ep, tp=tp, disp=disp, eff=eff, ei=i, kind=kind)
    # ---- 末根状态快照 ----
    i = len(bars) - 1; last = bars[i]['close']; info = None
    if pos:
        info = dict(mode='持仓中', kind=pos['kind'], ep=round(pos['ep'], 4), tp=round(pos['tp'], 4),
                    disp=round(pos['disp'], 4), eff=round(pos['eff'], 4), days=i - pos['ei'], last=last)
    elif box:
        L, H, li, fired = box
        al = a[i]
        trig = round(H + B * al, 4) if al else round(H, 4)
        rng = H - L
        info = dict(mode='箱体锁定', top=round(H, 4), bot=round(L, 4), age=i - li, last=last,
                    trig=trig, dist=round((trig - last) / last * 100, 2),
                    pos_in_box=round((last - L) / rng, 2) if rng > 0 else 0.0,
                    fired=bool(fired), li=li)
    elif streak >= 1:
        info = dict(mode='箱体搜索', seek_streak=streak, seek_need=M, N=N, last=last)
    return info, trades


def step2_engine_scan():
    eng = load_module("eng_final", os.path.join(ENG_DIR, "eng_final.py"))
    pool, dropped = eng.load_pool(CACHE_DIR)
    bull = eng.build_idx_bull(pool)
    out_runs = {}
    for key, rd in RUNS.items():
        # 引擎权威跑数（V2 可实现出场记账）
        trs, agg = eng.collect(rd['params'], pool, bull, v1=False)
        trs_main = [t for t in trs if t['et'] >= MAIN_WINDOW]
        # 影子状态扫描：卡片 + 一致性断言（交易键集合必须与引擎完全一致）
        cards, mismatch = [], []
        for tkr in sorted(pool):
            info, my_trs = scan_state(eng, pool[tkr], bull, rd['params'])
            k_eng = {(t['ei'], t['xi'], t['kind']) for t in trs if t['tkr'] == tkr}
            k_my = {(t['ei'], t['xi'], t['kind']) for t in my_trs}
            if k_eng != k_my:
                mismatch.append(tkr)
            if info:
                cards.append(dict(tkr=tkr, **info))
        assert not mismatch, f"[一致性断言失败] {key}: {mismatch}"
        cards.sort(key=lambda c: (c['mode'] != '持仓中', c.get('dist', 99) if c['mode'] == '箱体锁定' else 99))
        recent = sorted([t for t in trs_main
                         if t['xt'] >= (datetime.date.today() - datetime.timedelta(days=RECENT_DAYS)).isoformat()],
                        key=lambda t: (t['xt'], t['tkr']), reverse=True)
        rs = [t['r'] for t in recent]
        st = dict(total=len(rs), wins=len([r for r in rs if r > 0]),
                  mean=round(sum(rs) / len(rs), 2) if rs else 0.0)
        out_runs[key] = dict(label=rd['label'], params=rd['params'],
                             cards=cards, recent=[
                                 dict(tkr=t['tkr'], ep=t['ep'], xi=t['xi'], xc=t['xc'],
                                      kind=t['kind'], r=round(t['r'], 2), why=t['why'], xt=t['xt'])
                                 for t in recent],
                             stats=st,
                             main_stats=eng.stats(trs_main))
    return eng, pool, dropped, out_runs


def step3_verify_sample(pool, out_runs):
    """抽 3 只锁定箱体：独立用缓存原始 bars 复核 top/bot（=锁定窗口 max(high)/min(low)）。"""
    checks = []
    for t in ('AAPLUSDT', 'AVGOUSDT', 'BTCUSDT'):
        c = next((c for c in out_runs['baseline']['cards'] if c['tkr'] == t and c['mode'] == '箱体锁定'), None)
        if not c:
            continue
        bars = pool[t]
        N = RUNS['baseline']['params']['N']
        w = bars[c['li'] - N + 1:c['li'] + 1]
        top_chk = round(max(x['high'] for x in w), 4)
        bot_chk = round(min(x['low'] for x in w), 4)
        checks.append(dict(tkr=t, card_top=c['top'], raw_top=top_chk, card_bot=c['bot'], raw_bot=bot_chk,
                           ok=(abs(top_chk - c['top']) < 1e-6 and abs(bot_chk - c['bot']) < 1e-6)))
    assert all(c['ok'] for c in checks) and checks, "抽样核对失败"
    return checks


HTML_TMPL = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📦 箱体引擎 · 丁导K线交易系统</title>
<style>
body{background:#0d1117;color:#e6edf3;font-family:-apple-system,sans-serif;margin:0;padding:16px}
h1{font-size:20px} a{color:#58a6ff;text-decoration:none}
.meta{color:#8b949e;font-size:12px;margin-bottom:12px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px;margin:8px 0;font-size:14px}
.hold{border-left:4px solid #f59e0b}.lock{border-left:4px solid #30363d}.seek{border-left:4px solid #58a6ff;opacity:.75}
.tk{font-weight:bold;font-size:16px}
.buy{color:#ff2d2d;font-weight:bold}.sell{color:#16a34a;font-weight:bold}
.line{color:#8b949e;font-size:12px;margin-top:4px}
.stat{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px;margin:8px 0}
table{width:100%;border-collapse:collapse;font-size:12px}
td,th{border-bottom:1px solid #21262d;padding:4px 6px;text-align:left}
.up{color:#ff2d2d}.dn{color:#16a34a}
.sbar{position:relative;height:22px;background:#21262d;border-radius:4px;margin-top:6px}
.sfill{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#16a34a55,#f59e0b55)}
.sline{position:absolute;top:2px;font-size:10px;padding:0 4px}
.sline.stop{left:0;color:#8b949e}.sline.trg{right:0;color:#f59e0b}
.ptabs{margin:8px 0}.ptabs button{background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:6px;padding:4px 12px;margin-right:6px;cursor:pointer;font-size:12px}
.ptabs button.on{color:#e6edf3;border-color:#58a6ff}
footer{color:#8b949e;font-size:11px;margin-top:16px;line-height:1.6}
</style></head><body>
<h1>📦 箱体引擎 · 丁导K线交易系统</h1>
<div class="meta" id="meta">加载中…</div>
<div style="background:#5a1e1e;border:1px solid #f85149;color:#ffb3b3;border-radius:8px;padding:10px;margin:8px 0;font-size:13px"><b>⚠️ 诚实声明（空头席复核 2026-10-15）</b>：本策略为防守型工具，收益与池贝塔强相关——剔除同期池等权涨幅后无独立超额；回测含幸存者偏差（池=当前存续票，估计 ≥+9pp 高估，务必打折看待）；年化指标曾因计算错误高估已修正。本页为本机复刻版：口径=V2 可实现出场（触发仍为 V1 收盘判定）+ 清洗后 144 标的池，与权威引擎 eng_final.py 同源同数。仓位与买卖决策请勿仅依赖本页。</div>
<div class="ptabs" id="ptabs"></div>
<div id="cards"></div>
<div class="stat"><b>近30日已平交易</b><div id="stat" class="line"></div>
<table id="hist"></table></div>
<footer id="foot"></footer>
<script>
let DATA=null,CUR='baseline';
function render(){
  const d=DATA,r=d.runs[CUR];
  document.getElementById('meta').textContent='生成于 '+d.generated+' · 版本 '+d.version+
    ' · 参数组 '+r.label+' N='+r.params.N+' k='+r.params.k+' m='+r.params.m+' e='+r.params.e+
    ' · 牛市闸=idx>MA50 · 池='+d.pool.n+' 标的 · seed='+d.seed;
  const tb=document.getElementById('ptabs');tb.innerHTML='';
  Object.keys(d.runs).forEach(k=>{
    const b=document.createElement('button');b.textContent=d.runs[k].label+' N'+r2(d.runs[k].params);
    if(k===CUR)b.className='on';b.onclick=()=>{CUR=k;render();};tb.appendChild(b);});
  const cs=document.getElementById('cards');cs.innerHTML='';
  (r.cards||[]).forEach(c=>{
    const el=document.createElement('div');
    if(c.mode==='持仓中'){
      el.className='card hold';
      el.innerHTML='<span class="tk">'+c.tkr+'</span> <span class="buy">['+(c.kind==='bk'?'突破持仓':'回归持仓')+']</span> '+c.mode+
        '<div class="line">买入 '+c.ep+' → 止盈 '+c.tp+' | 显示止损 '+c.disp+' | 有效止损 '+c.eff+
        ' | 已持 '+c.days+' 天 | 现价 '+c.last+'</div>';
    }else if(c.mode==='箱体锁定'){
      el.className='card lock';
      const pct=Math.max(0,Math.min(100,(c.pos_in_box||0.5)*100));
      const near=(c.dist!==undefined&&c.dist<=1.5);
      el.innerHTML='<span class="tk">'+c.tkr+'</span> '+c.mode+(near?' <span class="buy">⚡接近触发('+c.dist+'%)</span>':'')+
        '<div class="sbar"><div class="sfill" style="width:'+pct+'%"></div>'+
        '<span class="sline stop">箱底 '+c.bot+'</span><span class="sline trg">触发 '+c.trig+'</span></div>'+
        '<div class="line">箱顶 '+c.top+' / 箱底 '+c.bot+' | 箱龄 '+c.age+' 天 | 现价 '+c.last+
        ' | 距突破触发 <b>'+c.dist+'%</b>（收盘判定，盘中触摸≠买入）</div>';
    }else{
      el.className='card seek';
      el.innerHTML='<span class="tk">'+c.tkr+'</span> 箱体搜索 seek '+c.seek_streak+'/'+c.seek_need+
        '<div class="line">N='+c.N+' 窗口收紧计数中 · 现价 '+c.last+'</div>';
    }
    cs.appendChild(el);});
  const s=r.stats||{};
  document.getElementById('stat').textContent='共 '+s.total+' 笔 · 胜 '+s.wins+' 笔 · 单笔均值 '+s.mean+'%（含资金费，收盘判定口径，主窗 et≥2025-06-01）';
  const h=document.getElementById('hist');
  h.innerHTML='<tr><th>标的</th><th>买</th><th>卖</th><th>收益</th><th>原因</th><th>日期</th></tr>';
  (r.recent||[]).forEach(x=>{
    const tr=document.createElement('tr');
    tr.innerHTML='<td>'+x.tkr+'</td><td class="buy">'+x.ep+'</td><td class="sell">'+x.xc+'</td>'+
      '<td class="'+(x.r>0?'up':'dn')+'">'+(x.r>0?'+':'')+x.r+'%</td><td>'+x.why+'</td><td>'+x.xt+'</td>';
    h.appendChild(tr);});
  document.getElementById('foot').innerHTML='seed='+d.seed+' · 口径：'+d.caliber.fill+'；触发：'+d.caliber.trigger+
    ' · 复现：PYTHONHASHSEED='+d.seed+' python3 generate_page.py';
}
function r2(p){return p.N+'/k'+p.k+'/m'+p.m+'/e'+p.e}
fetch('box_live.json?ts='+Date.now()).then(r=>r.json()).then(d=>{DATA=d;render();})
 .catch(e=>{document.getElementById('meta').textContent='数据加载失败：'+e});
</script></body></html>
"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print('[1/4] 32线程刷新行情缓存…', flush=True)
    step1_refresh_cache()
    print('[2/4] 引擎扫描（baseline + top1 两组冻结参数）…', flush=True)
    eng, pool, dropped, runs = step2_engine_scan()
    checks = step3_verify_sample(pool, runs)
    print('[3/4] 抽样核对：', json.dumps(checks, ensure_ascii=False), flush=True)
    data = dict(
        generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        version='box-web-v1.0(本机权威引擎复刻)',
        seed=SEED,
        params=runs['baseline']['params'],
        params_top1=runs['top1']['params'],
        caliber=dict(
            trigger='V1 收盘判定: close<=eff / close>=tp / hold>=30（信号序列零改动）',
            fill='V2 可实现价: 止损=min(eff,open) 止盈=max(tp,open) 30bar=close；须落在当根[low,high]否则顺延下一根 open',
            funding='0.03%/bar ×(出场bar-入场bar)',
            pool='清洗 low>0/close>0/OHLC 自洽 且 bars>=100 → %d 标的（幸存者偏差≥+9pp，打折看待）' % len(pool),
            idx='池内标的等权收盘均价 > MA50 牛闸',
            main_window='入场日 et>=%s' % MAIN_WINDOW),
        pool=dict(n=len(pool), dropped=dropped),
        runs={k: dict(label=v['label'], params=v['params'], stats=v['stats'],
                      main_stats=v['main_stats'], cards=v['cards'], recent=v['recent'])
              for k, v in runs.items()},
    )
    jp = os.path.join(OUT_DIR, 'box_live.json')
    with open(jp, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    hp = os.path.join(OUT_DIR, 'index.html')
    with open(hp, 'w') as f:
        f.write(HTML_TMPL)
    print('[4/4] 交付复制 → %s 与 %s' % (DELIVER_DIR, REPO_DIR), flush=True)
    for dst in (DELIVER_DIR, REPO_DIR):
        os.makedirs(dst, exist_ok=True)
        shutil.copy2(hp, os.path.join(dst, 'index.html'))
        shutil.copy2(jp, os.path.join(dst, 'box_live.json'))
        shutil.copy2(os.path.abspath(__file__), os.path.join(dst, 'generate_page.py'))
    for k, v in runs.items():
        print(f"{k}: 卡片 {len(v['cards'])} 张 · 近30日 {v['stats']['total']} 笔 胜{v['stats']['wins']} 均值 {v['stats']['mean']}% · 主窗 {v['main_stats']}")
    print('一致性断言（影子扫描 vs 引擎交易键集合）= PASS；抽样 top/bot 核对 = PASS')


if __name__ == '__main__':
    main()
