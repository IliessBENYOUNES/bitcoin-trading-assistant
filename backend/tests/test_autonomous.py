"""
Tests pour le mode autonome backend (headless / low-bandwidth).

Vérifie :
1. Les endpoints API /paper/autonomous/start, /stop, /status
2. Le singleton AutonomousManager
3. Le comportement sans frontend
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from app.services.autonomous_manager import AutonomousManager


class TestAutonomousManagerUnit:
    """Tests unitaires du AutonomousManager (sans DB)."""

    def setup_method(self):
        """Reset le singleton avant chaque test."""
        # Reset le singleton pour isolation
        AutonomousManager._instance = None

    def teardown_method(self):
        """Arrêter le manager si actif."""
        try:
            manager = AutonomousManager()
            if manager.is_running:
                manager.stop()
        except Exception:
            pass
        AutonomousManager._instance = None

    def test_singleton_pattern(self):
        """Deux instanciations retournent le même objet."""
        m1 = AutonomousManager()
        m2 = AutonomousManager()
        assert m1 is m2

    def test_initial_state(self):
        """État initial : non actif."""
        manager = AutonomousManager()
        status = manager.get_status()
        assert status["running"] is False
        assert status["tick_count"] == 0
        assert status["headless_capable"] is True
        assert status["frontend_required"] is False

    def test_start_returns_started(self):
        """Le démarrage retourne le status 'started'."""
        manager = AutonomousManager()
        # On mock le _do_tick pour ne pas avoir besoin de DB
        with patch.object(manager, '_do_tick'):
            result = manager.start(interval_seconds=60, profile="scalping")
            assert result["status"] == "started"
            assert result["interval_seconds"] == 60
            assert result["profile"] == "scalping"
            assert manager.is_running is True

    def test_start_already_running(self):
        """Double start retourne 'already_running'."""
        manager = AutonomousManager()
        with patch.object(manager, '_do_tick'):
            manager.start(interval_seconds=60, profile="scalping")
            result = manager.start(interval_seconds=30, profile="balanced")
            assert result["status"] == "already_running"

    def test_stop(self):
        """Stop arrête le manager."""
        manager = AutonomousManager()
        with patch.object(manager, '_do_tick'):
            manager.start(interval_seconds=60, profile="scalping")
            result = manager.stop()
            assert result["status"] == "stopped"
            assert manager.is_running is False

    def test_stop_not_running(self):
        """Stop quand pas actif retourne 'was_not_running'."""
        manager = AutonomousManager()
        result = manager.stop()
        assert result["status"] == "was_not_running"

    def test_minimum_interval(self):
        """L'intervalle minimum est 5 secondes."""
        manager = AutonomousManager()
        with patch.object(manager, '_do_tick'):
            result = manager.start(interval_seconds=1, profile="scalping")
            assert result["interval_seconds"] == 5

    def test_maximum_interval(self):
        """L'intervalle maximum est 3600 secondes."""
        manager = AutonomousManager()
        with patch.object(manager, '_do_tick'):
            result = manager.start(interval_seconds=9999, profile="scalping")
            assert result["interval_seconds"] == 3600

    def test_status_while_running(self):
        """Le statut reflète l'état actif."""
        manager = AutonomousManager()
        with patch.object(manager, '_do_tick'):
            manager.start(interval_seconds=30, profile="balanced")
            status = manager.get_status()
            assert status["running"] is True
            assert status["interval_seconds"] == 30
            assert status["profile"] == "balanced"
            assert status["started_at"] is not None
            assert status["uptime_seconds"] is not None
            assert status["uptime_seconds"] >= 0


class TestAutonomousEndpoints:
    """Tests des endpoints API /paper/autonomous/*."""

    def test_get_status_initial(self, client):
        """GET /paper/autonomous/status retourne un état initial inactif."""
        # Reset singleton
        AutonomousManager._instance = None
        resp = client.get("/paper/autonomous/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False
        assert data["headless_capable"] is True
        assert data["frontend_required"] is False

    def test_start_endpoint(self, client):
        """POST /paper/autonomous/start démarre le mode headless."""
        AutonomousManager._instance = None
        # Mock le tick pour ne pas dépendre de données réelles
        with patch.object(AutonomousManager, '_do_tick'):
            with patch.object(AutonomousManager, '_set_profile'):
                resp = client.post("/paper/autonomous/start", json={
                    "interval_seconds": 30,
                    "profile": "scalping",
                })
                assert resp.status_code == 200
                data = resp.json()
                assert data["running"] is True

                # Cleanup
                manager = AutonomousManager()
                manager.stop()

    def test_stop_endpoint(self, client):
        """POST /paper/autonomous/stop arrête le mode headless."""
        AutonomousManager._instance = None
        with patch.object(AutonomousManager, '_do_tick'):
            with patch.object(AutonomousManager, '_set_profile'):
                client.post("/paper/autonomous/start", json={
                    "interval_seconds": 60,
                    "profile": "balanced",
                })
                resp = client.post("/paper/autonomous/stop")
                assert resp.status_code == 200
                data = resp.json()
                assert data["running"] is False

    def test_status_reflects_running(self, client):
        """Le statut reflète l'état après start."""
        AutonomousManager._instance = None
        with patch.object(AutonomousManager, '_do_tick'):
            with patch.object(AutonomousManager, '_set_profile'):
                client.post("/paper/autonomous/start", json={
                    "interval_seconds": 15,
                    "profile": "scalping",
                })
                resp = client.get("/paper/autonomous/status")
                data = resp.json()
                assert data["running"] is True
                assert data["interval_seconds"] == 15
                assert data["profile"] == "scalping"

                # Cleanup
                AutonomousManager().stop()

    def test_start_validation_min_interval(self, client):
        """L'intervalle minimum est respecté (5s)."""
        AutonomousManager._instance = None
        with patch.object(AutonomousManager, '_do_tick'):
            with patch.object(AutonomousManager, '_set_profile'):
                resp = client.post("/paper/autonomous/start", json={
                    "interval_seconds": 5,
                    "profile": "scalping",
                })
                assert resp.status_code == 200

                # Cleanup
                AutonomousManager().stop()

    def test_start_validation_invalid_interval(self, client):
        """Intervalle < 5 est rejeté par validation Pydantic."""
        AutonomousManager._instance = None
        resp = client.post("/paper/autonomous/start", json={
            "interval_seconds": 2,
            "profile": "scalping",
        })
        assert resp.status_code == 422  # Validation error

