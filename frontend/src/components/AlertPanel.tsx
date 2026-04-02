// =============================================================================
// AlertPanel - Alert management panel with form, list, and notifications
// =============================================================================

import React, { useState } from 'react';
import {
  CardContent,
  CardHeader,
  Typography,
  Box,
  Chip,
  IconButton,
  Divider,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Alert as MuiAlert,
  Stack,
  Collapse,
  Badge,
  Tooltip,
  SelectChangeEvent,
  Switch,
  FormControlLabel,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Notifications as NotificationsIcon,
  NotificationsActive as NotificationsActiveIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  PlayArrow as CheckIcon,
} from '@mui/icons-material';
import type {
  AlertItem,
  AlertCreate,
  AlertNotification,
  AlertCheckResponse,
  ConditionType,
  AlertOperator,
  AlertStatus,
} from '../types';
import { AlertPresets } from './AlertPresets';
import { GlowingCard, ACCENT } from './GlowingCard';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export interface AlertPanelProps {
  alerts: AlertItem[];
  notifications: AlertNotification[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onAdd: (data: AlertCreate) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onCheck: () => Promise<AlertCheckResponse | null>;
  onDismissNotifications: () => void;
  timeframe: string;
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

const CONDITION_LABELS: Record<ConditionType, string> = {
  price: 'Prix',
  rsi: 'RSI (14)',
  macd_hist: 'MACD Histo.',
  score: 'Score composite',
};

const OPERATOR_LABELS: Record<AlertOperator, string> = {
  above: 'Au-dessus de',
  below: 'En dessous de',
};

function getStatusColor(status: AlertStatus): 'success' | 'warning' | 'default' {
  switch (status) {
    case 'active': return 'success';
    case 'triggered': return 'warning';
    case 'disabled': return 'default';
    default: return 'default';
  }
}

function getStatusLabel(status: AlertStatus): string {
  switch (status) {
    case 'active': return 'Active';
    case 'triggered': return 'Déclenchée';
    case 'disabled': return 'Désactivée';
    default: return status;
  }
}

function formatThreshold(conditionType: ConditionType, threshold: number): string {
  switch (conditionType) {
    case 'price':
      return `$${threshold.toLocaleString('fr-FR', { maximumFractionDigits: 0 })}`;
    case 'rsi':
      return threshold.toFixed(0);
    case 'macd_hist':
      return threshold.toFixed(2);
    case 'score':
      return `${threshold > 0 ? '+' : ''}${threshold.toFixed(0)}`;
    default:
      return String(threshold);
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Placeholders par type de condition pour guider l'utilisateur
function getThresholdPlaceholder(conditionType: ConditionType): string {
  switch (conditionType) {
    case 'price': return 'ex: 70000';
    case 'rsi': return 'ex: 70';
    case 'macd_hist': return 'ex: 0';
    case 'score': return 'ex: 50';
    default: return 'ex: 0';
  }
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

/** Formulaire de création d'alerte */
const AlertForm: React.FC<{
  onAdd: (data: AlertCreate) => Promise<void>;
  timeframe: string;
}> = ({ onAdd, timeframe }) => {
  const [conditionType, setConditionType] = useState<ConditionType>('price');
  const [operator, setOperator] = useState<AlertOperator>('above');
  const [threshold, setThreshold] = useState('');
  const [message, setMessage] = useState('');
  const [recurring, setRecurring] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async () => {
    const numThreshold = parseFloat(threshold);
    if (isNaN(numThreshold)) {
      setFormError('Le seuil doit être un nombre valide');
      return;
    }

    setFormError(null);
    setSubmitting(true);
    try {
      await onAdd({
        condition_type: conditionType,
        operator,
        threshold: numThreshold,
        message: message.trim() || undefined,
        recurring,
        timeframe,
      });
      // Reset form
      setThreshold('');
      setMessage('');
      setRecurring(false);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erreur lors de la création';
      setFormError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Box sx={{ display: 'flex', gap: 1 }}>
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel>Condition</InputLabel>
          <Select
            value={conditionType}
            label="Condition"
            onChange={(e: SelectChangeEvent) => setConditionType(e.target.value as ConditionType)}
          >
            <MenuItem value="price">Prix</MenuItem>
            <MenuItem value="rsi">RSI (14)</MenuItem>
            <MenuItem value="macd_hist">MACD Histo.</MenuItem>
            <MenuItem value="score">Score</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Opérateur</InputLabel>
          <Select
            value={operator}
            label="Opérateur"
            onChange={(e: SelectChangeEvent) => setOperator(e.target.value as AlertOperator)}
          >
            <MenuItem value="above">Au-dessus ≥</MenuItem>
            <MenuItem value="below">En dessous ≤</MenuItem>
          </Select>
        </FormControl>

        <TextField
          size="small"
          label="Seuil"
          type="number"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          placeholder={getThresholdPlaceholder(conditionType)}
          sx={{ minWidth: 100, flex: 1 }}
        />
      </Box>

      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <TextField
          size="small"
          label="Message (optionnel)"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Message personnalisé..."
          sx={{ flex: 1 }}
        />
        <FormControlLabel
          control={
            <Switch
              checked={recurring}
              onChange={(e) => setRecurring(e.target.checked)}
              size="small"
            />
          }
          label={
            <Typography variant="caption">Récurrent</Typography>
          }
        />
      </Box>

      {formError && (
        <MuiAlert severity="error" variant="outlined" sx={{ py: 0 }}>
          <Typography variant="caption">{formError}</Typography>
        </MuiAlert>
      )}

      <Button
        variant="contained"
        size="small"
        startIcon={<AddIcon />}
        onClick={handleSubmit}
        disabled={submitting || !threshold}
        fullWidth
      >
        {submitting ? 'Création...' : 'Créer l\'alerte'}
      </Button>
    </Box>
  );
};

/** Ligne d'alerte individuelle */
const AlertRow: React.FC<{
  alert: AlertItem;
  onDelete: (id: number) => Promise<void>;
}> = ({ alert, onDelete }) => {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete(alert.id);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <ListItem
      sx={{
        px: 1,
        py: 0.5,
        borderRadius: 1,
        '&:hover': { backgroundColor: 'action.hover' },
      }}
      disablePadding
    >
      <ListItemText
        primary={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Typography variant="body2" fontWeight={600}>
              {CONDITION_LABELS[alert.condition_type as ConditionType]}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {OPERATOR_LABELS[alert.operator as AlertOperator]}
            </Typography>
            <Typography variant="body2" fontWeight={700}>
              {formatThreshold(alert.condition_type as ConditionType, alert.threshold)}
            </Typography>
            <Chip
              label={getStatusLabel(alert.status as AlertStatus)}
              size="small"
              color={getStatusColor(alert.status as AlertStatus)}
              sx={{ ml: 'auto', height: 20, fontSize: '0.65rem' }}
            />
          </Box>
        }
        secondary={
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 0.25 }}>
            <Chip
              label={alert.timeframe}
              size="small"
              variant="outlined"
              sx={{ height: 18, fontSize: '0.6rem' }}
            />
            {alert.recurring && (
              <Chip
                label="Récurrent"
                size="small"
                variant="outlined"
                color="info"
                sx={{ height: 18, fontSize: '0.6rem' }}
              />
            )}
            {alert.message && (
              <Tooltip title={alert.message}>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: 120 }}>
                  {alert.message}
                </Typography>
              </Tooltip>
            )}
            {alert.triggered_at && (
              <Typography variant="caption" color="warning.main">
                Décl. {formatDate(alert.triggered_at)}
              </Typography>
            )}
          </Box>
        }
      />
      <ListItemSecondaryAction>
        <IconButton
          edge="end"
          size="small"
          onClick={handleDelete}
          disabled={deleting}
          color="error"
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      </ListItemSecondaryAction>
    </ListItem>
  );
};

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------

export const AlertPanel: React.FC<AlertPanelProps> = ({
  alerts,
  notifications,
  loading,
  error,
  onRefresh,
  onAdd,
  onDelete,
  onCheck,
  onDismissNotifications,
  timeframe,
}) => {
  const [formOpen, setFormOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<AlertCheckResponse | null>(null);

  const activeCount = alerts.filter(a => a.status === 'active').length;
  const triggeredCount = alerts.filter(a => a.status === 'triggered').length;

  const handleCheck = async () => {
    setChecking(true);
    setCheckResult(null);
    try {
      const result = await onCheck();
      setCheckResult(result);
    } finally {
      setChecking(false);
    }
  };

  return (
    <GlowingCard accentColor={ACCENT.orange.start} accentColorEnd={ACCENT.orange.end} delay={0.15}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Badge
              badgeContent={notifications.length}
              color="error"
              invisible={notifications.length === 0}
              sx={{
                '& .MuiBadge-badge': {
                  animation: notifications.length > 0 ? 'pulse-glow 2s ease-in-out infinite' : 'none',
                },
              }}
            >
              {notifications.length > 0 ? (
                <NotificationsActiveIcon color="warning" />
              ) : (
                <NotificationsIcon />
              )}
            </Badge>
            <Typography variant="h6" fontWeight={800} sx={{ fontSize: '1rem' }}>
              🔔 Alertes
            </Typography>
            <Chip
              label={`${activeCount} active${activeCount > 1 ? 's' : ''}`}
              size="small"
              color="success"
              variant="outlined"
            />
            {triggeredCount > 0 && (
              <Chip
                label={`${triggeredCount} déclenchée${triggeredCount > 1 ? 's' : ''}`}
                size="small"
                color="warning"
                variant="outlined"
              />
            )}
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', gap: 0.5 }}>
            <Tooltip title="Vérifier les alertes maintenant">
              <IconButton
                size="small"
                onClick={handleCheck}
                disabled={checking || loading}
                color="primary"
              >
                <CheckIcon />
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={onRefresh} disabled={loading}>
              <RefreshIcon />
            </IconButton>
          </Box>
        }
      />

      <CardContent sx={{ pt: 0 }}>
        {/* Notifications de déclenchement */}
        {notifications.length > 0 && (
          <MuiAlert
            severity="warning"
            sx={{ mb: 2 }}
            onClose={onDismissNotifications}
          >
            <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
              {notifications.length} alerte{notifications.length > 1 ? 's' : ''} déclenchée{notifications.length > 1 ? 's' : ''} !
            </Typography>
            {notifications.slice(0, 3).map((n, i) => (
              <Typography key={i} variant="caption" display="block">
                • {n.message}
              </Typography>
            ))}
            {notifications.length > 3 && (
              <Typography variant="caption" color="text.secondary">
                ... et {notifications.length - 3} autre(s)
              </Typography>
            )}
          </MuiAlert>
        )}

        {/* Résultat du dernier check */}
        {checkResult && (
          <MuiAlert
            severity={checkResult.triggered > 0 ? 'warning' : 'success'}
            variant="outlined"
            sx={{ mb: 2, py: 0 }}
            onClose={() => setCheckResult(null)}
          >
            <Typography variant="caption">
              {checkResult.checked} vérifiée{checkResult.checked > 1 ? 's' : ''} — {checkResult.triggered} déclenchée{checkResult.triggered > 1 ? 's' : ''}
            </Typography>
          </MuiAlert>
        )}

        {/* Erreur */}
        {error && (
          <MuiAlert severity="error" sx={{ mb: 2 }}>
            {error}
          </MuiAlert>
        )}

        {/* Bouton pour ouvrir/fermer le formulaire */}
        <Button
          size="small"
          variant="outlined"
          startIcon={formOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          endIcon={<AddIcon />}
          onClick={() => setFormOpen(!formOpen)}
          fullWidth
          sx={{ mb: 1 }}
        >
          Nouvelle alerte
        </Button>

        {/* Formulaire de création */}
        <Collapse in={formOpen}>
          <Box sx={{ mb: 2, p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
            <AlertForm onAdd={onAdd} timeframe={timeframe} />
          </Box>
        </Collapse>

        {/* Stratégies éprouvées (presets) */}
        <AlertPresets
          onAdd={onAdd}
          existingAlerts={alerts}
          timeframe={timeframe}
        />

        <Divider sx={{ my: 1 }} />

        {/* Liste des alertes */}
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ fontWeight: 600, letterSpacing: 1, display: 'block', mb: 0.5 }}
        >
          Alertes configurées ({alerts.length})
        </Typography>

        {alerts.length === 0 ? (
          <MuiAlert severity="info" variant="outlined" sx={{ mt: 1 }}>
            <Typography variant="caption">
              Aucune alerte configurée. Créez votre première alerte pour être notifié
              quand une condition de marché est remplie.
            </Typography>
          </MuiAlert>
        ) : (
          <List dense disablePadding>
            {alerts.map((alert) => (
              <AlertRow key={alert.id} alert={alert} onDelete={onDelete} />
            ))}
          </List>
        )}

        {/* Compteurs résumé */}
        {alerts.length > 0 && (
          <>
            <Divider sx={{ my: 1 }} />
            <Stack direction="row" spacing={1} justifyContent="center">
              <Chip
                label={`${activeCount} active${activeCount > 1 ? 's' : ''}`}
                size="small"
                sx={{ backgroundColor: '#4caf5020', color: '#4caf50' }}
              />
              <Chip
                label={`${triggeredCount} déclenchée${triggeredCount > 1 ? 's' : ''}`}
                size="small"
                sx={{ backgroundColor: '#ff980020', color: '#ff9800' }}
              />
              <Chip
                label={`${alerts.length - activeCount - triggeredCount} désactivée${(alerts.length - activeCount - triggeredCount) > 1 ? 's' : ''}`}
                size="small"
                variant="outlined"
              />
            </Stack>
          </>
        )}
      </CardContent>
    </GlowingCard>
  );
};

// Export nommé uniquement (pas de default export non utilisé)

