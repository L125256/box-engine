# SHADOW_CLOUD_FIX_REPORT — 云端影子旁路路径修复（batch=SHADOW-PATH-20261020）

- 工单来源：工程保障团队单 agent 5 席（工程总监终裁）；依据=主对话层诊断（纯路径/部署修复，非金融口径变更）
- 日期：2026-10-20
- 范围：`engine_f1/f1_signal.py`、`f1/f1_signal.py`（逐字节同步归档副本）、`engine_f1/AUTHORITY_SHA.json`、`f1/AUTHORITY_SHA.json`（同表同步）
- 红线遵守：回放/判定/熔断语义零改动（仅动判定轮/快照轮两处 shadow_cells 旁路共 12 行）；commit 不 push；Secret 零泄漏（本单不涉凭证，例行自查通过）

---

## ① 路径修复 diff（两处同款，判定轮 :1166-1171 / 快照轮 :1189-1194）

```diff
         try:
             import subprocess
-            subprocess.run([sys.executable,
-                            '/workspace/repo_ready/research/wo_mine/shadow_cells.py',
+            ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 引擎在 engine_f1/ 或 f1/，上级即仓库根
+            SHADOW_SCRIPT = os.path.join(ROOT, 'research', 'wo_mine', 'shadow_cells.py')
+            subprocess.run([sys.executable, SHADOW_SCRIPT,
                             '--auto'], timeout=1800, check=False)
```

- `f1/f1_signal.py` 归档副本：`cp` 逐字节同步，md5 双份一致（1dcf3ead97dada7648677afbb1538abc）。
- 语法自检：`ast.parse` PASS。
- 新 sha256：`a7e552f2f4c3aeb41f9fe7f27ad5767344d0114f2e83a9c439a4d201404ca097`（旧 `bfbbeba4…`）。

## ② 双布局解析验证（PASS）

| 布局 | 解析结果 | 判定 |
|---|---|---|
| `engine_f1/f1_signal.py`（本地） | `/workspace/repo_ready/research/wo_mine/shadow_cells.py` | 与原硬编码逐位等价 PASS |
| `f1/f1_signal.py`（归档副本） | 同上 | PASS |
| `/tmp/f1work/f1/f1_signal.py`（云端模拟） | `/tmp/f1work/research/wo_mine/shadow_cells.py` | 正确随 `__file__` 切换 PASS |

## ③ sha 闸门登记更新（两处同表）

- `files.f1_signal.py`：`bfbbeba4…` → `a7e552f2…`
- `batch`：`S5-PATCH-20261020` → `SHADOW-PATH-20261020`
- `note` 追加补登句（含新旧 sha、修复方式、语义零改动声明）
- 复验：`check_engine_authority` 逻辑离线对表，engine_f1 与 f1 两目录逐文件 sha256 对表 **PASS**；两份闸门表 diff 逐字节一致。

## ④ 云端拉码依赖清单（shadow_cells --auto 前瞻采集模式）

### A. 引擎判定/快照轮本体（f1_signal.py 云端布局）
| 依赖 | 级别 | 缺失时行为 |
|---|---|---|
| `f1/f1_signal.py` | 必需 | 本体，无法运行 |
| `f1/AUTHORITY_SHA.json` | 必需 | fail-closed `REFUSE_ENGINE_SHA` 拒绝产出 |
| `f1/f1_datasource.py` | 必需 | 闸门 fail-closed 拒绝产出 |
| `f1/f1_backtest_v2.py` | 必需 | 闸门 fail-closed 拒绝产出。⚠️ 仓库 `f1/` 目录现无此件，云端拉码须从 `engine_f1/` 取（本单模拟布局已实证 sha 对表 48aa668d… 一致） |
| 数据态三选一：`/tmp/box_cache` > env `SHADOW_BOX_CACHE`/`FORWARD_BOX_CACHE` > `engine_snapshot/box_cache_snapshot.tar.gz` 自动解包至 `ROOT/.cache/box_cache` | 必需（其一） | 全无→数据缺失失败；解包链云端可用（本单实测走通） |
| `engine_snapshot/cleaned_pool.json` 等 | 云端任务既有 | — |

### B. shadow_cells --auto（旁路目标件）
| 依赖 | 级别 | 缺失时行为 |
|---|---|---|
| `research/wo_mine/shadow_cells.py` | 必需 | 旁路空转（引擎不阻断） |
| `research/wo_mine/mine_common.py` | 必需 | ImportError→旁路退出（引擎不阻断，影子停摆）。⚠️ **其内部 ：26 硬编码 `REPO='/workspace/repo_ready'`**（dneg_engine sys.path 与 OUT_DIR）——云端布局下 dneg_engine 导入将失败；本沙箱因 `/workspace/repo_ready` 实存无法复现该失败（**未验证假设，R2 标注**），建议另开工单同款 `__file__` 化 |
| `research/wo_mine/batch1_run.py`、`batch2_run.py` | 必需 | ImportError→同上 |
| `research/wo_dneg/dneg_engine.py` | 必需 | mine_common import 失败→同上 |
| `research/wo_mine/domains.json` | 首跑 D0 必需 | FileNotFoundError→影子停摆（state 不落）；D0 已过（state 持久化）后不再需要 |
| `research/wo_mine/FACTBOOK_BATCH1.jsonl` | 首跑 D0 必需（断言③） | 同上 |
| `research/wo_fddual/fd_revive_run.py` | S5 必需 | Exception 被捕获「S5 采集异常（不阻断）」，S1-S4 照常 |
| `research/wo_fdbrk/common_fdbrk.py` | S5 必需 | 同上（经 `HERE/../wo_fdbrk` 相对解析，可移植） |
| `eng_final`（`/tmp/eng_wt_rc` 优先，回落 `ROOT/research/eng_wt_rc`） | S5 必需（其一） | 两处皆缺→S5 异常不阻断 |
| `research/wo_fddual/fd_revive_result.json` | 仅 S5 首跑 D0 | FileNotFoundError→Exception 捕获，S5 本轮跳过（**不致命**）；S5 d0 hit 后不再需要 |
| `/tmp/box_cache_fresh` | 仅 S5 首跑 D0 | 缺失→**SystemExit 整跑停**（连累 S1-S3，与上行不同级，禁以 live 数据代跑 D0 条款）；S5 d0 hit 后不再需要 |
| `ROOT/f1/` 可写目录 | 必需 | 状态落盘失败 |
| `f1/f1_live.json` | 可选 | 血缘只读，缺失→`round_asof=None` 容错 |
| `research/wo_mine/SHADOW_SPEC_v1.md`（SPEC_F） | **可选** | 定义于 :103 但运行时从未被读取（逐行核实），缺失零影响；纯规格出处文档 |

计数：**必需 13 项（含三选一组）、可选 2 项**。

## ⑤ 模拟端到端实测（/tmp/f1work 云端布局，三轮）

布局：`f1_signal.py→/tmp/f1work/f1/`、`box_cache_snapshot.tar.gz+cleaned_pool.json→/tmp/f1work/engine_snapshot/`、research 谱系树按仓库相对路径铺放；逐字执行旁路行 `subprocess.run([sys.executable, SHADOW_SCRIPT, '--auto'], timeout=1800, check=False)`。

| 轮 | 数据态 | 结果 |
|---|---|---|
| 1 | 无缓存 | 旁路定位 PASS，`shadow_cells` 被正确找到并执行（路径修复生效） |
| 2 | 快照包解包（10-17 冻结 vintage） | D0 全链执行：标签零漂移=hit、ATLAS 锚 diff0=hit、**S4 重放=MISS**（快照 vintage 与 FACTBOOK 重放窗数据态差，非路径问题）→停工条款触发（rc=1，语义正确） |
| 3 | live 数据态（env 覆盖 symlink 视图） | **全链 PASS**（rc=0，43.8s）：D0 all_pass=True（三腿全 hit）；S5 D0 realA 复放四位逐位 diff=0（`1228 / 0.9832 / 0.335 / 411.37`）；S1-S3 登记 n_registered=3 各 +3、S5 登记 1 日、盘中剔除 144 bar；reg-D0 四格全 hit；产物落 `tmp/f1work/f1/`（shadow_state.json / shadow_reg_S{1,2,3}.jsonl / fd_revive_state.json / fd_revive_days.jsonl） |

**结论：模拟端到端 = PASS**（live 数据态）。纯快照态下 S4 重放腿因数据 vintage MISS，属数据态口径而非本单路径缺陷；云端实机以 `/tmp/box_cache` live 态运行即为轮 3 同款条件。

## ⑥ 施工过程记录（诚实标注）

- 开工前发现 main 上一个**被中断的 interactive rebase**（orig-head 7bd1481，4 pick 完成 1）。经用户确认「先续完 rebase」：冲突两处（shadow_cells.py / AUTHORITY_SHA.json）取 HEAD（较新整合谱系）解决，末位 pick 7bd1481 被 git 判定 "patch contents already upstream" 自动丢弃——与树级诊断一致（809f484 与 orig-head 树完全一致，4 个旧 pick 内容已被新谱系吸收）。续完后 main 干净，本单改动基于 33d4071。
- `f1/` 目录缺 `f1_backtest_v2.py` 但闸门表列之：**改动前既存旧况**，本单不扩scope，已列入拉码清单（从 engine_f1/ 取）。
- `engine_f1/f1_signal.py:1159` forward_readout 旁路仍是硬编码绝对路径（同款缺陷，**不在本单 12 行范围内未动**），建议另开同款工单。
- 移交：结果交交易分析团队终裁追认（登记级）。

## ⑦ Secret 零泄漏自查

本单不涉任何凭证/密钥；diff 仅路径解析与 sha 登记；例行声明通过。

## ⑧ 遗留修复+端到端复测（续单第三件，2026-10-20 晚；主对话层核查移交两遗留）

### ⑧-1 遗留 1：mine_common.py REPO 硬编码（2 个修复点，纯路径，语义零改动）

```diff
-REPO = '/workspace/repo_ready'
-sys.path.insert(0, os.path.join(REPO, 'research', 'wo_dneg'))
+_HERE = os.path.dirname(os.path.abspath(__file__))
+REPO = os.environ.get('SHADOW_REPO_ROOT') or \
+    os.path.dirname(os.path.dirname(_HERE))          # research/wo_mine 上两级=仓库根（shadow_cells :83-85 同款）
+sys.path.insert(0, os.path.join(REPO, 'research', 'wo_dneg'))
```

- **修复点 2（云端复测实测暴露追加）**：`build_ctx` 内 `sys.path.insert(0, REPO/'engine_f1')` 在云端布局（引擎在 `f1/`）同样 ModuleNotFoundError→全 run 停摆。修法：`engine_f1/f1_signal.py` 存在优先（本地原行为逐位不变），否则回落 `REPO/f1`。
- REPO 引用点排查改净：L28 dneg sys.path / OUT_DIR / build_ctx 引擎目录 / `F1_POOL` env 全经 `REPO` 变量间接引用；其余绝对路径仅 `CACHE=/tmp/box_cache`、`TMP_DIR=/tmp/wo_mine`（数据态/临时态，非仓库布局，不改）。
- 语法自检 PASS；smoke：迁移布局（/tmp/smoke_mc）REPO 相对解析+`SHADOW_REPO_ROOT` env 覆盖+dneg_engine 导入全 PASS；本地仓库布局 REPO=`/workspace/repo_ready` 与原硬编码逐位等价 PASS。
- 登记口径：mine_common.py **不在 AUTHORITY_SHA 闸门表管辖内**（代码修复，无 sha 闸门动作）；两处 f1_signal.py sha 未触碰（⑧-3 对表复验 PASS）。

### ⑧-2 遗留 2：eng_final S5 装载（实证：回落路径已在库，无需新建/裁剪）

- 装载逻辑核实：`shadow_cells._fd_eng`（_OPS7）eng_final 优先 `/tmp/eng_wt_rc`，**回落 `ROOT/research/eng_wt_rc`**（fd_revive_run 自身 `/tmp/eng_wt_rc` insert 为无害硬编码）。
- **`research/eng_wt_rc/` 全套已在库且 git 追踪**（存档 commit 6546d8b），云端拉码自带；`eng_final.py` md5=`f59ddf73c18dcc2adcd3f5e374748631` 与 /tmp/eng_wt_rc 实件一致，9,887 B≤1MB。
- S5 每日采集（--auto 非 D0）最小文件集 = **{eng_final.py} 单文件**：fd_revive_run 仅用 `ENG.atrs/build_idx_bull/collect` 纯函数（eng_final 模块级仅 stdlib 导入）；eng_wt_rc 内 JSON/CSV 均为 WT-A 产物/登记件，非装载输入。**零裁剪**（R7：无裁剪口径需登记）；不新建 `eng_wt_rc_min/`（装载代码期望回落路径已满足，另建副本反生漂移风险）。B 组清单「eng_final」行实证修订：两缺前提不成立，云端拉码清单无需追加 eng_wt_rc 专项目。

### ⑧-3 端到端复测（/tmp/f1work 云端布局，/tmp/eng_wt_rc 全程移走模拟「两缺」，跑毕还原）

- 铺放：B 组全部文件+`research/eng_wt_rc/eng_final.py`（md5 同源）+修复后 mine_common；`python3 f1/f1_signal.py snapshot --round 20:30` 快照模式旁路。
- 前 2 轮排除非本单缺陷：①`/tmp/box_cache/box_cache` 嵌套解包残留（10-17 frozen vintage，176 件，早于本单既存）致 IsADirectoryError→移出至 `/tmp/nested_box_cache_HOLD`（未删除，live 外层 176 件复验无损）；②即 ⑧-1 修复点 2 暴露现场。
- **终轮断言全 PASS**：S1/S2/S3 登记 2→3 行各 **+1**；S5 reg_day 0→1 **+1**（盘中剔除 144 bar）；S4 SUSPENDED 维持；rc=0；零 Traceback/零 ImportError/零 eng_final 异常；`research/eng_wt_rc/__pycache__/eng_final*.pyc` 生成=回落导入实证；reg-D0 四格全 hit。
- 本地不回归：两处 `AUTHORITY_SHA.json` sha 对表 PASS（batch=SHADOW-PATH-20261020 未动）；判定轮同款旁路行 `python3 research/wo_mine/shadow_cells.py --auto` rc=0、幂等 +0、S5 reg-D0 hit（状态文件仅 updated_at 顶新，已还原 HEAD）。

- 移交：结果交交易分析团队终裁追认（登记级）。

## ⑨ 三轮修复终态独立终验（工程保障团队单 agent 5 席全席，2026-10-21 01:00–01:40）

- 依据：/tmp/fulltest2_report.md 缺陷清单+治理铁律 5e 主理人禁手令（主理人两次代写事故 D2'/D11 已证伪，本轮一切修复文本由工程保障团队产出）；沙箱 /tmp/fulltest3+fresh /tmp/f1work（只读远端、零 push）。

### ⑨-1 主理人三处修复独立终验（逐字取 scheduler-api 现版+实测）

| 项 | 判定 | 实证 |
|---|---|---|
| a) mkdir 4 影子目录 | **PASS 实证** | 逐字重放 exit=0，research/{wo_mine,wo_fddual,wo_fdbrk,eng_wt_rc} 四目录全落地（eng_wt_rc 与 curl -o 路径逐位一致）；mkdir -p 级联覆盖 wo_unlock 父目录 |
| b) tar.gz 行 | **PASS 实证** | URL 在注释之前、raw Accept 头在位；curl 实测拉回真 gzip 2,114,469B，tar 解包 176 件正常 |
| c) cand+= 行 | **PASS 实证** | ast.parse OK；7 条 (repo_path, local_path) 二元组逐条核对无误；第 5/6 步整条 python3 -c 命令 bash -n OK |

### ⑨-2 全文逐行扫描+新缺陷发现与修复（本轮核心产出）

扫描器：25→27 条 curl URL 完整性、mkdir 覆盖、2 个 python 块 ast.parse、全部 shell 行与整条命令 bash -n、影子 9 依赖清单比对——静态层零问题（D6 双拉 dneg 维持观察项：二次 -f 拉取幂等无害）。**端到端实跑揪出两个静态扫描不可见的致命缺陷（前两轮体检只验「落盘可解析」从未实跑旁路，即为漏网根因）**：

| # | 位置 | 现象 | 修复（本轮产出，scheduler-api update 锚点替换+回读逐字一致+新增行 bash -n 三步全做） | 级别 |
|---|---|---|---|---|
| D12 | 第 2 步拉码清单 | shadow_cells.py `d0_check`（云端沙箱每轮 state 全新必跑）硬依赖 `_HERE/domains.json`（:201,:285）与 `FACTBOOK_BATCH1.jsonl`（:243），均不在拉码清单 → FileNotFoundError → 影子全家（S1-S5）**每轮静默灭**（旁路 check=False 不阻断）；S5 `s5_d0` 另需 `/tmp/box_cache_fresh` 冻结副本（:674 缺即 SystemExit 停工），prompt 未建 | 补拉 2 条（domains.json 1,201,255B+FACTBOOK_BATCH1.jsonl 63,675B 实测可拉）+tar 后补建冻结副本解包行（`mkdir -p /tmp/box_cache_fresh && tar -xzf … --strip-components=1`，与第 3 步 live 刷新隔离，承 _OPS7 禁 live 代跑 D0） | 致命（影子链） |
| D13 | 第 2 步 16 条主拉码行 | 无 `-f`：瞬态 401（本轮实测复现：GitHub 返回 `Bad credentials` 112B 错误体）经 `-o` **逐字覆盖引擎/池文件**，且错误体恰为合法 Python dict 字面量 → `python3 f1_signal.py` 静默 no-op exit=0 → 全轮假 PASS（v2 实测 16 文件全被污染、引擎零产物零报错） | 16 条统一 `curl -fsS`+`|| rm -f 目标`（与影子行既有防污模式同构）；实测同轮瞬态 401 下影子行正确拒污、主行污染，修复后污染转为响亮缺席（第 3/4 步报错→按纪律报告终止），fail-open→fail-closed | 致命（主链） |

### ⑨-3 端到端实证 v3（/tmp/fulltest3，最终版 prompt 14,533 字符逐字执行）

- 第 1+2 步：27/27 拉码落盘（26 件+tar.gz），`/tmp/box_cache_fresh` 176 件解包成功。
- 第 4 步快照轮（第 3 步以快照解包模拟缓存数据态）：引擎 `snapshot ok(只读) round=20:30` **exit=0**；影子旁路自动触发——D0 all_pass=True（标签零漂移/ATLAS 锚/S4 重放三断言 hit）、S1/S2/S3 reg-D0 全 hit（n_registered 各 3）、S4 SUSPENDED（§4 补样 0/4 设计内）、S5 D0 hit（realA 复放 n_paired=1228/pair_rate=0.9832/mean=0.335/sum_r=411.37 四位 diff=0）、S5 reg-D0 hit。
- 第 5 步回传选择干跑（禁写远端，put 桩化仅本地）：快照轮命中 7 件=主产物+影子 6 件；shadow_days.jsonl 缺席为设计内（n_matured=0 不落盘，exists 容错语义保持）。
- 诚实标注（R2/R7）：①判定轮 live 分支受本地时刻限制未实跑（旁路与快照轮同一 subprocess 入口，S5 挂接点 f1_signal:1194-1203 快照/判定同款，判定轮证据沿用 ⑧-3 rc=0）；②真实云端 PUT 回传/第 6 步双通道验收未实测（禁写远端）；③远端 `f1/forward_ic_days.jsonl` 本轮实测 404（v1 实测 01:05 尚在，此后被仓库外侧删除，非本沙箱所为）——`-f||rm` 下优雅降级（`load_ic_days()` 缺失容错返回空表，前瞻累计自愈重积累），已移交交易分析团队知悉；④GitHub API 本地高频重放会触发限流（v2/v3 各复现一次），云端每轮 27 条单次串行间隔小时级，风险低但「-f 拒污」已把该风险从静默降为有界失败。

### ⑨-4 结论

云端任务 12769301 prompt 现版（14,533 字符，D12+D13 修复后）**可以上线**：三处主理人修复独立终验全 PASS，静态扫描+端到端实跑双通道零已知问题，S1-S5 登记行为+退出码全链实证 PASS。结果移交交易分析团队全场景终验。
