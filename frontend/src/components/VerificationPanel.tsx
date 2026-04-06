// =============================================================================
// VerificationPanel.tsx — Time-Travel Backtest UI
// Permet de : charger l'historique, vérifier à une date, lancer un walk-forward
// =============================================================================

import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  Button,
  CardContent,
  Chip,
  Stack,
  TextField,
  CircularProgress,
  Alert,
  Collapse,
  IconButton,
  Divider,
  LinearProgress,
  Tooltip,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  FormControlLabel,
  Checkbox,
} from '@mui/material';
import {
  History as HistoryIcon,
  CloudDownload as DownloadIcon,
  Search as SearchIcon,
  Timeline as TimelineIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  CheckCircle as CheckIcon,
  Cancel as CancelIcon,
  TrendingUp as TrendUpIcon,
  TrendingDown as TrendDownIcon,
  Remove as FlatIcon,
  CompareArrows as CompareIcon,
  VerifiedUser as IntegrityIcon,
  Info as InfoIcon,
  HelpOutline as HelpIcon,
} from '@mui/icons-material';

import { GlowingCard, ACCENT } from './GlowingCard';
import {
  loadHistory,
  getHistoryRange,
  getHistoryIntegrity,
  verifyAtDate,
  runWalkForward,
  loadSentimentHistory,
  getSentimentRange,
  getInterestingDates,
} from '../api/marketApi';
import type {
  HistoryRangeResponse,
  HistoryLoadResponse,
  HistoryIntegrityResponse,
  HistoryIntegrityGap,
  VerificationResult,
  WalkForwardResult,
  HorizonOutcome,
  HorizonAccuracy,
  SentimentRangeResponse,
  SentimentLoadResponse,
  InterestingDatesResponse,
} from '../types';

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

const pnlColor = (val: number) => (val > 0 ? '#00E676' : val < 0 ? '#FF1744' : 'text.secondary');

/** Formate un horizon fractionnaire (jours) en label lisible */
const formatHorizonLabel = (horizonDays: number): string => {
  const minutes = horizonDays * 24 * 60;
  if (minutes < 60) return `${Math.round(minutes)}min`;
  if (minutes < 1440) {
    const h = minutes / 60;
    return h === Math.floor(h) ? `${Math.floor(h)}h` : `${h.toFixed(1)}h`;
  }
  const d = horizonDays;
  return d === Math.floor(d) ? `${Math.floor(d)}j` : `${d.toFixed(1)}j`;
};

const DirectionIcon: React.FC<{ direction: string }> = ({ direction }) => {
  if (direction === 'hausse') return <TrendUpIcon sx={{ fontSize: 16, color: '#00E676' }} />;
  if (direction === 'baisse') return <TrendDownIcon sx={{ fontSize: 16, color: '#FF1744' }} />;
  return <FlatIcon sx={{ fontSize: 16, color: '#FFB74D' }} />;
};

const ActionChip: React.FC<{ action: string }> = ({ action }) => {
  const colorMap: Record<string, 'success' | 'error' | 'warning' | 'default'> = {
    acheter: 'success',
    vendre: 'error',
    attendre: 'warning',
  };
  return (
    <Chip
      label={action.toUpperCase()}
      size="small"
      color={colorMap[action] || 'default'}
      sx={{ fontSize: '0.65rem', fontWeight: 700, height: 22 }}
    />
  );
};

const AccuracyBar: React.FC<{ accuracy: number; label: string }> = ({ accuracy, label }) => {
  const color = accuracy >= 60 ? '#00E676' : accuracy >= 40 ? '#FFB74D' : '#FF1744';
  return (
    <Box sx={{ flex: 1, minWidth: 100 }}>
      <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
        {label}
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <LinearProgress
          variant="determinate"
          value={accuracy}
          sx={{
            flex: 1, height: 8, borderRadius: 4,
            bgcolor: 'rgba(255,255,255,0.05)',
            '& .MuiLinearProgress-bar': { bgcolor: color, borderRadius: 4 },
          }}
        />
        <Typography
          variant="caption"
          sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700, color, minWidth: 36, fontSize: '0.8rem' }}
        >
          {accuracy.toFixed(0)}%
        </Typography>
      </Box>
    </Box>
  );
};

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const VerificationPanel: React.FC = () => {
  // State: History loading
  const [range, setRange] = useState<HistoryRangeResponse | null>(null);
  const [loadResult, setLoadResult] = useState<HistoryLoadResponse | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadTimeframe, setLoadTimeframe] = useState('1d');

  // State: Integrity
  const [integrity, setIntegrity] = useState<HistoryIntegrityResponse | null>(null);
  const [loadingIntegrity, setLoadingIntegrity] = useState(false);

  // State: Single verification
  const [targetDate, setTargetDate] = useState('2020-01-01');
  const [verifyResult, setVerifyResult] = useState<VerificationResult | null>(null);
  const [verifying, setVerifying] = useState(false);

  // State: Walk-forward
  const [wfStartDate, setWfStartDate] = useState('2018-01-01');
  const [wfEndDate, setWfEndDate] = useState('2025-01-01');
  const [wfStepDays, setWfStepDays] = useState(30);
  const [wfCompareMode, setWfCompareMode] = useState(false);
  const [wfResult, setWfResult] = useState<WalkForwardResult | null>(null);
  const [walkingForward, setWalkingForward] = useState(false);

  // State: Horizon mode (scalping / intraday / swing)
  const [horizonMode, setHorizonMode] = useState<'scalping' | 'intraday' | 'swing'>('swing');

  // State: UI
  const [showOutcomes, setShowOutcomes] = useState(true);
  const [showWfDetails, setShowWfDetails] = useState(false);
  const [showComparison, setShowComparison] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // State: Interesting dates
  const [interestingDates, setInterestingDates] = useState<InterestingDatesResponse | null>(null);
  const [loadingInteresting, setLoadingInteresting] = useState(false);

  // Pas minimum et valeurs par défaut selon le mode horizon
  const STEP_CONFIG: Record<string, { min: number; step: number; default: number; label: string }> = {
    scalping: { min: 0.01, step: 0.01, default: 0.25, label: 'Pas (j) — 0.01=15min, 0.04=1h, 0.25=6h' },
    intraday: { min: 0.04, step: 0.04, default: 1, label: 'Pas (j) — 0.04=1h, 0.17=4h, 1=1j' },
    swing: { min: 1, step: 1, default: 30, label: 'Pas (j)' },
  };
  const stepConfig = STEP_CONFIG[horizonMode];

  // State: Sentiment historique
  const [sentimentRange, setSentimentRange] = useState<SentimentRangeResponse | null>(null);
  const [sentimentLoadResult, setSentimentLoadResult] = useState<SentimentLoadResponse | null>(null);
  const [loadingSentiment, setLoadingSentiment] = useState(false);

  // Anti-race: compteur de requêtes pour ignorer les réponses stales
  const requestIdRef = useRef(0);

  // Horizons prédéfinis par mode
  // scalping: 5min, 15min, 1h ; intraday: 1h, 4h, 1j ; swing: 7j, 30j, 90j
  const HORIZON_PRESETS: Record<string, { horizons: number[]; labels: string[] }> = {
    scalping: { horizons: [5 / 1440, 15 / 1440, 60 / 1440], labels: ['5min', '15min', '1h'] },
    intraday: { horizons: [60 / 1440, 240 / 1440, 1], labels: ['1h', '4h', '1j'] },
    swing: { horizons: [7, 30, 90], labels: ['7j', '30j', '90j'] },
  };

  const currentPreset = HORIZON_PRESETS[horizonMode];

  // Handler de changement de timeframe : nettoie les résultats stales
  const handleTimeframeChange = useCallback((newTf: string) => {
    setLoadTimeframe(newTf);
    // Clear les résultats de l'ancien TF pour éviter la confusion
    setVerifyResult(null);
    setWfResult(null);
    setLoadResult(null);
    setInterestingDates(null);
    setError(null);
    // L'intégrité et le range seront rechargés par l'effet ci-dessous
  }, []);

  // Charger range + intégrité quand loadTimeframe change, avec anti-race
  useEffect(() => {
    const currentRequestId = ++requestIdRef.current;

    const fetchData = async () => {
      setLoadingIntegrity(true);

      try {
        const [rangeResult, integrityResult] = await Promise.all([
          getHistoryRange({ timeframe: loadTimeframe }).catch(() => null),
          getHistoryIntegrity({ timeframe: loadTimeframe }).catch(() => null),
        ]);

        // Ignorer si le timeframe a changé entre-temps
        if (requestIdRef.current !== currentRequestId) return;

        setRange(rangeResult);
        setIntegrity(integrityResult);
      } finally {
        // Ne pas toucher au loading si un nouveau fetch est en cours
        if (requestIdRef.current === currentRequestId) {
          setLoadingIntegrity(false);
        }
      }
    };

    fetchData();
  }, [loadTimeframe]);

  // Charger le sentiment range une seule fois au mount (indépendant du TF)
  useEffect(() => {
    getSentimentRange()
      .then((r) => setSentimentRange(r))
      .catch(() => { /* ignore */ });
  }, []);

  // Helpers pour refresh après une action (utilisent le TF courant)
  const refreshRangeAndIntegrity = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setLoadingIntegrity(true);
    try {
      const [rangeResult, integrityResult] = await Promise.all([
        getHistoryRange({ timeframe: loadTimeframe }).catch(() => null),
        getHistoryIntegrity({ timeframe: loadTimeframe }).catch(() => null),
      ]);
      if (requestIdRef.current !== currentRequestId) return;
      setRange(rangeResult);
      setIntegrity(integrityResult);
    } finally {
      if (requestIdRef.current === currentRequestId) {
        setLoadingIntegrity(false);
      }
    }
  }, [loadTimeframe]);


  // Handlers
  const handleLoadHistory = async () => {
    setLoadingHistory(true);
    setError(null);
    setLoadResult(null);
    try {
      const result = await loadHistory({
        symbol: 'BTC/USD',
        timeframe: loadTimeframe,
        start_date: '2017-08-17',
      });
      setLoadResult(result);
      await refreshRangeAndIntegrity();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur chargement');
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleLoadSentiment = async () => {
    setLoadingSentiment(true);
    setError(null);
    setSentimentLoadResult(null);
    try {
      const result = await loadSentimentHistory({});
      setSentimentLoadResult(result);
      // Rafraîchir le range sentiment
      getSentimentRange()
        .then((r) => setSentimentRange(r))
        .catch(() => { /* ignore */ });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur chargement sentiment');
    } finally {
      setLoadingSentiment(false);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    setError(null);
    setVerifyResult(null);
    try {
      const result = await verifyAtDate({
        target_date: targetDate,
        timeframe: loadTimeframe,
        horizons: currentPreset.horizons,
      });
      setVerifyResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur vérification');
    } finally {
      setVerifying(false);
    }
  };

  const handleFindInterestingDates = async () => {
    setLoadingInteresting(true);
    setError(null);
    setInterestingDates(null);
    try {
      // Adapter le step_days au timeframe pour un scan pertinent
      const stepDaysMap: Record<string, number> = {
        '1m': 0.25, '5m': 0.5, '15m': 1, '30m': 1,
        '1h': 2, '4h': 5, '1d': 7, '1w': 30,
      };
      const stepDays = stepDaysMap[loadTimeframe] ?? 3;

      const result = await getInterestingDates({
        timeframe: loadTimeframe,
        min_strength: 0.7,
        max_results: 20,
        step_days: stepDays,
      });
      setInterestingDates(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur scan dates');
    } finally {
      setLoadingInteresting(false);
    }
  };

  const handleWalkForward = async () => {
    setWalkingForward(true);
    setError(null);
    setWfResult(null);
    try {
      const result = await runWalkForward({
        start_date: wfStartDate,
        end_date: wfEndDate,
        step_days: wfStepDays,
        timeframe: loadTimeframe,
        horizons: currentPreset.horizons,
        compare_mode: wfCompareMode,
      });
      setWfResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur walk-forward');
    } finally {
      setWalkingForward(false);
    }
  };

  return (
    <GlowingCard accentColor={ACCENT.purple.start} accentColorEnd={ACCENT.purple.end} delay={0.2}>
      <CardContent sx={{ p: 2 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <HistoryIcon sx={{ fontSize: 20, color: '#B388FF' }} />
            <Typography variant="subtitle1" fontWeight={700} sx={{ fontSize: '0.95rem' }}>
              Vérification Historique
            </Typography>
          </Box>
          {range?.has_data && (
            <Chip
              label={`${range.total_candles.toLocaleString()} candles`}
              size="small"
              color="secondary"
              variant="outlined"
              sx={{ fontSize: '0.65rem' }}
            />
          )}
        </Box>

        {/* Info message */}
        <Alert severity="info" sx={{ mb: 1.5, fontSize: '0.72rem', py: 0.5 }}>
          Testez les prédictions du modèle sur l'historique réel du BTC.
          {sentimentRange?.has_data
            ? `✅ Sentiment historique disponible (${sentimentRange.total_points} points Fear & Greed) — mode complet technique + sentiment.`
            : '⚠️ Chargez le sentiment historique (Fear & Greed) pour un backtest complet (technique + sentiment).'
          }
        </Alert>

        {error && (
          <Alert severity="error" sx={{ mb: 1.5, fontSize: '0.75rem' }}>
            {error}
          </Alert>
        )}

        {/* ====== SECTION 1: Charger l'historique ====== */}
        <Typography variant="caption" fontWeight={700} sx={{ textTransform: 'uppercase', color: '#B388FF', display: 'block', mb: 0.5 }}>
          1. Charger l'historique BTC
        </Typography>

        {/* Guide Section 1 */}
        <Box sx={{ mb: 1, p: 1, borderRadius: 1, bgcolor: 'rgba(179,136,255,0.04)', border: '1px solid rgba(179,136,255,0.1)' }}>
          <Stack direction="row" spacing={0.5} alignItems="flex-start">
            <HelpIcon sx={{ fontSize: 14, color: '#B388FF', mt: 0.2 }} />
            <Typography variant="caption" sx={{ fontSize: '0.63rem', color: 'text.secondary', lineHeight: 1.5 }}>
              <b style={{ color: '#B388FF' }}>Comment ça marche :</b> Choisissez un <b>timeframe</b> et un <b>mode</b>, puis chargez les données depuis Binance.
              <br />• <b>Scalping</b> (1m-15m) → vérifie sur 5min/15min/1h • <b>Intraday</b> (1h-4h) → vérifie sur 1h/4h/1j • <b>Swing</b> (1d) → vérifie sur 7j/30j/90j
              <br />• Le bouton <b>"5min / 15min / 1h"</b> indique les horizons de vérification actuels.
              {!sentimentRange?.has_data && <><br />• 💡 <b>Conseil :</b> Chargez aussi le Fear & Greed pour un mode complet technique + sentiment.</>}
            </Typography>
          </Stack>
        </Box>

        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <FormControl size="small" sx={{ minWidth: 80 }}>
            <InputLabel sx={{ fontSize: '0.75rem' }}>TF</InputLabel>
            <Select
              value={loadTimeframe}
              onChange={(e) => handleTimeframeChange(e.target.value)}
              label="TF"
              sx={{ fontSize: '0.8rem', height: 36 }}
            >
              <MenuItem value="1m">1 minute</MenuItem>
              <MenuItem value="5m">5 minutes</MenuItem>
              <MenuItem value="15m">15 minutes</MenuItem>
              <MenuItem value="1h">1 heure</MenuItem>
              <MenuItem value="4h">4 heures</MenuItem>
              <MenuItem value="1d">1 jour</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel sx={{ fontSize: '0.75rem' }}>Mode</InputLabel>
            <Select
              value={horizonMode}
              onChange={(e) => {
                const newMode = e.target.value as 'scalping' | 'intraday' | 'swing';
                setHorizonMode(newMode);
                setVerifyResult(null);
                setWfResult(null);
                // Adapter le pas du walk-forward au mode
                const defaults: Record<string, number> = { scalping: 0.25, intraday: 1, swing: 30 };
                setWfStepDays(defaults[newMode] ?? 30);
              }}
              label="Mode"
              sx={{ fontSize: '0.8rem', height: 36 }}
            >
              <MenuItem value="scalping">⚡ Scalping</MenuItem>
              <MenuItem value="intraday">📊 Intraday</MenuItem>
              <MenuItem value="swing">📈 Swing</MenuItem>
            </Select>
          </FormControl>

          <Chip
            label={currentPreset.labels.join(' / ')}
            size="small"
            variant="outlined"
            sx={{ fontSize: '0.65rem', borderColor: '#B388FF', color: '#B388FF' }}
          />

          <Button
            variant="contained"
            size="small"
            startIcon={loadingHistory ? <CircularProgress size={14} /> : <DownloadIcon />}
            onClick={handleLoadHistory}
            disabled={loadingHistory}
            sx={{
              background: 'linear-gradient(135deg, #7C4DFF 0%, #6200EA 100%)',
              '&:hover': { background: 'linear-gradient(135deg, #B388FF 0%, #7C4DFF 100%)' },
              fontWeight: 700, fontSize: '0.72rem', px: 1.5,
            }}
          >
            {loadingHistory ? 'Chargement...' : range?.has_data ? 'Mettre à jour' : 'Charger depuis 2017'}
          </Button>

          {range?.has_data && (
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
              {range.min_date?.slice(0, 10)} → {range.max_date?.slice(0, 10)}
            </Typography>
          )}
        </Stack>

        {loadingHistory && <LinearProgress sx={{ mb: 1, borderRadius: 1 }} color="secondary" />}

        {loadResult && (
          <Alert severity="success" sx={{ mb: 1.5, fontSize: '0.72rem', py: 0.3 }}>
            ✅ {loadResult.fetched.toLocaleString()} candles chargées en {loadResult.duration_seconds.toFixed(1)}s
          </Alert>
        )}

        {/* Charger le sentiment historique */}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={loadingSentiment ? <CircularProgress size={14} /> : <DownloadIcon />}
            onClick={handleLoadSentiment}
            disabled={loadingSentiment}
            color="secondary"
            sx={{ fontWeight: 700, fontSize: '0.72rem', px: 1.5 }}
          >
            {loadingSentiment ? 'Chargement...' : sentimentRange?.has_data ? 'Mettre à jour Fear & Greed' : 'Charger Fear & Greed (sentiment)'}
          </Button>

          {sentimentRange?.has_data && (
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
              {sentimentRange.total_points.toLocaleString()} points • {sentimentRange.min_date?.slice(0, 10)} → {sentimentRange.max_date?.slice(0, 10)}
            </Typography>
          )}
        </Stack>

        {loadingSentiment && <LinearProgress sx={{ mb: 1, borderRadius: 1 }} color="secondary" />}

        {sentimentLoadResult && (
          <Alert severity="success" sx={{ mb: 1.5, fontSize: '0.72rem', py: 0.3 }}>
            ✅ Sentiment: {sentimentLoadResult.fetched.toLocaleString()} points récupérés,
            {sentimentLoadResult.inserted} insérés, {sentimentLoadResult.updated} mis à jour
            ({sentimentLoadResult.duration_seconds.toFixed(1)}s)
          </Alert>
        )}

        {/* Integrity panel */}
        {loadingIntegrity && <LinearProgress sx={{ mb: 1, borderRadius: 1 }} color="secondary" />}
        {integrity && integrity.total_candles > 0 && (
          <Box sx={{
            mb: 1.5, p: 1.2, borderRadius: 1,
            bgcolor: integrity.quality_grade === 'EXCELLENT' ? 'rgba(0, 230, 118, 0.06)'
              : integrity.quality_grade === 'GOOD' ? 'rgba(0, 230, 118, 0.04)'
              : integrity.quality_grade === 'WARNING' ? 'rgba(255, 183, 77, 0.06)'
              : 'rgba(255, 23, 68, 0.06)',
            border: `1px solid ${
              integrity.quality_grade === 'EXCELLENT' ? 'rgba(0, 230, 118, 0.2)'
              : integrity.quality_grade === 'GOOD' ? 'rgba(0, 230, 118, 0.12)'
              : integrity.quality_grade === 'WARNING' ? 'rgba(255, 183, 77, 0.2)'
              : 'rgba(255, 23, 68, 0.2)'
            }`,
          }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
              <IntegrityIcon sx={{
                fontSize: 16,
                color: integrity.quality_grade === 'EXCELLENT' || integrity.quality_grade === 'GOOD'
                  ? '#00E676' : integrity.quality_grade === 'WARNING' ? '#FFB74D' : '#FF1744',
              }} />
              <Typography variant="caption" fontWeight={700} sx={{ fontSize: '0.72rem' }}>
                Intégrité des données
              </Typography>
              <Chip
                label={integrity.quality_grade}
                size="small"
                sx={{
                  fontWeight: 700, fontSize: '0.6rem', height: 20,
                  bgcolor: integrity.quality_grade === 'EXCELLENT' ? 'rgba(0, 230, 118, 0.2)'
                    : integrity.quality_grade === 'GOOD' ? 'rgba(0, 230, 118, 0.12)'
                    : integrity.quality_grade === 'WARNING' ? 'rgba(255, 183, 77, 0.2)'
                    : 'rgba(255, 23, 68, 0.2)',
                  color: integrity.quality_grade === 'EXCELLENT' || integrity.quality_grade === 'GOOD'
                    ? '#00E676' : integrity.quality_grade === 'WARNING' ? '#FFB74D' : '#FF1744',
                }}
              />
              <Typography variant="caption" sx={{
                fontFamily: '"JetBrains Mono", monospace', fontSize: '0.72rem', fontWeight: 700,
                color: integrity.completeness_pct >= 99 ? '#00E676'
                  : integrity.completeness_pct >= 95 ? '#FFB74D' : '#FF1744',
              }}>
                {integrity.completeness_pct.toFixed(1)}%
              </Typography>
            </Stack>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem', display: 'block' }}>
              {integrity.total_candles.toLocaleString()} / {integrity.expected_candles.toLocaleString()} candles attendues
              {integrity.missing_candles > 0 && ` • ${integrity.missing_candles} manquantes`}
              {integrity.min_date && ` • ${integrity.min_date.slice(0, 10)} → ${integrity.max_date?.slice(0, 10)}`}
            </Typography>
            {integrity.gaps.length > 0 && (
              <Box sx={{ mt: 0.5 }}>
                <Typography variant="caption" sx={{ color: '#FFB74D', fontSize: '0.6rem', fontWeight: 600 }}>
                  ⚠️ {integrity.gaps.length} gap{integrity.gaps.length > 1 ? 's' : ''} détecté{integrity.gaps.length > 1 ? 's' : ''} :
                </Typography>
                <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.3 }}>
                  {integrity.gaps.slice(0, 5).map((gap: HistoryIntegrityGap, idx: number) => (
                    <Chip
                      key={idx}
                      label={`${gap.start_date.slice(0, 10)} → ${gap.end_date.slice(0, 10)} (${gap.missing_days}j)`}
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: '0.55rem', height: 18, borderColor: '#FFB74D', color: '#FFB74D' }}
                    />
                  ))}
                  {integrity.gaps.length > 5 && (
                    <Chip
                      label={`+${integrity.gaps.length - 5} autres`}
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: '0.55rem', height: 18 }}
                    />
                  )}
                </Stack>
              </Box>
            )}
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.6rem', display: 'block', mt: 0.3 }}>
              {integrity.detail}
            </Typography>
          </Box>
        )}

        <Divider sx={{ my: 1.5 }} />

        {/* ====== SECTION 2: Vérification ponctuelle ====== */}
        <Typography variant="caption" fontWeight={700} sx={{ textTransform: 'uppercase', color: '#B388FF', display: 'block', mb: 0.5 }}>
          2. Vérifier à une date
        </Typography>

        {/* Guide Section 2 */}
        <Box sx={{ mb: 1, p: 1, borderRadius: 1, bgcolor: 'rgba(0,188,212,0.04)', border: '1px solid rgba(0,188,212,0.1)' }}>
          <Stack direction="row" spacing={0.5} alignItems="flex-start">
            <HelpIcon sx={{ fontSize: 14, color: '#4DD0E1', mt: 0.2 }} />
            <Typography variant="caption" sx={{ fontSize: '0.63rem', color: 'text.secondary', lineHeight: 1.5 }}>
              <b style={{ color: '#4DD0E1' }}>Vérification ponctuelle :</b> Le modèle se "téléporte" à la date choisie, calcule sa prédiction <b>sans tricher</b> (uniquement les données passées), puis compare avec ce qui s'est vraiment passé.
              <br />• 🔍 <b>Dates intéressantes</b> : scanne l'historique pour trouver des dates avec des signaux forts (RSI extrêmes, MACD croisé…). Cliquez sur un chip pour tester.
              <br />• 💡 <b>Pour des scores de qualité élevés</b>, ciblez les dates à signaux forts plutôt que des dates aléatoires.
            </Typography>
          </Stack>
        </Box>

        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <TextField
            type="date"
            size="small"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            sx={{
              width: 160,
              '& input': { fontFamily: '"JetBrains Mono", monospace', fontSize: '0.8rem' },
            }}
          />
          <Button
            variant="contained"
            size="small"
            startIcon={verifying ? <CircularProgress size={14} /> : <SearchIcon />}
            onClick={handleVerify}
            disabled={verifying || !range?.has_data}
            sx={{
              background: 'linear-gradient(135deg, #00BCD4 0%, #006064 100%)',
              '&:hover': { background: 'linear-gradient(135deg, #4DD0E1 0%, #00BCD4 100%)' },
              fontWeight: 700, fontSize: '0.72rem', px: 1.5,
            }}
          >
            {verifying ? 'Analyse...' : 'Vérifier'}
          </Button>
          <Tooltip title="Scanne l'historique pour trouver les dates avec des signaux techniques forts (RSI extrêmes, MACD croisé, Bollinger percé…)">
            <Button
              variant="outlined"
              size="small"
              startIcon={loadingInteresting ? <CircularProgress size={14} /> : <TimelineIcon />}
              onClick={handleFindInterestingDates}
              disabled={loadingInteresting || !range?.has_data || (range?.total_candles ?? 0) < 200}
              sx={{
                borderColor: '#FFD600',
                color: '#FFD600',
                '&:hover': { borderColor: '#FFFF00', color: '#FFFF00', bgcolor: 'rgba(255,214,0,0.08)' },
                fontWeight: 700, fontSize: '0.68rem', px: 1.2,
              }}
            >
              {loadingInteresting ? 'Scan…' : '🔍 Dates intéressantes'}
            </Button>
          </Tooltip>
        </Stack>

        {/* Interesting Dates Chips */}
        {interestingDates && interestingDates.dates.length > 0 && (
          <Box sx={{ mb: 1.5 }}>
            <Typography variant="caption" sx={{ color: '#FFD600', fontSize: '0.65rem', display: 'block', mb: 0.5 }}>
              ⚡ {interestingDates.total_found} dates avec signaux forts trouvées ({interestingDates.duration_seconds}s) — cliquez pour vérifier :
            </Typography>
            <Box sx={{
              display: 'flex', flexWrap: 'wrap', gap: 0.5,
              maxHeight: 120, overflowY: 'auto',
              p: 0.5, borderRadius: 1,
              bgcolor: 'rgba(255,214,0,0.04)', border: '1px solid rgba(255,214,0,0.15)',
            }}>
              {interestingDates.dates.map((item, i) => (
                <Tooltip
                  key={i}
                  title={
                    <Box sx={{ fontSize: '0.7rem' }}>
                      <b>${item.price.toLocaleString()}</b> — Score: {item.interest_score}/100<br />
                      {item.signals.map((s, j) => (
                        <Box key={j}>• {s.message}</Box>
                      ))}
                    </Box>
                  }
                  arrow
                >
                  <Chip
                    label={
                      <Stack direction="row" spacing={0.3} alignItems="center">
                        {item.dominant_direction === 'bullish' && <TrendUpIcon sx={{ fontSize: 12, color: '#00E676' }} />}
                        {item.dominant_direction === 'bearish' && <TrendDownIcon sx={{ fontSize: 12, color: '#FF1744' }} />}
                        {item.dominant_direction === 'mixed' && <CompareIcon sx={{ fontSize: 12, color: '#FFB74D' }} />}
                        <span>{item.date}</span>
                        <Chip
                          label={item.interest_score.toFixed(0)}
                          size="small"
                          sx={{
                            height: 16, fontSize: '0.55rem', fontWeight: 700, ml: 0.3,
                            bgcolor: item.interest_score >= 80 ? '#FF6D00' : item.interest_score >= 60 ? '#FFD600' : '#90A4AE',
                            color: '#000',
                          }}
                        />
                      </Stack>
                    }
                    size="small"
                    onClick={() => setTargetDate(item.date)}
                    sx={{
                      fontSize: '0.65rem', cursor: 'pointer',
                      border: targetDate === item.date ? '2px solid #FFD600' : '1px solid rgba(255,255,255,0.12)',
                      '&:hover': { bgcolor: 'rgba(255,214,0,0.12)' },
                    }}
                  />
                </Tooltip>
              ))}
            </Box>
          </Box>
        )}

        {interestingDates && interestingDates.dates.length === 0 && (
          <Alert severity="info" sx={{ mb: 1, fontSize: '0.7rem' }}>
            Aucune date avec signaux forts (strength ≥ {interestingDates.min_strength}) trouvée sur {interestingDates.total_scanned} points scannés.
            {(range?.total_candles ?? 0) < 200 && ' Il faut au moins 200 candles pour des indicateurs fiables.'}
          </Alert>
        )}

        {verifying && <LinearProgress sx={{ mb: 1, borderRadius: 1 }} />}

        {/* Verification Result */}
        {verifyResult && verifyResult.price_at_date > 0 && (
          <Box sx={{ mb: 1.5, p: 1.5, borderRadius: 1, bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
            {/* Prediction */}
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.7rem' }}>
                Le {verifyResult.target_date.slice(0, 10)} • BTC = ${verifyResult.price_at_date.toLocaleString()}
              </Typography>
              <ActionChip action={verifyResult.predicted_action} />
              <Chip
                label={`Score ${verifyResult.predicted_score >= 0 ? '+' : ''}${verifyResult.predicted_score}`}
                size="small"
                variant="outlined"
                sx={{
                  fontSize: '0.65rem',
                  borderColor: pnlColor(verifyResult.predicted_score),
                  color: pnlColor(verifyResult.predicted_score),
                }}
              />
              <Chip
                label={`${verifyResult.dominant_scenario} ${(verifyResult.dominant_probability * 100).toFixed(0)}%`}
                size="small"
                variant="outlined"
                sx={{ fontSize: '0.6rem' }}
              />
            </Stack>

            <Typography variant="body2" sx={{ fontSize: '0.72rem', mb: 1, color: 'text.secondary' }}>
              {verifyResult.predicted_summary}
            </Typography>

            {/* Outcomes (comparaison prédiction vs réalité) */}
            <Box
              onClick={() => setShowOutcomes(!showOutcomes)}
              sx={{ display: 'flex', alignItems: 'center', cursor: 'pointer', mb: 0.5 }}
            >
              <Typography variant="caption" fontWeight={700} sx={{ flex: 1, color: '#FFB74D' }}>
                Comparaison avec la réalité
              </Typography>
              <IconButton size="small">
                {showOutcomes ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
              </IconButton>
            </Box>

            <Collapse in={showOutcomes}>
              {verifyResult.outcomes.map((o: HorizonOutcome, idx: number) => (
                <Box
                  key={idx}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: 1, p: 0.8, mb: 0.5,
                    borderRadius: 1,
                    bgcolor: o.correct ? 'rgba(0, 230, 118, 0.05)' : 'rgba(255, 23, 68, 0.05)',
                    border: `1px solid ${o.correct ? 'rgba(0, 230, 118, 0.15)' : 'rgba(255, 23, 68, 0.15)'}`,
                  }}
                >
                  {o.correct ? (
                    <CheckIcon sx={{ fontSize: 18, color: '#00E676' }} />
                  ) : (
                    <CancelIcon sx={{ fontSize: 18, color: '#FF1744' }} />
                  )}
                  <Box sx={{ flex: 1 }}>
                    <Stack direction="row" alignItems="center" spacing={0.5}>
                      <Typography variant="caption" fontWeight={700} sx={{ fontSize: '0.72rem' }}>
                        +{formatHorizonLabel(o.horizon_days)}
                      </Typography>
                      <DirectionIcon direction={o.actual_direction} />
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: '"JetBrains Mono", monospace',
                          fontWeight: 700,
                          color: pnlColor(o.actual_change_pct),
                          fontSize: '0.78rem',
                        }}
                      >
                        {o.actual_change_pct >= 0 ? '+' : ''}{o.actual_change_pct.toFixed(1)}%
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                        (${o.end_price.toLocaleString()})
                      </Typography>
                      <Tooltip title={`Score de qualité : ${o.quality_score}/100 — ${o.quality_score >= 75 ? 'Excellent' : o.quality_score >= 55 ? 'Bon' : o.quality_score >= 35 ? 'Moyen' : 'Faible'}`}>
                        <Chip
                          label={`Q ${o.quality_score.toFixed(0)}`}
                          size="small"
                          variant="outlined"
                          sx={{
                            fontSize: '0.55rem', height: 18,
                            borderColor: o.quality_score >= 60 ? '#00E676' : o.quality_score >= 40 ? '#FFB74D' : '#FF1744',
                            color: o.quality_score >= 60 ? '#00E676' : o.quality_score >= 40 ? '#FFB74D' : '#FF1744',
                          }}
                        />
                      </Tooltip>
                      {o.directional_match && (
                        <Tooltip title="Direction correcte : le signe du score prédit correspond à la direction réelle du marché">
                          <Chip label="↕ DIR" size="small" color="success" variant="outlined" sx={{ fontSize: '0.5rem', height: 18 }} />
                        </Tooltip>
                      )}
                    </Stack>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.6rem', display: 'block' }}>
                      {o.detail}
                    </Typography>
                  </Box>
                </Box>
              ))}

              {/* Légende des badges */}
              <Box sx={{ mt: 1, p: 0.8, borderRadius: 1, bgcolor: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.08)' }}>
                <Typography variant="caption" sx={{ fontSize: '0.58rem', color: 'text.secondary', lineHeight: 1.6 }}>
                  📖 <b>Légende :</b>&nbsp;
                  <span style={{ color: '#00E676' }}>✅ CORRECT</span> / <span style={{ color: '#FF1744' }}>❌ INCORRECT</span> = la prédiction correspond-elle à la réalité ?&nbsp;|&nbsp;
                  <b>Q</b> = Qualité 0-100 (<span style={{ color: '#00E676' }}>≥60 bon</span>, <span style={{ color: '#FFB74D' }}>≥40 moyen</span>, <span style={{ color: '#FF1744' }}>&lt;40 faible</span>)&nbsp;|&nbsp;
                  <b>↕ DIR</b> = le signe du score (+/-) correspond à la direction réelle du marché
                </Typography>
              </Box>
            </Collapse>
          </Box>
        )}

        {verifyResult && verifyResult.price_at_date === 0 && (
          <Alert severity="warning" sx={{ mb: 1.5, fontSize: '0.72rem' }} icon={<InfoIcon />}>
            <b>Aucune donnée disponible à cette date</b> ({targetDate}).
            {range?.has_data
              ? <> Vos données couvrent <b>{range.min_date?.slice(0, 10)} → {range.max_date?.slice(0, 10)}</b> en timeframe <b>{loadTimeframe}</b>. Choisissez une date dans cette plage, ou chargez un autre timeframe.</>
              : <> Chargez d'abord l'historique avec le bouton de la section 1.</>}
          </Alert>
        )}

        <Divider sx={{ my: 1.5 }} />

        {/* ====== SECTION 3: Walk-Forward ====== */}
        <Typography variant="caption" fontWeight={700} sx={{ textTransform: 'uppercase', color: '#B388FF', display: 'block', mb: 0.5 }}>
          3. Analyse Walk-Forward (précision globale)
        </Typography>

        {/* Guide Section 3 */}
        <Box sx={{ mb: 1, p: 1, borderRadius: 1, bgcolor: 'rgba(255,109,0,0.04)', border: '1px solid rgba(255,109,0,0.1)' }}>
          <Stack direction="row" spacing={0.5} alignItems="flex-start">
            <HelpIcon sx={{ fontSize: 14, color: '#FF9100', mt: 0.2 }} />
            <Typography variant="caption" sx={{ fontSize: '0.63rem', color: 'text.secondary', lineHeight: 1.5 }}>
              <b style={{ color: '#FF9100' }}>Walk-Forward :</b> Teste automatiquement le modèle sur <b>des dizaines de dates</b> entre Début et Fin, espacées du Pas choisi. Calcule la <b>précision globale</b>.
              <br />• <b>Pas</b> : intervalle entre chaque test ({horizonMode === 'scalping' ? '0.04 = 1h, 0.25 = 6h' : horizonMode === 'intraday' ? '0.17 = 4h, 1 = 1j' : '7 = 1 semaine, 30 = 1 mois'})
              <br />• ☑️ <b>Mode comparaison</b> : lance 2× l'analyse (technique seul vs technique + sentiment) pour mesurer l'apport du Fear & Greed.
              <br />• ⏱️ <b>Durée</b> : ~{horizonMode === 'scalping' ? '30-120s' : horizonMode === 'intraday' ? '1-5min' : '2-10min'} selon la plage et le pas.
            </Typography>
          </Stack>
        </Box>

        <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center" sx={{ mb: 1 }}>
          <TextField
            type="date"
            size="small"
            label="Début"
            value={wfStartDate}
            onChange={(e) => setWfStartDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
            sx={{ width: 145, '& input': { fontFamily: '"JetBrains Mono", monospace', fontSize: '0.75rem' } }}
          />
          <TextField
            type="date"
            size="small"
            label="Fin"
            value={wfEndDate}
            onChange={(e) => setWfEndDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
            sx={{ width: 145, '& input': { fontFamily: '"JetBrains Mono", monospace', fontSize: '0.75rem' } }}
          />
          <Tooltip title={stepConfig.label}>
            <TextField
              type="number"
              size="small"
              label="Pas (j)"
              value={wfStepDays}
              onChange={(e) => setWfStepDays(Math.max(stepConfig.min, Math.min(365, Number(e.target.value))))}
              inputProps={{ min: stepConfig.min, max: 365, step: stepConfig.step }}
              sx={{ width: 80, '& input': { fontFamily: '"JetBrains Mono", monospace', fontSize: '0.8rem' } }}
            />
          </Tooltip>
          <Button
            variant="contained"
            size="small"
            startIcon={walkingForward ? <CircularProgress size={14} /> : <TimelineIcon />}
            onClick={handleWalkForward}
            disabled={walkingForward || !range?.has_data}
            sx={{
              background: 'linear-gradient(135deg, #FF6D00 0%, #BF360C 100%)',
              '&:hover': { background: 'linear-gradient(135deg, #FF9100 0%, #FF6D00 100%)' },
              fontWeight: 700, fontSize: '0.72rem', px: 1.5,
            }}
          >
            {walkingForward ? 'Analyse...' : 'Lancer'}
          </Button>
        </Stack>

        {/* Compare mode toggle */}
        <Tooltip title="Compare les résultats technique seul vs technique + sentiment (Fear & Greed). Double le temps d'analyse.">
          <FormControlLabel
            control={
              <Checkbox
                checked={wfCompareMode}
                onChange={(e) => setWfCompareMode(e.target.checked)}
                size="small"
                sx={{ '& .MuiSvgIcon-root': { fontSize: 18 }, color: '#B388FF', '&.Mui-checked': { color: '#B388FF' } }}
              />
            }
            label={
              <Stack direction="row" alignItems="center" spacing={0.5}>
                <CompareIcon sx={{ fontSize: 14, color: '#B388FF' }} />
                <Typography variant="caption" sx={{ fontSize: '0.7rem' }}>
                  Mode comparaison (technique seul vs technique + sentiment)
                </Typography>
              </Stack>
            }
            sx={{ mb: 1, ml: 0 }}
          />
        </Tooltip>

        {walkingForward && (
          <>
            <LinearProgress sx={{ mb: 0.5, borderRadius: 1 }} color="warning" />
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
              Analyse en cours... cela peut prendre plusieurs minutes.
            </Typography>
          </>
        )}

        {/* Walk-Forward Results */}
        {wfResult && (
          <Box sx={{ mt: 1 }}>
            {/* Summary */}
            <Typography
              variant="body2"
              sx={{
                mb: 1, p: 1, borderRadius: 1,
                bgcolor: 'rgba(255, 109, 0, 0.08)',
                border: '1px solid rgba(255, 109, 0, 0.15)',
                fontSize: '0.75rem',
                fontFamily: '"JetBrains Mono", monospace',
              }}
            >
              {wfResult.summary}
            </Typography>

            {/* Accuracy bars */}
            <Stack direction="row" spacing={2} sx={{ mb: 1.5 }}>
              {wfResult.accuracy_by_horizon.map((acc: HorizonAccuracy) => (
                <AccuracyBar
                  key={acc.horizon_days}
                  accuracy={acc.accuracy_pct}
                  label={`Horizon ${formatHorizonLabel(acc.horizon_days)} (${acc.correct}/${acc.total_points})`}
                />
              ))}
            </Stack>

            {/* Quality Score global */}
            <Box sx={{ mb: 1.5, p: 1, borderRadius: 1, bgcolor: 'rgba(255, 109, 0, 0.06)', border: '1px solid rgba(255, 109, 0, 0.12)' }}>
              <Stack direction="row" spacing={2} flexWrap="wrap" alignItems="center">
                <Tooltip title="Score qualité global moyen sur tous les horizons (0-100)">
                  <Chip
                    label={`Qualité globale: ${wfResult.overall_quality_score.toFixed(0)}/100`}
                    size="small"
                    sx={{
                      fontWeight: 700, fontSize: '0.72rem',
                      bgcolor: wfResult.overall_quality_score >= 55 ? 'rgba(0, 230, 118, 0.15)' : wfResult.overall_quality_score >= 40 ? 'rgba(255, 183, 77, 0.15)' : 'rgba(255, 23, 68, 0.15)',
                      color: wfResult.overall_quality_score >= 55 ? '#00E676' : wfResult.overall_quality_score >= 40 ? '#FFB74D' : '#FF1744',
                    }}
                  />
                </Tooltip>
                {wfResult.accuracy_by_horizon.map((acc: HorizonAccuracy) => (
                  <Stack key={acc.horizon_days} spacing={0.2}>
                    <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary' }}>
                      {formatHorizonLabel(acc.horizon_days)}
                    </Typography>
                    <Stack direction="row" spacing={0.5}>
                      <Tooltip title={`Accuracy directionnelle: ${acc.directional_accuracy_pct.toFixed(0)}%`}>
                        <Chip label={`Dir ${acc.directional_accuracy_pct.toFixed(0)}%`} size="small" variant="outlined" sx={{ fontSize: '0.55rem', height: 20 }} />
                      </Tooltip>
                      <Tooltip title={`Qualité moyenne: ${acc.avg_quality_score.toFixed(0)}/100`}>
                        <Chip label={`Q ${acc.avg_quality_score.toFixed(0)}`} size="small" variant="outlined" sx={{ fontSize: '0.55rem', height: 20 }} />
                      </Tooltip>
                      {acc.high_confidence_count > 0 && (
                        <Tooltip title={`Signaux forts (|score|>25): ${acc.high_confidence_accuracy_pct.toFixed(0)}% correct sur ${acc.high_confidence_count} signaux`}>
                          <Chip label={`HC ${acc.high_confidence_accuracy_pct.toFixed(0)}%`} size="small" color="warning" variant="outlined" sx={{ fontSize: '0.55rem', height: 20 }} />
                        </Tooltip>
                      )}
                      <Tooltip title={`${acc.profitable_direction_pct.toFixed(0)}% des signaux auraient été profitables`}>
                        <Chip label={`💰 ${acc.profitable_direction_pct.toFixed(0)}%`} size="small" variant="outlined" sx={{ fontSize: '0.55rem', height: 20 }} />
                      </Tooltip>
                    </Stack>
                  </Stack>
                ))}
              </Stack>

              {/* Légende des métriques walk-forward */}
              <Box sx={{ mt: 1, p: 0.8, borderRadius: 1, bgcolor: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.08)' }}>
                <Typography variant="caption" sx={{ fontSize: '0.58rem', color: 'text.secondary', lineHeight: 1.7 }}>
                  📖 <b>Légende des métriques :</b>
                  <br />• <b>Accuracy</b> = % de prédictions correctes (barre verte) — <span style={{ color: '#00E676' }}>≥60% bon</span>, <span style={{ color: '#FFB74D' }}>≥40% moyen</span>, <span style={{ color: '#FF1744' }}>&lt;40% faible</span>
                  <br />• <b>Dir</b> = Précision directionnelle (le signe +/- du score correspond à la hausse/baisse réelle)
                  <br />• <b>Q</b> = Score qualité moyen 0-100 (tient compte de la force du signal et du mouvement réel)
                  <br />• <b>HC</b> = High Confidence — précision uniquement sur les signaux forts (|score| &gt; 25). <b>C'est la métrique la plus fiable !</b>
                  <br />• <b>💰</b> = % des signaux où suivre la recommandation aurait été profitable
                </Typography>
              </Box>
            </Box>

            {/* Comparison results (compare_mode) */}
            {wfResult.comparison && (
              <Box sx={{ mb: 1.5 }}>
                <Box
                  onClick={() => setShowComparison(!showComparison)}
                  sx={{ display: 'flex', alignItems: 'center', cursor: 'pointer', mb: 0.5 }}
                >
                  <CompareIcon sx={{ fontSize: 16, color: '#B388FF', mr: 0.5 }} />
                  <Typography variant="caption" fontWeight={700} sx={{ flex: 1, color: '#B388FF', fontSize: '0.72rem' }}>
                    Comparaison : Technique seul vs Technique + Sentiment
                  </Typography>
                  <IconButton size="small">
                    {showComparison ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
                  </IconButton>
                </Box>

                <Collapse in={showComparison}>
                  {/* Verdict */}
                  <Alert
                    severity={
                      wfResult.comparison.sentiment_delta_accuracy_pct > 2 ? 'success'
                      : wfResult.comparison.sentiment_delta_accuracy_pct < -2 ? 'warning'
                      : 'info'
                    }
                    sx={{ mb: 1, fontSize: '0.72rem', py: 0.3 }}
                  >
                    {wfResult.comparison.verdict}
                  </Alert>

                  {/* Side-by-side stats */}
                  <Stack direction="row" spacing={1.5} sx={{ mb: 1 }}>
                    {/* Technical only */}
                    <Box sx={{
                      flex: 1, p: 1, borderRadius: 1,
                      bgcolor: 'rgba(0, 188, 212, 0.06)',
                      border: '1px solid rgba(0, 188, 212, 0.15)',
                    }}>
                      <Typography variant="caption" fontWeight={700} sx={{ color: '#4DD0E1', fontSize: '0.68rem', display: 'block', mb: 0.5 }}>
                        📊 Technique seul
                      </Typography>
                      <Stack spacing={0.3}>
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem' }}>
                          Accuracy : <b style={{ color: wfResult.comparison.technical_only.overall_accuracy_pct >= 50 ? '#00E676' : '#FF1744' }}>
                            {wfResult.comparison.technical_only.overall_accuracy_pct.toFixed(1)}%
                          </b>
                        </Typography>
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem' }}>
                          Qualité : <b>{wfResult.comparison.technical_only.overall_quality_score.toFixed(0)}</b>/100
                        </Typography>
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem' }}>
                          Direction : <b>{wfResult.comparison.technical_only.directional_accuracy_pct.toFixed(1)}%</b>
                        </Typography>
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem' }}>
                          Profitable : <b>{wfResult.comparison.technical_only.profitable_direction_pct.toFixed(1)}%</b>
                        </Typography>
                      </Stack>
                    </Box>

                    {/* With sentiment */}
                    <Box sx={{
                      flex: 1, p: 1, borderRadius: 1,
                      bgcolor: 'rgba(179, 136, 255, 0.06)',
                      border: '1px solid rgba(179, 136, 255, 0.15)',
                    }}>
                      <Typography variant="caption" fontWeight={700} sx={{ color: '#B388FF', fontSize: '0.68rem', display: 'block', mb: 0.5 }}>
                        🧠 Technique + Sentiment
                      </Typography>
                      <Stack spacing={0.3}>
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem' }}>
                          Accuracy : <b style={{ color: wfResult.comparison.with_sentiment.overall_accuracy_pct >= 50 ? '#00E676' : '#FF1744' }}>
                            {wfResult.comparison.with_sentiment.overall_accuracy_pct.toFixed(1)}%
                          </b>
                        </Typography>
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem' }}>
                          Qualité : <b>{wfResult.comparison.with_sentiment.overall_quality_score.toFixed(0)}</b>/100
                        </Typography>
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem' }}>
                          Direction : <b>{wfResult.comparison.with_sentiment.directional_accuracy_pct.toFixed(1)}%</b>
                        </Typography>
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem' }}>
                          Profitable : <b>{wfResult.comparison.with_sentiment.profitable_direction_pct.toFixed(1)}%</b>
                        </Typography>
                      </Stack>
                    </Box>
                  </Stack>

                  {/* Delta chips */}
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <Tooltip title="Différence d'accuracy entre les deux modes">
                      <Chip
                        label={`Δ Accuracy : ${wfResult.comparison.sentiment_delta_accuracy_pct >= 0 ? '+' : ''}${wfResult.comparison.sentiment_delta_accuracy_pct.toFixed(1)}%`}
                        size="small"
                        sx={{
                          fontWeight: 700, fontSize: '0.65rem', height: 22,
                          bgcolor: wfResult.comparison.sentiment_delta_accuracy_pct > 0
                            ? 'rgba(0, 230, 118, 0.15)' : wfResult.comparison.sentiment_delta_accuracy_pct < 0
                            ? 'rgba(255, 23, 68, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                          color: wfResult.comparison.sentiment_delta_accuracy_pct > 0
                            ? '#00E676' : wfResult.comparison.sentiment_delta_accuracy_pct < 0
                            ? '#FF1744' : 'text.secondary',
                        }}
                      />
                    </Tooltip>
                    <Tooltip title="Différence de score qualité entre les deux modes">
                      <Chip
                        label={`Δ Qualité : ${wfResult.comparison.sentiment_delta_quality >= 0 ? '+' : ''}${wfResult.comparison.sentiment_delta_quality.toFixed(1)}`}
                        size="small"
                        sx={{
                          fontWeight: 700, fontSize: '0.65rem', height: 22,
                          bgcolor: wfResult.comparison.sentiment_delta_quality > 0
                            ? 'rgba(0, 230, 118, 0.15)' : wfResult.comparison.sentiment_delta_quality < 0
                            ? 'rgba(255, 23, 68, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                          color: wfResult.comparison.sentiment_delta_quality > 0
                            ? '#00E676' : wfResult.comparison.sentiment_delta_quality < 0
                            ? '#FF1744' : 'text.secondary',
                        }}
                      />
                    </Tooltip>
                  </Stack>
                </Collapse>
              </Box>
            )}

            {/* Signal distribution */}
            <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 1 }}>
              {wfResult.accuracy_by_horizon.map((acc: HorizonAccuracy) => (
                <Box key={acc.horizon_days}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.6rem', display: 'block' }}>
                    {formatHorizonLabel(acc.horizon_days)}:
                  </Typography>
                  <Stack direction="row" spacing={0.5}>
                    <Chip label={`${acc.buy_signals} achats`} size="small" color="success" variant="outlined" sx={{ fontSize: '0.55rem', height: 20 }} />
                    <Chip label={`${acc.sell_signals} ventes`} size="small" color="error" variant="outlined" sx={{ fontSize: '0.55rem', height: 20 }} />
                    <Chip label={`${acc.hold_signals} attentes`} size="small" variant="outlined" sx={{ fontSize: '0.55rem', height: 20 }} />
                  </Stack>
                </Box>
              ))}
            </Stack>

            {/* Meta */}
            <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
              <Chip label={`${wfResult.total_points} points`} size="small" variant="outlined" sx={{ fontSize: '0.6rem' }} />
              <Chip label={`${wfResult.duration_seconds.toFixed(1)}s`} size="small" variant="outlined" sx={{ fontSize: '0.6rem' }} />
            </Stack>

            {/* Detailed points (collapsible) */}
            {wfResult.points.length > 0 && (
              <>
                <Box
                  onClick={() => setShowWfDetails(!showWfDetails)}
                  sx={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}
                >
                  <Typography variant="caption" fontWeight={600} sx={{ flex: 1, fontSize: '0.7rem' }}>
                    Détail par date ({wfResult.points.length})
                  </Typography>
                  <IconButton size="small">
                    {showWfDetails ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
                  </IconButton>
                </Box>
                <Collapse in={showWfDetails}>
                  <Box sx={{ maxHeight: 300, overflow: 'auto', mt: 0.5 }}>
                    {wfResult.points.map((pt: VerificationResult, i: number) => (
                      <Box
                        key={i}
                        sx={{
                          display: 'flex', alignItems: 'center', gap: 1, p: 0.6, mb: 0.3,
                          borderRadius: 1, bgcolor: 'rgba(255,255,255,0.02)',
                          border: '1px solid rgba(255,255,255,0.04)', fontSize: '0.68rem',
                        }}
                      >
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.65rem', minWidth: 72 }}>
                          {pt.target_date.slice(0, 10)}
                        </Typography>
                        <ActionChip action={pt.predicted_action} />
                        <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.65rem', color: pnlColor(pt.predicted_score) }}>
                          {pt.predicted_score >= 0 ? '+' : ''}{pt.predicted_score}
                        </Typography>
                        <Box sx={{ flex: 1, display: 'flex', gap: 0.5 }}>
                          {pt.outcomes.slice(0, 3).map((o: HorizonOutcome, j: number) => (
                            <Chip
                              key={j}
                              icon={o.correct ? <CheckIcon sx={{ fontSize: '12px !important' }} /> : <CancelIcon sx={{ fontSize: '12px !important' }} />}
                              label={`${formatHorizonLabel(o.horizon_days)} ${o.actual_change_pct >= 0 ? '+' : ''}${o.actual_change_pct.toFixed(0)}%`}
                              size="small"
                              color={o.correct ? 'success' : 'error'}
                              variant="outlined"
                              sx={{ fontSize: '0.5rem', height: 18, '& .MuiChip-icon': { ml: 0.3 } }}
                            />
                          ))}
                        </Box>
                      </Box>
                    ))}
                  </Box>
                </Collapse>
              </>
            )}
          </Box>
        )}

        {/* Empty state */}
        {!range?.has_data && !loadingHistory && (
          <Box sx={{ textAlign: 'center', py: 2 }}>
            <HistoryIcon sx={{ fontSize: 40, color: 'rgba(179,136,255,0.3)', mb: 1 }} />
            <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem', mb: 0.5 }}>
              Chargez l'historique BTC pour commencer
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
              1. Choisissez un timeframe et un mode dans la section 1<br />
              2. Cliquez <b>"Charger depuis 2017"</b> pour télécharger les données<br />
              3. Vérifiez des dates ou lancez un walk-forward
            </Typography>
          </Box>
        )}
      </CardContent>
    </GlowingCard>
  );
};

export default VerificationPanel;

