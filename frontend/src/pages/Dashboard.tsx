// =============================================================================
// Dashboard.tsx — Premium dark trading dashboard with tabbed navigation
// =============================================================================

import React, { useState, useEffect, useCallback, useRef } from 'react';
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
  Drawer,
  Badge,
  Snackbar,
  Divider,
  Tab,
  Tabs,
  alpha,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CloudDownload as FetchIcon,
  CheckCircle as SuccessIcon,
  CurrencyBitcoin as BitcoinIcon,
  NotificationsNone as NotificationsNoneIcon,
  NotificationsActive as NotificationsActiveIcon,
  Close as CloseIcon,
  Keyboard as KeyboardIcon,
  Dashboard as DashboardIcon,
  ShowChart as AnalyseIcon,
  AccountBalance as TradingIcon,
  Science as BacktestIcon,
  Newspaper as NewsIcon,
  BatteryChargingFull as LowBandwidthIcon,
} from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';

// Composants
import { StatusRowConnected } from '../components/StatusRow';
import { IndicatorPanel } from '../components/IndicatorPanel';
import { SignalPanel } from '../components/SignalPanel';
import { AlertPanel } from '../components/AlertPanel';
import { NewsPanel } from '../components/NewsPanel';
import { DecisionPanel } from '../components/DecisionPanel';
import { BacktestPanel } from '../components/BacktestPanel';
import { VerificationPanel } from '../components/VerificationPanel';
import { QuickMetricsBar } from '../components/QuickMetricsBar';
import RiskPanel from '../components/RiskPanel';
import PaperTradingPanel from '../components/PaperTradingPanel';
import JournalPanel from '../components/JournalPanel';
import DiagnosticPanel from '../components/DiagnosticPanel';
import CandlestickChart from '../components/CandlestickChart';
import { ChartErrorBoundary } from '../components/ErrorBoundary';
import { PriceTicker } from '../components/PriceTicker';

// Hooks
import { useIndicators } from '../hooks/useIndicators';
import { useMarketGaps } from '../hooks/useMarketGaps';
import { useCandles } from '../hooks/useCandles';
import { useSignals } from '../hooks/useSignals';
import { useAlerts } from '../hooks/useAlerts';
import { useNews } from '../hooks/useNews';
import { useLivePrice } from '../hooks/useLivePrice';
import { useDecision } from '../hooks/useDecision';
import { useBacktest } from '../hooks/useBacktest';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

type TimeframeOption = '1m' | '3m' | '5m' | '15m' | '30m' | '1h' | '2h' | '4h' | '6h' | '8h' | '12h' | '1d' | '3d' | '1w';
type DaysOption = 0.0625 | 0.125 | 0.25 | 0.5 | 1 | 2 | 3 | 5 | 7 | 14 | 30 | 60 | 90 | 180 | 365;

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

const SUPPORTED_TIMEFRAMES: TimeframeOption[] = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w'];

function isTimeframeSupported(tf: TimeframeOption): boolean {
  return SUPPORTED_TIMEFRAMES.includes(tf);
}

function formatDuration(days: number): string {
  if (days < 1) {
    const hours = days * 24;
    if (hours === Math.floor(hours)) return `${hours}h`;
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    return `${h}h${m.toString().padStart(2, '0')}`;
  }
  if (days === 365) return '1an';
  return `${days}j`;
}

// Largeur du panneau d'alertes latéral
const ALERT_DRAWER_WIDTH = 420;

// -----------------------------------------------------------------------------
// Tab definitions
// -----------------------------------------------------------------------------

interface TabDef {
  label: string;
  icon: React.ReactElement;
  shortcut: string;
  color: string;
}

const TAB_DEFS: TabDef[] = [
  { label: 'Dashboard',  icon: <DashboardIcon />, shortcut: '1', color: '#F7931A' },
  { label: 'Analyse',    icon: <AnalyseIcon />,   shortcut: '2', color: '#448AFF' },
  { label: 'Trading',    icon: <TradingIcon />,    shortcut: '3', color: '#00E676' },
  { label: 'Backtest',   icon: <BacktestIcon />,   shortcut: '4', color: '#B388FF' },
  { label: 'News',       icon: <NewsIcon />,       shortcut: '5', color: '#FFD600' },
];

// TabPanel — Garde le contenu monté mais caché (pour préserver l'état des hooks)
const TabPanel: React.FC<{
  value: number;
  index: number;
  children: React.ReactNode;
}> = ({ value, index, children }) => (
  <Box
    role="tabpanel"
    id={`tab-panel-${index}`}
    aria-labelledby={`tab-${index}`}
    sx={{
      display: value === index ? 'block' : 'none',
    }}
  >
    {children}
  </Box>
);

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

const Dashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [timeframe, setTimeframe] = useState<TimeframeOption>('4h');
  const [days, setDays] = useState<DaysOption>(7);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [fetchResult, setFetchResult] = useState<FetchResult | null>(null);
  const [alertDrawerOpen, setAlertDrawerOpen] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState<string | null>(null);

  // Mode low-bandwidth — désactive le WebSocket et réduit les pollings
  // Utile pour les runs de nuit ou connexion mobile limitée
  const [lowBandwidth, setLowBandwidth] = useState(false);

  // Compteur de trades — incrémenté à chaque trade exécuté dans PaperTradingPanel
  // Utilisé pour déclencher le rafraîchissement automatique du JournalPanel et DiagnosticPanel
  const [tradeVersion, setTradeVersion] = useState(0);
  const handleTradeExecuted = useCallback(() => {
    setTradeVersion(prev => prev + 1);
  }, []);

  // Appelé après un reset (daily loss ou full reset) pour forcer le refresh
  // de tous les panels dépendants : JournalPanel, DiagnosticPanel, RiskPanel
  const handleResetComplete = useCallback(() => {
    setTradeVersion(prev => prev + 1);
  }, []);

  const symbol = 'BTC/USD';
  const effectiveDays = days;

  // ---------------------------------------------------------------------------
  // Hooks — Toujours initialisés (indépendamment de l'onglet actif)
  // ---------------------------------------------------------------------------
  const indicators = useIndicators({ timeframe, historyDays: effectiveDays });
  const gaps = useMarketGaps({ timeframe, days: effectiveDays });
  const candles = useCandles({ timeframe, days: effectiveDays });
  const signals = useSignals({ timeframe, historyDays: effectiveDays });
  const decision = useDecision({ timeframe, historyDays: effectiveDays });
  const alertsHook = useAlerts({ timeframe, pollInterval: lowBandwidth ? 300000 : 60000 });
  const news = useNews({ limit: 20, pollInterval: lowBandwidth ? 900000 : 300000 });
  const backtest = useBacktest();

  const livePrice = useLivePrice({ enabled: !lowBandwidth });
  const currentPrice = livePrice.price ?? indicators.data?.latest?.close ?? null;

  const alertNotificationCount = alertsHook.notifications.length;
  const alertActiveCount = alertsHook.alerts.filter(a => a.status === 'active').length;

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

  const handleTabChange = (_: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const handleRefreshAll = useCallback(() => {
    indicators.refresh();
    gaps.refresh();
    candles.refresh();
    signals.refresh();
    decision.refresh();
    alertsHook.refresh();
    news.refresh();
    setSnackbarMsg('✓ Données rafraîchies');
  }, [indicators.refresh, gaps.refresh, candles.refresh, signals.refresh, decision.refresh, alertsHook.refresh, news.refresh]);

  // Keyboard shortcuts — ref pour éviter deps circulaires
  const handleFetchCandlesRef = useRef<() => void>(() => {});

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'select' || tag === 'textarea') return;

      // Raccourcis numériques pour les onglets
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        const tabIndex = parseInt(e.key) - 1;
        if (tabIndex >= 0 && tabIndex < TAB_DEFS.length) {
          e.preventDefault();
          setActiveTab(tabIndex);
          return;
        }
      }

      switch (e.key.toLowerCase()) {
        case 'r':
          e.preventDefault();
          handleRefreshAll();
          break;
        case 'f':
          if (!e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            handleFetchCandlesRef.current();
          }
          break;
        case 'a':
          e.preventDefault();
          setAlertDrawerOpen(prev => !prev);
          break;
        case 'escape':
          setAlertDrawerOpen(false);
          break;
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleRefreshAll]);

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

      const fetchUrl = `${baseUrl}/market/candles/fetch?timeframe=${encodeURIComponent(timeframe)}&days=${effectiveDays}`;
      const res = await fetch(fetchUrl, { method: 'POST' });

      if (!res.ok) {
        const text = await res.text().catch(() => 'Erreur inconnue');
        throw new Error(text);
      }

      const result = await res.json();

      setFetchResult({
        status: 'success',
        timeframe: result.timeframe ?? timeframe,
        fetched: result.fetched ?? 0,
        inserted: result.inserted ?? 0,
        updated: result.updated ?? 0,
        duplicates: result.duplicates ?? 0,
        resample: result.resample ?? undefined,
        duration_seconds: result.duration_seconds ?? undefined,
      });

      await new Promise(resolve => setTimeout(resolve, 300));

      candles.refresh();
      gaps.refresh();
      indicators.refresh();
      signals.refresh();
      decision.refresh();
      alertsHook.check();
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : String(e));
    } finally {
      setFetching(false);
    }
  };

  handleFetchCandlesRef.current = handleFetchCandles;

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
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* ================================================================= */}
      {/* APPBAR PREMIUM                                                     */}
      {/* ================================================================= */}
      <AppBar
        position="sticky"
        elevation={0}
        sx={{
          backgroundColor: 'rgba(10, 14, 23, 0.88)',
          backdropFilter: 'blur(24px)',
          borderBottom: '1px solid rgba(255,255,255,0.04)',
          zIndex: 1201,
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
                  Trading Assistant v1.4
                </Typography>
              </Box>
            </Box>
          </motion.div>

          {/* Price Ticker */}
          <Box sx={{ display: { xs: 'none', md: 'flex' }, ml: 2 }}>
            <PriceTicker
              price={currentPrice}
              previousPrice={livePrice.previousPrice}
              change24h={livePrice.change24h}
              high24h={livePrice.high24h}
              low24h={livePrice.low24h}
              volume24h={livePrice.volume24h}
              connected={livePrice.connected}
              loading={!livePrice.connected && indicators.loading}
            />
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
                <MenuItem value="1m">1m</MenuItem>
                <MenuItem value="3m">3m</MenuItem>
                <MenuItem value="5m">5m</MenuItem>
                <MenuItem value="15m">15m</MenuItem>
                <MenuItem value="30m">30m</MenuItem>
                <MenuItem value="1h">1h</MenuItem>
                <MenuItem value="2h">2h</MenuItem>
                <MenuItem value="4h">4h</MenuItem>
                <MenuItem value="6h">6h</MenuItem>
                <MenuItem value="8h">8h</MenuItem>
                <MenuItem value="12h">12h</MenuItem>
                <MenuItem value="1d">1d</MenuItem>
                <MenuItem value="3d">3d</MenuItem>
                <MenuItem value="1w">1w</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: { xs: 70, sm: 90 } }}>
              <InputLabel>Durée</InputLabel>
              <Select
                value={String(days)}
                label="Durée"
                onChange={handleDaysChange}
                sx={{ fontSize: { xs: '0.8rem', sm: '0.85rem' } }}
              >
                <MenuItem value="0.0625">1h30</MenuItem>
                <MenuItem value="0.125">3h</MenuItem>
                <MenuItem value="0.25">6h</MenuItem>
                <MenuItem value="0.5">12h</MenuItem>
                <MenuItem value="1">1j</MenuItem>
                <MenuItem value="2">2j</MenuItem>
                <MenuItem value="3">3j</MenuItem>
                <MenuItem value="5">5j</MenuItem>
                <MenuItem value="7">7j</MenuItem>
                <MenuItem value="14">14j</MenuItem>
                <MenuItem value="30">30j</MenuItem>
                <MenuItem value="60">60j</MenuItem>
                <MenuItem value="90">90j</MenuItem>
                <MenuItem value="180">180j</MenuItem>
                <MenuItem value="365">1an</MenuItem>
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

            <Tooltip title="Actualiser toutes les données (R)">
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

            {/* Bouton Low-Bandwidth Mode */}
            <Tooltip title={lowBandwidth
              ? '🌙 Mode Low-Bandwidth actif — WebSocket OFF, polling réduit. Cliquer pour désactiver.'
              : '🌙 Activer le mode Low-Bandwidth (coupe le WebSocket, réduit le polling)'
            }>
              <IconButton
                onClick={() => {
                  setLowBandwidth(prev => !prev);
                  setSnackbarMsg(lowBandwidth ? '🔌 Mode normal rétabli' : '🌙 Mode Low-Bandwidth activé');
                }}
                size="small"
                sx={{
                  color: lowBandwidth ? '#00E676' : 'text.secondary',
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    color: '#00E676',
                    backgroundColor: 'rgba(0, 230, 118, 0.08)',
                  },
                }}
              >
                <LowBandwidthIcon sx={{ fontSize: 20 }} />
              </IconButton>
            </Tooltip>

            {/* Bouton Alertes — ouvre le panneau latéral droit */}
            <Tooltip title={`Alertes${alertActiveCount > 0 ? ` (${alertActiveCount} actives)` : ''} (A)`}>
              <IconButton
                onClick={() => setAlertDrawerOpen(true)}
                size="small"
                sx={{
                  color: alertNotificationCount > 0 ? '#ff9800' : 'text.secondary',
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    color: '#F7931A',
                    backgroundColor: 'rgba(247, 147, 26, 0.08)',
                  },
                }}
              >
                <Badge
                  badgeContent={alertNotificationCount}
                  color="error"
                  invisible={alertNotificationCount === 0}
                  sx={{
                    '& .MuiBadge-badge': {
                      animation: alertNotificationCount > 0 ? 'pulse-glow 2s ease-in-out infinite' : 'none',
                      fontSize: '0.6rem',
                      height: 16,
                      minWidth: 16,
                    },
                  }}
                >
                  {alertNotificationCount > 0 ? (
                    <NotificationsActiveIcon />
                  ) : (
                    <NotificationsNoneIcon />
                  )}
                </Badge>
              </IconButton>
            </Tooltip>
          </Box>
        </Toolbar>

        {/* ================================================================= */}
        {/* TABS NAVIGATION — Sous la toolbar                                  */}
        {/* ================================================================= */}
        <Box
          sx={{
            px: { xs: 1, sm: 2 },
            backgroundColor: 'rgba(10, 14, 23, 0.5)',
            borderTop: '1px solid rgba(255,255,255,0.03)',
          }}
        >
          <Tabs
            value={activeTab}
            onChange={handleTabChange}
            variant="scrollable"
            scrollButtons="auto"
            allowScrollButtonsMobile
            sx={{
              minHeight: 44,
              '& .MuiTabs-indicator': {
                height: 3,
                borderRadius: '3px 3px 0 0',
                background: `linear-gradient(90deg, ${TAB_DEFS[activeTab].color}, ${alpha(TAB_DEFS[activeTab].color, 0.5)})`,
                boxShadow: `0 0 12px ${alpha(TAB_DEFS[activeTab].color, 0.4)}`,
              },
              '& .MuiTabs-scrollButtons': {
                color: 'text.secondary',
                '&.Mui-disabled': { opacity: 0.2 },
              },
            }}
          >
            {TAB_DEFS.map((tab, i) => (
              <Tab
                key={tab.label}
                icon={tab.icon}
                iconPosition="start"
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <span>{tab.label}</span>
                    <Typography
                      component="span"
                      sx={{
                        display: { xs: 'none', sm: 'inline' },
                        fontSize: '0.55rem',
                        color: 'text.secondary',
                        opacity: 0.5,
                        fontFamily: 'monospace',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '3px',
                        px: 0.5,
                        py: '1px',
                        lineHeight: 1.2,
                      }}
                    >
                      {tab.shortcut}
                    </Typography>
                  </Box>
                }
                id={`tab-${i}`}
                aria-controls={`tab-panel-${i}`}
                sx={{
                  minHeight: 44,
                  textTransform: 'none',
                  fontWeight: activeTab === i ? 700 : 500,
                  fontSize: { xs: '0.75rem', sm: '0.82rem' },
                  color: activeTab === i ? tab.color : 'text.secondary',
                  px: { xs: 1.5, sm: 2 },
                  transition: 'all 0.25s ease',
                  '&:hover': {
                    color: tab.color,
                    backgroundColor: alpha(tab.color, 0.06),
                  },
                  '&.Mui-selected': {
                    color: tab.color,
                  },
                  '& .MuiSvgIcon-root': {
                    fontSize: '1.1rem',
                    mr: 0.5,
                  },
                }}
              />
            ))}
          </Tabs>
        </Box>
      </AppBar>

      {/* ================================================================= */}
      {/* DRAWER ALERTES — Panneau latéral droit                             */}
      {/* ================================================================= */}
      <Drawer
        anchor="right"
        open={alertDrawerOpen}
        onClose={() => setAlertDrawerOpen(false)}
        PaperProps={{
          sx: {
            width: { xs: '100%', sm: ALERT_DRAWER_WIDTH },
            maxWidth: '100vw',
            background: 'linear-gradient(180deg, #0D1321 0%, #0A0E17 100%)',
            borderLeft: '1px solid rgba(255,255,255,0.06)',
            boxShadow: '-8px 0 40px rgba(0,0,0,0.5)',
          },
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            px: 2,
            py: 1.5,
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            background: 'rgba(247, 147, 26, 0.03)',
          }}
        >
          <Typography
            variant="h6"
            fontWeight={800}
            sx={{
              fontSize: '1rem',
              background: 'linear-gradient(135deg, #F7931A, #FFB74D)',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            🔔 Alertes & Notifications
          </Typography>
          <IconButton
            onClick={() => setAlertDrawerOpen(false)}
            size="small"
            sx={{ color: 'text.secondary' }}
          >
            <CloseIcon />
          </IconButton>
        </Box>

        <Box sx={{ overflow: 'auto', flex: 1 }}>
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
        </Box>
      </Drawer>

      {/* ================================================================= */}
      {/* MAIN CONTENT — Onglets                                             */}
      {/* ================================================================= */}
      <Box sx={{ flex: 1 }}>
        <Container maxWidth="xl" sx={{ pt: { xs: 1.5, sm: 2 }, pb: 4, px: { xs: 1.5, sm: 3 } }}>
          {/* Mobile Price Ticker */}
          <Box sx={{ display: { xs: 'block', md: 'none' }, mb: 1.5 }}>
            <PriceTicker
              price={currentPrice}
              previousPrice={livePrice.previousPrice}
              change24h={livePrice.change24h}
              high24h={livePrice.high24h}
              low24h={livePrice.low24h}
              volume24h={livePrice.volume24h}
              connected={livePrice.connected}
              loading={!livePrice.connected && indicators.loading}
            />
          </Box>

          {/* Fetch Result / Errors — Toujours visible */}
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

          {/* ============================================================= */}
          {/* TAB 0 — DASHBOARD (Chart + Quick Metrics + Décision)           */}
          {/* ============================================================= */}
          <TabPanel value={activeTab} index={0}>
            {/* Status Row */}
            <Box sx={{ mb: 2 }}>
              <StatusRowConnected timeframe={timeframe} days={effectiveDays} />
            </Box>

            {/* Chart Hero */}
            <Box sx={{ mb: 2 }}>
              {candles.error && <Alert severity="error" sx={{ mb: 2 }}>{candles.error}</Alert>}
              {noData && !candles.error && (
                <Alert severity="info" sx={{ mb: 2 }}>
                  Aucune donnée pour {timeframe} / {formatDuration(effectiveDays)}. Cliquez sur "Fetch API".
                </Alert>
              )}
              <ChartErrorBoundary fallbackMessage="Le graphique a rencontré une erreur.">
                <CandlestickChart
                  candles={candles.candles}
                  symbol={symbol}
                  timeframe={timeframe}
                  loading={candles.loading}
                  livePrice={currentPrice}
                />
              </ChartErrorBoundary>
            </Box>

            {/* Quick Metrics */}
            <Box sx={{ mb: 3 }}>
              <QuickMetricsBar
                decision={decision.data}
                signals={signals.data}
                news={news.data}
                loading={decision.loading || signals.loading}
              />
            </Box>

            {/* Décision + Signaux résumé */}
            <Grid container spacing={2.5}>
              <Grid item xs={12} md={6}>
                <DecisionPanel
                  data={decision.data}
                  loading={decision.loading}
                  error={decision.error}
                  onRefresh={decision.refresh}
                  timeframe={timeframe}
                  historyDays={effectiveDays}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <SignalPanel
                  data={signals.data}
                  loading={signals.loading}
                  error={signals.error}
                  onRefresh={signals.refresh}
                  timeframe={timeframe}
                  historyDays={effectiveDays}
                />
              </Grid>
            </Grid>
          </TabPanel>

          {/* ============================================================= */}
          {/* TAB 1 — ANALYSE (Signaux + Indicateurs détaillés)              */}
          {/* ============================================================= */}
          <TabPanel value={activeTab} index={1}>
            <Grid container spacing={2.5} sx={{ mb: 3 }}>
              <Grid item xs={12} md={6}>
                <SignalPanel
                  data={signals.data}
                  loading={signals.loading}
                  error={signals.error}
                  onRefresh={signals.refresh}
                  timeframe={timeframe}
                  historyDays={effectiveDays}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <DecisionPanel
                  data={decision.data}
                  loading={decision.loading}
                  error={decision.error}
                  onRefresh={decision.refresh}
                  timeframe={timeframe}
                  historyDays={effectiveDays}
                />
              </Grid>
            </Grid>

            <IndicatorPanel
              data={indicators.data}
              loading={indicators.loading}
              error={indicators.error}
              onRefresh={indicators.refresh}
              timeframe={timeframe}
              historyDays={effectiveDays}
            />
          </TabPanel>

          {/* ============================================================= */}
          {/* TAB 2 — TRADING (Risk + Paper Trading + Journal)               */}
          {/* ============================================================= */}
          <TabPanel value={activeTab} index={2}>
            <Grid container spacing={2.5}>
              <Grid item xs={12} lg={5}>
                <Box sx={{
                  bgcolor: 'rgba(255,255,255,0.03)',
                  borderRadius: 2,
                  p: 2,
                  border: '1px solid rgba(255,255,255,0.06)',
                  height: '100%',
                }}>
                  <RiskPanel refreshTrigger={tradeVersion} />
                </Box>
              </Grid>
              <Grid item xs={12} lg={7}>
                <Box sx={{
                  bgcolor: 'rgba(255,255,255,0.03)',
                  borderRadius: 2,
                  p: 2,
                  border: '1px solid rgba(255,255,255,0.06)',
                }}>
                  <PaperTradingPanel onTradeExecuted={handleTradeExecuted} onResetComplete={handleResetComplete} />
                </Box>
              </Grid>
              {/* Journal d'évaluation — Pleine largeur */}
              <Grid item xs={12}>
                <Box sx={{
                  bgcolor: 'rgba(255,255,255,0.03)',
                  borderRadius: 2,
                  p: 2,
                  border: '1px solid rgba(255,255,255,0.06)',
                }}>
                  <JournalPanel refreshTrigger={tradeVersion} />
                </Box>
              </Grid>
              <Grid item xs={12}>
                <Box sx={{
                  bgcolor: 'rgba(255,255,255,0.03)',
                  borderRadius: 2,
                  p: 2,
                  border: '1px solid rgba(255,255,255,0.06)',
                }}>
                  <DiagnosticPanel refreshTrigger={tradeVersion} />
                </Box>
              </Grid>
            </Grid>
          </TabPanel>

          {/* ============================================================= */}
          {/* TAB 3 — BACKTEST (Backtest + Vérification historique)           */}
          {/* ============================================================= */}
          <TabPanel value={activeTab} index={3}>
            <Grid container spacing={2.5} sx={{ mb: 3 }}>
              <Grid item xs={12}>
                <BacktestPanel
                  data={backtest.data}
                  loading={backtest.loading}
                  error={backtest.error}
                  onLaunch={(config) => backtest.launch({
                    ...config,
                    symbol: symbol,
                  })}
                  timeframe={timeframe}
                />
              </Grid>
            </Grid>

            <VerificationPanel />
          </TabPanel>

          {/* ============================================================= */}
          {/* TAB 4 — NEWS                                                    */}
          {/* ============================================================= */}
          <TabPanel value={activeTab} index={4}>
            <NewsPanel
              data={news.data}
              loading={news.loading}
              error={news.error}
              onRefresh={news.refresh}
            />
          </TabPanel>
        </Container>
      </Box>

      {/* ================================================================= */}
      {/* FOOTER                                                              */}
      {/* ================================================================= */}
      <Box
        component="footer"
        sx={{
          py: 2,
          px: 3,
          borderTop: '1px solid rgba(255,255,255,0.04)',
          background: 'rgba(10, 14, 23, 0.6)',
          backdropFilter: 'blur(12px)',
          position: 'relative',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '1px',
            background: 'linear-gradient(90deg, transparent, #F7931A30, transparent)',
          },
        }}
      >
        <Container maxWidth="xl">
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 2,
            }}
          >
            {/* Left: Brand */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 700,
                  fontSize: '0.65rem',
                  background: 'linear-gradient(135deg, #F7931A, #FFB74D)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                BTC Insight v1.4.0
              </Typography>
              <Divider orientation="vertical" flexItem sx={{ mx: 0.5, borderColor: 'rgba(255,255,255,0.08)' }} />
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.6rem' }}>
                © {new Date().getFullYear()} Bitcoin Trading Assistant
              </Typography>
            </Box>

            {/* Center: Keyboard shortcuts */}
            <Tooltip
              title={
                <Box sx={{ p: 0.5 }}>
                  <Typography variant="caption" sx={{ fontWeight: 700, display: 'block', mb: 0.5 }}>
                    Raccourcis clavier
                  </Typography>
                  <Typography variant="caption" sx={{ display: 'block' }}>1-5 — Changer d'onglet</Typography>
                  <Typography variant="caption" sx={{ display: 'block' }}>R — Rafraîchir les données</Typography>
                  <Typography variant="caption" sx={{ display: 'block' }}>F — Fetch API</Typography>
                  <Typography variant="caption" sx={{ display: 'block' }}>A — Ouvrir/Fermer les alertes</Typography>
                  <Typography variant="caption" sx={{ display: 'block' }}>Esc — Fermer le panneau</Typography>
                </Box>
              }
              arrow
            >
              <Box
                sx={{
                  display: { xs: 'none', sm: 'flex' },
                  alignItems: 'center',
                  gap: 0.5,
                  cursor: 'help',
                }}
              >
                <KeyboardIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.6rem' }}>
                  1-5 Onglets • R Rafraîchir • F Fetch • A Alertes
                </Typography>
              </Box>
            </Tooltip>

            {/* Right: Data status */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Box
                sx={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  backgroundColor: livePrice.connected ? '#00E676' : '#FF1744',
                  animation: livePrice.connected ? 'pulse-dot 2s ease-in-out infinite' : 'none',
                }}
              />
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.6rem' }}>
                {livePrice.connected ? 'WebSocket connecté' : 'WebSocket déconnecté'}
              </Typography>
            </Box>
          </Box>
        </Container>
      </Box>


      {/* ================================================================= */}
      {/* SNACKBAR: Feedback actions                                          */}
      {/* ================================================================= */}
      <Snackbar
        open={!!snackbarMsg}
        autoHideDuration={2000}
        onClose={() => setSnackbarMsg(null)}
        message={snackbarMsg}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        sx={{
          '& .MuiSnackbarContent-root': {
            background: 'rgba(17, 24, 39, 0.9)',
            backdropFilter: 'blur(12px)',
            border: '1px solid rgba(247, 147, 26, 0.2)',
            borderRadius: 2,
            fontWeight: 600,
            fontSize: '0.8rem',
          },
        }}
      />
    </Box>
  );
};

export default Dashboard;
