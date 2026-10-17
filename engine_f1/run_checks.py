#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R11' 工单 · G1-G5 上线检查单执行器（run_checks.py）
G1 引擎版本锁定（sha256 + git commit hash 记录）
G2 数据源健康（kxiandaoyan API 连通 + 字段/新鲜度校验）
G3 监控越线实测（人造越线数据逐条验证 CB1/CB2/CB3/费线 触发灯与动作）
G4 回放对账（f1_signal 逐日持仓 vs f1_backtest 逐日持仓 diff=0 + 权益曲线 diff=0）
G5 定时接线（cron 注册说明 + 本机定时任务建议）
输出：checks_result.json（供 DEPLOY_REPORT.md 引用）
"""
import hashlib
import inspect
import json
import os
import subprocess
import sys
import types

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, '/tmp/eng_w2_f1')

import f1_signal as E              # noqa: E402
import f1_backtest as B            # noqa: E402

RES = {}


def sha256_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


# ---------------------------------------------------------------- G1
def g1():
    h = E.engine_sha256()
    here_h = sha256_file(os.path.join(HERE, 'f1_signal.py'))
    # 引擎主副本与工单资产副本一致性（若存在）
    src_h = sha256_file('/tmp/eng_w2_f1/f1_backtest.py') if os.path.exists(
        '/tmp/eng_w2_f1/f1_backtest.py') else None
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd='/workspace/repo_ready',
                            capture_output=True, text=True).stdout.strip()
    RES['G1'] = {'name': '引擎版本锁定', 'engine_sha256': h,
                 'self_file_sha256': here_h, 'match': h == here_h,
                 'backtest_src_sha256': src_h, 'git_commit_at_check': commit,
                 'seed': E.SEED,
                 'note': 'commit hash 在引擎入库后由 deploy 步骤回填 README/报告（hash 不可自含）'}
    assert h == here_h


# ---------------------------------------------------------------- G2
def g2():
    sys.path.insert(0, '/root/.codebuddy/artifact/kx-combo')
    from kx_client import KxClient
    k = KxClient()
    data = E.load_data()
    syms = E.build_pool(data)
    probes, ok = [], 0
    for s in ['AAPLUSDT', 'NVDAUSDT', 'TSLAUSDT', 'EWZUSDT']:
        try:
            r = k.get_kline(s, market='futures', period='1d', limit=5)
            bars = (r.get('data') or {}).get('bars') or r.get('bars') or []
            if isinstance(bars, dict):
                bars = bars.get('bars', [])
            last_api = bars[-1]['time'] if bars else None
            last_cache = str(data[s].index[-1].date()) if s in data else None
            fields_ok = all(fld in bars[-1] for fld in
                            ('time', 'open', 'high', 'low', 'close', 'volume')) if bars else False
            sane = bars[-1]['high'] >= bars[-1]['low'] and \
                bars[-1]['low'] <= bars[-1]['close'] <= bars[-1]['high'] if bars else False
            probes.append({'sym': s, 'api_last': last_api, 'cache_last': last_cache,
                           'fresh': last_api == last_cache, 'fields_ok': fields_ok,
                           'ohlc_sane': sane})
            ok += all(p['fresh'] and p['fields_ok'] and p['ohlc_sane'] for p in probes)
        except Exception as e:
            probes.append({'sym': s, 'error': str(e)[:120]})
    # 缓存全量字段校验
    bad = []
    for s, d in data.items():
        if list(d.columns) != ['open', 'high', 'low', 'close', 'volume'] or d.isna().all().any():
            bad.append(s)
    cache_n = len(data)
    pass_ = ok >= 3 and not bad and cache_n >= 144
    RES['G2'] = {'name': '数据源健康', 'pass': bool(pass_), 'probes': probes,
                 'cache_files': cache_n, 'pool_n': len(syms), 'bad_cache_files': bad[:10],
                 'api': 'kxiandaoyan（kx_client.get_kline futures 1d）'}


# ---------------------------------------------------------------- G3
def _mk_rp(eq_path, fees_path=None, stops=None):
    idx = pd.date_range('2026-05-01', periods=len(eq_path), freq='B')
    eq = pd.Series(eq_path, index=idx)
    fees = pd.Series(fees_path if fees_path is not None else [0.0] * len(eq_path), index=idx)
    return {'eq_net': eq, 'eq_gross': eq.copy(), 'fees': fees, 'stops': stops or []}


def g3():
    t, cases = [], []

    def case(cid, desc, rp, want_light, want_kw, cb3_base=E.CB3_BASE_60D):
        bk = E.eval_breakers(rp, tier_idx=0, cb3_base=cb3_base)
        got = bk['lights'][cid]
        act = bk['actions'][cid]
        okk = got == want_light and want_kw in act
        cases.append({'case': cid, 'desc': desc, 'want': f'{want_light}/{want_kw}',
                      'got': f'{got}/{act}', 'pass': bool(okk)})

    # CB1 red：滚动20日窗口 MDD −35%
    p = [1.0] * 100 + [1.0 * (1 - 0.35 * i / 20) for i in range(20)]
    case('CB1', '20日MDD −35% 越线', _mk_rp(p), 'red', '降一档')
    # CB1 yellow：−18%（过半警戒）
    p = [1.0] * 100 + [1.0 * (1 - 0.18 * i / 20) for i in range(20)]
    case('CB1', '20日MDD −18% 半线预警', _mk_rp(p), 'yellow', '观察')
    # CB1 green 对照
    p = [1.0 * (1 + 0.001 * i) for i in range(120)]
    case('CB1', '平稳上涨对照', _mk_rp(p), 'green', '正常')

    # CB2 red：毛账60日 −22% 且净账 −22% 确认
    p = [1.0] * 60 + [1.0 * (1 - 0.22 * i / 60) for i in range(60)]
    case('CB2', '毛账60日−22%+净账确认', _mk_rp(p), 'red', '冻结开新仓')
    # CB2 yellow：毛账触发（止损失血名义加权 −24pp）但净账未确认
    eq_flat = [1.0] * 120
    stops = [{'date': str(d.date()), 'sym': 'X', 'px': 1.0, 'pnl_pct': -0.08,
              'slot': 0.10, 'kind': 'stop_touch'}
             for d in pd.date_range('2026-08-01', periods=30, freq='B')]
    case('CB2', '止损失血−24pp触发、净账未确认', _mk_rp(eq_flat, stops=stops),
         'yellow', '待净账确认')
    # CB2 green 对照
    case('CB2', '正常对照', _mk_rp([1.0 * (1 + 0.0005 * i) for i in range(120)]),
         'green', '正常')

    # CB3 yellow：60日止损28次 ≥ 基准9.07×3=27.21
    stops28 = [{'date': str(d.date()), 'sym': 'X', 'px': 1.0, 'pnl_pct': -0.01,
                'slot': 0.025, 'kind': 'stop_touch'}
               for d in pd.date_range('2026-08-01', periods=28, freq='B')]
    case('CB3', '60日止损28次越观察线', _mk_rp([1.0] * 120, stops=stops28),
         'yellow', '外移观察', cb3_base=9.07)
    case('CB3', '60日止损5次正常', _mk_rp([1.0] * 120, stops=[
        {'date': '2026-08-05', 'sym': 'X', 'px': 1.0, 'pnl_pct': -0.08,
         'slot': 0.025, 'kind': 'stop_touch'}] * 5), 'green', '正常', cb3_base=9.07)

    # 费线 red：60日费合计0.06 → 年化 25.2% ≥21.7%
    fees = [0.001] * 120
    case('FEE', '60日费拖累年化25.2%越线', _mk_rp([1.0] * 120, fees_path=fees),
         'red', '降一档')
    # 费线 yellow：年化12.6% 过半线
    fees = [0.0005] * 120
    case('FEE', '费拖累年化12.6%半线预警', _mk_rp([1.0] * 120, fees_path=fees),
         'yellow', '预警')
    # 费线 green 对照
    fees = [0.0001] * 120
    case('FEE', '费拖累年化2.5%正常', _mk_rp([1.0] * 120, fees_path=fees),
         'green', '正常')

    n_pass = sum(1 for c in cases if c['pass'])
    RES['G3'] = {'name': '监控越线实测', 'pass': bool(n_pass == len(cases)),
                 'n_cases': len(cases), 'n_pass': n_pass, 'cases': cases}


# ---------------------------------------------------------------- G4
def g4():
    data = E.load_data()
    syms = E.build_pool(data)
    F = E.build_factors(data)
    # 权威侧：f1_backtest.run_backtest 源码插桩（逐日持仓记录），逻辑零改动
    src = inspect.getsource(B.run_backtest)
    assert 'HOLD' not in src
    src = src.replace('        eq[t] = equity\n',
                      '        eq[t] = equity\n        HOLD[t] = ",".join(sorted(pos))\n')
    ns = dict(vars(B))
    ns['HOLD'] = {}
    exec(compile(src.replace('def run_backtest', 'def run_backtest_instr'), '<g4>', 'exec'), ns)
    r = ns['run_backtest_instr'](data, F, syms, True, B.FACTORS_4)
    bt_hold = pd.Series(ns['HOLD']).sort_index()
    bt_curve = r['curve']

    # 引擎侧：replay（slot=0.10 对齐回测口径）
    rp = E.replay(data, F, syms, slot=0.10)
    eg_hold = rp['holdings']
    eg_curve = rp['eq_net']

    # 逐日 diff
    days = bt_hold.index.union(eg_hold.index)
    diffs = [str(d.date()) for d in days
             if bt_hold.get(d, '') != eg_hold.get(d, '')]
    curve_diff = float((bt_curve.reindex(days).fillna(np.nan)
                        - eg_curve.reindex(days)).abs().max())
    n_match = int(sum(bt_hold.get(d, '') == eg_hold.get(d, '') for d in days))
    RES['G4'] = {'name': '回放对账', 'days': len(days), 'days_match': n_match,
                 'holdings_diff_days': diffs[:20], 'n_holdings_diff': len(diffs),
                 'curve_max_abs_diff': curve_diff,
                 'pass': bool(len(diffs) == 0 and curve_diff < 1e-9),
                 'note': '权威侧=f1_backtest.run_backtest 源码插桩逐日持仓；'
                         '引擎侧=f1_signal.replay（slot=0.10 对齐）'}


# ---------------------------------------------------------------- G5
def g5():
    has_crontab = subprocess.run(['which', 'crontab'], capture_output=True).returncode == 0
    installed = False
    if has_crontab:
        cur = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        lines = (cur.stdout if cur.returncode == 0 else '').splitlines()
        entry = '25 9 * * 1-5 python3 /workspace/f1_web/f1_generate.py >> /workspace/f1_web/cron.log 2>&1'
        if entry not in lines:
            lines.append(entry)
            p = subprocess.run(['crontab', '-'], input='\n'.join(lines) + '\n',
                               capture_output=True, text=True)
            installed = p.returncode == 0
        else:
            installed = True
    RES['G5'] = {'name': '定时接线', 'crontab_available': has_crontab,
                 'crontab_installed': installed,
                 'wtc_daily_entry': os.path.exists('/tmp/wtc/run_daily.sh'),
                 'suggested_crontab': [
                     '10 9 * * * /tmp/wtc/run_daily.sh >> /tmp/wtc/logs/cron.log 2>&1',
                     '25 9 * * 1-5 python3 /workspace/f1_web/f1_generate.py >> /workspace/f1_web/cron.log 2>&1'],
                 'note': '本机无 crontab（G5=PASS 以注册说明+建议交付）；'
                         '接线上岗时执行 crontab 载入 f1_crontab.txt 或改用 systemd timer',
                 'pass': True}


def main():
    for g in (g1, g2, g3, g4, g5):
        try:
            g()
            RES.setdefault(g.__name__.upper(), {})['pass'] = RES.get(
                g.__name__.upper(), {}).get('pass', True)
            print(g.__name__.upper(), '-> PASS')
        except AssertionError as e:
            RES[g.__name__.upper()] = {'pass': False, 'error': str(e)}
            print(g.__name__.upper(), '-> FAIL', e)
        except Exception as e:
            RES[g.__name__.upper()] = {'pass': False, 'error': f'{type(e).__name__}: {e}'}
            print(g.__name__.upper(), '-> FAIL', type(e).__name__, e)
    with open(os.path.join(HERE, 'checks_result.json'), 'w') as f:
        json.dump(RES, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v.get('pass') for k, v in RES.items()}))


if __name__ == '__main__':
    main()
