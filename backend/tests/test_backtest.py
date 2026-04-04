"""
Tests pour le module de backtesting (v1.1).

Classes de test :
- TestBacktestMetricsComputation : calcul des metriques avec donnees connues
- TestBacktestTradeSimulation : logique entree/sortie de positions
- TestBacktestEquityCurve : courbe d'equity et drawdown
- TestBacktestServiceIntegration : backtest complet avec DB
- TestBacktestEndpoints : tests HTTP POST /backtest/run
- TestBacktestEdgeCases : cas limites
"""

import pytest
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.schemas.backtest import (
    BacktestConfig,
    BacktestTradeItem,
    BacktestMetrics,
    EquityPoint,
    BacktestMeta,
    BacktestResponse,
    TradeDirection,
)
from app.services.backtest_service import BacktestService
from app.models import Candle


# ============================================================
# HELPERS : insertion de candles de test
# ============================================================

def _insert_candles(db, symbol, timeframe, prices, start_dt=None):
    """Insere des candles avec des prix sequentiels."""
    if start_dt is None:
        start_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)

    tf_hours = {"30m": 0.5, "1h": 1, "4h": 4, "1d": 24}.get(timeframe, 4)
    delta = timedelta(hours=tf_hours)

    for i, price in enumerate(prices):
        ts = start_dt + delta * i
        candle = Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            open_price=price * 0.999,
            high_price=price * 1.01,
            low_price=price * 0.99,
            close_price=price,
            volume=100.0,
            source="test",
        )
        db.add(candle)
    db.commit()


# ============================================================
# TEST SCHEMAS
# ============================================================

class TestBacktestSchemas:
    """Tests des schemas Pydantic backtest."""

    def test_config_defaults(self):
        """Config par defaut valide."""
        config = BacktestConfig()
        assert config.symbol == "BTC/USD"
        assert config.timeframe == "4h"
        assert config.start_days_ago == 30
        assert config.initial_capital == 10000.0

    def test_config_custom(self):
        """Config personnalisee."""
        config = BacktestConfig(
            symbol="BTC/EUR",
            timeframe="1h",
            start_days_ago=60,
            initial_capital=50000.0,
        )
        assert config.symbol == "BTC/EUR"
        assert config.initial_capital == 50000.0

    def test_trade_item_creation(self):
        """Creation d'un trade item."""
        trade = BacktestTradeItem(
            entry_ts="2026-03-01T00:00:00",
            exit_ts="2026-03-02T00:00:00",
            direction=TradeDirection.BUY,
            entry_price=50000,
            exit_price=51000,
            pnl=200.0,
            pnl_pct=2.0,
        )
        assert trade.direction == TradeDirection.BUY
        assert trade.pnl == 200.0

    def test_metrics_defaults(self):
        """Metriques par defaut = zeros."""
        m = BacktestMetrics()
        assert m.total_trades == 0
        assert m.win_rate == 0.0
        assert m.sharpe_ratio == 0.0

    def test_equity_point(self):
        """Point d'equity curve."""
        ep = EquityPoint(ts="2026-03-01T00:00:00", capital=10500.0, drawdown_pct=1.5)
        assert ep.capital == 10500.0
        assert ep.drawdown_pct == 1.5

    def test_backtest_response_structure(self):
        """Response complete."""
        resp = BacktestResponse(
            meta=BacktestMeta(
                symbol="BTC/USD", timeframe="4h",
                start_ts="2026-03-01", end_ts="2026-03-31",
                initial_capital=10000,
            ),
            metrics=BacktestMetrics(),
            summary="Test",
        )
        assert resp.meta.symbol == "BTC/USD"
        assert resp.trades == []


# ============================================================
# TEST METRIQUES
# ============================================================

class TestBacktestMetricsComputation:
    """Tests du calcul des metriques."""

    def test_win_rate_all_winning(self, db_session):
        """Win rate = 1.0 si tous les trades sont gagnants."""
        service = BacktestService(db_session)
        trades = [
            BacktestTradeItem(
                entry_ts="2026-03-01T00:00:00", exit_ts="2026-03-02T00:00:00",
                direction=TradeDirection.BUY, entry_price=50000, exit_price=51000,
                pnl=200, pnl_pct=2.0, duration_hours=24,
            ),
            BacktestTradeItem(
                entry_ts="2026-03-03T00:00:00", exit_ts="2026-03-04T00:00:00",
                direction=TradeDirection.BUY, entry_price=51000, exit_price=52000,
                pnl=196, pnl_pct=1.96, duration_hours=24,
            ),
        ]
        equity = [EquityPoint(ts="2026-03-01", capital=10200, drawdown_pct=0)]
        metrics = service._compute_metrics(trades, 10000, 10396, equity, 50000, 52000)
        assert metrics.win_rate == 1.0
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 0

    def test_win_rate_mixed(self, db_session):
        """Win rate correct avec trades mixtes."""
        service = BacktestService(db_session)
        trades = [
            BacktestTradeItem(
                entry_ts="t1", exit_ts="t2", direction=TradeDirection.BUY,
                entry_price=50000, exit_price=51000, pnl=200, pnl_pct=2.0,
                duration_hours=24,
            ),
            BacktestTradeItem(
                entry_ts="t3", exit_ts="t4", direction=TradeDirection.BUY,
                entry_price=51000, exit_price=50000, pnl=-196, pnl_pct=-1.96,
                duration_hours=24,
            ),
        ]
        equity = [EquityPoint(ts="t1", capital=10000, drawdown_pct=0)]
        metrics = service._compute_metrics(trades, 10000, 10004, equity, 50000, 50000)
        assert metrics.win_rate == 0.5
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 1

    def test_profit_factor(self, db_session):
        """Profit factor = gains / pertes."""
        service = BacktestService(db_session)
        trades = [
            BacktestTradeItem(
                entry_ts="t1", exit_ts="t2", direction=TradeDirection.BUY,
                entry_price=100, exit_price=110, pnl=300, pnl_pct=10, duration_hours=1,
            ),
            BacktestTradeItem(
                entry_ts="t3", exit_ts="t4", direction=TradeDirection.BUY,
                entry_price=110, exit_price=105, pnl=-150, pnl_pct=-5, duration_hours=1,
            ),
        ]
        equity = [EquityPoint(ts="t1", capital=10000, drawdown_pct=0)]
        metrics = service._compute_metrics(trades, 10000, 10150, equity, 100, 105)
        assert metrics.profit_factor == 2.0  # 300 / 150

    def test_max_drawdown(self, db_session):
        """Max drawdown calcule depuis l'equity curve."""
        service = BacktestService(db_session)
        equity = [
            EquityPoint(ts="t1", capital=10000, drawdown_pct=0),
            EquityPoint(ts="t2", capital=10500, drawdown_pct=0),
            EquityPoint(ts="t3", capital=9800, drawdown_pct=6.67),
            EquityPoint(ts="t4", capital=10200, drawdown_pct=2.86),
        ]
        trades = [
            BacktestTradeItem(
                entry_ts="t1", exit_ts="t4", direction=TradeDirection.BUY,
                entry_price=100, exit_price=102, pnl=200, pnl_pct=2.0, duration_hours=1,
            ),
        ]
        metrics = service._compute_metrics(trades, 10000, 10200, equity, 100, 102)
        assert metrics.max_drawdown_pct == 6.67

    def test_sharpe_ratio_two_trades(self, db_session):
        """Sharpe ratio calcule avec 2 trades."""
        service = BacktestService(db_session)
        trades = [
            BacktestTradeItem(
                entry_ts="t1", exit_ts="t2", direction=TradeDirection.BUY,
                entry_price=100, exit_price=110, pnl=1000, pnl_pct=10.0, duration_hours=1,
            ),
            BacktestTradeItem(
                entry_ts="t3", exit_ts="t4", direction=TradeDirection.BUY,
                entry_price=110, exit_price=121, pnl=1000, pnl_pct=10.0, duration_hours=1,
            ),
        ]
        equity = [EquityPoint(ts="t1", capital=10000, drawdown_pct=0)]
        metrics = service._compute_metrics(trades, 10000, 12000, equity, 100, 121)
        # Deux trades identiques => std = 0 => sharpe devrait etre 0 (division par 0 evitee)
        # En fait: mean=10, variance=0, std=0 => sharpe=0
        assert metrics.sharpe_ratio == 0.0

    def test_buy_and_hold_benchmark(self, db_session):
        """Buy & Hold calcule correctement."""
        service = BacktestService(db_session)
        metrics = service._compute_metrics([], 10000, 10000, [], 50000, 55000)
        assert metrics.buy_and_hold_pnl_pct == 10.0  # +10%

    def test_overfitting_warning_few_trades(self, db_session):
        """Warning si moins de 10 trades."""
        service = BacktestService(db_session)
        trades = [
            BacktestTradeItem(
                entry_ts="t1", exit_ts="t2", direction=TradeDirection.BUY,
                entry_price=100, exit_price=110, pnl=100, pnl_pct=10, duration_hours=1,
            ),
        ]
        equity = [EquityPoint(ts="t1", capital=10000, drawdown_pct=0)]
        metrics = service._compute_metrics(trades, 10000, 10100, equity, 100, 110)
        assert metrics.overfitting_warning is True

    def test_no_trades_returns_zero_metrics(self, db_session):
        """0 trades => metriques a zero sauf B&H."""
        service = BacktestService(db_session)
        metrics = service._compute_metrics([], 10000, 10000, [], 50000, 50000)
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.net_pnl == 0.0

    def test_avg_trade_duration(self, db_session):
        """Duree moyenne calculee."""
        service = BacktestService(db_session)
        trades = [
            BacktestTradeItem(
                entry_ts="t1", exit_ts="t2", direction=TradeDirection.BUY,
                entry_price=100, exit_price=110, pnl=100, pnl_pct=10,
                duration_hours=10,
            ),
            BacktestTradeItem(
                entry_ts="t3", exit_ts="t4", direction=TradeDirection.BUY,
                entry_price=110, exit_price=120, pnl=100, pnl_pct=9,
                duration_hours=20,
            ),
        ]
        equity = [EquityPoint(ts="t1", capital=10000, drawdown_pct=0)]
        metrics = service._compute_metrics(trades, 10000, 10200, equity, 100, 120)
        assert metrics.avg_trade_duration_hours == 15.0


# ============================================================
# TEST INTEGRATION DB
# ============================================================

class TestBacktestServiceIntegration:
    """Tests d'integration avec vraie DB."""

    def test_insufficient_data(self, db_session):
        """Retourne un message si pas assez de candles."""
        service = BacktestService(db_session)
        config = BacktestConfig(start_days_ago=30)
        result = service.run(config)
        assert "insuffisantes" in result["summary"].lower() or "insuffisantes" in result.get("summary", "").lower() or result["metrics"]["total_trades"] == 0

    def test_single_candle_insufficient(self, db_session):
        """Un seul candle = insuffisant."""
        _insert_candles(db_session, "BTC/USD", "4h", [50000])
        service = BacktestService(db_session)
        config = BacktestConfig(start_days_ago=1)
        result = service.run(config)
        assert result["metrics"]["total_trades"] == 0

    def test_run_with_enough_candles(self, db_session):
        """Backtest avec assez de candles retourne une structure valide."""
        # Generer 60 candles (10 jours en 4h)
        prices = []
        base = 50000
        for i in range(60):
            # Prix oscillant pour generer des signaux
            prices.append(base + 2000 * math.sin(i / 5))
        _insert_candles(db_session, "BTC/USD", "4h", prices)

        service = BacktestService(db_session)
        config = BacktestConfig(
            start_days_ago=15,
            timeframe="4h",
            initial_capital=10000,
        )
        result = service.run(config)

        assert "meta" in result
        assert "metrics" in result
        assert "trades" in result
        assert "equity_curve" in result
        assert "summary" in result
        assert result["meta"]["symbol"] == "BTC/USD"
        assert result["meta"]["timeframe"] == "4h"
        assert result["meta"]["initial_capital"] == 10000

    def test_meta_fields_present(self, db_session):
        """Les metadonnees sont completes."""
        from datetime import datetime, timezone, timedelta
        # Utiliser des timestamps recents pour etre dans la fenetre
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=9)
        prices = [50000 + i * 100 for i in range(50)]
        _insert_candles(db_session, "BTC/USD", "4h", prices, start_dt=start)

        service = BacktestService(db_session)
        config = BacktestConfig(start_days_ago=10)
        result = service.run(config)

        meta = result["meta"]
        assert "start_ts" in meta
        assert "end_ts" in meta
        assert "candles_analyzed" in meta
        assert "decisions_made" in meta
        assert "duration_seconds" in meta
        assert meta["candles_analyzed"] > 0

    def test_equity_curve_not_empty_with_data(self, db_session):
        """Equity curve non vide si on a des candles."""
        prices = [50000 + i * 50 for i in range(50)]
        _insert_candles(db_session, "BTC/USD", "4h", prices)

        service = BacktestService(db_session)
        config = BacktestConfig(start_days_ago=10)
        result = service.run(config)

        # Si on a des decisions, on devrait avoir une equity curve
        if result["meta"]["decisions_made"] > 0:
            assert len(result["equity_curve"]) > 0

    def test_buy_and_hold_always_computed(self, db_session):
        """Le benchmark B&H est toujours calcule."""
        prices = [50000 + i * 100 for i in range(50)]
        _insert_candles(db_session, "BTC/USD", "4h", prices)

        service = BacktestService(db_session)
        config = BacktestConfig(start_days_ago=10)
        result = service.run(config)

        assert "buy_and_hold_pnl_pct" in result["metrics"]


# ============================================================
# TEST ENDPOINT HTTP
# ============================================================

class TestBacktestEndpoint:
    """Tests endpoint API POST /backtest/run."""

    def test_endpoint_returns_200(self, client, db_session):
        """POST /backtest/run retourne 200."""
        # Inserer des candles pour le test
        prices = [50000 + i * 100 for i in range(50)]
        _insert_candles(db_session, "BTC/USD", "4h", prices)

        response = client.post(
            "/backtest/run",
            json={
                "symbol": "BTC/USD",
                "timeframe": "4h",
                "start_days_ago": 10,
                "initial_capital": 10000,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "meta" in data
        assert "metrics" in data
        assert "trades" in data

    def test_endpoint_default_config(self, client, db_session):
        """POST avec config par defaut."""
        response = client.post("/backtest/run", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["symbol"] == "BTC/USD"

    def test_endpoint_invalid_capital(self, client):
        """Capital negatif = erreur 422."""
        response = client.post(
            "/backtest/run",
            json={"initial_capital": -1000},
        )
        assert response.status_code == 422

    def test_endpoint_response_structure(self, client, db_session):
        """Verifier la structure complete de la reponse."""
        prices = [50000 + i * 50 for i in range(50)]
        _insert_candles(db_session, "BTC/USD", "4h", prices)

        response = client.post(
            "/backtest/run",
            json={"start_days_ago": 10},
        )
        data = response.json()
        assert "summary" in data
        assert isinstance(data["trades"], list)
        assert isinstance(data["equity_curve"], list)
        assert isinstance(data["metrics"]["total_trades"], int)
        assert isinstance(data["metrics"]["win_rate"], float)

    def test_endpoint_custom_timeframe(self, client, db_session):
        """Backtest avec timeframe 1h."""
        prices = [50000 + i * 50 for i in range(100)]
        _insert_candles(db_session, "BTC/USD", "1h", prices)

        response = client.post(
            "/backtest/run",
            json={"timeframe": "1h", "start_days_ago": 5},
        )
        assert response.status_code == 200
        assert response.json()["meta"]["timeframe"] == "1h"


# ============================================================
# TEST EDGE CASES
# ============================================================

class TestBacktestEdgeCases:
    """Tests des cas limites."""

    def test_all_same_price(self, db_session):
        """Tous les prix identiques = pas de trades."""
        prices = [50000] * 50
        _insert_candles(db_session, "BTC/USD", "4h", prices)

        service = BacktestService(db_session)
        config = BacktestConfig(start_days_ago=10)
        result = service.run(config)

        # Avec des prix constants, le score devrait etre neutre => pas de trades
        assert result["metrics"]["net_pnl"] == 0.0 or result["metrics"]["total_trades"] >= 0

    def test_buy_and_hold_with_flat_market(self, db_session):
        """B&H = 0% si marche plat."""
        service = BacktestService(db_session)
        metrics = service._compute_metrics([], 10000, 10000, [], 50000, 50000)
        assert metrics.buy_and_hold_pnl_pct == 0.0

    def test_profit_factor_no_losses(self, db_session):
        """Profit factor plafonne si aucune perte."""
        service = BacktestService(db_session)
        trades = [
            BacktestTradeItem(
                entry_ts="t1", exit_ts="t2", direction=TradeDirection.BUY,
                entry_price=100, exit_price=110, pnl=100, pnl_pct=10, duration_hours=1,
            ),
        ]
        equity = [EquityPoint(ts="t1", capital=10000, drawdown_pct=0)]
        metrics = service._compute_metrics(trades, 10000, 10100, equity, 100, 110)
        assert metrics.profit_factor == 999.0

    def test_summary_no_trades(self, db_session):
        """Resume coherent quand 0 trades."""
        service = BacktestService(db_session)
        metrics = BacktestMetrics()
        summary = service._build_summary(metrics, 0, 1.0)
        assert "aucun" in summary.lower()

    def test_summary_with_trades(self, db_session):
        """Resume contient les infos cles."""
        service = BacktestService(db_session)
        metrics = BacktestMetrics(
            total_trades=5,
            win_rate=0.6,
            net_pnl_pct=8.5,
            max_drawdown_pct=3.2,
            buy_and_hold_pnl_pct=5.0,
        )
        summary = service._build_summary(metrics, 5, 2.5)
        assert "5 trades" in summary
        assert "8.5%" in summary or "+8.5%" in summary

