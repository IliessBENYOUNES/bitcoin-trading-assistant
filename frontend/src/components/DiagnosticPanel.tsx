/**
 * DiagnosticPanel — Diagnostic de fréquence de trading v1.6
 *
 * Affiche :
 * 1. Résumé KPI (ticks, trades, ratio, bottleneck)
 * 2. Top raisons de non-trade (barre horizontale)
 * 3. Comparaison des profils (table)
 * 4. Durée des positions
 * 5. Analyse risk engine
 * 6. Opportunités manquées
 * 7. Analyse levier
 * 8. Recommandations
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Box, Typography, Paper, Chip, LinearProgress, Alert, AlertTitle,
  Table, TableHead, TableRow, TableCell, TableBody, Tooltip, Button,
  Divider, Stack, CircularProgress,
} from '@mui/material';
import {
  Warning as WarningIcon,
  Speed as SpeedIcon,
  Assessment as AssessmentIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import type {
  DiagnosticResponse,
  NonTradeRankedReason,
  ProfileComparisonRow,
  MissedOpportunitySummary,
  LeverageAnalysisResponse,
} from '../types/diagnostic';
import {
  getPaperDiagnostic,
  getPaperMissedOpportunities,
  getPaperLeverageAnalysis,
} from '../api/marketApi';


const CATEGORY_COLORS: Record<string, string> = {
  signal: '#ff9800',
  risk: '#f44336',
  structural: '#9c27b0',
  frequency: '#2196f3',
  other: '#757575',
};

const CATEGORY_LABELS: Record<string, string> = {
  signal: '📊 Signal',
  risk: '🛡️ Risque',
  structural: '🔧 Structure',
  frequency: '⏱️ Fréquence',
  other: '❓ Autre',
};

interface DiagnosticPanelProps {
  dateFrom?: string;
  dateTo?: string;
  /** Compteur externe — quand il change, le panneau se rafraîchit automatiquement */
  refreshTrigger?: number;
}

export default function DiagnosticPanel({ dateFrom, dateTo, refreshTrigger }: DiagnosticPanelProps) {
  const [diagnostic, setDiagnostic] = useState<DiagnosticResponse | null>(null);
  const [missed, setMissed] = useState<MissedOpportunitySummary | null>(null);
  const [leverage, setLeverage] = useState<LeverageAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { date_from: dateFrom, date_to: dateTo };
      const [diag, miss, lev] = await Promise.all([
        getPaperDiagnostic(params),
        getPaperMissedOpportunities(params),
        getPaperLeverageAnalysis(params),
      ]);
      setDiagnostic(diag);
      setMissed(miss);
      setLeverage(lev);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Erreur lors du chargement du diagnostic';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto-refresh quand refreshTrigger change (après un trade)
  const prevTriggerRef = useRef(refreshTrigger);
  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger !== prevTriggerRef.current) {
      prevTriggerRef.current = refreshTrigger;
      refresh();
    }
  }, [refreshTrigger, refresh]);

  if (loading) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <CircularProgress size={40} />
        <Typography sx={{ mt: 1 }}>Analyse en cours...</Typography>
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!diagnostic) return null;

  return (
    <Box>
      {/* Header + Refresh */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AssessmentIcon /> Diagnostic de Fréquence
        </Typography>
        <Button size="small" startIcon={<RefreshIcon />} onClick={refresh}>
          Actualiser
        </Button>
      </Box>

      {/* KPI Summary */}
      <Paper sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <KpiBox label="Ticks analysés" value={diagnostic.total_ticks} />
          <KpiBox label="Trades exécutés" value={diagnostic.total_trades} />
          <KpiBox
            label="Ratio Tick→Trade"
            value={`${diagnostic.tick_to_trade_pct}%`}
            color={diagnostic.tick_to_trade_pct < 1 ? '#f44336' : diagnostic.tick_to_trade_pct < 5 ? '#ff9800' : '#4caf50'}
          />
          <KpiBox label="Trades/jour" value={diagnostic.avg_trades_per_day.toFixed(1)} />
          <KpiBox label="Période" value={`${diagnostic.analysis_days.toFixed(0)}j`} />
        </Stack>
      </Paper>

      {/* Bottleneck Alert */}
      <Alert
        severity={diagnostic.main_bottleneck === 'no_data' ? 'info' : 'warning'}
        icon={<WarningIcon />}
        sx={{ mb: 2 }}
      >
        <AlertTitle>
          Goulot d'étranglement principal : {diagnostic.main_bottleneck.replace(/_/g, ' ')}
        </AlertTitle>
        {diagnostic.bottleneck_detail}
      </Alert>

      {/* Top Non-Trade Reasons */}
      {diagnostic.top_non_trade_reasons.length > 0 && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
            📊 Top Raisons de Non-Trade
          </Typography>
          {diagnostic.top_non_trade_reasons.slice(0, 7).map((r: NonTradeRankedReason) => (
            <Box key={r.reason} sx={{ mb: 1 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.3 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip
                    label={CATEGORY_LABELS[r.category] || r.category}
                    size="small"
                    sx={{ bgcolor: CATEGORY_COLORS[r.category] || '#757575', color: 'white', fontSize: '0.7rem' }}
                  />
                  <Typography variant="body2">{r.label}</Typography>
                </Box>
                <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                  {r.count} ({r.pct}%)
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={r.pct}
                sx={{
                  height: 8,
                  borderRadius: 4,
                  bgcolor: 'rgba(255,255,255,0.1)',
                  '& .MuiLinearProgress-bar': {
                    bgcolor: CATEGORY_COLORS[r.category] || '#757575',
                  },
                }}
              />
            </Box>
          ))}

          {/* Filter distribution */}
          <Divider sx={{ my: 1.5 }} />
          <Stack direction="row" spacing={2}>
            <FilterChip label="Signal" pct={diagnostic.risk_brake.pct_signal_filter} color="#ff9800" />
            <FilterChip label="Risque" pct={diagnostic.risk_brake.pct_risk_filter} color="#f44336" />
            <FilterChip label="Structure" pct={diagnostic.risk_brake.pct_structural} color="#9c27b0" />
          </Stack>
        </Paper>
      )}

      {/* Position Duration */}
      {diagnostic.position_duration.total_closed > 0 && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
            ⏱️ Durée des Positions
          </Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            <KpiBox label="Moy." value={`${diagnostic.position_duration.avg_duration_hours.toFixed(1)}h`} />
            <KpiBox label="Médiane" value={`${diagnostic.position_duration.median_duration_hours.toFixed(1)}h`} />
            <KpiBox label="< 1h" value={`${diagnostic.position_duration.pct_under_1h}%`} />
            <KpiBox label="1-4h" value={`${diagnostic.position_duration.pct_1h_to_4h}%`} />
            <KpiBox label="4-24h" value={`${diagnostic.position_duration.pct_4h_to_24h}%`} />
            <KpiBox label="> 24h" value={`${diagnostic.position_duration.pct_over_24h}%`} />
          </Stack>
          {diagnostic.position_duration.pct_ticks_blocked_by_position > 10 && (
            <Alert severity="warning" sx={{ mt: 1 }} variant="outlined">
              {diagnostic.position_duration.pct_ticks_blocked_by_position.toFixed(0)}% des ticks sont bloqués
              car une position est déjà ouverte ({diagnostic.position_duration.ticks_blocked_by_open_position} ticks)
            </Alert>
          )}
        </Paper>
      )}

      {/* Profile Comparison */}
      {diagnostic.profile_comparison.length > 0 && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
            📈 Comparaison des Profils
          </Typography>
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Profil</TableCell>
                  <TableCell align="right">Trades</TableCell>
                  <TableCell align="right">Trades/j</TableCell>
                  <TableCell align="right">Win Rate</TableCell>
                  <TableCell align="right">PnL</TableCell>
                  <TableCell align="right">Expectancy</TableCell>
                  <TableCell align="right">Durée moy.</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Entrées simulées si ce profil était actif">
                      <span>Simul. entrées/j</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell>Top blocage</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {diagnostic.profile_comparison.map((row: ProfileComparisonRow) => (
                  <TableRow
                    key={row.profile}
                    sx={{
                      bgcolor: row.profile === 'scalping' ? 'rgba(33, 150, 243, 0.08)' : undefined,
                    }}
                  >
                    <TableCell sx={{ fontWeight: 'bold', textTransform: 'capitalize' }}>
                      {row.profile}
                    </TableCell>
                    <TableCell align="right">{row.total_trades}</TableCell>
                    <TableCell align="right">{row.trades_per_day.toFixed(1)}</TableCell>
                    <TableCell align="right">{row.win_rate.toFixed(0)}%</TableCell>
                    <TableCell
                      align="right"
                      sx={{ color: row.net_pnl >= 0 ? '#4caf50' : '#f44336' }}
                    >
                      {row.net_pnl >= 0 ? '+' : ''}{row.net_pnl.toFixed(2)} $
                    </TableCell>
                    <TableCell align="right">{row.expectancy.toFixed(2)} $</TableCell>
                    <TableCell align="right">{row.avg_duration_hours.toFixed(1)}h</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 'bold', color: '#2196f3' }}>
                      {row.simulated_entries_per_day.toFixed(1)}
                    </TableCell>
                    <TableCell>
                      {row.top_block_reason && (
                        <Chip
                          label={`${row.top_block_reason} (${row.top_block_pct}%)`}
                          size="small"
                          variant="outlined"
                          sx={{ fontSize: '0.65rem' }}
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Paper>
      )}

      {/* Missed Opportunities */}
      {missed && missed.total_non_trade_ticks_analyzed > 0 && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
            🎯 Opportunités Manquées (ex-post)
          </Typography>
          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
            <KpiBox label="Ticks analysés" value={missed.total_non_trade_ticks_analyzed} />
            <KpiBox
              label="Avec mouvement favorable"
              value={missed.ticks_with_favorable_move}
              color="#ff9800"
            />
            <KpiBox label="% manqué" value={`${missed.pct_missed.toFixed(1)}%`} />
            <KpiBox label="Mouvement moyen" value={`${missed.avg_missed_move_pct.toFixed(2)}%`} />
          </Stack>
          <Stack direction="row" spacing={2} sx={{ mb: 1 }}>
            <Chip label={`≥ 0.1% : ${missed.missed_above_010_pct}`} size="small" />
            <Chip label={`≥ 0.2% : ${missed.missed_above_020_pct}`} size="small" />
            <Chip label={`≥ 0.3% : ${missed.missed_above_030_pct}`} size="small" />
            <Chip label={`≥ 0.5% : ${missed.missed_above_050_pct}`} size="small" color="warning" />
          </Stack>
          <Alert severity="info" variant="outlined" sx={{ fontSize: '0.75rem' }}>
            ⚠️ {missed.warning}
          </Alert>
        </Paper>
      )}

      {/* Leverage Analysis */}
      {leverage && (leverage.total_leveraged_trades > 0 || leverage.total_unleveraged_trades > 0) && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
            ⚖️ Analyse Levier
          </Typography>
          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
            <KpiBox label="Trades levierisés" value={leverage.total_leveraged_trades} />
            <KpiBox label="Trades x1" value={leverage.total_unleveraged_trades} />
            <KpiBox
              label="PnL avec levier"
              value={`${leverage.pnl_with_leverage >= 0 ? '+' : ''}${leverage.pnl_with_leverage.toFixed(2)} $`}
              color={leverage.pnl_with_leverage >= 0 ? '#4caf50' : '#f44336'}
            />
            <KpiBox
              label="PnL sans levier"
              value={`${leverage.pnl_without_leverage >= 0 ? '+' : ''}${leverage.pnl_without_leverage.toFixed(2)} $`}
            />
            <KpiBox
              label="Bénéfice levier"
              value={`${leverage.leverage_benefit >= 0 ? '+' : ''}${leverage.leverage_benefit.toFixed(2)} $`}
              color={leverage.leverage_benefit >= 0 ? '#4caf50' : '#f44336'}
            />
          </Stack>
          {leverage.trades_reduced_by_risk > 0 && (
            <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.secondary' }}>
              {leverage.trades_reduced_by_risk} trades avec levier réduit par le risk engine
            </Typography>
          )}
        </Paper>
      )}

      {/* Recommendations */}
      {diagnostic.recommendations.length > 0 && (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
            💡 Recommandations
          </Typography>
          {diagnostic.recommendations.map((rec: string, i: number) => (
            <Box key={i} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, mb: 0.5 }}>
              <SpeedIcon sx={{ fontSize: 16, mt: 0.3, color: '#2196f3' }} />
              <Typography variant="body2">{rec}</Typography>
            </Box>
          ))}
        </Paper>
      )}
    </Box>
  );
}

// ── Sous-composants ──────────────────────────────────────────────────────────

function KpiBox({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <Box sx={{ textAlign: 'center', minWidth: 80 }}>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>{label}</Typography>
      <Typography variant="h6" sx={{ fontWeight: 'bold', color: color || 'text.primary', lineHeight: 1.2 }}>
        {value}
      </Typography>
    </Box>
  );
}

function FilterChip({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <Chip
      label={`${label}: ${pct.toFixed(0)}%`}
      size="small"
      sx={{
        bgcolor: `${color}22`,
        color: color,
        fontWeight: 'bold',
        fontSize: '0.75rem',
      }}
    />
  );
}


