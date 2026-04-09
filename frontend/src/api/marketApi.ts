// =============================================================================
// Market API Client - Bitcoin Trading Assistant
// Exports: getSchedulerStatus, getMarketGaps, getIndicators, getSignals,
//          getAlerts, createAlert, deleteAlert, checkAlerts,
//          getNews, getNewsSentiment
// =============================================================================

import type {
  SchedulerStatus,
  MarketGapsResponse,
  MarketIndicatorsResponse,
  MarketSignalsResponse,
  AlertItem,
  AlertCreate,
  AlertCheckResponse,
  NewsResponse,
  NewsSentimentSummary,
  DecisionResponse,
  BacktestConfig,
  BacktestResponse,
  HistoryLoadConfig,
  HistoryLoadResponse,
  HistoryRangeResponse,
  HistoryIntegrityResponse,
  VerificationRequest,
  VerificationResult,
  WalkForwardConfig,
  WalkForwardResult,
  InterestingDatesResponse,
  SentimentLoadConfig,
  SentimentLoadResponse,
  SentimentRangeResponse,
  SentimentAtDateResponse,
  SentimentCoverageResponse,
  RiskConfigItem,
  RiskConfigCreate,
  RiskEvaluation,
  RiskStatus,
  RecordLossResponse,
  PaperAccountItem,
  PaperStatus,
  PaperTickResult,
  PaperTradeListResponse,
  PaperMetrics,
  PaperExportResponse,
} from '../types';

import type {
  DiagnosticResponse,
  MissedOpportunitySummary,
  LeverageAnalysisResponse,
} from '../types/diagnostic';

// -----------------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------------

const getBaseUrl = (): string => {
  // Vite expose les variables d'env via import.meta.env
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && typeof envUrl === 'string' && envUrl.trim() !== '') {
    return envUrl.trim().replace(/\/$/, ''); // Remove trailing slash
  }
  return 'http://localhost:8000';
};

const BASE_URL = getBaseUrl();

// -----------------------------------------------------------------------------
// Generic fetch wrapper
// -----------------------------------------------------------------------------

interface FetchOptions {
  signal?: AbortSignal;
  /** Timeout en ms (défaut: 45s — assez pour les appels RSS lents du backend) */
  timeoutMs?: number;
}

// Timeout par défaut : 45 secondes
// Le backend peut prendre jusqu'à 30s si les 3 sources RSS timeout (10s chacune)
const DEFAULT_TIMEOUT_MS = 45_000;

async function apiFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;

  // Combiner le signal externe (ex: AbortController du hook) avec un timeout
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), timeoutMs);

  // Si un signal externe est fourni, on écoute aussi son abort
  if (options.signal) {
    options.signal.addEventListener('abort', () => timeoutController.abort());
  }

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
      signal: timeoutController.signal,
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      throw new Error(`API Error ${response.status}: ${errorText}`);
    }

    return response.json() as Promise<T>;
  } catch (err) {
    // Transformer le timeout en message lisible
    if (err instanceof Error && err.name === 'AbortError') {
      if (options.signal?.aborted) {
        // L'abort vient du composant (cleanup) — on le propage tel quel
        throw err;
      }
      // L'abort vient du timeout
      throw new Error(`Timeout après ${timeoutMs / 1000}s: ${endpoint}`);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

// -----------------------------------------------------------------------------
// Scheduler Status
// -----------------------------------------------------------------------------

export async function getSchedulerStatus(
  options: FetchOptions = {}
): Promise<SchedulerStatus> {
  return apiFetch<SchedulerStatus>('/scheduler/status', options);
}

// -----------------------------------------------------------------------------
// Market Gaps (Data Quality)
// -----------------------------------------------------------------------------

export interface GetMarketGapsParams {
  timeframe: string;
  days: number;
}

export async function getMarketGaps(
  params: GetMarketGapsParams,
  options: FetchOptions = {}
): Promise<MarketGapsResponse> {
  const { timeframe, days } = params;
  const endpoint = `/market/candles/gaps?timeframe=${encodeURIComponent(timeframe)}&days=${days}`;
  return apiFetch<MarketGapsResponse>(endpoint, options);
}

// -----------------------------------------------------------------------------
// Market Indicators
// -----------------------------------------------------------------------------

export interface GetIndicatorsParams {
  timeframe: string;
  historyDays: number;
  includeCandles?: boolean;
}

export async function getIndicators(
  params: GetIndicatorsParams,
  options: FetchOptions = {}
): Promise<MarketIndicatorsResponse> {
  const { timeframe, historyDays, includeCandles = false } = params;
  let endpoint = `/market/indicators?timeframe=${encodeURIComponent(timeframe)}&history_days=${historyDays}`;
  if (includeCandles) {
    endpoint += '&include_candles=true';
  }
  return apiFetch<MarketIndicatorsResponse>(endpoint, options);
}

// -----------------------------------------------------------------------------
// Market Signals
// -----------------------------------------------------------------------------

export interface GetSignalsParams {
  timeframe: string;
  historyDays: number;
}

export async function getSignals(
  params: GetSignalsParams,
  options: FetchOptions = {}
): Promise<MarketSignalsResponse> {
  const { timeframe, historyDays } = params;
  const endpoint = `/market/signals?timeframe=${encodeURIComponent(timeframe)}&history_days=${historyDays}`;
  return apiFetch<MarketSignalsResponse>(endpoint, options);
}

// -----------------------------------------------------------------------------
// Health Check (utilitaire bonus)
// -----------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
}

export async function getHealth(
  options: FetchOptions = {}
): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health', options);
}

export interface HealthDbResponse {
  database: string;
}

export async function getHealthDb(
  options: FetchOptions = {}
): Promise<HealthDbResponse> {
  return apiFetch<HealthDbResponse>('/health/db', options);
}

// -----------------------------------------------------------------------------
// Alerts CRUD
// -----------------------------------------------------------------------------

export async function getAlerts(
  options: FetchOptions = {}
): Promise<AlertItem[]> {
  return apiFetch<AlertItem[]>('/alerts', options);
}

export async function createAlert(
  data: AlertCreate,
  options: FetchOptions = {}
): Promise<AlertItem> {
  const url = `${BASE_URL}/alerts`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<AlertItem>;
}

export async function deleteAlert(
  alertId: number,
  options: FetchOptions = {}
): Promise<void> {
  const url = `${BASE_URL}/alerts/${alertId}`;
  const response = await fetch(url, {
    method: 'DELETE',
    signal: options.signal,
  });
  if (!response.ok && response.status !== 204) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
}

export async function checkAlerts(
  params: { timeframe: string },
  options: FetchOptions = {}
): Promise<AlertCheckResponse> {
  const url = `${BASE_URL}/alerts/check?timeframe=${encodeURIComponent(params.timeframe)}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<AlertCheckResponse>;
}

// -----------------------------------------------------------------------------
// News & Sentiment
// -----------------------------------------------------------------------------

export interface GetNewsParams {
  limit?: number;
  sentiment?: string;
}

export async function getNews(
  params: GetNewsParams = {},
  options: FetchOptions = {}
): Promise<NewsResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.sentiment) searchParams.set('sentiment', params.sentiment);
  const qs = searchParams.toString();
  const endpoint = `/news${qs ? `?${qs}` : ''}`;
  return apiFetch<NewsResponse>(endpoint, options);
}

export async function getNewsSentiment(
  options: FetchOptions = {}
): Promise<NewsSentimentSummary> {
  return apiFetch<NewsSentimentSummary>('/news/sentiment', options);
}

// -----------------------------------------------------------------------------
// Decision Engine
// -----------------------------------------------------------------------------

export interface GetDecisionParams {
  timeframe: string;
  historyDays: number;
}

export async function getDecision(
  params: GetDecisionParams,
  options: FetchOptions = {}
): Promise<DecisionResponse> {
  const { timeframe, historyDays } = params;
  const endpoint = `/market/decision?timeframe=${encodeURIComponent(timeframe)}&history_days=${historyDays}`;
  return apiFetch<DecisionResponse>(endpoint, options);
}

// -----------------------------------------------------------------------------
// Backtesting
// -----------------------------------------------------------------------------

export async function runBacktest(
  config: BacktestConfig,
  options: FetchOptions = {}
): Promise<BacktestResponse> {
  const url = `${BASE_URL}/backtest/run`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(config),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<BacktestResponse>;
}

// -----------------------------------------------------------------------------
// Verification Historique (Time-Travel Backtest)
// -----------------------------------------------------------------------------

export async function loadHistory(
  config: HistoryLoadConfig,
  options: FetchOptions = {}
): Promise<HistoryLoadResponse> {
  const url = `${BASE_URL}/backtest/history/load`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(config),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<HistoryLoadResponse>;
}

export async function getHistoryRange(
  params: { symbol?: string; timeframe?: string } = {},
  options: FetchOptions = {}
): Promise<HistoryRangeResponse> {
  const symbol = params.symbol || 'BTC/USD';
  const timeframe = params.timeframe || '1d';
  const endpoint = `/backtest/history/range?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`;
  return apiFetch<HistoryRangeResponse>(endpoint, options);
}

export async function getHistoryIntegrity(
  params: { symbol?: string; timeframe?: string } = {},
  options: FetchOptions = {}
): Promise<HistoryIntegrityResponse> {
  const symbol = params.symbol || 'BTC/USD';
  const timeframe = params.timeframe || '1d';
  const endpoint = `/backtest/history/integrity?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`;
  return apiFetch<HistoryIntegrityResponse>(endpoint, options);
}

export async function getInterestingDates(
  params: {
    symbol?: string;
    timeframe?: string;
    min_strength?: number;
    max_results?: number;
    step_days?: number;
  } = {},
  options: FetchOptions = {}
): Promise<InterestingDatesResponse> {
  const symbol = params.symbol || 'BTC/USD';
  const timeframe = params.timeframe || '1d';
  const minStrength = params.min_strength ?? 0.7;
  const maxResults = params.max_results ?? 20;
  const stepDays = params.step_days ?? 3.0;
  const endpoint = `/backtest/interesting-dates?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&min_strength=${minStrength}&max_results=${maxResults}&step_days=${stepDays}`;
  return apiFetch<InterestingDatesResponse>(endpoint, options);
}

export async function verifyAtDate(
  request: VerificationRequest,
  options: FetchOptions = {}
): Promise<VerificationResult> {
  const url = `${BASE_URL}/backtest/verify`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(request),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<VerificationResult>;
}

export async function runWalkForward(
  config: WalkForwardConfig,
  options: FetchOptions = {}
): Promise<WalkForwardResult> {
  const url = `${BASE_URL}/backtest/walk-forward`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(config),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<WalkForwardResult>;
}

// -----------------------------------------------------------------------------
// Sentiment Historique
// ----------------------------------------------------------------------------

export async function loadSentimentHistory(
  config: SentimentLoadConfig = {},
  options: FetchOptions = {}
): Promise<SentimentLoadResponse> {
  const url = `${BASE_URL}/sentiment/history/load`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(config),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<SentimentLoadResponse>;
}

export async function getSentimentRange(
  params: { source?: string } = {},
  options: FetchOptions = {}
): Promise<SentimentRangeResponse> {
  const source = params.source || 'fear_and_greed';
  const endpoint = `/sentiment/history/range?source=${encodeURIComponent(source)}`;
  return apiFetch<SentimentRangeResponse>(endpoint, options);
}

export async function getSentimentCoverage(
  options: FetchOptions = {}
): Promise<SentimentCoverageResponse> {
  return apiFetch<SentimentCoverageResponse>('/sentiment/history/coverage', options);
}

export async function getSentimentAtDate(
  params: { date: string; source?: string },
  options: FetchOptions = {}
): Promise<SentimentAtDateResponse> {
  const source = params.source || 'fear_and_greed';
  const endpoint = `/sentiment/history/at-date?date=${encodeURIComponent(params.date)}&source=${encodeURIComponent(source)}`;
  return apiFetch<SentimentAtDateResponse>(endpoint, options);
}

// -----------------------------------------------------------------------------
// Risk Management
// -----------------------------------------------------------------------------

export async function getRiskConfig(
  options: FetchOptions = {}
): Promise<RiskConfigItem> {
  return apiFetch<RiskConfigItem>('/risk/config', options);
}

export async function updateRiskConfig(
  data: RiskConfigCreate,
  options: FetchOptions = {}
): Promise<RiskConfigItem> {
  const url = `${BASE_URL}/risk/config`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<RiskConfigItem>;
}

export async function getRiskStatus(
  options: FetchOptions = {}
): Promise<RiskStatus> {
  return apiFetch<RiskStatus>('/risk/status', options);
}

export async function evaluateRisk(
  params: { action: string; price: number; atr?: number },
  options: FetchOptions = {}
): Promise<RiskEvaluation> {
  let endpoint = `/risk/evaluate?action=${encodeURIComponent(params.action)}&price=${params.price}`;
  if (params.atr) endpoint += `&atr=${params.atr}`;
  const url = `${BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<RiskEvaluation>;
}

export async function activateKillSwitch(
  reason: string = 'Activation manuelle',
  options: FetchOptions = {}
): Promise<RiskConfigItem> {
  const url = `${BASE_URL}/risk/kill-switch/activate?reason=${encodeURIComponent(reason)}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<RiskConfigItem>;
}

export async function deactivateKillSwitch(
  options: FetchOptions = {}
): Promise<RiskConfigItem> {
  const url = `${BASE_URL}/risk/kill-switch/deactivate`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<RiskConfigItem>;
}

export async function recordLoss(
  amount: number,
  options: FetchOptions = {}
): Promise<RecordLossResponse> {
  const url = `${BASE_URL}/risk/record-loss?amount=${amount}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<RecordLossResponse>;
}

export async function resetDailyLoss(
  options: FetchOptions = {}
): Promise<{ daily_loss_current: number; daily_limit_usd: number; kill_switch_active: boolean; message: string }> {
  const url = `${BASE_URL}/risk/reset-daily-loss`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json();
}

// -----------------------------------------------------------------------------
// Paper Trading
// -----------------------------------------------------------------------------

export async function getPaperAccount(
  options: FetchOptions = {}
): Promise<PaperAccountItem> {
  return apiFetch<PaperAccountItem>('/paper/account', options);
}

export async function createPaperAccount(
  config: { initial_capital?: number; max_open_duration_hours?: number; max_open_positions?: number } = {},
  options: FetchOptions = {}
): Promise<PaperAccountItem> {
  const url = `${BASE_URL}/paper/account`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(config),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<PaperAccountItem>;
}

export interface FullResetResponse {
  account: PaperAccountItem | null;
  purged: Record<string, number>;
  reset_details: string[];
  message: string;
}

export async function resetPaperAccount(
  config: { initial_capital?: number; max_open_duration_hours?: number; max_open_positions?: number } = {},
  options: FetchOptions = {}
): Promise<FullResetResponse> {
  const url = `${BASE_URL}/paper/account/reset`;
  // Confirmation obligatoire côté backend — on envoie confirm: "RESET"
  const body = {
    confirm: "RESET",
    ...config,
  };
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(body),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<FullResetResponse>;
}

export async function getPaperStatus(
  options: FetchOptions = {}
): Promise<PaperStatus> {
  return apiFetch<PaperStatus>('/paper/status', options);
}

export async function paperTick(
  options: FetchOptions = {}
): Promise<PaperTickResult> {
  const url = `${BASE_URL}/paper/tick`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<PaperTickResult>;
}

export async function getPaperTrades(
  params: { limit?: number; offset?: number; status?: string } = {},
  options: FetchOptions = {}
): Promise<PaperTradeListResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));
  if (params.status) searchParams.set('status', params.status);
  const qs = searchParams.toString();
  return apiFetch<PaperTradeListResponse>(`/paper/trades${qs ? `?${qs}` : ''}`, options);
}

export async function getPaperMetrics(
  options: FetchOptions = {}
): Promise<PaperMetrics> {
  return apiFetch<PaperMetrics>('/paper/metrics', options);
}

export async function getPaperTradesExport(
  options: FetchOptions = {}
): Promise<PaperExportResponse> {
  return apiFetch<PaperExportResponse>('/paper/trades/export', options);
}

export async function closePaperPosition(
  reason: string = 'Fermeture manuelle',
  options: FetchOptions = {}
): Promise<unknown> {
  const url = `${BASE_URL}/paper/close?reason=${encodeURIComponent(reason)}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json();
}

// -----------------------------------------------------------------------------
// Paper Trading — Journal d'Évaluation (v1.5)
// -----------------------------------------------------------------------------

import type {
  JournalResponse,
  TradingProfileResponse,
  TradingProfileParams,
  TradingStyleResult,
} from '../types';

export async function getPaperJournal(
  params: { date_from?: string; date_to?: string } = {},
  options: FetchOptions = {}
): Promise<JournalResponse> {
  const searchParams = new URLSearchParams();
  if (params.date_from) searchParams.set('date_from', params.date_from);
  if (params.date_to) searchParams.set('date_to', params.date_to);
  const qs = searchParams.toString();
  return apiFetch<JournalResponse>(`/paper/journal${qs ? `?${qs}` : ''}`, options);
}

export async function getPaperProfile(
  options: FetchOptions = {}
): Promise<TradingProfileResponse> {
  return apiFetch<TradingProfileResponse>('/paper/profile', options);
}

export async function setPaperProfile(
  profile: string,
  options: FetchOptions = {}
): Promise<TradingProfileResponse> {
  const url = `${BASE_URL}/paper/profile`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify({ profile }),
    signal: options.signal,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json() as Promise<TradingProfileResponse>;
}

export async function getPaperProfilePresets(
  options: FetchOptions = {}
): Promise<TradingProfileParams[]> {
  return apiFetch<TradingProfileParams[]>('/paper/profile/presets', options);
}

export async function getPaperStyle(
  options: FetchOptions = {}
): Promise<TradingStyleResult> {
  return apiFetch<TradingStyleResult>('/paper/style', options);
}

// ─────────────────────────────────────────────────────────────────────────────
// [v1.6] Diagnostic de fréquence
// ─────────────────────────────────────────────────────────────────────────────

export async function getPaperDiagnostic(
  params: { date_from?: string; date_to?: string } = {},
  options: FetchOptions = {}
): Promise<DiagnosticResponse> {
  const q = new URLSearchParams();
  if (params.date_from) q.set('date_from', params.date_from);
  if (params.date_to) q.set('date_to', params.date_to);
  const qs = q.toString() ? `?${q.toString()}` : '';
  return apiFetch<DiagnosticResponse>(`/paper/diagnostic${qs}`, options);
}

export async function getPaperMissedOpportunities(
  params: { date_from?: string; date_to?: string; lookforward_minutes?: number; min_move_pct?: number } = {},
  options: FetchOptions = {}
): Promise<MissedOpportunitySummary> {
  const q = new URLSearchParams();
  if (params.date_from) q.set('date_from', params.date_from);
  if (params.date_to) q.set('date_to', params.date_to);
  if (params.lookforward_minutes) q.set('lookforward_minutes', String(params.lookforward_minutes));
  if (params.min_move_pct) q.set('min_move_pct', String(params.min_move_pct));
  const qs = q.toString() ? `?${q.toString()}` : '';
  return apiFetch<MissedOpportunitySummary>(`/paper/missed-opportunities${qs}`, options);
}

export async function getPaperLeverageAnalysis(
  params: { date_from?: string; date_to?: string } = {},
  options: FetchOptions = {}
): Promise<LeverageAnalysisResponse> {
  const q = new URLSearchParams();
  if (params.date_from) q.set('date_from', params.date_from);
  if (params.date_to) q.set('date_to', params.date_to);
  const qs = q.toString() ? `?${q.toString()}` : '';
  return apiFetch<LeverageAnalysisResponse>(`/paper/leverage-analysis${qs}`, options);
}

// -----------------------------------------------------------------------------
// Audit — Run Value Audit (v1.9.3)
// -----------------------------------------------------------------------------

export interface RunValueAuditResponse {
  total_trades: number;
  cost_model: string;
  economic_audit: Record<string, unknown>;
  usefulness_audit: {
    total: number;
    categories: Record<string, { count: number; pct: number; avg_pnl_brut: number; avg_pnl_net: number; total_pnl_net: number }>;
    pct_useful: number;
    pct_insignificant: number;
    pct_churn: number;
    verdict: string;
  };
  pnl_bucket_distribution: {
    gross: Record<string, number>;
    net: Record<string, number>;
    dust_zone_pct: number;
  };
  signal_exit_audit: Record<string, unknown>;
  short_economics: {
    short_count: number;
    long_count?: number;
    gross_pnl?: number;
    net_pnl?: number;
    avg_pnl_gross?: number;
    avg_pnl_net?: number;
    avg_duration_min?: number;
    dominant_exit?: string;
    useful?: number;
    insignificant?: number;
    churn?: number;
    pct_useful?: number;
    verdict: string;
  };
}

export async function getRunValueAudit(
  costPreset: string = 'realistic',
  options: FetchOptions = {}
): Promise<RunValueAuditResponse> {
  return apiFetch<RunValueAuditResponse>(`/audit/run-value?cost_preset=${costPreset}`, options);
}

