/**
 * PaperTradingPanel — Panneau de paper trading en temps réel.
 *
 * Affiche :
 * - État du compte (capital, PnL, win rate)
 * - Position ouverte courante (prix entrée, SL, TP, PnL latent)
 * - Métriques de performance (Sharpe, drawdown, profit factor)
 * - Journal des trades (table scrollable)
 * - Mode AUTO : exécute des ticks automatiquement à intervalle régulier
 * - 🤖 Bouton unique "Lancer le Robot" : choisit le profil, active, et démarre l'auto
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Typography,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Stack,
  Alert,
  Divider,
  Tooltip,
  CircularProgress,
  TextField,
  MenuItem,
  LinearProgress,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import {
  PlayArrow,
  Stop,
  Refresh,
  Close,
  TrendingUp,
  TrendingDown,
  AccountBalance,
  AutoMode as AutoModeIcon,
  Timer as TimerIcon,
  SmartToy as RobotIcon,
  FileDownload as ExportIcon,
  Cloud as HeadlessIcon,
  CloudOff as HeadlessOffIcon,
} from '@mui/icons-material';
import { usePaperTrading } from '../hooks/usePaperTrading';
import { setPaperProfile, getPaperProfile, createPaperAccount, closePaperPosition, getPaperTradesExport, resetDailyLoss, startAutonomous, stopAutonomous, getAutonomousStatus } from '../api/marketApi';
import type { PaperTradeItem, TradingProfileType, AutonomousStatus } from '../types';

// Couleur selon PnL
const pnlColor = (pnl: number | null): string => {
  if (pnl === null) return 'text.secondary';
  return pnl >= 0 ? '#4caf50' : '#f44336';
};

// Format PnL avec signe
const formatPnl = (pnl: number | null, suffix = ''): string => {
  if (pnl === null) return '—';
  const sign = pnl >= 0 ? '+' : '';
  return `${sign}${pnl.toFixed(2)}${suffix}`;
};

// Status badge
const statusChip = (status: string) => {
  const map: Record<string, { color: 'success' | 'error' | 'warning' | 'info' | 'default'; label: string }> = {
    open: { color: 'info', label: '🔵 Ouvert' },
    closed_tp: { color: 'success', label: '✅ TP' },
    closed_sl: { color: 'error', label: '❌ SL' },
    closed_signal: { color: 'warning', label: '⚠️ Signal' },
    closed_expired: { color: 'default', label: '⏰ Expiré' },
    closed_manual: { color: 'default', label: '✋ Manuel' },
    closed_stale: { color: 'default', label: '💤 Stagnant' },
    closed_momentum_fade: { color: 'warning', label: '📉 Fade' },
    closed_trailing_stop: { color: 'success', label: '🎯 Trail' },
  };
  const cfg = map[status] || { color: 'default' as const, label: status };
  return <Chip size="small" color={cfg.color} label={cfg.label} />;
};

// Options d'intervalle auto-tick
const AUTO_INTERVALS = [
  { value: 5, label: '5s' },
  { value: 10, label: '10s' },
  { value: 30, label: '30s' },
  { value: 60, label: '1 min' },
  { value: 300, label: '5 min' },
  { value: 900, label: '15 min' },
  { value: 3600, label: '1h' },
];

// Profils disponibles avec infos pour le one-click
const PROFILE_OPTIONS: {
  value: TradingProfileType;
  label: string;
  emoji: string;
  description: string;
  autoInterval: number;   // intervalle auto-tick optimal pour ce profil
  color: string;
}[] = [
  {
    value: 'conservative',
    label: 'Prudent',
    emoji: '🛡️',
    description: 'Peu de trades, haute qualité',
    autoInterval: 300,
    color: '#4caf50',
  },
  {
    value: 'balanced',
    label: 'Équilibré',
    emoji: '⚖️',
    description: 'Compromis fréquence / qualité',
    autoInterval: 60,
    color: '#ff9800',
  },
  {
    value: 'aggressive',
    label: 'Agressif',
    emoji: '🔥',
    description: 'Plus de trades, plus de risque',
    autoInterval: 30,
    color: '#f44336',
  },
  {
    value: 'scalping',
    label: 'Scalping',
    emoji: '⚡',
    description: 'Haute fréquence, sorties rapides',
    autoInterval: 5,
    color: '#e040fb',
  },
  {
    value: 'auto',
    label: 'Auto',
    emoji: '🤖',
    description: 'Le robot choisit le profil',
    autoInterval: 10,
    color: '#9c27b0',
  },
];

export default function PaperTradingPanel({ onTradeExecuted, onResetComplete }: { onTradeExecuted?: () => void; onResetComplete?: () => void }) {
  const {
    status,
    trades,
    loading,
    error,
    lastTick,
    autoMode,
    autoIntervalSec,
    autoTickCount,
    tradeVersion,
    startAuto,
    stopAuto,
    refresh,
    reset,
    manualTick,
    closePosition,
  } = usePaperTrading({ pollInterval: 30000 });

  // Notifier le parent quand un trade est exécuté
  const prevTradeVersionRef = useRef(tradeVersion);
  useEffect(() => {
    if (tradeVersion > prevTradeVersionRef.current) {
      prevTradeVersionRef.current = tradeVersion;
      onTradeExecuted?.();
    }
  }, [tradeVersion, onTradeExecuted]);

  const [capital, setCapital] = useState('10000');
  const [tickLoading, setTickLoading] = useState(false);
  const [selectedInterval, setSelectedInterval] = useState(10);
  const [selectedProfile, setSelectedProfile] = useState<TradingProfileType>('auto');
  const [activeProfile, setActiveProfile] = useState<TradingProfileType | null>(null);
  const [launching, setLaunching] = useState(false);
  const [exporting, setExporting] = useState(false);

  // ── Mode Headless (autonome backend) ──────────────────────────────────────
  const [headlessStatus, setHeadlessStatus] = useState<AutonomousStatus | null>(null);
  const headlessPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchHeadlessStatus = useCallback(async () => {
    try {
      const status = await getAutonomousStatus();
      setHeadlessStatus(status);
    } catch {
      // Ignore — endpoint peut ne pas exister sur ancien backend
    }
  }, []);

  // Polling du statut headless toutes les 10s (léger)
  useEffect(() => {
    fetchHeadlessStatus();
    headlessPollRef.current = setInterval(fetchHeadlessStatus, 10000);
    return () => {
      if (headlessPollRef.current) clearInterval(headlessPollRef.current);
    };
  }, [fetchHeadlessStatus]);

  const handleStartHeadless = async () => {
    setLaunching(true);
    try {
      const profileOpt = PROFILE_OPTIONS.find(p => p.value === selectedProfile);
      const interval = profileOpt?.autoInterval ?? 30;
      await startAutonomous({
        interval_seconds: interval,
        profile: selectedProfile,
      });
      await fetchHeadlessStatus();
    } catch (err) {
      console.error('Start headless failed:', err);
    } finally {
      setLaunching(false);
    }
  };

  const handleStopHeadless = async () => {
    try {
      await stopAutonomous();
      await fetchHeadlessStatus();
    } catch (err) {
      console.error('Stop headless failed:', err);
    }
  };

  // Countdown timer pour le prochain tick auto
  const [countdown, setCountdown] = useState(0);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Charger le profil actif au démarrage
  const loadProfile = useCallback(async () => {
    try {
      const p = await getPaperProfile();
      setActiveProfile(p.active_profile as TradingProfileType);
      setSelectedProfile(p.active_profile as TradingProfileType);
    } catch {
      // Ignore — profil par défaut
    }
  }, []);

  useEffect(() => { loadProfile(); }, [loadProfile]);

  // Gère le countdown quand autoMode est actif
  useEffect(() => {
    if (autoMode) {
      setCountdown(autoIntervalSec);
      countdownRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) return autoIntervalSec;
          return prev - 1;
        });
      }, 1000);
      return () => {
        if (countdownRef.current) clearInterval(countdownRef.current);
      };
    } else {
      setCountdown(0);
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    }
  }, [autoMode, autoIntervalSec]);

  // ═══════════════════════════════════════════════════════════════════════════
  // 🤖 LANCER LE ROBOT — Un seul bouton fait tout
  // ═══════════════════════════════════════════════════════════════════════════
  const handleLaunchRobot = async () => {
    setLaunching(true);
    try {
      // 0. Fermer la position existante si le profil change
      //    (évite le "goulot d'étranglement : position blocking")
      if (status?.open_position && activeProfile !== selectedProfile) {
        await closePaperPosition(`Changement de profil : ${activeProfile} → ${selectedProfile}`);
      }

      // 1. Définir le profil
      await setPaperProfile(selectedProfile);
      setActiveProfile(selectedProfile);

      // 2. Activer le compte avec multi-slot (3 positions simultanées)
      const isActive = status?.account?.is_active ?? false;
      if (!isActive) {
        await createPaperAccount({
          initial_capital: Number(capital) || 10000,
          max_open_positions: 3,
        });
        await refresh();
      } else {
        // Même si actif, mettre à jour max_open_positions pour le multi-slot
        await createPaperAccount({
          initial_capital: status?.account?.initial_capital || Number(capital) || 10000,
          max_open_positions: 3,
        });
      }

      // 3. Démarrer le mode auto avec l'intervalle optimal du profil
      const profileOpt = PROFILE_OPTIONS.find(p => p.value === selectedProfile);
      const interval = profileOpt?.autoInterval ?? 10;
      startAuto(interval);
    } catch {
      // error handled by hook
    } finally {
      setLaunching(false);
    }
  };

  const handleStopRobot = () => {
    stopAuto();
  };

  // Reset Daily Loss — ne touche PAS aux trades ni au capital
  // Contrat métier : remet daily_loss_current à zéro,
  // désactive le kill switch SEULEMENT si déclenché par "Perte journalière"
  const handleResetDailyLoss = async () => {
    if (window.confirm(
      'Remettre le compteur de perte journalière à zéro ?\n\n' +
      'Ceci ne touche PAS :\n' +
      '• Au capital\n' +
      '• Aux trades\n' +
      '• Au learning\n' +
      '• Aux runs\n\n' +
      'Le kill switch sera désactivé seulement s\'il avait été déclenché par la perte journalière.'
    )) {
      try {
        await resetDailyLoss();
        await refresh();
        // Notifier le parent pour rafraîchir RiskPanel et DiagnosticPanel
        onResetComplete?.();
      } catch (err) {
        console.error('Reset daily loss failed:', err);
      }
    }
  };

  // Reset COMPLET — DESTRUCTIF : supprime TOUT (trades, learning, runs, logs, risk)
  // Protégé par saisie obligatoire du mot "RESET"
  const handleFullReset = async () => {
    const confirmation = window.prompt(
      '⚠️ ATTENTION : Ceci effectue un FULL RESET TOTAL.\n\n' +
      'Seront supprimés :\n' +
      '• Tous les trades paper\n' +
      '• Tout le journal de ticks\n' +
      '• Tous les learning signals\n' +
      '• Toutes les suggestions IA\n' +
      '• Toutes les campagnes de validation (runs)\n' +
      '• Le risk config sera réinitialisé\n\n' +
      'Cette action est IRRÉVERSIBLE.\n\n' +
      'Pour confirmer, tapez RESET en majuscules :'
    );
    if (confirmation === 'RESET') {
      const result = await reset(Number(capital) || 10000);
      // Notifier le parent pour rafraîchir RiskPanel et autres panels
      onResetComplete?.();
      if (result) {
        // Afficher un résumé de ce qui a été purgé
        const summary = result.reset_details.join('\n');
        window.alert(`✅ ${result.message}\n\n${summary}`);
      }
    }
  };

  const handleTick = async () => {
    setTickLoading(true);
    await manualTick();
    setTickLoading(false);
  };

  const handleClose = async () => {
    if (window.confirm('Fermer la position ouverte ?')) {
      await closePosition();
    }
  };

  const handleStartAuto = async () => {
    // [v2.0.3-fix] Activer le compte avant de démarrer l'auto-tick.
    // Avant, "Auto custom" démarrait les ticks sans activation,
    // ce qui causait des réponses "inactive" en boucle.
    const isActive = status?.account?.is_active ?? false;
    if (!isActive) {
      await createPaperAccount({
        initial_capital: Number(capital) || 10000,
        max_open_positions: 3,
      });
      await refresh();
    }
    startAuto(selectedInterval);
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // 📥 EXPORT — Télécharge le journal complet en JSON
  // ═══════════════════════════════════════════════════════════════════════════
  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await getPaperTradesExport();
      const json = JSON.stringify(data, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const now = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `btc-trading-journal-${now}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Export failed:', e);
    } finally {
      setExporting(false);
    }
  };


  const account = status?.account;
  const openPos = status?.open_position;
  const metrics = status?.metrics;
  const isActive = account?.is_active ?? false;

  // Profil actif — trouver les infos d'affichage
  const activeProfileInfo = PROFILE_OPTIONS.find(p => p.value === activeProfile);

  // Progress pour le countdown
  const countdownProgress = autoMode && autoIntervalSec > 0
    ? ((autoIntervalSec - countdown) / autoIntervalSec) * 100
    : 0;

  return (
    <Box>
      {/* Header */}
      <Stack direction="row" alignItems="center" spacing={1} mb={2}>
        <AccountBalance sx={{ color: isActive ? '#4caf50' : '#999' }} />
        <Typography variant="h6" fontWeight={700}>
          📋 Paper Trading
        </Typography>
        <Chip
          size="small"
          label={isActive ? 'ACTIF' : 'INACTIF'}
          color={isActive ? 'success' : 'default'}
        />
        {autoMode && (
          <Chip
            size="small"
            icon={<AutoModeIcon sx={{ fontSize: 14 }} />}
            label={`AUTO ${AUTO_INTERVALS.find(i => i.value === autoIntervalSec)?.label ?? autoIntervalSec + 's'}`}
            color="primary"
            sx={{
              fontWeight: 700,
              animation: 'pulse-glow 2s ease-in-out infinite',
            }}
          />
        )}
        {activeProfileInfo && isActive && (
          <Chip
            size="small"
            label={`${activeProfileInfo.emoji} ${activeProfileInfo.label}`}
            sx={{
              fontWeight: 700,
              bgcolor: `${activeProfileInfo.color}22`,
              color: activeProfileInfo.color,
              border: `1px solid ${activeProfileInfo.color}44`,
            }}
          />
        )}
        {status?.current_btc_price && (
          <Chip
            size="small"
            variant="outlined"
            label={`BTC $${status.current_btc_price.toLocaleString()}`}
          />
        )}
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 🤖 ZONE LANCEMENT ROBOT — Un clic pour tout faire              */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {!autoMode && (
        <Box sx={{
          mb: 2,
          p: 2,
          borderRadius: 2,
          border: '1px solid rgba(247, 147, 26, 0.3)',
          bgcolor: 'rgba(247, 147, 26, 0.04)',
        }}>
          <Stack direction="row" alignItems="center" spacing={1} mb={1.5}>
            <RobotIcon sx={{ color: '#F7931A' }} />
            <Typography variant="body1" fontWeight={700} sx={{ color: '#F7931A' }}>
              🤖 Lancer le Robot
            </Typography>
            <Typography variant="caption" color="text.secondary">
              — Choisis un mode, appuie, c'est tout.
            </Typography>
          </Stack>

          {/* Sélecteur de profil */}
          <Stack direction="row" spacing={1} mb={2} flexWrap="wrap" useFlexGap>
            <ToggleButtonGroup
              value={selectedProfile}
              exclusive
              onChange={(_e, val) => val && setSelectedProfile(val as TradingProfileType)}
              size="small"
              sx={{
                '& .MuiToggleButton-root': {
                  textTransform: 'none',
                  fontWeight: 600,
                  px: 1.5,
                },
              }}
            >
              {PROFILE_OPTIONS.map((p) => (
                <ToggleButton
                  key={p.value}
                  value={p.value}
                  sx={{
                    '&.Mui-selected': {
                      bgcolor: `${p.color}22`,
                      color: p.color,
                      borderColor: p.color,
                      '&:hover': { bgcolor: `${p.color}33` },
                    },
                  }}
                >
                  <Tooltip title={p.description} arrow>
                    <span>{p.emoji} {p.label}</span>
                  </Tooltip>
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Stack>

          {/* Description du profil sélectionné */}
          {(() => {
            const p = PROFILE_OPTIONS.find(x => x.value === selectedProfile);
            return p ? (
              <Alert
                severity="info"
                icon={false}
                sx={{ mb: 2, py: 0.5, bgcolor: `${p.color}0A`, border: `1px solid ${p.color}33` }}
              >
                <Typography variant="body2">
                  <strong>{p.emoji} {p.label}</strong> — {p.description}
                  {' · '}Tick auto toutes les <strong>{AUTO_INTERVALS.find(i => i.value === p.autoInterval)?.label ?? p.autoInterval + 's'}</strong>
                </Typography>
              </Alert>
            ) : null;
          })()}

          {/* Capital + Bouton Lancer */}
          <Stack direction="row" spacing={1.5} alignItems="center">
            <TextField
              size="small"
              label="Capital ($)"
              type="number"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
              sx={{ width: 130 }}
            />
            <Button
              variant="contained"
              size="large"
              startIcon={launching ? <CircularProgress size={20} color="inherit" /> : <RobotIcon />}
              onClick={handleLaunchRobot}
              disabled={launching || loading}
              sx={{
                flex: 1,
                py: 1.5,
                fontWeight: 800,
                fontSize: '1rem',
                background: 'linear-gradient(135deg, #F7931A, #E65100)',
                boxShadow: '0 4px 20px rgba(247, 147, 26, 0.3)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #FFB74D, #F7931A)',
                  boxShadow: '0 6px 28px rgba(247, 147, 26, 0.5)',
                  transform: 'translateY(-1px)',
                },
                transition: 'all 0.2s ease',
              }}
            >
              {launching ? 'Lancement...' : '🤖 Lancer le Robot'}
            </Button>
          </Stack>
        </Box>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 🔴 ROBOT EN COURS — Countdown + Arrêt                           */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {autoMode && (
        <Box sx={{
          mb: 2,
          p: 1.5,
          borderRadius: 2,
          border: '1px solid #F7931A',
          bgcolor: 'rgba(247, 147, 26, 0.06)',
          transition: 'all 0.3s ease',
        }}>
          <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" useFlexGap>
            <AutoModeIcon sx={{ color: '#F7931A', fontSize: 20, animation: 'spin 2s linear infinite' }} />
            <Typography variant="body2" fontWeight={600} sx={{ color: '#F7931A' }}>
              Robot actif {activeProfileInfo ? `(${activeProfileInfo.emoji} ${activeProfileInfo.label})` : ''}
            </Typography>

            {/* Countdown + stats */}
            <Stack direction="row" alignItems="center" spacing={1} sx={{ flex: 1 }}>
              <TimerIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
              <Typography variant="caption" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
                Prochain tick dans {countdown}s
              </Typography>
              <Box sx={{ flex: 1, mx: 1 }}>
                <LinearProgress
                  variant="determinate"
                  value={countdownProgress}
                  sx={{
                    height: 4,
                    borderRadius: 2,
                    bgcolor: 'rgba(255,255,255,0.06)',
                    '& .MuiLinearProgress-bar': {
                      bgcolor: '#F7931A',
                      borderRadius: 2,
                      transition: 'transform 1s linear',
                    },
                  }}
                />
              </Box>
              <Chip
                size="small"
                label={`${autoTickCount} ticks`}
                variant="outlined"
                sx={{ fontWeight: 700, fontFamily: 'monospace' }}
              />
            </Stack>
            <Button
              variant="contained"
              color="error"
              size="small"
              startIcon={<Stop />}
              onClick={handleStopRobot}
              sx={{ fontWeight: 700 }}
            >
              Arrêter le Robot
            </Button>
          </Stack>
        </Box>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* ☁️ MODE HEADLESS — Robot autonome backend                        */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {headlessStatus?.running && (
        <Box sx={{
          mb: 2,
          p: 1.5,
          borderRadius: 2,
          border: '1px solid #00E676',
          bgcolor: 'rgba(0, 230, 118, 0.06)',
        }}>
          <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" useFlexGap>
            <HeadlessIcon sx={{ color: '#00E676', fontSize: 20 }} />
            <Typography variant="body2" fontWeight={700} sx={{ color: '#00E676' }}>
              🌙 Mode Headless actif
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Le robot tourne côté serveur — vous pouvez fermer ce navigateur.
            </Typography>
            <Box sx={{ flex: 1 }} />
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip
                size="small"
                label={`${headlessStatus.tick_count} ticks`}
                variant="outlined"
                sx={{ fontWeight: 700, fontFamily: 'monospace' }}
              />
              <Chip
                size="small"
                label={`${headlessStatus.trade_count} trades`}
                color="success"
                variant="outlined"
                sx={{ fontWeight: 700, fontFamily: 'monospace' }}
              />
              {headlessStatus.profile && (
                <Chip
                  size="small"
                  label={headlessStatus.profile}
                  sx={{ fontWeight: 600 }}
                />
              )}
              {headlessStatus.uptime_seconds != null && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={headlessStatus.uptime_seconds > 3600
                    ? `${Math.floor(headlessStatus.uptime_seconds / 3600)}h${Math.floor((headlessStatus.uptime_seconds % 3600) / 60)}m`
                    : `${Math.floor(headlessStatus.uptime_seconds / 60)}m`
                  }
                />
              )}
              <Button
                variant="outlined"
                color="error"
                size="small"
                startIcon={<HeadlessOffIcon />}
                onClick={handleStopHeadless}
                sx={{ fontWeight: 700 }}
              >
                Arrêter Headless
              </Button>
            </Stack>
          </Stack>
          {headlessStatus.last_result && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
              Dernier tick : {headlessStatus.last_result.action} — {headlessStatus.last_result.detail?.slice(0, 80)}
              {headlessStatus.last_result.price > 0 && ` | BTC $${headlessStatus.last_result.price.toLocaleString()}`}
            </Typography>
          )}
        </Box>
      )}

      {/* Bouton lancer en mode headless (visible quand ni auto ni headless actif) */}
      {!autoMode && !headlessStatus?.running && (
        <Box sx={{
          mb: 2,
          p: 1.5,
          borderRadius: 2,
          border: '1px dashed rgba(0, 230, 118, 0.3)',
          bgcolor: 'rgba(0, 230, 118, 0.02)',
        }}>
          <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" useFlexGap>
            <HeadlessIcon sx={{ color: '#00E676', fontSize: 20 }} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="body2" fontWeight={600} sx={{ color: '#00E676' }}>
                🌙 Mode Headless (nuit / low-bandwidth)
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Le robot tourne côté serveur uniquement. Fermez le navigateur, réduisez la data.
              </Typography>
            </Box>
            <Button
              variant="contained"
              size="small"
              startIcon={launching ? <CircularProgress size={14} color="inherit" /> : <HeadlessIcon />}
              onClick={handleStartHeadless}
              disabled={launching}
              sx={{
                fontWeight: 700,
                background: 'linear-gradient(135deg, #00C853, #00E676)',
                '&:hover': { background: 'linear-gradient(135deg, #00E676, #69F0AE)' },
              }}
            >
              {launching ? 'Démarrage...' : 'Lancer Headless'}
            </Button>
          </Stack>
        </Box>
      )}

      {/* Dernière action */}
      {lastTick && (
        <Alert
          severity={
            lastTick.action_taken.includes('opened') ? 'success' :
            lastTick.action_taken.includes('closed') ? 'warning' :
            'info'
          }
          sx={{ mb: 2 }}
        >
          <strong>{autoMode ? `Auto-tick #${autoTickCount} :` : 'Dernier tick :'}</strong> {lastTick.detail}
        </Alert>
      )}

      {/* Compte + Métriques */}
      {account && metrics && (
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 1.5,
          mb: 2,
          p: 2,
          bgcolor: 'background.paper',
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
        }}>
          <MetricBox label="Capital" value={`$${account.current_capital.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
          <MetricBox
            label="PnL total"
            value={formatPnl(account.total_pnl, ' $')}
            color={pnlColor(account.total_pnl)}
          />
          <MetricBox
            label="PnL %"
            value={formatPnl(account.total_pnl_pct, '%')}
            color={pnlColor(account.total_pnl_pct)}
          />
          <MetricBox label="Trades" value={`${metrics.total_trades}`} />
          <MetricBox
            label="Win Rate"
            value={`${metrics.win_rate.toFixed(1)}%`}
            color={metrics.win_rate >= 50 ? '#4caf50' : '#f44336'}
          />
          <MetricBox label="Max DD" value={`${metrics.max_drawdown_pct.toFixed(1)}%`} color="#f44336" />
          <MetricBox label="Sharpe" value={metrics.sharpe_ratio?.toFixed(2) ?? '—'} />
          <MetricBox label="Profit Factor" value={metrics.profit_factor.toFixed(2)} />
          <MetricBox
            label="Buy & Hold"
            value={formatPnl(metrics.buy_hold_pnl_pct, '%')}
            color={pnlColor(metrics.buy_hold_pnl_pct)}
          />
          {status?.unrealized_pnl !== null && status?.unrealized_pnl !== undefined && (
            <MetricBox
              label="PnL latent"
              value={formatPnl(status.unrealized_pnl, ' $')}
              color={pnlColor(status.unrealized_pnl)}
            />
          )}
        </Box>
      )}

      {/* Positions ouvertes (multi-slot) */}
      {(status?.open_positions?.length ?? 0) > 0 ? (
        <Box sx={{ mb: 2 }}>
          {(status?.open_positions ?? []).map((pos) => (
            <Box key={pos.id} sx={{
              mb: 1, p: 2,
              bgcolor: '#1a237e10',
              borderRadius: 2,
              border: `1px solid ${pos.direction === 'long' ? '#4caf50' : '#f44336'}44`,
            }}>
              <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
                {pos.direction === 'long' ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
                <Typography fontWeight={700} fontSize={14}>
                  {pos.direction.toUpperCase()}
                  {pos.slot && <Chip size="small" label={pos.slot} sx={{ ml: 1, fontSize: 11, height: 20 }} />}
                </Typography>
                {statusChip(pos.status)}
                <Button
                  variant="outlined"
                  color="warning"
                  size="small"
                  startIcon={<Close />}
                  onClick={handleClose}
                  sx={{ ml: 'auto' }}
                >
                  Fermer
                </Button>
              </Stack>
              <Typography variant="body2">
                Entrée : <strong>${pos.entry_price.toLocaleString()}</strong>
                {' | '}SL : <strong style={{ color: '#f44336' }}>${pos.stop_loss_price.toLocaleString()}</strong>
                {' | '}TP : <strong style={{ color: '#4caf50' }}>${pos.take_profit_price.toLocaleString()}</strong>
                {' | '}Taille : <strong>${pos.position_size_usd.toLocaleString()}</strong>
              </Typography>
              <Typography variant="body2" color="text.secondary" mt={0.5} fontSize={12}>
                Score : {pos.decision_score?.toFixed(0) ?? '—'} | {pos.entry_reason?.slice(0, 120)}
              </Typography>
            </Box>
          ))}
        </Box>
      ) : openPos && (
        <Box sx={{
          mb: 2, p: 2,
          bgcolor: '#1a237e10',
          borderRadius: 2,
          border: '1px solid #42a5f5',
        }}>
          <Stack direction="row" alignItems="center" spacing={1} mb={1}>
            {openPos.direction === 'long' ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
            <Typography fontWeight={700}>
              Position {openPos.direction.toUpperCase()} ouverte
            </Typography>
            {statusChip(openPos.status)}
            <Button
              variant="outlined"
              color="warning"
              size="small"
              startIcon={<Close />}
              onClick={handleClose}
              sx={{ ml: 'auto' }}
            >
              Fermer
            </Button>
          </Stack>
          <Typography variant="body2">
            Entrée : <strong>${openPos.entry_price.toLocaleString()}</strong>
            {' | '}SL : <strong style={{ color: '#f44336' }}>${openPos.stop_loss_price.toLocaleString()}</strong>
            {' | '}TP : <strong style={{ color: '#4caf50' }}>${openPos.take_profit_price.toLocaleString()}</strong>
            {' | '}Taille : <strong>${openPos.position_size_usd.toLocaleString()}</strong>
          </Typography>
          <Typography variant="body2" color="text.secondary" mt={0.5}>
            Score : {openPos.decision_score?.toFixed(0) ?? '—'} | {openPos.entry_reason}
          </Typography>
        </Box>
      )}

      {/* Contrôles secondaires (toujours visibles) */}
      <Stack direction="row" spacing={1} mb={2} flexWrap="wrap" useFlexGap>
        {isActive && !autoMode && (
          <Tooltip title="Exécuter un tick manuellement">
            <Button
              variant="outlined"
              size="small"
              startIcon={tickLoading ? <CircularProgress size={14} /> : <PlayArrow />}
              onClick={handleTick}
              disabled={tickLoading}
            >
              Tick manuel
            </Button>
          </Tooltip>
        )}
        <Tooltip title="Remettre à zéro le compteur de perte journalière (ne touche PAS aux trades)">
          <Button
            variant="outlined"
            size="small"
            color="warning"
            startIcon={<Refresh />}
            onClick={handleResetDailyLoss}
            disabled={loading || autoMode}
          >
            Reset perte jour
          </Button>
        </Tooltip>
        <Tooltip title="⚠️ DESTRUCTIF : Supprime TOUS les trades et remet le capital à zéro">
          <Button
            variant="outlined"
            size="small"
            color="error"
            startIcon={<Stop />}
            onClick={handleFullReset}
            disabled={loading || autoMode}
            sx={{ opacity: 0.7, fontSize: '0.75rem' }}
          >
            Full Reset
          </Button>
        </Tooltip>
        <Button
          variant="outlined"
          size="small"
          startIcon={<Refresh />}
          onClick={refresh}
          disabled={loading}
        >
          Actualiser
        </Button>
        <Tooltip title="Exporter le journal complet (JSON) pour analyse par un LLM ou sauvegarde">
          <Button
            variant="outlined"
            size="small"
            startIcon={exporting ? <CircularProgress size={14} /> : <ExportIcon />}
            onClick={handleExport}
            disabled={exporting || loading}
            sx={{ borderColor: '#F7931A', color: '#F7931A', '&:hover': { borderColor: '#E65100', bgcolor: 'rgba(247,147,26,0.06)' } }}
          >
            {exporting ? 'Export...' : '📥 Exporter Journal'}
          </Button>
        </Tooltip>
        {/* Mode avancé : intervalle custom */}
        {isActive && !autoMode && (
          <>
            <TextField
              select
              size="small"
              value={selectedInterval}
              onChange={(e) => setSelectedInterval(Number(e.target.value))}
              sx={{ minWidth: 90 }}
              label="Intervalle"
            >
              {AUTO_INTERVALS.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </TextField>
            <Button
              variant="outlined"
              size="small"
              startIcon={<AutoModeIcon />}
              onClick={handleStartAuto}
            >
              Auto custom
            </Button>
          </>
        )}
      </Stack>

      <Divider sx={{ my: 2 }} />

      {/* Journal des trades */}
      <Typography variant="subtitle2" mb={1} fontWeight={700}>
        📖 Journal des trades ({trades.length})
      </Typography>

      {trades.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Aucun trade clôturé pour le moment.
        </Typography>
      ) : (
        <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 400 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Status</TableCell>
                <TableCell>Direction</TableCell>
                <TableCell align="right">Entrée</TableCell>
                <TableCell align="right">Sortie</TableCell>
                <TableCell align="right">PnL</TableCell>
                <TableCell align="right">PnL %</TableCell>
                <TableCell align="right">Durée (h)</TableCell>
                <TableCell>Raison</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {trades.map((trade) => (
                <TradeRow key={trade.id} trade={trade} />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* CSS animation pour le spinner */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </Box>
  );
}

// Sous-composant : boîte de métrique
function MetricBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Box textAlign="center">
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="body1" fontWeight={700} sx={{ color: color || 'text.primary' }}>
        {value}
      </Typography>
    </Box>
  );
}

// Sous-composant : ligne de trade
function TradeRow({ trade }: { trade: PaperTradeItem }) {
  return (
    <TableRow hover>
      <TableCell>{statusChip(trade.status)}</TableCell>
      <TableCell>
        {trade.direction === 'long' ? '📈 Long' : '📉 Short'}
      </TableCell>
      <TableCell align="right">${trade.entry_price.toLocaleString()}</TableCell>
      <TableCell align="right">
        {trade.exit_price ? `$${trade.exit_price.toLocaleString()}` : '—'}
      </TableCell>
      <TableCell align="right" sx={{ color: pnlColor(trade.pnl), fontWeight: 700 }}>
        {formatPnl(trade.pnl, '$')}
      </TableCell>
      <TableCell align="right" sx={{ color: pnlColor(trade.pnl_pct) }}>
        {formatPnl(trade.pnl_pct, '%')}
      </TableCell>
      <TableCell align="right">
        {trade.duration_hours != null
          ? trade.duration_hours < 0.1
            ? `${Math.round(trade.duration_hours * 60)}m`
            : `${trade.duration_hours.toFixed(1)}h`
          : '—'}
      </TableCell>
      <TableCell>
        <Tooltip title={trade.exit_reason || trade.entry_reason}>
          <Typography variant="caption" noWrap sx={{ maxWidth: 150, display: 'block' }}>
            {trade.exit_reason || trade.entry_reason}
          </Typography>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
}

