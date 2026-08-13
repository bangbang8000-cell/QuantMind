"""
TDX Rolling Trade Service - 按分数滚动买卖并推送到通达信（半自动）

规则（每日推理完成后执行一次）：
  1. 个股 fusion_score > SCORE_THRESHOLD（2.2）→ 买入候选
  2. 已持仓且最新分数 <= 2.2（或最新推理不再有该股）→ 卖出
  3. 已持仓且最新分数仍 > 2.2 → 持有不动
  4. 上证指数（000001.SH）收盘 < MA20 → 只卖不买（强制过滤）

半自动执行：只推通达信预警（可双击闪电下单），由用户手动确认成交。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text

from backend.shared.database_manager_v2 import get_session
from backend.shared.stock_utils import StockCodeUtil
from backend.services.trade.services.tdx_push_service import (
    TdxPushError,
    tdx_pusher,
)

logger = logging.getLogger(__name__)

# 默认分数阈值: fusion_score > 2.2 视为买入信号（可在设置页修改，存 Redis）
DEFAULT_SCORE_THRESHOLD = 2.2
# 默认每只股票固定买入金额（元）
DEFAULT_FIXED_BUY_AMOUNT = 10000.0
# 买入手数向下取整到 100 股
LOT_SIZE = 100
# 上证指数代码（QuantDB index_daily）
INDEX_SYMBOL = "000001.SH"
MA_WINDOW = 20
_MAX_SELL_WARNINGS = 20
_MAX_BUY_WARNINGS = 20

_ROLLING_CONFIG_KEY = "tdx:rolling_config:{tenant_id}:{user_id}"


def load_rolling_config(
    tenant_id: str,
    user_id: str,
) -> tuple[float, float, bool]:
    """读取滚动买卖配置 (score_threshold, fixed_buy_amount, auto_place)。

    优先读 Redis（设置页保存），未保存时用环境变量/默认值。
    auto_place: 是否把买卖信号生成为真实委托推给通达信（客户端弹确认框）。
    """
    threshold = _env_float("TDX_ROLLING_SCORE_THRESHOLD", DEFAULT_SCORE_THRESHOLD)
    amount = _env_float("TDX_ROLLING_FIXED_BUY_AMOUNT", DEFAULT_FIXED_BUY_AMOUNT)
    auto_place = _env_bool("TDX_ROLLING_AUTO_PLACE", False)
    try:
        from backend.services.trade.redis_client import get_redis

        saved = get_redis().get(_ROLLING_CONFIG_KEY.format(tenant_id=tenant_id, user_id=user_id))
        if isinstance(saved, dict):
            t = saved.get("score_threshold")
            a = saved.get("fixed_buy_amount")
            p = saved.get("auto_place")
            if isinstance(t, (int, float)) and 0 < float(t) <= 10:
                threshold = float(t)
            if isinstance(a, (int, float)) and float(a) > 0:
                amount = float(a)
            if isinstance(p, bool):
                auto_place = p
    except Exception as exc:
        logger.warning("[TdxRolling] 读取滚动配置失败，使用默认值: %s", exc)
    return threshold, amount, auto_place


def save_rolling_config(
    tenant_id: str,
    user_id: str,
    *,
    score_threshold: float,
    fixed_buy_amount: float,
    auto_place: bool = False,
) -> None:
    """保存滚动买卖配置到 Redis（设置页）。"""
    from backend.services.trade.redis_client import get_redis

    get_redis().set(
        _ROLLING_CONFIG_KEY.format(tenant_id=tenant_id, user_id=user_id),
        {
            "score_threshold": float(score_threshold),
            "fixed_buy_amount": float(fixed_buy_amount),
            "auto_place": bool(auto_place),
        },
    )


def _env_float(name: str, default: float) -> float:
    import os

    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    import os

    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _to_suffix(symbol: str) -> str:
    return StockCodeUtil.to_suffix(str(symbol or "").strip()) or str(symbol or "").strip()


class TdxRollingTradeService:
    """滚动买卖: 分数>2.2 买 / 掉下 2.2 卖 / 大盘低于 MA20 只卖不买。"""

    # ---------- 数据侧 ----------

    async def load_latest_scores(
        self,
        *,
        tenant_id: str,
        user_id: str,
        run_id: str | None = None,
        trade_date: str | None = None,
    ) -> tuple[str | None, dict[str, float], str | None]:
        """读取推理 run 的 symbol->fusion_score。

        优先 run_id；否则 trade_date 指定的预测日期（推历史分数）；都没有取最新。
        返回 (run_id, score_map, prediction_trade_date)。score_map 的 key 为
        suffix 格式（600519.SH）。
        """
        async with get_session(read_only=True) as db:
            prediction_trade_date: str | None = None
            if run_id:
                selected_run = run_id
                row = (
                    await db.execute(
                        text(
                            """
                            SELECT prediction_trade_date
                            FROM qm_model_inference_runs
                            WHERE run_id = :run_id LIMIT 1
                            """
                        ),
                        {"run_id": run_id},
                    )
                ).mappings().first()
                if row:
                    prediction_trade_date = str(row.get("prediction_trade_date") or "")
            else:
                query = """
                    SELECT run_id, prediction_trade_date::text AS prediction_trade_date
                    FROM qm_model_inference_runs
                    WHERE tenant_id = :tenant_id
                      AND user_id = :user_id
                      AND status = 'completed'
                """
                params: dict[str, Any] = {"tenant_id": tenant_id, "user_id": user_id}
                if trade_date:
                    query += " AND prediction_trade_date = :trade_date"
                    try:
                        params["trade_date"] = datetime.strptime(trade_date, "%Y-%m-%d").date()
                    except ValueError:
                        return None, {}, None
                query += " ORDER BY created_at DESC LIMIT 1"
                row = (
                    await db.execute(text(query), params)
                ).mappings().first()
                if not row:
                    return None, {}, None
                selected_run = str(row.get("run_id") or "").strip() or None
                prediction_trade_date = str(row.get("prediction_trade_date") or "")

            if not selected_run:
                return None, {}, None

            rows = (
                await db.execute(
                    text(
                        """
                        SELECT symbol, fusion_score
                        FROM engine_signal_scores
                        WHERE run_id = :run_id
                          AND tenant_id = :tenant_id
                          AND user_id = :user_id
                        """
                    ),
                    {"run_id": selected_run, "tenant_id": tenant_id, "user_id": user_id},
                )
            ).mappings().all()

            score_map: dict[str, float] = {}
            for r in rows:
                symbol = _to_suffix(str(r.get("symbol") or ""))
                score = r.get("fusion_score")
                if symbol and isinstance(score, (int, float)):
                    score_map[symbol] = float(score)

            return selected_run, score_map, prediction_trade_date

    async def load_positions_from_tdx(self) -> tuple[list[dict[str, Any]], str]:
        """从通达信桥拉取当前持仓。

        返回 (positions, error)。positions 元素包含 symbol(600519.SH)/
        name/volume/available_volume/cost_price/market_value。
        """
        try:
            positions = await tdx_pusher.pull_positions()
        except TdxPushError as exc:
            return [], f"通达信桥持仓拉取失败: {exc}"
        except Exception as exc:
            return [], f"通达信桥持仓拉取失败: {exc}"

        normalized: list[dict[str, Any]] = []
        for p in positions or []:
            raw = str(p.get("stock_code") or "").strip()
            if not raw:
                continue
            symbol = _to_suffix(raw)
            volume = int(float(p.get("total_volume") or p.get("volume") or 0))
            if volume <= 0:
                continue
            normalized.append(
                {
                    "symbol": symbol,
                    "name": str(p.get("stock_name") or "").strip(),
                    "volume": volume,
                    "available_volume": int(float(p.get("available_volume") or volume)),
                    "cost_price": float(p.get("cost_price") or 0),
                    "market_value": float(p.get("market_value") or 0),
                }
            )
        return normalized, ""

    async def is_index_above_ma20(self) -> tuple[bool, str]:
        """上证指数是否站上 MA20。

        返回 (above, detail)。数据缺失时返回 (False, 原因)，安全侧只卖不买。
        """
        try:
            from datetime import date as _date
            from datetime import timedelta

            from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

            hub = QuantDBDataHub()
            # 取近 60 个自然日数据，足够 MA20 且覆盖长假
            df = hub.fetch_index_kline(
                INDEX_SYMBOL,
                _date.today() - timedelta(days=90),
                _date.today(),
            )
            if df is None or df.empty:
                return False, "QuantDB 无上证指数数据"
            df = df.drop_duplicates(subset=["trade_date"], keep="last")
            close = df["close"].astype(float)
            if len(close) < MA_WINDOW:
                return False, f"指数数据不足 {MA_WINDOW} 日"
            latest = float(close.iloc[-1])
            ma20 = float(close.tail(MA_WINDOW).mean())
            return latest >= ma20, (
                f"上证 {latest:.2f} vs MA20 {ma20:.2f} ({'之上' if latest >= ma20 else '之下'})"
            )
        except Exception as exc:
            return False, f"指数检查失败: {exc}"

    # ---------- 信号计算 ----------

    def compute_rolling_signals(
        self,
        *,
        score_map: dict[str, float],
        positions: list[dict[str, Any]],
        index_above_ma20: bool,
        fixed_buy_amount: float = DEFAULT_FIXED_BUY_AMOUNT,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    ) -> dict[str, Any]:
        """计算滚动买卖信号。

        返回 {buys, sells, holds, market_detail}:
          buys: [{symbol,name,score,volume,close,reason}]
          sells: [{symbol,name,score,volume,reason}]
        """
        held = {p["symbol"]: p for p in positions}

        # 卖出: 持仓且 (最新分数 <= 阈值 或 最新推理无该股)
        sells: list[dict[str, Any]] = []
        holds: list[dict[str, Any]] = []
        for symbol, pos in held.items():
            score = score_map.get(symbol)
            if score is None or score <= score_threshold:
                sells.append(
                    {
                        "symbol": symbol,
                        "name": pos.get("name") or symbol,
                        "score": score,
                        "volume": pos["volume"],
                        "available_volume": pos["available_volume"],
                        "reason": (
                            f"最新分数低于{score_threshold}阈值"
                            if score is not None
                            else "最新推理已无该股"
                        ),
                    }
                )
            else:
                holds.append(
                    {
                        "symbol": symbol,
                        "name": pos.get("name") or symbol,
                        "score": score,
                        "volume": pos["volume"],
                    }
                )

        buys: list[dict[str, Any]] = []
        if index_above_ma20:
            # 买入候选: 分数 > 阈值 且未持仓，按分数降序
            candidates = sorted(
                (
                    (sym, score)
                    for sym, score in score_map.items()
                    if score > score_threshold and sym not in held
                ),
                key=lambda kv: kv[1],
                reverse=True,
            )
            close_map = _batch_last_close([sym for sym, _ in candidates])
            for sym, score in candidates:
                close = close_map.get(sym, 0.0)
                if close <= 0:
                    continue
                volume = int((fixed_buy_amount / close) // LOT_SIZE) * LOT_SIZE
                if volume < LOT_SIZE:
                    continue
                buys.append(
                    {
                        "symbol": sym,
                        "score": round(float(score), 4),
                        "volume": volume,
                        "close": round(close, 2),
                        "amount": round(volume * close, 2),
                        "reason": f"分数 {score:.2f} > {score_threshold}",
                    }
                )

        return {
            "buys": buys,
            "sells": sells,
            "holds": holds,
            "index_above_ma20": index_above_ma20,
            "score_threshold": score_threshold,
            "fixed_buy_amount": fixed_buy_amount,
        }

    # ---------- 推送 ----------

    # ---------- 真实下单 ----------

    async def place_rolling_orders(
        self,
        *,
        run_id: str,
        buys: list[dict[str, Any]],
        sells: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """把滚动买卖信号生成为真实委托推给通达信（客户端弹确认框）。

        卖单: 市价 + 可卖量（先卖）
        买单: 收盘价限价 + 整手数量
        返回 (placed_orders, failed_orders)。
        """
        placed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        async def _submit(item: dict[str, Any], side: str) -> None:
            if side == "sell":
                volume = int(item.get("available_volume") or 0)
                price: float | None = None
                price_type = 1  # 市价
            else:
                volume = int(item.get("volume") or 0)
                price = float(item.get("close") or 0)
                price_type = 0  # 限价
            if volume <= 0 or (side == "buy" and (price or 0) <= 0):
                failed.append({**item, "side": side, "error": "数量或价格无效"})
                return
            plan_id = f"rolling_{run_id}_{item['symbol']}_{side}"
            try:
                resp = await tdx_pusher.place_order(
                    stock_code=item["symbol"],
                    side=side,
                    volume=volume,
                    price=price,
                    price_type=price_type,
                    plan_id=plan_id,
                )
                # 桥返回 {plan_id, status, orders:[{stock_code,side,volume,status,order_id,message}]}
                first = (resp.get("orders") or [{}])[0] if isinstance(resp, dict) else {}
                order_status = str(first.get("status") or resp.get("status") or "unknown")
                if order_status in ("rejected", "error"):
                    failed.append(
                        {
                            **item,
                            "side": side,
                            "error": str(first.get("message") or resp.get("message") or "下单被拒"),
                        }
                    )
                else:
                    placed.append(
                        {
                            **item,
                            "side": side,
                            "order_id": str(first.get("order_id") or ""),
                            "status": order_status,
                            "message": str(first.get("message") or ""),
                        }
                    )
            except TdxPushError as exc:
                failed.append({**item, "side": side, "error": str(exc)})
            except Exception as exc:
                failed.append({**item, "side": side, "error": str(exc)})

        # 先卖后买
        for item in sells:
            await _submit(item, "sell")
        for item in buys:
            await _submit(item, "buy")
        return placed, failed

    async def run_rolling_push(
        self,
        *,
        tenant_id: str,
        user_id: str,
        run_id: str | None = None,
        trade_date: str | None = None,
        fixed_buy_amount: float | None = None,
        push_message: bool = True,
        check_index: bool = True,
    ) -> dict[str, Any]:
        """执行一次滚动买卖检查并把买卖信号推到通达信预警。

        返回 {success, run_id, market, buys, sells, holds, warnings, error}
        """
        if not tdx_pusher.enabled:
            return {
                "success": False,
                "error": "TDX_BRIDGE_URL/TOKEN 未配置",
                "buys": [],
                "sells": [],
            }

        score_threshold, saved_amount, auto_place = load_rolling_config(tenant_id, user_id)
        if fixed_buy_amount is None:
            fixed_buy_amount = saved_amount

        selected_run, score_map, prediction_trade_date = await self.load_latest_scores(
            tenant_id=tenant_id, user_id=user_id, run_id=run_id, trade_date=trade_date
        )
        if not selected_run or not score_map:
            return {
                "success": False,
                "error": (
                    f"没有可用的推理信号（日期 {trade_date}）"
                    if trade_date
                    else "没有可用的推理信号（检查 run_id 或最新推理是否完成）"
                ),
                "buys": [],
                "sells": [],
            }

        positions, pos_error = await self.load_positions_from_tdx()
        if pos_error:
            logger.warning("[TdxRolling] %s", pos_error)

        # 推历史分数时不再用当日大盘 MA20 过滤（历史日期应只看当天的信号）
        if check_index and not trade_date:
            index_above, market_detail = await self.is_index_above_ma20()
        else:
            index_above, market_detail = True, "历史日期推送: 跳过当日大盘过滤"

        signals = self.compute_rolling_signals(
            score_map=score_map,
            positions=positions,
            index_above_ma20=index_above,
            fixed_buy_amount=fixed_buy_amount,
            score_threshold=score_threshold,
        )

        buys = signals["buys"]
        sells = signals["sells"]

        # 补股票名
        need_names = [b["symbol"] for b in buys] + [s["symbol"] for s in sells]
        from backend.services.trade.services.tdx_signal_push_service import (
            _batch_lookup_names,
        )

        name_map = _batch_lookup_names(need_names)
        for item in buys:
            item["name"] = name_map.get(item["symbol"], "") or item["symbol"]
        for item in sells:
            if not item.get("name") or item["name"] == item["symbol"]:
                item["name"] = name_map.get(item["symbol"], "") or item["symbol"]

        warnings_total = 0
        results: dict[str, Any] = {}

        # 卖出预警
        if sells:
            sell_list = sells[:_MAX_SELL_WARNINGS]
            try:
                warn_signals = [
                    {
                        "symbol": s["symbol"],
                        "side": "sell",
                        "price": 0,
                        "close": 0,
                        "volume": s["available_volume"],
                        "reason": f"卖 {s['name']} {s['reason']}",
                    }
                    for s in sell_list
                ]
                resp = await tdx_pusher.push_warnings(warn_signals)
                warnings_total += len(sell_list)
                results["sell_warnings"] = {"success": True, "result": resp}
            except TdxPushError as exc:
                logger.warning("[TdxRolling] 卖出预警推送失败: %s", exc)
                results["sell_warnings"] = {"success": False, "error": str(exc)}

        # 买入预警
        if buys:
            buy_list = buys[:_MAX_BUY_WARNINGS]
            try:
                warn_signals = [
                    {
                        "symbol": b["symbol"],
                        "side": "buy",
                        "price": b["close"],
                        "close": b["close"],
                        "volume": b["volume"],
                        "reason": f"买 {b['name']} 分{b['score']} {b['volume']}股",
                    }
                    for b in buy_list
                ]
                resp = await tdx_pusher.push_warnings(warn_signals)
                warnings_total += len(buy_list)
                results["buy_warnings"] = {"success": True, "result": resp}
            except TdxPushError as exc:
                logger.warning("[TdxRolling] 买入预警推送失败: %s", exc)
                results["buy_warnings"] = {"success": False, "error": str(exc)}

        # 汇总消息
        if push_message:
            try:
                date_label = f"（{prediction_trade_date or selected_run}）"
                lines = [f"滚动检查{date_label}: 大盘 {market_detail}"]
                if not index_above and not trade_date:
                    lines.append("大盘低于MA20, 只卖不买")
                if sells:
                    lines.append(
                        "卖出: " + "|".join(f"{s['name']}({s['reason']})" for s in sells[:10])
                    )
                if buys:
                    lines.append(
                        "买入: " + "|".join(f"{b['name']}:{b['score']}" for b in buys[:10])
                    )
                if not sells and not buys:
                    lines.append("无买卖动作")
                await tdx_pusher.push_message("MSG,QuantMind 滚动买卖|" + "\n".join(lines))
                results["message"] = {"success": True}
            except TdxPushError as exc:
                logger.warning("[TdxRolling] 消息推送失败: %s", exc)
                results["message"] = {"success": False, "error": str(exc)}

        # 真实下单（可选, 通达信客户端弹确认框）—— 先卖后买
        placed_orders: list[dict[str, Any]] = []
        failed_orders: list[dict[str, Any]] = []
        if auto_place and (buys or sells):
            placed_orders, failed_orders = await self.place_rolling_orders(
                run_id=selected_run,
                buys=buys[:_MAX_BUY_WARNINGS],
                sells=sells[:_MAX_SELL_WARNINGS],
            )
            if placed_orders:
                results["orders"] = {"success": True, "placed": placed_orders}
            if failed_orders:
                results["orders_failed"] = {"success": False, "failed": failed_orders}

        logger.info(
            "[TdxRolling] run=%s buys=%d sells=%d holds=%d market=%s orders=%d/%d",
            selected_run,
            len(buys),
            len(sells),
            len(signals["holds"]),
            market_detail,
            len(placed_orders),
            len(placed_orders) + len(failed_orders),
        )
        return {
            "success": True,
            "run_id": selected_run,
            "prediction_trade_date": prediction_trade_date,
            "market": {
                "above_ma20": index_above,
                "detail": market_detail,
                "index_symbol": INDEX_SYMBOL,
                "ma_window": MA_WINDOW,
            },
            "score_threshold": score_threshold,
            "auto_place": auto_place,
            "positions_from_tdx": len(positions),
            "positions_error": pos_error,
            "buys": buys,
            "sells": sells,
            "holds": signals["holds"],
            "warnings": warnings_total,
            "placed_orders": placed_orders,
            "failed_orders": failed_orders,
            "results": results,
            "pushed_at": datetime.now().isoformat(timespec="seconds"),
        }


def _batch_last_close(symbols: list[str]) -> dict[str, float]:
    """批量从 QuantDB 取最近交易日收盘价（与模拟撮合同源）。"""
    result: dict[str, float] = {}
    if not symbols:
        return result
    try:
        from backend.services.trade.simulation.services.local_market_data import (
            LocalMarketData,
        )

        market_data = LocalMarketData()
        latest_date = market_data.latest_trade_date()
        if latest_date is None:
            return result
        for symbol in symbols:
            bar = market_data.get_bar(symbol, latest_date)
            if bar is not None and bar.close > 0:
                result[symbol] = float(bar.close)
    except Exception as exc:
        logger.warning("[TdxRolling] QuantDB 收盘价读取失败: %s", exc)
    return result


tdx_rolling_trader = TdxRollingTradeService()
