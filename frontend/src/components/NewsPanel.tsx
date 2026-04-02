// =============================================================================
// NewsPanel - Premium news panel with sentiment analysis & animated gauge
// =============================================================================

import React, { useState } from 'react';
import {
  CardContent,
  CardHeader,
  Typography,
  Box,
  Chip,
  IconButton,
  Divider,
  Tooltip,
  Collapse,
  List,
  ListItem,
  ListItemText,
  Link,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert as MuiAlert,
  LinearProgress,
  SelectChangeEvent,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
  OpenInNew as OpenInNewIcon,
} from '@mui/icons-material';
import { motion } from 'framer-motion';
import type {
  NewsResponse,
  NewsItem,
  SentimentType,
  ImpactLevel,
} from '../types';
import { GlowingCard, ACCENT } from './GlowingCard';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface NewsPanelProps {
  data: NewsResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function getSentimentColor(sentiment: SentimentType): 'success' | 'error' | 'default' {
  switch (sentiment) {
    case 'positive': return 'success';
    case 'negative': return 'error';
    case 'neutral': return 'default';
    default: return 'default';
  }
}

function getSentimentLabel(sentiment: SentimentType): string {
  switch (sentiment) {
    case 'positive': return 'Positif';
    case 'negative': return 'Négatif';
    case 'neutral': return 'Neutre';
    default: return sentiment;
  }
}

function getSentimentIcon(sentiment: SentimentType) {
  switch (sentiment) {
    case 'positive': return <TrendingUpIcon fontSize="small" sx={{ color: '#00E676' }} />;
    case 'negative': return <TrendingDownIcon fontSize="small" sx={{ color: '#FF1744' }} />;
    case 'neutral': return <TrendingFlatIcon fontSize="small" sx={{ color: '#6B7280' }} />;
    default: return null;
  }
}

function getImpactColor(impact: ImpactLevel): 'error' | 'warning' | 'default' {
  switch (impact) {
    case 'high': return 'error';
    case 'medium': return 'warning';
    case 'low': return 'default';
    default: return 'default';
  }
}

function getImpactLabel(impact: ImpactLevel): string {
  switch (impact) {
    case 'high': return 'Fort';
    case 'medium': return 'Moyen';
    case 'low': return 'Faible';
    default: return impact;
  }
}

function getScoreColor(score: number): string {
  if (score > 30) return '#00E676';
  if (score > 10) return '#69F0AE';
  if (score < -30) return '#FF1744';
  if (score < -10) return '#FFB74D';
  return '#6B7280';
}

function getSentimentBorderColor(sentiment: SentimentType): string {
  switch (sentiment) {
    case 'positive': return '#00E676';
    case 'negative': return '#FF1744';
    case 'neutral': return 'rgba(255,255,255,0.08)';
    default: return 'rgba(255,255,255,0.08)';
  }
}

function formatRelativeDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMin < 60) return `il y a ${diffMin}min`;
  if (diffHours < 24) return `il y a ${diffHours}h`;
  if (diffDays < 7) return `il y a ${diffDays}j`;
  return date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' });
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

/** Animated Sentiment Gauge — SVG half-circle */
const SentimentGauge: React.FC<{ score: number; sentiment: SentimentType }> = ({ score, sentiment }) => {
  const color = getScoreColor(score);
  const angle = (score / 100) * 90;
  const radians = ((angle - 90) * Math.PI) / 180;
  const radius = 55;
  const cx = 65;
  const cy = 62;
  const x = cx + radius * Math.cos(radians);
  const y = cy + radius * Math.sin(radians);
  const bgPath = `M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`;
  const startX = cx - radius;
  const largeArc = angle > 0 ? 1 : 0;
  const fgPath = `M ${startX} ${cy} A ${radius} ${radius} 0 ${largeArc} 1 ${x} ${y}`;
  const sentimentLabel = sentiment === 'positive' ? 'BULLISH' : sentiment === 'negative' ? 'BEARISH' : 'NEUTRE';

  return (
    <Box sx={{ textAlign: 'center', mb: 1 }}>
      <svg width="130" height="75" viewBox="0 0 130 75" style={{ display: 'block', margin: '0 auto' }}>
        <path d={bgPath} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" strokeLinecap="round" />
        <motion.path
          d={fgPath}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 8px ${color}80)` }}
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 1, ease: 'easeOut', delay: 0.2 }}
        />
        <motion.text
          x={cx} y={cy - 10}
          textAnchor="middle"
          fill={color}
          style={{ fontSize: '22px', fontWeight: 800, fontFamily: '"JetBrains Mono", monospace' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.7 }}
        >
          {score > 0 ? '+' : ''}{score}
        </motion.text>
        <text x={cx} y={cy + 4} textAnchor="middle" fill="#6B7280"
          style={{ fontSize: '8px', fontWeight: 600, fontFamily: '"Inter", sans-serif', letterSpacing: '0.1em' }}>
          {sentimentLabel}
        </text>
        <text x="4" y={cy + 12} fill="#FF1744" style={{ fontSize: '7px', fontFamily: '"JetBrains Mono", monospace' }}>-100</text>
        <text x="108" y={cy + 12} fill="#00E676" style={{ fontSize: '7px', fontFamily: '"JetBrains Mono", monospace' }}>+100</text>
      </svg>
    </Box>
  );
};

/** News row with sentiment timeline border */
const NewsRow: React.FC<{ item: NewsItem; index: number }> = ({ item, index }) => (
  <motion.div
    initial={{ opacity: 0, x: -8 }}
    animate={{ opacity: 1, x: 0 }}
    transition={{ delay: 0.05 * index + 0.3, duration: 0.25 }}
  >
    <ListItem
      sx={{
        px: 1,
        py: 0.75,
        borderRadius: 1.5,
        borderLeft: `3px solid ${getSentimentBorderColor(item.sentiment)}`,
        mb: 0.5,
        transition: 'all 0.2s ease',
        '&:hover': {
          backgroundColor: 'rgba(255,255,255,0.03)',
          transform: 'translateX(2px)',
        },
      }}
      disablePadding
    >
      <ListItemText
        primary={
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.5 }}>
            {getSentimentIcon(item.sentiment)}
            <Box sx={{ flex: 1, minWidth: 0 }}>
              {item.url ? (
                <Link
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  underline="hover"
                  color="text.primary"
                  sx={{ fontWeight: 500, fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: 0.5 }}
                >
                  <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                    {item.title}
                  </Typography>
                  <OpenInNewIcon sx={{ fontSize: 12, flexShrink: 0, opacity: 0.4 }} />
                </Link>
              ) : (
                <Typography variant="body2" fontWeight={500} noWrap>
                  {item.title}
                </Typography>
              )}
            </Box>
          </Box>
        }
        secondary={
          <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mt: 0.25, ml: 3 }}>
            <Chip label={item.source} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
            <Chip label={getSentimentLabel(item.sentiment)} size="small" color={getSentimentColor(item.sentiment)} sx={{ height: 18, fontSize: '0.6rem' }} />
            {item.impact !== 'low' && (
              <Chip label={getImpactLabel(item.impact)} size="small" color={getImpactColor(item.impact)} variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
            )}
            <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto', fontSize: '0.65rem' }}>
              {formatRelativeDate(item.published_at)}
            </Typography>
          </Box>
        }
      />
    </ListItem>
  </motion.div>
);

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const NewsPanel: React.FC<NewsPanelProps> = ({ data, loading, error, onRefresh }) => {
  const [expanded, setExpanded] = useState(true);
  const [sentimentFilter, setSentimentFilter] = useState<string>('all');

  const summary = data?.summary;
  const items = data?.items ?? [];
  const filteredItems = sentimentFilter === 'all' ? items : items.filter(i => i.sentiment === sentimentFilter);
  const handleFilterChange = (e: SelectChangeEvent) => setSentimentFilter(e.target.value);

  // Determine accent color based on sentiment
  const accent = summary
    ? summary.overall_sentiment === 'positive' ? ACCENT.green
      : summary.overall_sentiment === 'negative' ? ACCENT.red
      : ACCENT.neutral
    : ACCENT.neutral;

  return (
    <GlowingCard accentColor={accent.start} accentColorEnd={accent.end} delay={0.2}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6" fontWeight={800} sx={{ fontSize: '1rem' }}>
              📰 News & Sentiment
            </Typography>
            {summary && (
              <Chip
                label={`${summary.total_articles}`}
                size="small"
                variant="outlined"
                sx={{ height: 20, fontSize: '0.65rem', fontWeight: 700 }}
              />
            )}
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', gap: 0.5 }}>
            <IconButton size="small" onClick={() => setExpanded(!expanded)}>
              {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
            <IconButton size="small" onClick={onRefresh} disabled={loading}
              sx={{ '&:hover': { color: '#F7931A' } }}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Box>
        }
      />

      <Collapse in={expanded}>
        <CardContent sx={{ pt: 0 }}>
          {error && <MuiAlert severity="error" sx={{ mb: 2 }}>{error}</MuiAlert>}

          {loading && !data && (
            <Box sx={{ py: 2 }}>
              <LinearProgress sx={{ backgroundColor: 'rgba(255,255,255,0.04)', '& .MuiLinearProgress-bar': { backgroundColor: '#F7931A' } }} />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block', textAlign: 'center' }}>
                Chargement des news...
              </Typography>
            </Box>
          )}

          {/* Animated sentiment gauge */}
          {summary && <SentimentGauge score={summary.sentiment_score} sentiment={summary.overall_sentiment} />}

          {/* Sentiment counters */}
          {summary && summary.total_articles > 0 && (
            <Box sx={{ display: 'flex', gap: 1, mb: 1.5, justifyContent: 'center' }}>
              <Chip icon={<TrendingUpIcon />} label={`${summary.positive_count} positif${summary.positive_count > 1 ? 's' : ''}`}
                size="small" sx={{ backgroundColor: '#00E67615', color: '#00E676', fontWeight: 600, fontSize: '0.7rem' }} />
              <Chip label={`${summary.neutral_count} neutre${summary.neutral_count > 1 ? 's' : ''}`}
                size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
              <Chip icon={<TrendingDownIcon />} label={`${summary.negative_count} négatif${summary.negative_count > 1 ? 's' : ''}`}
                size="small" sx={{ backgroundColor: '#FF174415', color: '#FF1744', fontWeight: 600, fontSize: '0.7rem' }} />
            </Box>
          )}

          <Divider sx={{ my: 1 }} />

          {/* Filter */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="overline" color="text.secondary" sx={{ fontWeight: 700, letterSpacing: '0.1em', fontSize: '0.6rem' }}>
              Dernières news ({filteredItems.length})
            </Typography>
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>Filtre</InputLabel>
              <Select value={sentimentFilter} label="Filtre" onChange={handleFilterChange} sx={{ fontSize: '0.75rem' }}>
                <MenuItem value="all">Tous</MenuItem>
                <MenuItem value="positive">Positif</MenuItem>
                <MenuItem value="neutral">Neutre</MenuItem>
                <MenuItem value="negative">Négatif</MenuItem>
              </Select>
            </FormControl>
          </Box>

          {/* Article list with timeline effect */}
          {filteredItems.length === 0 ? (
            <MuiAlert severity="info" variant="outlined" sx={{ mt: 1 }}>
              <Typography variant="caption">
                {items.length === 0
                  ? 'Aucune news disponible pour le moment.'
                  : 'Aucune news correspondant au filtre sélectionné.'}
              </Typography>
            </MuiAlert>
          ) : (
            <List dense disablePadding sx={{ maxHeight: 400, overflow: 'auto' }}>
              {filteredItems.map((item, index) => (
                <NewsRow key={`${item.source}-${index}`} item={item} index={index} />
              ))}
            </List>
          )}

          {/* Source info */}
          {data?.meta && (
            <>
              <Divider sx={{ my: 1 }} />
              <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.5, flexWrap: 'wrap' }}>
                {(data.meta.sources as string[] | undefined)?.map((source) => (
                  <Tooltip key={source} title={`Source: ${source}`}>
                    <Chip label={source} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
                  </Tooltip>
                ))}
              </Box>
            </>
          )}
        </CardContent>
      </Collapse>
    </GlowingCard>
  );
};

