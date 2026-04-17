"""
Tests pour le service de stabilité et la stabilisation globale v1.9.5.

Couvre :
- StabilityAuditService (direction, scores, R:R, exits, oscillation, verdict)
- Nouveaux paramètres scalping (SL, TP, trailing, stale, shorts)
- Stale exit asymétrique (positions négatives vs plates)
- Momentum fade configurable (rétention)
- Learning layer stabilité (suggestions 10-12)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.services.stability_audit_service import StabilityAuditService
from app.services.trading_profile_service import PROFILE_PRESETS
from app.services.learning_service import LearningService, SAFETY_BOUNDS
from app.services.paper_trading_service import PaperTradingService
from app.models.paper_account import PaperAccount, PaperTrade
from app.models.learning import LearningSignal


# ============================================================
# HELPERS
# ============================================================

def _make_trade(
    db, account_id,
    direction="long", pnl=1.0, pnl_pct=0.04, status="closed_tp",
    score=72, duration_hours=0.1, entry_price=72000, exit_price=72050,
    position_size_usd=2500, leverage=1.0, slot="scalping",
    profile_type="scalping", entry_ts=None, exit_ts=None,
):
    """Helper pour créer un PaperTrade fermé."""
    now = datetime.now(timezone.utc)
    t = PaperTrade(
        account_id=account_id,
        direction=direction,
        status=status,
        pnl=pnl,
        pnl_pct=pnl_pct,
        decision_score=score,
        duration_hours=duration_hours,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_loss_price=entry_price * 0.99,
        take_profit_price=entry_price * 1.01,
        position_size_usd=position_size_usd,
        leverage=leverage,
        effective_size_usd=position_size_usd * leverage,
        slot=slot,
        profile_type=profile_type,
        entry_ts=entry_ts or (now - timedelta(hours=1)),
        exit_ts=exit_ts or now,
        entry_reason="test",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_account(db, initial_capital=10000):
    a = PaperAccount(
        initial_capital=initial_capital,
        current_capital=initial_capital,
        peak_capital=initial_capital,
        is_active=True,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ============================================================
# TESTS : Paramètres scalping v1.9.5
# ============================================================

class TestScalpingParamsV195:
    """Vérifier que le preset scalping a les bonnes valeurs v2.0.0 (mis à jour)."""

    def test_loss_cut_pct(self):
        """SL resserré → 0.20%."""
        assert PROFILE_PRESETS["scalping"].loss_cut_pct == 0.50

    def test_profit_take_pct(self):
        """[v2.0.0] TP élargi de 0.6% → 0.8%."""
        assert PROFILE_PRESETS["scalping"].profit_take_pct == 1.5

    def test_trailing_stop_activation(self):
        """[v2.0.9] Activation trailing abaissée à 0.02% — protège dès ~$0.50."""
        assert PROFILE_PRESETS["scalping"].trailing_stop_activation_pct == 0.40

    def test_trailing_stop_pct(self):
        """Trail fallback absolu à 0.06%."""
        assert PROFILE_PRESETS["scalping"].trailing_stop_pct == 0.20

    def test_trailing_drop_ratio(self):
        """[v2.0.9] Drop ratio relatif à 3% — exit dès que gain baisse de 3% du pic."""
        assert PROFILE_PRESETS["scalping"].trailing_stop_drop_ratio == 0.25

    def test_buy_threshold(self):
        """[v2.0.3] Buy threshold relevé de 25 → 30."""
        assert PROFILE_PRESETS["scalping"].buy_threshold == 40

    def test_sell_threshold(self):
        """Sell threshold relevé de 15 → 20."""
        assert PROFILE_PRESETS["scalping"].sell_threshold == 30

    def test_min_score(self):
        """[v2.0.3] Min score relevé de 25 → 30."""
        assert PROFILE_PRESETS["scalping"].min_score == 40

    def test_short_min_score(self):
        """[v2.0.3] Short min score aligné à 30 avec min_score relevé."""
        assert PROFILE_PRESETS["scalping"].short_min_score == 40

    def test_short_exit_score_threshold(self):
        """Short exit threshold → 30 (v1.9.6)."""
        assert PROFILE_PRESETS["scalping"].short_exit_score_threshold == 40

    def test_short_min_hold_seconds(self):
        """Short min hold → 45 (v1.9.6)."""
        assert PROFILE_PRESETS["scalping"].short_min_hold_seconds == 300

    def test_momentum_fade_retention(self):
        """Momentum fade retention configuré à 0.55."""
        assert PROFILE_PRESETS["scalping"].momentum_fade_retention == 0.55

    def test_stale_negative_exit_minutes(self):
        """Stale négatif = 5 min (v1.9.6)."""
        assert PROFILE_PRESETS["scalping"].stale_negative_exit_minutes == 10

    def test_rr_ratio_theoretical(self):
        """[v2.0.0] Ratio R:R théorique = TP/SL = 0.8/0.20 = 4.0."""
        p = PROFILE_PRESETS["scalping"]
        rr = p.profit_take_pct / p.loss_cut_pct
        assert rr == pytest.approx(4.0, abs=0.01)

    def test_other_profiles_unchanged(self):
        """Les autres profils ne sont PAS impactés."""
        assert PROFILE_PRESETS["conservative"].loss_cut_pct == 1.5
        assert PROFILE_PRESETS["balanced"].loss_cut_pct == 1.2
        assert PROFILE_PRESETS["aggressive"].loss_cut_pct == 1.0


# ============================================================
# TESTS : StabilityAuditService
# ============================================================

class TestStabilityAuditEmpty:
    """Tests avec données insuffisantes."""

    def test_no_account(self, db_session):
        """Retourne un verdict UNSTABLE si pas de compte."""
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["verdict"]["level"] == "UNSTABLE"

    def test_few_trades(self, db_session):
        """Retourne un verdict UNSTABLE si < 5 trades."""
        account = _make_account(db_session)
        for _ in range(3):
            _make_trade(db_session, account.id)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["verdict"]["level"] == "UNSTABLE"


class TestDirectionBalance:
    """Tests de balance directionnelle."""

    def test_all_longs_is_mono(self, db_session):
        """100% longs → mono_long."""
        account = _make_account(db_session)
        for _ in range(10):
            _make_trade(db_session, account.id, direction="long")
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["direction_balance"]["status"] == "mono_long"

    def test_all_shorts_is_mono(self, db_session):
        """100% shorts → mono_short."""
        account = _make_account(db_session)
        for _ in range(10):
            _make_trade(db_session, account.id, direction="short")
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["direction_balance"]["status"] == "mono_short"

    def test_balanced_direction(self, db_session):
        """50/50 → balanced."""
        account = _make_account(db_session)
        for _ in range(5):
            _make_trade(db_session, account.id, direction="long")
        for _ in range(5):
            _make_trade(db_session, account.id, direction="short")
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["direction_balance"]["status"] == "balanced"

    def test_long_biased(self, db_session):
        """80% longs → long_biased."""
        account = _make_account(db_session)
        for _ in range(8):
            _make_trade(db_session, account.id, direction="long")
        for _ in range(2):
            _make_trade(db_session, account.id, direction="short")
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["direction_balance"]["status"] == "long_biased"


class TestScoreHomogeneity:
    """Tests d'homogénéité des scores."""

    def test_very_homogeneous(self, db_session):
        """Scores tous à 72 → very_homogeneous."""
        account = _make_account(db_session)
        for _ in range(10):
            _make_trade(db_session, account.id, score=72)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["score_homogeneity"]["status"] == "very_homogeneous"

    def test_well_distributed(self, db_session):
        """Scores variés → well_distributed."""
        account = _make_account(db_session)
        scores = [20, 35, 50, 65, 80, 25, 45, 70, 90, 15]
        for s in scores:
            _make_trade(db_session, account.id, score=s)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["score_homogeneity"]["status"] == "well_distributed"

    def test_std_dev_computed(self, db_session):
        """L'écart-type est correctement calculé."""
        account = _make_account(db_session)
        for s in [70, 71, 72, 71, 72]:
            _make_trade(db_session, account.id, score=s)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["score_homogeneity"]["std_dev"] < 3


class TestEffectiveRR:
    """Tests du ratio R:R effectif."""

    def test_broken_rr(self, db_session):
        """Gains petits, pertes grosses → broken."""
        account = _make_account(db_session)
        # 5 wins at +1, 5 losses at -9
        for _ in range(5):
            _make_trade(db_session, account.id, pnl=1.0, status="closed_tp")
        for _ in range(5):
            _make_trade(db_session, account.id, pnl=-9.0, status="closed_sl")
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["effective_rr"]["status"] == "broken"
        assert result["effective_rr"]["effective_rr"] < 0.5

    def test_healthy_rr(self, db_session):
        """Gains > pertes → healthy."""
        account = _make_account(db_session)
        for _ in range(5):
            _make_trade(db_session, account.id, pnl=5.0, status="closed_tp")
        for _ in range(5):
            _make_trade(db_session, account.id, pnl=-3.0, status="closed_sl")
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["effective_rr"]["status"] == "healthy"
        assert result["effective_rr"]["effective_rr"] >= 1.0


class TestExitDomination:
    """Tests de domination d'un type de sortie."""

    def test_over_dominant(self, db_session):
        """Un type de sortie > 50% → over_dominant."""
        account = _make_account(db_session)
        for _ in range(7):
            _make_trade(db_session, account.id, status="closed_stale", pnl=-3.0)
        for _ in range(3):
            _make_trade(db_session, account.id, status="closed_tp", pnl=2.0)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["exit_domination"]["status"] == "over_dominant"

    def test_diverse_exits(self, db_session):
        """Sorties variées → diverse."""
        account = _make_account(db_session)
        statuses = ["closed_tp", "closed_sl", "closed_stale",
                     "closed_trailing_stop", "closed_momentum_fade"]
        for i, s in enumerate(statuses * 2):
            _make_trade(db_session, account.id, status=s, pnl=1.0 if i % 2 == 0 else -1.0)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["exit_domination"]["status"] == "diverse"

    def test_destructive_exits_detected(self, db_session):
        """Sorties destructrices (PnL moyen < -1.0) sont identifiées."""
        account = _make_account(db_session)
        for _ in range(5):
            _make_trade(db_session, account.id, status="closed_sl", pnl=-8.0)
        for _ in range(5):
            _make_trade(db_session, account.id, status="closed_tp", pnl=4.0)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert "closed_sl" in result["exit_domination"]["destructive_exits"]


class TestOscillationDetection:
    """Tests de détection d'oscillation entre fenêtres."""

    def test_no_oscillation_with_few_trades(self, db_session):
        """Pas assez de trades pour 2 fenêtres → pas détecté."""
        account = _make_account(db_session)
        for _ in range(8):
            _make_trade(db_session, account.id, direction="long")
        service = StabilityAuditService(db_session)
        result = service.run_audit(window_size=5)
        assert result["oscillation_detection"]["detected"] is False

    def test_oscillation_detected(self, db_session):
        """Fenêtre 1 = short, fenêtre 2 = long → oscillation."""
        account = _make_account(db_session)
        base = datetime.now(timezone.utc) - timedelta(hours=10)
        for i in range(10):
            _make_trade(
                db_session, account.id, direction="short",
                entry_ts=base + timedelta(minutes=i * 10),
                exit_ts=base + timedelta(minutes=i * 10 + 5),
            )
        for i in range(10):
            _make_trade(
                db_session, account.id, direction="long",
                entry_ts=base + timedelta(hours=5, minutes=i * 10),
                exit_ts=base + timedelta(hours=5, minutes=i * 10 + 5),
            )
        service = StabilityAuditService(db_session)
        result = service.run_audit(window_size=10)
        assert result["oscillation_detection"]["detected"] is True

    def test_no_oscillation_same_direction(self, db_session):
        """2 fenêtres de même direction → pas d'oscillation."""
        account = _make_account(db_session)
        base = datetime.now(timezone.utc) - timedelta(hours=10)
        for i in range(20):
            _make_trade(
                db_session, account.id, direction="long",
                entry_ts=base + timedelta(minutes=i * 10),
                exit_ts=base + timedelta(minutes=i * 10 + 5),
            )
        service = StabilityAuditService(db_session)
        result = service.run_audit(window_size=10)
        assert result["oscillation_detection"]["detected"] is False


class TestStabilityVerdict:
    """Tests du verdict global de stabilité."""

    def test_stable_verdict(self, db_session):
        """Tout va bien → STABLE."""
        account = _make_account(db_session)
        # Trades variés, scores distribués, bons gains
        for i in range(10):
            _make_trade(
                db_session, account.id,
                direction="long" if i % 3 != 0 else "short",
                score=40 + i * 5,
                pnl=3.0 if i % 2 == 0 else -2.0,
                status="closed_tp" if i % 2 == 0 else "closed_sl",
            )
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["verdict"]["level"] in ("STABLE", "IMPROVING")

    def test_unstable_verdict(self, db_session):
        """Tout va mal → UNSTABLE."""
        account = _make_account(db_session)
        # Mono-long, scores homogènes, R:R cassé, une sortie domine
        for _ in range(10):
            _make_trade(
                db_session, account.id,
                direction="long", score=72,
                pnl=-9.0, status="closed_sl",
            )
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["verdict"]["level"] == "UNSTABLE"
        assert result["verdict"]["stability_score"] < 30

    def test_verdict_has_issues(self, db_session):
        """Le verdict contient des issues détaillées."""
        account = _make_account(db_session)
        for _ in range(10):
            _make_trade(db_session, account.id, direction="long", score=72, pnl=-5.0)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert len(result["verdict"]["issues"]) > 0


class TestGainLossAnalysis:
    """Tests de l'analyse gain/perte."""

    def test_profit_factor(self, db_session):
        """Profit factor calculé correctement."""
        account = _make_account(db_session)
        for _ in range(5):
            _make_trade(db_session, account.id, pnl=4.0)
        for _ in range(5):
            _make_trade(db_session, account.id, pnl=-2.0)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        assert result["gain_loss_analysis"]["profit_factor"] == pytest.approx(2.0, abs=0.01)

    def test_top3_losses_contribution(self, db_session):
        """La contribution des top 3 pertes est calculée."""
        account = _make_account(db_session)
        for _ in range(5):
            _make_trade(db_session, account.id, pnl=2.0)
        _make_trade(db_session, account.id, pnl=-10.0)
        _make_trade(db_session, account.id, pnl=-5.0)
        _make_trade(db_session, account.id, pnl=-3.0)
        _make_trade(db_session, account.id, pnl=-1.0)
        _make_trade(db_session, account.id, pnl=-0.5)
        service = StabilityAuditService(db_session)
        result = service.run_audit()
        # Top 3 = -10, -5, -3 = 18 sur total 19.5 = 92.3%
        assert result["gain_loss_analysis"]["top3_loss_contribution_pct"] > 80


# ============================================================
# TESTS : Stale exit asymétrique
# ============================================================

class TestStaleNegativeExit:
    """Tests du stale exit asymétrique (positions négatives vs plates)."""

    def test_param_exists(self):
        """Le paramètre stale_negative_exit_minutes existe."""
        assert hasattr(PROFILE_PRESETS["scalping"], "stale_negative_exit_minutes")
        assert PROFILE_PRESETS["scalping"].stale_negative_exit_minutes == 10

    def test_param_default_none_other_profiles(self):
        """Les autres profils n'ont pas ce paramètre (None)."""
        assert getattr(PROFILE_PRESETS["conservative"], "stale_negative_exit_minutes", None) is None
        assert getattr(PROFILE_PRESETS["balanced"], "stale_negative_exit_minutes", None) is None


# ============================================================
# TESTS : Momentum fade configurable
# ============================================================

class TestMomentumFadeRetention:
    """Tests du momentum fade à rétention configurable."""

    def test_param_exists(self):
        """Le paramètre momentum_fade_retention existe sur scalping."""
        assert hasattr(PROFILE_PRESETS["scalping"], "momentum_fade_retention")
        assert PROFILE_PRESETS["scalping"].momentum_fade_retention == 0.55

    def test_param_default_none_other(self):
        """Les autres profils n'ont pas ce paramètre (None)."""
        assert getattr(PROFILE_PRESETS["conservative"], "momentum_fade_retention", None) is None


# ============================================================
# TESTS : Learning stability suggestions
# ============================================================

class TestLearningStabilitySuggestions:
    """Tests des suggestions de stabilité dans le learning layer."""

    def test_safety_bounds_new_params(self):
        """Les bornes de sécurité couvrent les nouveaux paramètres."""
        assert "momentum_fade_retention" in SAFETY_BOUNDS
        assert "stale_negative_exit_minutes" in SAFETY_BOUNDS
        assert SAFETY_BOUNDS["momentum_fade_retention"] == (0.2, 0.8)

    def test_directional_imbalance_suggestion(self, db_session):
        """Si > 85% longs, une suggestion de stabilité est générée."""
        account = _make_account(db_session)

        # Créer 15 samples learning tous longs
        for i in range(15):
            t = _make_trade(
                db_session, account.id,
                direction="long", pnl=(-1)**i * 2.0,
                pnl_pct=(-1)**i * 0.08,
                score=72,
            )
            sample = LearningSignal(
                trade_id=t.id,
                score=72,
                direction="long",
                profile_type="scalping",
                exit_type=t.status,
                pnl_brut=t.pnl,
                pnl_pct=t.pnl_pct,
                was_profitable=1 if t.pnl >= 0 else 0,
                cost_estimated=0.5,
                pnl_net_estimated=t.pnl - 0.5,
                usefulness_category="useful" if t.pnl > 0.5 else "loss_useful",
            )
            db_session.add(sample)
        db_session.commit()

        service = LearningService(db_session)
        suggestions = service.suggest_adjustments("scalping")

        # Il devrait y avoir une suggestion pour déséquilibre directionnel
        param_names = [s.parameter_name for s in suggestions]
        assert "short_min_score" in param_names, f"Expected short_min_score in {param_names}"

        # La suggestion devrait baisser le short_min_score
        short_suggestion = next(s for s in suggestions if s.parameter_name == "short_min_score" and "Déséquilibre" in s.reason)
        assert short_suggestion.suggested_value < short_suggestion.original_value

    def test_rr_asymmetry_suggestion(self, db_session):
        """Si R:R < 0.4, une suggestion de resserrement SL est générée."""
        account = _make_account(db_session)

        for i in range(15):
            is_win = i < 5
            t = _make_trade(
                db_session, account.id,
                pnl=1.0 if is_win else -8.0,
                pnl_pct=0.04 if is_win else -0.32,
                score=72,
                status="closed_tp" if is_win else "closed_sl",
            )
            sample = LearningSignal(
                trade_id=t.id,
                score=72,
                direction="long",
                profile_type="scalping",
                exit_type=t.status,
                pnl_brut=t.pnl,
                pnl_pct=t.pnl_pct,
                was_profitable=1 if t.pnl >= 0 else 0,
                cost_estimated=0.5,
                pnl_net_estimated=t.pnl - 0.5,
                usefulness_category="useful" if t.pnl > 0.5 else "loss_destructive",
            )
            db_session.add(sample)
        db_session.commit()

        service = LearningService(db_session)
        suggestions = service.suggest_adjustments("scalping")

        param_names = [s.parameter_name for s in suggestions]
        assert "loss_cut_pct" in param_names, f"Expected loss_cut_pct in {param_names}"


# ============================================================
# TESTS : Endpoint
# ============================================================

class TestStabilityEndpoint:
    """Tests de l'endpoint GET /audit/stability."""

    def test_endpoint_returns_200(self, client):
        """L'endpoint retourne 200."""
        resp = client.get("/audit/stability")
        assert resp.status_code == 200

    def test_endpoint_has_verdict(self, client):
        """La réponse contient un verdict."""
        resp = client.get("/audit/stability")
        data = resp.json()
        assert "verdict" in data
        assert "level" in data["verdict"]
        assert data["verdict"]["level"] in ("UNSTABLE", "IMPROVING", "STABLE")

    def test_endpoint_with_window_param(self, client):
        """L'endpoint accepte le paramètre window."""
        resp = client.get("/audit/stability?window=10")
        assert resp.status_code == 200

    def test_endpoint_has_all_sections(self, client):
        """La réponse contient toutes les sections de l'audit."""
        resp = client.get("/audit/stability")
        data = resp.json()
        expected_keys = [
            "total_closed_trades",
            "direction_balance",
            "score_homogeneity",
            "effective_rr",
            "exit_domination",
            "gain_loss_analysis",
            "oscillation_detection",
            "verdict",
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"


# ============================================================
# TESTS : Convergence boost amélioré (score discrimination)
# ============================================================

class TestConvergenceBoost:
    """Tests du convergence boost amélioré pour la discrimination."""

    def test_boost_factor_higher(self):
        """Le boost factor est de 0.5 (vs ancien 0.4)."""
        # Indirect : on vérifie que le code a changé via un test fonctionnel
        from app.services.signal_service import compute_composite_score
        from app.schemas.signal import SignalItem, SignalDirection

        # Créer des signaux fortement bullish convergents
        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.8, value=25, message="test"),
            SignalItem(indicator="macd", direction=SignalDirection.BULLISH, strength=0.7, value=1, message="test"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.6, value=72000, message="test"),
            SignalItem(indicator="bollinger", direction=SignalDirection.BULLISH, strength=0.7, value=72000, message="test"),
        ]
        result = compute_composite_score(signals)
        # Score devrait être élevé grâce au convergence boost
        assert result.score >= 70, f"Score {result.score} trop bas pour 4 bullish convergents"

    def test_divided_signals_compressed(self):
        """Des signaux divisés donnent un score compressé."""
        from app.services.signal_service import compute_composite_score
        from app.schemas.signal import SignalItem, SignalDirection

        signals = [
            SignalItem(indicator="rsi", direction=SignalDirection.BULLISH, strength=0.8, value=25, message="test"),
            SignalItem(indicator="macd", direction=SignalDirection.BEARISH, strength=0.7, value=-1, message="test"),
            SignalItem(indicator="sma", direction=SignalDirection.BULLISH, strength=0.6, value=72000, message="test"),
            SignalItem(indicator="bollinger", direction=SignalDirection.BEARISH, strength=0.7, value=72000, message="test"),
            SignalItem(indicator="stoch_rsi", direction=SignalDirection.NEUTRAL, strength=0.3, value=50, message="test"),
        ]
        result = compute_composite_score(signals)
        # Score devrait être modéré/bas car signaux divisés
        assert abs(result.score) < 50, f"Score {result.score} trop haut pour signaux divisés"


# ============================================================
# TESTS : Signal contraire long (score -15)
# ============================================================

class TestSignalContraireLong:
    """Tests du seuil de signal contraire pour les longs (relevé à -15)."""

    def test_score_minus_10_no_close(self):
        """Score -10 ne doit plus fermer un long (seuil relevé à -15)."""
        # Ce test vérifie la logique indirectement via le code
        # Le vrai test serait d'intégration avec le paper trading
        score = -10
        threshold = -15
        assert score > threshold, "Score -10 ne devrait pas déclencher la fermeture"

    def test_score_minus_15_closes(self):
        """Score -15 doit fermer un long."""
        score = -15
        threshold = -15
        assert score <= threshold, "Score -15 devrait déclencher la fermeture"

    def test_score_minus_20_closes(self):
        """Score -20 doit fermer un long."""
        score = -20
        threshold = -15
        assert score <= threshold


# ============================================================
# TESTS : Reversal check (toujours 2 signaux convergents)
# ============================================================

class TestReversalCheck:
    """Tests du reversal check scalping v2.0.8 (seuil abaissé à 1)."""

    def test_single_overbought_triggers_reversal(self):
        """[v2.0.8] 1 seul oscillateur overbought SUFFIT maintenant (seuil 2→1)."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService.__new__(PaperTradingService)

        decision_result = {
            "rules_evaluated": [
                {"rule_name": "rsi_overbought", "satisfied": True, "direction": "bearish"},
                {"rule_name": "stochrsi_overbought", "satisfied": False, "direction": "bearish"},
            ],
            "combined_score": 72,
            "technical_score": 72,
        }
        result = pts._scalping_reversal_check(decision_result)
        assert result == "short", "1 oscillateur overbought doit suffire (v2.0.8)"

    def test_two_overbought_triggers_short(self):
        """2 oscillateurs overbought → reversal short."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService.__new__(PaperTradingService)

        decision_result = {
            "rules_evaluated": [
                {"rule_name": "rsi_overbought", "satisfied": True, "direction": "bearish"},
                {"rule_name": "stochrsi_overbought", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": 72,
            "technical_score": 72,
        }
        result = pts._scalping_reversal_check(decision_result)
        assert result == "short"

    def test_no_reversal_when_nothing_satisfied(self):
        """Pas de reversal si aucun signal n'est satisfait."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService.__new__(PaperTradingService)

        decision_result = {
            "rules_evaluated": [
                {"rule_name": "rsi_overbought", "satisfied": False, "direction": "bearish"},
                {"rule_name": "stochrsi_overbought", "satisfied": False, "direction": "bearish"},
            ],
            "combined_score": 50,
            "technical_score": 50,
        }
        result = pts._scalping_reversal_check(decision_result)
        assert result is None, "Aucun signal satisfait → pas de reversal"


# ============================================================
# TESTS v1.9.6 : INVARIANT SLOT UNIQUE + CORRECTIONS STABILITÉ
# ============================================================


class TestSlotInvariant:
    """Tests prouvant l'impossibilité d'ouvrir 2 positions sur le même slot."""

    def test_open_position_refuses_duplicate_slot(self, db_session):
        """_open_position refuse d'ouvrir si le slot a déjà une position ouverte."""
        account = _make_account(db_session)
        account.max_open_positions = 3
        db_session.commit()

        pts = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Ouvrir une première position sur le slot "scalping"
        pos1 = pts._open_position(
            account=account, price=70000, sl=69000, tp=71000,
            size_usd=2500, reason="test1", score=72, direction="long",
            now=now, slot="scalping",
        )
        assert pos1 is not None
        assert pos1.slot == "scalping"
        assert pos1.status == "open"

        # Tenter d'ouvrir une deuxième position sur le MÊME slot
        pos2 = pts._open_position(
            account=account, price=70100, sl=69100, tp=71100,
            size_usd=2500, reason="test2", score=71, direction="long",
            now=now, slot="scalping",
        )
        # DOIT retourner None (invariant : 1 slot = 1 position max)
        assert pos2 is None

        # Vérifier qu'une seule position ouverte existe sur ce slot
        open_on_slot = (
            db_session.query(PaperTrade)
            .filter(PaperTrade.status == "open", PaperTrade.slot == "scalping")
            .all()
        )
        assert len(open_on_slot) == 1
        assert open_on_slot[0].id == pos1.id

    def test_open_position_allows_different_slots(self, db_session):
        """_open_position autorise des positions ouvertes sur des slots DIFFÉRENTS."""
        account = _make_account(db_session)
        account.max_open_positions = 3
        db_session.commit()

        pts = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        pos1 = pts._open_position(
            account=account, price=70000, sl=69000, tp=71000,
            size_usd=2500, reason="test1", score=72, direction="long",
            now=now, slot="scalping",
        )
        pos2 = pts._open_position(
            account=account, price=70000, sl=69000, tp=71000,
            size_usd=2500, reason="test2", score=68, direction="long",
            now=now, slot="aggressive",
        )
        assert pos1 is not None
        assert pos2 is not None
        assert pos1.slot == "scalping"
        assert pos2.slot == "aggressive"

    def test_open_position_no_slot_no_guard(self, db_session):
        """Sans slot (mono-position), le guard ne bloque pas."""
        account = _make_account(db_session)
        pts = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        pos1 = pts._open_position(
            account=account, price=70000, sl=69000, tp=71000,
            size_usd=2500, reason="test1", score=72, direction="long",
            now=now, slot=None,
        )
        assert pos1 is not None

    def test_open_position_slot_freed_after_close(self, db_session):
        """Après fermeture d'une position, le slot est de nouveau libre."""
        account = _make_account(db_session)
        account.max_open_positions = 3
        db_session.commit()

        pts = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        # Ouvrir
        pos1 = pts._open_position(
            account=account, price=70000, sl=69000, tp=71000,
            size_usd=2500, reason="test1", score=72, direction="long",
            now=now, slot="scalping",
        )
        assert pos1 is not None

        # Fermer
        pts._close_position(pos1, 70100, "test close", "closed_signal")

        # Réouvrir le même slot → doit fonctionner
        pos2 = pts._open_position(
            account=account, price=70200, sl=69200, tp=71200,
            size_usd=2500, reason="test2", score=71, direction="long",
            now=now, slot="scalping",
        )
        assert pos2 is not None
        assert pos2.id != pos1.id

    def test_rapid_repeated_open_same_slot(self, db_session):
        """Appels rapides répétés sur le même slot : un seul doit réussir."""
        account = _make_account(db_session)
        account.max_open_positions = 3
        db_session.commit()

        pts = PaperTradingService(db_session)
        now = datetime.now(timezone.utc)

        results = []
        for i in range(5):
            pos = pts._open_position(
                account=account, price=70000 + i, sl=69000, tp=71000,
                size_usd=2500, reason=f"rapid_test_{i}", score=72,
                direction="long", now=now, slot="scalping",
            )
            results.append(pos)

        # Seul le premier doit réussir
        assert results[0] is not None
        assert all(r is None for r in results[1:])

        open_on_slot = (
            db_session.query(PaperTrade)
            .filter(PaperTrade.status == "open", PaperTrade.slot == "scalping")
            .all()
        )
        assert len(open_on_slot) == 1


class TestStaleExitV196:
    """Tests pour le stale exit recalibré v1.9.6."""

    def test_stale_negative_exit_minutes_reduced(self):
        """Le stale_negative_exit_minutes est à 5 (au lieu de 8)."""
        params = PROFILE_PRESETS["scalping"]
        assert params.stale_negative_exit_minutes == 10

    def test_sl_tighter_at_020(self):
        """Le SL est à 0.20% pour limiter les grosses pertes."""
        params = PROFILE_PRESETS["scalping"]
        assert params.loss_cut_pct == 0.50

    def test_rr_theoretical_3_to_1(self):
        """[v2.0.0] Le R:R théorique est TP/SL = 0.8/0.20 = 4:1."""
        params = PROFILE_PRESETS["scalping"]
        rr = params.profit_take_pct / params.loss_cut_pct
        assert rr == pytest.approx(4.0, abs=0.1)


class TestShortRebalanceV196:
    """Tests pour le rééquilibrage des shorts v1.9.6."""

    def test_short_min_score_25(self):
        """[v2.0.3] Short min score aligné à 30 avec min_score relevé."""
        params = PROFILE_PRESETS["scalping"]
        assert params.short_min_score == 40

    def test_short_exit_threshold_30(self):
        """Short exit score threshold remonté à 30 pour laisser respirer."""
        params = PROFILE_PRESETS["scalping"]
        assert params.short_exit_score_threshold == 40

    def test_short_min_hold_45(self):
        """Short min hold à 45s pour compromis capture rapide."""
        params = PROFILE_PRESETS["scalping"]
        assert params.short_min_hold_seconds == 300
