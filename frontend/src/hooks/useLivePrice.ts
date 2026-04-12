// =============================================================================
// useLivePrice — Real-time BTC price via Binance WebSocket
// =============================================================================
//
// Utilise le WebSocket public Binance (pas de clé API) pour recevoir
// le prix BTC en temps réel (~1 update/seconde).
//
// Endpoint : wss://stream.binance.com:9443/ws/btcusdt@ticker
//
// [v2.0.15] Fallback REST API :
// Si le WebSocket ne se connecte pas dans les 5 secondes,
// un polling REST vers /market/price est activé (toutes les 10s).
// Cela évite d'afficher un prix stale (dernière bougie en DB).
//
// Retourne :
// - price        : prix actuel en USD
// - previousPrice: prix précédent (pour animation flash)
// - change24h    : variation 24h en %
// - high24h      : plus haut 24h
// - low24h       : plus bas 24h
// - volume24h    : volume 24h en BTC
// - connected    : état de la connexion WebSocket
// - source       : 'websocket' | 'rest' | null — d'où vient le prix
// =============================================================================

import { useState, useEffect, useRef, useCallback } from 'react';

interface LivePriceData {
  price: number | null;
  previousPrice: number | null;
  change24h: number | null;
  high24h: number | null;
  low24h: number | null;
  volume24h: number | null;
  connected: boolean;
  source: 'websocket' | 'rest' | null;
}

// Binance 24hr mini ticker : champs utiles
// https://binance-docs.github.io/apidocs/spot/en/#individual-symbol-ticker-streams
interface BinanceTickerEvent {
  e: string;   // Event type ("24hrTicker")
  s: string;   // Symbol ("BTCUSDT")
  c: string;   // Last price
  o: string;   // Open price (24h)
  h: string;   // High price (24h)
  l: string;   // Low price (24h)
  v: string;   // Total traded base asset volume (24h)
  P: string;   // Price change percent (24h)
}

const BINANCE_WS_URL = 'wss://stream.binance.com:9443/ws/btcusdt@ticker';
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 10;

// Throttle : ne déclencher un re-render que toutes les N ms
// Le WebSocket envoie ~1 update/sec, on limite à 1 re-render/2s
// pour éviter de re-render le Dashboard trop souvent
const THROTTLE_MS = 2000;

// [v2.0.15] REST API fallback settings
const REST_FALLBACK_DELAY_MS = 5000;  // Délai avant d'activer le fallback REST
const REST_POLL_INTERVAL_MS = 10000;  // Polling REST toutes les 10s

function getApiBaseUrl(): string {
  try {
    // Vite expose les variables d'env via import.meta.env
    const envUrl = import.meta.env.VITE_API_BASE_URL;
    if (envUrl && typeof envUrl === 'string' && envUrl.trim() !== '') {
      return envUrl.trim().replace(/\/$/, '');
    }
  } catch {
    // Fallback si import.meta.env n'est pas disponible
  }
  return 'http://localhost:8000';
}

export function useLivePrice(options?: { enabled?: boolean }): LivePriceData {
  const enabled = options?.enabled !== false; // activé par défaut

  // Un seul state objet pour batcher les updates en un seul re-render
  const [state, setState] = useState<LivePriceData>({
    price: null,
    previousPrice: null,
    change24h: null,
    high24h: null,
    low24h: null,
    volume24h: null,
    connected: false,
    source: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPriceRef = useRef<number | null>(null);
  // Throttle : stocker le dernier update et l'appliquer périodiquement
  const pendingUpdateRef = useRef<Partial<LivePriceData> | null>(null);
  const throttleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // [v2.0.15] REST fallback refs
  const restPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const restFallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wsConnectedRef = useRef(false);

  // [v2.0.15] Fetch prix via REST API (/market/price)
  const fetchRestPrice = useCallback(async () => {
    // Ne pas fetcher en REST si le WebSocket est connecté
    if (wsConnectedRef.current) return;
    try {
      const baseUrl = getApiBaseUrl();
      const resp = await fetch(`${baseUrl}/market/price?symbol=BTC/USD`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!resp.ok) return;
      const data = await resp.json();
      const price = data?.price;
      if (typeof price === 'number' && price > 0) {
        const update: Partial<LivePriceData> = { source: 'rest' };
        if (lastPriceRef.current !== null && lastPriceRef.current !== price) {
          update.previousPrice = lastPriceRef.current;
        }
        lastPriceRef.current = price;
        update.price = price;
        // Récupérer les stats 24h si disponibles
        if (data.change_24h_pct != null) update.change24h = data.change_24h_pct;
        if (data.high_24h != null) update.high24h = data.high_24h;
        if (data.low_24h != null) update.low24h = data.low_24h;
        if (data.volume_24h != null) update.volume24h = data.volume_24h;
        setState(prev => ({ ...prev, ...update }));
      }
    } catch {
      // Silencieux — le REST est un fallback best-effort
    }
  }, []);

  // [v2.0.15] Démarre le polling REST si le WS n'est pas connecté après le délai
  const startRestFallback = useCallback(() => {
    if (restPollRef.current) return; // déjà en cours
    // Fetch immédiat + polling
    fetchRestPrice();
    restPollRef.current = setInterval(fetchRestPrice, REST_POLL_INTERVAL_MS);
    console.log('[useLivePrice] REST fallback activated (WS not connected)');
  }, [fetchRestPrice]);

  const stopRestFallback = useCallback(() => {
    if (restPollRef.current) {
      clearInterval(restPollRef.current);
      restPollRef.current = null;
    }
    if (restFallbackTimerRef.current) {
      clearTimeout(restFallbackTimerRef.current);
      restFallbackTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    // Éviter les connexions multiples
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      const ws = new WebSocket(BINANCE_WS_URL);

      ws.onopen = () => {
        wsConnectedRef.current = true;
        setState(prev => ({ ...prev, connected: true, source: 'websocket' }));
        reconnectAttempts.current = 0;
        // [v2.0.15] WS connecté → arrêter le fallback REST
        stopRestFallback();
        console.log('[useLivePrice] WebSocket connected to Binance');
      };

      ws.onmessage = (event) => {
        try {
          const data: BinanceTickerEvent = JSON.parse(event.data);

          const newPrice = parseFloat(data.c);
          const pct = parseFloat(data.P);
          const h = parseFloat(data.h);
          const l = parseFloat(data.l);
          const v = parseFloat(data.v);

          // Construire l'update en attente
          const update: Partial<LivePriceData> = { source: 'websocket' };

          if (!isNaN(newPrice) && newPrice > 0) {
            if (lastPriceRef.current !== null && lastPriceRef.current !== newPrice) {
              update.previousPrice = lastPriceRef.current;
            }
            lastPriceRef.current = newPrice;
            update.price = newPrice;
          }
          if (!isNaN(pct)) update.change24h = pct;
          if (!isNaN(h)) update.high24h = h;
          if (!isNaN(l)) update.low24h = l;
          if (!isNaN(v)) update.volume24h = v;

          // Accumuler l'update (throttle)
          pendingUpdateRef.current = { ...pendingUpdateRef.current, ...update };

          // Déclencher un re-render throttlé
          if (!throttleTimerRef.current) {
            throttleTimerRef.current = setTimeout(() => {
              const pending = pendingUpdateRef.current;
              if (pending) {
                setState(prev => ({ ...prev, ...pending }));
                pendingUpdateRef.current = null;
              }
              throttleTimerRef.current = null;
            }, THROTTLE_MS);
          }
        } catch {
          // Ignorer les messages invalides
        }
      };

      ws.onclose = () => {
        wsConnectedRef.current = false;
        setState(prev => ({ ...prev, connected: false }));
        wsRef.current = null;

        // Auto-reconnexion avec backoff
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_DELAY_MS * Math.pow(1.5, reconnectAttempts.current);
          reconnectAttempts.current += 1;
          console.log(`[useLivePrice] Reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttempts.current})`);
          reconnectTimer.current = setTimeout(connect, delay);
        }

        // [v2.0.15] Lancer le REST fallback immédiatement à la déconnexion
        if (!restPollRef.current) {
          startRestFallback();
        }
      };

      ws.onerror = () => {
        // onclose sera appelé après onerror
        ws.close();
      };

      wsRef.current = ws;
    } catch {
      console.error('[useLivePrice] Failed to create WebSocket');
    }
  }, [stopRestFallback, startRestFallback]);

  useEffect(() => {
    if (!enabled) {
      // Mode low-bandwidth : ne pas connecter le WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      wsConnectedRef.current = false;
      stopRestFallback();
      setState(prev => ({ ...prev, connected: false, source: null }));
      return;
    }

    connect();

    // [v2.0.15] Programmer le fallback REST si le WS n'est pas connecté après le délai
    restFallbackTimerRef.current = setTimeout(() => {
      if (!wsConnectedRef.current) {
        startRestFallback();
      }
    }, REST_FALLBACK_DELAY_MS);

    return () => {
      // Cleanup à l'unmount
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (throttleTimerRef.current) {
        clearTimeout(throttleTimerRef.current);
      }
      stopRestFallback();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, enabled, startRestFallback, stopRestFallback]);

  return state;
}

