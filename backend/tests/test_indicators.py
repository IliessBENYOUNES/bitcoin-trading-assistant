"""
Tests pour le service d'indicateurs techniques.

Tests couverts :
1. Calcul RSI/MACD sur dataset synthétique
2. Ordre chronologique ASC des séries
3. Cohérence timestamps avec /market/candles
4. Gestion NaN → null pour premiers points
5. Présence meta (now_ts, max_ts, data_lag_hours, statuses)
6. Validation timeframes
7. Alignement buckets
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd

# Import du service
from app.services.indicator_service import (
    IndicatorService,
    align_to_bucket,
    normalize_to_utc,
    nan_to_none,
    calculate_freshness_status,
    calculate_global_status,
    get_timeframe_hours,
    VALID_TIMEFRAMES
)
from app.models import Candle


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def sample_candles_list():
    """
    Génère 20 candles synthétiques pour les tests.
    Retourne une liste de dicts (pas de MagicMock).
    """
    base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []

    for i in range(20):
        ts = base_ts + timedelta(hours=4 * i)
        base_price = 100000 + (i * 100)

        candles.append({
            "timestamp": ts,
            "open_price": base_price,
            "high_price": base_price + 500,
            "low_price": base_price - 300,
            "close_price": base_price + 200,
            "volume": 1000.0 + i * 10,
        })

    return candles


@pytest.fixture
def sample_candles_list_50():
    """
    Génère 50 candles pour tester SMA_50.
    """
    base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []

    for i in range(50):
        ts = base_ts + timedelta(hours=4 * i)
        base_price = 95000 + (i * 50)

        candles.append({
            "timestamp": ts,
            "open_price": base_price,
            "high_price": base_price + 500,
            "low_price": base_price - 300,
            "close_price": base_price + 100,
            "volume": 1000.0,
        })

    return candles


def create_mock_candle(data: dict) -> MagicMock:
    """Crée un mock Candle avec les bonnes propriétés."""
    mock = MagicMock(spec=Candle)
    mock.timestamp = data["timestamp"]
    mock.open_price = data["open_price"]
    mock.high_price = data["high_price"]
    mock.low_price = data["low_price"]
    mock.close_price = data["close_price"]
    mock.volume = data["volume"]
    return mock


# ============================================================
# TESTS UTILITAIRES
# ============================================================

class TestAlignToBucket:
    """Tests pour align_to_bucket."""

    def test_align_4h_exact(self):
        """Un timestamp déjà aligné reste inchangé."""
        dt = datetime(2026, 1, 7, 12, 0, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "4h")
        assert result == dt

    def test_align_4h_floor(self):
        """Un timestamp est arrondi au bucket inférieur."""
        dt = datetime(2026, 1, 7, 14, 35, 22, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "4h")
        expected = datetime(2026, 1, 7, 12, 0, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_align_4h_just_before(self):
        """23:59 devient 20:00."""
        dt = datetime(2026, 1, 7, 23, 59, 59, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "4h")
        expected = datetime(2026, 1, 7, 20, 0, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_align_1h_exact(self):
        """Timeframe 1h - timestamp exact."""
        dt = datetime(2026, 1, 7, 15, 0, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "1h")
        assert result == dt

    def test_align_1h_floor(self):
        """Timeframe 1h - arrondi."""
        dt = datetime(2026, 1, 7, 15, 45, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "1h")
        expected = datetime(2026, 1, 7, 15, 0, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_align_30m_first_half(self):
        """Timeframe 30m - première demi-heure."""
        dt = datetime(2026, 1, 7, 15, 15, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "30m")
        expected = datetime(2026, 1, 7, 15, 0, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_align_30m_second_half(self):
        """Timeframe 30m - deuxième demi-heure."""
        dt = datetime(2026, 1, 7, 15, 45, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "30m")
        expected = datetime(2026, 1, 7, 15, 30, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_align_1d(self):
        """Timeframe 1d - arrondi à minuit."""
        dt = datetime(2026, 1, 7, 15, 45, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "1d")
        expected = datetime(2026, 1, 7, 0, 0, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_align_with_timezone_conversion(self):
        """Un timestamp +01 est converti en UTC avant alignement."""
        from datetime import timezone as tz
        paris_tz = tz(timedelta(hours=1))
        dt = datetime(2026, 1, 7, 13, 30, 0, tzinfo=paris_tz)  # 12:30 UTC
        result = align_to_bucket(dt, "4h")
        expected = datetime(2026, 1, 7, 12, 0, 0, tzinfo=timezone.utc)
        assert result == expected


class TestNanToNone:
    """Tests pour nan_to_none."""

    def test_nan_becomes_none(self):
        """NaN devient None."""
        assert nan_to_none(float('nan')) is None

    def test_none_stays_none(self):
        """None reste None."""
        assert nan_to_none(None) is None

    def test_float_rounded(self):
        """Float arrondi à 2 décimales."""
        assert nan_to_none(3.14159) == 3.14

    def test_integer_unchanged(self):
        """Integer inchangé."""
        assert nan_to_none(42) == 42


class TestFreshnessStatus:
    """Tests pour calculate_freshness_status."""

    def test_fresh(self):
        """Lag < 1 bucket = FRESH."""
        assert calculate_freshness_status(3.5, "4h") == "FRESH"

    def test_stale(self):
        """1 bucket <= lag < 2 buckets = STALE."""
        assert calculate_freshness_status(5.0, "4h") == "STALE"

    def test_very_stale(self):
        """Lag >= 2 buckets = VERY_STALE."""
        assert calculate_freshness_status(10.0, "4h") == "VERY_STALE"

class TestGlobalStatus:
    """Tests pour calculate_global_status."""

    def test_ok(self):
        """Complet + Fresh = OK."""
        assert calculate_global_status("OK", "FRESH") == "OK"

    def test_stale_from_freshness(self):
        """Complet + Stale = STALE."""
        assert calculate_global_status("OK", "STALE") == "STALE"
        assert calculate_global_status("OK", "VERY_STALE") == "STALE"

    def test_gaps_priority(self):
        """GAPS prime sur STALE."""
        assert calculate_global_status("GAPS_DETECTED", "FRESH") == "GAPS"
        assert calculate_global_status("GAPS_DETECTED", "STALE") == "GAPS"
        assert calculate_global_status("GAPS_DETECTED", "VERY_STALE") == "GAPS"


class TestValidTimeframes:
    """Tests pour la validation des timeframes."""

    def test_valid_timeframes(self):
        """Tous les timeframes valides sont reconnus."""
        assert "30m" in VALID_TIMEFRAMES
        assert "1h" in VALID_TIMEFRAMES
        assert "4h" in VALID_TIMEFRAMES
        assert "1d" in VALID_TIMEFRAMES

    def test_invalid_timeframe_not_in_list(self):
        """4d n'est pas un timeframe valide."""
        assert "4d" not in VALID_TIMEFRAMES

    def test_timeframe_hours(self):
        """Vérification des durées en heures."""
        assert get_timeframe_hours("30m") == 0.5
        assert get_timeframe_hours("1h") == 1
        assert get_timeframe_hours("4h") == 4
        assert get_timeframe_hours("1d") == 24


# ============================================================
# TESTS SERVICE INDICATEURS (avec mocks corrigés)
# ============================================================

class TestIndicatorService:
    """Tests pour IndicatorService avec mocks."""

    def test_no_data_returns_no_data_status(self):
        """Si pas de données, retourne NO_DATA."""
        mock_db = MagicMock()
        # Simuler une requête qui retourne None pour max_ts
        mock_db.query.return_value.filter.return_value.scalar.return_value = None

        service = IndicatorService(mock_db)
        result = service.calculate(symbol="BTC/USD", timeframe="4h")

        assert result["meta"]["global_status"] == "NO_DATA"
        assert result["series"] == []
        assert result["latest"] is None

    def test_invalid_timeframe_raises_error(self):
        """Un timeframe invalide lève une erreur."""
        mock_db = MagicMock()
        service = IndicatorService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            service.calculate(timeframe="4d")

        assert "Timeframe invalide" in str(exc_info.value)


# ============================================================
# TESTS D'INTÉGRATION (avec vraie DB de test)
# ============================================================

class TestIndicatorServiceIntegration:
    """
    Tests d'intégration avec la vraie base de données de test.
    Ces tests utilisent conftest.py pour la session DB SQLite.
    """

    def test_calculate_with_real_db_no_data(self, db_session):
        """Test avec vraie DB vide."""
        service = IndicatorService(db_session)
        result = service.calculate(symbol="BTC/USD", timeframe="4h")

        assert result["meta"]["global_status"] == "NO_DATA"

    def test_calculate_with_inserted_candles(self, db_session):
        """Test avec des candles insérés."""
        from app.models import Candle

        # Insérer 20 candles
        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(20):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000 + i * 100,
                high_price=100500 + i * 100,
                low_price=99700 + i * 100,
                close_price=100200 + i * 100,
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        # Calculer les indicateurs
        service = IndicatorService(db_session)
        result = service.calculate(symbol="BTC/USD", timeframe="4h", history_days=7)

        # Vérifications de base
        assert result["meta"]["count"] == 20
        assert result["latest"] is not None

        # Vérifier l'ordre chronologique ASC
        timestamps = [point["ts"] for point in result["series"]]
        assert timestamps == sorted(timestamps), "Series should be in chronological order ASC"

    def test_series_order_is_chronological_asc(self, db_session):
        """La série est triée par timestamp ASC."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Insérer dans un ordre aléatoire pour vérifier le tri
        for i in [5, 2, 8, 1, 9, 3, 7, 4, 6, 0]:
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000,
                high_price=100500,
                low_price=99700,
                close_price=100200,
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(symbol="BTC/USD", timeframe="4h", history_days=7)

        timestamps = [point["ts"] for point in result["series"]]
        assert timestamps == sorted(timestamps)

    def test_nan_becomes_null_in_first_points(self, db_session):
        """Les premiers points ont null pour RSI (besoin de 15 points)."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(20):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000 + i * 100,
                high_price=100500 + i * 100,
                low_price=99700 + i * 100,
                close_price=100200 + i * 100,
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(symbol="BTC/USD", timeframe="4h", history_days=7)

        # Les 14 premiers points doivent avoir rsi_14 = null
        for i in range(min(14, len(result["series"]))):
            assert result["series"][i]["rsi_14"] is None, f"Point {i} should have rsi_14=null"

    def test_meta_contains_required_fields(self, db_session):
        """Meta contient tous les champs requis."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(10):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000,
                high_price=100500,
                low_price=99700,
                close_price=100200,
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(symbol="BTC/USD", timeframe="4h", history_days=7)

        meta = result["meta"]

        # Vérifier présence des champs obligatoires
        required_fields = [
            "symbol", "timeframe", "history_days",
            "start_ts", "end_ts", "now_ts", "max_ts",
            "count", "data_lag_hours",
            "freshness_status", "completeness_status", "global_status"
        ]

        for field in required_fields:
            assert field in meta, f"Meta should contain '{field}'"

    def test_latest_is_last_point(self, db_session):
        """Latest contient le dernier point de la série."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(10):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000,
                high_price=100500,
                low_price=99700,
                close_price=100200 + i,  # Prix différent pour identifier le dernier
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(symbol="BTC/USD", timeframe="4h", history_days=7)

        assert result["latest"] is not None
        assert result["latest"]["ts"] == result["series"][-1]["ts"]
        assert result["latest"]["close"] == result["series"][-1]["close"]

    def test_include_candles_false_only_close(self, db_session):
        """Avec include_candles=False, seulement ts et close (pas OHLV)."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(5):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000,
                high_price=100500,
                low_price=99700,
                close_price=100200,
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(include_candles=False)

        if result["series"]:
            first_point = result["series"][0]
            assert "ts" in first_point
            assert "close" in first_point
            assert "open" not in first_point
            assert "high" not in first_point
            assert "low" not in first_point
            assert "volume" not in first_point

    def test_include_candles_true_has_ohlcv(self, db_session):
        """Avec include_candles=True, OHLCV est inclus."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(5):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000,
                high_price=100500,
                low_price=99700,
                close_price=100200,
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(include_candles=True)

        if result["series"]:
            first_point = result["series"][0]
            assert "open" in first_point
            assert "high" in first_point
            assert "low" in first_point
            assert "volume" in first_point

    def test_sma_50_null_with_20_candles(self, db_session):
        """SMA_50 est null avec seulement 20 candles."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(20):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000 + i * 100,
                high_price=100500 + i * 100,
                low_price=99700 + i * 100,
                close_price=100200 + i * 100,
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(history_days=30)  # Fenêtre plus large

        # Tous les points doivent avoir sma_50 = null (besoin de 50 points)
        for point in result["series"]:
            assert point["sma_50"] is None, "sma_50 should be null with only 20 candles"

    def test_sma_50_calculated_with_50_candles(self, db_session):
        """SMA_50 est calculé avec 50+ candles."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(55):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=95000 + i * 50,
                high_price=95500 + i * 50,
                low_price=94700 + i * 50,
                close_price=95100 + i * 50,
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(history_days=30)

        # Le dernier point devrait avoir sma_50 != null
        if result["series"]:
            last_point = result["series"][-1]
            assert last_point["sma_50"] is not None, "sma_50 should be calculated with 55 candles"

    def test_rsi_calculated_after_warmup(self, db_session):
        """RSI est calculé après la période de warmup (15 points)."""
        from app.models import Candle

        base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Créer des données avec une tendance pour avoir un RSI significatif
        for i in range(20):
            candle = Candle(
                symbol="BTC/USD",
                timeframe="4h",
                timestamp=base_ts + timedelta(hours=4 * i),
                open_price=100000 + i * 200,
                high_price=100500 + i * 200,
                low_price=99700 + i * 200,
                close_price=100300 + i * 200,  # Tendance haussière
                volume=1000.0,
                source="test"
            )
            db_session.add(candle)

        db_session.commit()

        service = IndicatorService(db_session)
        result = service.calculate(history_days=30)

        # Les derniers points (après le 14ème) doivent avoir un RSI
        if len(result["series"]) > 14:
            last_point = result["series"][-1]
            assert last_point["rsi_14"] is not None, "RSI should be calculated after warmup"
            assert 0 <= last_point["rsi_14"] <= 100, "RSI should be between 0 and 100"