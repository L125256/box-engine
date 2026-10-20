# DECBAR_FIX_REPORT — WO-DECBAR 引擎修复 + 本周判定补跑报告

- 工单：紧急（用户已授权「修」），2026-10-20
- 唯一依据：`engine_f1/METHOD_BOOK_DECBAR.md`（交易分析团队方法书，首席策略官·何执舟终裁）
- 施工：工程席单 agent 5 席全席，照方法书 §六施工要点逐条执行
- 回归锚：**DECBAR-20261020**（永久锚，改引擎必跑）

---

## 一、引擎修复结果（锚验收 PASS）

按方法书施工要点：

| # | 位置 | 改动 | 状态 |
|---|---|---|---|
| 1 | f1_signal.py `guard_last_bar` 后 | 新增 `trim_and_guard(cal, now)`（§二 S1–S4：trim forming 盘中K；R-陈旧>7 自然日 / R-错位（工作日轮次>4 日或落周末）两判；CALENDAR_SUSPECT 留痕） | 完成 |
| 2 | `run_live` 入口 | 先 trim（load_data 后、build_factors/replay 前），再对 cal_settled 两判；判定/回放/熔断/宽度一律只吃剔除后日历 | 完成 |
| 3 | `current_signal` | cal 用 trim 后日历；拒绝条件同步替换；asof/is_signal_day 按最后完整日 | 完成 |
| 4 | `run_snapshot` | 未动（快照轮 guard_last_bar 语义不变） | 不动 |
| 5 | 日志 | `TRIM_INTRADAY` / `CALENDAR_SUSPECT` 两类 f1_guard.log 事件（append-only） | 完成 |
| 6 | sha 闸门 | engine_f1/ 与 f1/ 两处 AUTHORITY_SHA.json 重登记，batch=DECBAR-20261020 | 完成 |
| 7 | 测试 | run_scenario_checks.py 新增 DECBAR 组（DC1–DC4）；I2 按新语义改判定 | 完成 |

**回放/熔断/成交语义零改动**：replay/eval_breakers/monthly_accounts/_emit_frozen/探活冻结/sha 对表一行未动；
`f1_backtest_v2.py`/`f1_datasource.py` sha 沿袭上批未变（见下表）。

### 场景检测（run_scenario_checks.py 全量）

**PASS 89/91**。DECBAR 组 4/4 全过：

- **DC1 主锚 PASS**：真实缓存（刷新后尾部=[10-19 完整, 10-20 forming]）端到端 run_live
  → `asof=2026-10-19`、`is_signal_day=True`、`guard.trimmed_intraday=['2026-10-20']`、
  非 `_emit_frozen` 正常产出、f1_guard.log 新增 TRIM_INTRADAY。
- **DC2 反例 R-陈旧 PASS**：尾部 10-12、now=10-20 → gap=8>7 → 拒绝（R_STALE）。
- **DC3 反例 R-错位 PASS**：尾部 10-14（周三）、now=10-20 → gap=6>4 → 拒绝（R_MISALIGN）+ CALENDAR_SUSPECT 入日志。
- **DC4 历史零影响 PASS**：asof=10-17 场景 trim 集合为空，gate idx/ma50（218.5703/236.3814）、
  top5（EWZUSDT/SHOPUSDT/VUSDT/EBAYUSDT/GMEUSDT）、is_signal_day=False 与既有落定 f1/f1_live.json 逐位一致。

2 项 FAIL（**均与本工单无关的既有环境漂移，本单未触碰**）：
- T5：`F1_台账口径_v1.md`/`index.html`/`f1_live_intraday.json` 三件 f1/ 归档副本与 /workspace/f1_web 部署位 sha 漂移（改前即漂移）；
- T6：/workspace/box_web/index.html 缺 B9/B10 标注（改前即缺失）。

## 二、sha 闸门前 后对照

| 文件 | 前（WO-AUDITFIX-01-2026-10-19） | 后（DECBAR-20261020） |
|---|---|---|
| f1_signal.py | 6acc937de54584fa…cb68a48c | **dc72783486daf4b2…ecd63b6** |
| f1_datasource.py | c263444785e80e2c…c56b758ebd | 同前（零改动） |
| f1_backtest_v2.py | 48aa668da1e5b6eb…5ea790712 | 同前（零改动） |

- 两处登记表（engine_f1/、f1/）同步更新，batch=**DECBAR-20261020**，generated=2026-10-20；
- 归档副本 `f1/f1_signal.py` 与主本 `cmp` 逐字节一致；
- `check_engine_authority()` 运行时对表 PASS（batch=DECBAR-20261020）。

## 三、本周判定结论（用户 21:30 买入榜单底座，f1/f1_live.json）

- **数据 asof：2026-10-19（纽约周一收盘完整 bar）**；主源 kxiandaoyan 可达已刷新（176/176 成功），
  10-20 盘中 forming bar 已按新口径剔除（guard.trimmed_intraday=['2026-10-20']，TRIM_INTRADAY 留痕）。
- 判定轮：NORMAL 主源单源模式（新浪备源停用），非冻结产出，operable。
- **闸状态：关（清仓持币）**——idx 222.6637 < MA50 235.9333，gate.status=red（regime 闸）。
- **is_signal_day=True**（10-19=本周首个交易日，周调仓锚定正常）。
- **top5（周信号参考排名，闸关期间不建仓；闸门重开后下一信号日按此优先）**：
  1. EWZUSDT（1.7967） 2. EBAYUSDT（1.6307） 3. TEAMUSDT（1.5866） 4. VUSDT（1.5571） 5. SHOPUSDT（1.4874）
- **单票仓位：2.5%（起步档 tier 0，四档表 2.5/1.5/1.0/0.5%）；总敞口上限 12.5%（2.5%×5）**。
- **四灯全绿**：CB1 回撤闸 green / CB2 止损闸 green / CB3 频次观察 green / FEE 费用闸 green，总灯 green「正常运行」；无冻结（freeze_days_left=0）。
- **breadth：27.78%**（40/144 标的站上自身 MA50，window 50 / min_periods 40）。
- 崩市检查：池单日中位 +0.26%，未触发（线 −5%）。
- ⚠️ 操作语义提醒：regime 闸红灯=**不开新仓、存量按止损/崩市/换仓退出**（页面 G1/G3 口径）；
  top5 为闸关期参考排名，非「现在买入」指令——请结合 21:30 实际决策。

## 四、影子期首采（SHADOW_SPEC_v1）

- `shadow_cells.py --auto` 随判定轮挂接**首次真实执行成功**：状态落盘 `f1/shadow_state.json`
  （created 2026-10-20，round_asof=2026-10-19，protocol SH-1..SH-6+§3+§4）。
- S1/S2/S3=ACCUMULATING 0/20（本轮新增 0，**规格内**：_OPS1 日频 IC 需 fwd5 满 5 交易日成熟，
  影子窗 2026-10-18 起，最早成熟读数约 10-27 起）；S4=SUSPENDED（补样 0/4，不采集不判读）。
- 旁路 forward_readout 同轮 ACCUMULATING 0/20（f1/forward_state.json round_asof→2026-10-19）。
- D0 基线（今晨 05:08 已跑）4 检查全 hit：域标签零漂移 / ATLAS 锚 diff=0 逐位 / S4 重放 hit / 补样基线 hit。

## 五、数据 asof 如实标注

- 判定锚 = **2026-10-19**（数据源主源实时拉取的最近完整日 bar；10-20 为 forming 已剔除）。
- 无「缓存旧 vintage」情形：主源探测可达，未启用缓存回退路径。
- 已知边界（空头席条款备案）：24/7 源含周末 bar，故**周一判定轮**（last_complete=周日）会按
  R-错位拒绝并标 CALENDAR_SUSPECT（宁拒勿漏，NY 连续假日同理留人工核）——今日（周二）轮次不受影响。

## 六、变更面（commit 不 push，推送另行授权）

- 改：engine_f1/{f1_signal.py, AUTHORITY_SHA.json, run_scenario_checks.py}、
  f1/{f1_signal.py, AUTHORITY_SHA.json, f1_live.json, forward_state.json, shadow_state.json(新)}、
  engine_f1/METHOD_BOOK_DECBAR.md（方法书入库）、本报告。
- 部署镜像同步（不入库）：f1_web/f1_live.json、f1_web/f1_state.json、/workspace/f1_web/ 同名两件。
- 未动：回放/熔断/成交语义、f1_datasource.py、f1_backtest_v2.py、页面、crontab、其他研究目录。
