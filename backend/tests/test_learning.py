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


# Helper enrichi pour créer des trades avec candle directions
def _make_candle_trade(db, account_id, pnl, direction, entry_candle, exit_candle,
                       status="closed_signal", duration_hours=0.01, score=30):
    """Crée un trade fermé avec candle directions renseignées."""
    now = datetime.now(timezone.utc)
    trade = PaperTrade(
        account_id=account_id, status=status, direction=direction,
        entry_price=85000.0, exit_price=85000.0 + pnl,
        stop_loss_price=84700, take_profit_price=85300,
        position_size_usd=1000.0, leverage=1.5,
        profile_type="scalping", slot="scalping",
        pnl=pnl, pnl_pct=round(pnl / 1500 * 100, 4),
        entry_reason="test", exit_reason="test",
        decision_score=score,
        entry_ts=now - timedelta(hours=duration_hours),
        exit_ts=now,
        duration_hours=duration_hours,
        entry_candle_direction=entry_candle,
        exit_candle_direction=exit_candle,
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

    def test_candle_pattern_same_aligned_detected(self, db_session):
        """Le pattern 'same_aligned' est détecté (long + green→green)."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        # Créer 12 trades : 6 long green→green (gagnants) + 6 longs red→green (perdants)
        for _ in range(6):
            t = _make_candle_trade(db_session, account.id, pnl=2.0, direction="long",
                                   entry_candle="green", exit_candle="green")
            svc.record_sample(t)
        for _ in range(6):
            t = _make_candle_trade(db_session, account.id, pnl=-1.5, direction="long",
                                   entry_candle="green", exit_candle="red")
            svc.record_sample(t)
        patterns = svc.analyze_patterns()
        names = [p.pattern_name for p in patterns]
        assert "candle_same_aligned" in names

    def test_candle_pattern_reversed_against_detected(self, db_session):
        """Le pattern 'reversed_against' est détecté (long + green→red = momentum perdu)."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        for _ in range(6):
            t = _make_candle_trade(db_session, account.id, pnl=2.0, direction="long",
                                   entry_candle="green", exit_candle="green")
            svc.record_sample(t)
        for _ in range(6):
            t = _make_candle_trade(db_session, account.id, pnl=-1.0, direction="long",
                                   entry_candle="green", exit_candle="red")
            svc.record_sample(t)
        patterns = svc.analyze_patterns()
        names = [p.pattern_name for p in patterns]
        assert "candle_reversed_against" in names

    def test_candle_meta_pattern_consistency_vs_reversal(self, db_session):
        """Le méta-pattern same vs reversed est calculé."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        for _ in range(6):
            t = _make_candle_trade(db_session, account.id, pnl=3.0, direction="long",
                                   entry_candle="green", exit_candle="green")
            svc.record_sample(t)
        for _ in range(6):
            t = _make_candle_trade(db_session, account.id, pnl=-2.0, direction="long",
                                   entry_candle="green", exit_candle="red")
            svc.record_sample(t)
        patterns = svc.analyze_patterns()
        meta = [p for p in patterns if p.pattern_name == "candle_consistency_vs_reversal"]
        assert len(meta) == 1
        # same color wins (3.0 avg) vs reversed loses (-2.0 avg)
        assert meta[0].avg_pnl > 0  # delta favorable

    def test_candle_duration_cross_analysis(self, db_session):
        """Le croisement durée × candle est détecté (pattern 8)."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        # Trades rapides (<2min = 0.03h) avec même couleur = bons
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=1.5, direction="long",
                                   entry_candle="green", exit_candle="green",
                                   duration_hours=0.01)
            svc.record_sample(t)
        # Trades rapides (<2min) avec changement de couleur = mauvais
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=-1.0, direction="long",
                                   entry_candle="green", exit_candle="red",
                                   duration_hours=0.01)
            svc.record_sample(t)
        # On a besoin de 10 minimum pour analyze_patterns
        patterns = svc.analyze_patterns()
        names = [p.pattern_name for p in patterns]
        assert "duration_candle_fast_same_candle" in names
        assert "duration_candle_fast_reversed_candle" in names

    def test_candle_short_direction_patterns(self, db_session):
        """Les patterns candle fonctionnent aussi pour les shorts."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        # Short + red→red = same_aligned (favorable pour un short)
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=2.0, direction="short",
                                   entry_candle="red", exit_candle="red")
            svc.record_sample(t)
        # Short + red→green = reversed_against (défavorable pour un short)
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=-1.5, direction="short",
                                   entry_candle="red", exit_candle="green")
            svc.record_sample(t)
        patterns = svc.analyze_patterns()
        names = [p.pattern_name for p in patterns]
        assert "candle_same_aligned" in names
        assert "candle_reversed_against" in names

    def test_candle_pattern_impact_correct(self, db_session):
        """Le pattern same_aligned gagnant a un impact positif, reversed_against perdant a un impact négatif."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        for _ in range(6):
            t = _make_candle_trade(db_session, account.id, pnl=3.0, direction="long",
                                   entry_candle="green", exit_candle="green")
            svc.record_sample(t)
        for _ in range(6):
            t = _make_candle_trade(db_session, account.id, pnl=-2.0, direction="long",
                                   entry_candle="green", exit_candle="red")
            svc.record_sample(t)
        patterns = svc.analyze_patterns()
        by_name = {p.pattern_name: p for p in patterns}
        assert by_name["candle_same_aligned"].impact == "positif"
        assert by_name["candle_reversed_against"].impact == "négatif"


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

    def test_suggestion_candle_reversal_destructive(self, db_session):
        """Si les trades avec changement de couleur défavorable sont perdants → suggestion stale_negative."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        # 5 trades "same color" gagnants + 5 trades "reversed_against" très perdants
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=2.0, direction="long",
                                   entry_candle="green", exit_candle="green")
            svc.record_sample(t)
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=-3.0, direction="long",
                                   entry_candle="green", exit_candle="red")
            svc.record_sample(t)
        suggestions = svc.suggest_adjustments("scalping")
        candle_sugg = [s for s in suggestions if "CANDLE" in (s.reason or "")]
        assert len(candle_sugg) >= 1
        # La suggestion doit toucher stale_negative_exit_minutes
        params = [s.parameter_name for s in candle_sugg]
        assert "stale_negative_exit_minutes" in params

    def test_suggestion_entry_counter_trend(self, db_session):
        """Si entrer contre le momentum est nettement pire → suggestion min_micro_trend_long."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        # 5 trades entrée alignée (long + green entry) → gagnants
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=3.0, direction="long",
                                   entry_candle="green", exit_candle="green")
            svc.record_sample(t)
        # 5 trades entrée contre-tendance (long + red entry) → très perdants
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=-4.0, direction="long",
                                   entry_candle="red", exit_candle="red")
            svc.record_sample(t)
        suggestions = svc.suggest_adjustments("scalping")
        trend_sugg = [s for s in suggestions if "CONTRE-TENDANCE" in (s.reason or "")]
        assert len(trend_sugg) >= 1
        params = [s.parameter_name for s in trend_sugg]
        assert "min_micro_trend_long" in params

    def test_no_candle_suggestion_with_mixed_results(self, db_session):
        """Si les reversals ne sont pas nettement perdants, pas de suggestion candle."""
        account = _make_account(db_session)
        svc = LearningService(db_session)
        # 5 trades same color gagnants
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=1.0, direction="long",
                                   entry_candle="green", exit_candle="green")
            svc.record_sample(t)
        # 5 trades reversed AUSSI gagnants → pas de problème → pas de suggestion
        for _ in range(5):
            t = _make_candle_trade(db_session, account.id, pnl=0.5, direction="long",
                                   entry_candle="green", exit_candle="red")
            svc.record_sample(t)
        suggestions = svc.suggest_adjustments("scalping")
        candle_sugg = [s for s in suggestions if "CANDLE CRITIQUE" in (s.reason or "")]
        assert len(candle_sugg) == 0  # Pas de suggestion si pas de problème


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

