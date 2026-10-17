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
| `f1_signal.py` | 信号引擎：周度信号（四因子 z-score 等权 → top-5 + 单票 2.5% 目标仓）+ 每日熔断监控（CB1/CB2 双账/CB3/费线，状态灯+建议动作）+ 月度三本账（毛/费/让渡） |
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

## 熔断器与档位（R11' 上线方案条款）

- **CB1**：滚动 20 交易日净账 MDD ≤ −32% → 降一档（半线 −16% 黄灯观察）
- **CB2**：滚动 60 日止损失血毛账触发（名义加权止损亏损 ≤ −20pp 或毛账同期 ≤ −20%）+ 净账确认 → 红灯，冻结开新仓 20 交易日（首月暂定）；毛账触发未确认 → 黄灯
- **CB3**：滚动 60 日止损次数 ≥ 基准(回放期统计 9.07 次/60日)×3 → 外移观察线（黄灯，不动作）
- **费线**：滚动 60 日费用年化拖累 ≥ 21.7pp → 降一档（10.85pp 黄灯）
- **档位表（单票）**：2.5% → 1.5% → 1.0% → 0.5%，起步 12.5% 总敞口；降档自动，升档人工复核后解锁

## 口径备忘

- 信号：每周首个交易日收盘打分（|z|≤3 截断等权），次日开盘成交；跌出 top-15 换仓；top-5 等权
- regime 闸：idx<MA50 清仓持币；崩市（池单日中位跌幅<−5%）次日开盘清仓；止损 −8% 硬截断（跳空按开盘价）
- 费：滑点 0.05%/边 + 资金费 0.03%/bar（持仓名义）
- 三本账：毛账=零费轨；费账=滑点+资金费；让渡账=池等权买入持有 − 策略毛账
- 上线首期账本由历史回放播种（shadow），真实交易记录接入后切换，切换时在月报标注
