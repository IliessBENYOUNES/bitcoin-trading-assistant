// =============================================================================
// DecisionPanel - Decision engine display with scenarios, recommendation & rules
// =============================================================================

import React, { useState } from 'react';
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
  Collapse,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  CheckCircle as CheckIcon,
  Cancel as CancelIcon,
  Psychology as PsychologyIcon,
} from '@mui/icons-material';
import { motion } from 'framer-motion';
import type {
  DecisionResponse,
  Scenario,
  RuleResult,
  ActionType,
  SignalDirection,
  ConfidenceLevel,
} from '../types';
import { GlowingCard, ACCENT } from './GlowingCard';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface DecisionPanelProps {
  data: DecisionResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh?: () => void;
  timeframe?: string;
  historyDays?: number;
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function getActionEmoji(action: ActionType): string {
  switch (action) {
    case 'acheter': return '🟢';
    case 'vendre': return '🔴';
    case 'attendre': return '⚪';
    default: return '⚪';
  }
}

function getActionLabel(action: ActionType): string {
  switch (action) {
    case 'acheter': return 'ACHETER';
    case 'vendre': return 'VENDRE';
    case 'attendre': return 'ATTENDRE';
    default: return 'ATTENDRE';
  }
}

function getActionColor(action: ActionType): string {
  switch (action) {
    case 'acheter': return '#00E676';
    case 'vendre': return '#FF1744';
    case 'attendre': return '#6B7280';
    default: return '#6B7280';
  }
}

function getDirectionColor(direction: SignalDirection): string {
  switch (direction) {
    case 'bullish': return '#00E676';
    case 'bearish': return '#FF1744';
    case 'neutral': return '#6B7280';
    default: return '#6B7280';
  }
}

function getConfidenceLabel(confidence: ConfidenceLevel): string {
  switch (confidence) {
    case 'high': return 'Haute';
    case 'medium': return 'Moyenne';
    case 'low': return 'Basse';
    default: return 'Basse';
  }
}

function getConfidenceColor(confidence: ConfidenceLevel): 'success' | 'warning' | 'default' {
  switch (confidence) {
    case 'high': return 'success';
    case 'medium': return 'warning';
    case 'low': return 'default';
    default: return 'default';
  }
}

function getScoreColor(score: number): string {
  if (score > 30) return '#00E676';
  if (score > 10) return '#69F0AE';
  if (score >= -10) return '#6B7280';
  if (score >= -30) return '#FFB74D';
  return '#FF1744';
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

/** Combined Score Gauge — similar to SignalPanel but with dual score display */
const CombinedScoreGauge: React.FC<{
  combinedScore: number;
  technicalScore: number;
  sentimentScore: number;
  sentimentAvailable: boolean;
}> = ({ combinedScore, technicalScore, sentimentScore, sentimentAvailable }) => {
  const color = getScoreColor(combinedScore);
  const angle = (combinedScore / 100) * 90;
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

  return (
    <Box sx={{ textAlign: 'center', py: 1, position: 'relative' }}>
      <svg width="160" height="95" viewBox="0 0 160 95" style={{ display: 'block', margin: '0 auto' }}>
        <path d={bgPath} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="12" strokeLinecap="round" />
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
        <motion.text
          x={cx} y={cx - 12}
          textAnchor="middle"
          fill={color}
          style={{ fontSize: '28px', fontWeight: 800, fontFamily: '"JetBrains Mono", monospace' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
        >
          {combinedScore > 0 ? '+' : ''}{combinedScore}
        </motion.text>
        <text x={cx} y={cx + 4} textAnchor="middle" fill="#6B7280"
          style={{ fontSize: '9px', fontWeight: 600, fontFamily: '"Inter", sans-serif', letterSpacing: '0.1em' }}>
          SCORE COMBINÉ
        </text>
        <text x="4" y={cy + 14} fill="#FF1744" style={{ fontSize: '9px', fontFamily: '"JetBrains Mono", monospace' }}>-100</text>
        <text x="134" y={cy + 14} fill="#00E676" style={{ fontSize: '9px', fontFamily: '"JetBrains Mono", monospace' }}>+100</text>
      </svg>

      {/* Dual score breakdown */}
      <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mt: 0.5 }}>
        <Tooltip title="Score technique (RSI, MACD, SMA, Bollinger) — 70%">
          <Chip
            label={`Tech: ${technicalScore > 0 ? '+' : ''}${technicalScore}`}
            size="small"
            sx={{
              backgroundColor: `${getScoreColor(technicalScore)}15`,
              color: getScoreColor(technicalScore),
              fontWeight: 700,
              fontSize: '0.7rem',
              fontFamily: '"JetBrains Mono", monospace',
            }}
          />
        </Tooltip>
        <Tooltip title={sentimentAvailable ? "Score sentiment des news — 30%" : "Sentiment indisponible (mode dégradé)"}>
          <Chip
            label={sentimentAvailable ? `Sent: ${sentimentScore > 0 ? '+' : ''}${sentimentScore}` : 'Sent: N/A'}
            size="small"
            sx={{
              backgroundColor: sentimentAvailable ? `${getScoreColor(sentimentScore)}15` : 'rgba(255,255,255,0.05)',
              color: sentimentAvailable ? getScoreColor(sentimentScore) : '#6B7280',
              fontWeight: 700,
              fontSize: '0.7rem',
              fontFamily: '"JetBrains Mono", monospace',
            }}
          />
        </Tooltip>
      </Box>
    </Box>
  );
};

/** Scenario bar with animated width */
const ScenarioBar: React.FC<{ scenario: Scenario; isDominant: boolean; index: number }> = ({
  scenario, isDominant, index,
}) => {
  const color = getDirectionColor(scenario.direction);
  const pctLabel = `${Math.round(scenario.probability * 100)}%`;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.1 * index + 0.5, duration: 0.3 }}
    >
      <Tooltip title={scenario.description} placement="left" arrow>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            py: 0.75,
            px: 1,
            borderRadius: 1.5,
            borderLeft: isDominant ? `3px solid ${color}` : '3px solid transparent',
            backgroundColor: isDominant ? `${color}10` : 'transparent',
            transition: 'all 0.2s ease',
            '&:hover': { backgroundColor: `${color}12` },
          }}
        >
          {/* Label */}
          <Typography
            variant="body2"
            fontWeight={isDominant ? 800 : 600}
            sx={{
              fontSize: '0.8rem',
              minWidth: 55,
              color: isDominant ? color : 'text.secondary',
            }}
          >
            {scenario.label}
          </Typography>

          {/* Progress bar */}
          <Box sx={{ flex: 1 }}>
            <LinearProgress
              variant="determinate"
              value={scenario.probability * 100}
              sx={{
                height: isDominant ? 8 : 5,
                borderRadius: 4,
                backgroundColor: 'rgba(255,255,255,0.04)',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: color,
                  borderRadius: 4,
                  boxShadow: isDominant ? `0 0 8px ${color}40` : 'none',
                },
              }}
            />
          </Box>

          {/* Percentage */}
          <Typography
            variant="body2"
            fontWeight={800}
            sx={{
              fontSize: isDominant ? '0.9rem' : '0.75rem',
              fontFamily: '"JetBrains Mono", monospace',
              color: isDominant ? color : 'text.secondary',
              minWidth: 38,
              textAlign: 'right',
            }}
          >
            {pctLabel}
          </Typography>
        </Box>
      </Tooltip>
    </motion.div>
  );
};

/** Recommendation card */
const RecommendationCard: React.FC<{ recommendation: DecisionResponse['recommendation'] }> = ({
  recommendation,
}) => {
  const color = getActionColor(recommendation.action);
  const emoji = getActionEmoji(recommendation.action);
  const label = getActionLabel(recommendation.action);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: 0.8, duration: 0.4 }}
    >
      <Box
        sx={{
          py: 1.5,
          px: 2,
          borderRadius: 2,
          backgroundColor: `${color}08`,
          border: `1px solid ${color}20`,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Glow effect */}
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '2px',
            background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
          }}
        />

        {/* Action + confidence */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Typography sx={{ fontSize: '1.4rem' }}>{emoji}</Typography>
          <Typography
            variant="h6"
            fontWeight={900}
            sx={{
              color,
              fontSize: '1.1rem',
              fontFamily: '"JetBrains Mono", monospace',
              letterSpacing: '0.05em',
            }}
          >
            {label}
          </Typography>
          <Chip
            label={`Confiance: ${getConfidenceLabel(recommendation.confidence)}`}
            size="small"
            color={getConfidenceColor(recommendation.confidence)}
            sx={{ ml: 'auto', fontSize: '0.65rem', height: 22 }}
          />
        </Box>

        {/* Explanation */}
        <Typography
          variant="body2"
          sx={{ fontSize: '0.78rem', lineHeight: 1.6, color: 'text.secondary', mb: 1 }}
        >
          {recommendation.explanation}
        </Typography>

        {/* Reasons */}
        {recommendation.reasons.length > 0 && (
          <Box sx={{ pl: 1 }}>
            {recommendation.reasons.map((reason: string, i: number) => (
              <Typography
                key={i}
                variant="caption"
                sx={{
                  display: 'block',
                  fontSize: '0.7rem',
                  color: 'text.secondary',
                  '&::before': { content: '"• "' },
                  lineHeight: 1.6,
                }}
              >
                {reason}
              </Typography>
            ))}
          </Box>
        )}
      </Box>
    </motion.div>
  );
};

/** Collapsible rules list */
const RulesList: React.FC<{ rules: RuleResult[] }> = ({ rules }) => {
  const [expanded, setExpanded] = useState(false);
  const satisfiedCount = rules.filter(r => r.satisfied).length;

  return (
    <Box>
      <Box
        onClick={() => setExpanded(!expanded)}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          cursor: 'pointer',
          py: 0.5,
          px: 1,
          borderRadius: 1,
          '&:hover': { backgroundColor: 'rgba(255,255,255,0.03)' },
        }}
      >
        <PsychologyIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ fontWeight: 700, letterSpacing: '0.1em', fontSize: '0.6rem', flex: 1 }}
        >
          Règles évaluées ({satisfiedCount}/{rules.length} satisfaites)
        </Typography>
        {expanded ? (
          <ExpandLessIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
        ) : (
          <ExpandMoreIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
        )}
      </Box>

      <Collapse in={expanded}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mt: 0.5, pl: 1 }}>
          {rules.map((rule) => (
            <Box
              key={rule.rule_name}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.75,
                py: 0.25,
                opacity: rule.satisfied ? 1 : 0.5,
              }}
            >
              {rule.satisfied ? (
                <CheckIcon sx={{ fontSize: 14, color: '#00E676' }} />
              ) : (
                <CancelIcon sx={{ fontSize: 14, color: '#6B7280' }} />
              )}
              <Tooltip title={rule.detail} placement="left" arrow>
                <Typography
                  variant="caption"
                  sx={{
                    fontSize: '0.68rem',
                    color: rule.satisfied ? 'text.primary' : 'text.secondary',
                    fontWeight: rule.satisfied ? 600 : 400,
                  }}
                >
                  {rule.condition}
                </Typography>
              </Tooltip>
            </Box>
          ))}
        </Box>
      </Collapse>
    </Box>
  );
};

// -----------------------------------------------------------------------------
// Loading skeleton
// -----------------------------------------------------------------------------

const DecisionPanelSkeleton: React.FC = () => (
  <GlowingCard accentColor={ACCENT.orange.start}>
    <CardHeader
      title={<Skeleton width={180} />}
      subheader={<Skeleton width={120} />}
    />
    <CardContent>
      <Box sx={{ textAlign: 'center', py: 2 }}>
        <Skeleton variant="circular" width={64} height={64} sx={{ mx: 'auto', mb: 1 }} />
        <Skeleton width={100} sx={{ mx: 'auto' }} />
      </Box>
      {[1, 2, 3].map((i) => (
        <Skeleton key={i} variant="rounded" height={32} sx={{ mb: 1, borderRadius: 1.5 }} />
      ))}
      <Skeleton variant="rounded" height={80} sx={{ mt: 2, borderRadius: 2 }} />
    </CardContent>
  </GlowingCard>
);

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const DecisionPanel: React.FC<DecisionPanelProps> = ({
  data,
  loading,
  error,
  onRefresh,
  timeframe = '4h',
  historyDays = 7,
}) => {
  if (loading && !data) return <DecisionPanelSkeleton />;

  if (error) {
    return (
      <GlowingCard accentColor={ACCENT.red.start}>
        <CardHeader
          title="🧠 Décision"
          action={onRefresh && <IconButton onClick={onRefresh} size="small"><RefreshIcon /></IconButton>}
        />
        <CardContent><Alert severity="error">{error}</Alert></CardContent>
      </GlowingCard>
    );
  }

  if (!data) {
    return (
      <GlowingCard accentColor={ACCENT.neutral.start}>
        <CardHeader
          title="🧠 Décision"
          action={onRefresh && <IconButton onClick={onRefresh} size="small"><RefreshIcon /></IconButton>}
        />
        <CardContent>
          <Alert severity="info">Aucune décision disponible. Données insuffisantes ou en cours de chargement.</Alert>
        </CardContent>
      </GlowingCard>
    );
  }

  const { scenarios, rules_evaluated, recommendation, combined_score, technical_score, sentiment_score } = data;
  const sentimentAvailable = data.meta.sentiment_available;
  const actionColor = getActionColor(recommendation.action);

  // Accent color based on recommendation
  const accent = recommendation.action === 'acheter' ? ACCENT.green
    : recommendation.action === 'vendre' ? ACCENT.red
    : ACCENT.neutral;

  return (
    <GlowingCard accentColor={accent.start} accentColorEnd={accent.end} delay={0.05}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6" fontWeight={800} sx={{ fontSize: '1rem' }}>
              🧠 Décision
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
              label={getActionLabel(recommendation.action)}
              size="small"
              sx={{
                backgroundColor: `${actionColor}20`,
                color: actionColor,
                fontWeight: 800,
                fontSize: '0.65rem',
                height: 22,
                letterSpacing: '0.05em',
              }}
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
        {/* Score gauge */}
        <CombinedScoreGauge
          combinedScore={combined_score}
          technicalScore={technical_score}
          sentimentScore={sentiment_score}
          sentimentAvailable={sentimentAvailable}
        />

        <Divider sx={{ my: 1.5 }} />

        {/* Scenarios */}
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ fontWeight: 700, letterSpacing: '0.12em', mb: 0.5, display: 'block', fontSize: '0.6rem' }}
        >
          Scénarios
        </Typography>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25, mb: 2 }}>
          {scenarios.map((scenario: Scenario, index: number) => (
            <ScenarioBar
              key={scenario.label}
              scenario={scenario}
              isDominant={index === 0}
              index={index}
            />
          ))}
        </Box>

        <Divider sx={{ my: 1.5 }} />

        {/* Recommendation */}
        <RecommendationCard recommendation={recommendation} />

        <Divider sx={{ my: 1.5 }} />

        {/* Rules (collapsible) */}
        <RulesList rules={rules_evaluated} />

        {/* Sentiment warning if degraded */}
        {!sentimentAvailable && (
          <Alert severity="warning" sx={{ mt: 1.5, fontSize: '0.7rem' }} variant="outlined">
            Sentiment indisponible — décision basée sur l'analyse technique uniquement.
          </Alert>
        )}
      </CardContent>
    </GlowingCard>
  );
};

export default DecisionPanel;




