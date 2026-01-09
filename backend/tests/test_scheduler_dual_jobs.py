"""
Tests pour les 2 jobs APScheduler distincts (PHASE 2B).

Vérifie:
- Les 2 jobs existent et sont configurés correctement
- Chaque job exécute uniquement son resample
- Le status expose les champs attendus pour chaque job
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from app.tasks.scheduler import (
    start_scheduler,
    stop_scheduler,
    get_status,
    fetch_candles_4h_job,
    fetch_candles_30m_job,
    _read_config,
    scheduler_state,
    _set_state,
    _set_job_state,
    JOB_ID_4H,
    JOB_ID_30M,
)


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    """Reset scheduler state before each test."""
    stop_scheduler()
    _set_state(
        enabled=False,
        running=False,
        symbol=None,
    )
    _set_job_state("4h", interval_minutes=None, days=7, last_run_time=None, next_run_time=None, last_result=None)
    _set_job_state("30m", interval_minutes=None, days=1, last_run_time=None, next_run_time=None, last_result=None)
    yield
    stop_scheduler()


class TestDualJobsConfig:
    """Tests de configuration des 2 jobs."""

    def test_read_config_has_both_intervals(self):
        """_read_config retourne les intervalles pour les 2 jobs."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )
            cfg = _read_config()

            assert cfg["interval_minutes_4h"] == 240
            assert cfg["interval_minutes_30m"] == 30
            assert cfg["days_4h"] == 7
            assert cfg["days_30m"] == 1  # Jamais 2!
            assert cfg["symbol"] == "BTC/USD"

    def test_days_30m_always_1_never_2(self):
        """days_30m est toujours 1, jamais 2 (évite erreur CoinGecko)."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )
            cfg = _read_config()
            assert cfg["days_30m"] == 1


class TestSchedulerStart:
    """Tests de démarrage du scheduler avec 2 jobs."""

    def test_start_scheduler_creates_both_jobs(self):
        """start_scheduler crée les 2 jobs APScheduler."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            start_scheduler()

            from app.tasks.scheduler import _scheduler
            assert _scheduler is not None

            job_4h = _scheduler.get_job(JOB_ID_4H)
            job_30m = _scheduler.get_job(JOB_ID_30M)

            assert job_4h is not None, "Job 4H doit exister"
            assert job_30m is not None, "Job 30M doit exister"

    def test_start_scheduler_sets_correct_intervals(self):
        """Les jobs ont les bons intervalles."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            start_scheduler()
            status = get_status()

            assert status["jobs"]["4h"]["interval_minutes"] == 240
            assert status["jobs"]["30m"]["interval_minutes"] == 30


class TestStatusFormat:
    """Tests du format de get_status()."""

    def test_status_has_jobs_structure(self):
        """get_status retourne la structure jobs avec 4h et 30m."""
        status = get_status()

        assert "jobs" in status
        assert "4h" in status["jobs"]
        assert "30m" in status["jobs"]

    def test_status_job_has_required_fields(self):
        """Chaque job a les champs requis."""
        status = get_status()

        for job_type in ["4h", "30m"]:
            job = status["jobs"][job_type]
            assert "interval_minutes" in job
            assert "days" in job
            assert "last_run_time" in job
            assert "next_run_time" in job
            assert "last_result" in job

    def test_status_has_global_fields(self):
        """get_status a les champs globaux."""
        status = get_status()

        assert "enabled" in status
        assert "running" in status
        assert "symbol" in status


class TestJob4HExecution:
    """Tests d'exécution du job 4H."""

    def test_job_4h_uses_days_7_timeframe_4h(self):
        """Le job 4H utilise days=7 et timeframe=4h."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings, \
                patch("app.tasks.scheduler._run_coroutine") as mock_run, \
                patch("app.tasks.scheduler.SessionLocal") as mock_session, \
                patch("app.tasks.scheduler._run_resample_4h_to_1d") as mock_resample:

            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            mock_db = MagicMock()
            mock_session.return_value = mock_db

            mock_run.return_value = {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 7,
                "timeframe": "4h",
                "fetched": 42,
                "inserted": 10,
                "updated": 5,
                "duplicates": 27,
                "min_ts": datetime.now(timezone.utc),
                "max_ts": datetime.now(timezone.utc),
            }
            mock_resample.return_value = {"1d": 3}

            fetch_candles_4h_job()

            # Vérifie que _fetch_and_store est appelé avec timeframe="4h"
            call_args = mock_run.call_args
            assert call_args is not None
            coro = call_args[0][0]
            # Le coro contient les args days=7, timeframe="4h"

    def test_job_4h_only_resamples_to_1d(self):
        """Le job 4H n'appelle que resample_4h_to_1d, pas 30m_to_1h."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings, \
                patch("app.tasks.scheduler._run_coroutine") as mock_run, \
                patch("app.tasks.scheduler.SessionLocal") as mock_session, \
                patch("app.tasks.scheduler._run_resample_4h_to_1d") as mock_resample_4h, \
                patch("app.tasks.scheduler._run_resample_30m_to_1h") as mock_resample_30m:

            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            mock_db = MagicMock()
            mock_session.return_value = mock_db

            mock_run.return_value = {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 7,
                "timeframe": "4h",
                "fetched": 42,
                "inserted": 10,
                "updated": 5,
                "duplicates": 27,
                "min_ts": datetime.now(timezone.utc),
                "max_ts": datetime.now(timezone.utc),
            }
            mock_resample_4h.return_value = {"1d": 3}

            fetch_candles_4h_job()

            mock_resample_4h.assert_called_once()
            mock_resample_30m.assert_not_called()

    def test_job_4h_result_has_resample_contract(self):
        """Le résultat du job 4H a le contrat resample avec 1d et 1h."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings, \
                patch("app.tasks.scheduler._run_coroutine") as mock_run, \
                patch("app.tasks.scheduler.SessionLocal") as mock_session, \
                patch("app.tasks.scheduler._run_resample_4h_to_1d") as mock_resample:

            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            mock_db = MagicMock()
            mock_session.return_value = mock_db

            mock_run.return_value = {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 7,
                "timeframe": "4h",
                "fetched": 42,
                "inserted": 10,
                "updated": 5,
                "duplicates": 27,
                "min_ts": datetime.now(timezone.utc),
                "max_ts": datetime.now(timezone.utc),
            }
            mock_resample.return_value = {"1d": 3}

            fetch_candles_4h_job()

            status = get_status()
            last_result = status["jobs"]["4h"]["last_result"]

            assert "resample" in last_result
            assert "1d" in last_result["resample"]
            assert "1h" in last_result["resample"]
            assert last_result["resample"]["1d"] == 3
            assert last_result["resample"]["1h"] == 0  # Non exécuté par ce job


class TestJob30MExecution:
    """Tests d'exécution du job 30M."""

    def test_job_30m_uses_days_1_timeframe_30m(self):
        """Le job 30M utilise days=1 et timeframe=30m."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings, \
                patch("app.tasks.scheduler._run_coroutine") as mock_run, \
                patch("app.tasks.scheduler.SessionLocal") as mock_session, \
                patch("app.tasks.scheduler._run_resample_30m_to_1h") as mock_resample:

            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            mock_db = MagicMock()
            mock_session.return_value = mock_db

            mock_run.return_value = {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 1,
                "timeframe": "30m",
                "fetched": 48,
                "inserted": 12,
                "updated": 8,
                "duplicates": 28,
                "min_ts": datetime.now(timezone.utc),
                "max_ts": datetime.now(timezone.utc),
            }
            mock_resample.return_value = {"1h": 24}

            fetch_candles_30m_job()

            # Vérifie l'appel
            mock_run.assert_called_once()

    def test_job_30m_only_resamples_to_1h(self):
        """Le job 30M n'appelle que resample_30m_to_1h, pas 4h_to_1d."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings, \
                patch("app.tasks.scheduler._run_coroutine") as mock_run, \
                patch("app.tasks.scheduler.SessionLocal") as mock_session, \
                patch("app.tasks.scheduler._run_resample_4h_to_1d") as mock_resample_4h, \
                patch("app.tasks.scheduler._run_resample_30m_to_1h") as mock_resample_30m:

            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            mock_db = MagicMock()
            mock_session.return_value = mock_db

            mock_run.return_value = {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 1,
                "timeframe": "30m",
                "fetched": 48,
                "inserted": 12,
                "updated": 8,
                "duplicates": 28,
                "min_ts": datetime.now(timezone.utc),
                "max_ts": datetime.now(timezone.utc),
            }
            mock_resample_30m.return_value = {"1h": 24}

            fetch_candles_30m_job()

            mock_resample_30m.assert_called_once()
            mock_resample_4h.assert_not_called()

    def test_job_30m_result_has_resample_contract(self):
        """Le résultat du job 30M a le contrat resample avec 1d et 1h."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings, \
                patch("app.tasks.scheduler._run_coroutine") as mock_run, \
                patch("app.tasks.scheduler.SessionLocal") as mock_session, \
                patch("app.tasks.scheduler._run_resample_30m_to_1h") as mock_resample:

            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            mock_db = MagicMock()
            mock_session.return_value = mock_db

            mock_run.return_value = {
                "status": "success",
                "symbol": "BTC/USD",
                "days": 1,
                "timeframe": "30m",
                "fetched": 48,
                "inserted": 12,
                "updated": 8,
                "duplicates": 28,
                "min_ts": datetime.now(timezone.utc),
                "max_ts": datetime.now(timezone.utc),
            }
            mock_resample.return_value = {"1h": 24}

            fetch_candles_30m_job()

            status = get_status()
            last_result = status["jobs"]["30m"]["last_result"]

            assert "resample" in last_result
            assert "1d" in last_result["resample"]
            assert "1h" in last_result["resample"]
            assert last_result["resample"]["1d"] == 0  # Non exécuté par ce job
            assert last_result["resample"]["1h"] == 24


class TestErrorHandling:
    """Tests de gestion des erreurs."""

    def test_job_4h_error_has_resample_contract(self):
        """En cas d'erreur, le résultat a quand même le contrat resample."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings, \
                patch("app.tasks.scheduler._run_coroutine") as mock_run, \
                patch("app.tasks.scheduler.SessionLocal") as mock_session:

            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            mock_db = MagicMock()
            mock_session.return_value = mock_db

            mock_run.side_effect = Exception("API error")

            fetch_candles_4h_job()

            status = get_status()
            last_result = status["jobs"]["4h"]["last_result"]

            assert last_result["status"] == "error"
            assert "resample" in last_result
            assert last_result["resample"]["1d"] == 0
            assert last_result["resample"]["1h"] == 0

    def test_job_30m_error_has_resample_contract(self):
        """En cas d'erreur sur job 30m, le résultat a quand même le contrat resample."""
        with patch("app.tasks.scheduler.get_settings") as mock_settings, \
                patch("app.tasks.scheduler._run_coroutine") as mock_run, \
                patch("app.tasks.scheduler.SessionLocal") as mock_session:

            mock_settings.return_value = MagicMock(
                scheduler_enabled=True,
                scheduler_interval_minutes=240,
                scheduler_interval_30m_minutes=30,
                scheduler_symbol="BTC/USD",
            )

            mock_db = MagicMock()
            mock_session.return_value = mock_db

            mock_run.side_effect = Exception("API error")

            fetch_candles_30m_job()

            status = get_status()
            last_result = status["jobs"]["30m"]["last_result"]

            assert last_result["status"] == "error"
            assert "resample" in last_result
            assert last_result["resample"]["1d"] == 0
            assert last_result["resample"]["1h"] == 0
