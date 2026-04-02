// =============================================================================
// IndicatorPanel - Technical indicators display card
// =============================================================================

import React from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Box,
  Grid,
  Tooltip,
  Skeleton,
  Alert,
  Chip,
  Divider,
  IconButton,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
} from '@mui/icons-material';
import type { MarketIndicatorsResponse } from '../types';

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

function formatValue(
  value: number | null | undefined,
  decimals: number = 2
): string {
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
  if (rsi === null) {
    return { label: 'N/A', color: 'text.secondary', icon: <TrendingFlatIcon /> };
  }
  if (rsi >= 70) {
    return { label: 'Overbought', color: 'error.main', icon: <TrendingUpIcon /> };
  }
  if (rsi <= 30) {
    return { label: 'Oversold', color: 'success.main', icon: <TrendingDownIcon /> };
  }
  return { label: 'Neutral', color: 'text.secondary', icon: <TrendingFlatIcon /> };
}

function getMacdInterpretation(
  macd: number | null,
  signal: number | null
): { label: string; color: string } {
  if (macd === null || signal === null) {
    return { label: 'N/A', color: 'text.secondary' };
  }
  if (macd > signal) {
    return { label: 'Bullish', color: 'success.main' };
  }
  if (macd < signal) {
    return { label: 'Bearish', color: 'error.main' };
  }
  return { label: 'Neutral', color: 'text.secondary' };
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

interface IndicatorRowProps {
  label: string;
  value: string;
  tooltip?: string;
  suffix?: string;
  valueColor?: string;
}

const IndicatorRow: React.FC<IndicatorRowProps> = ({
  label,
  value,
  tooltip,
  suffix,
  valueColor,
}) => {
  const content = (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        py: 0.5,
      }}
    >
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography
        variant="body2"
        fontWeight={600}
        color={valueColor ?? 'text.primary'}
        sx={{ fontFamily: 'monospace' }}
      >
        {value}
        {suffix && (
          <Typography component="span" variant="caption" color="text.secondary">
            {' '}{suffix}
          </Typography>
        )}
      </Typography>
    </Box>
  );

  if (tooltip && value === '—') {
    return (
      <Tooltip title={tooltip} placement="left" arrow>
        {content}
      </Tooltip>
    );
  }

  return content;
};

interface IndicatorSectionProps {
  title: string;
  children: React.ReactNode;
}

const IndicatorSection: React.FC<IndicatorSectionProps> = ({ title, children }) => (
  <Box sx={{ mb: 2 }}>
    <Typography
      variant="overline"
      color="text.secondary"
      sx={{ fontWeight: 600, letterSpacing: 1 }}
    >
      {title}
    </Typography>
    <Box sx={{ mt: 0.5 }}>{children}</Box>
  </Box>
);

// -----------------------------------------------------------------------------
// Loading skeleton
// -----------------------------------------------------------------------------

const IndicatorPanelSkeleton: React.FC = () => (
  <Card sx={{ height: '100%' }}>
    <CardHeader
      title={<Skeleton width={180} />}
      subheader={<Skeleton width={120} />}
    />
    <CardContent>
      {[1, 2, 3, 4].map((i) => (
        <Box key={i} sx={{ mb: 2 }}>
          <Skeleton width={80} height={16} sx={{ mb: 1 }} />
          <Skeleton width="100%" height={24} />
          <Skeleton width="100%" height={24} />
        </Box>
      ))}
    </CardContent>
  </Card>
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
  // Loading state
  if (loading && !data) {
    return <IndicatorPanelSkeleton />;
  }

  // Error state
  if (error) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardHeader
          title="Indicateurs"
          action={
            onRefresh && (
              <IconButton onClick={onRefresh} size="small">
                <RefreshIcon />
              </IconButton>
            )
          }
        />
        <CardContent>
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  // No data state
  if (!data || !data.latest) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardHeader
          title="Indicateurs"
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
            Aucune donnée disponible. Lancez une récupération de données.
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const { latest, meta } = data;
  const rsiInfo = getRsiInterpretation(latest.rsi_14);
  const macdInfo = getMacdInterpretation(latest.macd, latest.macd_signal);
  const nullTooltip = 'Données insuffisantes (période de warmup)';

  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            Indicateurs
            <Chip
              label={`${timeframe} / ${historyDays}j`}
              size="small"
              variant="outlined"
            />
          </Box>
        }
        subheader={`Dernier point: ${formatDate(meta.max_ts)}`}
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Chip
              label={meta.global_status}
              size="small"
              color={
                meta.global_status === 'OK'
                  ? 'success'
                  : meta.global_status === 'STALE'
                  ? 'warning'
                  : 'error'
              }
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
        <Grid container spacing={2}>
          {/* Colonne gauche */}
          <Grid item xs={12} md={6}>
            {/* Prix */}
            <IndicatorSection title="Prix">
              <IndicatorRow
                label="Close"
                value={formatPrice(latest.close)}
              />
            </IndicatorSection>

            {/* RSI */}
            <IndicatorSection title="RSI (14)">
              <IndicatorRow
                label="Valeur"
                value={formatValue(latest.rsi_14)}
                tooltip={nullTooltip}
              />
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5,
                  mt: 0.5,
                }}
              >
                <Box sx={{ color: rsiInfo.color }}>{rsiInfo.icon}</Box>
                <Typography variant="body2" color={rsiInfo.color}>
                  {rsiInfo.label}
                </Typography>
              </Box>
            </IndicatorSection>

            {/* MACD */}
            <IndicatorSection title="MACD (12, 26, 9)">
              <IndicatorRow
                label="MACD"
                value={formatValue(latest.macd)}
                tooltip={nullTooltip}
              />
              <IndicatorRow
                label="Signal"
                value={formatValue(latest.macd_signal)}
                tooltip={nullTooltip}
              />
              <IndicatorRow
                label="Histogram"
                value={formatValue(latest.macd_hist)}
                tooltip={nullTooltip}
                valueColor={
                  latest.macd_hist !== null
                    ? latest.macd_hist >= 0
                      ? 'success.main'
                      : 'error.main'
                    : undefined
                }
              />
              <Box sx={{ mt: 0.5 }}>
                <Typography variant="body2" color={macdInfo.color}>
                  {macdInfo.label}
                </Typography>
              </Box>
            </IndicatorSection>
          </Grid>

          {/* Colonne droite */}
          <Grid item xs={12} md={6}>
            {/* SMA */}
            <IndicatorSection title="SMA">
              <IndicatorRow
                label="SMA 20"
                value={formatPrice(latest.sma_20)}
                tooltip={nullTooltip}
              />
              <IndicatorRow
                label="SMA 50"
                value={formatPrice(latest.sma_50)}
                tooltip={nullTooltip}
              />
              <IndicatorRow
                label="SMA 200"
                value={formatPrice(latest.sma_200)}
                tooltip={nullTooltip}
              />
            </IndicatorSection>

            {/* Bollinger */}
            <IndicatorSection title="Bollinger (20, 2)">
              <IndicatorRow
                label="Upper"
                value={formatPrice(latest.bb_upper)}
                tooltip={nullTooltip}
              />
              <IndicatorRow
                label="Middle"
                value={formatPrice(latest.bb_mid)}
                tooltip={nullTooltip}
              />
              <IndicatorRow
                label="Lower"
                value={formatPrice(latest.bb_lower)}
                tooltip={nullTooltip}
              />
            </IndicatorSection>

            {/* Meta / Status */}
            <Divider sx={{ my: 1 }} />
            <IndicatorSection title="Qualité données">
              <IndicatorRow
                label="Data lag"
                value={formatValue(meta.data_lag_hours)}
                suffix="h"
              />
              <IndicatorRow
                label="Points"
                value={`${meta.count} / ${meta.expected_count}`}
              />
              <IndicatorRow
                label="Manquants"
                value={String(meta.missing_count)}
                valueColor={meta.missing_count > 0 ? 'error.main' : 'success.main'}
              />
            </IndicatorSection>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

export default IndicatorPanel;
