# WO-BREADTH-01 · F1 引擎市场宽度（G-breadth）读数输出

- 日期：2026-10-19
- 引擎：engine_f1/f1_signal.py（归档副本 f1/f1_signal.py 逐字节同步）
- 授权：工程保障团队单 agent 全席（施工+测试+审计），commit 不 push

## 一、变更范围
1. `f1_signal.py` 头注：新增「市场宽度」变更登记段。
2. `f1_signal.py` 新增常量 `BREADTH_MA_WINDOW=50` / `BREADTH_MIN_PERIODS=40`
   与函数 `calc_breadth(data, syms)`（数据与池 section，build_pool 之后）。
3. meta 组装处各加一行字段：`run_live` → `meta.breadth`、`run_snapshot` → `meta.breadth`。
4. `engine_f1/AUTHORITY_SHA.json` 与 `f1/AUTHORITY_SHA.json`：f1_signal.py 登记值
   同步为新 sha256（sha 闸门 fail-closed 防复发要求）。

## 二、零行为改动声明
四因子计算、top5、gate（idx<MA50）、崩市、止损、CB1/CB2/CB3/费线、
状态机（降档/冻结）、推送去重、guard 链路 **一行未动**。
`calc_breadth` 为纯只读函数，只读 `data/syms` 构造收盘矩阵计算比例，
结果仅落入 `meta.breadth`，不参与任何信号/闸/状态机判定。
回归验证：改动前后同一输入（/tmp/box_cache 全量 700 根K线）跑 live，
除 `meta.breadth`（新增）与 `meta.generated`/`meta.engine_sha256`（时间戳与
引擎自指 sha，必然变化）外，其余字段逐位一致（含 signal.top5 成员与分数、
gate 状态、熔断四灯与明细、monthly_accounts、state）。见 /tmp/breadth_wo/REPORT.md。

## 三、breadth 口径（锁定，禁改）
- 定义：池（cleaned_pool.json kept 144，与 idx 同池同「当日有K线」过滤口径）内，
  当日 close > 自身 MA50 的标的数 / 当日有K线标的总数 × 100。
- MA50：简单滚动均线，窗口 50、min_periods=40。逐字对齐研究
  `research/wo_g1g2fdr/wo_g1g2fdr_run.py` L300-302：
  `breadth = (above > above.rolling(50, min_periods=40).mean()).mean(axis=1) * 100.0`
- 数据不足（K线历史 < min_periods=40，MA 为 NaN）的票按研究口径处理：
  NaN 比较记 False → 计入分母 n_total、不计入分子 n_above，如实计数。
- 输出：`f1_live.json → meta.breadth = {"pct": 62.5, "n_above": 90, "n_total": 144,
  "ma_window": 50, "min_periods": 40}`，pct 保留 2 位小数。
- live（判定轮）与 snapshot（盘中只读轮）双模式均输出；
  降级冻结轮（_emit_frozen）不重算，沿用上一落定负载的 meta（含 breadth）。

## 四、sha 对照表

| 文件 | 旧 sha256（R15-2026-10-19） | 新 sha256（WO-BREADTH-01） |
|---|---|---|
| f1_signal.py | e616a28d06727232fdd5792e87d03dca115c9a43f3a624e1c8a297dfcaf36293 | 3f8c0b7130c8a77a917cf8977eb89f366951ec9e2780ecaa11a8ffabb2a1b0ca |

两处 AUTHORITY_SHA.json（engine_f1/ 主本与 f1/ 归档）同步更新；
f1_signal.py 主本/副本逐字节一致（已断言）。

## 五、遗留风险
- 降级冻结轮若基线 f1_live.json 无 breadth 字段（旧版产物），冻结负载将无该字段；
  晨报需容错（无 breadth = 数据尚未由新版判定轮刷新）。判定轮正常跑一轮后即有。
- 若未来池规模变化（144 改判），n_total 为实测值不受影响；口径禁改。
