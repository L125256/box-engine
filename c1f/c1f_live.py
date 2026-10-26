#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C1-fut live 入口 · 一条命令出页面
=====================================================================
用途：云端三步任务（拉码 → 拉 144 标喂引擎 → 上传）的中段执行体。
      python3 c1f_live.py  →  写 ./index.html 与 ./out/live.json

自足性：只依赖 numpy 与一个池文件（cleaned_pool.json 的 kept，144 只冻结）。
        不 import 任何一次性别名模块、不含 /workspace 绝对路径、不含 hardcode 日期。

口径（唯一口径书＝《牛闸口径书 v1》，落库 f1/F1_台账口径_v1.md §7.13）：
  ① 池 144 定版；② 判定基准＝最后一根收完整日K（读入即 rows[:-1] 剔 forming）；
  ③ 有效日 C(d) ≥ 0.90×median(C(d'), |d'-d|≤30 天)，7×24 日历（含周末）；
  ④ idx＝有效日等权收盘均价；⑤ MA50＝有效日序列 rolling(50)；⑥ 闸＝idx>MA50 硬比较；
  ⑦ 缺口 主=(MA50-idx)/idx，副=idx/MA50-1（仅括号）；⑧ 八字段同屏。

执行层（与闸分界，见口径书 §11）：
  · 入场只做周一~周五，按「入场那根K的日期」所属星期判定，周六/日不开仓；
  · 周末（北京时间周六、周日）运行本入口：不出新候选，只更新牛闸与持仓状态。

用法：
  python3 c1f_live.py [--cache DIR] [--pool FILE] [--outdir DIR] [--now ISO]
  环境变量：C1_CACHE（缓存目录，默认 /tmp/c1_cache）、C1_POOL、C1_NOW、C1_OUTDIR
"""
import os, sys, json, argparse, datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BJ = datetime.timezone(datetime.timedelta(hours=8))

# ---------------------------------------------------------------- 冻结参数
M_ATR = 3.5            # 止损 = 3.5×ATR
HOLD = 10              # 最长持有 10 根K（第 10 根K 收盘到期）
POS = 0.02             # 每笔仓位占净值（C1 执行版 2% 档）
MMR = 0.010            # 维持保证金率
LIQ_FEE = 0.006        # 强平费率
FEE_TAKER = 0.0005
SLIP = 0.0005
COST_RT = 2 * (FEE_TAKER + SLIP)
MIN_HIST = 60

RATIO, HALFWIN, MA_REG = 0.90, 30, 50
POOL_N = 144

RED_LINE = dict(dev50_max=0.15, ret20_max=0.25, ret60_max=0.60, streak_max=6)
DD120_RET20 = (0.02, 0.12)
F_TIGHT = dict(vol_max=0.045, r20=(0.03, 0.12), dev20=(0.00, 0.06), age_max=10)
FORMS = ('G1', 'S2', 'M1')

CURVE_C = dict(name='C', L=5)     # 2% 仓位 × 5x
CURVE_B = dict(name='B', L=3)     # 2% 仓位 × 3x


# ================================================================ 基本面函数
def sma(x, n):
    c = np.cumsum(np.insert(x, 0, 0.0))
    o = np.full(len(x), np.nan)
    if len(x) >= n:
        o[n - 1:] = (c[n:] - c[:-n]) / n
    return o


def roll_max(x, n):
    o = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        o[i] = x[i - n + 1:i + 1].max()
    return o


def roll_min(x, n):
    o = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        o[i] = x[i - n + 1:i + 1].min()
    return o


def atr14(h, l, c):
    pc = np.empty_like(c)
    pc[0] = np.nan
    pc[1:] = c[:-1]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    tr[0] = h[0] - l[0]
    return sma(tr, 14)


def features(b):
    c, h, l, v = b['close'], b['high'], b['low'], b['volume']
    for k, n in (('ma5', 5), ('ma10', 10), ('ma20', 20), ('ma50', 50)):
        b[k] = sma(c, n)
    b['atr'] = atr14(h, l, c)
    b['hh10'], b['hh20'], b['hh60'], b['hh120'] = roll_max(h, 10), roll_max(h, 20), roll_max(h, 60), roll_max(h, 120)
    b['ll10'] = roll_min(l, 10)
    b['vma20'] = sma(v, 20)
    b['ret1'] = np.r_[0.0, c[1:] / np.maximum(c[:-1], 1e-12) - 1]
    st = np.zeros(len(c), int)
    for i in range(len(c)):
        st[i] = st[i - 1] + 1 if i > 0 and b['ret1'][i] > 0 else (1 if b['ret1'][i] > 0 else 0)
    b['streak'] = st
    return b


# ---------------------------------------------------------------- 读数据
def find_pool(override=None):
    cands = []
    if override:
        cands.append(override)
    if os.environ.get('C1_POOL'):
        cands.append(os.environ['C1_POOL'])
    cands += [os.path.join(HERE, 'cleaned_pool.json'),
              os.path.join(HERE, '..', 'engine_snapshot', 'cleaned_pool.json'),
              '/tmp/cleaned_pool.json']
    for p in cands:
        p = os.path.abspath(p)
        if os.path.isfile(p):
            return p
    sys.exit('FATAL 找不到 cleaned_pool.json（用 --pool 或 C1_POOL 指定）')


def load_bars(cache, pool):
    """读缓存；每只票 rows[:-1] 无条件剔末根（forming），与口径书 §2 操作级规则一致。"""
    if not os.path.isdir(cache):
        sys.exit('FATAL 缓存目录不存在: %s' % cache)
    out, newest = {}, 0.0
    for t in pool:
        f = os.path.join(cache, t + '.json')
        if not os.path.exists(f):
            continue
        rows = sorted(json.load(open(f)), key=lambda r: r['time'])
        if len(rows) > 1:
            rows = rows[:-1]
        out[t] = dict(time=[r['time'] for r in rows],
                      open=np.array([r['open'] for r in rows], float),
                      high=np.array([r['high'] for r in rows], float),
                      low=np.array([r['low'] for r in rows], float),
                      close=np.array([r['close'] for r in rows], float),
                      volume=np.array([r['volume'] for r in rows], float))
        newest = max(newest, os.path.getmtime(f))
    return out, newest


# ---------------------------------------------------------------- 牛闸（口径书 v1）
def gate_v1(bars, pool):
    acc = {}
    for t in pool:
        b = bars.get(t)
        if b is None:
            continue
        for d, c in zip(b['time'], b['close']):
            if np.isfinite(c):
                acc.setdefault(d, []).append(c)
    all_dates = sorted(acc)
    cnt = np.array([len(acc[d]) for d in all_dates], float)
    med = np.array([np.median(cnt[max(0, i - HALFWIN): i + HALFWIN + 1]) for i in range(len(cnt))])
    keep = cnt >= RATIO * med
    kd = [d for d, k in zip(all_dates, keep) if k]
    kidx = np.array([np.mean(acc[d]) for d in kd], float)
    ma = np.full(len(kidx), np.nan)
    for i in range(MA_REG - 1, len(kidx)):
        ma[i] = kidx[i - MA_REG + 1: i + 1].mean()
    gate = np.isfinite(ma) & (kidx > ma)
    run = np.zeros(len(kd), int)
    for i in range(len(kd)):
        run[i] = run[i - 1] + 1 if i and gate[i] else (1 if gate[i] else 0)
    return dict(dates=kd, idx=kidx, ma=ma, gate=gate, run=run,
                n_all=len(all_dates), cnt=cnt, med=med, acc=acc)


def segments(dates, gate):
    segs, cur = [], None
    for d, g in zip(dates, gate):
        if g:
            cur = [d, d] if cur is None else [cur[0], d]
        elif cur:
            segs.append(tuple(cur))
            cur = None
    if cur:
        segs.append(tuple(cur))
    return segs


def seg_of(segs, day):
    for s in segs:
        if s[0] <= day <= s[1]:
            return s
    return None


# ---------------------------------------------------------------- 信号
def form_hit(b, i, form):
    c = b['close']
    ma10, ma20, ma50 = b['ma10'][i], b['ma20'][i], b['ma50'][i]
    if not (np.isfinite(ma50) and np.isfinite(ma20) and np.isfinite(ma10)):
        return False
    px = c[i]
    r20 = px / c[i - 20] - 1 if i >= 20 else np.nan
    dev50 = px / ma50 - 1
    rng10 = (b['hh10'][i] - b['ll10'][i]) / px if np.isfinite(b['hh10'][i]) else 9
    if form == 'S2':
        age = 0
        for j in range(i, max(i - 12, 0), -1):
            if c[j] > b['ma50'][j]:
                age += 1
            else:
                break
        return 2 <= age <= 9 and dev50 <= 0.10 and r20 <= 0.15 and px < b['hh60'][i]
    if form == 'M1':
        return (ma20 > ma50 and px > ma20 and rng10 <= 0.10
                and 0 <= px / ma20 - 1 <= 0.05 and dev50 <= 0.15)
    if form == 'G1':
        return (ma20 > ma50 and px > ma20 and 0 <= r20 <= 0.15 and 0 < dev50 <= 0.12)
    raise KeyError(form)


def red_line(b, i):
    c = b['close']
    ma50 = b['ma50'][i]
    if not np.isfinite(ma50) or i < 60:
        return False, ''
    px = c[i]
    dev50 = px / ma50 - 1
    r20 = px / c[i - 20] - 1
    r60 = px / c[i - 60] - 1
    st = b['streak'][i]
    dd120 = px / b['hh120'][i] - 1 if np.isfinite(b['hh120'][i]) else -9
    if dev50 > RED_LINE['dev50_max']:
        return True, 'dev50>15%'
    if r20 > RED_LINE['ret20_max']:
        return True, 'ret20>25%'
    if r60 > RED_LINE['ret60_max']:
        return True, 'ret60>60%'
    if st >= RED_LINE['streak_max'] + 1:
        return True, 'streak>=7'
    if dd120 > DD120_RET20[0] and r20 > DD120_RET20[1]:
        return True, '贴120日高+ret20>12%'
    return False, ''


def pass_filter(b, i, age):
    if age > F_TIGHT['age_max']:
        return False
    if b['atr'][i] / b['close'][i] > F_TIGHT['vol_max']:
        return False
    r20 = b['close'][i] / b['close'][i - 20] - 1
    if not (F_TIGHT['r20'][0] <= r20 <= F_TIGHT['r20'][1]):
        return False
    dv = b['close'][i] / b['ma20'][i] - 1
    return F_TIGHT['dev20'][0] <= dv <= F_TIGHT['dev20'][1]


def build_events(bars, pool, GM, form):
    ev = []
    for t in pool:
        b = bars.get(t)
        if b is None:
            continue
        n = len(b['time'])
        for i in range(MIN_HIST, n - 1):
            d = b['time'][i]
            g = GM.get(d)
            if not g or not g[0]:
                continue
            if not form_hit(b, i, form):
                continue
            blocked, _ = red_line(b, i)
            if blocked:
                continue
            ev.append(dict(tkr=t, i=i, day=d, gate_age=int(g[1]), form=form))
    return ev


def candidates(bars, pool, GM):
    ev = []
    for form in FORMS:
        for e in build_events(bars, pool, GM, form):
            if not pass_filter(bars[e['tkr']], e['i'], e['gate_age']):
                continue
            ev.append(e)
    ev.sort(key=lambda x: (x['tkr'], x['i']))
    out, seen = [], set()
    for e in ev:
        k = (e['tkr'], e['i'])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out, len(ev)


def build_sig(bars, ev):
    """信号层：次日开盘入场、3.5ATR 止损、10 根K 到期；同标的 10 根K 内不重复开仓。"""
    sig = []
    for e in ev:
        b = bars[e['tkr']]
        i = e['i']
        j0 = i + 1
        if j0 >= len(b['time']):
            continue
        a = float(b['atr'][i])
        px = float(b['close'][i])
        if not (np.isfinite(a) and a > 0 and np.isfinite(px) and px > 0):
            continue
        end = min(j0 + HOLD, len(b['time']) - 1)
        path = [(b['time'][j], float(b['open'][j]), float(b['high'][j]),
                 float(b['low'][j]), float(b['close'][j])) for j in range(j0, end + 1)]
        nom = j0 + HOLD
        sig.append(dict(tkr=e['tkr'], form=e['form'], day=e['day'], i=i, j0=j0,
                        entry_day=b['time'][j0], E=float(b['open'][j0]), atr=a,
                        path=path, due_day=b['time'][end], due_j=end,
                        due_nominal_day=(b['time'][nom] if nom < len(b['time']) else None)))
    sig = [s for s in sig if s['E'] > 0]
    sig.sort(key=lambda x: (x['tkr'], x['i']))
    out, busy = [], {}
    for s in sig:
        if s['i'] <= busy.get(s['tkr'], -1):
            continue
        out.append(s)
        busy[s['tkr']] = s['i'] + HOLD
    out.sort(key=lambda x: (x['day'], x['tkr']))
    return out


def weekday(d):
    return datetime.date.fromisoformat(d).weekday()


# ---------------------------------------------------------------- 撮合与曲线
def liq_px(e0, L):
    if L <= 1:
        return None
    den = 1.0 - MMR - LIQ_FEE
    return e0 * (1.0 - 1.0 / L) / den if den > 0 else 0.0


def sim(s, L, stop_level):
    """逐仓多头；止损与强平谁更靠近入场价者先触发；跳空穿价按开盘价成交。"""
    e0 = s['E']
    q = liq_px(e0, L)
    lvl = stop_level if q is None else max(stop_level, q)
    kind, exit_px, exit_day, jx = 'hold', None, s['due_day'], len(s['path']) - 1
    for k, (dt, o, h, l, c) in enumerate(s['path']):
        if l <= lvl:
            if q is not None and q >= stop_level:
                kind, exit_px = 'liq', min(o, q)
            else:
                kind, exit_px = 'stop', (o if o < stop_level else stop_level)
            exit_day, jx = dt, k
            break
    if kind == 'hold':
        exit_px = s['path'][-1][4]
    if kind == 'liq':
        eqr = -(1.0 + L * LIQ_FEE)
    else:
        eqr = L * (exit_px / e0 - 1.0 - COST_RT)
    return dict(exit_type=kind, exit_px=exit_px, exit_day=exit_day, exit_j=jx,
                eqr=eqr, stop=stop_level, q=q)


def queue_run(sig, L):
    rows = []
    for s in sig:
        r = sim(s, L, s['E'] - M_ATR * s['atr'])
        rows.append(dict(s, **r))
    rows.sort(key=lambda x: (x['entry_day'], x['tkr']))
    eq, used, op, taken = 1.0, 0.0, [], []
    for r in rows:
        d = r['entry_day']
        for o in op:
            if o['exit_day'] < d:
                eq += o['need'] * o['eqr']
                used -= o['need']
        op = [o for o in op if o['exit_day'] >= d]
        need = POS * eq
        if used + need <= eq + 1e-12:
            op.append(dict(exit_day=r['exit_day'], need=need, eqr=r['eqr']))
            used += need
            taken.append(dict(r, need=need))
    for o in op:
        eq += o['need'] * o['eqr']
    return taken, len(rows) - len(taken), eq


def daily_curve(taken, L):
    contrib = {}
    for t in taken:
        need, path, n = t['need'], t['path'], t['exit_j']
        prev, acc = t['E'], 0.0
        for k in range(0, n + 1):
            dt, o, h, l, c = path[k]
            px = t['exit_px'] if k == n else c
            pnl = need * L * (px / prev - 1.0)
            acc += pnl
            contrib[dt] = contrib.get(dt, 0.0) + pnl
            prev = c if k < n else prev
        dt0 = path[0][0]
        extra = (-need * (1.0 + L * LIQ_FEE) - acc) if t['exit_type'] == 'liq' else (-need * L * COST_RT)
        contrib[dt0] = contrib.get(dt0, 0.0) + extra
    if not contrib:
        return [], np.array([1.0])
    ds = sorted(contrib)
    e, cur = [], 1.0
    for d in ds:
        cur += contrib[d]
        e.append(cur)
    return ds, np.array(e, float)


def curve_stats(taken, eq, ds, e):
    rs = np.array([t['eqr'] for t in taken], float) * 100
    peak = np.maximum.accumulate(e) if len(e) else np.array([1.0])
    mdd = float(((peak - e) / peak).max() * 100) if len(e) else 0.0
    return dict(n=len(taken), final=round(float(eq), 4), mdd=round(mdd, 2),
                win=round(float((rs > 0).mean() * 100), 2) if len(rs) else None,
                mean=round(float(rs.mean()), 2) if len(rs) else None,
                span=[ds[0], ds[-1]] if ds else None)


# ---------------------------------------------------------------- 渲染辅助
def pct(v, d=3):
    return (('%.' + str(d) + 'f%%') % v).replace('-', '\u2212')


def px(v):
    if v >= 1000:
        return '%.1f' % v
    if v >= 100:
        return '%.2f' % v
    if v >= 10:
        return '%.3f' % v
    return '%.4f' % v


def curve_svg(ys, w=560, h=150, color='#3fb950'):
    ys = list(ys)
    if len(ys) < 2:
        return ''
    step = max(1, len(ys) // 300)
    ys = ys[::step] + ([ys[-1]] if (len(ys) - 1) % step else [])
    lo, hi = min(ys), max(ys)
    rng = (hi - lo) or 1
    pts = ' '.join('%.1f,%.1f' % (i / max(len(ys) - 1, 1) * (w - 20) + 10,
                                  h - 12 - (v - lo) / rng * (h - 30)) for i, v in enumerate(ys))
    return ('<svg viewBox="0 0 %d %d" width="100%%" height="%d" preserveAspectRatio="none">'
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6"/></svg>'
            % (w, h, h, pts, color))


CSS = """
:root{--bg:#0b1016;--card:#121a23;--line:#1e2a36;--tx:#e6edf3;--dim:#8b9bab;--up:#3fb950;--dn:#f85149;--ac:#d29922;--bl:#388bfd}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:0 18px 50px}
h1{font-size:20px;margin:26px 0 4px}
h2{font-size:15px;margin:30px 0 12px;padding-left:10px;border-left:3px solid var(--bl)}
.sub{color:var(--dim);font-size:12px}
.sub b{color:var(--tx)}
.status{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:14px 0}
.metric{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:11px 13px}
.ml{font-size:12px;color:var(--dim)}
.mv{font-size:20px;font-weight:600;margin:2px 0;font-variant-numeric:tabular-nums}
.ms{font-size:11px;color:var(--dim);line-height:1.5}
.metric.bad .mv{color:var(--dn)}.metric.good .mv{color:var(--up)}
.scroll{overflow-x:auto;border-radius:8px;border:1px solid var(--line)}
table{width:100%;border-collapse:collapse;font-size:12.5px;background:var(--card)}
th,td{padding:8px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{background:#0f1620;color:var(--dim);font-weight:500;font-size:11.5px}
tr:last-child td{border-bottom:none}
tr:hover td{background:#16202b}
.num{text-align:right;font-variant-numeric:tabular-nums}
.tk{font-weight:600;color:#79c0ff}
.note{font-size:12px;color:var(--dim);margin-top:9px;line-height:1.85}
.note b{color:var(--tx)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:820px){.two{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:13px}
.empty{background:var(--card);border:1px dashed var(--line);border-radius:8px;padding:22px 18px;text-align:center}
.empty .t{font-size:15px;font-weight:600;color:var(--tx);margin-bottom:6px}
.empty .s{font-size:12px;color:var(--dim);line-height:1.9}
.banner{background:#2a2113;border:1px solid #6b5320;color:#e3b341;border-radius:8px;padding:10px 14px;font-size:13px;margin:14px 0}
"""


def render(ctx):
    h = []
    h.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>C1-fut · 牛闸与标的清单</title><style>%s</style></head><body><div class="wrap">' % CSS)
    h.append('<h1>C1-fut · 牛闸与标的清单</h1>')
    h.append('<div class="sub">候选清单供人工筛选，非买入指令。｜标的池 144 只（冻结）｜'
             '口径书 <b>F1_台账口径 §7.13</b>｜数据拉取 <b>%s</b>｜生成 <b>%s</b></div>'
             % (ctx['pull_time'], ctx['generated_at'][:16]))

    if ctx['weekend_block']:
        h.append('<div class="banner">周末 · 不开新仓，仅更新牛闸与持仓状态（周六、周日不出新入场候选；'
                 '周一~周五恢复）</div>')

    # ---------------- 一、牛闸
    G = ctx['gate']
    h.append('<h2>一、牛闸（7×24 日历口径）</h2><div class="status">')
    h.append('<div class="metric"><div class="ml">判定基准日</div><div class="mv" style="font-size:16px">%s（%s）</div>'
             '<div class="ms">最后一根收完整日K；当根未收线K剔除</div></div>'
             % (G['asof'], G['asof_wd']))
    h.append('<div class="metric"><div class="ml">池均价 idx</div><div class="mv">%.3f</div>'
             '<div class="ms">有效日 %d 只等权收盘均价</div></div>' % (G['idx'], G['cnt']))
    h.append('<div class="metric"><div class="ml">开闸价（MA50）</div><div class="mv">%.3f</div>'
             '<div class="ms">有效交易日序列 rolling(50)</div></div>' % G['ma'])
    h.append('<div class="metric %s"><div class="ml">闸态</div><div class="mv">%s</div>'
             '<div class="ms">%s（硬比较，无缓冲）</div></div>'
             % ('good' if G['gate'] else 'bad', '开' if G['gate'] else '关',
                'idx &gt; MA50' if G['gate'] else 'idx &lt; MA50'))
    h.append('<div class="metric %s"><div class="ml">缺口（主）(MA50−idx)/idx</div><div class="mv">%s</div>'
             '<div class="ms">副口径 idx/MA50−1 = %s</div></div>'
             % ('good' if G['gate'] else 'bad', pct(G['gap']), pct(G['gap_alt'])))
    h.append('<div class="metric"><div class="ml">参与数</div><div class="mv" style="font-size:16px">%d / %d</div>'
             '<div class="ms">门槛 ≥ %.1f（0.90×±30日中位）</div></div>'
             % (G['cnt'], POOL_N, G['thr']))
    h.append('<div class="metric"><div class="ml">数据拉取时间</div><div class="mv" style="font-size:16px">%s</div>'
             '<div class="ms">%s 文件 mtime</div></div>' % (ctx['pull_time'][5:], ctx['source']))
    h.append('<div class="metric"><div class="ml">开闸段</div><div class="mv" style="font-size:15px">%s → %s</div>'
             '<div class="ms">%s</div></div>'
             % (G['seg'][0], G['seg'][1], G['seg_meta']))
    h.append('</div>')
    h.append('<div class="note"><b>执行口径：牛闸 7×24 计算、入场剔除周末。</b>'
             '牛闸＝市场状态，按日历口径（周末/假日只要参与数 ≥0.90×±30 日中位即为有效日）计算，'
             '闸开＝idx &gt; MA50；缺口主口径 (MA50−idx)/idx，副口径 idx/MA50−1 仅在括号内。'
             '入场＝可执行性，只做周一~周五（按入场那根K的日期所属星期，遇周六/日不开仓）。</div>')

    # ---------------- 二、标的清单
    B = ctx['batch']
    h.append('<h2>二、标的清单（本批：牛闸 %s 开闸）</h2>' % B['open_date'])
    if ctx['weekend_block']:
        h.append('<div class="empty"><div class="t">周末 · 不开新仓</div>'
                 '<div class="s">本批（牛闸 %s 开闸，信号日 %s）当前在持 <b>%d</b> 只。'
                 '周六、周日不出新入场候选，牛闸面板与净值曲线照常更新；周一 09:00 轮起恢复出候选。</div></div>'
                 % (B['open_date'], B['signal_day'], B['live_n']))
    elif B['live_n'] == 0:
        h.append('<div class="empty"><div class="t">本批已全部离场，当前在持 0 只</div>'
                 '<div class="s">%s</div></div>' % B['empty_text'])
    else:
        h.append('<div class="scroll"><table><thead><tr>'
                 '<th>标的</th><th>买入日</th><th>第 10 根K（到期日）</th>'
                 '<th class="num">买入价（次日开盘）</th><th class="num">止损价</th></tr></thead><tbody>')
        for r in B['rows']:
            h.append('<tr><td class="tk">%s</td><td>%s</td><td>%s</td>'
                     '<td class="num">%s</td><td class="num">%s</td></tr>'
                     % (r['tkr'], r['buy_date'], r['due_date'], px(r['entry']), px(r['stop'])))
        h.append('</tbody></table></div>')
        h.append('<div class="note">买入日＝信号次日、按该标的真实K线序列取下一根；'
                 '到期日＝买入日起第 10 根K 的收盘日，不是自然日 +10。'
                 '本批命中 %d 只，去重后 %d 只，其中在持 %d 只。</div>'
                 % (B['raw_n'], B['dedup_n'], B['live_n']))

    # ---------------- 三、净值曲线
    h.append('<h2>三、净值曲线（逐日盯市 · 执行版：剔周末入场）</h2><div class="two">')
    for key, color in (('C', '#3fb950'), ('B', '#58a6ff')):
        c = ctx['curves'][key]
        h.append('<div class="card"><div class="ml">%s 档 · 2%% 仓位 × %dx ｜ 期末 %.4f ｜ 最大回撤 %.2f%% ｜ %d 笔</div>%s</div>'
                 % (key, c['L'], c['final'], c['mdd'], c['n'], curve_svg(c['eq'], color=color)))
    h.append('</div>')
    h.append('<div class="sub" style="margin-top:24px">牛闸读数按《F1_台账口径》§7.13 复算（只读 %s）｜'
             '回测执行版 %d 信号 / %d 笔（%s 至 %s）｜页面由 c1f/c1f_live.py 生成</div>'
             % (ctx['source'], ctx['n_sig'], ctx['curves']['C']['n'],
                ctx['curves']['C']['span'][0], ctx['curves']['C']['span'][1]))
    h.append('</div></body></html>')
    return '\n'.join(h)


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default=os.environ.get('C1_CACHE', '/tmp/c1_cache'))
    ap.add_argument('--pool', default=None)
    ap.add_argument('--outdir', default=os.environ.get('C1_OUTDIR', HERE))
    ap.add_argument('--now', default=os.environ.get('C1_NOW'),
                    help='北京时间 YYYY-MM-DD[THH:MM]，用于周末判定与时间戳（默认取本机时钟）')
    a = ap.parse_args()

    now = (datetime.datetime.fromisoformat(a.now).replace(tzinfo=BJ) if a.now
           else datetime.datetime.now(BJ))
    cache = os.path.abspath(a.cache)
    outdir = os.path.abspath(a.outdir)

    pool_path = find_pool(a.pool)
    pool = [x['tkr'] for x in json.load(open(pool_path))['kept']]
    if len(pool) != POOL_N:
        sys.exit('FATAL 池不是 %d 只（实际 %d），口径书 §1 禁扩禁缩' % (POOL_N, len(pool)))

    bars, newest = load_bars(cache, pool)
    if len(bars) < POOL_N:
        sys.exit('FATAL 缓存缺标的：%d/%d 只（缺 %d），拒绝生成页面以免发陈旧/残缺读数'
                 % (len(bars), POOL_N, POOL_N - len(bars)))
    for t in bars:
        features(bars[t])

    g = gate_v1(bars, pool)
    if len(g['dates']) < MA_REG + 1:
        sys.exit('FATAL 有效交易日不足 %d 个' % (MA_REG + 1))
    GM = {d: (bool(g['gate'][i]), int(g['run'][i])) for i, d in enumerate(g['dates'])}

    last = len(g['dates']) - 1
    asof = g['dates'][last]
    idx = float(g['idx'][last])
    ma = float(g['ma'][last])
    # 参与数/门槛取判定日（有效日）上的实际值
    acc = g['acc']
    cnt_asof = len(acc[asof])
    all_dates = sorted(acc)
    pos_d = all_dates.index(asof)
    med_asof = float(np.median([len(acc[d]) for d in all_dates[max(0, pos_d - HALFWIN): pos_d + HALFWIN + 1]]))

    segs = segments(g['dates'], g['gate'])
    cur_seg = segs[-1]
    seg_len_eff = sum(1 for d in g['dates'] if cur_seg[0] <= d <= cur_seg[1])
    off_days = (datetime.date.fromisoformat(asof) - datetime.date.fromisoformat(cur_seg[1])).days
    seg_off = (datetime.date.fromisoformat(cur_seg[1]) + datetime.timedelta(days=1)).isoformat()
    seg_meta = ('连续开闸 %d 个有效日；%s 起闸关，至 %s 已 %d 日'
                % (seg_len_eff, seg_off, asof, off_days) if not g['gate'][last]
                else '连续开闸 %d 个有效日（当前在段内）' % seg_len_eff)

    ev, raw_hits = candidates(bars, pool, GM)
    sig = build_sig(bars, ev)
    exec_sig = [s for s in sig if weekday(s['entry_day']) < 5]

    # ---- 当前批次
    batch_day = max(s['day'] for s in sig) if sig else None
    batch_seg = seg_of(segs, batch_day) if batch_day else None
    b_rows, wk_n, stop_n, exp_n, live_n = [], 0, 0, 0, 0
    if batch_day:
        for s in [x for x in sig if x['day'] == batch_day]:
            stop_lv = s['E'] - M_ATR * s['atr']
            r = sim(s, CURVE_C['L'], stop_lv)
            weekend_entry = weekday(s['entry_day']) >= 5
            # 未到期＝第 10 根K 尚未落定（bar 序号口径，非自然日 +10）
            expired = s['due_nominal_day'] is not None and s['due_nominal_day'] <= asof
            if weekend_entry:
                wk_n += 1
            elif r['exit_type'] == 'stop':
                stop_n += 1
            elif expired:
                exp_n += 1
            else:
                live_n += 1
                b_rows.append(dict(tkr=s['tkr'], buy_date=s['entry_day'],
                                   due_date=s['due_nominal_day'] or '待定',
                                   entry=round(s['E'], 4), stop=round(stop_lv, 4)))
        b_rows.sort(key=lambda x: x['tkr'])
    dedup_n = len([x for x in sig if x['day'] == batch_day]) if batch_day else 0
    raw_n = len([e for e in ev if e['day'] == batch_day]) if batch_day else 0
    if batch_day:
        parts = ['本批（牛闸 %s 开闸）信号日 %s 当日命中 %d 只，同标的 10 根K 内不重复开仓去重后 %d 只'
                 % (batch_seg[0] if batch_seg else '-', batch_day, raw_n, dedup_n)]
        if wk_n:
            parts.append('入场落在周六/日的 %d 只按执行口径不开仓' % wk_n)
        if stop_n:
            parts.append('止损离场 %d 只' % stop_n)
        if exp_n:
            parts.append('持满 10 根K 到期 %d 只' % exp_n)
        if live_n:
            parts.append('仍在持 %d 只' % live_n)
        last_exit = max(sim(x, CURVE_C['L'], x['E'] - M_ATR * x['atr'])['exit_day']
                        for x in sig if x['day'] == batch_day)
        empty_text = '，'.join(parts) + '；最后离场 %s。已到期/已止损的标的不再列出；下一批待牛闸重新开闸后生成。' % last_exit
    else:
        empty_text = '缓存区间内无命中，下一批待牛闸开闸后生成。'

    # ---- 净值曲线（执行版：剔周末入场）
    curves, n_sig = {}, len(exec_sig)
    for key, cfg in (('C', CURVE_C), ('B', CURVE_B)):
        taken, skipped, eq = queue_run(exec_sig, cfg['L'])
        ds, e = daily_curve(taken, cfg['L'])
        st = curve_stats(taken, eq, ds, e)
        st.update(L=cfg['L'], eq=[round(float(v), 4) for v in e])
        curves[key] = st

    weekend_block = now.weekday() >= 5     # 北京时间周六/周日不开新仓
    pull_time = datetime.datetime.fromtimestamp(newest).strftime('%Y-%m-%d %H:%M')

    ctx = dict(
        generated_at=now.strftime('%Y-%m-%d %H:%M:%S %z'),
        pull_time=pull_time, source=cache, weekend_block=weekend_block,
        gate=dict(asof=asof,
                  asof_wd='周' + '一二三四五六日'[datetime.date.fromisoformat(asof).weekday()],
                  idx=idx, ma=ma, gap=(ma - idx) / idx * 100, gap_alt=(idx / ma - 1) * 100,
                  gate=bool(g['gate'][last]), cnt=cnt_asof, thr=0.9 * med_asof,
                  seg=cur_seg, seg_meta=seg_meta),
        batch=dict(open_date=batch_seg[0] if batch_seg else '-', signal_day=batch_day,
                   rows=[] if weekend_block else b_rows, live_n=live_n,
                   raw_n=raw_n, dedup_n=dedup_n, empty_text=empty_text),
        curves=curves, n_sig=n_sig)

    html = render(ctx)
    os.makedirs(os.path.join(outdir, 'out'), exist_ok=True)   # 校验通过后才落盘
    open(os.path.join(outdir, 'index.html'), 'w').write(html)

    live = dict(
        asof=asof, idx=round(idx, 3), ma50=round(ma, 3),
        gap=round((ma - idx) / idx * 100, 3), gap_alt=round((idx / ma - 1) * 100, 3),
        gate=bool(g['gate'][last]),
        participants=cnt_asof, participants_pool=POOL_N, threshold=round(0.9 * med_asof, 1),
        batch_open_date=batch_seg[0] if batch_seg else None,
        batch_signal_day=batch_day,
        candidates=[] if weekend_block else b_rows,
        weekend_block=weekend_block,
        generated_at=now.strftime('%Y-%m-%dT%H:%M:%S%z'),
        generated_at_bj=now.strftime('%Y-%m-%d %H:%M'),
        source=cache, pull_time=pull_time,
        gate_segment=list(cur_seg), gate_segment_days=seg_len_eff,
        n_signal=len(sig), n_signal_exec=n_sig,
        curve={k: dict(L=v['L'], final=v['final'], mdd=v['mdd'], n=v['n'],
                       win=v['win'], mean=v['mean'], span=v['span']) for k, v in curves.items()},
    )
    json.dump(live, open(os.path.join(outdir, 'out', 'live.json'), 'w'), ensure_ascii=False, indent=1)

    print('OK  asof=%s idx=%.3f ma50=%.3f gap=%.3f%% gate=%s cnt=%d/%d weekend_block=%s'
          % (asof, idx, ma, (ma - idx) / idx * 100, 'open' if g['gate'][last] else 'closed',
             cnt_asof, POOL_N, weekend_block))
    print('    批次 %s（牛闸 %s 开闸）在持 %d 只｜执行版信号 %d｜C 期末 %.4f 回撤 %.2f%%｜B 期末 %.4f 回撤 %.2f%%'
          % (batch_day, batch_seg[0] if batch_seg else '-', live_n, n_sig,
             curves['C']['final'], curves['C']['mdd'], curves['B']['final'], curves['B']['mdd']))
    print('    → %s/index.html  %s/out/live.json' % (outdir, outdir))


if __name__ == '__main__':
    main()
