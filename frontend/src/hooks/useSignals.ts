// =============================================================================
// useSignals - Hook for trading signals (interpretation of indicators)
// =============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import type { MarketSignalsResponse, FetchState } from '../types/api';
import { getSignals } from '../api/marketApi';

export interface UseSignalsParams {
  timeframe: string;
  historyDays: number;
}

export interface UseSignalsReturn extends FetchState<MarketSignalsResponse> {
  /** Manual refresh function */
  refresh: () => void;
}

export function useSignals(
  params: UseSignalsParams
): UseSignalsReturn {
  const { timeframe, historyDays } = params;

  const [data, setData] = useState<MarketSignalsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Keep track of current params to avoid stale closures
  const paramsRef = useRef({ timeframe, historyDays });
  paramsRef.current = { timeframe, historyDays };

  const fetchSignals = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await getSignals(
        {
          timeframe: paramsRef.current.timeframe,
          historyDays: paramsRef.current.historyDays,
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
      const message = err instanceof Error ? err.message : 'Failed to fetch signals';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Manual refresh
  const refresh = useCallback(() => {
    setLoading(true);
    const controller = new AbortController();
    fetchSignals(controller.signal);
  }, [fetchSignals]);

  // Fetch on mount and when params change
  useEffect(() => {
    const controller = new AbortController();

    setLoading(true);
    setError(null);
    fetchSignals(controller.signal);

    return () => {
      controller.abort();
    };
  }, [timeframe, historyDays, fetchSignals]);

  return { data, loading, error, refresh };
}

