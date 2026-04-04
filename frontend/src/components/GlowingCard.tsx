// =============================================================================
// GlowingCard — Premium animated card wrapper with gradient top-border & glow
// =============================================================================

import React from 'react';
import { Card, CardProps, Box } from '@mui/material';
import { motion } from 'framer-motion';

export interface GlowingCardProps extends Omit<CardProps, 'ref'> {
  /** Gradient color for the top accent border */
  accentColor?: string;
  /** Secondary gradient color (defaults to accentColor with opacity) */
  accentColorEnd?: string;
  /** Delay for stagger animation (seconds) */
  delay?: number;
  /** Disable entry animation */
  noAnimation?: boolean;
  children: React.ReactNode;
}

// Default gradient presets
export const ACCENT = {
  orange: { start: '#F7931A', end: '#E65100' },
  green: { start: '#00E676', end: '#00C853' },
  red: { start: '#FF1744', end: '#D50000' },
  purple: { start: '#7C4DFF', end: '#6200EA' },
  blue: { start: '#448AFF', end: '#2962FF' },
  neutral: { start: 'rgba(255,255,255,0.15)', end: 'rgba(255,255,255,0.05)' },
} as const;

export const GlowingCard: React.FC<GlowingCardProps> = ({
  accentColor = ACCENT.orange.start,
  accentColorEnd,
  delay = 0,
  noAnimation = false,
  children,
  sx,
  ...rest
}) => {
  const endColor = accentColorEnd ?? `${accentColor}60`;

  const cardSx = {
    position: 'relative' as const,
    height: '100%',
    overflow: 'hidden',
    // Gradient top border
    '&::before': {
      content: '""',
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      height: '2px',
      background: `linear-gradient(90deg, ${accentColor}, ${endColor}, transparent)`,
      zIndex: 1,
    },
    // Enhanced hover glow
    transition: 'border-color 0.3s ease, box-shadow 0.3s ease',
    '&:hover': {
      borderColor: `${accentColor}30`,
      boxShadow: `0 4px 40px ${accentColor}10, 0 0 0 1px ${accentColor}15`,
    },
    ...sx,
  };

  if (noAnimation) {
    return (
      <Card sx={cardSx} {...rest}>
        {children}
      </Card>
    );
  }

  return (
    <Box
      component={motion.div}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      transition={{
        duration: 0.5,
        delay,
        ease: [0.25, 0.46, 0.45, 0.94],
      }}
    >
      <Card sx={cardSx} {...rest}>
        {children}
      </Card>
    </Box>
  );
};

export default GlowingCard;

