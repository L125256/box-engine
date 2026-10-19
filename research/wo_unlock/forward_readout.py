#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三合一前瞻判读管线（F6 生死 + S3×D1 前瞻复评 + B1 部署评审 并窗）· 常设件
================================================================
【规格出处（冻结，禁改判据）】
- /tmp/trade9_specs/USERWORD_VERDICT.md §〇-Q1：F6 前瞻判活机制=「每天判定轮自动积累
  数据、到门槛自动判读一次并封印」；本件即该机制的自动化实现（置顶在建件）；
- /tmp/trade9_specs/G1G2FDR_VERDICT.md 交易员 §六-2（F6 生死判据逐字冻结）：
  ①前瞻/留出段 realC 型子段逐日 IC ≥0 且 t≥2；②前瞻费后 fwd20 价差>0（≥5 个显著日）；
  ③任一判据翻转即判死并颁发 F6 死亡证明；样本内数字封印；
- /tmp/trade9_specs/CROSSF6_VERDICT.md：S3×D1 前瞻复评=同判线 PCX-A9（不放宽不加档）；
  B1 解锁条件=F6 前瞻判活 + 新预注册部署评审 + 前瞻段新数字（数字封印 PCX-B6）；
  S3×D1 与 F6 前瞻判读并窗（保守席合流④）；
- R8=Pool(32)；seed=42；144 池定版；D0 对拍先过（F6 尺零漂移回拍强制）。

【判读协议（FR-1..FR-9，先冻结后运行；冻结时点 2026-10-19，前瞻窗开启前/数据尾日
2026-10-17 之后，无前瞻数据存在——冻结合法，防烧窗）】
FR-1 前瞻窗=2026-10-18 起（FULL 窗尾日 2026-10-17 之后的所有已落定判定轮）。
FR-2 每日积累（判定轮数据落盘后自动执行）：前瞻周信号日（144 池日历每周首个交易日）
  成熟后（fwd20 满 20 交易日）登记 F6|lo 态日记录——RS20 截面 Spearman IC + 费后
  fwd20 十分位价差（c4 谱系：top10−bottom10 均值 −0.10pp）；lo/hi 态=同一把尺
  （池内 20 日滚动平均两两相关、realA p50 阈值，wo_crossf6.f6_state 逐字同构）。
FR-3 F6 尺零漂移回拍：fwd 尺与 XF.f6_state 在 FULL 窗重叠日逐位一致（强制断言）。
FR-4 判读门槛：成熟 lo 态信号日 n≥20（对齐 realC 20 IC 日惯例）→ 三合一判读一次并封印。
FR-5 早判死条款（③翻转的前瞻实现）：n≥10 且 IC t≤−2 且 IC 均值<0 → 立即判读（判死）并封印。
FR-6 数据不足→不判读只累计：n<min(20, FR-5 触发) 时仅落盘状态，禁止任何结论输出。
FR-7 封印：判读一次后 readout_state.json sealed=true（含判定全文+时间戳），此后每次
  调用直接退出（禁重复判读）；状态落盘=唯一事实源。
FR-8 S3×D1 前瞻复评（同判线 PCX-A9 承继，前瞻段适用项）：前瞻段 avoid>0 ∧
  mdd_red≥10% ∧ lag=1 不翻转；FDR(BH q=0.10) 于前瞻段 m=2 池族内施行（如实记账；
  前瞻段 <30 交易日时 p 不计算、登记样本不足）。费压=PB-5/PCX-A5 承继（×1.5）。
FR-9 B1 部署评审：触发条件=F6 判活 ∧ B1 前瞻段 avoid>0 ∧ |MDD| 不劣化 → 报警输出
  「B1 部署评审待办（须新预注册，前瞻段新数字）」；B1 本身不部署、不改空仓姿态。

【云端沙箱化（2026-10-19 缺陷修复；判据零改动，FR-1..FR-9 逐字承继）】
- 缺陷根因：旧版硬编码本沙箱绝对路径（/workspace/repo_ready/research/wo_*、
  /tmp/box_cache）→ 云端任务沙箱无这些路径，每轮 0 行；且状态文件在
  research/wo_unlock/forward/ 不随判定轮回传。
- 修复：①所有路径相对仓库根（由 __file__ 上溯两级，env FORWARD_REPO_ROOT 可覆盖，
  禁绝对路径）；②数据源=仓库内引擎快照 engine_snapshot/box_cache_snapshot.tar.gz，
  首跑自动解包至 <repo>/.cache/box_cache（env FORWARD_BOX_CACHE 可覆盖，本地真实
  路径模式经此 env 指向实盘缓存即回归现状）；③状态文件迁移至 f1/ 目录
  （forward_state.json + forward_ic_days.jsonl 随判定轮回传持久化，云端每轮
  拉取→累计→回传，跨轮持久；旧 forward/ 目录现存文件自动迁移）；④输入接线=
  仓库内判定轮产物 f1/f1_live.json（每轮判定轮回传的就是它，本件只读其
  signal.asof 作轮次血缘登记，不参与任何判据计算）。

挂接：云端任务判定轮命令之后追加调用本件 --auto（只读+旁路落盘，不改引擎语义，
异常不阻断判定轮）；engine_f1/f1_signal.py 的本沙箱内挂接路径不变。
用法：python3 research/wo_unlock/forward_readout.py [--auto]
产出：f1/forward_state.json + f1/forward_ic_days.jsonl（+判读时 f1/forward_readout_*.json）
"""
import json
import os
import sys
import tarfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))                       # research/wo_unlock
ROOT = os.environ.get('FORWARD_REPO_ROOT') or \
    os.path.dirname(os.path.dirname(_HERE))                              # 仓库根（__file__ 相对，禁绝对路径）
for _d in ('research/wo_dneg', 'research/wo_rescue',
           'research/wo_g1g2fdr', 'research/wo_crossf6'):
    _p = os.path.join(ROOT, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

FW0 = '2026-10-18'          # FR-1 前瞻窗起点
MIN_READOUT_DAYS = 20       # FR-4
EARLY_DEATH_DAYS = 10       # FR-5
FWD_H = 20                  # 判据② fwd20（逐字）
MIN_NAMES = 30
FEE_RT_PP = 0.10            # c4 费后价差谱系（双边 0.10pp）
STATEDIR = os.path.join(ROOT, 'f1')            # 状态随判定轮回传（云端持久目录）
STATE_F = os.path.join(STATEDIR, 'forward_state.json')
IC_F = os.path.join(STATEDIR, 'forward_ic_days.jsonl')
ROUND_F = os.path.join(ROOT, 'f1', 'f1_live.json')   # 判定轮产物（每轮回传）
LEGACY_STATEDIR = os.path.join(_HERE, 'forward')     # 旧状态目录（迁移源）
SNAPSHOT_TAR = os.path.join(ROOT, 'engine_snapshot', 'box_cache_snapshot.tar.gz')

# 延迟重导入（首次调用 ~10s，常驻判定轮可接受）
_WR_LOADED = False


def _cache_dir():
    """引擎快照缓存目录：env 覆盖 > 仓库内 .cache（首跑从快照包解包，幂等）。"""
    env = os.environ.get('FORWARD_BOX_CACHE')
    if env:
        return env
    d = os.path.join(ROOT, '.cache', 'box_cache')
    if not os.path.isdir(d) or not os.listdir(d):
        os.makedirs(d, exist_ok=True)
        with tarfile.open(SNAPSHOT_TAR, 'r:gz') as tf:
            tf.extractall(os.path.dirname(d))          # 包内顶层即 box_cache/
    return d


def _migrate_state():
    """旧状态目录 → f1/ 一次性迁移（copy 式，仅当新处缺失；旧文件保留不删）。"""
    os.makedirs(STATEDIR, exist_ok=True)
    for fn in ('forward_state.json', 'forward_ic_days.jsonl'):
        src = os.path.join(LEGACY_STATEDIR, fn)
        dst = os.path.join(STATEDIR, fn)
        if os.path.exists(src) and not os.path.exists(dst):
            with open(src) as f:
                content = f.read()
            with open(dst, 'w') as f:
                f.write(content)
            print(f'forward_readout: 状态迁移 {src[len(ROOT):]} → f1/{fn}')


def _round_asof():
    """判定轮产物血缘（只读，不参与判据）：f1/f1_live.json 的 signal.asof。"""
    try:
        with open(ROUND_F) as f:
            d = json.load(f)
        return d.get('signal', {}).get('asof') or d.get('meta', {}).get('asof')
    except Exception:
        return None


def _eng():
    global _WR_LOADED
    import wo_rescue_run as WR
    if not _WR_LOADED:
        WR.CACHE = _cache_dir()          # 数据源=仓库内快照/env 覆盖（云端化接线点）
        WR._init()
        _WR_LOADED = True
    return WR


# ------------------------------------------------------------- F6 尺（FR-2/FR-3）
_F6F = None


def f6_state_fwd():
    """XF.f6_state 同构，avg_corr 延拓至前瞻窗（同一把尺：公式逐字+realA p50 同源）。"""
    global _F6F
    if _F6F is not None:
        return _F6F
    import numpy as np
    import pandas as pd
    import wo_crossf6_run as XF
    WR = _eng()
    XF.f6_state()                      # 确保官方尺已算（并供零漂移回拍）
    names = WR._POOLS['full144']
    C = pd.DataFrame({s: WR._DATA[s]['close'] for s in names}).sort_index()
    R = C.pct_change()
    pos = {d: i for i, d in enumerate(C.index)}
    fwd0 = pd.Timestamp(FW0)
    avg_corr = pd.Series(np.nan, index=C.index)
    arr = R.values
    for d in C.index:
        if d < pd.Timestamp(WR.FULL[0]):
            continue
        i = pos[d]
        if i < 19:
            continue
        w = arr[i - 19:i + 1]
        ok = np.isfinite(w).all(axis=0)
        if ok.sum() < 30:
            continue
        cm = np.corrcoef(w[:, ok], rowvar=False)
        k = cm.shape[0]
        avg_corr[d] = float((cm.sum() - k) / (k * (k - 1)))
    ra = C.index[(C.index >= WR.REALA[0]) & (C.index <= WR.REALA[1])]
    p50c = float(avg_corr[ra].quantile(0.5))
    # FR-3 零漂移回拍：FULL 窗重叠日 vs 官方尺逐位一致
    off = XF._F6['avg_corr'].dropna()
    mine = avg_corr.reindex(off.index).dropna()
    common = off.index.intersection(mine.index)
    drift = float((off[common] - mine[common]).abs().max())
    assert drift == 0.0, f'F6 尺零漂移回拍 FAIL：maxdiff={drift}'
    assert abs(p50c - XF._F6['p50']) <= 1e-12, 'F6 p50 阈值漂移'
    lab = pd.Series(np.where(avg_corr > p50c, 'hi', 'lo'), index=C.index)
    _F6F = {'C': C, 'avg_corr': avg_corr, 'p50': p50c,
            'lo': (lab == 'lo'), 'hi': (lab == 'hi'), 'names': names}
    return _F6F


# ------------------------------------------------------------- 每日积累（FR-2）
def collect():
    WR = _eng()
    import numpy as np
    import pandas as pd
    st = f6_state_fwd()
    C, lo = st['C'], st['lo']
    names = st['names']
    old131 = set(WR._POOLS['old131'])
    new13 = sorted(set(names) - old131)
    ret20 = C / C.shift(20) - 1
    idx_old20 = ret20[list(old131 & set(names))].mean(axis=1)
    idx_new20 = ret20[new13].mean(axis=1) if new13 else None
    rs = ret20.copy()
    for s in names:
        other = idx_new20 if s in old131 else idx_old20
        rs[s] = ret20[s] - other.reindex(ret20.index)
    fwd = C.shift(-FWD_H) / C - 1
    cal = C.index
    iso = cal.isocalendar()
    sig_all = pd.DatetimeIndex(cal.to_series().groupby(
        [iso['year'].values, iso['week'].values]).first().sort_values().values)
    fw0 = pd.Timestamp(FW0)
    last = cal[-1]
    done = set()
    if os.path.exists(IC_F):
        with open(IC_F) as f:
            for line in f:
                try:
                    done.add(json.loads(line)['date'])
                except Exception:
                    continue
    new_rows = []
    for t in sig_all:
        if t < fw0 or str(t.date()) in done:
            continue
        i = cal.get_loc(t)
        if i + FWD_H >= len(cal):        # fwd20 未成熟（FR-2：成熟后才登记）
            continue
        if not bool(lo.at[t]):           # 只积累 F6|lo 态日（A 臂域限定 PCX-B1 逐字）
            continue
        y = fwd.loc[t]
        x = rs.loc[t]
        m = x.notna() & y.notna()
        if m.sum() < MIN_NAMES:
            continue
        ic = float(np.corrcoef(x[m].rank(), y[m].rank())[0, 1])
        lab = pd.qcut(x[m].rank(method='first'), 10, labels=False)
        spread_pp = float((y[m][lab == 9].mean() - y[m][lab == 0].mean()) * 100
                          - FEE_RT_PP)
        new_rows.append({'date': str(t.date()), 'state': 'lo', 'ic': round(ic, 6),
                         'spread_pp_net': round(spread_pp, 4),
                         'n_names': int(m.sum()),
                         'matured_at': str(last.date()),
                         'sig_day_offset': int(i)})
    if new_rows:
        with open(IC_F, 'a') as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    return new_rows


def load_ic_days():
    if not os.path.exists(IC_F):
        return []
    out = []
    with open(IC_F) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


# ------------------------------------------------------------- 判读（FR-4/5/7/8/9）
def _seg(curve_d, t0, t1):
    import pandas as pd
    s = pd.Series({pd.Timestamp(k): v for k, v in curve_d.items()}).sort_index()
    seg = s[(s.index >= pd.Timestamp(t0)) & (s.index <= pd.Timestamp(t1))]
    if len(seg) < 2:
        return None
    ret = float(seg.iloc[-1] / seg.iloc[0] - 1) * 100
    mdd = float((seg / seg.cummax() - 1).min()) * 100
    return {'ret_pp': ret, 'mdd_pct': mdd, 'n_days': int(len(seg))}


def _readout_cells():
    """FR-8/FR-9：前瞻段 S3×D1 与 B1 臂（引擎/门信号/费压全部承继冻结谱系）。"""
    import wo_crossf6_run as XF
    import wo_g1g2fdr_run as WG
    WR = _eng()
    t1 = max(max(WR._DATA[s].index) for s in WR._DATA)
    res = {}
    for pname in WR._POOLS:
        syms = WR._POOLS[pname]
        runs = {}
        runs['base'] = XF.run_gate_x(syms, gate_map=None, off_mode='v2_full_stop',
                                     off_mode_map=None, fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
        gmap0 = WG.gate_maps(pname, 0)['g2_ma'].to_dict()
        runs['s3xd1'] = WG.run_gate_g(syms, gate_map=gmap0, off_mode='open_half_nosell',
                                      fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
        gmap1 = WG.gate_maps(pname, 1)['g2_ma'].to_dict()
        runs['s3xd1_lag1'] = WG.run_gate_g(syms, gate_map=gmap1, off_mode='open_half_nosell',
                                           fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
        gmap_v2 = WG.gate_maps(pname, 0)['v2'].to_dict()
        runs['B1'] = XF.run_gate_x(syms, gate_map=gmap_v2, off_mode='v2_full_stop',
                                   off_mode_map=XF.b_off_mode_map('B1_lo_open_half'),
                                   fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
        row = {}
        for k, g in runs.items():
            cd = {str(d.date()): float(v) for d, v in g['curve'].items()}
            row[k] = {'seg': _seg(cd, FW0, str(t1.date())), 'curve': cd,
                      'n_gate_off': g['n_gate_off']}
        res[pname] = row
    return res, str(t1.date())


def _boot_p(diff):
    import wo_rescue_run as WR
    import numpy as np
    x = np.asarray(diff, dtype=float)
    if len(x) < 30:
        return None                      # FR-8：前瞻段 <30 交易日不计算 p
    return WR.boot_p_one_sided(x)


def do_readout(state):
    WR = _eng()
    import numpy as np
    import pandas as pd
    days = load_ic_days()
    ics = pd.Series([d['ic'] for d in days], dtype=float)
    sps = pd.Series([d['spread_pp_net'] for d in days], dtype=float)
    n = len(days)
    ic_mean = float(ics.mean()) if n else None
    ic_t = float(ics.mean() / ics.std(ddof=1) * np.sqrt(n)) if n >= 3 and ics.std(ddof=1) > 0 else None
    sig_days = int((sps > 0).sum()) if n else 0
    spread_mean = float(sps.mean()) if n else None

    # ---- F6 生死（G1G2FDR 交易员 §六-2 三条逐字）
    c1 = bool(ic_mean is not None and ic_mean >= 0 and ic_t is not None and ic_t >= 2)
    c2 = bool(spread_mean is not None and spread_mean > 0 and sig_days >= 5)
    f6_verdict = 'ALIVE' if (c1 and c2) else 'DEAD'
    f6 = {'n_lo_days': n, 'ic_mean': ic_mean, 'ic_t': ic_t,
          'spread_mean_pp_net': spread_mean, 'spread_sig_days': sig_days,
          'clause1_ic_ge0_t_ge2': c1, 'clause2_spread_gt0_sig5': c2,
          'clause3_flip': not (c1 and c2),
          'verdict': f6_verdict,
          'judgment_basis': 'G1G2FDR_VERDICT 交易员 §六-2 逐字（FR 冻结）'}

    # ---- S3×D1 前瞻复评（PCX-A9 同判线承继）+ B1（FR-8/9）
    cells, last_day = _readout_cells()
    s3xd1, b1, ps = {}, {}, []
    for pname, row in cells.items():
        a, b = row['s3xd1']['seg'], row['base']['seg']
        lag = row['s3xd1_lag1']['seg']
        avoid = round(a['ret_pp'] - b['ret_pp'], 4) if a and b else None
        mdd_red = (round((abs(b['mdd_pct']) - abs(a['mdd_pct']))
                         / abs(b['mdd_pct']) * 100, 2)
                   if a and b and b['mdd_pct'] != 0 else None)
        lag_avoid = round(lag['ret_pp'] - b['ret_pp'], 4) if lag and b else None
        g_pd = (pd.Series({pd.Timestamp(k): v
                           for k, v in row['s3xd1']['curve'].items()}).sort_index()
                .pct_change()
                - pd.Series({pd.Timestamp(k): v
                             for k, v in row['base']['curve'].items()}).sort_index()
                .pct_change())
        g_pd = g_pd.dropna()
        g_pd = g_pd[(g_pd.index >= pd.Timestamp(FW0))]
        p = _boot_p(g_pd.values)
        if p is not None:
            ps.append(p)
        s3xd1[pname] = {'seg': a, 'base_seg': b, 'avoid_pp': avoid, 'mdd_red_pct': mdd_red,
                        'lag1_avoid_pp': lag_avoid, 'p_fwd': p,
                        'n_gate_off': row['s3xd1']['n_gate_off'],
                        'pass_avoid': bool(avoid is not None and avoid > 0),
                        'pass_mdd_red10': bool(mdd_red is not None and mdd_red >= 10),
                        'pass_lag': bool(lag_avoid is not None and lag_avoid > 0)}
        ba = row['B1']['seg']
        b1[pname] = {'seg': ba,
                     'avoid_pp': round(ba['ret_pp'] - b['ret_pp'], 4) if ba and b else None,
                     'mdd_not_worse': bool(ba and b and abs(ba['mdd_pct'])
                                           <= abs(b['mdd_pct']) + 1e-9),
                     'n_gate_off': row['B1']['n_gate_off']}
    if len(ps) >= 2:
        rej = WR.bh_fdr(ps, q=0.10)
        for (pname, row), rj in zip([(p, s3xd1[p]) for p in s3xd1], rej):
            row['fdr_reject_fwd'] = bool(rj)
    else:
        for row in s3xd1.values():
            row['fdr_reject_fwd'] = None
    sel = [p for p, r in s3xd1.items()
           if r['pass_avoid'] and r['pass_mdd_red10'] and r['pass_lag']
           and r['fdr_reject_fwd']]
    s3xd1_verdict = (f"前瞻复评通过池={sel if sel else '无'}（同判线 PCX-A9：avoid>0 ∧ "
                     f"mdd_red≥10 ∧ lag 不翻转 ∧ FDR 幸存）")

    alarms = []
    if f6_verdict == 'DEAD':
        alarms.append('F6 前瞻判死——颁发 F6 死亡证明 + 因子域死亡证明（判据③任一翻转）')
    else:
        alarms.append('F6 前瞻判活——样本内 B1 解锁条件之一达成，进入部署评审待办')
        if any(v['avoid_pp'] is not None and v['avoid_pp'] > 0 and v['mdd_not_worse']
               for v in b1.values()):
            alarms.append('B1 部署评审待办：F6 判活 ∧ B1 前瞻段 avoid>0 ∧ MDD 不劣化'
                          '——须新预注册部署评审，用前瞻段新数字（PCX-B6 数字封印）')
    if sel:
        alarms.append(f'S3×D1 前瞻复评过线池：{sel}（同判线，不放宽不加档）')

    verdict = {'readout_at': time.strftime('%F %T'),
               'forward_window': [FW0, last_day],
               'f6': f6, 's3xd1_forward': s3xd1, 'b1_forward': b1,
               's3xd1_verdict': s3xd1_verdict,
               'b1_rule': 'FR-9：触发≠部署——部署走新预注册评审（三重闸门承继）',
               'alarms': alarms,
               'seal': {'sealed': True, 'rule': 'FR-7：判读一次并封印，禁重复判读',
                        'n_lo_days_used': n}}
    state.update({'state': 'SEALED', 'sealed_at': verdict['readout_at'],
                  'last_readout': verdict})
    with open(os.path.join(STATEDIR, f"forward_readout_{verdict['readout_at'][:10]}.json"),
              'w') as f:
        json.dump(verdict, f, ensure_ascii=False, indent=1)
    for a in alarms:
        print(f'[ALARM] {a}')
    return verdict


def run(auto=False):
    _migrate_state()
    os.makedirs(STATEDIR, exist_ok=True)
    if os.path.exists(STATE_F):
        state = json.load(open(STATE_F))
    else:
        state = {'state': 'ACCUMULATING', 'created_at': time.strftime('%F %T'),
                 'protocol': 'FR-1..FR-9（forward_readout.py 头注，2026-10-19 前瞻数据到达前冻结）'}
    if state.get('state') == 'SEALED':
        print(f"forward_readout: 已封印（{state.get('sealed_at')}），禁重复判读（FR-7）——退出")
        return state
    WR = _eng()
    new = collect()
    days = load_ic_days()
    import numpy as np
    n = len(days)
    ic_mean = (sum(d['ic'] for d in days) / n) if n else None
    ic_t = None
    if n >= 3:
        arr = np.array([d['ic'] for d in days], dtype=float)
        sd = arr.std(ddof=1)
        ic_t = float(arr.mean() / sd * np.sqrt(n)) if sd > 0 else None
    state['accumulation'] = {'updated_at': time.strftime('%F %T'),
                             'n_lo_days_matured': n, 'target': MIN_READOUT_DAYS,
                             'new_rows_this_run': len(new),
                             'ic_mean': ic_mean, 'ic_t': ic_t,
                             'round_asof': _round_asof(),
                             'note': 'FR-6：数据不足→不判读只累计'}
    verdict = None
    # FR-5 早判死
    if n >= EARLY_DEATH_DAYS and ic_mean is not None and ic_mean < 0 \
            and ic_t is not None and ic_t <= -2:
        state['state'] = 'READOUT_EARLY_DEATH'
        verdict = do_readout(state)
    # FR-4 门槛判读
    elif n >= MIN_READOUT_DAYS:
        state['state'] = 'READOUT'
        verdict = do_readout(state)
    with open(STATE_F, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    if verdict is None:
        print(f"forward_readout: ACCUMULATING {n}/{MIN_READOUT_DAYS} lo 态成熟信号日"
              f"（本轮新增 {len(new)}）——数据不足，不判读只累计（FR-6）")
    else:
        print(f"forward_readout: 判读完成并封印（{state['state']}）——"
              f"F6={verdict['f6']['verdict']}")
    return state


if __name__ == '__main__':
    run(auto='--auto' in sys.argv)
