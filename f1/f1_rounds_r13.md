# R13 · F1 多轮扫描时刻表（展示多轮、判定一轮）

- 依据：R13 四席终审会「事项三」主管席终裁 + WO-R13-03
- 锚点：**本引擎日K 于 00:00 UTC（北京 08:00）落定**
- 原则：判定引擎**每日只跑一轮**（日K落定后）；其余三轮为**只读盘中快照**。

## 一、四个时刻的语义

| 时刻(北京) | UTC | 美股语义 | 读到的「今日 bar」 | 模式 |
|---|---|---|---|---|
| 20:30 | 12:30 | 夏令时盘前（9:30 ET 开盘 = 北京 21:30，本轮=开盘前约 1 小时） | 进行中（仅约 12.5h） | 只读快照 |
| 00:30 | 16:30 | 夏令时盘中（约 12:30 ET） | 进行中 | 只读快照 |
| 04:30 | 20:30 | **夏令时=收盘后 30 分钟**；**冬令时=收盘前 30 分钟**（16:00 ET 冬令 = 北京 05:00 收） | 进行中 | 只读快照 |
| 09:25 | 01:25 | 日K已落定 1 小时 25 分 | **完整日K** | **判定轮** |

> 备选：判定轮前移 08:30（=日K落定后 30 分钟）。**09:25 与 08:30 读到同一根已落定日K，
> 信息完全重复，仅差 55 分钟，二选一即可**（当前保留 09:25）。

## 二、夏令时（DST）标注 · 必读

- **北京时刻全年固定**（中国无夏令时）。
- 美股夏令时窗口：**3 月第二个周日 ~ 11 月第一个周日**。
- 因此 **04:30 轮的语义随 DST 漂移**：
  - 夏令时窗口内 → **收盘后 30 分钟快照**（页面标签：`美股收盘后快照`）；
  - 冬令时窗口内 → **收盘前 30 分钟快照**（页面标签：`美股收盘前快照`）。
- 引擎常量：`f1_signal.INTRADAY_ROUNDS['04:30']['semantic']`、`f1_signal.DST_NOTE`。

## 三、可注册 cron（见 `f1_crontab.txt`）

```cron
# 判定轮（每日一次，日K 落定后）
25 9 * * 1-5 PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py live >> /workspace/f1_web/cron.log 2>&1
# 只读盘中快照三轮
30 20 * * 1-5 PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py snapshot --round 20:30 >> /workspace/f1_web/cron.log 2>&1
30 0  * * 1-5 PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py snapshot --round 00:30 >> /workspace/f1_web/cron.log 2>&1
30 4  * * 1-5 PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py snapshot --round 04:30 >> /workspace/f1_web/cron.log 2>&1
```

## 四、只读快照 vs 判定轮 · 行为对照

| 行为 | 只读盘中快照（`snapshot`） | 判定轮（`live`） |
|---|---|---|
| 写 `f1_state.json`（档位/冻结） | ❌ 禁止 | ✅ 允许 |
| 覆盖 `f1_live.json` 判定字段 | ❌ 禁止 | ✅ 允许 |
| 产出 top5 建议 | ❌ 禁止 | ✅ 允许 |
| 周调仓锚定/信号判定 | ❌ 禁止（guard 拒绝） | ✅ 允许 |
| 持仓浮动盈亏展示 | ✅ | ✅ |
| 熔断预演（用已落定日K） | ✅ | ✅（真实判定） |
| 崩市中位跌幅 | 预估（未落定） | 判定 |
| 推送标注 | `盘中快照·不可操作` | `判定轮结论` |
| 输出文件 | `f1_live_intraday.json` | `f1_live.json` |

## 五、推送去重

- 判定轮：按 `asof` 去重（同一交易日只推一次结论）。
- 盘中轮：按 `asof + 轮次` 去重；**永不携带判定结论 / top5**。
- 实现：`f1_signal.push_plan(mode, asof, round_id, last_push)`。

## 六、防部分K污染 guard

- 规则：日K 在 **D+1 日 00:00 UTC** 才落定，故「最后一根 bar 日期 ≥ 当前 UTC 日期」⇒
  该 bar 仍在形成中，标记 `intraday`，**禁止进入周调仓锚定与信号判定**。
- 实现：`f1_signal.guard_last_bar(cal, now=None)`；`run_live` / `current_signal` 入口校验，
  未落定则**拒绝判定并记日志**（`f1_guard.log`），不写任何判定文件。
- 演练强判定（仅测试用）：`... live --allow-intraday`。
