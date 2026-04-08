"""
Tests pour le modèle de coûts de trading, l'audit de vérité et la gate v2.0.

Ce fichier couvre :
- TradingCostModel (presets, calculs, round-trip)
- TruthAuditService (expectancy, drawdown, slots, profils, trailing, levier, verdict)
- V2GateService (readiness check, critères, status)
- Endpoints API (/audit/truth, /audit/costs, /v2/readiness)
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.trading_cost_service import (
    TradingCostModel, COST_OPTIMISTIC, COST_REALISTIC, COST_STRESSED,
    get_cost_model, COST_PRESETS,
)
from app.services.truth_audit_service import TruthAuditService
from app.services.v2_gate_service import V2GateService
from app.models.paper_account import PaperAccount, PaperTrade


# ================================================================
# TESTS : TradingCostModel
# ================================================================

class TestTradingCostModelPresets:
    """Tests des presets de coûts."""

    def test_optimistic_preset_exists(self):
        assert COST_OPTIMISTIC.name == "optimistic"
        assert COST_OPTIMISTIC.maker_fee_pct == 0.04
        assert COST_OPTIMISTIC.taker_fee_pct == 0.06

    def test_realistic_preset_exists(self):
        assert COST_REALISTIC.name == "realistic"
        assert COST_REALISTIC.maker_fee_pct == 0.10
        assert COST_REALISTIC.taker_fee_pct == 0.10

    def test_stressed_preset_exists(self):
        assert COST_STRESSED.name == "stressed"
        assert COST_STRESSED.spread_pct == 0.15
        assert COST_STRESSED.slippage_pct == 0.10

    def test_get_cost_model_default(self):
        model = get_cost_model()
        assert model.name == "realistic"

    def test_get_cost_model_by_name(self):
        model = get_cost_model("optimistic")
        assert model.name == "optimistic"

    def test_get_cost_model_unknown_returns_realistic(self):
        model = get_cost_model("unknown")
        assert model.name == "realistic"

    def test_presets_dict_has_all(self):
        assert "optimistic" in COST_PRESETS
        assert "realistic" in COST_PRESETS
        assert "stressed" in COST_PRESETS


class TestTradingCostModelCalculations:
    """Tests des calculs de coûts."""

    def test_entry_cost_pct(self):
        model = COST_REALISTIC
        # taker_fee + spread/2 + slippage = 0.10 + 0.025 + 0.03 = 0.155
        assert abs(model.entry_cost_pct() - 0.155) < 0.001

    def test_exit_cost_pct(self):
        model = COST_REALISTIC
        # maker_fee + spread/2 + slippage = 0.10 + 0.025 + 0.03 = 0.155
        assert abs(model.exit_cost_pct() - 0.155) < 0.001

    def test_round_trip_cost_pct(self):
        model = COST_REALISTIC
        # entry + exit = 0.155 + 0.155 = 0.31
        assert abs(model.round_trip_cost_pct() - 0.31) < 0.001

    def test_round_trip_cost_usd(self):
        model = COST_REALISTIC
        cost = model.round_trip_cost_usd(1000.0)
        # 1000 × 0.31% = 3.10
        assert abs(cost - 3.10) < 0.1

    def test_optimistic_cheaper_than_realistic(self):
        assert COST_OPTIMISTIC.round_trip_cost_pct() < COST_REALISTIC.round_trip_cost_pct()

    def test_realistic_cheaper_than_stressed(self):
        assert COST_REALISTIC.round_trip_cost_pct() < COST_STRESSED.round_trip_cost_pct()

    def test_stressed_cost_is_significant(self):
        # En stressed, un round-trip sur 1000 USD doit coûter > 5 USD
        cost = COST_STRESSED.round_trip_cost_usd(1000.0)
        assert cost > 5.0


class TestTradingCostModelApply:
    """Tests de l'application des coûts à un PnL."""

    def test_apply_to_pnl_positive(self):
        model = COST_REALISTIC
        result = model.apply_to_pnl(gross_pnl=10.0, position_size_usd=1000.0)
        assert result["gross_pnl"] == 10.0
        assert result["total_costs"] > 0
        assert result["net_pnl"] < 10.0
        assert result["net_pnl"] == result["gross_pnl"] - result["total_costs"]

    def test_apply_to_pnl_negative(self):
        model = COST_REALISTIC
        result = model.apply_to_pnl(gross_pnl=-5.0, position_size_usd=1000.0)
        assert result["net_pnl"] < -5.0  # Les coûts aggravent la perte

    def test_apply_to_pnl_with_leverage(self):
        model = COST_REALISTIC
        result_x1 = model.apply_to_pnl(10.0, 1000.0, leverage=1.0)
        result_x3 = model.apply_to_pnl(10.0, 1000.0, leverage=3.0)
        # Avec levier x3, les coûts sont 3× plus élevés
        assert result_x3["total_costs"] > result_x1["total_costs"] * 2.5

    def test_apply_to_pnl_zero_position(self):
        model = COST_REALISTIC
        result = model.apply_to_pnl(0, 0)
        assert result["total_costs"] == 0
        assert result["cost_drag_pct"] == 0

    def test_apply_to_trades_empty(self):
        model = COST_REALISTIC
        result = model.apply_to_trades([])
        assert result["total_trades"] == 0
        assert result["gross_pnl"] == 0

    def test_apply_to_trades_with_data(self):
        model = COST_REALISTIC
        trades = [
            {"pnl": 10.0, "position_size_usd": 1000.0, "leverage": 1.0},
            {"pnl": -5.0, "position_size_usd": 1000.0, "leverage": 1.0},
            {"pnl": 15.0, "position_size_usd": 1000.0, "leverage": 1.0},
        ]
        result = model.apply_to_trades(trades)
        assert result["total_trades"] == 3
        assert result["gross_pnl"] == 20.0
        assert result["total_costs"] > 0
        assert result["net_pnl"] < 20.0
        assert result["cost_model"] == "realistic"

    def test_apply_to_trades_win_rate_brut_vs_net(self):
        """Un trade marginalement positif peut devenir négatif après coûts."""
        model = COST_REALISTIC
        # Un trade avec 1.5 USD de gain brut sur 1000 USD
        # Round-trip cost ≈ 3.10 USD → net = -1.60 USD
        trades = [
            {"pnl": 1.5, "position_size_usd": 1000.0, "leverage": 1.0},
        ]
        result = model.apply_to_trades(trades)
        assert result["gross_win_rate"] == 100.0
        assert result["net_win_rate"] == 0.0  # Le trade est négatif après coûts

    def test_apply_to_trades_scalping_cost_impact(self):
        """En scalping, les coûts consomment une grande partie du PnL."""
        model = COST_REALISTIC
        # 50 trades de scalping, gain moyen 3 USD sur 1000 USD
        trades = [
            {"pnl": 3.0, "position_size_usd": 1000.0, "leverage": 1.0}
            for _ in range(50)
        ]
        result = model.apply_to_trades(trades)
        assert result["gross_pnl"] == 150.0
        assert result["total_costs"] > 100  # > 60% du gain
        assert result["net_pnl"] < result["gross_pnl"] * 0.5

    def test_profit_factor_calculation(self):
        model = COST_REALISTIC
        trades = [
            {"pnl": 20.0, "position_size_usd": 1000.0, "leverage": 1.0},
            {"pnl": -10.0, "position_size_usd": 1000.0, "leverage": 1.0},
        ]
        result = model.apply_to_trades(trades)
        assert result["gross_profit_factor"] == 2.0
        # Net PF devrait être inférieur car les coûts mangent les gains
        assert result["net_profit_factor"] < result["gross_profit_factor"]


# ================================================================
# TESTS : TruthAuditService
# ================================================================

class TestTruthAuditServiceEmpty:
    """Tests avec un compte vide."""

    def test_audit_no_account(self, db_session):
        service = TruthAuditService(db_session)
        result = service.run_audit()
        assert result["verdict"]["label"] == "NOT_READY"
        assert result["total_closed_trades"] == 0

    def test_audit_no_trades(self, db_session):
        account = PaperAccount(
            initial_capital=10000, current_capital=10000,
            peak_capital=10000, is_active=True,
        )
        db_session.add(account)
        db_session.commit()

        service = TruthAuditService(db_session)
        result = service.run_audit()
        assert result["verdict"]["label"] == "NOT_READY"


class TestTruthAuditServiceWithTrades:
    """Tests avec de vrais trades."""

    def _create_account_with_trades(self, db_session, trades_data):
        """Helper : crée un compte avec des trades fermés."""
        account = PaperAccount(
            initial_capital=10000, current_capital=10000,
            peak_capital=10000, is_active=True,
            max_drawdown_pct=0,
        )
        db_session.add(account)
        db_session.commit()

        now = datetime.now(timezone.utc)
        for i, td in enumerate(trades_data):
            trade = PaperTrade(
                account_id=account.id,
                status=td.get("status", "closed_signal"),
                direction=td.get("direction", "long"),
                entry_price=td.get("entry_price", 50000.0),
                exit_price=td.get("exit_price", 50100.0),
                stop_loss_price=49000.0,
                take_profit_price=51000.0,
                position_size_usd=td.get("position_size_usd", 1000.0),
                leverage=td.get("leverage", 1.0),
                effective_size_usd=td.get("position_size_usd", 1000.0) * td.get("leverage", 1.0),
                pnl=td.get("pnl", 0),
                pnl_pct=td.get("pnl_pct", 0),
                duration_hours=td.get("duration_hours", 1.0),
                slot=td.get("slot", None),
                profile_type=td.get("profile_type", None),
                entry_ts=now - timedelta(hours=2 * (len(trades_data) - i)),
                exit_ts=now - timedelta(hours=2 * (len(trades_data) - i) - 1),
                entry_reason="test",
                exit_reason="test",
            )
            db_session.add(trade)
            # Mettre à jour le capital du compte
            account.current_capital += td.get("pnl", 0)
            if account.current_capital > account.peak_capital:
                account.peak_capital = account.current_capital
            dd = (account.peak_capital - account.current_capital) / account.peak_capital * 100 if account.peak_capital > 0 else 0
            if dd > account.max_drawdown_pct:
                account.max_drawdown_pct = dd

        db_session.commit()
        return account

    def test_audit_with_profitable_trades(self, db_session):
        trades = [{"pnl": 10.0, "pnl_pct": 1.0}] * 10
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        assert result["total_closed_trades"] == 10
        assert result["cost_audit"]["primary"]["gross_pnl"] == 100.0
        assert result["cost_audit"]["primary"]["net_pnl"] < 100.0  # Net < brut
        assert result["expectancy_audit"]["gross_expectancy_per_trade"] > 0

    def test_audit_with_losing_trades(self, db_session):
        trades = [{"pnl": -10.0, "pnl_pct": -1.0}] * 10
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        assert result["expectancy_audit"]["net_expectancy_per_trade"] < 0
        assert result["verdict"]["label"] in ("DANGEROUS", "FRAGILE")

    def test_audit_with_mixed_trades(self, db_session):
        trades = [
            {"pnl": 20.0, "pnl_pct": 2.0},
            {"pnl": -5.0, "pnl_pct": -0.5},
            {"pnl": 15.0, "pnl_pct": 1.5},
            {"pnl": -3.0, "pnl_pct": -0.3},
            {"pnl": 10.0, "pnl_pct": 1.0},
        ]
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        assert result["total_closed_trades"] == 5
        assert "primary" in result["cost_audit"]
        assert "all_presets" in result["cost_audit"]
        assert "optimistic" in result["cost_audit"]["all_presets"]

    def test_audit_drawdown_coherent(self, db_session):
        """Le drawdown recalculé doit être cohérent avec le stocké."""
        trades = [
            {"pnl": -50.0, "pnl_pct": -5.0},
            {"pnl": -30.0, "pnl_pct": -3.0},
            {"pnl": 100.0, "pnl_pct": 10.0},
        ]
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        dd = result["drawdown_audit"]
        assert dd["gross_max_drawdown_pct"] > 0
        assert dd["net_max_drawdown_pct"] >= dd["gross_max_drawdown_pct"]

    def test_audit_by_slot(self, db_session):
        trades = [
            {"pnl": 10.0, "slot": "balanced"},
            {"pnl": -5.0, "slot": "scalping"},
            {"pnl": 20.0, "slot": "balanced"},
            {"pnl": -2.0, "slot": "scalping"},
        ]
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        slots = result["slot_audit"]
        assert "balanced" in slots
        assert "scalping" in slots
        assert slots["balanced"]["count"] == 2
        assert slots["scalping"]["count"] == 2

    def test_audit_by_profile(self, db_session):
        trades = [
            {"pnl": 10.0, "profile_type": "conservative"},
            {"pnl": 5.0, "profile_type": "auto→balanced"},
            {"pnl": -3.0, "profile_type": "auto→scalping"},
        ]
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        profiles = result["profile_audit"]
        assert "conservative" in profiles
        # auto→xxx doit être normalisé en "auto"
        assert "auto" in profiles

    def test_audit_trailing_stop_used(self, db_session):
        trades = [
            {"pnl": 5.0, "status": "closed_trailing_stop"},
            {"pnl": 3.0, "status": "closed_trailing_stop"},
            {"pnl": -2.0, "status": "closed_signal"},
            {"pnl": 10.0, "status": "closed_tp"},
        ]
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        ts = result["trailing_stop_audit"]
        assert ts["trailing_used"] is True
        assert ts["trailing_count"] == 2

    def test_audit_trailing_stop_not_used(self, db_session):
        trades = [{"pnl": 10.0, "status": "closed_tp"}] * 5
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        ts = result["trailing_stop_audit"]
        assert ts["trailing_used"] is False

    def test_audit_leverage_used(self, db_session):
        trades = [
            {"pnl": 20.0, "leverage": 2.0},
            {"pnl": -5.0, "leverage": 2.0},
            {"pnl": 10.0, "leverage": 1.0},
        ]
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        lev = result["leverage_audit"]
        assert lev["leverage_used"] is True
        assert lev["leveraged_count"] == 2
        assert lev["avg_leverage"] == 2.0

    def test_audit_leverage_not_used(self, db_session):
        trades = [{"pnl": 10.0, "leverage": 1.0}] * 5
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        lev = result["leverage_audit"]
        assert lev["leverage_used"] is False

    def test_verdict_dangerous(self, db_session):
        """Trades perdants → verdict DANGEROUS ou FRAGILE."""
        trades = [{"pnl": -20.0, "pnl_pct": -2.0}] * 20
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        assert result["verdict"]["label"] in ("DANGEROUS", "FRAGILE")
        assert result["verdict"]["score"] < 50

    def test_verdict_solid(self, db_session):
        """50+ trades rentables → verdict potentiellement SOLID ou VIABLE."""
        trades = [{"pnl": 15.0, "pnl_pct": 1.5}] * 55
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        assert result["verdict"]["label"] in ("SOLID", "VIABLE")
        assert result["verdict"]["score"] >= 50

    def test_cost_warning_when_costs_exceed_gains(self, db_session):
        """Avertissement si les coûts dépassent les gains bruts."""
        # Trades de scalping avec gains très faibles
        trades = [{"pnl": 1.0, "pnl_pct": 0.1, "position_size_usd": 1000.0}] * 5
        self._create_account_with_trades(db_session, trades)

        service = TruthAuditService(db_session)
        result = service.run_audit()

        warning = result["cost_audit"].get("warning")
        assert warning is not None  # Doit y avoir un avertissement


# ================================================================
# TESTS : V2GateService
# ================================================================

class TestV2GateService:
    """Tests du service de gate v2.0."""

    def test_gate_no_account(self, db_session):
        service = V2GateService(db_session)
        result = service.check_readiness()
        assert result["status"] == "NOT_READY"

    def test_gate_not_enough_trades(self, db_session):
        account = PaperAccount(
            initial_capital=10000, current_capital=10000,
            peak_capital=10000, is_active=True, max_drawdown_pct=0,
        )
        db_session.add(account)
        db_session.commit()

        # Ajouter seulement 5 trades
        now = datetime.now(timezone.utc)
        for i in range(5):
            trade = PaperTrade(
                account_id=account.id, status="closed_signal",
                direction="long", entry_price=50000, exit_price=50100,
                stop_loss_price=49000, take_profit_price=51000,
                position_size_usd=1000, pnl=10, pnl_pct=1.0,
                duration_hours=1.0,
                entry_ts=now - timedelta(hours=i),
                exit_ts=now - timedelta(hours=i) + timedelta(minutes=30),
                entry_reason="test", exit_reason="test",
            )
            db_session.add(trade)
        db_session.commit()

        service = V2GateService(db_session)
        result = service.check_readiness()
        assert result["status"] in ("NOT_READY", "PARTIAL")
        # Le critère "nombre minimum de trades" ne passe pas
        trades_criterion = [c for c in result["criteria"] if "trades" in c["name"].lower()][0]
        assert trades_criterion["passed"] is False

    def test_gate_has_criteria(self, db_session):
        account = PaperAccount(
            initial_capital=10000, current_capital=10000,
            peak_capital=10000, is_active=True, max_drawdown_pct=0,
        )
        db_session.add(account)
        db_session.commit()

        service = V2GateService(db_session)
        result = service.check_readiness()
        assert "criteria" in result
        assert len(result["criteria"]) == 8  # 8 critères
        assert "blocking_reasons" in result
        assert "recommendation" in result

    def test_gate_recommendation_present(self, db_session):
        account = PaperAccount(
            initial_capital=10000, current_capital=10000,
            peak_capital=10000, is_active=True, max_drawdown_pct=0,
        )
        db_session.add(account)
        db_session.commit()

        service = V2GateService(db_session)
        result = service.check_readiness()
        assert len(result["recommendation"]) > 0


# ================================================================
# TESTS : Endpoints API
# ================================================================

class TestAuditEndpoints:
    """Tests des endpoints API d'audit."""

    def test_get_truth_audit_empty(self, client):
        resp = client.get("/audit/truth")
        assert resp.status_code == 200
        data = resp.json()
        assert "verdict" in data

    def test_get_truth_audit_with_preset(self, client):
        resp = client.get("/audit/truth?cost_preset=optimistic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cost_model_used"] == "optimistic"

    def test_get_cost_presets(self, client):
        resp = client.get("/audit/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert "presets" in data
        assert len(data["presets"]) == 3
        names = [p["name"] for p in data["presets"]]
        assert "optimistic" in names
        assert "realistic" in names
        assert "stressed" in names

    def test_get_cost_presets_has_fields(self, client):
        resp = client.get("/audit/costs")
        data = resp.json()
        preset = data["presets"][0]
        assert "maker_fee_pct" in preset
        assert "taker_fee_pct" in preset
        assert "spread_pct" in preset
        assert "slippage_pct" in preset
        assert "round_trip_cost_pct" in preset

    def test_get_v2_readiness(self, client):
        resp = client.get("/v2/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("READY", "PARTIAL", "NOT_READY")
        assert "criteria" in data
        assert "blocking_reasons" in data
        assert "recommendation" in data

    def test_v2_readiness_not_ready_by_default(self, client):
        resp = client.get("/v2/readiness")
        data = resp.json()
        assert data["status"] == "NOT_READY"

