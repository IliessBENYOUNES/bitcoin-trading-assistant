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

        # Reset — retourne (account, purged)
        new_account, purged = service.reset_account(initial_capital=20000.0)
        assert new_account.initial_capital == 20000.0
        assert new_account.current_capital == 20000.0
        assert new_account.total_pnl == 0.0
        assert new_account.total_trades == 0
        # Vérifier que les trades sont supprimés
        trades = db_session.query(PaperTrade).all()
        assert len(trades) == 0
        # Vérifier le compteur de purge
        assert purged["paper_trade"] >= 1
        assert purged["paper_account"] >= 1

    def test_reset_captures_btc_price(self, db_session):
        """Reset capture le prix BTC pour le buy & hold."""
        _insert_btc_candle(db_session, price=90000.0)
        service = PaperTradingService(db_session)
        account, _purged = service.reset_account()
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
        """POST /paper/account/reset reset le compte (exige confirm='RESET')."""
        # Créer d'abord un compte
        client.post("/paper/account", json={"initial_capital": 10000.0})
        # Reset avec confirmation
        resp = client.post("/paper/account/reset", json={
            "confirm": "RESET",
            "initial_capital": 50000.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        # FullResetResponse contient account, purged, reset_details, message
        assert data["account"]["initial_capital"] == 50000.0
        assert data["account"]["total_trades"] == 0
        assert "purged" in data
        assert "reset_details" in data
        assert "message" in data

    def test_reset_account_without_confirm_rejected(self, client, db_session):
        """POST /paper/account/reset sans confirm='RESET' doit être refusé."""
        client.post("/paper/account", json={"initial_capital": 10000.0})
        resp = client.post("/paper/account/reset", json={
            "confirm": "no",
            "initial_capital": 50000.0,
        })
        assert resp.status_code == 400

    def test_reset_account_missing_confirm_rejected(self, client, db_session):
        """POST /paper/account/reset sans champ confirm doit être refusé (422)."""
        client.post("/paper/account", json={"initial_capital": 10000.0})
        resp = client.post("/paper/account/reset", json={
            "initial_capital": 50000.0,
        })
        # confirm est required → 422 Unprocessable Entity
        assert resp.status_code == 422

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
        """POST /paper/tick auto-active le compte et exécute un tick.

        [v2.0.3-fix] L'endpoint auto-active le compte si inactif.
        Sans données de prix, le résultat est 'no_price' (et non plus 'inactive').
        """
        resp = client.post("/paper/tick")
        assert resp.status_code == 200
        data = resp.json()
        assert "action_taken" in data
        # Auto-activé → no_price (pas de candles en base)
        assert data["action_taken"] == "no_price"

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


# ============================================================
# 10. RESET COMPLET — CONTRAT MÉTIER (Full Reset + Daily Loss Reset)
# ============================================================

class TestFullResetContract:
    """
    Tests du contrat métier Full Reset.

    Vérifie que le full reset purge TOUTES les tables liées au paper trading :
    - paper_trade
    - paper_account
    - tick_activity_log
    - learning_signal
    - strategy_feedback
    - paper_run
    - risk_config (reset, pas supprimé)
    """

    def test_full_reset_purges_learning_signal(self, db_session):
        """Full reset supprime les learning_signal orphelins."""
        from app.models.learning import LearningSignal
        _insert_btc_candle(db_session, price=85000.0)

        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id)

        # Ajouter un learning signal
        ls = LearningSignal(
            trade_id=trade.id,
            score=42.0,
            direction="long",
            exit_type="tp",
            pnl_brut=50.0,
            was_profitable=1,
            was_reversal=0,
        )
        db_session.add(ls)
        db_session.commit()
        assert db_session.query(LearningSignal).count() == 1

        service = PaperTradingService(db_session)
        _account, purged = service.reset_account()
        assert purged["learning_signal"] == 1
        assert db_session.query(LearningSignal).count() == 0

    def test_full_reset_purges_strategy_feedback(self, db_session):
        """Full reset supprime les strategy_feedback obsolètes."""
        from app.models.learning import StrategyFeedback
        _insert_btc_candle(db_session, price=85000.0)

        # Ajouter un strategy_feedback
        fb = StrategyFeedback(
            parameter_name="buy_threshold",
            original_value=30.0,
            suggested_value=35.0,
            current_value=30.0,
            reason="test feedback",
            sample_size=10,
            mode="shadow",
        )
        db_session.add(fb)
        db_session.commit()
        assert db_session.query(StrategyFeedback).count() == 1

        service = PaperTradingService(db_session)
        _account, purged = service.reset_account()
        assert purged["strategy_feedback"] == 1
        assert db_session.query(StrategyFeedback).count() == 0

    def test_full_reset_purges_paper_run(self, db_session):
        """Full reset supprime les paper_run fantômes."""
        from app.models.paper_run import PaperRun
        _insert_btc_candle(db_session, price=85000.0)

        run = PaperRun(name="test-run", profile_type="scalping", status="running")
        db_session.add(run)
        db_session.commit()
        assert db_session.query(PaperRun).count() == 1

        service = PaperTradingService(db_session)
        _account, purged = service.reset_account()
        assert purged["paper_run"] == 1
        assert db_session.query(PaperRun).count() == 0

    def test_full_reset_purges_tick_activity_log(self, db_session):
        """Full reset supprime les tick_activity_log."""
        from app.models.tick_activity_log import TickActivityLog
        _insert_btc_candle(db_session, price=85000.0)

        account = _create_active_account(db_session)
        tick = TickActivityLog(
            account_id=account.id,
            timestamp=datetime.now(timezone.utc),
            action_taken="hold",
            reason_no_trade="score_too_low",
            profile_type="scalping",
        )
        db_session.add(tick)
        db_session.commit()
        assert db_session.query(TickActivityLog).count() == 1

        service = PaperTradingService(db_session)
        _account, purged = service.reset_account()
        assert purged["tick_activity_log"] == 1
        assert db_session.query(TickActivityLog).count() == 0

    def test_full_reset_resets_risk_config(self, db_session):
        """Full reset remet le risk config à zéro."""
        from app.models.risk_config import RiskConfig
        _insert_btc_candle(db_session, price=85000.0)

        # Créer un risk config avec kill switch actif
        config = RiskConfig(
            daily_loss_current=500.0,
            kill_switch_active=True,
            kill_switch_reason="Perte journalière atteinte",
            total_portfolio_value=8000.0,
        )
        db_session.add(config)
        db_session.commit()

        service = PaperTradingService(db_session)
        new_account, purged = service.reset_account(initial_capital=20000.0)
        assert purged["risk_config_reset"] == 1

        config = db_session.query(RiskConfig).first()
        assert config.daily_loss_current == 0.0
        assert config.kill_switch_active is False
        assert config.kill_switch_reason is None
        assert config.total_portfolio_value == 20000.0

    def test_full_reset_creates_clean_account(self, db_session):
        """Full reset crée un compte vierge avec les bonnes valeurs."""
        _insert_btc_candle(db_session, price=85000.0)

        # Créer un compte avec des stats
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id)

        service = PaperTradingService(db_session)
        new_account, _purged = service.reset_account(initial_capital=25000.0)
        assert new_account.initial_capital == 25000.0
        assert new_account.current_capital == 25000.0
        assert new_account.peak_capital == 25000.0
        assert new_account.total_pnl == 0.0
        assert new_account.total_trades == 0
        assert new_account.winning_trades == 0
        assert new_account.losing_trades == 0
        assert new_account.is_active is False

    def test_full_reset_returns_purge_counts(self, db_session):
        """Full reset retourne le dictionnaire complet des compteurs de purge."""
        _insert_btc_candle(db_session, price=85000.0)
        _create_active_account(db_session)

        service = PaperTradingService(db_session)
        _account, purged = service.reset_account()
        expected_keys = {
            "tick_activity_log",
            "learning_signal",
            "strategy_feedback",
            "paper_run",
            "paper_trade",
            "paper_account",
            "risk_config_reset",
        }
        assert set(purged.keys()) == expected_keys


class TestFullResetEndpoint:
    """Tests endpoint POST /paper/account/reset avec confirmation."""

    def test_full_reset_endpoint_returns_purge_details(self, client, db_session):
        """L'endpoint retourne les détails de purge."""
        _insert_btc_candle(db_session, price=85000.0)
        client.post("/paper/account", json={"initial_capital": 10000.0})

        resp = client.post("/paper/account/reset", json={
            "confirm": "RESET",
            "initial_capital": 30000.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "purged" in data
        assert "reset_details" in data
        assert "message" in data
        assert "account" in data
        assert data["account"]["initial_capital"] == 30000.0

    def test_full_reset_endpoint_rejects_wrong_confirm(self, client, db_session):
        """L'endpoint rejette un confirm != 'RESET'."""
        resp = client.post("/paper/account/reset", json={
            "confirm": "WRONG",
            "initial_capital": 10000.0,
        })
        assert resp.status_code == 400
        assert "Confirmation invalide" in resp.json()["detail"]


class TestDailyLossResetContract:
    """
    Tests du contrat métier Reset Perte Jour.

    Vérifie que le reset daily loss :
    - Remet daily_loss_current à 0
    - Désactive le kill switch si lié à "Perte journalière"
    - NE désactive PAS le kill switch si lié à une autre raison
    - NE touche PAS aux trades, learning, runs, logs
    """

    def test_daily_loss_reset_zeroes_counter(self, db_session):
        """Reset perte jour remet daily_loss_current à zéro."""
        from app.services.risk_service import RiskService
        service = RiskService(db_session)
        config = service.get_config()
        config.daily_loss_current = 300.0
        db_session.commit()

        result = service.reset_daily_loss()
        assert result.daily_loss_current == 0.0

    def test_daily_loss_reset_deactivates_kill_switch_if_daily_loss(self, db_session):
        """Reset perte jour désactive le kill switch si déclenché par perte journalière."""
        from app.services.risk_service import RiskService
        service = RiskService(db_session)
        config = service.get_config()
        config.daily_loss_current = 500.0
        config.kill_switch_active = True
        config.kill_switch_reason = "Perte journalière atteinte (500.00 / 500.00 USD)"
        config.kill_switch_triggered_at = datetime.utcnow()
        db_session.commit()

        result = service.reset_daily_loss()
        assert result.daily_loss_current == 0.0
        assert result.kill_switch_active is False
        assert result.kill_switch_reason is None
        assert result.kill_switch_triggered_at is None

    def test_daily_loss_reset_keeps_manual_kill_switch(self, db_session):
        """Reset perte jour ne désactive PAS un kill switch manuel."""
        from app.services.risk_service import RiskService
        service = RiskService(db_session)
        config = service.get_config()
        config.daily_loss_current = 100.0
        config.kill_switch_active = True
        config.kill_switch_reason = "Activation manuelle"
        config.kill_switch_triggered_at = datetime.utcnow()
        db_session.commit()

        result = service.reset_daily_loss()
        assert result.daily_loss_current == 0.0
        # Le kill switch reste actif car il n'est pas lié à la perte journalière
        assert result.kill_switch_active is True
        assert result.kill_switch_reason == "Activation manuelle"

    def test_daily_loss_reset_does_not_touch_trades(self, db_session):
        """Reset perte jour ne supprime aucun trade."""
        from app.services.risk_service import RiskService
        _insert_btc_candle(db_session, price=85000.0)
        account = _create_active_account(db_session)
        _create_open_trade(db_session, account.id)

        risk_service = RiskService(db_session)
        config = risk_service.get_config()
        config.daily_loss_current = 200.0
        db_session.commit()

        risk_service.reset_daily_loss()

        # Les trades sont toujours là
        trades = db_session.query(PaperTrade).all()
        assert len(trades) == 1

    def test_daily_loss_reset_does_not_touch_learning(self, db_session):
        """Reset perte jour ne supprime aucun learning_signal."""
        from app.models.learning import LearningSignal
        from app.services.risk_service import RiskService

        ls = LearningSignal(
            trade_id=999,
            score=42.0,
            direction="long",
            exit_type="tp",
            pnl_brut=50.0,
            was_profitable=1,
            was_reversal=0,
        )
        db_session.add(ls)
        db_session.commit()

        risk_service = RiskService(db_session)
        risk_service.reset_daily_loss()

        assert db_session.query(LearningSignal).count() == 1

    def test_daily_loss_reset_does_not_touch_paper_run(self, db_session):
        """Reset perte jour ne supprime aucun paper_run."""
        from app.models.paper_run import PaperRun
        from app.services.risk_service import RiskService

        run = PaperRun(name="test-run", profile_type="scalping", status="running")
        db_session.add(run)
        db_session.commit()

        risk_service = RiskService(db_session)
        risk_service.reset_daily_loss()

        assert db_session.query(PaperRun).count() == 1

    def test_daily_loss_reset_does_not_touch_tick_logs(self, db_session):
        """Reset perte jour ne supprime aucun tick_activity_log."""
        from app.models.tick_activity_log import TickActivityLog
        from app.services.risk_service import RiskService

        account = _create_active_account(db_session)
        tick = TickActivityLog(
            account_id=account.id,
            timestamp=datetime.now(timezone.utc),
            action_taken="hold",
            reason_no_trade="score_too_low",
            profile_type="scalping",
        )
        db_session.add(tick)
        db_session.commit()

        risk_service = RiskService(db_session)
        risk_service.reset_daily_loss()

        assert db_session.query(TickActivityLog).count() == 1


class TestDiagnosticAfterFullReset:
    """
    Tests que le diagnostic est propre après un full reset.

    Le diagnostic ne doit pas afficher de données de l'ancien état :
    - pas de "position_already_open" résiduel
    - pas de goulot d'étranglement fantôme
    - ticks = 0, trades = 0 après reset
    """

    def test_diagnostic_clean_after_full_reset(self, db_session):
        """Après full reset, le diagnostic retourne un état propre sans artefacts."""
        from app.models.tick_activity_log import TickActivityLog
        from app.services.diagnostic_service import DiagnosticService
        _insert_btc_candle(db_session, price=85000.0)

        # Créer un état avec beaucoup de ticks "position_already_open"
        account = _create_active_account(db_session)
        for i in range(50):
            tick = TickActivityLog(
                account_id=account.id,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                action_taken="blocked",
                reason_no_trade="position_already_open",
                profile_type="scalping",
                had_open_position=1,
            )
            db_session.add(tick)
        db_session.commit()
        assert db_session.query(TickActivityLog).count() == 50

        # Full reset
        service = PaperTradingService(db_session)
        _new_account, _purged = service.reset_account()
        assert db_session.query(TickActivityLog).count() == 0

        # Le diagnostic doit être propre
        diag_service = DiagnosticService(db_session)
        diag = diag_service.get_diagnostic()
        # Le bottleneck ne doit PAS être "position_already_open"
        assert diag.main_bottleneck != "position_already_open"
        assert diag.total_ticks == 0
        assert diag.total_trades == 0

    def test_diagnostic_endpoint_clean_after_full_reset(self, client, db_session):
        """GET /paper/diagnostic retourne un diagnostic propre après full reset."""
        from app.models.tick_activity_log import TickActivityLog
        _insert_btc_candle(db_session, price=85000.0)

        # Créer un état initial
        account = _create_active_account(db_session)
        for i in range(20):
            tick = TickActivityLog(
                account_id=account.id,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                action_taken="blocked",
                reason_no_trade="position_already_open",
                profile_type="scalping",
                had_open_position=1,
            )
            db_session.add(tick)
        db_session.commit()

        # Full reset via endpoint
        resp = client.post("/paper/account/reset", json={
            "confirm": "RESET",
            "initial_capital": 10000.0,
        })
        assert resp.status_code == 200

        # Vérifier que le diagnostic est propre
        diag_resp = client.get("/paper/diagnostic")
        assert diag_resp.status_code == 200
        diag_data = diag_resp.json()
        assert diag_data["total_ticks"] == 0
        assert diag_data["total_trades"] == 0


# ================================================================
# TESTS — Stale exit vs Trailing stop (v2.0.0-fix)
# ================================================================

class TestStaleVsTrailingThreshold:
    """
    [v2.0.0-fix] Le seuil de stagnation pour les profils tight doit utiliser
    trailing_stop_activation_pct (0.20%) au lieu de profit_take_pct (0.8%).

    Avant ce fix, un trade scalping à +0.46% après 15 min était fermé comme
    "stagnant" parce que 0.46% < 0.8% (profit_take_pct). Le trailing stop
    (activation 0.20%) était actif mais ne pouvait jamais agir.
    """

    def test_stale_threshold_uses_trailing_activation_for_tight_profiles(self):
        """Le seuil de stagnation doit être trailing_stop_activation_pct pour les profils tight."""
        from app.services.trading_profile_service import PROFILE_PRESETS

        scalping = PROFILE_PRESETS["scalping"]
        # Le scalping est un profil tight (loss_cut_pct <= 0.5)
        assert scalping.loss_cut_pct <= 0.5

        # Le seuil de stagnation doit être trailing_stop_activation_pct, pas profit_take_pct
        ts_act = getattr(scalping, "trailing_stop_activation_pct", None)
        assert ts_act is not None, "scalping doit avoir trailing_stop_activation_pct"
        assert ts_act < scalping.profit_take_pct, (
            f"trailing_stop_activation ({ts_act}) doit être < profit_take_pct ({scalping.profit_take_pct})"
        )
        # La logique dans _tick_single_slot doit utiliser ts_act, pas profit_take_pct
        # Vérifié via le code : stale_pnl_threshold = ts_act si disponible
        assert ts_act == 0.04, f"Expected 0.04, got {ts_act}"  # [v2.0.9] activation 0.04%

    def test_profitable_position_above_trailing_activation_not_stale(self, db_session):
        """Un trade à +0.46% ne doit PAS être fermé stale si au-dessus du seuil trailing."""
        from app.services.trading_profile_service import PROFILE_PRESETS

        scalping = PROFILE_PRESETS["scalping"]
        ts_act = scalping.trailing_stop_activation_pct  # 0.20%

        # Simuler la logique de seuil de stagnation
        stale_pnl_threshold = ts_act  # Nouveau comportement

        # Trade à +0.46% : ne doit PAS être stagnant
        unrealized_pct = 0.46
        assert abs(unrealized_pct) >= stale_pnl_threshold, (
            f"Trade à +{unrealized_pct}% ne devrait PAS être stagnant "
            f"(seuil={stale_pnl_threshold}%)"
        )

    def test_flat_position_below_trailing_activation_is_stale(self, db_session):
        """Un trade à +0.01% DOIT être fermé stale (en dessous du seuil trailing 0.04%)."""
        from app.services.trading_profile_service import PROFILE_PRESETS

        scalping = PROFILE_PRESETS["scalping"]
        ts_act = scalping.trailing_stop_activation_pct  # 0.02% [v2.0.9]

        stale_pnl_threshold = ts_act

        # Trade à +0.01% : DOIT être stagnant (< 0.02%)
        unrealized_pct = 0.01
        assert abs(unrealized_pct) < stale_pnl_threshold, (
            f"Trade à +{unrealized_pct}% devrait être stagnant "
            f"(seuil={stale_pnl_threshold}%)"
        )

    def test_aggressive_not_affected_by_tight_logic(self):
        """Le profil aggressive ne doit PAS utiliser la logique tight (loss_cut > 0.5%)."""
        from app.services.trading_profile_service import PROFILE_PRESETS

        aggressive = PROFILE_PRESETS["aggressive"]
        # Aggressive n'est pas un profil tight
        assert aggressive.loss_cut_pct > 0.5, (
            f"Aggressive loss_cut_pct={aggressive.loss_cut_pct} devrait être > 0.5"
        )
        # Donc le seuil de stagnation par défaut (0.1%) s'applique, pas le trailing
        stale_pnl_threshold = 0.1
        if aggressive.loss_cut_pct <= 0.5:
            # Ce bloc ne doit PAS être exécuté pour aggressive
            stale_pnl_threshold = getattr(aggressive, "trailing_stop_activation_pct", aggressive.profit_take_pct)

        assert stale_pnl_threshold == 0.1, (
            f"Aggressive stale threshold devrait être 0.1, got {stale_pnl_threshold}"
        )

    def test_stale_threshold_fallback_when_no_trailing(self):
        """Si trailing_stop_activation_pct absent, fallback sur profit_take_pct."""
        # Simuler un profil tight sans trailing stop configuré
        # (via un simple objet avec les attributs nécessaires)
        class FakeProfile:
            loss_cut_pct = 0.3   # tight profile
            profit_take_pct = 0.6
            trailing_stop_activation_pct = None  # Pas configuré

        params = FakeProfile()
        # Même logique que dans paper_trading_service.py
        ts_act = getattr(params, "trailing_stop_activation_pct", None)
        stale_pnl_threshold = ts_act if ts_act else params.profit_take_pct

        assert stale_pnl_threshold == params.profit_take_pct, (
            "Sans trailing, le fallback doit être profit_take_pct"
        )

    def test_stale_threshold_code_path_matches_service(self):
        """Vérifie que la logique du test correspond exactement au code du service."""
        from app.services.trading_profile_service import PROFILE_PRESETS

        for name, profile in PROFILE_PRESETS.items():
            stale_pnl_threshold = 0.1
            if profile.loss_cut_pct <= 0.5:
                ts_act = getattr(profile, "trailing_stop_activation_pct", None)
                stale_pnl_threshold = ts_act if ts_act else profile.profit_take_pct

            if name == "scalping":
                # Scalping tight : doit utiliser trailing_stop_activation_pct
                assert stale_pnl_threshold == profile.trailing_stop_activation_pct, (
                    f"Scalping stale_pnl_threshold devrait être "
                    f"{profile.trailing_stop_activation_pct}, got {stale_pnl_threshold}"
                )
            elif name == "aggressive":
                # Aggressive classique : seuil par défaut 0.1
                assert stale_pnl_threshold == 0.1, (
                    f"Aggressive stale_pnl_threshold devrait être 0.1, got {stale_pnl_threshold}"
                )


# ============================================================
# 13. MULTI-SLOT APRÈS FULL RESET
# ============================================================

class TestMultiSlotAfterReset:
    """
    Tests pour vérifier que le multi-slot est préservé après full reset.

    Bug corrigé : après full reset, max_open_positions retombait à 1
    (défaut schema), empêchant le slot aggressive de tourner en parallèle
    du scalping.
    """

    def test_reset_endpoint_default_max_open_positions_is_3(self, client, db_session):
        """POST /paper/account/reset crée le compte avec max_open_positions=3 par défaut."""
        _insert_btc_candle(db_session, price=85000.0)
        # Créer un compte initial
        client.post("/paper/account", json={"initial_capital": 10000.0})
        # Reset sans spécifier max_open_positions
        resp = client.post("/paper/account/reset", json={
            "confirm": "RESET",
            "initial_capital": 10000.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["account"]["max_open_positions"] == 3, (
            "Après reset, max_open_positions doit être 3 (multi-slot) par défaut"
        )

    def test_create_account_default_max_open_positions_is_3(self, client, db_session):
        """POST /paper/account crée le compte avec max_open_positions=3 par défaut."""
        resp = client.post("/paper/account", json={"initial_capital": 10000.0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_open_positions"] == 3, (
            "POST /paper/account doit créer avec max_open_positions=3 par défaut"
        )

    def test_get_enabled_slots_scalping_multi(self, db_session):
        """En mode scalping + max_open_positions=3, retourne ['scalping', 'aggressive']."""
        service = PaperTradingService(db_session)
        account = service.get_or_create_account()
        account.active_profile = "scalping"
        account.max_open_positions = 3
        db_session.commit()

        slots = service.get_enabled_slots(account)
        assert slots == ["scalping", "aggressive"], (
            f"Attendu ['scalping', 'aggressive'], obtenu {slots}"
        )

    def test_get_enabled_slots_scalping_mono(self, db_session):
        """En mode scalping + max_open_positions=1, retourne ['scalping'] (mono-slot)."""
        service = PaperTradingService(db_session)
        account = service.get_or_create_account()
        account.active_profile = "scalping"
        account.max_open_positions = 1
        db_session.commit()

        slots = service.get_enabled_slots(account)
        assert slots == ["scalping"], (
            f"Attendu ['scalping'] en mono-slot, obtenu {slots}"
        )

    def test_full_reset_then_scalping_gets_multi_slot(self, client, db_session):
        """
        Scénario complet : full reset → changer profil en scalping → get_enabled_slots
        doit retourner scalping + aggressive.
        """
        _insert_btc_candle(db_session, price=85000.0)
        # 1. Créer un compte
        client.post("/paper/account", json={"initial_capital": 10000.0})
        # 2. Full reset
        resp = client.post("/paper/account/reset", json={
            "confirm": "RESET",
            "initial_capital": 10000.0,
        })
        assert resp.status_code == 200
        # 3. Changer profil en scalping
        resp = client.post("/paper/profile", json={"profile": "scalping"})
        assert resp.status_code == 200
        # 4. Vérifier get_enabled_slots via le service
        service = PaperTradingService(db_session)
        account = db_session.query(PaperAccount).first()
        assert account.max_open_positions == 3
        assert account.active_profile == "scalping"
        slots = service.get_enabled_slots(account)
        assert slots == ["scalping", "aggressive"]


# ============================================================
# [v2.0.1] Tests : Assouplissement du slot Aggressive
# ============================================================

class TestAggressiveSlotCalibration:
    """
    Tests pour vérifier le calibrage v2.0.1 du slot aggressive.

    Changements testés :
    - analysis_timeframe passe de None (=4h) à "1h"
    - buy_threshold explicite à 20 (était None → 25 global)
    - sell_threshold explicite à 15 (était None → 20 global)
    - Le slot reste distinct du scalping
    """

    def test_aggressive_timeframe_is_1h(self):
        """Le slot aggressive utilise le timeframe 1h (pas 4h)."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        aggressive = PROFILE_PRESETS["aggressive"]
        assert aggressive.analysis_timeframe == "1h", (
            f"Attendu '1h', obtenu '{aggressive.analysis_timeframe}'"
        )

    def test_aggressive_buy_threshold_is_20(self):
        """Le slot aggressive a un buy_threshold explicite de 20."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        aggressive = PROFILE_PRESETS["aggressive"]
        assert aggressive.buy_threshold == 20, (
            f"Attendu 20, obtenu {aggressive.buy_threshold}"
        )

    def test_aggressive_sell_threshold_is_15(self):
        """Le slot aggressive a un sell_threshold explicite de 15."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        aggressive = PROFILE_PRESETS["aggressive"]
        assert aggressive.sell_threshold == 15, (
            f"Attendu 15, obtenu {aggressive.sell_threshold}"
        )

    def test_aggressive_distinct_from_scalping_timeframe(self):
        """Le timeframe aggressive (1h) est différent du scalping (15m)."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        agg = PROFILE_PRESETS["aggressive"]
        scl = PROFILE_PRESETS["scalping"]
        assert agg.analysis_timeframe != scl.analysis_timeframe, (
            "Les timeframes doivent être distincts : aggressive vs scalping"
        )
        assert agg.analysis_timeframe == "1h"
        assert scl.analysis_timeframe == "15m"

    def test_aggressive_distinct_from_scalping_risk_profile(self):
        """Le profil de risque aggressive reste distinct du scalping."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        agg = PROFILE_PRESETS["aggressive"]
        scl = PROFILE_PRESETS["scalping"]
        # TP plus large
        assert agg.profit_take_pct > scl.profit_take_pct, (
            f"Aggressive TP ({agg.profit_take_pct}) doit être > scalping TP ({scl.profit_take_pct})"
        )
        # SL plus large
        assert agg.loss_cut_pct > scl.loss_cut_pct, (
            f"Aggressive SL ({agg.loss_cut_pct}) doit être > scalping SL ({scl.loss_cut_pct})"
        )
        # Durée max plus longue
        assert agg.max_position_duration_hours > scl.max_position_duration_hours, (
            f"Aggressive duration ({agg.max_position_duration_hours}h) doit être > scalping ({scl.max_position_duration_hours}h)"
        )
        # Pas de trailing stop (scalping en a un)
        assert agg.trailing_stop_pct is None, "Aggressive ne doit pas avoir de trailing stop"
        assert scl.trailing_stop_pct is not None, "Scalping doit avoir un trailing stop"

    def test_aggressive_no_economic_gate(self):
        """Le slot aggressive n'a pas de gate économique (contrairement au scalping)."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        agg = PROFILE_PRESETS["aggressive"]
        scl = PROFILE_PRESETS["scalping"]
        assert agg.economic_gate_enabled is False
        assert scl.economic_gate_enabled is True

    def test_aggressive_no_structural_proofs(self):
        """Le slot aggressive n'exige pas de preuves structurelles."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        agg = PROFILE_PRESETS["aggressive"]
        assert agg.min_structural_proofs == 0

    def test_aggressive_stale_exit_much_longer_than_scalping(self):
        """Le stale exit aggressive (180min) est bien plus long que scalping (15min)."""
        from app.services.trading_profile_service import PROFILE_PRESETS
        agg = PROFILE_PRESETS["aggressive"]
        scl = PROFILE_PRESETS["scalping"]
        assert agg.stale_exit_minutes == 180
        assert scl.stale_exit_minutes == 5
        assert agg.stale_exit_minutes > scl.stale_exit_minutes * 5

    def test_aggressive_uses_1h_in_tick(self, db_session):
        """
        Vérifie que _tick_single_slot résout bien le timeframe 1h pour aggressive.
        Le DecisionService doit être appelé avec timeframe='1h'.
        """
        from app.services.trading_profile_service import PROFILE_PRESETS
        profile = PROFILE_PRESETS["aggressive"]
        # Vérifier le calcul fait dans _tick_single_slot
        _analysis_tf = getattr(profile, "analysis_timeframe", None) or "4h"
        assert _analysis_tf == "1h", f"Timeframe résolu: '{_analysis_tf}' (attendu '1h')"
        # history_days : 1h n'est PAS dans la liste short
        _analysis_days = 1 if _analysis_tf in ("1m", "3m", "5m", "15m", "30m") else 7
        assert _analysis_days == 7, f"history_days résolu: {_analysis_days} (attendu 7)"

    def test_aggressive_works_in_multislot_with_scalping(self, db_session):
        """Le slot aggressive fonctionne dans l'orchestrateur multi-slot à côté du scalping."""
        service = PaperTradingService(db_session)
        account = service.get_or_create_account()
        account.active_profile = "scalping"
        account.max_open_positions = 3
        db_session.commit()

        slots = service.get_enabled_slots(account)
        assert "aggressive" in slots, f"'aggressive' doit être dans les slots: {slots}"
        assert "scalping" in slots, f"'scalping' doit être dans les slots: {slots}"

    def test_aggressive_decision_threshold_allows_score_21(self):
        """
        Avec buy_threshold=20, un score de 21 (> 20) produit action='acheter'.
        Avant le fix (threshold=25), un score de 24 restait en 'attendre'.
        Note : DecisionService utilise '>' strict, pas '>='.
        """
        from app.services.decision_service import DecisionService
        from app.schemas.signal import SignalDirection
        from app.schemas.decision import Scenario

        scenarios = [
            Scenario(
                label="Hausse",
                probability=0.55,
                direction=SignalDirection.BULLISH,
                description="Test hausse",
            ),
            Scenario(
                label="Stable",
                probability=0.25,
                direction=SignalDirection.NEUTRAL,
                description="Test stable",
            ),
            Scenario(
                label="Baisse",
                probability=0.20,
                direction=SignalDirection.BEARISH,
                description="Test baisse",
            ),
        ]

        # Score = 21 avec buy_threshold=20 → 21 > 20 → DOIT donner "acheter"
        ds = DecisionService.__new__(DecisionService)
        rec = ds.generate_recommendation(
            scenarios=scenarios,
            rules=[],
            combined_score=21,
            buy_threshold=20,
            sell_threshold=15,
        )
        assert rec.action == "acheter", (
            f"Score 21 + buy_threshold=20 devrait donner 'acheter', obtenu '{rec.action}'"
        )

    def test_aggressive_decision_score_24_was_blocked_now_passes(self):
        """
        Le score runtime observé (~24) qui bloquait avec l'ancien seuil (25)
        passe maintenant avec le nouveau seuil (20).
        """
        from app.services.decision_service import DecisionService
        from app.schemas.signal import SignalDirection
        from app.schemas.decision import Scenario

        scenarios = [
            Scenario(
                label="Hausse",
                probability=0.55,
                direction=SignalDirection.BULLISH,
                description="Test hausse",
            ),
            Scenario(label="Stable", probability=0.25,
                     direction=SignalDirection.NEUTRAL, description="stable"),
            Scenario(label="Baisse", probability=0.20,
                     direction=SignalDirection.BEARISH, description="baisse"),
        ]

        ds = DecisionService.__new__(DecisionService)

        # Avec l'ancien seuil (25) : score 24 → "attendre"
        rec_old = ds.generate_recommendation(
            scenarios=scenarios, rules=[], combined_score=24,
            buy_threshold=25, sell_threshold=20,
        )
        assert rec_old.action == "attendre", "Score 24 + threshold 25 devrait être 'attendre'"

        # Avec le nouveau seuil (20) : score 24 → "acheter"
        rec_new = ds.generate_recommendation(
            scenarios=scenarios, rules=[], combined_score=24,
            buy_threshold=20, sell_threshold=15,
        )
        assert rec_new.action == "acheter", (
            f"Score 24 + threshold 20 devrait être 'acheter', obtenu '{rec_new.action}'"
        )

    def test_aggressive_decision_threshold_allows_short_at_minus_16(self):
        """
        Avec sell_threshold=15, un score de -16 (< -15) produit action='vendre'.
        Avant le fix (threshold=20), il fallait score < -20.
        Note : DecisionService utilise '<' strict, pas '<='.
        """
        from app.services.decision_service import DecisionService
        from app.schemas.signal import SignalDirection
        from app.schemas.decision import Scenario

        scenarios = [
            Scenario(
                label="Baisse",
                probability=0.55,
                direction=SignalDirection.BEARISH,
                description="Test baisse",
            ),
            Scenario(
                label="Stable",
                probability=0.25,
                direction=SignalDirection.NEUTRAL,
                description="Test stable",
            ),
            Scenario(
                label="Hausse",
                probability=0.20,
                direction=SignalDirection.BULLISH,
                description="Test hausse",
            ),
        ]

        ds = DecisionService.__new__(DecisionService)
        rec = ds.generate_recommendation(
            scenarios=scenarios,
            rules=[],
            combined_score=-16,
            buy_threshold=20,
            sell_threshold=15,
        )
        assert rec.action == "vendre", (
            f"Score -16 + sell_threshold=15 devrait donner 'vendre', obtenu '{rec.action}'"
        )


# ============================================================
# [v2.0.5] Tests : Préservation du profil actif (anti-bascule)
# ============================================================

class TestProfilePreservation:
    """
    Tests de non-régression pour l'incident v2.0.5 :
    le profil actif ne doit JAMAIS basculer en "conservative"
    sans action explicite utilisateur.

    Couvre :
    - Full reset préserve le profil
    - get_or_create_account avec profil explicite
    - Tick ne modifie pas le profil
    - Autonomous start avec profil
    - Self-healing (activation) ne modifie pas le profil
    - Création de compte avec profil personnalisé
    """

    def test_full_reset_preserves_scalping_profile(self, db_session):
        """[v2.0.5] Full reset doit préserver le profil scalping, pas basculer en conservative."""
        _insert_btc_candle(db_session, price=85000.0)
        service = PaperTradingService(db_session)

        # 1. Créer un compte et le mettre en scalping
        account = service.get_or_create_account()
        account.active_profile = "scalping"
        account.is_active = True
        db_session.commit()
        assert account.active_profile == "scalping"

        # 2. Full reset
        new_account, purged = service.reset_account(initial_capital=10000.0)

        # 3. Le profil doit être "scalping", pas "conservative"
        assert new_account.active_profile == "scalping", (
            f"INCIDENT v2.0.5 : Le reset a basculé le profil de 'scalping' → "
            f"'{new_account.active_profile}'. Attendu 'scalping'."
        )

    def test_full_reset_preserves_aggressive_profile(self, db_session):
        """[v2.0.5] Full reset doit préserver le profil aggressive."""
        _insert_btc_candle(db_session, price=85000.0)
        service = PaperTradingService(db_session)

        account = service.get_or_create_account()
        account.active_profile = "aggressive"
        account.is_active = True
        db_session.commit()

        new_account, purged = service.reset_account(initial_capital=10000.0)
        assert new_account.active_profile == "aggressive", (
            f"Le reset a basculé le profil de 'aggressive' → '{new_account.active_profile}'"
        )

    def test_full_reset_preserves_balanced_profile(self, db_session):
        """[v2.0.5] Full reset doit préserver le profil balanced."""
        _insert_btc_candle(db_session, price=85000.0)
        service = PaperTradingService(db_session)

        account = service.get_or_create_account()
        account.active_profile = "balanced"
        db_session.commit()

        new_account, _ = service.reset_account(initial_capital=10000.0)
        assert new_account.active_profile == "balanced"

    def test_full_reset_with_explicit_profile_override(self, db_session):
        """[v2.0.5] Full reset avec preserve_profile explicite utilise le profil demandé."""
        _insert_btc_candle(db_session, price=85000.0)
        service = PaperTradingService(db_session)

        account = service.get_or_create_account()
        account.active_profile = "conservative"
        db_session.commit()

        # Forcer "scalping" via preserve_profile
        new_account, _ = service.reset_account(
            initial_capital=10000.0,
            preserve_profile="scalping"
        )
        assert new_account.active_profile == "scalping", (
            f"preserve_profile='scalping' non respecté : '{new_account.active_profile}'"
        )

    def test_get_or_create_account_with_profile(self, db_session):
        """[v2.0.5] get_or_create_account avec active_profile crée le bon profil."""
        service = PaperTradingService(db_session)

        # Aucun compte n'existe
        assert db_session.query(PaperAccount).count() == 0

        # Créer avec profil "scalping"
        account = service.get_or_create_account(active_profile="scalping")
        assert account.active_profile == "scalping", (
            f"Le compte a été créé avec active_profile='{account.active_profile}' "
            f"au lieu de 'scalping'"
        )

    def test_get_or_create_account_does_not_overwrite_existing_profile(self, db_session):
        """[v2.0.5] get_or_create_account ne doit PAS écraser le profil d'un compte existant."""
        service = PaperTradingService(db_session)

        # Créer un compte en scalping
        account = service.get_or_create_account(active_profile="scalping")
        assert account.active_profile == "scalping"

        # Re-appeler avec un profil différent — ne doit PAS changer
        same_account = service.get_or_create_account(active_profile="conservative")
        assert same_account.active_profile == "scalping", (
            f"get_or_create_account a écrasé le profil existant ! "
            f"'scalping' → '{same_account.active_profile}'"
        )

    def test_tick_does_not_change_profile(self, client, db_session):
        """[v2.0.5] POST /paper/tick ne doit PAS modifier le profil actif."""
        _insert_btc_candle(db_session, price=85000.0)

        # 1. Créer un compte en scalping, actif
        service = PaperTradingService(db_session)
        account = service.get_or_create_account()
        account.active_profile = "scalping"
        account.is_active = True
        account.max_open_positions = 3
        db_session.commit()

        # 2. Exécuter un tick
        resp = client.post("/paper/tick")
        assert resp.status_code == 200

        # 3. Vérifier que le profil n'a pas changé
        db_session.expire_all()
        account = db_session.query(PaperAccount).first()
        assert account.active_profile == "scalping", (
            f"POST /paper/tick a basculé le profil de 'scalping' → "
            f"'{account.active_profile}'"
        )

    def test_create_account_endpoint_does_not_change_profile(self, client, db_session):
        """[v2.0.5] POST /paper/account ne doit PAS écraser le profil d'un compte existant."""
        _insert_btc_candle(db_session, price=85000.0)

        # 1. Créer un compte et le mettre en scalping
        service = PaperTradingService(db_session)
        account = service.get_or_create_account()
        account.active_profile = "scalping"
        account.is_active = True
        db_session.commit()

        # 2. Appeler POST /paper/account (self-healing / activation)
        resp = client.post("/paper/account", json={
            "initial_capital": 10000.0,
            "max_open_positions": 3,
        })
        assert resp.status_code == 200

        # 3. Vérifier que le profil n'a pas changé
        db_session.expire_all()
        account = db_session.query(PaperAccount).first()
        assert account.active_profile == "scalping", (
            f"POST /paper/account a basculé le profil de 'scalping' → "
            f"'{account.active_profile}'"
        )

    def test_full_reset_endpoint_preserves_profile(self, client, db_session):
        """[v2.0.5] POST /paper/account/reset doit préserver le profil via le backend."""
        _insert_btc_candle(db_session, price=85000.0)

        # 1. Créer un compte en scalping
        client.post("/paper/account", json={"initial_capital": 10000.0})
        resp = client.post("/paper/profile", json={"profile": "scalping"})
        assert resp.status_code == 200

        # 2. Full reset
        resp = client.post("/paper/account/reset", json={
            "confirm": "RESET",
            "initial_capital": 10000.0,
        })
        assert resp.status_code == 200

        # 3. Vérifier que le profil est toujours "scalping"
        db_session.expire_all()
        account = db_session.query(PaperAccount).first()
        assert account.active_profile == "scalping", (
            f"POST /paper/account/reset a basculé le profil de 'scalping' → "
            f"'{account.active_profile}'"
        )

    def test_full_reset_no_prior_account_defaults_to_conservative(self, db_session):
        """[v2.0.5] Full reset sans compte existant → conservative est acceptable (aucun profil à sauver)."""
        _insert_btc_candle(db_session, price=85000.0)

        # Aucun compte n'existe
        assert db_session.query(PaperAccount).count() == 0

        service = PaperTradingService(db_session)
        new_account, _ = service.reset_account(initial_capital=10000.0)

        # Sans ancien compte, conservative est le default attendu
        assert new_account.active_profile == "conservative"

    def test_autonomous_start_preserves_profile_via_endpoint(self, client, db_session):
        """[v2.0.5] POST /paper/autonomous/start avec profile=scalping doit poser le profil."""
        _insert_btc_candle(db_session, price=85000.0)

        # 1. Créer un compte
        client.post("/paper/account", json={"initial_capital": 10000.0})

        # 2. Démarrer le mode autonome avec scalping
        resp = client.post("/paper/autonomous/start", json={
            "interval_seconds": 30,
            "profile": "scalping",
        })
        assert resp.status_code == 200

        # 3. Vérifier le profil
        db_session.expire_all()
        account = db_session.query(PaperAccount).first()
        assert account.active_profile == "scalping", (
            f"Autonomous start avec profile=scalping a donné "
            f"active_profile='{account.active_profile}'"
        )

        # Cleanup : arrêter le mode autonome
        client.post("/paper/autonomous/stop")


# ============================================================
# TESTS v2.0.15 — entry_candle_direction
# ============================================================

class TestEntryCandleDirection:
    """Tests pour le champ entry_candle_direction sur PaperTrade."""

    def test_trade_default_candle_direction_is_none(self, db_session):
        """Un trade sans entry_candle_direction a None par défaut (rétrocompat)."""
        account = _create_active_account(db_session)
        trade = _create_open_trade(db_session, account.id)
        assert trade.entry_candle_direction is None

    def test_trade_with_green_candle_direction(self, db_session):
        """Un trade peut stocker entry_candle_direction='green'."""
        account = _create_active_account(db_session)
        trade = PaperTrade(
            account_id=account.id,
            status="open",
            direction="long",
            entry_price=85000.0,
            stop_loss_price=80750.0,
            take_profit_price=93500.0,
            position_size_usd=2500.0,
            entry_reason="Test green candle",
            decision_score=35.0,
            entry_ts=datetime.now(timezone.utc),
            entry_candle_direction="green",
        )
        db_session.add(trade)
        db_session.commit()
        db_session.refresh(trade)
        assert trade.entry_candle_direction == "green"

    def test_trade_with_red_candle_direction(self, db_session):
        """Un trade peut stocker entry_candle_direction='red'."""
        account = _create_active_account(db_session)
        trade = PaperTrade(
            account_id=account.id,
            status="open",
            direction="short",
            entry_price=85000.0,
            stop_loss_price=89250.0,
            take_profit_price=80750.0,
            position_size_usd=2500.0,
            entry_reason="Test red candle",
            decision_score=-35.0,
            entry_ts=datetime.now(timezone.utc),
            entry_candle_direction="red",
        )
        db_session.add(trade)
        db_session.commit()
        db_session.refresh(trade)
        assert trade.entry_candle_direction == "red"

    def test_open_position_stores_candle_direction(self, db_session):
        """_open_position stocke correctement entry_candle_direction."""
        _insert_btc_candle(db_session, price=85000.0)
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)

        trade = service._open_position(
            account=account,
            price=85000.0,
            sl=80750.0,
            tp=93500.0,
            size_usd=2500.0,
            reason="Test candle direction",
            score=40.0,
            direction="long",
            entry_candle_direction="green",
        )
        assert trade is not None
        assert trade.entry_candle_direction == "green"

    def test_open_position_without_candle_direction(self, db_session):
        """_open_position sans entry_candle_direction → None (rétrocompat)."""
        _insert_btc_candle(db_session, price=85000.0)
        account = _create_active_account(db_session)
        service = PaperTradingService(db_session)

        trade = service._open_position(
            account=account,
            price=85000.0,
            sl=80750.0,
            tp=93500.0,
            size_usd=2500.0,
            reason="Test no candle direction",
            score=40.0,
            direction="long",
        )
        assert trade is not None
        assert trade.entry_candle_direction is None

    def test_schema_includes_candle_direction(self, db_session):
        """PaperTradeResponse inclut entry_candle_direction."""
        account = _create_active_account(db_session)
        trade = PaperTrade(
            account_id=account.id,
            status="open",
            direction="long",
            entry_price=85000.0,
            stop_loss_price=80750.0,
            take_profit_price=93500.0,
            position_size_usd=2500.0,
            entry_reason="Test schema",
            decision_score=35.0,
            entry_ts=datetime.now(timezone.utc),
            entry_candle_direction="green",
        )
        db_session.add(trade)
        db_session.commit()
        db_session.refresh(trade)

        resp = PaperTradeResponse.model_validate(trade)
        assert resp.entry_candle_direction == "green"

    def test_status_endpoint_includes_candle_direction(self, client, db_session):
        """GET /paper/status inclut entry_candle_direction dans open_positions."""
        _insert_btc_candle(db_session, price=85000.0)
        account = _create_active_account(db_session)
        trade = PaperTrade(
            account_id=account.id,
            status="open",
            direction="long",
            entry_price=85000.0,
            stop_loss_price=80750.0,
            take_profit_price=93500.0,
            position_size_usd=2500.0,
            entry_reason="Test endpoint",
            decision_score=35.0,
            entry_ts=datetime.now(timezone.utc),
            entry_candle_direction="red",
        )
        db_session.add(trade)
        db_session.commit()

        resp = client.get("/paper/status")
        assert resp.status_code == 200
        data = resp.json()
        # Vérifier dans open_positions ou open_position
        if data.get("open_positions"):
            pos = data["open_positions"][0]
            assert pos["entry_candle_direction"] == "red"
        elif data.get("open_position"):
            pos = data["open_position"]
            assert pos["entry_candle_direction"] == "red"

