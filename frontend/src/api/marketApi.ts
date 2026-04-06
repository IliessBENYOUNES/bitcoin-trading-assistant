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
} from '../types';

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

