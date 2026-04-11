"""
Tests de la corrélation runtime et de l'enrichissement BTC du learning.

v2.0.2 — Corrélation trades vs mouvement BTC réel.
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.candle import Candle
from app.models.learning import LearningSignal
from app.services.runtime_correlation_service import RuntimeCorrelationService
from app.services.learning_service import LearningService


# ================================================================
# HELPERS
# ================================================================

def _make_account(db, capital=10000.0):
    account = PaperAccount(
        initial_capital=capital,
        current_capital=capital,
        total_pnl=0.0,
        total_pnl_pct=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=0.0,
        is_active=True,
        peak_capital=capital,
        max_open_positions=3,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _make_trade(
    db, account, entry_price=73000, exit_price=73100, direction="long",
    status="closed_stale", pnl=1.0, pnl_pct=0.1, duration_hours=0.08,
    slot="scalping", score=63.0, entry_ts=None, exit_ts=None,
    profile_type="scalping",
):
    now = datetime.now(timezone.utc)
    entry = entry_ts or now - timedelta(minutes=5)
    exit_ = exit_ts or now
    trade = PaperTrade(
        account_id=account.id,
        direction=direction,
        status=status,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_loss_price=entry_price * 0.998,
        take_profit_price=entry_price * 1.008,
        position_size_usd=2500.0,
        leverage=1.0,
        pnl=pnl,
        pnl_pct=pnl_pct,
        entry_reason="Test trade",
        exit_reason=status,
        decision_score=score,
        entry_ts=entry,
        exit_ts=exit_,
        duration_hours=duration_hours,
        slot=slot,
        profile_type=profile_type,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def _make_candle(
    db, timestamp, open_price=73000, close_price=73100,
    high_price=73200, low_price=72900, timeframe="1h",
    symbol="BTC/USD",
):
    candle = Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=100.0,
        source="test",
    )
    db.add(candle)
    db.commit()
    db.refresh(candle)
    return candle


# ================================================================
# TESTS DU SERVICE RuntimeCorrelationService
# ================================================================

class TestRuntimeCorrelationService:
    """Tests du service de corrélation runtime."""

    def test_empty_db_returns_empty(self, db_session):
        """DB vide → réponse vide."""
        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        assert result.trades == []
        assert result.missed_movements == []
        assert result.summary.total_trades == 0

    def test_no_account_returns_empty(self, db_session):
        """Pas de compte → réponse vide."""
        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        assert result.summary.total_trades == 0

    def test_trades_without_candles(self, db_session):
        """Trades sans bougies → trades retournés mais sans contexte BTC."""
        account = _make_account(db_session)
        _make_trade(db_session, account)
        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        assert len(result.trades) == 1
        assert result.trades[0].btc_context.trend_at_entry is None

    def test_single_trade_with_candles(self, db_session):
        """1 trade + bougies → contexte BTC renseigné."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)
        entry_ts = now - timedelta(minutes=10)
        exit_ts = now - timedelta(minutes=5)

        trade = _make_trade(
            db_session, account,
            entry_price=73000, exit_price=73100,
            entry_ts=entry_ts, exit_ts=exit_ts,
            pnl=2.0, pnl_pct=0.137,
        )

        # Bougie couvrant l'entrée (hausse)
        _make_candle(
            db_session,
            timestamp=entry_ts - timedelta(hours=1),
            open_price=72900, close_price=73050,  # hausse
        )
        # Bougie après la sortie
        _make_candle(
            db_session,
            timestamp=exit_ts + timedelta(minutes=5),
            open_price=73100, close_price=73200,  # hausse après
        )

        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        assert len(result.trades) == 1
        tc = result.trades[0]
        assert tc.btc_context.trend_at_entry == "up"
        assert tc.btc_context.btc_move_during_pct is not None
        assert tc.btc_context.btc_move_after_exit_pct is not None

    def test_fallback_to_4h_candles(self, db_session):
        """Pas de bougies 1h → utilise 4h."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)
        entry_ts = now - timedelta(minutes=10)
        exit_ts = now - timedelta(minutes=5)

        _make_trade(
            db_session, account,
            entry_ts=entry_ts, exit_ts=exit_ts,
        )
        _make_candle(
            db_session,
            timestamp=entry_ts - timedelta(hours=4),
            open_price=72800, close_price=72700,  # baisse
            timeframe="4h",
        )

        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        assert result.summary.candle_timeframe_used == "4h"
        assert result.trades[0].btc_context.trend_at_entry == "down"

    def test_missed_movement_detection(self, db_session):
        """Détecte un mouvement BTC significatif entre deux trades."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)

        # Trade 1 : sort à T-2h
        t1 = _make_trade(
            db_session, account,
            entry_ts=now - timedelta(hours=3),
            exit_ts=now - timedelta(hours=2),
        )
        # Trade 2 : entre à T-30min (1h30 de gap)
        t2 = _make_trade(
            db_session, account,
            entry_ts=now - timedelta(minutes=30),
            exit_ts=now,
        )
        # Bougie pendant le gap (entre T-2h et T-30min)
        _make_candle(
            db_session,
            timestamp=now - timedelta(hours=1, minutes=30),
            open_price=73000, close_price=73200,  # +0.27%
        )

        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation(missed_threshold_pct=0.15)
        assert result.summary.missed_movements_count >= 1
        assert len(result.missed_movements) >= 1
        assert result.missed_movements[0].direction == "up"

    def test_premature_stale_detection(self, db_session):
        """Stale exit + BTC favorable après → missed_favorable_move=True."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)
        entry_ts = now - timedelta(minutes=10)
        exit_ts = now - timedelta(minutes=5)

        _make_trade(
            db_session, account,
            status="closed_stale",
            entry_ts=entry_ts, exit_ts=exit_ts,
            pnl=-0.5, pnl_pct=-0.02,
        )
        # Bougie entrée
        _make_candle(
            db_session,
            timestamp=entry_ts - timedelta(hours=1),
            open_price=72900, close_price=73000,
        )
        # Bougie après sortie : forte hausse (+0.3%)
        _make_candle(
            db_session,
            timestamp=exit_ts + timedelta(minutes=5),
            open_price=73000, close_price=73220,  # +0.3% favorable pour long
        )

        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        assert len(result.trades) == 1
        tc = result.trades[0]
        assert tc.btc_context.missed_favorable_move is True
        assert result.summary.premature_stale_count == 1

    def test_capture_efficiency_long_positive(self, db_session):
        """Long gagnant capture ~100% du mouvement BTC."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)

        _make_trade(
            db_session, account,
            entry_price=73000, exit_price=73200,
            direction="long", status="closed_trailing_stop",
            pnl=5.0, pnl_pct=0.274,
            entry_ts=now - timedelta(minutes=10),
            exit_ts=now,
        )
        _make_candle(
            db_session,
            timestamp=now - timedelta(hours=1),
            open_price=72900, close_price=73000,
        )

        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        tc = result.trades[0]
        assert tc.capture_efficiency_pct is not None
        assert tc.capture_efficiency_pct == 100.0

    def test_capture_efficiency_wrong_direction(self, db_session):
        """Long perdant sur BTC baissier → capture=0."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)

        _make_trade(
            db_session, account,
            entry_price=73000, exit_price=72900,
            direction="long", status="closed_stale",
            pnl=-2.5, pnl_pct=-0.137,
            entry_ts=now - timedelta(minutes=5),
            exit_ts=now,
        )
        _make_candle(
            db_session,
            timestamp=now - timedelta(hours=1),
            open_price=73100, close_price=73000,
        )

        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        tc = result.trades[0]
        assert tc.capture_efficiency_pct == 0.0

    def test_summary_statistics(self, db_session):
        """Le résumé calcule correctement available vs captured."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)

        _make_trade(
            db_session, account,
            entry_price=73000, exit_price=73100,
            pnl=2.0, pnl_pct=0.137,
            entry_ts=now - timedelta(minutes=10),
            exit_ts=now - timedelta(minutes=5),
        )
        # Bougies BTC
        _make_candle(
            db_session,
            timestamp=now - timedelta(hours=2),
            open_price=72800, close_price=73000,  # +0.27%
        )
        _make_candle(
            db_session,
            timestamp=now - timedelta(hours=1),
            open_price=73000, close_price=73100,  # +0.14%
        )

        service = RuntimeCorrelationService(db_session)
        result = service.build_correlation()
        assert result.summary.total_candles_analyzed == 2
        assert result.summary.total_btc_movement_available_pct > 0
        assert result.summary.total_btc_movement_captured_pct > 0


# ================================================================
# TESTS DU LEARNING ENRICHI AVEC CONTEXTE BTC
# ================================================================

class TestLearningBtcContext:
    """Tests de l'enrichissement BTC dans le LearningService."""

    def test_record_sample_with_btc_context(self, db_session):
        """Trade + bougie → les champs BTC sont renseignés dans LearningSignal."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)
        entry_ts = now - timedelta(minutes=10)
        exit_ts = now - timedelta(minutes=5)

        trade = _make_trade(
            db_session, account,
            entry_price=73000, exit_price=73100,
            pnl=2.0, pnl_pct=0.137,
            entry_ts=entry_ts, exit_ts=exit_ts,
        )
        _make_candle(
            db_session,
            timestamp=entry_ts - timedelta(hours=1),
            open_price=72900, close_price=73050,
        )
        _make_candle(
            db_session,
            timestamp=exit_ts + timedelta(minutes=5),
            open_price=73100, close_price=73200,
        )

        learning = LearningService(db_session)
        sample = learning.record_sample(trade)
        assert sample is not None
        assert sample.btc_trend_at_entry == "up"
        assert sample.btc_move_during_pct is not None
        assert sample.btc_move_after_exit_pct is not None

    def test_record_sample_without_candles(self, db_session):
        """Pas de bougies → trend et move_after sont None, move_during calculé depuis trade."""
        account = _make_account(db_session)
        trade = _make_trade(db_session, account)

        learning = LearningService(db_session)
        sample = learning.record_sample(trade)
        assert sample is not None
        assert sample.btc_trend_at_entry is None
        # btc_move_during_pct est calculé à partir des prix entry/exit du trade
        assert sample.btc_move_during_pct is not None
        # btc_move_after_exit_pct nécessite une bougie post-exit
        assert sample.btc_move_after_exit_pct is None

    def test_missed_favorable_move_flagged(self, db_session):
        """Stale exit + bougie post favorable → missed_favorable_move=1."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)
        entry_ts = now - timedelta(minutes=10)
        exit_ts = now - timedelta(minutes=5)

        trade = _make_trade(
            db_session, account,
            status="closed_stale",
            pnl=-0.5, pnl_pct=-0.02,
            entry_ts=entry_ts, exit_ts=exit_ts,
        )
        _make_candle(
            db_session,
            timestamp=entry_ts - timedelta(hours=1),
            open_price=72900, close_price=73000,
        )
        _make_candle(
            db_session,
            timestamp=exit_ts + timedelta(minutes=5),
            open_price=73000, close_price=73300,  # +0.41% favorable
        )

        learning = LearningService(db_session)
        sample = learning.record_sample(trade)
        assert sample is not None
        assert sample.missed_favorable_move == 1

    def test_non_stale_exit_not_flagged(self, db_session):
        """Trailing stop exit → missed_favorable_move=0 même si BTC monte après."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)
        entry_ts = now - timedelta(minutes=10)
        exit_ts = now - timedelta(minutes=5)

        trade = _make_trade(
            db_session, account,
            status="closed_trailing_stop",
            pnl=5.0, pnl_pct=0.27,
            entry_ts=entry_ts, exit_ts=exit_ts,
        )
        _make_candle(
            db_session,
            timestamp=exit_ts + timedelta(minutes=5),
            open_price=73100, close_price=73400,
        )

        learning = LearningService(db_session)
        sample = learning.record_sample(trade)
        assert sample is not None
        assert sample.missed_favorable_move == 0


# ================================================================
# TESTS ENDPOINT
# ================================================================

class TestRuntimeCorrelationEndpoint:
    """Tests de l'endpoint GET /audit/runtime-correlation."""

    def test_endpoint_returns_200(self, client):
        """L'endpoint retourne 200 même sans données."""
        response = client.get("/audit/runtime-correlation")
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert "missed_movements" in data
        assert "summary" in data

    def test_endpoint_with_threshold(self, client):
        """L'endpoint accepte le paramètre missed_threshold_pct."""
        response = client.get("/audit/runtime-correlation?missed_threshold_pct=0.5")
        assert response.status_code == 200

    def test_endpoint_empty_returns_zero_summary(self, client):
        """DB vide → summary avec total_trades=0."""
        response = client.get("/audit/runtime-correlation")
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["total_trades"] == 0
        assert data["trades"] == []

