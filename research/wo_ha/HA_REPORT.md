# H-A 因子替换研究轨 · 执行报告（工程保障团队 · 施工+自测）

- 工单：H-A｜会期 2026-10-18｜规格（冻结）：`/tmp/trade9_specs/HA_SPEC.md` + `ha_spec.json`
- 引擎谱系：`research/wo_dneg/dneg_engine.py`（f1_backtest_v2 逐行 + 仪表化，W2-R14-G4 含 BUG-04 语义，止损 −8% 硬止损冻结）
- 筛选谱系：`/tmp/factor_screen/run_screen.py`（R3 因子席，因子计算段逐字复制为 `/tmp/ha_factor/r3_factor_ref.py`）
- 数据态：`/tmp/dneg/box_cache`（engine_snapshot 解包）＝`/tmp/box_cache` 逐文件 md5 一致（176/176，零漂移），逐文件聚合计账 `per_file_aggregate_md5 = 0e4c4fb9e487ff251639efa5fe06b05e`
- seed=42 冻结；并行 Pool(32)（R8）；分段 realA 2025-06-02→2026-03-31 / realB 2026-04-01→05-31 / realC 2026-06-01→10-17（两层口径伴行禁混用）
- 操作性定义 OD1–OD10 于开工写入执行脚本头注（`wo_ha_run.py`，跑后未改判据/X/Y/映射/seed/切点）

## 总判定

**H-A 按失败路径归档：Stage 1 存活仅 C1（mom_12m），Stage 2 realC 终验双池 FAIL（一次即烧），Stage 3 组合替换不触发。无候选进入组合。** 本单产出「候选因子证据基座」（C1–C10 全量 S1–S5 判据数字 + C5/C9 证据移交），非纯否定报告。复活条件 = 新评估段累积或制度性新证据（HA_SPEC 预注册）；H-D 状态门轨不受影响。

## Stage 0 对拍门 —— PASS（不过全停未触发）

| 项 | 结果 |
|---|---|
| md5 记账 | 176 文件 × 2 路径逐文件一致，drift=[]，聚合 md5=0e4c4f…b05e |
| 对拍 | mom_6m / atr_ratio_chg10 / rev_10d（取负后，冻结公式=反转符号）× 3 交易日（2024-06-03 / 2025-06-02 / 2026-05-29）maxdiff **= 0**（逐标的全截面比对） |
| C10 D0 可得性 | box_cache 字段仅 {time,open,high,low,close,volume}，无逐日资金费 → **C10 出局归档（禁换源）** |

## Stage 1 离线筛选（数据截断 2026-05-31，realC 零接触）—— 存活 **C1**

主 horizon fwd20（fwd10 辅），IC 日=截面 ≥30 名（run_screen 谱系）。逐判据（✓/✗）：

| 候选 | fwd20 IC | ICIR | bootstrap CI95 | S1 \|IC\|≥.03 且 \|ICIR\|≥.20 | S2 分年同号≥2/3 | S3 分位秩单调同号 | S4 IC 日 | S5 \|ρ\|≤.9 | 边界 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|
| **C1 mom_12m**（12-1，OD1） | **+0.1295** | **0.611** | [0.065, 0.198] | ✓ | ✓（2/2 年，2024 无样本=规格预写折扣） | ✓（Q1→Q5 严格单调） | ✓ 308≥250（discount 标记：无 2024，252 日预热） | ✓ vs mom_1m ρ̄=0.134 | ✓ vs dist_52w_high ρ̄=0.433（预写边界，max 0.716） | **PASS** |
| C2 mom_6m | +0.1104 | 0.461 | — | ✓ | ✓ 3/3 | ✗ Q2<Q1 微倒挂（0.0282<0.0363） | ✓ 434 | ✓ 0.432 | — | FAIL |
| C3 obv_slope60（OD2） | +0.0750 | 0.468 | — | ✓ | ✓ 3/3 | ✗ Q2<Q1 微倒挂 | ✓ 501 | ✓ 0.447 | — | FAIL |
| C4 atr_ratio_chg10 | +0.02998 | 0.209 | — | ✗（0.02998<0.03，差 2e-5 不救） | ✓ 3/3 | ✗ 非单调 | ✓ | ✓ | — | FAIL |
| C6 brk_vol_score（OD3） | +0.0380 | 0.282 | — | ✓ | ✓ 3/3 | ✗ 倒 V（Q4=0.0285 最低） | 事件型：事件数≥500 ✓（如实跑） | ✓ 0.095 | — | FAIL |
| C7 rev_10d（弱市条件臂 OD4） | −0.0544 | −0.255 | — | ✓ | ✓ 3/3 | ✗ Q3<Q4 倒挂 | ✓ 550 | ✓ −0.415 | — | FAIL |
| C8 gap_freq20（冻结 1% 口径） | +0.0262 | 0.122 | — | ✗ | ✓ 2/3（2024 翻脸 −0.070，规格预写"如实跑不救"应验） | ✓ | ✓ | ✓ | — | FAIL |

证据轨（不做替换臂）：
- **C5 vol_ratio**（冻结公式 5日均量/20日均量）：fwd20 IC=+0.0197 / ICIR=0.170 / CI 跨 0 —— 单独排序无结构，与 R3 证据一致；仅以 C6 突破确认形式生效（C6 本身 S3 出局）。
- **C9 breadth_above_ma50**：池等权 fwd20 时序 Spearman=+0.163（n=628）——与 R3 证据（+0.133）同向；状态因子不进四因子合成，**证据移交 H-D 状态门轨**。
- **C10 funding_pct60**：Stage0 可得性检查出局归档。

## Stage 2 F1 单因子替换回测（一次成活，realC 终验即烧）—— C1 双池 FAIL

基线臂=带闸 gated F1（OD7，生产口径）；替换臂=C1 mom_12m 替换 mom_1m，其余三因子不动；引擎逐行 dneg_engine 权威谱系；止损 −8% 硬止损（烧毁参数零触碰）。双池分别判定、双池全过才算过：

| 池 | 臂 | realA 年化 | realB 年化 | realC 年化 | P1 X（realC 改善≥+10pp） | P2 Y（realA 降幅≤5pp） | P3（realC 合成 fwd5 IC ≥基线+0.02） | 判定 |
|---|---|---|---|---|---|---|---|---|
| old131 | 基线 | +98.80% | +850.31% | −31.80% | — | — | IC=−0.00845（n=20） | — |
| old131 | C1 臂 | +85.59% | +1148.96% | −40.10% | **−8.31pp ✗** | **−13.22pp ✗** | diff=**+0.0000 ✗**（−0.00841 vs −0.00845） | **FAIL** |
| full144 | 基线 | +69.87% | +1550.94% | −36.93% | — | — | IC=+0.00403（n=20） | — |
| full144 | C1 臂 | +54.46% | +1148.96% | −31.84% | **+5.09pp ✗** | **−15.41pp ✗** | diff=**−0.0054 ✗** | **FAIL** |

- **realC 烧毁记账**：C1×双池各一次（backtest_realC + 合成 IC realC），台账在 `stage2_backtest.json.realC_burn_ledger`，未发生任何看完结果改参数再验。
- 判读：C1 与 mom_1m 同为动量族，替换后合成信号几乎不变（P3≈0），而 realC 段基线合成 IC 本身为负（−0.008/+0.004，与 D2 谱系 realC 一致），+10pp 的改善线在当段无可达路径；realA 段 mom_12m（12-1，剔除最近一月）相对 mom_1m 有 −13~−15pp 年化拖累（Y 判据双池爆线）。
- 如实呈报（口径副作用，非异常）：C1 替换臂 252 日预热 + 「四因子齐备才入池」规则使 full144 有效打分集收缩至老票子集，故两池替换臂 realB 年化同为 +1148.96%；两池差异仅剩 regime 闸所用池内 idx 不同。

## Stage 3 组合替换 + 既有闸门 —— NOT_RUN（书面归档）

Stage 2 双池全过者 = ∅ → 按规格「组合替换不触发」。LOTO / bootstrap 1000 / 随机带 500 seeds 因无组合可验而未消耗。归档记录：`stage3_combo.json`。

## 实现修正披露（均为 Stage2 终验前的实现层纠正，非判据修改）

1. **S2 分年同号率口径**：首版实现错把「三年齐备」作为前置（导致规格预写无 2024 样本的 C1 被误杀）。规格语义=同号率只计有样本年份（C1 失效边界明文"252 日预热，无 2024 样本（打折线）"），已修正并重跑 Stage1。修正前后 C1 的 S1/S3/S4/S5 全部不变；Stage1 全程零接触 realC。
2. **stationary bootstrap 块起点**：首版块起点连续推进（等价于原序列旋转，CI 退化为点值）。已改为新块起点独立均匀重抽（stationary bootstrap 标准构造），CI 随之有效（C1 CI=[0.065, 0.198]）。
3. Stage2 在 S2 修正后仅执行过一次（其输入=修正后 Stage1 存活集），realC 一次即烧未被重复消耗。

## 复现命令

```bash
cd /workspace/repo_ready/research/wo_ha
python3 wo_ha_run.py stage0   # 对拍门（maxdiff=0 + md5 记账 + C10 可得性）
python3 wo_ha_run.py stage1   # S1-S5 筛选（截断 2026-05-31）
python3 wo_ha_run.py stage2   # realC 终验（一次即烧，重跑仅复现同数）
python3 wo_ha_run.py stage3   # 组合闸门（本轮 NOT_RUN）
```

产物：`stage0_gate.json` / `stage1_screen.json` / `stage2_backtest.json` / `stage3_combo.json` / `wo_ha_run.py`；镜像 `/tmp/ha_factor/ha_results.json`；R3 参照模块 `/tmp/ha_factor/r3_factor_ref.py`（run_screen.py 因子段逐字复制）。

---

*证据分级：Stage0/Stage1/Stage2 表内数字均为【实证】（脚本落盘可复现）；「P1 在当段无可达路径」为【推断】；C9 移交价值判断归 H-D 轨。席位论证不单独流出，本报告 + 4 份 stage json 为唯一交付。*
