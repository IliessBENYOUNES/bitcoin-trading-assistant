"""
Tests pour le SmartCooldownService, PaperRunService, et l'intégration
du cooldown intelligent dans le diagnostic.

v1.9.0 — Smart Cooldown + PaperRun + CooldownDiagnostic
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.paper_run import PaperRun
from app.models.tick_activity_log import TickActivityLog
from app.services.smart_cooldown_service import SmartCooldownService
from app.services.paper_run_service import PaperRunService
from app.services.diagnostic_service import DiagnosticService
from app.services.trading_profile_service import PROFILE_PRESETS


# ================================================================
# Helpers
# ================================================================

def _make_account(db, active=True, profile="scalping"):
    account = PaperAccount(
        initial_capital=10000.0,
        current_capital=10000.0,
        peak_capital=10000.0,
        is_active=active,
        active_profile=profile,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _make_trade(db, account_id, pnl=10.0, duration_hours=0.1,
                direction="long", status="closed_signal",
                entry_offset_hours=1.0, slot="scalping",
                profile="scalping"):
    now = datetime.now(timezone.utc)
    trade = PaperTrade(
        account_id=account_id,
        status=status,
        direction=direction,
        entry_price=85000.0,
        exit_price=85000.0 + pnl,
        stop_loss_price=84700.0,
        take_profit_price=85300.0,
        position_size_usd=1000.0,
        leverage=1.5,
        profile_type=profile,
        slot=slot,
        pnl=pnl,
        pnl_pct=round(pnl / 1500 * 100, 4),
        entry_reason="Test entry",
        exit_reason="Test exit",
        decision_score=30,
        entry_ts=now - timedelta(hours=entry_offset_hours),
        exit_ts=now - timedelta(hours=entry_offset_hours - duration_hours),
        duration_hours=duration_hours,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def _make_tick(db, account_id, reason=None, score=None,
               decision_action=None, ts_offset_min=0, profile="scalping"):
    ts = datetime.now(timezone.utc) - timedelta(minutes=ts_offset_min)
    entry = TickActivityLog(
        account_id=account_id,
        timestamp=ts,
        btc_price=85000.0,
        action_taken="hold",
        decision_score=score,
        decision_action=decision_action,
        reason_no_trade=reason,
        profile_type=profile,
    )
    db.add(entry)
    db.commit()
    return entry


# ================================================================
# Tests SmartCooldownService
# ================================================================

class TestSmartCooldown:
    """Tests pour le service de cooldown intelligent."""

    def test_base_cooldown_unchanged_when_no_context(self):
        """Sans contexte, retourne le cooldown de base."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
        )
        assert result == 2.0

    def test_cooldown_increased_after_stale_exit(self):
        """[v1.9.9] Cooldown AUGMENTÉ après une sortie stale (anti-churn)."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_stale",
            last_pnl=0.5,
        )
        assert result >= 2.0

    def test_cooldown_reduced_after_trailing_stop(self):
        """Cooldown réduit après un trailing stop."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_trailing_stop",
            last_pnl=0.3,
        )
        assert result < 2.0

    def test_cooldown_increased_after_sl(self):
        """Cooldown allongé après un stop loss."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_sl",
            last_pnl=-5.0,
            last_pnl_pct=-0.3,
        )
        assert result > 2.0

    def test_cooldown_increased_after_big_loss(self):
        """Cooldown allongé après une grosse perte."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_signal",
            last_pnl=-10.0,
            last_pnl_pct=-0.5,
        )
        assert result > 2.0

    def test_cooldown_reduced_with_strong_signal(self):
        """Cooldown réduit si signal fort (score > 50)."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            signal_score=60,
        )
        assert result < 2.0

    def test_cooldown_increased_after_scratch(self):
        """[v1.9.9] Cooldown augmenté après un scratch (stale + flat = bruit)."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_stale",
            last_pnl=0.0,
            last_pnl_pct=0.01,
            last_duration_min=1.0,
        )
        # Stale positif/flat → multiplier 2.0 + gain small → 0.8 = 1.6 * 2.0 = 3.2
        assert result >= 2.0

    def test_cooldown_bounded_min(self):
        """Le cooldown ne descend pas en dessous de min_cooldown."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_stale",
            last_pnl=5.0,
            last_pnl_pct=0.01,
            last_duration_min=0.5,
            signal_score=80,
            min_cooldown=1.0,
        )
        assert result >= 1.0

    def test_cooldown_bounded_max(self):
        """Le cooldown ne dépasse pas max_cooldown."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=5.0,
            last_exit_type="closed_sl",
            last_pnl=-20.0,
            last_pnl_pct=-1.0,
            max_cooldown=8.0,
        )
        assert result <= 8.0

    def test_cooldown_absolute_min(self):
        """Le cooldown respecte la borne absolue de 0.5 min."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=0.1,
            min_cooldown=0.1,
        )
        assert result >= 0.5

    def test_cooldown_absolute_max(self):
        """Le cooldown respecte la borne absolue de 30 min."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=50.0,
            max_cooldown=50.0,
        )
        assert result <= 30.0

    def test_explain_cooldown_reduced(self):
        """L'explication mentionne la réduction."""
        explanation = SmartCooldownService.explain_cooldown(
            base_cooldown=2.0,
            computed_cooldown=1.0,
            last_exit_type="closed_stale",
            last_pnl=0.0,
        )
        assert "réduit" in explanation

    def test_explain_cooldown_increased(self):
        """L'explication mentionne l'allongement."""
        explanation = SmartCooldownService.explain_cooldown(
            base_cooldown=2.0,
            computed_cooldown=3.5,
            last_exit_type="closed_sl",
            last_pnl=-5.0,
        )
        assert "allongé" in explanation

    def test_explain_cooldown_standard(self):
        """L'explication pour un cooldown inchangé."""
        explanation = SmartCooldownService.explain_cooldown(
            base_cooldown=2.0,
            computed_cooldown=2.0,
        )
        assert "standard" in explanation

    def test_cooldown_after_tp_is_reduced(self):
        """Cooldown réduit après un TP (trade gagnant réussi)."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_tp",
            last_pnl=5.0,
        )
        assert result < 2.0

    def test_cooldown_after_momentum_fade(self):
        """Cooldown réduit après un momentum fade."""
        result = SmartCooldownService.compute_cooldown(
            base_cooldown=2.0,
            last_exit_type="closed_momentum_fade",
            last_pnl=1.0,
        )
        assert result < 2.0


# ================================================================
# Tests PaperRunService
# ================================================================

class TestPaperRunService:
    """Tests pour le service de campagnes de validation."""

    def test_start_run(self, db_session):
        """Peut démarrer une campagne."""
        svc = PaperRunService(db_session)
        run = svc.start_run("test-run", "scalping")
        assert run.id is not None
        assert run.name == "test-run"
        assert run.status == "running"
        assert run.profile_type == "scalping"

    def test_end_run(self, db_session):
        """Peut terminer une campagne."""
        svc = PaperRunService(db_session)
        run = svc.start_run("test-run", "scalping")
        _make_account(db_session)
        ended = svc.end_run(run.id)
        assert ended.status == "completed"
        assert ended.ended_at is not None

    def test_end_run_nonexistent(self, db_session):
        """Terminer un run inexistant retourne None."""
        svc = PaperRunService(db_session)
        assert svc.end_run(999) is None

    def test_list_runs(self, db_session):
        """Liste les campagnes."""
        svc = PaperRunService(db_session)
        svc.start_run("run-1", "scalping")
        svc.start_run("run-2", "aggressive")
        runs = svc.get_runs()
        assert len(runs) == 2

    def test_run_metrics_empty(self, db_session):
        """Métriques d'un run sans trades."""
        _make_account(db_session)
        svc = PaperRunService(db_session)
        run = svc.start_run("empty-run", "scalping")
        metrics = svc.get_run_metrics(run.id)
        assert metrics is not None
        assert metrics.metrics.total_trades == 0

    def test_run_metrics_with_trades(self, db_session):
        """Métriques d'un run avec des trades."""
        account = _make_account(db_session)
        svc = PaperRunService(db_session)
        # On démarre le run AVANT de créer les trades
        # Les trades doivent avoir entry_ts APRÈS le started_at du run
        from app.models.paper_run import PaperRun
        run = svc.start_run("test-run", "scalping")
        # Mettre le started_at 1h dans le passé pour que les trades récents soient inclus
        run.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db_session.commit()
        # Créer des trades dans la période du run
        _make_trade(db_session, account.id, pnl=5.0, entry_offset_hours=0.1)
        _make_trade(db_session, account.id, pnl=-3.0, entry_offset_hours=0.05)
        metrics = svc.get_run_metrics(run.id)
        assert metrics.metrics.total_trades >= 1

    def test_run_metrics_nonexistent(self, db_session):
        """Métriques d'un run inexistant retourne None."""
        svc = PaperRunService(db_session)
        assert svc.get_run_metrics(999) is None

    def test_compare_runs(self, db_session):
        """Peut comparer deux runs."""
        account = _make_account(db_session)
        svc = PaperRunService(db_session)
        r1 = svc.start_run("before", "scalping")
        r2 = svc.start_run("after", "scalping")
        comparison = svc.compare_runs(r1.id, r2.id)
        assert comparison is not None
        assert comparison.verdict is not None

    def test_compare_runs_nonexistent(self, db_session):
        """Comparaison avec un run inexistant retourne None."""
        svc = PaperRunService(db_session)
        svc.start_run("only-one", "scalping")
        assert svc.compare_runs(1, 999) is None

    def test_run_config_snapshot(self, db_session):
        """Le run sauvegarde le snapshot de config."""
        svc = PaperRunService(db_session)
        run = svc.start_run("snapshot-test", "scalping")
        assert run.config_snapshot is not None
        assert "scalping" in run.config_snapshot.lower() or "buy_threshold" in run.config_snapshot


# ================================================================
# Tests CooldownDiagnostic
# ================================================================

class TestCooldownDiagnostic:
    """Tests pour le diagnostic du cooldown dans DiagnosticService."""

    def test_diagnostic_has_cooldown_section(self, db_session):
        """Le diagnostic contient la section cooldown."""
        account = _make_account(db_session, profile="scalping")
        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()
        assert hasattr(result, "cooldown")
        assert result.cooldown is not None

    def test_cooldown_configured_visible(self, db_session):
        """Le cooldown configuré est visible dans le diagnostic."""
        account = _make_account(db_session, profile="scalping")
        _make_tick(db_session, account.id, reason="decision_wait")
        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()
        # [v2.0.28] Scalping cooldown réduit à 0.5 min (30 sec)
        assert result.cooldown.cooldown_configured_min == 0.5

    def test_cooldown_smart_enabled_visible(self, db_session):
        """Le smart cooldown enabled est visible dans le diagnostic."""
        account = _make_account(db_session, profile="scalping")
        _make_tick(db_session, account.id, reason="decision_wait")
        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()
        assert result.cooldown.smart_cooldown_enabled is True

    def test_cooldown_ticks_blocked(self, db_session):
        """Compte les ticks bloqués par le cooldown."""
        account = _make_account(db_session, profile="scalping")
        for _ in range(5):
            _make_tick(db_session, account.id, reason="cooldown_active")
        for _ in range(10):
            _make_tick(db_session, account.id, reason="decision_wait")
        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()
        assert result.cooldown.ticks_blocked_by_cooldown == 5

    def test_cooldown_signals_lost(self, db_session):
        """Détecte les signaux perdus pendant le cooldown."""
        account = _make_account(db_session, profile="scalping")
        # Ticks cooldown avec un signal exploitable
        for _ in range(3):
            _make_tick(db_session, account.id, reason="cooldown_active",
                       score=25, decision_action="acheter")
        # Tick cooldown sans signal fort
        _make_tick(db_session, account.id, reason="cooldown_active",
                   score=5, decision_action="attendre")
        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()
        assert result.cooldown.signals_lost_during_cooldown == 3

    def test_cooldown_delay_distribution(self, db_session):
        """Calcule la distribution des délais entre trades."""
        account = _make_account(db_session, profile="scalping")
        # Créer des trades avec des délais variés
        now = datetime.now(timezone.utc)
        for i in range(5):
            trade = PaperTrade(
                account_id=account.id, status="closed_signal", direction="long",
                entry_price=85000, exit_price=85010,
                stop_loss_price=84700, take_profit_price=85300,
                position_size_usd=1000, pnl=1.0, pnl_pct=0.01,
                entry_reason="test", exit_reason="test", decision_score=30,
                entry_ts=now - timedelta(hours=5 - i, minutes=0),
                exit_ts=now - timedelta(hours=5 - i, minutes=-3),
                duration_hours=0.05, slot="scalping", profile_type="scalping",
            )
            db_session.add(trade)
        db_session.commit()

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()
        assert result.cooldown.avg_delay_between_trades_min >= 0


# ================================================================
# Tests ScalpingProfileSmartCooldown
# ================================================================

class TestScalpingProfileSmartCooldown:
    """Tests pour l'intégration du smart cooldown dans le profil scalping."""

    def test_scalping_preset_has_smart_cooldown(self):
        """Le preset scalping a smart_cooldown_enabled."""
        p = PROFILE_PRESETS["scalping"]
        assert p.smart_cooldown_enabled is True

    def test_scalping_preset_min_cooldown(self):
        """[v2.0.28] Le preset scalping a min_cooldown_minutes = 0.25 (15 sec)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.min_cooldown_minutes == 2.0

    def test_scalping_preset_max_cooldown(self):
        """[v2.0.28] Le preset scalping a max_cooldown_minutes = 2.0."""
        p = PROFILE_PRESETS["scalping"]
        assert p.max_cooldown_minutes == 10.0  # [v2.0.28] 3→2

    def test_conservative_no_smart_cooldown(self):
        """Conservative n'a pas de smart cooldown."""
        p = PROFILE_PRESETS["conservative"]
        assert p.smart_cooldown_enabled is False

    def test_aggressive_has_smart_cooldown(self):
        """[v2.0.28] Aggressive a smart cooldown activé."""
        p = PROFILE_PRESETS["aggressive"]
        assert p.smart_cooldown_enabled is True


# ================================================================
# Tests API Endpoints
# ================================================================

class TestCooldownEndpoints:
    """Tests pour les endpoints de diagnostic avec cooldown."""

    def test_diagnostic_endpoint_has_cooldown(self, client, db_session):
        """GET /paper/diagnostic retourne la section cooldown."""
        resp = client.get("/paper/diagnostic")
        assert resp.status_code == 200
        data = resp.json()
        assert "cooldown" in data
        assert "cooldown_configured_min" in data["cooldown"]
        assert "smart_cooldown_enabled" in data["cooldown"]
        assert "ticks_blocked_by_cooldown" in data["cooldown"]

    def test_learning_stats_endpoint(self, client, db_session):
        """GET /learning/stats retourne 200."""
        resp = client.get("/learning/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_samples" in data

    def test_learning_patterns_endpoint(self, client, db_session):
        """GET /learning/patterns retourne 200."""
        resp = client.get("/learning/patterns")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_learning_analyze_endpoint(self, client, db_session):
        """POST /learning/analyze retourne 200."""
        resp = client.post("/learning/analyze?profile_type=scalping")
        assert resp.status_code == 200
        data = resp.json()
        assert "dataset_stats" in data
        assert "patterns" in data

    def test_learning_suggestions_endpoint(self, client, db_session):
        """GET /learning/suggestions retourne 200."""
        resp = client.get("/learning/suggestions")
        assert resp.status_code == 200

    def test_learning_versions_endpoint(self, client, db_session):
        """GET /learning/versions retourne 200."""
        resp = client.get("/learning/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "versions" in data

    def test_learning_signals_endpoint(self, client, db_session):
        """GET /learning/signals retourne 200."""
        resp = client.get("/learning/signals")
        assert resp.status_code == 200

    def test_run_start_endpoint(self, client, db_session):
        """POST /learning/run/start crée un run."""
        resp = client.post("/learning/run/start", json={
            "name": "test-api-run",
            "profile_type": "scalping"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-api-run"
        assert data["status"] == "running"

    def test_run_end_endpoint(self, client, db_session):
        """POST /learning/run/{id}/end termine un run."""
        # Démarrer un run
        resp = client.post("/learning/run/start", json={
            "name": "test-end-run",
            "profile_type": "scalping"
        })
        run_id = resp.json()["id"]
        # Terminer
        resp = client.post(f"/learning/run/{run_id}/end")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_runs_list_endpoint(self, client, db_session):
        """GET /learning/runs liste les runs."""
        client.post("/learning/run/start", json={"name": "run1", "profile_type": "scalping"})
        resp = client.get("/learning/runs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_run_metrics_endpoint(self, client, db_session):
        """GET /learning/run/{id}/metrics retourne des métriques."""
        resp = client.post("/learning/run/start", json={"name": "metrics-run", "profile_type": "scalping"})
        run_id = resp.json()["id"]
        resp = client.get(f"/learning/run/{run_id}/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data

    def test_runs_compare_endpoint(self, client, db_session):
        """GET /learning/runs/compare compare deux runs."""
        r1 = client.post("/learning/run/start", json={"name": "before", "profile_type": "scalping"})
        r2 = client.post("/learning/run/start", json={"name": "after", "profile_type": "scalping"})
        resp = client.get(f"/learning/runs/compare?before_id={r1.json()['id']}&after_id={r2.json()['id']}")
        assert resp.status_code == 200
        assert "verdict" in resp.json()

    def test_promote_nonexistent(self, client, db_session):
        """Promouvoir un ajustement inexistant → 404."""
        resp = client.post("/learning/promote/999")
        assert resp.status_code == 404

    def test_rollback_nonexistent(self, client, db_session):
        """Rollback un ajustement inexistant → 404."""
        resp = client.post("/learning/rollback/999")
        assert resp.status_code == 404

