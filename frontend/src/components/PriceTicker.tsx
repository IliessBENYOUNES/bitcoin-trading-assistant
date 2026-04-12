// =============================================================================
// PriceTicker — Real-time BTC price display with animated number + LIVE badge
// =============================================================================

import React, { useEffect, useRef, useState } from 'react';
import { Box, Typography, Chip, Tooltip } from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';

interface PriceTickerProps {
  price: number | null;
  previousPrice?: number | null;
  change24h?: number | null;
  high24h?: number | null;
  low24h?: number | null;
  volume24h?: number | null;
  connected?: boolean;
  loading?: boolean;
  source?: 'websocket' | 'rest' | null; // v2.0.15 — source du prix
}

function formatPrice(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

function formatPriceFull(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatVolume(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return value.toFixed(1);
}

export const PriceTicker: React.FC<PriceTickerProps> = ({
  price,
  previousPrice,
  change24h,
  high24h,
  low24h,
  volume24h,
  connected,
  loading,
  source,
}) => {
  const [flash, setFlash] = useState<'up' | 'down' | null>(null);
  const prevRef = useRef<number | null>(previousPrice ?? null);

  // Flash effect when price changes — green for up, red for down
  useEffect(() => {
    if (price !== null && prevRef.current !== null && price !== prevRef.current) {
      setFlash(price > prevRef.current ? 'up' : 'down');
      const timer = setTimeout(() => setFlash(null), 600);
      prevRef.current = price;
      return () => clearTimeout(timer);
    }
    if (price !== null) {
      prevRef.current = price;
    }
  }, [price]);

  const isUp = change24h !== null && change24h !== undefined ? change24h >= 0 : true;

  // Tooltip avec détails 24h
  const tooltipContent = high24h && low24h && volume24h
    ? `24h High: ${formatPriceFull(high24h)}\n24h Low: ${formatPriceFull(low24h)}\nVolume: ${formatVolume(volume24h)} BTC`
    : 'Prix en temps réel via Binance WebSocket';

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
    >
      <Tooltip title={<span style={{ whiteSpace: 'pre-line' }}>{tooltipContent}</span>} arrow>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: { xs: 0.75, sm: 1.5 },
            flexWrap: 'wrap',
          }}
        >
          {/* LIVE badge with connection indicator */}
          <Chip
            label={connected ? 'LIVE' : source === 'rest' ? 'REST' : 'OFFLINE'}
            size="small"
            sx={{
              backgroundColor: connected ? '#FF174420' : source === 'rest' ? '#FF980020' : '#FFFFFF10',
              color: connected ? '#FF1744' : source === 'rest' ? '#FF9800' : '#FFFFFF40',
              fontWeight: 800,
              fontSize: '0.55rem',
              height: 20,
              letterSpacing: '0.1em',
              '& .MuiChip-label': { px: 0.8 },
              // Pulse animation only when connected
              animation: connected ? 'pulse-glow 2s ease-in-out infinite' : source === 'rest' ? 'pulse-glow 3s ease-in-out infinite' : 'none',
              // Connection dot
              '&::before': {
                content: '""',
                display: 'inline-block',
                width: 6,
                height: 6,
                borderRadius: '50%',
                backgroundColor: connected ? '#FF1744' : source === 'rest' ? '#FF9800' : '#FFFFFF30',
                marginRight: 4,
                animation: connected ? 'pulse-dot 1.5s ease-in-out infinite' : source === 'rest' ? 'pulse-dot 2s ease-in-out infinite' : 'none',
              },
            }}
          />

          {/* BTC/USD label */}
          <Typography
            variant="caption"
            sx={{
              color: 'text.secondary',
              fontWeight: 600,
              fontSize: '0.7rem',
              letterSpacing: '0.05em',
            }}
          >
            BTC/USD
          </Typography>

          {/* Price */}
          <AnimatePresence mode="wait">
            {price !== null && !loading ? (
              <motion.div
                key={Math.round(price)}
                initial={{ opacity: 0.6, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.2 }}
              >
                <Typography
                  sx={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontWeight: 800,
                    fontSize: { xs: '1.1rem', sm: '1.3rem' },
                    color: flash === 'up' ? '#00E676'
                         : flash === 'down' ? '#FF1744'
                         : '#E8EAED',
                    transition: 'color 0.3s ease',
                    letterSpacing: '-0.02em',
                    textShadow: flash ? `0 0 12px ${flash === 'up' ? '#00E67640' : '#FF174440'}` : 'none',
                  }}
                >
                  {formatPrice(price)}
                </Typography>
              </motion.div>
            ) : (
              <Typography
                sx={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontWeight: 800,
                  fontSize: { xs: '1.1rem', sm: '1.3rem' },
                  color: 'text.secondary',
                }}
              >
                —
              </Typography>
            )}
          </AnimatePresence>

          {/* 24h Change indicator */}
          {change24h !== null && change24h !== undefined && (
            <motion.div
              initial={{ opacity: 0, x: -5 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
            >
              <Chip
                label={`${isUp ? '▲' : '▼'} ${isUp ? '+' : ''}${change24h.toFixed(2)}%`}
                size="small"
                sx={{
                  backgroundColor: isUp ? '#00E67615' : '#FF174415',
                  color: isUp ? '#00E676' : '#FF1744',
                  fontWeight: 700,
                  fontSize: '0.65rem',
                  fontFamily: '"JetBrains Mono", monospace',
                  height: 22,
                  border: `1px solid ${isUp ? '#00E67620' : '#FF174420'}`,
                }}
              />
            </motion.div>
          )}

          {/* 24h High/Low compact (desktop only) */}
          {high24h && low24h && (
            <Box sx={{ display: { xs: 'none', lg: 'flex' }, gap: 0.5, alignItems: 'center' }}>
              <Typography
                sx={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: '0.6rem',
                  color: '#00E67080',
                  fontWeight: 600,
                }}
              >
                H {formatPrice(high24h)}
              </Typography>
              <Typography sx={{ color: '#FFFFFF15', fontSize: '0.6rem' }}>|</Typography>
              <Typography
                sx={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: '0.6rem',
                  color: '#FF174480',
                  fontWeight: 600,
                }}
              >
                L {formatPrice(low24h)}
              </Typography>
            </Box>
          )}
        </Box>
      </Tooltip>
    </motion.div>
  );
};

export default PriceTicker;

