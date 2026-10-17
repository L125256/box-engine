# engine_f1 — F1 信号引擎（R11' 上线运营版）

F1 base 裸奔四因子带闸版的上线信号引擎。与权威回测 `/tmp/eng_w2_f1/f1_backtest.py` 同源同口径（G4 逐日对账 diff=0）。

## 版本锁定（G1）

- **引擎文件**：`f1_signal.py`（v1，seed=42 一次成活，改参数=新工单）
- **代码 sha256**：见 `checks_result.json` → `G1.engine_sha256`，同步烙印在每次生成的 `f1_live.json → meta.engine_sha256`
- **git commit hash 锁定**：`c8817d0c96449563007b65f175f8ddad29b96664`（本 README 与引擎同仓入库的锁定提交）
- **同源依据**：`f1_backtest.py` sha256 = 见 `checks_result.json → G1.backtest_src_sha256`

## 组成

| 文件 | 说明 |
|---|---|
| `f1_signal.py` | 信号引擎：周度信号（四因子 z-score 等权 → top-5 + 单票 2.5% 目标仓）+ 每日熔断监控（CB1/CB2 双账/CB3/费线，状态灯+建议动作）+ 月度三本账（毛/费/让渡）+ `snapshot` 只读盘中旁路（R13） |
| `f1_datasource.py` | 数据源容灾：主源健康检查、NORMAL/DEGRADED/RECOVERING 状态机、新浪只读 adapter（白名单 ≤6 只/轮）、一致性验收切回、事件日志（R13） |
| `replay_breakers_r13.py` | R13 重标定后真实段回放触发统计 → `breaker_stats_r13.json`（R13） |
| `run_r13_selftest.py` | R13 四工单专项自测（R1-R21）→ `r13_selftest_result.json`（R13） |
| `sync_archive.py` | 归档目录 `repo_ready/f1` 逐文件 sha256 对齐（R13） |
| `f1_rounds_r13.md` | 多轮扫描时刻表（20:30/00:30/04:30 只读 + 判定轮，含夏令时标注）（R13） |
| `F1_台账口径_v1.md` | 《F1 台账口径》v1 正式台账（五节，含 R13 新阈值表）（R13） |
| `R13_DEPLOY.md` | R13 四工单施工/自测报告（R13） |
| `run_checks.py` | G1-G5 检查单执行器 → `checks_result.json` |
| `checks_result.json` | 最近一次检查结果 |
| `DEPLOY_REPORT.md` | 上线验收报告（G1-G5 + 上线确认） |

## 运行

```bash
# 每日 live（生成 /workspace/f1_web/f1_live.json）
PYTHONHASHSEED=42 python3 f1_signal.py live

# 历史回放（G4 对账 / 口径复核）
PYTHONHASHSEED=42 python3 f1_signal.py replay --slot 0.10
```

数据：`/tmp/box_cache/*.json`（kxiandaoyan 日K，滚动700根），刷缓存用 `/tmp/wtc/refresh_cache.py`（32线程，失败跳过保留旧缓存）。

## 熔断器与档位（**R13 重标定 · 现行 12.5% 敞口口径**）

| 线 | 指标 | 🔴 红（动作） | 🟡 黄（观察） | 窗口 |
|---|---|---|---|---|
| **CB1** 回撤闸 | 滚动窗口净账 MDD | ≤ **−8%** → 降一档 | ≤ **−4%** | 20 交易日 |
| **CB2** 止损闸 | 毛账触发（名义加权止损亏损 ≤ 线 或 60 日毛跌 ≤ 线）+ 净账确认 | ≤ **−5pp** → 冻结开新仓 **20 交易日** | ≤ **−2.5pp** | 60 交易日 |
| **CB3** 频次观察 | 滚动窗口止损次数 | （永不红） | ≥ **27.21 次** | 60 交易日 |
| **费线** 费用闸 | 滚动窗口费用折年化 | ≥ **4pp** → 降一档 | ≥ **2pp** | 60 交易日 |

- **CB3 保留不动**：冻结基准 **9.07**（v1 冻结快照，live 重算值仅作 `cb3_baseline_recomputed` 对账字段）。
- **口径警告**：旧阈值（−32% / −20pp / 21.7pp）为满仓时代口径遗产，在本敞口下数学不可达，**已废止，禁止再引用**；
  若未来人工升敞口，须按敞口比例重标定（升档=新工单）。
- **档位表（单票）**：2.5% → 1.5% → 1.0% → 0.5%，起步 12.5% 总敞口；降档自动，升档人工复核后解锁。
- **阈值单一事实源**：`breaker_thresholds()` → `f1_live.json → meta.breaker_thresholds`；**页面一律读 JSON**。

## R13 增补能力

- **只读盘中快照**：`python3 f1_signal.py snapshot --round {20:30|00:30|04:30}`
  → 输出 `f1_live_intraday.json`，**禁写 `f1_state.json`、禁覆盖 `f1_live.json` 判定字段、禁出 top5**。
- **防部分K污染 guard**：`guard_last_bar()` 识别未落定当日 bar 并标记 intraday，
  `run_live` / `current_signal` 入口未落定即拒绝判定并写 `f1_guard.log`。
- **推送去重**：`push_plan()` 判定轮按 asof、盘中轮按 asof+轮次且不携带结论。
- **数据源容灾**：`python3 f1_datasource.py {status|check|drill}`；
  故障注入 `F1_PRIMARY_FAIL=1`，演练加速 `F1_RETRY_SLEEP=0`。

## 口径备忘

- 信号：每周首个交易日收盘打分（|z|≤3 截断等权），次日开盘成交；跌出 top-15 换仓；top-5 等权
- regime 闸：idx<MA50 清仓持币；崩市（池单日中位跌幅<−5%）次日开盘清仓；止损 −8% 硬截断（跳空按开盘价）
- 费：滑点 0.05%/边 + 资金费 0.03%/bar（持仓名义）
- 三本账：毛账=零费轨；费账=滑点+资金费；让渡账=池等权买入持有 − 策略毛账
- 上线首期账本由历史回放播种（shadow），真实交易记录接入后切换，切换时在月报标注
