#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enhance_discount.py — 分域增强插件层·折扣计算器（DEPLOY_SPEC_v1 §2/§3.1 照抄施工件）
================================================================================
【唯一依据】research/wo_mine/DEPLOY_SPEC_v1.md（2026-10-21 预注册冻结，首席策略官
·何执舟终裁批准）。本件=§3.1-② 新增·折扣计算器：输入=影子 state 文件；逻辑=§2.2
档位表查表（纯映射，零新判线）；输出=f1/enhancement_state.json（运行产物不入库，
云端轮回传，比照 fd_revive_state 先例）。

【架构定性（§0/§2.4，逐字承继）】本层=F1 之外的增强插件层（independent add-on），
不是 F1 内部权重；折扣分母=账户总权益，独立于 F1 的 12.5% 敞口，两层数学不相加进
任何熔断阈值计算；本件只读影子产物与 f1_live.json 血缘字段，绝不回写 F1 任何
参数/仓位/榜单（R10）。

【数据流（§3.1）】
① 采集（已有，零改动）：shadow_cells.py --auto 产 f1/shadow_state.json +
   f1/shadow_reg_S{1,2,3}.jsonl（S1-S4）、f1/fd_revive_state.json +
   f1/fd_revive_days.jsonl（S5）。
② 本件：查表折扣 → f1/enhancement_state.json。
③ 渲染并入：f1_generate.py 若存在 enhancement_state.json 则并入
   f1_live.json → meta.enhancement（无该文件时=null，页面显示「增强层未上线」）。
④ 页面 index.html 读 meta.enhancement 渲染 §3.2 区块。

【判线承继（零新判线）】SHADOW_SPEC_v1 §3（IC>0 ∧ t≥2 ∧ 命中率≥60%；早死
n≥10 ∧ t≤−2 ∧ IC<0；S4 事件腿 avoid>0 ∧ mdd_red≥10% ∧ lag 不翻转）+
FD_REVIVE_SPEC_v1 §4 J5（n≥20 配对 Δ meanR>0）。数字全部冻结逐字承继。

【挂接】判定轮/快照轮 f1_signal.py shadow_cells 旁路之后追加本件 --auto（同款
subprocess 模式，异常不阻断，学 SH-1 先例）。

【资金费降级（DEPLOY_SPEC §1/§3.1，工单件⑤）】S1-S3 IC 读数与 S5 Δ meanR 判定
管线中不存在资金费前置过滤步骤（本件施工时逐一核验：xsec_ic_series /
fd_revive_run 判定路径零资金费引用）——降级=事实确认+事后常数披露：本件落盘携带
fee_note 逐字；F1 引擎 f1_signal.py 费常数 0.03%/bar 一行不动（主引擎口径归台账管）。

【安全侧默认（§5-⑦）】输入缺失/轮次失败 → fail_streak 累计；连续 5 轮失败自动
全部降 T0 并冻结开新仓（安全侧默认）。升档（T3→T2 复审重读）须季度复审窗+终裁
确认，本件不做任何升档动作（降档只减仓不加仓，查表自动）。

用法：python3 research/wo_mine/enhance_discount.py [--auto]
产出：f1/enhancement_state.json
字段：{generated, asof, cells:{S1..S5:{tier, coef, n_days, sealed, status, ...}},
       linkage:{f1_gate, f1_breaker_light, enhanced_frozen}, ...}
"""
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))          # research/wo_mine
ROOT = os.environ.get('SHADOW_REPO_ROOT') or \
    os.path.dirname(os.path.dirname(_HERE))                 # 仓库根（__file__ 相对，禁绝对路径）
STATEDIR = os.path.join(ROOT, 'f1')
SHADOW_STATE_F = os.path.join(STATEDIR, 'shadow_state.json')
FD_STATE_F = os.path.join(STATEDIR, 'fd_revive_state.json')
FD_DAYS_F = os.path.join(STATEDIR, 'fd_revive_days.jsonl')
ROUND_F = os.path.join(STATEDIR, 'f1_live.json')            # 判定轮产物（血缘只读）
OUT_F = os.path.join(STATEDIR, 'enhancement_state.json')    # 运行产物不入库（云端轮回传）

# ---- 档位表（DEPLOY_SPEC_v1 §2.2 批准即冻结；数字=新增预注册 25/50/100/0）----
TIER_TABLE_VERSION = 'DEPLOY_SPEC_v1 §2.2（2026-10-21 预注册冻结）'
JUDGMENT_BASIS = ('SHADOW_SPEC_v1 §3（数字冻结：IC>0 ∧ t≥2 ∧ 命中率≥60%；早死 '
                  'n≥10 ∧ t≤−2 ∧ IC<0；S4 事件腿 avoid>0 ∧ mdd_red≥10% ∧ lag 不翻转）'
                  '+ FD_REVIVE_SPEC_v1 §4 J5（n≥20 配对 Δ meanR>0）——零新判线')
TIERS = {   # 档 → (档位名, 系数%)（§2.2 逐字）
    'T0': ('观察档', 25),
    'T1': ('试运行档', 50),
    'T2': ('转正档', 100),
    'T3': ('降档', 25),
    'T4': ('下线', 0),
}
SINGLE_POOL_CAP = 50        # §2.2 单池封顶注：S1-S3 T2 上限按 50% 执行（=T1 系数封顶）
BASELINE_PCT = 0.5          # §2.1 增强基线仓位（每格 0.5%，冻结）
TOTAL_CAP_PCT = 2.0         # §2.1 增强层总敞口上限 2.0%
FEE_NOTE = '资金费=背景常数 0.03%/bar 仅事后披露，不参与判定'   # §3.1 逐字
SAFE_STREAK_LINE = 5        # §5-⑦ 连续 5 轮失败自动全部降 T0 并冻结开新仓
CARD_ORDER = ['S1', 'S2', 'S3', 'S5', 'S4']    # §3.2 排序：S4 灰态垫底
SINGLE_POOL_CELLS = {'S1', 'S2', 'S3'}         # §2.2 单池格
CELL_META = {   # §1 格子卡登记表（名称/域，供页面五字段渲染；域标签=ATLAS D1 口径零改动）
    'S1': {'name': 'S1 反转', 'variant': 'Q3-rev-liq', 'domain': '弱躁', 'pool': 'full144 单池'},
    'S2': {'name': 'S2 反转粗筛', 'variant': 'Q3-rev-5', 'domain': '弱躁', 'pool': 'full144 单池'},
    'S3': {'name': 'S3 突破回踩', 'variant': 'Q1-brk-pos-20', 'domain': '牛躁', 'pool': 'full144 单池'},
    'S4': {'name': 'S4 高波停门', 'variant': 'K1-d-gate-vol20p80-pause', 'domain': '弱稳', 'pool': 'full144（old131 补样中）'},
    'S5': {'name': 'S5 fd 出场增强', 'variant': 'K5-fd-exit-partial3r-breakeven', 'domain': '全域', 'pool': 'fd 池配对'},
}


def _round_asof():
    """判定轮产物血缘（只读，比照 shadow_cells._round_asof）：f1/f1_live.json 的 signal.asof。"""
    try:
        with open(ROUND_F) as f:
            d = json.load(f)
        return d.get('signal', {}).get('asof') or d.get('meta', {}).get('asof')
    except Exception:
        return None


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _load_jsonl(path):
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except Exception:
        return []


# ------------------------------------------------------------- 查表（§2.2 纯映射）
def tier_factor_cell(n, ic_mean, ic_t, hit_rate, sealed, verdict):
    """S1-S3 因子格档位查表（§2.2，判线数字全部承继 SHADOW_SPEC_v1 §3 冻结值）。
    返回 (tier, note)。已封印格=终审档位固定（§5-⑤：达标→T2（单池封顶 50%）、
    命中率弱→T3、判死→T4；NOT_PASS=三腿未全过非失败路径，归 T3 下一复审窗重读）。"""
    if sealed:
        if verdict == 'PASS':
            return 'T2', 'n≥20 三腿达标（单池证据·T2 系数封顶 50%）'
        if verdict == 'FAIL':
            return 'T4', '判读封印：判死（§3 失败路径）'
        return 'T3', '判读封印：未达标（三腿未全过，下一复审窗季度重读）'
    # 未封印：n≥10 早死线（SH-5 冻结）→ T4
    if n >= 10 and ic_mean is not None and ic_mean < 0 \
            and ic_t is not None and ic_t <= -2.0:
        return 'T4', '早死线触发（n≥10 ∧ t≤−2 ∧ IC<0）——仓位归零下线'
    if n >= 20:
        # 防御分支：n≥20 未封印（正常应已由 shadow_cells 判读封印）——同表查档不判读
        if ic_mean is not None and ic_mean < 0:
            return 'T4', 'n≥20 IC<0（判死线，待 shadow_cells 判读封印）'
        if ic_mean is not None and ic_mean > 0 and ic_t is not None and ic_t >= 2.0:
            if hit_rate is not None and hit_rate >= 0.60:
                return 'T2', 'n≥20 三腿达标（待封印；单池封顶 50%）'
            return 'T3', 'n≥20 主腿过、命中率<60%（待封印；下一复审窗重读）'
        return 'T3', 'n≥20 三腿未全过（待封印；下一复审窗重读）'
    if n >= 10:
        return 'T1', 'n≥10 且早死判据未触发'
    return 'T0', '登记即部署起点（n<10）'


def tier_s5_cell(n, delta_mean, sealed, verdict):
    """S5=fd-da 格档位查表（§2.2，判线=J5 冻结：n≥20 配对 Δ meanR>0；n<20 只累计
    不判——S5 无 n≥10 早死条款，判死仅 n≥20 Δ≤0，方法书未定义处不自行新增）。"""
    if sealed:
        if verdict == 'PASS':
            return 'T2', 'n≥20 配对 Δ meanR>0（J5 达标；全域格无单池封顶）'
        return 'T4', '判读封印：判死（J5：n≥20 Δ meanR≤0）'
    if n >= 20:
        if delta_mean is not None and delta_mean > 0:
            return 'T2', 'n≥20 Δ meanR>0（待封印）'
        return 'T4', 'n≥20 Δ meanR≤0（判死线，待 shadow_cells 判读封印）'
    if n >= 10:
        return 'T1', 'n≥10（J5 判读线 n≥20 未至，只累计不判）'
    return 'T0', '登记即部署起点（n<10）'


def tier_s4_cell(g):
    """S4 专属（§2.2 注）：SUSPENDED 期=灰态不部署（不占用仓位）；ACTIVE 后按
    事件格判线走同表（事件≥3 次判读）。gate_state 未知=安全侧灰态不部署。"""
    gs = g.get('gate_state')
    if gs == 'SUSPENDED' or gs is None \
            or (not g.get('sealed') and g.get('status', '').startswith('SUSPENDED')):
        return None, 0, 'SUSPENDED（补样未达 60 日门，未部署·仅展示）', False
    if g.get('sealed'):
        v = g.get('verdict')
        if v == 'PASS':
            return 'T2', 100, '判读封印：事件三腿达标 ∧ 双池同向', True
        if v == 'FAIL':
            return 'T4', 0, '判读封印：事件腿翻转（§3 失败路径）', True
        return 'T3', 25, '判读封印：未达标（下一复审窗重读）', True
    rep = g.get('replenish', {})
    return 'T0', 25, (f"ACTIVE（old131 补样 {rep.get('fw_old131_weak_days', 0)}/4 达门，"
                      "事件<3 次只累计不判）"), True


# ------------------------------------------------------------- 组装
def build_s5_realtime(fd_state, fd_days, n5):
    """S5 实时信号状态行（UX_REPORT §G-1 逐字文案，工单 B-01；数据源=fd_revive_state/
    fd_revive_days 现有字段，缺事件行=无出场事件兜底）。判线/出场规则零新增：
    文案只如实转述，1/3 分批止盈+余仓保本=K5-fd-exit-partial3r-breakeven 登记口径。"""
    try:
        nline = int((fd_state or {}).get('n_line', 20) or 20)
    except Exception:
        nline = 20
    events = [r for r in (fd_days or [])
              if r.get('type') not in ('reg_day', None)
              and (r.get('tkr') or r.get('sym') or r.get('symbol'))]
    if events:
        last = events[-1]
        tkr = last.get('tkr') or last.get('sym') or last.get('symbol') or '—'
        return {'has_event': True, 'date': last.get('date'),
                'text': f'S5 出场信号：{tkr} 已按 1/3 分批止盈+余仓保本执行（增强层内，不动 F1）'}
    return {'has_event': False, 'date': None,
            'text': f'S5 今日实时信号：无出场事件（配对累计 n={n5}/{nline}）'}


def build_cells(shadow, fd_state, fd_days):
    """五格折扣状态（§3.1 字段：tier/coef/n_days/sealed/status + 页面五字段渲染
    所需的 name/domain/domain_active/verdict/deployed）。"""
    cells = {}
    sc = (shadow or {}).get('cells', {})
    # S1-S3：档位查表 + 域状态（当日登记行域标签 vs 本格域——ATLAS D1 口径零改动）
    for cid in ('S1', 'S2', 'S3'):
        meta = CELL_META[cid]
        g = sc.get(cid) or {}
        accum = g.get('accumulation') or {}
        n = accum.get('n_days') or 0
        tier, tnote = tier_factor_cell(n, accum.get('ic_mean'), accum.get('ic_t'),
                                       accum.get('hit_rate'), bool(g.get('sealed')),
                                       g.get('verdict'))
        coef = TIERS[tier][1]
        if tier == 'T2' and cid in SINGLE_POOL_CELLS:
            coef = min(coef, SINGLE_POOL_CAP)   # §2.2 单池封顶注：T2 上限按 50% 执行
        # 域状态：最新当日登记行（shadow_reg_S*.jsonl 现有字段 domain_label/cell_domain）
        regs = _load_jsonl(os.path.join(STATEDIR, f'shadow_reg_{cid}.jsonl')) or []
        last = regs[-1] if regs else {}
        domain_active = bool(last) and last.get('domain_label') == meta['domain']
        cells[cid] = {
            'tier': tier, 'tier_name': TIERS[tier][0], 'coef': coef,
            'n_days': n, 'n_registered': g.get('n_registered', len(regs)),
            'sealed': bool(g.get('sealed')), 'verdict': g.get('verdict'),
            'status': f"{TIERS[tier][0]}（{tnote}）",
            'name': meta['name'], 'variant': meta['variant'], 'domain': meta['domain'],
            'pool': meta['pool'], 'domain_active': domain_active,
            'deployed': True, 'tier_note': tnote,
            'pos_pct': round(BASELINE_PCT * coef / 100, 3),   # B-01 实际仓位金额
        }
    # S5：fd_revive_state.json（n_matured=J5 判读单位）+ fd_revive_days.jsonl 登记计数
    meta = CELL_META['S5']
    g5 = (fd_state or {}) if fd_state else (sc.get('S5') or {})
    n5 = g5.get('n_matured', g5.get('n', 0)) or 0
    tier, tnote = tier_s5_cell(n5, g5.get('delta_mean'), bool(g5.get('sealed')),
                               g5.get('verdict'))
    regs5 = [r for r in (fd_days or []) if r.get('type') == 'reg_day']
    cells['S5'] = {
        'tier': tier, 'tier_name': TIERS[tier][0], 'coef': TIERS[tier][1],
        'n_days': n5, 'n_registered': g5.get('n_registered', len(regs5)),
        'sealed': bool(g5.get('sealed')), 'verdict': g5.get('verdict'),
        'status': f"{TIERS[tier][0]}（{tnote}）",
        'name': meta['name'], 'variant': meta['variant'], 'domain': meta['domain'],
        'pool': meta['pool'], 'domain_active': True,   # 全域格（出场叠加）
        'deployed': True, 'tier_note': tnote,
        'pos_pct': round(BASELINE_PCT * TIERS[tier][1] / 100, 3),   # B-01 实际仓位金额
        # B-01：S5 实时信号状态行 + T2 满额白话（UX_REPORT §G-1/§G-3 逐字文案）
        'realtime': build_s5_realtime(fd_state, fd_days, n5),
        'full_note': '本格满额=转正档 100%（0.5% 全额）；与 S1-S3 单池格封顶 50% 不同',
    }
    # S4：灰态垫底（§3.2 排序）
    meta = CELL_META['S4']
    g4 = sc.get('S4') or {}
    tier4, coef4, status4, deployed4 = tier_s4_cell(g4)
    rep = g4.get('replenish') or {}
    cells['S4'] = {
        'tier': tier4, 'tier_name': TIERS[tier4][0] if tier4 else None,
        'coef': coef4,
        'n_days': (56 + rep.get('fw_old131_weak_days', 0))
                  if rep else None,   # old131 n_days=56+补样（ATLAS 冻结基线）
        'n_need': 60,
        'sealed': bool(g4.get('sealed')), 'verdict': g4.get('verdict'),
        'status': status4,
        'name': meta['name'], 'variant': meta['variant'], 'domain': meta['domain'],
        'pool': meta['pool'], 'domain_active': False,
        'deployed': deployed4,
        'replenish_need': rep.get('need', 4),
        'replenish_have': rep.get('fw_old131_weak_days', 0),
    }
    return cells


def build_linkage(live):
    """三条单向让位（§2.5）：F1 regime 闸关 → 冻结开新仓；F1 overall=red → 整体
    冻结；CB2 冻结期不连带冻结（§2.5-4，增强层风险自含）。单向让位：增强层状态
    永不反向影响 F1。"""
    sig = (live or {}).get('signal') or {}
    gate = sig.get('gate') or {}
    bk = ((live or {}).get('breakers') or {}).get('overall') or {}
    f1_gate = 'closed' if gate.get('on_holdcash') else 'open'
    light = bk.get('light') or 'unknown'
    frozen = bool(gate.get('on_holdcash') or light == 'red')
    return {'f1_gate': f1_gate, 'f1_breaker_light': light, 'enhanced_frozen': frozen,
            'rule': 'DEPLOY_SPEC_v1 §2.5 三条单向让位（闸关→冻结开新仓；红灯→整体冻结；'
                    'CB2 冻结不连带——增强层独立小止损与 T 档自降级，风险自含）；增强层永不反向影响 F1'}


def apply_safe_default(cells, frozen):
    """§5-⑦ 安全侧默认：连续 5 轮失败自动全部降 T0 并冻结开新仓。"""
    for cid, c in cells.items():
        if c.get('deployed'):
            c.update({'tier': 'T0', 'tier_name': TIERS['T0'][0], 'coef': TIERS['T0'][1],
                      'pos_pct': round(BASELINE_PCT * TIERS['T0'][1] / 100, 3),
                      'status': '安全侧默认（连续 5 轮输入失败，全部降 T0 并冻结开新仓；'
                                '档位冻结按旧值执行至管线恢复）'})
    return {'enhanced_frozen': True, 'safe_default': True, **({} if not frozen else {})}


def run(auto=False):
    prev = _load_json(OUT_F) or {}
    fail_streak = 0 if prev.get('inputs_ok') else int(prev.get('fail_streak', 0))
    shadow = _load_json(SHADOW_STATE_F)
    fd_state = _load_json(FD_STATE_F)
    fd_days = _load_jsonl(FD_DAYS_F)
    live = _load_json(ROUND_F)
    inputs_ok = bool(shadow and shadow.get('cells'))
    if not inputs_ok:
        fail_streak += 1
    else:
        fail_streak = 0
    safe = (not inputs_ok) and fail_streak >= SAFE_STREAK_LINE   # §5-⑦ 连续 5 轮失败
    cells = build_cells(shadow, fd_state, fd_days)
    linkage = build_linkage(live)
    if safe:
        apply_safe_default(cells, linkage.get('enhanced_frozen'))
        linkage['enhanced_frozen'] = True
    asof = _round_asof() or (shadow or {}).get('round_asof')
    out = {
        'generated': time.strftime('%F %T'),
        'asof': asof,
        'protocol': 'DEPLOY_SPEC_v1（分域增强插件层·影子折扣制；F1 外独立 add-on，R10 不回写）',
        'judgment_basis': JUDGMENT_BASIS,
        'tier_table_version': TIER_TABLE_VERSION,
        'fee_note': FEE_NOTE,
        'positioning': {'baseline_pct_per_cell': BASELINE_PCT,
                        'total_cap_pct': TOTAL_CAP_PCT,
                        'single_pool_cap_coef': SINGLE_POOL_CAP,
                        'denominator': '账户总权益（独立于 F1 的 12.5% 敞口；两层数学不相加进任何熔断阈值计算）'},
        'inputs_ok': inputs_ok,
        'fail_streak': fail_streak,
        'safe_default': bool(safe),
        'cells': {cid: cells[cid] for cid in CARD_ORDER},   # §3.2 排序 S1→S2→S3→S5→S4
        'linkage': linkage,
        'r10_note': '影子读数不回写 F1 主引擎任何参数/仓位/榜单（R10）；两引擎冲突时一律听 F1',
        'updated_at': time.strftime('%F %T'),
    }
    tmp = OUT_F + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_F)
    summary = ' '.join(f"{cid}:{c['tier'] or '灰'}{c['coef']}%" for cid, c in cells.items())
    print(f"enhance_discount: asof={asof} inputs_ok={inputs_ok} fail_streak={fail_streak} "
          f"frozen={linkage['enhanced_frozen']} | {summary} -> {os.path.relpath(OUT_F, ROOT)}")
    return out


if __name__ == '__main__':
    run(auto='--auto' in sys.argv)
