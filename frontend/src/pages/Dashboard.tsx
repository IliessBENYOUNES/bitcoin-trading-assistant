/**
 * Page Dashboard : page principale de l'application.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Container,
  Typography,
  Box,
  Button,
  Alert,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  CircularProgress,
  Snackbar,
  Chip,
  Tooltip
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import DownloadIcon from '@mui/icons-material/Download';
import WarningIcon from '@mui/icons-material/Warning';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';

import PriceCard from '../components/PriceCard';
import CandlestickChart from '../components/CandlestickChart';
import StatusBar from '../components/StatusBar';
import { healthApi, marketApi } from '../api/client';
import type { Candle, MarketInfo, CandleListResponse } from '../types';

export default function Dashboard() {
  // États
  const [apiStatus, setApiStatus] = useState<'loading' | 'connected' | 'error'>('loading');
  const [dbStatus, setDbStatus] = useState<'loading' | 'connected' | 'error'>('loading');
  const [marketInfo, setMarketInfo] = useState<MarketInfo | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [candlesMetadata, setCandlesMetadata] = useState<Partial<CandleListResponse>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Paramètres
  const [symbol] = useState('BTC/USD');
  const [timeframe, setTimeframe] = useState('4h');
  const [days, setDays] = useState(7);

  // Vérifier la connexion au backend
  const checkConnection = useCallback(async () => {
    try {
      await healthApi.check();
      setApiStatus('connected');
    } catch {
      setApiStatus('error');
    }

    try {
      const dbHealth = await healthApi.checkDb();
      setDbStatus(dbHealth.database === 'connected' ? 'connected' : 'error');
    } catch {
      setDbStatus('error');
    }
  }, []);

  // Charger les données
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Charger les infos de marché
      const info = await marketApi.getMarketInfo(symbol);
      setMarketInfo(info);

      // Charger les chandeliers avec le paramètre days pour filtrage rolling
      const candlesResponse = await marketApi.getCandles(symbol, timeframe, 200, days);
      setCandles(candlesResponse.data);
      setCandlesMetadata({
        count: candlesResponse.count,
        total_in_db: candlesResponse.total_in_db,
        expected_count: candlesResponse.expected_count,
        start_ts: candlesResponse.start_ts,
        end_ts: candlesResponse.end_ts,
      });
    } catch (err) {
      setError('Erreur lors du chargement des données. Vérifiez que le backend est lancé.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, days]);

  // Récupérer de nouvelles données depuis CoinGecko
  const fetchNewData = async () => {
    setFetching(true);
    setError(null);

    try {
      const result = await marketApi.fetchCandles(symbol, days);

      // Mettre à jour le timeframe selon les jours
      let newTimeframe = '4h';
      if (days <= 2) newTimeframe = '30m';
      else if (days > 30) newTimeframe = '4d';

      setTimeframe(newTimeframe);

      // Recharger les données
      await loadData();

      // Message de succès détaillé
      const coverageInfo = result.coverage_pct ? ` (couverture: ${result.coverage_pct}%)` : '';
      setSuccessMessage(
          `✅ ${result.inserted} insérées, ${result.updated || 0} mises à jour, ${result.duplicates} existantes${coverageInfo}`
      );
    } catch (err) {
      setError('Erreur lors de la récupération des données depuis CoinGecko');
      console.error(err);
    } finally {
      setFetching(false);
    }
  };

  // Charger au démarrage
  useEffect(() => {
    checkConnection();
  }, [checkConnection]);

  // Charger les données quand les paramètres changent
  useEffect(() => {
    if (apiStatus === 'connected') {
      loadData();
    }
  }, [apiStatus, loadData]);

  // Calculer le statut des données
  const getDataStatus = () => {
    if (!candlesMetadata.expected_count) return null;

    const actual = candlesMetadata.count || 0;
    const expected = candlesMetadata.expected_count;
    const diff = expected - actual;

    if (diff <= 1) {
      return { status: 'ok', message: 'Données complètes', color: 'success' as const };
    } else if (diff <= 3) {
      return { status: 'warning', message: `${diff} bougies manquantes`, color: 'warning' as const };
    } else {
      return { status: 'error', message: `${diff} bougies manquantes`, color: 'error' as const };
    }
  };

  const dataStatus = getDataStatus();

  return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4, flexWrap: 'wrap', gap: 2 }}>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 'bold' }}>
            🚀 Bitcoin Trading Assistant
          </Typography>
          <StatusBar apiStatus={apiStatus} dbStatus={dbStatus} />
        </Box>

        {/* Erreur */}
        {error && (
            <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
              {error}
            </Alert>
        )}

        {/* Message de succès */}
        <Snackbar
            open={!!successMessage}
            autoHideDuration={6000}
            onClose={() => setSuccessMessage(null)}
            message={successMessage}
        />

        {/* Contrôles */}
        <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap', alignItems: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
                value={timeframe}
                label="Timeframe"
                onChange={(e) => setTimeframe(e.target.value)}
            >
              <MenuItem value="30m">30 min</MenuItem>
              <MenuItem value="4h">4 heures</MenuItem>
              <MenuItem value="4d">4 jours</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Historique</InputLabel>
            <Select
                value={days}
                label="Historique"
                onChange={(e) => setDays(Number(e.target.value))}
            >
              <MenuItem value={1}>1 jour</MenuItem>
              <MenuItem value={7}>7 jours</MenuItem>
              <MenuItem value={14}>14 jours</MenuItem>
              <MenuItem value={30}>30 jours</MenuItem>
              <MenuItem value={90}>90 jours</MenuItem>
            </Select>
          </FormControl>

          <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={loadData}
              disabled={loading}
          >
            Actualiser
          </Button>

          <Button
              variant="contained"
              startIcon={fetching ? <CircularProgress size={20} color="inherit" /> : <DownloadIcon />}
              onClick={fetchNewData}
              disabled={fetching}
          >
            {fetching ? 'Récupération...' : 'Récupérer données'}
          </Button>
        </Box>

        {/* Indicateurs de données */}
        <Box sx={{ display: 'flex', gap: 1, mb: 3, flexWrap: 'wrap', alignItems: 'center' }}>
          <Tooltip title={`Fenêtre: ${candlesMetadata.start_ts ? new Date(candlesMetadata.start_ts).toLocaleString() : '?'} → ${candlesMetadata.end_ts ? new Date(candlesMetadata.end_ts).toLocaleString() : '?'}`}>
            <Chip
                label={`${candlesMetadata.count || 0} affichés (rolling ${days}j)`}
                size="small"
                variant="outlined"
            />
          </Tooltip>

          <Chip
              label={`${candlesMetadata.total_in_db || 0} en base`}
              size="small"
              variant="outlined"
              color="default"
          />

          {candlesMetadata.expected_count && (
              <Chip
                  label={`${candlesMetadata.expected_count} attendus`}
                  size="small"
                  variant="outlined"
                  color="default"
              />
          )}

          {dataStatus && (
              <Chip
                  icon={dataStatus.status === 'ok' ? <CheckCircleIcon /> : <WarningIcon />}
                  label={dataStatus.message}
                  size="small"
                  color={dataStatus.color}
              />
          )}
        </Box>

        {/* Contenu principal */}
        <Grid container spacing={3}>
          {/* Carte prix */}
          <Grid item xs={12} md={4}>
            <PriceCard marketInfo={marketInfo} loading={loading} />
          </Grid>

          {/* Graphique */}
          <Grid item xs={12} md={8}>
            <CandlestickChart
                candles={candles}
                symbol={symbol}
                timeframe={timeframe}
                loading={loading}
            />
          </Grid>
        </Grid>

        {/* Footer avec infos détaillées */}
        <Box sx={{ mt: 4, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Données fournies par CoinGecko
            {candlesMetadata.start_ts && candlesMetadata.end_ts && (
                <>
                  {' • '}
                  Période: {new Date(candlesMetadata.start_ts).toLocaleDateString()} → {new Date(candlesMetadata.end_ts).toLocaleDateString()}
                </>
            )}
          </Typography>
        </Box>
      </Container>
  );
}