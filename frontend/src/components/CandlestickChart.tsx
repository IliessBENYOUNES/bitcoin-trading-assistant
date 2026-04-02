import { useEffect, useRef, useState, useMemo } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
  UTCTimestamp,
  HistogramData,
} from 'lightweight-charts';
import { CardContent, Typography, Box, Alert, Skeleton } from '@mui/material';
import { motion } from 'framer-motion';
import type { Candle } from '../types';
import { GlowingCard, ACCENT } from './GlowingCard';

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

interface ChartCandle extends CandlestickData<UTCTimestamp> {
  volume?: number;
}

function buildChartData(candles: Candle[]): ChartCandle[] {
  if (!Array.isArray(candles) || candles.length === 0) return [];

  const result: ChartCandle[] = [];
  for (const c of candles) {
    const raw = c as unknown as Record<string, unknown>;
    const rawTime = raw.timestamp ?? raw.ts ?? raw.time;
    const time = toUtcSeconds(rawTime);
    if (time == null) continue;

    const open = toNum(raw.open_price ?? raw.open);
    const high = toNum(raw.high_price ?? raw.high);
    const low = toNum(raw.low_price ?? raw.low);
    const close = toNum(raw.close_price ?? raw.close);
    const volume = toNum(raw.volume) ?? undefined;

    if (open == null || high == null || low == null || close == null) continue;
    result.push({ time, open, high, low, close, volume });
  }

  result.sort((a, b) => (a.time as number) - (b.time as number));

  const deduped: ChartCandle[] = [];
  let lastTime: number | null = null;
  for (const item of result) {
    if ((item.time as number) !== lastTime) {
      deduped.push(item);
      lastTime = item.time as number;
    }
  }
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
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const chartData = useMemo(() => buildChartData(candles), [candles]);

  useEffect(() => {
    setError(null);

    const cleanup = () => {
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch { /* ignore */ }
        chartRef.current = null;
        seriesRef.current = null;
        volumeSeriesRef.current = null;
      }
    };

    if (!containerRef.current || loading) { cleanup(); return; }
    if (chartData.length === 0) { cleanup(); return; }

    cleanup();

    try {
      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 460,
        layout: {
          background: { color: '#0A0E17' },
          textColor: '#6B7280',
          fontSize: 11,
        },
        grid: {
          vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
          horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
        },
        crosshair: {
          mode: 1,
          vertLine: {
            color: 'rgba(247, 147, 26, 0.3)',
            labelBackgroundColor: '#F7931A',
          },
          horzLine: {
            color: 'rgba(247, 147, 26, 0.3)',
            labelBackgroundColor: '#F7931A',
          },
        },
        rightPriceScale: {
          borderColor: 'rgba(255, 255, 255, 0.06)',
          scaleMargins: { top: 0.1, bottom: 0.2 },
        },
        timeScale: {
          borderColor: 'rgba(255, 255, 255, 0.06)',
          timeVisible: true,
          secondsVisible: false,
        },
      });

      // Candlestick series with premium colors
      const series = chart.addCandlestickSeries({
        upColor: '#00E676',
        downColor: '#FF1744',
        borderVisible: false,
        wickUpColor: '#00E67680',
        wickDownColor: '#FF174480',
      });

      series.setData(chartData as CandlestickData<Time>[]);

      // Volume histogram overlay
      const hasVolume = chartData.some(c => c.volume != null && c.volume > 0);
      if (hasVolume) {
        const volumeSeries = chart.addHistogramSeries({
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume',
        });
        chart.priceScale('volume').applyOptions({
          scaleMargins: { top: 0.85, bottom: 0 },
        });
        const volumeData: HistogramData<Time>[] = chartData
          .filter(c => c.volume != null)
          .map(c => ({
            time: c.time as Time,
            value: c.volume!,
            color: c.close >= c.open ? 'rgba(0, 230, 118, 0.15)' : 'rgba(255, 23, 68, 0.15)',
          }));
        volumeSeries.setData(volumeData);
        volumeSeriesRef.current = volumeSeries;
      }

      chart.timeScale().fitContent();
      chartRef.current = chart;
      seriesRef.current = series;

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
    }
  }, [chartData, loading, timeframe]);

  // ---------- Render ----------

  if (loading) {
    return (
      <GlowingCard accentColor={ACCENT.orange.start} accentColorEnd={ACCENT.orange.end}>
        <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Skeleton variant="text" width={120} height={28} />
              <Skeleton variant="rounded" width={50} height={20} />
            </Box>
            <Skeleton variant="text" width={80} />
          </Box>
          {/* Shimmer skeleton chart area */}
          <Skeleton
            variant="rounded"
            height={420}
            className="animate-shimmer"
            sx={{
              borderRadius: 2,
              backgroundColor: 'rgba(255,255,255,0.03)',
            }}
          />
        </CardContent>
      </GlowingCard>
    );
  }

  if (error) {
    return (
      <GlowingCard accentColor={ACCENT.red.start} accentColorEnd={ACCENT.red.end}>
        <CardContent>
          <Typography variant="h6" gutterBottom>{symbol} — {timeframe}</Typography>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </GlowingCard>
    );
  }

  if (chartData.length === 0) {
    return (
      <GlowingCard accentColor={ACCENT.neutral.start}>
        <CardContent>
          <Typography variant="h6" gutterBottom>{symbol} — {timeframe}</Typography>
          <Alert severity="info">Aucune donnée disponible.</Alert>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Cliquez sur "Fetch API" pour charger les chandeliers.
          </Typography>
        </CardContent>
      </GlowingCard>
    );
  }

  const lastCandle = chartData[chartData.length - 1];
  const firstCandle = chartData[0];
  const priceChange = lastCandle && firstCandle ? lastCandle.close - firstCandle.open : 0;
  const isUp = priceChange >= 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <GlowingCard
        accentColor={isUp ? ACCENT.green.start : ACCENT.red.start}
        accentColorEnd={isUp ? ACCENT.green.end : ACCENT.red.end}
        noAnimation
      >
        <CardContent sx={{ p: { xs: 1.5, sm: 2.5 }, '&:last-child': { pb: { xs: 1.5, sm: 2 } } }}>
          {/* Chart header overlay */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              mb: 1.5,
              flexWrap: 'wrap',
              gap: 1,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Typography
                variant="h6"
                sx={{
                  fontWeight: 800,
                  fontSize: { xs: '0.9rem', sm: '1rem' },
                  letterSpacing: '-0.02em',
                }}
              >
                {symbol}
              </Typography>
              <Box
                sx={{
                  px: 1,
                  py: 0.25,
                  borderRadius: 1,
                  backgroundColor: 'rgba(247, 147, 26, 0.1)',
                  border: '1px solid rgba(247, 147, 26, 0.2)',
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    fontWeight: 700,
                    color: '#F7931A',
                    fontSize: '0.65rem',
                    letterSpacing: '0.05em',
                  }}
                >
                  {timeframe.toUpperCase()}
                </Typography>
              </Box>
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography
                variant="caption"
                sx={{
                  color: 'text.secondary',
                  fontSize: '0.7rem',
                  fontFamily: '"JetBrains Mono", monospace',
                }}
              >
                {chartData.length} candles
              </Typography>
              {lastCandle && (
                <Typography
                  sx={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontWeight: 700,
                    fontSize: { xs: '0.85rem', sm: '1rem' },
                    color: isUp ? '#00E676' : '#FF1744',
                  }}
                >
                  ${lastCandle.close.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </Typography>
              )}
            </Box>
          </Box>

          {/* Chart container */}
          <Box
            ref={containerRef}
            sx={{
              width: '100%',
              height: 460,
              borderRadius: 1.5,
              overflow: 'hidden',
              // Fade-out gradient at bottom
              '&::after': {
                content: '""',
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                height: '60px',
                background: 'linear-gradient(transparent, rgba(17, 24, 39, 0.6))',
                pointerEvents: 'none',
              },
              position: 'relative',
            }}
          />
        </CardContent>
      </GlowingCard>
    </motion.div>
  );
}
