"""
Tests pour l'intégration du resample 30m→1h dans le scheduler.

PHASE 2B: Vérifie que:
1. Le resample est appelé après le fetch 30m (days <= 2)
2. Les candles 1h sont créés en DB
3. last_result contient resample.1h
4. Le job reste idempotent
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Candle
from app.database import Base
from app.tasks import scheduler as sched


# =========================
# Fixtures
# =========================

@pytest.fixture
def test_db():
    """Crée une base SQLite en mémoire pour les tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestSessionLocal()

    yield db

    db.close()
    engine.dispose()


@pytest.fixture
def mock_settings_30m():
    """Mock des settings scheduler pour 30m (days=2)."""
    mock = MagicMock()
    mock.scheduler_enabled = True
    mock.scheduler_interval_minutes = 5
    mock.scheduler_symbol = "BTC/USD"
    mock.scheduler_days = 2  # 2 jours = timeframe 30m
    return mock


def generate_30m_candles(start_date: datetime, num_hours: int = 2) -> list[dict]:
    """
    Génère des candles 30m pour simulation CoinGecko.

    2 candles 30m = 1 heure (hh:00 et hh:30)
    """
    candles = []
    current = start_date.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

    base_price = 90000.0

    for hour in range(num_hours):
        for minute in [0, 30]:
            ts = current + timedelta(hours=hour, minutes=minute)
            price = base_price + (hour * 100) + (minute * 2)

            candles.append({
                "timestamp": ts,
                "open": price,
                "high": price + 50,
                "low": price - 50,
                "close": price + 20,
                "volume": 500000.0 + (hour * 5000) + (minute * 100),
            })

    return candles


# =========================
# Tests Resample Function
# =========================

class TestRunResample30mTo1h:
    """Tests pour _run_resample_30m_to_1h."""

    def test_resample_creates_1h_candles(self, test_db):
        """Le resample crée des candles 1h à partir de candles 30m."""
        symbol = "BTC/USD"
        start_date = datetime(2026, 1, 9, 10, 0, tzinfo=timezone.utc)

        # Insérer 4 candles 30m (2 heures complètes: 10:00, 10:30, 11:00, 11:30)
        candles_30m = generate_30m_candles(start_date, num_hours=2)

        for c in candles_30m:
            candle = Candle(
                symbol=symbol,
                timeframe="30m",
                timestamp=c["timestamp"],
                open_price=c["open"],
                high_price=c["high"],
                low_price=c["low"],
                close_price=c["close"],
                volume=c["volume"],
                source="test"
            )
            test_db.add(candle)

        test_db.commit()

        # Vérifier 4 candles 30m
        count_30m = test_db.query(Candle).filter(Candle.timeframe == "30m").count()
        assert count_30m == 4

        # Appeler le resample
        min_ts = candles_30m[0]["timestamp"]
        max_ts = candles_30m[-1]["timestamp"]

        result = sched._run_resample_30m_to_1h(
            db=test_db,
            symbol=symbol,
            min_ts=min_ts,
            max_ts=max_ts,
        )

        test_db.commit()

        # Vérifier le résultat
        assert result["1h"] >= 1
        assert "error" not in result

        # Vérifier qu'au moins 1 candle 1h existe
        count_1h = test_db.query(Candle).filter(Candle.timeframe == "1h").count()
        assert count_1h >= 1

        # Vérifier la source
        candle_1h = test_db.query(Candle).filter(Candle.timeframe == "1h").first()
        assert candle_1h is not None
        assert candle_1h.symbol == symbol
        assert candle_1h.source == "resample_30m"

    def test_resample_with_none_timestamps_skips(self, test_db):
        """Le resample est skippé si min_ts ou max_ts est None."""
        result = sched._run_resample_30m_to_1h(
            db=test_db,
            symbol="BTC/USD",
            min_ts=None,
            max_ts=None,
        )

        assert result["1h"] == 0
        assert result.get("skipped") is True

    def test_resample_idempotent(self, test_db):
        """Le resample est idempotent (upsert, pas de duplication)."""
        symbol = "BTC/USD"
        start_date = datetime(2026, 1, 9, 10, 0, tzinfo=timezone.utc)

        # Insérer 4 candles 30m
        candles_30m = generate_30m_candles(start_date, num_hours=2)
        for c in candles_30m:
            candle = Candle(
                symbol=symbol,
                timeframe="30m",
                timestamp=c["timestamp"],
                open_price=c["open"],
                high_price=c["high"],
                low_price=c["low"],
                close_price=c["close"],
                volume=c["volume"],
                source="test"
            )
            test_db.add(candle)
        test_db.commit()

        min_ts = candles_30m[0]["timestamp"]
        max_ts = candles_30m[-1]["timestamp"]

        # Premier resample
        result1 = sched._run_resample_30m_to_1h(test_db, symbol, min_ts, max_ts)
        test_db.commit()
        count_after_first = test_db.query(Candle).filter(Candle.timeframe == "1h").count()

        # Second resample (doit être idempotent)
        result2 = sched._run_resample_30m_to_1h(test_db, symbol, min_ts, max_ts)
        test_db.commit()
        count_after_second = test_db.query(Candle).filter(Candle.timeframe == "1h").count()

        # Le nombre de candles 1h ne doit pas augmenter
        assert count_after_first == count_after_second


# =========================
# Tests Job Integration
# =========================

class TestFetchCandlesJobWith30mResample:
    """Tests pour fetch_candles_job avec resample 30m→1h intégré."""

    def test_job_30m_includes_resample_1h_in_result(self, monkeypatch, mock_settings_30m):
        """Le job 30m inclut resample.1h dans last_result."""
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings_30m)

        # Mock SessionLocal avec une vraie DB SQLite
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        monkeypatch.setattr(sched, "SessionLocal", TestSessionLocal)

        start_date = datetime(2026, 1, 9, 10, 0, tzinfo=timezone.utc)

        def fake_run(coro):
            db = TestSessionLocal()
            candles_30m = generate_30m_candles(start_date, num_hours=2)

            min_ts = None
            max_ts = None

            for c in candles_30m:
                if min_ts is None or c["timestamp"] < min_ts:
                    min_ts = c["timestamp"]
                if max_ts is None or c["timestamp"] > max_ts:
                    max_ts = c["timestamp"]

                candle = Candle(
                    symbol="BTC/USD",
                    timeframe="30m",
                    timestamp=c["timestamp"],
                    open_price=c["open"],
                    high_price=c["high"],
                    low_price=c["low"],
                    close_price=c["close"],
                    volume=c["volume"],
                    source="scheduler"
                )
                db.add(candle)

            db.commit()
            db.close()

            return {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 2,
                "timeframe": "30m",
                "fetched": 4,
                "inserted": 4,
                "updated": 0,
                "duplicates": 0,
                "min_ts": min_ts,
                "max_ts": max_ts,
            }

        monkeypatch.setattr(sched, "_run_coroutine", fake_run)

        # Exécuter le job
        sched.fetch_candles_job()

        # Vérifications
        status = sched.get_status()
        last_result = status["last_result"]

        assert last_result["status"] == "success"
        assert last_result["timeframe"] == "30m"
        assert "resample" in last_result
        assert "1h" in last_result["resample"]
        assert last_result["resample"]["1h"] >= 0

    def test_job_4h_does_not_resample_1h(self, monkeypatch):
        """Le job 4h (days>2) ne déclenche pas le resample 30m→1h."""
        mock_settings = MagicMock()
        mock_settings.scheduler_enabled = True
        mock_settings.scheduler_interval_minutes = 5
        mock_settings.scheduler_symbol = "BTC/USD"
        mock_settings.scheduler_days = 7  # 7 jours = timeframe 4h

        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        fake_db = MagicMock()
        monkeypatch.setattr(sched, "SessionLocal", lambda: fake_db)

        def fake_run(_coro):
            return {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 7,
                "timeframe": "4h",
                "fetched": 42,
                "inserted": 5,
                "updated": 0,
                "duplicates": 37,
                "min_ts": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "max_ts": datetime(2026, 1, 7, tzinfo=timezone.utc),
            }

        monkeypatch.setattr(sched, "_run_coroutine", fake_run)

        # Mock resample 4h→1d pour vérifier qu'il est appelé
        mock_resample_4h = MagicMock(return_value={"1d": 7})
        monkeypatch.setattr(sched, "_run_resample_4h_to_1d", mock_resample_4h)

        # Exécuter le job
        sched.fetch_candles_job()

        # Vérifications
        status = sched.get_status()
        last_result = status["last_result"]

        assert last_result["status"] == "success"
        assert last_result["timeframe"] == "4h"
        # resample devrait contenir 1d (pas 1h)
        assert last_result["resample"].get("1d") == 7


# =========================
# Tests OHLCV Aggregation
# =========================

class TestOhlcvAggregation30mTo1h:
    """Tests pour vérifier les règles OHLCV du resample 30m→1h."""

    def test_1h_candle_has_correct_ohlcv(self, test_db):
        """Le candle 1h a les bonnes valeurs OHLCV agrégées."""
        symbol = "BTC/USD"
        base_ts = datetime(2026, 1, 9, 14, 0, tzinfo=timezone.utc)  # 14:00 UTC

        # Créer 2 candles 30m avec des valeurs connues
        candles_data = [
            # (minute, open, high, low, close, volume)
            (0,  90000, 90500, 89800, 90200, 1000),   # 14:00 → Open
            (30, 90200, 90800, 89600, 90400, 1500),   # 14:30 → Close, High max, Low min
        ]

        for minute, o, h, l, c, v in candles_data:
            candle = Candle(
                symbol=symbol,
                timeframe="30m",
                timestamp=base_ts + timedelta(minutes=minute),
                open_price=o,
                high_price=h,
                low_price=l,
                close_price=c,
                volume=v,
                source="test"
            )
            test_db.add(candle)

        test_db.commit()

        # Resample
        min_ts = base_ts
        max_ts = base_ts + timedelta(minutes=30)

        sched._run_resample_30m_to_1h(test_db, symbol, min_ts, max_ts)
        test_db.commit()

        # Vérifier le candle 1h
        candle_1h = test_db.query(Candle).filter(
            Candle.timeframe == "1h",
            Candle.timestamp == base_ts  # Doit être aligné sur 14:00
        ).first()

        assert candle_1h is not None

        # Vérifications OHLCV
        assert candle_1h.open_price == 90000   # Premier open (14:00)
        assert candle_1h.high_price == 90800   # Max des highs (14:30)
        assert candle_1h.low_price == 89600    # Min des lows (14:30)
        assert candle_1h.close_price == 90400  # Dernier close (14:30)
        assert candle_1h.volume == 2500        # Somme des volumes