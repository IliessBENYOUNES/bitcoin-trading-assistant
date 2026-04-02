"""
DataSourceRouter — Routeur intelligent de sources de données OHLCV.

Choisit automatiquement la meilleure source (Binance ou CoinGecko fallback)
selon le timeframe et le nombre de jours demandés.

Stratégie :
- Binance est la source principale (OHLCV natif, volume réel, toute granularité)
- CoinGecko est le fallback en cas d'erreur Binance

Cela permet de débloquer TOUTES les combinaisons timeframe × jours :
- 30m + 30j  → Binance (pagination automatique)
- 4h  + 1j   → Binance (pas de contrainte de granularité)
- 1h  + 14j  → Binance
- 1d  + 1j   → Binance
"""

import logging
from typing import Optional
from datetime import datetime

from app.services.binance_service import BinanceService
from app.services.coingecko_service import CoinGeckoService

logger = logging.getLogger(__name__)


class DataSourceRouter:
    """
    Abstraction qui unifie l'accès aux données OHLCV.

    Exemple :
        router = DataSourceRouter()
        candles = await router.get_candles("BTC/USD", timeframe="30m", days=7)
    """

    def __init__(self):
        self.binance = BinanceService()
        self.coingecko = CoinGeckoService()

    async def get_candles(
        self,
        symbol: str = "BTC/USD",
        timeframe: str = "4h",
        days: int = 7,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Récupère les données OHLCV en choisissant la meilleure source.

        Priorité : Binance (natif OHLCV toute granularité) → CoinGecko (fallback)

        Args:
            symbol: Paire de trading (ex: "BTC/USD")
            timeframe: Intervalle souhaité (ex: "30m", "1h", "4h", "1d")
            days: Nombre de jours d'historique
            start_time: Début de la fenêtre (optionnel)
            end_time: Fin de la fenêtre (optionnel)

        Returns:
            Liste de chandeliers [{timestamp, open, high, low, close, volume}]
        """
        # Tentative 1 : Binance (source principale)
        try:
            candles = await self.binance.get_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                days=days,
                start_time=start_time,
                end_time=end_time,
            )
            if candles:
                logger.info(
                    f"DataSourceRouter: Binance OK — {len(candles)} candles "
                    f"({timeframe}/{days}j)"
                )
                return candles
            logger.warning("DataSourceRouter: Binance returned empty, trying CoinGecko")
        except Exception as e:
            logger.warning(f"DataSourceRouter: Binance failed ({e}), falling back to CoinGecko")

        # Tentative 2 : CoinGecko (fallback)
        # CoinGecko ne supporte pas le choix du timeframe,
        # il sera déterminé automatiquement par le nombre de jours
        try:
            candles = await self.coingecko.get_ohlc(symbol=symbol, days=days)
            if candles:
                logger.info(
                    f"DataSourceRouter: CoinGecko fallback OK — {len(candles)} candles "
                    f"(days={days})"
                )
                return candles
        except Exception as e:
            logger.error(f"DataSourceRouter: CoinGecko also failed ({e})")

        # Les deux sources ont échoué
        return []

