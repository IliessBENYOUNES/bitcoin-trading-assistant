"""
Service pour récupérer les données de marché depuis CoinGecko.

CoinGecko est une API gratuite (pas de clé API requise) qui fournit :
- Prix en temps réel
- Données historiques OHLC
- Informations sur les cryptomonnaies

Documentation : https://www.coingecko.com/en/api/documentation

LIMITES DE L'API GRATUITE :
- 10-30 appels par minute
- Données OHLC limitées aux derniers jours
"""

import httpx
from datetime import datetime, timezone
from typing import Optional


class CoinGeckoService:
    """
    Client pour l'API CoinGecko.
    
    Exemple d'utilisation :
        service = CoinGeckoService()
        candles = await service.get_ohlc("bitcoin", "usd", days=7)
    """
    
    # URL de base de l'API CoinGecko
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    # Mapping des symboles vers les IDs CoinGecko
    COIN_IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "BTC/USD": "bitcoin",
        "BTC/EUR": "bitcoin",
        "ETH/USD": "ethereum",
    }
    
    # Mapping des symboles vers les devises
    CURRENCIES = {
        "BTC/USD": "usd",
        "BTC/EUR": "eur",
        "ETH/USD": "usd",
    }
    
    def __init__(self):
        """Initialise le client HTTP."""
        # Timeout de 30 secondes pour les requêtes
        self.timeout = 30.0
    
    def _get_coin_id(self, symbol: str) -> str:
        """Convertit un symbole en ID CoinGecko."""
        return self.COIN_IDS.get(symbol.upper(), "bitcoin")
    
    def _get_currency(self, symbol: str) -> str:
        """Extrait la devise d'un symbole."""
        return self.CURRENCIES.get(symbol.upper(), "usd")
    
    async def get_ohlc(
        self,
        symbol: str = "BTC/USD",
        days: int = 7
    ) -> list[dict]:
        """
        Récupère les données OHLC depuis CoinGecko.
        
        Args:
            symbol: Paire de trading (ex: "BTC/USD")
            days: Nombre de jours d'historique (1, 7, 14, 30, 90, 180, 365)
        
        Returns:
            Liste de chandeliers au format :
            [
                {
                    "timestamp": datetime,
                    "open": float,
                    "high": float,
                    "low": float,
                    "close": float
                },
                ...
            ]
        
        Note:
            CoinGecko retourne des chandeliers dont l'intervalle dépend de 'days':
            - 1-2 jours : chandeliers de 30 minutes
            - 3-30 jours : chandeliers de 4 heures
            - 31+ jours : chandeliers de 4 jours
        """
        coin_id = self._get_coin_id(symbol)
        currency = self._get_currency(symbol)
        
        url = f"{self.BASE_URL}/coins/{coin_id}/ohlc"
        params = {
            "vs_currency": currency,
            "days": days
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        
        # CoinGecko retourne : [[timestamp_ms, open, high, low, close], ...]
        candles = []
        for item in data:
            timestamp_ms, open_price, high_price, low_price, close_price = item
            
            candles.append({
                "timestamp": datetime.fromtimestamp(
                    timestamp_ms / 1000, 
                    tz=timezone.utc
                ),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": 0.0  # CoinGecko OHLC ne fournit pas le volume
            })
        
        return candles
    
    async def get_current_price(self, symbol: str = "BTC/USD") -> Optional[float]:
        """
        Récupère le prix actuel d'une crypto.
        
        Args:
            symbol: Paire de trading (ex: "BTC/USD")
        
        Returns:
            Prix actuel en float, ou None si erreur
        """
        coin_id = self._get_coin_id(symbol)
        currency = self._get_currency(symbol)
        
        url = f"{self.BASE_URL}/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": currency
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            return data.get(coin_id, {}).get(currency)
        
        except Exception:
            return None
    
    async def get_market_data(self, symbol: str = "BTC/USD") -> Optional[dict]:
        """
        Récupère les données de marché complètes.
        
        Inclut : prix, market cap, volume 24h, variations, etc.
        """
        coin_id = self._get_coin_id(symbol)
        currency = self._get_currency(symbol)
        
        url = f"{self.BASE_URL}/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "community_data": "false",
            "developer_data": "false"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            
            market_data = data.get("market_data", {})
            
            return {
                "symbol": symbol,
                "name": data.get("name"),
                "current_price": market_data.get("current_price", {}).get(currency),
                "market_cap": market_data.get("market_cap", {}).get(currency),
                "total_volume": market_data.get("total_volume", {}).get(currency),
                "price_change_24h": market_data.get("price_change_percentage_24h"),
                "price_change_7d": market_data.get("price_change_percentage_7d"),
                "price_change_30d": market_data.get("price_change_percentage_30d"),
                "ath": market_data.get("ath", {}).get(currency),
                "ath_date": market_data.get("ath_date", {}).get(currency),
                "last_updated": data.get("last_updated")
            }
        
        except Exception:
            return None