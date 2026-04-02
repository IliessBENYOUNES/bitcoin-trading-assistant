// =============================================================================
// Hook useNews — Fetch des news crypto avec sentiment et polling
// =============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import type { NewsResponse } from '../types';
import { getNews } from '../api/marketApi';

export interface UseNewsParams {
  limit?: number;
  pollInterval?: number; // en ms, 0 = pas de polling
}

export interface UseNewsResult {
  data: NewsResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useNews({ limit = 20, pollInterval = 0 }: UseNewsParams = {}): UseNewsResult {
  const [data, setData] = useState<NewsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchNews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getNews({ limit });
      setData(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur lors du chargement des news');
    } finally {
      setLoading(false);
    }
  }, [limit]);

  // Fetch initial
  useEffect(() => {
    void fetchNews();
  }, [fetchNews]);

  // Polling optionnel
  useEffect(() => {
    if (pollInterval > 0) {
      intervalRef.current = setInterval(() => {
        void fetchNews();
      }, pollInterval);
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
      };
    }
  }, [pollInterval, fetchNews]);

  return {
    data,
    loading,
    error,
    refresh: fetchNews,
  };
}

