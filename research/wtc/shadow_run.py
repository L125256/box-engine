#!/usr/bin/env python3
# shadow_run.py — WT-C 影子双轨每日运行主程序
# 流程：读 /tmp/box_cache（先由 refresh_cache.py 32线程刷新）→ 三轨各跑权威口径全窗回放
#       （引擎逻辑单源复用 /tmp/eng_wt_rc/eng_final.py，仅按工单参数化，32 进程并行 scan）
# 输出：三轨最新指标（全窗/主窗/滚动30日/分年，含厚利桶 r>=8 sum）→ 月度熔断判定（仅信号，
#       不做真实交易动作）→ 主轨降仓标记(≤50%) 常驻输出 → ledger JSONL 落盘 → status_shadow.txt
# 纪律：不修改 eng_final.py / /tmp/eng_wt/ / box_module.py 任何文件。
import sys, os, json, datetime
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, '/tmp/eng_wt_rc')
import eng_final as ENG  # 权威引擎单源：scan/atrs/stats/yearly/load_pool/build_idx_bull

WTC = '/tmp/wtc'
CACHE = '/tmp/box_cache'
LEDGER = os.path.join(WTC, 'ledger', 'daily.jsonl')
STATUS = os.path.join(WTC, 'status_shadow.txt')
REFRESH_REPORT = os.path.join(WTC, 'refresh_report.json')
MAIN = '2025-06-01'
WORKERS = 32

# 三轨参数（冻结，一季度禁调参）；b=0.25/x=0.75/Q=30 用 eng_final 冻结常量（与 box_module 一致）
TRACKS = {
    'top1':     dict(label='主轨 Top1  N15/k7.5/m2/e0.3',  params=dict(N=15, k=7.5, m=2, e=0.3)),
    'planb':    dict(label='观察轨 方案B N20/k6.0/m1/e0.3', params=dict(N=20, k=6.0, m=1, e=0.3)),
    'baseline': dict(label='对照轨 基线 N20/k6.0/m2/e0.2', params=dict(N=20, k=6.0, m=2, e=0.2)),
}
BREAKER_SUM_R = -100.0   # 当月 sum_r < -100R → 熔断
BREAKER_MEDIAN = -1.0    # 当月 median < -1.0% → 熔断

# ---- 并行 worker（fork 继承池与牛闸，仅传 tkr 字符串，免序列化大对象）----
_POOL = _BULL = None


def _init(params):
    global _N, _K, _M, _E
    _N, _K, _M, _E = params['N'], params['k'], params['m'], params['e']
    ENG.N, ENG.K, ENG.M, ENG.E = _N, _K, _M, _E


def _scan_tkr(tkr):
    res = ENG.scan(_POOL[tkr], _BULL)
    return tkr, res['trades'], res['stat']


def collect_parallel(params, pool, bull):
    """与 eng_final.collect 同口径的 32 进程并行版：单票状态机调用 eng_final.scan（单源），汇合后同键排序。"""
    global _POOL, _BULL
    _POOL, _BULL = pool, bull
    trades, agg = [], dict(defer=0, gap_stop=0, gap_tp=0, hardcap=0)
    with ProcessPoolExecutor(WORKERS, initializer=_init, initargs=(params,)) as ex:
        for tkr, trs, st in ex.map(_scan_tkr, sorted(pool), chunksize=2):
            bars = pool[tkr]
            for t in trs:
                trades.append(dict(tkr=tkr, **t, et=bars[t['ei']]['time'], xt=bars[t['xi']]['time']))
            for k in agg:
                agg[k] += st[k]
    return sorted(trades, key=lambda t: (t['xi'], t['tkr'])), agg


def window_stats(trades, lo=None, hi=None):
    sel = [t for t in trades
           if (lo is None or t['et'] >= lo) and (hi is None or t['et'] < hi)]
    return ENG.stats(sel), sel


def rolling30(trades, today):
    lo = (datetime.date.fromisoformat(today) - datetime.timedelta(days=30)).isoformat()
    s, _ = window_stats(trades, lo=lo)
    return s


def main():
    today = datetime.date.today().isoformat()
    month = today[:7]
    pool, dropped = ENG.load_pool(CACHE)
    bull = ENG.build_idx_bull(pool)
    print(f'[{today}] 池: {len(pool)} 标的 (被清洗 {len(dropped)})', flush=True)

    health = dict(ok=len(pool), fail=len(dropped), source='eng_final.load_pool')
    try:
        rep = json.load(open(REFRESH_REPORT))
        health = dict(ok=rep.get('ok'), fail=len(rep.get('fail') or []),
                      cache_files=rep.get('cache_files'), ts=rep.get('ts'))
    except Exception:
        pass

    out = dict(date=today, tracks={}, breaker=None, derisk='生效（主轨仓位≤50%，常驻）', health=health)
    for key, tdef in TRACKS.items():
        trs, agg = collect_parallel(tdef['params'], pool, bull)
        full, _ = window_stats(trs)
        main_s, main_trs = window_stats(trs, lo=MAIN)
        r30 = rolling30(trs, today)
        mon, _ = window_stats(trs, lo=month + '-01')
        yearly_full = ENG.yearly(trs)
        yearly_main = ENG.yearly(main_trs)
        out['tracks'][key] = dict(
            label=tdef['label'], params=tdef['params'],
            full=full, main=main_s, rolling30=r30, month=mon,
            yearly_full=yearly_full, yearly_main=yearly_main, exit_stat=agg,
            latest_exit=dict(xt=max((t['xt'] for t in trs), default=None),
                             n_after=len([t for t in trs if t['xt'] >= today]) if trs else 0))
        print(f"{key}: 全窗 n={full['n']} median={full['median']} sum={full['sum_r']} thick={full['thick']['n']}/{full['thick']['sum_r']} | "
              f"主窗 n={main_s['n']} median={main_s['median']} | 滚30 n={r30['n']} sum={r30['sum_r']} | "
              f"当月 n={mon['n']} sum={mon['sum_r']} median={mon['median']}", flush=True)

    # ---- 月度熔断判定：以主轨(top1)当月指标为准；仅输出信号，不做真实交易动作 ----
    m = out['tracks']['top1']['month']
    med = m['median'] if m['n'] else None
    hit_sum = m['n'] > 0 and m['sum_r'] < BREAKER_SUM_R
    hit_med = m['n'] > 0 and med is not None and med < BREAKER_MEDIAN
    out['breaker'] = dict(track='top1', month=month, month_n=m['n'],
                          month_sum_r=m['sum_r'], month_median=med,
                          rule=f'当月sum_r<{BREAKER_SUM_R} 或 当月median<{BREAKER_MEDIAN}%',
                          triggered=bool(hit_sum or hit_med),
                          reason=('sum_r' if hit_sum else '') + ('+median' if hit_med else '') or None,
                          action='停开新仓（信号标记，无真实交易动作）')

    # ---- ledger 落盘：一行一天，同日重跑覆盖 ----
    line = json.dumps(out, ensure_ascii=False)
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    lines = []
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            lines = [l for l in f.read().splitlines() if l.strip() and json.loads(l).get('date') != today]
    lines.append(line)
    with open(LEDGER, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    write_status(out, today)
    print(f"熔断: {out['breaker']['triggered']} | 降仓: {out['derisk']} | 健康度: {health.get('ok')} 标的", flush=True)


def fmt(s):
    if s['n'] == 0:
        return 'n=0'
    return f"n={s['n']} med={s['median']} sum={s['sum_r']} win={s['win_pct']}% pf={s['pf']} 厚利r>=8: {s['thick']['n']}/{s['thick']['sum_r']}"


def write_status(out, today):
    b = out['breaker']
    L = []
    L.append('=' * 100)
    L.append(f'WT-C 影子双轨状态页   生成: {today}   （仅信号输出，不做真实交易动作）')
    L.append(f'数据健康度: 成功 {out["health"].get("ok")} 标的  fail={out["health"].get("fail")}  cache_files={out["health"].get("cache_files")}')
    if b['triggered']:
        L.append(f'熔断状态: !! 熔断 触发（停开新仓标记）: 原因={b["reason"]}  当月主轨 n={b["month_n"]} sum={b["month_sum_r"]} med={b["month_median"]}')
    else:
        L.append(f'熔断状态: 未触发（规则: {b["rule"]}；当月主轨 n={b["month_n"]} sum={b["month_sum_r"]} med={b["month_median"]}）')
    L.append(f'主轨降仓标记: {out["derisk"]}')
    L.append('=' * 100)
    for key in ('top1', 'planb', 'baseline'):
        t = out['tracks'][key]
        L.append(f'◆ {t["label"]}')
        L.append(f'  全窗    {fmt(t["full"])}')
        L.append(f'  主窗    {fmt(t["main"])}  (入场日>={MAIN})')
        L.append(f'  滚动30日 {fmt(t["rolling30"])}')
        L.append(f'  当月    {fmt(t["month"])}')
        yf = t['yearly_full']
        L.append('  分年(全窗): ' + ' | '.join(
            f"{y}: n={yf[y]['n']} med={yf[y]['median']} sum={yf[y]['sum_r']}" for y in ('2024', '2025', '2026')))
        L.append('')
    L.append('-' * 100)
    L.append('近7日趋势（每日主轨主窗 n/median + 主轨滚动30日 sum_r）:')
    try:
        with open(LEDGER) as f:
            recent = [json.loads(l) for l in f.read().splitlines() if l.strip()][-7:]
        for r in recent:
            t1, r30 = r['tracks']['top1']['main'], r['tracks']['top1']['rolling30']
            bk = '熔断' if r['breaker']['triggered'] else '正常'
            L.append(f"  {r['date']}  主窗 n={t1['n']} med={t1['median']}  滚30sum={r30['sum_r']}  熔断={bk}")
    except Exception as e:
        L.append(f'  (趋势读取失败: {e})')
    with open(STATUS, 'w') as f:
        f.write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
