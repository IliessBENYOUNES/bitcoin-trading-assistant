"""
Tests pour le scheduler.

Tests couverts:
- Configuration via Pydantic Settings
- Comportement enabled/disabled
- Job success/error (avec mocks)
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.tasks import scheduler as sched


# =========================
# Mock Settings helper
# =========================
def make_mock_settings(**kwargs):
    """Crée un mock Settings avec les valeurs par défaut."""
    defaults = {
        "scheduler_enabled": False,
        "scheduler_interval_minutes": 240,
        "scheduler_symbol": "BTC/USD",
        "scheduler_days": 7,
    }
    defaults.update(kwargs)

    mock = MagicMock()
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


# =========================
# Tests Config
# =========================
class TestReadConfig:
    """Tests pour _read_config."""

    def test_defaults(self, monkeypatch):
        """Configuration par défaut."""
        mock_settings = make_mock_settings()
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        cfg = sched._read_config()

        assert cfg["enabled"] is False
        assert cfg["interval_minutes"] == 240
        assert cfg["symbol"] == "BTC/USD"
        assert cfg["days"] == 7

    def test_custom_config(self, monkeypatch):
        """Configuration personnalisée."""
        mock_settings = make_mock_settings(
            scheduler_enabled=True,
            scheduler_interval_minutes=5,
            scheduler_symbol="ETH/USD",
            scheduler_days=14,
        )
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        cfg = sched._read_config()

        assert cfg["enabled"] is True
        assert cfg["interval_minutes"] == 5
        assert cfg["symbol"] == "ETH/USD"
        assert cfg["days"] == 14

    def test_days_capped_at_30(self, monkeypatch):
        """days est plafonné à 30."""
        mock_settings = make_mock_settings(scheduler_days=90)
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        cfg = sched._read_config()

        assert cfg["days"] == 30

    def test_interval_minimum_1(self, monkeypatch):
        """interval_minutes minimum est 1."""
        mock_settings = make_mock_settings(scheduler_interval_minutes=0)
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        cfg = sched._read_config()

        assert cfg["interval_minutes"] == 1


# =========================
# Tests Timeframe
# =========================
class TestTimeframeFromDays:
    """Tests pour _timeframe_from_days."""

    def test_1_day_returns_30m(self):
        assert sched._timeframe_from_days(1) == "30m"

    def test_2_days_returns_30m(self):
        assert sched._timeframe_from_days(2) == "30m"

    def test_3_days_returns_4h(self):
        assert sched._timeframe_from_days(3) == "4h"

    def test_7_days_returns_4h(self):
        assert sched._timeframe_from_days(7) == "4h"

    def test_30_days_returns_4h(self):
        assert sched._timeframe_from_days(30) == "4h"

    def test_31_days_raises(self):
        with pytest.raises(ValueError) as exc_info:
            sched._timeframe_from_days(31)
        assert "non supporté" in str(exc_info.value)


# =========================
# Tests Lifecycle
# =========================
class TestSchedulerLifecycle:
    """Tests pour start/stop scheduler."""

    def test_start_disabled_does_not_start(self, monkeypatch):
        """Si disabled, le scheduler ne démarre pas."""
        mock_settings = make_mock_settings(scheduler_enabled=False)
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        # Reset state
        sched.stop_scheduler()
        sched.start_scheduler()

        status = sched.get_status()
        assert status["enabled"] is False
        assert status["running"] is False

    def test_stop_idempotent(self, monkeypatch):
        """stop_scheduler est idempotent."""
        mock_settings = make_mock_settings(scheduler_enabled=False)
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        # Appeler plusieurs fois ne crash pas
        sched.stop_scheduler()
        sched.stop_scheduler()
        sched.stop_scheduler()

        status = sched.get_status()
        assert status["running"] is False


# =========================
# Tests Job
# =========================
class TestFetchJob:
    """Tests pour fetch_candles_job."""

    def test_job_success_updates_state(self, monkeypatch):
        """Job success met à jour l'état correctement."""
        mock_settings = make_mock_settings(
            scheduler_enabled=True,
            scheduler_days=7,
            scheduler_symbol="BTC/USD",
        )
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        # Mock SessionLocal
        fake_db = MagicMock()
        monkeypatch.setattr(sched, "SessionLocal", lambda: fake_db)

        # Mock _run_coroutine
        def fake_run(_coro):
            return {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 7,
                "timeframe": "4h",
                "fetched": 42,
                "inserted": 2,
                "updated": 1,
                "duplicates": 39,
            }

        monkeypatch.setattr(sched, "_run_coroutine", fake_run)

        # Exécuter le job
        sched.fetch_candles_job()

        # Vérifications
        assert fake_db.commit.called is True
        assert fake_db.close.called is True

        status = sched.get_status()
        assert status["last_result"]["status"] == "success"
        assert status["last_result"]["inserted"] == 2
        assert status["last_result"]["duplicates"] == 39
        assert status["last_run_time"] is not None

    def test_job_error_updates_state(self, monkeypatch):
        """Job error met à jour l'état avec l'erreur."""
        mock_settings = make_mock_settings(
            scheduler_enabled=True,
            scheduler_days=7,
        )
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        fake_db = MagicMock()
        monkeypatch.setattr(sched, "SessionLocal", lambda: fake_db)

        def fake_run(_coro):
            raise RuntimeError("CoinGecko timeout")

        monkeypatch.setattr(sched, "_run_coroutine", fake_run)

        sched.fetch_candles_job()

        # Vérifications
        assert fake_db.rollback.called is True
        assert fake_db.close.called is True

        status = sched.get_status()
        assert status["last_result"]["status"] == "error"
        assert "CoinGecko timeout" in status["last_result"]["error"]

    def test_job_always_closes_db(self, monkeypatch):
        """La session DB est toujours fermée, même en cas d'erreur."""
        mock_settings = make_mock_settings(scheduler_days=7)
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        fake_db = MagicMock()
        monkeypatch.setattr(sched, "SessionLocal", lambda: fake_db)

        def fake_run(_coro):
            raise Exception("boom")

        monkeypatch.setattr(sched, "_run_coroutine", fake_run)

        sched.fetch_candles_job()

        assert fake_db.close.called is True


# =========================
# Tests Status
# =========================
class TestGetStatus:
    """Tests pour get_status."""

    def test_returns_all_fields(self, monkeypatch):
        """get_status retourne tous les champs attendus."""
        mock_settings = make_mock_settings(
            scheduler_enabled=True,
            scheduler_interval_minutes=60,
            scheduler_symbol="BTC/USD",
            scheduler_days=7,
        )
        monkeypatch.setattr(sched, "get_settings", lambda: mock_settings)

        # Reset state
        sched.stop_scheduler()
        sched._set_state(
            enabled=True,
            running=False,
            interval_minutes=60,
            symbol="BTC/USD",
            days=7,
            last_run_time=None,
            next_run_time=None,
            last_result=None,
        )

        status = sched.get_status()

        assert "enabled" in status
        assert "running" in status
        assert "interval_minutes" in status
        assert "symbol" in status
        assert "days" in status
        assert "last_run_time" in status
        assert "next_run_time" in status
        assert "last_result" in status