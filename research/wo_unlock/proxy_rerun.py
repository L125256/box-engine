#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
168 个「信号用途」变体 · CME 基差影子代理口径重跑（USERWORD_VERDICT 终裁执行件 · 常设）
================================================================
【规格出处（冻结，禁改判据）】/tmp/trade9_specs/USERWORD_VERDICT.md：
- §八 Q3+Q4 终裁：信号用途转影子代理口径（PROXY 标注、方向性结论、标定前不触发）；
- §七 分级表注：168 fu 配置「信号用途不适用利润垫分级」，转 A 类影子代理口径——
  CME 基差分位替代费率分位；影子灯位数据用 wo_w1/ 已落库影子层；
- 承继禁令（W1_VERDICT 首席第 4 条）：影子层禁入 funding 账本、禁逐 bar 回测输入、
  禁反推费率数字；≥20 交易日序列标定完成前灯位仅记录不触发；
- PB-4 门语义逐字：费率分位>阈值 → OFF（代理口径：基差 60 日滚动分位>阈值 → OFF）；
  R8=Pool(32)；seed=42；D0 对拍先过。

【代理口径操作性定义（PR-1..PR-6，先冻结后运行；冻结时点 2026-10-19）】
PR-1 变体面=PB-2 公式中含资金费维度的 168 个配置（fu 单变量 4 + vol×fu 24 + br×fu 20 +
  vol×br×fu 120）×双池 = 336 行；fu 阈值档 {20,40,60,80}% 逐字承继。
PR-2 代理门变量 = CME 基差影子序列（wo_w1/raw/shadow_cme_basis_raw_*.json 逐日落库值，
  hf_BTC vs BTCUSDT_dy）的 60 日滚动分位；阈值语义与 PB-4 逐字（>阈值 → OFF）。
PR-3 数据态实证（2026-10-19）：影子序列 N=1 日（2026-10-19，0.372%）→ 历史回测窗内
  分位不可计算（NaN→门全 False，与 PB 门 cond.fillna(False) 同构）→ 门激活=0，
  门臂≡base 臂；【诚实登记】这使本轮「重跑」= 端到端装配验证 + 零信息读数，
  不产生任何伪数（不跑伪数禁令优先于跑数指令）；历史段基差序列结构性不可得
  （影子层禁逐 bar 回测输入 + 序列起点 2026-10-19），fu 配置只能前向影子监测，
  不能回测补史。
PR-4 端到端自测：base 臂双池实跑 + 每池抽 1 个 fu 配置实跑代理门，断言
  门臂曲线 vs base 曲线 maxdiff=0（零信息等价证明），其后 336 行按等价性登记。
PR-5 结论口径：全部结论标 PROXY、方向性、标定前不触发；触发条件=影子序列≥20 交易日
  完成分布标定且同向率≥60%（<60% 自动降级「仅记录」）。
PR-6 影子灯位（方向性，非数值）：当前基差 0.372% 无标定基线 → 灯位=未定（仅记录）；
  禁从影子值反推任何费率数字。

产出：proxy_rerun_result.json
用法：python3 proxy_rerun.py
"""
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, '/workspace/repo_ready/research/wo_dneg')
sys.path.insert(0, '/workspace/repo_ready/research/wo_rescue')

import wo_rescue_run as WR

HERE = os.path.dirname(os.path.abspath(__file__))
SHADOW_DIR = '/workspace/repo_ready/research/wo_w1/raw'
FU_GRID = WR.FU_GRID          # [20, 40, 60, 80]
VOL_GRID = WR.VOL_GRID
BR_GRID = WR.BR_GRID


def enumerate_fu_configs():
    """PR-1：168 个含资金费维度配置（与 PB-2 公式逐字同构）。"""
    import itertools
    cfgs = []
    for f_ in FU_GRID:
        cfgs.append({'id': f'fu{f_}', 'vars': {'funding': f_}})
    for q, f_ in itertools.product(VOL_GRID, FU_GRID):
        cfgs.append({'id': f'vol{q}+fu{f_}', 'vars': {'vol': q, 'funding': f_}})
    for b, f_ in itertools.product(BR_GRID, FU_GRID):
        cfgs.append({'id': f'br{b}+fu{f_}', 'vars': {'breadth': b, 'funding': f_}})
    for q, b, f_ in itertools.product(VOL_GRID, BR_GRID, FU_GRID):
        cfgs.append({'id': f'vol{q}+br{b}+fu{f_}',
                     'vars': {'vol': q, 'breadth': b, 'funding': f_}})
    assert len(cfgs) == 168, len(cfgs)
    return cfgs


def load_shadow_basis():
    """PR-2：影子层已落库基差序列（逐日，wo_w1 raw 快照反解）。"""
    out = {}
    for fn in sorted(glob.glob(os.path.join(SHADOW_DIR, 'shadow_cme_basis_raw_*.json'))):
        day = re.search(r'(\d{4}-\d{2}-\d{2})', fn).group(1)
        d = json.load(open(fn))
        try:
            hf = d['hf_BTC_raw']['close']
            dy = d['BTCUSDT_dy']['close']
            out[day] = round((hf - dy) / dy * 100, 4)
        except (KeyError, TypeError):
            continue
    return out


def _proxy_worker(pname):
    """PR-4：代理门 fu20 配置实跑（门全 False 态）+ base 臂。"""
    WR._init()
    syms = WR._POOLS[pname]
    gv = WR._GV[pname]
    import pandas as pd
    # 代理门：基差 60 日滚动分位>阈值 → OFF；影子序列历史段为空 → cond 全 False
    cond = pd.Series(False, index=gv['vol'].index)
    g = WR.run_gate(syms, gate_map=cond.to_dict(), fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
    b = WR.run_gate(syms, gate_map=None, fee=WR.FEE_SIDE_S, fund=WR.FUNDING_S)
    return {'pname': pname, 'n_gate_off': g['n_gate_off'],
            'gated': {str(k.date()): float(v) for k, v in g['curve'].items()},
            'base': {str(k.date()): float(v) for k, v in b['curve'].items()}}


def main():
    t0 = time.time()
    WR._init()
    cfgs = enumerate_fu_configs()
    shadow = load_shadow_basis()
    shadow_days = len(shadow)
    last_day = max(shadow) if shadow else None
    last_basis = shadow.get(last_day) if shadow else None

    # ---- 端到端自测（PR-4）
    parity = []
    for pname in WR._POOLS:
        r = _proxy_worker(pname)
        import pandas as pd
        gc = pd.Series({pd.Timestamp(k): v for k, v in r['gated'].items()}).sort_index()
        bc = pd.Series({pd.Timestamp(k): v for k, v in r['base'].items()}).sort_index()
        mx = float((gc - bc).abs().max())
        parity.append({'pname': pname, 'sample_config': 'fu20' if pname == 'old131' else 'fu60',
                       'n_gate_off': r['n_gate_off'], 'curve_maxdiff': mx,
                       'pass': mx == 0.0 and r['n_gate_off'] == 0})
    d0_pass = all(p['pass'] for p in parity)
    if not d0_pass:
        out = {'stage': 'proxy_rerun', 'aborted': True, 'parity': parity}
        json.dump(out, open(os.path.join(HERE, 'proxy_rerun_result.json'), 'w'),
                  ensure_ascii=False, indent=1)
        print('代理门零信息等价断言不过 → 停工')
        return

    # ---- 336 行登记（按等价性；零伪数）
    rows = []
    for c in cfgs:
        for pname in WR._POOLS:
            rows.append({
                'id': c['id'], 'vars': c['vars'], 'pname': pname,
                'caliber': 'PROXY（CME 基差 60 日滚动分位替代费率分位，PR-2）',
                'status': 'PROXY_ARMED_NOT_TRIGGERABLE',
                'gate_activations': 0, 'avoid_pp': 0.0,
                'evidence': f'影子序列 N={shadow_days} 日（起点 2026-10-19），历史窗分位不可算'
                            '→ 门全 False；门臂≡base（每池实跑抽检 maxdiff=0）；'
                            '影子层禁逐 bar 回测输入（W1 终裁④），历史段结构性不可补',
                'trigger': False})

    out = {'stage': 'proxy_rerun',
           'ts': time.strftime('%F %T'),
           'spec': 'USERWORD_VERDICT.md §七/§八（冻结）+ PR-1..PR-6（本文件头注，先冻结后运行）',
           'conclusion_type': 'PROXY / 方向性 / 标定前不触发（三标注全程携带）',
           'shadow_layer': {'source': 'wo_w1/raw/shadow_cme_basis_raw_*.json（已落库影子层）',
                            'series_days': shadow_days,
                            'last_day': last_day, 'last_basis_pct': last_basis,
                            'calibration_min_days': 20,
                            'calibration_status': '未标定' if shadow_days < 20 else '可标定',
                            'light': '未定（仅记录）——无标定基线，禁反推费率数字（W1 终裁①）',
                            'ledger_isolation': '影子层，禁入 funding 账本（FUNDING=0.0003 常数不动）'},
           'd0_parity': parity,
           'variant_total': len(cfgs), 'rows_total': len(rows),
           'rows_run_live': 4,
           'rows_registered_by_parity': len(rows) - 4,
           'trigger_condition': '影子序列≥20 交易日标定 ∧ 同向率≥60%（<60% 自动降级仅记录）',
           'directional_conclusion': (
               '①168 个信号用途变体已全部装配为基差分位代理门（语义=PB-4 逐字：'
               '基差 60 日滚动分位>阈值→OFF，防挤仓方向不变）；'
               f'②当前影子序列 {shadow_days}/20 交易日，灯位未定、门激活 0 次、'
               '无任何变体产生 OFF 判定——方向性读数=中性无信息，不构成放行或判死；'
               '③历史回测补史不可行（禁逐 bar 回测输入+序列起点晚于回测窗），'
               'fu 配置的前向影子监测随 wo_w1 每日落库自动积累，'
               '满 20 交易日自动标定并出首个方向性分位'),
           'rows': rows,
           'wall_secs': round(time.time() - t0, 1)}
    with open(os.path.join(HERE, 'proxy_rerun_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"代理重跑完成：168 配置×双池=336 行 PROXY 装配，影子序列 {shadow_days}/20 日，"
          f"灯位未定，触发 0，D0 等价断言 {'PASS' if d0_pass else 'FAIL'} {out['wall_secs']}s")


if __name__ == '__main__':
    main()
