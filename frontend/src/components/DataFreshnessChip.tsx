// =============================================================================
// DataFreshnessChip - Visual indicator for data quality status
// =============================================================================

import React from 'react';
import { Chip, Tooltip, Skeleton, Box } from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  HelpOutline as HelpIcon,
} from '@mui/icons-material';
import type { MarketGapsResponse } from '../types/api';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface DataFreshnessChipProps {
  data: MarketGapsResponse | null;
  loading: boolean;
  error: string | null;
}

type ChipStatus = 'fresh' | 'stale' | 'gaps' | 'error' | 'loading';

interface ChipConfig {
  label: string;
  color: 'success' | 'warning' | 'error' | 'default';
  icon: React.ReactElement;
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function getChipStatus(data: MarketGapsResponse | null, error: string | null): ChipStatus {
  if (error) return 'error';
  if (!data) return 'loading';

  const { freshness, completeness, global_status } = data;

  // GAPS takes priority (data incomplete)
  if (completeness.status !== 'OK' || global_status === 'GAPS') {
    return 'gaps';
  }

  // STALE (data old but complete)
  if (freshness.status === 'STALE' || freshness.status === 'VERY_STALE' || global_status === 'STALE') {
    return 'stale';
  }

  // FRESH (all good)
  return 'fresh';
}

function getChipConfig(status: ChipStatus): ChipConfig {
  switch (status) {
    case 'fresh':
      return {
        label: 'DATA: FRESH',
        color: 'success',
        icon: <CheckCircleIcon fontSize="small" />,
      };
    case 'stale':
      return {
        label: 'DATA: STALE',
        color: 'warning',
        icon: <WarningIcon fontSize="small" />,
      };
    case 'gaps':
      return {
        label: 'DATA: GAPS',
        color: 'error',
        icon: <ErrorIcon fontSize="small" />,
      };
    case 'error':
      return {
        label: 'DATA: ERROR',
        color: 'error',
        icon: <ErrorIcon fontSize="small" />,
      };
    case 'loading':
    default:
      return {
        label: 'DATA: ...',
        color: 'default',
        icon: <HelpIcon fontSize="small" />,
      };
  }
}

function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleString();
  } catch {
    return isoString;
  }
}

function buildTooltipContent(
  data: MarketGapsResponse | null,
  error: string | null
): React.ReactNode {
  if (error) {
    return (
      <Box sx={{ p: 0.5 }}>
        <strong>Error:</strong> {error}
      </Box>
    );
  }

  if (!data) {
    return 'Loading...';
  }

  const { freshness, completeness, global_status, timeframe, days } = data;

  return (
    <Box sx={{ p: 0.5, fontSize: '0.85rem' }}>
      <Box><strong>Timeframe:</strong> {timeframe} / {days} days</Box>
      <Box><strong>Global Status:</strong> {global_status}</Box>
      <Box sx={{ mt: 1 }}>
        <strong>Freshness:</strong> {freshness.status}
        <Box sx={{ pl: 1 }}>
          • Data lag: {freshness.data_lag_hours.toFixed(2)}h (threshold: {freshness.threshold_hours}h)
          <br />
          • Last candle: {formatDate(freshness.max_ts)}
        </Box>
      </Box>
      <Box sx={{ mt: 1 }}>
        <strong>Completeness:</strong> {completeness.status}
        <Box sx={{ pl: 1 }}>
          • Expected: {completeness.expected_count}
          <br />
          • Actual: {completeness.actual_count}
          <br />
          • Missing: {completeness.missing_count}
        </Box>
      </Box>
      {completeness.missing_count > 0 && completeness.missing_timestamps.length > 0 && (
        <Box sx={{ mt: 1 }}>
          <strong>Missing timestamps:</strong>
          <Box sx={{ pl: 1, maxHeight: 100, overflow: 'auto' }}>
            {completeness.missing_timestamps.slice(0, 5).map((ts, i) => (
              <div key={i}>{formatDate(ts)}</div>
            ))}
            {completeness.missing_timestamps.length > 5 && (
              <div>... +{completeness.missing_timestamps.length - 5} more</div>
            )}
          </Box>
        </Box>
      )}
    </Box>
  );
}

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

export const DataFreshnessChip: React.FC<DataFreshnessChipProps> = ({
  data,
  loading,
  error,
}) => {
  // Show skeleton while loading initially
  if (loading && !data) {
    return <Skeleton variant="rounded" width={120} height={32} />;
  }

  const status = getChipStatus(data, error);
  const config = getChipConfig(status);
  const tooltipContent = buildTooltipContent(data, error);

  return (
    <Tooltip title={tooltipContent} arrow placement="bottom">
      <Chip
        icon={config.icon}
        label={config.label}
        color={config.color}
        size="small"
        variant="filled"
        sx={{
          fontWeight: 600,
          '& .MuiChip-icon': {
            color: 'inherit',
          },
        }}
      />
    </Tooltip>
  );
};

export default DataFreshnessChip;
