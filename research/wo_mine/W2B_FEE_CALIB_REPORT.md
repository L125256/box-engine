# W2B_FEE_CALIB_REPORT — 工单⑤ 费用真实化对拍报告（W2B_SPEC §5 冻结口径）

- 生成：2026-10-20 ｜ 运行件：`research/wo_mine/w2b_fee_calib_run.py` ｜ 结果：`w2b_fee_calib_result.json`
- 红线自查：`dneg_engine.py`/`common_fdbrk.py` md5 运行前后一致（禁改引擎费常数 ✓）；本单不含任何引擎费常数改动
- 数据态：唯一数据态=/tmp/box_cache_w2a（snapshot_20261019，perfile-agg 2b2c9572…，数据态事件登记见 wave2_run.py 头注）

## 一、结论三值（§5.3 冻结判读口径）

**费敏感成立**（替代路径口径；f_real 实测对拍因数据源判死不可执行，见下）。

| 线 | 敏感系数（每 ±0.01pp 费差） | ctrl ±0.05 容差判读 |
|---|---|---|
| fd 线（ctrl 冻结臂 n=1802） | ΔmeanR = **−0.1049**/+0.01pp/bar | **超限**（0.10 > 0.05） |
| dneg 线 old131（base & armC avoid） | Δavoid = **−0.6342pp**/±0.01pp funding | **超限** |
| dneg 线 full144（同上） | Δavoid = **−1.5410pp**/±0.01pp funding | **超限** |

受影响判读格清单（按风控席：加敏感注记，**不改已封印判读**，k1p70 sealed 先例）：
K5/fd 系全部 meanR 读数（fd_result final n=1802/sum 2125.96、K5 八出场变体、本批方向① D-A 臂）与 D-A 复活五件套；dneg 系 armC/gate 系 avoid_pp 读数（约 ±0.6~1.5pp/0.01pp funding）。

## 二、f_real 状态：【数据受限·R5·非死】

- funding 数据源维持 R9 判死：`raw/funding_death_archive.json`（58 探测证据，双源全无）；复活哨兵 `tools/w1_probe_rerun.py` 本会话复跑（57 路径，fetched_at=2026-10-20T10:45:36Z），funding 端点活 JSON=**0**——复活条件①（境外所可达实测）②（导演站新增端点）均未满足。
- box_cache 全 176 文件核查：无任何 funding/rate 字段。
- `gate_funding_eq` 三件已齐（`research/wo_w1/gate_funding/`：funding_eq.jsonl（0 行）+ `_manifest.json`，与 rg3_retest 引用键对得上）；manifest 缺口登记=**全部 176 标的**【数据受限】，有数标的=0，**禁代理顶替**（CME 基差/USDCNH 只进影子层，RG3 先例）。
- ⇒ §5.3 冻结对拍（f_const vs f_real 三臂双费基）本轮**不可执行**，如实登记。

## 三、R5 替代路径：费参数敏感扫描（非 f_real 对拍，R7 标注）

f_real 缺席下，以「费参数 ±0.01pp 邻域敏感系数」替代回答「0.03%/bar 常数可用性」：

1. **fd 线（解析法，零引擎改动）**：FEE 只线性进入 r 计算（出场决策与费无关，batch3 mk_partial 结构逐字核对），由 D0 重放落盘的 ctrl 逐笔 (ep,ei,xi,xc) 解析重算 r(FEE)：0.02%→1.2903 / 0.03%→1.1853 / 0.04%→1.0804（n=1802 逐位）。f_const 档 meanR=1.1853 与锚 1.1798 差 0.0055（vintage 漂移 batch3 同先例）。
2. **dneg 线（费参数化已就位 mine_common.py:189-190）**：base & armC（g2+s3 逐字）× fund ∈ {0.0002,0.0003,0.0004}，双池。avoid_pp 随 funding 单调：old131 43.17/42.54/41.91；full144 71.16/69.60/68.07（f_const=参照档，默认费基，非 D0 锚④费压臂）。

**判读**：若真实费基偏离 0.03%/bar 达 0.01pp，fd meanR 漂 ~0.10（2× 容差）、armC avoid 漂 0.6~1.5pp——常数可用性在 ±0.01pp 带内**不成立**。但「真实费基在哪」仍【未验证假设】（f_real 缺席），复活后须按 §5.3 补正式对拍。

## 四、复活条件与替代路径（R5）

1. funding 复活（境外所 API 实测通过 / 导演站新增端点）→ 按 §5.3 三臂双费基正式对拍（管线已就位，<30 分钟）；
2. 引擎费常数修改（如需）= **另立新工单交用户批准**（本单禁改）；
3. 影子期可用敏感系数做费基压力注记（每 0.01pp：fd meanR ∓0.105 / armC avoid ∓0.63~1.54pp）。
