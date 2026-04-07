"""
Tests du PriceService — Service de prix unifié.

Vérifie :
- La chaîne de fallback (Binance → CoinGecko → DB)
- Le ticker 24h
- Le fallback DB
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from app.services.price_service import PriceService


class TestPriceServiceGetPrice:
    """Tests pour PriceService.get_price — chaîne de fallback."""

    @pytest.mark.asyncio
    async def test_binance_price_returned_first(self):
        """Si Binance répond, on utilise ce prix."""
        service = PriceService()

        with patch.object(service, "_get_binance_price", new_callable=AsyncMock, return_value=84000.0):
            price = await service.get_price("BTC/USD")

        assert price == 84000.0

    @pytest.mark.asyncio
    async def test_coingecko_fallback_when_binance_fails(self):
        """Si Binance échoue, on tombe sur CoinGecko."""
        service = PriceService()

        with patch.object(service, "_get_binance_price", new_callable=AsyncMock, return_value=None), \
             patch.object(service, "_get_coingecko_price", new_callable=AsyncMock, return_value=83950.0):
            price = await service.get_price("BTC/USD")

        assert price == 83950.0

    @pytest.mark.asyncio
    async def test_db_fallback_when_both_apis_fail(self):
        """Si les deux APIs échouent, on utilise le dernier prix en DB."""
        service = PriceService()
        mock_db = MagicMock()

        with patch.object(service, "_get_binance_price", new_callable=AsyncMock, return_value=None), \
             patch.object(service, "_get_coingecko_price", new_callable=AsyncMock, return_value=None), \
             patch.object(PriceService, "_get_db_price", return_value=83000.0):
            price = await service.get_price("BTC/USD", db=mock_db)

        assert price == 83000.0

    @pytest.mark.asyncio
    async def test_returns_none_when_all_fail_no_db(self):
        """Sans DB et avec les APIs en échec, retourne None."""
        service = PriceService()

        with patch.object(service, "_get_binance_price", new_callable=AsyncMock, return_value=None), \
             patch.object(service, "_get_coingecko_price", new_callable=AsyncMock, return_value=None):
            price = await service.get_price("BTC/USD")

        assert price is None

    @pytest.mark.asyncio
    async def test_db_not_called_if_binance_works(self):
        """La DB n'est pas sollicitée si Binance fonctionne."""
        service = PriceService()
        mock_db = MagicMock()

        with patch.object(service, "_get_binance_price", new_callable=AsyncMock, return_value=84000.0) as mock_b, \
             patch.object(PriceService, "_get_db_price") as mock_db_price:
            price = await service.get_price("BTC/USD", db=mock_db)

        assert price == 84000.0
        mock_db_price.assert_not_called()


class TestPriceServiceBinancePrice:
    """Tests pour _get_binance_price."""

    @pytest.mark.asyncio
    async def test_binance_price_parses_response(self):
        """Vérifie le parsing de la réponse Binance."""
        service = PriceService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"symbol": "BTCUSDT", "price": "84123.45"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            price = await service._get_binance_price("BTC/USD")

        assert price == 84123.45

    @pytest.mark.asyncio
    async def test_binance_symbol_mapping(self):
        """Vérifie le mapping BTC/USD → BTCUSDT."""
        service = PriceService()
        assert service.BINANCE_SYMBOLS["BTC/USD"] == "BTCUSDT"
        assert service.BINANCE_SYMBOLS["BTC/EUR"] == "BTCEUR"
        assert service.BINANCE_SYMBOLS["ETH/USD"] == "ETHUSDT"

    @pytest.mark.asyncio
    async def test_binance_returns_none_on_error(self):
        """Retourne None si Binance est inaccessible."""
        service = PriceService()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            price = await service._get_binance_price("BTC/USD")

        assert price is None


class TestPriceServiceTicker24h:
    """Tests pour get_ticker_24h."""

    @pytest.mark.asyncio
    async def test_ticker_returns_all_fields(self):
        """Vérifie que le ticker 24h retourne tous les champs."""
        service = PriceService()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "lastPrice": "84000.00",
            "priceChangePercent": "2.35",
            "highPrice": "85000.00",
            "lowPrice": "83000.00",
            "volume": "12345.678",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            ticker = await service.get_ticker_24h("BTC/USD")

        assert ticker is not None
        assert ticker["price"] == 84000.0
        assert ticker["change_24h_pct"] == 2.35
        assert ticker["high_24h"] == 85000.0
        assert ticker["low_24h"] == 83000.0
        assert ticker["volume_24h"] == 12345.678
        assert ticker["source"] == "binance"

    @pytest.mark.asyncio
    async def test_ticker_returns_none_on_error(self):
        """Retourne None si Binance 24h est inaccessible."""
        service = PriceService()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            ticker = await service.get_ticker_24h("BTC/USD")

        assert ticker is None


class TestPriceServiceDbFallback:
    """Tests pour _get_db_price."""

    def test_db_returns_latest_close_price(self, db_session):
        """Retourne le close_price du candle le plus récent."""
        from app.models.candle import Candle

        # Ajouter deux candles
        c1 = Candle(
            symbol="BTC/USD", timeframe="4h",
            timestamp=datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc),
            open_price=82000, high_price=83000, low_price=81000,
            close_price=82500, volume=100, source="test",
        )
        c2 = Candle(
            symbol="BTC/USD", timeframe="4h",
            timestamp=datetime(2024, 1, 15, 4, 0, tzinfo=timezone.utc),
            open_price=82500, high_price=84000, low_price=82000,
            close_price=83800, volume=200, source="test",
        )
        db_session.add_all([c1, c2])
        db_session.commit()

        price = PriceService._get_db_price("BTC/USD", db_session)
        assert price == 83800  # Le plus récent

    def test_db_returns_none_when_empty(self, db_session):
        """Retourne None si pas de candles en base."""
        price = PriceService._get_db_price("BTC/USD", db_session)
        assert price is None


class TestPriceServiceEndpoint:
    """Tests de l'endpoint /market/price via TestClient."""

    def test_price_endpoint_with_binance_mock(self, client):
        """L'endpoint /market/price retourne un prix Binance."""
        with patch(
            "app.api.routes.market.price_service.get_price",
            new_callable=AsyncMock,
            return_value=84000.0,
        ), patch(
            "app.api.routes.market.price_service.get_ticker_24h",
            new_callable=AsyncMock,
            return_value={
                "price": 84000.0,
                "change_24h_pct": 1.5,
                "high_24h": 85000.0,
                "low_24h": 83000.0,
                "volume_24h": 10000.0,
                "source": "binance",
            },
        ):
            resp = client.get("/market/price")

        assert resp.status_code == 200
        data = resp.json()
        assert data["price"] == 84000.0
        assert data["source"] == "binance"
        assert "change_24h_pct" in data
        assert "high_24h" in data
        assert "timestamp" in data

    def test_price_endpoint_returns_502_when_unavailable(self, client):
        """L'endpoint retourne 502 si aucune source disponible."""
        with patch(
            "app.api.routes.market.price_service.get_price",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/market/price")

        assert resp.status_code == 502

    def test_price_endpoint_without_ticker(self, client):
        """L'endpoint fonctionne même si le ticker 24h échoue."""
        with patch(
            "app.api.routes.market.price_service.get_price",
            new_callable=AsyncMock,
            return_value=84000.0,
        ), patch(
            "app.api.routes.market.price_service.get_ticker_24h",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/market/price")

        assert resp.status_code == 200
        data = resp.json()
        assert data["price"] == 84000.0
        assert "change_24h_pct" not in data

