// =============================================================================
// useIndicators - Hook for technical indicators (RSI, MACD, SMA, Bollinger)
// =============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import type { MarketIndicatorsResponse, FetchState } from '../types/api';
import { getIndicators } from '../api/marketApi';

export interface UseIndicatorsParams {
  timeframe: string;
  historyDays: number;
  includeCandles?: boolean;
}

export interface UseIndicatorsReturn extends FetchState<MarketIndicatorsResponse> {
  /** Manual refresh function */
  refresh: () => void;
}

export function useIndicators(
  params: UseIndicatorsParams
): UseIndicatorsReturn {
  const { timeframe, historyDays, includeCandles = false } = params;

  const [data, setData] = useState<MarketIndicatorsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Keep track of current params to avoid stale closures
  const paramsRef = useRef({ timeframe, historyDays, includeCandles });
  paramsRef.current = { timeframe, historyDays, includeCandles };

  const fetchIndicators = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await getIndicators(
        {
          timeframe: paramsRef.current.timeframe,
          historyDays: paramsRef.current.historyDays,
          includeCandles: paramsRef.current.includeCandles,
        },
        { signal }
      );
      setData(result);
      setError(null);
    } catch (err) {
      // Ignore abort errors
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      const message = err instanceof Error ? err.message : 'Failed to fetch indicators';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Manual refresh
  const refresh = useCallback(() => {
    setLoading(true);
    const controller = new AbortController();
    fetchIndicators(controller.signal);
  }, [fetchIndicators]);

  // Fetch on mount and when params change
  useEffect(() => {
    const controller = new AbortController();

    setLoading(true);
    setError(null);
    fetchIndicators(controller.signal);

    return () => {
      controller.abort();
    };
  }, [timeframe, historyDays, includeCandles, fetchIndicators]);

  return { data, loading, error, refresh };
}
