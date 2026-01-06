/**
 * Client API pour communiquer avec le backend FastAPI.
 *
 * Utilise Axios pour les requêtes HTTP.
 * Le proxy Vite redirige /api vers localhost:8000.
 */

import axios from 'axios';
import type {
  CandleListResponse,
  PriceResponse,
  MarketInfo,
  FetchResponse,
  HealthResponse,
  HealthDbResponse,
  GapsResponse
} from '../types';

// Instance Axios configurée
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * API Health Check
 */
export const healthApi = {
  check: async (): Promise<HealthResponse> => {
    const response = await api.get<HealthResponse>('/health');
    return response.data;
  },

  checkDb: async (): Promise<HealthDbResponse> => {
    const response = await api.get<HealthDbResponse>('/health/db');
    return response.data;
  },
};

/**
 * API Market Data
 */
export const marketApi = {
  // Récupère les chandeliers avec filtrage rolling optionnel
  getCandles: async (
      symbol: string = 'BTC/USD',
      timeframe: string = '4h',
      limit: number = 100,
      days?: number  // Nouveau paramètre optionnel
  ): Promise<CandleListResponse> => {
    const params: Record<string, string | number> = { symbol, timeframe, limit };
    if (days) {
      params.days = days;
    }
    const response = await api.get<CandleListResponse>('/market/candles', { params });
    return response.data;
  },

  // Récupère les données depuis CoinGecko et les stocke
  fetchCandles: async (
      symbol: string = 'BTC/USD',
      days: number = 7
  ): Promise<FetchResponse> => {
    const response = await api.post<FetchResponse>('/market/candles/fetch', null, {
      params: { symbol, days },
    });
    return response.data;
  },

  // Détecte les trous dans les données
  detectGaps: async (
      symbol: string = 'BTC/USD',
      timeframe: string = '4h',
      days: number = 7
  ): Promise<GapsResponse> => {
    const response = await api.get<GapsResponse>('/market/candles/gaps', {
      params: { symbol, timeframe, days },
    });
    return response.data;
  },

  // Récupère le prix actuel
  getPrice: async (symbol: string = 'BTC/USD'): Promise<PriceResponse> => {
    const response = await api.get<PriceResponse>('/market/price', {
      params: { symbol },
    });
    return response.data;
  },

  // Récupère les informations de marché complètes
  getMarketInfo: async (symbol: string = 'BTC/USD'): Promise<MarketInfo> => {
    const response = await api.get<MarketInfo>('/market/info', {
      params: { symbol },
    });
    return response.data;
  },
};

export default api;