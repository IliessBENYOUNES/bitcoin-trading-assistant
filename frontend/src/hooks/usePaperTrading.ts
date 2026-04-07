// Hook usePaperTrading — gestion du paper trading (statut, tick, trades, métriques)
import { useState, useEffect, useCallback, useRef } from 'react';
import type { PaperStatus, PaperTickResult, PaperTradeItem } from '../types';
import {
  getPaperStatus,
  paperTick,
  getPaperTrades,
  createPaperAccount,
  resetPaperAccount,
  closePaperPosition,
} from '../api/marketApi';

interface UsePaperTradingParams {
  /** Polling interval in ms for status refresh (0 = disabled) */
  pollInterval?: number;
}

interface UsePaperTradingReturn {
  status: PaperStatus | null;
  trades: PaperTradeItem[];
  totalTrades: number;
  loading: boolean;
  error: string | null;
  lastTick: PaperTickResult | null;
  refresh: () => void;
  activate: (capital?: number) => Promise<void>;
  reset: (capital?: number) => Promise<void>;
  manualTick: () => Promise<PaperTickResult | null>;
  closePosition: (reason?: string) => Promise<void>;
}

export function usePaperTrading({
  pollInterval = 0,
}: UsePaperTradingParams = {}): UsePaperTradingReturn {
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [trades, setTrades] = useState<PaperTradeItem[]>([]);
  const [totalTrades, setTotalTrades] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastTick, setLastTick] = useState<PaperTickResult | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusData, tradesData] = await Promise.all([
        getPaperStatus(),
        getPaperTrades({ limit: 50, status: 'closed' }),
      ]);
      setStatus(statusData);
      setTrades(tradesData.trades);
      setTotalTrades(tradesData.total);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // Polling
  useEffect(() => {
    if (pollInterval <= 0) return;
    intervalRef.current = setInterval(fetchAll, pollInterval);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchAll, pollInterval]);

  const activate = useCallback(async (capital: number = 10000) => {
    try {
      await createPaperAccount({ initial_capital: capital });
      await fetchAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur activation');
    }
  }, [fetchAll]);

  const reset = useCallback(async (capital: number = 10000) => {
    try {
      await resetPaperAccount({ initial_capital: capital });
      setLastTick(null);
      await fetchAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur reset');
    }
  }, [fetchAll]);

  const manualTick = useCallback(async (): Promise<PaperTickResult | null> => {
    try {
      const result = await paperTick();
      setLastTick(result);
      await fetchAll();
      return result;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur tick');
      return null;
    }
  }, [fetchAll]);

  const closePosition = useCallback(async (reason: string = 'Fermeture manuelle') => {
    try {
      await closePaperPosition(reason);
      await fetchAll();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur fermeture');
    }
  }, [fetchAll]);

  return {
    status,
    trades,
    totalTrades,
    loading,
    error,
    lastTick,
    refresh: fetchAll,
    activate,
    reset,
    manualTick,
    closePosition,
  };
}

