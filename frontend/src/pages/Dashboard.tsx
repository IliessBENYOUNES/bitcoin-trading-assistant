// =============================================================================
// Dashboard.tsx - Main dashboard with indicators, status, and chart
// =============================================================================

import React, { useState } from 'react';
import {
  Box,
  Container,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Typography,
  SelectChangeEvent,
  Alert,
  Tooltip,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CloudDownload as FetchIcon,
} from '@mui/icons-material';

// Composants
import { StatusRowConnected } from '../components/StatusRow';
import { IndicatorPanel } from '../components/IndicatorPanel';
import CandlestickChart from '../components/CandlestickChart';
import { ChartErrorBoundary } from '../components/ErrorBoundary';

// Hooks
import { useIndicators } from '../hooks/useIndicators';
import { useMarketGaps } from '../hooks/useMarketGaps';
import { useCandles } from '../hooks/useCandles';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

type TimeframeOption = '30m' | '1h' | '4h' | '1d';
type DaysOption = 1 | 2 | 7 | 14 | 30;

// Timeframes actuellement supportés par le backend
const SUPPORTED_TIMEFRAMES: TimeframeOption[] = ['30m', '1h', '4h', '1d'];


function isTimeframeSupported(tf: TimeframeOption): boolean {
  return SUPPORTED_TIMEFRAMES.includes(tf);
}

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

const Dashboard: React.FC = () => {
  // ---------------------------------------------------------------------------
  // State - User controls
  // ---------------------------------------------------------------------------
  const [timeframe, setTimeframe] = useState<TimeframeOption>('4h');
  const [days, setDays] = useState<DaysOption>(7);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const symbol = 'BTC/USD';

  // ---------------------------------------------------------------------------
  // Hooks - Data fetching
  // ---------------------------------------------------------------------------
  const indicators = useIndicators({
    timeframe,
    historyDays: days,
  });

  const gaps = useMarketGaps({
    timeframe,
    days,
  });

  const candles = useCandles({
    timeframe,
    days,
  });

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------
  const handleTimeframeChange = (event: SelectChangeEvent) => {
    setTimeframe(event.target.value as TimeframeOption);
    setFetchError(null);
  };

  const handleDaysChange = (event: SelectChangeEvent) => {
    setDays(Number(event.target.value) as DaysOption);
    setFetchError(null);
  };

  const handleRefreshAll = () => {
    indicators.refresh();
    gaps.refresh();
    candles.refresh();
  };

  const handleFetchCandles = async () => {
    setFetchError(null);

    // Garde-fou: backend ne supporte pas encore 1h/1d
    if (!isTimeframeSupported(timeframe)) {
      setFetchError(
          `Timeframe "${timeframe}" non alimenté. Utilisez 4h (days>2) ou 30m (days≤2).`
      );
      return;
    }

    // Garde-fou: 30m sur CoinGecko = max ~2 jours
    let effectiveDays = days;
    if (timeframe === '30m' && days > 2) {
      effectiveDays = 2;
      setFetchError(
          `30m limité à 2 jours max (CoinGecko). Récupération de ${effectiveDays} jour(s).`
      );
    }

    try {
      setFetching(true);
      const baseUrl =
          (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
              /\/$/,
              ''
          ) ?? 'http://localhost:8000';

      const url =
          `${baseUrl}/market/candles/fetch` +
          `?symbol=${encodeURIComponent(symbol)}` +
          `&days=${effectiveDays}`;

      const res = await fetch(url, { method: 'POST' });
      if (!res.ok) {
        const text = await res.text().catch(() => 'Erreur inconnue');
        throw new Error(text);
      }

      // Refresh UI après fetch
      candles.refresh();
      gaps.refresh();
      indicators.refresh();
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : String(e));
    } finally {
      setFetching(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------
  const timeframeNotSupported = !isTimeframeSupported(timeframe);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
      <Box
          sx={{
            minHeight: '100vh',
            backgroundColor: 'background.default',
            py: 3,
          }}
      >
        <Container maxWidth="xl">
          {/* ================================================================= */}
          {/* HEADER: Title + Controls */}
          {/* ================================================================= */}
          <Box
              sx={{
                display: 'flex',
                flexWrap: 'wrap',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 2,
                mb: 3,
              }}
          >
            <Typography variant="h4" fontWeight={700}>
              Bitcoin Trading Assistant
            </Typography>

            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
              {/* Timeframe selector */}
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Timeframe</InputLabel>
                <Select
                    value={timeframe}
                    label="Timeframe"
                    onChange={handleTimeframeChange}
                >
                  <MenuItem value="30m">30 min</MenuItem>
                  <MenuItem value="4h">4 heures</MenuItem>
                  <MenuItem value="1d">1 jour</MenuItem>
                  <Tooltip title="Non alimenté actuellement" arrow>
                    <MenuItem value="1h" sx={{ opacity: 0.5 }}>
                      1 heure ⚠️
                    </MenuItem>
                  </Tooltip>

                </Select>
              </FormControl>

              {/* Days selector */}
              <FormControl size="small" sx={{ minWidth: 100 }}>
                <InputLabel>Historique</InputLabel>
                <Select
                    value={String(days)}
                    label="Historique"
                    onChange={handleDaysChange}
                >
                  <MenuItem value="1">1 jour</MenuItem>
                  <MenuItem value="2">2 jours</MenuItem>
                  <MenuItem value="7">7 jours</MenuItem>
                  <MenuItem value="14">14 jours</MenuItem>
                  <MenuItem value="30">30 jours</MenuItem>
                </Select>
              </FormControl>

              {/* Fetch candles button */}
              <Button
                  variant="contained"
                  color="secondary"
                  startIcon={<FetchIcon />}
                  onClick={handleFetchCandles}
                  disabled={fetching || timeframeNotSupported}
              >
                {fetching ? 'Récupération...' : 'Récupérer données'}
              </Button>

              {/* Refresh button */}
              <Button
                  variant="contained"
                  startIcon={<RefreshIcon />}
                  onClick={handleRefreshAll}
                  disabled={
                      indicators.loading || gaps.loading || candles.loading
                  }
              >
                Actualiser
              </Button>
            </Box>
          </Box>

          {/* ================================================================= */}
          {/* WARNINGS / ERRORS */}
          {/* ================================================================= */}
          {timeframeNotSupported && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                Le timeframe "{timeframe}" n'est pas encore alimenté par le
                backend. Les données affichées peuvent être incomplètes ou absentes.
              </Alert>
          )}

          {fetchError && (
              <Alert
                  severity="error"
                  sx={{ mb: 2 }}
                  onClose={() => setFetchError(null)}
              >
                {fetchError}
              </Alert>
          )}

          {/* ================================================================= */}
          {/* STATUS ROW */}
          {/* ================================================================= */}
          <Box sx={{ mb: 3 }}>
            <StatusRowConnected timeframe={timeframe} days={days} />
          </Box>

          {/* ================================================================= */}
          {/* MAIN CONTENT */}
          {/* ================================================================= */}
          <Grid container spacing={3}>
            {/* Left column: Indicators */}
            <Grid item xs={12} lg={4}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                <IndicatorPanel
                    data={indicators.data}
                    loading={indicators.loading}
                    error={indicators.error}
                    onRefresh={indicators.refresh}
                    timeframe={timeframe}
                    historyDays={days}
                />
              </Box>
            </Grid>

            {/* Right column: Chart */}
            <Grid item xs={12} lg={8}>
              {candles.error && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {candles.error}
                  </Alert>
              )}

              <ChartErrorBoundary
                  fallbackMessage="Le graphique a rencontré une erreur inattendue."
              >
                <CandlestickChart
                    candles={candles.candles}
                    symbol={symbol}
                    timeframe={timeframe}
                    loading={candles.loading}
                />
              </ChartErrorBoundary>
            </Grid>
          </Grid>
        </Container>
      </Box>
  );
};

export default Dashboard;
