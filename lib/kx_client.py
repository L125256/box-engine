# -*- coding: utf-8 -*-
"""K线导演 (kxiandaoyan.com) 数据对接层

已验证接口（均免鉴权，2026-09 实测）：
  GET /api/signals?market=futures|spot&period=1d&page=1&size=500
      -> 211 个标的的信号面板（AI + 7类技术信号 x 3周期）
  GET /api/qqq_judge/latest        -> QQQ 大盘研判
  GET /api/etf_judge/list          -> A股 ETF 信号列表
  GET /api/kline/{symbol}?market=&period=&limit>=50  -> 单标的K线
"""
from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import io
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import requests
import requests.adapters

log = logging.getLogger("kx.client")

BASE_URL = "https://www.kxiandaoyan.com/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 站点信号字典：signal -> 中文名
SIGNAL_NAMES = {
    "vertex": "三角·实心(顶底)",
    "circle": "三角·圆圈",
    "signal": "买卖信号",
    "cci": "CCI背离",
    "haos": "Haos动能",
    "haos_strong": "Haos·强",
    "haos_weak": "Haos·弱",
    "dvvo": "DVVO-V动能反转",
    "ai": "AI信号",
}
PERIOD_NAMES = {"4h": "4小时", "1d": "日线", "1w": "周线"}
UNDERLYING_NAMES = {
    "EQUITY": "美股",
    "HK_EQUITY": "港股",
    "KR_EQUITY": "韩股",
    "CRYPTO": "虚拟币",
    "COMMODITY": "商品",
    "INDEX": "指数",
    "ETF": "ETF",
    "PREMARKET": "Pre-IPO",
}


class KxClient:
    """带重试的 API 客户端"""

    def __init__(self, base_url: str = BASE_URL, timeout: int = 10,
                 retries: int = 1, retry_delay: float = 1.0,
                 signal_age_days: float = 10, connect_timeout: int = 5):
        self.base = base_url.rstrip("/")
        # 【v3.3.25 超时治理】拆分「连接超时 / 读取超时」，并整体下调。
        #
        #   旧值 timeout=15 / retries=3 / retry_delay=2.0 在 141 标规模下的
        #   最坏单标耗时 = (15 + 2) + (15 + 4) + 15 = **51s**（实测 ADBEUSDT
        #   单标 38.46s 即此形态）。而任务总预算 900s 里，扫描本不该占这么重。
        #
        #   为什么敢把读超时从 15 降到 10：
        #     实测（19:40）健康请求延迟 0.6~0.8s、P99 约 3.9s，
        #     连 limit=2000 的深视窗请求也只要 2.0s。10s 已是健康值的 3 倍以上，
        #     真正撞到 10s 的请求基本就是「服务端卡住」，重试一次足矣。
        #   为什么连接超时单独设 5s 并**不参与长重试**：
        #     连不上的典型原因是本机出网抖动/对端拒连，快速失败立刻重连
        #     比干等 10s 划算得多。
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.retries = retries
        self.retry_delay = retry_delay
        # 【v3.3.8】箭头新鲜度窗口（天）：1d/4h 的箭头距现在超过它就**不认方向**
        #   （绝不回头看老箭头）。默认 10 = max_signal_age_days，两者口径必须一致。
        self.signal_age_days = float(signal_age_days or 10)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Referer": "https://www.kxiandaoyan.com/"})
        # 【v3.3.25 性能修正】连接池必须放大，否则多线程会**退化成串行握手**。
        #
        #   requests 默认 HTTPAdapter(pool_connections=10, pool_maxsize=10)。
        #   而 HTTPAdapter.send() 在 pool 满时会阻塞等待（默认
        #   block=False 时 pool 竟抛异常→被重试逻辑吃掉，更糟）。
        #   实测（2026-09-15 19:40）：141 标 / 8 线程扫描 82.3s，
        #   其中 TLS 握手占掉大半——**每建立一次新连接约 1.3s**，
        #   而 keep-alive 复用的请求只要 0.6~0.8s。
        #   16 线程能降到 40.5s 的另一半原因就是池子被撑大后复用率上升。
        #
        #   pool_maxsize 取 32：覆盖 workers=16 + 复查/核验/裁定等旁路并发，
        #   留一倍余量。pool_block=True 让超额请求排队复用连接，
        #   而不是新建连接或抛异常。
        _adapter = requests.adapters.HTTPAdapter(
            pool_connections=32, pool_maxsize=32, pool_block=True,
            max_retries=0,           # 重试由本类统一控制，避免与 urllib3 双重重试
        )
        self.session.mount("https://", _adapter)
        self.session.mount("http://", _adapter)


    # ------------------------------------------------------------------ #
    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base}{path}"
        # 连接超时 5s / 读取超时 self.timeout，元组形式交给 requests 分治
        _to = (self.connect_timeout, self.timeout)
        last_err: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                r = self.session.get(url, params=params, timeout=_to)
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa: BLE001 - 网络/JSON 异常统一重试
                last_err = e
                # 【v3.3.25】超时类错误不再做「阶梯退避」——
                #   读超时说明服务端已经卡了 self.timeout 秒，再叠加
                #   retry_delay*attempt 的纯等待只是让总耗时更糟；
                #   立刻重试（换连接命中不同后端实例）反而更容易成功。
                #   其它错误（5xx/连接重置/JSON 解码失败）仍保留退避。
                _is_timeout = isinstance(e, requests.exceptions.Timeout)
                _wait = 0.0 if _is_timeout else self.retry_delay * attempt
                log.warning("请求失败(%s/%s)%s %s: %s", attempt, self.retries,
                            "(超时·立即重试)" if _is_timeout else "", url, e)
                if attempt < self.retries:
                    if _wait:
                        time.sleep(_wait)
        raise ConnectionError(f"API 请求最终失败: {url} -> {last_err}")

    # ------------------------------------------------------------------ #
    # 信号面板（核心接口）
    # ------------------------------------------------------------------ #
    def get_signals(self, market: str = "futures", period: str = "1d",
                    page: int = 1, size: int = 500) -> dict:
        """拉取全部标的信号面板。

        market: "futures"(币安合约) / "spot"(币安现货)
        返回: {"market":..., "total":n, "items":[{symbol, name, latest_price,
               change_pct, ai_signal, ai_up, ai_down,
               {vertex,circle,signal,cci,haos,haos_strong,haos_weak,dvvo}_{4h,1d,1w}, ...}]}
        """
        if market not in ("futures", "spot"):
            raise ValueError("market 仅支持 futures / spot")
        return self._get("/signals", {
            "market": market, "period": period,
            "page": page, "size": size, "sort": "symbol", "order": "asc",
        })

    # ------------------------------------------------------------------ #
    def get_qqq_judge(self) -> dict:
        """QQQ(纳指100) 最新大盘研判: side/combo/atr/rv60/rv240/pos60/heads..."""
        return self._get("/qqq_judge/latest")

    # ------------------------------------------------------------------ #
    def get_etf_judge(self) -> dict:
        """A股 ETF 信号列表: [{code, name, verdict, side, combo, sr30_choice, event_bj}]"""
        return self._get("/etf_judge/list")

    # ------------------------------------------------------------------ #
    def get_kline(self, symbol: str, market: str = "futures",
                  period: str = "1d", limit: int = 300) -> dict:
        """单标的 K 线 + 各指标信号（limit >= 50）。单源直连：导演，失败直接抛。"""
        r = self._get(f"/kline/{symbol}", {
            "market": market, "period": period, "limit": max(50, limit),
        })
        return r


    # ------------------------------------------------------------------ #


    # ------------------------------------------------------------------ #
    def get_status(self) -> dict:
        """数据源状态（供日志/快照上报，引擎零改动）。"""
        return {"source": "director", "degraded": False, "fail_count": 0}

    # ------------------------------------------------------------------ #


    def get_lucky_signal(self, symbol: str, market: str = "futures",
                         limit: int = 300,
                         ignore_unclosed: bool = False) -> dict:
        """获取标的在 4h/1d/1w 三个周期的 Lucky 买卖信号最新方向。

        ignore_unclosed=True 时，丢弃落在「最后一根尚未收盘的K线」上的箭头：
        该 bar 的收盘价仍在变动，箭头会随价格生灭（URNM 09-13 20:00 的4h买箭头
        就是此类：盘中冒出、收盘后被服务端撤销）。只对 4h/1d 生效（1w 一周一根，
        过滤代价过大，永不启用）。

        返回 {"4h": "buy|sell|none", "1d": ..., "1w": ..., "detail": {...},
              "vertex": {"4h": "buy|sell|", ...}}
        判定规则（v3.3.8 起）：**只收集新鲜箭头**——遍历时凡是超过新鲜度
        窗口的老箭头一律 `continue` 丢弃，既不参与方向判定、也不进 detail。
        新鲜箭头一个都没有 → 该周期判 `none`（绝不"回头看"老箭头）。

        【v3.3.29 新增 vertex 通道】顺手从**同一份** /api/kline 响应里摘出
        vertex.peaks（页面上的蓝色圆圈 = 顶点/底点标记），供「4h 蓝圈止盈预警」使用。
        ⚠️ **不新增任何 HTTP 请求**（vertex 与 signals 同响应）。
        ⚠️ **不筛 confirmed** —— confirmed 是滞后翻牌（通常要等 1~2 根 4h K 线），
           而止盈预警必须及时，等确认就晚了。取「时间最新的那个 peak」的 side。
        ⚠️ 该字段**不参与任何既有判定**（方向/共振/冻结全都不看它），
           纯粹是旁路信息，服务端不返回时取 "" 自动静默，绝不影响主流程。
        """
        result = {"detail": {}, "_ok": {}, "vertex": {}}
        for period in ("4h", "1d", "1w"):
            try:
                data = self.get_kline(symbol, market, period, limit)
            except Exception as e:  # noqa: BLE001
                log.warning("获取 %s %s K线失败: %s", symbol, period, e)
                result[period] = "none"
                result["_ok"][period] = False
                continue

            bars = data.get("bars") or []
            sig = data.get("signals") or {}
            # 【v3.2.4】limit=300 的 K 线不该是空的。空 = 限流/接口异常，
            # 此时"没有箭头"是假的。用 _ok 标记，让调用方把它和
            # 「真的没信号」区分开（否则一次限流会被当成全市场信号消失）。
            result["_ok"][period] = bool(bars)
            bar_times = {b["time"] for b in bars}

            # 未收盘bar的时间标识：4h 用原始时间戳，1d 用 UTC 日期字符串
            # （日线箭头 time 是 "YYYY-MM-DD"，bar time 是 UTC 午夜时间戳）
            drop_t = None
            if ignore_unclosed and period in ("4h", "1d") and bars:
                last_t = bars[-1]["time"]
                if period == "1d" and isinstance(last_t, (int, float)):
                    drop_t = datetime.utcfromtimestamp(float(last_t)).strftime("%Y-%m-%d")
                else:
                    drop_t = last_t

            # ──────────────────────────────────────────────────────────
            # 【v3.3.8】物理删除「回头看」—— 不再有"回退到老箭头"这种东西
            #
            #   用户口径（2026-09-15，第 N 次强调）：
            #     「不要看7月3号的箭头，不要往回头看。既然已有硬性标准+新鲜度门控
            #      +防抖冻结，回退到老箭头是毫无意义的错误逻辑，直接删。」
            #
            #   旧逻辑 = 「取可见范围内时间最新的箭头」。新鲜箭头一消失
            #   （HDUSDT buy@2026-09-13 重绘），它就**回退到 74 天前的老 sell**
            #   当"当前方向" → 判出与事实相反的"日线翻卖出" → 标的被判"不同向"
            #   掉出 hits → 冻结分支够不到 → 静默成僵尸。
            #
            #   现在：向外遍历箭头时，**只收集新鲜箭头**，老箭头连"不认"都不必说
            #   —— 它们根本不会进入方向判定。周期级别的方向**只能**来自新鲜箭头；
            #   新鲜箭头不存在（或全部消失）→ 该周期就是 none。
            #
            #   尺度：复用新鲜度门控的 max_signal_age_days（默认 10 天），
            #        不另造参数。1w **无时间限制**（与 config 口径一致）。
            #
            #   箭头消失后的正确链路（用户要的）：
            #     该周期 none → 与在册读数不同 → 触发防抖 → 防抖裁定
            #     （冻结走「冻结期照常推送」；确认到点走「放行/解除并提醒」）。
            # ──────────────────────────────────────────────────────────
            _age_win = float(self.signal_age_days or 10)
            _now_ts = time.time()

            def _fresh(key) -> bool:
                """箭头是否新鲜：1w 恒 True；1d/4h 必须在 max_signal_age 内。"""
                if period == "1w":
                    return True
                _ts = None
                if isinstance(key, (int, float)):
                    _ts = float(key)
                elif isinstance(key, str):
                    try:
                        _ts = datetime.strptime(key[:10],
                                                "%Y-%m-%d").replace(
                            tzinfo=timezone.utc).timestamp()
                    except (ValueError, TypeError):
                        _ts = None
                if _ts is None:
                    return False
                return (_now_ts - _ts) <= _age_win * 86400

            latest_t, latest_dir = None, "none"
            detail = {"buy": [], "sell": []}
            for direction in ("buy", "sell"):
                for item in sig.get(direction) or []:
                    t = item.get("time")
                    if isinstance(t, str):      # 日线/周线用日期字符串
                        key = t
                    elif t in bar_times:
                        key = t
                    else:
                        continue                 # 超出K线范围，页面上也不显示
                    if drop_t is not None and key == drop_t:
                        continue                 # 未收盘bar上的箭头，等收盘后再认
                    # 不新鲜 → **直接丢弃**（不进判定、不进 detail、无从回退）
                    if not _fresh(key):
                        continue
                    detail[direction].append({"time": key,
                                              "price": item.get("price")})
                    if latest_t is None or str(key) > str(latest_t):
                        latest_t, latest_dir = key, direction

            # 无新鲜箭头 → 该周期判 none（这是唯一合法结论，绝不回退老箭头）
            result[period] = latest_dir
            result["detail"][period] = {"latest": latest_dir, "time": latest_t,
                                        **detail}

            # ──────────────────────────────────────────────────────────
            # 【v3.3.29】vertex（蓝色圆圈 = 顶点/底点标记）旁路采集
            #
            #   为什么要它：用户 2026-09-18 复盘发现「三周期共振卖出期间，
            #   4h 一旦出现蓝色圆圈，价格基本就反转了」→ 需要一条止盈预警。
            #   而蓝色圆圈就是 vertex 引擎的 peaks，页面用它渲染圆圈。
            #
            #   口径（用户 16:25 拍板）：
            #     · **不筛 confirmed** —— 实测 MU/LITE 那些用户亲眼看到的圈
            #       全是 confirmed=False；筛了它们一个都推不出来。
            #       confirmed 是滞后翻牌（要等 1~2 根 4h K 线），止盈等不起。
            #     · 取「**时间最新的那个 peak**」的 side（不看 confirmed）。
            #     · 只认 BUY/SELL 两个值，其余（如空 peaks）记 ""。
            #
            #   安全性：
            #     · 与 signals 同一份响应，**零额外请求**；
            #     · 只写 result["vertex"][period]，**不碰任何既有返回字段**，
            #       方向/共振/冻结逻辑完全看不到它；
            #     · 整个块用 try 包住，任何结构异常都退化为 ""，
            #       绝不让旁路信息拖垮主扫描。
            # ──────────────────────────────────────────────────────────
            _v_side = ""
            try:
                _v = data.get("vertex") or {}
                _peaks = _v.get("peaks") or []
                _best_t = None
                for _pk in _peaks:
                    if not isinstance(_pk, dict):
                        continue
                    _sd = str(_pk.get("side") or "").strip().lower()
                    if _sd not in ("buy", "sell"):
                        continue
                    _pt = _pk.get("time")
                    # 时间取最新；时间缺失也接受（保留最后一个可用 peak）
                    if _pt is None:
                        if not _v_side:
                            _v_side = _sd
                        continue
                    if _best_t is None or str(_pt) > str(_best_t):
                        _best_t, _v_side = _pt, _sd
                result["vertex"][period] = _v_side
                # ★ 原始 peaks 一并带出，供 monitor 取「该圈的时间戳」。
                #   必须与上面算 _v_side **同源同序**（同一份 _peaks 同一个循环
                #   口径），否则会出现「side 取 buy、时间却取到另一个 peak」的错配。
                result.setdefault("_vertex_peaks", {})[period] = _peaks
            except Exception as e:  # noqa: BLE001
                log.warning("解析 %s %s vertex 失败: %s", symbol, period, e)
                result["vertex"][period] = ""
        return result

    # ------------------------------------------------------------------ #
    def scan_lucky_resonance(self, symbols: list, market: str = "futures",
                             limit: int = 300, direction: str = "any",
                             ignore_unclosed: bool = False) -> list:
        """扫描一批标的三周期 Lucky 买卖信号共振。

        direction: "buy"/"sell"/"any"
        返回 [{symbol, name, direction, detail}]，detail 含各周期箭头明细。
        """
        hits = []
        for sym in symbols:
            try:
                r = self.get_lucky_signal(sym, market, limit, ignore_unclosed)
            except Exception as e:  # noqa: BLE001
                log.warning("扫描 %s 失败: %s", sym, e)
                continue
            d4, d1, dw = r["4h"], r["1d"], r["1w"]
            if d4 == d1 == dw and d4 in ("buy", "sell"):
                if direction == "any" or d4 == direction:
                    hits.append({"symbol": sym, "direction": d4,
                                 "detail": r["detail"]})
        return hits


def iter_signal_fields() -> list[str]:
    """返回全部 7类信号 x 3周期 的字段名，供规则校验/遍历"""
    fields = []
    for p in ("4h", "1d", "1w"):
        for s in ("vertex", "circle", "signal", "cci", "haos",
                  "haos_strong", "haos_weak", "dvvo"):
            fields.append(f"{s}_{p}")
    return fields
