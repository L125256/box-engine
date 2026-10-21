# PLAN_FINAL_BUILD_REPORT — 计划书 5 项待施工执行报告

- 施工方：工程保障团队（单 agent 5 席全席，工程总监终裁收口）｜ skill=eng-team-entity 显式加载 ✓
- 唯一依据：`research/wo_mine/PLAN_FINAL_20261021.md`（§2.1 PLAN 表 C 类 5 项，照抄级施工）
- 日期：2026-10-21 ｜ commit：见文末（**commit 不 push，push 待用户授权**）

## 一、步骤｜结果表

| # | 项 | 施工文件 | 关键改动 | 结果 | 验证 |
|---|---|---|---|---|---|
| 7 | 台账口径 v1.5 增补（先行） | engine_f1/F1_台账口径_v1.md + f1/ 副本 | 版本头加 v1.5 行；§7.9 新制度三场景（⑧影子期废除+四层铁律 ⑨双闸分离+三道门+四要素 ⑩S5 满额+新档位映射）；§8.6 新部署铁律（四层定义+废除边界+实盘劣化线+三防线） | **完成** | 双副本 cmp 全等 ✓；§7.9/§8.6 在位 ✓；既有数字逐字未动 ✓ |
| 1 | S5 满额+新制档位 | research/wo_mine/enhance_discount.py | 删 T0-T4 爬档查表；新映射 S5=FULL 100%、S1–S3=POOL_CAP 50%、S4/域未激活=FROZEN、判死/劣化线=OFFLINE；输出 tier ∈ {FULL,POOL_CAP,FROZEN,OFFLINE}；n 计数保留=执照复审数据源；REVIEW_DUE=2027-04-21；安全侧默认降 FROZEN；2% 分母纪律承继 | **完成** | test_enhance_discount ① 21 项 PASS（含 S5 满额/单池 50/劣化线归零/域未激活 FROZEN/无爬档断言） |
| 4 | f1 页增强区块新口径 | f1/index.html（renderEnhancement 整段） | 「n=X/20」「折扣 X%」「影子」全清除；S5「满额运行·执照复审 2027-04-21 到期」、S1–S3「单池满额 50%·双池解锁另议」、S4 灰态不变；免责声明改「按重重检测满额部署，实盘劣化线自动降停，6 个月强制复审」；数字一律读 JSON | **完成** | render_harness 渲染零 JS 报错+新口径逐字断言 ✓；grep 旧字样=0 ✓；meta.enhancement=null 兜底「增强层未上线」✓ |
| 5 | 双手册更新 | f1/manual.html §8 + box/manual.html §4 | f1 手册分域增强章改「重重检测当日满额/劣化线自动降停/6 个月复审硬期限」；box 手册补双闸分离段（F1 闸收盘/箱体闸盘中+三道门+四要素怎么看） | **完成** | 双手册渲染断言 ✓；grep 影子/折扣=0 ✓ |
| 2 | 双闸分离+卫生三道门 | generate_page.py（加载层）+ index.html（根页面） | 门1 日期归一化（time→date-only）；门2 混格式拒载（同票原始格式混写→AssertionError exit≠0）；门3 池样本数下限 144（clean 冻结口径）；覆盖率门 ≥80%（<80% 闸值作废沿用上一收盘值并标注 inherited）；box_live.json 增 gate_meta（闸名｜池口径｜数据日期｜样本数+idx 贡献样本数）；页面温度计+fd 区四要素标注（缺字段兜底「—」） | **完成** | test_box_hygiene 12 项 PASS（混格式正负测/不可解析拒载/池下限/79%·81% 边界两测/无合格日拒载）；页面渲染断言 ✓ |
| 3 | 温度计 clean 口径 | generate_page.py 模板 + 根 index.html 再生 | 温度计标「clean 口径」；fd 激活观察区计数独立于牛闸（双闸分离·两闸各自独立算互不影响，触发仍按收盘判定零改动）；页面形态「开/关+fd 激活 N 只（观察区）」 | **完成** | 合成数据渲染「关+fd 激活 1 只（观察区）」形态断言 ✓（「9 只」为当日实时值，随云端首轮判定级数据落位） |
| 8 | 带病项 D4/D10/D6 | engine_f1/f1_signal.py + AUTHORITY_SHA.json + 云端任务 12769301 | D4：meta.generated 判定轮+快照轮改 utcnow+8+「北京时间」（纯 meta 展示）；D10：快照轮入口同挂 check_engine_authority（fail-closed，REFUSED exit=2）；sha 双登记 7da41c80→62a52b8f（batch=PLANFINAL-PATCH-20261021，归档副本逐字节同步）；D6：云端 prompt dneg 重复第 1 条删除（15290→15010 字符） | **完成** | py_compile ✓；引擎 diff 删除行=仅 2 条 D4 meta 行（判定主逻辑零删除）；D10 负测篡改副本→`snapshot REFUSED` exit=2 ✓；D6 三步验证（锚点替换→update→回读逐字一致）+bash -n PASS+2 个 python 块 ast.parse PASS+dneg 行数=1 ✓ |

## 二、测试汇总

| 套件 | 结果 |
|---|---|
| test_enhance_discount.py（新制档位/旁路/页面渲染/双手册/引擎回归） | **40 PASS / 0 FAIL** |
| test_box_hygiene.py（三道门正负测/覆盖率边界/四要素渲染/兜底） | **18 PASS / 0 FAIL** |
| D10 sha 闸门负测 | REFUSED exit=2 ✓ |
| D6 云端任务三步验证 | 回读逐字一致+bash -n+ast.parse 全 PASS ✓ |
| F1 主引擎红线终检 | 四因子/闸/熔断/回放/费常数 diff=0（仅 D4/D10 带病项行）✓ |

## 三、口径分叉登记（零自行定义）

1. **派单写「§八增补」、计划书 #7 写「§7 增三条目」**：处置=§7.9 三条目（承计划书）+§8.6 新部署铁律（承派单），两者纯增补、互不删改，请验证席确认此双落点。
2. **门3 池样本数下限数字**：计划书未给数值，按既有 clean 144 冻结口径执行（引用非新定义）。

## 四、遗留与待澄清

| # | 项 | 状态 |
|---|---|---|
| 1 | push 待用户授权：待推=177661f + b35a661 + 5c84243 + 本批 commit | 等授权 |
| 2 | D8 token 轮换不入批（风险主管跟踪项，不许丢） | 跟踪中 |
| 3 | D7 不纳入（计划书 §2.1#8 裁决：改版换行成本高收益低） | 关闭 |
| 4 | 「关+fd 激活 9 只」实数待云端 09:00 判定级轮首战落位（本地合成数据形态断言已过） | 待首战验收 |
| 5 | f1/ 归档台账原为陈旧 v1.1，本批跨版本补齐至 v1.5（逐字节同步） | 已修复 |
| 6 | 根 index.html 为本批模板再生（BULL_OPEN=false/BULL_ASOF=2026-10-20 现值），实数随云端轮刷新 | 正常 |

## 五、复现命令

```bash
cat /workspace/repo_ready/research/wo_mine/PLAN_FINAL_20261021.md        # 唯一依据
python3 /workspace/repo_ready/research/wo_mine/test_enhance_discount.py  # ① 40 PASS
python3 /workspace/repo_ready/research/wo_mine/test_box_hygiene.py       # ② 18 PASS
cmp /workspace/repo_ready/engine_f1/F1_台账口径_v1.md /workspace/repo_ready/f1/F1_台账口径_v1.md
sha256sum /workspace/repo_ready/engine_f1/f1_signal.py   # =AUTHORITY_SHA.json 登记 62a52b8f…
grep -c '折扣\|影子\|/20' /workspace/repo_ready/f1/index.html   # =0
```

—— 交付完成，待交易分析团队按计划书 §2.3 清单逐项验证后，等用户授权 push。
