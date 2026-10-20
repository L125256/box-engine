# 交易分析团队 · 全场景系统性大体检报告
- 执行时间：2026-10-21 00:05–00:35（北京时间）｜执行环境：本机 4 核沙箱 /tmp/fulltest（只读+本地模拟，未写远端、未动线上任务、未改引擎代码）
- 方法：真实执行（25 条拉码逐条跑、引擎判定/快照双模式端到端、sha 闸门正负测、箱体生成链全量冒烟、jsDelivr purge 三次实测、双页面 http.server 实测）

## 场景矩阵（PASS/FAIL/RISK 计数）

| 块 | 场景 | 结果 | 证据摘要 |
|---|---|---|---|
| 1a | F1 原 16 条拉码 | PASS | 全部 HTTP200 落盘，文件类型健康；f1_signal.py blob sha=f31038fca1 与仓库一致 |
| 1a | F1 新增 9 条影子拉码 | **FAIL** | 7/9 落盘失败：curl exit 23（目录不存在），`|| rm -f` 吞错码；仅 dneg_engine.py 落入已存在目录成功 |
| 1a | tar.gz 快照包拉取 | **FAIL** | `-sSL` 无 raw Accept 头 → 2,114,469B 文件返回 JSON 元数据（content=""），"tar.gz"实为 JSON 文本 |
| 1b | 判定轮端到端 | PASS | 21.4s，asof=2026-10-19 gate=持币 top5 五只 breaker=green tier=0；产出 f1_live.json sha=a7e552f2 |
| 1b | DECBAR trim_and_guard | PASS | 数据源含 10-20 盘中 bar 时 asof_settled=10-19，intraday=True 正确剔除 |
| 1c | 快照轮 20:30/00:30/04:30 | PASS | 三档 mode=intraday_snapshot、round_id 正确、operable=False、writes 隔离（f1_state/f1_live 均 False） |
| 1d | 回传 cand 16 条 exists 容错 | PASS | dry-run：缺文件跳过；判定轮存在时正常选入 |
| 1d | 自验收双通道比对 | RISK | 单次比对无重试/无空响应识别 → raw 假 MISMATCH 会误报 FAIL（今晚 3 次即此） |
| 1e | 版本漂移/sha 误拦 | PASS | AUTHORITY_SHA 3 文件 sha256 全 MATCH（a7e552f2/c2634447/48aa668d），无旧 sha 误拦 |
| 2a | 箱体 round_type 时区 | PASS | generate_page.py:367 `utcnow+8` 取北京时间小时，21 点落「盘中快照·不可操作」正确；怀疑排除 |
| 2b | 箱体生成链端到端 | PASS | 72s：176/176 缓存→双冻结参数→抽样核对 3/3 ok→一致性断言 PASS，卡片 108/143 |
| 3a/3b | 晨报 | PASS | 两 URL HTTP200；f1_live 有 breadth(27.78%,40/144)/asof/gate/breaker 全字段；容错句在 |
| 4a | sha 闸门正/负测 | PASS | 篡改 SEED 42→43 → REFUSED（got=a71ff1d1 want=a7e552f2）且零产出；恢复后 PASS |
| 4a | REFUSED 退出码 | RISK | REFUSED 时 exit=0（应非零，自动化按码判定会漏） |
| 4b | 判定/快照冒烟 | PASS | 见 1b/1c |
| 4c | 熔断阈值一致性 | PASS | 单一事实源 breaker_thresholds()；CB1 −8%/−4%、CB2 −5/−2.5pp、CB3 line 27.21 与代码常量一致 |
| 5a | box_live.json 生成链 | PASS | 见 2b |
| 5b | fd 卡片手工复算 | RISK(观察) | AAPLUSDT 复刻复算末态=冷却 vs 卡=持仓中——归因缓存 vintage 新旧（卡=10-20 快照），抽样断言 3/3 兜底，非引擎缺陷 |
| 6a | 页面字段对账 | PASS | box 页 d.round_type/d.caliber/d.runs 与 JSON 键全对上；f1 页 f1_live/f1_live_intraday 双 fetch 容错齐 |
| 6a | generated 时区显示 | RISK | f1_live.json meta.generated 无时区标注（云端 UTC 会显示 00:30）；box 带 " UTC" 后缀可读性欠佳 |
| 6b | http.server 实测 | PASS | f1 页 4 项/box 页 3 项全部 200（浏览器级未验，诚实标注：仅 curl+静态 JS 审查） |
| 7a | Contents API 幂等性 | 未验证 | 不写远端铁律限制；纸面审查：GET_SHA_FAIL→PUT 无 sha→422→重试刷 sha 可自愈；同内容重复 PUT 会空 diff commit（每轮 1-2 commit 属预期） |
| 7b | raw 假 MISMATCH 应对 | RISK | 自验收脚本无复测逻辑（见 1d） |
| 7c | jsDelivr purge 时效 | PASS | 3 次实测收敛 16s/10s/5s；prompt 固定 sleep 30s 够用 |

## 缺陷清单定版
| # | 位置 | 现象 | 级别 | 修复建议（一句话） |
|---|---|---|---|---|
| D1 | F1 prompt 第1步 mkdir | 缺 research/wo_mine、wo_fddual、wo_fdbrk、eng_wt_rc 四目录→9 条新拉码 7 条 exit 23 全灭、`|| rm -f` 吞错→影子登记每轮静默旁路（live 输出「shadow_cells 挂接异常」证实） | **致命** | mkdir 行补齐 4 个目录即可 |
| D2 | F1 prompt 第2步 tar.gz 拉取 | 无 raw Accept 头→>1MB 文件 Contents API 回 JSON 元数据，解包必败→forward_readout 数据源失效（nonblock 静默） | **致命** | 该条加 `-H "Accept: application/vnd.github.raw"` |
| D3 | 两任务第6步自验收 | 单次比对无重试/空响应识别→GitHub raw 滞后假 MISMATCH 误报 FAIL | 中 | MISMATCH 后 sleep15s+二次 purge+复测 2 次，<100B 视无效样本 |
| D4 | f1_signal.py:85/709/908/1065 | pd.Timestamp.now() 无时区→云端 UTC 下页面 generated 显示 00:30 误导 | 中 | 改 utcnow+8 并加「北京时间」后缀 |
| D5 | f1_signal.py REFUSED 路径 | 判死退出码 0，按码监控漏报 | 中 | REFUSE 分支 sys.exit(2) |
| D6 | F1 prompt dneg_engine.py 双拉 | 第 1 条无 -f（404 会落错误 JSON 为文件），第 2 条 -f+rm -f 若 404 会删第 1 条成果 | 低 | 删除重复第 1 条，或给第 1 条补 -f |
| D7 | box generated | UTC 后缀有但需心算换算 | 低 | 改输出北京时间+标注 |
| D8 | 两任务 prompt | GitHub token 明文内嵌 | 低(安全) | 建议轮换该 token 并评估最小权限 |
| D9 | fd 卡片 vintage | 复算差=快照新旧非缺陷 | 观察 | 登记不做处理 |

## 十席位结论
- 空头席（静默失败清点）：D1 是本轮最危险发现——「修复影子依赖」的工单本身因目录缺失而整批静默失效，`|| rm -f` 把错误码也吞了，报告模板不核对影子文件清单，故三道防线同时失明。
- 激进风险席：GitHub 全挂→拉码失败按纪律终止（可接受）；kxiandaoyan.com 全挂→无旧缓存时引擎空跑（云端首日风险，本地实测源站可达、58s 全成功）。
- 保守风险席：今晚 5 次生产修复中 WO-SHADOW-CLOUD-FIX（D1/D2 即其产物）未实测即上线，属变更管理漏洞；AUTHORITY_SHA 更新流程本身干净。
- 交易员席：页面/晨报读数链完好，明早 08:30/09:00 判定不受 D1/D2 影响（引擎主链 PASS），影子登记数据继续断流而已。
- 首席终裁：**必须立即修 Top3 = D1、D2（改两条 prompt 文本即可，改完触发一次手动验证轮）、D3；D4/D5/D7 可带病运行至本周修复批次；D6/D8 观察项。**总评：主生产链（判定/快照/生成/回传/自验收/页面）实测全通，可以带影子功能残缺运行；两条致命缺陷都在「昨晚新增的修复」而非存量链路——修而不验，是最该写进台账的一课。

## 未验证假设（诚实标注）
1. 真实云端沙箱时区/网络栈（kxiandaoyan.com 与 GitHub API 可达性）——本地模拟无法等同。
2. Contents API PUT 幂等行为/422 重试实况（禁写远端，未实测）。
3. GitHub Pages 部署延迟对晨报 09:05 读数的影响（实测当时点 200，未测刚 PUT 后窗口）。
4. 双任务 09:00/09:05 并发撞车（GitHub API 限流 5000/h，纸面评估安全）。
5. 浏览器级页面渲染（仅 curl+静态 JS 审查替代）。
