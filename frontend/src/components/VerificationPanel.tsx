// =============================================================================
// VerificationPanel.tsx — Time-Travel Backtest UI
// Permet de : charger l'historique, vérifier à une date, lancer un walk-forward
// =============================================================================

import React, { useState, useCallback, useEffect } from 'react';
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
} from '../types';

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

const pnlColor = (val: number) => (val > 0 ? '#00E676' : val < 0 ? '#FF1744' : 'text.secondary');

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

  // State: UI
  const [showOutcomes, setShowOutcomes] = useState(true);
  const [showWfDetails, setShowWfDetails] = useState(false);
  const [showComparison, setShowComparison] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // State: Sentiment historique
  const [sentimentRange, setSentimentRange] = useState<SentimentRangeResponse | null>(null);
  const [sentimentLoadResult, setSentimentLoadResult] = useState<SentimentLoadResponse | null>(null);
  const [loadingSentiment, setLoadingSentiment] = useState(false);

  // Fetch range on mount
  const refreshRange = useCallback(async () => {
    try {
      const r = await getHistoryRange({ timeframe: loadTimeframe });
      setRange(r);
    } catch {
      /* ignore */
    }
  }, [loadTimeframe]);

  const refreshIntegrity = useCallback(async () => {
    setLoadingIntegrity(true);
    try {
      const r = await getHistoryIntegrity({ timeframe: loadTimeframe });
      setIntegrity(r);
    } catch {
      setIntegrity(null);
    } finally {
      setLoadingIntegrity(false);
    }
  }, [loadTimeframe]);

  const refreshSentimentRange = useCallback(async () => {
    try {
      const r = await getSentimentRange();
      setSentimentRange(r);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    refreshRange();
    refreshIntegrity();
    refreshSentimentRange();
  }, [refreshRange, refreshIntegrity, refreshSentimentRange]);

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
      await refreshRange();
      await refreshIntegrity();
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
      await refreshSentimentRange();
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
        horizons: [7, 30, 90],
      });
      setVerifyResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur vérification');
    } finally {
      setVerifying(false);
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
        horizons: [7, 30, 90],
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

        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <FormControl size="small" sx={{ minWidth: 80 }}>
            <InputLabel sx={{ fontSize: '0.75rem' }}>TF</InputLabel>
            <Select
              value={loadTimeframe}
              onChange={(e) => setLoadTimeframe(e.target.value)}
              label="TF"
              sx={{ fontSize: '0.8rem', height: 36 }}
            >
              <MenuItem value="1d">1 jour</MenuItem>
              <MenuItem value="4h">4 heures</MenuItem>
            </Select>
          </FormControl>

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
            {loadingHistory ? 'Chargement...' : 'Charger depuis 2017'}
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
            {loadingSentiment ? 'Chargement...' : 'Charger Fear & Greed (sentiment)'}
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
        </Stack>

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
                        +{o.horizon_days}j
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
                      <Tooltip title={`Score de qualité : ${o.quality_score}/100`}>
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
                        <Tooltip title="Direction correcte (signe du score = direction réelle)">
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
            </Collapse>
          </Box>
        )}

        {verifyResult && verifyResult.price_at_date === 0 && (
          <Alert severity="warning" sx={{ mb: 1.5, fontSize: '0.72rem' }}>
            Aucune donnée disponible à cette date. Chargez d'abord l'historique.
          </Alert>
        )}

        <Divider sx={{ my: 1.5 }} />

        {/* ====== SECTION 3: Walk-Forward ====== */}
        <Typography variant="caption" fontWeight={700} sx={{ textTransform: 'uppercase', color: '#B388FF', display: 'block', mb: 0.5 }}>
          3. Analyse Walk-Forward (précision globale)
        </Typography>

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
          <Tooltip title="Intervalle entre chaque point de vérification (jours)">
            <TextField
              type="number"
              size="small"
              label="Pas (j)"
              value={wfStepDays}
              onChange={(e) => setWfStepDays(Math.max(7, Math.min(365, Number(e.target.value))))}
              inputProps={{ min: 7, max: 365 }}
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
                  label={`Horizon ${acc.horizon_days}j (${acc.correct}/${acc.total_points})`}
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
                      {acc.horizon_days}j
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
                    {acc.horizon_days}j:
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
                              label={`${o.horizon_days}j ${o.actual_change_pct >= 0 ? '+' : ''}${o.actual_change_pct.toFixed(0)}%`}
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
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 1, fontSize: '0.75rem' }}>
            Chargez d'abord l'historique BTC pour commencer la vérification.
          </Typography>
        )}
      </CardContent>
    </GlowingCard>
  );
};

export default VerificationPanel;

