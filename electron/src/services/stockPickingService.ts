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

/** 模型分数校准回测：分数档×市值档×多周期收益/下跌概率 */
export interface ScoreBandHorizon {
  horizon: number;
  n: number;
  win_rate: number;
  down_prob: number;
  avg_ret: number;
  median_ret: number;
}

export interface ScoreBandSummary {
  score_band: string;
  n: number;
  top50_count: number;
  avg_rank: number;
  avg_rank_pct: number;
  main_horizon_avg_ret: number | null;
  horizons: ScoreBandHorizon[];
  nature?: string;
}

export interface ScoreCapCell {
  cap: string;
  n: number;
  down_prob: number | null;
  avg_ret: number | null;
}

export interface ScoreCapRow {
  score_band: string;
  caps: ScoreCapCell[];
}

export interface ScoreCalibrationResponse {
  status: string;
  detail?: string;
  meta?: {
    model_scope: string;
    backtest_days: number;
    horizons: number[];
    main_horizon: number;
    top_n: number;
    total_samples: number;
    latest_trade_date: string;
  };
  matrix?: ScoreCapRow[];
  score_summary?: ScoreBandSummary[];
  neg_industry_avg?: Array<{ industry: string; neg_count: number; neg_avg: number; neg_extreme?: number }>;
  neg_board_avg?: Array<{ board: string; neg_count: number; neg_avg: number }>;
  pos_industry_avg?: Array<{ industry: string; pos_count: number; pos_avg: number; pos_extreme?: number }>;
  pos_board_avg?: Array<{ board: string; pos_count: number; pos_avg: number }>;
  market_signal?: {
    status: string;
    baseline?: { days: number; red_prob: number; avg_next_chg: number };
    signal_table?: Array<{ condition: string; days: number; red_prob: number; green_prob: number; avg_next_chg: number }>;
    recent_days?: Array<{ date: string; avg_score: number; pos_count: number; neg_count: number; pos_ratio: number; next_day_index_chg: number; next_day_red: number }>;
    index_symbol?: string;
  };
  score_range?: { min: number; max: number; band_count: number };
  recommended_band?: ScoreBandSummary | null;
  warnings?: string[];
  total_samples?: number;
  latest_trade_date?: string;
}

/** 提交校准任务，返回 task_id */
export interface CalibrationTaskResponse {
  status: string;
  task_id?: string;
  data?: { task_id: string; status: string; progress: number };
  detail?: string;
}

/** 校准任务进度 */
export interface CalibrationTaskProgress {
  status: string;
  task_id?: string;
  progress?: number;
  message?: string;
  result?: ScoreCalibrationResponse;
  error?: string;
  detail?: string;
  meta?: {
    model_scope: string;
    backtest_days: number;
    horizons: number[];
    top_n: number;
  };
}

export async function submitScoreCalibration(params?: {
  days?: number;
  horizons?: string;
  top_n?: number;
  model_id?: string;
}): Promise<CalibrationTaskResponse> {
  const qp = new URLSearchParams();
  if (params?.days) qp.set('days', String(params.days));
  if (params?.horizons) qp.set('horizons', params.horizons);
  if (params?.top_n) qp.set('top_n', String(params.top_n));
  if (params?.model_id) qp.set('model_id', params.model_id);
  const qs = qp.toString();
  const res = await apiClient.post(`/selection/score-calibration${qs ? `?${qs}` : ''}`);
  return res.data;
}

export async function getCalibrationTask(taskId: string): Promise<CalibrationTaskProgress> {
  const res = await apiClient.get(`/selection/score-calibration/${taskId}`);
  return res.data;
}

/** 校准历史记录 */
export interface CalibrationHistoryItem {
  task_id: string;
  status: string;
  progress: number;
  message?: string;
  params?: { days?: number; horizons?: string; top_n?: number };
  created_at?: string;
  total_samples?: number;
  recommended_band?: string | null;
  latest_trade_date?: string;
}

export async function getCalibrationHistory(limit = 20): Promise<{
  status: string;
  items: CalibrationHistoryItem[];
  total: number;
}> {
  const res = await apiClient.get(`/selection/score-calibration-history?limit=${limit}`);
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
