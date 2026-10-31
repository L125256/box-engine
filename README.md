> 五套美股代币永续策略（v2.1、HF-1、批量点火、FD-1、P6）的代码、规则、回测与交接文档见 [SYSTEMS.md](SYSTEMS.md)。本 README 下半部分描述的是早期箱体引擎，保留作历史。

# 📦 箱体引擎状态页（本机权威引擎复刻版）

复刻 [原版状态页](https://llng125256.github.io/kx-combo/status/box.html) 同款风格（GitHub Dark 卡片式 UI），数据改由本机权威引擎 `eng_final.py`（WT-A 仲裁权威基线 v1.0，V2 可实现口径 + 清洗 144 标的池）每日自动计算生成。

## 文件清单

| 文件 | 说明 |
|---|---|
| `index.html` | 状态页（自包含：CSS 内嵌、无外链依赖，fetch 同目录 `box_live.json`） |
| `box_live.json` | 引擎输出数据（原版 box-live.txt 同结构 + 扩展字段 `seed/caliber/pool/runs`） |
| `generate_page.py` | 一键生成器：32线程刷缓存 → 跑引擎（冻结基线 N20/k6.0/m2/e0.2 + Top1 N15/k7.5/m2/e0.3 两组）→ 渲染 HTML+JSON，幂等 |
| `README.md` | 本说明 |

## 自动化架构（GitHub Actions 四轮接管，2026-10-18 起）

每日刷新由 `.github/workflows/daily_refresh.yml` 承接（本机 cron 已退役）。四轮时间表：

| 北京时间 | UTC cron | 轮次 | 动作 |
|---|---|---|---|
| 20:30 | `30 12 * * *` | 快照轮 | `f1_signal.py snapshot`：只读盘中快照（禁写状态、禁出 top5），更新 `f1/f1_live_intraday.json` |
| 00:30 | `30 16 * * *` | 快照轮 | 同上（round 00:30） |
| 04:30 | `30 20 * * *` | 快照轮 | 同上（round 04:30） |
| 08:30 | `30 0 * * *` | 判定轮 | `f1_signal.py live`：完整日K、写 `f1_state.json`、出 top5、熔断判定 + `generate_page.py` 箱体页 |

- 北京 = UTC+8，无夏令时（DST），偏移全年恒定。
- 快照轮只读：不写 `f1_state.json`、不覆盖 `f1_live.json` 判定字段、不做调仓决策。
- 美股休市日（周末/假日）快照轮拉不到新盘中数据属**正常**，生成器退回最近落定 K 并标注 `intraday=False`。
- 手动触发：Actions → Run workflow，`mode` ∈ {snapshot, decision, auto}（auto=按当前 UTC 就近判定）。
- `f1_state.json` / `f1_source_state.json` 随 git 提交：状态机跨轮续命（CI 每轮取上一轮状态）。
- 数据源容灾状态机（f1_datasource.py 主备源 + 降级冻结）在判定轮内自动运行，事件见 `f1_source_events.log`（不入库）。
- 详细设计与演进记录见晨报 id 12762479。

### 失败报警（三层）

1. **job 失败邮件**：任何步骤失败 → GitHub 默认向仓库 watcher/作者发失败通知邮件；
2. **push 重试后显式失败**：push 失败重试 3 次（间隔 60s），三连败步骤显式 `exit 1` 触发第 1 层；
3. **金丝雀验证**：手动触发时 `fail_test=true`，最后一步故意 `exit 1` —— 一次性验证失败邮件能真发出（平时恒跳过）。

### 手动复现（调试用）

```bash
PYTHONHASHSEED=42 BOX_CACHE_DIR=/tmp/box_cache python3 research/wtc/refresh_cache.py   # 拉行情
PYTHONHASHSEED=42 F1_CACHE=/tmp/box_cache python3 f1/f1_signal.py live --out f1/f1_live.json
PYTHONHASHSEED=42 BOX_CACHE_DIR=/tmp/box_cache python3 generate_page.py                # 箱体页
```

路径均可用环境变量覆盖（`F1_CACHE`/`F1_POOL`/`F1_OUT_JSON`/`BOX_CACHE_DIR`/`BOX_POOL`/`BOX_ENG_DIR` 等），缺省值即仓库内基线（`engine_snapshot/`），全新机器 clone + `pip install -r requirements.txt` 即可跑通。

## GitHub Pages 部署步骤

1. 在 GitHub 建一个**公开仓库**（如 `box-web`），不要初始化 README。
2. 推送本目录（或已初始化好的 `/workspace/repo_ready/`）：

   ```bash
   cd repo_ready
   git remote add origin https://github.com/<username>/box-web.git
   git push -u origin main
   ```

3. 仓库页 → Settings → Pages → Source 选 `Deploy from a branch`，Branch 选 `main` / `(root)` → Save。
4. 1-2 分钟后固定地址生效，规则为：

   ```
   https://<username>.github.io/<reponame>/
   ```

   即本页为 `https://<username>.github.io/box-web/`（index.html 在仓库根目录即可，无需 Jekyll）。

## 更新线上数据

由 GitHub Actions 四轮自动 `commit + push`（见「自动化架构」）；本机人工调试跑完后同样 `git commit + push` 即可，页面 fetch `box_live.json?ts=时间戳` 不缓存，刷新即最新。

## 口径与诚实声明

- 触发：V1 收盘判定（`close<=eff / close>=tp / hold>=30`，信号序列零改动）
- 成交：V2 可实现价（止损 `min(eff,open)`、止盈 `max(tp,open)`、30bar 硬顶 `close`；须落在当根 `[low,high]` 否则顺延下一根 open）
- 资金费 0.03%/bar；池 = 清洗后 bars≥100 的 144 标的；牛市闸 = 池等权 idx > MA50；主窗 et ≥ 2025-06-01
- **幸存者偏差 ≥+9pp 高估，收益务必打折看待**；剔除池贝塔后无独立超额；仓位与买卖决策请勿仅依赖本页。
- `seed=42` 固定随机种子（引擎本身确定性，种子用于保证任何辅助随机过程可复现）。
