// =============================================================================
// useLivePrice — Real-time BTC price via Binance WebSocket
// =============================================================================
//
// Utilise le WebSocket public Binance (pas de clé API) pour recevoir
// le prix BTC en temps réel (~1 update/seconde).
//
// Endpoint : wss://stream.binance.com:9443/ws/btcusdt@ticker
//
// Retourne :
// - price        : prix actuel en USD
// - previousPrice: prix précédent (pour animation flash)
// - change24h    : variation 24h en %
// - high24h      : plus haut 24h
// - low24h       : plus bas 24h
// - volume24h    : volume 24h en BTC
// - connected    : état de la connexion WebSocket
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
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPriceRef = useRef<number | null>(null);
  // Throttle : stocker le dernier update et l'appliquer périodiquement
  const pendingUpdateRef = useRef<Partial<LivePriceData> | null>(null);
  const throttleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    // Éviter les connexions multiples
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      const ws = new WebSocket(BINANCE_WS_URL);

      ws.onopen = () => {
        setState(prev => ({ ...prev, connected: true }));
        reconnectAttempts.current = 0;
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
          const update: Partial<LivePriceData> = {};

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
        setState(prev => ({ ...prev, connected: false }));
        wsRef.current = null;

        // Auto-reconnexion avec backoff
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_DELAY_MS * Math.pow(1.5, reconnectAttempts.current);
          reconnectAttempts.current += 1;
          console.log(`[useLivePrice] Reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttempts.current})`);
          reconnectTimer.current = setTimeout(connect, delay);
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
  }, []);

  useEffect(() => {
    if (!enabled) {
      // Mode low-bandwidth : ne pas connecter le WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setState(prev => ({ ...prev, connected: false }));
      return;
    }

    connect();

    return () => {
      // Cleanup à l'unmount
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (throttleTimerRef.current) {
        clearTimeout(throttleTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, enabled]);

  return state;
}

