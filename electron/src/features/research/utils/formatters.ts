export const safeNum = (value: unknown, fallback = 0): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback;

export const normalizeSymbol = (raw: string): string => {
  const s = (raw || '').trim().toUpperCase();
  if (!s) return s;
  if (/^(SH|SZ|BJ)\d{6}$/.test(s)) return s;
  const suffixMatch = s.match(/^(\d{6})\.(SH|SZ|BJ)$/);
  if (suffixMatch) return `${suffixMatch[2]}${suffixMatch[1]}`;
  if (/^\d{6}$/.test(s)) {
    if (s.startsWith('6') || s.startsWith('68') || s.startsWith('90')) return `SH${s}`;
    if (s.startsWith('4') || s.startsWith('8') || s.startsWith('9')) return `BJ${s}`;
    return `SZ${s}`;
  }
  return s;
};

export const normalizeRoe = (value: unknown): number => {
  let v = safeNum(value, 0);
  if (Math.abs(v) > 200) v = v / 100;
  return v;
};

export const normalizeYiValue = (value: unknown): number => {
  const v = safeNum(value, 0);
  return Math.abs(v) >= 1_000_000 ? v / 100_000_000 : v;
};

export const fmt2 = (value: unknown): string => safeNum(value, 0).toFixed(2);
export const fmtPercent2 = (value: unknown): string => `${safeNum(value, 0).toFixed(2)}%`;

export const fmtSignedPercent2 = (value: unknown): string => {
  const v = safeNum(value, 0);
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
};

export const fmtNullableSignedPercent2 = (value: unknown): string =>
  value === null || value === undefined ? '-' : fmtSignedPercent2(value);

export const fmtMainFlowCn = (value: unknown): string => {
  const v = safeNum(value, 0);
  if (Math.abs(v) >= 10000) return `${(v / 10000).toFixed(2)}亿`;
  return `${v.toFixed(2)}百万`;
};

export const fmtFloat = (value: unknown, decimals = 3): string => {
  const v = safeNum(value, 0);
  return v.toFixed(decimals);
};

export const fmtNullableFloat = (value: unknown, decimals = 3): string =>
  value === null || value === undefined ? '-' : fmtFloat(value, decimals);

/**
 * 用于 PE / ROE / RSI / 均线 / 市值这类“0 在现实中不可能”的指标。
 *
 * PG `stock_daily_latest` 在近期交易日未回填这些列，序列化后 NULL 变成了 0，
 * 于是详情页出现 “PE 0.0 / ROE 0.0% / RSI 0.0” 这种看起来像真实数据的假值。
 * 这里把 0 一并显示为 “-”，避免把缺失当成极端估值误导判断。
 */
export const fmtPositiveOrDash = (value: unknown, decimals = 2, suffix = ''): string => {
  if (value === null || value === undefined) return '-';
  const v = safeNum(value, 0);
  if (!Number.isFinite(v) || v === 0) return '-';
  return `${v.toFixed(decimals)}${suffix}`;
};

export const fmtSignedFloat = (value: unknown, decimals = 3): string => {
  const v = safeNum(value, 0);
  return `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}`;
};

export const fmtNullableSignedFloat = (value: unknown, decimals = 3): string =>
  value === null || value === undefined ? '-' : fmtSignedFloat(value, decimals);

export const fmtPercent = (value: unknown, decimals = 2): string =>
  `${safeNum(value, 0).toFixed(decimals)}%`;

export const fmtNullablePercent = (value: unknown, decimals = 2): string =>
  value === null || value === undefined ? '-' : fmtPercent(value, decimals);

export const fmtSignedPercent = (value: unknown, decimals = 2): string => {
  const v = safeNum(value, 0);
  return `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}%`;
};

export const fmtNullableSignedPercent = (value: unknown, decimals = 2): string =>
  value === null || value === undefined ? '-' : fmtSignedPercent(value, decimals);

export const fmtYi = (value: unknown, decimals = 2): string => {
  const v = safeNum(value, 0) / 100_000_000;
  return `${v.toFixed(decimals)}亿`;
};

export const fmtNullableYi = (value: unknown, decimals = 2): string =>
  value === null || value === undefined ? '-' : fmtYi(value, decimals);

export const fmtExponential = (value: unknown, decimals = 2): string => {
  const v = safeNum(value, 0);
  return v.toExponential(decimals);
};

export const fmtNullableExponential = (value: unknown, decimals = 2): string =>
  value === null || value === undefined ? '-' : fmtExponential(value, decimals);