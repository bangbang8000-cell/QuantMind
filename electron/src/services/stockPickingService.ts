import { apiClient } from './aiStrategyClients';

/* ---- Types ---- */

export type StrategyPreset = 'conservative' | 'balanced' | 'aggressive';

export interface StrategyConfig {
  entry_threshold: number;
  exit_threshold: number;
  strong_industry_min: number;
  score_min: number;
  score_max: number;
  max_positions: number;
}

export interface MarketState {
  state: string;
  avg_top1: number;
  strong_count: number;
  index_above_ma20: boolean;
  index_detail: string;
  ignore_ma20: boolean;
  should_enter: boolean;
  position: string;
  position_reason: string;
}

export interface IndustrySignal {
  industry: string;
  top1: number;
  stock: string;
}

export interface CandidateStock {
  symbol: string;
  name: string;
  score: number;
  industry: string;
  trend: string;
  buy_reason: string;
  warnings: string[];
}

export interface ExcludedExample {
  symbol: string;
  score: number;
  reason: string;
  detail: string;
}

export interface DailySelectionResponse {
  status: string;
  meta: {
    trade_date: string | null;
    strategy: string;
    total_signals: number;
    strategy_config: StrategyConfig;
  };
  market_state: MarketState;
  industry_signals: IndustrySignal[];
  candidates: CandidateStock[];
  excluded_examples: ExcludedExample[];
  warnings: string[];
}

export interface HistoryDay {
  trade_date: string;
  state: string;
  avg_top1: number;
  strong_count: number;
  should_enter: boolean;
  candidates: Array<{ symbol: string; score: number; industry: string; trend: string }>;
}

export interface SelectionHistoryResponse {
  status: string;
  days: HistoryDay[];
  total: number;
}

export interface ShortCandidate {
  symbol: string;
  name: string;
  score: number;
  cap: string;
  board: string;
  short_reason: string;
}

export interface MissedReference {
  symbol: string;
  name: string;
  score: number;
  cap: string;
  board: string;
  missed_reason: string;
}

export interface MatrixRow {
  score_band: string;
  caps: Array<{ cap: string; count: number }>;
}

export interface NegativeSelectionResponse {
  status: string;
  meta: {
    trade_date: string | null;
    total_signals: number;
    negative_count: number;
  };
  short_candidates: ShortCandidate[];
  missed_reference: MissedReference[];
  matrix: MatrixRow[];
  warnings: string[];
}

/* ---- API ---- */

export async function getDailySelection(
  strategy: StrategyPreset = 'balanced',
  date?: string,
  ignoreMa20 = false,
): Promise<DailySelectionResponse> {
  const params = new URLSearchParams({ strategy });
  if (date) params.set('date', date);
  if (ignoreMa20) params.set('ignore_ma20', 'true');
  const res = await apiClient.get(`/selection/daily?${params.toString()}`);
  return res.data;
}

export async function getNegativeSelection(
  date?: string,
): Promise<NegativeSelectionResponse> {
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  const res = await apiClient.get(`/selection/negative?${params.toString()}`);
  return res.data;
}

export async function getSelectionHistory(
  from: string,
  to: string,
  strategy: StrategyPreset = 'balanced',
): Promise<SelectionHistoryResponse> {
  const params = new URLSearchParams({ from, to, strategy });
  const res = await apiClient.get(`/selection/history?${params.toString()}`);
  return res.data;
}

export const STRATEGY_PRESETS: Array<{
  key: StrategyPreset;
  label: string;
  desc: string;
  entry: number;
  exit: number;
  strong_min: number;
}> = [
  { key: 'balanced', label: '平衡型', desc: '推荐', entry: 0.09, exit: 0.06, strong_min: 2 },
  { key: 'conservative', label: '保守型', desc: '低回撤', entry: 0.10, exit: 0.10, strong_min: 5 },
  { key: 'aggressive', label: '激进型', desc: '高收益', entry: 0.07, exit: 0.06, strong_min: 1 },
];
