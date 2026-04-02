// =============================================================================
// NewsPanel - Panel de news crypto avec analyse de sentiment
// =============================================================================

import React, { useState } from 'react';
import {
  Card,
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
  Newspaper as NewsIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
  OpenInNew as OpenInNewIcon,
} from '@mui/icons-material';
import type {
  NewsResponse,
  NewsItem,
  SentimentType,
  ImpactLevel,
} from '../types';

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
    case 'positive': return <TrendingUpIcon fontSize="small" color="success" />;
    case 'negative': return <TrendingDownIcon fontSize="small" color="error" />;
    case 'neutral': return <TrendingFlatIcon fontSize="small" color="disabled" />;
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
  if (score > 30) return '#4caf50';
  if (score > 10) return '#8bc34a';
  if (score < -30) return '#f44336';
  if (score < -10) return '#ff9800';
  return '#9e9e9e';
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

/** Jauge de sentiment visuelle */
const SentimentGauge: React.FC<{ score: number; sentiment: SentimentType }> = ({
  score,
  sentiment,
}) => {
  // Normaliser le score de -100/+100 vers 0/100 pour la barre
  const normalizedValue = (score + 100) / 2;
  const color = getScoreColor(score);

  return (
    <Box sx={{ mb: 1.5 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          {getSentimentIcon(sentiment)}
          <Typography variant="body2" fontWeight={600}>
            Sentiment global
          </Typography>
        </Box>
        <Typography variant="h6" fontWeight={700} sx={{ color }}>
          {score > 0 ? '+' : ''}{score}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={normalizedValue}
        sx={{
          height: 8,
          borderRadius: 4,
          backgroundColor: '#f4433620',
          '& .MuiLinearProgress-bar': {
            backgroundColor: color,
            borderRadius: 4,
          },
        }}
      />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.25 }}>
        <Typography variant="caption" color="text.secondary">Bearish</Typography>
        <Typography variant="caption" color="text.secondary">Bullish</Typography>
      </Box>
    </Box>
  );
};

/** Ligne d'article individuelle */
const NewsRow: React.FC<{ item: NewsItem }> = ({ item }) => (
  <ListItem
    sx={{
      px: 1,
      py: 0.75,
      borderRadius: 1,
      '&:hover': { backgroundColor: 'action.hover' },
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
                sx={{ fontWeight: 500, fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: 0.5 }}
              >
                <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                  {item.title}
                </Typography>
                <OpenInNewIcon sx={{ fontSize: 12, flexShrink: 0, opacity: 0.5 }} />
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
          <Chip
            label={item.source}
            size="small"
            variant="outlined"
            sx={{ height: 18, fontSize: '0.6rem' }}
          />
          <Chip
            label={getSentimentLabel(item.sentiment)}
            size="small"
            color={getSentimentColor(item.sentiment)}
            sx={{ height: 18, fontSize: '0.6rem' }}
          />
          {item.impact !== 'low' && (
            <Chip
              label={getImpactLabel(item.impact)}
              size="small"
              color={getImpactColor(item.impact)}
              variant="outlined"
              sx={{ height: 18, fontSize: '0.6rem' }}
            />
          )}
          <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
            {formatRelativeDate(item.published_at)}
          </Typography>
        </Box>
      }
    />
  </ListItem>
);

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const NewsPanel: React.FC<NewsPanelProps> = ({
  data,
  loading,
  error,
  onRefresh,
}) => {
  const [expanded, setExpanded] = useState(true);
  const [sentimentFilter, setSentimentFilter] = useState<string>('all');

  const summary = data?.summary;
  const items = data?.items ?? [];

  // Filtrage local
  const filteredItems = sentimentFilter === 'all'
    ? items
    : items.filter(i => i.sentiment === sentimentFilter);

  const handleFilterChange = (e: SelectChangeEvent) => {
    setSentimentFilter(e.target.value);
  };

  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <NewsIcon color="primary" />
            <Typography variant="h6" fontWeight={600}>
              News & Sentiment
            </Typography>
            {summary && (
              <Chip
                label={`${summary.total_articles} article${summary.total_articles > 1 ? 's' : ''}`}
                size="small"
                variant="outlined"
              />
            )}
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', gap: 0.5 }}>
            <IconButton
              size="small"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
            <IconButton size="small" onClick={onRefresh} disabled={loading}>
              <RefreshIcon />
            </IconButton>
          </Box>
        }
      />

      <Collapse in={expanded}>
        <CardContent sx={{ pt: 0 }}>
          {/* Erreur */}
          {error && (
            <MuiAlert severity="error" sx={{ mb: 2 }}>
              {error}
            </MuiAlert>
          )}

          {/* Loading */}
          {loading && !data && (
            <Box sx={{ py: 2 }}>
              <LinearProgress />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block', textAlign: 'center' }}>
                Chargement des news...
              </Typography>
            </Box>
          )}

          {/* Jauge de sentiment */}
          {summary && (
            <SentimentGauge
              score={summary.sentiment_score}
              sentiment={summary.overall_sentiment}
            />
          )}

          {/* Compteurs sentiment */}
          {summary && summary.total_articles > 0 && (
            <Box sx={{ display: 'flex', gap: 1, mb: 1.5, justifyContent: 'center' }}>
              <Chip
                icon={<TrendingUpIcon />}
                label={`${summary.positive_count} positif${summary.positive_count > 1 ? 's' : ''}`}
                size="small"
                sx={{ backgroundColor: '#4caf5020', color: '#4caf50' }}
              />
              <Chip
                label={`${summary.neutral_count} neutre${summary.neutral_count > 1 ? 's' : ''}`}
                size="small"
                variant="outlined"
              />
              <Chip
                icon={<TrendingDownIcon />}
                label={`${summary.negative_count} négatif${summary.negative_count > 1 ? 's' : ''}`}
                size="small"
                sx={{ backgroundColor: '#f4433620', color: '#f44336' }}
              />
            </Box>
          )}

          <Divider sx={{ my: 1 }} />

          {/* Filtre sentiment */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography
              variant="overline"
              color="text.secondary"
              sx={{ fontWeight: 600, letterSpacing: 1 }}
            >
              Dernières news ({filteredItems.length})
            </Typography>
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>Filtre</InputLabel>
              <Select
                value={sentimentFilter}
                label="Filtre"
                onChange={handleFilterChange}
                sx={{ fontSize: '0.75rem' }}
              >
                <MenuItem value="all">Tous</MenuItem>
                <MenuItem value="positive">Positif</MenuItem>
                <MenuItem value="neutral">Neutre</MenuItem>
                <MenuItem value="negative">Négatif</MenuItem>
              </Select>
            </FormControl>
          </Box>

          {/* Liste d'articles */}
          {filteredItems.length === 0 ? (
            <MuiAlert severity="info" variant="outlined" sx={{ mt: 1 }}>
              <Typography variant="caption">
                {items.length === 0
                  ? 'Aucune news disponible pour le moment. Les sources RSS seront consultées automatiquement.'
                  : 'Aucune news correspondant au filtre sélectionné.'}
              </Typography>
            </MuiAlert>
          ) : (
            <List dense disablePadding sx={{ maxHeight: 400, overflow: 'auto' }}>
              {filteredItems.map((item, index) => (
                <NewsRow key={`${item.source}-${index}`} item={item} />
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
                    <Chip
                      label={source}
                      size="small"
                      variant="outlined"
                      sx={{ height: 18, fontSize: '0.6rem' }}
                    />
                  </Tooltip>
                ))}
              </Box>
            </>
          )}
        </CardContent>
      </Collapse>
    </Card>
  );
};

