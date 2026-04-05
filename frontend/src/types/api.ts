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
  now_utc?: string;
  freshness?: GapsFreshness;
  completeness?: GapsCompleteness;
  stats?: GapsStats;
  global_status: "OK" | "STALE" | "GAPS" | "NO_DATA";
  error?: string;
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

// -----------------------------------------------------------------------------
// News & Sentiment (/news)
// -----------------------------------------------------------------------------

export type SentimentType = 'positive' | 'negative' | 'neutral';
export type ImpactLevel = 'high' | 'medium' | 'low';

export interface NewsItem {
  title: string;
  url: string | null;
  source: string;
  published_at: string | null;
  sentiment: SentimentType;
  impact: ImpactLevel;
  keywords: string[];
  description: string | null;
}

export interface NewsSentimentSummary {
  total_articles: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  overall_sentiment: SentimentType;
  sentiment_score: number;
}

export interface NewsResponse {
  items: NewsItem[];
  summary: NewsSentimentSummary;
  meta: Record<string, unknown>;
}

// -----------------------------------------------------------------------------
// Decision Engine (/market/decision)
// -----------------------------------------------------------------------------

export type ActionType = 'acheter' | 'vendre' | 'attendre';

export interface Scenario {
  label: string;
  probability: number;
  direction: SignalDirection;
  description: string;
}

export interface RuleResult {
  rule_name: string;
  condition: string;
  satisfied: boolean;
  weight: number;
  detail: string;
  direction: SignalDirection;
}

export interface DecisionRecommendation {
  action: ActionType;
  confidence: ConfidenceLevel;
  explanation: string;
  reasons: string[];
}

export interface DecisionMeta {
  symbol: string;
  timeframe: string;
  history_days: number;
  timestamp: string;
  sentiment_available: boolean;
  technical_weight: number;
  sentiment_weight: number;
}

export interface DecisionResponse {
  meta: DecisionMeta;
  scenarios: Scenario[];
  rules_evaluated: RuleResult[];
  recommendation: DecisionRecommendation;
  technical_score: number;
  sentiment_score: number;
  combined_score: number;
  summary: string;
}

// -----------------------------------------------------------------------------
// Backtesting (/backtest)
// -----------------------------------------------------------------------------

export type TradeDirection = 'buy' | 'sell';

export interface BacktestConfig {
  symbol?: string;
  timeframe?: string;
  start_days_ago?: number;
  initial_capital?: number;
}

export interface BacktestTradeItem {
  entry_ts: string;
  exit_ts: string | null;
  direction: TradeDirection;
  entry_price: number;
  exit_price: number | null;
  pnl: number;
  pnl_pct: number;
  reason_entry: string;
  reason_exit: string;
  duration_hours: number;
}

export interface BacktestMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  net_pnl: number;
  net_pnl_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  avg_trade_pnl: number;
  avg_trade_duration_hours: number;
  sharpe_ratio: number;
  buy_and_hold_pnl_pct: number;
  overfitting_warning: boolean;
}

export interface EquityPoint {
  ts: string;
  capital: number;
  drawdown_pct: number;
}

export interface BacktestMeta {
  symbol: string;
  timeframe: string;
  start_ts: string;
  end_ts: string;
  initial_capital: number;
  candles_analyzed: number;
  decisions_made: number;
  duration_seconds: number;
}

export interface BacktestResponse {
  meta: BacktestMeta;
  metrics: BacktestMetrics;
  trades: BacktestTradeItem[];
  equity_curve: EquityPoint[];
  summary: string;
}

// -----------------------------------------------------------------------------
// Verification Historique (/backtest/verify, /backtest/walk-forward)
// -----------------------------------------------------------------------------

export interface HistoryLoadConfig {
  symbol?: string;
  timeframe?: string;
  start_date?: string;
  end_date?: string;
}

export interface HistoryLoadResponse {
  fetched: number;
  inserted: number;
  symbol: string;
  timeframe: string;
  start_ts: string;
  end_ts: string;
  duration_seconds: number;
}

export interface HistoryRangeResponse {
  symbol: string;
  timeframe: string;
  min_date: string | null;
  max_date: string | null;
  total_candles: number;
  has_data: boolean;
}

export interface HorizonOutcome {
  horizon_days: number;
  end_date: string;
  end_price: number;
  actual_change_pct: number;
  actual_direction: string;
  predicted_action: string;
  predicted_score: number;
  correct: boolean;
  quality_score: number;
  directional_match: boolean;
  detail: string;
}

export interface VerificationRequest {
  target_date: string;
  symbol?: string;
  timeframe?: string;
  history_days?: number;
  horizons?: number[];
}

export interface VerificationResult {
  target_date: string;
  price_at_date: number;
  predicted_action: string;
  predicted_confidence: string;
  predicted_score: number;
  predicted_summary: string;
  dominant_scenario: string;
  dominant_probability: number;
  outcomes: HorizonOutcome[];
  meta: Record<string, unknown>;
}

export interface WalkForwardConfig {
  start_date: string;
  end_date: string;
  step_days?: number;
  symbol?: string;
  timeframe?: string;
  history_days?: number;
  horizons?: number[];
  compare_mode?: boolean;
}

export interface HorizonAccuracy {
  horizon_days: number;
  total_points: number;
  correct: number;
  incorrect: number;
  accuracy_pct: number;
  avg_predicted_score: number;
  avg_actual_change_pct: number;
  buy_signals: number;
  sell_signals: number;
  hold_signals: number;
  // Métriques avancées v1.2
  directional_accuracy_pct: number;
  avg_quality_score: number;
  high_confidence_accuracy_pct: number;
  high_confidence_count: number;
  profitable_direction_pct: number;
}

export interface WalkForwardSummaryStats {
  total_points: number;
  overall_accuracy_pct: number;
  overall_quality_score: number;
  directional_accuracy_pct: number;
  profitable_direction_pct: number;
  accuracy_by_horizon: HorizonAccuracy[];
}

export interface WalkForwardComparison {
  technical_only: WalkForwardSummaryStats;
  with_sentiment: WalkForwardSummaryStats;
  sentiment_delta_accuracy_pct: number;
  sentiment_delta_quality: number;
  verdict: string;
}

export interface WalkForwardResult {
  total_points: number;
  start_date: string;
  end_date: string;
  step_days: number;
  accuracy_by_horizon: HorizonAccuracy[];
  points: VerificationResult[];
  summary: string;
  duration_seconds: number;
  overall_quality_score: number;
  comparison: WalkForwardComparison | null;
}

// -----------------------------------------------------------------------------
// History Integrity (/backtest/history/integrity)
// -----------------------------------------------------------------------------

export interface HistoryIntegrityGap {
  start_date: string;
  end_date: string;
  missing_days: number;
}

export interface HistoryIntegrityResponse {
  symbol: string;
  timeframe: string;
  total_candles: number;
  expected_candles: number;
  missing_candles: number;
  completeness_pct: number;
  gaps: HistoryIntegrityGap[];
  min_date: string | null;
  max_date: string | null;
  quality_grade: 'EXCELLENT' | 'GOOD' | 'WARNING' | 'CRITICAL' | 'UNKNOWN';
  detail: string;
}

// -----------------------------------------------------------------------------
// Sentiment Historique (/sentiment/history)
// -----------------------------------------------------------------------------

export interface SentimentLoadConfig {
  source?: string;
  start_date?: string;
  end_date?: string;
}

export interface SentimentLoadResponse {
  source: string;
  fetched: number;
  inserted: number;
  updated: number;
  skipped: number;
  total_in_db: number;
  date_range_start: string | null;
  date_range_end: string | null;
  duration_seconds: number;
}

export interface SentimentRangeResponse {
  source: string;
  min_date: string | null;
  max_date: string | null;
  total_points: number;
  has_data: boolean;
}

export interface SentimentAtDateResponse {
  date: string;
  source: string;
  raw_score: number;
  normalized_score: number;
  label: string | null;
  exact_match: boolean;
  actual_date: string | null;
}

export interface SentimentCoverageResponse {
  sources: SentimentRangeResponse[];
  total_points: number;
  earliest_date: string | null;
  latest_date: string | null;
}
