// =============================================================================
// API Response Types - Bitcoin Trading Assistant
// =============================================================================

// -----------------------------------------------------------------------------
// Scheduler Status (/scheduler/status)
// -----------------------------------------------------------------------------

export interface SchedulerLastResult {
  status: "success" | "error";
  symbol?: string;
  days?: number;
  timeframe?: string;
  fetched?: number;
  inserted?: number;
  updated?: number;
  duplicates?: number;
  duration_seconds?: number;
  error?: string;
}

export interface SchedulerStatus {
  enabled: boolean;
  running: boolean;
  interval_minutes: number | null;
  symbol: string | null;
  days: number | null;
  last_run_time: string | null;
  next_run_time: string | null;
  last_result: SchedulerLastResult | null;
}

// -----------------------------------------------------------------------------
// Market Gaps (/market/candles/gaps)
// -----------------------------------------------------------------------------

export interface GapsFreshness {
  max_ts: string;
  data_lag: string;
  data_lag_hours: number;
  threshold_hours: number;
  status: "FRESH" | "STALE" | "VERY_STALE";
}

export interface GapsCompleteness {
  window_start: string;
  window_end: string;
  expected_count: number;
  actual_count: number;
  missing_count: number;
  missing_timestamps: string[];
  status: "OK" | "GAPS";
}

export interface GapsStats {
  total_in_db: number;
  min_ts: string;
  max_ts: string;
  span_days: number;
}

export interface MarketGapsResponse {
  symbol: string;
  timeframe: string;
  days: number;
  now_utc: string;
  freshness: GapsFreshness;
  completeness: GapsCompleteness;
  stats: GapsStats;
  global_status: "OK" | "STALE" | "GAPS" | "NO_DATA";
}

// -----------------------------------------------------------------------------
// Market Indicators (/market/indicators)
// -----------------------------------------------------------------------------

export interface IndicatorPoint {
  ts: string;
  close: number;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  bb_mid: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  // OHLCV optionnel (si include_candles=true)
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
}

export interface IndicatorsMeta {
  symbol: string;
  timeframe: string;
  history_days: number;
  start_ts: string;
  end_ts: string;
  now_ts: string;
  max_ts: string;
  count: number;
  expected_count: number;
  missing_count: number;
  data_lag_hours: number;
  freshness_status: "FRESH" | "STALE" | "VERY_STALE";
  completeness_status: "OK" | "GAPS";
  global_status: "OK" | "STALE" | "GAPS" | "NO_DATA";
}

export interface MarketIndicatorsResponse {
  meta: IndicatorsMeta;
  series: IndicatorPoint[];
  latest: IndicatorPoint | null;
}

// -----------------------------------------------------------------------------
// Generic fetch state (pour les hooks)
// -----------------------------------------------------------------------------

export interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}
