# SHADOW_BUILD_REPORT — 影子期施工六件交付报告（工程保障团队单 agent 5 席全席）

- 施工：2026-10-20 ｜ 方法书=SHADOW_SPEC_v1.md + K1P70_SPEC_v1.md（预注册冻结，照抄执行零发挥）
- 数据态：/tmp/box_cache（OD-R1 引擎唯一数据态；D0 实测全部锚在其上逐位复现；
  快照 tar 为冷启动兜底——tar 与 /tmp 在合成段早期历史存在 vintage 行差，
  已在 D0 chk1 以域锚窗断言+窗外登记处理，见 §D0）

## 一、六件状态

| # | 件 | 状态 | 产出 |
|---|---|---|---|
| 1 | shadow_cells.py（4 格影子计数器） | ✅ 落地 | research/wo_mine/shadow_cells.py；状态 f1/shadow_state.json（+影子窗有读数后 f1/shadow_days.jsonl；判读时 f1/shadow_readout_*.json） |
| 2 | 判定轮 --auto 挂接 | ✅ 落地 | engine_f1/f1_signal.py:1082-1091 与 f1/f1_signal.py:1082-1091（forward_readout 挂接之后同款 subprocess 旁路，timeout=1800、check=False、异常不阻断判定轮；引擎主逻辑零改动） |
| 3 | p80 补样状态机 | ✅ 落地（SUSPENDED 0/4） | S4 计数器内置 shadow_cells.py s4_collect：old131 弱稳（lag=1）真实交易日累积 ≥4 当轮自动 ACTIVE 并落盘留痕；补齐前不采集/不计数/不判读/不输出（§4 不启停规则逐字） |
| 4 | REALC 传参修复 + 重落 | ✅ 落地 | batch2_run.py 三处（现行行号 396/461/532，工单行号 518 系审计修正后漂移，注释已登记）rc 误传 ic 改显式传参（默认值不动，登记级）；realc_fix_batch2.py 重跑 Q1/Q3/Q4 重落 FACTBOOK_BATCH2.jsonl REALC 行 26 行（Q2 8 行本就正确未动） |
| 5 | k1p70_grid.py | ✅ 落地 | research/wo_mine/k1p70_grid.py → k1p70_result.json + k1p70_verdict.json（sealed 判读产出，§五） |
| 6 | D0 延续（首跑过锚） | ✅ 全过 | shadow D0 四腿 all_pass（§三）；k1p70 D0 两腿 hit（§五）；REALC 修复 diff 见 §四 |

## 二、shadow_cells.py 结构（骨架承继 forward_readout.py 逐项）

- 路径：仓库根相对（__file__ 上溯两级，env SHADOW_REPO_ROOT 可覆盖，禁绝对路径）；
- 数据源：env > /tmp/box_cache > engine_snapshot 快照解包（幂等）；
- 状态：f1/ 目录随判定轮回传持久化（shadow_state.json + shadow_days.jsonl）；
- 血缘：只读 f1/f1_live.json signal.asof（本轮 round_asof=2026-10-17）；
- S1-S3：因子式=batch2_run.py VS 清单逐字抄录（Q3-rev-liq:438 / Q3-rev-5:436 /
  Q1-brk-pos-20:360-361），horizon=fwd5，MC.xsec_ic_series（min_names=30），
  域限定采集（S1/S2=弱躁、S3=牛躁，不跨域——因子研究席条款）；
- 判线（§3 数字冻结）：达标=IC>0 ∧ t≥2 ∧ 日命中率≥60%（定夺点：用户批准 60%，
  只作辅助腿）；失败=IC<0（n≥20 判死）或早判死 n≥10∧IC<0∧t≤−2；一次判读封印；
- S4：门阈值=domains.json anchors.gate_vol20_p80_by_pool（冻结），臂=batch3 gate80
  pause 逐字同构（base/gate80/gate80lag1），影子窗段统计 avoid/mdd_red/lag1 avoid，
  三腿=avoid>0 ∧ mdd_red≥10% ∧ lag 不翻转，事件≥3 判读，双池同向为达标前置。

### 口径操作化登记（R7；SHADOW_SPEC 未逐字定义处，提请终裁）

- _OPS1 S1-S3 采集频次=日频（非周信号日）：ATLAS 底层=batch2 逐日截面 IC 按域分窗，
  §3 自述「日频 Spearman 截面 IC」「回测段日命中率」，影子复验须同尺度；成熟度=fwd5
  满 5 交易日（承继 FR-2 成熟登记语义）。
- _OPS2 域标签：回测段=domains.json 冻结标签（D0 断言 pool_d1 重算零漂移）；前瞻段=
  同式实时延拓（idx/MA50 ∧ vol_med>冻结锚 VAG，lag=1）。
- _OPS3 S4 触发事件=执行日读门信号（shift(1)）连续为真段数（episode）；判读触发以
  主格池 full144 事件≥3 为准，old131 随双池纪律并入。
- _OPS4 判读三态：达标/失败/未达标（事件或 n 达门即判即封印；三腿未全过且未触发
  失败路径=未达标，无中间态留窗）。
- 补样计数单位=old131 池 lag=1 弱稳真实交易日（与 ATLAS n_days=56 同单位，56+4=60
  对齐 60 日门；spec「信号日」措辞按此口径落，已在状态文件 unit 字段登记）。

## 三、D0：shadow 首跑读数与 ATLAS 底层数据 diff=0（工单件⑥）

f1/shadow_state.json d0 节（all_pass=true，2026-10-20）：

| 腿 | 内容 | 结果 |
|---|---|---|
| chk1 | full144 域标签重算 vs domains.json 冻结标签（域锚窗 2025-06-01 起） | hit，n_diff=0（窗外合成段 2024-04-05 一处 vintage 行差已登记：None vs 弱稳） |
| chk2 | S1/S2/S3 FULL 窗域内日 IC 均值 vs ATLAS 锚 | **diff=0 逐位**：S1 0.133685=0.133685、S2 0.10875=0.10875、S3 0.1126=0.1126（n=110/110/103，回测段命中率 0.5545/0.5636/0.6505——60% 判线与回测段下沿相容） |
| chk3 | S4 重放 gate80 pause 臂 vs FACTBOOK_BATCH1 FULL 行 ±0.01 | hit：full144 189.6599/27.9 逐位；old131 −8.7673/49.08 逐位（batch3 replay_check_all=hit 同证） |
| chk4 | 补样基线 n_days=56 + 需 4 天 → 60 | hit |

首采预告：影子窗 2026-10-18 起，数据尾日 2026-10-17，fwd5 成熟需 5 个交易日——
**判定轮未到，挂接完成待 08:30 首采**；首批成熟 IC 读数预计 2026-10-27 前后开始入册。

## 四、REALC 修复（登记级）

- 缺陷：batch2_run.py Q1/Q3/Q4 三处 REALC 行误传全窗 ic（rc 已算未用）——REALC 行
  实为 FULL 窗重贴（如 Q3-rev-liq n_days=282 应为 116）。
- 修复：三处改显式传 REALC 窗序列（默认值不动）；价差列同步限窗保单窗口径
  （空序列守卫防 RangeIndex 比较，登记）。
- 重落：26 行（Q1 8+Q3 10+Q4 8）替换 FACTBOOK_BATCH2.jsonl；git diff 24 行实质变化
  （2 行重算逐位同值）。样例（n_days / ic_mean / ic_t / spread_net_pp）：
  - Q3-rev-liq：282/0.011533/0.661229/−0.8424 → **116/0.076134/2.457391/+1.8430**
  - Q1-brk-pos-20：302/0.033576/2.244295/+0.5401 → **135/0.032677/1.152536/−0.2468**
- 影响面：仅 REALC 行（D1/FULL 行零改动）；ATLAS 图谱基于 D1 行，不受影响。

## 五、k1p70_grid.py 判读（K1P70_SPEC §3，无中间态）

- D0：gate70 重放 vs FACTBOOK_BATCH3 hit（128.2103/13.04 与 100.7821/19.46 逐位）、
  gate80 重放 vs FACTBOOK_BATCH1 hit——两腿全过方出数。
- 阈值锚：p80=domains.json（1.035910/1.226653）；p70=batch3 冻结（0.219964/0.223697）；
  p75=本件 LN_REALA q0.75 先落盘后回放（0.925061/1.102614）。
- 四数表（现行费率臂，费后，A/C 单位=万元=名义 100 万×1pp）：

| 池 | 档 | avoid_pp | mdd_red% | OFF 执行日 | OFF 扩大量 vs p80 | A | C |
|---|---|---|---|---|---|---|---|
| old131 | p70 | +128.2103 | 13.04 | 237 | +82 | 0.00 | −64.57 |
| old131 | p75 | +111.2115 | 11.04 | 177 | +22 | 10.73 | −48.98 |
| old131 | p80 | −8.7673 | 49.08 | 155 | 0 | 5.55 | +20.05 |
| full144 | p70 | +100.7821 | 19.46 | 237 | +103 | 0.00 | −53.19 |
| full144 | p75 | +128.8728 | 28.88 | 155 | +21 | 1.78 | −60.92 |
| full144 | p80 | +189.6599 | 27.90 | 134 | 0 | 14.62 | −57.77 |

- 判线（只裁 p70 vs p80；p75 只算不裁）：
  ① 净差为正 ΔA>ΔC：old131 −5.55>−84.62 ✓；full144 −14.62>4.58 ✗ → **不过**
  ② 双池同向（净差>0）：old131 +79.06 万 ✓；full144 **−19.20 万 ✗** → 不过
  ③ 分年不翻脸：负年=2025|old131 −0.0048 万、2025|full144 −0.0034 万、
     2026|full144 −19.20 万 → 不过（逐年明细全量见 k1p70_result.json yearly_net
     与 episodes 逐段明细）
  ④ p75 只算不裁 ✓（交换曲线完整性）
- **判定（无中间态）：p70 不优于 p80，维持 p80 锚**（负结果同权入册；不触发任何
  F1/部署改动——拒绝清单③；p70 谱系 MAP-INVALID 标记不混写，两标记并行）。
- 读数注记（如实）：p70 档触发段内基线回撤段数为 0（A=0）——p70 阈值低门常开，
  avoid 增益主要来自 OFF 段存量仓续持相对基线的超额（PB-7 语义），错过成本同步
  放大；p80 档避免/错过两边并存。×1.5 费压伴行臂四数同步落 grid[].fee15。

## 六、纪律遵守

- 引擎 f1_signal.py 主逻辑零改动（挂接=forward_readout 同款旁路块，仅追加）；
- f1/shadow_state.json / shadow_days.jsonl 为运行产物不入库（云端轮回传）；
- R8：k1p70 16 臂 Pool(32)（墙钟 26.1s）；REALC 三族并行重跑；shadow 常驻件
  分钟级（≈3-30s/轮，timeout=1800 富余）；
- R10：影子读数/深化产出均不回写部署姿态，全部产出带 R10 注记；
- commit 不 push；本报告为节点交付，**当前待推送 commit 数见 git log（本节点 1 个）**。

## 七、待办与移交

1. 08:30 判定轮首采后：shadow_days.jsonl 开始累积；S1-S3 n≥10 前无任何结论输出（SH-6）；
2. old131 弱稳累积满 4 天当轮 S4 自动 ACTIVE（落盘留痕）；
3. _OPS1.._OPS4 口径操作化提请交易分析团队/首席终裁追认；
4. K1P70_VERDICT.md（席位签署版）按 K1P70_SPEC §5-4 留待跑数后另立——本工单以
   k1p70_verdict.json（sealed）+本报告 §五 为判读载体，如需签署版另派工单。
