"""
Service de prix unifie - Source unique de verite pour le prix BTC.

Utilise Binance comme source principale (coherent avec le WebSocket frontend
et les donnees OHLCV candles). CoinGecko en fallback si Binance indisponible.
DB en dernier recours.

Ceci resout le probleme de prix incoherents entre :
- Le PriceTicker frontend (Binance WebSocket BTCUSDT)
- L'endpoint /market/price (anciennement CoinGecko BTC/USD)
- Le Paper Trading (Binance REST BTCUSDT)
- Les candles en base (Binance REST BTCUSDT)

Maintenant TOUT utilise Binance BTCUSDT comme source primaire.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class PriceService:
    """
    Service centralise pour obtenir le prix BTC en temps reel.

    Priorite des sources :
    1. Binance REST API (ticker/price) - latence ~100ms, meme source que le WS frontend
    2. CoinGecko (simple/price) - fallback si Binance indisponible
    3. Derniere bougie en DB - dernier recours (peut etre vieux de plusieurs heures)

    Usage :
        service = PriceService()
        price = await service.get_price()        # Binance -> CoinGecko fallback
        price = await service.get_price(db=db)    # + fallback DB
        data  = await service.get_ticker_24h()    # Stats 24h Binance
    """

    BINANCE_BASE = "https://api.binance.com/api/v3"
    COINGECKO_BASE = "https://api.coingecko.com/api/v3"

    # Mapping symboles internes -> Binance
    BINANCE_SYMBOLS = {
        "BTC/USD": "BTCUSDT",
        "BTC/EUR": "BTCEUR",
        "ETH/USD": "ETHUSDT",
        "ETH/EUR": "ETHEUR",
    }

    # Mapping symboles internes -> CoinGecko
    COINGECKO_IDS = {
        "BTC/USD": ("bitcoin", "usd"),
        "BTC/EUR": ("bitcoin", "eur"),
        "ETH/USD": ("ethereum", "usd"),
    }

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    async def get_price(
        self,
        symbol: str = "BTC/USD",
        db=None,
    ) -> Optional[float]:
        """
        Recupere le prix actuel depuis Binance (prioritaire) ou CoinGecko (fallback).

        Args:
            symbol: Paire de trading (ex: "BTC/USD")
            db: Session SQLAlchemy optionnelle pour fallback DB

        Returns:
            Prix en float, ou None si toutes les sources echouent
        """
        # Source 1 : Binance REST API (meme source que le WebSocket frontend)
        price = await self._get_binance_price(symbol)
        if price is not None:
            return price

        # Source 2 : CoinGecko (fallback)
        price = await self._get_coingecko_price(symbol)
        if price is not None:
            return price

        # Source 3 : Derniere bougie en DB (dernier recours)
        if db is not None:
            price = self._get_db_price(symbol, db)
            if price is not None:
                logger.warning(
                    f"PriceService: prix depuis DB (potentiellement ancien) pour {symbol}"
                )
                return price

        logger.error(f"PriceService: aucune source disponible pour {symbol}")
        return None

    async def get_ticker_24h(self, symbol: str = "BTC/USD") -> Optional[dict]:
        """
        Recupere les stats 24h depuis Binance (high, low, volume, variation).

        Returns:
            Dict avec price, change_24h_pct, high_24h, low_24h, volume_24h
            ou None si erreur
        """
        binance_symbol = self.BINANCE_SYMBOLS.get(symbol.upper(), "BTCUSDT")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.BINANCE_BASE}/ticker/24hr",
                    params={"symbol": binance_symbol},
                )
                resp.raise_for_status()
                data = resp.json()

            return {
                "price": float(data["lastPrice"]),
                "change_24h_pct": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "volume_24h": float(data["volume"]),
                "source": "binance",
            }
        except Exception as e:
            logger.warning(f"PriceService: Binance 24h ticker failed ({e})")
            return None

    # ------------------------------------------------------------------
    # Sources internes
    # ------------------------------------------------------------------

    async def _get_binance_price(self, symbol: str) -> Optional[float]:
        """Prix via Binance REST API ticker/price."""
        binance_symbol = self.BINANCE_SYMBOLS.get(symbol.upper(), "BTCUSDT")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.BINANCE_BASE}/ticker/price",
                    params={"symbol": binance_symbol},
                )
                resp.raise_for_status()
                price = float(resp.json()["price"])
                if price > 0:
                    logger.debug(f"PriceService: Binance OK - {symbol} = {price}")
                    return price
        except Exception as e:
            logger.warning(f"PriceService: Binance price failed ({e})")

        return None

    async def _get_coingecko_price(self, symbol: str) -> Optional[float]:
        """Prix via CoinGecko simple/price (fallback)."""
        mapping = self.COINGECKO_IDS.get(symbol.upper())
        if not mapping:
            return None

        coin_id, currency = mapping

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.COINGECKO_BASE}/simple/price",
                    params={"ids": coin_id, "vs_currencies": currency},
                )
                resp.raise_for_status()
                data = resp.json()
                price = data.get(coin_id, {}).get(currency)
                if price and price > 0:
                    logger.info(
                        f"PriceService: CoinGecko fallback OK - {symbol} = {price}"
                    )
                    return float(price)
        except Exception as e:
            logger.warning(f"PriceService: CoinGecko price failed ({e})")

        return None

    @staticmethod
    def _get_db_price(symbol: str, db) -> Optional[float]:
        """Dernier close_price en base (dernier recours)."""
        from app.models.candle import Candle

        candle = (
            db.query(Candle)
            .filter(Candle.symbol == symbol)
            .order_by(Candle.timestamp.desc())
            .first()
        )
        if candle:
            return candle.close_price
        return None

