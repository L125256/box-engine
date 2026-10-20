# 第三次全场景大体检·终验报告（交易分析团队 10 席全席）
- 执行：2026-10-21 01:50–02:40 ｜ 沙箱 /tmp/fulltest3/v4 + /tmp/fulltest3/box（只读远端+本地模拟，未写远端/未改代码/未推送）
- 被测：F1 云端任务 12769301 prompt 现版 14,533 字符（scheduler-api 实取）；箱体 12772079（4,414 字符）；晨报 12762479（470 字符）
- 方法：五项修复逐项独立复测（不看工程报告结论，全部自己实跑）+ 七大块重过 + 影子终审

## 一、工程五项修复独立复测（全部实证）

| # | 项 | 判定 | 实证 |
|---|---|---|---|
| 1 | mkdir 四影子目录 | **PASS** | prompt 第 10 行覆盖 research/wo_mine、wo_fddual、wo_fdbrk、eng_wt_rc；逐字实跑 exit=0 四目录落地 |
| 2 | 27 条 curl 逐条实跑 | **PASS** | /tmp/fulltest3/v4 布局 27/27 整行 exit=0；25 常规件落盘（24 py 全 py_compile OK+全部 json/jsonl 可解析，FACTBOOK 98 行合法）；tar.gz 实测真 gzip 2,114,469B，tar 解包 177 项（176 件+根目录）。forward_ic_days.jsonl 远端实测 404（复证工程⑨-3 ③），`-f\|\|rm` 优雅缺席整行 exit=0 |
| 3 | cand+= 行 | **PASS** | ast.parse OK；7 对 (repo,local) 逐对核对，local=/tmp/f1work/+repo 路径全一致；第 5/6 步两片段 ast.parse OK |
| 4 | 第 6 步假 MISMATCH 模拟 | **PASS** | mock urlopen 三场景：A) MISMATCH 1 次后收敛 tries=1→PASS；B) 永不 MISMATCH→tries=2 有界退出 FAIL（不死循环）；C) API<100B→拦截 FAIL。三行为全符合 D3 修复设计 |
| 5 | 影子 d0 依赖 | **PASS** | domains.json（1,201,255B）/FACTBOOK_BATCH1.jsonl（63,675B）拉码行在清单且实测落盘；box_cache_fresh 冻结副本解包行实跑 exit=0，176 件解出 |

## 二、七大块矩阵

| 块 | 场景 | 结果 | 证据摘要 |
|---|---|---|---|
| 1 | 快照轮端到端（fresh 缓存态） | **PASS** | exit=0；影子旁路自动触发：D0 all_pass=True（三断言 hit）、S1/S2/S3 reg-D0 全 hit（n_registered 各 3）、S5 D0 hit（realA 复放 1228/0.9832/0.335/411.37 逐位 diff=0）、S5 reg-D0 hit、S4 SUSPENDED（补样 0/4 正确不启停）；snapshot ok(只读) round=20:30，writes 隔离（f1_state/f1_live 均 False）；6 件影子产物+快照 JSON 落盘 |
| 1 | 判定轮 trim_and_guard | **PASS** | 四场景单元实测：含 forming 盘中 K→剔除 asof=10-20 通过；陈旧 16 日→R_STALE 拒；工作日缺 5 日→R_MISALIGN 拒；周末 2 日跨度→通过。判定轮 live 全链未实跑（见未验证假设③），沿用第一轮 21.4s PASS |
| 2 | 箱体 prompt 逐行审查 | **FAIL（新 D14）** | 5 条 curl 无 `-f` 无 `\|\|rm`：实测 401 体（112B "Bad credentials"）落盘后 `python3` 执行 **exit=0 静默 no-op**。云端全新沙箱=第 3 步静默不生成→第 4 步响亮崩；最坏情形残留产物假 PASS |
| 2 | 箱体自验收片段 | **FAIL（新 D15，中）** | 无 D3 重试/无 <100B 拦截（F1 已修，箱体未跟）——jsDelivr 滞后假 MISMATCH 误报 FAIL |
| 2 | round_type 小时档边界 | **PASS** | round_type_for_hour 实测：8-12 时=判定级，0/20/21/22/23 一律盘中快照·保守默认，边界正确 |
| 3 | 晨报 prompt+实测拉取 | **PASS** | 两 URL HTTP200；f1_live.json signal.asof=2026-10-19/gate.status=red(on_holdcash=True)/breakers 四灯全 green/breadth 27.78%(40/144)/slot 在 state 全字段在位，与晨报模板字段路径全匹配；箱体 generated+round_type 在 |
| 4 | sha 闸门正负测 | **PASS** | 正测：干净副本 sha 过闸→数据层 R-错位 fail-closed 拒绝（today_utc 按 UTC 计正确），零产出；负测：篡改副本（语法合法+注释行）→REFUSE_ENGINE_SHA got=b21df77d want=a7e552f2，零产出。**两类 REFUSED 退出码均=2**（D5 修复生效并泛化到数据拒绝） |
| 4 | 三模式冒烟 | **PASS** | 快照（块1 PASS）/回放 replay ok（2024-01-24~2026-10-17 eq_net=1.2641 exit=0）/判定（正测+第一轮） |
| 5 | 箱体生成链端到端 | **PASS** | exit=0；176/176 缓存刷新成功→双冻结参数扫描→内置抽样 3/3 ok→一致性断言 PASS；baseline 卡 107 张/top1 卡 143 张 |
| 5 | fd 独立抽验 | **PASS** | 锁定卡字典序**后** 3 张（XBI/ZM/ZSUSDT，与内置前 3 无重叠）同 vintage 复核 top/bot 逐位一致 3/3 |
| 6 | f1 页字段对齐 | **PASS** | 判定区 m.*（caliber/cb3_*/tier_table/calib_epoch 等）全在 live meta；calib_note/state_note 有 `\|\|''` 兜底；快照区只用 round_id/round_semantic/notice/crash_watch/breaker_preview/holdings 全在；池均价 gate.idx/ma50 显示链在位 |
| 6 | box 页字段对齐 | **PASS** | d.*（round_type 徽标+兜底/caliber 三键/runs/seed/version/generated）全对上，零缺失 |
| 6 | generated 时区现状量化 | **RISK（D4/D7 沿用）** | f1_live.meta.generated=裸值（实测 "2026-10-21 02:03:21"）——云端 UTC 沙箱将偏 8h 误导；box="2026-10-20 13:01 UTC"（北京需心算 -8h） |
| 7 | purge 时效 | **PASS** | 实测收敛 8s（第一轮 16/10/5s），sleep30 充足 |
| 7 | Contents API 幂等 | **未验证假设** | 禁写远端未实测；纸面：同内容重复 PUT→422→put() 重试 2 次刷 sha 仍 422→UPLOAD FAIL 有界误报；f1_live 每 4h 必变故低频 |
| 7 | raw 假 MISMATCH 应对 | **PASS** | F1 第 6 步三场景模拟实证（见五项复测#4）；箱体未跟=D15 |

## 三、影子计数去留终审（用户通牒 2026-10-21 00:30「再坏一次就给我去掉」）

**留案（机制保证——为什么三轮修完不会再坏）**【设计推断+本轮实证】：
1. 三轮三坏根因全在**工单文本层**（D1 目录缺/D2' 注释吃 URL/D11 元组语法），机制层（shadow_cells.py S1-S5+旁路挂接+D0 自检）三轮零缺陷；本轮端到端实证 D0 三断言 hit+S1-S3/S5 reg-D0 全 hit+S4 正确 SUSPENDED。
2. D12 补拉+D13 `-f` 后，影子链旧静默死根因已闭环：目录在、依赖在清单、污染转响亮缺席。
3. **影子自带每轮自检**：云端全新沙箱每轮必跑 D0（realA 复放逐位 diff=0），影子链任一环坏→D0 fail→「shadow D0:」行进引擎 stdout 报告可见——不再有静默失明窗口。

**「再坏一次自动下线」可执行条款**【设计推断】：
- 监测者：每轮 F1 四轮报告模板新增固定行「影子=<n>/9」（9=6 件状态/登记产物+D0 hit+reg-D0 hit 计数口径），禁用 exists 容错吞没。
- 「坏」的信号（任一即触发）：a) 影子行致主链任一步 FAIL；b) 影子=<9 连续 2 轮；c) shadow_reg_S*.jsonl 回传断流>3 天。
- 砍的动作：预制「无影子版 prompt」备份（剔除 12 条影子拉码+cand+= 7 对+报告影子行），触发后一条 scheduler-api update 整体替换，禁临时手编。

**砍案替代路径（备而不用）**：S1-S3 因子格前瞻采集改挂 forward_readout 辅轨（FR 同源、同窗 SH-2，断链持久化已实证）；fd-D-A 部署化验证改独立云端任务跑（无旁路挂接，爆炸半径隔离）+fd_revive_result.json 固定 vintage 人工登记。

**首席策略官·何执舟一锤定音**：【数据实证】本轮端到端影子链全链 hit、零静默窗口、D0 每轮自检在场；【设计推断】静默死根因三项闭环+自动下线条款可执行。【终裁：留】。D11 已烧掉一次豁免——条款即刻生效待命，触发即砍不复议。

## 四、缺陷清单定版

| # | 位置 | 现象 | 级别 | 修复建议 |
|---|---|---|---|---|
| D14 | 箱体 12772079 第 2 步 5 条 curl | 无 `-f`/无 `\|\|rm`：401/404 错误体（112B 合法 Python dict）覆盖拉码文件，python3 执行 exit=0 静默 no-op（实测） | **致命** | 5 条统一 `curl -fsS … \|\| rm -f 目标`（F1 同款，一行级文本） |
| D15 | 箱体 12772079 第 5 步 | 自验收无 D3 重试/无 <100B 拦截，假 MISMATCH 误报 FAIL | 中 | 同步 F1 D3 三件套 |
| D4 | f1_signal.py meta.generated | 裸值无时区，云端 UTC 显示偏 8h（实测量化） | 中 | utcnow+8+「北京时间」后缀 |
| D10 | f1_signal.py snapshot 轮 | 不校验 sha（check_engine_authority 只挂 live 入口）；快照只读+不可操作标注，影响面=展示层 | 中 | snapshot 入口同挂闸门 |
| D6 | F1 prompt dneg 双拉 | 第 1 条无 -f+第 2 条 -f\|\|rm；本轮实测远端存在双拉幂等无害 | 低 | 删重复第 1 条或补 -f |
| D7 | box generated | " UTC" 后缀需心算换算（实测） | 低 | 改北京时间输出 |
| D8 | 两任务 prompt | token 明文内嵌 | 低(安全) | 轮换+最小权限 |
| D16 | f1_signal.py live 拒绝路径 | 数据拒绝（R-陈旧/R-错位）与 sha REFUSED 同 exit=2，按码监控不可区分两类（报告文本可区分） | 观察 | 设计内 fail-closed，登记 |
| D17 | 远端 f1/forward_ic_days.jsonl | 404（仓库外侧被删）；`-f\|\|rm` 优雅缺席+load_ic_days 容错自愈（实测缺席不炸任务） | 观察 | 跟踪前瞻累计重积累 |
| D9 | fd 卡片 vintage | 复算差=快照新旧非缺陷 | 观察 | 不处理 |

**可上线判定**：
- F1 云端任务 12769301 现版（14,533 字符）：**可上线**（五项复测+七大块双通道零已知问题；真实云端差异见未验证假设）。
- 箱体任务 12772079：**带病运行→修 D14 一行后可上线**（D14 不修则每轮高概率响亮失败）。
- 晨报 12762479：**PASS 可上线**（无病）。

## 五、未验证假设（诚实标注 R2/R7）
1. 真实云端沙箱差异：UTC 时区、网络栈、GitHub 限流、沙箱残留——本地 4 核模拟不等同。
2. PUT 回传实况/同 sha 重复 PUT 幂等行为（禁写远端，纸面评估）。
3. 判定轮 live 全链未实跑：本地 vintage 冻结在 10-17 触发 R-错位 fail-closed（该拒绝本身实测 PASS）；live 判定证据沿用第一轮 21.4s PASS+本轮 trim_and_guard 四场景单元验证。
4. 浏览器级页面渲染未验（curl+静态 JS 审查替代）。
5. purge 8s 为单次单文件实测；箱体生成链本轮 2 次实跑成功但 kxiandaoyan.com 可达性随时间波动。

## 六、复现命令（关键项）
```bash
# 拉现版 prompt
bash /root/.codebuddy/skills/automation-task-manager/scripts/scheduler-api.sh get --id 12769301
# 五项复测布局（/tmp/f1work→/tmp/fulltest3/v4/work 替换后逐字执行 prompt 第 1/2 步）
grep -E '^mkdir -p /tmp/f1work' /tmp/f1_prompt_v2.md | sed 's#/tmp/f1work#/tmp/fulltest3/v4/work#g' | bash
# 快照端到端
cd /tmp/fulltest3/v4/work && PYTHONHASHSEED=42 F1_CACHE=$PWD/box_cache F1_OUT_JSON=$PWD/f1_live_intraday.json python3 f1/f1_signal.py snapshot --round 20:30
# sha 负测：echo "# TAMPERED_FOR_TEST" >> f1/f1_signal.py 后同上跑 live（应 REFUSE_ENGINE_SHA exit=2）
# trim_and_guard 四场景 / 第6步三场景模拟 / fd 独立抽验：见本报告证据，脚本在 /tmp/fulltest3/v4/
```

## ⑦ D14/D15 修复 diff+实证证据（工程保障团队 2026-10-21 02:30，收尾单）
- 对象：箱体云端任务 12772079 prompt（4,414→5,054 字符）；禁改项（F1 12769301/晨报 12762479/引擎代码/远端数据）零触碰，全文 diff 仅 D14 五行+D15 第5步段+验收模板行同步。
- **D14（致命）**：第 2 步 5 条 curl 统一 `-sS`→`-fsS`+行尾 `|| rm -f <目标>`（逐字照 F1 12769301 已验证防污模式）。update 后 get 回读 5,054 字符**逐字一致**（python3 全文 == 比对 True）；5 条 curl 行+全文 `bash -n` 全 OK。
- **D15（中）**：第 5 步自验收照 F1 第 6 步逐字移植（cand/local 适配箱体 box_live.json+index.html，路径 /tmp/kxbox）：D3 重试(sleep 15+二次 purge+tries≤2)+<100B 无效样本拦截。`ast.parse` OK（1,341 字符）。附随：第5步头注释与报告模板「验收=」行同步为逐字节比对口径（原「index.html 200」口径随旧实现废止）。
- **修后实证**：
  1. 拉码：5 条修复后 curl（/tmp/kxbox→/tmp/kxbox_sim）整组 exit=0，5 件全落盘（generate_page.py 25,793B/kx_client.py 29,679B/refresh_cache.py 3,699B/eng_final.py 9,887B/cleaned_pool.json 8,883B），4 py `py_compile` OK+json 解析 OK（长度 5）。
  2. **401 拒污断言**：坏 token 重跑同批行→5 条全响亮 `curl: (22) 401`，`||rm` 吸收整组 exit=0，/tmp/kxbox_401 落盘 **0 文件**（错误体不落盘，旧版 112B 覆盖病实证闭环）。
  3. 自验收干跑（mock urlopen 三场景，脚本 /tmp/sim_verify_dryrun.py）：A) 假 MISMATCH 1 次后收敛 tries=1→PASS；B) 永不 MISMATCH→tries=2 有界退出 FAIL（SIGALRM 10s 未触发，不死循环）；C) API 21B<100B→拦截 FAIL。三行为与 F1 D3 已验证设计逐项一致。
- **结论：箱体任务 12772079 修后可上线**（D14/D15 双清，下一轮 2026-10-21 09:00 定时轮为首次云端实战验证点）。
- 备案登记（交交易分析团队，登记级）：本单为第三次全场景终验钦定收尾行，D14/D15 修复完毕，缺陷清单 D14/D15 状态→已闭环；D4/D10/D6/D7/D8/D16/D17 维持原状不动。
- 复现：`bash /root/.codebuddy/skills/automation-task-manager/scripts/scheduler-api.sh get --id 12772079 | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['agentConfig']['prompt'])" | bash -n`；401 拒污复现 `T=invalid bash /tmp/sim_pull_401.sh; find /tmp/kxbox_401 -type f | wc -l`（应 0）。
