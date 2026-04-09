/**
 * Types TypeScript pour l'application.
 * Barrel re-export de tous les types API.
 */

// Re-export explicite des types API (scheduler, gaps, indicators, signals, alerts, risk)
export type {
  // Scheduler
  SchedulerLastResult,
  SchedulerStatus,
  // Gaps
  GapsFreshness,
  GapsCompleteness,
  GapsStats,
  MarketGapsResponse,
  // Indicators
  IndicatorPoint,
  IndicatorsMeta,
  MarketIndicatorsResponse,
  // Generic
  FetchState,
  // Signals
  SignalDirection,
  ConfidenceLevel,
  SignalItem,
  CompositeScore,
  MarketSignalsResponse,
  // Alerts
  ConditionType,
  AlertOperator,
  AlertStatus,
  AlertItem,
  AlertCreate,
  AlertNotification,
  AlertCheckResponse,
  // News & Sentiment
  SentimentType,
  ImpactLevel,
  NewsItem,
  NewsSentimentSummary,
  NewsResponse,
  // Decision Engine
  ActionType,
  Scenario,
  RuleResult,
  DecisionRecommendation,
  DecisionMeta,
  DecisionResponse,
  // Backtesting
  TradeDirection,
  BacktestConfig,
  BacktestTradeItem,
  BacktestMetrics,
  EquityPoint,
  BacktestMeta,
  BacktestResponse,
  // Verification Historique
  HistoryLoadConfig,
  HistoryLoadResponse,
  HistoryRangeResponse,
  HorizonOutcome,
  VerificationRequest,
  VerificationResult,
  WalkForwardConfig,
  WalkForwardResult,
  HorizonAccuracy,
  WalkForwardSummaryStats,
  WalkForwardComparison,
  // Interesting Dates
  InterestingSignalDetail,
  InterestingDateItem,
  InterestingDatesResponse,
  // History Integrity
  HistoryIntegrityGap,
  HistoryIntegrityResponse,
  // Sentiment Historique
  SentimentLoadConfig,
  SentimentLoadResponse,
  SentimentRangeResponse,
  SentimentAtDateResponse,
  SentimentCoverageResponse,
  // Risk Management
  StopLossType,
  RiskLevel,
  RiskConfigItem,
  RiskConfigCreate,
  RiskEvaluation,
  RiskStatus,
  RecordLossResponse,
  // Paper Trading
  PaperTradeItem,
  PaperAccountItem,
  PaperMetrics,
  PaperStatus,
  PaperTickResult,
  SlotTickResult,
  PaperTradeListResponse,
  // Paper Trading — Export (v1.7.3)
  PaperTradeExportItem,
  PaperExportAccountSummary,
  PaperExportResponse,
  // Paper Trading — Mode Autonome Backend (v1.9.7)
  AutonomousStatus,
  // Paper Trading — Journal & Profils (v1.5)
  JournalPeriodSummary,
  JournalDaySummary,
  JournalActivityStats,
  NonTradeReasonItem,
  JournalNonTradeReasons,
  JournalResponse,
  TradingProfileType,
  TradingProfileParams,
  TradingProfileResponse,
  DurationBucket,
  TradingStyleResult,
  // Paper Trading — Diagnostic (v1.6) - re-exported from api.ts
  NonTradeRankedReason,
  PositionDurationStats,
  ProfileComparisonRow,
  RiskBrakeAnalysis,
  DiagnosticResponse,
  MissedOpportunityItem,
  MissedOpportunitySummary,
  LeverageAnalysisResponse,
} from './api';

// Also re-export from diagnostic.ts for direct imports
export type {
  NonTradeRankedReason as DiagNonTradeRankedReason,
  DiagnosticResponse as DiagResponse,
  MissedOpportunitySummary as DiagMissedSummary,
  LeverageAnalysisResponse as DiagLeverageAnalysis,
} from './diagnostic';

// Représente un chandelier (bougie) OHLCV
export interface Candle {
  id: number;
  symbol: string;
  timeframe: string;
  timestamp: string;
  open_price: number;
  high_price: number;
  low_price: number;
  close_price: number;
  volume: number;
  source: string;
  created_at: string;
}

// Réponse de l'API /market/candles (enrichie)
export interface CandleListResponse {
  data: Candle[];
  count: number;
  symbol: string | null;
  timeframe: string | null;
  // Nouveaux champs
  total_in_db?: number;
  expected_count?: number | null;
  start_ts?: string | null;
  end_ts?: string | null;
}

// Réponse de l'API /market/candles/fetch (enrichie)
export interface FetchResponse {
  message: string;
  symbol: string;
  timeframe: string;
  days: number;
  fetched: number;
  inserted: number;
  updated?: number;
  duplicates: number;
  expected_theoretical?: number;
  coverage_pct?: number;
}

// Réponse de l'API /market/candles/gaps
export interface GapsResponse {
  symbol: string;
  timeframe: string;
  days: number;
  start_ts: string;
  end_ts: string;
  expected_count: number;
  actual_count: number;
  missing_count: number;
  missing_timestamps: string[];
  status: 'OK' | 'GAPS_DETECTED';
}

// Réponse de l'API /market/price
export interface PriceResponse {
  symbol: string;
  price: number;
  timestamp: string;
}

// Réponse de l'API /market/info
export interface MarketInfo {
  symbol: string;
  name: string;
  current_price: number;
  market_cap: number;
  total_volume: number;
  price_change_24h: number;
  price_change_7d: number;
  price_change_30d: number;
  ath: number;
  ath_date: string;
  last_updated: string;
}

// Réponse de l'API /health
export interface HealthResponse {
  status: string;
  service: string;
}

// Réponse de l'API /health/db
export interface HealthDbResponse {
  status: string;
  database: string;
  error?: string;
}