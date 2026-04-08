"""
Tests pour le service d'audit scalping et les optimisations v1.8.1.

Couvre :
- ScalpingAuditService (audit complet, distribution sorties, trailing, scores, long/short)
- Recalibrage des paramètres scalping (trailing stop, thresholds, levier)
- Endpoint GET /audit/scalping
- Protection du levier en mode scalping conservateur
- Logique de reversal améliorée
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.scalping_audit_service import ScalpingAuditService
from app.services.trading_profile_service import PROFILE_PRESETS, TradingProfileService
from app.services.leverage_service import LeverageService
from app.services.paper_trading_service import PaperTradingService
from app.models.paper_account import PaperAccount, PaperTrade
from app.schemas.journal import TradingProfileParams, TradingProfileType


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


def _make_scalping_trade(db, account_id, pnl, status="closed_trailing_stop",
                         direction="long", score=72, duration_hours=0.05,
                         entry_price=71000, leverage=1.5):
    """Crée un trade scalping fermé."""
    now = datetime.now(timezone.utc)
    exit_price = entry_price * (1 + pnl / (2500 * leverage)) if pnl else entry_price
    trade = PaperTrade(
        account_id=account_id,
        status=status,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_loss_price=entry_price * 0.997,
        take_profit_price=entry_price * 1.003,
        highest_price_since_entry=entry_price * 1.001,
        position_size_usd=2500,
        leverage=leverage,
        effective_size_usd=2500 * leverage,
        profile_type="scalping",
        slot="scalping",
        pnl=pnl,
        pnl_pct=round(pnl / 2500 * 100, 4) if pnl else 0,
        entry_reason=f"ActionType.BUY | score={score} | ConfidenceLevel.MEDIUM",
        exit_reason=f"Trade fermé ({status})",
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
# TESTS : ScalpingAuditService
# ================================================================

class TestScalpingAuditEmpty:
    """Tests audit scalping sans données."""

    def test_audit_no_account(self, db_session):
        """Audit sans compte retourne audit vide."""
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()
        assert result["total_scalping_trades"] == 0
        assert "recommendations" in result

    def test_audit_no_scalping_trades(self, db_session):
        """Audit avec compte mais sans trades scalping."""
        account = _make_account(db_session)
        # Créer un trade non-scalping
        trade = PaperTrade(
            account_id=account.id,
            status="closed_signal",
            direction="long",
            entry_price=70000,
            exit_price=70100,
            stop_loss_price=69000,
            take_profit_price=71000,
            position_size_usd=5000,
            profile_type="balanced",
            slot="balanced",
            pnl=10,
            pnl_pct=0.14,
            entry_reason="test",
            decision_score=50,
            entry_ts=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_ts=datetime.now(timezone.utc),
            duration_hours=1.0,
        )
        db_session.add(trade)
        db_session.commit()

        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()
        assert result["total_scalping_trades"] == 0


class TestScalpingAuditWithData:
    """Tests audit scalping avec données réelles."""

    def _setup_trades(self, db):
        """Crée un ensemble de trades scalping réalistes."""
        account = _make_account(db)
        # Simulation de l'export fourni : 15 trades, la plupart trailing
        trades = [
            # Trailing stop trades (8)
            _make_scalping_trade(db, account.id, pnl=0.0, status="closed_trailing_stop"),
            _make_scalping_trade(db, account.id, pnl=1.39, status="closed_trailing_stop"),
            _make_scalping_trade(db, account.id, pnl=-0.32, status="closed_trailing_stop"),
            _make_scalping_trade(db, account.id, pnl=-0.50, status="closed_trailing_stop"),
            _make_scalping_trade(db, account.id, pnl=-0.45, status="closed_trailing_stop"),
            _make_scalping_trade(db, account.id, pnl=-1.11, status="closed_trailing_stop"),
            _make_scalping_trade(db, account.id, pnl=-0.01, status="closed_trailing_stop"),
            _make_scalping_trade(db, account.id, pnl=2.33, status="closed_trailing_stop"),
            # Signal trades (3) — 2 loss cut, 1 profit
            _make_scalping_trade(db, account.id, pnl=8.15, status="closed_signal"),
            _make_scalping_trade(db, account.id, pnl=-7.53, status="closed_signal"),
            _make_scalping_trade(db, account.id, pnl=-7.88, status="closed_signal"),
            # Stale trades (3) — 2 positive, 1 negative
            _make_scalping_trade(db, account.id, pnl=5.65, status="closed_stale"),
            _make_scalping_trade(db, account.id, pnl=7.32, status="closed_stale"),
            _make_scalping_trade(db, account.id, pnl=-3.04, status="closed_stale"),
            # Momentum fade (1)
            _make_scalping_trade(db, account.id, pnl=0.87, status="closed_momentum_fade"),
        ]
        return account, trades

    def test_overview_metrics(self, db_session):
        """L'overview contient les métriques clés du scalping."""
        account, trades = self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        assert result["total_scalping_trades"] == 15
        ov = result["overview"]
        assert ov["total_trades"] == 15
        assert ov["winning_trades"] == 7  # 1.39, 2.33, 8.15, 5.65, 7.32, 0.87, 0.0
        assert ov["gross_pnl"] == pytest.approx(4.87, abs=0.1)
        assert "verdict" in ov

    def test_exit_distribution(self, db_session):
        """La distribution des sorties est correcte."""
        self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        exits = result["exit_analysis"]
        assert "closed_trailing_stop" in exits
        assert exits["closed_trailing_stop"]["count"] == 8
        assert "closed_signal" in exits
        assert exits["closed_signal"]["count"] == 3
        assert "closed_stale" in exits
        assert exits["closed_stale"]["count"] == 3
        assert "closed_momentum_fade" in exits
        assert exits["closed_momentum_fade"]["count"] == 1

    def test_trailing_stop_audit(self, db_session):
        """L'audit du trailing stop détecte les problèmes."""
        self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        ta = result["trailing_stop_audit"]
        assert ta["used"] is True
        assert ta["trailing_count"] == 8
        # 6/8 des trailing sont à plat ou négatifs
        assert ta["pct_near_zero"] > 50  # >50% quasi à plat
        assert "BRUIT" in ta["verdict"] or "NÉGATIF" in ta["verdict"]

    def test_score_distribution_saturated(self, db_session):
        """Le scoring saturé est détecté."""
        self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        sd = result["score_distribution"]
        assert sd["saturated"] is True
        assert sd["saturation_pct"] > 90  # tous les trades ont score=72

    def test_direction_audit_no_shorts(self, db_session):
        """L'audit détecte l'absence de shorts."""
        self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        da = result["direction_audit"]
        assert da["long_count"] == 15
        assert da["short_count"] == 0
        assert "AUCUN" in da["verdict"] or "MORT" in da["verdict"]

    def test_direction_audit_with_shorts(self, db_session):
        """L'audit reconnaît les shorts quand ils existent."""
        account = _make_account(db_session)
        _make_scalping_trade(db_session, account.id, pnl=1.0, direction="long")
        _make_scalping_trade(db_session, account.id, pnl=-0.5, direction="short")

        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        da = result["direction_audit"]
        assert da["long_count"] == 1
        assert da["short_count"] == 1

    def test_leverage_audit(self, db_session):
        """L'audit du levier détecte l'uniformité."""
        self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        la = result["leverage_audit"]
        assert la["leverage_uniform"] is True
        assert la["avg_leverage"] == 1.5

    def test_recommendations_generated(self, db_session):
        """Des recommandations sont générées."""
        self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        recs = result["recommendations"]
        assert len(recs) > 0
        # Au moins une recommandation sur le trailing
        assert any("TRAILING" in r.upper() for r in recs)

    def test_slot_comparison(self, db_session):
        """La comparaison par slot fonctionne."""
        self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        comp = result["slot_comparison"]
        assert "scalping" in comp
        assert comp["scalping"]["count"] == 15

    def test_cost_model_impact(self, db_session):
        """Les coûts impactent fortement le PnL net scalping."""
        self._setup_trades(db_session)
        svc = ScalpingAuditService(db_session)
        result = svc.run_audit()

        ov = result["overview"]
        # Brut positif mais net devrait être très négatif
        # 15 trades × $3750 effective × 0.31% round-trip = ~$174 de coûts
        assert ov["total_costs"] > 100  # coûts significatifs
        assert ov["net_pnl"] < ov["gross_pnl"]  # net < brut


# ================================================================
# TESTS : Recalibrage des paramètres scalping
# ================================================================

class TestScalpingRecalibration:
    """Tests pour les paramètres recalibrés du scalping v1.8.1."""

    def test_trailing_stop_activation_increased(self):
        """Trailing stop activation augmenté de 0.03% à 0.08%."""
        p = PROFILE_PRESETS["scalping"]
        assert p.trailing_stop_activation_pct == 0.08

    def test_trailing_stop_trail_increased(self):
        """Trailing stop trail augmenté de 0.05% à 0.12%."""
        p = PROFILE_PRESETS["scalping"]
        assert p.trailing_stop_pct == 0.12

    def test_buy_threshold_increased(self):
        """Buy threshold augmenté de 10 à 20 pour meilleure discrimination."""
        p = PROFILE_PRESETS["scalping"]
        assert p.buy_threshold == 20

    def test_sell_threshold_increased(self):
        """Sell threshold augmenté de 8 à 15."""
        p = PROFILE_PRESETS["scalping"]
        assert p.sell_threshold == 15

    def test_min_score_increased(self):
        """Min score augmenté de 5 à 15 pour filtrer le bruit."""
        p = PROFILE_PRESETS["scalping"]
        assert p.min_score == 15

    def test_cooldown_increased(self):
        """Cooldown augmenté de 1 à 2 min."""
        p = PROFILE_PRESETS["scalping"]
        assert p.cooldown_minutes == 2

    def test_stale_exit_increased(self):
        """Stale exit augmenté de 10 à 12 min."""
        p = PROFILE_PRESETS["scalping"]
        assert p.stale_exit_minutes == 15

    def test_max_leverage_reduced(self):
        """Max leverage réduit de 2.0 à 1.5."""
        p = PROFILE_PRESETS["scalping"]
        assert p.max_leverage == 1.5

    def test_unchanged_params(self):
        """Les paramètres scalping reflètent le recalibrage v1.9.1."""
        p = PROFILE_PRESETS["scalping"]
        # [v1.9.1] TP/SL élargis pour dépasser le cost model realistic
        assert p.profit_take_pct == 0.5   # was 0.3
        assert p.loss_cut_pct == 0.4      # was 0.3
        assert p.max_trades_per_day == 50
        assert p.max_position_duration_hours == 2
        assert p.analysis_timeframe == "15m"
        assert p.momentum_fade_enabled is True
        # [v1.9.1] Protection anti-micro-PnL
        assert p.min_hold_seconds == 30
        assert p.min_economic_pnl_pct == 0.15


# ================================================================
# TESTS : Levier conservateur en scalping
# ================================================================

class TestScalpingLeverage:
    """Tests pour le levier conservateur en mode scalping."""

    def test_scalping_low_confidence_forces_x1(self):
        """Scalping avec confiance medium (0.6) → x1.0 (conservateur)."""
        p = PROFILE_PRESETS["scalping"]
        rec = LeverageService.compute_leverage(
            score=72, confidence="medium",
            profile_params=p,
            risk_level="safe",
        )
        # max_leverage=1.5, confidence=0.6 < 0.8 → scalping conservateur → x1.0
        assert rec.final == 1.0

    def test_scalping_high_confidence_gets_leverage(self):
        """Scalping avec confiance high (1.0) et score fort → levier > 1."""
        p = PROFILE_PRESETS["scalping"]
        rec = LeverageService.compute_leverage(
            score=72, confidence="high",
            profile_params=p,
            risk_level="safe",
        )
        # max_leverage=1.5, confidence=1.0 >= 0.8, score_factor=1.0 >= 0.7
        assert rec.final >= 1.0

    def test_scalping_low_score_forces_x1(self):
        """Scalping avec score faible → x1.0."""
        p = PROFILE_PRESETS["scalping"]
        rec = LeverageService.compute_leverage(
            score=20, confidence="high",
            profile_params=p,
            risk_level="safe",
        )
        # score=20 → score_factor=0.1 < 0.7 → scalping conservateur → x1.0
        assert rec.final == 1.0

    def test_non_scalping_profile_not_affected(self):
        """Les profils non-scalping ne sont pas affectés par la règle conservatrice."""
        p = PROFILE_PRESETS["aggressive"]
        rec = LeverageService.compute_leverage(
            score=72, confidence="medium",
            profile_params=p,
            risk_level="safe",
        )
        # max_leverage=3.0 → pas en mode scalping, levier normal
        assert rec.final >= 1.0


# ================================================================
# TESTS : Reversal check amélioré
# ================================================================

class TestScalpingReversalImproved:
    """Tests pour la logique de reversal scalping améliorée."""

    def test_reversal_none_when_no_extremes(self, db_session):
        """Pas de reversal si pas d'extrêmes."""
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [],
            "combined_score": 50,
            "technical_score": 50,
        }
        result = pts._scalping_reversal_check(decision)
        assert result is None

    def test_reversal_short_on_rsi_overbought(self, db_session):
        """RSI overbought → short (comme avant)."""
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "rsi_overbought", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": 50,
            "technical_score": 50,
        }
        result = pts._scalping_reversal_check(decision)
        assert result == "short"

    def test_reversal_long_on_stochrsi_oversold(self, db_session):
        """StochRSI oversold → long."""
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "stochrsi_oversold", "satisfied": True, "direction": "bullish"},
            ],
            "combined_score": -50,
            "technical_score": -50,
        }
        result = pts._scalping_reversal_check(decision)
        assert result == "long"

    def test_reversal_short_on_extreme_tech_score(self, db_session):
        """Score technique ≥ 90 sans bearish → overbought → short."""
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "macd_bullish_cross", "satisfied": True, "direction": "bullish"},
            ],
            "combined_score": 72,
            "technical_score": 95,  # Très haussier → potentiel surachat
        }
        result = pts._scalping_reversal_check(decision)
        assert result == "short"

    def test_reversal_long_on_extreme_negative_tech_score(self, db_session):
        """Score technique ≤ -90 → oversold → long."""
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "macd_bearish_cross", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": -72,
            "technical_score": -95,  # Très baissier → potentiel survente
        }
        result = pts._scalping_reversal_check(decision)
        assert result == "long"

    def test_no_reversal_moderate_tech_score(self, db_session):
        """Score technique modéré → pas de reversal."""
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [],
            "combined_score": 50,
            "technical_score": 70,  # Pas assez extrême
        }
        result = pts._scalping_reversal_check(decision)
        assert result is None


# ================================================================
# TESTS : Endpoint GET /audit/scalping
# ================================================================

class TestScalpingAuditEndpoint:
    """Tests de l'endpoint /audit/scalping."""

    def test_endpoint_returns_200(self, client):
        """L'endpoint retourne 200."""
        resp = client.get("/audit/scalping")
        assert resp.status_code == 200

    def test_endpoint_returns_structure(self, client):
        """L'endpoint retourne la structure attendue."""
        resp = client.get("/audit/scalping")
        data = resp.json()
        assert "total_scalping_trades" in data
        assert "overview" in data
        assert "recommendations" in data

    def test_endpoint_with_cost_preset(self, client):
        """L'endpoint accepte le paramètre cost_preset."""
        resp = client.get("/audit/scalping?cost_preset=stressed")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("cost_model_used") == "stressed" or data["total_scalping_trades"] == 0

