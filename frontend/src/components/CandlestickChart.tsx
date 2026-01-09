import { useEffect, useRef, useState, useMemo } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';
import { Card, CardContent, Typography, Box, Alert, CircularProgress } from '@mui/material';
import type { Candle } from '../types';

interface CandlestickChartProps {
  candles: Candle[];
  symbol: string;
  timeframe: string;
  loading: boolean;
}

// ---------- Helpers ----------

function toUtcSeconds(raw: unknown): UTCTimestamp | null {
  if (raw == null) return null;

  let ms: number;

  if (typeof raw === 'number') {
    if (!Number.isFinite(raw)) return null;
    ms = raw > 1e12 ? raw : raw * 1000;
  } else if (raw instanceof Date) {
    ms = raw.getTime();
  } else if (typeof raw === 'string') {
    const s = raw.trim().replace(' ', 'T');
    if (s.length === 0) return null;
    ms = Date.parse(s);
  } else {
    return null;
  }

  if (!Number.isFinite(ms)) return null;
  return Math.floor(ms / 1000) as UTCTimestamp;
}

function toNum(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function buildChartData(candles: Candle[]): CandlestickData<UTCTimestamp>[] {
  if (!Array.isArray(candles) || candles.length === 0) {
    return [];
  }

  const result: CandlestickData<UTCTimestamp>[] = [];

  for (const c of candles) {
    // Cast via unknown pour éviter l'erreur TS2352
    const raw = c as unknown as Record<string, unknown>;

    const rawTime = raw.timestamp ?? raw.ts ?? raw.time;
    const time = toUtcSeconds(rawTime);
    if (time == null) continue;

    const open = toNum(raw.open_price ?? raw.open);
    const high = toNum(raw.high_price ?? raw.high);
    const low = toNum(raw.low_price ?? raw.low);
    const close = toNum(raw.close_price ?? raw.close);

    if (open == null || high == null || low == null || close == null) continue;

    result.push({ time, open, high, low, close });
  }

  // Trier ASC
  result.sort((a, b) => (a.time as number) - (b.time as number));

  // Dédupliquer
  const deduped: CandlestickData<UTCTimestamp>[] = [];
  let lastTime: number | null = null;
  for (const item of result) {
    if ((item.time as number) !== lastTime) {
      deduped.push(item);
      lastTime = item.time as number;
    }
  }

  console.log(`[CandlestickChart] Built ${deduped.length} chart points from ${candles.length} candles`);

  return deduped;
}

// ---------- Component ----------

export default function CandlestickChart({
                                           candles,
                                           symbol,
                                           timeframe,
                                           loading,
                                         }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Mémoriser les données pour éviter les recalculs
  const chartData = useMemo(() => buildChartData(candles), [candles]);

  // Effet principal pour le chart
  useEffect(() => {
    setError(null);

    // Cleanup fonction
    const cleanup = () => {
      if (chartRef.current) {
        try {
          chartRef.current.remove();
        } catch { /* ignore */ }
        chartRef.current = null;
        seriesRef.current = null;
      }
    };

    // Si pas de container ou loading, cleanup et sortir
    if (!containerRef.current || loading) {
      cleanup();
      return;
    }

    // Si pas de données, cleanup et sortir
    if (chartData.length === 0) {
      cleanup();
      return;
    }

    // Cleanup avant création
    cleanup();

    try {
      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 400,
        layout: {
          background: { color: '#1e1e1e' },
          textColor: '#d1d4dc',
        },
        grid: {
          vertLines: { color: '#2e2e2e' },
          horzLines: { color: '#2e2e2e' },
        },
        crosshair: { mode: 1 },
        rightPriceScale: { borderColor: '#2e2e2e' },
        timeScale: {
          borderColor: '#2e2e2e',
          timeVisible: true,
          secondsVisible: false,
        },
      });

      const series = chart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
      });

      series.setData(chartData as CandlestickData<Time>[]);
      chart.timeScale().fitContent();

      chartRef.current = chart;
      seriesRef.current = series;

      // Resize handler
      const handleResize = () => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
        }
      };
      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        cleanup();
      };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error('[CandlestickChart] Error:', msg);
      setError(msg);
      cleanup();
    }
  }, [chartData, loading, timeframe]);

  // ---------- Render ----------

  if (loading) {
    return (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>{symbol} - {timeframe}</Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, py: 4 }}>
              <CircularProgress size={24} />
              <Typography>Chargement...</Typography>
            </Box>
          </CardContent>
        </Card>
    );
  }

  if (error) {
    return (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>{symbol} - {timeframe}</Typography>
            <Alert severity="error">{error}</Alert>
          </CardContent>
        </Card>
    );
  }

  if (chartData.length === 0) {
    return (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>{symbol} - {timeframe}</Typography>
            <Alert severity="info">Aucune donnée disponible.</Alert>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Cliquez sur "Récupérer données" pour charger les chandeliers.
            </Typography>
          </CardContent>
        </Card>
    );
  }

  return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>{symbol} - {timeframe}</Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            {chartData.length} chandeliers
          </Typography>
          <Box ref={containerRef} sx={{ width: '100%', height: 400 }} />
        </CardContent>
      </Card>
  );
}

