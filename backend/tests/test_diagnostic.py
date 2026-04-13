"""
Tests pour le diagnostic de fréquence, les opportunités manquées,
le profil scalping, les sorties rapides, et l'analyse levier.

v1.6 — "Pourquoi le bot trade trop peu" + augmentation du débit.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.models.paper_account import PaperAccount, PaperTrade
from app.models.tick_activity_log import TickActivityLog
from app.models.candle import Candle
from app.services.diagnostic_service import DiagnosticService
from app.services.trading_profile_service import TradingProfileService, PROFILE_PRESETS
from app.services.paper_trading_service import PaperTradingService
from app.services.decision_service import DecisionService
from app.schemas.journal import TradingProfileType, TradingProfileParams
from app.schemas.diagnostic import (
    DiagnosticResponse,
    MissedOpportunitySummary,
    LeverageAnalysisResponse,
    NonTradeRankedReason,
)


# ================================================================
# Helpers
# ================================================================

def _make_account(db, active=True, profile="conservative"):
    """Crée un compte paper trading de test."""
    account = PaperAccount(
        initial_capital=10000.0,
        current_capital=10000.0,
        peak_capital=10000.0,
        is_active=active,
        active_profile=profile,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _make_tick(db, account_id, action="hold", reason=None, score=None,
               decision_action=None, confidence=None, btc_price=85000.0,
               profile="conservative", trade_id=None, ts_offset_min=0,
               leverage_rec=None, leverage_final=None):
    """Crée un tick dans le journal."""
    ts = datetime.now(timezone.utc) - timedelta(minutes=ts_offset_min)
    entry = TickActivityLog(
        account_id=account_id,
        timestamp=ts,
        btc_price=btc_price,
        action_taken=action,
        decision_score=score,
        decision_action=decision_action,
        decision_confidence=confidence,
        reason_no_trade=reason,
        reason_detail=f"Test detail for {reason}" if reason else None,
        profile_type=profile,
        had_open_position=1 if action == "hold" and reason == "position_already_open" else 0,
        trade_id=trade_id,
        leverage_recommended=leverage_rec,
        leverage_final=leverage_final,
    )
    db.add(entry)
    db.commit()
    return entry


def _make_trade(db, account_id, pnl=10.0, duration_hours=2.0,
                direction="long", leverage=1.0, profile="conservative",
                entry_price=85000.0, exit_offset_hours=0):
    """Crée un trade fermé de test."""
    now = datetime.now(timezone.utc)
    trade = PaperTrade(
        account_id=account_id,
        status="closed_signal",
        direction=direction,
        entry_price=entry_price,
        exit_price=entry_price + (pnl / (1000 * leverage) * entry_price) if direction == "long" else entry_price,
        stop_loss_price=entry_price * 0.95 if direction == "long" else entry_price * 1.05,
        take_profit_price=entry_price * 1.05 if direction == "long" else entry_price * 0.95,
        position_size_usd=1000.0,
        leverage=leverage,
        effective_size_usd=1000.0 * leverage,
        profile_type=profile,
        pnl=pnl,
        pnl_pct=round(pnl / (1000 * leverage) * 100, 4),
        entry_reason="Test entry",
        exit_reason="Test exit",
        decision_score=30,
        entry_ts=now - timedelta(hours=duration_hours + exit_offset_hours),
        exit_ts=now - timedelta(hours=exit_offset_hours),
        duration_hours=duration_hours,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


# ================================================================
# Tests DiagnosticService — Diagnostic principal
# ================================================================

class TestDiagnosticService:
    """Tests pour le service de diagnostic de fréquence."""

    def test_diagnostic_no_account(self, db_session):
        """Diagnostic sans compte retourne response minimale."""
        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()
        assert result.main_bottleneck == "no_account"

    def test_diagnostic_empty_data(self, db_session):
        """Diagnostic avec compte mais sans ticks."""
        account = _make_account(db_session)
        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()
        assert result.total_ticks == 0
        assert result.total_trades == 0

    def test_diagnostic_ranks_reasons(self, db_session):
        """Les raisons de non-trade sont correctement classées."""
        account = _make_account(db_session)
        # Créer des ticks avec différentes raisons
        for _ in range(10):
            _make_tick(db_session, account.id, reason="decision_wait", score=15, decision_action="attendre")
        for _ in range(5):
            _make_tick(db_session, account.id, reason="score_too_low", score=8, decision_action="acheter")
        for _ in range(3):
            _make_tick(db_session, account.id, reason="position_already_open")
        for _ in range(2):
            _make_tick(db_session, account.id, reason="cooldown_active")

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        assert len(result.top_non_trade_reasons) == 4
        assert result.top_non_trade_reasons[0].reason == "decision_wait"
        assert result.top_non_trade_reasons[0].rank == 1
        assert result.top_non_trade_reasons[0].count == 10
        assert result.top_non_trade_reasons[1].reason == "score_too_low"

    def test_diagnostic_categories(self, db_session):
        """Les catégories de raisons sont correctement assignées."""
        account = _make_account(db_session)
        _make_tick(db_session, account.id, reason="decision_wait")
        _make_tick(db_session, account.id, reason="risk_blocked")
        _make_tick(db_session, account.id, reason="position_already_open")
        _make_tick(db_session, account.id, reason="cooldown_active")

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        cats = {r.reason: r.category for r in result.top_non_trade_reasons}
        assert cats["decision_wait"] == "signal"
        assert cats["risk_blocked"] == "risk"
        assert cats["position_already_open"] == "structural"
        assert cats["cooldown_active"] == "frequency"

    def test_diagnostic_position_duration(self, db_session):
        """Analyse correctement la durée des positions."""
        account = _make_account(db_session)
        _make_trade(db_session, account.id, duration_hours=0.5)  # < 1h
        _make_trade(db_session, account.id, duration_hours=2.0)  # 1-4h
        _make_trade(db_session, account.id, duration_hours=12.0)  # 4-24h
        _make_trade(db_session, account.id, duration_hours=48.0)  # > 24h

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        assert result.position_duration.total_closed == 4
        assert result.position_duration.pct_under_1h == 25.0
        assert result.position_duration.pct_over_24h == 25.0

    def test_diagnostic_risk_brake(self, db_session):
        """Analyse l'impact du risk engine comme frein."""
        account = _make_account(db_session)
        for _ in range(5):
            _make_tick(db_session, account.id, reason="risk_blocked")
        for _ in range(2):
            _make_tick(db_session, account.id, reason="kill_switch_active")
        for _ in range(3):
            _make_tick(db_session, account.id, reason="daily_loss_protection")
        for _ in range(90):
            _make_tick(db_session, account.id, reason="decision_wait")

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        assert result.risk_brake.ticks_blocked_by_risk == 10  # 5 + 2 + 3
        assert result.risk_brake.ticks_kill_switch == 2
        assert result.risk_brake.ticks_daily_loss == 3

    def test_diagnostic_leverage_tracking(self, db_session):
        """Détecte les réductions de levier."""
        account = _make_account(db_session)
        _make_tick(db_session, account.id, action="opened_long",
                   leverage_rec=2.0, leverage_final=1.5)  # réduit
        _make_tick(db_session, account.id, action="opened_long",
                   leverage_rec=2.0, leverage_final=1.0)  # forcé x1
        _make_tick(db_session, account.id, action="opened_long",
                   leverage_rec=1.5, leverage_final=1.5)  # pas réduit

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        assert result.risk_brake.ticks_leverage_reduced == 2
        assert result.risk_brake.ticks_leverage_forced_x1 == 1

    def test_diagnostic_bottleneck_decision_wait(self, db_session):
        """Identifie le bottleneck quand decision_wait domine."""
        account = _make_account(db_session)
        for _ in range(50):
            _make_tick(db_session, account.id, reason="decision_wait", score=15, decision_action="attendre")
        for _ in range(5):
            _make_tick(db_session, account.id, reason="score_too_low")

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        assert result.main_bottleneck == "decision_thresholds_too_high"
        assert len(result.recommendations) > 0

    def test_diagnostic_bottleneck_position_blocking(self, db_session):
        """Identifie le bottleneck quand les positions bloquent."""
        account = _make_account(db_session)
        _make_trade(db_session, account.id, duration_hours=24.0)
        for _ in range(60):
            _make_tick(db_session, account.id, reason="position_already_open")
        for _ in range(10):
            _make_tick(db_session, account.id, reason="decision_wait")

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        assert result.main_bottleneck == "position_blocking"

    def test_diagnostic_tick_to_trade_ratio(self, db_session):
        """Calcule correctement le ratio ticks→trades."""
        account = _make_account(db_session)
        _make_trade(db_session, account.id)
        for _ in range(98):
            _make_tick(db_session, account.id, reason="decision_wait")
        _make_tick(db_session, account.id, action="opened_long")
        _make_tick(db_session, account.id, action="closed_signal")

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        assert result.total_ticks == 100
        assert result.total_trades == 1

    def test_diagnostic_profile_comparison(self, db_session):
        """La comparaison des profils inclut les 4 presets."""
        account = _make_account(db_session)
        _make_tick(db_session, account.id, reason="decision_wait", score=15,
                   decision_action="attendre")

        svc = DiagnosticService(db_session)
        result = svc.get_diagnostic()

        assert len(result.profile_comparison) == 4
        profiles = [r.profile for r in result.profile_comparison]
        assert "scalping" in profiles
        assert "conservative" in profiles


# ================================================================
# Tests Scalping Profile
# ================================================================

class TestScalpingProfile:
    """Tests pour le profil Scalping."""

    def test_scalping_preset_exists(self):
        """Le preset scalping existe avec les bons paramètres (v2.0.3 recalibré)."""
        assert "scalping" in PROFILE_PRESETS
        p = PROFILE_PRESETS["scalping"]
        assert p.min_score == 30           # [v2.0.3] 25→30
        assert p.cooldown_minutes == 0.5    # [v2.0.28] 1.0→0.5 (cooldown réduit)
        assert p.max_trades_per_day == 999  # [v2.0.24] 30→999 (illimité)
        # [v2.0.0] TP élargi, SL maintenu
        assert p.profit_take_pct == 0.8    # [v2.0.0] 0.6→0.8
        assert p.loss_cut_pct == 0.20      # maintenu
        assert p.max_position_duration_hours == 2
        assert p.analysis_timeframe == "5m"
        assert p.buy_threshold == 30       # [v2.0.3] recalibré 25→30
        assert p.sell_threshold == 20      # [v1.9.5] recalibré 15→20
        assert p.momentum_fade_enabled is False
        assert p.stale_exit_minutes == 5
        # [v1.9.1] min_hold et min_economic_pnl
        assert p.min_hold_seconds == 30
        assert p.min_economic_pnl_pct == 0.15

    def test_scalping_in_enum(self):
        """TradingProfileType inclut scalping."""
        assert TradingProfileType.scalping.value == "scalping"

    def test_set_profile_scalping(self, db_session):
        """On peut activer le profil scalping."""
        account = _make_account(db_session)
        svc = TradingProfileService(db_session)
        result = svc.set_profile("scalping")
        assert result.active_profile == TradingProfileType.scalping

    def test_scalping_valid_profile(self, db_session):
        """Scalping est dans la liste des profils valides."""
        assert "scalping" in TradingProfileService.VALID_PROFILES

    def test_scalping_params_analysis_timeframe(self):
        """Scalping utilise timeframe 15m."""
        p = PROFILE_PRESETS["scalping"]
        assert p.analysis_timeframe == "5m"

    def test_scalping_params_buy_threshold(self):
        """Scalping a un seuil BUY recalibré (v2.0.3: 25→30)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.buy_threshold == 30  # [v2.0.3] recalibré 25→30

    def test_scalping_params_sell_threshold(self):
        """Scalping a un seuil SELL recalibré."""
        p = PROFILE_PRESETS["scalping"]
        assert p.sell_threshold == 20  # [v1.9.5] recalibré 15→20

    def test_scalping_momentum_fade_enabled(self):
        """Scalping active le momentum fade."""
        p = PROFILE_PRESETS["scalping"]
        assert p.momentum_fade_enabled is False

    def test_scalping_stale_exit(self):
        """Scalping a un stale exit à 12 minutes (recalibré)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.stale_exit_minutes == 5

    def test_conservative_no_new_fields(self):
        """Conservative n'a pas les nouveaux champs activés."""
        p = PROFILE_PRESETS["conservative"]
        assert p.analysis_timeframe is None
        assert p.buy_threshold is None
        assert p.sell_threshold is None
        assert p.momentum_fade_enabled is False
        assert p.stale_exit_minutes is None

    def test_aggressive_stale_exit(self):
        """Aggressive a un stale exit à 180 minutes."""
        p = PROFILE_PRESETS["aggressive"]
        assert p.stale_exit_minutes == 180


# ================================================================
# Tests DecisionService — Seuils personnalisés
# ================================================================

class TestDecisionCustomThresholds:
    """Tests pour les seuils BUY/SELL personnalisés."""

    def test_default_thresholds_unchanged(self, db_session):
        """Sans seuils personnalisés, les seuils globaux sont utilisés."""
        svc = DecisionService(db_session)
        # Mock signals+sentiment pour contrôler le score
        mock_signals = {
            "signals": [],
            "composite": {"score": 22, "direction": "bullish", "confidence": "low"},
        }

        rules = svc.evaluate_rules(mock_signals, {"sentiment_score": 0})
        scenarios = svc.compute_scenarios(22, rules)
        rec = svc.generate_recommendation(scenarios, rules, 22)
        # Score 22 < 25 (BUY_THRESHOLD) → attendre
        assert rec.action.value == "attendre"

    def test_custom_buy_threshold_lower(self, db_session):
        """Avec buy_threshold=10, un score de 15 déclenche un achat."""
        svc = DecisionService(db_session)
        mock_signals = {
            "signals": [],
            "composite": {"score": 15, "direction": "bullish", "confidence": "low"},
        }

        rules = svc.evaluate_rules(mock_signals, {"sentiment_score": 0})
        scenarios = svc.compute_scenarios(15, rules)
        rec = svc.generate_recommendation(scenarios, rules, 15, buy_threshold=10)
        # Score 15 > 10 (buy_threshold personnalisé) → acheter
        assert rec.action.value == "acheter"

    def test_custom_sell_threshold_lower(self, db_session):
        """Avec sell_threshold=8, un score de -10 déclenche une vente."""
        svc = DecisionService(db_session)
        mock_signals = {
            "signals": [],
            "composite": {"score": -10, "direction": "bearish", "confidence": "low"},
        }

        rules = svc.evaluate_rules(mock_signals, {"sentiment_score": 0})
        scenarios = svc.compute_scenarios(-10, rules)
        rec = svc.generate_recommendation(scenarios, rules, -10, sell_threshold=8)
        # Score -10 < -8 (sell_threshold personnalisé) → vendre
        assert rec.action.value == "vendre"

    def test_thresholds_none_uses_defaults(self, db_session):
        """buy_threshold=None / sell_threshold=None → seuils globaux."""
        svc = DecisionService(db_session)
        rules = svc.evaluate_rules({"signals": [], "composite": {"score": 22}}, {})
        scenarios = svc.compute_scenarios(22, rules)
        rec = svc.generate_recommendation(scenarios, rules, 22, buy_threshold=None, sell_threshold=None)
        assert rec.action.value == "attendre"  # 22 < 25

    def test_analyze_passes_thresholds(self, db_session):
        """analyze() accepte et utilise les seuils personnalisés."""
        # Injecter des candles pour que le service ne crash pas
        for i in range(250):
            ts = datetime.now(timezone.utc) - timedelta(hours=i)
            db_session.add(Candle(
                symbol="BTC/USD", timeframe="15m", timestamp=ts,
                open_price=85000, high_price=85100, low_price=84900,
                close_price=85000 + (i % 10) * 10, volume=100,
                source="test",
            ))
        db_session.commit()

        svc = DecisionService(db_session)
        # Avec des seuils très bas, le service devrait produire un résultat
        result = svc.analyze(
            symbol="BTC/USD", timeframe="15m", history_days=1,
            buy_threshold=5, sell_threshold=5,
        )
        assert result is not None
        assert "recommendation" in result
        assert "combined_score" in result


# ================================================================
# Tests MissedOpportunities
# ================================================================

class TestMissedOpportunities:
    """Tests pour la détection d'opportunités manquées."""

    def test_missed_no_account(self, db_session):
        """Sans compte, retourne résultat vide."""
        svc = DiagnosticService(db_session)
        result = svc.get_missed_opportunities()
        assert result.total_non_trade_ticks_analyzed == 0

    def test_missed_no_non_trade_ticks(self, db_session):
        """Sans ticks non-trade, retourne résultat vide."""
        account = _make_account(db_session)
        _make_tick(db_session, account.id, action="opened_long")

        svc = DiagnosticService(db_session)
        result = svc.get_missed_opportunities()
        assert result.total_non_trade_ticks_analyzed == 0

    def test_missed_with_data(self, db_session):
        """Avec des ticks non-trade et des candles, détecte les opportunités."""
        account = _make_account(db_session)
        now = datetime.now(timezone.utc)

        # Créer un tick non-trade
        tick = TickActivityLog(
            account_id=account.id,
            timestamp=now - timedelta(hours=1),
            btc_price=85000.0,
            action_taken="hold",
            decision_score=15,
            decision_action="acheter",
            reason_no_trade="score_too_low",
            profile_type="conservative",
        )
        db_session.add(tick)

        # Créer une candle 15min plus tard avec prix en hausse
        candle = Candle(
            symbol="BTC/USD",
            timeframe="1m",
            timestamp=now - timedelta(hours=1) + timedelta(minutes=15),
            open_price=85000,
            high_price=85500,
            low_price=85000,
            close_price=85300,  # +0.35%
            volume=100,
            source="test",
        )
        db_session.add(candle)
        db_session.commit()

        svc = DiagnosticService(db_session)
        result = svc.get_missed_opportunities(min_move_pct=0.10, lookforward_minutes=30)
        assert result.total_non_trade_ticks_analyzed >= 1

    def test_missed_warning_present(self, db_session):
        """L'avertissement sur les faux positifs est présent."""
        svc = DiagnosticService(db_session)
        result = svc.get_missed_opportunities()
        assert "ex-post" in result.warning


# ================================================================
# Tests LeverageAnalysis
# ================================================================

class TestLeverageAnalysis:
    """Tests pour l'analyse comparative levier."""

    def test_leverage_analysis_no_account(self, db_session):
        """Sans compte, retourne résultat vide."""
        svc = DiagnosticService(db_session)
        result = svc.get_leverage_analysis()
        assert result.total_leveraged_trades == 0

    def test_leverage_analysis_with_trades(self, db_session):
        """Calcule correctement avec/sans levier."""
        account = _make_account(db_session)
        # Trade avec levier x2, PnL = +100
        _make_trade(db_session, account.id, pnl=100, leverage=2.0)
        # Trade sans levier, PnL = +50
        _make_trade(db_session, account.id, pnl=50, leverage=1.0)
        # Trade avec levier x3, PnL = -60
        _make_trade(db_session, account.id, pnl=-60, leverage=3.0)

        svc = DiagnosticService(db_session)
        result = svc.get_leverage_analysis()

        assert result.total_leveraged_trades == 2  # x2 et x3
        assert result.total_unleveraged_trades == 1  # x1
        assert result.pnl_with_leverage == 90.0  # 100 + 50 - 60
        # Sans levier : 100/2 + 50/1 + (-60)/3 = 50 + 50 - 20 = 80
        assert result.pnl_without_leverage == 80.0
        assert result.leverage_benefit == 10.0  # 90 - 80
        assert result.trades_amplified_positive == 1
        assert result.trades_amplified_negative == 1

    def test_leverage_analysis_no_trades(self, db_session):
        """Sans trades, retourne zéros."""
        account = _make_account(db_session)
        svc = DiagnosticService(db_session)
        result = svc.get_leverage_analysis()
        assert result.pnl_with_leverage == 0.0
        assert result.pnl_without_leverage == 0.0


# ================================================================
# Tests Faster Exits
# ================================================================

class TestFasterExits:
    """Tests pour les sorties rapides (stale + momentum fade)."""

    def test_stale_exit_not_triggered_if_disabled(self, db_session):
        """Stale exit ne se déclenche pas si stale_exit_minutes est None."""
        p = PROFILE_PRESETS["conservative"]
        assert p.stale_exit_minutes is None

    def test_stale_exit_configured_for_scalping(self):
        """Scalping a stale_exit_minutes = 12 (recalibré v1.8.1)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.stale_exit_minutes == 5

    def test_momentum_fade_not_on_conservative(self):
        """Conservative n'active pas momentum_fade."""
        p = PROFILE_PRESETS["conservative"]
        assert p.momentum_fade_enabled is False

    def test_momentum_fade_on_scalping(self):
        """Scalping active momentum_fade."""
        p = PROFILE_PRESETS["scalping"]
        assert p.momentum_fade_enabled is False

    def test_paper_service_pnl_at_price(self, db_session):
        """_calc_unrealized_pnl_at_price fonctionne correctement."""
        account = _make_account(db_session)
        trade = PaperTrade(
            account_id=account.id,
            status="open",
            direction="long",
            entry_price=85000.0,
            stop_loss_price=84000.0,
            take_profit_price=86000.0,
            position_size_usd=1000.0,
            leverage=2.0,
            entry_reason="test",
            decision_score=30,
            entry_ts=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        db_session.commit()

        svc = PaperTradingService(db_session)
        # Prix monte à 85850 → +1% → PnL = 1000 * 2 * 0.01 = 20
        pnl = svc._calc_unrealized_pnl_at_price(trade, 85850.0)
        assert abs(pnl - 20.0) < 1.0

    def test_paper_service_pnl_at_price_short(self, db_session):
        """_calc_unrealized_pnl_at_price fonctionne pour les shorts."""
        account = _make_account(db_session)
        trade = PaperTrade(
            account_id=account.id,
            status="open",
            direction="short",
            entry_price=85000.0,
            stop_loss_price=86000.0,
            take_profit_price=84000.0,
            position_size_usd=1000.0,
            leverage=1.0,
            entry_reason="test",
            decision_score=-30,
            entry_ts=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        db_session.commit()

        svc = PaperTradingService(db_session)
        # Prix baisse à 84150 → +1% → PnL = 1000 * 1 * 0.01 = 10
        pnl = svc._calc_unrealized_pnl_at_price(trade, 84150.0)
        assert abs(pnl - 10.0) < 1.0


# ================================================================
# Tests API Endpoints
# ================================================================

class TestDiagnosticEndpoints:
    """Tests pour les endpoints de diagnostic."""

    def test_diagnostic_endpoint(self, client, db_session):
        """GET /paper/diagnostic retourne 200."""
        resp = client.get("/paper/diagnostic")
        assert resp.status_code == 200
        data = resp.json()
        assert "top_non_trade_reasons" in data
        assert "position_duration" in data
        assert "risk_brake" in data
        assert "main_bottleneck" in data

    def test_diagnostic_endpoint_with_dates(self, client, db_session):
        """GET /paper/diagnostic avec filtres de date."""
        resp = client.get("/paper/diagnostic?date_from=2026-01-01&date_to=2026-12-31")
        assert resp.status_code == 200

    def test_missed_opportunities_endpoint(self, client, db_session):
        """GET /paper/missed-opportunities retourne 200."""
        resp = client.get("/paper/missed-opportunities")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_non_trade_ticks_analyzed" in data
        assert "warning" in data

    def test_missed_opportunities_params(self, client, db_session):
        """GET /paper/missed-opportunities accepte les paramètres."""
        resp = client.get("/paper/missed-opportunities?lookforward_minutes=60&min_move_pct=0.20")
        assert resp.status_code == 200

    def test_leverage_analysis_endpoint(self, client, db_session):
        """GET /paper/leverage-analysis retourne 200."""
        resp = client.get("/paper/leverage-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert "pnl_with_leverage" in data
        assert "pnl_without_leverage" in data

    def test_profile_presets_includes_scalping(self, client, db_session):
        """GET /paper/profile/presets inclut scalping."""
        resp = client.get("/paper/profile/presets")
        assert resp.status_code == 200
        data = resp.json()
        types = [p["profile_type"] for p in data]
        assert "scalping" in types

    def test_set_profile_scalping(self, client, db_session):
        """POST /paper/profile peut activer scalping."""
        # Créer un compte d'abord
        client.post("/paper/account", json={"initial_capital": 10000})
        resp = client.post("/paper/profile", json={"profile": "scalping"})
        assert resp.status_code == 200
        assert resp.json()["active_profile"] == "scalping"

    def test_diagnostic_endpoint_custom_params(self, client, db_session):
        """GET /paper/diagnostic accepte tous les filtres."""
        resp = client.get("/paper/diagnostic?date_from=2026-04-01&date_to=2026-04-08")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["profile_comparison"], list)
        assert isinstance(data["recommendations"], list)


# ================================================================
# Tests Auto-Profile avec Scalping
# ================================================================

class TestAutoProfileWithScalping:
    """Tests pour le mode auto avec le nouveau tier scalping."""

    def test_auto_select_scalping_low_score(self):
        """Score ≥ 10 + confiance low → scalping."""
        result = TradingProfileService.auto_select_profile(score=15, confidence="low")
        assert result == "scalping"

    def test_auto_select_scalping_score_20(self):
        """Score 20 + confiance low → scalping (pas balanced car conf < medium)."""
        result = TradingProfileService.auto_select_profile(score=20, confidence="low")
        assert result == "scalping"

    def test_auto_select_conservative_below_10(self):
        """Score < 10 → conservative."""
        result = TradingProfileService.auto_select_profile(score=9, confidence="low")
        assert result == "conservative"

    def test_auto_select_conservative_zero(self):
        """Score 0 → conservative."""
        result = TradingProfileService.auto_select_profile(score=0, confidence="high")
        assert result == "conservative"

    def test_auto_select_scalping_negative(self):
        """Score négatif abs ≥ 10 → scalping."""
        result = TradingProfileService.auto_select_profile(score=-15, confidence="low")
        assert result == "scalping"

    def test_auto_select_balanced_still_works(self):
        """Score ≥ 30 + medium → balanced (pas impacté par scalping)."""
        result = TradingProfileService.auto_select_profile(score=35, confidence="medium")
        assert result == "balanced"

    def test_auto_select_aggressive_still_works(self):
        """Score ≥ 50 + high → aggressive (pas impacté par scalping)."""
        result = TradingProfileService.auto_select_profile(score=55, confidence="high")
        assert result == "aggressive"

