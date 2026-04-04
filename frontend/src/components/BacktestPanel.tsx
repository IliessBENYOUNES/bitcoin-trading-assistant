// =============================================================================
// BacktestPanel.tsx — Backtesting UI with metrics, trades list, equity curve
// =============================================================================

import React, { useState } from 'react';
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
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  Warning as WarningIcon,
  TrendingUp as TrendUpIcon,
  TrendingDown as TrendDownIcon,
} from '@mui/icons-material';

import { GlowingCard, ACCENT } from './GlowingCard';
import type { BacktestResponse, BacktestTradeItem } from '../types';

// -----------------------------------------------------------------------------
// Props
// -----------------------------------------------------------------------------

export interface BacktestPanelProps {
  data: BacktestResponse | null;
  loading: boolean;
  error: string | null;
  onLaunch: (config: { timeframe: string; start_days_ago: number; initial_capital: number }) => void;
  timeframe: string;
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

const MetricCard: React.FC<{
  label: string;
  value: string;
  color?: string;
  tooltip?: string;
}> = ({ label, value, color, tooltip }) => (
  <Tooltip title={tooltip || ''} arrow>
    <Box
      sx={{
        textAlign: 'center',
        p: 1,
        borderRadius: 1,
        bgcolor: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.06)',
        minWidth: 80,
        flex: '1 1 80px',
      }}
    >
      <Typography
        variant="caption"
        sx={{ color: 'text.secondary', fontSize: '0.65rem', textTransform: 'uppercase' }}
      >
        {label}
      </Typography>
      <Typography
        variant="body1"
        sx={{
          fontFamily: '"JetBrains Mono", monospace',
          fontWeight: 700,
          fontSize: '0.95rem',
          color: color || 'text.primary',
        }}
      >
        {value}
      </Typography>
    </Box>
  </Tooltip>
);

const pnlColor = (val: number) => (val > 0 ? '#00E676' : val < 0 ? '#FF1744' : 'text.secondary');

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const BacktestPanel: React.FC<BacktestPanelProps> = ({
  data,
  loading,
  error,
  onLaunch,
  timeframe,
}) => {
  const [daysAgo, setDaysAgo] = useState<number>(30);
  const [capital, setCapital] = useState<number>(10000);
  const [showTrades, setShowTrades] = useState(false);

  const handleLaunch = () => {
    onLaunch({
      timeframe,
      start_days_ago: daysAgo,
      initial_capital: capital,
    });
  };

  const metrics = data?.metrics;
  const trades = data?.trades || [];

  return (
    <GlowingCard accentColor={ACCENT.purple.start} accentColorEnd={ACCENT.purple.end} delay={0.15}>
      <CardContent sx={{ p: 2 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ fontSize: '0.95rem' }}>
            Backtesting
          </Typography>
          <Chip
            label={data ? `${metrics?.total_trades || 0} trades` : 'Pret'}
            size="small"
            color={data ? 'primary' : 'default'}
            variant="outlined"
            sx={{ fontSize: '0.7rem' }}
          />
        </Box>

        {/* Config Form */}
        <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
          <TextField
            label="Jours"
            type="number"
            size="small"
            value={daysAgo}
            onChange={(e) => setDaysAgo(Math.max(1, Math.min(365, Number(e.target.value))))}
            inputProps={{ min: 1, max: 365, step: 1 }}
            sx={{ width: 90, '& input': { fontFamily: '"JetBrains Mono", monospace', fontSize: '0.85rem' } }}
          />
          <TextField
            label="Capital $"
            type="number"
            size="small"
            value={capital}
            onChange={(e) => setCapital(Math.max(100, Number(e.target.value)))}
            inputProps={{ min: 100, step: 1000 }}
            sx={{ width: 110, '& input': { fontFamily: '"JetBrains Mono", monospace', fontSize: '0.85rem' } }}
          />
          <Button
            variant="contained"
            size="small"
            startIcon={loading ? <CircularProgress size={16} /> : <PlayIcon />}
            onClick={handleLaunch}
            disabled={loading}
            sx={{
              background: 'linear-gradient(135deg, #7C4DFF 0%, #6200EA 100%)',
              '&:hover': { background: 'linear-gradient(135deg, #B388FF 0%, #7C4DFF 100%)' },
              fontWeight: 700,
              fontSize: '0.78rem',
              px: 2,
              minWidth: 90,
            }}
          >
            {loading ? 'En cours...' : 'Lancer'}
          </Button>
        </Stack>

        {/* Error */}
        {error && (
          <Alert severity="error" sx={{ mb: 1.5, fontSize: '0.8rem' }}>
            {error}
          </Alert>
        )}

        {/* Loading bar */}
        {loading && <LinearProgress sx={{ mb: 1.5, borderRadius: 1 }} color="secondary" />}

        {/* Results */}
        {data && metrics && (
          <>
            {/* Summary */}
            <Typography
              variant="body2"
              sx={{
                mb: 1.5,
                p: 1,
                borderRadius: 1,
                bgcolor: 'rgba(124, 77, 255, 0.08)',
                border: '1px solid rgba(124, 77, 255, 0.15)',
                fontSize: '0.78rem',
                fontFamily: '"JetBrains Mono", monospace',
              }}
            >
              {data.summary}
            </Typography>

            {/* Overfitting warning */}
            {metrics.overfitting_warning && (
              <Alert severity="warning" icon={<WarningIcon />} sx={{ mb: 1.5, fontSize: '0.75rem' }}>
                Risque de suroptimisation (peu de trades ou Sharpe anormalement eleve)
              </Alert>
            )}

            {/* Key Metrics Grid */}
            <Stack direction="row" flexWrap="wrap" gap={0.8} sx={{ mb: 1.5 }}>
              <MetricCard
                label="PnL"
                value={`${metrics.net_pnl_pct >= 0 ? '+' : ''}${metrics.net_pnl_pct.toFixed(1)}%`}
                color={pnlColor(metrics.net_pnl_pct)}
                tooltip={`${metrics.net_pnl >= 0 ? '+' : ''}$${metrics.net_pnl.toFixed(0)}`}
              />
              <MetricCard
                label="Win Rate"
                value={`${(metrics.win_rate * 100).toFixed(0)}%`}
                color={metrics.win_rate >= 0.5 ? '#00E676' : '#FF1744'}
                tooltip={`${metrics.winning_trades}W / ${metrics.losing_trades}L`}
              />
              <MetricCard
                label="Max DD"
                value={`${metrics.max_drawdown_pct.toFixed(1)}%`}
                color={metrics.max_drawdown_pct > 10 ? '#FF1744' : '#FFB74D'}
                tooltip="Drawdown maximum"
              />
              <MetricCard
                label="Sharpe"
                value={metrics.sharpe_ratio.toFixed(2)}
                color={metrics.sharpe_ratio > 1 ? '#00E676' : metrics.sharpe_ratio > 0 ? '#FFB74D' : '#FF1744'}
                tooltip="Ratio rendement/risque"
              />
              <MetricCard
                label="Profit F."
                value={metrics.profit_factor >= 999 ? 'Inf' : metrics.profit_factor.toFixed(1)}
                color={metrics.profit_factor > 1.5 ? '#00E676' : '#FFB74D'}
                tooltip="Gains bruts / Pertes brutes"
              />
              <MetricCard
                label="B&H"
                value={`${metrics.buy_and_hold_pnl_pct >= 0 ? '+' : ''}${metrics.buy_and_hold_pnl_pct.toFixed(1)}%`}
                color={pnlColor(metrics.buy_and_hold_pnl_pct)}
                tooltip="Benchmark Buy & Hold"
              />
            </Stack>

            {/* Meta info */}
            <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 1 }}>
              <Chip label={`${data.meta.candles_analyzed} candles`} size="small" variant="outlined" sx={{ fontSize: '0.65rem' }} />
              <Chip label={`${data.meta.decisions_made} decisions`} size="small" variant="outlined" sx={{ fontSize: '0.65rem' }} />
              <Chip label={`${data.meta.duration_seconds.toFixed(1)}s`} size="small" variant="outlined" sx={{ fontSize: '0.65rem' }} />
            </Stack>

            {/* Trades list (collapsible) */}
            {trades.length > 0 && (
              <>
                <Divider sx={{ my: 1 }} />
                <Box
                  onClick={() => setShowTrades(!showTrades)}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    cursor: 'pointer',
                    '&:hover': { opacity: 0.8 },
                  }}
                >
                  <Typography variant="caption" fontWeight={600} sx={{ flex: 1 }}>
                    Journal des trades ({trades.length})
                  </Typography>
                  <IconButton size="small">
                    {showTrades ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
                  </IconButton>
                </Box>
                <Collapse in={showTrades}>
                  <Box sx={{ maxHeight: 250, overflow: 'auto', mt: 0.5 }}>
                    {trades.map((t: BacktestTradeItem, i: number) => (
                      <Box
                        key={i}
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1,
                          p: 0.8,
                          mb: 0.5,
                          borderRadius: 1,
                          bgcolor: 'rgba(255,255,255,0.02)',
                          border: '1px solid rgba(255,255,255,0.04)',
                          fontSize: '0.72rem',
                        }}
                      >
                        <Box sx={{ display: 'flex', alignItems: 'center', minWidth: 20 }}>
                          {t.pnl >= 0 ? (
                            <TrendUpIcon sx={{ fontSize: 16, color: '#00E676' }} />
                          ) : (
                            <TrendDownIcon sx={{ fontSize: 16, color: '#FF1744' }} />
                          )}
                        </Box>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography
                            variant="caption"
                            sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.7rem' }}
                          >
                            ${t.entry_price.toLocaleString()} → ${t.exit_price?.toLocaleString() ?? '?'}
                          </Typography>
                          <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary', fontSize: '0.6rem' }}>
                            {t.duration_hours.toFixed(0)}h
                          </Typography>
                        </Box>
                        <Typography
                          variant="caption"
                          sx={{
                            fontFamily: '"JetBrains Mono", monospace',
                            fontWeight: 700,
                            color: pnlColor(t.pnl),
                            fontSize: '0.75rem',
                          }}
                        >
                          {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(1)}%
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Collapse>
              </>
            )}
          </>
        )}

        {/* Empty state */}
        {!data && !loading && !error && (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 2, fontSize: '0.8rem' }}>
            Configurez et lancez un backtest pour voir les resultats
          </Typography>
        )}
      </CardContent>
    </GlowingCard>
  );
};

export default BacktestPanel;



