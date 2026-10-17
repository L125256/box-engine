# R13 四工单施工报告（工程保障席）

- 日期：2026-10-18 · seed=**42**（全部命令带 `PYTHONHASHSEED=42`）
- 依据：`/tmp/fourseat_r13/verdict.md`（含附录 A 口径书草稿）+ `work_orders.json` + `breaker_stats.json`
- 产物目录：`/workspace/repo_ready/engine_f1/`（权威）、`/workspace/repo_ready/f1/`（归档副本）、`/workspace/f1_web/`（线上页面+数据）
- 状态：**已 commit，未 push**，等审计+测试席 → 交易团队复分析 → 用户授权发版

---

## 一、工单结果一览

| 工单 | 结果 | 一句话 |
|---|---|---|
| WO-R13-01 熔断线重标定（P1） | **DONE** | CB1 −8%/−4%、CB2 −5pp/−2.5pp、费线 4pp/2pp 写入常量与 `meta.breaker_thresholds`；页面全读 JSON |
| WO-R13-02 台账口径落库（P1） | **DONE** | `F1_台账口径_v1.md` 五节齐全，阈值表已用重标定后新值 |
| WO-R13-03 多轮只读旁路（P2） | **DONE** | `snapshot` 只读模式 + 部分K guard + 推送去重 + 可注册时刻表（DST 标注） |
| WO-R13-04 数据源容灾（P2） | **DONE** | 分层判死 + 三态状态机 + 新浪白名单 adapter + 验收切回 + 事件日志 |

---

## 二、WO-R13-01 · 熔断线重标定

### 2.1 常量改动（`f1_signal.py`）

| 常量 | 旧 | 新 | 依据 |
|---|---|---|---|
| `CB1_MDD` | −0.32 | **−0.08** | 实测极值 −6.64%（2026-05-19）×1.20 |
| `CB1_WARN` | （隐式 /2） | **−0.04** | R13 改显式常量 |
| `CB2_LOSS` | −0.20 | **−0.05** | 实测 `stop_pnl60` −4.73pp ×1.06 |
| `CB2_WARN` | （隐式 /2） | **−0.025** | R13 改显式常量 |
| `FEE_LINE_ANN` | 0.217 | **0.04** | 满周转手结构上限 ≈4.1pp |
| `FEE_WARN` | （隐式 /2） | **0.02** | 取红线之半 |
| `CB3_BASE_60D` / `CB3_MULT` | 9.07 / 3 | **不动** | 唯一活线，基准无漂移 |
| `CALIB_EPOCH` | — | **`R13-2026-10-18`** | 换批即清空 `prev_reds` |

判定符未改：CB1/费线 `<=`/`>=` 含等号；CB2 毛触发与净确认同线同号。

### 2.2 阈值单一事实源 + 页面读 JSON

- 新增 `breaker_thresholds()` → 写入 `f1_live.json → meta.breaker_thresholds`
  （含 name/red/yellow/window/action/metric）。
- 页面 `index.html`：
  - CB1 卡片文案 `≤−8% 降一档；≤−4% 黄灯观察` 全部由 `T.CB1.red / T.CB1.yellow` 渲染；
  - CB2 卡片阈值由 `T.CB2.red / T.CB2.yellow` 渲染；
  - CB3 观察线由 `T.CB3.line` 渲染；
  - 费线由 `T.FEE.red / T.FEE.yellow` 渲染；
  - 顶部新增徽标「熔断阈值：R13-2026-10-18 重标定 · 12.5% 敞口口径」。
- 断言（测试席）：`HTML 无 21.7/10.85 字面量`，且阈值文本随引擎常量变化（E8/T8 渲染级 PASS）。

### 2.3 重标定后真实段回放触发次数（核心交付）

口径：真实缓存全量回放（2024-01-24 → 2026-10-17），统计窗 **2025-06-02 → 2026-10-17（428 交易日）**；
与引擎 `eval_breakers` 同源（`_roll_mdd`、滚动 60 日双账）。

| 线 | 🔴 红灯天数 | 🟡 黄灯天数 | 首次触发 | 历史解释 |
|---|---|---|---|---|
| **CB1 回撤闸**（20日净账 MDD ≤ −8%） | **0** | **18** | 2026-05-15（黄） | 2026-05-15~06-01 连续 18 日过 −4% 黄线；极值 −6.64%（05-19）距红线 −8% 尚差 1.36pp，故红灯 0 次（verdict 已允许 0 次并说明） |
| **CB2 止损闸**（60日 ≤ −5pp，毛触发+净确认） | **5** | 0 | 2026-07-07（红） | 2026-07-07/08/09/10/12 共 5 日毛账失血 −7.38% 且净账 −7.52% 双双越 −5pp；按动作=冻结开新仓 20 交易日 |
| **CB3 频次观察**（60日 ≥ 27.21 次） | —（永不红） | **0** | 无 | 极值 21 次 < 27.21；**与改前一致**（基准 9.07 冻结、无漂移） |
| **费线 费用闸**（60日折年化 ≥ 4pp） | **0** | **0** | 无 | 实测年化峰值 1.6pp（p99 1.57pp）距黄线 2pp 仍差 25% |

对照：**旧阈值下四条线红/黄灯天数全部为 0**（结构性死线复核一致）。

**⚠️ 如实标注（不粉饰）**：费线按 WO 指定的 4pp/2pp 重标定后，在 12.5% 敞口 +
现行费率（滑点 0.05%/边、资金费 0.03%/bar）下**仍为 0 触发**——
因为满周转手年化拖累的理论上限仅 ≈4.1pp，实测 1.6pp。该线只有在敞口上调或费率上浮时
才可能触发。已按规格保留刻度并在 `meta.calib_note` 标注「阈值随敞口走」。
建议交交易团队复分析时确认是否接受「费线=结构性弱活线」。

- 结果文件：`engine_f1/breaker_stats_r13.json`（含 old/new 双列 + 触发日期明细）
- 复现：`PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/replay_breakers_r13.py`

### 2.4 验收对照

- ① 新阈值下 CB1 黄 18 次、CB2 红 5 次，历史可解释；CB1 红灯 0 次（verdict 明示允许并已说明）→ **PASS**
- ② CB3 触发统计与改前一致（0/0）→ **PASS**
- ③ live sha256 更新（`9c5590b3…`/现 `ae92dfaf…`），**月报三本账 12 行与改前逐位一致** → **PASS**
  （`signal/breakers/state/monthly_accounts` 逐字段比对 identical=True）

---

## 三、WO-R13-02 · 《F1 台账口径》v1 落库

- 文件：`/workspace/repo_ready/engine_f1/F1_台账口径_v1.md`（生效日 2026-10-18）
- 五节齐全：
  1. **引擎身份**：引擎/sha256 锚/版本/seed=42/池 144/idx/四因子/调仓/仓位/闸/熔断/费/口径锁
     —— 熔断阈值表**已用 WO-R13-01 重标定后新阈值表**（含窗口、动作、重标定依据）
  2. **推荐规则**：买（信号日 + 闸开 + 未冻结 + 总灯非红）/ 卖（止损·崩市·闸转持币·换出·红灯动作）/
     等（非信号日·冻结期·持币·asof 非当日落定）；**用户执行价 = 次日开盘价**（开盘附近限价单）
  3. **四条禁令**（脱离引擎自由推荐 / 盘中数字替代落定信号 / idx 回撤当账户回撤 / 无 sha256+asof 输出）
  4. **数据出身标注义务**（asof + sha256 前缀 + 数据窗末 + 数据源 + 模式；备源仅「抽查参考」）
  5. **冲突裁决**（引擎 > 记忆；sha256 不符即停；口径与源码冲突以源码为准并触发修订工单）
- 阈值表已同步回填口径书 §一.8（旧阈值标注「已废止，禁止再引用」）。

---

## 四、WO-R13-03 · 多轮扫描「展示多轮、判定一轮」

### 4.1 只读盘中快照 `f1_signal.py snapshot --round {20:30|00:30|04:30}`

做：① 当前持仓浮动盈亏（含止损价、距止损距离、逼近提示 `stop_near≤2%`）
② 熔断预演（**只用已落定日K**）③ 崩市池中位跌幅**预估**（标注未落定）
不做：**不写 `f1_state.json`**、**不覆盖 `f1_live.json` 任何判定字段**、**不出 top5 建议**、
不做周调仓锚定与任何调仓决策。
输出 → `/workspace/f1_web/f1_live_intraday.json`，
`meta.mode='intraday_snapshot'`、`meta.operable=false`、`writes={f1_state.json:false, f1_live.json:false}`。

### 4.2 防部分K污染 guard

- `guard_last_bar(cal, now=None)` →
  `settled = 最后一根 bar 日期 < 当前 UTC 日期`；否则标记 `intraday` 并给出拒绝理由。
- 入口校验：`run_live` / `current_signal` 未落定即 **抛 RuntimeError 拒绝判定**并写
  `f1_guard.log`（JSONL append-only）。
- 自测 R9/R10 二态 PASS：落定后 `settled=True`，当日 bar `settled=False` 且拒绝判定。

### 4.3 推送去重

- `push_plan(mode, asof, round_id, last_push)`：
  判定轮按 `decide:<asof>` 去重；盘中轮按 `intraday:<asof>:<round>` 去重，
  且 `carries_decision=false`、label=「盘中快照·不可操作」。
- 自测 R13 PASS：同日 4 轮（1 判定 + 3 盘中）无重复判定推送。

### 4.4 多轮时刻说明（含夏令时标注）

文件：`engine_f1/f1_rounds_r13.md` + 注册条目 `engine_f1/f1_crontab.txt`

| 时刻(北京) | UTC | 美股语义 | 模式 |
|---|---|---|---|
| 20:30 | 12:30 | 盘前（夏令时开盘前约 1 小时） | 只读 |
| 00:30 | 16:30 | 盘中（夏令时约 12:30 ET） | 只读 |
| 04:30 | 20:30 | **夏令时=收盘后 30 分钟；冬令时=收盘前 30 分钟** | 只读 |
| 09:25 | 01:25 | 日K已落定 | **判定轮** |

- 北京无夏令时（时刻全年固定）；美股夏令时窗口 = 3 月第二个周日 ~ 11 月第一个周日。
- 04:30 轮随 DST 漂移，页面按窗口改标签（引擎常量 `INTRADAY_ROUNDS['04:30'].semantic`、`DST_NOTE`）。
- 09:25 与 08:30 读同一根已落定日K，**二选一**（当前保留 09:25）。

---

## 五、WO-R13-04 · 数据源容灾

### 5.1 主源健康检查 + 判死（分层）

- 单次失败判定：连接超时 >5s / 读超时 >15s / HTTP≠200 / JSON 解析失败 /
  schema 校验失败（必需字段缺失、标的数 <144、字段类型错、OHLC 不合理）/
  数据过期（最新 bar 落后预期交易日 >1 天）。
- 单轮内重试 3 次（间隔 30s；演练用 `F1_RETRY_SLEEP=0` 加速）→ 全败记 1 个「周期失败」。
- **连续 2 个周期失败 → 判死切备源**（常量 `FAIL_PERIODS_TO_DEGRADE=2`）。
- 人造故障注入：环境变量 `F1_PRIMARY_FAIL=1`（仅测试用）。

### 5.2 三态状态机

`NORMAL → DEGRADED → RECOVERING → NORMAL`

- 落盘 `f1_source_state.json`（state / consec_fail / consec_ok / frozen_asof / pending_manual / history）
- 事件日志 `f1_source_events.log`（JSONL，含 DEGRADE / RECOVERING / RECOVERED / RECOVER_PENDING_MANUAL / SINA_FETCH_FAIL）

### 5.3 降级行为（两条红线）

- **新浪不做 144 全量**：`fetch_sina_daily()` 入参 >`MAX_PROXY_SYMBOLS=6` 直接抛 `ValueError`
  → 代码里不存在全量路径。
- **降级期不出新信号**：`run_live` 探测到 DEGRADED/RECOVERING → 走 `_emit_frozen()`，
  只补 `meta.source` / `meta.data_source` / `signal.operable=false` / `writes` 标注，
  **判定字段（signal/breakers/state/monthly_accounts）逐位不动，且绝不写 `f1_state.json`**。
- 白名单 ≈6 只/轮 = top-5 持仓 + ≤2 只 idx 代理（`proxy_watchlist()`）。
- 页面/推送说人话：`主源故障：信号冻结至 <asof>，以下为备源（新浪）抽查参考，不构成新推荐。`

### 5.4 切回验收

- 主源连续 2 周期全检通过 → 进入 `RECOVERING` 待验收。
- 一致性验收（`consistency_check()`）：按 (symbol, date) 对齐比 close，
  **容差 = 价格 1% + 代币(USDT)/现货(USD) 基差 1% = 2%**（基差计入，满足空头席要求）。
- 验收通过 → 自动切回 `NORMAL`；不通过 → `pending_manual=true` 挂待人工，**禁止自动强切**。

### 5.5 新浪 adapter（只读）

- 接口：`US_MinKService.getDailyK`，symbol = **小写基础代码**（`AAOIUSDT` → `aaoi`，不带后缀）
- 头：`Referer: https://finance.sina.com.cn`（+ UA）
- 字段映射：`d/o/h/l/c/v` → `date/open/high/low/close/volume`，并打 `source='sina'`
- **SLA 标注**：无官方 SLA（内部灰色接口，无文档、无限流承诺、字段可随时变更），
  仅作降级期抽查核对与人工止损参考，**不得用于信号重建**。

---

## 六、自测结果（工程侧）

| 套件 | 结果 |
|---|---|
| `run_checks.py`（G1-G5） | G1 PASS / G2 PASS / **G3 PASS** / G5 PASS；**G4 FAIL（既有偏差，非 R13 引入）** |
| `run_scenario_checks.py`（场景矩阵 A-T + R13 H/I/J） | **87/87 PASS**（含渲染级 E/T 组） |
| `run_r13_selftest.py`（R13 专项 R1-R21） | **21/21 PASS** |
| `f1_datasource.py drill`（容灾切换演练） | **8/8 PASS** |

### G4 FAIL 的如实说明（重要，交交易团队复分析）

G4 = 引擎 `replay` 逐日持仓 vs 权威 `f1_backtest.run_backtest` 逐日持仓对账。
当前缓存（2026-10-17 刷新）下 **逐日持仓差异 11 天**
（2025-08-12~08-25 共 9 天、2026-01-06/01-07 共 2 天）。

**已做 A/B 验证排除 R13 归因**：用 git HEAD 版引擎（sha `83dc6caa…`）在当前缓存下复跑，
差异集合**同样为这 11 天**，与 R13 版（sha `ae92dfaf…`）**完全一致**。
→ G4 偏差为**既有问题**（缓存刷新后新数据引入），**非本次四工单改动导致**，
不计入 R13 验收。建议交易团队复分析时确认这 11 天的持仓口径。

---

## 七、复现命令（全部固定 seed=42）

```bash
# ① 熔断线重标定后的真实段回放统计（结果落 breaker_stats_r13.json）
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/replay_breakers_r13.py

# ② R13 专项自测（R1-R21，结果落 r13_selftest_result.json）
PYTHONHASHSEED=42 F1_RETRY_SLEEP=0 python3 /workspace/repo_ready/engine_f1/run_r13_selftest.py

# ③ 数据源容灾人造故障切换演练（结果落 r13_failover_drill.json）
PYTHONHASHSEED=42 F1_RETRY_SLEEP=0 python3 /workspace/repo_ready/engine_f1/f1_datasource.py drill

# ④ 只读盘中快照（三轮，禁写状态）
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py snapshot --round 20:30
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py snapshot --round 00:30
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py snapshot --round 04:30

# ⑤ 判定轮（日K 落定后；未落定时 guard 会拒绝并提示）
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py live
#   演练强判定（仅测试）： ... live --allow-intraday

# ⑥ 归档副本对齐
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/sync_archive.py

# ⑦ 既有检测套件
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/run_checks.py
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/run_scenario_checks.py
```

## 八、发版闸门

- [x] 工程改码完成（四工单）
- [x] 自测（重标定回放统计 + 容灾演练 + 只读快照不写状态验证）
- [x] commit（本地，未 push）
- [ ] 审计+测试席复核
- [ ] 交易团队复分析（含 G4 11 天偏差、费线弱活线两项待确认）
- [ ] 发版问用户（未授权不 push / 不注册 cron 上线）
