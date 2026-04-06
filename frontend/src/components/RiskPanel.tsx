// =============================================================================
// RiskPanel — Dashboard de gestion du risque
// Affiche : état du risque, kill switch, config SL/TP, perte journalière
// =============================================================================

import { useState } from 'react';
import {
  Box,
  Typography,
  Button,
  Chip,
  LinearProgress,
  TextField,
  MenuItem,
  Stack,
  Alert,
  Divider,
  IconButton,
  Collapse,
  Tooltip,
} from '@mui/material';
import {
  Shield as ShieldIcon,
  Warning as WarningIcon,
  PowerSettingsNew as PowerIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Edit as EditIcon,
  Save as SaveIcon,
  Cancel as CancelIcon,
} from '@mui/icons-material';
import { useRisk } from '../hooks/useRisk';
import type { RiskConfigCreate, StopLossType } from '../types';

// Couleurs par niveau de risque
const RISK_COLORS: Record<string, string> = {
  safe: '#4caf50',
  caution: '#ff9800',
  danger: '#f44336',
  blocked: '#9c27b0',
};

const RISK_LABELS: Record<string, string> = {
  safe: '🟢 Sûr',
  caution: '🟡 Attention',
  danger: '🔴 Danger',
  blocked: '🟣 Bloqué',
};

export default function RiskPanel() {
  const { config, status, loading, error, refresh, updateConfig, toggleKillSwitch } = useRisk();
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState<RiskConfigCreate>({});

  const startEditing = () => {
    if (config) {
      setFormData({
        stop_loss_type: config.stop_loss_type as StopLossType,
        stop_loss_pct: config.stop_loss_pct,
        take_profit_pct: config.take_profit_pct,
        max_position_pct: config.max_position_pct,
        total_portfolio_value: config.total_portfolio_value,
        max_daily_loss_pct: config.max_daily_loss_pct,
      });
    }
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditing(false);
    setFormData({});
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      await updateConfig(formData);
      setEditing(false);
    } catch {
      // Error handled by hook
    } finally {
      setSaving(false);
    }
  };

  const handleKillSwitch = async () => {
    const isActive = status?.kill_switch_active ?? false;
    try {
      await toggleKillSwitch(!isActive, isActive ? undefined : 'Activation manuelle depuis le dashboard');
    } catch {
      // Error handled by hook
    }
  };

  if (loading && !status) {
    return (
      <Box sx={{ p: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1, opacity: 0.7 }}>
          Chargement du risk engine...
        </Typography>
        <LinearProgress />
      </Box>
    );
  }

  if (error && !status) {
    return (
      <Box sx={{ p: 2 }}>
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
        <Button size="small" onClick={refresh}>Réessayer</Button>
      </Box>
    );
  }

  if (!status || !config) return null;

  const riskColor = RISK_COLORS[status.risk_level] || '#888';
  const riskLabel = RISK_LABELS[status.risk_level] || status.risk_level;
  const dailyLossPct = status.daily_loss_limit_usd > 0
    ? (status.daily_loss_current / status.daily_loss_limit_usd) * 100
    : 0;

  return (
    <Box>
      {/* Header with risk level */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <ShieldIcon sx={{ color: riskColor, fontSize: 20 }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Gestion du Risque
          </Typography>
          <Chip
            label={riskLabel}
            size="small"
            sx={{
              bgcolor: `${riskColor}22`,
              color: riskColor,
              fontWeight: 700,
              fontSize: '0.75rem',
            }}
          />
        </Stack>
        <Stack direction="row" spacing={0.5}>
          {!editing ? (
            <Tooltip title="Configurer">
              <IconButton size="small" onClick={startEditing}>
                <EditIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : (
            <>
              <Tooltip title="Sauvegarder">
                <IconButton size="small" onClick={saveConfig} disabled={saving} color="primary">
                  <SaveIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Annuler">
                <IconButton size="small" onClick={cancelEditing}>
                  <CancelIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </>
          )}
          <IconButton size="small" onClick={() => setExpanded(!expanded)}>
            {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
          </IconButton>
        </Stack>
      </Stack>

      {/* Kill Switch Button */}
      <Button
        variant={status.kill_switch_active ? 'contained' : 'outlined'}
        color={status.kill_switch_active ? 'error' : 'warning'}
        startIcon={<PowerIcon />}
        onClick={handleKillSwitch}
        fullWidth
        size="small"
        sx={{
          mb: 1.5,
          fontWeight: 700,
          textTransform: 'none',
          ...(status.kill_switch_active && {
            animation: 'pulse 2s infinite',
            '@keyframes pulse': {
              '0%': { boxShadow: '0 0 0 0 rgba(244, 67, 54, 0.4)' },
              '70%': { boxShadow: '0 0 0 10px rgba(244, 67, 54, 0)' },
              '100%': { boxShadow: '0 0 0 0 rgba(244, 67, 54, 0)' },
            },
          }),
        }}
      >
        {status.kill_switch_active ? '⛔ KILL SWITCH ACTIF — Cliquer pour désactiver' : '🛡️ Kill Switch (arrêt d\'urgence)'}
      </Button>

      {status.kill_switch_active && status.config.kill_switch_reason && (
        <Alert severity="error" sx={{ mb: 1.5, py: 0 }} icon={<WarningIcon />}>
          <Typography variant="caption">
            {status.config.kill_switch_reason}
          </Typography>
        </Alert>
      )}

      {/* Daily Loss Progress */}
      <Box sx={{ mb: 1.5 }}>
        <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
          <Typography variant="caption" sx={{ opacity: 0.7 }}>
            Perte journalière
          </Typography>
          <Typography variant="caption" sx={{ fontWeight: 600 }}>
            {status.daily_loss_current.toFixed(2)} / {status.daily_loss_limit_usd.toFixed(2)} USD
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={Math.min(dailyLossPct, 100)}
          sx={{
            height: 8,
            borderRadius: 4,
            bgcolor: 'rgba(255,255,255,0.08)',
            '& .MuiLinearProgress-bar': {
              bgcolor: dailyLossPct > 80 ? '#f44336' : dailyLossPct > 50 ? '#ff9800' : '#4caf50',
              borderRadius: 4,
            },
          }}
        />
        <Typography variant="caption" sx={{ opacity: 0.5, fontSize: '0.65rem' }}>
          Reste : {status.daily_loss_remaining_usd.toFixed(2)} USD ({(100 - dailyLossPct).toFixed(0)}%)
        </Typography>
      </Box>

      {/* Quick Stats */}
      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
        <Box sx={{ flex: 1, p: 1, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 1 }}>
          <Typography variant="caption" sx={{ opacity: 0.5, display: 'block', fontSize: '0.65rem' }}>
            Stop-Loss
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {config.stop_loss_pct}% ({config.stop_loss_type})
          </Typography>
        </Box>
        <Box sx={{ flex: 1, p: 1, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 1 }}>
          <Typography variant="caption" sx={{ opacity: 0.5, display: 'block', fontSize: '0.65rem' }}>
            Take-Profit
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {config.take_profit_pct}%
          </Typography>
        </Box>
        <Box sx={{ flex: 1, p: 1, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 1 }}>
          <Typography variant="caption" sx={{ opacity: 0.5, display: 'block', fontSize: '0.65rem' }}>
            Position Max
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {status.max_position_size_usd.toLocaleString()} $
          </Typography>
        </Box>
      </Stack>

      {/* Expandable Config Form */}
      <Collapse in={expanded || editing}>
        <Divider sx={{ my: 1.5, borderColor: 'rgba(255,255,255,0.08)' }} />

        {editing ? (
          <Stack spacing={1.5}>
            <TextField
              select
              label="Type Stop-Loss"
              size="small"
              value={formData.stop_loss_type || 'fixed'}
              onChange={(e) => setFormData({ ...formData, stop_loss_type: e.target.value as StopLossType })}
              fullWidth
            >
              <MenuItem value="fixed">Fixe (%)</MenuItem>
              <MenuItem value="trailing">Trailing (suiveur)</MenuItem>
              <MenuItem value="atr">ATR (volatilité)</MenuItem>
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Stop-Loss %"
                type="number"
                size="small"
                value={formData.stop_loss_pct ?? ''}
                onChange={(e) => setFormData({ ...formData, stop_loss_pct: Number(e.target.value) })}
                inputProps={{ min: 0.1, max: 50, step: 0.5 }}
                fullWidth
              />
              <TextField
                label="Take-Profit %"
                type="number"
                size="small"
                value={formData.take_profit_pct ?? ''}
                onChange={(e) => setFormData({ ...formData, take_profit_pct: Number(e.target.value) })}
                inputProps={{ min: 0.1, max: 100, step: 0.5 }}
                fullWidth
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Position Max %"
                type="number"
                size="small"
                value={formData.max_position_pct ?? ''}
                onChange={(e) => setFormData({ ...formData, max_position_pct: Number(e.target.value) })}
                inputProps={{ min: 1, max: 100, step: 1 }}
                fullWidth
              />
              <TextField
                label="Perte Max/Jour %"
                type="number"
                size="small"
                value={formData.max_daily_loss_pct ?? ''}
                onChange={(e) => setFormData({ ...formData, max_daily_loss_pct: Number(e.target.value) })}
                inputProps={{ min: 0.1, max: 50, step: 0.5 }}
                fullWidth
              />
            </Stack>
            <TextField
              label="Portefeuille Total (USD)"
              type="number"
              size="small"
              value={formData.total_portfolio_value ?? ''}
              onChange={(e) => setFormData({ ...formData, total_portfolio_value: Number(e.target.value) })}
              inputProps={{ min: 0, step: 100 }}
              fullWidth
            />
          </Stack>
        ) : (
          <Stack spacing={0.5}>
            <Typography variant="caption" sx={{ opacity: 0.5 }}>
              Portefeuille : {config.total_portfolio_value.toLocaleString()} USD
            </Typography>
            <Typography variant="caption" sx={{ opacity: 0.5 }}>
              Limite perte/jour : {config.max_daily_loss_pct}% ({status.daily_loss_limit_usd.toFixed(0)} USD)
            </Typography>
            <Typography variant="caption" sx={{ opacity: 0.5 }}>
              Ratio R/R cible : {(config.take_profit_pct / config.stop_loss_pct).toFixed(1)}:1
            </Typography>
            <Typography variant="caption" sx={{ opacity: 0.5 }}>
              {status.detail}
            </Typography>
          </Stack>
        )}
      </Collapse>
    </Box>
  );
}

