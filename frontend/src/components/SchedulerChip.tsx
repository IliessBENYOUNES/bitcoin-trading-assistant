// =============================================================================
// SchedulerChip - Visual indicator for scheduler status
// =============================================================================

import React from 'react';
import { Chip, Tooltip, Skeleton, Box } from '@mui/material';
import {
  Schedule as ScheduleIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  PauseCircle as PauseCircleIcon,
} from '@mui/icons-material';
import type { SchedulerStatus } from '../types/api';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface SchedulerChipProps {
  data: SchedulerStatus | null;
  loading: boolean;
  error: string | null;
}

type ChipStatus = 'on' | 'off' | 'error' | 'fetch-error' | 'loading';

interface ChipConfig {
  label: string;
  color: 'success' | 'warning' | 'error' | 'default';
  icon: React.ReactElement;
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function getChipStatus(
  data: SchedulerStatus | null,
  fetchError: string | null
): ChipStatus {
  if (fetchError) return 'fetch-error';
  if (!data) return 'loading';

  // Scheduler disabled
  if (!data.enabled) return 'off';

  // Scheduler enabled but last run failed
  if (data.last_result?.status === 'error') return 'error';

  // Scheduler enabled and running OK
  if (data.running) return 'on';

  // Enabled but not running (edge case)
  return 'off';
}

function getChipConfig(status: ChipStatus): ChipConfig {
  switch (status) {
    case 'on':
      return {
        label: 'SCHEDULER: ON',
        color: 'success',
        icon: <CheckCircleIcon fontSize="small" />,
      };
    case 'off':
      return {
        label: 'SCHEDULER: OFF',
        color: 'default',
        icon: <PauseCircleIcon fontSize="small" />,
      };
    case 'error':
      return {
        label: 'SCHEDULER: ERROR',
        color: 'error',
        icon: <ErrorIcon fontSize="small" />,
      };
    case 'fetch-error':
      return {
        label: 'SCHEDULER: ?',
        color: 'error',
        icon: <ErrorIcon fontSize="small" />,
      };
    case 'loading':
    default:
      return {
        label: 'SCHEDULER: ...',
        color: 'default',
        icon: <ScheduleIcon fontSize="small" />,
      };
  }
}

function formatDate(isoString: string | null): string {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    return date.toLocaleString();
  } catch {
    return isoString;
  }
}

function formatDuration(seconds: number | undefined): string {
  if (seconds === undefined) return '—';
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
  return `${seconds.toFixed(2)}s`;
}

function buildTooltipContent(
  data: SchedulerStatus | null,
  fetchError: string | null
): React.ReactNode {
  if (fetchError) {
    return (
      <Box sx={{ p: 0.5 }}>
        <strong>Connection Error:</strong> {fetchError}
      </Box>
    );
  }

  if (!data) {
    return 'Loading...';
  }

  const { enabled, running, interval_minutes, symbol, days, last_run_time, next_run_time, last_result } = data;

  return (
    <Box sx={{ p: 0.5, fontSize: '0.85rem' }}>
      <Box><strong>Enabled:</strong> {enabled ? 'Yes' : 'No'}</Box>
      <Box><strong>Running:</strong> {running ? 'Yes' : 'No'}</Box>
      
      {enabled && (
        <>
          <Box sx={{ mt: 1 }}>
            <strong>Config:</strong>
            <Box sx={{ pl: 1 }}>
              • Interval: {interval_minutes ?? '—'} min
              <br />
              • Symbol: {symbol ?? '—'}
              <br />
              • Days: {days ?? '—'}
            </Box>
          </Box>

          <Box sx={{ mt: 1 }}>
            <strong>Schedule:</strong>
            <Box sx={{ pl: 1 }}>
              • Last run: {formatDate(last_run_time)}
              <br />
              • Next run: {formatDate(next_run_time)}
            </Box>
          </Box>

          {last_result && (
            <Box sx={{ mt: 1 }}>
              <strong>Last Result:</strong>{' '}
              <Box
                component="span"
                sx={{
                  color: last_result.status === 'success' ? 'success.main' : 'error.main',
                  fontWeight: 600,
                }}
              >
                {last_result.status.toUpperCase()}
              </Box>
              <Box sx={{ pl: 1 }}>
                {last_result.status === 'success' ? (
                  <>
                    • Fetched: {last_result.fetched ?? '—'}
                    <br />
                    • Inserted: {last_result.inserted ?? 0}
                    <br />
                    • Updated: {last_result.updated ?? 0}
                    <br />
                    • Duplicates: {last_result.duplicates ?? 0}
                    <br />
                    • Duration: {formatDuration(last_result.duration_seconds)}
                  </>
                ) : (
                  <>
                    • Error: {last_result.error ?? 'Unknown error'}
                  </>
                )}
              </Box>
            </Box>
          )}
        </>
      )}
    </Box>
  );
}

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

export const SchedulerChip: React.FC<SchedulerChipProps> = ({
  data,
  loading,
  error,
}) => {
  // Show skeleton while loading initially
  if (loading && !data) {
    return <Skeleton variant="rounded" width={140} height={32} />;
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

export default SchedulerChip;
