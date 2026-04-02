import { useState, useEffect, useCallback, useRef } from 'react';
import type { AlertItem, AlertCheckResponse, AlertNotification } from '../types/api';
import { getAlerts, createAlert, deleteAlert, checkAlerts } from '../api/marketApi';
import type { AlertCreate } from '../types/api';

interface UseAlertsParams {
  timeframe: string;
  /** Polling interval in ms for checking alerts (0 = disabled) */
  pollInterval?: number;
}

interface UseAlertsReturn {
  alerts: AlertItem[];
  notifications: AlertNotification[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
  add: (data: AlertCreate) => Promise<void>;
  remove: (id: number) => Promise<void>;
  check: () => Promise<AlertCheckResponse | null>;
  dismissNotifications: () => void;
}

export function useAlerts({ timeframe, pollInterval = 0 }: UseAlertsParams): UseAlertsReturn {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [notifications, setNotifications] = useState<AlertNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAlerts();
      setAlerts(data);
    } catch (err: any) {
      setError(err.message ?? 'Erreur');
    } finally {
      setLoading(false);
    }
  }, []);

  const add = useCallback(async (data: AlertCreate) => {
    await createAlert(data);
    await fetchAlerts();
  }, [fetchAlerts]);

  const remove = useCallback(async (id: number) => {
    await deleteAlert(id);
    await fetchAlerts();
  }, [fetchAlerts]);

  const check = useCallback(async (): Promise<AlertCheckResponse | null> => {
    try {
      const result = await checkAlerts({ timeframe });
      if (result.notifications.length > 0) {
        setNotifications(prev => [...result.notifications, ...prev]);
      }
      // Refresh list to get updated statuses
      await fetchAlerts();
      return result;
    } catch {
      return null;
    }
  }, [timeframe, fetchAlerts]);

  const dismissNotifications = useCallback(() => {
    setNotifications([]);
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Polling
  useEffect(() => {
    if (pollInterval > 0) {
      intervalRef.current = setInterval(() => {
        check();
      }, pollInterval);
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
      };
    }
  }, [pollInterval, check]);

  return {
    alerts,
    notifications,
    loading,
    error,
    refresh: fetchAlerts,
    add,
    remove,
    check,
    dismissNotifications,
  };
}

