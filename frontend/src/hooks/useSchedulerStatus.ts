// =============================================================================
// useSchedulerStatus - Polling hook for scheduler status
// =============================================================================

import { useState, useEffect, useCallback } from 'react';
import type { SchedulerStatus, FetchState } from '../types/api';
import { getSchedulerStatus } from '../api/marketApi';

// Polling interval en ms (15s par défaut, configurable)
const POLLING_INTERVAL_MS = 15_000;

export interface UseSchedulerStatusOptions {
  /** Enable/disable polling (default: true) */
  polling?: boolean;
  /** Polling interval in ms (default: 15000) */
  intervalMs?: number;
}

export interface UseSchedulerStatusReturn extends FetchState<SchedulerStatus> {
  /** Manual refresh function */
  refresh: () => void;
}

export function useSchedulerStatus(
  options: UseSchedulerStatusOptions = {}
): UseSchedulerStatusReturn {
  const { polling = true, intervalMs = POLLING_INTERVAL_MS } = options;

  const [data, setData] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await getSchedulerStatus({ signal });
      setData(result);
      setError(null);
    } catch (err) {
      // Ignore abort errors (component unmounted)
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      const message = err instanceof Error ? err.message : 'Failed to fetch scheduler status';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Manual refresh (without setting loading to avoid UI flicker)
  const refresh = useCallback(() => {
    const controller = new AbortController();
    fetchStatus(controller.signal);
    // Note: no cleanup here, it's a one-shot manual refresh
  }, [fetchStatus]);

  useEffect(() => {
    const controller = new AbortController();

    // Initial fetch
    setLoading(true);
    fetchStatus(controller.signal);

    // Polling
    let intervalId: ReturnType<typeof setInterval> | null = null;
    if (polling) {
      intervalId = setInterval(() => {
        // Create new controller for each poll (don't reuse aborted one)
        const pollController = new AbortController();
        fetchStatus(pollController.signal);
      }, intervalMs);
    }

    // Cleanup
    return () => {
      controller.abort();
      if (intervalId !== null) {
        clearInterval(intervalId);
      }
    };
  }, [fetchStatus, polling, intervalMs]);

  return { data, loading, error, refresh };
}
