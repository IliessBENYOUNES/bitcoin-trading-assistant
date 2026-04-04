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
  VerificationRequest,
  VerificationResult,
  WalkForwardConfig,
  WalkForwardResult,
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
}

async function apiFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
    signal: options.signal,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }

  return response.json() as Promise<T>;
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

