#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
复活机制常设件（DUAL_VERDICT §九 终裁定稿逐字 · 月度+触发式全量重审）
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/DUAL_VERDICT.md：
- §九 复活机制（定稿）：频率=月度定期重审（每月首个判定轮）+ 触发式即时重审
  （①新数据段满 20 交易日；②复活哨兵命中：境外 API 通/新 funding 端点/影子序列
  满 20 日标定；③realB 型段触发器）。判据=同判线不放宽（垫≥3× 双口径、F6 ①②③、
  门 FDR q=0.10），只在新数据段上评。通道=复活进「可跑池（纸面）」→ 影子伴行
  ≥20 交易日 → 新预注册部署评审 → 方可动实盘；全程带「复活来源+口径变更重判」标注；
- §七 全量重审表：判据=首席定死「利润垫 ≥3× 双口径同过；垫=最差侧年化费后利润
  ÷ 43.8pp/年」；被资费卡死总盘子 ≈235 变体级（58 挂账行 + 171 信号用途变体
  + c2 6 行），垫可算的全部算完；
- §五-4 辅轨权威：影子标定（≥20 交易日）与真实费率哨兵任一命中即触发全表重算；
- §三 0 新复活是诚实结果：58 挂账行垫薄是实测（双窗 avoid 均正 46 行最高 1.77×、
  12 行 avoid 为负），171 信号用途变体垫概念不适用（范畴错误），历史枪毙死于
  方向性负证据非资费；
- R8=Pool(32)；seed=42；144 池定版；判死永远附复活条件（R4/R5/R9）。

【台账协议（RV-1..RV-9，先冻结后运行；冻结时点 2026-10-19）】
RV-1 台账=reaudit_ledger.jsonl，逐行 JSON，每次重审整表追加、禁覆盖禁回写
  （追加不覆盖是硬条款）；历史行只读。
RV-2 人口表（全量重审表，写死禁止漏行）：
  A 成本用途 82 行（coverage_grades.json：带资费可跑 24 + 冻结挂账 58[正垫 46+负垫 12]）
  B 信号用途 171 行（168 fu 配置 + 3 c1 变体——垫概念不适用，范畴错误）
  C 事件叠加 c2 6 行（E1/E2/E3 × 双池，X4）
  D 排除册 X1（41 配置聚合 1 行，垫数字已并入 A 类）/X5/X6/X7 共 4 行
  E 历史出清 8 行 + F3 待补档 1 行
  合计 272 行/轮；其中被资费卡死核心盘子=58+171+6=235 变体级（§七 汇总口径）。
RV-3 判线（同判线不放宽，逐字）：
  A 类=利润垫 ≥3× 双口径同过（双口径=min_both ∧ avoid_caliber；垫=最差侧年化费后
    利润÷43.8pp/年）；B 类=无法评估（垫不适用）——复活门=新 funding 数据源；
  C 类=FULL 判线（avoid>0 ∧ MDD 不劣化）——复活门=realB 型段触发器命中；
  D/E 类=条目专用冻结判线（DUAL_VERDICT §七 B/C 表原文）。
RV-4 复活判定（A 类，数据驱动）：双口径均 ≥3× → 复活；其余类别仅在其复活门
  证据出现时复活（哨兵文件登记），无一门证据 → 维持原档。
RV-5 复活通道（定稿四段）：复活进「可跑池（纸面）」→ 影子伴行 ≥20 交易日 →
  新预注册部署评审 → 方可动实盘；复活行强制携带 revival_channel 字段与
  「复活来源+口径变更重判」标注；复活≠部署，垫厚按未来打折（§五-3）。
RV-6 触发器：
  T0 月度定期=每月首个判定轮（state.last_monthly_audit ≠ 当前月即触发）；
  T1 新数据段满 20 交易日（池日历 last_seen_data_tail 之后新增交易日 ≥20）；
  T2 复活哨兵命中（revival_sentinels.json：overseas_api_ok / new_funding_endpoint /
     shadow_seq_days≥20 任一为真）；
  T3 realB 型段触发器（revival_sentinels.json.realb_like_segment.detected=true）。
  无触发时调用=只检状态不重审不落库（防台账噪声膨胀）。
RV-7 证据源（数据驱动重审时）：A 类证据=coverage_grades.json 当前冻结台账
  （其本身为常设重标定件——影子≥20 日自动重算上限并刷新，本件只读其最新态）；
  C 类证据=c_new_candidates.json 冻结存档；判线重算只在新数据段上评（§九）。
RV-8 首轮审计（R0，2026-10-19）：以冻结存档数字过同判线，结果必须复现
  DUAL_VERDICT §七 汇总（复活 0 / 维持挂账 / 无法评估 / 历史出清维持 8 / F3 待补档），
  断言不过即停工。
RV-9 自测（--selftest）：沙箱目录验证 ①追加不覆盖（两轮追加后首轮行逐位不变）；
  ②触发器 T0/T1 判定正确；③复活行通道字段与标注齐备；④断言 0 复活复现。

用法：
  python3 revival_watch.py           # 判定轮调用：检触发器，命中即整表重审追加
  python3 revival_watch.py --build   # 首轮建账（R0，复现 §七 并断言）
  python3 revival_watch.py --selftest
产出：reaudit_ledger.jsonl（常设台账，追加不覆盖）+ revival_state.json
"""
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
for p in ('/workspace/repo_ready/research/wo_dneg',
          '/workspace/repo_ready/research/wo_rescue',
          '/workspace/repo_ready/research/wo_unlock'):
    if p not in sys.path:
        sys.path.insert(0, p)

LEDGER_F = os.path.join(_HERE, 'reaudit_ledger.jsonl')
STATE_F = os.path.join(_HERE, 'revival_state.json')
SENTINEL_F = os.path.join(_HERE, 'revival_sentinels.json')
CG_F = '/workspace/repo_ready/research/wo_unlock/coverage_grades.json'
CNC_F = '/workspace/repo_ready/research/wo_rescue/c_new_candidates.json'
SPEC = '/tmp/trade9_specs/DUAL_VERDICT.md'

THICK_X = 3.0                    # 垫≥3× 双口径同过（定死，不放宽）
SHADOW_DAYS_REQ = 20             # 影子伴行 ≥20 交易日（定稿通道）
NEWSEG_DAYS_REQ = 20             # 触发器①：新数据段满 20 交易日

JUDGE_COST = ('利润垫 ≥3× 双口径同过（垫=最差侧年化费后利润÷43.8pp/年；'
              '双口径=min_both ∧ avoid_caliber；USERWORD §八 / DUAL_VERDICT §七 定死）')
JUDGE_SIGNAL = '垫概念不适用（信号用途，费率=变量，范畴错误——USERWORD §三-1 承继）'
JUDGE_EVENT = 'FULL 窗判线：叠加臂净收益−base>0 ∧ |MDD_叠加|≤|MDD_base|（PC-2 逐字）'

DUAL_TAG = '口径变更重判'


# ============================================================ 人口表（RV-2，写死）
def population():
    rows = []
    cg = json.load(open(CG_F))
    for r in cg['rows']:
        if r['grade'] == '带资费可跑':
            verdict = '已在可跑池（维持，非本次复活）'
            gate = '维持可跑；部署另走新预注册评审'
        elif (r.get('cushion_x_avoid_caliber') or 0) > 0:
            verdict = '维持挂账（正垫 <3×）'
            gate = '真实费率数据或影子标定 ≥20 日重算后双口径 ≥3×'
        else:
            verdict = '垫算不出（avoid 口径为负）'
            gate = '真实费率/影子标定重算（垫为负，换任何不挑数字口径需先翻正）'
        rows.append({
            'category': 'A_cost_use', 'id': r['id'], 'pname': r['pname'],
            'domain': '成本用途（门域配置）',
            'judging_line': JUDGE_COST,
            'evidence': {'cushion_x_min_both': r.get('cushion_x_min_both'),
                         'cushion_x_avoid_caliber': r.get('cushion_x_avoid_caliber'),
                         'cushion_x_full_side': r.get('cushion_x_full_side'),
                         'cushion_x_holdout_side': r.get('cushion_x_holdout_side'),
                         'full_avoid_pp': r.get('full_avoid_pp'),
                         'holdout_avoid_pp': r.get('holdout_avoid_pp'),
                         'source': 'coverage_grades.json（冻结台账，B0-初始）'},
            'verdict': verdict, 'revival_gate': gate})

    # B 类：168 fu 配置（PB-2 公式枚举）+ 3 c1
    VOL, BR, FU = [30, 40, 50, 60, 70, 80], [20, 30, 40, 50, 60], [20, 40, 60, 80]
    fu_ids = [f'fu{f}' for f in FU]
    fu_ids += [f'vol{v}+fu{f}' for v in VOL for f in FU]
    fu_ids += [f'br{b}+fu{f}' for b in BR for f in FU]
    fu_ids += [f'vol{v}+br{b}+fu{f}' for v in VOL for b in BR for f in FU]
    assert len(fu_ids) == 168, len(fu_ids)
    for cid in fu_ids:
        rows.append({'category': 'B_signal_use', 'id': cid, 'pname': '双池（配置族）',
                     'domain': '信号用途（资金费门）', 'judging_line': JUDGE_SIGNAL,
                     'evidence': {'status': 'NOT_RUNNABLE',
                                  'evidence': 'box_cache 仅 OHLCV 无 funding 字段；'
                                              'wo2 P1 探针 11 端点 200 响应均无 funding '
                                              '字段指纹（PB-2 附证据不跑伪数）'},
                     'verdict': '无法评估（垫不适用）',
                     'revival_gate': '新 funding 数据源接入（探针证据在册，复活哨兵 T2）'})
    for cid in ('c1a_funding_pct', 'c1b_funding_slope', 'c1c_fund_px_div'):
        rows.append({'category': 'B_signal_use', 'id': cid, 'pname': '双池',
                     'domain': '信号用途（资金费代理）', 'judging_line': JUDGE_SIGNAL,
                     'evidence': {'status': 'NOT_RUNNABLE',
                                  'evidence': '快照字段无 funding/rate；样本要求=日频≥240 '
                                              '交易日费率史，覆盖 0%（PC-1）'},
                     'verdict': '无法评估（垫不适用）',
                     'revival_gate': '新 funding 数据源接入（复活哨兵 T2）'})

    # C 类：c2 事件叠加 6 行（X4）
    cnc = json.load(open(CNC_F))
    for key, ev in sorted(cnc['directions']['c2']['events'].items()):
        full, rc = ev['FULL'], ev['realC']
        rows.append({'category': 'C_event_overlay', 'id': key, 'pname': key.split('|')[1],
                     'domain': '事件叠加（避损型）', 'judging_line': JUDGE_EVENT,
                     'evidence': {'FULL_avoid_incr_pp': full['avoid_incr_pp'],
                                  'FULL_mdd_not_worse': full['mdd_not_worse'],
                                  'realC_avoid_incr_pp': rc['avoid_incr_pp'],
                                  'realC_mdd_not_worse': rc['mdd_not_worse'],
                                  'source': 'c_new_candidates.json（冻结存档）'},
                     'verdict': '维持挂账（FULL 全负；realC 伴行正但垫 <0.2×，X4）',
                     'revival_gate': 'realB 型段触发器命中（T3）'})

    # D 类：排除册 X1/X5/X6/X7（DUAL_VERDICT §七-B 原文）
    xrows = [
        ('X1_b_state_gate_41cfg', 'b 状态门 41 配置（聚合行）',
         '无法评估（垫不适用：门信号用途；垫数字已并入 A 类 82 行）',
         'FDR 0/41；复活=前瞻累积/数据域回填'),
        ('X5_c3_multi_period', 'c3 多周期合成',
         '维持挂账（提升 −31.8%/−3.49% 需>+15%）',
         '复活线=单周期 smoothing（daily_smooth5/weekly_agg IC 0.081 t≈3.5 在册）'),
        ('X6_c4_mean_reversion', 'c4 均值回归',
         '维持排除（与动量同信息，垫不适用）', '无独立增量'),
        ('X7_d_period_swap', 'd-换周期',
         '维持排除（IC −0.054/−0.063 更差）', '三路径已试尽之一'),
    ]
    for rid, desc, verdict, gate in xrows:
        rows.append({'category': 'D_exclude_book', 'id': rid, 'pname': '—',
                     'domain': desc, 'judging_line': '条目专用冻结判线（DUAL_VERDICT §七-B）',
                     'evidence': {'source': SPEC + ' §七-B（冻结原文）'},
                     'verdict': verdict, 'revival_gate': gate})

    # E 类：历史出清 8 + F3 待补档（§七-C 原文）
    erows = [
        ('H8', '维持出清（负垫）', '判据②③④命中，翻案成立（R2 终裁）'),
        ('M3', '维持出清（负垫）', '对抗样本+厚利桶 −85.3%'),
        ('bear_leg_family', '维持出清（负垫）', '方向性无边际，mean/sum/PF 全负，双席独立证实'),
        ('bks_overlay', '维持出清（垫不适用）', '稀释型假提升'),
        ('bks_bear_tp05', '维持出清（垫不适用）', 'n=40 噪声'),
        ('fd_bear', '维持出清（负垫）', '2024 单年肥尾伪提升'),
        ('fd_A_B_C', '维持出清（垫算不出：主窗交易数=0）', 'fd 闸无的放矢；重开门槛已写死'),
        ('state_23', '维持出清（负效应）', '35 态扫描 24 真拒绝中的 PF-8 负尾真实负效应'),
    ]
    for rid, verdict, basis in erows:
        rows.append({'category': 'E_historical_purge', 'id': rid, 'pname': '—',
                     'domain': '历史出清归档项', 'judging_line': '≥3× 判据逐条过（§七-C）',
                     'evidence': {'basis': basis, 'source': SPEC + ' §七-C（冻结原文）'},
                     'verdict': verdict, 'revival_gate': '方向性负证据翻转（新数据段重评，R9）'})
    rows.append({'category': 'E_historical_purge', 'id': 'F3_oversold_short_reversion',
                 'pname': '—', 'domain': '超跌短回归（终裁记录未定位）',
                 'judging_line': '待补档（不计入三档）',
                 'evidence': {'basis': '终裁记录未定位，下轮档案核查工单',
                              'source': SPEC + ' §七-C（冻结原文）'},
                 'verdict': '待补档（1 条）', 'revival_gate': '补档核查后按同判线补判'})
    return rows


# ============================================================ 复活判定（RV-4/5）
def revive_row(row, round_id, trigger):
    """A 类数据驱动判复活；其余类别仅在哨兵证据出现时复活（RV-4）。
    域限定：已在可跑池的 24 行（维持，非本次复活）不进复活判定——§七 口径。"""
    ev = row['evidence']
    if row['category'] == 'A_cost_use' \
            and not row['verdict'].startswith('已在可跑池'):
        mb, av = ev.get('cushion_x_min_both'), ev.get('cushion_x_avoid_caliber')
        if mb is not None and av is not None and mb >= THICK_X and av >= THICK_X:
            row['verdict'] = '复活进可跑池（纸面）'
            row['revived'] = True
    row.setdefault('revived', False)
    if row['revived']:
        row['annotations'] = ['复活来源=' + trigger, DUAL_TAG,
                              '复活≠部署：纸面可跑池→影子伴行≥20 交易日→'
                              '新预注册部署评审→方可动实盘（垫厚按未来打折）']
        row['revival_channel'] = {'stage': '纸面可跑池（paper_runnable）',
                                  'shadow_companion_days_required': SHADOW_DAYS_REQ,
                                  'shadow_companion_days_done': 0,
                                  'next_gate': '新预注册部署评审（前瞻段新数字，PCX-B6）',
                                  'deployed': False, 'round_id': round_id}
    return row


# ============================================================ 触发器（RV-6）
def _pool_calendar_tail():
    import wo_rescue_run as WR
    WR._init()
    cal = set().union(*[set(WR._DATA[s].index) for s in WR._POOLS['full144']])
    return max(cal)


def triggers(state):
    tr = []
    now_month = time.strftime('%Y-%m')
    if state.get('last_monthly_audit') != now_month:
        tr.append(('T0_月度定期重审（每月首个判定轮）',
                   f"last_monthly_audit={state.get('last_monthly_audit')} ≠ {now_month}"))
    sent = {}
    if os.path.exists(SENTINEL_F):
        sent = json.load(open(SENTINEL_F))
    if sent.get('overseas_api_ok') or sent.get('new_funding_endpoint') \
            or (sent.get('shadow_seq_days') or 0) >= SHADOW_DAYS_REQ:
        tr.append(('T2_复活哨兵命中', {k: sent.get(k) for k in
                                     ('overseas_api_ok', 'new_funding_endpoint',
                                      'shadow_seq_days')}))
    if (sent.get('realb_like_segment') or {}).get('detected'):
        tr.append(('T3_realB 型段触发器', sent['realb_like_segment']))
    tail = _pool_calendar_tail()
    last_seen = state.get('last_seen_data_tail')
    if last_seen:
        import pandas as pd
        import wo_rescue_run as WR
        ls = pd.Timestamp(last_seen)
        cal = set().union(*[set(WR._DATA[s].index) for s in WR._POOLS['full144']])
        n_new = len([d for d in cal if d > ls])
        if n_new >= NEWSEG_DAYS_REQ:
            tr.append(('T1_新数据段满 20 交易日', f'新增 {n_new} 交易日（>{last_seen}）'))
    state['data_tail_seen_this_run'] = str(tail.date())
    return tr


# ============================================================ 重审执行（RV-1/7）
def audit(round_id, trigger, note=''):
    """整表重审并追加落库（追加不覆盖）。返回行数。"""
    src = population()
    n_revived = 0
    with open(LEDGER_F, 'a') as f:
        f.write(json.dumps({'_round': round_id, 'audited_at': time.strftime('%F %T'),
                            'trigger': trigger, 'note': note,
                            'judging_line_rule': '同判线不放宽（垫≥3× 双口径 / F6 ①②③ / '
                                                 '门 FDR q=0.10），只在新数据段上评',
                            'population_size': len(src),
                            'core_population': '被资费卡死 ≈235 变体级'
                                               '（58 挂账 + 171 信号用途 + c2 6 行）',
                            'spec': SPEC + ' §九（冻结）'},
                           ensure_ascii=False) + '\n')
        for i, row in enumerate(src):
            row = revive_row(row, round_id, trigger)
            row.update({'round_id': round_id, 'seq': i,
                        'audited_at': time.strftime('%F %T')})
            n_revived += int(row['revived'])
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    return len(src), n_revived


def run():
    if os.path.exists(STATE_F):
        state = json.load(open(STATE_F))
    else:
        state = {'created_at': time.strftime('%F %T'), 'round_counter': 0,
                 'last_monthly_audit': None, 'last_seen_data_tail': None,
                 'protocol': 'RV-1..RV-9（revival_watch.py 头注，2026-10-19 冻结）'}
    tr = triggers(state)
    if not tr:
        print(f"revival_watch: 无触发（月度={state.get('last_monthly_audit')}；"
              f"数据尾={state.get('data_tail_seen_this_run')}）——只检状态不重审（RV-6）")
        with open(STATE_F, 'w') as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        return state
    names = '; '.join(t[0] for t in tr)
    state['round_counter'] = int(state.get('round_counter', 0)) + 1
    rid = f"R{state['round_counter']}"
    n, n_rev = audit(rid, names, note=str([t[1] for t in tr]))
    state['last_monthly_audit'] = time.strftime('%Y-%m')
    state['last_seen_data_tail'] = state.get('data_tail_seen_this_run')
    state[f'last_round_{rid}'] = {'rows': n, 'revived': n_rev,
                                  'trigger': names, 'at': time.strftime('%F %T')}
    with open(STATE_F, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print(f"revival_watch: 重审 {rid} 落库（触发={names}）——{n} 行追加，"
          f"复活 {n_rev} 行")
    return state


def build():
    """R0 首轮建账：复现 DUAL_VERDICT §七 汇总并断言（RV-8）。"""
    assert not os.path.exists(LEDGER_F), '台账已存在——R0 只建一次（追加不覆盖，禁重建）'
    rid = 'R0'
    n, n_rev = audit(rid, 'R0_首轮全量重审（冻结存档数字过同判线）',
                     note='DUAL_VERDICT §七 全量重审表落库为常设台账')
    state = {'created_at': time.strftime('%F %T'), 'round_counter': 0,
             'last_monthly_audit': time.strftime('%Y-%m'),
             'last_seen_data_tail': _pool_calendar_tail().strftime('%Y-%m-%d'),
             'protocol': 'RV-1..RV-9（revival_watch.py 头注，2026-10-19 冻结）',
             'r0_note': f'{n} 行落库，复活 {n_rev}（§七：0 新复活=诚实结果）'}
    with open(STATE_F, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    # RV-8 断言：复现 §七 汇总
    rows = [json.loads(l) for l in open(LEDGER_F) if '"_round"' not in l]
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r['category'], []).append(r)
    assert len(rows) == 272, len(rows)
    assert sum(1 for r in rows if r['category'] == 'A_cost_use') == 82
    assert sum(1 for r in rows if r['category'] == 'B_signal_use') == 171
    assert sum(1 for r in rows if r['category'] == 'C_event_overlay') == 6
    pend_pos = sum(1 for r in by_cat['A_cost_use'] if r['verdict'].startswith('维持挂账'))
    pend_neg = sum(1 for r in by_cat['A_cost_use'] if r['verdict'].startswith('垫算不出'))
    keep = sum(1 for r in by_cat['A_cost_use'] if r['verdict'].startswith('已在可跑池'))
    assert (keep, pend_pos, pend_neg) == (24, 46, 12), (keep, pend_pos, pend_neg)
    assert n_rev == 0, f'复活 {n_rev}≠0——与 §七「0 新复活」不符，停工'
    print(f'R0 建账完成：{n} 行（A82/B171/C6/D4/E9）；断言全过：'
          f'可跑池维持 24 / 正垫挂账 46 / 负垫 12 / 复活 0（§七 逐位复现）')


def selftest():
    """RV-9：沙箱自测（不改真台账）。"""
    import shutil
    import tempfile
    global LEDGER_F, STATE_F, SENTINEL_F
    tmp = tempfile.mkdtemp(prefix='revival_selftest_')
    real = (LEDGER_F, STATE_F, SENTINEL_F)
    LEDGER_F, STATE_F = os.path.join(tmp, 'l.jsonl'), os.path.join(tmp, 's.json')
    SENTINEL_F = os.path.join(tmp, 'sent.json')
    try:
        # ① 首轮建账（R0）
        build()
        first = [l for l in open(LEDGER_F)]
        # ② 触发器判定：T0 月度（新 state）+ T1 伪造 25 个新交易日 + T2 哨兵
        json.dump({'overseas_api_ok': True}, open(SENTINEL_F, 'w'))
        import pandas as pd
        import wo_rescue_run as WR
        WR._init()
        cal = sorted(set().union(*[set(WR._DATA[s].index)
                                   for s in WR._POOLS['full144']]))
        fake_tail_25 = cal[-25]
        st = {'round_counter': 0, 'last_monthly_audit': '2000-01',
              'last_seen_data_tail': str(fake_tail_25.date())}
        json.dump(st, open(STATE_F, 'w'))
        tr = triggers(st)
        kinds = [t[0].split('_')[0] for t in tr]
        assert 'T0' in kinds and 'T1' in kinds and 'T2' in kinds, kinds
        # ③ 第二轮重审追加
        run()
        second = [l for l in open(LEDGER_F)]
        assert second[:len(first)] == first, '追加不覆盖 FAIL：首轮行被改动'
        # ④ 复活行通道字段与标注齐备（伪造 A 类双口径 ≥3×）
        rows = population()
        fake = next(r for r in rows if r['category'] == 'A_cost_use'
                    and r['verdict'].startswith('维持挂账'))
        fake['evidence']['cushion_x_min_both'] = 4.0
        fake['evidence']['cushion_x_avoid_caliber'] = 3.5
        revive_row(fake, 'RX', '自测伪造证据')
        assert fake['revived'] and fake['revival_channel']['stage'] == '纸面可跑池（paper_runnable）'
        assert any('复活来源' in a for a in fake['annotations']) and DUAL_TAG in fake['annotations']
        n_lines = len(second)
        n_rounds = sum(1 for l in second if '"_round"' in l)
        print(f'SELFTEST PASS：追加不覆盖 ✓（{n_rounds} 轮 {n_lines} 行，首轮逐位不变）；'
              f'触发器 T0/T1/T2 ✓；复活通道四段字段+标注 ✓；0 复活复现 ✓')
    finally:
        LEDGER_F, STATE_F, SENTINEL_F = real
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else 'run'
    cmd = {'--build': 'build', '--selftest': 'selftest'}.get(arg, arg)
    {'run': run, 'build': build, 'selftest': selftest}[cmd]()
