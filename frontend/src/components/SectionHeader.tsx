// =============================================================================
// SectionHeader — Premium section divider with icon, title, and gradient line
// =============================================================================

import React from 'react';
import { Box, Typography } from '@mui/material';
import { motion } from 'framer-motion';

interface SectionHeaderProps {
  icon: string;
  title: string;
  accentColor?: string;
  delay?: number;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  icon,
  title,
  accentColor = '#F7931A',
  delay = 0,
}) => (
  <motion.div
    initial={{ opacity: 0, x: -20 }}
    animate={{ opacity: 1, x: 0 }}
    transition={{ duration: 0.4, delay }}
  >
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        mb: 2,
        mt: 1,
      }}
    >
      <Typography sx={{ fontSize: '1.1rem', lineHeight: 1 }}>{icon}</Typography>
      <Typography
        variant="overline"
        sx={{
          fontWeight: 800,
          fontSize: '0.7rem',
          letterSpacing: '0.15em',
          color: 'text.secondary',
          whiteSpace: 'nowrap',
        }}
      >
        {title}
      </Typography>
      <Box
        sx={{
          flex: 1,
          height: '1px',
          background: `linear-gradient(90deg, ${accentColor}40, transparent)`,
        }}
      />
    </Box>
  </motion.div>
);

export default SectionHeader;

