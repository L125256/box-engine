# REGIME 工单 · 第一阶段（快件）战报 PHASE1_REPORT

> 工单：REGIME_SPEC_v1 运行第一阶段（R8 并行铁律：本单只跑 <10 分钟快件；主判线大计算留主对话层满核收口）
> 执行：工程保障团队（单 agent 5 席全席，工程总监终裁）· 2026-10-19
> 依据：research/REGIME_SPEC_v1.md（含三修改批准记录：探针先行 / E2E3 补 CUSUM 锚定 / 无中间态）——判线数字逐字实现，无发挥
> 证据分级：【实证】/【推断】/【假设】三级标注全程适用

---

## ① E2/E3 CUSUM 变点锚定（事件清单已冻结）【实证】

方法：双侧 CUSUM（S=cumsum(x−mean)，k\*=argmax|S|，同 E1/T4 法）；主判序列 E1=fee60_ann（费压）、E2/E3=idx 日收益（池等权均价）；±30 日窗；另跑 3 条旁证序列互证防边界伪影。决策规则（工单冻结）：偏差 ≤2 日维持原锚，>2 日建议修正。

| 事件 | 原锚 | 主判实测 | 偏差 | 旁证序列实测 | 判定 |
|---|---|---|---|---|---|
| E1（2026-04 成本脸跳变） | 未落日（假设锚 04-15） | **2026-04-20**（fee60_ann） | 5 日 | idx_ret=05-09（旁证非判） | **首测落锚 2026-04-20，冻结** |
| E2（realC 段开始） | 2026-06-01 | **2026-05-09**（idx_ret） | 23 日 | idx_logdiff=05-09、fee60_ann=05-13、abs_ret=05-18 | **建议修正 → 2026-05-09，冻结** |
| E3（realC1/C2 切点） | 2026-08-09 | **2026-07-29**（idx_ret） | 11 日 | idx_logdiff=07-29、fee60_ann=07-30、abs_ret=08-04 | **建议修正 → 2026-07-29，冻结** |

要点：
- E2：四序列同向指 5 月上中旬（非单序列边界伪影，实测位均处窗内前 1/4~中部）——realC 变脸在费压与指数收益上**早于段切分边界 23 日**显现，费压 CUSUM 05-13 同向佐证「5 月成本脸已在变」。【实证】
- E3：三序列同指 07-29/07-30（窗中部，非边界），原锚 08-09 偏后。【实证】
- 冻结产物：`research/wo_regime/event_anchor.json`（含全量 CUSUM 数字与旁证表）；`run` 子命令已改为读取该冻结值。**事件清单就此冻结，「只刷新一次」规则维持。**
- 语义注【推断】：修正后 E2/E3 为「读数可测变脸点」，与「研究段切分边界」分离——这正是批准记录第 2 条要求锚定的目的（缓解 §六.2-② 循环风险）。

## ② RG3 探针【实证-沙箱】

| 端点 | 结果 |
|---|---|
| fapi.binance.com/fapi/v1/fundingRate | **不可达**（curl: 连接超时 10s；urllib: Errno 101 Network is unreachable） |
| api.bybit.com/v5/market/tickers | **不可达**（同上） |

- 结论：**沙箱实测不可达；云端待复测**。按批准记录第 1 条：不可达 → RG3 以「不可判定」结单（W1 复活条件①合法执行，非判死），RG3-1/RG3-2 计入 FDR m=15、不产 p 值，禁备源估算顶替。
- 产物：/tmp/wo_regime/rg3_probe.json（脚本化复跑件）。

## ③ 判线运行脚本（写好+冒烟通过，全量留主对话层）

- 脚本：`research/wo_regime/regime_run.py`（子命令 prep/probe/anchor/run[--smoke]）
- 头注=预注册声明：15 变体一次性冻结（RG1×3/RG2×2/RG3×2/RG4×3/RG5×2/RG6×3）、六腿判线逐条引用 SPEC §四条款号、R1 重跑配额 ≤1 写入、无仓位动作逻辑（§六.1 铁律）。
- 判线数字逐字：L1 训练段 P90/P10 极值带+≥3 交易日提前；L2 N1≤2 次+月均≤1；L3 分年/双池/lag=1；L4 bootstrap **B=2000** seed=42 + LOTO 20 次 ≥19；L5 BH q=0.10 m=15；L6 垫 ≥3× 置换基线（1000 次 seed=42）。
  - 【规格对齐注】工单文本写「bootstrap 1000 次」但同句声明「全按规格」——SPEC L4 冻结 B=2000 为准，实现取 2000。
- 并行：multiprocessing Pool(32)（变体×双池 map、LOTO 回放 map）。
- 冒烟【实证】：`run --smoke` 60 日截断窗+E1 单事件+降配，**全链路无报错跑通**（15 变体六腿+双池+BH FDR+LOTO 路径+聚合判定+产物落盘；13 DEAD+2 UNDECIDABLE，冒烟结果【冒烟·低权重】非权威，R7 标注）。产物：research/wo_regime/rg_result_smoke.json。
- 全量耗时预估（供主对话层决策）：prep 回放 16s + 判线 map（秒级）+ 回放域 LOTO 20 次回放 Pool(32)（~40-60s）+ 价格域 LOTO（~10s）≈ **2-4 分钟，分钟级**（与 SPEC §五 成本预估一致）。主对话层执行 `python3 research/wo_regime/regime_run.py run` 即可（需 /tmp/wo_regime/baseline.npz，缺失时自动先跑 prep）。

## ④ D0 对拍（ALL PASS，diff=0）

基线：f1_web/f1_live.json（asof=2026-10-17）；复算：现行引擎（sha=6acc937d…，AUTHORITY_SHA.json 登记）+ 权威缓存。

| 对拍项 | 复算值 | live 值 | 结果 |
|---|---|---|---|
| D0-2 gate.idx | 218.5703 | 218.5703 | PASS（diff=0） |
| D0-2 gate.ma50 | 236.3814 | 236.3814 | PASS（diff=0） |
| D0-2 gate.on_holdcash | True | True | PASS |
| D0-4 fee_60d | 0.001617 | 0.001617 | PASS（diff=0） |
| D0-4 fee_ann_pct | 0.0068 | 0.0068 | PASS |
| D0-3 CB2 stop_count_60d（引擎 eval_breakers 重算） | 14 | 14 | PASS |
| D0-3 CB2 stop_pnl_sum_60d | −0.035 | −0.035 | PASS |
| D0-3 CB3 基线 | 9.07 | 9.07 | PASS |
| D0-1 CB1 mdd20（引擎重算） | −0.0069 | −0.0069 | PASS |
| 回放净账终值（备查非四腿） | 1.2653 | 1.2653 | 一致 |
| breadth 读数管线 vs calc_breadth（同输入逐位） | 21.53/31/144 | — | PASS（diff=0） |

缺口与事故登记（R7 诚实标注）：
1. **f1_live.json 无 breadth 字段**（生成于 WO-BREADTH-01 落盘前，两份副本同）——D0-1 改以「读数管线 vs f1_signal.calc_breadth 同输入逐位一致」断言。【实证】
2. **规格 breadth 锚 22.92/33/144 本地不可复现**：该锚为 2026-10-19 盘中根（10-19 部分K）实测，本地无对应数据 vintage；可复现锚=22.22/32/144（asof 10-17，fresh 缓存）与 21.53/31/144（asof 10-18）。差 1 票归因 asof vintage 差异，非口径错误。【实证+推断】
3. **live meta engine_sha256=262bf3a4 ≠ 现行 6acc937d**：WO-BREADTH-01 于 live 生成（10-19 05:20）后改引擎；D0 以行为值对拍为准（全部 diff=0），登记备查。
4. **/tmp/box_cache 曾被污染**（部分标的仅剩近 90 根K，权威池 144→133 崩）：已用快照包+fresh 缓存诊断，最终数据源=/tmp/box_cache_fresh（复算 idx(10-17)=218.5703 与 live 逐位一致，即 live 生成态）。污染副本留 /tmp/box_cache_dirty_20261019 备查。engine_snapshot/box_cache_snapshot.tar.gz 的 10-17 根为盘中部分K（18:28 刷新），不用于 D0。【实证】
5. RG2 换手【推断】口径：引擎不落盘 qty 明细，以「开桶日持仓成分变动率 =(n_out+n_in)/(2×5)」日度化实现，T4 的 0.175→0.678x 同为开桶日口径；L3-② 双池同向对回放域读数（RG1/RG2/RG6）以 144 池序列为准，价格域（RG4/RG5）逐位重算 old131——已在 rg_result.json data_limits 如实登记。

## 主判线运行清单（主对话层收口用）

```bash
cd /workspace/repo_ready/research/wo_regime
python3 regime_run.py prep     # 如 baseline 缓存缺失会自动跑，可跳过
python3 regime_run.py run      # 全量六族六腿，Pool(32)，预计 2-4 分钟
# 产物：research/wo_regime/rg_result.json + /tmp/wo_regime/rg_result.json
```

## 纪律与遗留

- 本单未动 f1_signal.py、未动现有 research/ 文件（仅新增 wo_regime/）。
- commit（不 push，攒着）：分两阶段——锚定（event_anchor.json+探针）/ 脚本+D0+冒烟+报告。
- 遗留主对话层：①跑全量判线收口；②云端复测 RG3 探针（可复活 RG3）；③RG1 日度费用归因引擎日志补齐路径（SPEC §2.1 数据受限项）未在本单展开。
