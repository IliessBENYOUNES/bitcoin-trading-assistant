/**
 * Composant racine de l'application.
 * Thème premium dark optimisé pour le trading crypto.
 */

import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import Dashboard from './pages/Dashboard';

// ═══════════════════════════════════════════════════════════════════════════════
// THÈME PREMIUM — Dark Trading UI
// Couleurs : BTC Orange (#F7931A), Vert trading (#00E676), Rouge trading (#FF1744)
// Glassmorphism : backdrop-filter + rgba borders
// ═══════════════════════════════════════════════════════════════════════════════

const premiumDarkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#F7931A',       // BTC Orange — accent principal
      light: '#FFB74D',
      dark: '#E65100',
    },
    secondary: {
      main: '#7C4DFF',       // Violet premium
      light: '#B388FF',
      dark: '#6200EA',
    },
    success: {
      main: '#00E676',       // Vert trading (bullish)
      light: '#69F0AE',
      dark: '#00C853',
    },
    error: {
      main: '#FF1744',       // Rouge trading (bearish)
      light: '#FF5252',
      dark: '#D50000',
    },
    warning: {
      main: '#FFD600',
      light: '#FFFF00',
      dark: '#F9A825',
    },
    background: {
      default: '#0A0E17',    // Fond très sombre (style Bloomberg)
      paper: '#111827',       // Cards légèrement plus claires
    },
    text: {
      primary: '#E8EAED',
      secondary: '#9AA0A6',
    },
    divider: 'rgba(255, 255, 255, 0.06)',
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", sans-serif',
    h4: {
      fontWeight: 800,
      letterSpacing: '-0.02em',
    },
    h5: {
      fontWeight: 700,
      letterSpacing: '-0.01em',
    },
    h6: {
      fontWeight: 700,
      fontSize: '1rem',
    },
    body2: {
      fontSize: '0.85rem',
    },
    caption: {
      fontSize: '0.72rem',
      letterSpacing: '0.02em',
    },
    overline: {
      fontWeight: 700,
      letterSpacing: '0.1em',
    },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    // Cards glassmorphism
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          backgroundColor: 'rgba(17, 24, 39, 0.7)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.05)',
          transition: 'border-color 0.3s ease, box-shadow 0.3s ease, transform 0.2s ease',
          '&:hover': {
            borderColor: 'rgba(247, 147, 26, 0.12)',
            boxShadow: '0 8px 40px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(247, 147, 26, 0.08)',
          },
        },
      },
    },
    MuiCardHeader: {
      styleOverrides: {
        root: {
          paddingBottom: 8,
        },
      },
    },
    // Paper glassmorphism
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
        outlined: {
          borderColor: 'rgba(255, 255, 255, 0.08)',
        },
      },
    },
    // Boutons avec hover glow
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none' as const,
          fontWeight: 600,
          borderRadius: 8,
        },
        contained: {
          boxShadow: 'none',
          '&:hover': {
            boxShadow: '0 0 20px rgba(247, 147, 26, 0.2)',
          },
        },
      },
    },
    // Chips plus arrondis
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
        },
        sizeSmall: {
          fontSize: '0.7rem',
        },
      },
    },
    // Select/Input plus discret
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(255, 255, 255, 0.1)',
          },
          '&:hover .MuiOutlinedInput-notchedOutline': {
            borderColor: 'rgba(247, 147, 26, 0.3)',
          },
        },
      },
    },
    // LinearProgress premium
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          height: 6,
        },
      },
    },
    // Divider subtil
    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: 'rgba(255, 255, 255, 0.04)',
        },
      },
    },
    // Alert arrondi
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 10,
        },
      },
    },
    // Tooltip dark
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: 'rgba(0, 0, 0, 0.85)',
          backdropFilter: 'blur(10px)',
          borderRadius: 8,
          fontSize: '0.75rem',
        },
      },
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={premiumDarkTheme}>
      <CssBaseline />
      <Dashboard />
    </ThemeProvider>
  );
}

export default App;
