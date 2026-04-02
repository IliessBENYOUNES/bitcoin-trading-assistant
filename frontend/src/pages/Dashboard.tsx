// =============================================================================
// Dashboard.tsx — Premium dark trading dashboard with animations
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
import { motion, AnimatePresence } from 'framer-motion';

// Composants
import { StatusRowConnected } from '../components/StatusRow';
import { IndicatorPanel } from '../components/IndicatorPanel';
import { SignalPanel } from '../components/SignalPanel';
import { AlertPanel } from '../components/AlertPanel';
import { NewsPanel } from '../components/NewsPanel';
import CandlestickChart from '../components/CandlestickChart';
import { ChartErrorBoundary } from '../components/ErrorBoundary';
import { PriceTicker } from '../components/PriceTicker';
import { SectionHeader } from '../components/SectionHeader';

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
type DaysOption = 1 | 2 | 7 | 14 | 30 | 90;

interface FetchResult {
  status: string;
  timeframe?: string;
  fetched?: number;
  inserted?: number;
  updated?: number;
  duplicates?: number;
  resample?: { '1d': number; '1h': number };
  duration_seconds?: number;
  error?: string;
}

const SUPPORTED_TIMEFRAMES: TimeframeOption[] = ['30m', '1h', '4h', '1d'];

function isTimeframeSupported(tf: TimeframeOption): boolean {
  return SUPPORTED_TIMEFRAMES.includes(tf);
}

function getTriggerEndpoint(tf: TimeframeOption): string {
  if (tf === '30m' || tf === '1h') return '/scheduler/trigger/30m';
  return '/scheduler/trigger/4h';
}

// Toutes les combinaisons timeframe × jours sont maintenant possibles
// grâce à Binance comme source de données (pas de contrainte de granularité)
function getEffectiveDays(_tf: TimeframeOption, requestedDays: DaysOption): number {
  return requestedDays;
}

function isHistoryCapped(_tf: TimeframeOption, _requestedDays: DaysOption): boolean {
  return false;
}

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

const Dashboard: React.FC = () => {
  const [timeframe, setTimeframe] = useState<TimeframeOption>('4h');
  const [days, setDays] = useState<DaysOption>(7);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [fetchResult, setFetchResult] = useState<FetchResult | null>(null);

  const symbol = 'BTC/USD';

  const effectiveDays = useMemo(() => getEffectiveDays(timeframe, days), [timeframe, days]);
  const historyCapped = useMemo(() => isHistoryCapped(timeframe, days), [timeframe, days]);

  // ---------------------------------------------------------------------------
  // Hooks
  // ---------------------------------------------------------------------------
  const indicators = useIndicators({ timeframe, historyDays: effectiveDays });
  const gaps = useMarketGaps({ timeframe, days: effectiveDays });
  const candles = useCandles({ timeframe, days: effectiveDays });
  const signals = useSignals({ timeframe, historyDays: effectiveDays });
  const alertsHook = useAlerts({ timeframe, pollInterval: 60000 });
  const news = useNews({ limit: 20, pollInterval: 300000 });

  // Get latest price from indicators data
  const currentPrice = indicators.data?.latest?.close ?? null;

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
        (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? 'http://localhost:8000';
      const triggerEndpoint = getTriggerEndpoint(timeframe);
      const url = `${baseUrl}${triggerEndpoint}`;
      const res = await fetch(url, { method: 'POST' });

      if (!res.ok) {
        const text = await res.text().catch(() => 'Erreur inconnue');
        throw new Error(text);
      }

      const statusRes = await fetch(`${baseUrl}/scheduler/status`);
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        const jobType = (timeframe === '30m' || timeframe === '1h') ? '30m' : '4h';
        const jobResult = statusData?.jobs?.[jobType]?.last_result;
        if (jobResult) setFetchResult(jobResult);
      }

      await new Promise(resolve => setTimeout(resolve, 500));

      candles.refresh();
      gaps.refresh();
      indicators.refresh();
      signals.refresh();
      alertsHook.check();
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : String(e));
    } finally {
      setFetching(false);
    }
  };

  const timeframeNotSupported = !isTimeframeSupported(timeframe);
  const noData = !candles.loading && candles.candles.length === 0;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <Box
      className="grid-bg"
      sx={{
        minHeight: '100vh',
        background: 'linear-gradient(180deg, #0A0E17 0%, #0D1321 40%, #0A0E17 100%)',
      }}
    >
      {/* ================================================================= */}
      {/* APPBAR PREMIUM — Glassmorphism + gradient accent line              */}
      {/* ================================================================= */}
      <AppBar
        position="sticky"
        elevation={0}
        sx={{
          backgroundColor: 'rgba(10, 14, 23, 0.88)',
          backdropFilter: 'blur(24px)',
          borderBottom: '1px solid rgba(255,255,255,0.04)',
          // Orange gradient accent line at bottom
          '&::after': {
            content: '""',
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            height: '1px',
            background: 'linear-gradient(90deg, transparent, #F7931A40, transparent)',
          },
        }}
      >
        <Toolbar
          sx={{
            gap: { xs: 1, sm: 2 },
            flexWrap: 'wrap',
            minHeight: { xs: 56, sm: 64 },
            py: { xs: 0.5, sm: 0 },
          }}
        >
          {/* Logo + Title */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 36,
                  height: 36,
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #F7931A20, #E6510020)',
                  border: '1px solid #F7931A30',
                }}
              >
                <BitcoinIcon sx={{ color: '#F7931A', fontSize: 22 }} />
              </Box>
              <Box>
                <Typography
                  variant="h6"
                  fontWeight={800}
                  sx={{
                    lineHeight: 1.1,
                    letterSpacing: '-0.02em',
                    fontSize: { xs: '0.9rem', sm: '1rem' },
                    background: 'linear-gradient(135deg, #F7931A, #FFB74D)',
                    backgroundClip: 'text',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                  }}
                >
                  BTC Insight
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    color: 'text.secondary',
                    fontSize: '0.5rem',
                    display: { xs: 'none', sm: 'block' },
                    letterSpacing: '0.1em',
                    textTransform: 'uppercase',
                  }}
                >
                  Trading Assistant v0.9
                </Typography>
              </Box>
            </Box>
          </motion.div>

          {/* Price Ticker */}
          <Box sx={{ display: { xs: 'none', md: 'flex' }, ml: 2 }}>
            <PriceTicker price={currentPrice} loading={indicators.loading} />
          </Box>

          {/* Spacer */}
          <Box sx={{ flex: 1 }} />

          {/* Controls */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.5, sm: 1.5 } }}>
            <FormControl size="small" sx={{ minWidth: { xs: 80, sm: 100 } }}>
              <InputLabel>Timeframe</InputLabel>
              <Select
                value={timeframe}
                label="Timeframe"
                onChange={handleTimeframeChange}
                sx={{ fontSize: { xs: '0.8rem', sm: '0.85rem' } }}
              >
                <MenuItem value="30m">30m</MenuItem>
                <MenuItem value="1h">1h</MenuItem>
                <MenuItem value="4h">4h</MenuItem>
                <MenuItem value="1d">1d</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: { xs: 70, sm: 90 } }}>
              <InputLabel>Jours</InputLabel>
              <Select
                value={String(days)}
                label="Jours"
                onChange={handleDaysChange}
                sx={{ fontSize: { xs: '0.8rem', sm: '0.85rem' } }}
              >
                <MenuItem value="1">1j</MenuItem>
                <MenuItem value="2">2j</MenuItem>
                <MenuItem value="7">7j</MenuItem>
                <MenuItem value="14">14j</MenuItem>
                <MenuItem value="30">30j</MenuItem>
                <MenuItem value="90">90j</MenuItem>
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
                '&:hover': {
                  background: 'linear-gradient(135deg, #FFB74D 0%, #F7931A 100%)',
                  boxShadow: '0 0 24px rgba(247, 147, 26, 0.3)',
                },
                fontSize: { xs: '0.7rem', sm: '0.78rem' },
                px: { xs: 1.5, sm: 2 },
                display: { xs: 'none', sm: 'inline-flex' },
                fontWeight: 700,
              }}
            >
              {fetching ? 'Fetch...' : 'Fetch API'}
            </Button>

            <Tooltip title="Récupérer les données">
              <IconButton
                onClick={handleFetchCandles}
                disabled={fetching || timeframeNotSupported}
                sx={{
                  color: '#F7931A',
                  display: { xs: 'inline-flex', sm: 'none' },
                }}
                size="small"
              >
                <FetchIcon />
              </IconButton>
            </Tooltip>

            <Tooltip title="Actualiser toutes les données">
              <IconButton
                onClick={handleRefreshAll}
                disabled={indicators.loading || gaps.loading || candles.loading || signals.loading}
                sx={{
                  color: 'text.secondary',
                  transition: 'all 0.3s ease',
                  '&:hover': { color: '#F7931A', transform: 'rotate(180deg)' },
                }}
                size="small"
              >
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ pt: { xs: 1.5, sm: 2.5 }, pb: 4, px: { xs: 1.5, sm: 3 } }}>
        {/* Mobile Price Ticker */}
        <Box sx={{ display: { xs: 'block', md: 'none' }, mb: 1.5 }}>
          <PriceTicker price={currentPrice} loading={indicators.loading} />
        </Box>

        {/* ================================================================= */}
        {/* FETCH RESULT INFO */}
        {/* ================================================================= */}
        <AnimatePresence>
          {fetchResult && fetchResult.status === 'success' && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
            >
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
                  <Chip label={`${fetchResult.timeframe}`} size="small" color="primary" variant="outlined" />
                  <Chip label={`${fetchResult.fetched ?? 0} fetched`} size="small" variant="outlined" />
                  <Chip label={`${fetchResult.inserted ?? 0} inserted`} size="small" color="success" variant="outlined" />
                  <Chip label={`${fetchResult.updated ?? 0} updated`} size="small" color="info" variant="outlined" />
                  {fetchResult.resample && (
                    <>
                      {fetchResult.resample['1h'] > 0 && <Chip label={`1h: ${fetchResult.resample['1h']}`} size="small" color="secondary" />}
                      {fetchResult.resample['1d'] > 0 && <Chip label={`1d: ${fetchResult.resample['1d']}`} size="small" color="secondary" />}
                    </>
                  )}
                </Stack>
              </Alert>
            </motion.div>
          )}
        </AnimatePresence>

        {fetchResult && fetchResult.status === 'error' && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setFetchResult(null)}>
            Erreur lors du fetch: {fetchResult.error}
          </Alert>
        )}

        {/* Warnings */}
        {timeframeNotSupported && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Le timeframe "{timeframe}" n'est pas supporté.
          </Alert>
        )}
        {fetchError && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setFetchError(null)}>
            {fetchError}
          </Alert>
        )}
        {historyCapped && (
          <Alert severity="info" icon={<InfoIcon />} sx={{ mb: 2 }}>
            <strong>Source Binance :</strong> Toutes les combinaisons timeframe/jours sont supportées.
          </Alert>
        )}

        {/* ================================================================= */}
        {/* STATUS ROW */}
        {/* ================================================================= */}
        <Box sx={{ mb: 2.5 }}>
          <StatusRowConnected timeframe={timeframe} days={effectiveDays} />
        </Box>

        {/* ================================================================= */}
        {/* ZONE 1 — CHART HERO                                               */}
        {/* ================================================================= */}
        <Box sx={{ mb: 3 }}>
          {candles.error && <Alert severity="error" sx={{ mb: 2 }}>{candles.error}</Alert>}
          {noData && !candles.error && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Aucune donnée pour {timeframe} / {effectiveDays}j. Cliquez sur "Fetch API".
            </Alert>
          )}
          <ChartErrorBoundary fallbackMessage="Le graphique a rencontré une erreur.">
            <CandlestickChart
              candles={candles.candles}
              symbol={symbol}
              timeframe={timeframe}
              loading={candles.loading}
            />
          </ChartErrorBoundary>
        </Box>

        {/* ================================================================= */}
        {/* ZONE 2 — ANALYSE RAPIDE (3 colonnes)                              */}
        {/* ================================================================= */}
        <SectionHeader icon="📊" title="Analyse du marché" accentColor="#7C4DFF" delay={0.1} />

        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} md={6} lg={4}>
            <SignalPanel
              data={signals.data}
              loading={signals.loading}
              error={signals.error}
              onRefresh={signals.refresh}
              timeframe={timeframe}
              historyDays={effectiveDays}
            />
          </Grid>

          <Grid item xs={12} md={6} lg={4}>
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
          </Grid>

          <Grid item xs={12} md={12} lg={4}>
            <NewsPanel
              data={news.data}
              loading={news.loading}
              error={news.error}
              onRefresh={news.refresh}
            />
          </Grid>
        </Grid>

        {/* ================================================================= */}
        {/* ZONE 3 — DONNÉES TECHNIQUES                                       */}
        {/* ================================================================= */}
        <SectionHeader icon="🔬" title="Données techniques détaillées" accentColor="#448AFF" delay={0.2} />

        <IndicatorPanel
          data={indicators.data}
          loading={indicators.loading}
          error={indicators.error}
          onRefresh={indicators.refresh}
          timeframe={timeframe}
          historyDays={effectiveDays}
        />
      </Container>
    </Box>
  );
};

export default Dashboard;
