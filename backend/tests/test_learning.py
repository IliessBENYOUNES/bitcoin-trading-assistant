"""
Tests pour le LearningService — apprentissage explicable.

v1.9.0 — Tests record_sample, analyze_patterns, suggest_adjustments,
promote, rollback, safety bounds.
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.learning import LearningSignal, StrategyFeedback
from app.services.learning_service import LearningService, SAFETY_BOUNDS, MIN_SAMPLES


# ================================================================
# Helpers
# ================================================================

def _make_account(db):
    account = PaperAccount(
        initial_capital=10000.0,
        current_capital=10000.0,
        peak_capital=10000.0,
        is_active=True,
        active_profile="scalping",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _make_closed_trade(db, account_id, pnl=5.0, direction="long",
                       status="closed_signal", score=30, slot="scalping",
                       duration_hours=0.1):
    now = datetime.now(timezone.utc)
    trade = PaperTrade(
        account_id=account_id, status=status, direction=direction,
        entry_price=85000.0, exit_price=85000.0 + pnl,
        stop_loss_price=84700, take_profit_price=85300,
        position_size_usd=1000.0, leverage=1.5,
        profile_type="scalping", slot=slot,
        pnl=pnl, pnl_pct=round(pnl / 1500 * 100, 4),
        entry_reason="test", exit_reason="test",
        decision_score=score,
        entry_ts=now - timedelta(hours=duration_hours),
        exit_ts=now,
        duration_hours=duration_hours,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


# ================================================================
# Tests record_sample
# ================================================================

class TestLearningRecordSample:
    """Tests pour l'enregistrement d'échantillons."""

    def test_record_sample_basic(self, db_session):
        """Enregistre un échantillon simple."""
        account = _make_account(db_session)
        trade = _make_closed_trade(db_session, account.id, pnl=5.0)
        svc = LearningService(db_session)
        sample = svc.record_sample(trade)
        assert sample is not None
        assert sample.trade_id == trade.id
        assert sample.pnl_brut == 5.0
        assert sample.was_profitable == 1

    def test_record_sample_losing(self, db_session):
        """Enregistre un échantillon perdant."""
        account = _make_account(db_session)
        trade = _make_closed_trade(db_session, account.id, pnl=-3.0)
        svc = LearningService(db_session)
        sample = svc.record_sample(trade)
        assert sample.was_profitable == 0

    def test_record_sample_none_trade(self, db_session):
        """Retourne None si trade est None."""
        svc = LearningService(db_session)
        assert svc.record_sample(None) is None

    def test_record_sample_short(self, db_session):
        """Enregistre un échantillon short."""
        account = _make_account(db_session)
        trade = _make_closed_trade(db_session, account.id, direction="short")
        svc = LearningService(db_session)
        sample = svc.record_sample(trade)
        assert sample.direction == "short"

    def test_record_sample_with_reversal(self, db_session):
        """Enregistre un échantillon reversal."""
        account = _make_account(db_session)
        trade = _make_closed_trade(db_session, account.id)
        svc = LearningService(db_session)
        sample = svc.record_sample(trade, was_reversal=True)
        assert sample.was_reversal == 1

    def test_record_sample_with_cooldown_info(self, db_session):
        """Enregistre le contexte cooldown."""
        account = _make_account(db_session)
        trade = _make_closed_trade(db_session, account.id)
        svc = LearningService(db_session)
        sample = svc.record_sample(trade, time_since_last_trade_min=3.5, cooldown_configured_min=2.0)
        assert sample.time_since_last_trade_min == 3.5
        assert sample.cooldown_configured_min == 2.0


# ================================================================
# Tests dataset stats
# ================================================================

class TestLearningDatasetStats:
    """Tests pour les statistiques du dataset."""

    def test_empty_dataset(self, db_session):
        """Dataset vide retourne des zéros."""
        svc = LearningService(db_session)
        stats = svc.get_dataset_stats()
        assert stats.total_samples == 0

    def test_dataset_with_samples(self, db_session):
        """Dataset avec échantillons retourne des stats correctes."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        for pnl in [5.0, -3.0, 2.0, -1.0, 4.0]:
            trade = _make_closed_trade(db_session, account.id, pnl=pnl)
            svc.record_sample(trade)
        stats = svc.get_dataset_stats()
        assert stats.total_samples == 5
        assert stats.samples_profitable == 3
        assert stats.samples_unprofitable == 2

    def test_dataset_direction_breakdown(self, db_session):
        """Breakdown par direction."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        for _ in range(3):
            trade = _make_closed_trade(db_session, account.id, direction="long")
            svc.record_sample(trade)
        for _ in range(2):
            trade = _make_closed_trade(db_session, account.id, direction="short")
            svc.record_sample(trade)
        stats = svc.get_dataset_stats()
        assert stats.long_samples == 3
        assert stats.short_samples == 2


# ================================================================
# Tests analyze_patterns
# ================================================================

class TestLearningPatterns:
    """Tests pour l'analyse de patterns."""

    def test_no_patterns_insufficient_data(self, db_session):
        """Pas assez de données → pas de patterns."""
        svc = LearningService(db_session)
        patterns = svc.analyze_patterns()
        assert patterns == []

    def test_patterns_with_enough_data(self, db_session):
        """Avec assez de données, des patterns sont identifiés."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        # Créer 15 échantillons
        for i in range(15):
            pnl = 5.0 if i % 2 == 0 else -3.0
            trade = _make_closed_trade(db_session, account.id, pnl=pnl, score=30 + i)
            svc.record_sample(trade)
        patterns = svc.analyze_patterns()
        assert len(patterns) > 0


# ================================================================
# Tests suggest_adjustments
# ================================================================

class TestLearningSuggestions:
    """Tests pour les suggestions d'ajustements."""

    def test_no_suggestions_insufficient_data(self, db_session):
        """Pas assez de données → pas de suggestions."""
        svc = LearningService(db_session)
        suggestions = svc.suggest_adjustments("scalping")
        assert suggestions == []

    def test_suggestions_bounded(self, db_session):
        """Les suggestions respectent les safety bounds."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        # Créer des échantillons avec trailing stop perdant
        for _ in range(10):
            trade = _make_closed_trade(db_session, account.id, pnl=-2.0,
                                       status="closed_trailing_stop")
            svc.record_sample(trade)
        suggestions = svc.suggest_adjustments("scalping")
        for s in suggestions:
            bounds = SAFETY_BOUNDS.get(s.parameter_name)
            if bounds:
                assert s.suggested_value >= bounds[0]
                assert s.suggested_value <= bounds[1]


# ================================================================
# Tests promote / rollback
# ================================================================

class TestLearningPromoteRollback:
    """Tests pour la promotion et le rollback des ajustements."""

    def test_promote_adjustment(self, db_session):
        """Promouvoir un ajustement passe en mode applied."""
        svc = LearningService(db_session)
        fb = StrategyFeedback(
            parameter_name="buy_threshold",
            original_value=20, suggested_value=25, current_value=20,
            reason="Test", sample_size=10, version=1, mode="shadow",
            profile_type="scalping",
        )
        db_session.add(fb)
        db_session.commit()
        db_session.refresh(fb)

        promoted = svc.promote_adjustment(fb.id)
        assert promoted.mode == "applied"
        assert promoted.is_active == 1
        assert promoted.current_value == 25

    def test_rollback_adjustment(self, db_session):
        """Rollback un ajustement restaure la valeur originale."""
        svc = LearningService(db_session)
        fb = StrategyFeedback(
            parameter_name="buy_threshold",
            original_value=20, suggested_value=25, current_value=25,
            reason="Test", sample_size=10, version=1, mode="applied",
            is_active=1, profile_type="scalping",
        )
        db_session.add(fb)
        db_session.commit()
        db_session.refresh(fb)

        rolled = svc.rollback_adjustment(fb.id)
        assert rolled.mode == "rolled_back"
        assert rolled.is_active == 0
        assert rolled.current_value == 20

    def test_promote_nonexistent(self, db_session):
        """Promouvoir un ID inexistant retourne None."""
        svc = LearningService(db_session)
        assert svc.promote_adjustment(999) is None

    def test_rollback_nonexistent(self, db_session):
        """Rollback un ID inexistant retourne None."""
        svc = LearningService(db_session)
        assert svc.rollback_adjustment(999) is None


# ================================================================
# Tests version history
# ================================================================

class TestLearningVersionHistory:
    """Tests pour l'historique des versions."""

    def test_empty_history(self, db_session):
        """Historique vide."""
        svc = LearningService(db_session)
        hist = svc.get_version_history()
        assert hist.current_version == 0
        assert hist.versions == []

    def test_history_with_feedback(self, db_session):
        """Historique avec des ajustements."""
        db_session.add(StrategyFeedback(
            parameter_name="buy_threshold",
            original_value=20, suggested_value=25, current_value=20,
            reason="Test", sample_size=10, version=1, mode="shadow",
            profile_type="scalping",
        ))
        db_session.commit()
        svc = LearningService(db_session)
        hist = svc.get_version_history()
        assert hist.current_version == 1
        assert len(hist.versions) == 1


# ================================================================
# Tests safety bounds
# ================================================================

class TestSafetyBounds:
    """Tests pour les bornes de sécurité."""

    def test_all_params_have_bounds(self):
        """Tous les paramètres importants ont des bornes."""
        important = ["buy_threshold", "sell_threshold", "trailing_stop_pct",
                     "stale_exit_minutes", "cooldown_minutes", "min_score"]
        for param in important:
            assert param in SAFETY_BOUNDS

    def test_bounds_are_reasonable(self):
        """Les bornes sont raisonnables (min < max)."""
        for param, (lo, hi) in SAFETY_BOUNDS.items():
            assert lo < hi, f"{param}: min ({lo}) >= max ({hi})"

    def test_min_samples_is_positive(self):
        """MIN_SAMPLES est positif."""
        assert MIN_SAMPLES > 0

