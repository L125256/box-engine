#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
四胜任格影子计数器（SHADOW_SPEC_v1 照抄施工件 · S1-S3 因子格 + S4 换门事件格）
================================================================================
【规格出处（冻结，禁改判据）】research/wo_mine/SHADOW_SPEC_v1.md（2026-10-20 预注册
冻结，首席策略官·何执舟终裁批准）：影子期目的=前瞻复验后再议双池/部署；影子读数
不回写部署姿态（R10），影子达标≠放行。
- SH-1 采集挂接：每日判定轮命令之后追加本件 --auto（只读+旁路落盘，异常不阻断判定轮）
  ——与辅轨 forward_readout 同一挂点（engine_f1/f1_signal.py live 分支尾部 subprocess）。
- SH-2 影子窗：2026-10-18 起（FULL 窗尾日 2026-10-17 之后），与 FR-1 同窗同源。
- SH-3 状态落盘：f1/shadow_state.json + f1/shadow_days.jsonl（随判定轮回传持久化）。
- SH-4 判读门槛：每格 n≥20 前瞻信号日 → 判读一次并封印（sealed=true，禁重复判读）。
- SH-5 早判死：n≥10 且 IC 均值<0 且 t≤−2 → 立即判读（判死）并封印。
- SH-6 数据不足→不判读只累计，禁止任何结论输出。
- 判线（§3 数字冻结）：S1-S3 因子格三腿=IC 均值>0 ∧ t≥2 ∧ IC 日方向命中率≥60%；
  S1-S3 失败=IC 均值<0（n≥20 即判死）或早判死条款；S4 事件格三腿=avoid>0 ∧
  mdd_red≥10% ∧ lag=1 不翻转，事件≥3 次判读，失败=avoid<0 或 mdd_red<0。
- S4 补样（§4）：old131 弱稳真实数据自然累积满 4 天（n_days 56→60）当轮自动
  SUSPENDED→ACTIVE；补齐前 S4 计数器 suspended=true——不采集、不计数、不判读、
  不输出任何中间读数；补齐=获得入图谱资格，不等于 old131 胜任。
- 双池纪律（§3）：S4 在 old131 补齐前只对 full144 单池读数；补齐后两池均入影子，
  影子「达标」要求双池同向。S1-S3 仅 full144 域格。
- S5=fd-da 格（FD_REVIVE_SPEC_v1 §4 J5 + 交易分析团队终裁 2026-10-20 影子挂接授权，
  判线承继 J5 冻结数字）：每日旁路采集 fd 分批+保本出场（D-A）前瞻同信号配对 ΔR
  （入场 scan_fd_exit 零改动 + 出场 _fd_exit_fns D-A/ctrl 逐字 + pair_stats/
  delta_summary 逐字，全部复用 research/wo_fddual/fd_revive_run.py）；判线=
  n≥20 配对前瞻信号 Δ meanR>0，判读一次封印 sealed=true，n<20 只累计不判；
  判死后复活路径(a)=按同判线机械复判每自然季至多一次；影子读数不回写部署姿态
  （R10）。施工登记项 f1/fd_revive_state.json（比照 SH-3，n 计数/sealed/季度
  复判时间戳字段）+ f1/fd_revive_days.jsonl 逐笔读数。

【骨架承继】research/wo_unlock/forward_readout.py（FR 谱系）：仓库根相对路径
（__file__ 上溯两级，env 可覆盖，禁绝对路径）、引擎快照缓存首跑自动解包、状态文件
落 f1/ 随判定轮回传、输入接线=f1/f1_live.json signal.asof（只读血缘）。

【口径操作化·R7 登记·SHADOW_SPEC 未逐字定义处提请终裁】
- _OPS1 S1-S3 采集频次=日频（非周信号日）：ATLAS 底层读数=batch2 逐日截面 IC 按域
  分窗均值（SHADOW_SPEC §3 自述「日频 Spearman 截面 IC」「回测段日命中率」），
  影子复验须同尺度方可与锚可比；成熟度=fwd5 满 5 交易日（承继 FR-2 成熟登记语义）。
- _OPS2 域标签：回测段=domains.json 冻结标签（D0 断言与 B1.pool_d1 重算逐位一致）；
  前瞻段=同式实时延拓（轴A=idx/MA50，轴B=vol_med>冻结锚 VAG，lag=1）。
- _OPS3 S4 触发事件=门信号（vol20>thr80，执行日读 shift(1)）在影子窗内连续为真的
  段数（episode）；S4 判读触发以主格池 full144 事件≥3 为准，old131 随双池纪律并入。
- _OPS4 S4 判读输出含三态：达标/失败（§3 两条失败路径）/未达标（事件≥3 但三腿
  未全过且未触发失败路径——n≥事件门即判即封印，无中间态留窗）。
- _OPS5 S5 扫描口径（WO-DECBAR 判定轮 bar 选择承继）：剔除数据尾日=运行日的
  未收盘盘中 bar（当日盘中伪出场不入册），只用最后完整日收盘数据扫描；D0 复放
  用冻结副本（尾日 2026-10-18 全完整），不受影响。
- _OPS6 S5 影子读数只计「已平仓」配对信号：D-A/ctrl 两臂出场均已发生（why≠数据末）
  方入计数——持仓中交易的 r 为临时值，入册即伪读数（fd_revive_run 回测口径为
  全历史窗，此差异为本格前瞻化操作化，提请终裁追认）。
- _OPS7 S5 fd 谱系装载回落：eng_final 优先 /tmp/eng_wt_rc（fd_revive_run 在库口径），
  /tmp 失忆时回落仓库内 research/eng_wt_rc（同件）；D0 数据=冻结快照内容副本
  /tmp/box_cache_fresh（缺失即停工重锚，禁以 live 数据代跑 D0）；前瞻采集=
  live 唯一数据态（S1-S4 同源 _cache_dir()）。

用法：python3 research/wo_mine/shadow_cells.py [--auto] [--d0]
产出：f1/shadow_state.json + f1/shadow_days.jsonl（+判读时 f1/shadow_readout_*.json）
     + f1/fd_revive_state.json + f1/fd_revive_days.jsonl（S5 格，判读时 f1/fd_revive_readout_*.json）
"""
import json
import os
import sys
import tarfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))                       # research/wo_mine
ROOT = os.environ.get('SHADOW_REPO_ROOT') or \
    os.path.dirname(os.path.dirname(_HERE))                              # 仓库根（__file__ 相对，禁绝对路径）
sys.path.insert(0, _HERE)

FW0 = '2026-10-18'                       # SH-2 影子窗起点（FR-1 同窗）
MIN_READOUT_DAYS = 20                    # SH-4
EARLY_DEATH_DAYS = 10                    # SH-5
FWD_H = 5                                # S1-S3 判据 horizon（batch2 谱系 fwd5）
MIN_NAMES = 30                           # xsec_ic_series 谱系门
HIT_RATE_LINE = 0.60                     # §3 稳定性腿（定夺点：用户批准 60%）
T_LINE = 2.0                             # §3 显著性腿
MDD_RED_LINE = 10.0                      # §3 S4 腿②（FR-8 承继）
REPLENISH_NEED = 4                       # §4 old131 弱稳补样 4 天（n_days 56→60）
ATLAS_N_DAYS = 56                        # ATLAS K1-p80|old131|弱稳 现值
STATEDIR = os.path.join(ROOT, 'f1')      # 状态随判定轮回传（云端持久目录）
STATE_F = os.path.join(STATEDIR, 'shadow_state.json')
DAYS_F = os.path.join(STATEDIR, 'shadow_days.jsonl')
ROUND_F = os.path.join(ROOT, 'f1', 'f1_live.json')   # 判定轮产物（血缘只读）
SNAPSHOT_TAR = os.path.join(ROOT, 'engine_snapshot', 'box_cache_snapshot.tar.gz')
SPEC_F = os.path.join(_HERE, 'SHADOW_SPEC_v1.md')
# ---- S5=fd-da（FD_REVIVE_SPEC_v1 §4 J5 冻结 + 终裁 2026-10-20 影子挂接授权）----
S5_FW = '2026-10-20'                     # §3.1④ 影子窗起点（快照尾日次日，晚于规格冻结时刻）
S5_N_LINE = 20                           # J5 冻结：n≥20 配对前瞻信号
FD_FRESH_CACHE = '/tmp/box_cache_fresh'  # D0 冻结快照内容副本（fd_revive_run 同款）
FD_ENG_TMP = '/tmp/eng_wt_rc'            # eng_final 优先路径（fd_revive_run 在库口径）
FD_ENG_REPO = os.path.join(ROOT, 'research', 'eng_wt_rc')   # /tmp 失忆回落（_OPS7）
FD_STATE_F = os.path.join(STATEDIR, 'fd_revive_state.json') # 终裁施工登记项（比照 SH-3）
FD_DAYS_F = os.path.join(STATEDIR, 'fd_revive_days.jsonl')  # S5 逐笔读数（比照 shadow_days.jsonl）
FD_RESULT_F = os.path.join(ROOT, 'research', 'wo_fddual', 'fd_revive_result.json')
ATLAS_ANCHORS = {   # ATLAS_v1.md 底层读数（D0 断言源；S1/S2/S3=域内日 IC 均值，6 位小数）
    'S1': {'variant_id': 'Q3-rev-liq', 'domain': '弱躁', 'anchor': 0.133685},
    'S2': {'variant_id': 'Q3-rev-5', 'domain': '弱躁', 'anchor': 0.10875},
    'S3': {'variant_id': 'Q1-brk-pos-20', 'domain': '牛躁', 'anchor': 0.1126},
}

# 延迟重导入（首次调用 ~20s，常驻判定轮可接受）
_ENG_LOADED = False


def _cache_dir():
    """数据缓存：env 覆盖 > /tmp/box_cache（OD-R1 引擎唯一数据态，批次谱系锚
    全在其上逐位复现——本件 D0 实测四腿 diff=0）> 仓库内 .cache（首跑从快照包
    解包，幂等；云端沙箱无 /tmp 时的兜底）。"""
    env = os.environ.get('SHADOW_BOX_CACHE') or os.environ.get('FORWARD_BOX_CACHE')
    if env:
        return env
    d = '/tmp/box_cache'
    if os.path.isdir(d) and os.listdir(d):
        return d
    d = os.path.join(ROOT, '.cache', 'box_cache')
    if not os.path.isdir(d) or not os.listdir(d):
        os.makedirs(d, exist_ok=True)
        with tarfile.open(SNAPSHOT_TAR, 'r:gz') as tf:
            tf.extractall(os.path.dirname(d))          # 包内顶层即 box_cache/
    return d


def _eng():
    """谱系件装载：mine_common/batch1/batch2（因子式与统计件逐字复用，禁另写）。"""
    global _ENG_LOADED
    import mine_common as MC
    if not _ENG_LOADED:
        MC.CACHE = _cache_dir()          # 数据源=仓库内快照/env 覆盖（云端化接线点）
        import batch1_run as B1
        import batch2_run as B2
        _ENG_LOADED = True
    import mine_common as MC
    import batch1_run as B1
    import batch2_run as B2
    return MC, B1, B2


def _round_asof():
    """判定轮产物血缘（只读，不参与判据）：f1/f1_live.json 的 signal.asof。"""
    try:
        with open(ROUND_F) as f:
            d = json.load(f)
        return d.get('signal', {}).get('asof') or d.get('meta', {}).get('asof')
    except Exception:
        return None


# ------------------------------------------------------------- 因子格（batch2 谱系）
def factor_panels(B2):
    """batch2_run.panels() 逐字复用（full144 面板：C/H/V/ret5/fwd5/turn20）。"""
    return B2.panels()


def factor_series(P, vid):
    """三格因子式=batch2_run.py VS 清单逐字抄录（禁改写）：
    - Q3-rev-liq（batch2_run.py:438）：(-ret5).where(turn20>当日中位)
    - Q3-rev-5 （batch2_run.py:436）：-ret5
    - Q1-brk-pos-20（batch2_run.py:360-361/374）：C/H.rolling(20).max().shift(1)-1
    horizon 一律 fwd5（同源 VS 清单）。"""
    if vid == 'Q3-rev-liq':
        turn20 = P['turn20']
        liq_med = turn20.median(axis=1)
        return (-P['ret5']).where(turn20.gt(liq_med, axis=0))
    if vid == 'Q3-rev-5':
        return -P['ret5']
    if vid == 'Q1-brk-pos-20':
        C, H = P['C'], P['H']
        return C / H.rolling(20).max().shift(1) - 1.0
    raise ValueError(vid)


# ------------------------------------------------------------- D0（工单件⑥：首跑过锚）
def d0_check(MC, B1, B2, state):
    """四断言：①full144 域标签重算 vs domains.json 冻结标签逐位一致；
    ②S1-S3 FULL 窗域内日 IC 均值 vs ATLAS 锚 diff=0（6 位小数）；
    ③S4 重放 gate80 pause 臂 FULL avoid/mdd_red vs FACTBOOK_BATCH3 ±0.01；
    ④old131 补样基线 n_days=56 与 ATLAS 一致。任一 FAIL 即停工（batch 谱系条款）。"""
    import numpy as np
    import pandas as pd
    dom = json.load(open(os.path.join(_HERE, 'domains.json')))
    frozen = dom['labels']['d1']
    # ① 域标签零漂移（B1.pool_d1 重算 vs 冻结；断言域=域锚窗 MS_REALA 内——
    #    合成段早期历史行 vintage 差（快照 vs 缓存）不影响影子窗与锚，差异只登记）
    lab_live = B1.pool_d1('full144')
    common = sorted(k for k in (set(frozen) & set(lab_live)) if k >= '2025-06-01')
    diff = [(k, frozen[k], lab_live[k]) for k in common if frozen[k] != lab_live[k]]
    early = [(k, frozen[k], lab_live[k]) for k in (set(frozen) & set(lab_live))
             if k < '2025-06-01' and frozen[k] != lab_live[k]]
    chk1 = {'name': 'd1_labels_zero_drift', 'assert_window': 'MS_REALA 2025-06-01 起',
            'n_common': len(common), 'n_diff': len(diff),
            'out_of_window_diff_registered': len(early),
            'verdict': 'hit' if not diff else 'MISS'}
    if diff:
        chk1['sample_diff'] = diff[:5]
    if early:
        chk1['early_sample'] = early[:3]
    # ② S1-S3 域内日 IC 均值 vs ATLAS 锚（FULL 窗 + 冻结标签）
    P = factor_panels(B2)
    full = B1.FULL
    cells = {}
    chk2 = {'name': 'atlas_anchor_diff0', 'window': [str(full[0].date()), str(full[1].date())],
            'cells': cells}
    all_hit = True
    for cid, spec in ATLAS_ANCHORS.items():
        fa = factor_series(P, spec['variant_id']).sort_index()
        fwd = P['fwd5']
        ic = MC.xsec_ic_series(fa[(fa.index >= full[0]) & (fa.index <= full[1])], fwd)
        dom_ic = [float(v) for t, v in ic.items()
                  if frozen.get(str(pd.Timestamp(t).date())) == spec['domain']]
        mean6 = round(float(np.mean(dom_ic)), 6) if dom_ic else None
        hit = mean6 is not None and abs(mean6 - spec['anchor']) == 0.0
        all_hit = all_hit and hit
        cells[cid] = {'variant_id': spec['variant_id'], 'domain': spec['domain'],
                      'n_days': len(dom_ic), 'ic_mean_6dp': mean6,
                      'atlas_anchor': spec['anchor'], 'diff': None if mean6 is None else round(mean6 - spec['anchor'], 9),
                      'backtest_hit_rate': round(float(np.mean([v > 0 for v in dom_ic])), 4) if dom_ic else None,
                      'verdict': 'hit' if hit else 'MISS'}
    chk2['verdict'] = 'hit' if all_hit else 'MISS'
    # ③ S4 重放 gate80 臂 vs FACTBOOK_BATCH1 FULL 行（±0.01，batch3 replay 同款；
    #    batch3 对重放臂只落 D2 行无 FULL 行，故参照源=FACTBOOK_BATCH1，
    #    batch3 replay_check_all=hit 已证 batch1 行可确定性复现）
    fb1 = [json.loads(l) for l in open(os.path.join(_HERE, 'FACTBOOK_BATCH1.jsonl'))]
    ref = {r['pool']: r for r in fb1
           if r['variant_id'] == 'K1-d-gate-vol20p80-pause' and r['axis'] == 'FULL'}
    curves = s4_curves(MC, B1)
    chk3 = {'name': 's4_replay_factbook_batch1', 'tol': 0.01, 'pools': {}}
    ok3 = True
    for p, cv in curves.items():
        gs = B1.seg_stats(cv['gate80'], *full)
        bs = B1.seg_stats(cv['base'], *full)
        mdd_red = ((abs(bs['mdd_pct']) - abs(gs['mdd_pct'])) / abs(bs['mdd_pct']) * 100
                   if bs['mdd_pct'] != 0 else None)
        a, mr = round(gs['ret_pp'] - bs['ret_pp'], 4), (None if mdd_red is None else round(mdd_red, 2))
        r = ref.get(p)
        ok = (r is not None and abs(a - r['avoid_pp']) <= 0.01
              and mr is not None and r['mdd_red_pct'] is not None
              and abs(mr - r['mdd_red_pct']) <= 0.01)
        ok3 = ok3 and ok
        chk3['pools'][p] = {'replay_avoid': a, 'replay_mdd_red': mr,
                            'factbook1_avoid': None if r is None else r['avoid_pp'],
                            'factbook1_mdd_red': None if r is None else r['mdd_red_pct'],
                            'verdict': 'hit' if ok else 'MISS'}
    chk3['verdict'] = 'hit' if ok3 else 'MISS'
    # ④ 补样基线
    chk4 = {'name': 's4_replenish_baseline', 'atlas_n_days': ATLAS_N_DAYS,
            'replenish_need': REPLENISH_NEED, 'target_n_days': ATLAS_N_DAYS + REPLENISH_NEED,
            'verdict': 'hit' if ATLAS_N_DAYS == 56 and REPLENISH_NEED == 4 else 'MISS'}
    out = {'ran_at': time.strftime('%F %T'), 'checks': [chk1, chk2, chk3, chk4],
           'all_pass': bool(chk1['verdict'] == 'hit' and chk2['verdict'] == 'hit'
                            and chk3['verdict'] == 'hit' and chk4['verdict'] == 'hit'),
           'lineage': 'SHADOW_SPEC_v1 工单件⑥：shadow 首跑读数与 ATLAS 底层数据 diff=0'}
    state['d0'] = out
    print(f"shadow D0: all_pass={out['all_pass']}（标签零漂移={chk1['verdict']} "
          f"ATLAS 锚 diff0={chk2['verdict']} S4 重放={chk3['verdict']}）")
    return out


# ------------------------------------------------------------- S4 换门事件格
def s4_curves(MC, B1):
    """S4 臂曲线（batch3_run.py run_k1 gate80 臂逐字同构，只 diff 无）：
    base=gate 谱系无 overlay；gate80=cond80.shift(1) pause；gate80lag1=cond80.shift(2) pause。
    阈值=domains.json anchors.gate_vol20_p80_by_pool（冻结锚）。"""
    import json
    thr80 = json.load(open(os.path.join(_HERE, 'domains.json')))[
        'anchors']['gate_vol20_p80_by_pool']
    out = {}
    for p in ('full144', 'old131'):
        P = MC.build_ctx()[p]
        cond80 = (P['vol20'] > thr80[p]).fillna(False)
        base = MC.simulate(MC.build_ctx(), p, lineage='gate')
        g80 = MC.simulate(MC.build_ctx(), p, lineage='gate',
                          overlay={'off': cond80.shift(1).fillna(False), 'mode': 'pause'})
        g80l1 = MC.simulate(MC.build_ctx(), p, lineage='gate',
                            overlay={'off': cond80.shift(2).fillna(False), 'mode': 'pause'})
        out[p] = {'base': base['curve'], 'gate80': g80['curve'], 'gate80lag1': g80l1['curve'],
                  'cond80': cond80, 'thr80': thr80[p]}
    return out


def gate_episodes(cond_exec, t0, t1):
    """_OPS3：执行日读门信号（shift(1) 后）在 [t0,t1] 内连续为真的段数与段清单。"""
    import pandas as pd
    s = cond_exec[(cond_exec.index >= pd.Timestamp(t0)) & (cond_exec.index <= pd.Timestamp(t1))]
    eps, cur = [], None
    for t, v in s.items():
        if bool(v):
            cur = [t, t] if cur is None else [cur[0], t]
        else:
            if cur is not None:
                eps.append(cur)
                cur = None
    if cur is not None:
        eps.append(cur)
    return eps


def s4_collect(state):
    """S4 补样状态机 +（ACTIVE 后）事件计数。suspended 期不采集不判读（§4）。"""
    import pandas as pd
    MC, B1, _ = _eng()
    ctx = MC.build_ctx()
    lab_old = B1.pool_d1('old131')
    cal_old = ctx['old131']['cal']
    fw = pd.Timestamp(FW0)
    weak_days = [str(t.date()) for t in cal_old
                 if t >= fw and lab_old.get(str(t.date())) == '弱稳']
    g = state['cells']['S4']
    g['replenish'] = {'fw_old131_weak_days': len(weak_days), 'need': REPLENISH_NEED,
                      'days': weak_days, 'n_days_if_completed': ATLAS_N_DAYS + len(weak_days),
                      'unit': 'old131 池 lag=1 域标签=弱稳 的真实交易日（ATLAS n_days 同单位）',
                      'updated_at': time.strftime('%F %T')}
    if g['gate_state'] == 'SUSPENDED':
        if len(weak_days) >= REPLENISH_NEED:
            g['gate_state'] = 'ACTIVE'
            g['activated_at'] = time.strftime('%F %T')
            g['activation_note'] = (f"§4：old131 弱稳真实累积 {len(weak_days)}≥{REPLENISH_NEED} 天，"
                                    f"n_days {ATLAS_N_DAYS}→{ATLAS_N_DAYS + len(weak_days)} 达 60 日门；"
                                    "补齐=入图谱资格，不等于胜任（保守席条款）；双池并入影子")
            print(f"shadow S4: SUSPENDED→ACTIVE（{g['activation_note']}）")
        else:
            print(f"shadow S4: SUSPENDED（补样 {len(weak_days)}/{REPLENISH_NEED}）"
                  "——不采集不计数不判读（§4 不启停规则）")
            return
    # ACTIVE：事件计数（full144 主格 + old131 双池）
    cv = s4_curves(MC, B1)
    last = max(c.index[-1] for c in (cv['full144']['base'], cv['old131']['base']))
    ev = {}
    for p in cv:
        eps = gate_episodes(cv[p]['cond80'].shift(1).fillna(False), FW0, str(last.date()))
        ev[p] = {'n_episodes': len(eps), 'episodes': [[str(a.date()), str(b.date())] for a, b in eps]}
    g['events'] = {'updated_at': time.strftime('%F %T'), 'window': [FW0, str(last.date())],
                   'by_pool': ev, 'trigger_pool': 'full144', 'trigger_line': 3}
    state['s4_cache'] = {'seg_window': [FW0, str(last.date())]}
    n_ev = ev['full144']['n_episodes']
    if n_ev >= 3 and not g.get('sealed'):
        do_s4_readout(state, cv, ev, str(last.date()))


def do_s4_readout(state, cv, ev, last_day):
    """S4 判读（§3 三腿，一次封印）：avoid>0 ∧ mdd_red≥10% ∧ lag=1 不翻转；
    失败=avoid<0 或 mdd_red<0（主格池）。双池同向=达标前置（§3 双池纪律）。"""
    MC, B1, _ = _eng()
    import pandas as pd
    win = (pd.Timestamp(FW0), pd.Timestamp(last_day))
    pools = {}
    for p, c in cv.items():
        seg = lambda cur: B1.seg_stats(cur, *win)
        gs, bs = seg(c['gate80']), seg(c['base'])
        lg = seg(c['gate80lag1'])
        avoid = round(gs['ret_pp'] - bs['ret_pp'], 4)
        mdd_red = round((abs(bs['mdd_pct']) - abs(gs['mdd_pct'])) / abs(bs['mdd_pct']) * 100, 2)
        lag_avoid = round(lg['ret_pp'] - bs['ret_pp'], 4)
        pools[p] = {'avoid_pp': avoid, 'mdd_red_pct': mdd_red, 'lag1_avoid_pp': lag_avoid,
                    'n_episodes': ev[p]['n_episodes'],
                    'pass_avoid_gt0': bool(avoid > 0), 'pass_mdd_red10': bool(mdd_red >= MDD_RED_LINE),
                    'pass_lag_no_flip': bool(lag_avoid > 0)}
        pools[p]['all_legs'] = bool(pools[p]['pass_avoid_gt0'] and pools[p]['pass_mdd_red10']
                                    and pools[p]['pass_lag_no_flip'])
    main = pools['full144']
    fail = bool(main['avoid_pp'] < 0 or main['mdd_red_pct'] < 0)
    dual_same = all(v['all_legs'] for v in pools.values())
    if fail:
        verdict, verdict_note = 'FAIL', '§3 失败路径：avoid<0 或 mdd_red<0（主格池）'
    elif dual_same:
        verdict, verdict_note = 'PASS', '§3 达标：三腿全过 ∧ 双池同向（影子达标≠放行，R10）'
    else:
        verdict, verdict_note = 'NOT_PASS', ('_OPS4：事件≥3 即判即封印；三腿未全过或双池不同向，'
                                             '非 §3 失败路径，判「未达标」')
    readout = {'readout_at': time.strftime('%F %T'), 'cell': 'S4',
               'cell_id': 'K1|K1-d-gate-vol20p80-pause|full144|弱稳',
               'window': [FW0, last_day], 'events_by_pool': ev, 'pools': pools,
               'dual_pool_same_direction': dual_same,
               'verdict': verdict, 'verdict_note': verdict_note,
               'r10_note': '影子读数不回写部署姿态（R10）；达标≠放行',
               'seal': {'sealed': True, 'rule': 'SH-4/SH-7：判读一次并封印，禁重复判读'}}
    with open(os.path.join(STATEDIR, f"shadow_readout_S4_{readout['readout_at'][:10]}.json"),
              'w') as f:
        json.dump(readout, f, ensure_ascii=False, indent=1)
    g = state['cells']['S4']
    g.update({'sealed': True, 'sealed_at': readout['readout_at'], 'verdict': verdict,
              'last_readout': readout})
    print(f"[SHADOW-S4] 判读封印：{verdict}（{verdict_note}）")


# ------------------------------------------------------------- S1-S3 因子格采集/判读
def load_days():
    if not os.path.exists(DAYS_F):
        return []
    out = []
    with open(DAYS_F) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def collect_factor_cells(state):
    """SH-2/SH-3：影子窗内、域限定（因子研究席条款：不跨域采集）、fwd5 成熟的
    日频截面 IC 逐日落盘（_OPS1/_OPS2）；返回各格本轮新增数。"""
    import pandas as pd
    MC, B1, B2 = _eng()
    P = factor_panels(B2)
    lab = B1.pool_d1('full144')
    fw = pd.Timestamp(FW0)
    done = {(d['cell'], d['date']) for d in load_days()}
    new_rows = []
    counts = {}
    for cid, spec in ATLAS_ANCHORS.items():
        fa = factor_series(P, spec['variant_id']).sort_index()
        ic = MC.xsec_ic_series(fa, P['fwd5'])          # fwd5 未成熟日=NaN 自动不产 IC
        n_new = 0
        for t, v in ic.items():
            d = str(pd.Timestamp(t).date())
            if pd.Timestamp(t) < fw or (cid, d) in done:
                continue
            if lab.get(d) != spec['domain']:           # 域限定（不跨域采集）
                continue
            new_rows.append({'cell': cid, 'variant_id': spec['variant_id'],
                             'domain': spec['domain'], 'date': d,
                             'ic': round(float(v), 6),
                             'collected_at': time.strftime('%F %T')})
            done.add((cid, d))
            n_new += 1
        counts[cid] = n_new
    if new_rows:
        with open(DAYS_F, 'a') as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    return counts


def judge_factor_cell(cid, days):
    """§3 判线（数字冻结）：达标三腿 IC>0 ∧ t≥2 ∧ 命中率≥60%；失败=IC<0（n≥20）
    或早判死（n≥10 ∧ IC<0 ∧ t≤−2）；其余只累计（SH-6）。返回 (action, detail)。"""
    import numpy as np
    ics = np.array([d['ic'] for d in days], dtype=float)
    n = len(ics)
    mean = float(ics.mean()) if n else None
    sd = float(ics.std(ddof=1)) if n >= 2 else None
    t = float(mean / sd * np.sqrt(n)) if (n >= 3 and sd and sd > 0) else None
    hit = float((ics > 0).mean()) if n else None
    det = {'n_days': n, 'ic_mean': None if mean is None else round(mean, 6),
           'ic_t': None if t is None else round(t, 4),
           'hit_rate': None if hit is None else round(hit, 4),
           'target': MIN_READOUT_DAYS, 'early_death_line': EARLY_DEATH_DAYS}
    if n >= MIN_READOUT_DAYS:
        legs = {'ic_gt0': bool(mean > 0), 't_ge2': bool(t is not None and t >= T_LINE),
                'hit_ge60': bool(hit is not None and hit >= HIT_RATE_LINE)}
        if mean < 0:
            return 'READOUT', {**det, 'verdict': 'FAIL',
                               'verdict_note': '§3 失败：IC 均值<0（方向翻转，n≥20 即判死）'}
        if all(legs.values()):
            return 'READOUT', {**det, 'verdict': 'PASS', 'legs': legs,
                               'verdict_note': '§3 达标：三腿全过（影子达标≠放行，R10）'}
        return 'READOUT', {**det, 'verdict': 'NOT_PASS', 'legs': legs,
                           'verdict_note': ('_OPS4：n≥20 即判即封印；三腿未全过且未触发失败路径，'
                                            '判「未达标」')}
    if n >= EARLY_DEATH_DAYS and mean is not None and mean < 0 \
            and t is not None and t <= -T_LINE:
        return 'READOUT', {**det, 'verdict': 'FAIL',
                           'verdict_note': '§3/SH-5 早判死：n≥10 ∧ IC<0 ∧ t≤−2'}
    return 'ACCUMULATE', det


def do_factor_readout(cid, det, state):
    readout = {'readout_at': time.strftime('%F %T'), 'cell': cid,
               'cell_id': f"{cid}|{ATLAS_ANCHORS[cid]['variant_id']}|full144|{ATLAS_ANCHORS[cid]['domain']}",
               'judgment_basis': 'SHADOW_SPEC_v1 §3（数字冻结：IC>0 ∧ t≥2 ∧ 命中率≥60%；'
                                 '早判死 n≥10/t≤−2；一次判读封印）',
               **det,
               'r10_note': '影子读数不回写部署姿态（R10）；达标≠放行',
               'seal': {'sealed': True, 'rule': 'SH-4/SH-7：判读一次并封印，禁重复判读'}}
    with open(os.path.join(STATEDIR, f"shadow_readout_{cid}_{readout['readout_at'][:10]}.json"),
              'w') as f:
        json.dump(readout, f, ensure_ascii=False, indent=1)
    g = state['cells'][cid]
    g.update({'sealed': True, 'sealed_at': readout['readout_at'], 'verdict': det['verdict'],
              'last_readout': readout})
    print(f"[SHADOW-{cid}] 判读封印：{det['verdict']}（{det['verdict_note']}）")


# ------------------------------------------------------------- S5=fd-da 格（fd_revive_run 逐字复用）
_fd = None


def _fd_eng():
    """fd 谱系装载（_OPS7）：fd_revive_run.py 逐字复用——入场 scan_fd_exit 零改动、
    出场 _fd_exit_fns（D-A=partial3r-breakeven / ctrl）逐字、pair_stats/delta_summary
    逐字、_w_main Pool 任务逐字。禁另写任何出场/配对逻辑。"""
    global _fd
    if _fd is None:
        if not os.path.isdir(FD_ENG_TMP) and os.path.isdir(FD_ENG_REPO):
            sys.path.insert(0, FD_ENG_REPO)          # /tmp 失忆回落（同件）
        sys.path.insert(0, os.path.join(ROOT, 'research', 'wo_fddual'))
        import fd_revive_run as FR
        import common_fdbrk as CF
        _fd = (FR, CF)
    return _fd


def _fd_load_cache(CF, cache):
    """数据态切换（common_fdbrk 单例重置）：D0=冻结副本（realA 逐位对拍）；
    前瞻=live 唯一数据态（S1-S4 同源 _cache_dir()）。"""
    if CF.CACHE != cache or CF._pool is not None:
        CF.CACHE = cache
        CF._pool = CF._bull = CF._idxv = None


def _fd_trim_intraday(pool):
    """_OPS5（WO-DECBAR 判定轮口径承继）：剔除数据尾日≥运行日的未收盘盘中 bar，
    只用最后完整日收盘数据扫描。返回剔除 bar 数（登记用）。"""
    today = time.strftime('%Y-%m-%d', time.gmtime())
    n = 0
    for bars in pool.values():
        while bars and bars[-1]['time'] >= today:
            bars.pop()
            n += 1
    return n


def s5_scan_pool(FR, CF, arms=('ctrl', 'DA'), settled_only=False):
    """全池两臂扫描（fd_revive_run._w_main 逐字经 Pool(32)，R8 并行铁律；
    DB 不入 S5——§5-2 禁第三方向）。settled_only（_OPS6）：影子前瞻只保留两臂
    出场均已发生的信号（why≠数据末），持仓中不入计数。"""
    from multiprocessing import get_context
    jobs = [(arm, tk) for arm in arms for tk in sorted(CF.pool_bull()[0])]
    out = {a: [] for a in arms}
    with get_context('fork').Pool(32) as p:
        for arm, tk, lst in p.map(FR._w_main, jobs, chunksize=4):
            out[arm].extend(lst)
    if settled_only:
        out = {a: [t for t in lst if t['why'] != '数据末'] for a, lst in out.items()}
    return out


def s5_d0(FR, CF):
    """S5 D0（工单件⑥ S5 腿）：S5 采集机器逐字复放 realA 配对段（冻结副本，
    窗=CF.MAIN..CF.TRUNC）vs fd_revive_result.json results.DA.legs.J1 逐位 diff=0
    （n_paired/pair_rate/mean/sum_r 四位）。任一 MISS 即停工（batch 谱系条款）。"""
    if not (os.path.isdir(FD_FRESH_CACHE) and os.listdir(FD_FRESH_CACHE)):
        raise SystemExit('shadow S5 D0: 冻结快照内容副本 /tmp/box_cache_fresh 缺失——'
                         '停工重锚（禁以 live 数据代跑 D0，_OPS7）')
    _fd_load_cache(CF, FD_FRESH_CACHE)
    arms = s5_scan_pool(FR, CF, settled_only=False)
    ref = json.load(open(FD_RESULT_F))['results']['DA']['legs']['J1']
    dA, pA = FR.pair_stats(arms['ctrl'], arms['DA'], CF.MAIN, CF.TRUNC)
    sA = FR.delta_summary(dA)
    got = {'n_paired': pA['n_paired'], 'pair_rate': pA['pair_rate'],
           'mean': sA['mean'], 'sum_r': sA['sum_r']}
    want = {'n_paired': ref['realA']['n_paired'], 'pair_rate': ref['realA']['pair_rate'],
            'mean': ref['delta']['mean'], 'sum_r': ref['delta']['sum_r']}
    diff = {k: round(got[k] - want[k], 10) for k in got}
    hit = all(v == 0.0 for v in diff.values())
    out = {'name': 's5_realA_replay_diff0', 'window': [CF.MAIN, CF.TRUNC],
           'lineage': ('S5 机器=fd_revive_run.py 逐字复用（scan_fd_exit 入场零改动+'
                       '_fd_exit_fns D-A/ctrl 出场逐字+pair_stats/delta_summary 逐字）；'
                       '数据=冻结快照内容副本 /tmp/box_cache_fresh'),
           'got': got, 'want': want, 'diff': diff,
           'verdict': 'hit' if hit else 'MISS', 'ran_at': time.strftime('%F %T')}
    print(f"shadow S5 D0: {out['verdict']}（realA 复放 got={got} vs result.json want={want}）")
    return out


def _s5_next_quarter(dstr):
    """复活路径(a)：下一自然季首日（判死后季度滚动复判窗起点）。"""
    y, m = int(dstr[:4]), int(dstr[5:7])
    qm = ((m - 1) // 3) * 3 + 4                     # 下一季首月（4/7/10，跨年进 1）
    if qm > 12:
        y, qm = y + 1, 1
    return f'{y:04d}-{qm:02d}-01'


def s5_load_rows():
    if not os.path.exists(FD_DAYS_F):
        return []
    out = []
    with open(FD_DAYS_F) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def s5_collect(state):
    """S5=fd-da 每日旁路采集（终裁 2026-10-20 授权）：live 数据态 + _OPS5 盘中剔除 +
    _OPS6 已平仓过滤，前瞻窗 S5_FW 起同信号 (tkr,et) 配对 ΔR 逐笔落
    fd_revive_days.jsonl（比照 SH-3）；J5 冻结判线 n≥20 Δ meanR>0 一次封印；
    状态落 fd_revive_state.json（n 计数/sealed/季度复判时间戳，比照 SH-3）。"""
    FR, CF = _fd_eng()
    g = state['cells'].setdefault('S5', {'status': 'ACCUMULATING', 'sealed': False})
    if g.get('sealed'):
        print('shadow S5: 已封印（判读一次，禁重复判读）——只登记不采集')
        return
    # D0 首跑（不过即停工）
    if g.get('d0', {}).get('verdict') != 'hit':
        g['d0'] = s5_d0(FR, CF)
        if g['d0']['verdict'] != 'hit':
            raise SystemExit('shadow S5 D0 MISS——停工（禁带病出数，batch 谱系条款）')
    # 前瞻采集（live 唯一数据态）
    _fd_load_cache(CF, _cache_dir())
    pool, bull, _ = CF.pool_bull()
    trimmed = _fd_trim_intraday(pool)
    arms = s5_scan_pool(FR, CF, settled_only=True)
    c = {(t['tkr'], t['et']): t for t in arms['ctrl'] if t['et'] >= S5_FW}
    a = {(t['tkr'], t['et']): t for t in arms['DA'] if t['et'] >= S5_FW}
    done = {(r['tkr'], r['et']) for r in s5_load_rows()}
    new_rows = []
    for k in sorted(c.keys() & a.keys()):
        if k in done:
            continue
        new_rows.append({'cell': 'S5', 'tkr': k[0], 'et': k[1],
                         'r_da': round(a[k]['r'], 4), 'r_ctrl': round(c[k]['r'], 4),
                         'delta': round(a[k]['r'] - c[k]['r'], 4),
                         'why_da': a[k]['why'], 'why_ctrl': c[k]['why'],
                         'collected_at': time.strftime('%F %T')})
    if new_rows:
        with open(FD_DAYS_F, 'a') as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    rows = s5_load_rows()
    deltas = [r['delta'] for r in rows]
    n = len(deltas)
    mean = round(sum(deltas) / n, 4) if n else None
    g.update({'n': n, 'delta_mean': mean,
              'new_rows_this_run': len(new_rows),
              'intraday_trimmed_bars': trimmed,
              'last_scan_tail': max((bars[-1]['time'] for bars in pool.values() if bars),
                                    default=None)})
    # J5 冻结判线：n≥20 配对 Δ meanR>0 → 一次封印（n<20 只累计不判，SH-6 同款）
    if n >= S5_N_LINE:
        verdict = 'PASS' if mean > 0 else 'FAIL'
        note = ('J5 达标：n≥20 配对前瞻 Δ meanR>0（影子候选终审资格；影子达标≠放行，R10）'
                if verdict == 'PASS' else
                'J5 判死：n≥20 配对前瞻 Δ meanR≤0（维持 fd 原判死结论；复活路径(a)=同判线'
                '机械复判每自然季至多一次，或(b)=用户批准 v2 新预注册）')
        readout = {'readout_at': time.strftime('%F %T'), 'cell': 'S5',
                   'cell_id': 'FD|K5-fd-exit-partial3r-breakeven vs K5-fd-exit-ctrl|同信号配对|fd-da',
                   'judgment_basis': 'FD_REVIVE_SPEC_v1 §4 J5（数字冻结）+ 交易分析团队终裁 2026-10-20',
                   'window_from': S5_FW, 'n_paired': n, 'delta_meanR': mean,
                   'r10_note': '影子读数不回写部署姿态（R10）；达标≠放行',
                   'verdict': verdict, 'verdict_note': note,
                   'seal': {'sealed': True, 'rule': '判读一次封印，禁重复判读'}}
        with open(os.path.join(STATEDIR, f"fd_revive_readout_S5_{readout['readout_at'][:10]}.json"),
                  'w') as f:
            json.dump(readout, f, ensure_ascii=False, indent=1)
        g.update({'sealed': True, 'sealed_at': readout['readout_at'], 'verdict': verdict,
                  'last_readout': readout})
        if verdict == 'FAIL':                       # 复活路径(a)季度复判窗登记（≤1/季）
            g['rejudge_next_from'] = _s5_next_quarter(readout['readout_at'][:10])
        print(f"[SHADOW-S5] 判读封印：{verdict}（{note}）")
    else:
        print(f"shadow S5: ACCUMULATING n={n}/{S5_N_LINE}（本轮新增 {len(new_rows)}，"
              f"盘中剔除 bar {trimmed}）——n<20 只累计不判（SH-6 同款）")
    s5_write_fd_state(state)


def s5_write_fd_state(state):
    """施工登记项 f1/fd_revive_state.json（终裁要求，比照 SH-3）：n 计数/sealed/
    季度复判时间戳字段；运行产物不入库（云端轮回传）。"""
    g = state['cells'].get('S5', {})
    fs = {'protocol': 'FD_REVIVE_SPEC_v1 §4 J5（数字冻结）+ 交易分析团队终裁 2026-10-20'
                       '（影子挂接授权，S5 格判线承继 J5 冻结数字）',
          'cell': 'S5=fd-da（K5-fd-exit-partial3r-breakeven vs K5-fd-exit-ctrl 同信号配对 ΔR）',
          'lineage': {'collector': 'research/wo_mine/shadow_cells.py s5_*（fd_revive_run.py 逐字复用，_OPS5/6/7）',
                      'hook': 'engine_f1/f1_signal.py + f1/f1_signal.py 判定轮/快照轮 --auto subprocess 旁路（异常不阻断）'},
          'window_from': S5_FW,
          'n': g.get('n', 0), 'n_line': S5_N_LINE,
          'delta_mean': g.get('delta_mean'),
          'sealed': bool(g.get('sealed')), 'verdict': g.get('verdict'),
          'sealed_at': g.get('sealed_at'),
          'rejudge': {'rule': '判死后复活路径(a)：影子窗样本自然滚动，同判线机械复判，每自然季至多一次',
                      'max_per_quarter': 1,
                      'last_rejudge_at': g.get('rejudge_last_at'),
                      'next_window_from': g.get('rejudge_next_from')},
          'd0': g.get('d0'),
          'r10_note': '影子读数不回写部署姿态（R10）；影子达标≠放行，放行仍走部署三道门+新预注册',
          'updated_at': time.strftime('%F %T')}
    json.dump(fs, open(FD_STATE_F, 'w'), ensure_ascii=False, indent=1)


# ------------------------------------------------------------- 主入口
def run(auto=False, d0_only=False):
    os.makedirs(STATEDIR, exist_ok=True)
    if os.path.exists(STATE_F):
        state = json.load(open(STATE_F))
    else:
        state = {'state': 'ACCUMULATING', 'created_at': time.strftime('%F %T'),
                 'protocol': 'SHADOW_SPEC_v1（2026-10-20 预注册冻结；SH-1..SH-6+§3 判线+§4 补样）',
                 'window_from': FW0, 'round_asof': None,
                 'cells': {**{cid: {'status': 'ACCUMULATING', 'sealed': False}
                              for cid in ATLAS_ANCHORS},
                           'S4': {'gate_state': 'SUSPENDED', 'sealed': False,
                                  'status': 'SUSPENDED（§4 补样未达门）'},
                           'S5': {'status': 'ACCUMULATING', 'sealed': False}}}
    # 上面一行防呆占位删除——S4 格初始化见下
    state['cells'].setdefault('S4', {'gate_state': 'SUSPENDED', 'sealed': False,
                                     'status': 'SUSPENDED（§4 补样未达门）'})
    state['cells'].setdefault('S5', {'status': 'ACCUMULATING', 'sealed': False})
    if state.get('state') == 'SEALED_ALL':
        print(f"shadow_cells: 全格已封印，退出")
        return state
    MC, B1, B2 = _eng()
    if not state.get('d0', {}).get('all_pass'):
        d0_check(MC, B1, B2, state)          # 工单件⑥：首跑过锚，不过即停工
        with open(STATE_F, 'w') as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        if not state['d0']['all_pass']:
            raise SystemExit('shadow D0 校验 MISS——停工（batch 谱系停工条款，禁带病出数）')
        if d0_only:
            return state
    state['round_asof'] = _round_asof()
    # S4 补样状态机（suspended 期不采集不判读）
    s4_collect(state)
    # S1-S3 采集 + 判读
    counts = collect_factor_cells(state)
    for cid in ATLAS_ANCHORS:
        g = state['cells'][cid]
        if g.get('sealed'):
            continue
        days = [d for d in load_days() if d['cell'] == cid]
        action, det = judge_factor_cell(cid, days)
        g['accumulation'] = det
        g['new_rows_this_run'] = counts[cid]
        if action == 'READOUT':
            do_factor_readout(cid, det, state)
        else:
            print(f"shadow {cid}: ACCUMULATING {det['n_days']}/{MIN_READOUT_DAYS}"
                  f"（本轮新增 {counts[cid]}）——数据不足，不判读只累计（SH-6）")
    # S5=fd-da（FD_REVIVE_SPEC_v1 §4 J5 + 终裁 2026-10-20 影子挂接授权）：
    # 旁路采集异常不阻断 S1-S4 既有格（SH-1 同款旁路纪律）；D0 MISS 属停工条款不吞
    try:
        s5_collect(state)
    except SystemExit:
        raise
    except Exception as _s5e:
        print(f'shadow S5 采集异常（不阻断）: {_s5e}')
    sealed = [c for c, g in state['cells'].items() if g.get('sealed')]
    state['state'] = 'SEALED_ALL' if len(sealed) == len(state['cells']) else 'ACCUMULATING'  # S5 并入=5 格
    state['updated_at'] = time.strftime('%F %T')
    with open(STATE_F, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print(f"shadow_cells: 状态={state['state']} 已封印格={sealed or '无'}")
    return state


if __name__ == '__main__':
    run(auto='--auto' in sys.argv, d0_only='--d0' in sys.argv)
