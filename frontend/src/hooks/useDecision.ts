// =============================================================================
// useDecision - Hook for decision engine (combined signals + sentiment → scenarios)
// =============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import type { DecisionResponse, FetchState } from '../types';
import { getDecision } from '../api/marketApi';

export interface UseDecisionParams {
  timeframe: string;
  historyDays: number;
}

export interface UseDecisionReturn extends FetchState<DecisionResponse> {
  /** Manual refresh function */
  refresh: () => void;
}

export function useDecision(
  params: UseDecisionParams
): UseDecisionReturn {
  const { timeframe, historyDays } = params;

  const [data, setData] = useState<DecisionResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Keep track of current params to avoid stale closures
  const paramsRef = useRef({ timeframe, historyDays });
  paramsRef.current = { timeframe, historyDays };

  const fetchDecision = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await getDecision(
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
      const message = err instanceof Error ? err.message : 'Failed to fetch decision';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Manual refresh
  const refresh = useCallback(() => {
    setLoading(true);
    const controller = new AbortController();
    fetchDecision(controller.signal);
  }, [fetchDecision]);

  // Fetch on mount and when params change
  useEffect(() => {
    const controller = new AbortController();

    setLoading(true);
    setError(null);
    fetchDecision(controller.signal);

    return () => {
      controller.abort();
    };
  }, [timeframe, historyDays, fetchDecision]);

  return { data, loading, error, refresh };
}

