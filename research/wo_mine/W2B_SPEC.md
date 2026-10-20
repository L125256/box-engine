# W2B_SPEC — W2-B 两工单预注册规格（⑤费用真实化 · ⑥Gate 两市场价差序列入库）

- 文号：W2B_SPEC ｜ 立项：用户 L125256 批准 WAVE2（36 变体+2 工单），2026-10-20
- 执行实体：交易分析团队专家实体（单 agent 10 席位全席，首席策略官·何执舟终裁）。R1/R2/R4/R5/R7/R9 适用
- 性质：**只写规格不跑数**。两工单均为数据/对拍件，无生死判线；**引擎费常数改动=新工单交用户批准，本单只出对拍报告不改引擎**
- 配套：METHOD_BOOK_W2A.md（同目录）

---

## 工单⑤：费用真实化（费基实测替换 0.03%/bar 常数的对拍设计）

### 5.1 问题与现状（R2 出处）

- 引擎费常数：`research/wo_dneg/dneg_engine.py:34 FUNDING = 0.0003`（0.03%/bar，资金费占位常数）；fd 线 `research/wo_fdbrk/common_fdbrk.py:12 FEE = 0.03  # %/bar`。两处均为**未经实测锚定的常数**。
- 数据集缺口：`gate_funding_eq` 数据集被 `wo_regime/__pycache__/rg3_retest.cpython-311.pyc`（源码仅存 pyc，常量提取已核）引用，且需读 `_manifest.json`；`research/wo_w1/gate_funding/` 目录**存在但为空**——manifest 与数据落盘缺失（RG3 谱系「manifest 实测 2026-01 起」记录见 rg3_retest 头注常量）。

### 5.2 步骤一：修复 gate_funding_eq/_manifest.json 缺失（前置，不修禁跑对拍）

1. 数据源盘点（只读）：`research/wo_w1/raw/funding_death_archive.json`、`/workspace/repo_ready/.cache/box_cache/*.json` 内 per-symbol funding 字段、W1 台账（W1_REPORT.md / wo_w1_result.json）；**禁备源顶替**（RG3 先例：资金费数据缺席一律【数据受限】登记，不得用代理顶替）。
2. 重建数据集目录 `research/wo_w1/gate_funding/`：funding 日频 jsonl（逐 symbol：ts/symbol/rate）+ `_manifest.json`（必填字段：生成时间、数据窗起止、symbols 覆盖清单与计数、字段 schema、逐文件 md5、等权口径=140 标的费率等权 30 日滚动（rg3_retest 终裁口径，年化 ×252 单调变换对判线尺度不变）、生成脚本指纹、缺口登记）。
3. 完备性门：manifest 落盘后与 rg3_retest 引用键逐项对得上（gate_funding_eq/资金费 jsonl/_manifest.json 三件齐）；缺数据标的清单全量登记【数据受限】，不入费基均值（分母=有数标的数，如实标注）。

### 5.3 步骤二：费基实测对拍（本单核心交付，不改引擎）

- **实测费基序列**：`f_real(t) = gate_funding_eq 等权日费率序列`（30 日滚动，口径=§5.2-2 manifest 冻结值）；对照常数 `f_const = 0.03%/bar`（dneg_engine.py:34 / common_fdbrk.py:12 原值）。
- **对拍臂（三条曲线，费参数化已就位 mine_common.py:189-190，零引擎改动）**：
  | 臂 | 定义 | 对拍锚 |
  |---|---|---|
  | ctrl-fd | fd 原版出场冻结臂（V-FD-A/E2/refresh 逐字），分别以 f_const/f_real 重放 | meanR **1.1798**（n=1802，FD_REVIVE_SPEC §6-2）；快照 md5=33c8b9ec… |
  | base | dneg 谱系 base 曲线，双费基重放 | wo_w1/eng 谱系存档值（±0.05） |
  | armC 参照 | S3×D1 臂（batch1 逐字），双费基重放 | FULL_avoid 43.7883/69.7292 ±0.05 |
- **容差判读（冻结）**：每臂每池出三读数 Δ = |f_const 版 − f_real 版|（meanR、FULL avoid pp、年化 pp）；**ctrl 锚差 |Δ|≤0.05** = 费基不敏感（常数可用性成立）；任一 Δ>0.05 = 费敏感成立，报告须给敏感系数（Δ per 0.01% 费差）与受影响判读格清单（重点：K5/fd 系所有 meanR 读数与 D-A 复活五件套）。
- **产出**：`research/wo_mine/w2b_fee_calib_result.json` + `W2B_FEE_CALIB_REPORT.md`（结论三值：不敏感/敏感可控/敏感超限；附 manifest 内容与缺口清单全量）。
- **红线**：禁改 `dneg_engine.py`/`common_fdbrk.py`/任何引擎费常数——若费敏感成立，**另立引擎费常数修改新工单交用户批准**（本单只出报告）；禁以对拍结果回写任何已判读格的生死（已封印结果不改判，只登记敏感注记）。
- 算力预估：三臂×双费基×双池重放 ≈ **<30 分钟**（Pool(32)），含 §5.2 数据盘点确认。

## 工单⑥：Gate 两市场价差序列入库（EWZUSDT vs EWZ_USDT 日 K）

### 6.1 问题与现状

- 同一标的两种命名并存：本地缓存 `.cache/box_cache/EWZUSDT.json`（**无下划线**，实测 700 根日 K，2024-03-01 起，字段 time/open/high/low/close/volume）vs Gate 原始 API 命名 **EWZ_USDT**（带下划线）——命名不规范导致两源序列从未对齐对账（池级符号对账仅有 `research/wo_w1/raw/symbols_reconcile.json` 2026-10-18 快照，无标的级价差序列）。

### 6.2 规格（数据件，冻结）

1. **源定位**：EWZUSDT=box_cache 现货缓存（只读）；EWZ_USDT=Gate 原始 API 日 K（有网则拉取全历史，禁网则用 raw 缓存并在报告登记源与截至日，缺源=【数据受限】登记非死，R5）。
2. **对齐与价差序列**（按日 inner join，缺日单列）：
   - `abs_gap(t) = |close_A(t) − close_B(t)|`
   - `rel_gap_bp(t) = 200 × (close_A − close_B) / (close_A + close_B)`（对称相对价差，bp）
   - 复权/口径声明：两源均为原始日 K，若任一源含复权标记须在 manifest 声明并停机核对。
3. **低量日标注**：`low_liq = (volume == 0) OR (volume < 全样本 volume 的 P10)`，逐日 mark 落列；低量日价差单列统计（防低量日假价差污染均值）。
4. **描述统计（两序列并排）**：n、覆盖窗、mean/median/std、P5/P50/P95、max abs_gap 及其日期、rel_gap_bp 分位、低量日占比、|rel_gap_bp|>50（0.5%）日数、缺日清单全量。
5. **入库**：`research/wo_w1/gate_funding/gate_spread_EWZ.jsonl`（逐日行）+ `gate_spread_EWZ_manifest.json`（schema/md5/源声明）+ 报告 `W2B_GATE_SPREAD_REPORT.md`。
6. **完备性门（冻结）**：对齐日 n≥500 且 2025-06-01（realA 起点）后覆盖完整；不满足=登记缺口清单交付，不强行插值（禁 fill）。
7. 算力预估：**<10 分钟**。

### 6.3 查重与纪律

- 查重：symbols_reconcile.json 为池级 241→144 对账（wo_w1/raw），标的级价差序列入库为首次，无重复；W1 资金费工单（RG3 挂账）只共享数据目录，判线互不污染。
- 纪律：数据件无生死判线、无中间态表述；两工单产出均不改部署姿态（R10）；引用必附出处（R2）；缺数如实登记【数据受限】（R5）。

## 席位纪要 + 首席终裁（签署位）

| 席位 | 纪要 |
|---|---|
| 数据审计席 | manifest 缺失是 RG3 复活前置与本单共同病根，先修数据集再对拍，顺序不可倒；缺日禁插值已冻结 |
| 工程席 | 费参数化管线 mine_common.py:189-190 已就位，三臂重放零引擎改动；pyc 常量提取仅作出处证据，禁反编译恢复代码执行 |
| 风控席 | 费敏感若成立，所有 K5/fd 系 meanR 读数加敏感注记，但不改已封印判读（k1p70_verdict sealed 先例） |
| 记账席 | 对拍报告入 FACTBOOK 增量章；价差序列与 manifest 入 wo_w1 台账 |
| 合规席 | EWZ_USDT 拉取须声明源与截至日，禁网络时走缓存不顶替 |
| **首席策略官·何执舟（终裁）** | 批准两工单规格进入用户审批：⑤先修 gate_funding_eq/_manifest.json、后出双费基对拍报告，**引擎费常数改动另立新工单交用户批准，本单禁改引擎**；⑥价差序列按 §6.2 六步入库，完备性门 n≥500。待用户批准后开工。 |

## 待用户批准点

1. 批准本规格冻结（§5.2/§5.3/§6.2 全部口径与容差，批准即冻结）；
2. 批准两工单运行（合计 <40 分钟单机）；
3. 预授权确认：本单不含任何引擎费常数改动（改动走新工单）。
