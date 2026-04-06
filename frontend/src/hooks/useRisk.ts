// =============================================================================
// useRisk - Hook for Risk Management Engine
// Provides risk config, status, kill switch control, and config updates
// =============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import type { RiskConfigItem, RiskConfigCreate, RiskStatus } from '../types';
import {
  getRiskConfig,
  updateRiskConfig,
  getRiskStatus,
  activateKillSwitch,
  deactivateKillSwitch,
} from '../api/marketApi';

export interface UseRiskReturn {
  config: RiskConfigItem | null;
  status: RiskStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
  updateConfig: (data: RiskConfigCreate) => Promise<void>;
  toggleKillSwitch: (activate: boolean, reason?: string) => Promise<void>;
}

export function useRisk(): UseRiskReturn {
  const [config, setConfig] = useState<RiskConfigItem | null>(null);
  const [status, setStatus] = useState<RiskStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchAll = useCallback(async (signal?: AbortSignal) => {
    try {
      const [configData, statusData] = await Promise.all([
        getRiskConfig({ signal }),
        getRiskStatus({ signal }),
      ]);
      setConfig(configData);
      setStatus(statusData);
      setError(null);
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      const message = err instanceof Error ? err.message : 'Erreur risk engine';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(() => {
    setLoading(true);
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    fetchAll(controller.signal);
  }, [fetchAll]);

  const updateConfigHandler = useCallback(async (data: RiskConfigCreate) => {
    try {
      const updated = await updateRiskConfig(data);
      setConfig(updated);
      // Refresh status after config change
      const statusData = await getRiskStatus();
      setStatus(statusData);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erreur mise à jour config';
      setError(message);
      throw err;
    }
  }, []);

  const toggleKillSwitch = useCallback(async (activate: boolean, reason?: string) => {
    try {
      if (activate) {
        await activateKillSwitch(reason || 'Activation manuelle');
      } else {
        await deactivateKillSwitch();
      }
      // Refresh everything
      refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erreur kill switch';
      setError(message);
      throw err;
    }
  }, [refresh]);

  // Initial fetch
  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    fetchAll(controller.signal);
    return () => controller.abort();
  }, [fetchAll]);

  return {
    config,
    status,
    loading,
    error,
    refresh,
    updateConfig: updateConfigHandler,
    toggleKillSwitch,
  };
}

