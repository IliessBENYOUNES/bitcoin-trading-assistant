"""
Service pour récupérer les données OHLCV depuis l'API publique Binance.

Binance offre des données OHLCV (klines) à n'importe quel intervalle,
gratuitement et sans clé API, avec un volume réel.

Endpoint : GET https://api.binance.com/api/v3/klines
Limites  : 1200 requêtes/min, 1000 candles max par appel

Note : Binance n'a pas de paire BTC/USD exacte, on utilise BTCUSDT
(Tether) — la différence de prix est négligeable (<0.1%).

Documentation : https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data
"""

import httpx
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class BinanceService:
    """
    Client pour l'API publique Binance (klines/OHLCV).

    Exemple d'utilisation :
        service = BinanceService()
        candles = await service.get_ohlcv("BTC/USD", timeframe="30m", days=7)
    """

    BASE_URL = "https://api.binance.com/api/v3"

    # Mapping symboles internes → symboles Binance
    SYMBOL_MAP = {
        "BTC/USD": "BTCUSDT",
        "BTC/EUR": "BTCEUR",
        "ETH/USD": "ETHUSDT",
        "ETH/EUR": "ETHEUR",
    }

    # Mapping timeframes internes → intervalles Binance
    INTERVAL_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    # Nombre max de candles par requête Binance
    MAX_CANDLES_PER_REQUEST = 1000

    def __init__(self, timeout: float = 30.0):
        """Initialise le client HTTP."""
        self.timeout = timeout

    def _get_binance_symbol(self, symbol: str) -> str:
        """Convertit un symbole interne en symbole Binance."""
        return self.SYMBOL_MAP.get(symbol.upper(), "BTCUSDT")

    def _get_binance_interval(self, timeframe: str) -> str:
        """Convertit un timeframe interne en intervalle Binance."""
        return self.INTERVAL_MAP.get(timeframe, "4h")

    def _timeframe_to_ms(self, timeframe: str) -> int:
        """Retourne la durée d'un intervalle en millisecondes."""
        mapping = {
            "1m": 60_000,
            "5m": 300_000,
            "15m": 900_000,
            "30m": 1_800_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
        }
        return mapping.get(timeframe, 14_400_000)

    async def get_ohlcv(
        self,
        symbol: str = "BTC/USD",
        timeframe: str = "30m",
        days: int = 7,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Récupère les données OHLCV depuis Binance avec pagination automatique.

        Args:
            symbol: Paire de trading (ex: "BTC/USD")
            timeframe: Intervalle (ex: "30m", "1h", "4h", "1d")
            days: Nombre de jours d'historique
            start_time: Début de la fenêtre (optionnel, calculé depuis days)
            end_time: Fin de la fenêtre (optionnel, défaut = maintenant)

        Returns:
            Liste de chandeliers au format :
            [
                {
                    "timestamp": datetime,
                    "open": float,
                    "high": float,
                    "low": float,
                    "close": float,
                    "volume": float
                },
                ...
            ]
        """
        binance_symbol = self._get_binance_symbol(symbol)
        interval = self._get_binance_interval(timeframe)
        interval_ms = self._timeframe_to_ms(timeframe)

        # Calculer la fenêtre temporelle
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        if start_time is None:
            start_time = end_time - timedelta(days=days)

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        # Pagination : Binance limite à 1000 candles par requête
        all_candles: list[dict] = []
        current_start_ms = start_ms

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while current_start_ms < end_ms:
                params = {
                    "symbol": binance_symbol,
                    "interval": interval,
                    "startTime": current_start_ms,
                    "endTime": end_ms,
                    "limit": self.MAX_CANDLES_PER_REQUEST,
                }

                response = await client.get(
                    f"{self.BASE_URL}/klines",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                for kline in data:
                    # Format Binance kline :
                    # [open_time, open, high, low, close, volume,
                    #  close_time, quote_volume, trades, taker_buy_base,
                    #  taker_buy_quote, ignore]
                    all_candles.append({
                        "timestamp": datetime.fromtimestamp(
                            kline[0] / 1000,
                            tz=timezone.utc,
                        ),
                        "open": float(kline[1]),
                        "high": float(kline[2]),
                        "low": float(kline[3]),
                        "close": float(kline[4]),
                        "volume": float(kline[5]),
                    })

                # Avancer le curseur : dernier open_time + 1 intervalle
                last_open_time_ms = data[-1][0]
                current_start_ms = last_open_time_ms + interval_ms

                # Sécurité anti-boucle infinie
                if len(data) < self.MAX_CANDLES_PER_REQUEST:
                    break

        logger.info(
            f"Binance: fetched {len(all_candles)} {timeframe} candles "
            f"for {symbol} over {days} days"
        )
        return all_candles

