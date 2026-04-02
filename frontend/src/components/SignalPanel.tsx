// =============================================================================
// SignalPanel - Trading signals display with score gauge and signal list
// =============================================================================

import React from 'react';
import {
  Card,
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
  Speed as SpeedIcon,
} from '@mui/icons-material';
import type { MarketSignalsResponse, SignalItem, SignalDirection, ConfidenceLevel } from '../types';

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
    case 'bullish': return '#4caf50';
    case 'bearish': return '#f44336';
    case 'neutral': return '#9e9e9e';
  }
}

function getDirectionIcon(direction: SignalDirection): React.ReactElement {
  switch (direction) {
    case 'bullish': return <TrendingUpIcon sx={{ color: '#4caf50' }} />;
    case 'bearish': return <TrendingDownIcon sx={{ color: '#f44336' }} />;
    case 'neutral': return <TrendingFlatIcon sx={{ color: '#9e9e9e' }} />;
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

/**
 * Calcule la couleur du score sur le gradient bearish-neutral-bullish.
 * -100 = rouge, 0 = gris, +100 = vert
 */
function getScoreColor(score: number): string {
  if (score > 30) return '#4caf50';
  if (score > 10) return '#8bc34a';
  if (score >= -10) return '#9e9e9e';
  if (score >= -30) return '#ff9800';
  return '#f44336';
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

/** Jauge de score composite */
const ScoreGauge: React.FC<{ score: number; direction: SignalDirection }> = ({ score, direction }) => {
  // Normaliser le score de [-100, 100] à [0, 100] pour la progress bar
  const normalized = (score + 100) / 2;
  const color = getScoreColor(score);

  return (
    <Box sx={{ textAlign: 'center', py: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mb: 1 }}>
        <SpeedIcon sx={{ fontSize: 32, color }} />
        <Typography
          variant="h3"
          fontWeight={700}
          sx={{ fontFamily: 'monospace', color }}
        >
          {score > 0 ? '+' : ''}{score}
        </Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {getDirectionLabel(direction)}
      </Typography>
      <Box sx={{ px: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
          <Typography variant="caption" color="error.main">-100</Typography>
          <Typography variant="caption" color="text.secondary">0</Typography>
          <Typography variant="caption" color="success.main">+100</Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={normalized}
          sx={{
            height: 8,
            borderRadius: 4,
            backgroundColor: '#e0e0e0',
            '& .MuiLinearProgress-bar': {
              backgroundColor: color,
              borderRadius: 4,
            },
          }}
        />
      </Box>
    </Box>
  );
};

/** Ligne de signal individuel */
const SignalRow: React.FC<{ signal: SignalItem }> = ({ signal }) => {
  const strengthPercent = Math.round(signal.strength * 100);

  return (
    <Tooltip title={signal.message} placement="left" arrow>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          py: 1,
          px: 1,
          borderRadius: 1,
          '&:hover': { backgroundColor: 'action.hover' },
        }}
      >
        {getDirectionIcon(signal.direction)}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2" fontWeight={600}>
              {getIndicatorLabel(signal.indicator)}
            </Typography>
            <Chip
              label={getDirectionLabel(signal.direction)}
              size="small"
              sx={{
                backgroundColor: getDirectionColor(signal.direction) + '20',
                color: getDirectionColor(signal.direction),
                fontWeight: 600,
                fontSize: '0.7rem',
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
            }}
          >
            {signal.message}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={strengthPercent}
            sx={{
              mt: 0.5,
              height: 4,
              borderRadius: 2,
              backgroundColor: '#e0e0e0',
              '& .MuiLinearProgress-bar': {
                backgroundColor: getDirectionColor(signal.direction),
                borderRadius: 2,
              },
            }}
          />
        </Box>
      </Box>
    </Tooltip>
  );
};

// -----------------------------------------------------------------------------
// Loading skeleton
// -----------------------------------------------------------------------------

const SignalPanelSkeleton: React.FC = () => (
  <Card sx={{ height: '100%' }}>
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
        <Box key={i} sx={{ mb: 1.5 }}>
          <Skeleton width="100%" height={50} />
        </Box>
      ))}
    </CardContent>
  </Card>
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
  // Loading state
  if (loading && !data) {
    return <SignalPanelSkeleton />;
  }

  // Error state
  if (error) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardHeader
          title="Signaux"
          action={
            onRefresh && (
              <IconButton onClick={onRefresh} size="small">
                <RefreshIcon />
              </IconButton>
            )
          }
        />
        <CardContent>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  // No data state
  if (!data || data.signals.length === 0) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardHeader
          title="Signaux"
          action={
            onRefresh && (
              <IconButton onClick={onRefresh} size="small">
                <RefreshIcon />
              </IconButton>
            )
          }
        />
        <CardContent>
          <Alert severity="info">
            Aucun signal disponible. Données insuffisantes ou en cours de chargement.
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const { signals, composite, summary } = data;

  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            Signaux
            <Chip
              label={`${timeframe} / ${historyDays}j`}
              size="small"
              variant="outlined"
            />
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Chip
              label={`Confiance: ${getConfidenceLabel(composite.confidence)}`}
              size="small"
              color={getConfidenceColor(composite.confidence)}
            />
            <Chip
              label={getConsensusLabel(composite.consensus)}
              size="small"
              variant="outlined"
            />
            {onRefresh && (
              <IconButton onClick={onRefresh} size="small" disabled={loading}>
                <RefreshIcon />
              </IconButton>
            )}
          </Box>
        }
      />

      <CardContent>
        {/* Score composite (jauge) */}
        <ScoreGauge score={composite.score} direction={composite.direction} />

        <Divider sx={{ my: 2 }} />

        {/* Résumé */}
        <Alert
          severity="info"
          variant="outlined"
          sx={{ mb: 2, '& .MuiAlert-message': { width: '100%' } }}
        >
          <Typography variant="body2">{summary}</Typography>
        </Alert>

        {/* Liste des signaux */}
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ fontWeight: 600, letterSpacing: 1, mb: 1, display: 'block' }}
        >
          Détail des signaux ({signals.length})
        </Typography>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          {signals.map((signal, index) => (
            <SignalRow key={`${signal.indicator}-${index}`} signal={signal} />
          ))}
        </Box>

        {/* Compteurs */}
        <Divider sx={{ my: 2 }} />
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2 }}>
          <Chip
            icon={<TrendingUpIcon />}
            label={`${composite.bullish_count} haussier${composite.bullish_count > 1 ? 's' : ''}`}
            size="small"
            sx={{ backgroundColor: '#4caf5020', color: '#4caf50' }}
          />
          <Chip
            icon={<TrendingFlatIcon />}
            label={`${composite.neutral_count} neutre${composite.neutral_count > 1 ? 's' : ''}`}
            size="small"
            variant="outlined"
          />
          <Chip
            icon={<TrendingDownIcon />}
            label={`${composite.bearish_count} baissier${composite.bearish_count > 1 ? 's' : ''}`}
            size="small"
            sx={{ backgroundColor: '#f4433620', color: '#f44336' }}
          />
        </Box>
      </CardContent>
    </Card>
  );
};

export default SignalPanel;

