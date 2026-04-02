// =============================================================================
// IndicatorPanel — Premium technical indicators with mini-cards & visual bars
// =============================================================================

import React from 'react';
import {
  CardContent,
  CardHeader,
  Typography,
  Box,
  Grid,
  Tooltip,
  Skeleton,
  Alert,
  Chip,
  IconButton,
  LinearProgress,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
} from '@mui/icons-material';
import { motion } from 'framer-motion';
import type { MarketIndicatorsResponse } from '../types';
import { GlowingCard, ACCENT } from './GlowingCard';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface IndicatorPanelProps {
  data: MarketIndicatorsResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh?: () => void;
  timeframe?: string;
  historyDays?: number;
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function formatValue(value: number | null | undefined, decimals: number = 2): string {
  if (value === null || value === undefined) return '—';
  return value.toFixed(decimals);
}

function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatDate(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  try {
    return new Date(isoString).toLocaleString();
  } catch {
    return isoString;
  }
}

function getRsiInterpretation(rsi: number | null): {
  label: string;
  color: string;
  icon: React.ReactElement;
} {
  if (rsi === null) return { label: 'N/A', color: '#6B7280', icon: <TrendingFlatIcon /> };
  if (rsi >= 70) return { label: 'Overbought', color: '#FF1744', icon: <TrendingUpIcon /> };
  if (rsi <= 30) return { label: 'Oversold', color: '#00E676', icon: <TrendingDownIcon /> };
  return { label: 'Neutral', color: '#6B7280', icon: <TrendingFlatIcon /> };
}

function getMacdInterpretation(
  macd: number | null,
  signal: number | null
): { label: string; color: string } {
  if (macd === null || signal === null) return { label: 'N/A', color: '#6B7280' };
  if (macd > signal) return { label: 'Bullish', color: '#00E676' };
  if (macd < signal) return { label: 'Bearish', color: '#FF1744' };
  return { label: 'Neutral', color: '#6B7280' };
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

/** Mini-card for a single indicator section */
const IndicatorMiniCard: React.FC<{
  title: string;
  accentColor: string;
  children: React.ReactNode;
  delay?: number;
}> = ({ title, accentColor, children, delay = 0 }) => (
  <motion.div
    initial={{ opacity: 0, y: 15 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay, duration: 0.4 }}
  >
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        backgroundColor: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(255,255,255,0.05)',
        borderTop: `2px solid ${accentColor}40`,
        transition: 'all 0.2s ease',
        '&:hover': {
          borderColor: `${accentColor}30`,
          backgroundColor: 'rgba(255,255,255,0.03)',
        },
      }}
    >
      <Typography
        variant="overline"
        sx={{
          fontWeight: 800,
          letterSpacing: '0.1em',
          color: accentColor,
          fontSize: '0.6rem',
          display: 'block',
          mb: 1,
        }}
      >
        {title}
      </Typography>
      {children}
    </Box>
  </motion.div>
);

interface IndicatorRowProps {
  label: string;
  value: string;
  tooltip?: string;
  suffix?: string;
  valueColor?: string;
}

const IndicatorRow: React.FC<IndicatorRowProps> = ({ label, value, tooltip, suffix, valueColor }) => {
  const content = (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.3 }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
        {label}
      </Typography>
      <Typography
        variant="body2"
        fontWeight={700}
        color={valueColor ?? 'text.primary'}
        sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.8rem' }}
      >
        {value}
        {suffix && (
          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.3 }}>
            {suffix}
          </Typography>
        )}
      </Typography>
    </Box>
  );

  if (tooltip && value === '—') {
    return <Tooltip title={tooltip} placement="left" arrow>{content}</Tooltip>;
  }
  return content;
};

// -----------------------------------------------------------------------------
// Loading skeleton
// -----------------------------------------------------------------------------

const IndicatorPanelSkeleton: React.FC = () => (
  <GlowingCard accentColor={ACCENT.blue.start}>
    <CardHeader title={<Skeleton width={180} />} subheader={<Skeleton width={120} />} />
    <CardContent>
      <Grid container spacing={1.5}>
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <Grid item xs={12} sm={6} md={4} key={i}>
            <Skeleton variant="rounded" height={120} className="animate-shimmer" sx={{ borderRadius: 2 }} />
          </Grid>
        ))}
      </Grid>
    </CardContent>
  </GlowingCard>
);

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const IndicatorPanel: React.FC<IndicatorPanelProps> = ({
  data,
  loading,
  error,
  onRefresh,
  timeframe = '4h',
  historyDays = 7,
}) => {
  if (loading && !data) return <IndicatorPanelSkeleton />;

  if (error) {
    return (
      <GlowingCard accentColor={ACCENT.red.start}>
        <CardHeader
          title="🔬 Indicateurs"
          action={onRefresh && <IconButton onClick={onRefresh} size="small"><RefreshIcon /></IconButton>}
        />
        <CardContent><Alert severity="error" sx={{ mb: 2 }}>{error}</Alert></CardContent>
      </GlowingCard>
    );
  }

  if (!data || !data.latest) {
    return (
      <GlowingCard accentColor={ACCENT.neutral.start}>
        <CardHeader
          title="🔬 Indicateurs"
          action={onRefresh && <IconButton onClick={onRefresh} size="small"><RefreshIcon /></IconButton>}
        />
        <CardContent>
          <Alert severity="info">Aucune donnée disponible. Lancez une récupération de données.</Alert>
        </CardContent>
      </GlowingCard>
    );
  }

  const { latest, meta } = data;
  const rsiInfo = getRsiInterpretation(latest.rsi_14);
  const macdInfo = getMacdInterpretation(latest.macd, latest.macd_signal);
  const nullTooltip = 'Données insuffisantes (période de warmup)';

  return (
    <GlowingCard accentColor={ACCENT.blue.start} accentColorEnd={ACCENT.blue.end} delay={0.3}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6" fontWeight={800} sx={{ fontSize: '1rem' }}>
              🔬 Indicateurs
            </Typography>
            <Box
              sx={{
                px: 0.8,
                py: 0.2,
                borderRadius: 1,
                backgroundColor: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.65rem', color: 'text.secondary' }}>
                {timeframe} / {historyDays}j
              </Typography>
            </Box>
          </Box>
        }
        subheader={
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
            Dernier point: {formatDate(meta.max_ts)}
          </Typography>
        }
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Chip
              label={meta.global_status}
              size="small"
              color={meta.global_status === 'OK' ? 'success' : meta.global_status === 'STALE' ? 'warning' : 'error'}
              sx={{ height: 22, fontSize: '0.65rem', fontWeight: 700 }}
            />
            {onRefresh && (
              <IconButton onClick={onRefresh} size="small" disabled={loading}
                sx={{ '&:hover': { color: '#F7931A' } }}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            )}
          </Box>
        }
      />

      <CardContent sx={{ pt: 0 }}>
        <Grid container spacing={1.5}>
          {/* PRIX */}
          <Grid item xs={12} sm={6} md={4}>
            <IndicatorMiniCard title="💰 PRIX" accentColor="#F7931A" delay={0.35}>
              <Typography
                sx={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontWeight: 800,
                  fontSize: '1.4rem',
                  color: '#F7931A',
                  textShadow: '0 0 20px rgba(247, 147, 26, 0.2)',
                }}
              >
                {formatPrice(latest.close)}
              </Typography>
            </IndicatorMiniCard>
          </Grid>

          {/* RSI */}
          <Grid item xs={12} sm={6} md={4}>
            <IndicatorMiniCard title="📊 RSI (14)" accentColor={rsiInfo.color} delay={0.4}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography
                  sx={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontWeight: 800,
                    fontSize: '1.3rem',
                    color: rsiInfo.color,
                  }}
                >
                  {formatValue(latest.rsi_14)}
                </Typography>
                <Chip
                  icon={rsiInfo.icon}
                  label={rsiInfo.label}
                  size="small"
                  sx={{
                    backgroundColor: `${rsiInfo.color}15`,
                    color: rsiInfo.color,
                    fontWeight: 700,
                    fontSize: '0.65rem',
                    height: 22,
                  }}
                />
              </Box>
              {/* RSI visual bar 0-100 */}
              {latest.rsi_14 !== null && (
                <Box sx={{ position: 'relative', mt: 0.5 }}>
                  <LinearProgress
                    variant="determinate"
                    value={latest.rsi_14}
                    sx={{
                      height: 6,
                      borderRadius: 3,
                      backgroundColor: 'rgba(255,255,255,0.04)',
                      '& .MuiLinearProgress-bar': {
                        borderRadius: 3,
                        background: `linear-gradient(90deg, #00E676, #FFD600 50%, #FF1744)`,
                        boxShadow: `0 0 8px ${rsiInfo.color}40`,
                      },
                    }}
                  />
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.25 }}>
                    <Typography variant="caption" sx={{ fontSize: '0.55rem', color: '#00E676' }}>0</Typography>
                    <Typography variant="caption" sx={{ fontSize: '0.55rem', color: '#6B7280' }}>30</Typography>
                    <Typography variant="caption" sx={{ fontSize: '0.55rem', color: '#6B7280' }}>70</Typography>
                    <Typography variant="caption" sx={{ fontSize: '0.55rem', color: '#FF1744' }}>100</Typography>
                  </Box>
                </Box>
              )}
            </IndicatorMiniCard>
          </Grid>

          {/* MACD */}
          <Grid item xs={12} sm={6} md={4}>
            <IndicatorMiniCard title="📈 MACD (12, 26, 9)" accentColor={macdInfo.color} delay={0.45}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography
                  sx={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontWeight: 800,
                    fontSize: '1.1rem',
                    color: macdInfo.color,
                  }}
                >
                  {formatValue(latest.macd)}
                </Typography>
                <Chip
                  label={macdInfo.label}
                  size="small"
                  sx={{
                    backgroundColor: `${macdInfo.color}15`,
                    color: macdInfo.color,
                    fontWeight: 700,
                    fontSize: '0.65rem',
                    height: 22,
                  }}
                />
              </Box>
              <IndicatorRow label="Signal" value={formatValue(latest.macd_signal)} tooltip={nullTooltip} />
              <IndicatorRow
                label="Histogram"
                value={formatValue(latest.macd_hist)}
                tooltip={nullTooltip}
                valueColor={latest.macd_hist !== null ? (latest.macd_hist >= 0 ? '#00E676' : '#FF1744') : undefined}
              />
            </IndicatorMiniCard>
          </Grid>

          {/* SMA */}
          <Grid item xs={12} sm={6} md={4}>
            <IndicatorMiniCard title="〰️ SMA" accentColor="#7C4DFF" delay={0.5}>
              <IndicatorRow label="SMA 20" value={formatPrice(latest.sma_20)} tooltip={nullTooltip} />
              <IndicatorRow label="SMA 50" value={formatPrice(latest.sma_50)} tooltip={nullTooltip} />
              <IndicatorRow label="SMA 200" value={formatPrice(latest.sma_200)} tooltip={nullTooltip} />
            </IndicatorMiniCard>
          </Grid>

          {/* Bollinger */}
          <Grid item xs={12} sm={6} md={4}>
            <IndicatorMiniCard title="📐 BOLLINGER (20, 2)" accentColor="#FFD600" delay={0.55}>
              <IndicatorRow label="Upper" value={formatPrice(latest.bb_upper)} tooltip={nullTooltip} valueColor="#FF174490" />
              <IndicatorRow label="Middle" value={formatPrice(latest.bb_mid)} tooltip={nullTooltip} />
              <IndicatorRow label="Lower" value={formatPrice(latest.bb_lower)} tooltip={nullTooltip} valueColor="#00E67690" />
            </IndicatorMiniCard>
          </Grid>

          {/* Qualité données */}
          <Grid item xs={12} sm={6} md={4}>
            <IndicatorMiniCard title="🔍 QUALITÉ DONNÉES" accentColor="#448AFF" delay={0.6}>
              <IndicatorRow label="Data lag" value={formatValue(meta.data_lag_hours)} suffix="h" />
              <IndicatorRow label="Points" value={`${meta.count} / ${meta.expected_count}`} />
              <IndicatorRow
                label="Manquants"
                value={String(meta.missing_count)}
                valueColor={meta.missing_count > 0 ? '#FF1744' : '#00E676'}
              />
            </IndicatorMiniCard>
          </Grid>
        </Grid>
      </CardContent>
    </GlowingCard>
  );
};

export default IndicatorPanel;
