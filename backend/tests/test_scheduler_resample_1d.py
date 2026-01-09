"""
Tests pour l'intégration du resample 4h→1d dans le scheduler.

PHASE 2A: Vérifie que:
1. Le resample est appelé après le fetch 4h
2. Les candles 1d sont créés en DB
3. last_result contient resample.1d
4. Le job reste idempotent
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

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
def mock_settings():
    """Mock des settings scheduler."""
    mock = MagicMock()
    mock.scheduler_enabled = True
    mock.scheduler_interval_minutes = 5
    mock.scheduler_symbol = "BTC/USD"
    mock.scheduler_days = 7  # 7 jours = timeframe 4h
    return mock


def generate_4h_candles(start_date: datetime, num_days: int = 1) -> list[dict]:
    """
    Génère des candles 4h pour simulation CoinGecko.

    6 candles 4h = 1 jour complet (00:00, 04:00, 08:00, 12:00, 16:00, 20:00)
    """
    candles = []
    current = start_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

    base_price = 90000.0

    for day in range(num_days):
        for hour in range(0, 24, 4):
            ts = current + timedelta(days=day, hours=hour)
            price = base_price + (day * 100) + (hour * 10)  # Prix croissant

            candles.append({
                "timestamp": ts,
                "open": price,
                "high": price + 50,
                "low": price - 50,
                "close": price + 20,
                "volume": 1000000.0 + (hour * 10000),
            })

    return candles


# =========================
# Tests Resample Function
# =========================

class TestRunResample4hTo1d:
    """Tests pour _run_resample_4h_to_1d."""

    def test_resample_creates_1d_candles(self, test_db):
        """Le resample crée des candles 1d à partir de candles 4h."""
        symbol = "BTC/USD"
        start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        # Insérer 6 candles 4h (1 jour complet)
        candles_4h = generate_4h_candles(start_date, num_days=1)

        for c in candles_4h:
            candle = Candle(
                symbol=symbol,
                timeframe="4h",
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

        # Vérifier 6 candles 4h
        count_4h = test_db.query(Candle).filter(Candle.timeframe == "4h").count()
        assert count_4h == 6

        # Appeler le resample
        min_ts = candles_4h[0]["timestamp"]
        max_ts = candles_4h[-1]["timestamp"]

        result = sched._run_resample_4h_to_1d(
            db=test_db,
            symbol=symbol,
            min_ts=min_ts,
            max_ts=max_ts,
        )

        test_db.commit()

        # Vérifier le résultat
        assert result["1d"] >= 1
        assert "error" not in result

        # Vérifier qu'au moins 1 candle 1d existe
        count_1d = test_db.query(Candle).filter(Candle.timeframe == "1d").count()
        assert count_1d >= 1

        # Vérifier les valeurs OHLCV du candle 1d
        candle_1d = test_db.query(Candle).filter(Candle.timeframe == "1d").first()
        assert candle_1d is not None
        assert candle_1d.symbol == symbol
        assert candle_1d.source == "resample_4h"

    def test_resample_with_none_timestamps_skips(self, test_db):
        """Le resample est skippé si min_ts ou max_ts est None."""
        result = sched._run_resample_4h_to_1d(
            db=test_db,
            symbol="BTC/USD",
            min_ts=None,
            max_ts=None,
        )

        assert result["1d"] == 0
        assert result.get("skipped") is True

    def test_resample_idempotent(self, test_db):
        """Le resample est idempotent (upsert, pas de duplication)."""
        symbol = "BTC/USD"
        start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        # Insérer 6 candles 4h
        candles_4h = generate_4h_candles(start_date, num_days=1)
        for c in candles_4h:
            candle = Candle(
                symbol=symbol,
                timeframe="4h",
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

        min_ts = candles_4h[0]["timestamp"]
        max_ts = candles_4h[-1]["timestamp"]

        # Premier resample
        result1 = sched._run_resample_4h_to_1d(test_db, symbol, min_ts, max_ts)
        test_db.commit()
        count_after_first = test_db.query(Candle).filter(Candle.timeframe == "1d").count()

        # Second resample (doit être idempotent)
        result2 = sched._run_resample_4h_to_1d(test_db, symbol, min_ts, max_ts)
        test_db.commit()
        count_after_second = test_db.query(Candle).filter(Candle.timeframe == "1d").count()

        # Le nombre de candles 1d ne doit pas augmenter
        assert count_after_first == count_after_second


# =========================
# Tests Job Integration
# =========================
@pytest.fixture
def mock_session():
    """
    Fixture manquante: mock SessionLocal pour éviter d'ouvrir une vraie DB
    et stabiliser les tests de scheduler.
    """
    with patch("app.tasks.scheduler.SessionLocal") as mock_session_local:
        db = MagicMock()
        mock_session_local.return_value = db
        yield db


class TestFetchCandlesJobWithResample:
    """Tests pour fetch_candles_job avec resample intégré."""

    def test_job_includes_resample_in_result(self, monkeypatch, mock_settings):
        """Le job inclut resample.1d dans last_result."""
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        # Mock SessionLocal avec une vraie DB SQLite
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        monkeypatch.setattr(sched, "SessionLocal", TestSessionLocal)

        # Mock _run_coroutine pour simuler fetch CoinGecko
        start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def fake_run(coro):
            # Simuler l'insertion de 6 candles 4h dans la vraie DB
            db = TestSessionLocal()
            candles_4h = generate_4h_candles(start_date, num_days=1)

            min_ts = None
            max_ts = None

            for c in candles_4h:
                if min_ts is None or c["timestamp"] < min_ts:
                    min_ts = c["timestamp"]
                if max_ts is None or c["timestamp"] > max_ts:
                    max_ts = c["timestamp"]

                candle = Candle(
                    symbol="BTC/USD",
                    timeframe="4h",
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
                "days": 7,
                "timeframe": "4h",
                "fetched": 6,
                "inserted": 6,
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
        assert "resample" in last_result
        assert "1d" in last_result["resample"]
        assert last_result["resample"]["1d"] >= 0  # Peut être 0 si la fenêtre ne couvre pas un jour complet

    def test_job_30m_does_not_resample(self, mock_settings, mock_session):
        """
        Vérifie que le job 30m n'exécute PAS resample_4h_to_1d.
        (Il fait resample_30m_to_1h à la place)
        """
        from app.tasks.scheduler import fetch_candles_30m_job, scheduler_state

        with patch("app.tasks.scheduler._run_coroutine") as mock_run:
            mock_run.return_value = {
                "status": "success",
                "fetched": 48,
                "inserted": 48,
                "updated": 0,
                "duplicates": 0,
                "min_ts": datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
                "max_ts": datetime(2024, 1, 1, 23, 30, tzinfo=timezone.utc),
            }

            with patch("app.tasks.scheduler.resample_4h_to_1d") as mock_resample_4h:
                with patch("app.tasks.scheduler.resample_30m_to_1h", return_value=2):
                    fetch_candles_30m_job()

                    # Le job 30m ne doit PAS appeler resample_4h_to_1d
                    mock_resample_4h.assert_not_called()

                    # Vérifier que le résultat a le contrat correct
                    last_result = scheduler_state["jobs"]["30m"]["last_result"]
                    assert last_result["resample"]["1d"] == 0  # Pas de resample 1d
                    assert last_result["resample"]["1h"] == 2  # Resample 1h fait

    def test_job_resample_error_does_not_fail_job(self, monkeypatch, mock_settings):
        """Une erreur dans le resample ne fait pas échouer le job principal."""
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
                "updated": 2,
                "duplicates": 35,
                "min_ts": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "max_ts": datetime(2026, 1, 7, tzinfo=timezone.utc),
            }

        monkeypatch.setattr(sched, "_run_coroutine", fake_run)

        # Mock resample pour qu'il échoue
        def fake_resample(*args, **kwargs):
            raise RuntimeError("Resample DB error")

        monkeypatch.setattr(sched, "resample_4h_to_1d", fake_resample)

        # Exécuter le job - ne doit pas lever d'exception
        sched.fetch_candles_job()

        # Vérifications
        status = sched.get_status()
        last_result = status["last_result"]

        # Le job doit quand même être success pour le fetch
        assert last_result["status"] == "success"
        # resample doit contenir l'erreur
        assert last_result["resample"]["1d"] == 0
        assert "error" in last_result["resample"]
        assert "Resample DB error" in last_result["resample"]["error"]


# =========================
# Tests OHLCV Aggregation
# =========================

class TestOhlcvAggregation:
    """Tests pour vérifier les règles OHLCV du resample."""

    def test_1d_candle_has_correct_ohlcv(self, test_db):
        """Le candle 1d a les bonnes valeurs OHLCV agrégées."""
        symbol = "BTC/USD"
        start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

        # Créer 6 candles 4h avec des valeurs connues
        candles_data = [
            # (hour, open, high, low, close, volume)
            (0,  90000, 90500, 89800, 90200, 1000),  # Premier du jour → Open
            (4,  90200, 91000, 90000, 90800, 1200),  # High max = 91000
            (8,  90800, 90900, 89500, 89600, 800),   # Low min = 89500
            (12, 89600, 90200, 89400, 90100, 900),   # Low min = 89400
            (16, 90100, 90300, 89900, 90000, 1100),
            (20, 90000, 90600, 89700, 90400, 1500),  # Dernier du jour → Close
        ]

        for hour, o, h, l, c, v in candles_data:
            candle = Candle(
                symbol=symbol,
                timeframe="4h",
                timestamp=start_date + timedelta(hours=hour),
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
        min_ts = start_date
        max_ts = start_date + timedelta(hours=20)

        sched._run_resample_4h_to_1d(test_db, symbol, min_ts, max_ts)
        test_db.commit()

        # Vérifier le candle 1d
        candle_1d = test_db.query(Candle).filter(
            Candle.timeframe == "1d",
            Candle.timestamp == start_date
        ).first()

        assert candle_1d is not None

        # Vérifications OHLCV
        assert candle_1d.open_price == 90000   # Premier open
        assert candle_1d.high_price == 91000   # Max des highs (04:00)
        assert candle_1d.low_price == 89400    # Min des lows (12:00)
        assert candle_1d.close_price == 90400  # Dernier close (20:00)
        assert candle_1d.volume == 6500        # Somme des volumes