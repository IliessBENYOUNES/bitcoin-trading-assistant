// =============================================================================
// API Response Types - Bitcoin Trading Assistant
// Last updated: 2026-04-02 — All types exported for barrel re-export
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

// -----------------------------------------------------------------------------
// Market Signals (/market/signals)
// -----------------------------------------------------------------------------

export type SignalDirection = 'bullish' | 'bearish' | 'neutral';
export type ConfidenceLevel = 'high' | 'medium' | 'low';

export interface SignalItem {
  indicator: string;
  direction: SignalDirection;
  strength: number;
  value: number | null;
  message: string;
}

export interface CompositeScore {
  score: number;
  direction: SignalDirection;
  confidence: ConfidenceLevel;
  consensus: string;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
}

export interface MarketSignalsResponse {
  meta: IndicatorsMeta;
  signals: SignalItem[];
  composite: CompositeScore;
  summary: string;
}

// -----------------------------------------------------------------------------
// Alerts (/alerts)
// -----------------------------------------------------------------------------

export type ConditionType = 'price' | 'rsi' | 'macd_hist' | 'score';
export type AlertOperator = 'above' | 'below';
export type AlertStatus = 'active' | 'triggered' | 'disabled';

export interface AlertItem {
  id: number;
  symbol: string;
  timeframe: string;
  condition_type: ConditionType;
  operator: AlertOperator;
  threshold: number;
  message: string | null;
  status: AlertStatus;
  recurring: boolean;
  created_at: string | null;
  triggered_at: string | null;
  triggered_value: number | null;
}

export interface AlertCreate {
  symbol?: string;
  timeframe?: string;
  condition_type: ConditionType;
  operator: AlertOperator;
  threshold: number;
  message?: string;
  recurring?: boolean;
}

export interface AlertNotification {
  alert_id: number;
  condition_type: string;
  operator: string;
  threshold: number;
  current_value: number;
  message: string;
  triggered_at: string;
}

export interface AlertCheckResponse {
  checked: number;
  triggered: number;
  notifications: AlertNotification[];
}

