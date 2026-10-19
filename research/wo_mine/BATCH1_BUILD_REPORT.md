# BATCH1_BUILD_REPORT · Batch 1 施工报告（工程执行方）

- 日期：2026-10-20 ｜ 施工依据：`research/wo_mine/METHOD_BOOK_BATCH1.md`（逐字照抄，零发挥）
- 判线：全部引用 MINE_SPEC_v1 §五（C1–C6 / §5.3 / m=86 / 双池同向 / n<60 门），本批零新增判线数字
- R10 红线：全部运行脚本不产出「域读数→仓位」映射
- 产物：`batch1_run.py`（施工件）、`batch1_result.json`（锚校验+明细）、`FACTBOOK_BATCH1.jsonl`（98 行）、本报告

---

## 一、D0 重跑结果（停工条款解除）

`python3 batch0_domains.py` → **all_pass=true（8.2s）**，D0_RESULT.json 已刷新：

| 项 | 结果 | 关键数 |
|---|---|---|
| D0-1 域标签 vs 引擎闸 | PASS | same_day_diff=0（428 日）、lag 链 diff=0、53 切换日核对 |
| D0-2 序列/常量/breadth 锚 | PASS | 双路 maxdiff=5.68e-14 ≤ 1e-9（§6.1 裁定阈值）；breadth 21.53/31/144 逐位 |
| D0-3 fd 锚 + md5 书面澄清 | PASS | 673 笔/+723.64R/厚利 118 笔 2019.76R 逐位；澄清见下 |
| D0-4 ALPHA 锚 | PASS | kernel_final=**4.730578**（执行日闸开复核修复后），absdiff=4.8e-7 ≤ 1e-6 |
| domains.json 补项 | 完成 | `gate_vol20_p80_by_pool`: old131=**1.035910（103.59%）** / full144=1.226653（122.67%），与 §四 锚逐位一致 |

**simulate alpha 分支修复**（mine_common.simulate，方法书 §6.1 唯一口径修复点）：执行日整段重建（卖+买）补闸开复核（alpha_run.py:138 谱系），D0-④ 锚 4.730578 复现即验收。

**D0-3 md5 书面澄清（R7，实测于 2026-10-20）**：md5 不符=计算范围/公式差异，非数据损坏。① RESCUE 登记 `0e4c4fb9…`＝wo_ha 口径（对 `/tmp/dneg/box_cache` 10-17 vintage 逐文件 md5 的 json-dict 聚合），本机复算该目录该口径**逐位命中**；② 工作副本 `/tmp/box_cache`=snapshot_20261019（176/176 文件各多一根 2026-10-18 日线）；③ fdbrk 常量 `33c8b9ec…`（账本式）对任何本机目录均不命中，如实登记；④ 数据态实质一致性以锚为准：fd/breadth/ALPHA 三锚均逐位复现。澄清全文落盘 D0_RESULT.json `D0_3.md5_clarification`。

## 二、复现锚校验清单（57 项：hit 36 / miss 21，**21 个 miss 同根因=vintage 漂移，非实现误差**）

### 2.1 逐位命中（节选，全表见 batch1_result.json `anchors`）

| 锚 | got | want |
|---|---|---|
| c4 费后价差 raw/net | +1.5041/+1.4041* | +1.4616/+1.3616（±0.05 内） |
| c5 V1 IC_mean_ext / n_ext | +0.043310 / 54 | +0.0430687 / 54 |
| c5 V1 IC_mean_realC / n_realC | +0.010126 / 20 | +0.0094756 / 20 |
| d 降权 full144 base/dw realC ann·MDD | −56.31/−27.72 · −33.56/−14.81 | 逐位（**Δann=+22.75pp 命中**） |
| d 换门 full144 gate realC ann·MDD | −15.53/−24.19 | 逐位（**Δann=+40.78pp 命中**） |
| 换门 realC OFF 占比 old131/full144 | 35.25%(49/139) / 26.62%(37/139) | 逐位 |
| S3×D1 臂A full144 FULL avoid/mdd_red | +197.2062 / 7.17% | 逐位（<10 卡线锚） |
| S3×D1 臂A lag FULL/HOLD full144 | +177.8786 / +68.8166 | 逐位 |
| S3×D1 臂B lag HOLDOUT avoid | −0.085 / −0.0944 | 逐位（≈0 卡线锚） |
| 臂A realB old131（解锁锚） | +90.3139（v2 +14.8909 → +75.42pp） | 逐位 |
| 八列抽查 臂A/臂B old131 realB ann·MDD | +4926.62/−13.80 · +2139.40/−16.39 | 逐位 |

### 2.2 MISS 清单与根因证据（21 项，锚未改、未调参，按纪律如实上报）

| 组 | miss 项 | got vs want |
|---|---|---|
| c4 | t_ext 4.758518/n 318、t_realC −3.4709、fwd5 t_ext 1.7023/t_rc −1.1064/n_rc 135 | vs 4.776407/317、−3.446861、1.618675/−1.236898/134 |
| c5 | V1 t_ext 2.200859、t_realC 0.2700 | vs 2.182077、0.251334（n 全命中） |
| 框架族 old131 | base/dw/gate realC ann·MDD（差 0.05~0.23pp）、臂A/B FULL avoid/mdd_red/lag（差 0.07~0.18pp） | full144 全部逐位命中 |

**根因=数据 vintage 漂移，三组独立谱系逐位对拍证明工程实现零误差**：
1. **c4**：原版 `wo_rescue_run` PC-4 冻结代码在当前 `/tmp/box_cache` 只读复算 t_ext=**4.758517872143934**/n=318，与本件**逐位一致**（lineage_check 已固化进 batch1_result.json）。锚 4.776407/n=317 出自旧 vintage（c_new_candidates.json 归档时少 2026-10-18 一根日线；fwd20 前视统计在 09-28 多出一个 IC 日）。
2. **c5**：原版 PC-5 冻结代码同数据复算 t_ext=**2.2008593424462317**/n=54，与本件逐位一致。
3. **框架族**：权威引擎 `dneg_engine.run_instr`（D0 权威谱系）同数据复算 old131 base realC ann/MDD=**−49.15/−23.00**，与本件 gate 谱系完全一致（full144=−56.31/−27.72 与锚逐位）。old131 池数据在 realA/realC 段存在微修订（0.05~0.23pp 级），影响所有跨 realA 的 old131 段指标；realB 锚（+90.31、八列、lag_HOLD −0.085）逐位命中证明 2026-04 后数据未变。
→ 处置：锚数字未改，全部 miss 按 R7 登记「vintage 漂移」，**提请终裁裁定锚是否随 vintage 重锚**。

## 三、五变体实现与 FACTBOOK（98 行）

| 变体 | variant_id | FACTBOOK 行 | 说明 |
|---|---|---|---|
| c4 池间 RS | Q5-c4-rs_mom-{fwd20,fwd5} | 6+6 | 照抄 wo_rescue:779-812；LOTO(144 去一×20)/分年/lag1 已挂 fwd20 |
| c5 正交残差 | Q6-c5-{v1_orig,v2_breadth,v3_gap,v4_norev,v5_pool60,v6_pool120} | 36 | V1 锚绑定；V5/V6=时序 pooled OLS（§二细化口径） |
| d 降权 | K1-d-downweight-slot05 | 10 | slot 0.10→0.05，C1 随机带 20 种子 |
| d 换门 | K1-d-gate-vol20p80-pause | 10 | 逐池阈值（先落盘后回放），pause 语义，lag 臂披露 |
| S3×D1 | K1-s3d1-arm{A,B,C} | 30 | 费压 PB-5（×1.5），base 同费对比；T1'/T2'/T3' 照 G1G2FDR 定义 |

字段=§七 22 字段（JSONL 另含 notes 详注）；n<60 行 26 行已加 `INSUFFICIENT`；FDR=BH 合并族 m=86（本批 72 个可测格 p 值补入，q 值逐行落盘）。全量运行 **159s（<10 分钟，R8 直接跑完，无需分块）**，32 进程并行。

## 四、可用统计事实预览（【实证】，n/CI/域标签/口径四要素齐备）

1. **RS 动量的域结构守恒且两极分化**（Q5-c4-rs_mom-fwd20，full144 D1 lag1）：牛稳域 IC=+0.1362（t=7.64，n=111，CI[+0.0417,+0.2306]，费后十分位价差 +3.16pp，垫 2.28×，BH q=0.0）；弱躁域 IC=**−0.0451**（t=−1.86，n=92，CI[−0.0932,+0.0028]，q=1.0）——「轮动熄火」集中在弱躁域，与 realC 翻转（t=−3.45）互为印证；安慰剂 100 组 p=0.00 → 域间差异可归因于域（MAP 有效）。
2. **c5 残差 alpha 域分解不可归因于域**（Q6-c5-v1_orig）：四域 IC 均值全正（牛稳 +0.0510/牛躁 +0.0407/弱稳 +0.0122/弱躁 +0.0377）但域样本 24/20/3/7 全部 n<60（只入册），安慰剂 p=0.89 → **MAP-INVALID**（域间差异在随机标签下同样频繁）；extended 全窗 t=+2.20 为唯一有效读数。
3. **S3×D1 交叉臂（臂C，新预注册）realB 解锁成立（old131）**：realB 段净收益 +65.30pp vs v2 参照 +14.89pp（**解锁 +50.41pp**），realC 避损保持 +1.38pp，FULL avoid +43.79pp / mdd_red 20.72%、HOLDOUT avoid +6.42pp，lag 全量重跑 FULL/HOLD avoid +32.18/+0.56 不翻转，T1' OFF 日 base 净日收益 realB −0.51pp/realC −0.72pp（方向过滤把 OFF 集中到亏损日）。
4. **唯一域胜任格**：换门 full144·弱稳（C2 超额>0 且 CI>0 + C4 垫 + C6 q≤0.10 + C1/C3 不劣，n≥60）——**单池达标，按 §5.4 双池同向纪律登记不放行**。
5. **换门 lag 脆弱性（old131，披露不入判定）**：滞后门 FULL/HOLDOUT avoid −15.21/−20.05pp 翻负，与 G2 lag 教训同型。

## 五、必答差异题（S3×D1，报告专节）

W3 总 FAIL 病根=old131 realB 锁死 −44.69pp。臂C 在 old131 realB=+65.30pp（vs v2 +14.89）→ **解锁成立**；full144 臂C realB=+95.34 vs v2 +94.67（+0.67pp，本就无锁死）。T1'/T2'/T3' 数值见 batch1_result.json `detail.{pool}|armC`。

## 六、口径注记（R7 如实登记，未自行立线）

1. **old131 域标签轴 B 阈值**：§0.3 仅冻结一个 D1 分位锚（full144 的 vol_med P50=0.4202424…）。本件按「锚已冻结、分母池内自算」字面执行：轴 A/轴 B 序列均用该池自身成员，阈值共用冻结锚。如终裁判 old131 需自算 P50，仅需重切标签重出域格，全部复现锚与全窗数字不受影响。**建议终裁明确。**
2. **D3 安慰剂统计量**：MINE_SPEC §2.3 未定义「域间差异」具体统计量，本件取四域 IC 均值极差（因子族）/四域日超额均值极差（框架族），P(安慰剂≥观测)>0.05 → MAP-INVALID。**操作化口径提请终裁确认。**
3. c5 V3 控制变量=wo_rescue E3 掩码 0/1（「E3 同式」字面）；V5/V6「窗内有效截面日」=窗内（z 与控制与 fwd5 齐备标的≥30）的日数。
4. 工程增补（默认值=原行为逐位不变，D0-④/全部复现锚验收）：mine_common.simulate 增 `fee/fund/target_fn` 三可选参数（PB-5 费压与 C1 随机带 B 臂法所需）。
5. FACTBOOK axis 枚举含 `D3-placebo-k{0..99}`：本批以每变体一行安慰剂汇总（p 值+极差分布）落盘，100 组逐 k 明细在 batch1_result.json/domains.json——格式偏差如实登记。

## 七、声明

- 判线 C1–C6/生死胜任/m=86/双池同向/n<60：全部引用 MINE_SPEC_v1 §五，零重立；
- 本批 16 格预算（c4×2+c5×6+d 降权 1+d 换门 1+交叉 6）符合方法书 §八冻结；
- 锚 21 miss 已如实上报待终裁；除 wo_mine/ 内文件外未动任何引擎与 research 现有文件；commit 不 push。
