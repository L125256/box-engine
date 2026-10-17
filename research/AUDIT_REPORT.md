# R13 终验审计报告（审计席 · 独立于施工席与测试席）

- 日期：2026-10-18 · 被审对象：commit `795c4d3`（未推送）
- 立场：一切以盘上实据与本席自跑为准，不采信施工席/测试席声明；两席声明仅作交叉参照
- 本席自跑记录：`/tmp/r13_audit/`（frozen_test 沙箱、ab 双轨回放、f1_source_state.json.bak）
- 引擎指纹自验：`/workspace/repo_ready/engine_f1/f1_signal.py` sha256 = `ae92dfafc1b13603…`，
  归档副本 `/workspace/repo_ready/f1/f1_signal.py` 与 `/workspace/f1_web/index.html`=`f1/index.html` 逐字节一致

---

## 一、四工单逐项独立验证

### WO-R13-01 熔断线重标定 —— **PASS**
- **阈值落盘三处一致（本席自验）**：代码常量（f1_signal.py：CB1 −0.08/−0.04、CB2 −0.05/−0.025、费线 0.04/0.02、CB3 9.07×3=27.27 不动、CALIB_EPOCH='R13-2026-10-18'）= `f1_web/f1_live.json → meta.breaker_thresholds` 逐值一致 = `f1_state.json.calib_epoch` 一致且 `prev_reds` 已清空（迁移纪律生效）。
- **页面联动（本席读源码核验）**：index.html 全部阈值经 `T.CB1/T.CB2/T.CB3/T.FEE` 从 JSON 渲染；grep 旧字面量 21.7/10.85/0.32/0.217 于 index.html 0 命中；manual.html 唯一命中为 pp 单位词典示例（非活阈值）。
- **验收③独立复跑（本席 A/B 双轨）**：pre-R13 引擎（65bb3fd 版）vs 795c4d3 引擎，同缓存 slot=0.10 全量回放（2024-01-24~2026-10-17）：eq_net=2.2817 / eq_gross=2.4347 / stops=104 **逐位相同**，逐日持仓 767 天 **diff=0** → 重标定不改任何交易行为。
- **触发统计**：采信链=施工回放+测试席自实现计数+本席代码级复核（同源 `_roll_mdd`/滚动60日）三方一致（CB1 黄18、CB2 红5、CB3/费线 0）；本席未第三次全量重跑回放统计（时限控制），判 PASS 留 1% 保留。

### WO-R13-02 《F1 台账口径》v1 落库 —— **PASS（附 1 条编辑瑕疵，见 §五）**
- 五节齐全（引擎身份/推荐规则/禁止事项/出身标注/冲突裁决），阈值表已回填新值并标注旧阈值「已废止禁止再引用」，四条禁令完整可执行。详见 §五终验。

### WO-R13-03 快照旁路 —— **PASS（本席自跑实测）**
- 三轮 `snapshot --round {20:30|00:30|04:30}` 实跑：`f1_live.json`/`f1_state.json` md5 **前后不变**；输出 `writes={f1_state.json:false, f1_live.json:false}`；全文 **无 top5**；`meta.operable=false`、push `carries_decision=false` + 「盘中快照·不可操作」。
- 部分K不进锚定/判定：实跑 `live` 被 guard 拒绝（RuntimeError「最后一根K日期 2026-10-17 >= 当前 UTC 日…」）并落 `f1_guard.log` REFUSE_DECIDE —— 本席以真实时钟触发，非模拟。
- 推送去重：代码级核验 `push_plan()`（判定轮 `decide:<asof>`、盘中轮 `intraday:<asof>:<round>`）+ 场景矩阵 I5 实算，逻辑正确。

### WO-R13-04 数据源容灾 —— **PASS（附 1 条「存疑」，见 §四）**
- **判死→降级（本席自跑 drill）**：8/8 PASS；trace 实录 NORMAL→(fail×2)→DEGRADED→(ok×2)→RECOVERING→验收(1%≤2%)→NORMAL；事件日志 DEGRADE/RECOVERING/RECOVERED 齐全。
- **冻结实质（本席沙箱补验真实 `_emit_frozen` 路径）**：`F1_PRIMARY_FAIL=1` 连续 2 周期 → DEGRADED；`run_live` 走 `_emit_frozen`：signal/breakers/state/monthly_accounts 四棵判定树**逐字段 diff 仅 2 个新增标注键**（`operable=false`、`frozen_by_source_failover=true`），实质判定内容逐位不变；`f1_state.json` 未创建；banner 说人话完整。
- **新浪白名单（本席自跑）**：白名单 6 只（top-5+1 代理）≤`MAX_PROXY_SYMBOLS=6`；144 全量请求被 ValueError 硬拒（`fetch_sina_daily` 首行检查，无全量代码路径）；symbol=小写基础代码、带 `Referer: https://finance.sina.com.cn`、`source='sina'` 打标。
- 验收不过挂待人工：本席核对代码路径（`pending_manual=true`，无自动强切分支）+ 自测 R19/矩阵 J5 实算 10%>2% → 成立。

---

## 二、夹带排查（git diff ae41f50 → 795c4d3，43 文件）

**结论：未发现无法归因的改动。** 逐文件归因：

| 归因 | 文件 |
|---|---|
| 65bb3fd（四席会文档，非施工改动） | research/verdict.md（重写）、research/work_orders.json（新增） |
| WO-01 | f1_signal.py（常量+breaker_thresholds+update_state 迁移）、index.html、manual.html、f1/f1_live.json（meta 新键+数据刷新）、f1/f1_state.json（calib_epoch+prev_reds 清空）、run_checks.py（夹具阈值同步更新，+41 行均为夹具重标定，无弱化）、README.md |
| WO-02 | F1_台账口径_v1.md |
| WO-03 | f1_signal.py（snapshot/guard/push_plan）、f1_rounds_r13.md、f1_crontab.txt（三轮只读注册）、f1/f1_live_intraday.json（运行产物） |
| WO-04 | f1_datasource.py（新增 504 行）、f1_source_state.json/f1_guard.log（运行产物） |
| 测试与取证（已批自测义务） | breaker_stats_r13.json、replay_breakers_r13.py、run_r13_selftest.py、r13_selftest_result.json、r13_failover_drill.json、run_scenario_checks.py（+248 行 H/I/J 组，无弱化）、checks/scenario 结果 json、f1/render_harness.cjs（归档同步既有文件）、f1/ 下 run_checks/run_scenario_checks/sync_archive 等归档副本 |
| 卫生（良性） | engine_f1/__pycache__/*.pyc 删除 |

**夹带排查中列出的 3 条瑕疵（非夹带，如实列出）**：
1. **运行时产物入库**：f1_guard.log、f1_source_state.json、f1_live_intraday.json、各 *result.json 被 commit。属测试取证可归因，但运行态文件随每次运行漂移（本席复跑已使盘上状态与 commit 版不一致），建议 .gitignore。
2. **crontab 任务3 的 `--out` 参数从未被 main() 解析**（R11' 起 docstring 即虚标 `[--out ...]`）：R13 将其固化进 f1_crontab.txt:12，月度归档任务实际会把 live 输出覆盖写到 `/workspace/f1_web/f1_live.json`（内容相同、破坏性低），月报归档永远不落盘。**既有潜伏缺陷被搬运固化**，非四工单引入，建议 R14 修复。
3. 本席审计复跑自身改动了 engine_f1 的 f1_source_state.json / f1_source_events.log（drill 会 _reset），已备份原状态至 /tmp/r13_audit/f1_source_state.json.bak。

---

## 三、红线重扫（13 条一致性红线 @ 新页面）—— **13/13 PASS**

| # | 要点 | 结果 |
|---|---|---|
| 1 闸判定 | 「不出新仓，老仓位按止损/崩市/换仓规则照常退出（不是立即全部卖出）」index.html:77 | ✅ |
| 2 信号时点 | 「周首个交易日收盘定名单，次日开盘成交」:81/:106 | ✅ |
| 3 top5 | 「相对分」，无绝对承诺 :106 | ✅ |
| 4 止损 | 「跳空日实际亏损可能更大（GPRO −12.2%）」:158 | ✅ |
| 5 崩市 | 「池中位（一半以上标的）<−5% 次日清仓」:93 | ✅ |
| 6 CB1 | 红−8%/黄−4% 读 JSON | ✅ |
| 7 CB2 | 「毛账触发+净账确认才红灯」读 JSON :121 | ✅ |
| 8 CB3 | 「只观察不动仓」「不会自动升/降仓」:122 + manual | ✅ |
| 9 费线 | 读 T.FEE，无写死 :149 | ✅ |
| 10 档位 | 「降档自动、升档人工复核解锁」:115 | ✅ |
| 11 让渡 | 「正=跑输躺平/负=跑赢」，中性配色 :138/:180 | ✅ |
| 12 毛净双轨 | 无分裂暗示 | ✅ |
| 13 回放≠实盘 | 「历史模拟（非实盘）」:164 | ✅ |

**检测矩阵弱断言回潮：发现 2 处（低危，实测不掩盖缺陷）**
- `run_r13_selftest.py` **R10**：else 分支 `raised = bool(g_settled['settled'])` 恒真——若 current_signal 未抛错仍会 PASS。对照组 run_scenario_checks.py **I2** 写法正确。实测该路径真实抛错（本席 live 实跑被拒），故未掩盖实际缺陷，但属弱断言，应改写。
- `run_r13_selftest.py` **R16** 与 drill **DR2**：冻结比对为空洞成立——`freeze_payload()` 只读不写，f1_live.json 判定字段「不变」必然为真；**真实 `_emit_frozen` 路径未被自测覆盖**。本席已在沙箱实跑该路径补验（实质不变，见 §一-WO-04），结论未翻案，但断言须修为「调用 _emit_frozen 后逐位比对」。

---

## 四、安全审计 —— **PASS（附 2 条低风险建议）**

1. **凭据**：f1_datasource.py / f1_signal.py 及全部新增脚本 grep token/password/secret/api_key/authorization/bearer/cookie 0 命中；新浪 adapter 仅发 `Referer: https://finance.sina.com.cn` + 通用 UA，无任何凭据；主源凭据在仓库外（/root/.codebuddy/artifact/kx-combo 的 KxClient），未进仓库。✅
2. **并发写保护**：三个落盘点（f1_source_state.json、f1_live.json、f1_live_intraday.json）均走 `tmp + os.replace` 原子替换，无 torn file；事件/guard 日志为 O_APPEND 单行写。**无文件锁**：cron 判定轮与手工 `f1_datasource.py check` 并发时存在 load→modify→save 丢更新窗口（低风险，单写者为主）。建议：状态机文件加 flock 或约定单写入口。
3. **日志**：f1_guard.log / f1_source_events.log 实查内容仅含时间戳、日期、标的代码、价格偏差、拒绝原因，无用户敏感信息（引擎不接触用户数据）。✅
4. 低风险备注：`F1_PRIMARY_FAIL=1` 环境变量若误留生产 cron 会导致主源被永久判死（fail-safe 方向=冻结不出错信号，有「仅测试用」文档标注）。

---

## 五、《F1 台账口径》v1 终验 —— **PASS（附 1 条编辑瑕疵）**

- 五节完整性 ✅；阈值表与代码/JSON 逐值一致 ✅；旧阈值废止声明 ✅；「阈值随敞口走，升敞口=新工单」✅；推荐规则买/卖/等三分 + 执行价=次日开盘 ✅；四条禁令均可执行（有明确判据：sha256/asof/落定时刻）✅。
- **遗漏场景覆盖核查**：空仓态问「现在买什么」→ §二③ 持币=等待、不得擅自给标的 ✅；盘中/部分K/降级冻结问 → §二③ asof 非当日落定=等待 + §四标注义务 ✅；冻结期 → §二③④ ✅；引擎换版 → §五.3 停用+报差异 ✅。
- **瑕疵（D-1）**：§一 内部编号歧义——参数全表自身编号 1–11（第 8 行=崩市），其下又有小节「### 8 · 熔断阈值表」，「§一.8」双重指向（R13_DEPLOY.md:93 即引用「口径书 §一.8」）。作为「未来对话唯一权威依据」的文件不应有歧义编号，建议修订（改为 §一.12 或独立节号），属编辑级、不动实体内容。
- WO-02 验收「用户确认生效」未完成——属发版闸门既定流程，非文件缺陷。

---

## 六、存疑项清单

| # | 级别 | 事项 |
|---|---|---|
| Q-1 | 存疑（功能缺口，fail-safe 方向） | **RECOVERING→NORMAL 的「自动切回」未接线**：run_live 调 `DS.transition()` 不传 consistency（f1_signal.py:804），transition 在 RECOVERING+consistency=None 时永远维持待验收；一致性验收只能外部手工构造调用（drill/自测即如此）。工单要求「自动切回」，实现只到「自动进 RECOVERING+验收函数在位」。降级方向安全（宁可冻结不出错信号），不阻断发版，但需 R14 补线或明确「验收=人工流程」并回填文档。 |
| Q-2 | 存疑（状态机边界） | RECOVERING 期间主源再次失败（round_ok=False）时状态滞留 RECOVERING、consec_fail 累加但不回退 DEGRADED——行为未定义，建议补规则（回退 DEGRADED 或显式维持并告警）。 |
| Q-3 | 备注（表述口径） | 「判定字段逐位不动」实际=实质判定内容逐位不动+新增 2 个可操作性标注键（与测试席备注一致，本席逐字段证实仅此 2 键差异）。建议施工/文档表述按测试席建议修正。 |
| Q-4 | 备注 | 费线 4pp/2pp 重标定后仍 0 触发（结构性弱活线，实测峰值 1.6pp vs 黄线 2pp）——施工/测试已如实标注，交交易团队复分析决策是否再降档，不阻断。 |
| Q-5 | 备注 | G4 既有 11 天持仓偏差（BUG-04 口径差，非 R13 引入）：本席 A/B（pre vs cur 引擎持仓 diff=0）独立佐证「非 R13 引入」成立；升版工单移交交易团队。 |

---

## 七、发版建议

**GO（有条件）**——前提是以下 5 条作为 R14 尾巴工单/发版前处置（均不改变 R13 实体结论）：
1. Q-1：RECOVERING 自动验收补线，或在台账/crontab 注释中明确「一致性验收=人工触发」；
2. 弱断言修复：run_r13_selftest R10 恒真分支、R16/drill DR2 空洞比对（改为真实调用 `_emit_frozen` 后逐位比对）；
3. crontab 任务3 `--out` 失效修复（或删除该任务）；
4. 台账口径 §一.8 编号歧义修订（修订=新工单+用户确认，按口径书 §五.5 执行）；
5. 运行时产物（*result.json、f1_guard.log、f1_source_state.json、f1_live_intraday.json）gitignore。
另按既定闸门：发版仍需交易团队复分析（G4 11 天、费线弱活线两项）+ **用户授权**（未授权不 push / 不注册 cron）。

—— 审计席 · 2026-10-18 · 全部结论可由 /tmp/r13_audit/ 与文内复现路径复跑
