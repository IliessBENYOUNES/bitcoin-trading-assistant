/**
 * PaperTradingPanel — Panneau de paper trading en temps réel.
 *
 * Affiche :
 * - État du compte (capital, PnL, win rate)
 * - Position ouverte courante (prix entrée, SL, TP, PnL latent)
 * - Métriques de performance (Sharpe, drawdown, profit factor)
 * - Journal des trades (table scrollable)
 * - Mode AUTO : exécute des ticks automatiquement à intervalle régulier
 * - Boutons : Activer, Reset, Tick manuel, Auto ON/OFF, Fermer position
 */
import { useState, useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Stack,
  Alert,
  Divider,
  Tooltip,
  CircularProgress,
  TextField,
  MenuItem,
  LinearProgress,
} from '@mui/material';
import {
  PlayArrow,
  Stop,
  Refresh,
  Close,
  TrendingUp,
  TrendingDown,
  AccountBalance,
  AutoMode as AutoModeIcon,
  Timer as TimerIcon,
} from '@mui/icons-material';
import { usePaperTrading } from '../hooks/usePaperTrading';
import type { PaperTradeItem } from '../types';

// Couleur selon PnL
const pnlColor = (pnl: number | null): string => {
  if (pnl === null) return 'text.secondary';
  return pnl >= 0 ? '#4caf50' : '#f44336';
};

// Format PnL avec signe
const formatPnl = (pnl: number | null, suffix = ''): string => {
  if (pnl === null) return '—';
  const sign = pnl >= 0 ? '+' : '';
  return `${sign}${pnl.toFixed(2)}${suffix}`;
};

// Status badge
const statusChip = (status: string) => {
  const map: Record<string, { color: 'success' | 'error' | 'warning' | 'info' | 'default'; label: string }> = {
    open: { color: 'info', label: '🔵 Ouvert' },
    closed_tp: { color: 'success', label: '✅ TP' },
    closed_sl: { color: 'error', label: '❌ SL' },
    closed_signal: { color: 'warning', label: '⚠️ Signal' },
    closed_expired: { color: 'default', label: '⏰ Expiré' },
    closed_manual: { color: 'default', label: '✋ Manuel' },
  };
  const cfg = map[status] || { color: 'default' as const, label: status };
  return <Chip size="small" color={cfg.color} label={cfg.label} />;
};

// Options d'intervalle auto-tick
const AUTO_INTERVALS = [
  { value: 5, label: '5s' },
  { value: 10, label: '10s' },
  { value: 30, label: '30s' },
  { value: 60, label: '1 min' },
  { value: 300, label: '5 min' },
  { value: 900, label: '15 min' },
  { value: 3600, label: '1h' },
];

export default function PaperTradingPanel() {
  const {
    status,
    trades,
    loading,
    error,
    lastTick,
    autoMode,
    autoIntervalSec,
    autoTickCount,
    startAuto,
    stopAuto,
    refresh,
    activate,
    reset,
    manualTick,
    closePosition,
  } = usePaperTrading({ pollInterval: 30000 });

  const [capital, setCapital] = useState('10000');
  const [tickLoading, setTickLoading] = useState(false);
  const [selectedInterval, setSelectedInterval] = useState(10);

  // Countdown timer pour le prochain tick auto
  const [countdown, setCountdown] = useState(0);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Gère le countdown quand autoMode est actif
  useEffect(() => {
    if (autoMode) {
      setCountdown(autoIntervalSec);
      countdownRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) return autoIntervalSec;
          return prev - 1;
        });
      }, 1000);
      return () => {
        if (countdownRef.current) clearInterval(countdownRef.current);
      };
    } else {
      setCountdown(0);
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    }
  }, [autoMode, autoIntervalSec]);

  const handleActivate = async () => {
    await activate(Number(capital) || 10000);
  };

  const handleReset = async () => {
    if (window.confirm('Réinitialiser le compte paper ? Tous les trades seront supprimés.')) {
      await reset(Number(capital) || 10000);
    }
  };

  const handleTick = async () => {
    setTickLoading(true);
    await manualTick();
    setTickLoading(false);
  };

  const handleClose = async () => {
    if (window.confirm('Fermer la position ouverte ?')) {
      await closePosition();
    }
  };

  const handleStartAuto = () => {
    startAuto(selectedInterval);
  };

  const handleStopAuto = () => {
    stopAuto();
  };

  const account = status?.account;
  const openPos = status?.open_position;
  const metrics = status?.metrics;
  const isActive = account?.is_active ?? false;

  // Progress pour le countdown
  const countdownProgress = autoMode && autoIntervalSec > 0
    ? ((autoIntervalSec - countdown) / autoIntervalSec) * 100
    : 0;

  return (
    <Box>
      {/* Header */}
      <Stack direction="row" alignItems="center" spacing={1} mb={2}>
        <AccountBalance sx={{ color: isActive ? '#4caf50' : '#999' }} />
        <Typography variant="h6" fontWeight={700}>
          📋 Paper Trading
        </Typography>
        <Chip
          size="small"
          label={isActive ? 'ACTIF' : 'INACTIF'}
          color={isActive ? 'success' : 'default'}
        />
        {autoMode && (
          <Chip
            size="small"
            icon={<AutoModeIcon sx={{ fontSize: 14 }} />}
            label={`AUTO ${AUTO_INTERVALS.find(i => i.value === autoIntervalSec)?.label ?? autoIntervalSec + 's'}`}
            color="primary"
            sx={{
              fontWeight: 700,
              animation: 'pulse-glow 2s ease-in-out infinite',
            }}
          />
        )}
        {status?.current_btc_price && (
          <Chip
            size="small"
            variant="outlined"
            label={`BTC $${status.current_btc_price.toLocaleString()}`}
          />
        )}
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
      )}

      {/* Contrôles principaux */}
      <Stack direction="row" spacing={1} mb={1.5} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Capital ($)"
          type="number"
          value={capital}
          onChange={(e) => setCapital(e.target.value)}
          sx={{ width: 120 }}
        />
        {!isActive ? (
          <Button
            variant="contained"
            color="success"
            startIcon={<PlayArrow />}
            onClick={handleActivate}
            disabled={loading}
          >
            Activer
          </Button>
        ) : (
          <>
            {!autoMode && (
              <Tooltip title="Exécuter un tick manuellement">
                <Button
                  variant="outlined"
                  startIcon={tickLoading ? <CircularProgress size={16} /> : <PlayArrow />}
                  onClick={handleTick}
                  disabled={tickLoading}
                >
                  Tick
                </Button>
              </Tooltip>
            )}
            {openPos && (
              <Button
                variant="outlined"
                color="warning"
                startIcon={<Close />}
                onClick={handleClose}
              >
                Fermer position
              </Button>
            )}
          </>
        )}
        <Button
          variant="outlined"
          color="error"
          startIcon={<Stop />}
          onClick={handleReset}
          disabled={loading}
        >
          Reset
        </Button>
        <Button
          variant="outlined"
          startIcon={<Refresh />}
          onClick={refresh}
          disabled={loading}
        >
          Actualiser
        </Button>
      </Stack>

      {/* ── MODE AUTO ─────────────────────────────────────────────────────── */}
      {isActive && (
        <Box sx={{
          mb: 2,
          p: 1.5,
          borderRadius: 2,
          border: autoMode ? '1px solid #F7931A' : '1px solid rgba(255,255,255,0.08)',
          bgcolor: autoMode ? 'rgba(247, 147, 26, 0.06)' : 'rgba(255,255,255,0.02)',
          transition: 'all 0.3s ease',
        }}>
          <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" useFlexGap>
            <AutoModeIcon sx={{ color: autoMode ? '#F7931A' : 'text.secondary', fontSize: 20 }} />
            <Typography variant="body2" fontWeight={600} sx={{ color: autoMode ? '#F7931A' : 'text.secondary' }}>
              Mode Auto
            </Typography>

            {!autoMode ? (
              <>
                <TextField
                  select
                  size="small"
                  value={selectedInterval}
                  onChange={(e) => setSelectedInterval(Number(e.target.value))}
                  sx={{ minWidth: 100 }}
                  label="Intervalle"
                >
                  {AUTO_INTERVALS.map(opt => (
                    <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                  ))}
                </TextField>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<PlayArrow />}
                  onClick={handleStartAuto}
                  sx={{
                    background: 'linear-gradient(135deg, #F7931A, #E65100)',
                    fontWeight: 700,
                    '&:hover': {
                      background: 'linear-gradient(135deg, #FFB74D, #F7931A)',
                      boxShadow: '0 0 16px rgba(247, 147, 26, 0.4)',
                    },
                  }}
                >
                  Démarrer Auto
                </Button>
              </>
            ) : (
              <>
                {/* Countdown + stats */}
                <Stack direction="row" alignItems="center" spacing={1} sx={{ flex: 1 }}>
                  <TimerIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                  <Typography variant="caption" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
                    Prochain tick dans {countdown}s
                  </Typography>
                  <Box sx={{ flex: 1, mx: 1 }}>
                    <LinearProgress
                      variant="determinate"
                      value={countdownProgress}
                      sx={{
                        height: 4,
                        borderRadius: 2,
                        bgcolor: 'rgba(255,255,255,0.06)',
                        '& .MuiLinearProgress-bar': {
                          bgcolor: '#F7931A',
                          borderRadius: 2,
                          transition: 'transform 1s linear',
                        },
                      }}
                    />
                  </Box>
                  <Chip
                    size="small"
                    label={`${autoTickCount} ticks`}
                    variant="outlined"
                    sx={{ fontWeight: 700, fontFamily: 'monospace' }}
                  />
                </Stack>
                <Button
                  variant="contained"
                  color="error"
                  size="small"
                  startIcon={<Stop />}
                  onClick={handleStopAuto}
                  sx={{ fontWeight: 700 }}
                >
                  Arrêter
                </Button>
              </>
            )}
          </Stack>
        </Box>
      )}

      {/* Dernière action */}
      {lastTick && (
        <Alert
          severity={
            lastTick.action_taken.includes('opened') ? 'success' :
            lastTick.action_taken.includes('closed') ? 'warning' :
            'info'
          }
          sx={{ mb: 2 }}
        >
          <strong>{autoMode ? `Auto-tick #${autoTickCount} :` : 'Dernier tick :'}</strong> {lastTick.detail}
        </Alert>
      )}

      {/* Compte + Métriques */}
      {account && metrics && (
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 1.5,
          mb: 2,
          p: 2,
          bgcolor: 'background.paper',
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
        }}>
          <MetricBox label="Capital" value={`$${account.current_capital.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
          <MetricBox
            label="PnL total"
            value={formatPnl(account.total_pnl, ' $')}
            color={pnlColor(account.total_pnl)}
          />
          <MetricBox
            label="PnL %"
            value={formatPnl(account.total_pnl_pct, '%')}
            color={pnlColor(account.total_pnl_pct)}
          />
          <MetricBox label="Trades" value={`${metrics.total_trades}`} />
          <MetricBox
            label="Win Rate"
            value={`${metrics.win_rate.toFixed(1)}%`}
            color={metrics.win_rate >= 50 ? '#4caf50' : '#f44336'}
          />
          <MetricBox label="Max DD" value={`${metrics.max_drawdown_pct.toFixed(1)}%`} color="#f44336" />
          <MetricBox label="Sharpe" value={metrics.sharpe_ratio?.toFixed(2) ?? '—'} />
          <MetricBox label="Profit Factor" value={metrics.profit_factor.toFixed(2)} />
          <MetricBox
            label="Buy & Hold"
            value={formatPnl(metrics.buy_hold_pnl_pct, '%')}
            color={pnlColor(metrics.buy_hold_pnl_pct)}
          />
          {status?.unrealized_pnl !== null && status?.unrealized_pnl !== undefined && (
            <MetricBox
              label="PnL latent"
              value={formatPnl(status.unrealized_pnl, ' $')}
              color={pnlColor(status.unrealized_pnl)}
            />
          )}
        </Box>
      )}

      {/* Position ouverte */}
      {openPos && (
        <Box sx={{
          mb: 2, p: 2,
          bgcolor: '#1a237e10',
          borderRadius: 2,
          border: '1px solid #42a5f5',
        }}>
          <Stack direction="row" alignItems="center" spacing={1} mb={1}>
            {openPos.direction === 'long' ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
            <Typography fontWeight={700}>
              Position {openPos.direction.toUpperCase()} ouverte
            </Typography>
            {statusChip(openPos.status)}
          </Stack>
          <Typography variant="body2">
            Entrée : <strong>${openPos.entry_price.toLocaleString()}</strong>
            {' | '}SL : <strong style={{ color: '#f44336' }}>${openPos.stop_loss_price.toLocaleString()}</strong>
            {' | '}TP : <strong style={{ color: '#4caf50' }}>${openPos.take_profit_price.toLocaleString()}</strong>
            {' | '}Taille : <strong>${openPos.position_size_usd.toLocaleString()}</strong>
          </Typography>
          <Typography variant="body2" color="text.secondary" mt={0.5}>
            Score : {openPos.decision_score?.toFixed(0) ?? '—'} | {openPos.entry_reason}
          </Typography>
        </Box>
      )}

      <Divider sx={{ my: 2 }} />

      {/* Journal des trades */}
      <Typography variant="subtitle2" mb={1} fontWeight={700}>
        📖 Journal des trades ({trades.length})
      </Typography>

      {trades.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Aucun trade clôturé pour le moment.
        </Typography>
      ) : (
        <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 400 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Status</TableCell>
                <TableCell>Direction</TableCell>
                <TableCell align="right">Entrée</TableCell>
                <TableCell align="right">Sortie</TableCell>
                <TableCell align="right">PnL</TableCell>
                <TableCell align="right">PnL %</TableCell>
                <TableCell align="right">Durée (h)</TableCell>
                <TableCell>Raison</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {trades.map((trade) => (
                <TradeRow key={trade.id} trade={trade} />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

// Sous-composant : boîte de métrique
function MetricBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Box textAlign="center">
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="body1" fontWeight={700} sx={{ color: color || 'text.primary' }}>
        {value}
      </Typography>
    </Box>
  );
}

// Sous-composant : ligne de trade
function TradeRow({ trade }: { trade: PaperTradeItem }) {
  return (
    <TableRow hover>
      <TableCell>{statusChip(trade.status)}</TableCell>
      <TableCell>
        {trade.direction === 'long' ? '📈 Long' : '📉 Short'}
      </TableCell>
      <TableCell align="right">${trade.entry_price.toLocaleString()}</TableCell>
      <TableCell align="right">
        {trade.exit_price ? `$${trade.exit_price.toLocaleString()}` : '—'}
      </TableCell>
      <TableCell align="right" sx={{ color: pnlColor(trade.pnl), fontWeight: 700 }}>
        {formatPnl(trade.pnl, '$')}
      </TableCell>
      <TableCell align="right" sx={{ color: pnlColor(trade.pnl_pct) }}>
        {formatPnl(trade.pnl_pct, '%')}
      </TableCell>
      <TableCell align="right">{trade.duration_hours?.toFixed(1) ?? '—'}</TableCell>
      <TableCell>
        <Tooltip title={trade.exit_reason || trade.entry_reason}>
          <Typography variant="caption" noWrap sx={{ maxWidth: 150, display: 'block' }}>
            {trade.exit_reason || trade.entry_reason}
          </Typography>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
}

