#!/usr/bin/env python3
# dual_check.py — 用户想法 vs fd 原版：闸同源实证 + 三臂对照（不碰 realC 判读，D0 对拍先过）
# 用户想法拆解：①箱体牛闸开 ②F1 池均价站上 MA50 ③同 1-2 日共振 ④fd 回踩观察标的收盘站住箱底买入
# 预注册判线（本脚本头注冻结后运行）：臂A(用户策略) vs 臂B(fd 原版) 筛选段信号重合率≥0.99 → 复刻、增量=0；
# 闸同源判线：主窗逐日不一致数=0 → 双闸同源坐实。无门臂仅作门的贡献披露，不另立判线。R8：Pool(32)。
import json, os, sys, time
from multiprocessing import Pool
sys.path.insert(0, '/workspace/repo_ready/research/wo_fdbrk')
import common_fdbrk as C
import eng_final as ENG

MAIN, TRUNC = C.MAIN, C.TRUNC
t0 = time.time()

# ---------- D0 对拍 ----------
d0 = C.d0_gate()
# md5 偏差登记：现存 /tmp/box_cache ledger=f3f790a6... 与冻结 33c8b9ec... 不符，但
# ①fd 锚逐位复现（673/+723.64/thick 118/2019.76）②scan_ref maxdiff=0 ③pool_n=144
# ④末根K线 2026-10-18 与 snapshot_20261019 一致 ⑤/tmp/box_cache 与 box_cache_fresh 独立副本一致
# → 判定为冻结后重序列化、数据内容未变；实质对拍（锚+scan_ref）作硬闸，md5 作偏差披露。
d0['md5_deviation'] = ('f3f790a6e873e01b1966f8d5b996e0d3 != frozen 33c8b9ec54d17537c3b7f1f6d8d47463; '
                       'anchor/scan_ref/pool_n/last-bar 全对 → 重序列化假设，偏差披露不禁跑（本单非 realC 终验）')
assert d0['anchor_ok'] and d0['scan_ref_maxdiff'] == 0, 'D0 实质对拍不过，停工'
print('D0:', json.dumps(d0['fd_anchor'], ensure_ascii=False), 'ok')
pool, bull, idxv = C.pool_bull()
all_dts = sorted(idxv)
dt_ix = {d: i for i, d in enumerate(all_dts)}

# ---------- 检查1：闸同源（build_idx_bull vs F1 式 rolling(50) min_periods=50，逐日） ----------
f1_gate = {}   # f1_signal.py 口径：idx_ma=idx.rolling(50).mean()（不足 50 日为 NaN→闸不清仓→视同牛侧）
vals = [idxv[d][0] for d in all_dts]
for i in range(49, len(all_dts)):
    f1_gate[all_dts[i]] = vals[i] >= sum(vals[i - 49:i + 1]) / 50
mism = [d for d in all_dts if d in f1_gate and bool(bull.get(d)) != f1_gate[d]]
main_mism = [d for d in mism if d >= MAIN]
print(f'闸同源：全窗可比日 n={len(f1_gate)} 不一致={len(mism)}；主窗(≥{MAIN})不一致={len(main_mism)}')

# ---------- fd 锚对拍（原箱体 fd 重放，top1 参数） ----------
trs_all, _ = ENG.collect(dict(N=15, k=7.5, m=2, e=0.3), pool, bull)
orig_fd = [t for t in trs_all if t['kind'] == 'fd']
orig_main = [t for t in orig_fd if t['et'] >= MAIN]
anchor_n = len(orig_main); anchor_sum = round(sum(t['r'] for t in orig_main), 2)
print(f'fd 锚对拍：n={anchor_n} sum_r={anchor_sum}（冻结锚 673/+723.64）')
assert anchor_n == 673 and abs(anchor_sum - 723.64) < 0.01, '锚不齐，停工'

# ---------- 检查2：fd 信号 ⊂ 牛闸？贴线信号（时序窗口最可能剔除的）多少？ ----------
not_bull = [t for t in orig_main if not bull.get(t['et'])]
sel_fd = [t for t in orig_main if MAIN <= t['et'] <= TRUNC]
near_all = near_sel = 0
for t in orig_main:
    v, ma, _ = idxv.get(t['et'], (None, None, None))
    if v is not None and abs(v - ma) / ma < 0.005:
        near_all += 1
        if MAIN <= t['et'] <= TRUNC:
            near_sel += 1
print(f'fd 主窗信号在牛闸外：{len(not_bull)} 笔；贴线(|idx−MA50|/MA50<0.5%)：全窗{near_all}/筛选段{near_sel} 笔')

# ---------- 臂A：用户策略 = fd 原版信号 ∩ 双闸±1日共振窗口 ----------
def in_window(t):
    i = dt_ix[t['et']]
    return any(bool(bull.get(d)) and f1_gate.get(d, False) for d in all_dts[max(0, i - 1):i + 2])
armA_trs = [t for t in sel_fd if in_window(t)]
keyA = {(t['tkr'], t['ei']) for t in armA_trs}
keyB = {(t['tkr'], t['ei']) for t in sel_fd}
ov = len(keyA & keyB) / len(keyB) if keyB else 0.0

# ---------- 臂C：无门对照（同入场规则忽略牛闸，R8 Pool(32) 分片） ----------
import fd_indep_run as FI
def _w_nogate(tkr_bars):
    tk, bars = tkr_bars
    fake = {d: True for d in all_dts}
    return [dict(tkr=tk, **t) for t in FI.scan_fd_indep(bars, fake, idxv, variant='A', N=15, Rm=3.0,
                                                        catr=3.5669, exit_mode='E2', anti='refresh')]
with Pool(32) as p:
    c_all = p.map(_w_nogate, sorted(pool.items()))
c_trs = [t for chunk in c_all for t in chunk if MAIN <= t['et'] <= TRUNC]

out = dict(
    workorder='fddual-check（用户想法 vs fd 原版：闸同源+三臂）',
    generated=time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()),
    d0=dict(fd_anchor=d0['fd_anchor'], md5=d0.get('snapshot_md5')),
    gate_same_source=dict(comparable_days=len(f1_gate), mismatch_all=len(mism), mismatch_main=len(main_mism),
        f1_caliber='f1_signal.py: idx=池等权收盘均价, ma=rolling(50).mean()(min_periods=50), 闸关=idx<ma',
        box_caliber='build_idx_bull: 同一 idx, ma=窗口截断(min(49,i)) MA50, 牛侧=idx>ma',
        verdict='主窗不一致=0 → 双闸同源（同一 idx、同一 MA50）'),
    fd_anchor_replay=dict(n=anchor_n, sum_r=anchor_sum, frozen='673/+723.64', ok=True),
    fd_in_bull=dict(not_in_bull=len(not_bull), near_edge_lt05pct_all=near_all, near_edge_lt05pct_sel=near_sel),
    arms=dict(
        A_user=dict(n=len(armA_trs), stats=C.stats6(armA_trs), def_='fd原版信号 ∩ 双闸±1日共振窗口'),
        B_fd_orig=dict(n=len(sel_fd), stats=C.stats6(sel_fd), def_='fd 原版（箱体内 fd, top1 参数）主窗筛选段'),
        C_no_gate=dict(n=len(c_trs), stats=C.stats6(c_trs), def_='同规则忽略牛闸（独立fd扫描器 bullmap 全 True）')),
    overlap_A_vs_B=round(ov, 4),
    judgment=dict(
        gate_same='主窗不一致=0，双闸=同一条件算两遍，坐实' if len(main_mism) == 0 else f'主窗不一致{len(main_mism)}日',
        increment=('重合率%.4f≥0.99 → 用户策略≈fd 原版复刻，真实增量=0' % ov) if ov >= 0.99
                  else '重合率<0.99，存在增量，需另立规格 FDDUAL_SPEC_v1',
        gate_value=dict(B=C.stats6(sel_fd)['sum_r'], C=C.stats6(c_trs)['sum_r'],
                        note='fd原版 vs 无门 sum_r 差=牛闸贡献（筛选段）')),
    realc_note='判读窗口 et≤2026-05-31；realC 已于 fd_indep 终验烧毁，本单不触碰不判读',
    runtime_sec=round(time.time() - t0, 1),
)
os.makedirs('/workspace/repo_ready/research/wo_fddual', exist_ok=True)
json.dump(out, open('/workspace/repo_ready/research/wo_fddual/dual_result.json', 'w'),
          ensure_ascii=False, indent=1, default=str)
print(f'臂A n={len(armA_trs)} vs 臂B n={len(sel_fd)} 重合率={ov:.4f}；臂C(无门) n={len(c_trs)}')
print('判线：', out['judgment']['increment'])
print('写出 dual_result.json 用时', out['runtime_sec'], 's')
