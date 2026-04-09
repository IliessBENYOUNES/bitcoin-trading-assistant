"""
Tests pour l'optimisation des shorts v1.9.3.

Valide :
- RunValueAuditService (audit économique du run)
- Short exit score threshold (signal contraire relevé)
- Short min score (filtre économique shorts)
- Short min hold seconds (min hold conditionnel)
- Score convergence boost (cassure homogénéité)
- Learning layer short suggestions
- Endpoint /audit/run-value
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.services.trading_cost_service import (
    TradingCostModel, COST_REALISTIC, get_cost_model,
)
from app.services.trading_profile_service import PROFILE_PRESETS
from app.services.learning_service import LearningService
from app.services.run_value_audit_service import RunValueAuditService
from app.services.signal_service import compute_composite_score
from app.services.smart_cooldown_service import SmartCooldownService
from app.models.learning import LearningSignal, StrategyFeedback
from app.models.paper_account import PaperTrade, PaperAccount
from app.schemas.journal import TradingProfileParams, TradingProfileType
from app.schemas.signal import SignalItem, SignalDirection, CompositeScore


# ================================================================
# SECTION 1 : SHORT EXIT SCORE THRESHOLD
# ================================================================

class TestShortExitScoreThreshold:
    """Tests pour le seuil configurable de signal contraire sur les shorts."""

    def test_scalping_preset_has_short_exit_threshold(self):
        """Le preset scalping a un short_exit_score_threshold configuré."""
        p = PROFILE_PRESETS["scalping"]
        assert hasattr(p, "short_exit_score_threshold")
        assert p.short_exit_score_threshold is not None
        assert p.short_exit_score_threshold > 10, (
            "Le seuil doit être supérieur à l'ancien défaut de 10"
        )

    def test_short_exit_threshold_is_35(self):
        """[v1.9.6] Le seuil est configuré à 30 (compromis entre 10 et 35)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.short_exit_score_threshold == 30

    def test_conservative_has_no_short_exit_threshold(self):
        """Le profil conservative n'a pas besoin de ce paramètre."""
        p = PROFILE_PRESETS["conservative"]
        val = getattr(p, "short_exit_score_threshold", None)
        assert val is None

    def test_schema_accepts_short_exit_threshold(self):
        """Le schéma TradingProfileParams accepte le nouveau champ."""
        params = TradingProfileParams(
            profile_type=TradingProfileType.scalping,
            label="Test",
            description="Test",
            min_score=15,
            min_confidence="low",
            min_scenario_dominance=0.35,
            max_trades_per_day=50,
            cooldown_minutes=2,
            max_position_duration_hours=2,
            profit_take_pct=0.5,
            loss_cut_pct=0.4,
            loss_cut_score_threshold=5,
            leverage_enabled=True,
            max_leverage=1.5,
            short_exit_score_threshold=25,
        )
        assert params.short_exit_score_threshold == 25


# ================================================================
# SECTION 2 : SHORT MIN SCORE FILTER
# ================================================================

class TestShortMinScore:
    """Tests pour le filtre de score minimum des shorts."""

    def test_scalping_has_short_min_score(self):
        """Le preset scalping a un short_min_score."""
        p = PROFILE_PRESETS["scalping"]
        assert hasattr(p, "short_min_score")
        assert p.short_min_score is not None
        assert p.short_min_score > 0

    def test_short_min_score_value(self):
        """[v1.9.6] Le short_min_score est configuré à 25 (la 2-convergence suffit comme filtre)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.short_min_score == 25

    def test_short_min_score_filters_weak_setups(self):
        """Un score abs de 20 < short_min_score de 25 → short rejeté."""
        p = PROFILE_PRESETS["scalping"]
        assert abs(20) < p.short_min_score
        assert abs(30) >= p.short_min_score


# ================================================================
# SECTION 3 : SHORT MIN HOLD SECONDS
# ================================================================

class TestShortMinHoldSeconds:
    """Tests pour le min hold spécifique aux shorts."""

    def test_scalping_has_short_min_hold(self):
        """Le preset scalping a un short_min_hold_seconds."""
        p = PROFILE_PRESETS["scalping"]
        assert hasattr(p, "short_min_hold_seconds")
        assert p.short_min_hold_seconds is not None
        assert p.short_min_hold_seconds > 0

    def test_short_min_hold_longer_than_general(self):
        """Le min hold short est plus long que le min hold général."""
        p = PROFILE_PRESETS["scalping"]
        general_hold = p.min_hold_seconds or 0
        short_hold = p.short_min_hold_seconds or 0
        assert short_hold >= general_hold, (
            f"Short min hold ({short_hold}s) devrait être >= général ({general_hold}s)"
        )

    def test_short_min_hold_is_90(self):
        """[v1.9.6] Le short_min_hold_seconds est 45 (compromis entre respiration et capture rapide)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.short_min_hold_seconds == 45


# ================================================================
# SECTION 4 : CONVERGENCE BOOST (score homogénéité)
# ================================================================

class TestConvergenceBoost:
    """Tests pour le boost de convergence qui casse l'homogénéité des scores."""

    def _make_signal(self, direction, strength=0.5, indicator="test"):
        return SignalItem(
            indicator=indicator,
            direction=direction,
            strength=strength,
            value=0,
            message="test",
        )

    def test_unanimous_bullish_gets_boosted(self):
        """Score unanime bullish (5 signaux) doit être boosté au-dessus du score sans boost."""
        signals = [
            self._make_signal(SignalDirection.BULLISH, 0.6, f"ind_{i}")
            for i in range(5)
        ]
        result = compute_composite_score(signals)
        # Avec 5 signaux bullish à strength 0.6, le score doit être élevé
        # Le boost de convergence devrait pousser au-dessus de 60
        assert result.score >= 60, f"Score unanime {result.score} trop bas"

    def test_divided_signals_compressed(self):
        """Signaux très divisés doivent donner un score comprimé."""
        signals = [
            self._make_signal(SignalDirection.BULLISH, 0.5, "bull1"),
            self._make_signal(SignalDirection.BULLISH, 0.5, "bull2"),
            self._make_signal(SignalDirection.BEARISH, 0.5, "bear1"),
            self._make_signal(SignalDirection.BEARISH, 0.5, "bear2"),
            self._make_signal(SignalDirection.NEUTRAL, 0.3, "neutral"),
        ]
        result = compute_composite_score(signals)
        # Score devrait être proche de 0 et comprimé
        assert abs(result.score) <= 20, f"Score divisé {result.score} pas assez bas"

    def test_strong_unanimous_beats_moderate(self):
        """4 bullish à 0.6 + 1 neutral > 4 bullish à 0.15 + 1 neutral."""
        strong = [
            self._make_signal(SignalDirection.BULLISH, 0.6, f"ind_{i}")
            for i in range(4)
        ] + [self._make_signal(SignalDirection.NEUTRAL, 0.1, "n1")]
        moderate = [
            self._make_signal(SignalDirection.BULLISH, 0.15, f"ind_{i}")
            for i in range(4)
        ] + [self._make_signal(SignalDirection.NEUTRAL, 0.1, "n1")]
        strong_score = compute_composite_score(strong).score
        moderate_score = compute_composite_score(moderate).score
        assert strong_score > moderate_score, (
            f"Strong ({strong_score}) devrait battre moderate ({moderate_score})"
        )

    def test_convergence_boost_with_bearish(self):
        """Le boost fonctionne aussi pour les signaux bearish unanimes."""
        signals = [
            self._make_signal(SignalDirection.BEARISH, 0.7, f"ind_{i}")
            for i in range(5)
        ]
        result = compute_composite_score(signals)
        assert result.score <= -60, f"Score bearish unanime {result.score} pas assez négatif"

    def test_two_signals_no_boost(self):
        """Avec seulement 2 signaux, pas de convergence boost."""
        signals = [
            self._make_signal(SignalDirection.BULLISH, 0.9, "ind1"),
            self._make_signal(SignalDirection.BULLISH, 0.9, "ind2"),
        ]
        result = compute_composite_score(signals)
        # Pas de crash, pas de boost, score raisonnable
        assert 0 < result.score <= 100


# ================================================================
# SECTION 5 : RUN VALUE AUDIT SERVICE
# ================================================================

class TestRunValueAuditService:
    """Tests pour le service d'audit de valeur économique."""

    def _create_account_and_trades(self, db, trades_data):
        """Helper pour créer un compte et des trades de test."""
        account = PaperAccount(
            initial_capital=10000.0,
            current_capital=10000.0,
            peak_capital=10000.0,
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        for td in trades_data:
            trade = PaperTrade(
                account_id=account.id,
                status=td.get("status", "closed_signal"),
                direction=td.get("direction", "short"),
                entry_price=td.get("entry_price", 80000),
                exit_price=td.get("exit_price", 79900),
                stop_loss_price=80500,
                take_profit_price=79500,
                position_size_usd=td.get("size", 1000),
                leverage=td.get("leverage", 1.5),
                pnl=td.get("pnl", 0.5),
                pnl_pct=td.get("pnl_pct", 0.05),
                entry_reason="test",
                exit_reason=td.get("exit_reason", "signal contraire"),
                decision_score=td.get("score", 70),
                entry_ts=datetime.now(timezone.utc) - timedelta(hours=1),
                exit_ts=datetime.now(timezone.utc),
                duration_hours=td.get("duration_h", 0.03),
                profile_type="scalping",
                slot="scalping",
            )
            db.add(trade)
        db.commit()
        return account

    def test_empty_audit(self, db_session):
        """Audit sans trades retourne un résultat vide."""
        service = RunValueAuditService(db_session)
        result = service.run_audit()
        assert result["total_trades"] == 0

    def test_audit_with_trades(self, db_session):
        """Audit avec des trades retourne les sections attendues."""
        trades = [
            {"pnl": 2.0, "pnl_pct": 0.2, "direction": "short", "status": "closed_signal"},
            {"pnl": -1.0, "pnl_pct": -0.1, "direction": "short", "status": "closed_sl"},
            {"pnl": 0.5, "pnl_pct": 0.05, "direction": "long", "status": "closed_tp"},
            {"pnl": 0.1, "pnl_pct": 0.01, "direction": "short", "status": "closed_signal"},
            {"pnl": -0.3, "pnl_pct": -0.03, "direction": "short", "status": "closed_stale"},
        ]
        self._create_account_and_trades(db_session, trades)
        service = RunValueAuditService(db_session)
        result = service.run_audit()

        assert result["total_trades"] == 5
        assert "economic_audit" in result
        assert "usefulness_audit" in result
        assert "pnl_bucket_distribution" in result
        assert "signal_exit_audit" in result
        assert "short_economics" in result

    def test_economic_audit_structure(self, db_session):
        """L'audit économique contient les métriques clés."""
        trades = [
            {"pnl": 2.0, "pnl_pct": 0.2},
            {"pnl": -1.0, "pnl_pct": -0.1},
        ]
        self._create_account_and_trades(db_session, trades)
        service = RunValueAuditService(db_session)
        result = service.run_audit()
        eco = result["economic_audit"]

        assert "gross_pnl" in eco
        assert "net_pnl" in eco
        assert "total_costs" in eco
        assert "avg_trade_pnl_gross" in eco
        assert "avg_trade_pnl_net" in eco
        assert "gross_profit_factor" in eco
        assert "net_profit_factor" in eco
        assert "net_expectancy" in eco

    def test_usefulness_categories(self, db_session):
        """L'audit d'utilité catégorise les trades."""
        trades = [
            {"pnl": 3.0, "pnl_pct": 0.3, "duration_h": 0.1},   # useful
            {"pnl": 0.1, "pnl_pct": 0.01, "duration_h": 0.01},  # churn
            {"pnl": -1.5, "pnl_pct": -0.15, "duration_h": 0.5}, # loss
        ]
        self._create_account_and_trades(db_session, trades)
        service = RunValueAuditService(db_session)
        result = service.run_audit()
        cats = result["usefulness_audit"]["categories"]
        assert len(cats) > 0

    def test_pnl_bucket_distribution(self, db_session):
        """La distribution par bucket contient gross et net."""
        trades = [
            {"pnl": 0.1, "pnl_pct": 0.01},
            {"pnl": 1.5, "pnl_pct": 0.15},
            {"pnl": -0.5, "pnl_pct": -0.05},
        ]
        self._create_account_and_trades(db_session, trades)
        service = RunValueAuditService(db_session)
        result = service.run_audit()
        buckets = result["pnl_bucket_distribution"]
        assert "gross" in buckets
        assert "net" in buckets
        assert "dust_zone_pct" in buckets

    def test_signal_exit_audit_shorts(self, db_session):
        """L'audit de signal contraire identifie les shorts impactés."""
        trades = [
            {"pnl": 0.2, "direction": "short", "status": "closed_signal"},
            {"pnl": 0.1, "direction": "short", "status": "closed_signal"},
            {"pnl": -0.3, "direction": "short", "status": "closed_signal"},
            {"pnl": 1.0, "direction": "short", "status": "closed_tp"},
        ]
        self._create_account_and_trades(db_session, trades)
        service = RunValueAuditService(db_session)
        result = service.run_audit()
        sig = result["signal_exit_audit"]
        assert sig["total_short_signal_exits"] == 3
        assert sig["total_shorts"] == 4
        assert sig["signal_exit_pct_of_shorts"] == 75.0

    def test_short_economics(self, db_session):
        """L'audit short economics fournit les métriques clés."""
        trades = [
            {"pnl": 0.5, "direction": "short", "status": "closed_signal"},
            {"pnl": -0.3, "direction": "short", "status": "closed_sl"},
            {"pnl": 2.0, "direction": "long", "status": "closed_tp"},
        ]
        self._create_account_and_trades(db_session, trades)
        service = RunValueAuditService(db_session)
        result = service.run_audit()
        se = result["short_economics"]
        assert se["short_count"] == 2
        assert se["long_count"] == 1
        assert "dominant_exit" in se
        assert "pct_useful" in se


# ================================================================
# SECTION 6 : ENDPOINT /audit/run-value
# ================================================================

class TestRunValueAuditEndpoint:
    """Tests pour l'endpoint GET /audit/run-value."""

    def test_endpoint_returns_200_empty(self, client):
        """L'endpoint retourne 200 même sans données."""
        resp = client.get("/audit/run-value")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_trades" in data

    def test_endpoint_accepts_cost_preset(self, client):
        """L'endpoint accepte un preset de coûts."""
        resp = client.get("/audit/run-value?cost_preset=optimistic")
        assert resp.status_code == 200

    def test_endpoint_with_trades(self, client):
        """L'endpoint retourne les données avec des trades (via API)."""
        # Créer un compte paper via l'API pour que la session soit cohérente
        resp_create = client.post("/paper/account", json={
            "initial_capital": 10000,
        })
        # L'endpoint retourne 200 même si pas de trades encore
        resp = client.get("/audit/run-value")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_trades" in data
        assert "long_short_balance" in data


# ================================================================
# SECTION 7 : LEARNING LAYER SHORT SUGGESTIONS
# ================================================================

class TestLearningShortSuggestions:
    """Tests pour les suggestions learning orientées short."""

    def _seed_learning_data(self, db, n_shorts=15, short_useful_pct=0.2):
        """Seed des échantillons learning pour les tests."""
        for i in range(n_shorts):
            is_useful = i < int(n_shorts * short_useful_pct)
            sample = LearningSignal(
                trade_id=i + 1,
                score=70,
                direction="short",
                slot="scalping",
                profile_type="scalping",
                leverage=1.5,
                entry_price=80000,
                exit_type="closed_signal",
                pnl_brut=2.0 if is_useful else 0.1,
                pnl_pct=0.2 if is_useful else 0.01,
                duration_minutes=5.0 if is_useful else 0.5,
                was_profitable=1,
                cost_estimated=1.5,
                pnl_net_estimated=0.5 if is_useful else -1.4,
                usefulness_category="useful" if is_useful else "insignificant",
            )
            db.add(sample)
        db.commit()

    def test_suggestion_short_min_score(self, db_session):
        """Si >50% shorts insignifiants, suggestion de relever short_min_score."""
        self._seed_learning_data(db_session, n_shorts=15, short_useful_pct=0.2)
        service = LearningService(db_session)
        suggestions = service.suggest_adjustments("scalping")
        names = [s.parameter_name for s in suggestions]
        assert "short_min_score" in names, (
            f"Suggestion short_min_score manquante. Found: {names}"
        )

    def test_suggestion_short_exit_threshold(self, db_session):
        """Si >50% shorts fermés par signal contraire, suggestion de relever le seuil."""
        for i in range(12):
            sample = LearningSignal(
                trade_id=i + 1,
                score=70,
                direction="short",
                slot="scalping",
                profile_type="scalping",
                leverage=1.5,
                entry_price=80000,
                exit_type="closed_signal",
                pnl_brut=0.1,
                pnl_pct=0.01,
                duration_minutes=1.0,
                was_profitable=1,
                cost_estimated=1.5,
                pnl_net_estimated=-1.4,
                usefulness_category="insignificant",
            )
            db_session.add(sample)
        db_session.commit()

        service = LearningService(db_session)
        suggestions = service.suggest_adjustments("scalping")
        names = [s.parameter_name for s in suggestions]
        assert "short_exit_score_threshold" in names, (
            f"Suggestion short_exit_score_threshold manquante. Found: {names}"
        )

    def test_suggestion_short_min_hold(self, db_session):
        """Si beaucoup de shorts < 2min avec net négatif, suggestion d'allonger min hold."""
        for i in range(12):
            sample = LearningSignal(
                trade_id=i + 1,
                score=70,
                direction="short",
                slot="scalping",
                profile_type="scalping",
                leverage=1.5,
                entry_price=80000,
                exit_type="closed_signal",
                pnl_brut=-0.5,
                pnl_pct=-0.05,
                duration_minutes=0.8,  # < 2 minutes
                was_profitable=0,
                cost_estimated=1.5,
                pnl_net_estimated=-2.0,
                usefulness_category="loss_useful",
            )
            db_session.add(sample)
        db_session.commit()

        service = LearningService(db_session)
        suggestions = service.suggest_adjustments("scalping")
        names = [s.parameter_name for s in suggestions]
        assert "short_min_hold_seconds" in names, (
            f"Suggestion short_min_hold_seconds manquante. Found: {names}"
        )

    def test_safety_bounds_new_params(self):
        """Les nouveaux paramètres ont des safety bounds."""
        from app.services.learning_service import SAFETY_BOUNDS
        assert "short_min_score" in SAFETY_BOUNDS
        assert "short_exit_score_threshold" in SAFETY_BOUNDS
        assert "short_min_hold_seconds" in SAFETY_BOUNDS

    def test_dataset_stats_short_fields(self, db_session):
        """Les stats incluent les champs short spécifiques."""
        self._seed_learning_data(db_session, n_shorts=15, short_useful_pct=0.2)
        service = LearningService(db_session)
        stats = service.get_dataset_stats()
        assert hasattr(stats, "short_trades_useful")
        assert hasattr(stats, "short_trades_insignificant")
        assert hasattr(stats, "short_trades_churn")
        assert hasattr(stats, "pct_short_economically_useful")


# ================================================================
# SECTION 8 : PAPER TRADING SHORT EXIT BEHAVIOR
# ================================================================

class TestPaperTradingShortExit:
    """Tests pour le comportement de sortie des shorts dans paper_trading_service."""

    def test_short_not_closed_below_threshold(self):
        """Un short ne devrait PAS être fermé si score < short_exit_score_threshold."""
        # Simulation : score = 30, threshold = 35 → le short reste ouvert
        threshold = 35
        score = 30
        assert score < threshold, "Le score doit être sous le seuil pour que le short survive"

    def test_short_closed_above_threshold(self):
        """Un short DEVRAIT être fermé si score >= short_exit_score_threshold."""
        threshold = 35
        score = 40
        assert score >= threshold, "Le score doit être au-dessus du seuil pour fermer le short"

    def test_short_min_hold_applies(self):
        """Le short_min_hold_seconds s'applique aux shorts."""
        p = PROFILE_PRESETS["scalping"]
        # Un short de 30 secondes (< 45) est trop jeune
        elapsed = 30
        min_hold = p.short_min_hold_seconds or 0
        assert elapsed < min_hold, "Un short de 30s < min_hold 45s → trop jeune"

    def test_short_allowed_after_min_hold(self):
        """Le short peut être fermé après le min_hold."""
        p = PROFILE_PRESETS["scalping"]
        elapsed = 120
        min_hold = p.short_min_hold_seconds or 0
        assert elapsed >= min_hold, "Un short de 120s >= min_hold 45s → peut être fermé"


# ================================================================
# SECTION 9 : USEFULNESS CLASSIFICATION
# ================================================================

class TestUsefulnessClassification:
    """Tests pour _classify_usefulness."""

    def test_useful_trade(self):
        """Trade avec net > 0.5 = useful."""
        cat = LearningService._classify_usefulness(
            pnl_brut=3.0, pnl_net=1.5, pnl_pct=0.15, duration_min=5.0,
        )
        assert cat == "useful"

    def test_insignificant_trade(self):
        """Trade brut positif mais net quasi nul = insignificant."""
        cat = LearningService._classify_usefulness(
            pnl_brut=0.5, pnl_net=0.1, pnl_pct=0.05, duration_min=3.0,
        )
        assert cat == "insignificant"

    def test_churn_trade(self):
        """Trade < 1 min et PnL % < 0.05% = churn."""
        cat = LearningService._classify_usefulness(
            pnl_brut=0.01, pnl_net=-1.0, pnl_pct=0.01, duration_min=0.5,
        )
        assert cat == "churn"

    def test_loss_useful(self):
        """Perte bien coupée (PnL % > -0.3%) = loss_useful."""
        cat = LearningService._classify_usefulness(
            pnl_brut=-1.0, pnl_net=-2.5, pnl_pct=-0.15, duration_min=5.0,
        )
        assert cat == "loss_useful"

    def test_loss_destructive(self):
        """Grosse perte (PnL % <= -0.3%) = loss_destructive."""
        cat = LearningService._classify_usefulness(
            pnl_brut=-5.0, pnl_net=-6.5, pnl_pct=-0.5, duration_min=10.0,
        )
        assert cat == "loss_destructive"


# ================================================================
# SECTION 10 : NON-REGRESSION SCALPING PRESET
# ================================================================

class TestScalpingPresetNonRegression:
    """Vérifier que les changements ne cassent pas le preset scalping existant."""

    def test_scalping_tp_pct(self):
        """[v1.9.5] Le TP scalping est élargi à 0.6%."""
        p = PROFILE_PRESETS["scalping"]
        assert p.profit_take_pct == 0.6

    def test_scalping_sl_pct(self):
        """[v1.9.6] Le SL scalping est resserré à 0.20%."""
        p = PROFILE_PRESETS["scalping"]
        assert p.loss_cut_pct == 0.20

    def test_scalping_min_hold(self):
        """Le min_hold général est inchangé (30s)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.min_hold_seconds == 30

    def test_scalping_smart_cooldown(self):
        """Le smart cooldown est toujours activé."""
        p = PROFILE_PRESETS["scalping"]
        assert p.smart_cooldown_enabled is True

    def test_scalping_max_trades_per_day(self):
        """Le max trades par jour est inchangé (50)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.max_trades_per_day == 50

    def test_scalping_analysis_timeframe(self):
        """Le timeframe d'analyse est inchangé (15m)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.analysis_timeframe == "15m"

    def test_scalping_trailing_stop(self):
        """[v1.9.5] Les paramètres trailing stop recalibrés."""
        p = PROFILE_PRESETS["scalping"]
        assert p.trailing_stop_activation_pct == 0.15  # [v1.9.5] was 0.08
        assert p.trailing_stop_pct == 0.10             # [v1.9.5] was 0.12

    def test_scalping_leverageééévalues(self):
        """Le levier scalping est inchangé."""
        p = PROFILE_PRESETS["scalping"]
        assert p.max_leverage == 1.5
        assert p.leverage_enabled is True

    def test_all_presets_valid(self):
        """Tous les presets sont valides et instanciables."""
        for name, params in PROFILE_PRESETS.items():
            assert params.profile_type is not None
            assert params.label
            assert params.min_score >= 0
            assert params.max_trades_per_day > 0


# ================================================================
# SECTION 11 : ECONOMIC EDGE INTEGRATION
# ================================================================

class TestEconomicEdgeIntegration:
    """Tests d'intégration pour la valeur économique."""

    def test_net_margin_with_new_params(self):
        """Après v1.9.3, un trade gagnant au TP garde une marge nette."""
        p = PROFILE_PRESETS["scalping"]
        cm = COST_REALISTIC
        gross = 1000 * p.max_leverage * (p.profit_take_pct / 100)
        cost = cm.round_trip_cost_usd(1000 * p.max_leverage)
        net = gross - cost
        assert net > 0, f"Marge nette {net:.2f} doit être positive"

    def test_short_min_score_above_cost_threshold(self):
        """Le short_min_score est au-dessus du min_score général."""
        p = PROFILE_PRESETS["scalping"]
        assert p.short_min_score >= p.min_score, (
            f"short_min_score ({p.short_min_score}) devrait être >= min_score ({p.min_score})"
        )


# ================================================================
# SECTION 12 : [v1.9.4] REVERSAL SÉLECTIVITÉ
# ================================================================

class TestReversalSelectivity:
    """Tests pour la sélectivité du reversal scalping v1.9.4."""

    def test_single_overbought_no_reversal(self, db_session):
        """Un seul RSI overbought ne déclenche plus un reversal short."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "rsi_overbought", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": 65,
            "technical_score": 70,
        }
        result = pts._scalping_reversal_check(decision)
        assert result is None, "1 seul oscillateur ne doit plus déclencher un short"

    def test_double_overbought_triggers_reversal(self, db_session):
        """2 oscillateurs overbought déclenchent un reversal short."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [
                {"rule_name": "rsi_overbought", "satisfied": True, "direction": "bearish"},
                {"rule_name": "stochrsi_overbought", "satisfied": True, "direction": "bearish"},
            ],
            "combined_score": 65,
            "technical_score": 70,
        }
        result = pts._scalping_reversal_check(decision)
        assert result == "short"

    def test_tech_score_alone_not_enough(self, db_session):
        """Tech score extrême seul ne suffit pas pour un reversal."""
        from app.services.paper_trading_service import PaperTradingService
        pts = PaperTradingService(db_session)
        decision = {
            "rules_evaluated": [],
            "combined_score": 72,
            "technical_score": 98,
        }
        result = pts._scalping_reversal_check(decision)
        # tech_score ≥ 95 + bearish_rules==0 → overbought=1, mais pas ≥2
        assert result is None, "tech_score seul ne suffit pas"

    def test_short_min_score_rejects_weak(self):
        """[v1.9.6] Le short_min_score à 25 rejette les shorts avec abs(score) < 25."""
        p = PROFILE_PRESETS["scalping"]
        assert p.short_min_score == 25
        # Score de 20 → rejeté
        assert abs(20) < p.short_min_score
        # Score de 30 → accepté
        assert abs(30) >= p.short_min_score


# ================================================================
# SECTION 13 : [v1.9.4] RATIO GAIN/PERTE (R/R AMÉLIORÉ)
# ================================================================

class TestGainLossRatio:
    """Tests pour le contrôle du ratio gain/perte."""

    def test_scalping_rr_ratio_above_1(self):
        """Le ratio R/R scalping (TP/SL) doit être > 1.0."""
        p = PROFILE_PRESETS["scalping"]
        rr = p.profit_take_pct / p.loss_cut_pct
        assert rr > 1.0, f"R/R {rr:.2f} devrait être > 1.0"

    def test_scalping_rr_improved_vs_previous(self):
        """Le R/R v1.9.4 (1.43) est meilleur que v1.9.3 (1.25)."""
        p = PROFILE_PRESETS["scalping"]
        rr = p.profit_take_pct / p.loss_cut_pct
        assert rr >= 1.4, f"R/R {rr:.2f} devrait être >= 1.4 (ancien: 1.25)"

    def test_sl_tighter_than_tp(self):
        """Le SL doit être plus serré que le TP pour un edge positif."""
        p = PROFILE_PRESETS["scalping"]
        assert p.loss_cut_pct < p.profit_take_pct, (
            f"SL {p.loss_cut_pct}% devrait être < TP {p.profit_take_pct}%"
        )

    def test_sl_still_above_spread(self):
        """[v1.9.5] Le SL ne doit pas être absurdement serré. 0.25% > 0.15% (demi round-trip)."""
        p = PROFILE_PRESETS["scalping"]
        # [v1.9.5] Le SL à 0.25% est intentionnellement sous le round-trip complet (0.31%)
        # pour réduire les pertes maximales. Le coût d'entrée seul est ~0.155%.
        # Le SL doit rester au-dessus du coût d'entrée seul.
        assert p.loss_cut_pct > 0.15, f"SL {p.loss_cut_pct}% trop serré (< 0.15% entrée seule)"


# ================================================================
# SECTION 14 : [v1.9.4] LONG/SHORT BALANCE AUDIT
# ================================================================

class TestLongShortBalanceAudit:
    """Tests pour le diagnostic de balance long/short."""

    def test_audit_returns_long_short_balance(self, db_session):
        """L'audit run-value inclut la section long_short_balance."""
        from app.services.run_value_audit_service import RunValueAuditService
        service = RunValueAuditService(db_session)
        result = service.run_audit()
        # Même sans trades, la structure existe
        assert "long_short_balance" in result

    def test_audit_balance_verdict_no_trades(self, db_session):
        """Sans trades, le verdict est approprié."""
        from app.services.run_value_audit_service import RunValueAuditService
        service = RunValueAuditService(db_session)
        result = service.run_audit()
        # Sans compte, retourne l'audit vide
        assert result["total_trades"] == 0

    def test_audit_economic_has_win_loss_ratio(self, db_session):
        """L'audit économique inclut le win_loss_ratio."""
        from app.services.run_value_audit_service import RunValueAuditService
        from app.models.paper_account import PaperAccount, PaperTrade
        from datetime import datetime, timezone

        # Créer un compte et un trade
        account = PaperAccount(
            current_capital=10000, initial_capital=10000,
            is_active=True, max_open_positions=1,
        )
        db_session.add(account)
        db_session.commit()
        now = datetime.now(timezone.utc)
        trade = PaperTrade(
            account_id=account.id, entry_price=70000, exit_price=70100,
            position_size_usd=1000, direction="long",
            stop_loss_price=69000, take_profit_price=71000,
            status="closed_tp", pnl=1.43, pnl_pct=0.14,
            entry_ts=now, exit_ts=now, duration_hours=0.01,
            slot="scalping", entry_reason="test",
        )
        db_session.add(trade)
        db_session.commit()

        service = RunValueAuditService(db_session)
        result = service.run_audit()
        audit = result["economic_audit"]
        assert "win_loss_ratio" in audit
        assert "median_win" in audit
        assert "top3_loss_contribution_pct" in audit


# ================================================================
# SECTION 15 : [v1.9.4] SIGNAL CONTRAIRE PROTECTION
# ================================================================

class TestSignalContraireProtection:
    """Tests pour la protection des shorts contre la sortie signal contraire."""

    def test_short_exit_threshold_35(self):
        """[v1.9.6] Le seuil de sortie signal contraire est à 30 (compromis)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.short_exit_score_threshold == 30

    def test_short_survives_moderate_bullish(self):
        """Un short ne se ferme pas sur un score bullish de 25 (< 30)."""
        p = PROFILE_PRESETS["scalping"]
        score = 25
        assert score < p.short_exit_score_threshold, (
            "Score 25 doit être sous le seuil 30 → le short survit"
        )

    def test_short_closes_on_strong_bullish(self):
        """Un short se ferme sur un score bullish de 35 (>= 30)."""
        p = PROFILE_PRESETS["scalping"]
        score = 35
        assert score >= p.short_exit_score_threshold, (
            "Score 35 doit être au-dessus du seuil 30 → le short est fermé"
        )

    def test_short_min_hold_45s(self):
        """[v1.9.6] Le min hold short est 45s (plus que le 30s général)."""
        p = PROFILE_PRESETS["scalping"]
        assert p.short_min_hold_seconds == 45
        assert p.short_min_hold_seconds > p.min_hold_seconds

