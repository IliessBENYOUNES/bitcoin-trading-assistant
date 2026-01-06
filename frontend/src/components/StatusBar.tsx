/**
 * Composant StatusBar : affiche l'état de connexion au backend.
 */

import { Chip, Box } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import CircularProgress from '@mui/material/CircularProgress';

interface StatusBarProps {
  apiStatus: 'loading' | 'connected' | 'error';
  dbStatus: 'loading' | 'connected' | 'error';
}

export default function StatusBar({ apiStatus, dbStatus }: StatusBarProps) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <CheckCircleIcon />;
      case 'error':
        return <ErrorIcon />;
      default:
        return <CircularProgress size={16} />;
    }
  };

  const getStatusColor = (status: string): 'success' | 'error' | 'default' => {
    switch (status) {
      case 'connected':
        return 'success';
      case 'error':
        return 'error';
      default:
        return 'default';
    }
  };

  return (
    <Box sx={{ display: 'flex', gap: 1 }}>
      <Chip
        icon={getStatusIcon(apiStatus)}
        label={`API: ${apiStatus}`}
        color={getStatusColor(apiStatus)}
        size="small"
        variant="outlined"
      />
      <Chip
        icon={getStatusIcon(dbStatus)}
        label={`DB: ${dbStatus}`}
        color={getStatusColor(dbStatus)}
        size="small"
        variant="outlined"
      />
    </Box>
  );
}
