// =============================================================================
// StatusRow - Horizontal row of status badges/chips
// =============================================================================

import React from 'react';
import { Box, Divider } from '@mui/material';
import { DataFreshnessChip } from './DataFreshnessChip';
import { SchedulerChip } from './SchedulerChip';
import { useMarketGaps } from '../hooks/useMarketGaps';
import { useSchedulerStatus } from '../hooks/useSchedulerStatus';
import type { MarketGapsResponse, SchedulerStatus } from '../types';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface StatusRowProps {
  // Data freshness
  gapsData: MarketGapsResponse | null;
  gapsLoading: boolean;
  gapsError: string | null;
  
  // Scheduler
  schedulerData: SchedulerStatus | null;
  schedulerLoading: boolean;
  schedulerError: string | null;
  
  // Optional: existing badges to include (API, DB, etc.)
  children?: React.ReactNode;
}

// -----------------------------------------------------------------------------
// Component (controlled version)
// -----------------------------------------------------------------------------

export const StatusRow: React.FC<StatusRowProps> = ({
  gapsData,
  gapsLoading,
  gapsError,
  schedulerData,
  schedulerLoading,
  schedulerError,
  children,
}) => {
  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 1.5,
        p: 1.5,
        backgroundColor: 'background.paper',
        borderRadius: 1,
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      {/* Data Freshness Chip */}
      <DataFreshnessChip
        data={gapsData}
        loading={gapsLoading}
        error={gapsError}
      />

      {/* Scheduler Chip */}
      <SchedulerChip
        data={schedulerData}
        loading={schedulerLoading}
        error={schedulerError}
      />

      {/* Optional: existing badges (API, DB) */}
      {children && (
        <>
          <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
          {children}
        </>
      )}
    </Box>
  );
};

// -----------------------------------------------------------------------------
// Connected version (uses hooks internally)
// -----------------------------------------------------------------------------

export interface StatusRowConnectedProps {
  timeframe: string;
  days: number;
  children?: React.ReactNode;
}

export const StatusRowConnected: React.FC<StatusRowConnectedProps> = ({
  timeframe,
  days,
  children,
}) => {
  const gaps = useMarketGaps({ timeframe, days });
  const scheduler = useSchedulerStatus();

  return (
    <StatusRow
      gapsData={gaps.data}
      gapsLoading={gaps.loading}
      gapsError={gaps.error}
      schedulerData={scheduler.data}
      schedulerLoading={scheduler.loading}
      schedulerError={scheduler.error}
    >
      {children}
    </StatusRow>
  );
};

export default StatusRow;
