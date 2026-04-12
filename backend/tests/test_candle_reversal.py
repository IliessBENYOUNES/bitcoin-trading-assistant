"""
Tests pour le Candle Reversal Exit — v2.0.18.

Tests :
- TickMomentumService.check_candle_reversal
- Intégration dans paper_trading_service (closed_candle_reversal)
- reversal_delay_seconds dans LearningSignal
- Pattern 9 d'analyse reversal delay dans learning
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.tick_momentum_service import TickMomentumService


# ================================================================
# TickMomentumService — check_candle_reversal
# ================================================================

class TestCandleReversalDetection:
    """Tests pour la détection de reversal via TickMomentumService."""

    def setup_method(self):
        """Nettoyer les buffers avant chaque test."""
        TickMomentumService.clear_buffer()

    def test_no_data_no_reversal(self):
        """Pas de données → pas de reversal."""
        should_exit, delay, reason = TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="green",
            trade_direction="long", min_reversal_seconds=3.0,
        )
        assert should_exit is False
        assert delay == 0.0

    def test_same_direction_no_reversal(self):
        """Prix continue dans la même direction → pas de reversal."""
        base = datetime.now(timezone.utc) - timedelta(seconds=20)
        # Simuler des prix en hausse (green) pour un long entré green
        for i in range(10):
            TickMomentumService.record_tick(
                "test", 80000 + i * 10, base + timedelta(seconds=i * 2)
            )

        should_exit, delay, reason = TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="green",
            trade_direction="long", window_seconds=15.0,
            min_ticks=2, min_reversal_seconds=3.0,
        )
        assert should_exit is False
        assert "Pas de reversal" in reason

    def test_reversal_detected_but_too_short(self):
        """Reversal détecté mais pas assez long → pas de sortie."""
        base = datetime.now(timezone.utc) - timedelta(seconds=10)
        # Prix en baisse (red) pour un long entré green
        for i in range(5):
            TickMomentumService.record_tick(
                "test", 80000 - i * 20, base + timedelta(seconds=i * 2)
            )

        # Premier appel → enregistre le début du reversal
        should_exit, delay, reason = TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="green",
            trade_direction="long", min_reversal_seconds=10.0,
        )
        assert should_exit is False
        assert "Reversal" in reason

    def test_reversal_confirmed_after_delay(self):
        """Reversal confirmé après le délai minimum → sortie."""
        base = datetime.now(timezone.utc) - timedelta(seconds=20)
        # Prix en baisse (red) pour un long entré green
        for i in range(10):
            TickMomentumService.record_tick(
                "test", 80000 - i * 20, base + timedelta(seconds=i * 2)
            )

        # Premier appel → enregistre le début
        TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="green",
            trade_direction="long", min_reversal_seconds=3.0,
        )

        # Simuler que le reversal a commencé il y a 5 secondes (> 3s min)
        TickMomentumService._reversal_start["test"] = datetime.now(timezone.utc) - timedelta(seconds=5)

        # Ajouter un tick récent pour que detect_direction fonctionne
        now = datetime.now(timezone.utc)
        TickMomentumService.record_tick("test", 79600, now)

        # Deuxième appel → reversal confirmé (5s > 3s)
        should_exit, delay, reason = TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="green",
            trade_direction="long", min_reversal_seconds=3.0,
        )
        assert should_exit is True
        assert delay >= 3.0
        assert "confirmé" in reason

    def test_reversal_cancelled_when_direction_returns(self):
        """Reversal annulé si le prix revient dans la bonne direction."""
        base = datetime.now(timezone.utc) - timedelta(seconds=20)
        # D'abord en baisse (reversal)
        for i in range(5):
            TickMomentumService.record_tick(
                "test", 80000 - i * 20, base + timedelta(seconds=i * 2)
            )

        # Enregistrer le début du reversal
        TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="green",
            trade_direction="long", min_reversal_seconds=5.0,
        )

        # Maintenant le prix remonte (green)
        later = datetime.now(timezone.utc)
        for i in range(10):
            TickMomentumService.record_tick(
                "test", 79900 + i * 30, later + timedelta(seconds=i)
            )

        should_exit, delay, reason = TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="green",
            trade_direction="long", min_reversal_seconds=5.0,
        )
        assert should_exit is False

    def test_short_reversal_on_green(self):
        """Pour un short entré red, une bougie verte est un reversal."""
        base = datetime.now(timezone.utc) - timedelta(seconds=15)
        # Prix en hausse (green) → mauvais pour un short
        for i in range(8):
            TickMomentumService.record_tick(
                "test", 80000 + i * 15, base + timedelta(seconds=i * 2)
            )

        # Premier appel → enregistre le début du reversal
        TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="red",
            trade_direction="short", min_reversal_seconds=3.0,
        )

        # Simuler que le reversal a commencé il y a 5 secondes
        TickMomentumService._reversal_start["test"] = datetime.now(timezone.utc) - timedelta(seconds=5)

        now = datetime.now(timezone.utc)
        TickMomentumService.record_tick("test", 80120, now)

        should_exit, delay, reason = TickMomentumService.check_candle_reversal(
            slot="test", entry_candle_direction="red",
            trade_direction="short", min_reversal_seconds=3.0,
        )
        assert should_exit is True
        assert "confirmé" in reason

    def test_reset_reversal(self):
        """reset_reversal vide le tracker."""
        TickMomentumService._reversal_start["test"] = datetime.now(timezone.utc)
        TickMomentumService.reset_reversal("test")
        assert TickMomentumService._reversal_start.get("test") is None

    def test_clear_buffer_clears_reversal(self):
        """clear_buffer vide aussi le tracker de reversal."""
        TickMomentumService._reversal_start["test"] = datetime.now(timezone.utc)
        TickMomentumService.clear_buffer()
        assert TickMomentumService._reversal_start.get("test") is None


# ================================================================
# LearningSignal — reversal_delay_seconds
# ================================================================

class TestReversalDelayInLearning:
    """Tests pour le champ reversal_delay_seconds dans LearningSignal."""

    def test_record_sample_with_reversal_delay(self, db_session):
        """record_sample enregistre le reversal_delay_seconds du trade."""
        from app.models.paper_account import PaperAccount, PaperTrade
        from app.services.learning_service import LearningService
        from app.models.learning import LearningSignal

        account = PaperAccount(
            initial_capital=10000, current_capital=10000,
            peak_capital=10000, is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.commit()

        trade = PaperTrade(
            account_id=account.id, status="closed_candle_reversal",
            direction="long", entry_price=80000, exit_price=79950,
            stop_loss_price=79800, take_profit_price=80200,
            position_size_usd=2500, pnl=-1.56, pnl_pct=-0.06,
            entry_reason="test", duration_hours=0.01,
            entry_ts=datetime.now(timezone.utc) - timedelta(minutes=1),
            exit_ts=datetime.now(timezone.utc),
            entry_candle_direction="green",
            exit_candle_direction="red",
            reversal_delay_seconds=4.2,
        )
        db_session.add(trade)
        db_session.commit()

        svc = LearningService(db_session)
        sample = svc.record_sample(trade)

        assert sample is not None
        assert sample.reversal_delay_seconds == 4.2
        assert sample.exit_type == "closed_candle_reversal"
        assert sample.entry_candle_direction == "green"
        assert sample.exit_candle_direction == "red"

    def test_record_sample_without_reversal_delay(self, db_session):
        """record_sample gère l'absence de reversal_delay_seconds."""
        from app.models.paper_account import PaperAccount, PaperTrade
        from app.services.learning_service import LearningService

        account = PaperAccount(
            initial_capital=10000, current_capital=10000,
            peak_capital=10000, is_active=True, active_profile="scalping",
        )
        db_session.add(account)
        db_session.commit()

        trade = PaperTrade(
            account_id=account.id, status="closed_trailing_stop",
            direction="long", entry_price=80000, exit_price=80100,
            stop_loss_price=79800, take_profit_price=80500,
            position_size_usd=2500, pnl=3.12, pnl_pct=0.12,
            entry_reason="test", duration_hours=0.02,
            entry_ts=datetime.now(timezone.utc) - timedelta(minutes=1),
            exit_ts=datetime.now(timezone.utc),
            entry_candle_direction="green",
            exit_candle_direction="green",
        )
        db_session.add(trade)
        db_session.commit()

        svc = LearningService(db_session)
        sample = svc.record_sample(trade)

        assert sample is not None
        assert sample.reversal_delay_seconds is None


# ================================================================
# Pattern 9 — Reversal delay analysis
# ================================================================

class TestReversalDelayPatterns:
    """Tests pour le Pattern 9 dans analyze_patterns."""

    def _make_sample(self, db, **kwargs):
        """Helper pour créer un LearningSignal."""
        from app.models.learning import LearningSignal
        defaults = dict(
            trade_id=0, direction="long", slot="scalping",
            profile_type="scalping", exit_type="closed_candle_reversal",
            pnl_brut=-1.0, pnl_pct=-0.04, was_profitable=0,
            duration_minutes=1.5, entry_candle_direction="green",
            exit_candle_direction="red",
        )
        defaults.update(kwargs)
        s = LearningSignal(**defaults)
        db.add(s)
        return s

    def test_pattern_reversal_delay_fast_vs_slow(self, db_session):
        """Pattern 9 : analyse fast vs slow reversal delay."""
        from app.services.learning_service import LearningService

        # 3 fast reversals (< 5s)
        for i in range(3):
            self._make_sample(db_session, trade_id=i + 1,
                              reversal_delay_seconds=2.0 + i * 0.5,
                              pnl_brut=-0.5, was_profitable=0)
        # 3 slow reversals (≥ 5s)
        for i in range(3):
            self._make_sample(db_session, trade_id=i + 10,
                              reversal_delay_seconds=8.0 + i * 2,
                              pnl_brut=-3.0, was_profitable=0)
        # 5 trades sans reversal (pour atteindre MIN_SAMPLES=10)
        for i in range(5):
            self._make_sample(db_session, trade_id=i + 20,
                              reversal_delay_seconds=None,
                              exit_type="closed_trailing_stop",
                              pnl_brut=2.0, was_profitable=1)
        db_session.commit()

        svc = LearningService(db_session)
        patterns = svc.analyze_patterns()

        # Vérifier qu'on a des patterns de reversal
        reversal_patterns = [p for p in patterns if "reversal" in p.pattern_name.lower()]
        assert len(reversal_patterns) >= 1, f"Attendu au moins 1 pattern reversal, obtenu: {[p.pattern_name for p in patterns]}"

    def test_pattern_reversal_vs_normal_exit(self, db_session):
        """Méta-pattern : trades avec reversal vs sans reversal."""
        from app.services.learning_service import LearningService

        # 4 trades avec reversal
        for i in range(4):
            self._make_sample(db_session, trade_id=i + 1,
                              reversal_delay_seconds=3.0 + i,
                              pnl_brut=-1.5, was_profitable=0)
        # 6 trades sans reversal
        for i in range(6):
            self._make_sample(db_session, trade_id=i + 10,
                              reversal_delay_seconds=None,
                              exit_type="closed_trailing_stop",
                              pnl_brut=1.5, was_profitable=1)
        db_session.commit()

        svc = LearningService(db_session)
        patterns = svc.analyze_patterns()

        # Le méta-pattern compare reversal vs normal
        meta = [p for p in patterns if p.pattern_name == "reversal_exit_vs_normal"]
        assert len(meta) >= 1, f"Méta-pattern reversal_exit_vs_normal non trouvé: {[p.pattern_name for p in patterns]}"
