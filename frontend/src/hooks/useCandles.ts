import { useState, useEffect, useCallback, useRef } from 'react';
import type { Candle } from '../types';

interface UseCandlesParams {
    timeframe: string;
    days: number;
}

interface UseCandlesResult {
    candles: Candle[];
    loading: boolean;
    error: string | null;
    refresh: () => void;
}

export function useCandles({ timeframe, days }: UseCandlesParams): UseCandlesResult {
    const [candles, setCandles] = useState<Candle[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [refreshKey, setRefreshKey] = useState(0);
    const abortRef = useRef<AbortController | null>(null);

    const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

    useEffect(() => {
        setCandles([]);
        setError(null);

        if (abortRef.current) {
            abortRef.current.abort();
        }

        const controller = new AbortController();
        abortRef.current = controller;

        const fetchData = async () => {
            setLoading(true);

            try {
                const baseUrl = (
                    import.meta.env.VITE_API_BASE_URL as string | undefined
                )?.replace(/\/+$/, '') || 'http://localhost:8000';

                const url = `${baseUrl}/market/candles?timeframe=${encodeURIComponent(timeframe)}&days=${days}`;

                console.log('[useCandles] Fetching:', url);

                const res = await fetch(url, { signal: controller.signal });

                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
                }

                const data = await res.json();

                // DEBUG: Afficher la structure de la réponse
                console.log('[useCandles] Raw response type:', typeof data);
                console.log('[useCandles] Raw response:', JSON.stringify(data).slice(0, 500));

                if (controller.signal.aborted) return;

                // Extraire le tableau de candles selon le format de réponse
                let candlesArray: Candle[] = [];

                if (Array.isArray(data)) {
                    // Réponse directe en tableau
                    candlesArray = data;
                } else if (data && typeof data === 'object') {
                    // Réponse en objet - chercher le tableau
                    if (Array.isArray(data.candles)) {
                        candlesArray = data.candles;
                    } else if (Array.isArray(data.data)) {
                        candlesArray = data.data;
                    } else if (Array.isArray(data.items)) {
                        candlesArray = data.items;
                    } else if (Array.isArray(data.results)) {
                        candlesArray = data.results;
                    } else {
                        // Dernière tentative: chercher la première propriété qui est un tableau
                        for (const key of Object.keys(data)) {
                            if (Array.isArray(data[key])) {
                                console.log(`[useCandles] Found array in key: ${key}`);
                                candlesArray = data[key];
                                break;
                            }
                        }
                    }
                }

                console.log(`[useCandles] Extracted ${candlesArray.length} candles`);

                if (candlesArray.length > 0) {
                    console.log('[useCandles] Sample candle:', candlesArray[0]);
                }

                setCandles(candlesArray);

                if (candlesArray.length === 0) {
                    setError('Aucune donnée retournée par l\'API');
                }
            } catch (e) {
                if (e instanceof Error && e.name === 'AbortError') return;

                const msg = e instanceof Error ? e.message : String(e);
                console.error('[useCandles] Error:', msg);

                if (!controller.signal.aborted) {
                    setError(msg);
                    setCandles([]);
                }
            } finally {
                if (!controller.signal.aborted) {
                    setLoading(false);
                }
            }
        };

        fetchData();

        return () => controller.abort();
    }, [timeframe, days, refreshKey]);

    return { candles, loading, error, refresh };
}