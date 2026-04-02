// =============================================================================
// SignalPanel - Trading signals display with animated score gauge and signal list
// =============================================================================

import React from 'react';
import {
  CardContent,
  CardHeader,
  Typography,
  Box,
  Chip,
  Skeleton,
  Alert,
  IconButton,
  LinearProgress,
  Divider,
  Tooltip,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
} from '@mui/icons-material';
import { motion } from 'framer-motion';
import type { MarketSignalsResponse, SignalItem, SignalDirection, ConfidenceLevel } from '../types';
import { GlowingCard, ACCENT } from './GlowingCard';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface SignalPanelProps {
  data: MarketSignalsResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh?: () => void;
  timeframe?: string;
  historyDays?: number;
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function getDirectionColor(direction: SignalDirection): string {
  switch (direction) {
    case 'bullish': return '#00E676';
    case 'bearish': return '#FF1744';
    case 'neutral': return '#6B7280';
  }
}

function getDirectionIcon(direction: SignalDirection): React.ReactElement {
  switch (direction) {
    case 'bullish': return <TrendingUpIcon sx={{ color: '#00E676', fontSize: 18 }} />;
    case 'bearish': return <TrendingDownIcon sx={{ color: '#FF1744', fontSize: 18 }} />;
    case 'neutral': return <TrendingFlatIcon sx={{ color: '#6B7280', fontSize: 18 }} />;
  }
}

function getDirectionLabel(direction: SignalDirection): string {
  switch (direction) {
    case 'bullish': return 'Haussier';
    case 'bearish': return 'Baissier';
    case 'neutral': return 'Neutre';
  }
}

function getConfidenceLabel(confidence: ConfidenceLevel): string {
  switch (confidence) {
    case 'high': return 'Haute';
    case 'medium': return 'Moyenne';
    case 'low': return 'Basse';
  }
}

function getConfidenceColor(confidence: ConfidenceLevel): 'success' | 'warning' | 'default' {
  switch (confidence) {
    case 'high': return 'success';
    case 'medium': return 'warning';
    case 'low': return 'default';
  }
}

function getConsensusLabel(consensus: string): string {
  switch (consensus) {
    case 'unanimous': return 'Unanime';
    case 'strong_majority': return 'Forte majorité';
    case 'majority': return 'Majorité';
    case 'divided': return 'Divisé';
    case 'no_data': return 'Pas de données';
    default: return consensus;
  }
}

function getScoreColor(score: number): string {
  if (score > 30) return '#00E676';
  if (score > 10) return '#69F0AE';
  if (score >= -10) return '#6B7280';
  if (score >= -30) return '#FFB74D';
  return '#FF1744';
}

function getIndicatorLabel(indicator: string): string {
  switch (indicator) {
    case 'rsi': return 'RSI (14)';
    case 'macd': return 'MACD';
    case 'sma': return 'SMA';
    case 'bollinger': return 'Bollinger';
    default: return indicator.toUpperCase();
  }
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

/** Animated Score Gauge — SVG half-circle with drawing animation */
const ScoreGauge: React.FC<{ score: number; direction: SignalDirection }> = ({ score, direction }) => {
  const color = getScoreColor(score);
  const angle = (score / 100) * 90;
  const radians = ((angle - 90) * Math.PI) / 180;
  const radius = 70;
  const cx = 80;
  const cy = 80;
  const x = cx + radius * Math.cos(radians);
  const y = cy + radius * Math.sin(radians);
  const bgPath = `M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`;
  const startX = cx - radius;
  const largeArc = angle > 0 ? 1 : 0;
  const fgPath = `M ${startX} ${cy} A ${radius} ${radius} 0 ${largeArc} 1 ${x} ${y}`;

  // Background glow based on direction
  const bgGradient = direction === 'bullish'
    ? 'radial-gradient(ellipse at 50% 100%, rgba(0, 230, 118, 0.08), transparent 70%)'
    : direction === 'bearish'
    ? 'radial-gradient(ellipse at 50% 100%, rgba(255, 23, 68, 0.08), transparent 70%)'
    : 'none';

  return (
    <Box sx={{ textAlign: 'center', py: 1.5, position: 'relative', background: bgGradient, borderRadius: 2 }}>
      <svg width="160" height="95" viewBox="0 0 160 95" style={{ display: 'block', margin: '0 auto' }}>
        {/* Background arc */}
        <path d={bgPath} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="12" strokeLinecap="round" />
        {/* Animated foreground arc */}
        <motion.path
          d={fgPath}
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 10px ${color}80)` }}
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 1.2, ease: 'easeOut', delay: 0.3 }}
        />
        {/* Score text */}
        <motion.text
          x={cx} y={cx - 12}
          textAnchor="middle"
          fill={color}
          style={{ fontSize: '28px', fontWeight: 800, fontFamily: '"JetBrains Mono", monospace' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
        >
          {score > 0 ? '+' : ''}{score}
        </motion.text>
        {/* Direction label */}
        <text x={cx} y={cx + 4} textAnchor="middle" fill="#6B7280"
          style={{ fontSize: '10px', fontWeight: 600, fontFamily: '"Inter", sans-serif', letterSpacing: '0.12em' }}>
          {getDirectionLabel(direction).toUpperCase()}
        </text>
        {/* Min/Max labels */}
        <text x="4" y={cy + 14} fill="#FF1744" style={{ fontSize: '9px', fontFamily: '"JetBrains Mono", monospace' }}>-100</text>
        <text x="134" y={cy + 14} fill="#00E676" style={{ fontSize: '9px', fontFamily: '"JetBrains Mono", monospace' }}>+100</text>
      </svg>
    </Box>
  );
};

/** Signal row with colored left border */
const SignalRow: React.FC<{ signal: SignalItem; index: number }> = ({ signal, index }) => {
  const strengthPercent = Math.round(signal.strength * 100);
  const dirColor = getDirectionColor(signal.direction);

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.1 * index + 0.5, duration: 0.3 }}
    >
      <Tooltip title={signal.message} placement="left" arrow>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            py: 0.75,
            px: 1,
            borderRadius: 1.5,
            borderLeft: `3px solid ${dirColor}`,
            backgroundColor: `${dirColor}08`,
            transition: 'all 0.2s ease',
            '&:hover': {
              backgroundColor: `${dirColor}15`,
              transform: 'translateX(2px)',
            },
          }}
        >
          {getDirectionIcon(signal.direction)}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2" fontWeight={700} sx={{ fontSize: '0.8rem' }}>
                {getIndicatorLabel(signal.indicator)}
              </Typography>
              <Chip
                label={getDirectionLabel(signal.direction)}
                size="small"
                sx={{
                  backgroundColor: `${dirColor}20`,
                  color: dirColor,
                  fontWeight: 700,
                  fontSize: '0.65rem',
                  height: 20,
                }}
              />
            </Box>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                display: 'block',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: '0.7rem',
              }}
            >
              {signal.message}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={strengthPercent}
              sx={{
                mt: 0.5,
                height: 3,
                borderRadius: 2,
                backgroundColor: 'rgba(255,255,255,0.04)',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: dirColor,
                  borderRadius: 2,
                  boxShadow: `0 0 6px ${dirColor}40`,
                },
              }}
            />
          </Box>
        </Box>
      </Tooltip>
    </motion.div>
  );
};

// -----------------------------------------------------------------------------
// Loading skeleton
// -----------------------------------------------------------------------------

const SignalPanelSkeleton: React.FC = () => (
  <GlowingCard accentColor={ACCENT.purple.start}>
    <CardHeader
      title={<Skeleton width={180} />}
      subheader={<Skeleton width={120} />}
    />
    <CardContent>
      <Box sx={{ textAlign: 'center', py: 2 }}>
        <Skeleton variant="circular" width={64} height={64} sx={{ mx: 'auto', mb: 1 }} />
        <Skeleton width={100} sx={{ mx: 'auto' }} />
      </Box>
      {[1, 2, 3, 4].map((i) => (
        <Skeleton key={i} variant="rounded" height={52} sx={{ mb: 1, borderRadius: 1.5 }} className="animate-shimmer" />
      ))}
    </CardContent>
  </GlowingCard>
);

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const SignalPanel: React.FC<SignalPanelProps> = ({
  data,
  loading,
  error,
  onRefresh,
  timeframe = '4h',
  historyDays = 7,
}) => {
  if (loading && !data) return <SignalPanelSkeleton />;

  if (error) {
    return (
      <GlowingCard accentColor={ACCENT.red.start}>
        <CardHeader
          title="⚡ Signaux"
          action={onRefresh && <IconButton onClick={onRefresh} size="small"><RefreshIcon /></IconButton>}
        />
        <CardContent><Alert severity="error">{error}</Alert></CardContent>
      </GlowingCard>
    );
  }

  if (!data || data.signals.length === 0) {
    return (
      <GlowingCard accentColor={ACCENT.neutral.start}>
        <CardHeader
          title="⚡ Signaux"
          action={onRefresh && <IconButton onClick={onRefresh} size="small"><RefreshIcon /></IconButton>}
        />
        <CardContent>
          <Alert severity="info">Aucun signal disponible. Données insuffisantes ou en cours de chargement.</Alert>
        </CardContent>
      </GlowingCard>
    );
  }

  const { signals, composite, summary } = data;
  const scoreColor = getScoreColor(composite.score);

  // Determine accent color based on direction
  const accent = composite.direction === 'bullish' ? ACCENT.green
    : composite.direction === 'bearish' ? ACCENT.red
    : ACCENT.neutral;

  return (
    <GlowingCard accentColor={accent.start} accentColorEnd={accent.end} delay={0.1}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6" fontWeight={800} sx={{ fontSize: '1rem' }}>
              ⚡ Signaux
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
                {timeframe} / {historyDays < 1 ? `${Math.round(historyDays * 24)}h` : historyDays === 365 ? '1an' : `${historyDays}j`}
              </Typography>
            </Box>
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Chip
              label={getConfidenceLabel(composite.confidence)}
              size="small"
              color={getConfidenceColor(composite.confidence)}
              sx={{ height: 22, fontSize: '0.65rem' }}
            />
            <Chip
              label={getConsensusLabel(composite.consensus)}
              size="small"
              variant="outlined"
              sx={{ height: 22, fontSize: '0.65rem' }}
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
        {/* Score composite (animated gauge) */}
        <ScoreGauge score={composite.score} direction={composite.direction} />

        <Divider sx={{ my: 1.5 }} />

        {/* Summary — styled as a quote */}
        <Box
          sx={{
            py: 1,
            px: 1.5,
            borderRadius: 1.5,
            backgroundColor: `${scoreColor}08`,
            borderLeft: `3px solid ${scoreColor}60`,
            mb: 2,
          }}
        >
          <Typography variant="body2" sx={{ fontSize: '0.8rem', lineHeight: 1.5, color: 'text.secondary' }}>
            {summary}
          </Typography>
        </Box>

        {/* Signal list header */}
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ fontWeight: 700, letterSpacing: '0.12em', mb: 1, display: 'block', fontSize: '0.6rem' }}
        >
          Détail des signaux ({signals.length})
        </Typography>

        {/* Signal rows with stagger */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
          {signals.map((signal, index) => (
            <SignalRow key={`${signal.indicator}-${index}`} signal={signal} index={index} />
          ))}
        </Box>

        {/* Counters */}
        <Divider sx={{ my: 1.5 }} />
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1 }}>
          <Chip
            icon={<TrendingUpIcon />}
            label={`${composite.bullish_count} haussier${composite.bullish_count > 1 ? 's' : ''}`}
            size="small"
            sx={{ backgroundColor: '#00E67615', color: '#00E676', fontWeight: 600, fontSize: '0.7rem' }}
          />
          <Chip
            icon={<TrendingFlatIcon />}
            label={`${composite.neutral_count} neutre${composite.neutral_count > 1 ? 's' : ''}`}
            size="small"
            variant="outlined"
            sx={{ fontSize: '0.7rem' }}
          />
          <Chip
            icon={<TrendingDownIcon />}
            label={`${composite.bearish_count} baissier${composite.bearish_count > 1 ? 's' : ''}`}
            size="small"
            sx={{ backgroundColor: '#FF174415', color: '#FF1744', fontWeight: 600, fontSize: '0.7rem' }}
          />
        </Box>
      </CardContent>
    </GlowingCard>
  );
};

export default SignalPanel;

