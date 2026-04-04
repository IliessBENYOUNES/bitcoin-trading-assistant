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
} from '@mui/icons-material';

import { GlowingCard, ACCENT } from './GlowingCard';
import {
  loadHistory,
  getHistoryRange,
  verifyAtDate,
  runWalkForward,
} from '../api/marketApi';
import type {
  HistoryRangeResponse,
  HistoryLoadResponse,
  VerificationResult,
  WalkForwardResult,
  HorizonOutcome,
  HorizonAccuracy,
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

  // State: Single verification
  const [targetDate, setTargetDate] = useState('2020-01-01');
  const [verifyResult, setVerifyResult] = useState<VerificationResult | null>(null);
  const [verifying, setVerifying] = useState(false);

  // State: Walk-forward
  const [wfStartDate, setWfStartDate] = useState('2018-01-01');
  const [wfEndDate, setWfEndDate] = useState('2025-01-01');
  const [wfStepDays, setWfStepDays] = useState(30);
  const [wfResult, setWfResult] = useState<WalkForwardResult | null>(null);
  const [walkingForward, setWalkingForward] = useState(false);

  // State: UI
  const [showOutcomes, setShowOutcomes] = useState(true);
  const [showWfDetails, setShowWfDetails] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch range on mount
  const refreshRange = useCallback(async () => {
    try {
      const r = await getHistoryRange({ timeframe: loadTimeframe });
      setRange(r);
    } catch {
      /* ignore */
    }
  }, [loadTimeframe]);

  useEffect(() => {
    refreshRange();
  }, [refreshRange]);

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
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur chargement');
    } finally {
      setLoadingHistory(false);
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
          Le moteur fonctionne en mode 100% technique (pas de sentiment en historique).
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

