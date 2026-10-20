# METHOD_BOOK_DECBAR — 判定轮 bar 选择口径方法书（WO-DECBAR）

- 签发：交易分析团队 10 席位全席议事，首席策略官·何执舟终裁
- 日期：2026-10-20（紧急工单：今早 08:30 判定轮被 fail-closed 误拒，用户已授权「修」）
- 效力：本方法书是 `f1_signal.py` 判定轮 bar 选择/拒绝语义的**唯一工程依据**，工程侧照抄改引擎；
  与 F1_台账口径_v1.md §一「周调仓信号日」定义兼容，不改成交语义（收盘出信号、次日开盘成交）。
- 触发场景（回归锚，复现细节见 §四）：数据源在判定轮返回「最后一根 bar 日期=当日 10-20（盘中未落定）+
  前一日 10-19（已完整）」，引擎按旧语义整轮拒绝（guard_last_bar 原话：「最后一根日K日期 2026-10-20 >=
  当前 UTC 日 2026-10-20：未收盘的部分K（intraday），禁止进入周调仓锚定与信号判定」），导致本周榜单缺位。

---

## 〇、一句话新口径（终裁）

> **判定轮必须「剔除」当日未收盘 bar 并基于最后完整日 bar 判定，而不是因数据源含当日盘中 bar 就整轮拒绝；拒绝仅保留「数据陈旧」与「周调仓时序错位」两类。**

旧语义（f1_signal.py:709-727 `guard_last_bar`）把「数据源含未落定 bar」本身当拒绝理由，混淆了
「数据源给什么」与「判定用哪根」两件事——24/7 数据源普遍会附带当日 forming bar，这不是数据缺陷。

---

## 一、正确语义：周调仓信号 = 每周首个交易日（纽约）收盘口径

1. 周调仓信号日定义（口径 §一，不变）：**每周首个交易日收盘出信号，次日开盘成交**。
2. 时序事实：纽约周一日K（10-19）在其收盘（ET 16:00 = 北京周二 04:00）后即为完整 bar；
   按 DAILY_BAR_SETTLE_UTC_HOUR=0 的落定规则，日期 D 的日K于 D+1 日 00:00 UTC（北京 08:00）落定。
   北京周二 08:00/08:30（=UTC 00:00/00:30）跑判定轮时，10-19 bar **已完整、可判定**。
3. 数据源同时附带的 10-20 当日 bar（still-forming 盘中K）对周调仓判定**无信息增量且未落定**——
   正确处置是**剔除（trim）**，不是拒绝。剔除后日历上最后完整日 bar（10-19）即判定锚。
4. 因此：今晨 08:30 轮的判定**必须基于 10-19**，且 10-19（纽约周一）=本周首个交易日 ⇒ is_signal_day=True。

## 二、fail-closed 新语义：拒绝条件收窄为两条（任一命中即拒）

新函数 `trim_and_guard(cal, now)`（替代现行 guard_last_bar 在判定轮的语义）：

```
输入 cal（日K 日历，升序）、now（默认当前 UTC）
S1  trim：剔除 cal 中日期 >= today_utc 的所有 bar（forming 盘中K），得 cal_settled / last_complete
S2  拒绝条件：
    R-陈旧：today_utc − last_complete > N（N=7 自然日）→ 拒绝（数据陈旧/断源/断更）
    R-错位：today_utc 为工作日（周一~五，NY 假日未知时宁严）且
            (today_utc − last_complete > 4 自然日 或 last_complete 落在周末)
            → 拒绝（周调仓时序错位：本应已有更新的已收盘 bar 却缺失）
S3  通过 → 判定基于 last_complete，guard 返回 settled=True、asof=last_complete、
    并在 f1_guard.log 记 TRIM_INTRADAY{trimmed:[...], last_complete:...}
S4  R-错位命中但 R-陈旧未命中 → 拒绝同时在日志标 CALENDAR_SUSPECT
    （NY 连续假日如圣诞周可能误伤，留人工核；宁拒勿漏不变）
```

**N=7 的依据**：
- 正常最坏间隔 = 周五 bar 在下一交易日（周一）判定 = 3 自然日（跨周末）；
- 叠加单个 NY 全市场假日（周一休市）= 周五 bar 在周二判定 = 4 自然日；
- 现代美股历史最长闭市为 9/11（2001-09-11 起 4 个交易日），跨约 6 自然日；
- 取 N=7：既覆盖极端闭市不误拒，又能保证日更数据源断更一周内必然触发拒绝（拦截断源）。
  R-错位的 4 自然日内层闸保证周调仓时序敏感错位被更早拦截，7 日仅作外层兜底。

**不变的部分**：`check_data_integrity`（重复时间标签，f1_signal.py:616）仍前置拒绝；
探活 DEGRADED 冻结、R15 sha 对表闸门、`_emit_frozen` 冻结产出路径全部不动。

## 三、周调仓信号日语义保真

1. 剔除当日 bar 后，`cal_settled` 只含完整日K，`week_first_days(cal_settled)`（f1_signal.py:227）
   按完整 bar 的 ISO 周分组取每周首个交易日——**不受 24/7 数据源附带 forming bar 影响**，
   is_signal_day 判定天然回到「纽约周交易日历」语义。
2. is_signal_day := (last_complete ∈ week_first_days(cal_settled))。asof 恒为 last_complete。
3. **相邻信号日边界**：周一生成的信号在周二盘中跑（周二 08:30 判定轮，最后完整日=周一）时，
   asof=周一、is_signal_day=True——判定仍锚定周一收盘口径，周二轮是**同一信号的重复产出**；
   push 去重 key=`decide:<asof>`（f1_signal.py:740 起 push_plan）保证同一 asof 只推一次，语义自洽。
4. 非信号日轮次（如最后完整日=周三）：is_signal_day=False，照常产出横截面参考
   （signal_rule 字段已注明「本表为最新横截面评分参考」），不给调仓操作指令——现行语义保留。
5. 回放/replay（f1_signal.py:240 起双账本）与月度归档天然只看完整 bar，无需改动。

## 四、复现锚（回归用例，并入 run_scenario_checks.py 风格）

**锚名：DECBAR-20261020**
- 输入：now=2026-10-20 00:30 UTC（北京 08:30）；数据源日历尾部 = [..., 2026-10-19（完整）, 2026-10-20（盘中 forming）]
- 期望：
  1. trim 掉 2026-10-20，判定基于 2026-10-19；`asof == '2026-10-19'`；
  2. `is_signal_day == True`（10-19 纽约周一 = 本周首个交易日，按周一收盘口径）；
  3. f1_live.json 正常产出（非 _emit_frozen），meta/guard 记 `trimmed_intraday: ['2026-10-20']`；
  4. f1_guard.log 新增一条 `TRIM_INTRADAY`；
- 反例锚：
  - 输入尾部仅到 2026-10-12 且 now=2026-10-20 → R-陈旧（8 日 > 7）拒绝；
  - 输入尾部到 2026-10-14（周三）、now=2026-10-20（周二，工作日）→ R-错位（6 日 > 4）拒绝 + CALENDAR_SUSPECT。

## 五、对历史判定零改动声明

- 历史判定（如 asof=2026-10-17 及此前）**零改动**：当时数据源不含当日 forming bar，trim 集合为空，
  trim 后日历与原日历逐日相同，判定结论、回放、月度账本、熔断基准（CB3_BASE_60D 冻结常量）均不变。
- 本方法书只改「判定轮入口的 bar 选择/拒绝语义」，不改因子、评分、仓位、熔断、成交语义任何数值。

## 六、工程施工要点（工程侧照抄）

| # | 位置 | 改动 |
|---|---|---|
| 1 | f1_signal.py:709-727 `guard_last_bar` | 保留原函数（快照轮仍用其 settled 判定展示语义），**新增** `trim_and_guard(cal, now)` 实现本方法书 §二 S1–S4 |
| 2 | f1_signal.py:958-964 run_live 入口 guard | `guard_last_bar(_cal0)` 拒绝逻辑替换为：先 trim（load_data 后、build_factors/replay 前）再对 cal_settled 走 R-陈旧/R-错位两判 |
| 3 | f1_signal.py:642-647 `current_signal` | cal 用 trim 后日历；guard 拒绝条件同步替换；asof/is_signal_day 按最后完整日 |
| 4 | f1_signal.py:786-790 `run_snapshot` | 不动（快照轮本来就取 cal[-2] 兜底，行为兼容） |
| 5 | 日志 | 新增 `TRIM_INTRADAY`、`CALENDAR_SUSPECT` 两类 f1_guard.log 事件（走 _log_guard） |
| 6 | sha 闸门 | 改引擎=新工单：重算 engine_sha256 并同步更新 AUTHORITY_SHA.json（R15 fail-closed 对表） |
| 7 | 测试 | DECBAR-20261020 主锚 + §四两反例锚入 run_scenario_checks.py；全绿方可部署 |
| 8 | crontab | 08:30 前移轮与 09:25 现行轮读同一根最后完整 bar，二者语义等价（f1_crontab.txt 注释已备案），可选启用 |

## 七、10 席位议事纪要 + 首席终裁

| 席位 | 意见摘要 |
|---|---|
| 数据源席 | 24/7 源附带 forming bar 是常态而非污染；trim 是唯一自洽处置。同意。 |
| 回测席 | trim 仅作用于入口日历，replay 双账本零影响；历史零改动成立。 |
| 时序席 | 落定规则 00:00 UTC 与纽约收盘（北京 04:00/05:00 随 DST）之间留有 3~4h 余量，08:00/08:30 跑判定安全。 |
| 风控席 | 拒绝收窄不等于放水：陈旧/错位两闸保留 fail-closed，宁拒勿漏原则不变。 |
| 量化席 | N=7 依据充分（3 日正常上界 → 4 日假日 → 6 日极端闭市 → 7 日兜底）。 |
| 工程席 | 改动面收敛在 guard_last_bar 语义与 run_live/current_signal 两处入口，sha 闸门必须同步。 |
| 合规席 | 剔除≠篡改：trim 事件全量落 f1_guard.log append-only，可审计。 |
| 产品席 | 用户今晚 21:30 买入依赖本周榜单，今晨误拒必须当日修复并以复现锚验收。 |
| 空头席 | 唯一风险是 NY 连续假日误触发 R-错位，CALENDAR_SUSPECT 标记 + 人工核可兜住。 |
| 多头席 | 10-19 为本周首个交易日，判定基于 10-19 完全符合周调仓口径，无语义漂移。 |

**首席策略官·何执舟终裁**：全席一致，批准 §〇～§六全部条款，即刻生效。
裁定要点背书——「数据源给什么是它的事，判定用哪根是引擎的事；引擎只吃完整日K，
盘中K剔除入日志，陈旧与错位才拒绝。」以 DECBAR-20261020 为永久回归锚，改引擎必跑此锚。
