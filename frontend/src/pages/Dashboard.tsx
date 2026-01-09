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
  Chip,
  Stack,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CloudDownload as FetchIcon,
  CheckCircle as SuccessIcon,
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

interface FetchResult {
  status: string;
  timeframe?: string;
  fetched?: number;
  inserted?: number;
  updated?: number;
  duplicates?: number;
  resample?: {
    '1d': number;
    '1h': number;
  };
  duration_seconds?: number;
  error?: string;
}

// Tous les timeframes sont maintenant supportés
const SUPPORTED_TIMEFRAMES: TimeframeOption[] = ['30m', '1h', '4h', '1d'];

function isTimeframeSupported(tf: TimeframeOption): boolean {
  return SUPPORTED_TIMEFRAMES.includes(tf);
}

/**
 * Détermine quel endpoint trigger utiliser selon le timeframe demandé.
 * - 30m, 1h => /scheduler/trigger/30m (le job 30m alimente 30m + resample 1h)
 * - 4h, 1d => /scheduler/trigger/4h (le job 4h alimente 4h + resample 1d)
 */
function getTriggerEndpoint(tf: TimeframeOption): string {
  if (tf === '30m' || tf === '1h') {
    return '/scheduler/trigger/30m';
  }
  return '/scheduler/trigger/4h';
}

/**
 * Retourne un label explicatif pour l'utilisateur sur ce que le fetch va faire.
 */
function getFetchDescription(tf: TimeframeOption): string {
  if (tf === '30m' || tf === '1h') {
    return 'Récupère 30m + génère 1h';
  }
  return 'Récupère 4h + génère 1d';
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
  const [fetchResult, setFetchResult] = useState<FetchResult | null>(null);

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
    setFetchResult(null);
  };

  const handleDaysChange = (event: SelectChangeEvent) => {
    setDays(Number(event.target.value) as DaysOption);
    setFetchError(null);
    setFetchResult(null);
  };

  const handleRefreshAll = () => {
    indicators.refresh();
    gaps.refresh();
    candles.refresh();
  };

  const handleFetchCandles = async () => {
    setFetchError(null);
    setFetchResult(null);

    // Garde-fou: vérifier si timeframe supporté
    if (!isTimeframeSupported(timeframe)) {
      setFetchError(
          `Timeframe "${timeframe}" non supporté.`
      );
      return;
    }

    try {
      setFetching(true);
      const baseUrl =
          (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
              /\/$/,
              ''
          ) ?? 'http://localhost:8000';

      // Utiliser le bon endpoint trigger selon le timeframe
      const triggerEndpoint = getTriggerEndpoint(timeframe);
      const url = `${baseUrl}${triggerEndpoint}`;

      const res = await fetch(url, { method: 'POST' });

      if (!res.ok) {
        const text = await res.text().catch(() => 'Erreur inconnue');
        throw new Error(text);
      }

      // Récupérer le status du scheduler pour obtenir last_result
      const statusRes = await fetch(`${baseUrl}/scheduler/status`);
      if (statusRes.ok) {
        const statusData = await statusRes.json();

        // Déterminer quel job a été déclenché
        const jobType = (timeframe === '30m' || timeframe === '1h') ? '30m' : '4h';
        const jobResult = statusData?.jobs?.[jobType]?.last_result;

        if (jobResult) {
          setFetchResult(jobResult);
        }
      }

      // Petit délai pour laisser le job terminer puis refresh UI
      await new Promise(resolve => setTimeout(resolve, 500));

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
  const noData = !candles.loading && candles.candles.length === 0;

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
                  <MenuItem value="1h">1 heure</MenuItem>
                  <MenuItem value="4h">4 heures</MenuItem>
                  <MenuItem value="1d">1 jour</MenuItem>
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
                  title={getFetchDescription(timeframe)}
              >
                {fetching ? 'Récupération...' : 'Fetch API'}
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
          {/* FETCH RESULT INFO (non bloquant) */}
          {/* ================================================================= */}
          {fetchResult && fetchResult.status === 'success' && (
              <Alert
                  severity="success"
                  icon={<SuccessIcon />}
                  sx={{ mb: 2 }}
                  onClose={() => setFetchResult(null)}
              >
                <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
                  <Typography variant="body2" fontWeight={600}>
                    Fetch réussi ({fetchResult.duration_seconds?.toFixed(2)}s)
                  </Typography>
                  <Chip
                      label={`Timeframe: ${fetchResult.timeframe}`}
                      size="small"
                      color="primary"
                      variant="outlined"
                  />
                  <Chip
                      label={`Fetched: ${fetchResult.fetched ?? 0}`}
                      size="small"
                      variant="outlined"
                  />
                  <Chip
                      label={`Inserted: ${fetchResult.inserted ?? 0}`}
                      size="small"
                      color="success"
                      variant="outlined"
                  />
                  <Chip
                      label={`Updated: ${fetchResult.updated ?? 0}`}
                      size="small"
                      color="info"
                      variant="outlined"
                  />
                  <Chip
                      label={`Duplicates: ${fetchResult.duplicates ?? 0}`}
                      size="small"
                      variant="outlined"
                  />
                  {fetchResult.resample && (
                      <>
                        {fetchResult.resample['1h'] > 0 && (
                            <Chip
                                label={`Resample 1h: ${fetchResult.resample['1h']}`}
                                size="small"
                                color="secondary"
                            />
                        )}
                        {fetchResult.resample['1d'] > 0 && (
                            <Chip
                                label={`Resample 1d: ${fetchResult.resample['1d']}`}
                                size="small"
                                color="secondary"
                            />
                        )}
                      </>
                  )}
                </Stack>
              </Alert>
          )}

          {fetchResult && fetchResult.status === 'error' && (
              <Alert
                  severity="error"
                  sx={{ mb: 2 }}
                  onClose={() => setFetchResult(null)}
              >
                Erreur lors du fetch: {fetchResult.error}
              </Alert>
          )}

          {/* ================================================================= */}
          {/* WARNINGS / ERRORS */}
          {/* ================================================================= */}
          {timeframeNotSupported && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                Le timeframe "{timeframe}" n'est pas supporté.
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

          {/* Info pour 30m/1h: limité à 1 jour via scheduler */}
          {(timeframe === '30m' || timeframe === '1h') && days > 1 && (
              <Alert severity="info" sx={{ mb: 2 }}>
                Note: Le scheduler 30m récupère 1 jour de données (limite CoinGecko).
                L'historique affiché peut être limité.
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

              {/* Message si aucune donnée */}
              {noData && !candles.error && (
                  <Alert severity="info" sx={{ mb: 2 }}>
                    Aucune donnée disponible pour {timeframe} / {days} jour(s).
                    Cliquez sur "Fetch API" pour récupérer les données.
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
