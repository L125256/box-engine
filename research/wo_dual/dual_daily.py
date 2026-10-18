#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双轨并排日报件（DUAL_VERDICT §〇/§六 · 辅轨确认，常设日调项）
================================================================
【规格出处（冻结）】/tmp/trade9_specs/DUAL_VERDICT.md：
- §〇 辅轨 = n≥20 前瞻管线照挂每天收集，不废弃：forward_readout.py 保留（0/20
  ACCUMULATING），每日判定轮自动积累照跑；冲突裁决=辅轨为最终确认、主轨为当下
  行动依据；
- §六 交易员日调新增：dual_readout 精确切分读数（每日判定轮搭车，异常不阻断）；
- 本件职责：把主轨读数（dual_result.json）与辅轨累计状态（forward_state.json）
  并排成日报字段，逐日落库 daily_track_compare.jsonl（追加不覆盖）。
  forward_readout.py 本体不删不停、n≥20 累计保留不动——本件只读其状态文件，
  不改引擎语义、不参与封印逻辑。

字段（DC/FR 承继）：
  main_track   = 主轨读数（F6 互验结论 + 门域两件 dual 结论 + 总读数，全部带
                 「口径变更重判」标注）
  aux_track    = 辅轨累计状态（n_lo_days_matured/target、ACCUMULATING/SEALED、
                 ic_mean/ic_t；只读 forward_state.json）
  conflict_rule= 两轨冲突时：辅轨最终确认、主轨当下行动依据（§〇 逐字）

用法：python3 dual_daily.py [--auto]   # 判定轮落盘后搭车调用，异常不阻断
产出：daily_track_compare.jsonl（追加一行/次）
"""
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DUAL_RESULT_F = os.path.join(_HERE, 'dual_result.json')
FWD_STATE_F = '/workspace/repo_ready/research/wo_unlock/forward/forward_state.json'
OUT_F = os.path.join(_HERE, 'daily_track_compare.jsonl')
CONFLICT_RULE = '两轨结论冲突时：辅轨为最终确认、主轨为当下行动依据（DUAL_VERDICT §〇）'


def main_track_read():
    if not os.path.exists(DUAL_RESULT_F):
        return {'status': 'PENDING（dual_result.json 未生成——精确切分件未跑）'}
    r = json.load(open(DUAL_RESULT_F))
    return {'annotation': '口径变更重判（dual_* 命名空间；原数字封印 *_orig 不混写）',
            'F6_dual': r['dual_f6']['dual_verdict'],
            'F6_segments': {sn: s['dual_segment_state']
                            for sn, s in r['dual_f6']['segments'].items()},
            'S3xD1_dual': r['main_track_read']['S3xD1'],
            'B1_dual': r['main_track_read']['B1'],
            'overall': r['overall'],
            'rerun_quota_used': r['rerun_quota']['used']}


def aux_track_state():
    if not os.path.exists(FWD_STATE_F):
        return {'status': 'PENDING（forward_state.json 未生成）'}
    s = json.load(open(FWD_STATE_F))
    acc = s.get('accumulation', {})
    sealed = s.get('last_readout', {}).get('f6', {}) if s.get('state') == 'SEALED' else {}
    return {'n_lo_days_matured': acc.get('n_lo_days_matured'),
            'target': acc.get('target', 20),
            'state': s.get('state'),
            'ic_mean': acc.get('ic_mean'), 'ic_t': acc.get('ic_t'),
            'sealed_verdict': sealed.get('verdict'),
            'note': 'forward_readout.py n≥20 累计保留不动（不删不停，FR 系冻结）'}


def run():
    row = {'date': time.strftime('%Y-%m-%d'), 'ts': time.strftime('%F %T'),
           'main_track': main_track_read(), 'aux_track': aux_track_state(),
           'conflict_rule': CONFLICT_RULE}
    with open(OUT_F, 'a') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
    m, a = row['main_track'], row['aux_track']
    print(f"dual_daily: 主轨={m.get('overall', 'PENDING')} | "
          f"辅轨={a.get('n_lo_days_matured')}/{a.get('target')} {a.get('state')}")
    return row


if __name__ == '__main__':
    run()
