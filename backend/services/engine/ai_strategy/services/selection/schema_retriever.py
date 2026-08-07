import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from ...ai_strategy_config import get_config as _get_config
from .dashscope_client import DashScopeClient

ai_strategy_config = _get_config()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchemaColumn:
    table: str
    name: str
    description: str


TABLE_DESCRIPTIONS: dict[str, str] = {
    "stock_selection": "滚动近30天选股因子表，适合近期快速筛选与技术指标组合。",
    "stock_daily": "日线全量历史行情与估值表，适合长期/历史/风控/波动类筛选。",
    "stock_daily_latest": "最新交易日全市场快照表（每股一行），适合实时筛选与条件查询。",
}


STOCK_SELECTION_SCHEMA: list[SchemaColumn] = [
    SchemaColumn("stock_selection", "trade_date", "交易日期"),
    SchemaColumn("stock_selection", "symbol", "股票代码"),
    SchemaColumn("stock_selection", "name", "股票名称"),
    SchemaColumn("stock_selection", "close", "收盘价"),
    SchemaColumn("stock_selection", "market_cap", "总市值（亿元）"),
    SchemaColumn("stock_selection", "industry", "行业"),
    SchemaColumn("stock_selection", "pe_ratio", "市盈率 TTM"),
    SchemaColumn("stock_selection", "pb_ratio", "市净率"),
    SchemaColumn("stock_selection", "ps_ratio", "市销率"),
    SchemaColumn("stock_selection", "roe", "净资产收益率"),
    SchemaColumn("stock_selection", "net_profit_growth", "净利润增长率"),
    SchemaColumn("stock_selection", "volume", "成交量（手）"),
    SchemaColumn("stock_selection", "amount", "成交额（元）"),
    SchemaColumn("stock_selection", "turnover_rate", "换手率"),
    SchemaColumn("stock_selection", "pct_chg", "涨跌幅"),
    SchemaColumn("stock_selection", "float_share_ratio", "流通股占比"),
    SchemaColumn("stock_selection", "is_st", "是否 ST"),
    SchemaColumn("stock_selection", "is_suspended", "是否停牌"),
    SchemaColumn("stock_selection", "is_listed_over_1y", "上市是否超过一年"),
    SchemaColumn("stock_selection", "macd_dif", "MACD DIF"),
    SchemaColumn("stock_selection", "macd_dea", "MACD DEA"),
    SchemaColumn("stock_selection", "macd_hist", "MACD 柱"),
    SchemaColumn("stock_selection", "kdj_k", "KDJ K"),
    SchemaColumn("stock_selection", "kdj_d", "KDJ D"),
    SchemaColumn("stock_selection", "kdj_j", "KDJ J"),
    SchemaColumn("stock_selection", "sma5", "5日均线"),
    SchemaColumn("stock_selection", "sma20", "20日均线"),
    SchemaColumn("stock_selection", "sma60", "60日均线"),
    SchemaColumn("stock_selection", "rsi", "RSI"),
]


STOCK_DAILY_SCHEMA: list[SchemaColumn] = [
    SchemaColumn("stock_daily", "trade_date", "交易日期"),
    SchemaColumn("stock_daily", "symbol", "股票代码"),
    SchemaColumn("stock_daily", "name", "股票名称"),
    SchemaColumn("stock_daily", "open", "开盘价"),
    SchemaColumn("stock_daily", "high", "最高价"),
    SchemaColumn("stock_daily", "low", "最低价"),
    SchemaColumn("stock_daily", "close", "收盘价"),
    SchemaColumn("stock_daily", "volume", "成交量（手）"),
    SchemaColumn("stock_daily", "amount", "成交额（元）"),
    SchemaColumn("stock_daily", "pct_change", "涨跌幅"),
    SchemaColumn("stock_daily", "turnover_rate", "换手率"),
    SchemaColumn("stock_daily", "pe_ttm", "市盈率 TTM"),
    SchemaColumn("stock_daily", "pb", "市净率"),
    SchemaColumn("stock_daily", "total_mv", "总市值（亿元）"),
    SchemaColumn("stock_daily", "is_st", "是否 ST (1/0)"),
    SchemaColumn("stock_daily", "idx_hs300", "是否沪深300成分股 (1/0)"),
    SchemaColumn("stock_daily", "idx_zz1000", "是否中证1000成分股 (1/0)"),
]

STOCK_DAILY_LATEST_SCHEMA: list[SchemaColumn] = [
    # === 基础信息 (8个) ===
    SchemaColumn("stock_daily_latest", "trade_date", "交易日期"),
    SchemaColumn("stock_daily_latest", "symbol", "股票代码"),
    SchemaColumn("stock_daily_latest", "stock_name", "股票简称"),
    SchemaColumn("stock_daily_latest", "listed_days", "上市天数"),
    SchemaColumn("stock_daily_latest", "is_st", "是否ST股票 (0=正常, 1=ST/*ST)"),
    SchemaColumn("stock_daily_latest", "listing_market", "上市板块（主板/创业板/科创板）"),
    SchemaColumn("stock_daily_latest", "industry", "申万一级行业（如：银行、半导体、白酒）"),
    SchemaColumn("stock_daily_latest", "province", "所属省份"),

    # === 基础行情 (9个) ===
    SchemaColumn("stock_daily_latest", "open", "开盘价（元）"),
    SchemaColumn("stock_daily_latest", "high", "最高价（元）"),
    SchemaColumn("stock_daily_latest", "low", "最低价（元）"),
    SchemaColumn("stock_daily_latest", "close", "收盘价（元）"),
    SchemaColumn("stock_daily_latest", "volume", "成交量（股）"),
    SchemaColumn("stock_daily_latest", "amount", "成交额（元）"),
    SchemaColumn("stock_daily_latest", "pct_change", "涨跌幅（比率，0.05=5%）"),
    SchemaColumn("stock_daily_latest", "turnover_rate", "换手率（百分比）"),
    SchemaColumn("stock_daily_latest", "adj_factor", "复权因子"),

    # === 估值指标 (8个) ===
    SchemaColumn("stock_daily_latest", "pe_ttm", "动态市盈率（倍）"),
    SchemaColumn("stock_daily_latest", "pb", "市净率（倍）"),
    SchemaColumn("stock_daily_latest", "total_mv", "总市值（元）"),
    SchemaColumn("stock_daily_latest", "float_mv", "流通市值（元）"),
    SchemaColumn("stock_daily_latest", "bp", "账面市值比（1/PB）"),
    SchemaColumn("stock_daily_latest", "ep_ttm", "盈利收益率（1/PE）"),
    SchemaColumn("stock_daily_latest", "ln_mv_total", "总市值的对数"),
    SchemaColumn("stock_daily_latest", "roe", "净资产收益率ROE（百分比）"),

    # === 收益率序列 (6个) ===
    SchemaColumn("stock_daily_latest", "return_1d", "当日收益率"),
    SchemaColumn("stock_daily_latest", "return_3d", "近3日收益率"),
    SchemaColumn("stock_daily_latest", "return_5d", "近5日收益率"),
    SchemaColumn("stock_daily_latest", "return_10d", "近10日收益率"),
    SchemaColumn("stock_daily_latest", "return_20d", "近20日收益率"),
    SchemaColumn("stock_daily_latest", "return_60d", "近60日收益率"),

    # === 均线系统 (7个) ===
    SchemaColumn("stock_daily_latest", "ma5", "5日均线（元）"),
    SchemaColumn("stock_daily_latest", "ma10", "10日均线（元）"),
    SchemaColumn("stock_daily_latest", "ma20", "20日均线（元）"),
    SchemaColumn("stock_daily_latest", "ma60", "60日均线（元）"),
    SchemaColumn("stock_daily_latest", "ma_gap_5", "5日均线偏离度"),
    SchemaColumn("stock_daily_latest", "ma_gap_10", "10日均线偏离度"),
    SchemaColumn("stock_daily_latest", "ma_gap_20", "20日均线偏离度"),

    # === 技术指标 (9个) ===
    SchemaColumn("stock_daily_latest", "rsi_6", "RSI 6日指标（0-100）"),
    SchemaColumn("stock_daily_latest", "rsi_14", "RSI 14日指标（0-100）"),
    SchemaColumn("stock_daily_latest", "kdj_k", "KDJ K值（0-100）"),
    SchemaColumn("stock_daily_latest", "kdj_d", "KDJ D值（0-100）"),
    SchemaColumn("stock_daily_latest", "kdj_j", "KDJ J值（0-100）"),
    SchemaColumn("stock_daily_latest", "macd_dif", "MACD快线DIF"),
    SchemaColumn("stock_daily_latest", "macd_dea", "MACD慢线DEA"),
    SchemaColumn("stock_daily_latest", "macd_hist", "MACD柱状图"),
    SchemaColumn("stock_daily_latest", "beta_20", "20日贝塔系数"),

    # === 波动与量能 (10个) ===
    SchemaColumn("stock_daily_latest", "vol_std_5", "5日波动率"),
    SchemaColumn("stock_daily_latest", "vol_std_20", "20日波动率"),
    SchemaColumn("stock_daily_latest", "vol_std_60", "60日波动率"),
    SchemaColumn("stock_daily_latest", "vol_atr_14", "14日平均真实振幅ATR"),
    SchemaColumn("stock_daily_latest", "volume_ratio_5", "5日量比"),
    SchemaColumn("stock_daily_latest", "volume_ratio_20", "20日量比"),
    SchemaColumn("stock_daily_latest", "volume_ma_3", "3日平均成交量"),
    SchemaColumn("stock_daily_latest", "volume_ma_5", "5日平均成交量"),
    SchemaColumn("stock_daily_latest", "amount_ma_5", "5日平均成交额"),
    SchemaColumn("stock_daily_latest", "volume_trend_3d", "3日成交量趋势"),

    # === 行业概念与标签 (14个) ===
    SchemaColumn("stock_daily_latest", "ind_code_l1", "一级行业代码"),
    SchemaColumn("stock_daily_latest", "ind_code_l2", "二级行业代码"),
    SchemaColumn("stock_daily_latest", "label", "自动分类标签（0=周期,1=价值,2=成长,3=价值成长）"),
    SchemaColumn("stock_daily_latest", "concept_ai", "是否AI概念股（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_chip", "是否芯片概念股（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_new_energy", "是否新能源概念股（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_pv", "是否光伏概念股（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_military", "是否军工概念股（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_medical", "是否医药概念股（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_fintech", "是否金融科技概念股（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_consumption", "是否大消费概念股（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_state_owned", "是否国资委背景（0/1）"),
    SchemaColumn("stock_daily_latest", "concept_lithium", "是否锂电池概念股（0/1）"),

    # === 资金持仓流向 (7个) ===
    SchemaColumn("stock_daily_latest", "main_flow", "主力资金净流入（元）"),
    SchemaColumn("stock_daily_latest", "inst_ownership", "流通市值占比"),
    SchemaColumn("stock_daily_latest", "lrg_trd_tolbuynum", "大单买入笔数"),
    SchemaColumn("stock_daily_latest", "lrg_trd_tolsellnum", "大单卖出笔数"),
    SchemaColumn("stock_daily_latest", "flow_net_amount", "资金总净流入额（元）"),
    SchemaColumn("stock_daily_latest", "b_volume", "外盘主动买入量（股）"),
    SchemaColumn("stock_daily_latest", "s_volume", "内盘主动卖出量（股）"),

    # === 指数关联属性 (5个) ===
    SchemaColumn("stock_daily_latest", "idx_all", "全A股集合（1）"),
    SchemaColumn("stock_daily_latest", "idx_hs300", "沪深300成分股（0/1）"),
    SchemaColumn("stock_daily_latest", "idx_zz1000", "中证1000成分股（0/1）"),
    SchemaColumn("stock_daily_latest", "idx_margin", "融资融券标的（0/1）"),
    SchemaColumn("stock_daily_latest", "idx_chinext", "创业板指成分股（0/1）"),

    # === 市场微结构 (3个) ===
    SchemaColumn("stock_daily_latest", "micro_effective_spread", "有效价差"),
    SchemaColumn("stock_daily_latest", "micro_imbalance_volume", "指数订单不平衡量"),
    SchemaColumn("stock_daily_latest", "micro_jump_flag", "价格跳变标记（0/1）"),

    # === 特殊交易状态 (3个) ===
    SchemaColumn("stock_daily_latest", "consecutive_limit_up_days", "连板天数"),
    SchemaColumn("stock_daily_latest", "limit_up_today", "今日涨停（0/1）"),
    SchemaColumn("stock_daily_latest", "limit_down_today", "今日跌停（0/1）"),

    # === 其他核心财务 (1个) ===
    SchemaColumn("stock_daily_latest", "profit_growth", "净利润同比增长率"),
]

QUANTDB_TABLE_DESCRIPTIONS: dict[str, str] = {
    "quantdb_valuation": "QuantDB 估值指标日频数据（PS/股息率/静态PE/净资产等），从本地 parquet 实时读取。",
    "quantdb_sentiment": "QuantDB 市场情绪数据（流动性/买卖压力/动量/跳空/K线形态等），从本地 parquet 实时读取。",
    "quantdb_factors": "QuantDB L1 因子数据（筹码/行业/风格/技术/概念等 101 列），从本地 parquet 实时读取。",
    "quantdb_margin": "QuantDB 融资融券数据，从本地 parquet 实时读取。",
    "quantdb_technical": "QuantDB 技术指标数据（量比等扩展字段），从本地 parquet 实时读取。",
    "quantdb_financial": "QuantDB 财务报表核心筛选字段（利润表/资产负债表/现金流），从本地 parquet 实时读取。",
}

# Merge QuantDB descriptions into the main dict
TABLE_DESCRIPTIONS.update(QUANTDB_TABLE_DESCRIPTIONS)

QUANTDB_SCHEMA: list[SchemaColumn] = [
    # === 估值扩展 (8个) ===
    SchemaColumn("quantdb_valuation", "ps_ttm", "市销率PS(TTM)"),
    SchemaColumn("quantdb_valuation", "dividend_rate", "股息率(%)"),
    SchemaColumn("quantdb_valuation", "pe_static", "静态市盈率"),
    SchemaColumn("quantdb_valuation", "equity", "净资产(元)"),
    SchemaColumn("quantdb_valuation", "annual_net_profit", "年度净利润(元)"),
    SchemaColumn("quantdb_valuation", "revenue_ttm", "TTM营业收入(元)"),
    SchemaColumn("quantdb_valuation", "net_profit_ttm", "TTM净利润(元)"),
    SchemaColumn("quantdb_valuation", "total_capital", "总股本"),

    # === 市场情绪 (14个) ===
    SchemaColumn("quantdb_sentiment", "liquidity_score", "流动性评分(0-1)"),
    SchemaColumn("quantdb_sentiment", "buy_pressure", "买入压力"),
    SchemaColumn("quantdb_sentiment", "sell_pressure", "卖出压力"),
    SchemaColumn("quantdb_sentiment", "body_ratio", "K线实体比例"),
    SchemaColumn("quantdb_sentiment", "upper_shadow", "上影线长度"),
    SchemaColumn("quantdb_sentiment", "lower_shadow", "下影线长度"),
    SchemaColumn("quantdb_sentiment", "gap_up_down", "跳空幅度"),
    SchemaColumn("quantdb_sentiment", "momentum_1d", "1日动量"),
    SchemaColumn("quantdb_sentiment", "momentum_3d", "3日动量"),
    SchemaColumn("quantdb_sentiment", "price_range", "振幅(%)"),
    SchemaColumn("quantdb_sentiment", "intraday_vol", "日内波动率"),
    SchemaColumn("quantdb_sentiment", "volume_concentration", "成交量集中度"),
    SchemaColumn("quantdb_sentiment", "amount_per_trade", "每笔成交额(元)"),
    SchemaColumn("quantdb_sentiment", "am_pm_trend", "早盘/尾盘趋势"),

    # === 筹码分析 (8个) ===
    SchemaColumn("quantdb_factors", "chip_profit_ratio_20", "20日获利盘比例(%)"),
    SchemaColumn("quantdb_factors", "chip_profit_ratio_60", "60日获利盘比例(%)"),
    SchemaColumn("quantdb_factors", "chip_profit_ratio_120", "120日获利盘比例(%)"),
    SchemaColumn("quantdb_factors", "chip_floating_ratio", "浮动筹码比例(%)"),
    SchemaColumn("quantdb_factors", "chip_concentration_20", "20日筹码集中度"),
    SchemaColumn("quantdb_factors", "chip_cost_90_width", "90%成本带宽"),
    SchemaColumn("quantdb_factors", "chip_peak_distance", "筹码峰距"),
    SchemaColumn("quantdb_factors", "chip_profit_delta_5", "5日获利变化"),

    # === 行业因子 (11个) ===
    SchemaColumn("quantdb_factors", "ind_strength_20", "行业强度20日"),
    SchemaColumn("quantdb_factors", "ind_strength_60", "行业强度60日"),
    SchemaColumn("quantdb_factors", "ind_relative_momentum_20", "行业相对动量"),
    SchemaColumn("quantdb_factors", "ind_relative_pe", "行业相对PE"),
    SchemaColumn("quantdb_factors", "ind_netflow_rank_20", "行业资金流排名"),
    SchemaColumn("quantdb_factors", "ind_breadth_up_20", "行业广度(上涨比例)"),
    SchemaColumn("quantdb_factors", "ind_rotation_speed_20", "行业轮动速度"),
    SchemaColumn("quantdb_factors", "ind_crowding_20", "行业拥挤度"),
    SchemaColumn("quantdb_factors", "ind_dispersion_20", "行业离散度"),
    SchemaColumn("quantdb_factors", "ind_concentration", "行业集中度"),
    SchemaColumn("quantdb_factors", "ind_momentum_decay", "行业动量衰减"),

    # === 风格因子 (7个) ===
    SchemaColumn("quantdb_factors", "style_beta_20", "20日Beta系数"),
    SchemaColumn("quantdb_factors", "style_beta_60", "60日Beta系数"),
    SchemaColumn("quantdb_factors", "style_value_20", "价值因子暴露"),
    SchemaColumn("quantdb_factors", "style_size_20", "规模因子暴露"),
    SchemaColumn("quantdb_factors", "style_idio_vol_20", "20日特质波动率"),
    SchemaColumn("quantdb_factors", "style_idio_vol_60", "60日特质波动率"),
    SchemaColumn("quantdb_factors", "style_residual_ret_20", "20日残差收益"),

    # === 扩展技术 (5个) ===
    SchemaColumn("quantdb_factors", "tech_adx_14", "ADX趋势强度(14日)"),
    SchemaColumn("quantdb_factors", "tech_bb_pos", "布林带位置(0-1)"),
    SchemaColumn("quantdb_factors", "tech_bb_width", "布林带宽度"),
    SchemaColumn("quantdb_factors", "tech_cci_20", "CCI商品通道指数(20日)"),
    SchemaColumn("quantdb_factors", "tech_vol_price_corr_20", "20日量价相关性"),

    # === 概念因子 (10个) ===
    SchemaColumn("quantdb_factors", "concept_hot_score", "概念热度评分"),
    SchemaColumn("quantdb_factors", "concept_momentum_top3", "TOP3概念动量"),
    SchemaColumn("quantdb_factors", "concept_leader_score", "概念领导力评分"),
    SchemaColumn("quantdb_factors", "concept_rotation_score", "概念轮动评分"),
    SchemaColumn("quantdb_factors", "concept_crowding_max", "概念拥挤度"),
    SchemaColumn("quantdb_factors", "concept_diversity", "概念分散度"),
    SchemaColumn("quantdb_factors", "concept_flow_rank", "概念资金流排名"),
    SchemaColumn("quantdb_factors", "concept_exposure_top1", "TOP1概念暴露"),
    SchemaColumn("quantdb_factors", "concept_cross_sector", "跨板块概念"),
    SchemaColumn("quantdb_factors", "concept_volume_ratio", "概念量比"),

    # === 量能扩展 (4个) ===
    SchemaColumn("quantdb_factors", "liq_mfi_14", "MFI资金流量指数(14日)"),
    SchemaColumn("quantdb_factors", "liq_obv_20", "OBV能量潮(20日)"),
    SchemaColumn("quantdb_technical", "vol_to_ma5", "5日量比(相对均线)"),
    SchemaColumn("quantdb_technical", "vol_to_ma20", "20日量比(相对均线)"),

    # === 融资融券 (8个) ===
    SchemaColumn("quantdb_margin", "finance_balance", "融资余额(元)"),
    SchemaColumn("quantdb_margin", "slo_volume", "融券余量(股)"),
    SchemaColumn("quantdb_margin", "finance_buy", "融资买入额(元)"),
    SchemaColumn("quantdb_margin", "slo_sell_amount", "融券卖出额(元)"),
    SchemaColumn("quantdb_margin", "finance_repay", "融资偿还额(元)"),
    SchemaColumn("quantdb_margin", "slo_repay", "融券偿还额(元)"),
    SchemaColumn("quantdb_margin", "finance_net", "融资净买入(元)"),
    SchemaColumn("quantdb_margin", "slo_net", "融券净卖出(元)"),

    # === 财务指标(核心筛选字段) (20个) ===
    SchemaColumn("quantdb_financial", "revenue", "营业收入(元)"),
    SchemaColumn("quantdb_financial", "operating_revenue", "营业总收入(元)"),
    SchemaColumn("quantdb_financial", "net_profit_incl_min_int_inc", "净利润(元)"),
    SchemaColumn("quantdb_financial", "oper_profit", "营业利润(元)"),
    SchemaColumn("quantdb_financial", "research_expenses", "研发费用(元)"),
    SchemaColumn("quantdb_financial", "sale_expense", "销售费用(元)"),
    SchemaColumn("quantdb_financial", "s_fa_eps_basic", "基本每股收益"),
    SchemaColumn("quantdb_financial", "s_fa_eps_diluted", "稀释每股收益"),
    SchemaColumn("quantdb_financial", "tot_assets", "总资产(元)"),
    SchemaColumn("quantdb_financial", "tot_liab", "总负债(元)"),
    SchemaColumn("quantdb_financial", "total_equity", "所有者权益(元)"),
    SchemaColumn("quantdb_financial", "net_cash_flows_oper_act", "经营现金流净额(元)"),
    SchemaColumn("quantdb_financial", "goodwill", "商誉(元)"),
    SchemaColumn("quantdb_financial", "inventories", "存货(元)"),
    SchemaColumn("quantdb_financial", "account_receivable", "应收账款(元)"),
    SchemaColumn("quantdb_financial", "shortterm_loan", "短期借款(元)"),
    SchemaColumn("quantdb_financial", "long_term_loans", "长期借款(元)"),
    SchemaColumn("quantdb_financial", "inc_revenue_rate", "营收同比增长率(%)"),
    SchemaColumn("quantdb_financial", "inc_net_profit_rate", "净利润同比增长率(%)"),
    SchemaColumn("quantdb_financial", "sales_gross_profit", "销售毛利率(%)"),
]


SCHEMAS: dict[str, list[SchemaColumn]] = {
    "stock_selection": STOCK_SELECTION_SCHEMA,
    "stock_daily": STOCK_DAILY_SCHEMA,
    "stock_daily_latest": STOCK_DAILY_LATEST_SCHEMA,
    "quantdb_valuation": [c for c in QUANTDB_SCHEMA if c.table == "quantdb_valuation"],
    "quantdb_sentiment": [c for c in QUANTDB_SCHEMA if c.table == "quantdb_sentiment"],
    "quantdb_factors": [c for c in QUANTDB_SCHEMA if c.table == "quantdb_factors"],
    "quantdb_margin": [c for c in QUANTDB_SCHEMA if c.table == "quantdb_margin"],
    "quantdb_technical": [c for c in QUANTDB_SCHEMA if c.table == "quantdb_technical"],
    "quantdb_financial": [c for c in QUANTDB_SCHEMA if c.table == "quantdb_financial"],
}


def _cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


class SchemaRetriever:
    def __init__(self) -> None:
        self.client = DashScopeClient()
        self.model = ai_strategy_config.DASHSCOPE_EMBEDDING_MODEL
        self._column_vectors: dict[str, list[tuple[SchemaColumn, np.ndarray]]] = {}
        self._initialized = False

    def _embed(self, text: str) -> np.ndarray | None:
        try:
            resp = self.client.get_embedding(text, model=self.model)
            return np.array(resp["vector"])
        except Exception as exc:
            logger.error("Schema embedding failed: %s", exc)
            return None

    async def initialize(self) -> None:
        if self._initialized:
            return
        for table, columns in SCHEMAS.items():
            vectors: list[tuple[SchemaColumn, np.ndarray]] = []
            for col in columns:
                vec = self._embed(f"{col.name} {col.description}")
                if vec is not None:
                    vectors.append((col, vec))
            self._column_vectors[table] = vectors
        self._initialized = True

    def _heuristic_table_bias(self, query: str) -> dict[str, float]:
        q = query.lower()
        bias: dict[str, float] = {
            "stock_selection": 0.0,
            "stock_daily": 0.0,
            "stock_daily_latest": 0.0,
            "quantdb_valuation": 0.0,
            "quantdb_sentiment": 0.0,
            "quantdb_factors": 0.0,
            "quantdb_margin": 0.0,
            "quantdb_technical": 0.0,
            "quantdb_financial": 0.0,
        }
        if any(k in q for k in ["近30", "近期", "最近", "短期", "当日", "今日", "最新"]):
            bias["stock_daily_latest"] += 0.2
        if any(
            k in q
            for k in [
                "历史",
                "长期",
                "多年",
                "回撤",
                "波动",
                "beta",
                "atr",
                "boll",
                "stoch",
            ]
        ):
            bias["stock_daily"] += 0.15
        if any(k in q for k in ["全市场", "全量", "全部", "快照"]):
            bias["stock_daily_latest"] += 0.2
        # QuantDB heuristic biases
        if any(k in q for k in ["估值", "ps", "股息", "分红", "净资产", "市销"]):
            bias["quantdb_valuation"] += 0.25
        if any(k in q for k in ["情绪", "流动性", "买卖压力", "动量", "跳空", "k线形态", "日内"]):
            bias["quantdb_sentiment"] += 0.25
        if any(k in q for k in ["筹码", "因子", "行业强度", "风格", "概念", "布林", "adx", "cci"]):
            bias["quantdb_factors"] += 0.25
        if any(k in q for k in ["融资", "融券", "两融", "融资余额"]):
            bias["quantdb_margin"] += 0.25
        if any(k in q for k in ["量比", "技术指标", "obv", "mfi"]):
            bias["quantdb_technical"] += 0.25
        if any(k in q for k in ["财务", "利润", "营收", "现金流", "商誉", "每股收益", "毛利率"]):
            bias["quantdb_financial"] += 0.25
        return bias

    async def retrieve(self, query: str, top_k: int = 12) -> dict[str, object]:
        if not self._initialized:
            await self.initialize()

        query_vec = self._embed(query)
        if query_vec is None:
            return {
                "target_table": "quantdb_valuation",
                "table_scores": {
                    "quantdb_valuation": 0.0,
                    "quantdb_technical": 0.0,
                    "quantdb_sentiment": 0.0,
                    "quantdb_factors": 0.0,
                    "quantdb_margin": 0.0,
                },
                "candidate_fields": [],
                "allowed_fields": [c.name for c in QUANTDB_SCHEMA if c.table == "quantdb_valuation"],
            }

        table_scores: dict[str, float] = {}
        candidates: dict[str, list[tuple[SchemaColumn, float]]] = {}
        for table, vectors in self._column_vectors.items():
            sims: list[tuple[SchemaColumn, float]] = []
            for col, vec in vectors:
                sims.append((col, _cosine_similarity(query_vec, vec)))
            sims.sort(key=lambda x: x[1], reverse=True)
            candidates[table] = sims
            top_scores = [s for _, s in sims[: min(top_k, len(sims))]]
            table_scores[table] = float(np.mean(top_scores)) if top_scores else 0.0

        bias = self._heuristic_table_bias(query)
        for table, score in table_scores.items():
            table_scores[table] = score + bias.get(table, 0.0)

        # 根据查询内容选择最优表，默认优先使用 QuantDB valuation（最常用）
        best_table = None
        best_score = -1.0
        for table, score in table_scores.items():
            if score > best_score and table in SCHEMAS:
                best_score = score
                best_table = table

        # Default to quantdb_valuation if no table scores well or bias didn't help
        target_table = best_table if best_table and best_score > 0.1 else "quantdb_valuation"
        top_candidates = candidates.get(target_table, [])[:top_k]

        return {
            "target_table": target_table,
            "table_scores": table_scores,
            "candidate_fields": [
                {
                    "name": col.name,
                    "description": col.description,
                    "score": round(score, 4),
                    "table": col.table,
                }
                for col, score in top_candidates
            ],
            "allowed_fields": [c.name for c in SCHEMAS.get(target_table, [])],
        }


_retriever: SchemaRetriever | None = None


async def get_schema_retriever() -> SchemaRetriever:
    global _retriever
    if _retriever is None:
        _retriever = SchemaRetriever()
        await _retriever.initialize()
    return _retriever
