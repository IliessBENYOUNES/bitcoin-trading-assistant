/**
 * Composant PriceCard : affiche le prix actuel et les variations.
 */

import { Card, CardContent, Typography, Box, Chip } from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import type { MarketInfo } from '../types';

interface PriceCardProps {
  marketInfo: MarketInfo | null;
  loading: boolean;
}

export default function PriceCard({ marketInfo, loading }: PriceCardProps) {
  if (loading) {
    return (
      <Card sx={{ minWidth: 300 }}>
        <CardContent>
          <Typography color="text.secondary">Chargement...</Typography>
        </CardContent>
      </Card>
    );
  }

  if (!marketInfo) {
    return (
      <Card sx={{ minWidth: 300 }}>
        <CardContent>
          <Typography color="error">Erreur de chargement</Typography>
        </CardContent>
      </Card>
    );
  }

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(price);
  };

  const formatPercent = (percent: number) => {
    return `${percent >= 0 ? '+' : ''}${percent.toFixed(2)}%`;
  };

  const getChangeColor = (change: number): 'success' | 'error' => {
    return change >= 0 ? 'success' : 'error';
  };

  return (
    <Card sx={{ minWidth: 300 }}>
      <CardContent>
        {/* Titre */}
        <Typography variant="h6" color="text.secondary" gutterBottom>
          {marketInfo.name} ({marketInfo.symbol})
        </Typography>

        {/* Prix actuel */}
        <Typography variant="h3" component="div" sx={{ fontWeight: 'bold', mb: 2 }}>
          {formatPrice(marketInfo.current_price)}
        </Typography>

        {/* Variations */}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
          <Chip
            icon={marketInfo.price_change_24h >= 0 ? <TrendingUpIcon /> : <TrendingDownIcon />}
            label={`24h: ${formatPercent(marketInfo.price_change_24h)}`}
            color={getChangeColor(marketInfo.price_change_24h)}
            size="small"
          />
          <Chip
            label={`7j: ${formatPercent(marketInfo.price_change_7d)}`}
            color={getChangeColor(marketInfo.price_change_7d)}
            size="small"
            variant="outlined"
          />
          <Chip
            label={`30j: ${formatPercent(marketInfo.price_change_30d)}`}
            color={getChangeColor(marketInfo.price_change_30d)}
            size="small"
            variant="outlined"
          />
        </Box>

        {/* Infos supplémentaires */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            Market Cap: {formatPrice(marketInfo.market_cap)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Volume 24h: {formatPrice(marketInfo.total_volume)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            ATH: {formatPrice(marketInfo.ath)}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
}
