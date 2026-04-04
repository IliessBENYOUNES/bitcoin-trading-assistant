// =============================================================================
// SectionHeader — Premium section divider with icon, title, and gradient line
// =============================================================================

import React from 'react';
import { Box, Typography } from '@mui/material';
import { motion } from 'framer-motion';

interface SectionHeaderProps {
  icon: string;
  title: string;
  subtitle?: string;
  accentColor?: string;
  delay?: number;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  icon,
  title,
  subtitle,
  accentColor = '#F7931A',
  delay = 0,
}) => (
  <motion.div
    initial={{ opacity: 0, x: -20 }}
    whileInView={{ opacity: 1, x: 0 }}
    viewport={{ once: true, margin: '-50px' }}
    transition={{ duration: 0.4, delay }}
  >
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        mb: 2,
        mt: 3,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 32,
          height: 32,
          borderRadius: '8px',
          background: `linear-gradient(135deg, ${accentColor}20, ${accentColor}08)`,
          border: `1px solid ${accentColor}25`,
          flexShrink: 0,
        }}
      >
        <Typography sx={{ fontSize: '0.9rem', lineHeight: 1 }}>{icon}</Typography>
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
        <Typography
          variant="overline"
          sx={{
            fontWeight: 800,
            fontSize: '0.7rem',
            letterSpacing: '0.15em',
            color: 'text.secondary',
            whiteSpace: 'nowrap',
            lineHeight: 1.3,
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography
            variant="caption"
            sx={{
              fontSize: '0.6rem',
              color: `${accentColor}90`,
              fontWeight: 500,
              lineHeight: 1.2,
            }}
          >
            {subtitle}
          </Typography>
        )}
      </Box>
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

