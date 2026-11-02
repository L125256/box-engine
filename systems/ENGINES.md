# 两套可直接运行的引擎：FD-1 双通道 + P6 v2

最后更新：2026-11-03（数据截至 2026-11-01 收盘）
适用对象：第一次拿到本仓库的人或 AI。只要把日线 K 线喂进 `cache_fresh/`，按下面的命令就能跑；不需要数据库、不需要 API key、不需要 pandas。

---

## 0. 30 秒快速开始

```bash
# 1) 依赖：Python 3.10+，numpy
pip install -r systems/requirements.txt

# 2) 把 K 线转成引擎格式（CSV 或已有 JSON 都行）
python systems/prepare_data.py --input /path/to/kline.csv --out cache_fresh
#    或：python systems/prepare_data.py --input /path/to/kline_dir --out cache_fresh

# 3) 跑两套引擎的当日扫描
V2_CACHE=/abs/path/to/cache_fresh python systems/fd1/strategy.py
V2_CACHE=/abs/path/to/cache_fresh python systems/p6/rs_scan.py

# 4) 生成本地看板（只写本地 HTML，不发布）
V2_CACHE=/abs/path/to/cache_fresh python systems/fd1/board.py
V2_CACHE=/abs/path/to/cache_fresh python systems/p6/board.py
```

两套引擎共用 `v2/engine/v2_lib.py` 的数据加载、特征、组合模拟；**P6 还依赖 `systems/fd1/` 里的 `strategy.py`、`variants.py`、`portfolio.py`，两个目录要一起保留**。

---

## 1. 数据契约（最重要）

### 1.1 目录格式

```
cache_fresh/
  AAPLUSDT.json
  NVDAUSDT.json
  TSLAUSDT.json
  ...
```

每个文件是该标的的日线数组，按时间升序：

```json
[
  {"time": "2026-10-30", "open": 338.1, "high": 346.2, "low": 337.0, "close": 345.1, "volume": 1234567.0},
  {"time": "2026-11-01", "open": 345.1, "high": 348.0, "low": 342.2, "close": 346.5, "volume": 987654.0}
]
```

字段：
- `time`：`YYYY-MM-DD`（日线）。引擎按自然日对齐，7×24 每自然日一根，不是美股交易日。
- `open/high/low/close`：正数；建议用未复权或前复权都可以，但同一标的全历史必须一致。
- `volume`：基础币/股成交量（不是成交额）；`dv20` = `close × volume` 的 20 日中位数。

### 1.2 最少根数

- 引擎有 210 / 220 根 warmup；**每个标的至少 260 根**才有意义。
- 少于 210 根的标的不会产生信号；`prepare_data.py` 会给出 WARN。

### 1.3 标的范围

- 引擎读取 `cache_fresh/` 下**所有** `*.json`，不依赖外部池文件。
- 参考结果使用 120 只核心个股（144 个标的里剔除 24 个杠杆/ETF；代码里 `v2_lib.ETF` / `v2_lib.LEV` 会自动剔除）。
- 想复现参考统计，就喂同样的 120 只；只喂 10 只也能跑，但统计会变。

### 1.4 数据清洗

`v2_lib.load_all()` 会自动做：
- 丢弃 open/close 为空的 bar；
- 对“价格尺度跳变”（如 167 → 658 → 195）做段剔除；
- 对单边向上 >40% 的跳变做前复权；
- 对 `|ret| > 35%` 的 bar 标记 `jump`，不参与入场和止损/止盈触发。

**不要把已经复权/清洗过的数据再手工改一遍**；直接把原始日线喂进来即可。`prepare_data.py` 只做格式转换和同日聚合，不做复权。

### 1.5 成交与成本假设

- 收盘出信号，**下一根工作日开盘**成交；周五信号等周一。
- 5x 逐仓；单笔保证金 = 权益 × 3%（名义 = 权益 × 15%）。
- 最多 16 个同时持仓；总毛敞口 ≤ 2.5 × 权益；P6 同日最多 5 个新仓。
- 手续费 + 滑点 0.20% 往返；资金费 0.03%/日；5x 爆仓距离约 19%。
- 同一根 bar 内止损与止盈都触及时，回测按**先止损**处理（保守）；跳空按开盘价成交。

---

## 2. FD-1 双通道（`systems/fd1/`）

### 2.1 一句话逻辑

通道 A 做“上升趋势里的深踩”：收盘仍在 MA100 上方、MA100 斜率不为负，20 日偏离 ≤ −5%、RSI2 ≤ 30 时买入。通道 B 做“上升趋势里的 20 日新高放量突破”：收盘创 20 日收盘新高、当日量 ≥ 2 倍 20 日中位量、仍在 MA100 上方。两条通道共用 +0.8 ATR 止盈、−1.5 ATR 止损、最多 5 根日线。

### 2.2 精确规则

**通道 A · 深踩**（全部满足）：
- 收盘 > MA100，且 MA100 的 20 日斜率 ≥ 0；
- `close / MA20 - 1 ≤ −5%`；
- RSI2 ≤ 30；
- 收盘 ≥ 5；20 日成交额中位数 ≥ 3000 万美元；ATR% ≤ 6%；
- 只做个股（剔除 ETF/杠杆）；至少 210 根历史；非数据跳变。

**通道 B · 20 日新高放量突破**（全部满足）：
- 收盘 > 过去 20 根收盘最高（不含当日）；
- 当日成交量 ≥ 2.0 × 过去 20 日中位量；
- 收盘 > MA100，且 MA100 的 20 日斜率 ≥ 0；
- 收盘 ≥ 5；20 日成交额中位数 ≥ 3000 万美元；ATR% ≤ 6%；
- 只做个股；至少 210 根历史；同一标的 10 根内只取第一次。

**出场（两通道共用）**：
- 止盈 `entry + 0.8 × ATR14`；
- 止损 `entry − 1.5 × ATR14`；
- 最多 5 根日线，到期按收盘；
- 跳空：开盘低于止损按开盘，开盘高于止盈按开盘。

### 2.3 参考统计（asof 2026-11-01，120 只个股，5x/3%/16/2.5x）

| 口径 | 笔数 | 胜率 | PF | 年化 | 最大回撤 |
|---|---:|---:|---:|---:|---:|
| 双通道 全样本 | 519 | 70.7% | 1.49 | 36.7% | 12.46% |
| 双通道 2025-06 起 | 435 | 71.7% | 1.67 | 52.4% | 7.77% |
| 双通道 2026-01-26 起 | 147 | 72.8% | 1.78 | 34.7% | 5.35% |
| 原版深踩 全样本（对照） | 271 | 70.8% | 1.60 | 22.3% | 8.52% |
| 原版深踩 2026-01-26 起（对照） | 65 | 69.2% | 1.65 | 12.7% | 4.05% |

通道拆分（组合内实际成交）：深踩 271 笔 / 70.8% / PF1.60；突破 248 笔 / 70.6% / PF1.38。两条通道各占约一半，胜率几乎相同；突破通道 PF 低一些，但把笔数从 271 拉到 519。

### 2.4 运行

```bash
V2_CACHE=/abs/path/to/cache_fresh python systems/fd1/strategy.py   # 当日候选 + 最近成交
V2_CACHE=/abs/path/to/cache_fresh python systems/fd1/board.py      # 本地 index.html + build_report.json
```

预期（参考缓存、asof 2026-11-01）：深踩 0 只、突破 0 只；`build_report.json` 的 `stats.full` = 519 / 70.7 / 1.49 / 36.7 / 12.46。

### 2.5 文件

| 文件 | 作用 |
|---|---|
| `strategy.py` | 双通道规则、候选、单笔模拟、最近成交；`load()` 读 `V2_CACHE` |
| `board.py` | 本地看板 + `build_report.json` + `forward_log.jsonl` |
| `variants.py` / `portfolio.py` | 变体与组合复核；P6 的 `rs_lab` 也会 import |
| `live_scan.py` | 盘中/收盘预演，打印两通道严格候选和深踩差 1–2 项名单 |
| `nodv_scan.py` | 去掉 dv20 门槛的对照 |
| `README.md` | 本系统的详细说明与变更记录 |

---

## 3. P6 v2（`systems/p6/`）

### 3.1 一句话逻辑

不设全市场闸门，只看个股自己的趋势、强度和量能：站上 MA50 且 MA50 > MA100、两条均线都向上、20 日收益为正，并且信号日成交量 ≥ 1.5 × 20 日中位量时买入；+0.8 ATR 止盈、−1.8 ATR 止损、最多 7 根日线。**只在状态第一次从 false 变 true 时入场；一个上涨段只做一次。**

### 3.2 精确规则

**入场**（全部满足）：
- 收盘 > MA50 > MA100；
- MA50 的 10 日斜率 ≥ 0；MA100 的 20 日斜率 ≥ 0；
- 20 日收益 > 0（绝对强度，不要求跑赢指数）；
- 信号日成交量 ≥ 1.5 × 20 日中位量；
- 收盘 ≥ 5；20 日成交额中位数 ≥ 3000 万美元；ATR% ≤ 6%；
- 只做个股；至少 220 根历史；非数据跳变；
- 首次触发：今天满足且昨天不满足；平仓后要等状态 reset 再重新计数。

**出场**：
- 止盈 `entry + 0.8 × ATR14`；
- 止损 `entry − 1.8 × ATR14`；
- 最多 7 根日线；跳空按开盘；同 bar 先止损。

### 3.3 参考统计（asof 2026-11-01，页面口径）

| 口径 | 笔数 | 笔/月 | 胜率 | PF | 区间收益 | 年化 | 最大回撤 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 全样本 | 653 | 29.7 | 70.0% | 1.17 | +32.5% | +16.6% | −14.39% |
| 2025-06-01 起 | 581 | 34.2 | 71.4% | 1.27 | +48.1% | +31.9% | −12.45% |

2026-01-26 起（研究 `sim_port` 口径）：217 笔 / 73.7% / PF1.47 / 年化 +41.8% / 回撤 7.11%。

### 3.4 运行

```bash
V2_CACHE=/abs/path/to/cache_fresh python systems/p6/rs_scan.py   # 当日候选
V2_CACHE=/abs/path/to/cache_fresh python systems/p6/board.py     # 本地 index.html + build_report.json
```

预期（参考缓存、asof 2026-11-01）：0 候选；`build_report.json` 全样本 653 笔 / 70.0% / PF1.17；2025-06 起 581 笔 / 71.4% / PF1.27 / CAGR31.9% / MDD−12.45%。

### 3.5 文件与依赖

| 文件 | 作用 |
|---|---|
| `rs_scan.py` | 当日扫描；只列首次触发候选 |
| `board.py` | 本地看板 + 组合统计 + `build_report.json` |
| `rs_lab.py` | 研究脚本（趋势/回踩/量能/突破等变体） |
| `rs_hold.py` | 持有期研究 |
| `p6_results.json` | 旧研究结果快照 |
| `README.md` | 本系统的详细说明与变更记录 |

**依赖**：`board.py` / `rs_lab.py` / `rs_scan.py` 会 `import v2_lib`，并 `from strategy import load`、`from variants import sim_trade`、`from portfolio import port`；后三者来自 `systems/fd1/`。**不要把 `systems/p6` 单独拷走**，要么保留 `systems/fd1`，要么把这三个文件一起复制。

---

## 4. 共享口径（两套都一样）

- 只做多；5x 逐仓；单笔保证金 3% 权益；最多 16 仓；毛敞口 2.5x。
- 收盘出信号，下一根工作日开盘成交；ETF/杠杆 ETF 剔除。
- 成本 0.20% 往返；资金费 0.03%/日；跳空按开盘；同 bar 先止损。
- 两套都**没有市场闸门**；个股趋势和形态就是过滤器。
- 两套都只生成候选/研究统计，**不下单、不接交易所、不需要 API key**。

---

## 5. 验证清单（换机器/换数据后先跑这个）

1. `python systems/prepare_data.py --input ... --out cache_fresh` 输出 `wrote N symbols / M bars`，日期范围覆盖你预期的时间。
2. `V2_CACHE=... python systems/fd1/strategy.py` 输出 `asof ... ｜ 深踩 X 只 ｜ 突破 Y 只`，不报 `FileNotFoundError`。
3. `V2_CACHE=... python systems/p6/rs_scan.py` 输出 `asof ... ｜ 候选 ...`，不报 `ModuleNotFoundError: strategy`。
4. `V2_CACHE=... python systems/fd1/board.py` 的 `build_report.json` 里 `stats.full` 有 519 笔（参考缓存）；如果你换了数据/标的数量，数字会变，这是正常的。
5. `V2_CACHE=... python systems/p6/board.py` 的 `build_report.json` 全样本 653 笔（参考缓存）。
6. 看板 `index.html` 的 `built_at` 是生成时刻；每次重建哈希都会变，不能拿旧哈希核对新页面。

常见差异来源：数据日期范围、标的数量、warmup 不足、`V2_CACHE` 指错、numpy 版本导致数值微小差异。先核对这五项，再怀疑规则。

---

## 6. 已知限制与风险

- 2026-01-26 之前的日线包含回填/合成段；2025 年数据权重低。真实合约段样本薄，任何高 PF 都不应外推。
- 5x 杠杆下，历史回撤 ≠ 未来最大回撤；跳空可能显著超过止损。
- 只做多；系统性下跌时两套都会连续止损；仓位上限和止损是唯一保护。
- 这是研究代码，不是投资建议，也不是自动交易系统；上线前必须自己做前向验证。
- `board.py` 生成的 `index.html` 只写本地，不上传、不发布；`build_report.json` 的哈希是本地页面哈希。

---

## 7. 变更记录

- 2026-10-29：FD-1 v1 冻结（单通道深踩 −5% / RSI2 30；0.8/1.5/5）。
- 2026-11-03：FD-1 替换为双通道（新增 20 日新高 + 2.0× 量能突破；出场不变）。原版备份在本地 `_backup_2026-11-03_v1/`，未上传。
- 2026-11-03：P6 替换为 v2（趋势 + 20 日收益 > 0 + 1.5× 量能，首次触发；0.8/1.8/7）。v1 回踩版备份在本地 `_backup_2026-11-03/`，未上传。
- 2026-11-03：新增 `systems/prepare_data.py` 与本文件；根目录 `SYSTEMS.md` 同步更新 FD-1/P6 两行。
