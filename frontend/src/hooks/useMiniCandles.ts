// =============================================================================
// useMiniCandles — Bougies 1m BTC depuis Binance REST (dernière heure)
// =============================================================================
//
// Appelle directement l'API Binance publique (pas de clé API) pour récupérer
// ~60 bougies 1m (1h de données). Polling toutes les 30s.
//
// Données éphémères — pas de stockage en DB, uniquement pour le mini chart.
//
// [v2.0.27] Créé pour le mini chart temps réel sur l'onglet Trading.
// =============================================================================

import { useState, useEffect, useRef, useCallback } from 'react';

export interface MiniCandle {
  time: number;   // UTC timestamp en secondes
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface UseMiniCandlesReturn {
  candles: MiniCandle[];
  loading: boolean;
  error: string | null;
  lastUpdate: Date | null;
}

const BINANCE_KLINES_URL = 'https://api.binance.com/api/v3/klines';
const SYMBOL = 'BTCUSDT';
const INTERVAL = '1m';
const LIMIT = 60; // 60 bougies = 1 heure
const POLL_INTERVAL_MS = 30_000; // Refresh toutes les 30s

/**
 * Hook pour récupérer les bougies 1m BTC depuis Binance REST.
 * @param enabled - Ne poller que quand l'onglet Trading est visible
 */
export function useMiniCandles(options?: { enabled?: boolean }): UseMiniCandlesReturn {
  const enabled = options?.enabled !== false;

  const [candles, setCandles] = useState<MiniCandle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchCandles = useCallback(async () => {
    // Annuler le fetch précédent s'il est en cours
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      setLoading(prev => prev || candles.length === 0); // Loading seulement au premier chargement
      const url = `${BINANCE_KLINES_URL}?symbol=${SYMBOL}&interval=${INTERVAL}&limit=${LIMIT}`;
      const resp = await fetch(url, { signal: controller.signal });

      if (!resp.ok) {
        throw new Error(`Binance API ${resp.status}`);
      }

      const data = await resp.json();

      // Binance klines format:
      // [openTime, open, high, low, close, volume, closeTime, ...]
      const parsed: MiniCandle[] = data.map((k: unknown[]) => ({
        time: Math.floor(Number(k[0]) / 1000), // openTime ms → seconds
        open: parseFloat(k[1] as string),
        high: parseFloat(k[2] as string),
        low: parseFloat(k[3] as string),
        close: parseFloat(k[4] as string),
        volume: parseFloat(k[5] as string),
      }));

      setCandles(parsed);
      setError(null);
      setLastUpdate(new Date());
    } catch (e) {
      if ((e as Error).name === 'AbortError') return; // Annulé, ignore
      setError(e instanceof Error ? e.message : 'Erreur fetch klines');
    } finally {
      setLoading(false);
    }
  }, [candles.length]);

  useEffect(() => {
    if (!enabled) {
      // Nettoyer le polling quand désactivé
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }

    // Fetch immédiat
    fetchCandles();

    // Polling
    pollRef.current = setInterval(fetchCandles, POLL_INTERVAL_MS);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, [enabled, fetchCandles]);

  return { candles, loading, error, lastUpdate };
}

