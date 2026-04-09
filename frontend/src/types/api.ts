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
  horizons?: number[];  // float: 0.00347=5min, 0.01042=15min, 0.04167=1h, 0.1667=4h, 7, 30, 90
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
  horizons?: number[];  // float: supports scalping (0.00347, 0.01042, 0.04167) and swing (7, 30, 90)
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
// Interesting Dates (/backtest/interesting-dates)
// -----------------------------------------------------------------------------

export interface InterestingSignalDetail {
  indicator: string;   // rsi, macd, sma, bollinger
  direction: string;   // bullish, bearish, neutral
  strength: number;    // 0-1
  message: string;
  value: number | null;
}

export interface InterestingDateItem {
  date: string;                    // ISO date (ex: 2021-05-19)
  price: number;
  interest_score: number;          // 0-100
  dominant_direction: string;      // bullish, bearish, mixed
  signals: InterestingSignalDetail[];
  label: string;                   // ex: "RSI survendu + MACD ↑"
}

export interface InterestingDatesResponse {
  dates: InterestingDateItem[];
  total_scanned: number;
  total_found: number;
  timeframe: string;
  min_strength: number;
  duration_seconds: number;
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

// -----------------------------------------------------------------------------
// Risk Management (/risk)
// -----------------------------------------------------------------------------

export type StopLossType = 'fixed' | 'trailing' | 'atr';
export type RiskLevel = 'safe' | 'caution' | 'danger' | 'blocked';

export interface RiskConfigItem {
  id: number;
  stop_loss_type: StopLossType;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_position_pct: number;
  total_portfolio_value: number;
  max_daily_loss_pct: number;
  daily_loss_current: number;
  kill_switch_active: boolean;
  kill_switch_triggered_at: string | null;
  kill_switch_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RiskConfigCreate {
  stop_loss_type?: StopLossType;
  stop_loss_pct?: number;
  take_profit_pct?: number;
  max_position_pct?: number;
  total_portfolio_value?: number;
  max_daily_loss_pct?: number;
}

export interface RiskEvaluation {
  allowed: boolean;
  original_action: string;
  adjusted_action: string;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  max_position_size_usd: number | null;
  risk_reward_ratio: number | null;
  reasons: string[];
  warnings: string[];
}

export interface RiskStatus {
  config: RiskConfigItem;
  kill_switch_active: boolean;
  daily_loss_current: number;
  daily_loss_limit_usd: number;
  daily_loss_pct: number;
  daily_loss_remaining_usd: number;
  max_position_size_usd: number;
  risk_level: RiskLevel;
  detail: string;
}

export interface RecordLossResponse {
  recorded: number;
  daily_loss_current: number;
  daily_limit_usd: number;
  limit_reached: boolean;
  kill_switch_active: boolean;
}

// -----------------------------------------------------------------------------
// Paper Trading (/paper)
// -----------------------------------------------------------------------------

export interface PaperTradeItem {
  id: number;
  account_id: number;
  status: string; // open, closed_tp, closed_sl, closed_signal, closed_expired, closed_manual
  direction: string; // long, short
  entry_price: number;
  exit_price: number | null;
  stop_loss_price: number;
  take_profit_price: number;
  highest_price_since_entry: number | null;
  position_size_usd: number;
  pnl: number | null;
  pnl_pct: number | null;
  entry_reason: string;
  exit_reason: string | null;
  decision_score: number | null;
  entry_ts: string;
  exit_ts: string | null;
  duration_hours: number | null;
  created_at: string | null;
  updated_at: string | null;
  slot?: string | null; // v1.7 multi-slot
}

export interface PaperAccountItem {
  id: number;
  initial_capital: number;
  current_capital: number;
  total_pnl: number;
  total_pnl_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  max_drawdown_pct: number;
  sharpe_ratio: number | null;
  is_active: boolean;
  max_open_duration_hours: number;
  max_open_positions?: number; // v1.7
  btc_price_at_start: number | null;
  peak_capital: number;
  created_at: string | null;
  updated_at: string | null;
  open_position: PaperTradeItem | null;
  open_positions?: PaperTradeItem[]; // v1.7
}

export interface PaperMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  net_pnl: number;
  net_pnl_pct: number;
  sharpe_ratio: number | null;
  max_drawdown_pct: number;
  avg_trade_pnl: number;
  avg_trade_duration_hours: number;
  best_trade_pnl: number;
  worst_trade_pnl: number;
  profit_factor: number;
  buy_hold_pnl_pct: number;
}

export interface PaperStatus {
  account: PaperAccountItem;
  open_position: PaperTradeItem | null;
  open_positions?: PaperTradeItem[]; // v1.7
  metrics: PaperMetrics;
  is_running: boolean;
  last_check_ts: string | null;
  current_btc_price: number | null;
  unrealized_pnl: number | null;
}

export interface SlotTickResult {
  slot: string;
  action_taken: string;
  detail: string;
  profile_type: string;
  position_opened: PaperTradeItem | null;
  position_closed: PaperTradeItem | null;
}

export interface PaperTickResult {
  action_taken: string;
  detail: string;
  position_opened: PaperTradeItem | null;
  position_closed: PaperTradeItem | null;
  current_price: number;
  timestamp: string;
  decision_score: number | null;
  decision_action: string | null;
  risk_allowed: boolean | null;
  slot_results?: SlotTickResult[]; // v1.7
}

export interface PaperTradeListResponse {
  trades: PaperTradeItem[];
  total: number;
}

// Export complet du journal de trading
export interface PaperTradeExportItem {
  id: number;
  status: string;
  direction: string;
  entry_price: number;
  exit_price: number | null;
  stop_loss_price: number;
  take_profit_price: number;
  highest_price_since_entry: number | null;
  lowest_price_since_entry: number | null;
  position_size_usd: number;
  leverage: number;
  effective_size_usd: number | null;
  leverage_reason: string | null;
  profile_type: string | null;
  slot: string | null;
  pnl: number | null;
  pnl_pct: number | null;
  entry_reason: string;
  exit_reason: string | null;
  decision_score: number | null;
  entry_ts: string;
  exit_ts: string | null;
  duration_hours: number | null;
}

export interface PaperExportAccountSummary {
  initial_capital: number;
  current_capital: number;
  total_pnl: number;
  total_pnl_pct: number;
  peak_capital: number;
  max_drawdown_pct: number;
  btc_price_at_start: number | null;
  active_profile: string;
  max_open_positions: number;
  created_at: string | null;
}

export interface PaperExportResponse {
  export_version: string;
  exported_at: string;
  account: PaperExportAccountSummary;
  metrics: PaperMetrics;
  current_btc_price: number | null;
  total_trades: number;
  open_trades: PaperTradeExportItem[];
  closed_trades: PaperTradeExportItem[];
}

// -----------------------------------------------------------------------------
// Mode Autonome Backend (Headless) — v1.9.7
// -----------------------------------------------------------------------------

export interface AutonomousStatus {
  running: boolean;
  interval_seconds: number | null;
  profile: string | null;
  tick_count: number;
  trade_count: number;
  last_tick_time: string | null;
  last_result: {
    action: string;
    detail: string;
    price: number;
    timestamp: string;
  } | null;
  started_at: string | null;
  uptime_seconds: number | null;
  frontend_required: boolean;
  headless_capable: boolean;
}

// -----------------------------------------------------------------------------
// Paper Trading — Journal d'Évaluation (v1.5)
// -----------------------------------------------------------------------------

export interface JournalPeriodSummary {
  date_from: string;
  date_to: string;
  total_ticks: number;
  total_trades: number;
  trades_per_day: number;
  trades_per_hour_avg: number;
  win_rate: number;
  pnl_realized: number;
  pnl_latent: number | null;
  pnl_pct: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
  profit_factor: number;
  sharpe: number | null;
  max_drawdown_pct: number;
  best_streak: number;
  worst_streak: number;
  avg_position_duration_hours: number;
  buy_hold_pct: number;
  delta_vs_buy_hold: number;
  verdict: string;
}

export interface JournalDaySummary {
  date: string;
  total_ticks: number;
  total_trades: number;
  pnl_realized: number;
  pnl_pct: number;
  win_rate: number;
  drawdown_pct: number;
  best_trade_pnl: number;
  worst_trade_pnl: number;
  avg_position_duration_hours: number;
  verdict: string;
}

export interface JournalActivityStats {
  total_ticks: number;
  ticks_with_signal: number;
  ticks_opened: number;
  ticks_closed: number;
  ticks_hold: number;
  ticks_blocked_risk: number;
  ticks_ignored_signal: number;
  ticks_position_held: number;
  ticks_exit_tp: number;
  ticks_exit_sl: number;
  ticks_exit_signal: number;
  ticks_exit_expired: number;
  tick_to_trade_ratio: number;
}

export interface NonTradeReasonItem {
  reason: string;
  label: string;
  count: number;
  pct: number;
}

export interface JournalNonTradeReasons {
  total_non_trade_ticks: number;
  reasons: NonTradeReasonItem[];
}

export interface JournalResponse {
  period: JournalPeriodSummary;
  daily: JournalDaySummary[];
  activity: JournalActivityStats;
  non_trade_reasons: JournalNonTradeReasons;
  profile_type: string;
}

// -----------------------------------------------------------------------------
// Paper Trading — Profils (v1.5)
// -----------------------------------------------------------------------------

export type TradingProfileType = 'conservative' | 'balanced' | 'aggressive' | 'scalping' | 'auto';

export interface TradingProfileParams {
  profile_type: TradingProfileType;
  label: string;
  description: string;
  min_score: number;
  min_confidence: string;
  min_scenario_dominance: number;
  max_trades_per_day: number;
  cooldown_minutes: number;
  max_position_duration_hours: number;
  profit_take_pct: number;
  loss_cut_pct: number;
  loss_cut_score_threshold: number;
  leverage_enabled: boolean;
  max_leverage: number;
  // v1.6 — Nouveaux champs
  analysis_timeframe?: string | null;
  buy_threshold?: number | null;
  sell_threshold?: number | null;
  momentum_fade_enabled?: boolean;
  stale_exit_minutes?: number | null;
}

export interface TradingProfileResponse {
  active_profile: TradingProfileType;
  params: TradingProfileParams;
}

// -----------------------------------------------------------------------------
// Paper Trading — Style de Trading (v1.5)
// -----------------------------------------------------------------------------

export interface DurationBucket {
  label: string;
  count: number;
  pct: number;
}

export interface TradingStyleResult {
  total_closed_trades: number;
  duration_distribution: DurationBucket[];
  dominant_style: string;
  avg_duration_minutes: number;
  median_duration_minutes: number;
  signals_strong_per_hour: number;
  signals_ignored_per_hour: number;
  exits_fast_count: number;
  exits_slow_count: number;
}

// -----------------------------------------------------------------------------
// Paper Trading — Diagnostic de Fréquence (v1.6)
// -----------------------------------------------------------------------------

export interface NonTradeRankedReason {
  rank: number;
  reason: string;
  label: string;
  count: number;
  pct: number;
  category: string;
}

export interface PositionDurationStats {
  total_closed: number;
  avg_duration_hours: number;
  median_duration_hours: number;
  min_duration_hours: number;
  max_duration_hours: number;
  pct_under_1h: number;
  pct_1h_to_4h: number;
  pct_4h_to_24h: number;
  pct_over_24h: number;
  ticks_blocked_by_open_position: number;
  pct_ticks_blocked_by_position: number;
}

export interface ProfileComparisonRow {
  profile: string;
  total_trades: number;
  trades_per_day: number;
  win_rate: number;
  net_pnl: number;
  expectancy: number;
  avg_duration_hours: number;
  max_drawdown_pct: number;
  simulated_entries: number;
  simulated_entries_per_day: number;
  top_block_reason: string;
  top_block_pct: number;
}

export interface RiskBrakeAnalysis {
  total_ticks: number;
  ticks_blocked_by_risk: number;
  pct_blocked_by_risk: number;
  ticks_kill_switch: number;
  ticks_daily_loss: number;
  ticks_leverage_reduced: number;
  ticks_leverage_forced_x1: number;
  pct_signal_filter: number;
  pct_risk_filter: number;
  pct_structural: number;
}

export interface DiagnosticResponse {
  total_ticks: number;
  total_trades: number;
  tick_to_trade_pct: number;
  avg_trades_per_day: number;
  analysis_days: number;
  top_non_trade_reasons: NonTradeRankedReason[];
  position_duration: PositionDurationStats;
  profile_comparison: ProfileComparisonRow[];
  risk_brake: RiskBrakeAnalysis;
  main_bottleneck: string;
  bottleneck_detail: string;
  recommendations: string[];
}

export interface MissedOpportunityItem {
  tick_timestamp: string;
  btc_price_at_tick: number;
  decision_action?: string;
  decision_score?: number;
  reason_no_trade: string;
  profile_at_tick: string;
  price_after_5m?: number;
  price_after_15m?: number;
  price_after_30m?: number;
  best_move_pct: number;
  best_move_window: string;
  was_exploitable: boolean;
}

export interface MissedOpportunitySummary {
  total_non_trade_ticks_analyzed: number;
  ticks_with_favorable_move: number;
  pct_missed: number;
  avg_missed_move_pct: number;
  missed_above_010_pct: number;
  missed_above_020_pct: number;
  missed_above_030_pct: number;
  missed_above_050_pct: number;
  missed_by_reason: NonTradeRankedReason[];
  top_examples: MissedOpportunityItem[];
  warning: string;
}

export interface LeverageAnalysisResponse {
  total_leveraged_trades: number;
  total_unleveraged_trades: number;
  pnl_with_leverage: number;
  pnl_without_leverage: number;
  leverage_benefit: number;
  win_rate_leveraged: number;
  win_rate_unleveraged: number;
  trades_amplified_positive: number;
  trades_amplified_negative: number;
  trades_refused_by_leverage: number;
  trades_reduced_by_risk: number;
}

