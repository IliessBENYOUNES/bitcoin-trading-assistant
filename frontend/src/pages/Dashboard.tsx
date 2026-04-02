// =============================================================================
// Dashboard.tsx - Premium dark trading dashboard
// =============================================================================

import React, { useState, useMemo } from 'react';
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
  AppBar,
  Toolbar,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CloudDownload as FetchIcon,
  CheckCircle as SuccessIcon,
  Info as InfoIcon,
  CurrencyBitcoin as BitcoinIcon,
} from '@mui/icons-material';

// Composants
import { StatusRowConnected } from '../components/StatusRow';
import { IndicatorPanel } from '../components/IndicatorPanel';
import { SignalPanel } from '../components/SignalPanel';
import { AlertPanel } from '../components/AlertPanel';
import { NewsPanel } from '../components/NewsPanel';
import CandlestickChart from '../components/CandlestickChart';
import { ChartErrorBoundary } from '../components/ErrorBoundary';

// Hooks
import { useIndicators } from '../hooks/useIndicators';
import { useMarketGaps } from '../hooks/useMarketGaps';
import { useCandles } from '../hooks/useCandles';
import { useSignals } from '../hooks/useSignals';
import { useAlerts } from '../hooks/useAlerts';
import { useNews } from '../hooks/useNews';

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

// Tous les timeframes sont supportés
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
 * Calcule l'historique effectif en fonction du timeframe.
 * Pour 30m et 1h, on cap à 1 jour (limite CoinGecko).
 */
function getEffectiveDays(tf: TimeframeOption, requestedDays: DaysOption): number {
  if (tf === '30m' || tf === '1h') {
    return Math.min(requestedDays, 1);
  }
  return requestedDays;
}

/**
 * Vérifie si l'historique est cappé pour ce timeframe.
 */
function isHistoryCapped(tf: TimeframeOption, requestedDays: DaysOption): boolean {
  return (tf === '30m' || tf === '1h') && requestedDays > 1;
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
  // Computed: effectiveDays (cappé pour 30m/1h)
  // ---------------------------------------------------------------------------
  const effectiveDays = useMemo(
      () => getEffectiveDays(timeframe, days),
      [timeframe, days]
  );

  const historyCapped = useMemo(
      () => isHistoryCapped(timeframe, days),
      [timeframe, days]
  );

  // ---------------------------------------------------------------------------
  // Hooks - Data fetching (utilisent effectiveDays)
  // ---------------------------------------------------------------------------
  const indicators = useIndicators({
    timeframe,
    historyDays: effectiveDays,
  });

  const gaps = useMarketGaps({
    timeframe,
    days: effectiveDays,
  });

  const candles = useCandles({
    timeframe,
    days: effectiveDays,
  });

  const signals = useSignals({
    timeframe,
    historyDays: effectiveDays,
  });

  // Hook alertes avec polling toutes les 60s
  const alertsHook = useAlerts({
    timeframe,
    pollInterval: 60000,
  });

  // Hook news avec polling toutes les 5 minutes
  const news = useNews({
    limit: 20,
    pollInterval: 300000,
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
    signals.refresh();
    alertsHook.refresh();
    news.refresh();
  };

  const handleFetchCandles = async () => {
    setFetchError(null);
    setFetchResult(null);

    if (!isTimeframeSupported(timeframe)) {
      setFetchError(`Timeframe "${timeframe}" non supporté.`);
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
      signals.refresh();
      alertsHook.check(); // Vérifie les alertes après un fetch

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
            background: 'linear-gradient(180deg, #0A0E17 0%, #0D1321 50%, #0A0E17 100%)',
          }}
      >
        {/* ================================================================= */}
        {/* APPBAR PREMIUM */}
        {/* ================================================================= */}
        <AppBar
          position="sticky"
          elevation={0}
          sx={{
            backgroundColor: 'rgba(10, 14, 23, 0.85)',
            backdropFilter: 'blur(20px)',
            borderBottom: '1px solid rgba(255,255,255,0.04)',
          }}
        >
          <Toolbar sx={{ gap: 2 }}>
            {/* Logo + Title */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mr: 2 }}>
              <BitcoinIcon sx={{ color: '#F7931A', fontSize: 32 }} />
              <Box>
                <Typography variant="h6" fontWeight={800} sx={{ lineHeight: 1, letterSpacing: '-0.02em' }}>
                  BTC Insight
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem' }}>
                  Trading Assistant v0.9
                </Typography>
              </Box>
            </Box>

            {/* Spacer */}
            <Box sx={{ flex: 1 }} />

            {/* Controls */}
            <FormControl size="small" sx={{ minWidth: 110 }}>
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

            <Button
                variant="contained"
                color="primary"
                size="small"
                startIcon={<FetchIcon />}
                onClick={handleFetchCandles}
                disabled={fetching || timeframeNotSupported}
                sx={{
                  background: 'linear-gradient(135deg, #F7931A 0%, #E65100 100%)',
                  '&:hover': { background: 'linear-gradient(135deg, #FFB74D 0%, #F7931A 100%)' },
                }}
            >
              {fetching ? 'Fetch...' : 'Fetch API'}
            </Button>

            <Tooltip title="Actualiser toutes les données">
              <IconButton
                  onClick={handleRefreshAll}
                  disabled={indicators.loading || gaps.loading || candles.loading || signals.loading}
                  sx={{ color: 'text.secondary', '&:hover': { color: '#F7931A' } }}
              >
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Toolbar>
        </AppBar>

        <Container maxWidth="xl" sx={{ pt: 2.5, pb: 4 }}>

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

          {/* Info: historique cappé pour 30m/1h */}
          {historyCapped && (
              <Alert
                  severity="info"
                  icon={<InfoIcon />}
                  sx={{ mb: 2 }}
              >
                <strong>Limite CoinGecko :</strong> Les timeframes 30m et 1h sont disponibles sur 1 jour maximum.
                L'affichage est limité à {effectiveDays} jour (vous avez sélectionné {days} jours).
                Pour un historique plus long, utilisez 4h ou 1d.
              </Alert>
          )}

          {/* ================================================================= */}
          {/* STATUS ROW (utilise effectiveDays) */}
          {/* ================================================================= */}
          <Box sx={{ mb: 3 }}>
            <StatusRowConnected timeframe={timeframe} days={effectiveDays} />
          </Box>

          {/* ================================================================= */}
          {/* MAIN CONTENT — Grille premium */}
          {/* ================================================================= */}
          <Grid container spacing={2.5}>
            {/* Colonne gauche: Signaux + Alertes + News + Indicateurs */}
            <Grid item xs={12} lg={4}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
                <SignalPanel
                    data={signals.data}
                    loading={signals.loading}
                    error={signals.error}
                    onRefresh={signals.refresh}
                    timeframe={timeframe}
                    historyDays={effectiveDays}
                />
                <AlertPanel
                    alerts={alertsHook.alerts}
                    notifications={alertsHook.notifications}
                    loading={alertsHook.loading}
                    error={alertsHook.error}
                    onRefresh={alertsHook.refresh}
                    onAdd={alertsHook.add}
                    onDelete={alertsHook.remove}
                    onCheck={alertsHook.check}
                    onDismissNotifications={alertsHook.dismissNotifications}
                    timeframe={timeframe}
                />
                <NewsPanel
                    data={news.data}
                    loading={news.loading}
                    error={news.error}
                    onRefresh={news.refresh}
                />
                <IndicatorPanel
                    data={indicators.data}
                    loading={indicators.loading}
                    error={indicators.error}
                    onRefresh={indicators.refresh}
                    timeframe={timeframe}
                    historyDays={effectiveDays}
                />
              </Box>
            </Grid>

            {/* Colonne droite: Chart */}
            <Grid item xs={12} lg={8}>
              {candles.error && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {candles.error}
                  </Alert>
              )}

              {/* Message si aucune donnée */}
              {noData && !candles.error && (
                  <Alert severity="info" sx={{ mb: 2 }}>
                    Aucune donnée disponible pour {timeframe} / {effectiveDays} jour(s).
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
