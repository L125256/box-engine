# AUDITFIX_BATCH23_REPORT — 交易分析团队 Batch 2/3 金融逻辑审计终裁执行登记（2026-10-20）

执行依据：交易分析团队审计终裁处置清单（逐条照抄执行）。仓库 /workspace/repo_ready（main），
只动 batch2_run.py 相关修正与 wo_mine/ 产物；commit 不 push。

## ① Q1-touch-bounce-5/20【高·前视】——去前视修正重跑（缺陷修复配额各 1/1，禁第三次）

**缺陷**：原 `bounce_rate`（batch2_run.py）中 `nxt_up = C.shift(-1) > C` 与 `touch` 同日进入
N 日滚动和——t 日因子值包含当日触及的反弹结果，而该结果依赖 t+1 收盘，与 fwd5 前视窗重叠。

**修正 diff**：`good` 与 `hits` 整体 `shift(1)` 后再 `rolling(N).sum()`——t 日因子只用
t−N..t−1 的触及，最近一次反弹结果 C(t) vs C(t−1) 当日已知，无前视。

**同切分重跑**（D0 闸 all_pass 放行 → full Q1；重跑前后数字对照，IC=逐日截面 Spearman vs fwd5）：

| 变体·窗 | IC 前→后 | t 前→后 | n 前→后 | 价差(净pp) 前→后 |
|---|---|---|---|---|
| bounce-5 FULL | 0.073462 → **−0.010510** | 6.076 → **−0.953** | 285→284 | 1.4233 → 0.1721 |
| bounce-5 REALC | 0.073462 → −0.010510 | 6.076 → −0.953 | 285→284 | 同上 |
| bounce-5 牛稳 | 0.138097 → 0.034409 | 10.702 → 2.466 | 120→120 | 2.1215 → −0.3895 |
| bounce-5 弱稳 | 0.131619 → 0.083049 | 2.987 → 1.897 | 25→26 | −3.3347 → −0.5041 |
| bounce-20 FULL | 0.049764 → 0.024627 | 4.827 → **2.451** | 276→275 | 0.4910 → 0.2052 |
| bounce-20 牛稳 | 0.048046 → 0.017888 | 3.147 → 1.192 | 122→122 | 0.6515 → 0.4086 |
| bounce-20 弱躁 | 0.032469 → 0.012290 | 1.445 → 0.574 | 70→70 | −0.8295 → −1.5541 |

**结论**：去前视后 bounce-5 全窗 IC 由 +0.073（t=6.08）塌缩至 −0.011（t=−0.95）——原读数为
前视溢价，**原 IC/价差/CI/q 值全数作废**（前值仅存本报告与 git 历史）。FACTBOOK_BATCH2
两变体 12 行已刷新并注明【去前视修正版重算】。FDR（383 格全表）中 bounce-5 牛躁
0.0845→0.2245、bounce-20 弱躁 0.0414→0.1115 两格跌出 q≤0.10。

## ② Q2-ar1-hl-lev【中·公式】——OU 口径修正重算（原恒≈−1 读数作废）

**缺陷**：原实现对对数价格 AR1 斜率 φ_p 误用半衰期公式 −log2/log(1+φ_p)；φ_p≈1 时分母
log(2)，读数恒≈−1.06（t 高达 −884），量级失真。

**修正 diff**：新增 `hl_ou`，HL=−log2/log(φ_p)（OU 口径，φ_p∈(0,1)，审计书引用公式）。

**重算前后**（ic_mean 字段承载半衰期日数中位）：

| 域 | 前（恒≈−1）→ 后（OU 口径） | t 前→后 |
|---|---|---|
| 牛稳 | −1.056048 → 10.32849 | −592.16 → 34.41 |
| 牛躁 | −1.060148 → 9.261925 | −471.37 → 28.95 |
| 弱稳 | −1.064868 → 8.655323 | −286.77 → 20.22 |
| 弱躁 | −1.074414 → 7.379008 | −527.66 → 35.14 |
| FULL | −1.062027 → 9.258697 | −884.12 → 51.15 |
| REALC | −1.081723 → 6.645766 | — → 53.71 |

8 格（4 域 D1 + FULL + REALC 计 6 行/8 统计格）全部重算落 FACTBOOK_BATCH2；ATLAS 四格
judge 的 C2 腿由 False→True（IC 转正），但 C4（垫≥3×）仍不过 → 四态不变（不胜任/样本不足）。

## ③ Q2-ar1-hl-ret【低】——登记【口径存疑·量级失真】，不重算（按审计书倾向二选一）

OU 口径 −log2/log(φ) 下日收益 AR1 斜率 φ_ret→0（且可为负），半衰期量级不可比、大量 NaN；
原式 −log2/log(1+φ) 读数（牛稳 23.5 / 弱躁 9.05 日）仅可保序使用、不可作日数直读。
**执行登记**：FACTBOOK_BATCH2 行注与 batch2_run.py 变体描述均已标注【口径存疑·量级失真·
审计终裁③登记不重算】；重跑 Q2 时该变体数值逐位不变（确定性核对 6 行全 hit），仅加注。

## ④ Q3-rs-ew/med ×fwd5/20——不重跑，登记「预算虚耗」

分母（池等权/池中位 ret20）为逐日截面常数平移，Spearman 秩相关对平移不变 → ew 与 med
恒等式重复（FACTBOOK 在册四变体 ic_mean/ic_t/spread_net 逐位相同实证）。四变体退化为
**2 个有效变体**（Q3-rs-ew-fwd5/fwd20），原 4 行已合并标注【AUDITFIX 预算虚耗登记】
（24 行 = 4 变体 × 6 行），读数以 Q3-rs-ew-\* 为准。

## ⑤ K5-atr2/3——更名「固定 ATR 目标」，保留读数，不重实现

FACTBOOK_BATCH3 10 行（atr2/3 × 5 行）行注已加【AUDITFIX 终裁更名·固定 ATR 目标】：
预注册语义=ATR 跟踪式目标，本实现=固定倍数目标——**语义漂移登记在案**，读数保留、
判死结论不改、不重实现（终裁二选一之更名方案）。

## ⑥ ATLAS / FACTBOOK / FDR 刷新

- **受影响格**：重算期间按「待重算·挂起」处理不入图谱判分；重算完成后 ATLAS_v1 整体
  刷新一次（build_atlas 重读三 FACTBOOK 全量重判）。
- **ATLAS 四态计数**：刷新前 392 格=胜任 4 / 不胜任 129 / 样本不足 103 / 无效 156 →
  刷新后**完全相同**（4/129/103/156）；变化在格级读数与判定腿（hl-lev C2 False→True 等
  26 个受影响格字段更新，见上）。全纲领核验：非受影响格除 fdr_q 及其引用（one_line）外
  逐位一致，状态/判定零漂移。顶层增 `auditfix_note` 登记。
- **FDR m=86 合并表**：整体刷新一次——batch1+batch2 格 p=修正重跑后值，batch3 格 p 原值
  （未受影响），BH 全表重算：383 格中 q≤0.10 由 215 → **213**（跌出 2 格均为 bounce 修正格）；
  最大 q 漂移格 0.224543（bounce-5 牛躁）。FACTBOOK_BATCH3 D1 行 fdr_q 按新表刷新 76 行
  （batch3 判定腿 C6 用 p_one 非 q，格级状态不受影响）。
- batch2_result.json 增 `auditfix` 登记；d0_gate_batch2.json 两次放行（all_pass=True）。

## 纪律核验

- 重跑配额：Q1-touch-bounce-5/20 各 1 次（缺陷修复，1/1，禁第三次）✓；hl-lev 重算 1 次 ✓。
- D0 延续：两次 full 前均过既有 batch0_domains 四对拍锚（all_pass=True）✓。
- 确定性：Q2-ar1-hl-ret / Q2-hl-xdom-speed / Q2-hl-xdom-disp 等未受影响变体重跑后 18/18 行
  逐位一致（含 REALC/FULL 全字段）✓。
- R8：2 族重跑 + 表刷新，Q1 6.1s / Q2 5.2s / assemble <1s，分钟级 ✓。
- R10：全程未产出任何「域读数→仓位」映射 ✓。
- batch2_repl.py 抽样三变体（Q2-ac-lag1/Q3-rs-ew-fwd20/Q4-gap-unfilled-mom）均非修正对象，
  dual_impl 登记无需重跑 ✓。

## 修正 diff 摘要（batch2_run.py）

1. `bounce_rate`：`good`/`hits` 增 `shift(1)`（去当日 touch 前视重叠）。
2. `run_q2`：新增 `hl_ou(pm) = −log2/log(pm) (0<pm<1)`；`hl_lev = hl_ou(phi_p_med)` 替换原
   `hl(phi_p_med)`。
3. 变体描述同步：bounce-5/20 注【去前视修正版重算】；hl-lev 注【OU 口径·审计修正版】；
   hl-ret 注【口径存疑·量级失真·登记不重算】。

产物清单：FACTBOOK_BATCH2.jsonl / FACTBOOK_BATCH3.jsonl / FDR_MERGED_M86.jsonl /
ATLAS_v1.json / ATLAS_v1.md / batch2_partial_Q1.json / batch2_partial_Q2.json /
batch2_result.json / d0_gate_batch2.json（均 wo_mine/ 内）；本报告 AUDITFIX_BATCH23_REPORT.md。
