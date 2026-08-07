/**
 * 尾盘交易模式共享工具
 *
 * 统一两种执行口径：
 * - ON:  T 日信号 + T+1 收盘成交 (deal_price=close, signal_lag_days=1)
 *        信号在 T 日收盘后生成，T+1 尾盘成交，无前视偏差
 * - OFF: T 日信号 + T+1 开盘成交 (deal_price=open, signal_lag_days=1)
 *        信号在 T 日收盘后生成，T+1 开盘成交，标准口径
 *
 * ⚠️ signal_lag_days=0 + deal_price=close 已被禁止（前视偏差）：
 *    模型在 T 日收盘前使用 T 日收盘价预测并以 T 日收盘价成交。
 *
 * 所有回测入口共享同一个 localStorage 键，保证口径一致。
 */

export const TAIL_TRADE_MODE_STORAGE_KEY = 'backtest_tail_trade_mode';

export const getStoredTailTradeMode = (): boolean => {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(TAIL_TRADE_MODE_STORAGE_KEY) === '1';
};

export const setStoredTailTradeMode = (enabled: boolean): void => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(TAIL_TRADE_MODE_STORAGE_KEY, enabled ? '1' : '0');
};

export const getTailTradeDealPrice = (enabled: boolean): 'open' | 'close' =>
  enabled ? 'close' : 'open';

export const getTailTradeSignalLagDays = (_enabled: boolean): number =>
  1; // 始终使用 signal_lag_days=1，避免前视偏差

/**
 * 是否强制禁止信号缺失时的 feature 降级回退。
 * 文档口径要求始终为 false，避免静默降级污染口径。
 */
export const ALLOW_FEATURE_SIGNAL_FALLBACK = false;
