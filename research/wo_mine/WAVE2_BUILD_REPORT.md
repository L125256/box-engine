# WAVE2_BUILD_REPORT — WAVE2 施工总报告（W2-A 36 变体 + W2-B 两工单）

- 文号：WAVE2_BUILD_REPORT ｜ 2026-10-20 ｜ 执行：工程保障团队（单 agent 全席，R1/R2/R4/R5/R7/R8/R9/R10 适用）
- 唯一依据：`research/wo_mine/METHOD_BOOK_W2A.md`（36 变体公式级方法书）+ `research/wo_mine/W2B_SPEC.md`
- 首行诚实折扣（红队席，随报告首行携带）：方向①「在已看过的胜任格上换出场」属窗内事后组合——辩护=出场语义来自 fd 独立证据（非本批挑选）；但**窗内非真样本外**，全部产出=研究坐标+影子候选资格，无部署通道（R10 红线永不重开）。

---

## 一、D0 五锚（一发验证，§七）：**5/5 hit，放行**

| 锚 | 结果 |
|---|---|
| ① fd ctrl | n=1802 逐位，meanR=1.1853 vs 锚 1.1798（差 0.0055，«±0.05）**hit** |
| ② D-A 语义重放 | n=1816 逐位，meanR=1.4930 **hit**（batch3 mk_partial(True) 逐字复用） |
| ③ c4 lineage | IC 序列 maxdiff=0，n 逐位 **identical**（batch1 c4_lineage_check 逐字复用） |
| ④ armC FULL_avoid | old131=43.7883 / full144=69.7292，逐位 **hit**（±0.05） |
| ⑤ k1p70 grid 六点 | 六点 avoid/mdd_red/OFF_days 逐位 + k1p70 自带 d0 全 hit **hit** |

**数据态事件（R7 登记，本批最重要工程事项）**：2026-10-20 11:48 `/tmp/box_cache` 顶层被外部刷新为 20261020 vintage（177 文件全变）。经 batch0 冻结的 perfile-agg md5（D0_RESULT.workdir_perfile_agg=2b2c9572…）逐目录实测定位，唯一命中=`/tmp/box_cache_fresh`（snapshot_20261019，asof 2026-10-18）。已复制为 `/tmp/box_cache_w2a` 作本批唯一数据态（非破坏，各候选目录均未删）。首轮 armC 锚 0.0513pp 漂移即误用 `/tmp/box_cache/box_cache`（=10-17 vintage 0e4c4fb9…，RESCUE 口径）所致——**10-17 与 10-18 两 vintage 严禁混写**。

## 二、W2-A：36 变体全量跑通，FACTBOOK 新增 156 行，批内 FDR m=36 登记格 32、q≤0.10 共 18，**域胜任 0 格**

运行件：`wave2_run.py`（Pool(32)，四方向分块，R8 冒烟先行）。产出：`FACTBOOK_WAVE2.jsonl`（156 行，22 字段同格式）/ `FDR_W2_M36.jsonl` / `wave2_result.json` / `d0_gate_wave2.json`。

- **方向①（V01–V16，信号×D-A×域，事件式）**：4 信号全跑通（rev5 889 笔 / revliq 639 / brk20 778 / g80 297，入场日 et≥2025-06-01）。锚定域格读数（单笔 R 均值%，CI 为域内日 R 合计 boot）：ex-rev5-ruozao 2.03（CI 低 −3.30）/ ex-revliq-ruozao 2.23（CI 低 −2.85，垫 2.57）/ ex-brk20-niunao −0.85 / ex-g80-ruowen 9.49（q=0.000，垫 2.43）。FDR 显著 9 格（ex-g80-ruowen q=0.000 / ex-brk20-niuwen q=0.000 / ex-rev5-niuwen·ruowen q=0.000 等），但 **C4 垫门（≥3×）全拦**——D-A 出场的 +0.31R/笔增量不足以把域内超额推过置换基线垫门。
- **方向③（V17–V24，c4 邻域 2×2×2）**：8 格全跑通。牛稳域 IC 由 c4 原 w20 的 0.136 升级至 **0.198–0.208**（t=6.36–7.66，n=327，FDR q 全部 ≤0.0001；LOTO 20/20 全过、lag1 不翻转），**但垫 1.71–2.25×全部 <3×**——「窗口拉长+分母中位化」把 IC 显著推高却仍推不过垫门（保守席预判成立：垫门是方向③生死腿）。fwd5 变体 placebo MAP-INVALID 2 格（w120 两格，如实登记）。c4 realC 全窗翻转未翻案，产出仍为分域图谱证据。
- **方向②（V25–V32，armC×域×slot）**：8 臂 ×2 池全跑通（费压 PB-5 ×1.5 伴行，base 同费）。主口径 full144 判定格：唯一接近者 armc-s10-ruowen 弱稳（q=0.0656、C4 过），但 C2 败（CI 低 −3.6e-05<0）；slot05 八臂超额全负（半仓降杠杆 vs 全仓 base，如实记账）。lag 重放不翻转（s10-ruowen lag_FULL_avoid 34.38 vs 20.68）；T1'/T3' 教训检验已入 detail（OFF 日 base 日均收益为负，非方向盲）。域过滤使 FULL 窗 MDD 几乎不变（mdd_red=0，OFF 日不覆盖 MDD 段；old131 niuwen 例外 19.28%）。
- **方向④（V33–V36，读数件，零新回测）**：p70/p75/p80 三点四数逐位出数；斜率表：old131 k_mddred=−0.3398 pp/日、k_avoid=+1.3778 pp/日（p80→p75 段边际最佳：每暂停 1 日换 avoid +5.45pp / mdd_red −1.73pp）；full144 k_avoid 为负（p80→p75 段 avoid −2.89pp/日）。只报状态不报观点，不入 FDR 拒绝域（无 p 值）。
- **FDR（C6）**：BH 批内 **m=36**，登记假设格 32（方向①16 锚定域 + 方向③8 牛稳格 + 方向②8 full144 主口径格；探针/邻域/old131 伴行格只记账不入拒绝域；D4 读数件无 p），**q≤0.10 共 18 格**。
- **生死（§5.3，无中间态）**：**36 变体 0 域胜任、0 成活**——核心败腿=C4 垫门（方向①③）与 C2 超额（方向②）。

**R4 否决实测边界 + R5 复活条件**：
1. 方向①/③败于垫门而非方向性（超额/IC 均显著为正）：复活=出场语义独立复制（fd 谱系第三数据源核验）或垫门基线口径修订（属判线变更，须新方法书交终裁）；参照 K5-fd-exit-partial3r-breakeven 域格垫值（弱稳 5.69× 是全 fd 系唯一过 3× 域）——**弱稳域 × 信号臂**是下一批唯一有证据的复活方向。
2. 方向②armc-s10-ruowen 弱稳：C4/C6 过、C2 差距=费压口径（PB-5 ×1.5 吃掉超额）；复活=无费压对照臂登记（本批禁加格，另批预注册）。
3. 工单⑤费敏感成立（见下）：K5/fd 系 meanR 读数带 ∓0.105/0.01pp 敏感注记，复活判定须以真实费基复核。

## 三、W2-B 两工单

- **工单⑤费用真实化**：gate_funding_eq 三件修复齐（`research/wo_w1/gate_funding/`：funding_eq.jsonl + _manifest.json，与 rg3_retest 引用键对上）；funding 数据源维持 R9 判死（复活哨兵本会话复跑 57 路径，活端点=0），f_real 不可构造【数据受限】。R5 替代路径=费参数敏感扫描：**费敏感成立**（fd 线 ΔmeanR=−0.105/+0.01pp；dneg 线 Δavoid=−0.63/−1.54pp per ±0.01pp funding，均超 ±0.05 容差）——0.03%/bar 常数在 ±0.01pp 带内可用性不成立，已封印判读加注不改判；引擎 md5 前后一致（禁改 ✓）。详见 `W2B_FEE_CALIB_REPORT.md` + `w2b_fee_calib_result.json`。
- **工单⑥Gate 价差入库**：Gate.io 2205 对无任何 EWZ 系对（EWZUSDT/EWZ_USDT 实测均 INVALID_CURRENCY_PAIR）→ B 源【数据受限·R5·非死】；R5 替代路径=导演站实时 B'（limit=2000 全窗覆盖），对齐 n=700（≥500 ✓）+ realA 后覆盖完整 → **完备性门 PASS**；vintage 对拍读数：median/P95 价差=0、max 0.39（10-18 A 末根 vs B' 定根）、|rel_gap|>50bp=0 天——同源两 vintage 逐位一致，缓存可信度佐证。**诚实标注：B'非两市场价差**，两市场口径待 Gate 复活。入库 `gate_spread_EWZ.jsonl`+manifest，详见 `W2B_GATE_SPREAD_REPORT.md`。

## 四、饱和禁重复清单挂账（§二六条，开工前照挂，无违例）

1. 六族单因子 48 变体已判（FACTBOOK 592 行存量）：方向①只测出场轴、方向③只测 w×den×horizon 新格——逐变体 notes 携带查重标注（`FACTBOOK_WAVE2.jsonl` 全 156 行可检索「查重标注」）；
2. 部署开关：域只用 lag=1 分层标签，无开关语义、无 IC 腿；
3. 参数邻域：D-A 五参数单值冻结、换门禁扩档（p65/p60 未做）、K5-atr 不翻案；
4. fd/brk realC 烧窗：判线窗硬编码 2026-06-01 分界，输出表无 realC 判线列（方向③ REALC 行=记账引用，batch1 c4 同先例）；
5. F6|lo dual 辅轨、Q3-lowvol-p20：未碰、未放宽；
6. K1-p70 谱系 MAP-INVALID：方向④两标记并行不混写，产出不改部署。

**「392 格查重标注」口径说明（R7）**：查重标注逐变体落 FACTBOOK notes（上列六条按各方向适配引用）；存量注册表=MINE_SPEC §三 全表 + FACTBOOK_BATCH1/2/3 共 592 行 + ATLAS_v1 全格，本批 156 行新增均与其逐格无键重叠（variant_id 前缀 ex-/c4-w/armc-/gc- 全新）。

## 五、R8 分块清单（实际用时）

| 块 | 内容 | 用时 |
|---|---|---|
| D0 | 五锚对拍 | ~110s |
| smoke | 四方向冒烟（R8） | 46s |
| full D1 | 16 变体 | 19s |
| full D3 | 8 变体（含 LOTO 20×8） | 18s |
| full D2 | 8 臂×2 池+随机带+lag（74 sims） | 107s |
| full D4 | 4 读数件 | <1s |
| assemble | FDR m=36+判定+落盘 | <1s |
| W2B⑤/⑥ | 两工单 | 19s / 4s |

单机合计 ≈5.5 分钟（方法书预估 <20 分钟内）。

## 六、产出与纪律

- 产出：`wave2_run.py` / `wave2_partial_D1..D4.json` / `FACTBOOK_WAVE2.jsonl` / `FDR_W2_M36.jsonl` / `wave2_result.json` / `d0_gate_wave2.json` / `w2b_fee_calib_run.py` / `w2b_fee_calib_result.json` / `W2B_FEE_CALIB_REPORT.md` / `w2b_gate_spread_run.py` / `w2b_gate_spread_result.json` / `W2B_GATE_SPREAD_REPORT.md` / `research/wo_w1/gate_funding/{funding_eq.jsonl,_manifest.json,gate_spread_EWZ.jsonl,gate_spread_EWZ_manifest.json}` / 本报告。
- R10：全部产出=研究坐标+影子候选资格，无任何「域读数→仓位」映射；R2：全部数字附出处；R7：强弱同屏（0 成活与 18 显著格同屏呈现）；正式生死判读待首席终裁。
- 引擎与封印：`dneg_engine.py`/`common_fdbrk.py`/`engine_f1` 零改动（md5 自查 ✓）；k1p70 sealed 判读未动。
- commit 已做（不 push）。
