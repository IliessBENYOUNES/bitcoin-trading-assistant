// =============================================================================
// useMarketGaps - Hook for data quality (freshness + completeness)
// =============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import type { MarketGapsResponse, FetchState } from '../types';
import { getMarketGaps } from '../api/marketApi';

export interface UseMarketGapsParams {
  timeframe: string;
  days: number;
}

export interface UseMarketGapsReturn extends FetchState<MarketGapsResponse> {
  /** Manual refresh function */
  refresh: () => void;
}

export function useMarketGaps(
  params: UseMarketGapsParams
): UseMarketGapsReturn {
  const { timeframe, days } = params;

  const [data, setData] = useState<MarketGapsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Keep track of current params to avoid stale closures
  const paramsRef = useRef({ timeframe, days });
  paramsRef.current = { timeframe, days };

  const fetchGaps = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await getMarketGaps(
        {
          timeframe: paramsRef.current.timeframe,
          days: paramsRef.current.days,
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
      const message = err instanceof Error ? err.message : 'Failed to fetch market gaps';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Manual refresh
  const refresh = useCallback(() => {
    setLoading(true);
    const controller = new AbortController();
    fetchGaps(controller.signal);
  }, [fetchGaps]);

  // Fetch on mount and when params change
  useEffect(() => {
    const controller = new AbortController();

    setLoading(true);
    setError(null);
    fetchGaps(controller.signal);

    return () => {
      controller.abort();
    };
  }, [timeframe, days, fetchGaps]);

  return { data, loading, error, refresh };
}
