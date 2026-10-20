# W2B_GATE_SPREAD_REPORT — 工单⑥ Gate 两市场价差序列入库报告（W2B_SPEC §6 冻结口径）

- 生成：2026-10-20 ｜ 运行件：`research/wo_mine/w2b_gate_spread_run.py` ｜ 结果：`w2b_gate_spread_result.json`
- 入库：`research/wo_w1/gate_funding/gate_spread_EWZ.jsonl`（700 行）+ `gate_spread_EWZ_manifest.json`
- 数据态：源 A=唯一数据态 /tmp/box_cache_w2a（snapshot_20261019，perfile-agg 2b2c9572…）

## 一、源定位结论（§6.2-1）

| 源 | 状态 | 证据 |
|---|---|---|
| A：box_cache EWZUSDT | ✅ 700 根，2024-03-04→2026-10-18 | md5 a982e0a7…（snapshot_20261019 成员） |
| B：Gate 原始 API EWZ_USDT | **缺源【数据受限·R5·非死】** | Gate.io 全部 **2205** 现货交易对无任何 EWZ 系对；EWZUSDT/EWZ_USDT candlesticks 实测均 `INVALID_CURRENCY_PAIR` |
| B'：导演站 EWZUSDT 实时（R5 替代路径） | ✅ 2000 根，2019-01-04→2026-10-20 | `/api/kline/EWZUSDT?limit=2000`（limit>2000 实测 422，2000=API 上限且已覆盖 A 全窗） |

**诚实标注（R7）**：B'=**同源不同 vintage（导演站），非两市场价差**。「Gate 两市场价差」两源口径因 Gate 缺 EWZ 系对而不可得；本件交付=对齐机制+入库序列+vintage 对拍读数，序列列名沿用 close_A/close_B 并在 manifest 声明 B 的真实身份。复活条件=Gate 上架 EWZ 系对或提供 EWZ_USDT 端点。

## 二、对齐与价差序列（§6.2-2/3，按日 inner join，缺日禁插值）

- `abs_gap(t)=|close_A−close_B|`、`rel_gap_bp(t)=200×(A−B)/(A+B)`（对称相对价差）。
- 复权声明：两源均原始日 K 无复权标记（manifest 已声明，无需停机核对）。
- 低量日标注：`low_liq = (vol_A==0) OR (vol_A<P10(vol_A))`，P10=129 万股（【口径操作化·R7】以 A 源 volume 为口径）；低量日 70 天（10.0%）。

## 三、描述统计（两序列并排，§6.2-4）

| 指标 | 值 |
|---|---|
| 对齐日 n | **700**（≥500 ✓） |
| 覆盖窗 | 2024-03-04 → 2026-10-18（A∩B'） |
| abs_gap mean / median / P95 | 0.00056 / **0** / **0** |
| abs_gap max | **0.39（2026-10-18）**＝A 快照末根（盘中/未定根）vs B' 已定根 |
| rel_gap_bp mean / P95 | −0.0013bp / 0bp |
| \|rel_gap_bp\|>50bp（0.5%）日数 | **0** |
| 缺日清单 | **0 天**（A 全部交易日 B' 均有） |

**读数**：同源两 vintage 逐位基本一致（中位/P95 价差=0），唯一分歧在 A 快照截至根（10-18）——vintage 对拍通过，缓存数据态可信度佐证；真实两市场价差待 Gate 源复活后按同管线补算。

## 四、完备性门（§6.2-6 冻结）与查重

- 门：n≥500 ✓ 且 2025-06-01（realA 起点）后覆盖完整 ✓ → **PASS**（覆盖口径=两源交易日并集，【口径操作化·R7】自然日历会把周末误报为缺口）。
- 查重：symbols_reconcile.json=池级 241→144 对账（无标的级价差序列），本件为首次入库，无重复；与工单⑤只共享数据目录，判线互不污染。
- 纪律：数据件无生死判线；缺源不顶替、缺日不插值；不改部署姿态（R10）。
