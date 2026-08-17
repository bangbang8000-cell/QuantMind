/** 个股终端类型定义 */

export interface StockListItem {
  symbol: string;        // 600519.SH
  name: string;
  board: string;         // 沪市主板/科创板/深市主板/创业板/北交所
  industry: string | null;
  close: number | null;
  pct_change: number | null;  // 百分数
  total_mv: number | null;    // 亿元
  float_mv: number | null;    // 亿元
  pe: number | null;
  pb: number | null;
  is_st: boolean;
  fusion: number | null;
  side: string | null;
  signal_date: string | null;
  model: string | null;
}

export interface StockListResponse {
  total: number;
  page: number;
  page_size: number;
  trade_date: string;
  signal_date?: string;
  items: StockListItem[];
}

export interface IndexMembership {
  index_code: string;
  index_name: string;
  weight: number | null;
}

export interface StockProfile {
  symbol: string;
  name: string;
  board: string;
  industry: string | null;
  trade_date: string;
  close: number | null;
  pct_change: number | null;
  total_mv: number | null;        // 亿元
  float_mv: number | null;        // 亿元
  total_share: number | null;     // 万股
  free_float_share: number | null;
  pe_dynamic: number | null;
  pb: number | null;
  dividend_yield: number | null;
  beta: number | null;
  staff_num: number | null;
  main_business: string | null;
  ipo_price: number | null;
  limit_up_price: number | null;
  limit_down_price: number | null;
  flags: {
    hs300: boolean;
    marginable: boolean;
    sh_hk_connect: boolean;
    is_st: boolean;
    is_hk_listed: boolean;
  };
  valuation: {
    pe_ttm?: number | null;
    pe_static?: number | null;
    pb?: number | null;
    ps_ttm?: number | null;
    dividend_rate?: number | null;
    total_mv?: number | null;
    float_mv?: number | null;
    net_profit_ttm?: number | null;
    revenue_ttm?: number | null;
    equity?: number | null;
  };
  index_membership: IndexMembership[];
  concepts: string[];
}

export interface KlineBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  amount?: number | null;
}

export type Exchange = 'SH' | 'SZ' | 'BJ';
