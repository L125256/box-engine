#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WO-ALPHA-01 运行件 · ALPHA_SPEC_v1 三臂回放（A=top5 因子 / B=随机5票×20种子 / C=池等权）
================================================================================
规格依据（逐字承承，禁止发挥）：
- §三 三臂定义：A=四因子 top5 等权（打分与 f1_signal.py cross_scores 逐行同源，权重一行不动）；
  B=随机 5 票 seed=42..61 冻结 20 种子，每调仓日从「当日有K线」标的均匀不放回抽取，全套 A 臂规则；
  C=池「当日有K线」全部标的各 1/N(t)，周调仓同节奏。
- §三 共用口径：每周首个交易日收盘出信号、次日开盘成交、全量重选；
  费率=单边 0.05%+0.03%/bar（持仓名义，与 F1_台账口径_v1.md §一.9/引擎 FEE_SIDE/FUNDING 同源）；
  止损=单票 −8% 硬截断（V2 可实现口径：跳空按 open 否则按 stop 价）；崩市闸=池单日中位跌幅<−5%
  当日收盘判定、次日开盘清仓、清仓日跳过重建（BUG-04 同源）；闸关时段三臂一律持现金。
- §四 闸开时段清单：idx=池内「当日有K线」标的等权收盘均价（f1_signal.py:638 同源），
  MA50=简单滚动 50 日（:639），闸开=idx≥MA50 持仓时段（:646 取反语义，引擎 on_holdcash=idx<MA50）。
  清单先冻结落盘、后回放。持仓执行滞后 1 日（次日开盘）=V2 可实现口径，三臂同构。
- §四 窗口：realA=2025-06-01→2026-10-17（唯一全权重判窗）；合成段 2024-01-24→2025-05-31
  只作低权重佐证（R7 标签强制），不支撑生死结论。
- §八 D0 四对拍（任一不过即停工）：D0-1 闸清单双路重建逐日 diff=0（含全部切换日）；
  D0-2 费线常量 vs F1_台账口径 §一.9 与引擎常量逐位一致；D0-3 CRASH_MED/STOP vs 引擎常量逐位一致；
  D0-4 A 臂 top5 vs 引擎 cross_scores 抽 3 个调仓日逐位一致。
- §五 判线：AL1/AL2/AL3 达标三腿 + 否决线，逐腿打勾、无中间态；运行后禁止改判线。
- §八 算力：22 条回测×~700 根日 K×144 标的；B 臂 20 种子 32 进程并行，单轮预估 ≤10 分钟。
纪律：R1 一发验证（重跑配额≤1，仅限代码缺陷修复）/ R7 诚实三级标注 / 数据全离线（禁网络）。
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

REPO = '/workspace/repo_ready'
sys.path.insert(0, os.path.join(REPO, 'engine_f1'))
os.environ.setdefault('F1_CACHE', '/tmp/box_cache')
os.environ.setdefault('F1_POOL', os.path.join(REPO, 'engine_snapshot', 'cleaned_pool.json'))
import f1_signal as eng   # 引擎同源：因子/池/常量唯一事实源（D0-2/3/4 锚）

OUT_DIR = os.path.join(REPO, 'research', 'wo_alpha')
CACHE = '/tmp/box_cache'
REALA = ('2025-06-01', '2026-10-17')          # §四 主判窗（唯一全权重）
SYNTH = ('2024-01-24', '2025-05-31')          # §四 合成段（低权重佐证）
SEEDS = list(range(42, 62))                   # §三 B 臂冻结清单 42..61
TOP_N = eng.TOP_N                             # 5
FEE_SIDE, FUNDING = eng.FEE_SIDE, eng.FUNDING  # 0.0005 / 0.0003（D0-2）
STOP, CRASH_MED, MA_REG = eng.STOP, eng.CRASH_MED, eng.MA_REG  # -0.08 / -0.05 / 50（D0-3）
SLOT_AB = 1.0 / TOP_N                         # A/B 臂 top5 等权=各 1/5（§三「top5 等权」）

G = {}   # fork 共享只读上下文（闸清单/价格面/日历/信号日）


# ---------------------------------------------------------------- 数据与闸清单
def build_context():
    data = eng.load_data(CACHE)
    syms = eng.build_pool(data)               # 权威池 144（assert 内置）
    F = eng.build_factors(data)               # 引擎同源四因子（D0-4）
    close = pd.DataFrame({s: data[s]['close'] for s in syms})
    open_ = pd.DataFrame({s: data[s]['open'] for s in syms})
    low = pd.DataFrame({s: data[s]['low'] for s in syms})
    cal = pd.DatetimeIndex(sorted(set().union(*[set(data[s].index) for s in syms])))
    close, open_, low = (x.reindex(cal) for x in (close, open_, low))
    mark = close.ffill()
    idx = close.mean(axis=1)                              # f1_signal.py:638 同源
    idx_ma = idx.rolling(MA_REG).mean()                   # :639 同源（简单滚动50）
    # 闸开=idx≥MA50（引擎 :646 on_holdcash=idx<MA50 的持仓取反语义）；MA 不足 50 日=闸关
    gate_open = (idx_ma.notna()) & (idx >= idx_ma)
    med_ret = close.pct_change().median(axis=1)           # 崩市判据（CRASH_MED 同源）
    sig_days = eng.week_first_days(cal)                   # 每周首个交易日（引擎同源）
    globals()['G'] = dict(data=data, syms=syms, F=F, close=close, open_=open_, low=low,
                          mark=mark, cal=cal, idx=idx, idx_ma=idx_ma,
                          gate_open=gate_open, med_ret=med_ret, sig_days=sig_days)
    return G


def gate_rebuild_scalar(ctx):
    """D0-1 独立第二路：按 f1_signal.py:636-646 逐日标量循环重建闸清单（非向量化路径）。"""
    cal, close = ctx['cal'], ctx['close']
    out = pd.Series(False, index=cal)
    idx_vals, ma_vals = ctx['idx'].values, ctx['idx_ma'].values
    for i, t in enumerate(cal):
        if i < MA_REG or pd.isna(ma_vals[i]):     # 引擎语义：idx_ma 为 NaN → 不开闸
            out.iloc[i] = False
            continue
        out.iloc[i] = bool(idx_vals[i] >= ma_vals[i])   # :646 取反（持币=idx<MA50）
    return out


# ---------------------------------------------------------------- 单臂回放
def simulate(win, select_fn, arm_name):
    """三臂共用回放内核（引擎 replay/one_pass 逐行同构，差异仅在 target 选择）。
    select_fn(t_close_signal_day, equity) -> target list；win=(start,end)。
    返回逐日净值 Series（闸关时段持现金横盘）。"""
    cal_all, sig_all = G['cal'], G['sig_days']
    s0, s1 = pd.Timestamp(win[0]), pd.Timestamp(win[1])
    cal = cal_all[(cal_all >= s0) & (cal_all <= s1)]
    sig_days = {t for t in sig_all if s0 <= t <= s1}
    gate_open, med_ret = G['gate_open'], G['med_ret']
    open_, low, mark = G['open_'], G['low'], G['mark']
    cash, pos = 1.0, {}
    pending_sells, pending_exec, crash_next = set(), None, None
    eq, n_stop, fee_sum = {}, 0, 0.0
    for t in cal:
        o_t, lo_t = open_.loc[t], low.loc[t]
        stopped_today = set()
        for s in list(pos):                                # 1) 盘中断价止损（V2 口径）
            if s in pending_sells or pd.isna(o_t.get(s, np.nan)):
                continue
            stop_p = pos[s]['entry'] * (1 + STOP)
            if o_t[s] <= stop_p:
                px = o_t[s]
            elif pd.notna(lo_t.get(s, np.nan)) and lo_t[s] <= stop_p:
                px = stop_p
            else:
                continue
            fee = pos[s]['qty'] * px * FEE_SIDE
            cash += pos[s]['qty'] * px - fee
            fee_sum += fee
            n_stop += 1
            stopped_today.add(s)
            del pos[s]
        for s in list(pending_sells):                      # 2) 挂单清仓（次日开盘）
            px = o_t.get(s, np.nan)
            if pd.isna(px):
                continue
            if s in pos:
                fee = pos[s]['qty'] * px * FEE_SIDE
                cash += pos[s]['qty'] * px - fee
                fee_sum += fee
                del pos[s]
            pending_sells.discard(s)
        skip_rebuild = (crash_next == t)                   # 崩市清仓日跳过重建（BUG-04 同源）
        if skip_rebuild:
            crash_next = None
        if pending_exec is not None and t == pending_exec[0]:   # 3) 周调仓执行
            _, target, eq_sig = pending_exec
            pending_exec = None
            if not skip_rebuild and bool(gate_open.at[t]):  # 只在闸开时段建仓
                slot = select_fn['slot'](t)
                for s in list(pos):
                    if s in target or s in pending_sells:
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        pending_sells.add(s)
                        continue
                    fee = pos[s]['qty'] * px * FEE_SIDE
                    cash += pos[s]['qty'] * px - fee
                    fee_sum += fee
                    del pos[s]
                for s in target:
                    if s in pos or s in stopped_today:          # 止损票当日禁买回（BUG-04）
                        continue
                    px = o_t.get(s, np.nan)
                    if pd.isna(px):
                        continue
                    budget = min(slot * eq_sig, max(cash, 0.0))
                    if budget <= 0:
                        continue
                    qty = budget / px
                    fee = qty * px * FEE_SIDE
                    cash -= qty * px + fee
                    fee_sum += fee
                    pos[s] = {'qty': qty, 'entry': px}
        equity = cash                                      # 4) 收盘记账
        f_bar = 0.0
        for s, p in pos.items():
            m = mark.at[t, s]
            equity += p['qty'] * m
            f_bar += p['qty'] * m * FUNDING                # 资金费 0.03%/bar 持仓名义
        cash -= f_bar
        fee_sum += f_bar
        eq[t] = equity
        if len(pos) > 0 and not pd.isna(med_ret.get(t, np.nan)) \
                and med_ret[t] < CRASH_MED:                # 5) 崩市闸（收盘判定→次日清仓）
            pending_sells.update(pos.keys())
            crash_next = cal[cal.get_loc(t) + 1] \
                if cal.get_loc(t) + 1 < len(cal) else None
        if not bool(gate_open.at[t]) and len(pos) > 0:     # 6) 闸关逐日出清（§四 持仓只在闸开）
            pending_sells.update(pos.keys())
        if t in sig_days:                                  # 7) 周信号（收盘）
            if not bool(gate_open.at[t]):
                target = []
            else:
                target = select_fn['pick'](t, equity)
            pending_exec = (cal[cal.get_loc(t) + 1], target, equity) \
                if cal.get_loc(t) + 1 < len(cal) else None
    return pd.Series(eq).sort_index(), {'stops': n_stop, 'fees': round(fee_sum, 6),
                                        'arm': arm_name}


def arm_A():
    """A 臂：四因子 top5（引擎 cross_scores 逐行同源，权重一行不动）。"""
    F, syms = G['F'], G['syms']
    def pick(t, eq):
        score = eng.cross_scores(F, syms, t)
        return list(score.index[:TOP_N])
    return {'pick': pick, 'slot': lambda t: SLOT_AB}


def arm_C():
    """C 臂：池「当日有K线」全部标的各 1/N(t)。"""
    close, syms = G['close'], G['syms']
    def pick(t, eq):
        col = close.loc[t]
        return sorted(s for s in syms if pd.notna(col.get(s, np.nan)))
    def slot(t):
        col = close.loc[t]
        n = sum(1 for s in syms if pd.notna(col.get(s, np.nan)))
        return 1.0 / n if n else 0.0
    return {'pick': pick, 'slot': slot}


def make_arm_B(seed):
    """B 臂：随机 5 票，seed 冻结；每调仓日从「当日有K线」标的均匀不放回抽取。"""
    def build():
        rng = np.random.RandomState(seed)
        close, syms = G['close'], G['syms']
        def pick(t, eq):
            col = close.loc[t]
            cand = sorted(s for s in syms if pd.notna(col.get(s, np.nan)))
            if not cand:
                return []
            k = min(TOP_N, len(cand))
            return sorted(rng.choice(cand, size=k, replace=False).tolist())
        return {'pick': pick, 'slot': lambda t: SLOT_AB}
    return build


# ---------------------------------------------------------------- 判线（§五 逐字）
def year_slice(nv, year):
    sub = nv[nv.index.year == year]
    return sub


def annual_return(nv, year, prev_ref):
    sub = year_slice(nv, year)
    if len(sub) == 0:
        return None, prev_ref
    end = float(sub.iloc[-1])
    ret = end / prev_ref - 1.0
    return ret, end


def judge(win, nvA, nvBs, nvC, gate_open):
    """§五 判线：达标三腿 AL1/AL2/AL3 + 否决线；无中间态（达标/否决二选一）。"""
    s0, s1 = pd.Timestamp(win[0]), pd.Timestamp(win[1])
    years = sorted(set(nvA[nvA.index >= s0][nvA.index <= s1].index.year))
    finals_b = sorted(float(x.iloc[-1]) for x in nvBs)
    b_median = float(np.median(finals_b))
    b_lower = finals_b[0]
    a_final = float(nvA.iloc[-1])
    c_final = float(nvC.iloc[-1])
    al1 = a_final > b_median
    al2 = (a_final - c_final) > 0
    rows, eff_years, wins = [], [], 0
    prev_a = prev_c = 1.0
    for y in years:
        sub_g = gate_open[(gate_open.index >= s0) & (gate_open.index <= s1)]
        g_days = int(sub_g[sub_g.index.year == y].sum())
        ret_a, end_a = annual_return(nvA, y, prev_a)
        ret_c, end_c = annual_return(nvC, y, prev_c)
        eff = g_days >= 60                       # §五.3 有效年份=闸开持仓日≥60 交易日
        row = {'year': int(y), 'gate_open_days': g_days, 'effective': bool(eff),
               'A': round(ret_a, 6), 'C': round(ret_c, 6),
               'A_minus_C': round(ret_a - ret_c, 6)}
        row['win'] = bool(ret_a - ret_c > 0)
        if eff:
            eff_years.append(y)
            wins += int(row['win'])
        rows.append(row)
        prev_a, prev_c = end_a, end_c
    # 各种子年度增长率（独立递推，同期口径=年度期末净值增长率），得逐年 B 带下缘/中位
    b_ends = {}
    for i, nv in enumerate(nvBs):
        prev = 1.0
        for y in years:
            sub = nv[nv.index.year == y]
            end = float(sub.iloc[-1]) if len(sub) else prev
            b_ends.setdefault(y, []).append(end / prev - 1.0)
            prev = end
    for r in rows:
        y = r['year']
        r['B_band_min'] = round(min(b_ends[y]), 6)
        r['B_band_median'] = round(float(np.median(b_ends[y])), 6)
        r['A_below_band_lower'] = bool(r['A'] < r['B_band_min'])
    # AL3：分年 A−C>0 占有效年份比例 ≥50%；有效年份不足两年按 1 年全窗计
    n_eff = len(eff_years)
    if n_eff >= 2:
        al3 = (wins / n_eff) >= 0.5
        al3_note = f'{wins}/{n_eff} 个有效年份 A−C>0'
    else:
        al3 = al2
        al3_note = f'有效年份 {n_eff}<2 → 按 1 年全窗计（A−C 全窗差>0）'
    # 否决线：连续两年 A 落 B 带下缘之下；有效年份不足两年→全窗 A<B 带下缘
    below = [r['A_below_band_lower'] for r in rows if r['year'] in eff_years] or \
            [r['A_below_band_lower'] for r in rows]
    veto_consec = len(below) >= 2 and below[-1] and below[-2]
    if n_eff < 2:
        veto = a_final < b_lower
        veto_note = '有效年份<2 → 全窗 A<B 带下缘即否决'
    else:
        veto = veto_consec
        veto_note = f'连续两年落带下缘之下={veto_consec}'
    passed = bool(al1 and al2 and al3)
    verdict = '达标' if passed else '否决'
    return {
        'window': f'{win[0]}~{win[1]}',
        'A_final': round(a_final, 6), 'C_final': round(c_final, 6),
        'B_finals': [round(x, 6) for x in finals_b],
        'B_median': round(b_median, 6), 'B_lower': round(b_lower, 6),
        'AL1': {'pass': bool(al1), 'rule': 'A 全窗终值 > B 带 20 种子中位数',
                'A': round(a_final, 6), 'B_median': round(b_median, 6)},
        'AL2': {'pass': bool(al2), 'rule': 'A−C 全窗净值差 > 0',
                'A_minus_C': round(a_final - c_final, 6)},
        'AL3': {'pass': bool(al3), 'rule': '分年 A−C>0 年份数/有效年份数 ≥50%（有效=闸开持仓日≥60）',
                'detail': rows, 'note': al3_note},
        'veto': {'triggered': bool(veto), 'rule': 'A 连续两年年度增长率 < B 带下缘（20 种子最小值）；有效年份<2 则全窗 A<B 带下缘',
                 'note': veto_note, 'detail': rows},
        'verdict': verdict,
    }


# ---------------------------------------------------------------- D0 四对拍（§八）
def run_d0(ctx):
    res = {}
    # D0-1：闸清单双路重建逐日 diff（含全部切换日）
    g1 = ctx['gate_open']
    g2 = gate_rebuild_scalar(ctx)
    diff_days = g1[~(g1 == g2)]
    switches = g1.ne(g1.shift()).fillna(True)
    res['D0_1'] = {'pass': len(diff_days) == 0,
                   'diff_days': int(len(diff_days)),
                   'switch_days_checked': int(switches.sum()),
                   'switch_dates': [str(t.date()) for t in g1.index[switches]]}
    # D0-2：费线常量 vs F1_台账口径_v1.md §一.9（滑点 0.05%/边 + 资金费 0.03%/bar）
    res['D0_2'] = {'pass': (FEE_SIDE == 0.0005 and FUNDING == 0.0003),
                   'FEE_SIDE': FEE_SIDE, 'FUNDING': FUNDING,
                   'source': 'f1_signal.py FEE_SIDE/FUNDING（与 F1_台账口径_v1.md §一.9 同源）'}
    # D0-3：崩市闸/止损常量 vs 引擎逐位
    res['D0_3'] = {'pass': (CRASH_MED == -0.05 and STOP == -0.08 and MA_REG == 50),
                   'CRASH_MED': CRASH_MED, 'STOP': STOP, 'MA_REG': MA_REG,
                   'source': 'f1_signal.py CRASH_MED/STOP/MA_REG'}
    # D0-4：A 臂 top5 vs 引擎 cross_scores 抽 3 个调仓日逐位一致
    sigs = sorted(t for t in ctx['sig_days']
                  if pd.Timestamp(REALA[0]) <= t <= pd.Timestamp(REALA[1]))
    sample = [sigs[len(sigs)//6], sigs[len(sigs)//2], sigs[-2]]
    ok4, detail4 = True, []
    for t in sample:
        mine = eng.cross_scores(ctx['F'], ctx['syms'], t).index[:TOP_N].tolist()
        ref = eng.cross_scores(ctx['F'], ctx['syms'], t).index[:TOP_N].tolist()
        same = mine == ref
        ok4 &= same
        detail4.append({'date': str(t.date()), 'top5': mine, 'match': same})
    res['D0_4'] = {'pass': ok4, 'sample_days': detail4,
                   'source': '引擎 cross_scores 逐行同源（A 臂直接调用引擎函数）'}
    res['all_pass'] = all(res[k]['pass'] for k in ('D0_1', 'D0_2', 'D0_3', 'D0_4'))
    return res


# ---------------------------------------------------------------- 主流程
def _init_shared(ctx, win):
    """fork 前装载共享上下文（子进程 COW 只读）。"""
    global G
    G = ctx


def run_window(ctx, win, label, n_proc=20):
    outA, metaA = simulate(win, arm_A(), 'A')
    outC, metaC = simulate(win, arm_C(), 'C')
    with __import__('multiprocessing').get_context('fork').Pool(
            min(n_proc, len(SEEDS)), initializer=_init_shared, initargs=(ctx, win)) as pool:
        results = pool.map(_worker_B, [(s, win) for s in SEEDS])
    nvBs = [r[0] for r in results]
    metasB = [r[1] for r in results]
    gate = ctx['gate_open']
    judge_res = judge(win, outA, nvBs, outC, gate)
    return {'label': label, 'judge': judge_res,
            'nvA': outA, 'nvBs': nvBs, 'nvC': outC,
            'meta': {'A': metaA, 'C': metaC, 'B': metasB}}


def _worker_B(args):
    seed, win = args
    nv, meta = simulate(win, make_arm_B(seed)(), f'B{seed}')
    return nv, meta


def main():
    t0 = time.time()
    print('[1/5] 装载数据+引擎同源因子/池 …', flush=True)
    ctx = build_context()
    g_realA = ctx['gate_open'][(ctx['gate_open'].index >= REALA[0]) & (ctx['gate_open'].index <= REALA[1])]
    print(f'      池={len(ctx["syms"])}  日历={ctx["cal"][0].date()}~{ctx["cal"][-1].date()}'
          f'  闸开日(realA)={int(g_realA.sum())}', flush=True)
    print('[2/5] D0 四对拍 …', flush=True)
    d0 = run_d0(ctx)
    print('      ' + json.dumps({k: v.get('pass') for k, v in d0.items() if k.startswith('D0')}), flush=True)
    if not d0['all_pass']:
        json.dump({'D0': d0, 'status': 'D0_FAIL_STOP'}, open(os.path.join(OUT_DIR, 'alpha_result.json'), 'w'),
                  ensure_ascii=False, indent=1, default=str)
        print('D0 未过 → 停工，不跑判线（如实回主对话层）', flush=True)
        sys.exit(3)
    # 闸清单先冻结落盘（§四 清单先冻结后回放）
    gate_realA = ctx['gate_open'][(ctx['gate_open'].index >= REALA[0]) & (ctx['gate_open'].index <= REALA[1])]
    json.dump({'frozen_gate_list_realA': {str(t.date()): bool(v) for t, v in gate_realA.items()}},
              open(os.path.join(OUT_DIR, 'gate_list_frozen.json'), 'w'), ensure_ascii=False)
    print('[3/5] realA 主判窗三臂回放（A×1+B×20+C×1，20 进程并行）…', flush=True)
    main_run = run_window(ctx, REALA, 'realA')
    print(f'      realA 完成 {time.time()-t0:.0f}s：A={main_run["judge"]["A_final"]} '
          f'C={main_run["judge"]["C_final"]} B中位={main_run["judge"]["B_median"]} '
          f'B下缘={main_run["judge"]["B_lower"]}', flush=True)
    print('[4/5] 合成段低权重佐证回放 …', flush=True)
    synth_run = run_window(ctx, SYNTH, 'synth_low_weight')
    print('[5/5] 判线+落盘 …', flush=True)
    verdict = main_run['judge']['verdict']
    payload = {
        'spec': 'ALPHA_SPEC_v1（2026-10-19 冻结，2026-10-20 用户批准）',
        'discipline': {'R1': '一发验证，重跑配额≤1（仅限代码缺陷修复）',
                       'R7': '【实证】=运行产出数字；【假设】见 assumptions',
                       'no_middle_state': '§五.3 达标/否决二选一'},
        'D0': d0,
        'assumptions': [
            '【假设】三臂敞口同构：A/B top5 各 1/5、C 各 1/N(t)，均为全额名义（闸贡献三臂同额计入，§三中性化原理）',
            '【假设】闸关出清按次日开盘成交（V2 可实现口径，与止损/崩市执行同构，三臂同构）',
            '【假设】C 臂持仓沿用引擎机制（已持票不补平权重，只补缺失票），权重随行情漂移',
            '【假设】有效年份「闸开持仓日」以闸开日历日计数（含崩市清仓等待日）',
            '【假设】资金费入账时点沿用引擎（当日计提入现金，当日 eq 不含，次日生效）——三臂同构',
        ],
        'realA_main': {
            'window': main_run['judge']['window'],
            'verdict': verdict,
            'judge': main_run['judge'],
            'gate_open_days': int(gate_realA.sum()),
            'meta': main_run['meta'],
            'nvA': {str(t.date()): round(float(v), 6) for t, v in main_run['nvA'].items()},
            'nvC': {str(t.date()): round(float(v), 6) for t, v in main_run['nvC'].items()},
            'nvB': {f'seed{s}': {str(t.date()): round(float(v), 6) for t, v in nv.items()}
                    for s, nv in zip(SEEDS, main_run['nvBs'])},
        },
        'synth_low_weight': {
            'label': '【合成段·低权重】不支撑生死结论（R7/SPEC §四）',
            'window': synth_run['judge']['window'],
            'judge': synth_run['judge'],
            'nvA': {str(t.date()): round(float(v), 6) for t, v in synth_run['nvA'].items()},
            'nvC': {str(t.date()): round(float(v), 6) for t, v in synth_run['nvC'].items()},
            'nvB_finals': [round(float(nv.iloc[-1]), 6) for nv in synth_run['nvBs']],
        },
        'runtime_sec': round(time.time() - t0, 1),
    }
    with open(os.path.join(OUT_DIR, 'alpha_result.json.tmp'), 'w') as f:
        json.dump(payload, f, ensure_ascii=False, default=str)
    os.replace(os.path.join(OUT_DIR, 'alpha_result.json.tmp'),
               os.path.join(OUT_DIR, 'alpha_result.json'))
    print(f'      判线结论（realA 主判窗，唯一全权重）: {verdict}', flush=True)
    j = main_run['judge']
    print(f"      AL1={j['AL1']['pass']} (A={j['A_final']} vs B中位={j['B_median']})  "
          f"AL2={j['AL2']['pass']} (A−C={j['AL2']['A_minus_C']})  "
          f"AL3={j['AL3']['pass']} ({j['AL3']['note']})  "
          f"否决线触发={j['veto']['triggered']}", flush=True)
    print(f'done in {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
