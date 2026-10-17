# 📦 箱体引擎状态页（本机权威引擎复刻版）

复刻 [原版状态页](https://llng125256.github.io/kx-combo/status/box.html) 同款风格（GitHub Dark 卡片式 UI），数据改由本机权威引擎 `eng_final.py`（WT-A 仲裁权威基线 v1.0，V2 可实现口径 + 清洗 144 标的池）每日自动计算生成。

## 文件清单

| 文件 | 说明 |
|---|---|
| `index.html` | 状态页（自包含：CSS 内嵌、无外链依赖，fetch 同目录 `box_live.json`） |
| `box_live.json` | 引擎输出数据（原版 box-live.txt 同结构 + 扩展字段 `seed/caliber/pool/runs`） |
| `generate_page.py` | 一键生成器：32线程刷缓存 → 跑引擎（冻结基线 N20/k6.0/m2/e0.2 + Top1 N15/k7.5/m2/e0.3 两组）→ 渲染 HTML+JSON，幂等 |
| `README.md` | 本说明 |

## 每日自动刷新（本机）

```bash
PYTHONHASHSEED=42 python3 generate_page.py
```

流程：复用 `/tmp/wtc/refresh_cache.py` 逻辑 32 线程拉最新日线（失败保留旧缓存）→ import 本机权威引擎 `/tmp/eng_wt_rc/eng_final.py`（只复用不修改）→ 影子状态机输出当前箱体卡片（与引擎交易键集合全量断言一致）→ 抽样独立复核 top/bot → 渲染并覆盖本目录 `index.html` / `box_live.json`。

配合 cron 每日收盘后运行（示例）：

```cron
30 21 * * 1-5  cd /workspace/box_web && PYTHONHASHSEED=42 python3 generate_page.py >> /tmp/box_web_cron.log 2>&1
```

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

本机每日跑完 `generate_page.py` 后 `git commit + push` 即可，页面 fetch `box_live.json?ts=时间戳` 不缓存，刷新即最新。

## 口径与诚实声明

- 触发：V1 收盘判定（`close<=eff / close>=tp / hold>=30`，信号序列零改动）
- 成交：V2 可实现价（止损 `min(eff,open)`、止盈 `max(tp,open)`、30bar 硬顶 `close`；须落在当根 `[low,high]` 否则顺延下一根 open）
- 资金费 0.03%/bar；池 = 清洗后 bars≥100 的 144 标的；牛市闸 = 池等权 idx > MA50；主窗 et ≥ 2025-06-01
- **幸存者偏差 ≥+9pp 高估，收益务必打折看待**；剔除池贝塔后无独立超额；仓位与买卖决策请勿仅依赖本页。
- `seed=42` 固定随机种子（引擎本身确定性，种子用于保证任何辅助随机过程可复现）。
