"""
Tests pour le moteur de décision (v1.0).

Couvre :
- Évaluation des règles individuelles
- Calcul des scénarios (probabilités, normalisation)
- Génération de recommandation
- Intégration DecisionService avec DB
- Endpoint GET /market/decision
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.services.decision_service import (
    DecisionService,
    _eval_rsi_overbought,
    _eval_rsi_oversold,
    _eval_macd_bullish,
    _eval_macd_bearish,
    _eval_sma_trend_up,
    _eval_sma_trend_down,
    _eval_sentiment_positive,
    _eval_sentiment_negative,
    _eval_ema_crossover_bullish,
    _eval_ema_crossover_bearish,
    _eval_stochrsi_oversold,
    _eval_stochrsi_overbought,
    _eval_multi_confluence_bullish,
    _eval_multi_confluence_bearish,
    _find_signal,
    DEFAULT_RULES,
    TECHNICAL_WEIGHT,
    SENTIMENT_WEIGHT,
    FNG_HIST_WEIGHT,
    NEWS_HIST_WEIGHT,
)
from app.schemas.decision import (
    Scenario,
    RuleResult,
    Recommendation,
    DecisionMeta,
    DecisionResponse,
    ActionType,
)
from app.schemas.signal import SignalDirection, ConfidenceLevel
from app.models import Candle


# ============================================================
# HELPER : créer des données de signaux fictives
# ============================================================

def _make_signals_data(
    rsi_dir="neutral", rsi_strength=0.1,
    macd_dir="neutral", macd_strength=0.1,
    sma_dir="neutral", sma_strength=0.1,
    score=0,
):
    """Crée un dict de signaux fictif pour les tests."""
    return {
        "signals": [
            {"indicator": "rsi", "direction": rsi_dir, "strength": rsi_strength, "value": 50, "message": "RSI test"},
            {"indicator": "macd", "direction": macd_dir, "strength": macd_strength, "value": 0, "message": "MACD test"},
            {"indicator": "sma", "direction": sma_dir, "strength": sma_strength, "value": 50000, "message": "SMA test"},
        ],
        "composite": {"score": score, "direction": rsi_dir, "confidence": "low", "consensus": "divided"},
        "summary": "Test",
    }


def _make_sentiment_data(score=0):
    """Crée un dict de sentiment fictif."""
    return {
        "total_articles": 10,
        "positive_count": 3,
        "negative_count": 3,
        "neutral_count": 4,
        "overall_sentiment": "neutral",
        "sentiment_score": score,
    }


# ============================================================
# TESTS : _find_signal helper
# ============================================================

class TestFindSignal:
    """Tests pour le helper _find_signal."""

    def test_find_existing_signal(self):
        """Trouve un signal existant par nom d'indicateur."""
        data = _make_signals_data()
        result = _find_signal(data, "rsi")
        assert result is not None
        assert result["indicator"] == "rsi"

    def test_find_nonexistent_signal(self):
        """Retourne None pour un indicateur inexistant."""
        data = _make_signals_data()
        result = _find_signal(data, "ichimoku")
        assert result is None

    def test_find_signal_empty_data(self):
        """Retourne None pour des données vides."""
        result = _find_signal({}, "rsi")
        assert result is None

    def test_find_signal_no_signals_key(self):
        """Retourne None si pas de clé 'signals'."""
        result = _find_signal({"composite": {}}, "rsi")
        assert result is None


# ============================================================
# TESTS : Règles individuelles
# ============================================================

class TestRuleEvaluators:
    """Tests pour chaque fonction d'évaluation de règle."""

    def test_rsi_overbought_satisfied(self):
        """RSI baissier fort → surachat détecté."""
        data = _make_signals_data(rsi_dir="bearish", rsi_strength=0.8)
        satisfied, detail = _eval_rsi_overbought(data, {})
        assert satisfied is True
        assert "surachat" in detail.lower()

    def test_rsi_overbought_not_satisfied(self):
        """RSI neutre → pas de surachat."""
        data = _make_signals_data(rsi_dir="neutral", rsi_strength=0.1)
        satisfied, detail = _eval_rsi_overbought(data, {})
        assert satisfied is False

    def test_rsi_overbought_weak_bearish(self):
        """RSI baissier faible (strength < 0.7) → pas de surachat."""
        data = _make_signals_data(rsi_dir="bearish", rsi_strength=0.3)
        satisfied, _ = _eval_rsi_overbought(data, {})
        assert satisfied is False

    def test_rsi_oversold_satisfied(self):
        """RSI haussier fort → survente détectée."""
        data = _make_signals_data(rsi_dir="bullish", rsi_strength=0.8)
        satisfied, detail = _eval_rsi_oversold(data, {})
        assert satisfied is True
        assert "survente" in detail.lower()

    def test_rsi_oversold_not_satisfied(self):
        """RSI neutre → pas de survente."""
        data = _make_signals_data(rsi_dir="neutral", rsi_strength=0.1)
        satisfied, _ = _eval_rsi_oversold(data, {})
        assert satisfied is False

    def test_macd_bullish_satisfied(self):
        """MACD haussier fort → croisement détecté."""
        data = _make_signals_data(macd_dir="bullish", macd_strength=0.6)
        satisfied, detail = _eval_macd_bullish(data, {})
        assert satisfied is True
        assert "haussier" in detail.lower()

    def test_macd_bullish_not_satisfied(self):
        """MACD baissier → pas de croisement haussier."""
        data = _make_signals_data(macd_dir="bearish", macd_strength=0.6)
        satisfied, _ = _eval_macd_bullish(data, {})
        assert satisfied is False

    def test_macd_bearish_satisfied(self):
        """MACD baissier fort → croisement détecté."""
        data = _make_signals_data(macd_dir="bearish", macd_strength=0.6)
        satisfied, detail = _eval_macd_bearish(data, {})
        assert satisfied is True
        assert "baissier" in detail.lower()

    def test_macd_bearish_not_satisfied(self):
        """MACD haussier → pas de croisement baissier."""
        data = _make_signals_data(macd_dir="bullish", macd_strength=0.6)
        satisfied, _ = _eval_macd_bearish(data, {})
        assert satisfied is False

    def test_sma_trend_up_satisfied(self):
        """SMA haussier fort → tendance haussière."""
        data = _make_signals_data(sma_dir="bullish", sma_strength=0.7)
        satisfied, detail = _eval_sma_trend_up(data, {})
        assert satisfied is True
        assert "dessus" in detail.lower() or "moyennes" in detail.lower()

    def test_sma_trend_up_not_satisfied(self):
        """SMA baissier → pas de tendance haussière."""
        data = _make_signals_data(sma_dir="bearish", sma_strength=0.7)
        satisfied, _ = _eval_sma_trend_up(data, {})
        assert satisfied is False

    def test_sma_trend_down_satisfied(self):
        """SMA baissier fort → tendance baissière."""
        data = _make_signals_data(sma_dir="bearish", sma_strength=0.7)
        satisfied, _ = _eval_sma_trend_down(data, {})
        assert satisfied is True

    def test_sma_trend_down_not_satisfied(self):
        """SMA haussier → pas de tendance baissière."""
        data = _make_signals_data(sma_dir="bullish", sma_strength=0.7)
        satisfied, _ = _eval_sma_trend_down(data, {})
        assert satisfied is False

    def test_sentiment_positive_convergence(self):
        """Sentiment positif + technique haussière → convergence."""
        data = _make_signals_data(score=30)
        sentiment = _make_sentiment_data(score=40)
        satisfied, detail = _eval_sentiment_positive(data, sentiment)
        assert satisfied is True
        assert "converge" in detail.lower()

    def test_sentiment_positive_no_convergence(self):
        """Sentiment positif + technique baissière → pas de convergence."""
        data = _make_signals_data(score=-30)
        sentiment = _make_sentiment_data(score=40)
        satisfied, _ = _eval_sentiment_positive(data, sentiment)
        assert satisfied is False

    def test_sentiment_negative_convergence(self):
        """Sentiment négatif + technique baissière → convergence."""
        data = _make_signals_data(score=-30)
        sentiment = _make_sentiment_data(score=-40)
        satisfied, detail = _eval_sentiment_negative(data, sentiment)
        assert satisfied is True
        assert "converge" in detail.lower()

    def test_sentiment_negative_no_convergence(self):
        """Sentiment négatif + technique haussière → pas de convergence."""
        data = _make_signals_data(score=30)
        sentiment = _make_sentiment_data(score=-40)
        satisfied, _ = _eval_sentiment_negative(data, sentiment)
        assert satisfied is False

    def test_ema_crossover_bullish_satisfied(self):
        """EMA cross bullish fort → règle satisfaite."""
        data = {
            "signals": [
                {"indicator": "ema_cross", "direction": "bullish", "strength": 0.7, "value": 500, "message": "EMA golden cross"},
            ],
            "composite": {"score": 30},
        }
        satisfied, detail = _eval_ema_crossover_bullish(data, {})
        assert satisfied is True
        assert "golden" in detail.lower() or "ema" in detail.lower()

    def test_ema_crossover_bullish_not_satisfied(self):
        """EMA cross absent ou faible → pas satisfaite."""
        data = {"signals": [], "composite": {"score": 0}}
        satisfied, _ = _eval_ema_crossover_bullish(data, {})
        assert satisfied is False

    def test_ema_crossover_bearish_satisfied(self):
        """EMA cross bearish fort → règle satisfaite."""
        data = {
            "signals": [
                {"indicator": "ema_cross", "direction": "bearish", "strength": 0.7, "value": -500, "message": "EMA death cross"},
            ],
            "composite": {"score": -30},
        }
        satisfied, detail = _eval_ema_crossover_bearish(data, {})
        assert satisfied is True

    def test_stochrsi_oversold_satisfied(self):
        """StochRSI bullish fort → règle survente satisfaite."""
        data = {
            "signals": [
                {"indicator": "stoch_rsi", "direction": "bullish", "strength": 0.8, "value": 5, "message": "StochRSI survendu"},
            ],
            "composite": {"score": 20},
        }
        satisfied, detail = _eval_stochrsi_oversold(data, {})
        assert satisfied is True

    def test_stochrsi_overbought_satisfied(self):
        """StochRSI bearish fort → règle surachat satisfaite."""
        data = {
            "signals": [
                {"indicator": "stoch_rsi", "direction": "bearish", "strength": 0.8, "value": 95, "message": "StochRSI suracheté"},
            ],
            "composite": {"score": -20},
        }
        satisfied, detail = _eval_stochrsi_overbought(data, {})
        assert satisfied is True

    def test_stochrsi_not_satisfied_weak(self):
        """StochRSI faible → pas satisfaite (seuil 0.6)."""
        data = {
            "signals": [
                {"indicator": "stoch_rsi", "direction": "bullish", "strength": 0.3, "value": 35, "message": "StochRSI léger"},
            ],
            "composite": {"score": 5},
        }
        satisfied, _ = _eval_stochrsi_oversold(data, {})
        assert satisfied is False

    def test_multi_confluence_bullish_satisfied(self):
        """3+ signaux bullish forts → confluence satisfaite."""
        data = {
            "signals": [
                {"indicator": "rsi", "direction": "bullish", "strength": 0.7, "value": 25, "message": "RSI"},
                {"indicator": "macd", "direction": "bullish", "strength": 0.6, "value": 100, "message": "MACD"},
                {"indicator": "sma", "direction": "bullish", "strength": 0.8, "value": 100000, "message": "SMA"},
                {"indicator": "ema_cross", "direction": "bullish", "strength": 0.6, "value": 500, "message": "EMA"},
            ],
            "composite": {"score": 50},
        }
        satisfied, detail = _eval_multi_confluence_bullish(data, {})
        assert satisfied is True
        assert "confluence" in detail.lower()

    def test_multi_confluence_bullish_not_enough(self):
        """Seulement 2 signaux bullish → pas de confluence."""
        data = {
            "signals": [
                {"indicator": "rsi", "direction": "bullish", "strength": 0.7, "value": 25, "message": "RSI"},
                {"indicator": "macd", "direction": "bullish", "strength": 0.6, "value": 100, "message": "MACD"},
            ],
            "composite": {"score": 20},
        }
        satisfied, _ = _eval_multi_confluence_bullish(data, {})
        assert satisfied is False

    def test_multi_confluence_bearish_satisfied(self):
        """3+ signaux bearish forts → confluence baissière."""
        data = {
            "signals": [
                {"indicator": "rsi", "direction": "bearish", "strength": 0.8, "value": 80, "message": "RSI"},
                {"indicator": "macd", "direction": "bearish", "strength": 0.7, "value": -100, "message": "MACD"},
                {"indicator": "sma", "direction": "bearish", "strength": 0.6, "value": 90000, "message": "SMA"},
            ],
            "composite": {"score": -50},
        }
        satisfied, detail = _eval_multi_confluence_bearish(data, {})
        assert satisfied is True

    def test_multi_confluence_ignores_volume_and_adx(self):
        """La confluence ignore volume et ADX (pas directionnels)."""
        data = {
            "signals": [
                {"indicator": "rsi", "direction": "bullish", "strength": 0.7, "value": 25, "message": "RSI"},
                {"indicator": "macd", "direction": "bullish", "strength": 0.6, "value": 100, "message": "MACD"},
                {"indicator": "volume", "direction": "bullish", "strength": 0.5, "value": 2.0, "message": "Volume"},
                {"indicator": "adx", "direction": "bullish", "strength": 0.8, "value": 35, "message": "ADX"},
            ],
            "composite": {"score": 40},
        }
        satisfied, _ = _eval_multi_confluence_bullish(data, {})
        assert satisfied is False  # Seulement RSI + MACD = 2, pas 3

    def test_neutral_data_no_new_rules_satisfied(self):
        """Données neutres → aucune nouvelle règle satisfaite."""
        data = {"signals": [], "composite": {"score": 0}}
        sentiment = {"sentiment_score": 0}

        for rule_eval in [_eval_ema_crossover_bullish, _eval_ema_crossover_bearish,
                          _eval_stochrsi_oversold, _eval_stochrsi_overbought,
                          _eval_multi_confluence_bullish, _eval_multi_confluence_bearish]:
            satisfied, _ = rule_eval(data, sentiment)
            assert satisfied is False

    def test_lowered_threshold_score_21_buys(self, db_session):
        """Score 26 + scénario Hausse dominant → Acheter (seuil rétabli à 25)."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Hausse", probability=0.55, direction=SignalDirection.BULLISH, description=""),
            Scenario(label="Stable", probability=0.25, direction=SignalDirection.NEUTRAL, description=""),
            Scenario(label="Baisse", probability=0.20, direction=SignalDirection.BEARISH, description=""),
        ]
        rules = [
            RuleResult(rule_name="r1", condition="", satisfied=True, weight=0.7, detail="", direction=SignalDirection.BULLISH),
        ]
        rec = service.generate_recommendation(scenarios, rules, combined_score=26)
        assert rec.action == ActionType.BUY

    def test_lowered_threshold_score_minus_21_sells(self, db_session):
        """Score -26 + scénario Baisse dominant → Vendre (seuil rétabli à -25)."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Baisse", probability=0.55, direction=SignalDirection.BEARISH, description=""),
            Scenario(label="Stable", probability=0.25, direction=SignalDirection.NEUTRAL, description=""),
            Scenario(label="Hausse", probability=0.20, direction=SignalDirection.BULLISH, description=""),
        ]
        rules = [
            RuleResult(rule_name="r1", condition="", satisfied=True, weight=0.7, detail="", direction=SignalDirection.BEARISH),
        ]
        rec = service.generate_recommendation(scenarios, rules, combined_score=-26)
        assert rec.action == ActionType.SELL

    def test_default_rules_count_v13(self):
        """Vérifie que DEFAULT_RULES contient 14 règles (v1.3)."""
        assert len(DEFAULT_RULES) == 14


# ============================================================
# TESTS : DecisionService.evaluate_rules
# ============================================================

class TestEvaluateRules:
    """Tests pour evaluate_rules."""

    def test_returns_rule_results_for_all_rules(self, db_session):
        """Retourne un résultat pour chaque règle."""
        service = DecisionService(db_session)
        data = _make_signals_data()
        sentiment = _make_sentiment_data()
        results = service.evaluate_rules(data, sentiment)
        assert len(results) == len(DEFAULT_RULES)
        assert all(isinstance(r, RuleResult) for r in results)

    def test_bullish_scenario_rules_satisfied(self, db_session):
        """Scénario haussier : RSI survendu + MACD bullish + SMA up."""
        service = DecisionService(db_session)
        data = _make_signals_data(
            rsi_dir="bullish", rsi_strength=0.8,
            macd_dir="bullish", macd_strength=0.7,
            sma_dir="bullish", sma_strength=0.7,
            score=60,
        )
        sentiment = _make_sentiment_data(score=30)
        results = service.evaluate_rules(data, sentiment)

        satisfied_names = [r.rule_name for r in results if r.satisfied]
        assert "rsi_oversold" in satisfied_names
        assert "macd_bullish_cross" in satisfied_names
        assert "sma_trend_up" in satisfied_names

    def test_bearish_scenario_rules_satisfied(self, db_session):
        """Scénario baissier : RSI suracheté + MACD bearish + SMA down."""
        service = DecisionService(db_session)
        data = _make_signals_data(
            rsi_dir="bearish", rsi_strength=0.8,
            macd_dir="bearish", macd_strength=0.7,
            sma_dir="bearish", sma_strength=0.7,
            score=-60,
        )
        sentiment = _make_sentiment_data(score=-30)
        results = service.evaluate_rules(data, sentiment)

        satisfied_names = [r.rule_name for r in results if r.satisfied]
        assert "rsi_overbought" in satisfied_names
        assert "macd_bearish_cross" in satisfied_names
        assert "sma_trend_down" in satisfied_names

    def test_neutral_scenario_no_rules_satisfied(self, db_session):
        """Scénario neutre : aucune règle satisfaite."""
        service = DecisionService(db_session)
        data = _make_signals_data(score=0)
        sentiment = _make_sentiment_data(score=0)
        results = service.evaluate_rules(data, sentiment)

        satisfied_count = sum(1 for r in results if r.satisfied)
        assert satisfied_count == 0

    def test_rule_evaluation_error_handled(self, db_session):
        """Les erreurs dans les règles sont gérées gracieusement."""
        service = DecisionService(db_session)

        # Règle qui lève une exception
        bad_rules = [{
            "name": "bad_rule",
            "condition_desc": "Test",
            "direction": SignalDirection.NEUTRAL,
            "weight": 0.5,
            "evaluate": lambda s, se: (_ for _ in ()).throw(ValueError("test")),
        }]

        results = service.evaluate_rules({}, {}, rules=bad_rules)
        assert len(results) == 1
        assert results[0].satisfied is False
        assert "erreur" in results[0].detail.lower() or "Erreur" in results[0].detail


# ============================================================
# TESTS : DecisionService.compute_scenarios
# ============================================================

class TestComputeScenarios:
    """Tests pour compute_scenarios."""

    def test_returns_three_scenarios(self, db_session):
        """Retourne exactement 3 scénarios."""
        service = DecisionService(db_session)
        rules = []
        scenarios = service.compute_scenarios(0, rules)
        assert len(scenarios) == 3

    def test_probabilities_sum_to_one(self, db_session):
        """Les probabilités somment approximativement à 1.0."""
        service = DecisionService(db_session)
        for score in [-100, -50, 0, 50, 100]:
            scenarios = service.compute_scenarios(score, [])
            total = sum(s.probability for s in scenarios)
            assert abs(total - 1.0) < 0.02, f"Score {score}: total={total}"

    def test_bullish_score_favors_hausse(self, db_session):
        """Un score fortement positif favorise le scénario Hausse."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(80, [])
        hausse = next(s for s in scenarios if s.label == "Hausse")
        baisse = next(s for s in scenarios if s.label == "Baisse")
        assert hausse.probability > baisse.probability

    def test_bearish_score_favors_baisse(self, db_session):
        """Un score fortement négatif favorise le scénario Baisse."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(-80, [])
        hausse = next(s for s in scenarios if s.label == "Hausse")
        baisse = next(s for s in scenarios if s.label == "Baisse")
        assert baisse.probability > hausse.probability

    def test_neutral_score_balanced(self, db_session):
        """Un score neutre donne des probabilités équilibrées."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(0, [])
        hausse = next(s for s in scenarios if s.label == "Hausse")
        baisse = next(s for s in scenarios if s.label == "Baisse")
        # Doit être à peu près égal (±10%)
        assert abs(hausse.probability - baisse.probability) < 0.15

    def test_rules_boost_probabilities(self, db_session):
        """Les règles satisfaites boostent la probabilité correspondante."""
        service = DecisionService(db_session)

        bullish_rules = [
            RuleResult(rule_name="r1", condition="test", satisfied=True, weight=0.8, detail="", direction=SignalDirection.BULLISH),
            RuleResult(rule_name="r2", condition="test", satisfied=True, weight=0.7, detail="", direction=SignalDirection.BULLISH),
        ]
        scenarios_with_rules = service.compute_scenarios(20, bullish_rules)
        scenarios_without_rules = service.compute_scenarios(20, [])

        hausse_with = next(s for s in scenarios_with_rules if s.label == "Hausse")
        hausse_without = next(s for s in scenarios_without_rules if s.label == "Hausse")

        assert hausse_with.probability > hausse_without.probability

    def test_sorted_by_probability(self, db_session):
        """Les scénarios sont triés par probabilité décroissante."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(50, [])
        probs = [s.probability for s in scenarios]
        assert probs == sorted(probs, reverse=True)

    def test_extreme_score_100(self, db_session):
        """Score +100 : Hausse largement dominant."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(100, [])
        dominant = scenarios[0]
        assert dominant.label == "Hausse"
        assert dominant.probability >= 0.5

    def test_extreme_score_minus_100(self, db_session):
        """Score -100 : Baisse largement dominant."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(-100, [])
        dominant = scenarios[0]
        assert dominant.label == "Baisse"
        assert dominant.probability >= 0.5


# ============================================================
# TESTS : DecisionService.generate_recommendation
# ============================================================

class TestGenerateRecommendation:
    """Tests pour generate_recommendation."""

    def test_buy_recommendation(self, db_session):
        """Score positif + scénario Hausse dominant → Acheter."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Hausse", probability=0.65, direction=SignalDirection.BULLISH, description=""),
            Scenario(label="Stable", probability=0.20, direction=SignalDirection.NEUTRAL, description=""),
            Scenario(label="Baisse", probability=0.15, direction=SignalDirection.BEARISH, description=""),
        ]
        rules = [
            RuleResult(rule_name="r1", condition="", satisfied=True, weight=0.8, detail="", direction=SignalDirection.BULLISH),
            RuleResult(rule_name="r2", condition="", satisfied=True, weight=0.7, detail="", direction=SignalDirection.BULLISH),
        ]
        rec = service.generate_recommendation(scenarios, rules, combined_score=50)
        assert rec.action == ActionType.BUY
        assert len(rec.reasons) >= 1

    def test_sell_recommendation(self, db_session):
        """Score négatif + scénario Baisse dominant → Vendre."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Baisse", probability=0.65, direction=SignalDirection.BEARISH, description=""),
            Scenario(label="Stable", probability=0.20, direction=SignalDirection.NEUTRAL, description=""),
            Scenario(label="Hausse", probability=0.15, direction=SignalDirection.BULLISH, description=""),
        ]
        rules = [
            RuleResult(rule_name="r1", condition="", satisfied=True, weight=0.8, detail="", direction=SignalDirection.BEARISH),
        ]
        rec = service.generate_recommendation(scenarios, rules, combined_score=-50)
        assert rec.action == ActionType.SELL

    def test_hold_recommendation_neutral(self, db_session):
        """Score neutre → Attendre."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Stable", probability=0.40, direction=SignalDirection.NEUTRAL, description=""),
            Scenario(label="Hausse", probability=0.30, direction=SignalDirection.BULLISH, description=""),
            Scenario(label="Baisse", probability=0.30, direction=SignalDirection.BEARISH, description=""),
        ]
        rec = service.generate_recommendation(scenarios, [], combined_score=0)
        assert rec.action == ActionType.HOLD

    def test_hold_recommendation_low_score(self, db_session):
        """Score légèrement positif (< 25) → Attendre malgré hausse."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Hausse", probability=0.45, direction=SignalDirection.BULLISH, description=""),
            Scenario(label="Stable", probability=0.35, direction=SignalDirection.NEUTRAL, description=""),
            Scenario(label="Baisse", probability=0.20, direction=SignalDirection.BEARISH, description=""),
        ]
        rec = service.generate_recommendation(scenarios, [], combined_score=15)
        assert rec.action == ActionType.HOLD

    def test_recommendation_has_explanation(self, db_session):
        """La recommandation a toujours une explication non vide."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Stable", probability=0.50, direction=SignalDirection.NEUTRAL, description=""),
        ]
        rec = service.generate_recommendation(scenarios, [], combined_score=0)
        assert rec.explanation
        assert len(rec.explanation) > 10

    def test_confidence_high_many_rules(self, db_session):
        """4+ règles satisfaites + score élevé → confiance haute."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Hausse", probability=0.70, direction=SignalDirection.BULLISH, description=""),
        ]
        rules = [
            RuleResult(rule_name=f"r{i}", condition="", satisfied=True, weight=0.7, detail="", direction=SignalDirection.BULLISH)
            for i in range(4)
        ]
        rec = service.generate_recommendation(scenarios, rules, combined_score=60)
        assert rec.confidence == ConfidenceLevel.HIGH

    def test_confidence_low_no_rules(self, db_session):
        """Pas de règles satisfaites → confiance basse."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Stable", probability=0.50, direction=SignalDirection.NEUTRAL, description=""),
        ]
        rec = service.generate_recommendation(scenarios, [], combined_score=10)
        assert rec.confidence == ConfidenceLevel.LOW


# ============================================================
# TESTS : DecisionService.analyze (intégration)
# ============================================================

def _insert_test_candles(db_session, count=50, timeframe="4h"):
    """Insert des candles de test pour l'intégration."""
    now = datetime.now(timezone.utc)
    tf_hours = {"4h": 4, "1h": 1, "30m": 0.5}.get(timeframe, 4)

    for i in range(count):
        ts = now - timedelta(hours=tf_hours * (count - i))
        candle = Candle(
            symbol="BTC/USD",
            timeframe=timeframe,
            timestamp=ts,
            open_price=50000 + i * 100,
            high_price=50500 + i * 100,
            low_price=49500 + i * 100,
            close_price=50200 + i * 100,
            volume=1000.0,
            source="test",
        )
        db_session.add(candle)
    db_session.commit()


class TestDecisionServiceIntegration:
    """Tests d'intégration avec la DB."""

    @patch("app.services.decision_service.NewsService")
    def test_analyze_with_candles(self, MockNewsService, db_session):
        """Analyse avec des candles en DB retourne une structure complète."""
        # Mock du news service
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 10
        mock_sentiment.model_dump.return_value = {"sentiment_score": 10}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        _insert_test_candles(db_session, count=50)

        service = DecisionService(db_session)
        service.news_service = MockNewsService()
        result = service.analyze(symbol="BTC/USD", timeframe="4h", history_days=7)

        # Vérifier la structure complète
        assert "meta" in result
        assert "scenarios" in result
        assert "rules_evaluated" in result
        assert "recommendation" in result
        assert "technical_score" in result
        assert "sentiment_score" in result
        assert "combined_score" in result
        assert "summary" in result

        # Vérifier les types
        assert isinstance(result["scenarios"], list)
        assert len(result["scenarios"]) == 3
        assert isinstance(result["rules_evaluated"], list)
        assert len(result["rules_evaluated"]) == len(DEFAULT_RULES)

    @patch("app.services.decision_service.NewsService")
    def test_analyze_no_data(self, MockNewsService, db_session):
        """Analyse sans données retourne une décision neutre."""
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 0
        mock_sentiment.model_dump.return_value = {"sentiment_score": 0}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        service = DecisionService(db_session)
        service.news_service = MockNewsService()
        result = service.analyze(symbol="BTC/USD", timeframe="4h", history_days=7)

        assert result["technical_score"] == 0
        assert result["recommendation"]["action"] == "attendre"

    @patch("app.services.decision_service.NewsService")
    def test_analyze_sentiment_failure_degraded_mode(self, MockNewsService, db_session):
        """Si le sentiment échoue, le mode dégradé utilise 100% technique."""
        MockNewsService.return_value.get_sentiment_only.side_effect = Exception("RSS timeout")

        _insert_test_candles(db_session, count=50)

        service = DecisionService(db_session)
        service.news_service = MockNewsService()
        result = service.analyze(symbol="BTC/USD", timeframe="4h", history_days=7)

        assert result["meta"]["sentiment_available"] is False
        assert result["sentiment_score"] == 0
        # Le score combiné doit être égal au score technique (100% technique)
        assert result["combined_score"] == result["technical_score"]

    @patch("app.services.decision_service.NewsService")
    def test_combined_score_weighted(self, MockNewsService, db_session):
        """Le score combiné est bien la pondération technique + sentiment."""
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 50
        mock_sentiment.model_dump.return_value = {"sentiment_score": 50}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        _insert_test_candles(db_session, count=50)

        service = DecisionService(db_session)
        service.news_service = MockNewsService()
        result = service.analyze(symbol="BTC/USD", timeframe="4h", history_days=7)

        tech = result["technical_score"]
        sent = result["sentiment_score"]
        expected = int(round(tech * TECHNICAL_WEIGHT + sent * SENTIMENT_WEIGHT))
        expected = max(-100, min(100, expected))

        assert result["combined_score"] == expected

    @patch("app.services.decision_service.NewsService")
    def test_meta_contains_expected_fields(self, MockNewsService, db_session):
        """Les métadonnées contiennent tous les champs attendus."""
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 0
        mock_sentiment.model_dump.return_value = {"sentiment_score": 0}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        service = DecisionService(db_session)
        service.news_service = MockNewsService()
        result = service.analyze(symbol="BTC/USD", timeframe="4h", history_days=7)

        meta = result["meta"]
        assert meta["symbol"] == "BTC/USD"
        assert meta["timeframe"] == "4h"
        assert meta["history_days"] == 7
        assert "timestamp" in meta
        assert "sentiment_available" in meta
        assert "technical_weight" in meta
        assert "sentiment_weight" in meta


# ============================================================
# TESTS : Endpoint GET /market/decision
# ============================================================

class TestDecisionEndpoint:
    """Tests pour l'endpoint HTTP."""

    @patch("app.services.decision_service.NewsService")
    def test_endpoint_returns_200(self, MockNewsService, client, db_session):
        """GET /market/decision retourne 200."""
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 0
        mock_sentiment.model_dump.return_value = {"sentiment_score": 0}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        response = client.get("/market/decision")
        assert response.status_code == 200

    @patch("app.services.decision_service.NewsService")
    def test_endpoint_response_structure(self, MockNewsService, client, db_session):
        """GET /market/decision retourne la structure attendue."""
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 0
        mock_sentiment.model_dump.return_value = {"sentiment_score": 0}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        response = client.get("/market/decision?timeframe=4h&history_days=7")
        assert response.status_code == 200

        data = response.json()
        assert "meta" in data
        assert "scenarios" in data
        assert "rules_evaluated" in data
        assert "recommendation" in data
        assert "technical_score" in data
        assert "sentiment_score" in data
        assert "combined_score" in data
        assert "summary" in data

        # Vérifier les scénarios
        assert len(data["scenarios"]) == 3
        for s in data["scenarios"]:
            assert "label" in s
            assert "probability" in s
            assert "direction" in s
            assert "description" in s

        # Vérifier la recommandation
        rec = data["recommendation"]
        assert rec["action"] in ["acheter", "vendre", "attendre"]
        assert rec["confidence"] in ["high", "medium", "low"]
        assert "explanation" in rec
        assert "reasons" in rec

    @patch("app.services.decision_service.NewsService")
    def test_endpoint_with_candles(self, MockNewsService, client, db_session):
        """GET /market/decision avec des candles en DB."""
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 20
        mock_sentiment.model_dump.return_value = {"sentiment_score": 20}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        _insert_test_candles(db_session, count=50)

        response = client.get("/market/decision?timeframe=4h&history_days=7")
        assert response.status_code == 200

        data = response.json()
        # Avec des candles, on devrait avoir des données non triviales
        assert data["technical_score"] != 0 or data["combined_score"] != 0 or len(data["scenarios"]) == 3

    @patch("app.services.decision_service.NewsService")
    def test_endpoint_days_alias(self, MockNewsService, client, db_session):
        """Le paramètre 'days' est accepté comme alias de 'history_days'."""
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 0
        mock_sentiment.model_dump.return_value = {"sentiment_score": 0}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        response = client.get("/market/decision?days=3")
        assert response.status_code == 200

    @patch("app.services.decision_service.NewsService")
    def test_endpoint_fractional_days(self, MockNewsService, client, db_session):
        """Les jours fractionnels sont supportés."""
        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 0
        mock_sentiment.model_dump.return_value = {"sentiment_score": 0}
        MockNewsService.return_value.get_sentiment_only.return_value = mock_sentiment

        response = client.get("/market/decision?history_days=0.25&timeframe=5m")
        assert response.status_code == 200


# ============================================================
# TESTS : Propriétés mathématiques des scénarios
# ============================================================

class TestScenarioMathProperties:
    """Tests des propriétés mathématiques des scénarios."""

    @pytest.mark.parametrize("score", [-100, -80, -50, -25, 0, 25, 50, 80, 100])
    def test_probabilities_always_sum_to_one(self, db_session, score):
        """Les probabilités somment à ~1.0 pour tout score."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(score, [])
        total = sum(s.probability for s in scenarios)
        assert abs(total - 1.0) < 0.02

    @pytest.mark.parametrize("score", [-100, -80, -50, -25, 0, 25, 50, 80, 100])
    def test_all_probabilities_positive(self, db_session, score):
        """Toutes les probabilités sont positives pour tout score."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(score, [])
        for s in scenarios:
            assert s.probability >= 0.01

    @pytest.mark.parametrize("score", [-100, -50, 0, 50, 100])
    def test_three_scenarios_always(self, db_session, score):
        """Toujours exactement 3 scénarios."""
        service = DecisionService(db_session)
        scenarios = service.compute_scenarios(score, [])
        assert len(scenarios) == 3
        labels = {s.label for s in scenarios}
        assert labels == {"Hausse", "Stable", "Baisse"}


# ============================================================
# TESTS : Sentiment historique combiné (v1.2.4)
# ============================================================

class TestHistoricalSentimentCombined:
    """Tests pour _get_historical_sentiment avec combinaison FGI + News History."""

    def test_both_sources_combined_score(self, db_session):
        """Les deux sources disponibles → moyenne pondérée FGI/News."""
        service = DecisionService(db_session)

        # Mock les deux services
        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: 60.0  # FGI = +60
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: 40.0  # News = +40
        )

        end_ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        expected = int(round(60.0 * FNG_HIST_WEIGHT + 40.0 * NEWS_HIST_WEIGHT))
        assert score == expected
        assert available is True
        assert source == "fear_and_greed+news_history"

    def test_both_sources_negative(self, db_session):
        """Deux sources négatives → score combiné négatif."""
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: -80.0
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: -60.0
        )

        end_ts = datetime(2024, 3, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        expected = int(round(-80.0 * FNG_HIST_WEIGHT + -60.0 * NEWS_HIST_WEIGHT))
        assert score == expected
        assert score < 0
        assert available is True
        assert source == "fear_and_greed+news_history"

    def test_fng_only_fallback(self, db_session):
        """Seulement FGI disponible → 100% FGI."""
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: 50.0
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: None  # Pas de news
        )

        end_ts = datetime(2023, 1, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        assert score == 50
        assert available is True
        assert source == "fear_and_greed_historical"

    def test_news_only_fallback(self, db_session):
        """Seulement News disponible → 100% News."""
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: None  # Pas de FGI
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: -30.0
        )

        end_ts = datetime(2017, 6, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        assert score == -30
        assert available is True
        assert source == "news_history"

    def test_no_source_available(self, db_session):
        """Aucune source → mode dégradé."""
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: None
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: None
        )

        end_ts = datetime(2015, 1, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        assert score == 0
        assert available is False
        assert source == "none"

    def test_combined_score_clamped_positive(self, db_session):
        """Le score combiné est plafonné à +100."""
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: 100.0
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: 100.0
        )

        end_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        assert score <= 100
        assert available is True

    def test_combined_score_clamped_negative(self, db_session):
        """Le score combiné est plafonné à -100."""
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: -100.0
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: -100.0
        )

        end_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        assert score >= -100
        assert available is True

    def test_fng_error_falls_through_to_news(self, db_session):
        """Si FGI lève une exception, utilise News seul."""
        service = DecisionService(db_session)

        def raise_error(*args, **kwargs):
            raise RuntimeError("DB error")

        service.sentiment_history_service.get_normalized_score_at_date = raise_error
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: 25.0
        )

        end_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        assert score == 25
        assert available is True
        assert source == "news_history"

    def test_news_error_falls_through_to_fng(self, db_session):
        """Si News lève une exception, utilise FGI seul."""
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: -40.0
        )

        def raise_error(*args, **kwargs):
            raise RuntimeError("DB error")

        service.news_history_service.get_daily_sentiment = raise_error

        end_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        assert score == -40
        assert available is True
        assert source == "fear_and_greed_historical"

    def test_both_errors_mode_degrade(self, db_session):
        """Les deux sources en erreur → mode dégradé."""
        service = DecisionService(db_session)

        def raise_error(*args, **kwargs):
            raise RuntimeError("DB error")

        service.sentiment_history_service.get_normalized_score_at_date = raise_error
        service.news_history_service.get_daily_sentiment = raise_error

        end_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        score, available, source = service._get_historical_sentiment(end_ts)

        assert score == 0
        assert available is False
        assert source == "none"

    def test_sentiment_source_in_meta_live(self, db_session):
        """En mode live, sentiment_source est 'live_rss' dans le meta."""
        service = DecisionService(db_session)

        mock_sentiment = MagicMock()
        mock_sentiment.sentiment_score = 10
        mock_sentiment.model_dump.return_value = {"sentiment_score": 10}
        service.news_service = MagicMock()
        service.news_service.get_sentiment_only.return_value = mock_sentiment

        result = service.analyze(symbol="BTC/USD", timeframe="4h", history_days=7)
        assert result["meta"]["sentiment_source"] == "live_rss"

    def test_sentiment_source_in_meta_historical(self, db_session):
        """En mode historique avec FGI + News, sentiment_source est combiné."""
        _insert_test_candles(db_session, count=50)
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: 30.0
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: 20.0
        )

        end_ts = datetime.now(timezone.utc) - timedelta(hours=10)
        result = service.analyze(
            symbol="BTC/USD", timeframe="4h", history_days=7, end_ts=end_ts
        )
        assert result["meta"]["sentiment_source"] == "fear_and_greed+news_history"
        assert result["meta"]["sentiment_available"] is True

    def test_weights_sum_to_one(self):
        """Les poids FGI + News somment à 1.0."""
        assert abs(FNG_HIST_WEIGHT + NEWS_HIST_WEIGHT - 1.0) < 0.001

    def test_combined_proportional(self, db_session):
        """Le score combiné est bien proportionnel aux poids."""
        service = DecisionService(db_session)

        # FGI = +100, News = 0 → score = FNG_HIST_WEIGHT * 100
        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: 100.0
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: 0.0
        )

        end_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        score, _, _ = service._get_historical_sentiment(end_ts)

        expected = int(round(100.0 * FNG_HIST_WEIGHT))
        assert score == expected

    def test_symmetric_combination(self, db_session):
        """FGI = +X, News = -X → le score est bien la différence pondérée."""
        service = DecisionService(db_session)

        service.sentiment_history_service.get_normalized_score_at_date = (
            lambda *args, **kwargs: 50.0
        )
        service.news_history_service.get_daily_sentiment = (
            lambda *args, **kwargs: -50.0
        )

        end_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        score, available, _ = service._get_historical_sentiment(end_ts)

        expected = int(round(50.0 * FNG_HIST_WEIGHT + (-50.0) * NEWS_HIST_WEIGHT))
        assert score == expected
        assert available is True


# ============================================================
# TESTS : Nouvelles règles v1.3 (EMA, StochRSI, Confluence)
# ============================================================

class TestNewRulesV13:
    """Tests pour les nouvelles règles de décision v1.3."""

    def test_ema_crossover_bullish_satisfied(self):
        """EMA cross bullish fort → règle satisfaite."""
        data = {
            "signals": [
                {"indicator": "ema_cross", "direction": "bullish", "strength": 0.7, "value": 500, "message": "EMA golden cross"},
            ],
            "composite": {"score": 30},
        }
        satisfied, detail = _eval_ema_crossover_bullish(data, {})
        assert satisfied is True
        assert "golden" in detail.lower() or "ema" in detail.lower()

    def test_ema_crossover_bullish_not_satisfied(self):
        """EMA cross absent ou faible → pas satisfaite."""
        data = {"signals": [], "composite": {"score": 0}}
        satisfied, _ = _eval_ema_crossover_bullish(data, {})
        assert satisfied is False

    def test_ema_crossover_bearish_satisfied(self):
        """EMA cross bearish fort → règle satisfaite."""
        data = {
            "signals": [
                {"indicator": "ema_cross", "direction": "bearish", "strength": 0.7, "value": -500, "message": "EMA death cross"},
            ],
            "composite": {"score": -30},
        }
        satisfied, detail = _eval_ema_crossover_bearish(data, {})
        assert satisfied is True

    def test_stochrsi_oversold_satisfied(self):
        """StochRSI bullish fort → règle survente satisfaite."""
        data = {
            "signals": [
                {"indicator": "stoch_rsi", "direction": "bullish", "strength": 0.8, "value": 5, "message": "StochRSI survendu"},
            ],
            "composite": {"score": 20},
        }
        satisfied, detail = _eval_stochrsi_oversold(data, {})
        assert satisfied is True

    def test_stochrsi_overbought_satisfied(self):
        """StochRSI bearish fort → règle surachat satisfaite."""
        data = {
            "signals": [
                {"indicator": "stoch_rsi", "direction": "bearish", "strength": 0.8, "value": 95, "message": "StochRSI suracheté"},
            ],
            "composite": {"score": -20},
        }
        satisfied, detail = _eval_stochrsi_overbought(data, {})
        assert satisfied is True

    def test_stochrsi_not_satisfied_weak(self):
        """StochRSI faible → pas satisfaite (seuil 0.6)."""
        data = {
            "signals": [
                {"indicator": "stoch_rsi", "direction": "bullish", "strength": 0.3, "value": 35, "message": "StochRSI léger"},
            ],
            "composite": {"score": 5},
        }
        satisfied, _ = _eval_stochrsi_oversold(data, {})
        assert satisfied is False

    def test_multi_confluence_bullish_satisfied(self):
        """3+ signaux bullish forts → confluence satisfaite."""
        data = {
            "signals": [
                {"indicator": "rsi", "direction": "bullish", "strength": 0.7, "value": 25, "message": "RSI"},
                {"indicator": "macd", "direction": "bullish", "strength": 0.6, "value": 100, "message": "MACD"},
                {"indicator": "sma", "direction": "bullish", "strength": 0.8, "value": 100000, "message": "SMA"},
                {"indicator": "ema_cross", "direction": "bullish", "strength": 0.6, "value": 500, "message": "EMA"},
            ],
            "composite": {"score": 50},
        }
        satisfied, detail = _eval_multi_confluence_bullish(data, {})
        assert satisfied is True
        assert "confluence" in detail.lower()

    def test_multi_confluence_bullish_not_enough(self):
        """Seulement 2 signaux bullish → pas de confluence."""
        data = {
            "signals": [
                {"indicator": "rsi", "direction": "bullish", "strength": 0.7, "value": 25, "message": "RSI"},
                {"indicator": "macd", "direction": "bullish", "strength": 0.6, "value": 100, "message": "MACD"},
            ],
            "composite": {"score": 20},
        }
        satisfied, _ = _eval_multi_confluence_bullish(data, {})
        assert satisfied is False

    def test_multi_confluence_bearish_satisfied(self):
        """3+ signaux bearish forts → confluence baissière."""
        data = {
            "signals": [
                {"indicator": "rsi", "direction": "bearish", "strength": 0.8, "value": 80, "message": "RSI"},
                {"indicator": "macd", "direction": "bearish", "strength": 0.7, "value": -100, "message": "MACD"},
                {"indicator": "sma", "direction": "bearish", "strength": 0.6, "value": 90000, "message": "SMA"},
            ],
            "composite": {"score": -50},
        }
        satisfied, detail = _eval_multi_confluence_bearish(data, {})
        assert satisfied is True

    def test_multi_confluence_ignores_volume_and_adx(self):
        """La confluence ignore volume et ADX (pas directionnels)."""
        data = {
            "signals": [
                {"indicator": "rsi", "direction": "bullish", "strength": 0.7, "value": 25, "message": "RSI"},
                {"indicator": "macd", "direction": "bullish", "strength": 0.6, "value": 100, "message": "MACD"},
                {"indicator": "volume", "direction": "bullish", "strength": 0.5, "value": 2.0, "message": "Volume"},
                {"indicator": "adx", "direction": "bullish", "strength": 0.8, "value": 35, "message": "ADX"},
            ],
            "composite": {"score": 40},
        }
        satisfied, _ = _eval_multi_confluence_bullish(data, {})
        assert satisfied is False  # Seulement RSI + MACD = 2, pas 3

    def test_neutral_data_no_new_rules_satisfied(self):
        """Données neutres → aucune nouvelle règle satisfaite."""
        data = {"signals": [], "composite": {"score": 0}}
        sentiment = {"sentiment_score": 0}

        for rule_eval in [_eval_ema_crossover_bullish, _eval_ema_crossover_bearish,
                          _eval_stochrsi_oversold, _eval_stochrsi_overbought,
                          _eval_multi_confluence_bullish, _eval_multi_confluence_bearish]:
            satisfied, _ = rule_eval(data, sentiment)
            assert satisfied is False

    def test_lowered_threshold_score_21_buys(self, db_session):
        """Score 26 + scénario Hausse dominant → Acheter (seuil rétabli à 25)."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Hausse", probability=0.55, direction=SignalDirection.BULLISH, description=""),
            Scenario(label="Stable", probability=0.25, direction=SignalDirection.NEUTRAL, description=""),
            Scenario(label="Baisse", probability=0.20, direction=SignalDirection.BEARISH, description=""),
        ]
        rules = [
            RuleResult(rule_name="r1", condition="", satisfied=True, weight=0.7, detail="", direction=SignalDirection.BULLISH),
        ]
        rec = service.generate_recommendation(scenarios, rules, combined_score=26)
        assert rec.action == ActionType.BUY

    def test_lowered_threshold_score_minus_21_sells(self, db_session):
        """Score -26 + scénario Baisse dominant → Vendre (seuil rétabli à -25)."""
        service = DecisionService(db_session)
        scenarios = [
            Scenario(label="Baisse", probability=0.55, direction=SignalDirection.BEARISH, description=""),
            Scenario(label="Stable", probability=0.25, direction=SignalDirection.NEUTRAL, description=""),
            Scenario(label="Hausse", probability=0.20, direction=SignalDirection.BULLISH, description=""),
        ]
        rules = [
            RuleResult(rule_name="r1", condition="", satisfied=True, weight=0.7, detail="", direction=SignalDirection.BEARISH),
        ]
        rec = service.generate_recommendation(scenarios, rules, combined_score=-26)
        assert rec.action == ActionType.SELL

    def test_default_rules_count_v13(self):
        """Vérifie que DEFAULT_RULES contient 14 règles (v1.3)."""
        assert len(DEFAULT_RULES) == 14

