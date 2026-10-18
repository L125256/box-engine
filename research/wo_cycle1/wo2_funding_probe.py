#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WO2 R11 资金费回填 + 成本可交易性（冻结规格 v1.0 · 一次成活 · seed=42）
① P1 导演站 funding 接口探测：仅探测记录，不改任何代码逻辑；常见路径试探。
   无接口 → 缺口登记单（「不可计算≠证伪」），维持 0.03%/bar 常数记账，回填挂起；
   P2 反推 / P3 新浪备源均按冻结条款否决用于 funding，禁伪回填。
② 影子先行（不依赖回填）：I_turn = 0.05% × 池 20 日均换手(EMA)年化 pp/年，
   全部只用 T 日及之前数据（杜绝前视）；I_fund 无数据源 → 登记不可计算
   （常数 0.03%/bar 记账下滚动分位恒为常数，无判别力，不作伪计算）。
③ 事前捕捉回放：标签=未来 20 日交易费 regime 高/低（pp/日中位切）；打分=I_turn；
   回放 2025-06→今双池分列，报 AUC + 阈值命中表（换手 EMA>0.25x/日 越线灯）。
   通过判据：AUC>=0.70（至少一池）或 2026-03 内 >=1 次事前命中（早于 2026-04-01
   >=5 交易日）；两证均无 → 指标降级「仅记录不判定」。单事件局限强制标注【假设→打折】。
复现：python3 wo2_funding_probe.py
"""
import json
import os
import sys
import datetime

import numpy as np
import pandas as pd
import requests

sys.dont_write_bytecode = True
sys.path.insert(0, '/workspace/repo_ready/research/wo_cycle1')
sys.path.insert(0, '/tmp/eng_w2_f1')
from eng_f1_instr import run_instr   # noqa: E402
from f1_backtest import load_data, build_pools, build_factors, SEED   # noqa: E402

np.random.seed(SEED)
OUT = '/workspace/repo_ready/research/wo_cycle1'
BASE = 'https://www.kxiandaoyan.com/api'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
REAL_START = pd.Timestamp('2025-06-01')
FWD = 20
TURN_LINE_X_DAY = 0.25          # S1 冻结灯位：换手 <=0.25x/日 成本友好
I_TURN_AT_LINE = 0.0005 * TURN_LINE_X_DAY * 365 * 100   # = 4.5625 pp/年


# ------------------------------------------------ ① P1 探测（仅记录）
def probe():
    paths = [
        ('/funding', {'market': 'futures', 'symbol': 'MVLLUSDT'}),
        ('/fundingRate', {'market': 'futures', 'symbol': 'MVLLUSDT'}),
        ('/funding_rate', {'market': 'futures', 'symbol': 'MVLLUSDT'}),
        ('/fundingRates', {'market': 'futures'}),
        ('/funding/history', {'market': 'futures', 'symbol': 'MVLLUSDT'}),
        ('/fundingRate/history', {'market': 'futures', 'symbol': 'MVLLUSDT'}),
        ('/funding_history', {'symbol': 'MVLLUSDT'}),
        ('/markPrice', {'market': 'futures', 'symbol': 'MVLLUSDT'}),
        ('/premiumIndex', {'market': 'futures', 'symbol': 'MVLLUSDT'}),
        ('/kline/MVLLUSDT', {'market': 'futures', 'period': '8h', 'limit': 50}),
        ('/signals', {'market': 'futures', 'period': '1d', 'page': 1, 'size': 3}),
    ]
    rec = []
    for p, params in paths:
        url = BASE + p
        item = {'path': p, 'params': params}
        try:
            r = requests.get(url, params=params, headers={'User-Agent': UA},
                             timeout=(5, 10))
            body = r.text[:300].replace('\n', ' ')
            item.update(status=r.status_code, content_type=r.headers.get('content-type'),
                        body_head=body)
            # funding 字段指纹
            low = r.text.lower()
            item['mentions_funding'] = ('funding' in low)
        except Exception as e:
            item.update(error=f'{type(e).__name__}: {e}')
        rec.append(item)
        print('probe', p, '->', item.get('status', item.get('error', '?')),
              'funding Mentioned' if item.get('mentions_funding') else '')
    return rec


# ------------------------------------------------ ②③ 影子先行
def auc(score_pos, score_neg):
    """秩和 AUC：P(正例分 > 负例分) + 0.5*P(=)。"""
    sp = np.asarray(score_pos, dtype=float)
    sn = np.asarray(score_neg, dtype=float)
    if len(sp) == 0 or len(sn) == 0:
        return None
    allv = np.concatenate([sp, sn])
    order = allv.argsort().argsort().astype(float)   # 平均秩
    r_pos = order[:len(sp)].sum()
    n1, n0 = len(sp), len(sn)
    return float((r_pos - n1 * (n1 + 1) / 2) / (n1 * n0))


def main():
    os.makedirs(OUT, exist_ok=True)
    probes = probe()

    data = load_data()
    pools = build_pools(data)
    F = build_factors(data)
    shadow = {}
    for pname, syms in pools.items():
        r = run_instr(data, F, syms, rebal_weeks=1)     # 周=权威形态（ungated）
        led = pd.DataFrame(r['fee_ledger'])
        led['date'] = pd.to_datetime(led['date'])
        trade_fee_d = led.groupby('date')['fee'].sum().reindex(r['curve'].index).fillna(0.0)
        fund_d = pd.Series(r['funding_by_day'], dtype=float)
        fund_d.index = pd.to_datetime(fund_d.index)
        fund_d = fund_d.reindex(r['curve'].index).fillna(0.0)
        # 换手 x/日 = 当日成交名义（权益基数≈1）
        to_d = led.groupby('date')['notional'].sum().reindex(r['curve'].index).fillna(0.0)
        ema20 = to_d.ewm(span=20, adjust=False).mean()
        i_turn = 0.0005 * ema20 * 365 * 100             # pp/年
        cost_pp_day = trade_fee_d * 100                 # 交易费 pp/日（影子口径，常数资金费另列）
        idx = (r['curve'].index >= REAL_START) & (r['curve'].index <= r['curve'].index[-1])
        df = pd.DataFrame({'i_turn': i_turn, 'cost_pp_day': cost_pp_day,
                           'funding_pp_day': fund_d * 100})[idx].dropna()
        # 标签：未来 20 日成本 regime（交易费 pp/日 中位切，只用窗口内样本）
        fut = df['cost_pp_day'].shift(-1).rolling(FWD).mean().shift(-FWD)
        med = float(fut.median())
        lab = (fut > med).astype(int)
        valid = fut.notna()
        # AUC（打分只用 T 日及之前：i_turn 为 EMA，天然无前视）
        pos = df.loc[valid & (lab == 1), 'i_turn']
        neg = df.loc[valid & (lab == 0), 'i_turn']
        a = auc(pos, neg)
        # 阈值命中表：I_turn 越线（换手 EMA>0.25x/日）
        hit = df['i_turn'] > I_TURN_AT_LINE
        hits = df.index[hit]
        pre = [d for d in hits
               if pd.Timestamp('2026-03-01') <= d <= pd.Timestamp('2026-03-31')]
        # 事前命中：2026-03 内且早于 2026-04-01 >=5 交易日
        cal = df.index
        pre_hits = []
        for d in pre:
            gi = cal.get_loc(d)
            gap_days = int((cal >= pd.Timestamp('2026-04-01')).argmax() - gi)
            if gap_days >= 5:
                pre_hits.append({'date': str(d.date()),
                                 'trading_days_before_0401': gap_days,
                                 'i_turn_pp': round(float(df.at[d, 'i_turn']), 2)})
        shadow[pname] = {
            'window': f'{df.index[0].date()}~{df.index[-1].date()} (>=2025-06 真实窗)',
            'i_turn': {'def': '0.05%×池20日均换手(EMA,t=20)年化 pp/年；只用T日及之前数据',
                       'line_pp_ann': round(I_TURN_AT_LINE, 4),
                       'mean': round(float(df['i_turn'].mean()), 2),
                       'max': round(float(df['i_turn'].max()), 2),
                       'n_days_over_line': int(hit.sum())},
            'label': {'def': '未来20日交易费pp/日均值 > 窗口中位数 = 高成本 regime',
                      'median_pp_day': round(med, 4), 'n_valid': int(valid.sum()),
                      'n_high': int(valid.sum() and ((lab == 1) & valid).sum())},
            'auc_i_turn': None if a is None else round(a, 4),
            'i_fund': {'status': '不可计算（无 funding 数据源；P2 反推/P3 新浪均被冻结条款否决；'
                                  '0.03%/bar 常数记账下滚动分位恒为常数，无判别力，不作伪计算）'},
            'hits_2026_03': [str(d.date()) for d in pre],
            'pre_hits_ge5td_before_0401': pre_hits,
            'n_pre_hits': len(pre_hits),
        }
        print(f"[{pname}] AUC(I_turn)={shadow[pname]['auc_i_turn']} "
              f"2026-03命中={len(pre_hits)} 越线日={int(hit.sum())}")

    aucs = [v['auc_i_turn'] for v in shadow.values() if v['auc_i_turn'] is not None]
    n_pre = sum(v['n_pre_hits'] for v in shadow.values())
    auc_pass = any(a is not None and a >= 0.70 for a in aucs)
    hit_pass = n_pre >= 1
    verdict = ('PASS（AUC 达标）' if auc_pass else
               'PASS（2026-03 事前命中达标）' if hit_pass else
               '两证均无 → 指标降级「仅记录不判定」')

    out = dict(
        generated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        workorder='WO2 R11 资金费回填 + 成本可交易性 · 冻结规格 v1.0',
        seed=SEED,
        p1_probe=dict(
            base=BASE,
            note='仅探测记录，不改任何代码逻辑（冻结条款）；探测时点见 generated',
            results=probes,
            conclusion=('探测到 funding 字段/接口 → 走回填'
                        if any(p.get('mentions_funding') and p.get('status') == 200
                               for p in probes)
                        else '无 funding 历史 endpoint（200 响应均无 funding 字段指纹）→ 缺口登记：'
                             '回填判 P1 无接口，维持 0.03%/bar 常数记账，回填挂起等新数据源，'
                             '不影响②③影子先行（冻结降级条款）')),
        p2_p3_rejected=dict(P2='反推路线否决（资金费不可由K线/价格反推，设计推断）——禁伪回填',
                            P3='新浪备源否决用于 funding（美元现货价、无费率字段、无 SLA）——仅价格抽查'),
        gap_register=dict(
            item='funding rate 历史（144 标的 × 8h × 2025-06→今）',
            status='缺口——导演站无接口（见 p1_probe），本地 box_cache 仅 OHLCV',
            rule='「不可计算≠证伪」；复活条件=新数据源出现',
            coverage='0%（真实窗）→ 若按回填判据口径记 FAIL，但不报废，降级影子计算+缺口登记'),
        shadow=shadow,
        validation=dict(
            design='标签=未来20日成本 regime 高/低（交易费 pp/日 中位切）；打分=I_turn；'
                   '回放 2025-06→今双池分列；资金费侧因缺口仅常数记账，成本标签为影子口径（仅交易费）',
            verdict=verdict,
            auc_pass=bool(auc_pass), hit_pass=bool(hit_pass),
            limitation='单事件验证（2026-04 成本跳升仅一次）属【假设→打折】级，结论禁过度宣称'),
        fail_action='回填覆盖<80%真实窗 → 判 FAIL 不报废，降级影子计算+缺口登记；复活=新数据源',
    )
    with open(os.path.join(OUT, 'wo2_result.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print('OK ->', os.path.join(OUT, 'wo2_result.json'))
    print('WO2 verdict:', verdict)


if __name__ == '__main__':
    main()
