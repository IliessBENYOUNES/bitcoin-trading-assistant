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

export function useLivePrice(): LivePriceData {
  const [price, setPrice] = useState<number | null>(null);
  const [previousPrice, setPreviousPrice] = useState<number | null>(null);
  const [change24h, setChange24h] = useState<number | null>(null);
  const [high24h, setHigh24h] = useState<number | null>(null);
  const [low24h, setLow24h] = useState<number | null>(null);
  const [volume24h, setVolume24h] = useState<number | null>(null);
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPriceRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    // Éviter les connexions multiples
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      const ws = new WebSocket(BINANCE_WS_URL);

      ws.onopen = () => {
        setConnected(true);
        reconnectAttempts.current = 0;
        console.log('[useLivePrice] WebSocket connected to Binance');
      };

      ws.onmessage = (event) => {
        try {
          const data: BinanceTickerEvent = JSON.parse(event.data);

          const newPrice = parseFloat(data.c);
          if (!isNaN(newPrice) && newPrice > 0) {
            // Stocker l'ancien prix pour l'animation flash
            if (lastPriceRef.current !== null && lastPriceRef.current !== newPrice) {
              setPreviousPrice(lastPriceRef.current);
            }
            lastPriceRef.current = newPrice;
            setPrice(newPrice);
          }

          const pct = parseFloat(data.P);
          if (!isNaN(pct)) setChange24h(pct);

          const h = parseFloat(data.h);
          if (!isNaN(h)) setHigh24h(h);

          const l = parseFloat(data.l);
          if (!isNaN(l)) setLow24h(l);

          const v = parseFloat(data.v);
          if (!isNaN(v)) setVolume24h(v);
        } catch {
          // Ignorer les messages invalides
        }
      };

      ws.onclose = () => {
        setConnected(false);
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
    connect();

    return () => {
      // Cleanup à l'unmount
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    price,
    previousPrice,
    change24h,
    high24h,
    low24h,
    volume24h,
    connected,
  };
}

