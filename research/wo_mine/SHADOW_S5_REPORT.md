# SHADOW_S5_REPORT — S5=fd-da 格影子挂接交付报告（工程保障团队单 agent 5 席全席）

- 施工：2026-10-20 ｜ 依据=FD_REVIVE_SPEC_v1.md §4 J5（数字冻结）+ 交易分析团队终裁
  （2026-10-20：影子挂接授权，S5 格判线承继 J5 冻结数字：n≥20 配对 Δ meanR>0、
  判读一次封印、季度滚动复判≤1、不回写）+ SHADOW_SPEC_v1 挂接先例
  （shadow_cells.py S1-S4 同构）。照抄执行，零自行定义金融口径。

## 一、五件状态

| # | 件 | 状态 | 产出 |
|---|---|---|---|
| 1 | shadow_cells.py 增格 S5=fd-da | ✅ 落地 | research/wo_mine/shadow_cells.py s5_*（fd_revive_run.py 逐字复用：入场 scan_fd_exit 零改动、出场 _fd_exit_fns D-A/ctrl 逐字、pair_stats/delta_summary/_w_main 逐字，禁另写）；S1-S4 既有格零改动 |
| 2 | fd_revive_state.json 落 f1/（终裁施工登记项，比照 SH-3） | ✅ 落地 | f1/fd_revive_state.json（n 计数/sealed/verdict/sealed_at/rejudge{max_per_quarter=1, last_rejudge_at, next_window_from} 字段）+ f1/fd_revive_days.jsonl 逐笔配对读数（比照 shadow_days.jsonl）；运行产物不入库（云端轮回传） |
| 3 | 判定轮/快照轮 --auto 挂接 | ✅ 落地 | 判定轮=既有 S1-S4 同款 subprocess 旁路自动覆盖 S5（shadow_cells.py --auto 单入口）；快照轮=新增同款旁路块 engine_f1/f1_signal.py:1194-1203 与 f1/f1_signal.py 同行号（timeout=1800、check=False、异常不阻断；引擎主逻辑零改动） |
| 4 | D0：S5 首跑读数 vs fd_revive_result.json realA 配对段 diff=0 | ✅ 全过 | 四位逐位 diff=0（见 §二） |
| 5 | 报告 | ✅ 本件 | research/wo_mine/SHADOW_S5_REPORT.md |

## 二、D0：S5 采集机器复放 realA 配对段 diff=0（工单件⑥ S5 腿）

数据=冻结快照内容副本 /tmp/box_cache_fresh（fd_revive_run 同款；缺失即停工，
禁以 live 数据代跑 D0），窗=CF.MAIN..CF.TRUNC（2025-06-01→2026-05-31）：

| 位 | S5 复放 got | fd_revive_result.json want | diff |
|---|---|---|---|
| n_paired | 1228 | 1228 | **0** |
| pair_rate | 0.9832 | 0.9832 | **0** |
| Δ meanR | 0.335 | 0.335 | **0** |
| Δ sum_r | 411.37 | 411.37 | **0** |

verdict=hit（f1/fd_revive_state.json d0 节留痕）。逐字复用管线（入场/出场/配对/
汇总四层零另写）+ 冻结副本数据 → 逐位复现，机器等价性成立。

## 三、S5 格语义（判线全部承继冻结数字，零新判线）

- 采集：每日旁路（判定轮/快照轮），live 唯一数据态，前瞻窗 S5_FW=2026-10-20
  （FD_REVIVE_SPEC §3.1④ 冻结）起，同信号 (tkr, et) 配对（fd_revive_run.pair_stats
  逐字），D-A 臂=K5-fd-exit-partial3r-breakeven、对照臂=K5-fd-exit-ctrl。
- 判线（J5 冻结）：n≥20 配对前瞻信号 Δ meanR>0 → 达标（影子候选终审资格）；
  否则判死。判读一次封印 sealed=true；n<20 只累计不判（SH-6 同款）。
- 季度滚动复判：判死后复活路径(a)=同判线机械复判，每自然季至多一次
  （rejudge.next_window_from 落盘留痕）；不回写部署姿态（R10）。

### 口径操作化登记（R7；提请终裁追认）

- _OPS5 扫描口径（WO-DECBAR 判定轮 bar 选择承继）：剔除数据尾日=运行日的未收盘
  盘中 bar，只用最后完整日收盘数据（首采实测剔除 144 根 2026-10-20 盘中 bar，
  扫描尾日=2026-10-19）。D0 用冻结副本（全完整）不受影响。
- _OPS6 影子读数只计「已平仓」配对信号：两臂出场均已发生（why≠数据末）方入计数——
  持仓中交易的 r 为临时值，入册即伪读数（fd_revive_run 回测口径为全历史窗，此差异
  为本格前瞻化操作化）。
- _OPS7 fd 谱系装载回落：eng_final 优先 /tmp/eng_wt_rc（fd_revive_run 在库口径），
  /tmp 失忆回落仓库内 research/eng_wt_rc（同件）；D0 数据缺失即停工重锚。

## 四、影子家族全景（首采日 2026-10-20 读数）

| 格 | 类型 | 门状态 | n/门 | 说明 |
|---|---|---|---|---|
| S1 | Q3-rev-liq 因子格 | ACCUMULATING | 0/20 | fwd5 成熟需 5 交易日，首批 IC 读数预计 2026-10-27 前后 |
| S2 | Q3-rev-5 因子格 | ACCUMULATING | 0/20 | 同上 |
| S3 | Q1-brk-pos-20 因子格 | ACCUMULATING | 0/20 | 同上 |
| S4 | K1 换门事件格 | **SUSPENDED** | 0/4 事件 | §4 补样未达门（old131 弱稳 0/4）——不采集不计数不判读 |
| S5 | fd-da 出场格 | ACCUMULATING（起跑） | 0/20 配对信号 | 本单挂接；D0 过；前瞻信号待影子窗入场 |

五格判读彼此独立，不合并成组合读数；全部 R10 不回写。

## 五、纪律遵守

- 引擎 f1_signal.py 主逻辑零改动（仅追加同款旁路块与注释）；S1-S4 既有格零改动
  （SEALED_ALL 计数 4→5 格登记级适配，S1-S4 语义不变）；
- f1/fd_revive_state.json、f1/fd_revive_days.jsonl 为运行产物不入库（云端轮回传，
  B6 运行产物零污染）；
- R8：全池两臂扫描 Pool(32)（288 jobs，秒级）；R10：S5 全部产出带不回写注记；
- commit 不 push；当前待推送 commit 数=1（本节点）。

## 六、待办与移交

1. _OPS5/_OPS6/_OPS7 口径操作化提请交易分析团队/首席终裁追认；
2. 影子窗内 fd 前瞻信号入场后 fd_revive_days.jsonl 开始累积（n≥20 即判一次封印）；
3. 若判死：季度滚动复判（≤1/自然季）按 rejudge.next_window_from 机械执行；
4. S5 达标≠放行：放行仍走部署三道门+新预注册（R10 红线永不重开）。
