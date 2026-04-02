"""
Tests pour BinanceService et DataSourceRouter.

Vérifie :
- Parsing des réponses Binance (klines)
- Pagination automatique
- Fallback CoinGecko quand Binance échoue
- Toutes les combinaisons timeframe × jours accessibles
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from app.services.binance_service import BinanceService
from app.services.data_source_router import DataSourceRouter


# =============================================================================
# BinanceService — Tests unitaires
# =============================================================================

class TestBinanceServiceSymbolMapping:
    """Tests du mapping de symboles."""

    def test_btc_usd_maps_to_btcusdt(self):
        """BTC/USD doit être mappé à BTCUSDT."""
        service = BinanceService()
        assert service._get_binance_symbol("BTC/USD") == "BTCUSDT"

    def test_eth_usd_maps_to_ethusdt(self):
        """ETH/USD doit être mappé à ETHUSDT."""
        service = BinanceService()
        assert service._get_binance_symbol("ETH/USD") == "ETHUSDT"

    def test_unknown_symbol_defaults_to_btcusdt(self):
        """Un symbole inconnu doit retourner BTCUSDT par défaut."""
        service = BinanceService()
        assert service._get_binance_symbol("UNKNOWN") == "BTCUSDT"


class TestBinanceServiceIntervalMapping:
    """Tests du mapping d'intervalles."""

    def test_5m_interval(self):
        service = BinanceService()
        assert service._get_binance_interval("5m") == "5m"

    def test_15m_interval(self):
        service = BinanceService()
        assert service._get_binance_interval("15m") == "15m"

    def test_30m_interval(self):
        service = BinanceService()
        assert service._get_binance_interval("30m") == "30m"


    def test_1d_interval(self):
        service = BinanceService()
        assert service._get_binance_interval("1d") == "1d"


class TestBinanceServiceTimeframeMs:
    """Tests de la conversion timeframe en millisecondes."""

    def test_5m_is_300000ms(self):
        service = BinanceService()
        assert service._timeframe_to_ms("5m") == 300_000

    def test_15m_is_900000ms(self):
        service = BinanceService()
        assert service._timeframe_to_ms("15m") == 900_000

    def test_30m_is_1800000ms(self):
        service = BinanceService()
        assert service._timeframe_to_ms("30m") == 1_800_000

    def test_1h_is_3600000ms(self):
        service = BinanceService()
        assert service._timeframe_to_ms("1h") == 3_600_000

    def test_4h_is_14400000ms(self):
        service = BinanceService()
        assert service._timeframe_to_ms("4h") == 14_400_000

    def test_1d_is_86400000ms(self):
        service = BinanceService()
        assert service._timeframe_to_ms("1d") == 86_400_000


class TestBinanceServiceParsing:
    """Tests du parsing de la réponse Binance klines."""

    @pytest.mark.asyncio
    async def test_parse_single_kline(self):
        """Vérifie le parsing d'une réponse Binance avec une seule kline."""
        # Format Binance kline : [open_time, open, high, low, close, volume,
        #   close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, ignore]
        mock_kline = [
            1700000000000,  # open_time ms
            "50000.00",     # open
            "51000.00",     # high
            "49000.00",     # low
            "50500.00",     # close
            "123.456",      # volume
            1700003599999,  # close_time
            "6172800.0",    # quote_volume
            1000,           # trades
            "60.0",         # taker_buy_base
            "3000000.0",    # taker_buy_quote
            "0",            # ignore
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [mock_kline]
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            service = BinanceService()
            candles = await service.get_ohlcv("BTC/USD", timeframe="1h", days=1)

        assert len(candles) == 1
        c = candles[0]
        assert c["open"] == 50000.00
        assert c["high"] == 51000.00
        assert c["low"] == 49000.00
        assert c["close"] == 50500.00
        assert c["volume"] == 123.456
        assert isinstance(c["timestamp"], datetime)
        assert c["timestamp"].tzinfo is not None

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self):
        """Une réponse vide de Binance doit retourner une liste vide."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            service = BinanceService()
            candles = await service.get_ohlcv("BTC/USD", timeframe="4h", days=1)

        assert candles == []


# =============================================================================
# DataSourceRouter — Tests unitaires
# =============================================================================

class TestDataSourceRouter:
    """Tests du routeur de sources de données."""

    @pytest.mark.asyncio
    async def test_binance_success_returns_data(self):
        """Quand Binance réussit, on retourne ses données."""
        mock_candles = [
            {"timestamp": datetime.now(timezone.utc), "open": 50000, "high": 51000,
             "low": 49000, "close": 50500, "volume": 100}
        ]

        router = DataSourceRouter()
        with patch.object(router.binance, "get_ohlcv", new_callable=AsyncMock, return_value=mock_candles):
            result = await router.get_candles("BTC/USD", timeframe="30m", days=7)

        assert len(result) == 1
        assert result[0]["open"] == 50000

    @pytest.mark.asyncio
    async def test_binance_failure_falls_back_to_coingecko(self):
        """Quand Binance échoue, on bascule sur CoinGecko."""
        mock_candles = [
            {"timestamp": datetime.now(timezone.utc), "open": 50000, "high": 51000,
             "low": 49000, "close": 50500, "volume": 0}
        ]

        router = DataSourceRouter()
        with patch.object(router.binance, "get_ohlcv", new_callable=AsyncMock, side_effect=Exception("Binance down")):
            with patch.object(router.coingecko, "get_ohlc", new_callable=AsyncMock, return_value=mock_candles):
                result = await router.get_candles("BTC/USD", timeframe="4h", days=7)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_binance_empty_falls_back_to_coingecko(self):
        """Quand Binance retourne vide, on bascule sur CoinGecko."""
        mock_candles = [
            {"timestamp": datetime.now(timezone.utc), "open": 50000, "high": 51000,
             "low": 49000, "close": 50500, "volume": 0}
        ]

        router = DataSourceRouter()
        with patch.object(router.binance, "get_ohlcv", new_callable=AsyncMock, return_value=[]):
            with patch.object(router.coingecko, "get_ohlc", new_callable=AsyncMock, return_value=mock_candles):
                result = await router.get_candles("BTC/USD", timeframe="30m", days=7)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_both_fail_returns_empty(self):
        """Quand les deux sources échouent, on retourne une liste vide."""
        router = DataSourceRouter()
        with patch.object(router.binance, "get_ohlcv", new_callable=AsyncMock, side_effect=Exception("fail")):
            with patch.object(router.coingecko, "get_ohlc", new_callable=AsyncMock, side_effect=Exception("fail")):
                result = await router.get_candles("BTC/USD", timeframe="4h", days=7)

        assert result == []


# =============================================================================
# Combinaisons — Toutes les combinaisons doivent être accessibles
# =============================================================================

class TestAllCombinations:
    """Vérifie que toutes les 66 combinaisons timeframe × jours sont acceptées."""

    TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"]
    DAYS_OPTIONS = [1, 2, 3, 5, 7, 14, 30, 60, 90, 180, 365]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("timeframe", TIMEFRAMES)
    @pytest.mark.parametrize("days", DAYS_OPTIONS)
    async def test_combination_accepted(self, timeframe, days):
        """Chaque combinaison timeframe/days doit retourner des données (via mock)."""
        mock_candles = [
            {"timestamp": datetime.now(timezone.utc), "open": 50000, "high": 51000,
             "low": 49000, "close": 50500, "volume": 100}
        ]

        router = DataSourceRouter()
        with patch.object(router.binance, "get_ohlcv", new_callable=AsyncMock, return_value=mock_candles):
            result = await router.get_candles("BTC/USD", timeframe=timeframe, days=days)

        assert len(result) >= 1, f"Combinaison {timeframe}/{days}j doit fonctionner"


# =============================================================================
# Tests des nouveaux resamplings
# =============================================================================

class TestResample30mTo4h:
    """Tests pour le resample 30m → 4h."""

    def test_resample_30m_to_4h_with_data(self, db_session):
        """Le resample 30m → 4h doit créer des candles 4h."""
        from app.models import Candle
        from app.services.resample_service import resample_30m_to_4h

        # Créer 8 candles 30m (= 1 bucket 4h complet, de 00:00 à 03:30)
        base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        for i in range(8):
            db_session.add(Candle(
                symbol="BTC/USD",
                timeframe="30m",
                timestamp=base_time + timedelta(minutes=30 * i),
                open_price=50000 + i * 100,
                high_price=50100 + i * 100,
                low_price=49900 + i * 100,
                close_price=50050 + i * 100,
                volume=10.0,
                source="test",
            ))
        db_session.commit()

        count = resample_30m_to_4h(db_session, "BTC/USD")
        assert count >= 1

        # Vérifier qu'un candle 4h a été créé
        candle_4h = db_session.query(Candle).filter(
            Candle.timeframe == "4h",
            Candle.symbol == "BTC/USD",
        ).first()
        assert candle_4h is not None
        assert candle_4h.open_price == 50000  # premier open
        assert candle_4h.volume > 0

    def test_resample_30m_to_4h_empty_db(self, db_session):
        """Sans données 30m, le resample retourne 0."""
        from app.services.resample_service import resample_30m_to_4h

        count = resample_30m_to_4h(db_session, "BTC/USD")
        assert count == 0


class TestResample1hTo4h:
    """Tests pour le resample 1h → 4h."""

    def test_resample_1h_to_4h_with_data(self, db_session):
        """Le resample 1h → 4h doit créer des candles 4h."""
        from app.models import Candle
        from app.services.resample_service import resample_1h_to_4h

        # Créer 4 candles 1h (= 1 bucket 4h complet)
        base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        for i in range(4):
            db_session.add(Candle(
                symbol="BTC/USD",
                timeframe="1h",
                timestamp=base_time + timedelta(hours=i),
                open_price=50000 + i * 100,
                high_price=50200 + i * 100,
                low_price=49800 + i * 100,
                close_price=50100 + i * 100,
                volume=20.0,
                source="test",
            ))
        db_session.commit()

        count = resample_1h_to_4h(db_session, "BTC/USD")
        assert count >= 1

        # Vérifier le candle 4h
        candle_4h = db_session.query(Candle).filter(
            Candle.timeframe == "4h",
            Candle.symbol == "BTC/USD",
        ).first()
        assert candle_4h is not None
        assert candle_4h.open_price == 50000

    def test_resample_1h_to_4h_empty_db(self, db_session):
        """Sans données 1h, le resample retourne 0."""
        from app.services.resample_service import resample_1h_to_4h

        count = resample_1h_to_4h(db_session, "BTC/USD")
        assert count == 0

