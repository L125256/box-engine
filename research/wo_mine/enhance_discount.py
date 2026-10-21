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
全部降 FROZEN 并冻结开新仓（安全侧默认，新制映射）。升档须季度复审窗+终裁
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

# ---- 档位表（新制映射：方法书 v1.1 §二·补遗 公式级定义照抄施工，裁定书
#      FINAL-VERDICT-FULLSCENE-v1 §二并入；判线数字仍承继 SHADOW_SPEC/J5 冻结值，零新判线）----
TIER_TABLE_VERSION = ('方法书 v1.1 §二·补遗（ACCEPT-BOOK-FULLSCENE-v1.1 · 裁定书 §二并入 · '
                      '用户授权 2026-10-21 20:10）')
JUDGMENT_BASIS = ('SHADOW_SPEC_v1 §3（数字冻结：IC>0 ∧ t≥2 ∧ 命中率≥60%；早死 '
                  'n≥10 ∧ t≤−2 ∧ IC<0；S4 事件腿 avoid>0 ∧ mdd_red≥10% ∧ lag 不翻转）'
                  '+ FD_REVIVE_SPEC_v1 §4 J5（n≥20 配对 Δ meanR>0）——零新判线'
                  '（新制下判线输出=执照复审数据源，不再直接定档）')
TIERS = {   # tier → (档位名, 系数%)（方法书 v1.1 §二·补遗 公式级定义，工程照抄）
    'FULL':      ('满额档', 100),   # S5 满额终裁（2026-10-21 16:08）生效；pos_pct=0.5%/格
    'POOL_CAP':  ('单池封顶', 50),   # S1-S3 单池满额封顶；pos_pct=0.25%/格
    'FROZEN':    ('冻结', 0),        # S4 灰态/域未激活/判死；pos_pct=0
    'OFFLINE':   ('下线', 0),        # 保留值：仅实盘劣化处置下线触发（DEPLOY_SPEC T4→PLAN #9）；
                                     # 部署态五格出现即异常态（方法书 A3-5）
}
SINGLE_POOL_CAP = 50        # §2.2 单池封顶注：S1-S3 满额封顶按 50% 执行（新制=POOL_CAP 系数本身）
BASELINE_PCT = 0.5          # §2.1 增强基线仓位（每格 0.5%，冻结）
TOTAL_CAP_PCT = 2.0         # §2.1 增强层总敞口上限 2.0%
FEE_NOTE = '资金费=背景常数 0.03%/bar 仅事后披露，不参与判定'   # §3.1 逐字
SAFE_STREAK_LINE = 5        # §5-⑦ 连续 5 轮失败自动全部降 FROZEN 并冻结开新仓
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


# ------------------------------------------------------------- 查表（新制映射 + 判线承继）
def tier_factor_cell(n, ic_mean, ic_t, hit_rate, sealed, verdict):
    """S1-S3 因子格档位（新制映射：方法书 v1.1 §二·补遗；判线数字全部承继
    SHADOW_SPEC_v1 §3 冻结值，作执照复审数据源）。返回 (tier, note)。
    新制：未封印观察/达标=POOL_CAP（单池满额封顶 50%）；判死（封印 FAIL/未达标封印/
    早死线/n≥20 IC<0）=FROZEN 0%；域未激活由 build_cells 归 FROZEN；OFFLINE 保留值
    不在此产生（部署态出现即异常态，方法书 A3-5）。"""
    if sealed:
        if verdict == 'PASS':
            return 'POOL_CAP', 'n≥20 三腿达标（单池证据·单池封顶 50%）'
        if verdict == 'FAIL':
            return 'FROZEN', '判读封印：判死（§3 失败路径）——仓位归零（FROZEN）'
        return 'FROZEN', '判读封印：未达标（三腿未全过，下一复审窗季度重读）——仓位归零（FROZEN）'
    # 未封印：n≥10 早死线（SH-5 冻结）→ FROZEN（判死）
    if n >= 10 and ic_mean is not None and ic_mean < 0 \
            and ic_t is not None and ic_t <= -2.0:
        return 'FROZEN', '早死线触发（n≥10 ∧ t≤−2 ∧ IC<0）判死——仓位归零（FROZEN）'
    if n >= 20:
        # 防御分支：n≥20 未封印（正常应已由 shadow_cells 判读封印）——同表查档不判读
        if ic_mean is not None and ic_mean < 0:
            return 'FROZEN', 'n≥20 IC<0 判死线（待 shadow_cells 判读封印）——仓位归零（FROZEN）'
        if ic_mean is not None and ic_mean > 0 and ic_t is not None and ic_t >= 2.0:
            if hit_rate is not None and hit_rate >= 0.60:
                return 'POOL_CAP', 'n≥20 三腿达标（待封印；单池封顶 50%）'
            return 'POOL_CAP', 'n≥20 主腿过、命中率<60%（待封印；下一复审窗重读）'
        return 'POOL_CAP', 'n≥20 三腿未全过（待封印；下一复审窗重读）'
    return 'POOL_CAP', '复审样本累计中（执照复审数据源；单池封顶 50%）'


def tier_s5_cell(n, delta_mean, sealed, verdict):
    """S5=fd-da 格档位（新制映射：方法书 v1.1 §二·补遗——tier(S5)=FULL 当且仅当
    S5 满额终裁（2026-10-21 16:08）生效；判线=J5 冻结：n≥20 配对 Δ meanR>0 作执照
    复审数据源，判死仅 n≥20 Δ≤0，方法书未定义处不自行新增）。"""
    if sealed:
        if verdict == 'PASS':
            return 'FULL', 'n≥20 配对 Δ meanR>0（J5 达标；满额终裁生效）'
        return 'FROZEN', '判读封印：判死（J5：n≥20 Δ meanR≤0）——仓位归零（FROZEN）'
    if n >= 20:
        if delta_mean is not None and delta_mean > 0:
            return 'FULL', 'n≥20 Δ meanR>0（待封印；满额终裁生效）'
        return 'FROZEN', 'n≥20 Δ meanR≤0 判死线（待 shadow_cells 判读封印）——仓位归零（FROZEN）'
    return 'FULL', 'S5 满额终裁（2026-10-21 16:08）生效；J5 判读线 n≥20 未至，n 只累计不判（执照复审数据源）'


def tier_s4_cell(g):
    """S4 专属（新制映射：方法书 v1.1 §二·补遗——tier(S4)=FROZEN（灰态）coef=0；
    域未激活=FROZEN）。SUSPENDED 期=灰态不部署（不占用仓位）；封印 PASS=FULL
    （事件格双池无单池封顶）；判死/未达标=FROZEN（新制无 25% 观察档，安全侧冻结，
    属设计推断待终裁回填）。gate_state 未知=安全侧灰态不部署。"""
    gs = g.get('gate_state')
    if gs == 'SUSPENDED' or gs is None \
            or (not g.get('sealed') and g.get('status', '').startswith('SUSPENDED')):
        return 'FROZEN', 0, 'SUSPENDED（补样未达 60 日门，灰态未部署·仅展示）', False
    if g.get('sealed'):
        v = g.get('verdict')
        if v == 'PASS':
            return 'FULL', 100, '判读封印：事件三腿达标 ∧ 双池同向', True
        if v == 'FAIL':
            return 'FROZEN', 0, '判读封印：事件腿翻转（§3 失败路径）——仓位归零（FROZEN）', True
        return 'FROZEN', 0, '判读封印：未达标（下一复审窗重读）——新制无观察档系数，安全侧冻结', True
    rep = g.get('replenish', {})
    return 'FROZEN', 0, (f"ACTIVE（old131 补样 {rep.get('fw_old131_weak_days', 0)}/4 达门，"
                         "事件<3 次只累计不判）——新制无观察档系数，安全侧冻结"), True


# ------------------------------------------------------------- 组装
def build_s5_realtime(fd_state, fd_days, n5):
    """S5 实时信号状态行（UX_REPORT §G-1 文案，工单 B-01；数据源=fd_revive_state/
    fd_revive_days 现有字段，缺事件行=无出场事件兜底）。判线/出场规则零新增：
    文案只如实转述，1/3 分批止盈+余仓保本=K5-fd-exit-partial3r-breakeven 登记口径。
    A4-6（方法书 v1.1 字面集）：页面渲染产物禁「n=X/20」模板——只报 n 值，判读线
    n≥20 由 n_days 字段承载（执照复审数据源，A0-5 机判不受影响）。"""
    events = [r for r in (fd_days or [])
              if r.get('type') not in ('reg_day', None)
              and (r.get('tkr') or r.get('sym') or r.get('symbol'))]
    if events:
        last = events[-1]
        tkr = last.get('tkr') or last.get('sym') or last.get('symbol') or '—'
        return {'has_event': True, 'date': last.get('date'),
                'text': f'【该动了】出场信号：{tkr}——按 S5 规则：先把这只票增强层小仓卖掉 1/3（分批止盈，落袋利润），'
                        f'剩余仓位把卖出线抬到买入成本价（保本卖，最差不亏本）。只动增强层小仓，F1 主仓完全不用动。'}
    return {'has_event': False, 'date': None,
            'text': f'S5 今日实时信号：无出场事件（配对累计 n={n5}）——今天增强层小仓不用做任何操作'}


def symbols_top_from_reg(reg, k=5):
    """本格标的行·数据源（整改 2026-10-21：用户立法准绳「重要信息页面肉眼可见」）。
    零新判线：只如实转述 shadow_reg 最新登记行已有的因子读数——因子值降序前 k 只。
    方向依据【设计推断，回测锚实证承继】：S1/S2 反转因子（-ret5）与 S3 位置因子
    （C/H20max-1）均为 IC>0 正向格（ATLAS 锚 IC 全正），因子值高=fwd5 期望收益高的
    多头侧候选。性质=参考读数（推导值），非买入指令，非 F1 榜单。"""
    f = (reg or {}).get('factor') or {}
    if not f:
        return []
    return [{'sym': s, 'val': v} for s, v in
            sorted(f.items(), key=lambda kv: kv[1], reverse=True)[:k]]


def build_cells(shadow, fd_state, fd_days):
    """五格折扣状态（§3.1 字段：tier/coef/n_days/sealed/status + 页面五字段渲染
    所需的 name/domain/domain_active/verdict/deployed）。整改 2026-10-21 追加
    symbols_* 字段：每格当前标的可见性（用户两连问之一「到底增强哪个标」）。"""
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
        # 域状态：最新当日登记行（shadow_reg_S*.jsonl 现有字段 domain_label/cell_domain）
        regs = _load_jsonl(os.path.join(STATEDIR, f'shadow_reg_{cid}.jsonl')) or []
        last = regs[-1] if regs else {}
        domain_active = bool(last) and last.get('domain_label') == meta['domain']
        if not domain_active:
            # 新制映射：域未激活=FROZEN（方法书 v1.1 §二·补遗）
            tier, coef, tnote = 'FROZEN', TIERS['FROZEN'][1], '域未激活=FROZEN（方法书 v1.1 §二·补遗）'
        else:
            coef = TIERS[tier][1]
        cells[cid] = {
            'tier': tier, 'tier_name': TIERS[tier][0], 'coef': coef,
            'n_days': n, 'n_registered': g.get('n_registered', len(regs)),
            'sealed': bool(g.get('sealed')), 'verdict': g.get('verdict'),
            'status': f"{TIERS[tier][0]}（{tnote}）",
            'name': meta['name'], 'variant': meta['variant'], 'domain': meta['domain'],
            'pool': meta['pool'], 'domain_active': domain_active,
            'deployed': True, 'tier_note': tnote,
            'pos_pct': round(BASELINE_PCT * coef / 100, 3),   # B-01 实际仓位金额
            # 整改 2026-10-21：本格标的可见行（零新判线，转述 shadow_reg 最新行）
            'symbols_scope': (f"{meta['pool']}·本行打分 {last.get('n_names', '—')} 只"
                              if (last or {}).get('factor')
                              else f"{meta['pool']}（暂无当日因子读数）"),
            'symbols_top': symbols_top_from_reg(last),
            'symbols_note': (f"因子记分牌格——不绑定单一标的：对池内 {last.get('n_names', '—')} 只逐日打分，"
                             f"分高者为多头侧候选（最新读数 {last.get('date', '—')}，参考·推导值·非指令）"
                             if (last or {}).get('factor')
                             else '因子记分牌格——暂无当日因子读数（数据源 shadow_reg_%s.jsonl）' % cid),
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
        'pos_pct': round(BASELINE_PCT * TIERS[tier][1] / 100, 3),   # B-01 实际仓位金额（新制：S5=0.5/格）
        # B-01：S5 实时信号状态行 + 满额白话（UX_REPORT §G-1/§G-3 文案，新制措辞）
        'realtime': build_s5_realtime(fd_state, fd_days, n5),
        'full_note': '本格满额=FULL 100%（0.5%/格）；与 S1-S3 单池封顶 50%（0.25%/格）不同'
                     '（白话：S5 这格买入最多用账户总资金的 0.5%，S1-S3 三格每格最多 0.25%）',
        # 整改 2026-10-21：S5 服务对象白话（用户问「S5 服务对象=哪些持仓」）
        'targets_note': '服务对象=增强层自己按 S5 规则买入的小仓（1/3 分批止盈+余仓保本只动这些仓）；'
                        '增强层当前处于信号登记观察期、尚未开通实际开仓执行（无增强层持仓记录）；'
                        'F1 主仓持仓不在本格服务范围（DEPLOY_SPEC §1：作用对象=增强层自己的仓，不动 F1 持仓）',
    }
    # S4：灰态垫底（§3.2 排序）
    meta = CELL_META['S4']
    g4 = sc.get('S4') or {}
    tier4, coef4, status4, deployed4 = tier_s4_cell(g4)
    rep = g4.get('replenish') or {}
    cells['S4'] = {
        'tier': tier4, 'tier_name': TIERS[tier4][0],
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
        # 整改 2026-10-21：S4=纪律格无标的对象
        'symbols_note': '纪律格——本格不买任何标的：它是「高波动日暂停开新仓」的换门规则，没有持仓对象',
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
    """§5-⑦ 安全侧默认：连续 5 轮失败自动全部降 FROZEN（新制映射，原 T0 观察档废除）
    并冻结开新仓。"""
    for cid, c in cells.items():
        if c.get('deployed'):
            c.update({'tier': 'FROZEN', 'tier_name': TIERS['FROZEN'][0],
                      'coef': TIERS['FROZEN'][1],
                      'pos_pct': round(BASELINE_PCT * TIERS['FROZEN'][1] / 100, 3),
                      'status': '安全侧默认（连续 5 轮输入失败，全部降 FROZEN 并冻结开新仓；'
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
        'protocol': 'DEPLOY_SPEC_v1（分域增强插件层·执照复审制·新制映射 v1.1 §二补遗；F1 外独立 add-on，R10 不回写）',
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
        'r10_note': '增强层读数不回写 F1 主引擎任何参数/仓位/榜单（R10）；两引擎冲突时一律听 F1',
        'updated_at': time.strftime('%F %T'),
    }
    tmp = OUT_F + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_F)
    _merge_into_live(out)
    summary = ' '.join(f"{cid}:{c['tier'] or '灰'}{c['coef']}%" for cid, c in cells.items())
    print(f"enhance_discount: asof={asof} inputs_ok={inputs_ok} fail_streak={fail_streak} "
          f"frozen={linkage['enhanced_frozen']} | {summary} -> {os.path.relpath(OUT_F, ROOT)}")
    return out


def _merge_into_live(state):
    """缓存免疫修复（2026-10-22）：本件写完 enhancement_state.json 后**立即**并入
    f1_live.json → meta.enhancement（f1_generate.merge_enhancement 同款逻辑原位内联，
    修时序缺口：旧链路只在 09:25 判定轮由 f1_generate 并入一次，本件 23:20 更新 state
    后 f1_live.json 无人回写 → 页面读 meta.enhancement 渲染旧制一整天）。
    R10 定性不变：meta.enhancement=渲染拼接字段（学 meta.breadth 先例），非 F1 参数/
    仓位/榜单；本件对 f1_live.json 只动 meta.enhancement 一个键，其余逐字节不动；
    容错不阻断（f1_live.json 缺失/坏 JSON 时跳过，判定轮 f1_generate 兜底再并入）。"""
    try:
        with open(ROUND_F) as f:
            live = json.load(f)
        live.setdefault('meta', {})['enhancement'] = state
        tmp = ROUND_F + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(live, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ROUND_F)
        print(f"enhance_discount: meta.enhancement 并入 {os.path.relpath(ROUND_F, ROOT)}")
    except Exception as _e:
        print(f"enhance_discount: meta.enhancement 并入跳过（不阻断）: {_e}")


if __name__ == '__main__':
    run(auto='--auto' in sys.argv)
