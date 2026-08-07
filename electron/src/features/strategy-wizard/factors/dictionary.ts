export const FACTOR_DICTIONARY_VERSION = '2.0.0';

export const FACTORS: Array<{ key: string; label: string; category: string; unit?: string }> = [
  // ============ 估值因子 ============
  { key: 'market_cap', label: '总市值', category: '估值因子', unit: '亿' },
  { key: 'float_mv', label: '流通市值', category: '估值因子', unit: '亿' },
  { key: 'pe', label: '市盈率PE(TTM)', category: '估值因子' },
  { key: 'pb', label: '市净率PB', category: '估值因子' },
  { key: 'roe', label: '净资产收益率ROE', category: '估值因子', unit: '%' },
  { key: 'main_flow', label: '主力资金净流入', category: '资金流向', unit: '元' },
  { key: 'flow_net_amount', label: '资金净流入总额', category: '资金流向', unit: '元' },

  // ============ 价格因子 ============
  { key: 'close', label: '收盘价', category: '价格因子', unit: '元' },
  { key: 'pct_change', label: '当日涨跌幅', category: '价格因子', unit: '%' },
  { key: 'turnover_rate', label: '换手率', category: '价格因子', unit: '%' },

  // ============ 均线因子 ============
  { key: 'ma5', label: '5日均线', category: '均线因子', unit: '元' },
  { key: 'ma10', label: '10日均线', category: '均线因子', unit: '元' },
  { key: 'ma20', label: '20日均线', category: '均线因子', unit: '元' },
  { key: 'ma60', label: '60日均线', category: '均线因子', unit: '元' },
  { key: 'ma_gap_5', label: '5日均线偏离度', category: '均线因子', unit: '%' },
  { key: 'ma_gap_10', label: '10日均线偏离度', category: '均线因子', unit: '%' },
  { key: 'ma_gap_20', label: '20日均线偏离度', category: '均线因子', unit: '%' },

  // ============ 技术指标 ============
  { key: 'rsi_6', label: 'RSI(6)', category: '技术指标' },
  { key: 'rsi_14', label: 'RSI(14)', category: '技术指标' },
  { key: 'kdj_k', label: 'KDJ-K值', category: '技术指标' },
  { key: 'kdj_d', label: 'KDJ-D值', category: '技术指标' },
  { key: 'kdj_j', label: 'KDJ-J值', category: '技术指标' },
  { key: 'macd_dif', label: 'MACD-DIF', category: '技术指标' },
  { key: 'macd_dea', label: 'MACD-DEA', category: '技术指标' },
  { key: 'macd_hist', label: 'MACD柱', category: '技术指标' },

  // ============ 收益率因子 ============
  { key: 'return_1d', label: '近1日收益率', category: '收益率因子', unit: '%' },
  { key: 'return_3d', label: '近3日收益率', category: '收益率因子', unit: '%' },
  { key: 'return_5d', label: '近5日收益率', category: '收益率因子', unit: '%' },
  { key: 'return_10d', label: '近10日收益率', category: '收益率因子', unit: '%' },
  { key: 'return_20d', label: '近20日收益率', category: '收益率因子', unit: '%' },
  { key: 'return_60d', label: '近60日收益率', category: '收益率因子', unit: '%' },

  // ============ 波动率因子 ============
  { key: 'vol_std_5', label: '5日波动率', category: '波动率因子', unit: '%' },
  { key: 'vol_std_20', label: '20日波动率', category: '波动率因子', unit: '%' },
  { key: 'vol_std_60', label: '60日波动率', category: '波动率因子', unit: '%' },
  { key: 'vol_atr_14', label: '14日ATR', category: '波动率因子' },
  { key: 'beta_20', label: '20日Beta', category: '波动率因子' },

  // ============ 量能因子 ============
  { key: 'volume', label: '成交量', category: '量能因子' },
  { key: 'amount', label: '成交额', category: '量能因子', unit: '亿' },
  { key: 'volume_ratio_5', label: '5日量比', category: '量能因子' },
  { key: 'volume_ratio_20', label: '20日量比', category: '量能因子' },
  { key: 'volume_ma_5', label: '5日均量', category: '量能因子' },

  // ============ 指数成分 ============
  { key: 'idx_hs300', label: '沪深300成分', category: '指数成分' },
  { key: 'idx_zz500', label: '中证500成分', category: '指数成分' },
  { key: 'idx_zz1000', label: '中证1000成分', category: '指数成分' },
  { key: 'idx_chinext', label: '创业板指成分', category: '指数成分' },
  { key: 'idx_margin', label: '融资融券标的', category: '指数成分' },

  // ============ 概念标签 ============
  { key: 'concept_ai', label: 'AI概念', category: '概念标签' },
  { key: 'concept_chip', label: '芯片概念', category: '概念标签' },
  { key: 'concept_new_energy', label: '新能源概念', category: '概念标签' },
  { key: 'concept_ev', label: '电动车概念', category: '概念标签' },
  { key: 'concept_pv', label: '光伏概念', category: '概念标签' },
  { key: 'concept_lithium', label: '锂电概念', category: '概念标签' },
  { key: 'concept_semiconductor', label: '半导体概念', category: '概念标签' },
  { key: 'concept_military', label: '军工概念', category: '概念标签' },
  { key: 'concept_medical', label: '医药概念', category: '概念标签' },
  { key: 'concept_cyber', label: '网络安全概念', category: '概念标签' },
  { key: 'concept_fintech', label: '金融科技概念', category: '概念标签' },
  { key: 'concept_consumption', label: '消费概念', category: '概念标签' },
  { key: 'concept_real_estate', label: '地产概念', category: '概念标签' },
  { key: 'concept_infrastructure', label: '基建概念', category: '概念标签' },
  { key: 'concept_state_owned', label: '国企改革概念', category: '概念标签' },

  // ============ 其他因子 ============
  { key: 'is_st', label: 'ST标记', category: '其他' },
  { key: 'listed_days', label: '上市天数', category: '其他' },
  { key: 'limit_up_today', label: '当日涨停', category: '其他' },
  { key: 'limit_down_today', label: '当日跌停', category: '其他' },
  { key: 'consecutive_limit_up_days', label: '连续涨停天数', category: '其他' },
  { key: 'volume_trend_3d', label: '3日量能增强', category: '其他' },
  { key: 'industry', label: '所属行业', category: '其他' },
  { key: 'listing_market', label: '上市板块', category: '其他' },

  // ============ 估值因子扩展 ============
  { key: 'ps_ttm', label: '市销率PS(TTM)', category: '估值因子' },
  { key: 'dividend_rate', label: '股息率', category: '估值因子', unit: '%' },
  { key: 'pe_static', label: '静态市盈率', category: '估值因子' },
  { key: 'equity', label: '净资产', category: '估值因子', unit: '亿' },
  { key: 'annual_net_profit', label: '年度净利润', category: '估值因子', unit: '亿' },
  { key: 'revenue_ttm', label: 'TTM营业收入', category: '估值因子', unit: '亿' },
  { key: 'net_profit_ttm', label: 'TTM净利润', category: '估值因子', unit: '亿' },
  { key: 'total_capital', label: '总股本', category: '估值因子', unit: '万股' },

  // ============ 市场情绪 ============
  { key: 'liquidity_score', label: '流动性评分', category: '市场情绪' },
  { key: 'buy_pressure', label: '买入压力', category: '市场情绪' },
  { key: 'sell_pressure', label: '卖出压力', category: '市场情绪' },
  { key: 'body_ratio', label: 'K线实体比例', category: '市场情绪' },
  { key: 'upper_shadow', label: '上影线', category: '市场情绪' },
  { key: 'lower_shadow', label: '下影线', category: '市场情绪' },
  { key: 'gap_up_down', label: '跳空幅度', category: '市场情绪' },
  { key: 'momentum_1d', label: '1日动量', category: '市场情绪' },
  { key: 'momentum_3d', label: '3日动量', category: '市场情绪' },
  { key: 'price_range', label: '振幅', category: '市场情绪', unit: '%' },
  { key: 'intraday_vol', label: '日内波动率', category: '市场情绪' },
  { key: 'volume_concentration', label: '成交量集中度', category: '市场情绪' },
  { key: 'amount_per_trade', label: '每笔成交额', category: '市场情绪', unit: '万' },
  { key: 'am_pm_trend', label: '早盘/尾盘趋势', category: '市场情绪' },

  // ============ 筹码分析 ============
  { key: 'chip_profit_ratio_20', label: '20日获利盘比例', category: '筹码分析', unit: '%' },
  { key: 'chip_profit_ratio_60', label: '60日获利盘比例', category: '筹码分析', unit: '%' },
  { key: 'chip_profit_ratio_120', label: '120日获利盘比例', category: '筹码分析', unit: '%' },
  { key: 'chip_floating_ratio', label: '浮动筹码比例', category: '筹码分析', unit: '%' },
  { key: 'chip_concentration_20', label: '20日筹码集中度', category: '筹码分析' },
  { key: 'chip_cost_90_width', label: '90%成本带宽', category: '筹码分析' },
  { key: 'chip_peak_distance', label: '筹码峰距', category: '筹码分析' },
  { key: 'chip_profit_delta_5', label: '5日获利变化', category: '筹码分析' },

  // ============ 行业因子 ============
  { key: 'ind_strength_20', label: '行业强度20日', category: '行业因子' },
  { key: 'ind_strength_60', label: '行业强度60日', category: '行业因子' },
  { key: 'ind_relative_momentum_20', label: '行业相对动量', category: '行业因子' },
  { key: 'ind_relative_pe', label: '行业相对PE', category: '行业因子' },
  { key: 'ind_netflow_rank_20', label: '行业资金流排名', category: '行业因子' },
  { key: 'ind_breadth_up_20', label: '行业广度', category: '行业因子' },
  { key: 'ind_rotation_speed_20', label: '行业轮动速度', category: '行业因子' },
  { key: 'ind_crowding_20', label: '行业拥挤度', category: '行业因子' },
  { key: 'ind_dispersion_20', label: '行业离散度', category: '行业因子' },
  { key: 'ind_concentration', label: '行业集中度', category: '行业因子' },
  { key: 'ind_momentum_decay', label: '行业动量衰减', category: '行业因子' },

  // ============ 风格因子 ============
  { key: 'style_beta_20', label: '20日Beta', category: '风格因子' },
  { key: 'style_beta_60', label: '60日Beta', category: '风格因子' },
  { key: 'style_value_20', label: '价值因子暴露', category: '风格因子' },
  { key: 'style_size_20', label: '规模因子暴露', category: '风格因子' },
  { key: 'style_idio_vol_20', label: '20日特质波动', category: '风格因子' },
  { key: 'style_idio_vol_60', label: '60日特质波动', category: '风格因子' },
  { key: 'style_residual_ret_20', label: '20日残差收益', category: '风格因子' },

  // ============ 扩展技术 ============
  { key: 'tech_adx_14', label: 'ADX趋势强度', category: '扩展技术' },
  { key: 'tech_bb_pos', label: '布林带位置', category: '扩展技术' },
  { key: 'tech_bb_width', label: '布林带宽度', category: '扩展技术' },
  { key: 'tech_cci_20', label: 'CCI通道指数', category: '扩展技术' },
  { key: 'tech_vol_price_corr_20', label: '量价相关性', category: '扩展技术' },

  // ============ 概念因子 ============
  { key: 'concept_hot_score', label: '概念热度', category: '概念因子' },
  { key: 'concept_momentum_top3', label: 'TOP3概念动量', category: '概念因子' },
  { key: 'concept_leader_score', label: '概念领导力', category: '概念因子' },
  { key: 'concept_rotation_score', label: '概念轮动', category: '概念因子' },
  { key: 'concept_crowding_max', label: '概念拥挤度', category: '概念因子' },
  { key: 'concept_diversity', label: '概念分散度', category: '概念因子' },
  { key: 'concept_flow_rank', label: '概念资金流排名', category: '概念因子' },
  { key: 'concept_exposure_top1', label: 'TOP1概念暴露', category: '概念因子' },
  { key: 'concept_cross_sector', label: '跨板块概念', category: '概念因子' },
  { key: 'concept_volume_ratio', label: '概念量比', category: '概念因子' },

  // ============ 量能因子扩展 ============
  { key: 'liq_mfi_14', label: 'MFI资金流量', category: '量能因子' },
  { key: 'liq_obv_20', label: 'OBV能量潮', category: '量能因子' },
  { key: 'vol_to_ma5', label: '5日量比(均线)', category: '量能因子' },
  { key: 'vol_to_ma20', label: '20日量比(均线)', category: '量能因子' },

  // ============ 融资融券 ============
  { key: 'finance_balance', label: '融资余额', category: '融资融券', unit: '亿' },
  { key: 'slo_volume', label: '融券余量', category: '融资融券', unit: '万股' },
  { key: 'finance_buy', label: '融资买入额', category: '融资融券', unit: '亿' },
  { key: 'slo_sell_amount', label: '融券卖出额', category: '融资融券', unit: '亿' },
  { key: 'finance_repay', label: '融资偿还额', category: '融资融券', unit: '亿' },
  { key: 'slo_repay', label: '融券偿还额', category: '融资融券', unit: '亿' },
  { key: 'finance_net', label: '融资净买入', category: '融资融券', unit: '亿' },
  { key: 'slo_net', label: '融券净卖出', category: '融资融券', unit: '亿' },

  // ============ 财务指标 ============
  { key: 'revenue', label: '营业收入', category: '财务指标', unit: '亿' },
  { key: 'operating_revenue', label: '营业总收入', category: '财务指标', unit: '亿' },
  { key: 'net_profit_incl_min_int_inc', label: '净利润', category: '财务指标', unit: '亿' },
  { key: 'oper_profit', label: '营业利润', category: '财务指标', unit: '亿' },
  { key: 'research_expenses', label: '研发费用', category: '财务指标', unit: '亿' },
  { key: 'sale_expense', label: '销售费用', category: '财务指标', unit: '亿' },
  { key: 's_fa_eps_basic', label: '基本每股收益', category: '财务指标' },
  { key: 's_fa_eps_diluted', label: '稀释每股收益', category: '财务指标' },
  { key: 'tot_assets', label: '总资产', category: '财务指标', unit: '亿' },
  { key: 'tot_liab', label: '总负债', category: '财务指标', unit: '亿' },
  { key: 'total_equity', label: '所有者权益', category: '财务指标', unit: '亿' },
  { key: 'net_cash_flows_oper_act', label: '经营现金流净额', category: '财务指标', unit: '亿' },
  { key: 'goodwill', label: '商誉', category: '财务指标', unit: '亿' },
  { key: 'inventories', label: '存货', category: '财务指标', unit: '亿' },
  { key: 'account_receivable', label: '应收账款', category: '财务指标', unit: '亿' },
  { key: 'shortterm_loan', label: '短期借款', category: '财务指标', unit: '亿' },
  { key: 'long_term_loans', label: '长期借款', category: '财务指标', unit: '亿' },
  { key: 'inc_revenue_rate', label: '营收同比增长率', category: '财务指标', unit: '%' },
  { key: 'inc_net_profit_rate', label: '净利润增长率', category: '财务指标', unit: '%' },
  { key: 'sales_gross_profit', label: '销售毛利率', category: '财务指标', unit: '%' },
];

// 因子同义词映射（用于自然语言解析）
export const SYNONYMS: Record<string, string> = {
  // 估值
  市值: 'market_cap',
  总市值: 'market_cap',
  流通市值: 'float_mv',
  PE: 'pe',
  PE_TTM: 'pe',
  市盈率: 'pe',
  PB: 'pb',
  市净率: 'pb',
  ROE: 'roe',
  净资产收益率: 'roe',

  // 价格
  收盘价: 'close',
  涨跌幅: 'pct_change',
  涨跌: 'pct_change',
  换手率: 'turnover_rate',

  // 均线
  MA5: 'ma5',
  MA10: 'ma10',
  MA20: 'ma20',
  MA60: 'ma60',
  五日线: 'ma5',
  十日线: 'ma10',
  二十日线: 'ma20',
  六十日线: 'ma60',

  // 技术指标
  RSI: 'rsi_14',
  RSI6: 'rsi_6',
  RSI14: 'rsi_14',
  KDJ: 'kdj_k',
  MACD: 'macd_hist',

  // 收益率
  一日收益: 'return_1d',
  三日收益: 'return_3d',
  五日收益: 'return_5d',
  六十日收益: 'return_60d',
  近期收益: 'return_5d',

  // 波动率
  波动率: 'vol_std_20',
  二十日波动率: 'vol_std_20',
  六十日波动率: 'vol_std_60',
  ATR: 'vol_atr_14',
  Beta: 'beta_20',

  // 量能
  成交量: 'volume',
  成交额: 'amount',
  量比: 'volume_ratio_5',

  // 指数
  沪深300: 'idx_hs300',
  中证500: 'idx_zz500',
  中证1000: 'idx_zz1000',
  创业板: 'idx_chinext',
  创业板指: 'idx_chinext',
  两融: 'idx_margin',
  融资融券: 'idx_margin',

  // 概念
  AI: 'concept_ai',
  人工智能: 'concept_ai',
  芯片: 'concept_chip',
  新能源: 'concept_new_energy',
  电动车: 'concept_ev',
  光伏: 'concept_pv',
  锂电: 'concept_lithium',
  半导体: 'concept_semiconductor',
  军工: 'concept_military',
  医药: 'concept_medical',
  网络安全: 'concept_cyber',
  金融科技: 'concept_fintech',
  消费: 'concept_consumption',
  地产: 'concept_real_estate',
  基建: 'concept_infrastructure',
  国企: 'concept_state_owned',

  // 其他
  ST: 'is_st',
  涨停: 'limit_up_today',
  跌停: 'limit_down_today',
  量能增强: 'volume_trend_3d',
  三日量能增强: 'volume_trend_3d',
  行业: 'industry',
  所属行业: 'industry',
  板块: 'listing_market',
  上市板块: 'listing_market',

  // 估值扩展
  市销率: 'ps_ttm',
  PS: 'ps_ttm',
  股息率: 'dividend_rate',
  分红率: 'dividend_rate',
  静态PE: 'pe_static',

  // 市场情绪
  流动性: 'liquidity_score',
  流动性评分: 'liquidity_score',
  买入压力: 'buy_pressure',
  买压: 'buy_pressure',
  卖出压力: 'sell_pressure',
  卖压: 'sell_pressure',
  实体比例: 'body_ratio',
  上影线: 'upper_shadow',
  下影线: 'lower_shadow',
  跳空: 'gap_up_down',
  动量: 'momentum_1d',
  振幅: 'price_range',
  日内波动: 'intraday_vol',

  // 筹码
  获利盘: 'chip_profit_ratio_20',
  获利盘比例: 'chip_profit_ratio_20',
  筹码获利: 'chip_profit_ratio_20',
  浮筹: 'chip_floating_ratio',
  浮动筹码: 'chip_floating_ratio',
  筹码集中度: 'chip_concentration_20',
  成本带宽: 'chip_cost_90_width',

  // 行业
  行业强度: 'ind_strength_20',
  行业轮动: 'ind_rotation_speed_20',
  行业拥挤: 'ind_crowding_20',
  行业动量: 'ind_relative_momentum_20',

  // 风格
  价值因子: 'style_value_20',
  规模因子: 'style_size_20',
  特质波动: 'style_idio_vol_20',
  特质波动率: 'style_idio_vol_20',
  低波: 'style_idio_vol_20',
  残差收益: 'style_residual_ret_20',

  // 扩展技术
  布林带: 'tech_bb_pos',
  ADX: 'tech_adx_14',
  趋势强度: 'tech_adx_14',
  CCI: 'tech_cci_20',
  量价相关: 'tech_vol_price_corr_20',
  布林带宽度: 'tech_bb_width',
  布林口: 'tech_bb_width',
  布林收口: 'tech_bb_width',

  // 概念因子
  概念热度: 'concept_hot_score',
  概念轮动: 'concept_rotation_score',
  概念拥挤: 'concept_crowding_max',
  概念领导力: 'concept_leader_score',

  // 量能扩展
  MFI: 'liq_mfi_14',
  资金流量: 'liq_mfi_14',
  OBV: 'liq_obv_20',
  能量潮: 'liq_obv_20',

  // 融资融券
  融资余额: 'finance_balance',
  两融余额: 'finance_balance',
  融资买入: 'finance_buy',
  融券余量: 'slo_volume',
  融资净买入: 'finance_net',
  融资加仓: 'finance_net',
  融资: 'finance_balance',

  // 财务
  营收: 'revenue',
  研发: 'research_expenses',
  研发投入: 'research_expenses',
  每股收益: 's_fa_eps_basic',
  EPS: 's_fa_eps_basic',
  毛利率: 'sales_gross_profit',
  商誉: 'goodwill',
  经营现金流: 'net_cash_flows_oper_act',
  营收增长: 'inc_revenue_rate',
  净利增长: 'inc_net_profit_rate',
};

// 按类别分组的因子（用于UI展示）
export const FACTORS_BY_CATEGORY: Record<string, Array<{ key: string; label: string; unit?: string }>> = {
  '估值因子': FACTORS.filter(f => f.category === '估值因子').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '价格因子': FACTORS.filter(f => f.category === '价格因子').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '均线因子': FACTORS.filter(f => f.category === '均线因子').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '技术指标': FACTORS.filter(f => f.category === '技术指标').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '收益率因子': FACTORS.filter(f => f.category === '收益率因子').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '波动率因子': FACTORS.filter(f => f.category === '波动率因子').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '量能因子': FACTORS.filter(f => f.category === '量能因子').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '指数成分': FACTORS.filter(f => f.category === '指数成分').map(f => ({ key: f.key, label: f.label })),
  '概念标签': FACTORS.filter(f => f.category === '概念标签').map(f => ({ key: f.key, label: f.label })),
  '市场情绪': FACTORS.filter(f => f.category === '市场情绪').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '筹码分析': FACTORS.filter(f => f.category === '筹码分析').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '行业因子': FACTORS.filter(f => f.category === '行业因子').map(f => ({ key: f.key, label: f.label })),
  '风格因子': FACTORS.filter(f => f.category === '风格因子').map(f => ({ key: f.key, label: f.label })),
  '扩展技术': FACTORS.filter(f => f.category === '扩展技术').map(f => ({ key: f.key, label: f.label })),
  '概念因子': FACTORS.filter(f => f.category === '概念因子').map(f => ({ key: f.key, label: f.label })),
  '融资融券': FACTORS.filter(f => f.category === '融资融券').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '财务指标': FACTORS.filter(f => f.category === '财务指标').map(f => ({ key: f.key, label: f.label, unit: f.unit })),
  '其他': FACTORS.filter(f => f.category === '其他').map(f => ({ key: f.key, label: f.label })),
};
