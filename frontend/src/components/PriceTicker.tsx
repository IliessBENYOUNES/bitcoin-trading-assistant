// =============================================================================
// PriceTicker — Real-time BTC price display with animated number + LIVE badge
// =============================================================================

import React, { useEffect, useRef, useState } from 'react';
import { Box, Typography, Chip } from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';

interface PriceTickerProps {
  price: number | null;
  previousPrice?: number | null;
  loading?: boolean;
}

function formatPrice(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

export const PriceTicker: React.FC<PriceTickerProps> = ({
  price,
  previousPrice,
  loading,
}) => {
  const [flash, setFlash] = useState(false);
  const prevRef = useRef<number | null>(null);

  // Flash effect when price changes
  useEffect(() => {
    if (price !== null && prevRef.current !== null && price !== prevRef.current) {
      setFlash(true);
      const timer = setTimeout(() => setFlash(false), 600);
      return () => clearTimeout(timer);
    }
    prevRef.current = price;
  }, [price]);

  const diff = price && previousPrice ? price - previousPrice : null;
  const diffPercent = price && previousPrice ? ((price - previousPrice) / previousPrice) * 100 : null;
  const isUp = diff !== null && diff >= 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: { xs: 1, sm: 2 },
          flexWrap: 'wrap',
        }}
      >
        {/* LIVE badge */}
        <Chip
          label="LIVE"
          size="small"
          sx={{
            backgroundColor: '#FF174420',
            color: '#FF1744',
            fontWeight: 800,
            fontSize: '0.6rem',
            height: 20,
            letterSpacing: '0.1em',
            '& .MuiChip-label': { px: 1 },
            // Pulse animation
            animation: 'pulse-glow 2s ease-in-out infinite',
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
              key={price}
              initial={{ opacity: 0.6, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
            >
              <Typography
                sx={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontWeight: 800,
                  fontSize: { xs: '1.1rem', sm: '1.3rem' },
                  color: flash ? '#F7931A' : '#E8EAED',
                  transition: 'color 0.3s ease',
                  letterSpacing: '-0.02em',
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

        {/* Change indicator */}
        {diff !== null && diffPercent !== null && (
          <motion.div
            initial={{ opacity: 0, x: -5 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Chip
              label={`${isUp ? '+' : ''}${diffPercent.toFixed(2)}%`}
              size="small"
              sx={{
                backgroundColor: isUp ? '#00E67615' : '#FF174415',
                color: isUp ? '#00E676' : '#FF1744',
                fontWeight: 700,
                fontSize: '0.7rem',
                fontFamily: '"JetBrains Mono", monospace',
                height: 22,
              }}
            />
          </motion.div>
        )}
      </Box>
    </motion.div>
  );
};

export default PriceTicker;

