"""
Tests pour le Paper Trading (v1.4).

Couvre :
1. Modèles PaperAccount + PaperTrade (création, defaults, FK)
2. Service : get_or_create_account, reset, open/close position
3. Service : check SL/TP, check expiration, métriques
4. Service : tick() avec mocks DecisionService + RiskService
5. Endpoints HTTP (status codes, structure réponse)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.candle import Candle
from app.services.paper_trading_service import PaperTradingService
from app.schemas.paper_trading import (
    PaperAccountResponse,
    PaperTradeResponse,
    PaperMetrics,
    PaperStatus,
    PaperTickResult,
)


@pytest.fixture(autouse=True)
def _disable_live_binance_price(monkeypatch):
    """
    Désactive l'appel HTTP live Binance dans _get_current_price
    pour que les tests utilisent toujours le prix des candles en DB.
    Cela évite que le prix réel (~68K) override les données de test.
    """
    import httpx
    original_get = httpx.get

    def _mock_binance_get(url, **kwargs):
        if "binance.com" in str(url):
            raise ConnectionError("Binance mocked in tests")
        return original_get(url, **kwargs)

    monkeypatch.setattr("httpx.get", _mock_binance_get)


# ============================================================
# Helper : insérer des candles BTC pour simuler un prix
# ============================================================
def _insert_btc_candle(db, price=85000.0, timeframe="4h", ts=None):
    """Insère une candle BTC en base pour simuler un prix courant."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    candle = Candle(
        symbol="BTC/USD",
        timeframe=timeframe,
        timestamp=ts,
        open_price=price - 100,
        high_price=price + 200,
        low_price=price - 300,
        close_price=price,
        volume=1000.0,
        source="test",
    )
    db.add(candle)
    db.commit()
    return candle


def _create_active_account(db, capital=10000.0, btc_price=85000.0):
    """Crée un compte paper actif avec un prix initial."""
    account = PaperAccount(
        initial_capital=capital,
        current_capital=capital,
        peak_capital=capital,
        btc_price_at_start=btc_price,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _create_open_trade(db, account_id, entry_price=85000.0, sl=80750.0, tp=93500.0, size=2500.0, direction="long"):
    """Crée un trade paper ouvert (long ou short)."""
    # Pour un short, les SL/TP sont inversés par défaut
    if direction == "short" and sl == 80750.0 and tp == 93500.0:
        sl = 89250.0   # SL au-dessus pour un short
        tp = 80750.0   # TP en-dessous pour un short
    trade = PaperTrade(
        account_id=account_id,
        status="open",
        direction=direction,
        entry_price=entry_price,
        stop_loss_price=sl,
        take_profit_price=tp,
        highest_price_since_entry=entry_price if direction == "long" else None,
        lowest_price_since_entry=entry_price if direction == "short" else None,
        position_size_usd=size,
        entry_reason=f"Test signal {'acheter' if direction == 'long' else 'vendre'}",
        decision_score=35.0 if direction == "long" else -35.0,
        entry_ts=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


# ============================================================
# 1. MODÈLES
# ============================================================

class TestPaperAccountModel:
    """Tests pour le modèle PaperAccount."""

    def test_create_default_account(self, db_session):
        """Création d'un compte avec les valeurs par défaut."""
        account = PaperAccount()
        db_session.add(account)
        db_session.commit()
        db_session.refresh(account)
        assert account.id is not None
        assert account.initial_capital == 10000.0
        assert account.current_capital == 10000.0
        assert account.total_pnl == 0.0
        assert account.total_trades == 0
        assert account.is_active is False
        assert account.max_open_duration_hours == 168.0

    def test_account_custom_capital(self, db_session):
        """Création avec un capital personnalisé."""
        account = PaperAccount(initial_capital=50000.0, current_capital=50000.0)
        db_session.add(account)
        db_session.commit()
        assert account.initial_capital == 50000.0

    def test_account_repr(self, db_session):
        """Vérification du __repr__."""
        account = _create_active_account(db_session)
        repr_str = repr(account)
        assert "PaperAccount" in repr_str
        assert "10000.00" in repr_str

    def test_account_relationship_to_trades(self, db_session):
        """L'account a une relation vers les trades."""
        account = _create_active_account(db_session)
        assert hasattr(account, "trades")
        assert account.trades == []


class TestPaperTradeModel:
    """Tests pour le modèle PaperTrade."""

    def test_create_trade(self, db_session):
        """Création d'un trade paper."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id)
        assert trade.id is not None
        assert trade.account_id == account.id
        assert trade.status == "open"
        assert trade.direction == "long"
        assert trade.entry_price == 85000.0

    def test_trade_repr(self, db_session):
        """Vérification du __repr__."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id)
        repr_str = repr(trade)
        assert "PaperTrade" in repr_str
        assert "long" in repr_str

    def test_trade_fk_account(self, db_session):
        """Le trade est lié au bon compte."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id)
        assert trade.account.id == account.id

    def test_trade_pnl_initially_none(self, db_session):
        """Le PnL est None pour un trade ouvert."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id)
        assert trade.pnl is None
        assert trade.exit_price is None


# ============================================================
# 2. SERVICE — GESTION DU COMPTE
# ============================================================

class TestPaperTradingServiceAccount:
    """Tests pour la gestion du compte paper."""

    def test_get_or_create_account_creates_default(self, db_session):
        """Crée un compte par défaut si aucun n'existe."""
        service = PaperTradingService(db_session)
        account = service.get_or_create_account()
        assert account is not None
        assert account.initial_capital == 10000.0
        assert account.is_active is False

    def test_get_or_create_account_returns_same(self, db_session):
        """Retourne le même compte à chaque appel."""
        service = PaperTradingService(db_session)
        a1 = service.get_or_create_account()
        a2 = service.get_or_create_account()
        assert a1.id == a2.id

    def test_get_or_create_with_custom_capital(self, db_session):
        """Crée avec un capital personnalisé."""
        service = PaperTradingService(db_session)
        account = service.get_or_create_account(initial_capital=50000.0)
        assert account.initial_capital == 50000.0

    def test_reset_account(self, db_session):
        """Reset supprime les trades et remet le capital."""
        _insert_btc_candle(db_session, price=85000.0)
        service = PaperTradingService(db_session)

        # Créer un compte et un trade
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id)

        # Reset
        new_account = service.reset_account(initial_capital=20000.0)
        assert new_account.initial_capital == 20000.0
        assert new_account.current_capital == 20000.0
        assert new_account.total_pnl == 0.0
        assert new_account.total_trades == 0
        # Vérifier que les trades sont supprimés
        trades = db_session.query(PaperTrade).all()
        assert len(trades) == 0

    def test_reset_captures_btc_price(self, db_session):
        """Reset capture le prix BTC pour le buy & hold."""
        _insert_btc_candle(db_session, price=90000.0)
        service = PaperTradingService(db_session)
        account = service.reset_account()
        assert account.btc_price_at_start == 90000.0

    def test_get_open_position_none(self, db_session):
        """Pas de position ouverte par défaut."""
        service = PaperTradingService(db_session)
        service.get_or_create_account()
        assert service.get_open_position() is None

    def test_get_open_position_exists(self, db_session):
        """Retourne la position ouverte."""
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id)
        service = PaperTradingService(db_session)
        pos = service.get_open_position()
        assert pos is not None
        assert pos.status == "open"


# ============================================================
# 3. SERVICE — OUVERTURE / FERMETURE
# ============================================================

class TestPaperTradingServicePositions:
    """Tests pour l'ouverture/fermeture de positions."""

    def test_open_position(self, db_session):
        """Ouvrir une position crée un trade en base."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)
        trade = service._open_position(
            account=account,
            price=85000.0,
            sl=80750.0,
            tp=93500.0,
            size_usd=2500.0,
            reason="Test open",
            score=30.0,
            direction="long",
        )
        assert trade.id is not None
        assert trade.status == "open"
        assert trade.entry_price == 85000.0
        assert trade.stop_loss_price == 80750.0
        assert trade.take_profit_price == 93500.0

    def test_close_position_profit(self, db_session):
        """Fermer une position en profit met à jour le PnL."""
        account = _create_active_account(db_session, capital=10000.0)
        trade = _create_open_trade(db_session, account.id, entry_price=85000.0, size=2500.0)
        service = PaperTradingService(db_session)

        closed = service._close_position(trade, exit_price=90000.0, reason="TP", status="closed_tp")
        assert closed.status == "closed_tp"
        assert closed.pnl > 0  # Profit
        assert closed.pnl_pct > 0
        assert closed.exit_price == 90000.0
        assert closed.duration_hours is not None

        # Vérifier le compte
        db_session.refresh(account)
        assert account.total_trades == 1
        assert account.winning_trades == 1
        assert account.current_capital > 10000.0

    def test_close_position_loss(self, db_session):
        """Fermer une position en perte met à jour le PnL."""
        account = _create_active_account(db_session, capital=10000.0)
        trade = _create_open_trade(db_session, account.id, entry_price=85000.0, size=2500.0)
        service = PaperTradingService(db_session)

        closed = service._close_position(trade, exit_price=80000.0, reason="SL", status="closed_sl")
        assert closed.pnl < 0
        assert closed.status == "closed_sl"

        db_session.refresh(account)
        assert account.losing_trades == 1
        assert account.current_capital < 10000.0

    def test_close_position_updates_win_rate(self, db_session):
        """Le win rate est calculé correctement."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)

        # Trade gagnant
        t1 = _create_open_trade(db_session, account.id, entry_price=85000.0)
        service._close_position(t1, 90000.0, "win", "closed_tp")

        # Trade perdant
        t2 = _create_open_trade(db_session, account.id, entry_price=90000.0)
        service._close_position(t2, 85000.0, "loss", "closed_sl")

        db_session.refresh(account)
        assert account.total_trades == 2
        assert account.win_rate == 50.0

    def test_close_position_updates_drawdown(self, db_session):
        """Le drawdown est calculé correctement."""
        account = _create_active_account(db_session, capital=10000.0)
        service = PaperTradingService(db_session)

        # Trade perdant
        trade = _create_open_trade(db_session, account.id, entry_price=85000.0, size=5000.0)
        service._close_position(trade, 80000.0, "loss", "closed_sl")

        db_session.refresh(account)
        assert account.max_drawdown_pct > 0

    def test_close_position_manual(self, db_session):
        """Fermeture manuelle d'une position."""
        _insert_btc_candle(db_session, price=86000.0)
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id, entry_price=85000.0)
        service = PaperTradingService(db_session)

        closed = service.close_position_manual("test manual close")
        assert closed is not None
        assert closed.status == "closed_manual"

    def test_close_position_manual_no_position(self, db_session):
        """Fermeture manuelle quand pas de position retourne None."""
        _create_active_account(db_session)
        service = PaperTradingService(db_session)
        assert service.close_position_manual() is None

    def test_position_size_capped_by_capital(self, db_session):
        """La taille de position est plafonnée au capital disponible."""
        account = _create_active_account(db_session, capital=1000.0)
        service = PaperTradingService(db_session)
        trade = service._open_position(
            account=account, price=85000.0, sl=80000.0, tp=90000.0,
            size_usd=5000.0, reason="test", score=10.0,
        )
        assert trade.position_size_usd == 1000.0  # Capped


# ============================================================
# 4. SERVICE — SL / TP / EXPIRATION
# ============================================================

class TestPaperTradingSLTP:
    """Tests pour les vérifications SL/TP/expiration."""

    def test_check_sl_long_hit(self, db_session):
        """SL touché pour un long."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id, entry_price=85000.0, sl=80000.0)
        service = PaperTradingService(db_session)
        result = service._check_sl_tp(trade, current_price=79000.0)
        assert result == "closed_sl"

    def test_check_tp_long_hit(self, db_session):
        """TP touché pour un long."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id, entry_price=85000.0, tp=93500.0)
        service = PaperTradingService(db_session)
        result = service._check_sl_tp(trade, current_price=94000.0)
        assert result == "closed_tp"

    def test_check_sl_tp_none(self, db_session):
        """Ni SL ni TP touché."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id, sl=80000.0, tp=93500.0)
        service = PaperTradingService(db_session)
        result = service._check_sl_tp(trade, current_price=87000.0)
        assert result is None

    def test_check_sl_short_hit(self, db_session):
        """SL touché pour un short."""
        account = _create_active_account(db_session)
        trade = PaperTrade(
            account_id=account.id, status="open", direction="short",
            entry_price=85000.0, stop_loss_price=90000.0, take_profit_price=80000.0,
            position_size_usd=2500.0, entry_reason="test short",
            entry_ts=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        db_session.commit()
        service = PaperTradingService(db_session)
        result = service._check_sl_tp(trade, current_price=91000.0)
        assert result == "closed_sl"

    def test_check_tp_short_hit(self, db_session):
        """TP touché pour un short."""
        account = _create_active_account(db_session)
        trade = PaperTrade(
            account_id=account.id, status="open", direction="short",
            entry_price=85000.0, stop_loss_price=90000.0, take_profit_price=80000.0,
            position_size_usd=2500.0, entry_reason="test short",
            entry_ts=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        db_session.commit()
        service = PaperTradingService(db_session)
        result = service._check_sl_tp(trade, current_price=79000.0)
        assert result == "closed_tp"

    def test_check_expiration_not_expired(self, db_session):
        """Position non expirée."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id)
        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)
        result = service._check_expiration(trade, now)
        assert result is None

    def test_check_expiration_expired(self, db_session):
        """Position expirée (> max_open_duration_hours)."""
        account = _create_active_account(db_session)
        # Créer un trade ouvert il y a 200h (max = 168h)
        trade = PaperTrade(
            account_id=account.id, status="open", direction="long",
            entry_price=85000.0, stop_loss_price=80000.0, take_profit_price=93000.0,
            position_size_usd=2500.0, entry_reason="test",
            entry_ts=datetime.now(timezone.utc) - timedelta(hours=200),
        )
        db_session.add(trade)
        db_session.commit()
        service = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)
        result = service._check_expiration(trade, now)
        assert result == "closed_expired"


# ============================================================
# 5. SERVICE — MÉTRIQUES
# ============================================================

class TestPaperTradingMetrics:
    """Tests pour le calcul des métriques."""

    def test_metrics_empty(self, db_session):
        """Métriques vides quand pas de trades."""
        _create_active_account(db_session)
        service = PaperTradingService(db_session)
        metrics = service.get_metrics()
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.net_pnl == 0.0

    def test_metrics_with_trades(self, db_session):
        """Métriques calculées après des trades."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)

        # Trade gagnant
        t1 = _create_open_trade(db_session, account.id, entry_price=85000.0, size=2500.0)
        service._close_position(t1, 90000.0, "win", "closed_tp")

        # Trade perdant
        t2 = _create_open_trade(db_session, account.id, entry_price=90000.0, size=2500.0)
        service._close_position(t2, 85000.0, "loss", "closed_sl")

        metrics = service.get_metrics()
        assert metrics.total_trades == 2
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 1
        assert metrics.win_rate == 50.0
        assert metrics.best_trade_pnl > 0
        assert metrics.worst_trade_pnl < 0

    def test_metrics_profit_factor(self, db_session):
        """Le profit factor est calculé correctement."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)

        # 2 trades gagnants
        for _ in range(2):
            t = _create_open_trade(db_session, account.id, entry_price=85000.0, size=1000.0)
            service._close_position(t, 90000.0, "win", "closed_tp")

        # 1 trade perdant
        t = _create_open_trade(db_session, account.id, entry_price=90000.0, size=1000.0)
        service._close_position(t, 85000.0, "loss", "closed_sl")

        metrics = service.get_metrics()
        assert metrics.profit_factor > 0

    def test_buy_hold_pnl(self, db_session):
        """Le PnL buy & hold est calculé correctement."""
        _insert_btc_candle(db_session, price=90000.0)
        account = _create_active_account(db_session, btc_price=80000.0)
        service = PaperTradingService(db_session)
        metrics = service.get_metrics()
        # BTC est passé de 80k à 90k = +12.5%
        assert metrics.buy_hold_pnl_pct == pytest.approx(12.5, abs=0.5)

    def test_status_complete(self, db_session):
        """Le status retourne toutes les informations."""
        _insert_btc_candle(db_session, price=85000.0)
        _create_active_account(db_session)
        service = PaperTradingService(db_session)
        status = service.get_status()
        assert status.account is not None
        assert status.metrics is not None
        assert isinstance(status.is_running, bool)

    def test_sharpe_ratio_none_with_few_trades(self, db_session):
        """Le Sharpe est None avec < 2 trades."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)
        t = _create_open_trade(db_session, account.id)
        service._close_position(t, 90000.0, "win", "closed_tp")
        metrics = service.get_metrics()
        assert metrics.sharpe_ratio is None

    def test_sharpe_ratio_calculated(self, db_session):
        """Le Sharpe est calculé avec assez de trades."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)

        for i in range(5):
            t = _create_open_trade(db_session, account.id, entry_price=85000.0 + i * 100, size=1000.0)
            exit_price = 86000.0 + i * 100 if i % 2 == 0 else 84000.0 + i * 100
            service._close_position(t, exit_price, "test", "closed_signal")

        metrics = service.get_metrics()
        assert metrics.sharpe_ratio is not None


# ============================================================
# 6. SERVICE — TICK (avec mocks)
# ============================================================

class TestPaperTradingTick:
    """Tests pour la boucle tick()."""

    def test_tick_inactive_account(self, db_session):
        """Tick sur un compte inactif retourne 'inactive'."""
        service = PaperTradingService(db_session)
        service.get_or_create_account()  # inactif par défaut
        result = service.tick()
        assert result.action_taken == "inactive"

    def test_tick_no_price(self, db_session):
        """Tick sans données de prix retourne 'no_price'."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)
        result = service.tick()
        assert result.action_taken == "no_price"

    def test_tick_hold_no_signal(self, db_session):
        """Tick avec signal 'attendre' → hold."""
        _insert_btc_candle(db_session, price=85000.0)
        _create_active_account(db_session)
        service = PaperTradingService(db_session)

        mock_decision = {
            "recommendation": {"action": "attendre", "confidence": "medium"},
            "combined_score": 0,
            "summary": "Signal neutre",
        }
        with patch.object(service, "_get_decision", return_value=mock_decision):
            result = service.tick()
        assert result.action_taken == "hold"

    def test_tick_opens_position_on_buy_signal(self, db_session):
        """Tick avec signal 'acheter' ouvre une position long."""
        _insert_btc_candle(db_session, price=85000.0)
        _create_active_account(db_session)
        service = PaperTradingService(db_session)

        mock_decision = {
            "recommendation": {"action": "acheter", "confidence": "high"},
            "combined_score": 45,
            "summary": "Signal haussier fort",
        }
        mock_evaluation = MagicMock()
        mock_evaluation.allowed = True
        mock_evaluation.stop_loss_price = 80750.0
        mock_evaluation.take_profit_price = 93500.0
        mock_evaluation.max_position_size_usd = 2500.0
        mock_evaluation.reasons = []

        with patch.object(service, "_get_decision", return_value=mock_decision):
            with patch("app.services.paper_trading_service.RiskService") as MockRisk:
                MockRisk.return_value.evaluate_trade.return_value = mock_evaluation
                result = service.tick()

        assert result.action_taken == "opened_long"
        assert result.position_opened is not None
        assert result.decision_score == 45

    def test_tick_opens_short_position_on_sell_signal(self, db_session):
        """Tick avec signal 'vendre' ouvre une position short."""
        _insert_btc_candle(db_session, price=85000.0)
        _create_active_account(db_session)
        service = PaperTradingService(db_session)

        mock_decision = {
            "recommendation": {"action": "vendre", "confidence": "medium"},
            "combined_score": -45,
            "summary": "Signal baissier",
        }
        mock_evaluation = MagicMock()
        mock_evaluation.allowed = True
        mock_evaluation.stop_loss_price = 89250.0  # SL au-dessus pour un short
        mock_evaluation.take_profit_price = 76500.0  # TP en-dessous
        mock_evaluation.max_position_size_usd = 2500.0
        mock_evaluation.reasons = []

        with patch.object(service, "_get_decision", return_value=mock_decision):
            with patch("app.services.paper_trading_service.RiskService") as MockRisk:
                MockRisk.return_value.evaluate_trade.return_value = mock_evaluation
                result = service.tick()

        assert result.action_taken == "opened_short"
        assert result.position_opened is not None
        assert result.position_opened.direction == "short"
        assert result.decision_score == -45

    def test_tick_blocked_by_risk(self, db_session):
        """Tick bloqué par le risk engine."""
        _insert_btc_candle(db_session, price=85000.0)
        _create_active_account(db_session)
        service = PaperTradingService(db_session)

        mock_decision = {
            "recommendation": {"action": "acheter", "confidence": "high"},
            "combined_score": 45,
            "summary": "Signal haussier",
        }
        mock_evaluation = MagicMock()
        mock_evaluation.allowed = False
        mock_evaluation.reasons = ["Kill switch actif"]

        with patch.object(service, "_get_decision", return_value=mock_decision):
            with patch("app.services.paper_trading_service.RiskService") as MockRisk:
                MockRisk.return_value.evaluate_trade.return_value = mock_evaluation
                result = service.tick()

        assert result.action_taken == "blocked"
        assert result.risk_allowed is False

    def test_tick_closes_on_sl(self, db_session):
        """Tick ferme la position quand SL touché."""
        _insert_btc_candle(db_session, price=79000.0)  # Sous le SL
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id, entry_price=85000.0, sl=80000.0)
        service = PaperTradingService(db_session)

        result = service.tick()
        assert result.action_taken == "closed_sl"
        assert result.position_closed is not None

    def test_tick_closes_on_tp(self, db_session):
        """Tick ferme la position quand TP touché."""
        _insert_btc_candle(db_session, price=95000.0)  # Au-dessus du TP
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id, entry_price=85000.0, tp=93500.0)
        service = PaperTradingService(db_session)

        result = service.tick()
        assert result.action_taken == "closed_tp"
        assert result.position_closed is not None

    def test_tick_holds_open_position(self, db_session):
        """Tick conserve la position si ni SL ni TP touché et pas de signal contraire."""
        _insert_btc_candle(db_session, price=86000.0)  # Entre SL et TP, PnL < 2%
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id, entry_price=85000.0, sl=80000.0, tp=93500.0)
        service = PaperTradingService(db_session)

        # Mock le DecisionService : signal toujours haussier avec score positif
        # (score > 0 nécessaire pour que la position ne soit pas fermée par "signal affaibli")
        mock_decision = {
            "recommendation": {"action": "acheter", "confidence": "medium"},
            "combined_score": 35,
        }
        with patch.object(service, "_get_decision", return_value=mock_decision):
            result = service.tick()

        assert result.action_taken == "hold"
        assert "PnL latent" in result.detail

    def test_tick_closes_on_contrary_signal(self, db_session):
        """Tick ferme la position sur signal contraire fort."""
        _insert_btc_candle(db_session, price=86000.0)
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id, entry_price=85000.0, sl=80000.0, tp=93500.0)
        service = PaperTradingService(db_session)

        mock_decision = {
            "recommendation": {"action": "vendre", "confidence": "high"},
            "combined_score": -40,
        }
        with patch.object(service, "_get_decision", return_value=mock_decision):
            result = service.tick()

        assert result.action_taken == "closed_signal"

    def test_tick_closes_expired_position(self, db_session):
        """Tick ferme une position expirée."""
        _insert_btc_candle(db_session, price=86000.0)
        account = _create_active_account(db_session)
        # Trade ouvert il y a 200h
        trade = PaperTrade(
            account_id=account.id, status="open", direction="long",
            entry_price=85000.0, stop_loss_price=70000.0, take_profit_price=100000.0,
            highest_price_since_entry=86000.0,
            position_size_usd=2500.0, entry_reason="test",
            entry_ts=datetime.now(timezone.utc) - timedelta(hours=200),
        )
        db_session.add(trade)
        db_session.commit()

        service = PaperTradingService(db_session)
        result = service.tick()
        assert result.action_taken == "closed_expired"

    def test_tick_no_decision(self, db_session):
        """Tick sans moteur de décision disponible."""
        _insert_btc_candle(db_session, price=85000.0)
        _create_active_account(db_session)
        service = PaperTradingService(db_session)

        with patch.object(service, "_get_decision", return_value=None):
            result = service.tick()
        assert result.action_taken == "no_decision"

    def test_tick_captures_btc_price_at_start(self, db_session):
        """Tick capture le prix BTC si btc_price_at_start est None."""
        _insert_btc_candle(db_session, price=85000.0)
        account = _create_active_account(db_session)
        account.btc_price_at_start = None
        db_session.commit()

        service = PaperTradingService(db_session)
        mock_decision = {
            "recommendation": {"action": "attendre", "confidence": "low"},
            "combined_score": 0,
            "summary": "Neutre",
        }
        with patch.object(service, "_get_decision", return_value=mock_decision):
            service.tick()

        db_session.refresh(account)
        assert account.btc_price_at_start == 85000.0

    def test_tick_tracks_lowest_price_for_short(self, db_session):
        """Tick met à jour lowest_price_since_entry pour une position short."""
        _insert_btc_candle(db_session, price=84500.0)  # Légèrement sous l'entrée (PnL < 2%)
        account = _create_active_account(db_session)
        trade = _create_open_trade(
            db_session, account.id, entry_price=85000.0,
            sl=89000.0, tp=80000.0, direction="short"
        )
        service = PaperTradingService(db_session)

        # Mock : signal toujours baissier (score négatif pour conserver le short)
        mock_decision = {
            "recommendation": {"action": "vendre", "confidence": "medium"},
            "combined_score": -30,
        }
        with patch.object(service, "_get_decision", return_value=mock_decision):
            result = service.tick()

        assert result.action_taken == "hold"
        db_session.refresh(trade)
        assert trade.lowest_price_since_entry == 84500.0

    def test_tick_closes_short_on_buy_signal(self, db_session):
        """Tick ferme un short quand signal contraire 'acheter'."""
        _insert_btc_candle(db_session, price=84000.0)
        account = _create_active_account(db_session)
        _create_open_trade(
            db_session, account.id, entry_price=85000.0,
            sl=89000.0, tp=80000.0, direction="short"
        )
        service = PaperTradingService(db_session)

        mock_decision = {
            "recommendation": {"action": "acheter", "confidence": "high"},
            "combined_score": 40,
        }
        with patch.object(service, "_get_decision", return_value=mock_decision):
            result = service.tick()

        assert result.action_taken == "closed_signal"

    def test_close_short_position_profit(self, db_session):
        """Fermer un short en profit (prix a baissé)."""
        account = _create_active_account(db_session, capital=10000.0)
        trade = _create_open_trade(
            db_session, account.id, entry_price=85000.0,
            sl=89000.0, tp=80000.0, size=2500.0, direction="short"
        )
        service = PaperTradingService(db_session)

        closed = service._close_position(trade, exit_price=80000.0, reason="TP", status="closed_tp")
        assert closed.pnl > 0  # Profit car prix a baissé
        assert closed.pnl_pct > 0


# ============================================================
# 7. SERVICE — TRADES LIST
# ============================================================

class TestPaperTradingTradesList:
    """Tests pour la liste des trades."""

    def test_get_trades_empty(self, db_session):
        """Liste vide quand pas de trades."""
        _create_active_account(db_session)
        service = PaperTradingService(db_session)
        trades, total = service.get_trades()
        assert total == 0
        assert trades == []

    def test_get_trades_with_filter(self, db_session):
        """Filtrer les trades par statut."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)

        # Créer un trade ouvert et un fermé
        _create_open_trade(db_session, account.id)
        t2 = _create_open_trade(db_session, account.id, entry_price=90000.0)
        service._close_position(t2, 95000.0, "test", "closed_tp")

        trades_open, _ = service.get_trades(status_filter="open")
        assert len(trades_open) == 1

        trades_closed, _ = service.get_trades(status_filter="closed")
        assert len(trades_closed) == 1

    def test_get_trades_pagination(self, db_session):
        """Pagination des trades."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)

        for i in range(5):
            t = _create_open_trade(db_session, account.id, entry_price=85000.0 + i * 1000)
            service._close_position(t, 86000.0 + i * 1000, "test", "closed_tp")

        trades, total = service.get_trades(limit=2, offset=0)
        assert total == 5
        assert len(trades) == 2


# ============================================================
# 8. ENDPOINTS HTTP
# ============================================================

class TestPaperTradingEndpoints:
    """Tests pour les endpoints HTTP."""

    def test_get_account_creates_default(self, client):
        """GET /paper/account crée un compte par défaut."""
        resp = client.get("/paper/account")
        assert resp.status_code == 200
        data = resp.json()
        assert data["initial_capital"] == 10000.0
        assert data["is_active"] is False

    def test_create_account(self, client, db_session):
        """POST /paper/account crée/active un compte."""
        resp = client.post("/paper/account", json={
            "initial_capital": 25000.0,
            "max_open_duration_hours": 48.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["initial_capital"] == 25000.0
        assert data["max_open_duration_hours"] == 48.0
        assert data["is_active"] is True

    def test_reset_account(self, client, db_session):
        """POST /paper/account/reset reset le compte."""
        # Créer d'abord un compte
        client.post("/paper/account", json={"initial_capital": 10000.0})
        # Reset
        resp = client.post("/paper/account/reset", json={"initial_capital": 50000.0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["initial_capital"] == 50000.0
        assert data["total_trades"] == 0

    def test_get_status(self, client, db_session):
        """GET /paper/status retourne le statut complet."""
        resp = client.get("/paper/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "account" in data
        assert "metrics" in data
        assert "is_running" in data

    def test_get_trades_empty(self, client, db_session):
        """GET /paper/trades retourne une liste vide."""
        resp = client.get("/paper/trades")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trades"] == []
        assert data["total"] == 0

    def test_get_metrics(self, client, db_session):
        """GET /paper/metrics retourne les métriques."""
        resp = client.get("/paper/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_trades" in data
        assert "win_rate" in data
        assert "buy_hold_pnl_pct" in data

    def test_tick_manual(self, client, db_session):
        """POST /paper/tick exécute un tick."""
        resp = client.post("/paper/tick")
        assert resp.status_code == 200
        data = resp.json()
        assert "action_taken" in data
        # Inactif par défaut
        assert data["action_taken"] == "inactive"

    def test_close_no_position(self, client, db_session):
        """POST /paper/close sans position ouverte → 404."""
        # Créer un compte actif
        client.post("/paper/account", json={"initial_capital": 10000.0})
        resp = client.post("/paper/close?reason=test")
        assert resp.status_code == 404

    def test_close_with_position(self, client, db_session):
        """POST /paper/close avec position ouverte → ferme."""
        # Créer un compte actif + candle + trade
        _insert_btc_candle(db_session, price=86000.0)
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id)

        resp = client.post("/paper/close?reason=manual+test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "closed_manual"

    def test_get_trades_with_status_filter(self, client, db_session):
        """GET /paper/trades?status=closed filtre correctement."""
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)
        t = _create_open_trade(db_session, account.id)
        service._close_position(t, 90000.0, "test", "closed_tp")

        resp = client.get("/paper/trades?status=closed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["trades"][0]["status"] == "closed_tp"

    def test_tick_with_active_account_no_data(self, client, db_session):
        """POST /paper/tick avec compte actif mais pas de données → no_price."""
        _create_active_account(db_session)
        resp = client.post("/paper/tick")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_taken"] == "no_price"

    def test_status_with_open_position(self, client, db_session):
        """GET /paper/status avec une position ouverte."""
        _insert_btc_candle(db_session, price=86000.0)
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id, entry_price=85000.0)

        resp = client.get("/paper/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["open_position"] is not None
        assert data["unrealized_pnl"] is not None

    def test_export_trades_empty(self, client, db_session):
        """GET /paper/trades/export sans trades → structure valide vide."""
        client.post("/paper/account", json={"initial_capital": 10000.0})
        resp = client.get("/paper/trades/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["export_version"] == "1.0"
        assert data["exported_at"] is not None
        assert data["account"]["initial_capital"] == 10000.0
        assert data["total_trades"] == 0
        assert data["open_trades"] == []
        assert data["closed_trades"] == []
        assert "metrics" in data

    def test_export_trades_with_closed_trades(self, client, db_session):
        """GET /paper/trades/export avec trades fermés → contient les détails complets."""
        _insert_btc_candle(db_session, price=90000.0)
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)
        trade = _create_open_trade(db_session, account.id, entry_price=85000.0)
        service._close_position(trade, 90000.0, "TP hit", "closed_tp")

        resp = client.get("/paper/trades/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_trades"] >= 1
        assert len(data["closed_trades"]) >= 1
        closed = data["closed_trades"][0]
        # Vérifier tous les champs enrichis sont présents
        assert "entry_price" in closed
        assert "exit_price" in closed
        assert "leverage" in closed
        assert "stop_loss_price" in closed
        assert "take_profit_price" in closed
        assert "entry_reason" in closed
        assert "exit_reason" in closed
        assert "direction" in closed
        assert "pnl" in closed
        assert "duration_hours" in closed

    def test_export_trades_with_open_position(self, client, db_session):
        """GET /paper/trades/export avec position ouverte → listée dans open_trades."""
        _insert_btc_candle(db_session, price=86000.0)
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id, entry_price=85000.0)

        resp = client.get("/paper/trades/export")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["open_trades"]) >= 1
        assert data["open_trades"][0]["status"] == "open"

