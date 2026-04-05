"""
Tests pour le job scheduler de persistance des news RSS.

Vérifie que fetch_news_job():
- Appelle NewsHistoryService.persist_current_news()
- Met à jour le scheduler_state["jobs"]["news"]
- Gère les erreurs sans crash
- Est exposé dans get_status() et dans la config
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.tasks.scheduler import (
    _read_config,
    fetch_news_job,
    get_status,
    scheduler_state,
    _set_job_state,
    start_scheduler,
    stop_scheduler,
    JOB_ID_NEWS,
)


class TestNewsJobConfig:
    """Tests de configuration du job news."""

    def test_read_config_has_news_interval(self):
        """_read_config() doit retourner interval_minutes_news."""
        cfg = _read_config()
        assert "interval_minutes_news" in cfg
        assert isinstance(cfg["interval_minutes_news"], int)
        assert cfg["interval_minutes_news"] >= 1

    def test_default_news_interval_is_10(self):
        """L'intervalle par défaut du job news est 10 minutes."""
        cfg = _read_config()
        assert cfg["interval_minutes_news"] == 10


class TestNewsJobState:
    """Tests sur le state du job news dans scheduler_state."""

    def test_status_has_news_job(self):
        """get_status() doit inclure jobs.news."""
        status = get_status()
        assert "news" in status["jobs"]

    def test_news_job_has_required_fields(self):
        """Le job news doit avoir interval_minutes, last_run_time, next_run_time, last_result."""
        status = get_status()
        news = status["jobs"]["news"]
        assert "interval_minutes" in news
        assert "last_run_time" in news
        assert "next_run_time" in news
        assert "last_result" in news

    def test_news_job_has_no_days_field(self):
        """Le job news ne doit pas avoir de champ 'days' (pas un job candles)."""
        status = get_status()
        news = status["jobs"]["news"]
        assert "days" not in news


class TestFetchNewsJobExecution:
    """Tests d'exécution du job fetch_news_job."""

    @patch("app.tasks.scheduler.SessionLocal")
    @patch("app.tasks.scheduler._update_next_run_time")
    def test_job_success_updates_state(self, mock_update, mock_session_cls):
        """Le job doit mettre à jour le state avec le résultat."""
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_persist_result = {
            "inserted": 5,
            "updated": 2,
            "skipped": 10,
            "total_fetched": 17,
            "total_in_db": 100,
            "duration_seconds": 1.5,
        }

        with patch(
            "app.services.news_history_service.NewsHistoryService.persist_current_news",
            return_value=mock_persist_result,
        ):
            fetch_news_job()

        # Vérifier que le state est mis à jour
        news_state = scheduler_state["jobs"]["news"]
        assert news_state["last_run_time"] is not None
        assert news_state["last_result"] is not None
        assert news_state["last_result"]["status"] == "success"
        assert news_state["last_result"]["inserted"] == 5
        assert news_state["last_result"]["total_in_db"] == 100

        # DB doit être fermée
        mock_db.close.assert_called_once()

    @patch("app.tasks.scheduler.SessionLocal")
    @patch("app.tasks.scheduler._update_next_run_time")
    def test_job_error_updates_state(self, mock_update, mock_session_cls):
        """En cas d'erreur, le state doit contenir le message d'erreur."""
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        with patch(
            "app.services.news_history_service.NewsHistoryService.persist_current_news",
            side_effect=Exception("RSS timeout"),
        ):
            fetch_news_job()

        news_state = scheduler_state["jobs"]["news"]
        assert news_state["last_result"]["status"] == "error"
        assert "RSS timeout" in news_state["last_result"]["error"]

        # DB doit être rollback + fermée
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.tasks.scheduler.SessionLocal")
    @patch("app.tasks.scheduler._update_next_run_time")
    def test_job_always_closes_db(self, mock_update, mock_session_cls):
        """La DB doit toujours être fermée, même en cas d'erreur."""
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        with patch(
            "app.services.news_history_service.NewsHistoryService.persist_current_news",
            side_effect=RuntimeError("boom"),
        ):
            fetch_news_job()

        mock_db.close.assert_called_once()

    @patch("app.tasks.scheduler.SessionLocal")
    @patch("app.tasks.scheduler._update_next_run_time")
    def test_job_result_has_duration(self, mock_update, mock_session_cls):
        """Le résultat doit contenir duration_seconds."""
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        with patch(
            "app.services.news_history_service.NewsHistoryService.persist_current_news",
            return_value={"inserted": 0, "updated": 0, "skipped": 0, "total_fetched": 0, "total_in_db": 0, "duration_seconds": 0.1},
        ):
            fetch_news_job()

        news_state = scheduler_state["jobs"]["news"]
        assert "duration_seconds" in news_state["last_result"]
        assert news_state["last_result"]["duration_seconds"] >= 0


class TestSchedulerStartWithNews:
    """Tests que start_scheduler enregistre bien le job news."""

    @patch("app.tasks.scheduler._read_config")
    def test_start_scheduler_registers_news_job(self, mock_config):
        """start_scheduler doit enregistrer le job news."""
        mock_config.return_value = {
            "enabled": True,
            "interval_minutes": 240,
            "symbol": "BTC/USD",
            "days": 7,
            "interval_minutes_4h": 240,
            "interval_minutes_30m": 30,
            "days_4h": 7,
            "days_30m": 1,
            "dual_jobs": True,
            "interval_minutes_news": 10,
        }

        try:
            start_scheduler()

            from app.tasks.scheduler import _scheduler
            assert _scheduler is not None

            # Le job news doit être enregistré
            news_job = _scheduler.get_job(JOB_ID_NEWS)
            assert news_job is not None, "Job news doit être enregistré dans le scheduler"
        finally:
            stop_scheduler()

    @patch("app.tasks.scheduler._read_config")
    def test_news_job_interval_is_correct(self, mock_config):
        """L'intervalle du job news doit correspondre à la config."""
        mock_config.return_value = {
            "enabled": True,
            "interval_minutes": 240,
            "symbol": "BTC/USD",
            "days": 7,
            "interval_minutes_4h": 240,
            "interval_minutes_30m": 30,
            "days_4h": 7,
            "days_30m": 1,
            "dual_jobs": True,
            "interval_minutes_news": 15,
        }

        try:
            start_scheduler()

            status = get_status()
            assert status["jobs"]["news"]["interval_minutes"] == 15
        finally:
            stop_scheduler()

