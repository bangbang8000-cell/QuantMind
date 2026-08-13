"""
模拟交易页面

根据首页全局 session_state.trading_mode 切换数据源:
  SIMULATION → 模拟盘 (/api/v1/simulation/*)
  REAL       → 实盘通达信桥 (/api/v1/real-trading/* → TdxBroker)
统一展示: 账户KPI / 策略启停 / 手动执行 / 下单 / 委托持仓
"""

import os
from datetime import date

import pandas as pd
import streamlit as st

from services.trade_api import (
    TRADE_SERVICE_URL,
    cancel_simulation_order,
    create_simulation_order,
    get_real_account,
    get_real_orders,
    get_simulation_account,
    get_strategy_status,
    list_executions,
    list_signals,
    list_simulation_orders,
    login,
    preview_execution,
    start_strategy,
    stop_strategy,
    submit_execution,
)

st.set_page_config(page_title="模拟交易 - QuantMind", layout="wide", page_icon="💰")

st.title("💰 模拟交易")
st.caption("模拟盘 · 通达信实盘桥 · 统一交易管理")

# 读取全局模式
trading_mode = st.session_state.get("trading_mode", "SIMULATION")
is_real = trading_mode == "REAL"
mode_label = "实盘(通达信)" if is_real else "模拟盘"
st.info(f"当前交易模式: **{mode_label}** (首页侧边栏切换)")

# ============ 侧边栏: 登录 + 模式信息 ============
with st.sidebar:
    st.subheader("登录")
    api_url = st.text_input("API 网关地址",
                            value=os.getenv("API_GATEWAY_URL", "http://127.0.0.1:8000"))
    tenant_id = st.text_input("租户ID", value="default")
    username = st.text_input("用户名", value="admin")
    password = st.text_input("密码", value="", type="password")
    if st.button("🔑 登录", type="primary", use_container_width=True):
        token = login(api_url, tenant_id, username, password)
        if token:
            st.session_state["access_token"] = token
            st.success("登录成功")
        else:
            st.error("登录失败")

    st.divider()
    st.caption(f"模式: {mode_label}")
    if is_real:
        st.caption(f"桥: {os.getenv('TDX_BRIDGE_URL', 'http://192.168.31.39:8550')}")
        st.caption("实盘下单需通达信客户端确认")

    if st.button("🔄 刷新", use_container_width=True):
        st.rerun()

token = st.session_state.get("access_token")
if not token:
    st.warning("请先在侧边栏登录")

# ============ 账户 KPI ============
st.subheader("账户概览")
col_kpi = st.columns(4)

if is_real:
    real_acct = get_real_account(token) if token else {"error": "未登录"}
    if "error" in real_acct:
        st.warning(f"实盘账户: {real_acct['error']}")
    asset = {k: real_acct.get(k) for k in ("cash", "asset", "market_value", "balance")} if "error" not in real_acct else {}
    cash = float(asset.get("cash", 0) or 0)
    total = float(asset.get("asset", 0) or 0)
    market_value = float(asset.get("market_value", 0) or 0)
    balance = float(asset.get("balance", 0) or 0)
    col_kpi[0].metric("可用资金", f"¥{cash:,.2f}")
    col_kpi[1].metric("总资产", f"¥{total:,.2f}")
    col_kpi[2].metric("持仓市值", f"¥{market_value:,.2f}")
    col_kpi[3].metric("余额", f"¥{balance:,.2f}")
    positions = real_acct.get("positions", []) if "error" not in real_acct else []
else:
    sim_acct = get_simulation_account(token) if token else {}
    cash = float(sim_acct.get("cash", 0) or 0)
    total = float(sim_acct.get("total_asset", 0) or 0)
    market_value = float(sim_acct.get("market_value", 0) or 0)
    equity = float(sim_acct.get("initial_equity", 0) or 0)
    pnl = total - equity if equity else 0.0
    col_kpi[0].metric("可用资金", f"¥{cash:,.2f}")
    col_kpi[1].metric("总资产", f"¥{total:,.2f}")
    col_kpi[2].metric("持仓市值", f"¥{market_value:,.2f}")
    col_kpi[3].metric("总盈亏", f"¥{pnl:,.2f}", delta=f"{pnl/equity:.2%}" if equity else None)
    positions = sim_acct.get("positions", {})

st.divider()

# ============ 策略启停 ============
st.subheader("策略启停")
col_ctrl = st.columns([2, 2, 1])
with col_ctrl[0]:
    strategy_id = st.text_input("策略ID", value="", help="留空用默认策略")
with col_ctrl[1]:
    c1, c2 = st.columns(2)
    if c1.button("▶️ 启动策略", use_container_width=True):
        result = start_strategy(token, trading_mode=trading_mode, strategy_id=strategy_id)
        if result["success"]:
            st.success(result["message"])
        else:
            st.error(result["message"])
    if c2.button("⏹ 停止策略", use_container_width=True):
        result = stop_strategy(token)
        if result["success"]:
            st.success(result["message"])
        else:
            st.error(result["message"])

if token:
    status = get_strategy_status(token)
    if not status.get("error"):
        st.caption(f"运行状态: {status.get('run_status', status.get('mode', '未知'))}")

st.divider()

# ============ 手动执行 (信号→预案→提交) ============
st.subheader("手动执行")
with st.expander("从推理信号构建调仓预案", expanded=False):
    signals = list_signals(token) if token else []
    if not signals:
        st.info("暂无最近推理信号")
    else:
        sig_df = pd.DataFrame(signals)[["run_id", "symbol", "side", "score"]].drop_duplicates(
            "run_id") if signals else pd.DataFrame()
        if sig_df.empty:
            st.info("信号数据格式待适配")
        else:
            run_choice = st.selectbox("选择推理批次", sig_df["run_id"].tolist())
            sel_run = sig_df[sig_df["run_id"] == run_choice].iloc[0]
            st.caption(f"信号数: {len(signals)} · 模型批次: {run_choice}")
            if st.button("📋 预览预案", use_container_width=True):
                prev = preview_execution(token, model_id="", run_id=str(run_choice),
                                         strategy_id=strategy_id or "default",
                                         trading_mode=trading_mode)
                if prev["success"]:
                    st.session_state["preview"] = prev["data"]
                    st.success("预案已生成, 请核对后提交")
                else:
                    st.error(prev["message"])

    preview = st.session_state.get("preview")
    if preview:
        st.markdown("#### 预案摘要")
        summary = preview.get("summary", {})
        c = st.columns(4)
        c[0].metric("卖出数", summary.get("sell_order_count", 0))
        c[1].metric("买入数", summary.get("buy_order_count", 0))
        c[2].metric("卖出金额", f"¥{summary.get('estimated_sell_proceeds', 0):,.0f}")
        c[3].metric("买入金额", f"¥{summary.get('estimated_buy_amount', 0):,.0f}")

        sell_rows = [{"代码": o.get("symbol"), "方向": "卖", "数量": o.get("quantity"),
                      "参考价": o.get("reference_price"), "原因": o.get("reason")}
                     for o in preview.get("sell_orders", [])]
        buy_rows = [{"代码": o.get("symbol"), "方向": "买", "数量": o.get("quantity"),
                     "参考价": o.get("reference_price"), "原因": o.get("reason")}
                    for o in preview.get("buy_orders", [])]
        if sell_rows:
            st.markdown("**卖出**")
            st.dataframe(pd.DataFrame(sell_rows), use_container_width=True, hide_index=True)
        if buy_rows:
            st.markdown("**买入**")
            st.dataframe(pd.DataFrame(buy_rows), use_container_width=True, hide_index=True)

        if st.button("🚀 提交执行", type="primary"):
            run_id = preview.get("strategy_context", {}).get("run_id", "")
            submit = submit_execution(token,
                                      model_id="",
                                      run_id=str(run_id),
                                      strategy_id=strategy_id or "default",
                                      trading_mode=trading_mode,
                                      preview_hash=preview.get("preview_hash", ""))
            if submit["success"]:
                st.success(submit["message"])
                st.session_state.pop("preview", None)
            else:
                st.error(submit["message"])

st.divider()

# ============ 快速下单 ============
st.subheader("快速下单")
col_order = st.columns([2, 2, 1])
with col_order[0]:
    symbol = st.text_input("股票代码", value="600519", help="如 600519 / 600519.SH")
with col_order[1]:
    side = st.selectbox("买卖方向", ["买入", "卖出"])
with col_order[2]:
    order_type = st.selectbox("价格类型", ["限价", "市价"])

col_price = st.columns([2, 2, 1])
with col_price[0]:
    quantity = st.number_input("数量(股)", min_value=100, step=100, value=100)
with col_price[1]:
    price = st.number_input("价格", min_value=0.0, step=0.01, value=0.0,
                            disabled=(order_type == "市价"))
with col_price[2]:
    st.write("")
    st.write("")
    submit_order = st.button("🚀 下单", type="primary", use_container_width=True)

if submit_order:
    if not symbol.strip():
        st.error("请输入股票代码")
    elif not token:
        st.error("请先登录")
    elif is_real:
        # 实盘: 走 manual-execution 简单单 (需 run_id, 简化直接提示)
        st.warning("实盘快速下单需通过手动执行流程, 请用上方'从推理信号构建调仓预案'")
    else:
        result = create_simulation_order(token, symbol.strip(), side, order_type,
                                         quantity, price if price > 0 else None)
        if result["success"]:
            st.success(result["message"])
        else:
            st.error(result["message"])

st.divider()

# ============ 持仓 ============
st.subheader("持仓")
if is_real:
    if isinstance(positions, list) and positions:
        rows = [{
            "代码": p.get("symbol") or p.get("stock_code", ""),
            "数量": p.get("quantity") or p.get("total_volume", 0),
            "可用": p.get("available_volume", 0),
            "成本": p.get("cost") or p.get("cost_price", 0),
            "市值": p.get("market_value", 0),
        } for p in positions]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("暂无持仓")
else:
    if isinstance(positions, dict) and positions:
        rows = [{
            "代码": sym,
            "数量": p.get("volume", 0),
            "可用": p.get("available_volume", 0),
            "成本价": p.get("cost", 0),
            "现价": p.get("price", 0),
            "市值": p.get("market_value", 0),
        } for sym, p in positions.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("暂无持仓")

st.divider()

# ============ 委托记录 ============
st.subheader("委托记录")
if is_real:
    real_orders = get_real_orders(token) if token else {"orders": [], "error": "未登录"}
    if real_orders.get("error"):
        st.info(f"实盘委托: {real_orders['error']}")
    elif real_orders.get("orders"):
        rows = [{
            "委托号": o.get("order_id", "") or o.get("exchange_order_id", ""),
            "代码": o.get("symbol", "") or o.get("stock_code", ""),
            "方向": o.get("side", ""),
            "数量": o.get("quantity", 0) or o.get("total_volume", 0),
            "委托价": o.get("price", 0) or o.get("order_price", 0),
            "成交价": o.get("average_price", 0) or o.get("filled_price", 0),
            "状态": o.get("status", ""),
        } for o in real_orders["orders"]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("暂无实盘委托")
else:
    sim_orders = list_simulation_orders(token) if token else []
    if sim_orders:
        rows = [{
            "委托号": str(o.get("order_id", "")),
            "代码": o.get("symbol", ""),
            "方向": "买" if str(o.get("side", "")).upper() == "BUY" else "卖",
            "类型": o.get("order_type", ""),
            "数量": o.get("quantity", 0),
            "委托价": o.get("price") or o.get("average_price") or 0,
            "状态": o.get("status", ""),
            "成交价": o.get("average_price") or 0,
            "成交数": o.get("filled_quantity", 0),
        } for o in sim_orders]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("暂无委托")

st.divider()

# ============ 执行任务列表 ============
if token:
    st.subheader("执行任务")
    tasks = list_executions(token)
    if tasks:
        rows = [{
            "任务号": t.get("task_id", ""),
            "类型": t.get("task_type", ""),
            "模式": t.get("trading_mode", ""),
            "状态": t.get("status", ""),
            "创建时间": t.get("created_at", ""),
        } for t in tasks[:20]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("暂无执行任务")
