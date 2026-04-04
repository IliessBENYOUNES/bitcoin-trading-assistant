// =============================================================================
// QuickMetricsBar — Compact horizontal KPI bar (below chart, above analysis)
// Shows key metrics at a glance: Score, Decision, RSI, Sentiment, Signals
// =============================================================================

import React from 'react';
import { Box, Typography, Tooltip, Skeleton } from '@mui/material';
import { motion } from 'framer-motion';
import type {
  DecisionResponse,
  MarketSignalsResponse,
  NewsResponse,
} from '../types';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface QuickMetricsBarProps {
  decision: DecisionResponse | null;
  signals: MarketSignalsResponse | null;
  news: NewsResponse | null;
  loading: boolean;
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function getScoreColor(score: number): string {
  if (score > 30) return '#00E676';
  if (score > 10) return '#69F0AE';
  if (score >= -10) return '#6B7280';
  if (score >= -30) return '#FFB74D';
  return '#FF1744';
}

function getActionColor(action: string): string {
  switch (action) {
    case 'acheter': return '#00E676';
    case 'vendre': return '#FF1744';
    default: return '#6B7280';
  }
}

function getActionLabel(action: string): string {
  switch (action) {
    case 'acheter': return '🟢 ACHETER';
    case 'vendre': return '🔴 VENDRE';
    default: return '⚪ ATTENDRE';
  }
}

function getDirectionColor(direction: string): string {
  switch (direction) {
    case 'bullish': return '#00E676';
    case 'bearish': return '#FF1744';
    default: return '#6B7280';
  }
}

function getDirectionLabel(direction: string): string {
  switch (direction) {
    case 'bullish': return '▲ Haussier';
    case 'bearish': return '▼ Baissier';
    default: return '— Neutre';
  }
}

// -----------------------------------------------------------------------------
// Sub-component: Single metric cell
// -----------------------------------------------------------------------------

const MetricCell: React.FC<{
  label: string;
  value: string;
  color?: string;
  tooltip?: string;
  delay?: number;
}> = ({ label, value, color = '#E8EAED', tooltip, delay = 0 }) => (
  <Tooltip title={tooltip || ''} arrow placement="bottom">
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      style={{ flex: '1 1 0', minWidth: 0 }}
    >
      <Box
        sx={{
          textAlign: 'center',
          py: { xs: 0.75, sm: 1 },
          px: { xs: 0.5, sm: 1.5 },
          borderRight: '1px solid rgba(255,255,255,0.04)',
          '&:last-child': { borderRight: 'none' },
          transition: 'background-color 0.2s ease',
          '&:hover': {
            backgroundColor: 'rgba(255,255,255,0.02)',
          },
        }}
      >
        <Typography
          variant="caption"
          sx={{
            color: 'text.secondary',
            fontSize: { xs: '0.55rem', sm: '0.6rem' },
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            display: 'block',
            mb: 0.25,
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </Typography>
        <Typography
          sx={{
            fontFamily: '"JetBrains Mono", monospace',
            fontWeight: 800,
            fontSize: { xs: '0.8rem', sm: '0.95rem' },
            color,
            whiteSpace: 'nowrap',
            letterSpacing: '-0.02em',
          }}
        >
          {value}
        </Typography>
      </Box>
    </motion.div>
  </Tooltip>
);

// -----------------------------------------------------------------------------
// Skeleton
// -----------------------------------------------------------------------------

const QuickMetricsBarSkeleton: React.FC = () => (
  <Box
    sx={{
      display: 'flex',
      alignItems: 'center',
      p: 1.5,
      borderRadius: 2,
      backgroundColor: 'rgba(17, 24, 39, 0.6)',
      backdropFilter: 'blur(12px)',
      border: '1px solid rgba(255,255,255,0.04)',
    }}
  >
    {[1, 2, 3, 4, 5].map((i) => (
      <Box key={i} sx={{ flex: 1, textAlign: 'center', px: 1 }}>
        <Skeleton width="60%" height={12} sx={{ mx: 'auto', mb: 0.5 }} />
        <Skeleton width="40%" height={20} sx={{ mx: 'auto' }} />
      </Box>
    ))}
  </Box>
);

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const QuickMetricsBar: React.FC<QuickMetricsBarProps> = ({
  decision,
  signals,
  news,
  loading,
}) => {
  if (loading && !decision && !signals) return <QuickMetricsBarSkeleton />;

  const combinedScore = decision?.combined_score ?? 0;
  const action = decision?.recommendation?.action ?? 'attendre';
  const confidence = decision?.recommendation?.confidence ?? 'low';
  const signalDirection = signals?.composite?.direction ?? 'neutral';
  const signalScore = signals?.composite?.score ?? 0;
  const sentimentScore = news?.summary?.sentiment_score ?? null;
  const bullishCount = signals?.composite?.bullish_count ?? 0;
  const bearishCount = signals?.composite?.bearish_count ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'stretch',
          borderRadius: 2,
          backgroundColor: 'rgba(17, 24, 39, 0.5)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(255,255,255,0.04)',
          overflow: 'hidden',
          // Gradient top border
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '1px',
            background: 'linear-gradient(90deg, transparent, rgba(247, 147, 26, 0.3), transparent)',
          },
          position: 'relative',
        }}
      >
        <MetricCell
          label="Décision"
          value={getActionLabel(action)}
          color={getActionColor(action)}
          tooltip={`Confiance: ${confidence}`}
          delay={0.05}
        />
        <MetricCell
          label="Score combiné"
          value={`${combinedScore > 0 ? '+' : ''}${combinedScore}`}
          color={getScoreColor(combinedScore)}
          tooltip="Score combiné technique (70%) + sentiment (30%)"
          delay={0.1}
        />
        <MetricCell
          label="Tendance"
          value={getDirectionLabel(signalDirection)}
          color={getDirectionColor(signalDirection)}
          tooltip={`Score signal: ${signalScore > 0 ? '+' : ''}${signalScore}`}
          delay={0.15}
        />
        <MetricCell
          label="Signaux"
          value={`${bullishCount}▲ ${bearishCount}▼`}
          color={bullishCount > bearishCount ? '#00E676' : bearishCount > bullishCount ? '#FF1744' : '#6B7280'}
          tooltip={`${bullishCount} haussiers, ${bearishCount} baissiers`}
          delay={0.2}
        />
        <MetricCell
          label="Sentiment"
          value={sentimentScore !== null ? `${sentimentScore > 0 ? '+' : ''}${sentimentScore}` : 'N/A'}
          color={sentimentScore !== null ? getScoreColor(sentimentScore) : '#6B7280'}
          tooltip="Score sentiment des news crypto"
          delay={0.25}
        />
      </Box>
    </motion.div>
  );
};

export default QuickMetricsBar;

