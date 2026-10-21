#!/usr/bin/env python3
# generate_page.py — 箱体引擎状态页一键生成器（幂等）
# 流程：32线程刷缓存 → import 本机权威引擎 eng_final.py（禁止修改，仅复用）跑两组冻结参数
#       → 状态机影子扫描输出当前箱体卡片（与引擎交易键集合断言一致）→ 渲染同款风格 HTML + JSON
# 复现：PYTHONHASHSEED=42 python3 /tmp/web_build/generate_page.py
import sys, os, json, importlib.util, random, datetime, shutil

SEED = 42
random.seed(SEED)

# 自足性 WO：默认全部指向本仓库（全新机器 clone 即跑）；env 可覆盖回旧机路径
_HERE      = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR   = os.environ.get("BOX_BUILD_DIR", "/tmp/web_build")
OUT_DIR     = os.path.join(BUILD_DIR, "out")
CACHE_DIR   = os.environ.get("BOX_CACHE_DIR", "/tmp/box_cache")
ENG_DIR     = os.environ.get("BOX_ENG_DIR", os.path.join(_HERE, "engine_snapshot"))
POOL_FILE   = os.environ.get("BOX_POOL", os.path.join(_HERE, "engine_snapshot", "cleaned_pool.json"))
REFRESH_PY  = os.environ.get("BOX_REFRESH_PY", os.path.join(_HERE, "research", "wtc", "refresh_cache.py"))
DELIVER_DIR = os.environ.get("BOX_DELIVER_DIR", _HERE)   # 交付目录=仓库根（Pages 由 git push 送达）
REPO_DIR    = os.environ.get("BOX_REPO_DIR", _HERE)
MAIN_WINDOW = "2025-06-01"
RECENT_DAYS = 30

# 两组冻结参数（工单要求：N20/k6.0/m2 冻结参数 + Top1 参数）
RUNS = {
    "baseline": dict(label="冻结基线", params=dict(N=20, k=6.0, m=2, e=0.2)),
    "top1":     dict(label="Top1",     params=dict(N=15, k=7.5, m=2, e=0.3)),
}
# eng_final.py 模块级常量（逐字引用，勿改）
B, X, Q, AMAX, FEE = 0.25, 0.75, 30, 60, 0.03

# 双轮标注（交易分析团队终裁 2026-10-19）：云端主轮已双轮（09:00 判定级 / 21:00 盘中快照，cron 0 0 9,21 * * *），
# 按生成时北京时间小时打 round_type 标，防止 21:00 轮被误读为当日收盘判定。
RT_JUDGE = '判定级'
RT_SNAP  = '盘中快照·不可操作'


def round_type_for_hour(hour):
    """北京时间小时 → 轮次标注：8-12 时区间=09:00 判定级；19-23（21:00 轮）与其余时段
    一律保守默认=盘中快照·不可操作。不改主扫描流程、不动 fd 信号判定逻辑。"""
    if 8 <= hour < 12:
        return RT_JUDGE
    return RT_SNAP


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- WO-UX-A01：箱体判定级 forming-K 剔除（唯一依据=engine_f1/METHOD_BOOK_DECBAR.md §二，
#      照 F1 trim_and_guard 口径逐字移植；锚回归：10-19 dirty 输入→BULL_OPEN=false/
#      BULL_ASOF=2026-10-17，正常输入→闸与 F1 同步）。作用在数据加载层：box 缓存装载后、
#      build_idx_bull 之前；BULL_ASOF 语义改「最后完整日」。----
GUARD_LOG_F = os.path.join(_HERE, 'box_guard.log')
BOX_SETTLE_RULE = '日K 00:00 UTC（北京 08:00）落定'


def _log_box_guard(kind, payload):
    """guard 事件日志（append-only JSONL，学 f1_signal._log_guard，合规席条款）。"""
    try:
        rec = {'ts': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), 'kind': kind}
        rec.update(payload)
        with open(GUARD_LOG_F, 'a') as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
    except Exception:
        pass


def trim_and_guard_pool(pool, now=None):
    """剔除未收盘 forming 盘中K并基于最后完整日判定（METHOD_BOOK_DECBAR.md §二 S1–S4 逐字）；
    拒绝仅保留两类（fail-closed 宁拒勿漏，任一命中即拒）：
    - R-陈旧：today_utc − last_complete > 7 自然日（数据陈旧/断源/断更）
    - R-错位：today_utc 为工作日 且（距 last_complete > 4 自然日 或 last_complete 落在周末）
      （命中且 R-陈旧未命中 → 日志标 CALENDAR_SUSPECT，NY 连续假日留人工核）
    通过 → settled=True、asof=last_complete；trimmed 非空 → 日志记 TRIM_INTRADAY。
    返回 (pool_settled, guard)。"""
    now = now or datetime.datetime.utcnow()
    today = datetime.date(now.year, now.month, now.day)
    today_iso = today.isoformat()
    trimmed = sorted({b['time'] for bars in pool.values() for b in bars
                      if b['time'] >= today_iso})
    pool_settled = {t: [b for b in bars if b['time'] < today_iso]
                    for t, bars in pool.items()}
    base = {'trimmed': trimmed, 'today_utc_date': today_iso, 'settle_rule': BOX_SETTLE_RULE}
    dates = sorted({b['time'] for bars in pool_settled.values() for b in bars})
    if not dates:
        return pool_settled, dict(base, settled=False, check='NO_SETTLED_BAR',
                                  last_complete=None,
                                  reason='剔除 forming 盘中K后无任何完整日K，禁止进入牛闸判定')
    last_complete = dates[-1]
    gap = (today - datetime.date.fromisoformat(last_complete)).days
    is_weekday = today.weekday() < 5                          # 周一~五（NY 假日未知时宁严）
    weekend_last = datetime.date.fromisoformat(last_complete).weekday() >= 5
    stale = bool(gap > 7)                                     # R-陈旧
    misaligned = bool(is_weekday and (gap > 4 or weekend_last))   # R-错位
    base.update(last_complete=last_complete, gap_days=gap)
    if stale or misaligned:
        if misaligned and not stale:
            _log_box_guard('CALENDAR_SUSPECT', dict(base, check='R_MISALIGN'))
        check = 'R_STALE' if stale else 'R_MISALIGN'
        reason = (f'数据陈旧：最后完整日 {last_complete} 距今 {gap} 自然日 > 7'
                  f'（R-陈旧，疑似断源/断更），禁止进入牛闸判定'
                  if stale else
                  f'周调仓时序错位：最后完整日 {last_complete} 距今 {gap} 自然日'
                  f'{"，且落在周末" if weekend_last else ""}（今日为工作日），'
                  '本应已有更新的已收盘 bar 却缺失（R-错位），禁止进入牛闸判定')
        return pool_settled, dict(base, settled=False, check=check, reason=reason)
    if trimmed:
        _log_box_guard('TRIM_INTRADAY', {'trimmed': trimmed, 'last_complete': last_complete})
    return pool_settled, dict(base, settled=True, check='OK', asof=last_complete,
                              reason=('剔除 forming 盘中K后基于最后完整日判定'
                                      if trimmed else '无 forming 盘中K，基于最后完整日判定'))


def step1_refresh_cache():
    """刷新行情缓存：复用 refresh_cache.py（默认仓库内 research/wtc/，env 可指旧机 /tmp/wtc 版），
    32 线程拉最新日线，失败保留旧缓存。"""
    rc = load_module("refresh_cache", REFRESH_PY)
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
    # WO-UX-A01：forming-K 剔除在数据加载层（缓存装载后、build_idx_bull 之前）
    pool, bull_guard = trim_and_guard_pool(pool)
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
    return eng, pool, dropped, out_runs, bull_guard


def step3_verify_sample(pool, out_runs):
    """抽样核对（自足性 WO 修订）：不再硬编码票名（会随日期漂移导致全新机器断言失败），
    改为从当前「箱体锁定」卡中按 tkr 字典序确定性抽最多 3 只，独立用缓存原始 bars
    复核 top/bot（=锁定窗口 max(high)/min(low)）。"""
    locked = sorted([c for c in out_runs['baseline']['cards'] if c['mode'] == '箱体锁定'],
                    key=lambda c: c['tkr'])
    checks = []
    for c in locked[:3]:
        t = c['tkr']
        bars = pool[t]
        N = RUNS['baseline']['params']['N']
        w = bars[c['li'] - N + 1:c['li'] + 1]
        top_chk = round(max(x['high'] for x in w), 4)
        bot_chk = round(min(x['low'] for x in w), 4)
        checks.append(dict(tkr=t, card_top=c['top'], raw_top=top_chk, card_bot=c['bot'], raw_bot=bot_chk,
                           ok=(abs(top_chk - c['top']) < 1e-6 and abs(bot_chk - c['bot']) < 1e-6)))
    assert all(c['ok'] for c in checks), "抽样核对失败"
    if not checks:
        print('[warn] 当日无箱体锁定卡，抽样核对空转（页面仍渲染）', flush=True)
    return checks


HTML_TMPL = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📦 箱体引擎 · 观察站（fd 信号源 + 市况温度计）</title>
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
footer{color:#8b949e;font-size:11px;margin-top:16px;line-height:1.6}
details{margin:8px 0}details>summary{cursor:pointer;padding:6px 10px;background:#161b22;border:1px solid #30363d;border-radius:8px;font-size:13px}
.arch>summary{border-style:dashed;color:#8b949e}
.decl{background:#5a1e1e;border:1px solid #f85149;color:#ffb3b3;border-radius:8px;padding:8px 10px;margin:8px 0;font-size:13px;line-height:1.6}
.decl details{margin:4px 0 0}.decl summary{background:none;border:none;color:#ffb3b3;padding:0;font-size:12px}
.thermo{background:#102a1a;border:1px solid #16a34a;color:#c9d1d9;border-radius:8px;padding:10px;margin:8px 0;font-size:14px}
.thermo.off{background:#2a1212;border-color:#f85149}
.fdhead{border:1px solid #58a6ff;border-radius:8px;padding:8px 10px;margin:8px 0;font-size:13px;background:#0d1a2d}
.warnbk{background:#24292e;border:1px solid #30363d;color:#8b949e;border-radius:6px;padding:6px 10px;font-size:12px;margin:6px 0}
.bkcard{opacity:.55;filter:grayscale(.7);border-left:4px solid #30363d}
.bktag{display:inline-block;background:#30363d;color:#8b949e;border-radius:4px;padding:1px 6px;font-size:11px;margin-left:6px}
.fdtag{display:inline-block;background:#1f3a5f;color:#58a6ff;border-radius:4px;padding:1px 6px;font-size:11px;margin-left:6px}
.warnfd{color:#f59e0b;font-size:12px}
.linkbar{margin:10px 0;font-size:13px}
.rt{display:inline-block;border-radius:4px;padding:1px 6px;font-size:11px;font-weight:bold;margin-left:6px;vertical-align:1px}
.rt.judge{background:#12301c;color:#3fb950;border:1px solid #16a34a}
.rt.snap{background:#33270a;color:#e3b341;border:1px solid #f59e0b}
.rt.unknown{background:#30363d;color:#8b949e;border:1px solid #30363d}
</style></head><body>
<h1>📦 箱体引擎 · 观察站（fd 信号源 + 市况温度计）</h1>
<div class="meta" id="meta">加载中…</div>
<div class="meta" id="roundline"></div>
<div class="decl">📦 <b>观察站——本页只看不操作，操作指令只在 F1 页（/f1/）</b>
→ <a href="f1/index.html">去 F1 运行页</a> · <a href="f1/manual.html">📖 F1 说明书</a> · <a href="box/manual.html">📖 本页使用说明</a>
<details><summary>展开诚实声明（空头席复核 2026-10-15）</summary><div style="margin-top:6px">本策略为防守型工具，收益与池贝塔强相关——剔除同期池等权涨幅后无独立超额；回测含幸存者偏差（池=当前存续票，估计 ≥+9pp 高估，务必打折看待）；年化指标曾因计算错误高估已修正。本页为本机复刻版：口径=V2 可实现出场（触发仍为 V1 收盘判定）+ 清洗后 144 标的池，与权威引擎 eng_final.py 同源同数。仓位与买卖决策请勿仅依赖本页。</div></details></div>
<div class="thermo" id="thermo">温度计加载中…</div>
<div class="fdhead"><b>fd 信号参考区</b>（冻结基线 N20/k6.0/m2/e0.2 · v1.0 验收参数）· <b>fd 信号 · 收盘判定 · 参考非指令</b></div>
<div id="fdmain"></div>
<details class="arch"><summary>⛔ bk 突破信号 · 已穷举归档 · 非信号 · 仅存档对照（点击展开）</summary>
<div class="warnbk">bk 突破买入信号已经穷举研究判死归档：<b>非信号、不下单、不参与任何触发提示</b>。以下内容仅作引擎历史账存档对照，与 fd 主区无关。</div>
<div id="bkcards"></div>
<div class="stat"><b>bk 近30日已平交易（存档对照）</b><table id="bkhist"></table></div>
</details>
<details class="arch"><summary>🔬 研究对照 Top1（N15/k7.5/m2/e0.3 · 候选研究组 · 非实盘）（点击展开）</summary>
<div class="warnbk">Top1 为 R2 回测候选参数组，<b>从未实盘授权</b>；与冻结基线是两套平行研究视角，<b>没有哪个是"该跟的"</b>。本区仅研究对照，不构成操作依据。</div>
<div id="t1cards"></div>
<div class="stat"><b>Top1 近30日已平交易（研究对照·非实盘）</b><div id="t1stat" class="line"></div><table id="t1hist"></table></div>
</details>
<div class="stat"><b>近30日绩效（冻结基线 · 负数如实展示）</b><div id="stat" class="line"></div>
<div class="line">⚠️ 近期表现≠长期统计：近30日均值含 bk 归档单，主窗长期口径见下方主窗统计。</div>
<table id="hist"></table><div id="mainstat" class="line" style="margin-top:6px"></div></div>
<div class="linkbar">🔗 <a href="box/manual.html">📖 使用说明 manual.html</a> · <a href="f1/index.html">📊 F1 运行页</a> · <a href="f1/manual.html">📖 F1 说明书</a></div>
<footer id="foot"></footer>
<script>
const BULL_OPEN=__BULL_OPEN__;const BULL_ASOF='__BULL_ASOF__';const BULL_NOTE='__BULL_NOTE__';
let DATA=null;
function render(){
  const d=DATA,r=d.runs.baseline,p=r.params;
  document.getElementById('meta').textContent='生成于 '+d.generated+' · 版本 '+d.version+
    ' · 主区=冻结基线 N='+p.N+' k='+p.k+' m='+p.m+' e='+p.e+
    ' · 池='+d.pool.n+' 标的 · seed='+d.seed+' · 牛闸快照='+BULL_ASOF+BULL_NOTE;
  const rt=d.round_type||'轮次未标注';
  const rtCls=(rt==='判定级')?'rt judge':((rt==='盘中快照·不可操作')?'rt snap':'rt unknown');
  document.getElementById('roundline').innerHTML='本轮类型 <span class="'+rtCls+'">'+rt+
    '</span> · 21:00 轮为盘中快照，仅供参考，fd 信号一律以收盘判定为准';
  const cs=r.cards||[];
  const nLock=cs.filter(c=>c.mode==='箱体锁定').length,nSeek=cs.filter(c=>c.mode==='箱体搜索').length;
  const th=document.getElementById('thermo');
  th.className='thermo'+(BULL_OPEN?'':' off');
  const mood=(!BULL_OPEN)?'牛闸关闭：非箱体策略的天气，fd 回踩信号不触发——只看不动。'
    :(nLock>=15?'牛闸开放 + 锁定 '+nLock+' 张：池子普遍横盘蓄势，是箱体策略的天气。'
    :'牛闸开放 + 锁定 '+nLock+' 张（少）：行情偏趋势、无箱可做，耐心等池子降温收窄。');
  th.innerHTML='🌡️ 市况温度计：'+(BULL_OPEN?'🟩 牛闸开放（池均价 idx > MA50）':'🟥 牛闸关闭（池均价 idx < MA50）')+
    ' · 箱体锁定 <b>'+nLock+'</b> 张 / 搜索中 '+nSeek+' 只<div class="line">'+mood+'（锁定多=普遍横盘蓄势，少=trending 无箱）· 牛闸快照 '+BULL_ASOF+BULL_NOTE+'</div>';
  const fm=document.getElementById('fdmain');fm.innerHTML='';
  const e=p.e;
  cs.forEach(c=>{
    if(c.mode==='持仓中'&&c.kind==='bk')return;            // bk 不入 fd 主区（折叠区另渲染）
    const el=document.createElement('div');
    if(c.mode==='持仓中'){
      el.className='card hold';
      el.innerHTML='<span class="tk">'+c.tkr+'</span> <span class="buy">[fd 回归持仓]</span> '+c.mode+
        '<span class="fdtag">fd · 收盘判定 · 参考非指令</span>'+
        '<div class="line">买入 '+c.ep+' → 止盈 '+c.tp+' | 显示止损 '+c.disp+' | 有效止损 '+c.eff+
        ' | 已持 '+c.days+' 天 | 现价 '+c.last+'</div>';
    }else if(c.mode==='箱体锁定'){
      el.className='card lock';
      const pct=Math.max(0,Math.min(100,(c.pos_in_box||0.5)*100));
      const rng=c.top-c.bot,zone=+(c.bot+e*rng).toFixed(4);
      const near=(BULL_OPEN&&c.last<=zone);
      el.innerHTML='<span class="tk">'+c.tkr+'</span> '+c.mode+
        (near?' <span class="buy">⚡接近 fd 回踩观察区</span>':'')+
        '<div class="sbar"><div class="sfill" style="width:'+pct+'%"></div>'+
        '<span class="sline stop">箱底 '+c.bot+'</span><span class="sline trg">箱顶 '+c.top+'</span></div>'+
        '<div class="line">箱顶 '+c.top+' / 箱底 '+c.bot+' | 箱龄 '+c.age+' 天 | 现价 '+c.last+
        ' | fd 回踩观察区 ≤'+zone+'</div>'+
        '<div class="warnfd">⚡=现价进入 fd 回踩观察区（收盘判定，盘中触摸≠买入）· 参考观察，非买入指令'+(BULL_OPEN?'':' · 牛闸关闭，fd 不触发')+'</div>';
    }else{
      el.className='card seek';
      el.innerHTML='<span class="tk">'+c.tkr+'</span> 箱体搜索 seek '+c.seek_streak+'/'+c.seek_need+
        '<div class="line">N='+c.N+' 窗口收紧计数中 · 现价 '+c.last+'</div>';
    }
    fm.appendChild(el);});
  const bkHold=cs.filter(c=>c.mode==='持仓中'&&c.kind==='bk');
  const bc=document.getElementById('bkcards');bc.innerHTML='';
  bkHold.forEach(c=>{
    const el=document.createElement('div');el.className='card bkcard';
    el.innerHTML='<span class="tk">'+c.tkr+'</span> [突破持仓] '+c.mode+'<span class="bktag">⛔ bk·已归档非信号</span>'+
      '<div class="line">买入 '+c.ep+' → 止盈 '+c.tp+' | 显示止损 '+c.disp+' | 有效止损 '+c.eff+
      ' | 已持 '+c.days+' 天 | 现价 '+c.last+'</div>';
    bc.appendChild(el);});
  function histTable(id,rows,bkMark){
    const h=document.getElementById(id);
    h.innerHTML='<tr><th>标的</th><th>买</th><th>卖</th><th>收益</th><th>原因</th><th>日期</th></tr>';
    rows.forEach(x=>{
      const tr=document.createElement('tr');
      tr.innerHTML='<td>'+x.tkr+'</td><td class="buy">'+x.ep+'</td><td class="sell">'+x.xc+'</td>'+
        '<td class="'+(x.r>0?'up':'dn')+'">'+(x.r>0?'+':'')+x.r+'%</td><td>'+x.why+
        (bkMark&&x.kind==='bk'?' <span class="bktag">⛔bk·已归档非信号</span>':'')+'</td><td>'+x.xt+'</td>';
      h.appendChild(tr);});
  }
  const rec=r.recent||[];
  histTable('hist',rec.filter(x=>x.kind==='fd'),false);
  histTable('bkhist',rec.filter(x=>x.kind==='bk'),true);
  const fd=rec.filter(x=>x.kind==='fd'),fr=fd.map(x=>x.r);
  const s=r.stats||{};
  document.getElementById('stat').innerHTML='fd 已平（客户端按 fd 行复算）：共 '+fd.length+' 笔 · 胜 '+
    fr.filter(x=>x>0).length+' 笔 · 单笔均值 '+(fr.length?+(sum(fr)/fd.length).toFixed(2):0)+'%'+
    '（含资金费，收盘判定口径）<br>全口径（含 bk 存档单）：共 '+s.total+' 笔 · 胜 '+s.wins+' 笔 · 单笔均值 '+s.mean+'%';
  const ms=r.main_stats||{};
  document.getElementById('mainstat').textContent='主窗（et≥'+(d.caliber?d.caliber.main_window.replace('入场日 et>=',''):'2025-06-01')+'）长期统计：n='+ms.n+' · pf='+ms.pf+' · 单笔均值 '+ms.mean+'% · 胜率 '+ms.win_pct+'%（含 bk 历史账，bk 已归档不再产生新信号）';
  const t1=d.runs.top1||{};
  const tc=document.getElementById('t1cards');tc.innerHTML='';
  (t1.cards||[]).forEach(c=>{
    const el=document.createElement('div');
    const isBk=(c.mode==='持仓中'&&c.kind==='bk');
    el.className='card '+(c.mode==='持仓中'?'hold':(c.mode==='箱体锁定'?'lock':'seek'))+(isBk?' bkcard':'');
    el.innerHTML='<span class="tk">'+c.tkr+'</span> '+c.mode+(isBk?'<span class="bktag">⛔ bk·已归档非信号</span>':'')+
      '<div class="line">'+(c.mode==='持仓中'?('买入 '+c.ep+' → 止盈 '+c.tp+' | 已持 '+c.days+' 天 | 现价 '+c.last):
        (c.mode==='箱体锁定'?('箱顶 '+c.top+' / 箱底 '+c.bot+' | 箱龄 '+c.age+' 天 | 现价 '+c.last):
        ('seek '+c.seek_streak+'/'+c.seek_need+' · 现价 '+c.last)))+'</div>';
    tc.appendChild(el);});
  const t1r=t1.recent||[],t1s=t1.stats||{};
  histTable('t1hist',t1r,true);
  document.getElementById('t1stat').textContent='Top1（非实盘）：共 '+t1s.total+' 笔 · 胜 '+t1s.wins+' 笔 · 单笔均值 '+t1s.mean+'%';
  document.getElementById('foot').innerHTML='seed='+d.seed+' · 口径：'+d.caliber.fill+'；触发：'+d.caliber.trigger+
    ' · 复现：PYTHONHASHSEED='+d.seed+' python3 generate_page.py';
}
function sum(a){return a.reduce((x,y)=>x+y,0)}
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
    eng, pool, dropped, runs, bull_guard = step2_engine_scan()
    checks = step3_verify_sample(pool, runs)
    print('[3/4] 抽样核对：', json.dumps(checks, ensure_ascii=False), flush=True)
    bj_hour = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).hour
    round_type = round_type_for_hour(bj_hour)
    data = dict(
        generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        round_type=round_type,
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
        bull_guard={k: bull_guard[k] for k in
                    ('trimmed', 'today_utc_date', 'last_complete', 'check', 'reason')
                    if k in bull_guard},   # WO-UX-A01 trim 审计字段
        runs={k: dict(label=v['label'], params=v['params'], stats=v['stats'],
                      main_stats=v['main_stats'], cards=v['cards'], recent=v['recent'])
              for k, v in runs.items()},
    )
    jp = os.path.join(OUT_DIR, 'box_live.json')
    with open(jp, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    hp = os.path.join(OUT_DIR, 'index.html')
    # 温度计牛闸：复用引擎既有 build_idx_bull（WO-3 禁止触碰 eng_final.py，仅渲染层推导）。
    # WO-UX-A01：pool 已在数据加载层 trim（BULL_ASOF 语义=最后完整日）；guard 拒绝
    # （R-陈旧/R-错位/无完整日K）→ fail-closed 牛闸强制关闭（宁拒勿漏）。
    bull = eng.build_idx_bull(pool)
    if bull_guard.get('settled') and any(bars for bars in pool.values()):
        last_dt = max(b['time'] for bars in pool.values() for b in bars)
        bull_open = bool(bull.get(last_dt, False))
        bull_note = '（落定K）'
    else:
        last_dt = bull_guard.get('last_complete') or bull_guard.get('today_utc_date', '')
        bull_open = False
        bull_note = '（数据守卫拒绝·fail-closed：牛闸强制关闭）'
    html = (HTML_TMPL.replace('__BULL_OPEN__', 'true' if bull_open else 'false')
                      .replace('__BULL_ASOF__', last_dt)
                      .replace('__BULL_NOTE__', bull_note))
    with open(hp, 'w') as f:
        f.write(html)
    print('[4/4] 交付复制 → %s 与 %s' % (DELIVER_DIR, REPO_DIR), flush=True)
    for dst in (DELIVER_DIR, REPO_DIR):
        os.makedirs(dst, exist_ok=True)
        for src in (hp, jp, os.path.abspath(__file__)):
            d = os.path.join(dst, os.path.basename(src))
            if os.path.abspath(src) == os.path.abspath(d):
                continue                      # 同文件（脚本已在仓库根运行）不复制
            shutil.copy2(src, d)
    for k, v in runs.items():
        print(f"{k}: 卡片 {len(v['cards'])} 张 · 近30日 {v['stats']['total']} 笔 胜{v['stats']['wins']} 均值 {v['stats']['mean']}% · 主窗 {v['main_stats']}")
    print('一致性断言（影子扫描 vs 引擎交易键集合）= PASS；抽样 top/bot 核对 = PASS')


if __name__ == '__main__':
    main()
