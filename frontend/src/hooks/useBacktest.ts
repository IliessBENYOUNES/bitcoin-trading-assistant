// =============================================================================
// useBacktest - Hook for backtesting engine
// =============================================================================

import { useState, useCallback } from 'react';
import type { BacktestResponse, BacktestConfig } from '../types';
import { runBacktest } from '../api/marketApi';

export interface UseBacktestReturn {
  data: BacktestResponse | null;
  loading: boolean;
  error: string | null;
  launch: (config: BacktestConfig) => void;
  reset: () => void;
}

export function useBacktest(): UseBacktestReturn {
  const [data, setData] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const launch = useCallback(async (config: BacktestConfig) => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const result = await runBacktest(config);
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erreur backtest';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { data, loading, error, launch, reset };
}

