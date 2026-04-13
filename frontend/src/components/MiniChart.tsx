// =============================================================================
// MiniChart — Mini graphique BTC 1m temps réel pour l'onglet Trading
// =============================================================================
//
// Version allégée de CandlestickChart :
// - Hauteur compacte (~250px)
// - Pas de volume histogram
// - Header minimal (BTC 1m + prix + variation)
// - Focus auto sur les 15 dernières bougies
// - Mise à jour en temps réel via livePrice
//
// [v2.0.27] Créé pour donner une visibilité prix directe sur l'onglet Trading.
// =============================================================================

import { useEffect, useRef, useState, useMemo } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';
import { Box, Typography, Skeleton } from '@mui/material';
import type { MiniCandle } from '../hooks/useMiniCandles';

interface MiniChartProps {
  candles: MiniCandle[];
  loading: boolean;
  error: string | null;
  /** Prix live (WebSocket) pour mettre à jour le dernier chandelier */
  livePrice?: number | null;
  /** Timestamp de la dernière mise à jour des bougies */
  lastUpdate?: Date | null;
}

// Nombre de bougies visibles au focus (les ~15 dernières minutes)
const FOCUS_CANDLES = 15;
const CHART_HEIGHT = 250;

interface ChartCandle extends CandlestickData<UTCTimestamp> {
  volume?: number;
}

function buildMiniChartData(candles: MiniCandle[]): ChartCandle[] {
  if (!candles || candles.length === 0) return [];

  const result: ChartCandle[] = [];
  for (const c of candles) {
    if (!c.time || !Number.isFinite(c.open)) continue;
    result.push({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
    });
  }

  result.sort((a, b) => (a.time as number) - (b.time as number));

  // Dedup par timestamp
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

export default function MiniChart({
  candles,
  loading,
  error,
  livePrice,
  lastUpdate,
}: MiniChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const lastCandleBaseRef = useRef<ChartCandle | null>(null);
  const [displayPrice, setDisplayPrice] = useState<number | null>(null);

  const chartData = useMemo(() => buildMiniChartData(candles), [candles]);

  // ---------- Chart creation & data update ----------
  useEffect(() => {
    const cleanup = () => {
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch { /* ignore */ }
        chartRef.current = null;
        seriesRef.current = null;
      }
    };

    if (!containerRef.current || loading) { cleanup(); return; }
    if (chartData.length === 0) { cleanup(); return; }

    cleanup();

    try {
      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: CHART_HEIGHT,
        layout: {
          background: { color: '#0A0E17' },
          textColor: '#4B5563',
          fontSize: 10,
        },
        grid: {
          vertLines: { color: 'rgba(255, 255, 255, 0.02)' },
          horzLines: { color: 'rgba(255, 255, 255, 0.02)' },
        },
        crosshair: {
          mode: 1,
          vertLine: {
            color: 'rgba(247, 147, 26, 0.25)',
            labelBackgroundColor: '#F7931A',
          },
          horzLine: {
            color: 'rgba(247, 147, 26, 0.25)',
            labelBackgroundColor: '#F7931A',
          },
        },
        rightPriceScale: {
          borderColor: 'rgba(255, 255, 255, 0.04)',
          scaleMargins: { top: 0.08, bottom: 0.08 },
        },
        timeScale: {
          borderColor: 'rgba(255, 255, 255, 0.04)',
          timeVisible: true,
          secondsVisible: false,
          fixLeftEdge: true,
          fixRightEdge: true,
        },
      });

      const series = chart.addCandlestickSeries({
        upColor: '#00E676',
        downColor: '#FF1744',
        borderVisible: false,
        wickUpColor: '#00E67680',
        wickDownColor: '#FF174480',
      });

      series.setData(chartData as CandlestickData<Time>[]);

      // Stocker le dernier candle d'origine pour les updates live
      if (chartData.length > 0) {
        lastCandleBaseRef.current = { ...chartData[chartData.length - 1] };
        setDisplayPrice(chartData[chartData.length - 1].close);
      }

      // Focus sur les ~15 dernières bougies
      if (chartData.length > FOCUS_CANDLES) {
        chart.timeScale().setVisibleLogicalRange({
          from: chartData.length - FOCUS_CANDLES - 0.5,
          to: chartData.length + 0.5,
        });
      } else {
        chart.timeScale().fitContent();
      }

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
      console.error('[MiniChart] Error:', e);
    }
  }, [chartData, loading]);

  // ---------- Live price update ----------
  useEffect(() => {
    if (
      livePrice == null ||
      !seriesRef.current ||
      !lastCandleBaseRef.current
    ) return;

    const base = lastCandleBaseRef.current;
    const updatedCandle: CandlestickData<Time> = {
      time: base.time as Time,
      open: base.open,
      high: Math.max(base.high, livePrice),
      low: Math.min(base.low, livePrice),
      close: livePrice,
    };

    try {
      seriesRef.current.update(updatedCandle);
    } catch {
      // Ignorer si la série n'est plus disponible
    }

    setDisplayPrice(livePrice);
  }, [livePrice]);

  // ---------- Render ----------
  const effectivePrice = displayPrice ?? (chartData.length > 0 ? chartData[chartData.length - 1].close : null);
  const firstPrice = chartData.length > 0 ? chartData[0].open : null;
  const priceChange = effectivePrice && firstPrice ? effectivePrice - firstPrice : 0;
  const priceChangePct = firstPrice && firstPrice > 0 ? (priceChange / firstPrice) * 100 : 0;
  const isUp = priceChange >= 0;

  if (loading && chartData.length === 0) {
    return (
      <Box sx={{
        borderRadius: 2,
        overflow: 'hidden',
        backgroundColor: 'rgba(10, 14, 23, 0.6)',
        border: '1px solid rgba(255,255,255,0.06)',
        p: 2,
      }}>
        <Skeleton variant="text" width={120} height={20} sx={{ mb: 1 }} />
        <Skeleton variant="rounded" height={CHART_HEIGHT} sx={{ borderRadius: 1.5 }} />
      </Box>
    );
  }

  return (
    <Box sx={{
      borderRadius: 2,
      overflow: 'hidden',
      backgroundColor: 'rgba(10, 14, 23, 0.6)',
      border: `1px solid ${isUp ? 'rgba(0, 230, 118, 0.12)' : 'rgba(255, 23, 68, 0.12)'}`,
      transition: 'border-color 0.5s ease',
    }}>
      {/* Header compact */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        px: 1.5,
        py: 1,
        borderBottom: '1px solid rgba(255,255,255,0.04)',
        flexWrap: 'wrap',
        gap: 0.5,
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography sx={{
            fontWeight: 800,
            fontSize: '0.8rem',
            letterSpacing: '-0.01em',
            color: '#F7931A',
          }}>
            BTC
          </Typography>
          <Box sx={{
            px: 0.75,
            py: 0.15,
            borderRadius: 0.75,
            backgroundColor: 'rgba(247, 147, 26, 0.08)',
            border: '1px solid rgba(247, 147, 26, 0.15)',
          }}>
            <Typography sx={{
              fontWeight: 700,
              color: '#F7931A',
              fontSize: '0.55rem',
              letterSpacing: '0.05em',
            }}>
              1M
            </Typography>
          </Box>
          <Typography sx={{
            fontSize: '0.55rem',
            color: 'text.secondary',
            fontFamily: '"JetBrains Mono", monospace',
          }}>
            {chartData.length} bougies
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {effectivePrice && (
            <>
              <Typography sx={{
                fontFamily: '"JetBrains Mono", monospace',
                fontWeight: 700,
                fontSize: '0.85rem',
                color: isUp ? '#00E676' : '#FF1744',
              }}>
                ${effectivePrice.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              </Typography>
              <Typography sx={{
                fontFamily: '"JetBrains Mono", monospace',
                fontWeight: 600,
                fontSize: '0.65rem',
                color: isUp ? '#00E676' : '#FF1744',
                opacity: 0.8,
              }}>
                {isUp ? '+' : ''}{priceChangePct.toFixed(2)}%
              </Typography>
            </>
          )}
          {/* Dot de statut */}
          <Box sx={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            backgroundColor: error ? '#FF1744' : '#00E676',
            animation: !error ? 'pulse-dot 2s ease-in-out infinite' : 'none',
            ml: 0.5,
          }} />
        </Box>
      </Box>

      {/* Erreur inline */}
      {error && (
        <Box sx={{ px: 1.5, py: 0.5 }}>
          <Typography sx={{ fontSize: '0.6rem', color: '#FF1744' }}>
            ⚠️ {error}
          </Typography>
        </Box>
      )}

      {/* Chart container */}
      <Box
        ref={containerRef}
        sx={{
          width: '100%',
          height: CHART_HEIGHT,
          position: 'relative',
        }}
      />

      {/* Footer ultra compact */}
      {lastUpdate && (
        <Box sx={{
          px: 1.5,
          py: 0.5,
          borderTop: '1px solid rgba(255,255,255,0.03)',
          display: 'flex',
          justifyContent: 'flex-end',
        }}>
          <Typography sx={{
            fontSize: '0.5rem',
            color: 'text.secondary',
            fontFamily: '"JetBrains Mono", monospace',
            opacity: 0.6,
          }}>
            MAJ {lastUpdate.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

