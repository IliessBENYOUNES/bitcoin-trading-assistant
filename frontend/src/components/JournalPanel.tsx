/**
 * JournalPanel — Journal d'évaluation Paper Trading multi-jours.
 *
 * Affiche :
 * - Filtres par plage de dates (presets + custom)
 * - Vue synthétique de la période (KPIs + verdict)
 * - Vue journalière (résumé par jour)
 * - Activité / fréquence (ticks → trades ratio)
 * - Raisons de non-trade (distribution)
 * - Profil actif + sélection
 * - Style de trading (distribution durées)
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Typography,
  Chip,
  Stack,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  Button,
  CircularProgress,
  LinearProgress,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import {
  Assessment as AssessmentIcon,
  CalendarMonth as CalendarIcon,
  TrendingUp,
  Speed as SpeedIcon,
  Block as BlockIcon,
  Style as StyleIcon,
  Tune as TuneIcon,
} from '@mui/icons-material';
import type {
  JournalResponse,
  TradingProfileResponse,
  TradingProfileParams,
  TradingStyleResult,
} from '../types';
import {
  getPaperJournal,
  getPaperProfile,
  setPaperProfile,
  getPaperProfilePresets,
  getPaperStyle,
} from '../api/marketApi';

// Couleurs
const pnlColor = (v: number): string => (v >= 0 ? '#4caf50' : '#f44336');
const verdictColor = (v: string): string => {
  if (v.includes('prometteur')) return '#4caf50';
  if (v.includes('mitigé') || v.includes('correct')) return '#ff9800';
  if (v.includes('faible') || v.includes('mauvais')) return '#f44336';
  if (v.includes('critique')) return '#d32f2f';
  if (v.includes('bon')) return '#4caf50';
  return '#999';
};

// Date presets
const DATE_PRESETS = [
  { label: "Aujourd'hui", getValue: () => { const d = isoDate(); return { from: d, to: d }; } },
  { label: 'Hier', getValue: () => { const d = isoDate(-1); return { from: d, to: d }; } },
  { label: '7 jours', getValue: () => ({ from: isoDate(-7), to: isoDate() }) },
  { label: '14 jours', getValue: () => ({ from: isoDate(-14), to: isoDate() }) },
  { label: '30 jours', getValue: () => ({ from: isoDate(-30), to: isoDate() }) },
  { label: 'Tout', getValue: () => ({ from: '2020-01-01', to: isoDate() }) },
];

function isoDate(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().split('T')[0];
}

// Profile colors
const PROFILE_COLORS: Record<string, string> = {
  conservative: '#4caf50',
  balanced: '#ff9800',
  aggressive: '#f44336',
};

export default function JournalPanel() {
  // Date filters
  const [dateFrom, setDateFrom] = useState(isoDate(-7));
  const [dateTo, setDateTo] = useState(isoDate());
  const [activePreset, setActivePreset] = useState(2); // "7 jours"

  // Data
  const [journal, setJournal] = useState<JournalResponse | null>(null);
  const [profile, setProfile] = useState<TradingProfileResponse | null>(null);
  const [presets, setPresets] = useState<TradingProfileParams[]>([]);
  const [style, setStyle] = useState<TradingStyleResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sub-view tabs
  const [subView, setSubView] = useState<'summary' | 'daily' | 'activity' | 'reasons' | 'style'>('summary');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [j, p, pr, s] = await Promise.all([
        getPaperJournal({ date_from: dateFrom, date_to: dateTo }),
        getPaperProfile(),
        getPaperProfilePresets(),
        getPaperStyle(),
      ]);
      setJournal(j);
      setProfile(p);
      setPresets(pr);
      setStyle(s);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handlePreset = (idx: number) => {
    setActivePreset(idx);
    const v = DATE_PRESETS[idx].getValue();
    setDateFrom(v.from);
    setDateTo(v.to);
  };

  const handleProfileChange = async (newProfile: string) => {
    try {
      const result = await setPaperProfile(newProfile);
      setProfile(result);
      await fetchData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erreur profil');
    }
  };

  const period = journal?.period;
  const daily = journal?.daily ?? [];
  const activity = journal?.activity;
  const nonTrade = journal?.non_trade_reasons;

  return (
    <Box>
      {/* ── HEADER ── */}
      <Stack direction="row" alignItems="center" spacing={1} mb={2}>
        <AssessmentIcon sx={{ color: '#F7931A' }} />
        <Typography variant="h6" fontWeight={700}>
          📊 Journal d'Évaluation
        </Typography>
        {profile && (
          <Chip
            size="small"
            label={profile.params.label}
            sx={{
              bgcolor: `${PROFILE_COLORS[profile.active_profile]}20`,
              color: PROFILE_COLORS[profile.active_profile],
              fontWeight: 700,
              border: `1px solid ${PROFILE_COLORS[profile.active_profile]}40`,
            }}
          />
        )}
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── PROFIL ── */}
      <Box sx={{
        mb: 2, p: 1.5,
        borderRadius: 2,
        border: '1px solid rgba(255,255,255,0.06)',
        bgcolor: 'rgba(255,255,255,0.02)',
      }}>
        <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
          <TuneIcon sx={{ color: 'text.secondary', fontSize: 18 }} />
          <Typography variant="body2" fontWeight={600} color="text.secondary">Profil :</Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={profile?.active_profile ?? 'conservative'}
            onChange={(_, v) => v && handleProfileChange(v)}
          >
            {presets.map(p => (
              <ToggleButton
                key={p.profile_type}
                value={p.profile_type}
                sx={{
                  textTransform: 'none',
                  fontWeight: 700,
                  fontSize: '0.75rem',
                  px: 1.5,
                  color: PROFILE_COLORS[p.profile_type],
                  borderColor: `${PROFILE_COLORS[p.profile_type]}40`,
                  '&.Mui-selected': {
                    bgcolor: `${PROFILE_COLORS[p.profile_type]}20`,
                    color: PROFILE_COLORS[p.profile_type],
                    borderColor: PROFILE_COLORS[p.profile_type],
                  },
                }}
              >
                {p.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          {profile && (
            <Typography variant="caption" color="text.secondary">
              Score min: {profile.params.min_score} | Cooldown: {profile.params.cooldown_minutes}m |
              Max/jour: {profile.params.max_trades_per_day} |
              Levier: {profile.params.leverage_enabled ? `x${profile.params.max_leverage}` : 'OFF'}
            </Typography>
          )}
        </Stack>
      </Box>

      {/* ── DATE FILTERS ── */}
      <Stack direction="row" spacing={1} mb={2} flexWrap="wrap" useFlexGap alignItems="center">
        <CalendarIcon sx={{ color: 'text.secondary', fontSize: 18 }} />
        {DATE_PRESETS.map((p, i) => (
          <Chip
            key={i}
            size="small"
            label={p.label}
            variant={activePreset === i ? 'filled' : 'outlined'}
            color={activePreset === i ? 'primary' : 'default'}
            onClick={() => handlePreset(i)}
            sx={{ cursor: 'pointer', fontWeight: activePreset === i ? 700 : 400 }}
          />
        ))}
        <TextField
          size="small" type="date" value={dateFrom}
          onChange={e => { setDateFrom(e.target.value); setActivePreset(-1); }}
          label="Du" InputLabelProps={{ shrink: true }}
          sx={{ width: 145 }}
        />
        <TextField
          size="small" type="date" value={dateTo}
          onChange={e => { setDateTo(e.target.value); setActivePreset(-1); }}
          label="Au" InputLabelProps={{ shrink: true }}
          sx={{ width: 145 }}
        />
        <Button size="small" variant="outlined" onClick={fetchData} disabled={loading}>
          {loading ? <CircularProgress size={14} /> : 'Actualiser'}
        </Button>
      </Stack>

      {/* ── SUB-TABS ── */}
      <Stack direction="row" spacing={0.5} mb={2} flexWrap="wrap" useFlexGap>
        {[
          { key: 'summary', label: '📈 Synthèse', icon: <TrendingUp sx={{ fontSize: 14 }} /> },
          { key: 'daily', label: '📅 Journalier', icon: <CalendarIcon sx={{ fontSize: 14 }} /> },
          { key: 'activity', label: '⚡ Activité', icon: <SpeedIcon sx={{ fontSize: 14 }} /> },
          { key: 'reasons', label: '🚫 Non-trade', icon: <BlockIcon sx={{ fontSize: 14 }} /> },
          { key: 'style', label: '🎯 Style', icon: <StyleIcon sx={{ fontSize: 14 }} /> },
        ].map(t => (
          <Chip
            key={t.key}
            size="small"
            icon={t.icon}
            label={t.label}
            variant={subView === t.key ? 'filled' : 'outlined'}
            color={subView === t.key ? 'primary' : 'default'}
            onClick={() => setSubView(t.key as typeof subView)}
            sx={{ cursor: 'pointer', fontWeight: subView === t.key ? 700 : 400 }}
          />
        ))}
      </Stack>

      {loading && <LinearProgress sx={{ mb: 2 }} />}

      {/* ── SYNTHÈSE ── */}
      {subView === 'summary' && period && (
        <Box>
          {/* Verdict */}
          <Alert
            severity={
              period.verdict.includes('prometteur') ? 'success' :
              period.verdict.includes('mitigé') ? 'warning' :
              period.verdict.includes('N/A') ? 'info' : 'error'
            }
            sx={{ mb: 2 }}
          >
            <strong>Verdict :</strong> {period.verdict}
            {period.total_trades > 0 && (
              <> — {period.total_trades} trades sur {period.date_from} → {period.date_to}</>
            )}
          </Alert>

          {/* KPIs Grid */}
          <Box sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
            gap: 1.5, mb: 2, p: 2,
            bgcolor: 'background.paper', borderRadius: 2,
            border: '1px solid', borderColor: 'divider',
          }}>
            <KPI label="Trades" value={`${period.total_trades}`} />
            <KPI label="Trades/jour" value={`${period.trades_per_day}`} />
            <KPI label="Win Rate" value={`${period.win_rate}%`} color={period.win_rate >= 50 ? '#4caf50' : '#f44336'} />
            <KPI label="PnL réalisé" value={`${period.pnl_realized >= 0 ? '+' : ''}${period.pnl_realized.toFixed(2)} $`} color={pnlColor(period.pnl_realized)} />
            <KPI label="PnL %" value={`${period.pnl_pct >= 0 ? '+' : ''}${period.pnl_pct.toFixed(2)}%`} color={pnlColor(period.pnl_pct)} />
            <KPI label="Gain moyen" value={`${period.avg_win.toFixed(2)} $`} color="#4caf50" />
            <KPI label="Perte moy." value={`${period.avg_loss.toFixed(2)} $`} color="#f44336" />
            <KPI label="Expectancy" value={`${period.expectancy >= 0 ? '+' : ''}${period.expectancy.toFixed(2)} $`} color={pnlColor(period.expectancy)} />
            <KPI label="Profit Factor" value={`${period.profit_factor}`} color={period.profit_factor >= 1 ? '#4caf50' : '#f44336'} />
            <KPI label="Sharpe" value={period.sharpe !== null ? `${period.sharpe}` : '—'} />
            <KPI label="Max Drawdown" value={`${period.max_drawdown_pct}%`} color="#f44336" />
            <KPI label="Série gagnante" value={`${period.best_streak}`} color="#4caf50" />
            <KPI label="Série perdante" value={`${period.worst_streak}`} color="#f44336" />
            <KPI label="Durée moy." value={`${period.avg_position_duration_hours.toFixed(1)}h`} />
            <KPI label="Ticks total" value={`${period.total_ticks}`} />
          </Box>
        </Box>
      )}

      {/* ── JOURNALIER ── */}
      {subView === 'daily' && (
        <Box>
          {daily.length === 0 ? (
            <Alert severity="info">Aucune donnée journalière sur cette période.</Alert>
          ) : (
            <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 400 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell align="center">Ticks</TableCell>
                    <TableCell align="center">Trades</TableCell>
                    <TableCell align="right">PnL</TableCell>
                    <TableCell align="right">PnL %</TableCell>
                    <TableCell align="right">Win Rate</TableCell>
                    <TableCell align="right">Meilleur</TableCell>
                    <TableCell align="right">Pire</TableCell>
                    <TableCell align="right">Durée moy.</TableCell>
                    <TableCell>Verdict</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {daily.map(d => (
                    <TableRow key={d.date} hover>
                      <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700 }}>{d.date}</TableCell>
                      <TableCell align="center">{d.total_ticks}</TableCell>
                      <TableCell align="center">{d.total_trades}</TableCell>
                      <TableCell align="right" sx={{ color: pnlColor(d.pnl_realized), fontWeight: 700 }}>
                        {d.pnl_realized >= 0 ? '+' : ''}{d.pnl_realized.toFixed(2)} $
                      </TableCell>
                      <TableCell align="right" sx={{ color: pnlColor(d.pnl_pct) }}>
                        {d.pnl_pct >= 0 ? '+' : ''}{d.pnl_pct.toFixed(2)}%
                      </TableCell>
                      <TableCell align="right">{d.total_trades > 0 ? `${d.win_rate.toFixed(0)}%` : '—'}</TableCell>
                      <TableCell align="right" sx={{ color: '#4caf50' }}>
                        {d.best_trade_pnl !== 0 ? `+${d.best_trade_pnl.toFixed(2)}` : '—'}
                      </TableCell>
                      <TableCell align="right" sx={{ color: '#f44336' }}>
                        {d.worst_trade_pnl !== 0 ? `${d.worst_trade_pnl.toFixed(2)}` : '—'}
                      </TableCell>
                      <TableCell align="right">{d.avg_position_duration_hours > 0 ? `${d.avg_position_duration_hours.toFixed(1)}h` : '—'}</TableCell>
                      <TableCell>
                        <Chip size="small" label={d.verdict} sx={{ color: verdictColor(d.verdict), fontWeight: 700, fontSize: '0.7rem' }} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      )}

      {/* ── ACTIVITÉ ── */}
      {subView === 'activity' && activity && (
        <Box>
          <Box sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 1.5, p: 2,
            bgcolor: 'background.paper', borderRadius: 2,
            border: '1px solid', borderColor: 'divider',
          }}>
            <KPI label="Total ticks" value={`${activity.total_ticks}`} />
            <KPI label="Ticks avec signal" value={`${activity.ticks_with_signal}`} />
            <KPI label="Ouvertures" value={`${activity.ticks_opened}`} color="#4caf50" />
            <KPI label="Fermetures" value={`${activity.ticks_closed}`} color="#ff9800" />
            <KPI label="Hold (conserve)" value={`${activity.ticks_hold}`} />
            <KPI label="Bloqués (risk)" value={`${activity.ticks_blocked_risk}`} color="#f44336" />
            <KPI label="Signal ignoré" value={`${activity.ticks_ignored_signal}`} color="#ff9800" />
            <KPI label="Position gardée" value={`${activity.ticks_position_held}`} />
            <KPI label="Sorties TP" value={`${activity.ticks_exit_tp}`} color="#4caf50" />
            <KPI label="Sorties SL" value={`${activity.ticks_exit_sl}`} color="#f44336" />
            <KPI label="Sorties signal" value={`${activity.ticks_exit_signal}`} color="#ff9800" />
            <KPI label="Sorties expirées" value={`${activity.ticks_exit_expired}`} />
            <KPI
              label="Ratio tick → trade"
              value={`${activity.tick_to_trade_ratio.toFixed(1)}%`}
              color={activity.tick_to_trade_ratio > 5 ? '#4caf50' : '#ff9800'}
            />
          </Box>

          {/* Barre visuelle du ratio */}
          {activity.total_ticks > 0 && (
            <Box sx={{ mt: 2, p: 2, bgcolor: 'background.paper', borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
              <Typography variant="body2" fontWeight={600} mb={1}>
                Répartition des ticks
              </Typography>
              <TickDistributionBar activity={activity} />
            </Box>
          )}
        </Box>
      )}

      {/* ── RAISONS DE NON-TRADE ── */}
      {subView === 'reasons' && nonTrade && (
        <Box>
          {nonTrade.total_non_trade_ticks === 0 ? (
            <Alert severity="info">Aucune raison de non-trade enregistrée.</Alert>
          ) : (
            <>
              <Alert severity="info" sx={{ mb: 2 }}>
                <strong>{nonTrade.total_non_trade_ticks}</strong> ticks sans trade sur la période.
                Comprendre pourquoi aide à ajuster les profils.
              </Alert>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Raison</TableCell>
                      <TableCell align="right">Occurrences</TableCell>
                      <TableCell align="right">%</TableCell>
                      <TableCell>Barre</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {nonTrade.reasons.map(r => (
                      <TableRow key={r.reason} hover>
                        <TableCell>
                          <Tooltip title={r.reason}>
                            <Typography variant="body2">{r.label}</Typography>
                          </Tooltip>
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700, fontFamily: 'monospace' }}>
                          {r.count}
                        </TableCell>
                        <TableCell align="right" sx={{ fontFamily: 'monospace' }}>
                          {r.pct.toFixed(1)}%
                        </TableCell>
                        <TableCell sx={{ width: '30%' }}>
                          <LinearProgress
                            variant="determinate"
                            value={r.pct}
                            sx={{
                              height: 6,
                              borderRadius: 3,
                              bgcolor: 'rgba(255,255,255,0.06)',
                              '& .MuiLinearProgress-bar': {
                                bgcolor: r.pct > 30 ? '#f44336' : r.pct > 15 ? '#ff9800' : '#4caf50',
                                borderRadius: 3,
                              },
                            }}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </Box>
      )}

      {/* ── STYLE DE TRADING ── */}
      {subView === 'style' && style && (
        <Box>
          {style.total_closed_trades === 0 ? (
            <Alert severity="info">Pas assez de trades pour qualifier le style.</Alert>
          ) : (
            <>
              <Alert
                severity="info"
                sx={{ mb: 2 }}
              >
                Style dominant : <strong>{style.dominant_style}</strong>
                {' — '}Durée médiane : <strong>{style.median_duration_minutes.toFixed(1)} min</strong>
                {' — '}{style.total_closed_trades} trades analysés
              </Alert>

              {/* Distribution des durées */}
              <Box sx={{
                p: 2, mb: 2,
                bgcolor: 'background.paper', borderRadius: 2,
                border: '1px solid', borderColor: 'divider',
              }}>
                <Typography variant="body2" fontWeight={600} mb={1.5}>
                  Distribution des durées de position
                </Typography>
                <Stack spacing={1}>
                  {style.duration_distribution.map(b => (
                    <Stack key={b.label} direction="row" alignItems="center" spacing={1.5}>
                      <Typography variant="caption" sx={{ minWidth: 80, fontFamily: 'monospace', fontWeight: 700 }}>
                        {b.label}
                      </Typography>
                      <Box sx={{ flex: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={b.pct}
                          sx={{
                            height: 10,
                            borderRadius: 5,
                            bgcolor: 'rgba(255,255,255,0.06)',
                            '& .MuiLinearProgress-bar': {
                              borderRadius: 5,
                              background: 'linear-gradient(90deg, #F7931A, #FFB74D)',
                            },
                          }}
                        />
                      </Box>
                      <Typography variant="caption" sx={{ minWidth: 50, fontFamily: 'monospace', textAlign: 'right' }}>
                        {b.count} ({b.pct}%)
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              </Box>

              {/* Stats résumées */}
              <Box sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                gap: 1.5, p: 2,
                bgcolor: 'background.paper', borderRadius: 2,
                border: '1px solid', borderColor: 'divider',
              }}>
                <KPI label="Style dominant" value={style.dominant_style} />
                <KPI label="Durée moyenne" value={`${style.avg_duration_minutes.toFixed(1)} min`} />
                <KPI label="Durée médiane" value={`${style.median_duration_minutes.toFixed(1)} min`} />
                <KPI label="Exits rapides (<5m)" value={`${style.exits_fast_count}`} />
                <KPI label="Exits lents (>1h)" value={`${style.exits_slow_count}`} />
                <KPI label="Trades analysés" value={`${style.total_closed_trades}`} />
              </Box>
            </>
          )}
        </Box>
      )}
    </Box>
  );
}

// ── Sous-composants ──

function KPI({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Box textAlign="center">
      <Typography variant="caption" color="text.secondary" display="block" sx={{ fontSize: '0.65rem' }}>
        {label}
      </Typography>
      <Typography variant="body1" fontWeight={700} sx={{ color: color || 'text.primary', fontSize: '0.95rem' }}>
        {value}
      </Typography>
    </Box>
  );
}

function TickDistributionBar({ activity }: { activity: JournalResponse['activity'] }) {
  const total = activity.total_ticks || 1;
  const segments = [
    { label: 'Ouvertures', count: activity.ticks_opened, color: '#4caf50' },
    { label: 'Fermetures', count: activity.ticks_closed, color: '#ff9800' },
    { label: 'Hold', count: activity.ticks_hold, color: '#448AFF' },
    { label: 'Bloqué', count: activity.ticks_blocked_risk, color: '#f44336' },
    { label: 'Ignoré', count: activity.ticks_ignored_signal, color: '#9e9e9e' },
  ].filter(s => s.count > 0);

  return (
    <Box>
      <Box sx={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden', mb: 1 }}>
        {segments.map(s => (
          <Tooltip key={s.label} title={`${s.label}: ${s.count} (${((s.count / total) * 100).toFixed(1)}%)`}>
            <Box sx={{ width: `${(s.count / total) * 100}%`, bgcolor: s.color, transition: 'width 0.5s' }} />
          </Tooltip>
        ))}
      </Box>
      <Stack direction="row" spacing={2} flexWrap="wrap">
        {segments.map(s => (
          <Stack key={s.label} direction="row" alignItems="center" spacing={0.5}>
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: s.color }} />
            <Typography variant="caption" color="text.secondary">{s.label} ({s.count})</Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}




