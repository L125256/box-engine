# METHOD_BOOK_BATCH1 · Batch 1 实施方法书（工程唯一施工依据）

- 立法实体：交易分析团队（单 agent 10 席位全席）· 首席策略官何执舟终裁 · 2026-10-20
- 适用纪律：R1 一发验证 / R2 知识霸权（引用必附出处 file:line）/ R4 庸医禁令 / R5 抢救义务 / R7 诚实标注 / R9 穷尽附证据 / R10 域只作坐标系不作开关
- 上位纲领：`research/MINE_SPEC_v1.md`（判线 §五、分域 §二、批次 §六 Batch 1）。**本方法书只定义金融逻辑与口径，不重立任何判线数字**；判线一律引用 MINE_SPEC §五（C1–C6 六腿、生死判定 §5.3、BH 合并族 m=86 §5.2-C6、双池同向 §5.4、n<60 只入册 §2.4-4）。
- 工程纪律：本文件公式与伪代码**逐字照抄**，工程零发挥空间；任何工程自行调整口径视为污染源。同切分重跑配额每变体 ≤1 次（仅代码缺陷修复）。

---

## 〇、总则（全部变体共用，先读本章）

### 0.1 数据源与常量（冻结）

| 项 | 值 | 出处 |
|---|---|---|
| 数据 | `/tmp/box_cache`（176 标的 OHLCV 日线，7×24 日历，engine_snapshot 唯一数据态） | RESCUE_REPORT.md L5 |
| 常量 | `FEE_SIDE=0.0005, FUNDING=0.0003, STOP=-0.08, CRASH_MED=-0.05, MA_REG=50, SLOT=0.10, TOP_N=5, SEED=42` | dneg_engine.py:28-41 |
| 引擎谱系 | 回测=dneg_engine.run_instr（f1_backtest_v2 逐行，D0 权威谱系）；门臂=run_gate/run_gate_g 谱系；选股=cross_scores 四因子 z 合成 | dneg_engine.py:86-104、f1_signal.py:210-222 |
| 池 | old131（2025-03-31 前上市 131 只）/ full144（≥100 根 K 线 144 只），断言 131/144 | dneg_engine.py:60-66 |
| 段定义 | realA=2025-06-02→2026-03-31；realB=04-01→05-31；realC=06-01→10-17；FULL=2025-06-02→10-17；HOLDOUT=04-01→10-17 | wo_rescue_run.py:86-89 |

### 0.2 双锚窗（分离登记，禁止混写）

1. **谱系窗**（活口原始验证口径，复现锚用）：realA=2025-06-02→2026-03-31（W3/PB-3，wo_rescue_run.py:86）。
2. **纲领窗**（域锚/FDR/图谱主判窗）：MS_REALA=2025-06-01→2026-10-17（MINE_SPEC §2.4）。
   分位锚逐窗各算各的，落盘时键名必须带窗名（`wo_mine/mine_common.py:36-37` 的 MS_REALA/LN_REALA 分离即为正确形态）。

### 0.3 域标签（D1 主方案，全部变体共用）

- 轴 A（趋势）：`牛 = idx >= MA50(idx)`，否则 `弱`；idx=池等权收盘均值；MA 不足 50 日=域未定义（None）。同源引擎 f1_signal.py:638-646（引擎 gate_on=idx<MA50 为持币取反语义，域标签用其取反=闸开语义，ALPHA D0-1 已证 diff=0）。
- 轴 B（波动）：`躁 = 池 vol20 中位 > MS_REALA 段 P50`，否则 `稳`；vol_med=个股日收益 20 日滚动 std(ddof=1)×√252 的池内中位（mine_common.py:87-88 已按此实现）。
- 四域：牛稳/牛躁/弱稳/弱躁。**域标签一律 lag=1**（昨日状态标今日格，MINE_SPEC §2.4-2）。
- D1 分位锚（MS_REALA 冻结，先落盘后回放，本席复算值）：vol_med P50=0.4202424305853871。域计数（realA 窗内，lag1 后）：牛稳 151 / 牛躁 103 / 弱稳 64 / 弱躁 110，无 <60 域。
- D2/D3 按 MINE_SPEC §2.2/§2.3 执行（D3 安慰剂 seed=42..141 ×100，仅 MS_REALA 评估窗内置换）。

### 0.4 分域统计通式（各变体章节只写差异）

每个「变体 × 域」格产出 FACTBOOK 一行（§七格式），指标分母如下：

| 指标 | 定义 | 分母 |
|---|---|---|
| n_days | 域内有效交易日数（该变体当日有输出的日子） | 域内交易日 |
| 费后胜率 | 域内 ISO 周段净收益>0 占比（周段=段末净值/段初净值−1，费后） | 域内完整周段数 |
| 年化超额 | 臂域内年化 − 参照臂（base/随机带中位/池等权）同域年化；年化=`(nav_end/nav_start)^(365.25/自然日差)−1` | 域内日历日 |
| MDD | 域内净值分段重链 cumprod 后最大回撤（跨域缺口不链接；近似口径【推断】登记，mine_common.mdd_of 谱系） | 域内净值段 |
| 垫 | 域内效应量 ≥3× 随机置换基线中位（置换 1000 次 seed=42，MINE_SPEC §5.2-C4） | — |
| CI | 日块 stationary bootstrap 95% CI（块长 10，B=2000，seed=42，MINE_SPEC §5.2-C2） | — |

- 域标签 lag=1；n_days<60 的域只入事实手册附数、不入图谱判分（MINE_SPEC §5.4）。
- 双池纪律：域胜任须 old131/full144 同向（MINE_SPEC §5.4）。
- **R10 红线：任何脚本不得产出「域读数→仓位」映射**（每个运行脚本头注写明）。

### 0.5 复现锚容差（全表通用）

- 同数据同 seed 重跑应为逐位一致；允许容差：t 值与 IC ±0.01、pp 类 ±0.05、净值/曲线类 absdiff ≤1e-6、笔数类必须逐位相等。超容差=工程实现有错，禁改锚。

---

## 一、变体 1-1：c4 池间 RS（Q5 承接，活口 M1）

- **金融含义**：抓「新旧币世代间的资金轮动」——个股 20 日收益相对另一世代池等权 20 日收益的强弱差，动量臂押注的是「轮动一旦启动会自我强化」（强者相对更强的正反馈段）。

### 精确定义（照抄 wo_rescue_run.py:779-812，PC-4 冻结）

```
ret20_s(t) = Close_s(t)/Close_s(t−20) − 1                      # 逐标的
idx_old(t) = mean(ret20_s(t), s∈old131)                        # 老池等权 20 日收益
idx_new(t) = mean(ret20_s(t), s∈new13)                         # new13 = full144 − old131（13 只）
RS_s(t)    = ret20_s(t) − (s∈old131 ? idx_new(t) : idx_old(t)) # 异池互指
因子面板    fa = RS（rs_mom）；rs_rev = −RS 为均值回归臂（X6 已判死，禁再跑）
IC(t)      = Spearman 截面秩相关(fa(t), fwd20(t))              # fwd20_s(t)=Close_s(t+20)/Close_s(t)−1
             当日截面有效样本 <30 → 当日无 IC
t          = mean(IC)/std(IC, ddof=1) × sqrt(n)               # n=有效 IC 日数
费后十分位价差（信号日口径）：
  信号日 = 每周首个交易日（ISO 周首日，sig_ext 谱系）
  按因子值 rank 十分位（qcut, method='first'），价差=(Top组 fwd5 日收益均值 − Bottom组)×100 pp
  费后价差 = 价差 − 0.10pp（双边费）
活口臂 = RS_momentum|fwd20；Q5 预算内另跑 RS_momentum|fwd5（MINE_SPEC §3.5 双持有 2）
评估窗：extended=2025-06-02→2026-10-17 全交易日（逐日 IC，非仅信号日）
```

- **出处**：PC-4 操作性定义 wo_rescue_run.py:53-55；实现 wo_rescue_run.py:779-812；统计件 `_xsec_ic_series`/`_tstat`/`_decile_spread_fee` wo_rescue_run.py:549-586（mine_common.py:297-335 已逐行同构，可直接复用）；主册登记 RESCUE_REPORT.md L87（M1）。
- **复现锚**（c_new_candidates.json RS_momentum|fwd20，容差 §0.5）：

| 量 | 锚值 |
|---|---|
| t_extended | **+4.776407**（n_extended=317） |
| IC_mean_extended | +0.0592315 |
| t_realC | **−3.446861**（符号翻转，n=119；打折标签的实证内容） |
| IC_mean_realC | −0.0738190 |
| decile_spread_pp_raw / net | +1.4616 / **+1.3616** |
| fwd5 伴行 | t_extended=+1.618675、t_realC=−1.236898（n=134） |

- **分域统计口径**：域标签=full144 池 D1（lag1）逐日归属；①域内逐日 IC 均值/t/n_ic（分母=域内有效 IC 日数）；②域内信号日费后价差（分母=域内信号日数，≥30 标的才算）；③C1 随机带三臂按 MINE_SPEC §三统一判线（与 A 臂同口径对拍，ALPHA 谱系）；④D3 安慰剂照 §0.3。图谱答题：**RS 动量的翻转（realC t=−3.45）是否集中在特定域**——这正是活口转正/判死的判据路径（MINE_SPEC §3.5 假设句）。
- **数据与缺失**：/tmp/box_cache 全量；个股缺 K 线=NaN 跳过（不计入截面）；截面 <30 只当日弃算；new13 由 DE.build_pools 断言产出禁手改；资金费不涉及。

---

## 二、变体 2-1：c5 正交残差（Q6 承接，活口 M2）

- **金融含义**：抓「动量里剥不掉风格暴露后剩下的纯选股信息」——把波动、短期反转、流动性三个已知风格从四因子动量打分中正交掉，看残差是否仍能排序未来收益；赌的是动量 alpha 中有独立于三风格的成分。

### 精确定义（照抄 wo_rescue_run.py:814-864，PC-5 冻结）

```
合成 z（信号日 t 截面）：
  四因子值（ma20_slope/obv_slope20/dist_52w_high/mom_1m，缺任一剔除该标的）
  z = ((x − mean)/std(ddof=0)).clip(±3)，四因子等权均值
控制变量（逐标的、逐日）：
  vol_i  = Close.pct_change().rolling(20).std()          # 未年化（照抄原实现，勿加 √252）
  rev_i  = −(Close/Close.shift(10) − 1)                  # 10 日反转
  turn_i = log((Close×Volume).rolling(20).mean())        # 均额成交对数
逐信号日截面 OLS：z_s ~ vol_s + rev_s + turn_s + 1（np.linalg.lstsq），残差 res_s
IC(t) = Spearman(res, fwd5(t))；当日有效样本 <30 → 弃
窗口：extended=sig_ext（2025-06-02→2026-10-17 每周首日）；realC20=sig_rc（realC 内信号日）
t    = mean(IC)/std(IC,ddof=1)×sqrt(n)
```

- **Q6 变体 6 个细化（MINE_SPEC §3.6 预算内，本席细化落盘，禁加号）**：
  - V1 原集（=活口原口径，逐信号日截面 OLS，控制集 [vol20, rev_10d, log_turn20]）；
  - V2 +breadth（控制集追加当日池宽度 breadth，g1g2fdr_run.py:300-302 同式）；
  - V3 +缺口密度（追加近 5 日向下跳空>1% 未回补计数，wo_rescue_run.py:624-628 E3 同式）；
  - V4 原集−反转（控制集去掉 rev_i）；
  - V5/V6 窗口变体（60/120 日 OLS 窗）=**时序 pooled OLS**：以信号日 t 为终点取过去 60/120 个交易日的全部（日×标的）观测合并、带常数项一次估计 beta，再对 t 日截面应用得残差；窗内有效截面日 <30 该信号日弃用【细化口径，首次定义，登记 R7】。
  - 复现锚只绑定 V1；V2–V6 为新变体，无锚，判线走 MINE_SPEC §五。
- **出处**：PC-5 wo_rescue_run.py:56-57；实现 wo_rescue_run.py:814-864；主册 RESCUE_REPORT.md L88（M2）。
- **复现锚**（c_new_candidates.json c5，容差 §0.5）：

| 量 | extended | realC20 |
|---|---|---|
| IC_mean | **+0.0430687** | +0.0094756 |
| t | **+2.182077** | +0.251334（弱，n=20） |
| n_days | 54 | 20 |

- **分域统计口径**：域标签=full144 D1（lag1）；信号日按域归属后：域内残差 IC 均值/t/n（分母=域内有效信号日数）；域内费后十分位价差（Top−Bottom fwd5 − 0.10pp，分母=域内信号日数）；C1 三臂/C4 垫/C6 FDR 照 MINE_SPEC §三/§五。图谱答题：残差 alpha 的衰减（realC t=0.25）是否域可隔离。
- **数据与缺失**：/tmp/box_cache；四因子或控制变量任一缺失该标的当日剔除；截面 <30 弃算；信号日=ISO 周首日（含跨年周，isocalendar 口径）。

---

## 三、变体 3-1：d 降权 SLOT 半额（K1 承接，活口 M3）

- **金融含义**：抓「信号错向但未全错时的线性减伤」——alpha 衰减段把单仓风险预算从 10% 降到 5%，赌的是亏损与仓位近似线性、而换手成本减半+留存仓仍能吃到部分反弹，净改善为正。

### 精确定义（照抄 wo_rescue_run.py run_gate 谱系 + d_decay_monitor.json 路径①）

```
base 臂   = run_gate 谱系（无闸、无 crash 跳重建）：周信号日（ISO 周首日）收盘出信号，
            次日开盘成交 top5 等权，slot=DE.SLOT=0.10；止损 −8% 盘中触发；崩市闸
            med_ret<−5% 收盘判定→挂单次日开盘清仓；费 0.0005/0.0003；BUG-04 止损票当日禁买回。
降权臂    = 与 base 逐行相同，唯一改动 slot: 0.10 → 0.05（单仓预算减半）。
主判窗    = realC（2026-06-01→2026-10-17），费率=现行实盘（非费压）。
年化      = (nav_end/nav_start)^(365.25/自然日差) − 1（wo_hd_run.py:318-324 冻结公式）
MDD      = 段内净值最大回撤
```

- **出处**：RESCUE_REPORT.md L74（路径①表）、d_decay_monitor.json `reform_paths.1_downweight_slot_half`（数字权威源）；回放内核 mine_common.simulate lineage='gate'（wo_rescue run_gate 逐行同构）。
- **复现锚**（d_decay_monitor.json，容差 §0.5）：

| 池 | base realC ann/MDD | 降权 realC ann/MDD | Δann | ΔMDD 收窄 |
|---|---|---|---|---|
| old131 | −49.31% / −23.09% | **−28.33% / −12.08%** | **+20.98pp** | 11.01pp |
| full144 | −56.31% / −27.72% | **−33.56% / −14.81%** | **+22.75pp** | 12.91pp |

- **分域统计口径**：域标签=各池自身 D1（lag1；轴 A 用该池 idx，轴 B 用该池 vol_med——分母都是池内成员，不跨池借用）；域内分段（连续交易日段）重链净值后算 §0.4 全套；参照臂=base 同域；C1 随机带同域 20 种子（seed=42..61，ALPHA B 臂法）；双池同向纪律适用。
- **数据与缺失**：缺开盘价当日→挂单次日开盘执行（pending_sells 语义照抄 run_gate）；缺收盘价→mark=ffill 记账；其余照引擎。

---

## 四、变体 4-1：d 换门 vol20 p80 pause（K1 承接，活口 M4）

- **金融含义**：抓「风大不出海」——池等权 20 日实现波动率冲进历史（realA）最陡的 20% 分位时暂停开新仓，躲开止损绞肉最密集的日子；存量仓的止损/崩市处理照常，**不是清仓**。

### 精确定义（照抄 wo_hd_report/wo_hd_run.py，H-D 冻结口径）

```
vol20_p(t) = 池 p 等权收盘均值 idx 的日收益 20 日滚动 std(ddof=1) × √252（年化）
阈值       = vol20_p 在该池 realA 段（2025-06-02→2026-03-31）的 P80：
             old131 = 103.59% / full144 = 122.67%（年化波动率，逐池各算，禁共用）
门信号     = 信号日收盘 vol20_p(t) > 阈值 → 次日 OFF
OFF 语义   = pause（PB-4/H-D 冻结）：跳过开仓与换仓卖出；存量仓止损/崩市/BUG-04 照常；
             OFF 日若为信号日，target 照常计算但执行日不建仓
引擎       = run_gate 谱系 + overlay={'off':门信号, 'mode':'pause'}（mine_common.simulate 已实现）
费率       = 现行实盘（wo_hd 权威数字即现行费率口径）
```

- **出处**：HD_REPORT.md L19-22（施工口径表）、L39-57（八列终审表）；RESCUE_REPORT.md L76（引用不重烧）；门信号实现 gate_maps 谱系 wo_g1g2fdr_run.py:298（`vol_hi = gv['vol'] > gv['vol_thr'][80]`）。
- **复现锚**（wo_hd 八列表 + d_decay_monitor.json 路径③，容差 §0.5）：

| 池 | base realC ann/MDD | 门 realC ann/MDD | Δann | realC OFF 占比 |
|---|---|---|---|---|
| old131 | −49.31% / −23.09% | **−27.17% / −11.29%** | **+22.14pp** | 35.25%（49/139 天） |
| full144 | −56.31% / −27.72% | **−15.53% / −24.19%** | **+40.78pp** | 26.62%（37/139 天） |

伴行锚：realA 门臂 old131 +152.38%/full144 +164.91%（误伤率 20.18%）；滞后敏感性臂（vol20.shift(1)）照挂披露，不进判定。
- **分域统计口径**：同变体 3-1（各池自身 D1 lag1、§0.4 全套、参照臂=base 同域）；另按门域惯例加记 FULL/HOLDOUT avoid_pp 与 mdd_red（PB-7/8 公式：avoid=门臂段净收益−base 段净收益；mdd_red=(|base MDD|−|门臂 MDD|)/|base MDD|×100）作对照列，引用不混写。
- **数据与缺失**：vol20 窗口不足 20 日=NaN=不开 OFF；阈值估计仅用 realA 数据（防前视）；其余同引擎。

---

## 五、变体 5-1：S3×D1 交叉格 6 格（K1 承接，新预注册）

- **金融含义**：抓「该降风险的状态=高波动∧方向向下，且降风险=降半不清仓」——G1（S3 半额开门）与 G2（D1 方向过滤）各差一脚且失败腿互补（S3 卡 mdd_red、D1 卡 lag）；交叉赌的是：方向过滤砍掉「高波∧上涨」的误杀（realB 踏空病根），半额开门+不停换仓卖出保住存量仓与一半进攻（高波动态全额开仓放大回撤的 S2 病根）。

### 精确定义（照抄 wo_g1g2fdr_run.py:295-326 门信号 + :204-214 OFF 语义，PG1-2/PG2-2 冻结）

```
门信号 g2_ma(t) = (vol20_p(t) > 该池 realA P80 阈值) ∧ (idx_p(t) < MA50(idx_p)(t))
                  # vol_hi ∧ 方向向下；方向分母=池等权 idx 自身；NaN 比较记 False
OFF 语义 open_half_nosell（S3）：OFF 时 sell_skip=True（跳过换仓卖出）+ do_open=True
                  + slot_mult=0.5（新开仓半额 slot×0.5×eq_sig）；存量仓止损/崩市照常
费压口径   = 主判沿用 G1/G2 冻结口径：FEE_SIDE×1.5=0.00075、FUNDING×1.5=0.00045，
            base 臂同费对比（PB-5）；现行费率臂并行登记不混写
6 格       = 双池 {old131, full144} × 3 臂：
   臂 A：S3|v2门   （门=vol20 p80，语义=open_half_nosell）——G1 已有样本内数，对照臂
   臂 B：D1|v2门   （门=vol_hi∧idx<MA50，语义=v2_full_stop）——G2 已有样本内数，对照臂
   臂 C：S3×D1     （门=g2_ma，语义=open_half_nosell）——本轮新证据主体
（G1G2FDR §4.1 的 9 格矩阵 {S1/S2/S3}×{D1/D2/D3} 中 S1/D2/D3 已判死，本单按
  MINE_SPEC §4.1 冻结收窄为上 6 格；9→6 收窄依据=G1G2FDR §1/§2 判死证据，非挑点。）
```

- **出处**：MINE_SPEC §4.1（K1 变体 12 中的交叉格 6）+ §一 L37（承接登记）；G1G2FDR_REPORT.md §1（S3 全绿行）、§2（D1 机制增益坐实但 lag HOLD≈0）、§4.1（交叉格必须先立新预注册——本方法书即该预注册）；OFF 语义实现 wo_g1g2fdr_run.py:204-214、mine_common.simulate mode='s3'。
- **复现锚**（对照臂数字必须复现，容差 §0.5；臂 C 为新跑无锚）：

| 量 | old131 | full144 |
|---|---|---|
| 臂 A(S3) realB 段净收益（费压） | +90.31pp（v2 +14.89 → **+75.42pp**） | +129.72pp（+94.67 → **+35.04pp**） |
| 臂 A(S3) realC avoid | +12.77pp | +10.06pp |
| 臂 A(S3) FULL avoid / mdd_red | +155.03 / 38.81% | +197.21 / **7.17%**（<10 卡线锚） |
| 臂 A(S3) lag(FULL/HOLD avoid) | +154.84/+59.71 | +177.88/+68.82 |
| 臂 B(D1) FULL avoid / mdd_red | +60.86 / 36.60% | +85.44 / 27.74% |
| 臂 B(D1) lag HOLDOUT avoid | **−0.085**（≈0 卡线锚） | **−0.094** |
| 八列抽查：臂 A realB ann/MDD | +4926.62 / −13.80 | — |
| 八列抽查：臂 B realB ann/MDD | +2139.40 / −16.39 | — |

- **必答差异题（报告专节）**：W3 总 FAIL 病根=old131 realB 锁死 −44.69pp（MINE_SPEC §4.1）——臂 C 在 realB 的段净收益 vs v2 必须报告「解锁是否成立」，T1'/T2'/T3' 三检验照抄 G1G2FDR §1-2 定义（方向盲/OFF 日均值、滞后 shift(1) 全量重跑、反弹段 OFF 占比与踏空成本）。
- **分域统计口径**：臂 C 各池跑 §0.4 全套（域标签=各池自身 D1 lag1）；臂 A/B 的域格从本轮重跑产出（费压口径），与 G1/G2 存档数对拍后引用；C1 参照臂=base 同域同费压；FDR 走 m=86 合并表（C6）；双池同向纪律适用。
- **数据与缺失**：同引擎与门域谱系；NaN 方向读数=不 OFF（fillna(False)，gate_maps 同式）；资金费不涉及。

---

## 六、工程半成品验收意见（wo_mine/ 四件审查）

> 审查人：交易分析团队（本席复算于 2026-10-20）；结论分级照 R7。

### 6.1 逐件结论

| 件 | 结论 | 依据 |
|---|---|---|
| `mine_common.py`（统计件/域切分件） | **可保留** | xsec_ic_series/tstat/decile_spread_fee/stationary_boot/perm_baseline/bh_fdr_q 与 RESCUE/G1G2FDR 谱系逐行同构（R2 出处头注在）；域切分 D1/D2 定义与 §〇.3 一致；双锚窗分离正确（mine_common.py:36-38）；R10 红线声明在（:18） |
| `mine_common.simulate` lineage='alpha' 分支 | **须重写（口径错误点坐实）** | 缺「执行日闸开复核」：alpha_run.py:138 为 `if not skip_rebuild and bool(gate_open.at[t])`，mine_common.py:247 只判 `do_open`——信号日闸开、执行日闸关的周会误建仓。本席补复核后复算 **final=4.730578 与 alpha_result.json A_final 逐位一致（absdiff=0.000000）**，根因唯一坐实 |
| `mine_common.simulate` lineage='gate' 分支 | **可保留** | run_gate 谱系逐行同构，off_mode pause/s3 语义与 run_gate_g:204-214 一致（本席比对） |
| `batch0_domains.py` D0-1 | **可保留，须重跑落盘** | 现行代码逻辑正确（本席复算 same-day diff=0）；`D0_RESULT.json` 内 D0_1（diff_days=52）系**旧版脚本陈旧产物**（旧字段名 diff_days 与现行代码不符可证）——工程已改代码但未重跑，须重跑刷新 D0_RESULT.json 后方算过闸 |
| `batch0_domains.py` D0-2 | **可保留，判定式一处须修** | 内容全过（常量、breadth 锚 21.53/31/144、calc_breadth 同式）；FAIL 仅因浮点容差用 `==0`（maxdiff=5.68e-14）。**裁定：判定阈值改 ≤1e-9**（浮点噪声非口径错）。MINE_SPEC 引 22.92/33/144 为 10-19 盘中根，本地 vintage asof 10-18 复现 21.53/31/144——**本席裁定以本地快照 vintage 为准，纲领锚注记勘误**（batch0_domains.py:114 已如实登记，维持） |
| `batch0_domains.py` D0-3 | **可保留，md5 澄清项挂账** | fd 锚 673 笔/+723.64R/厚利 118 笔 2019.76R 逐位复现（PASS）；`snapshot_md5_ok=false` 与 RESCUE 登记 md5=0e4c4fb9… 不符——锚数字逐位一致说明数据态实质一致，但工程必须书面澄清 md5 计算范围差异后方可放行（R7 如实登记，禁止跳过） |
| `batch0_domains.py` D0-4 | **随 simulate 重写后重跑** | 根因见上；修复判据=absdiff≤1e-6 |
| `domains.json` | **可保留，须补一项** | D1 锚复算一致（vol_med P50=0.4202424305853871）；四域计数 151/103/64/110 全 ≥60；placebo 100 组齐；lag1 正确。**缺项：vol20 门锚只落盘了 full144（p80=1.226653=122.67% 与 wo_hd 一致），须补 old131 池自身 vol20 realA P80=103.59% 的逐池锚落盘**（变体 4-1/5-1 需要逐池阈值） |

### 6.2 停工条款

D0 四项按上述修复+重跑后 `all_pass=true` 方可开工 Batch 1；任一项复跑仍不过 → 停工上报，禁带病跑数（MINE_SPEC §六 Batch 0「任一对拍不过即停工」逐字适用）。

---

## 七、FACTBOOK 行格式终版（字段级定义）

每「变体 × 域（或窗）」一行；CSV/JSONL 皆可，字段名逐字如下：

| 字段 | 类型 | 定义 |
|---|---|---|
| batch | str | `batch1` |
| variant_id | str | `Q5-c4-rs_mom-fwd20` / `Q6-c5-v1_orig` / `K1-d-downweight-slot05` / `K1-d-gate-vol20p80-pause` / `K1-s3d1-arm{A,B,C}` |
| family | str | `Q5`/`Q6`/`K1` |
| pool | str | `old131`/`full144` |
| axis | str | `D1`/`D2`/`D3-placebo-k{0..99}`/`FULL`/`REALC`（域外对照行） |
| domain | str | D1: `牛稳/牛躁/弱稳/弱躁`；D2: `宽低费/…`；FULL 行填 `all` |
| n_days | int | 域内该变体有输出的交易日数（分母） |
| n_sig | int/null | 域内信号日数（因子族）或调仓次数（框架族）；无则 null |
| win_rate_pct | float/null | 域内费后周段胜率（§0.4）；无周段则 null |
| ann_pct | float/null | 域内年化（365.25 公式） |
| excess_pp | float/null | vs 参照臂同域年化差（pp）；参照臂在 notes 注明 |
| mdd_pct | float/null | 域内分段 MDD（§0.4） |
| ic_mean / ic_t / n_ic | float/float/int/null | 域内逐日（或逐信号日）IC 三件套；因子族必填，框架族 null |
| spread_net_pp | float/null | 域内费后十分位价差（因子族）；框架族 null |
| avoid_pp / mdd_red_pct | float/null | 门域/框架域对照列（PB-7/8 公式）；仅门臂行填 |
| cushion_x | float/null | 效应量/置换基线中位（C4 垫） |
| fdr_q | float/null | BH 合并族 m=86 下的 q 值（全纲领一张表，逐批补入） |
| ci95_low / ci95_high | float/null | stationary bootstrap 95% CI（超额或价差，notes 注明对象） |
| loto_pass / yearly_flip / lag_flip | bool/null | C5 稳健三件（LOTO 20 次 ≥19 / 分年 / lag1 重跑方向） |
| evidence_tag | str | `【实证】`/`【推断】`/`【合成段·低权重】` |
| anchor_ref | str | 复现锚坐标（如 `RESCUE_REPORT.md:L87 M1`）；无锚新格填 `new` |
| notes | str | 口径差异、数据受限、MAP-INVALID 等登记 |

规则：正负同权入册（MINE_SPEC §5.5-1）；每域行必须 n_days 与 CI 齐备才算「可用统计事实」（§5.5-2）；n_days<60 行 `note` 加 `INSUFFICIENT`。

---

## 八、判线引用声明（不重立）

- 六腿判线 C1–C6、生死/胜任判定、m=86 合并 FDR、双池同向、n<60 门、安慰剂 MAP-INVALID：**全部引用 MINE_SPEC_v1 §五，本方法书零新增判线数字**。
- 变体预算核对：Batch 1 覆盖 Q5（8）+Q6（6）+K1（12）+K3 brk 分域部分（1 格冻结臂重切，另行工单细化）= 本方法书先放行五活口变体组（c4 双持有 2 + c5 六变体 + d 降权 1 + d 换门 1 + S3×D1 交叉 6 = 16 格），余者按 MINE_SPEC §六批次计划推进，预算冻结不破。
- 每批收口：FDR 合并表更新 + FACTBOOK 增章 + 用户过目（MINE_SPEC §六批次纪律）。

---

*签名：交易分析团队（单 agent 10 席位）· 首席策略官何执舟终裁批准 · 2026-10-20 · 本文件为 wo_mine 工程唯一施工依据，与 MINE_SPEC_v1 冲突处以 MINE_SPEC 为上位法。*
