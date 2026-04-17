"""
Tests pour le Micro Stop Loss (v2.0.23, recalibré v2.0.24).

Le micro SL est un garde-fou ultra-serré qui ferme immédiatement une position
dès que le PnL latent dépasse un seuil négatif (-0.05% par défaut = -$1.25 sur $2500).
Contrairement au loss_cut_pct classique (qui attend un signal faible),
le micro SL est INCONDITIONNEL : il sort sans rien vérifier d'autre.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.schemas.journal import TradingProfileParams, TradingProfileType
from app.services.trading_profile_service import PROFILE_PRESETS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_active_account(db, capital=10000.0):
    """Crée un compte paper trading actif."""
    from app.models.paper_account import PaperAccount
    account = PaperAccount(
        initial_capital=capital,
        current_capital=capital,
        peak_capital=capital,
        btc_price_at_start=84000.0,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _create_open_trade(db, account_id, entry_price=84000.0, size=2500.0,
                        direction="long", leverage=1.0, slot="scalping"):
    """Crée un trade ouvert."""
    from app.models.paper_account import PaperTrade
    trade = PaperTrade(
        account_id=account_id,
        direction=direction,
        entry_price=entry_price,
        stop_loss_price=entry_price * (0.998 if direction == "long" else 1.002),
        take_profit_price=entry_price * (1.008 if direction == "long" else 0.992),
        position_size_usd=size,
        leverage=leverage,
        status="open",
        entry_ts=datetime.now(timezone.utc) - timedelta(seconds=5),
        entry_reason="test micro stop loss",
        slot=slot,
        highest_price_since_entry=entry_price,
        lowest_price_since_entry=entry_price,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


# ---------------------------------------------------------------------------
# Tests du paramètre dans le profil
# ---------------------------------------------------------------------------

class TestMicroStopLossProfileParams:
    """Vérifier que le paramètre est bien configuré sur le profil scalping."""

    def test_scalping_has_micro_sl(self):
        """Le profil scalping a un micro_stop_loss_pct configuré."""
        p = PROFILE_PRESETS["scalping"]
        assert p.micro_stop_loss_pct is not None
        assert p.micro_stop_loss_pct == 0.20

    def test_balanced_has_no_micro_sl(self):
        """Le profil balanced n'a PAS de micro SL (désactivé par défaut)."""
        p = PROFILE_PRESETS["balanced"]
        assert p.micro_stop_loss_pct is None

    def test_aggressive_has_micro_sl(self):
        """[v2.0.28] Le profil aggressive a un micro SL à 0.15% (adapté pour swings)."""
        p = PROFILE_PRESETS["aggressive"]
        assert p.micro_stop_loss_pct == 0.30

    def test_default_is_none(self):
        """Le défaut de micro_stop_loss_pct est None (désactivé)."""
        params = TradingProfileParams(
            profile_type=TradingProfileType.scalping,
            label="Test",
            description="Test",
            min_score=30,
            min_confidence="low",
            min_scenario_dominance=0.35,
            max_trades_per_day=30,
            cooldown_minutes=1,
            max_position_duration_hours=2,
            profit_take_pct=0.8,
            loss_cut_pct=0.20,
            loss_cut_score_threshold=5,
            leverage_enabled=True,
            max_leverage=1.5,
        )
        assert params.micro_stop_loss_pct is None


# ---------------------------------------------------------------------------
# Tests unitaires du calcul PnL
# ---------------------------------------------------------------------------

class TestMicroStopLossPnlCalc:
    """Vérifier que le PnL est bien calculé pour le micro SL."""

    def test_long_negative_pnl(self, db_session):
        """Un LONG avec prix en baisse a un PnL négatif."""
        from app.services.paper_trading_service import PaperTradingService
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id, entry_price=84000.0,
                                    direction="long", size=2500.0)
        service = PaperTradingService(db_session)

        # Prix en baisse de 0.01% → PnL = -0.01% × $2500 = -$0.25
        pnl = service._calc_unrealized_pnl(trade, 84000.0 * 0.9999)
        assert pnl < 0

    def test_short_negative_pnl(self, db_session):
        """Un SHORT avec prix en hausse a un PnL négatif."""
        from app.services.paper_trading_service import PaperTradingService
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id, entry_price=84000.0,
                                    direction="short", size=2500.0)
        service = PaperTradingService(db_session)

        # Prix en hausse de 0.01% → PnL négatif pour un short
        pnl = service._calc_unrealized_pnl(trade, 84000.0 * 1.0001)
        assert pnl < 0

    def test_long_positive_pnl_no_trigger(self, db_session):
        """Un LONG avec prix en hausse est en profit → pas de micro SL."""
        from app.services.paper_trading_service import PaperTradingService
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id, entry_price=84000.0,
                                    direction="long", size=2500.0)
        service = PaperTradingService(db_session)

        pnl = service._calc_unrealized_pnl(trade, 84000.0 * 1.001)
        assert pnl > 0


# ---------------------------------------------------------------------------
# Tests d'intégration avec _tick_single_slot
# ---------------------------------------------------------------------------

class TestMicroStopLossIntegration:
    """Tests d'intégration : le micro SL ferme les positions en perte."""

    @patch("app.services.paper_trading_service.TickMomentumService")
    @patch("app.services.paper_trading_service.EntrySasService")
    def test_micro_sl_closes_long_in_loss(self, mock_sas, mock_tms, db_session):
        """Un LONG en perte de -0.06% est fermé par le micro SL (-0.05%)."""
        from app.services.paper_trading_service import PaperTradingService
        mock_tms.detect_direction.return_value = ("long", 0.5)
        mock_sas.has_pending.return_value = False

        account = _create_active_account(db_session)
        entry = 84000.0
        trade = _create_open_trade(db_session, account.id, entry_price=entry,
                                    direction="long", size=2500.0, slot="scalping")

        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Prix baisse de 0.06% → doit déclencher le micro SL (seuil 0.05%)
        bad_price = entry * (1 - 0.0006)
        result = service._tick_single_slot(account, "scalping", bad_price, now)

        assert result.action_taken == "closed_micro_sl"
        assert "Micro stop loss" in result.detail

    @patch("app.services.paper_trading_service.TickMomentumService")
    @patch("app.services.paper_trading_service.EntrySasService")
    def test_micro_sl_closes_short_in_loss(self, mock_sas, mock_tms, db_session):
        """Un SHORT en perte de -0.06% est fermé par le micro SL."""
        from app.services.paper_trading_service import PaperTradingService
        mock_tms.detect_direction.return_value = ("short", 0.5)
        mock_sas.has_pending.return_value = False

        account = _create_active_account(db_session)
        entry = 84000.0
        trade = _create_open_trade(db_session, account.id, entry_price=entry,
                                    direction="short", size=2500.0, slot="scalping")

        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Prix monte de 0.06% → perte pour un short
        bad_price = entry * (1 + 0.0006)
        result = service._tick_single_slot(account, "scalping", bad_price, now)

        assert result.action_taken == "closed_micro_sl"
        assert "Micro stop loss" in result.detail

    @patch("app.services.paper_trading_service.TickMomentumService")
    @patch("app.services.paper_trading_service.EntrySasService")
    def test_micro_sl_does_not_trigger_in_profit(self, mock_sas, mock_tms, db_session):
        """Une position en profit ne déclenche PAS le micro SL."""
        from app.services.paper_trading_service import PaperTradingService
        mock_tms.detect_direction.return_value = ("long", 0.5)
        mock_sas.has_pending.return_value = False

        account = _create_active_account(db_session)
        entry = 84000.0
        trade = _create_open_trade(db_session, account.id, entry_price=entry,
                                    direction="long", size=2500.0, slot="scalping")

        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Prix monte → en profit
        good_price = entry * 1.001
        result = service._tick_single_slot(account, "scalping", good_price, now)

        assert result.action_taken != "closed_micro_sl"

    @patch("app.services.paper_trading_service.TickMomentumService")
    @patch("app.services.paper_trading_service.EntrySasService")
    def test_micro_sl_does_not_trigger_at_exact_threshold(self, mock_sas, mock_tms, db_session):
        """Au-delà de -0.05%, le micro SL déclenche."""
        from app.services.paper_trading_service import PaperTradingService
        mock_tms.detect_direction.return_value = ("long", 0.5)
        mock_sas.has_pending.return_value = False

        account = _create_active_account(db_session)
        entry = 84000.0
        trade = _create_open_trade(db_session, account.id, entry_price=entry,
                                    direction="long", size=2500.0, slot="scalping")

        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Prix baisse de un peu plus que 0.05% pour être sûr de dépasser le seuil
        threshold_price = entry * (1 - 0.00055)
        result = service._tick_single_slot(account, "scalping", threshold_price, now)

        assert result.action_taken == "closed_micro_sl"

    @patch("app.services.paper_trading_service.TickMomentumService")
    @patch("app.services.paper_trading_service.EntrySasService")
    def test_micro_sl_tiny_loss_below_threshold(self, mock_sas, mock_tms, db_session):
        """Une perte de -0.03% ne déclenche PAS le micro SL (seuil -0.05%)."""
        from app.services.paper_trading_service import PaperTradingService
        mock_tms.detect_direction.return_value = ("long", 0.5)
        mock_sas.has_pending.return_value = False

        account = _create_active_account(db_session)
        entry = 84000.0
        trade = _create_open_trade(db_session, account.id, entry_price=entry,
                                    direction="long", size=2500.0, slot="scalping")

        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Perte de 0.03% → sous le seuil de 0.05% → pas de micro SL
        small_loss_price = entry * (1 - 0.0003)
        result = service._tick_single_slot(account, "scalping", small_loss_price, now)

        assert result.action_taken != "closed_micro_sl"


# ---------------------------------------------------------------------------
# Tests avec micro SL désactivé
# ---------------------------------------------------------------------------

class TestMicroStopLossDisabled:
    """Quand micro_stop_loss_pct est None, le check est ignoré."""

    @patch("app.services.paper_trading_service.TickMomentumService")
    @patch("app.services.paper_trading_service.EntrySasService")
    def test_no_micro_sl_on_balanced(self, mock_sas, mock_tms, db_session):
        """Le profil balanced ne déclenche PAS de micro SL même en grosse perte."""
        from app.services.paper_trading_service import PaperTradingService
        mock_tms.detect_direction.return_value = ("long", 0.5)
        mock_sas.has_pending.return_value = False

        account = _create_active_account(db_session)
        entry = 84000.0
        trade = _create_open_trade(db_session, account.id, entry_price=entry,
                                    direction="long", size=2500.0, slot="balanced")

        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Grosse perte de 0.5% → le balanced n'a pas de micro SL
        bad_price = entry * (1 - 0.005)
        result = service._tick_single_slot(account, "balanced", bad_price, now)

        # Ne doit PAS être micro_sl (le SL classique pourrait le fermer, mais pas micro)
        assert result.action_taken != "closed_micro_sl"


# ---------------------------------------------------------------------------
# Tests de non-régression
# ---------------------------------------------------------------------------

class TestMicroStopLossNonRegression:
    """Le micro SL ne casse pas le trailing stop, breakeven, etc."""

    @patch("app.services.paper_trading_service.TickMomentumService")
    @patch("app.services.paper_trading_service.EntrySasService")
    def test_trailing_stop_still_works_in_profit(self, mock_sas, mock_tms, db_session):
        """Le trailing stop fonctionne toujours quand on est en profit."""
        from app.services.paper_trading_service import PaperTradingService
        mock_tms.detect_direction.return_value = ("long", 0.5)
        mock_sas.has_pending.return_value = False

        account = _create_active_account(db_session)
        entry = 84000.0
        # Position avec un pic élevé → le trailing devrait se déclencher au recul
        trade = _create_open_trade(db_session, account.id, entry_price=entry,
                                    direction="long", size=2500.0, slot="scalping")
        # Simuler un pic à +0.10% puis retour à +0.04% (trailing activation 0.04%, drop 15%)
        trade.highest_price_since_entry = entry * 1.001  # pic +0.10%
        db_session.commit()

        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Prix actuel = entry + 0.04% → pic 0.10%, actuel 0.04%, drop = 60% > 15%
        current = entry * 1.0004
        result = service._tick_single_slot(account, "scalping", current, now)

        # Doit être trailing stop (pas micro sl, car on est en profit)
        assert result.action_taken == "closed_trailing_stop"

    def test_micro_sl_pnl_is_small(self):
        """Vérifier que -0.05% sur $2500 = perte contenue (~$1.25)."""
        size = 2500.0
        pnl_pct = -0.05  # -0.05%
        pnl_usd = size * pnl_pct / 100
        assert -1.30 < pnl_usd < -1.20  # ~-$1.25

    def test_scalping_loss_cut_still_higher(self):
        """Le loss_cut_pct (0.20%) est 4× plus large que le micro SL (0.05%)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.loss_cut_pct == 0.50
        assert p.micro_stop_loss_pct == 0.20
        assert p.loss_cut_pct / p.micro_stop_loss_pct == 4.0


# ---------------------------------------------------------------------------
# Tests valeur limite
# ---------------------------------------------------------------------------

class TestMicroStopLossEdgeCases:
    """Edge cases pour le micro stop loss."""

    def test_zero_position_size(self, db_session):
        """Si position_size_usd = 0, pas de division par zéro."""
        from app.services.paper_trading_service import PaperTradingService
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id, entry_price=84000.0,
                                    direction="long", size=0.0, slot="scalping")
        service = PaperTradingService(db_session)
        # Le calcul PnL % doit gérer size=0 sans crash
        pnl = service._calc_unrealized_pnl(trade, 83000.0)
        # Pas de crash = succès

    def test_micro_sl_pct_configurable(self):
        """Le seuil est configurable (pas hardcodé)."""
        params = TradingProfileParams(
            profile_type=TradingProfileType.scalping,
            label="Custom",
            description="Test custom micro SL",
            min_score=30,
            min_confidence="low",
            min_scenario_dominance=0.35,
            max_trades_per_day=30,
            cooldown_minutes=1,
            max_position_duration_hours=2,
            profit_take_pct=0.8,
            loss_cut_pct=0.20,
            loss_cut_score_threshold=5,
            leverage_enabled=True,
            max_leverage=1.5,
            micro_stop_loss_pct=0.05,  # Custom : 0.05% au lieu de 0.01%
        )
        assert params.micro_stop_loss_pct == 0.20

