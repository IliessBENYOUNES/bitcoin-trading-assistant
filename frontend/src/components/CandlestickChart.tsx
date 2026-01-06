/**
 * Composant CandlestickChart : affiche un graphique de chandeliers.
 * 
 * Utilise Lightweight Charts (TradingView).
 */

import { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts';
import { Card, CardContent, Typography, Box } from '@mui/material';
import type { Candle } from '../types';

interface CandlestickChartProps {
  candles: Candle[];
  symbol: string;
  timeframe: string;
  loading: boolean;
}

export default function CandlestickChart({ 
  candles, 
  symbol, 
  timeframe, 
  loading 
}: CandlestickChartProps) {
  // Référence vers le conteneur du graphique
  const chartContainerRef = useRef<HTMLDivElement>(null);
  
  // Références vers les objets chart (pour cleanup)
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    // Ne rien faire si pas de conteneur ou pas de données
    if (!chartContainerRef.current || candles.length === 0) return;

    // Supprimer l'ancien graphique s'il existe
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
      seriesRef.current = null;
    }

    // Créer le graphique
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 400,
      layout: {
        background: { color: '#1e1e1e' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#2e2e2e' },
        horzLines: { color: '#2e2e2e' },
      },
      crosshair: {
        mode: 1, // Normal
      },
      rightPriceScale: {
        borderColor: '#2e2e2e',
      },
      timeScale: {
        borderColor: '#2e2e2e',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // Créer la série de chandeliers
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });

    // Convertir les données pour Lightweight Charts
    // Les données doivent être triées du plus ancien au plus récent
    const chartData: CandlestickData<Time>[] = [...candles]
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
      .map((candle) => ({
        time: (new Date(candle.timestamp).getTime() / 1000) as Time,
        open: candle.open_price,
        high: candle.high_price,
        low: candle.low_price,
        close: candle.close_price,
      }));

    // Ajouter les données
    candlestickSeries.setData(chartData);

    // Ajuster la vue pour voir toutes les données
    chart.timeScale().fitContent();

    // Sauvegarder les références
    chartRef.current = chart;
    seriesRef.current = candlestickSeries;

    // Gérer le redimensionnement
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
      }
    };
  }, [candles]);

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Typography>Chargement du graphique...</Typography>
        </CardContent>
      </Card>
    );
  }

  if (candles.length === 0) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {symbol} - {timeframe}
          </Typography>
          <Typography color="text.secondary">
            Aucune donnée disponible. Cliquez sur "Récupérer données" pour charger les chandeliers.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {symbol} - {timeframe}
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {candles.length} chandeliers
        </Typography>
        <Box 
          ref={chartContainerRef} 
          sx={{ 
            width: '100%', 
            height: 400,
            '& > div': { borderRadius: 1 }
          }} 
        />
      </CardContent>
    </Card>
  );
}
