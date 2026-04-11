"""
Tests pour l'export enrichi et le learning runtime v2.0.4.

Couvre :
- EnrichedExportService (export tick-par-tick, gate distribution, missed trends)
- LearningService.learn_from_runtime (suggestions basées sur les tick logs)
- Endpoint GET /audit/enriched-export
- Endpoint POST /learning/learn-runtime
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.enriched_export_service import EnrichedExportService
from app.services.learning_service import LearningService, SAFETY_BOUNDS
from app.models.paper_account import PaperAccount, PaperTrade
from app.models.tick_activity_log import TickActivityLog


# ================================================================
# Helpers
# ================================================================

def _make_account(db, profile="scalping"):
    """Crée un compte paper trading."""
    account = PaperAccount(
        initial_capital=10000.0,
        current_capital=10000.0,
        peak_capital=10000.0,
        is_active=True,
        active_profile=profile,
        max_open_positions=3,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _make_tick(
    db, account_id, action_taken="hold", btc_price=73000.0,
    profile_type="scalping", decision_score=65, decision_action="acheter",
    decision_confidence="medium", reason_no_trade=None, reason_detail=None,
    micro_trend_score=None, market_quality_score=None, volume_ratio=None,
    rejection_category=None, had_open_position=False, trade_id=None,
    ts_offset_seconds=0,
):
    """Crée un tick d'activité."""
    tick = TickActivityLog(
        account_id=account_id,
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=ts_offset_seconds),
        btc_price=btc_price,
        action_taken=action_taken,
        decision_score=decision_score,
        decision_action=decision_action,
        decision_confidence=decision_confidence,
        reason_no_trade=reason_no_trade,
        reason_detail=reason_detail,
        profile_type=profile_type,
        micro_trend_score=micro_trend_score,
        market_quality_score=market_quality_score,
        volume_ratio=volume_ratio,
        rejection_category=rejection_category,
        had_open_position=1 if had_open_position else 0,
        trade_id=trade_id,
    )
    db.add(tick)
    db.commit()
    db.refresh(tick)
    return tick


# ================================================================
# TESTS : EnrichedExportService
# ================================================================

class TestEnrichedExportEmpty:
    """Tests export enrichi sans données."""

    def test_no_account_returns_empty(self, db_session):
        """Sans compte, retourne un export vide."""
        svc = EnrichedExportService(db_session)
        result = svc.build_export()
        assert result.ticks == []
        assert result.summary.total_ticks == 0

    def test_no_ticks_returns_empty(self, db_session):
        """Avec compte mais sans ticks, retourne un export vide."""
        _make_account(db_session)
        svc = EnrichedExportService(db_session)
        result = svc.build_export()
        assert result.ticks == []


class TestEnrichedExportWithData:
    """Tests export enrichi avec données."""

    def _setup_ticks(self, db):
        """Crée un ensemble de ticks scalping réalistes."""
        account = _make_account(db)
        ticks = []
        # 10 ticks bloqués par micro_trend_insufficient
        for i in range(10):
            ticks.append(_make_tick(
                db, account.id,
                btc_price=73000 + i * 10,
                reason_no_trade="micro_trend_insufficient",
                reason_detail=f"micro_trend_score -2 < 2 requis",
                micro_trend_score=-2,
                market_quality_score=55,
                volume_ratio=1.2,
                rejection_category="structure",
                ts_offset_seconds=100 - i * 10,
            ))
        # 3 ticks bloqués par score_too_low
        for i in range(3):
            ticks.append(_make_tick(
                db, account.id,
                btc_price=73100 + i * 5,
                decision_score=20,
                reason_no_trade="score_too_low",
                reason_detail="Score 20 < seuil 30",
                micro_trend_score=1,
                ts_offset_seconds=10 - i * 3,
            ))
        # 1 tick avec trade ouvert
        ticks.append(_make_tick(
            db, account.id,
            btc_price=73200,
            action_taken="opened_long",
            reason_no_trade=None,
            decision_score=65,
            micro_trend_score=3,
            ts_offset_seconds=0,
        ))
        return account, ticks

    def test_ticks_returned(self, db_session):
        """Les ticks sont retournés dans l'export."""
        self._setup_ticks(db_session)
        svc = EnrichedExportService(db_session)
        result = svc.build_export(profile_type="scalping")
        assert len(result.ticks) == 14  # 10 + 3 + 1

    def test_summary_counts(self, db_session):
        """Le résumé contient les bons compteurs."""
        self._setup_ticks(db_session)
        svc = EnrichedExportService(db_session)
        result = svc.build_export(profile_type="scalping")
        assert result.summary.total_ticks == 14
        assert result.summary.total_entries == 1  # 1 opened_long
        assert result.summary.total_holds >= 13  # 10 + 3 holds

    def test_gate_distribution(self, db_session):
        """La distribution des gates est correcte."""
        self._setup_ticks(db_session)
        svc = EnrichedExportService(db_session)
        result = svc.build_export(profile_type="scalping")
        gate_names = [g.gate_name for g in result.summary.gate_distribution]
        assert "micro_trend_insufficient" in gate_names
        assert "score_too_low" in gate_names
        # micro_trend est le gate dominant
        mt_gate = next(
            g for g in result.summary.gate_distribution
            if g.gate_name == "micro_trend_insufficient"
        )
        assert mt_gate.block_count == 10
        # Le gate dominant devrait être micro_trend
        assert result.summary.dominant_gate == "micro_trend_insufficient"

    def test_btc_variation_computed(self, db_session):
        """La variation BTC entre ticks est calculée."""
        self._setup_ticks(db_session)
        svc = EnrichedExportService(db_session)
        result = svc.build_export(profile_type="scalping")
        # Le premier tick n'a pas de variation (pas de précédent)
        # Le deuxième doit avoir une variation
        variations = [t.btc_variation_pct for t in result.ticks if t.btc_variation_pct is not None]
        assert len(variations) > 0

    def test_period_computed(self, db_session):
        """Les dates de période sont correctes."""
        self._setup_ticks(db_session)
        svc = EnrichedExportService(db_session)
        result = svc.build_export(profile_type="scalping")
        assert result.summary.period_start is not None
        assert result.summary.period_end is not None

    def test_filter_by_profile(self, db_session):
        """Le filtre par profil fonctionne."""
        account = _make_account(db_session)
        _make_tick(db_session, account.id, profile_type="scalping",
                   reason_no_trade="score_too_low", ts_offset_seconds=10)
        _make_tick(db_session, account.id, profile_type="aggressive",
                   reason_no_trade="score_too_low", ts_offset_seconds=5)
        svc = EnrichedExportService(db_session)
        result = svc.build_export(profile_type="scalping")
        assert len(result.ticks) == 1
        assert result.ticks[0].profile_type == "scalping"

    def test_entry_exit_flags(self, db_session):
        """Les flags d'entrée et sortie sont corrects."""
        account = _make_account(db_session)
        _make_tick(db_session, account.id, action_taken="opened_long",
                   reason_no_trade=None, ts_offset_seconds=10)
        _make_tick(db_session, account.id, action_taken="hold",
                   reason_no_trade="score_too_low", ts_offset_seconds=5)
        _make_tick(db_session, account.id, action_taken="closed_tp",
                   reason_no_trade=None, ts_offset_seconds=0)
        svc = EnrichedExportService(db_session)
        result = svc.build_export()
        assert result.ticks[0].is_entry is True
        assert result.ticks[1].is_entry is False
        assert result.ticks[2].is_exit is True


class TestEnrichedExportMissedTrends:
    """Tests pour la détection des tendances ratées."""

    def test_detects_missed_uptrend(self, db_session):
        """Détecte une tendance haussière ratée (BTC monte, moteur bloqué)."""
        account = _make_account(db_session)
        base_price = 73000.0
        # 5 ticks hold consécutifs avec BTC qui monte +0.5%
        for i in range(5):
            _make_tick(
                db_session, account.id,
                btc_price=base_price + i * 73,  # +0.5% total
                reason_no_trade="micro_trend_insufficient",
                had_open_position=False,
                ts_offset_seconds=50 - i * 10,
            )
        svc = EnrichedExportService(db_session)
        result = svc.build_export(missed_threshold_pct=0.10)
        # Le mouvement total est ~0.4% — devrait être détecté si > 0.10%
        missed = result.summary.missed_trends
        assert len(missed) >= 1 or result.summary.total_missed_move_pct > 0

    def test_no_missed_trend_when_flat(self, db_session):
        """Pas de tendance ratée si le BTC ne bouge pas."""
        account = _make_account(db_session)
        for i in range(5):
            _make_tick(
                db_session, account.id,
                btc_price=73000.0,  # prix stable
                reason_no_trade="score_too_low",
                had_open_position=False,
                ts_offset_seconds=50 - i * 10,
            )
        svc = EnrichedExportService(db_session)
        result = svc.build_export(missed_threshold_pct=0.15)
        assert len(result.summary.missed_trends) == 0


# ================================================================
# TESTS : LearningService.learn_from_runtime
# ================================================================

class TestLearnFromRuntime:
    """Tests pour l'apprentissage basé sur les tick logs runtime."""

    def test_no_account_returns_empty(self, db_session):
        """Sans compte, retourne une liste vide."""
        svc = LearningService(db_session)
        result = svc.learn_from_runtime("scalping")
        assert result == []

    def test_not_enough_ticks_returns_empty(self, db_session):
        """Avec < 10 ticks, retourne une liste vide."""
        account = _make_account(db_session)
        for i in range(5):
            _make_tick(db_session, account.id,
                       reason_no_trade="micro_trend_insufficient",
                       ts_offset_seconds=i * 10)
        svc = LearningService(db_session)
        result = svc.learn_from_runtime("scalping")
        assert result == []

    def test_detects_micro_trend_overblocking(self, db_session):
        """Détecte que le gate micro-trend bloque > 50% des ticks."""
        account = _make_account(db_session)
        # 15 ticks bloqués par micro_trend_insufficient avec score=65
        for i in range(15):
            _make_tick(
                db_session, account.id,
                decision_score=65,
                decision_action="acheter",
                reason_no_trade="micro_trend_insufficient",
                micro_trend_score=-2,
                ts_offset_seconds=i * 10,
            )
        svc = LearningService(db_session)
        suggestions = svc.learn_from_runtime("scalping")
        # Devrait avoir une suggestion pour min_micro_trend_long
        mt_suggestions = [
            s for s in suggestions
            if s.parameter_name == "min_micro_trend_long"
        ]
        assert len(mt_suggestions) >= 1
        assert mt_suggestions[0].suggested_value < mt_suggestions[0].original_value

    def test_suggestion_is_shadow_mode(self, db_session):
        """Les suggestions runtime sont créées en mode shadow."""
        account = _make_account(db_session)
        for i in range(15):
            _make_tick(
                db_session, account.id,
                decision_score=65,
                reason_no_trade="micro_trend_insufficient",
                ts_offset_seconds=i * 10,
            )
        svc = LearningService(db_session)
        suggestions = svc.learn_from_runtime("scalping")
        for s in suggestions:
            assert s.mode == "shadow"
            assert s.is_active == 0

    def test_no_suggestion_when_balanced_blocks(self, db_session):
        """Pas de suggestion si les refus sont bien répartis (pas de gate dominant)."""
        account = _make_account(db_session)
        # 5 ticks par raison (aucun gate à > 50%)
        for reason in ["score_too_low", "micro_trend_insufficient", "cooldown_active"]:
            for i in range(5):
                _make_tick(
                    db_session, account.id,
                    decision_score=25 if reason == "score_too_low" else 65,
                    reason_no_trade=reason,
                    ts_offset_seconds=i * 10 + (["score_too_low", "micro_trend_insufficient", "cooldown_active"].index(reason) * 100),
                )
        svc = LearningService(db_session)
        suggestions = svc.learn_from_runtime("scalping")
        # micro_trend à 5/15 = 33% < 50% → pas de suggestion 15
        mt_suggestions = [
            s for s in suggestions
            if s.parameter_name == "min_micro_trend_long"
        ]
        assert len(mt_suggestions) == 0


class TestLearnFromRuntimeSafetyBounds:
    """Tests pour les bornes de sécurité du learn_from_runtime."""

    def test_min_micro_trend_long_in_safety_bounds(self):
        """Le paramètre min_micro_trend_long a des bornes de sécurité."""
        assert "min_micro_trend_long" in SAFETY_BOUNDS
        lo, hi = SAFETY_BOUNDS["min_micro_trend_long"]
        assert lo >= 0
        assert hi <= 5


# ================================================================
# TESTS : Endpoint GET /audit/enriched-export
# ================================================================

class TestEnrichedExportEndpoint:
    """Tests de l'endpoint /audit/enriched-export."""

    def test_endpoint_returns_200(self, client):
        """L'endpoint retourne 200."""
        resp = client.get("/audit/enriched-export")
        assert resp.status_code == 200

    def test_endpoint_returns_structure(self, client):
        """L'endpoint retourne la structure attendue."""
        resp = client.get("/audit/enriched-export")
        data = resp.json()
        assert "ticks" in data
        assert "summary" in data
        assert "total_ticks" in data["summary"]
        assert "gate_distribution" in data["summary"]
        assert "missed_trends" in data["summary"]

    def test_endpoint_accepts_profile_filter(self, client):
        """L'endpoint accepte le paramètre profile_type."""
        resp = client.get("/audit/enriched-export?profile_type=scalping")
        assert resp.status_code == 200

    def test_endpoint_accepts_limit(self, client):
        """L'endpoint accepte le paramètre limit."""
        resp = client.get("/audit/enriched-export?limit=100")
        assert resp.status_code == 200

    def test_endpoint_accepts_threshold(self, client):
        """L'endpoint accepte le paramètre missed_threshold_pct."""
        resp = client.get("/audit/enriched-export?missed_threshold_pct=0.5")
        assert resp.status_code == 200


# ================================================================
# TESTS : Endpoint POST /learning/learn-runtime
# ================================================================

class TestLearnRuntimeEndpoint:
    """Tests de l'endpoint /learning/learn-runtime."""

    def test_endpoint_returns_200(self, client):
        """L'endpoint retourne 200."""
        resp = client.post("/learning/learn-runtime")
        assert resp.status_code == 200

    def test_endpoint_returns_list(self, client):
        """L'endpoint retourne une liste (vide ou non)."""
        resp = client.post("/learning/learn-runtime")
        data = resp.json()
        assert isinstance(data, list)

    def test_endpoint_accepts_profile(self, client):
        """L'endpoint accepte le paramètre profile_type."""
        resp = client.post("/learning/learn-runtime?profile_type=scalping")
        assert resp.status_code == 200

