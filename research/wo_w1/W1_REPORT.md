# W1 施工报告 · 资金费数据源（冻结规格 v1.0 · R8=Pool(32)）

工单：W1 ｜ 执行：工程保障团队（施工+自测）｜ 时点：2026-10-19（北京），UTC 2026-10-18T16:3x~16:45Z
规格：`/tmp/trade9_specs/W1_SPEC.md` + `w1_spec.json`（逐字执行；落库以 repo 快照为准）

---

## 一、可达性矩阵与预判对拍

复跑 58 端点（导演站 38 路径 + 新浪 20 端点，Pool(32)，完整 UA+Referer），留痕 `raw/w1_probe_rerun.json`。

### 导演站（kxiandaoyan.com）

| 状态 | 路径 | 与规格预判 |
|---|---|---|
| 200 JSON | `/api/signals`、`/api/kline/{S}`、`/api/symbols` | ✅ 一致 |
| 200 SPA HTML 兜底 | `/funding`、`/openapi/v1/funding`、`/swagger.json` | ✅ 一致（非 API） |
| 404 ×32 | funding×8 拼写变体、markPrice、premiumIndex、ticker/depth/trades、OI、多空比、income、exchangeInfo、markets/status/version/index、v1/klines 变体、quote/rate/docs/api/history | ✅ 一致 |
| 变更 | `/api/positions`：基准轮 TLS 超时 → 本轮复测 404 | ⚠️ 口径变更（更判死） |

**funding 字段：导演站全链无（38 路径复确认）。**

### 新浪（hq.sinajs.cn）

| 产品线 | 端点 | 本轮状态 | 与规格预判 |
|---|---|---|---|
| 美股现货 | `gb_aapl` | 200（需 Accept 头） | ✅ |
| 外盘期货 | `hf_CL/GC/BTC/SI/CAD` | 200 | ✅（无 funding） |
| 外汇 | `fx_susdcnh/eurusd/usdjpy`、`DINIW` | 200 | ✅（无利率字段） |
| A股 | `s_sh000001` | 200 | ✅ |
| 期权/场外/财报/利率 | `usAAPL_OQ`、`op_/of_/bt_aapl`、`SHIBOR/sofr/hl_usd` | 200 空串 | ✅ |
| 文档页 | `chyyshb.html` | 404 | ✅ |

**funding/隔夜利率字段：新浪全线无。**

### 对拍差异（3 条，均不推翻预判）

1. 规格文字写「37 导演路径」，实际冻结清单 38 条（规格表 404×34+200×3+超时×1=38，与冻结留痕一致）——文字笔误。
2. `/api/positions` 超时→404（判死依据更硬）。
3. 新浪 403 为**并发限频**非端点死亡：Pool(32) 突发下 5 端点瞬时 403，串行降频后 4/5 恢复；`gb_*` 反爬三件套实测 = **完整 UA + Referer + Accept: */***（已写入回填流程 headers_required）。

## 二、新端点入库与 144 池对账

- `/api/symbols` 全量落盘：`raw/dy_symbols_241.json`（血缘四元组齐备，fetched_at=2026-10-18T16:36Z）。
- 241 标的 = EQUITY 185 + COMMODITY 14 + CRYPTO 13 + HK_EQUITY 13 + KR_EQUITY 8 + PREMARKET 4 + INDEX 4。
- 对账 `cleaned_pool.json` kept 144：**缺失 0**（池 ⊆ 字典）；**新增 97**（含 BTCUSDT/ETHUSDT/XAUUSDT/SAMSUNGUSDT/TENCENTUSDT/HSI/VIX/DXY 等），明细 `raw/symbols_reconcile.json`。
- **字典漂移预警**：现抓分域与规格冻结口径「240 EQUITY+BTCUSDT」不符——导演站字典已扩容至 7 分域。池构建以现抓字典为唯一底表（激进席五-3 落地），逐会话心跳核对 `total==241`。

## 三、校验结果（首批 BTCUSDT/AAPLUSDT/AAOIUSDT）

对齐判据：最近同步快照 + 0/±1 天偏移探测取最小偏差；周日合成 bar 自动跳锚。常设件 `tools/w1_xval_pipeline.py`（每日 1 CRYPTO+1 高量+1 低量轮换，超差→口径复查→ALARM_FREEZE_SOURCE）。

| 层 | 对照 | 选中偏移 | 偏差 | 容差 | 判定 |
|---|---|---|---|---|---|
| CRYPTO | BTCUSDT vs hf_BTC | +1 天（10-16 bar） | −0.221% | ±1.5% | PASS |
| EQUITY 高量 | AAPLUSDT vs gb_aapl | 0 天（10-17 bar） | +0.023% | ±1.0% | PASS |
| EQUITY 低量 | AAOIUSDT vs gb_aaoi | +1 天（10-16 bar） | +0.172% | ±1.0% | PASS |

3/3 PASS，0 报警。偏移探测实证有效：BTC/AAOI 最优对齐均在 ±1 天档，逐日硬对齐必产伪偏差（规格空头席预判复现）。

轮换池缺口登记（不判死，R9 穷举后另议）：`hf_ETH`、`hf_SOL`、`gb_hanmi`、`gb_mvizy` 实测 200 空串 → CRYPTO 线轮换暂固定 BTCUSDT。

## 四、影子回填样本（血缘四元组齐备）

funding 列零改动：`FUNDING = 0.0003`（0.03%/bar 常数记账，engine_f1/f1_signal.py:68）。代理字段只进影子层。

```json
{"shadow_field": "cme_basis_pct", "value": 0.372, "asof_date": "2026-10-19",
 "source": "sina+kxiandaoyan", "path": "hq.sinajs.cn/list=hf_BTC + /api/kline/BTCUSDT",
 "fetched_at": "2026-10-18T16:44:07Z", "raw_snapshot": "raw/shadow_cme_basis_raw_2026-10-19.json",
 "headers_required": "full-UA+Referer+Accept(sina)", "bar_date_convention": "北京日期+盘后延伸+周日合成bar(dy)",
 "ledger_isolation": "影子层，禁入 funding 账本"}

{"shadow_field": "usdcnh_close", "value": 6.685, "asof_date": "2026-10-17",
 "source": "sina", "path": "hq.sinajs.cn/list=fx_susdcnh",
 "fetched_at": "2026-10-18T16:44:07Z", "raw_snapshot": "raw/shadow_usdcnh_raw_2026-10-19.json",
 "headers_required": "full-UA+Referer+Accept(sina)",
 "ledger_isolation": "影子层，禁入 funding 账本"}
```

## 五、失败路径执行：funding 判死归档

- 归档件：`raw/funding_death_archive.json` —— 58 探测证据全列（dy 200×3/HTML 兜底×3/404×32；sina 有数据×12/空串×7/404×1），funding/隔夜利率字段双源全无，R9 合规判死成立。
- **复活条件（冻结）**：①境外 API（Binance/Bybit 等）可达环境实测通过；②导演站新增 funding 端点（探测自动发现）。
- 判死≠报废：0.03%/bar 常数记账维持 + 缺口登记；代理线（CME 基差 regime 灯位）影子计算已开，同向率 <60% 自动降级「仅记录」。

## 六、心跳件说明（常设件）

| 工具 | 用途 | 节奏 |
|---|---|---|
| `tools/w1_heartbeat.py` | 每会话 3 端点心跳：dy `/api/symbols`（total==241 校验）、sina `gb_aapl`、sina `hf_BTC`；追加 `raw/w1_heartbeat_log.jsonl`，exit code 反映健康 | 每次会话开工先跑 |
| `tools/w1_probe_rerun.py` | 38+20 全量路径复跑（Pool(32)），funding 复活哨兵 | 每会话或可疑时 |
| `tools/w1_xval_pipeline.py` | 每日 3 只双源对照 + 影子回填 + 超差报警（北京业务日轮换） | 每交易日 |

心跳首轮（2026-10-18T16:45:04Z）：3/3 all_ok=true（dy total=241 / gb_aapl 200 / hf_BTC 200）。

## 产物清单

- `wo_w1_result.json` 汇总
- `raw/`：w1_probe_rerun.json、w1_sina_retry.json、dy_symbols_241.json、symbols_reconcile.json、w1_xval_run_2026-10-19.json、shadow_*_2026-10-19.json、funding_death_archive.json、w1_heartbeat_log.jsonl
- `tools/`：w1_probe_rerun.py、w1_xval_pipeline.py、w1_heartbeat.py

— W1 施工+自测完毕，commit 不 push。
