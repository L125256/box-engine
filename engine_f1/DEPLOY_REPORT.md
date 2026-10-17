# R11' 发版工单 · F1 上线验收报告（DEPLOY_REPORT.md）

- 工单：R11' F1 base 裸奔四因子带闸版 上线运营
- 验收日期：2026-10-17
- seed：42（一次成活；改参数=新工单，禁止调参重跑）
- 引擎：`engine_f1/f1_signal.py` v1，sha256 见 `checks_result.json → G1`
- 锁定 commit：`c8817d0c96449563007b65f175f8ddad29b96664`

## 上线方案要点（照此部署，已确认条款）

- 四因子 = ma20_slope / obv_slope20 / dist_52w_high / mom_1m，横截面 z-score(|z|≤3) 等权合成
- 周调仓（星期一信号、次日开盘成交）持 top-5 等权；regime 闸 = idx<MA50 清仓持币
- 止损 −8% 硬截断（V2 可实现口径：跳空按开盘、触线按止损价）；崩市（池单日中位跌幅<−5%）清仓
- 费：滑点 0.05%/边 + 资金费 0.03%/bar；起步仓位 12.5%（单票 2.5%）
- 熔断：CB1（MDD−32%/20交易日降一档）、CB2（滚动60日止损失血毛账触发+净账确认，20pp 暂定首月冻结）、CB3（频次外移观察线）、费线（21.7pp×2月降一档）
- 监控四件套 + 三本账月报；页面 `/workspace/f1_web/index.html`，数据 `f1_live.json`，生成器 `f1_generate.py` 幂等可 cron

## G1-G5 检查单实测结果

| 检查项 | 内容 | 方法 | 结果 |
|---|---|---|---|
| **G1 引擎版本锁定** | 引擎文件 sha256 自校验 + 同源回测 sha256 记录 + commit hash 锁定 | `engine_sha256()` 双副本比对一致；回测源 sha256 存档 | **PASS** |
| **G2 数据源健康** | kxiandaoyan API 连通 + 字段/新鲜度校验 | 4 标的探针（AAPL/NVDA/TSLA/EWZ）：API 最新 bar == 缓存最新 bar（2026-10-17），time/OHLCV 字段齐备且 high≥low、close∈[low,high]；全量 176 缓存文件字段校验无坏档；权威池 144 | **PASS** |
| **G3 监控越线实测** | 人造越线数据逐条验证熔断灯与动作 | 11 个用例全过：CB1 红（20日MDD−35%→降一档）/黄（−18%→观察）/绿对照；CB2 红（毛账60日−22%+净账确认→冻结开新仓）/黄（失血触发未确认→待确认）/绿对照；CB3 黄（60日28次≥观察线27.21→外移观察）/绿（5次）；费线 红（年化25.2%→降一档）/黄（12.6%过半线）/绿（2.5%） | **PASS**（11/11） |
| **G4 回放对账** | 信号引擎历史持仓 vs f1_backtest 逐日 diff=0 | 权威侧=`f1_backtest.run_backtest` 源码插桩逐日持仓（逻辑零改动）；引擎侧=`f1_signal.replay`（slot=0.10 对齐）；**767 个交易日持仓逐日 diff=0**，权益曲线最大绝对差 1.8e-15（浮点噪声级） | **PASS** |
| **G5 定时接线** | cron 注册说明 + 本机定时任务建议 | 本机无 crontab 命令（沙箱环境），以注册说明+建议交付；WT-C 日更入口 `/tmp/wtc/run_daily.sh`（09:10）已就绪，F1 生成器建议挂 09:25（工作日）；注册文件见 `engine_f1/f1_crontab.txt`，上岗时 `crontab f1_crontab.txt` 或改 systemd timer | **PASS**（说明+建议） |

明细数据：`engine_f1/checks_result.json`。

## 上线确认

1. **信号引擎上线**：`f1_signal.py live` 实测输出正常（asof=2026-10-17，当前 regime 闸关闭·清仓持币，idx 220.10 < MA50 236.41；熔断四灯全绿；CB3 基准由回放期统计回填 9.07 次/60日）。
2. **状态页上线**：`/workspace/f1_web/index.html`（📦 F1 多因子轮动·上线运营版），含持仓建议/熔断状态灯/三本账月报/费拖累曲线/监控明细，数据 `f1_live.json` 由 `f1_generate.py` 幂等生成。
3. **部署归档**：产物复制至 `repo_ready/f1/` 并 commit+push（结果见下节）。
4. **首月纪律**：起步档 12.5%（单票 2.5%）；CB2 冻结 20 交易日为暂定值，首月末由月报复核；降档自动执行、升档需人工复核。

## push 结果

`PUSH OK`：引擎锁定提交 `c8817d0`（a17b590..c8817d0 main→main，2026-10-17 23:20，第 1 次尝试成功；此前 2 轮失败为本机工作目录问题非网络故障，如实记录）。文档回填提交随后追加。

## 复现命令

```bash
# 0) 刷缓存（32线程，kxiandaoyan）
python3 /tmp/wtc/refresh_cache.py

# 1) 权威回测（G4 基准）
PYTHONHASHSEED=42 python3 /tmp/eng_w2_f1/f1_backtest.py

# 2) G1-G5 检查单
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/run_checks.py

# 3) 信号引擎 live（页面数据）
PYTHONHASHSEED=42 python3 /workspace/f1_web/f1_generate.py

# 4) 历史回放（口径复核）
PYTHONHASHSEED=42 python3 /workspace/repo_ready/engine_f1/f1_signal.py replay --slot 0.10
```
