"""
Tests pour le module de verification historique (Time-Travel Backtest).

Tests couverts :
- HistoryRangeResponse (plage de dates)
- VerificationService.verify_at_date (verification ponctuelle)
- VerificationService.walk_forward (analyse walk-forward)
- Endpoints HTTP (POST /backtest/verify, /backtest/walk-forward, etc.)
- Edge cases (date sans donnees, horizon hors plage, etc.)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.models import Candle
from app.services.verification_service import VerificationService
from app.schemas.verification import (
    HistoryLoadConfig,
    HistoryLoadResponse,
    HistoryRangeResponse,
    VerificationRequest,
    VerificationResult,
    WalkForwardConfig,
    WalkForwardResult,
    HorizonOutcome,
    HorizonAccuracy,
    HistoryIntegrityResponse,
    HistoryIntegrityGap,
    WalkForwardComparison,
    WalkForwardSummaryStats,
)


# =============================================================================
# Helpers : peupler la DB avec des candles de test
# =============================================================================

def _seed_candles(db, symbol="BTC/USD", timeframe="1d", days=400, start_price=10000):
    """
    Genere des candles quotidiennes simulees sur N jours.
    Le prix monte de 0.5% par jour (tendance haussiere simple).
    """
    base_date = datetime(2019, 1, 1, tzinfo=timezone.utc)
    price = start_price

    candles = []
    for i in range(days):
        ts = base_date + timedelta(days=i)
        # Simuler un leger mouvement haussier
        daily_change = 1.005 if i % 7 != 6 else 0.98  # +0.5%/j, -2% chaque 7e jour
        price *= daily_change

        candles.append(Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            open_price=round(price * 0.999, 2),
            high_price=round(price * 1.01, 2),
            low_price=round(price * 0.99, 2),
            close_price=round(price, 2),
            volume=1000.0 + i * 10,
            source="test",
        ))

    db.add_all(candles)
    db.commit()
    return candles


def _seed_minimal_candles(db, symbol="BTC/USD", timeframe="1d"):
    """Seed minimal : quelques candles pour tester les edge cases."""
    candles = [
        Candle(
            symbol=symbol, timeframe=timeframe,
            timestamp=datetime(2020, 6, 1, tzinfo=timezone.utc),
            open_price=9000, high_price=9500, low_price=8800,
            close_price=9200, volume=1000, source="test",
        ),
        Candle(
            symbol=symbol, timeframe=timeframe,
            timestamp=datetime(2020, 6, 8, tzinfo=timezone.utc),
            open_price=9200, high_price=9800, low_price=9100,
            close_price=9700, volume=1200, source="test",
        ),
        Candle(
            symbol=symbol, timeframe=timeframe,
            timestamp=datetime(2020, 7, 1, tzinfo=timezone.utc),
            open_price=9700, high_price=10500, low_price=9600,
            close_price=10200, volume=1500, source="test",
        ),
        Candle(
            symbol=symbol, timeframe=timeframe,
            timestamp=datetime(2020, 9, 1, tzinfo=timezone.utc),
            open_price=10200, high_price=11000, low_price=10000,
            close_price=10800, volume=2000, source="test",
        ),
    ]
    db.add_all(candles)
    db.commit()
    return candles


# =============================================================================
# Tests HistoryRangeResponse
# =============================================================================

class TestHistoryRange:
    """Tests pour get_history_range."""

    def test_no_data_returns_empty(self, db_session):
        """Si pas de donnees, retourne has_data=False."""
        service = VerificationService(db_session)
        result = service.get_history_range("BTC/USD", "1d")
        assert result.has_data is False
        assert result.total_candles == 0
        assert result.min_date is None
        assert result.max_date is None

    def test_with_data_returns_range(self, db_session):
        """Avec des donnees, retourne la plage correcte."""
        _seed_candles(db_session, days=100)
        service = VerificationService(db_session)
        result = service.get_history_range("BTC/USD", "1d")
        assert result.has_data is True
        assert result.total_candles == 100
        assert result.min_date is not None
        assert result.max_date is not None

    def test_different_timeframes(self, db_session):
        """Timeframes differents ne se melangent pas."""
        _seed_candles(db_session, timeframe="1d", days=50)
        _seed_candles(db_session, timeframe="4h", days=50, start_price=20000)

        service = VerificationService(db_session)
        daily = service.get_history_range("BTC/USD", "1d")
        hourly = service.get_history_range("BTC/USD", "4h")

        assert daily.total_candles == 50
        assert hourly.total_candles == 50


# =============================================================================
# Tests VerificationService.verify_at_date
# =============================================================================

class TestVerifyAtDate:
    """Tests pour la verification ponctuelle."""

    def test_no_data_returns_error(self, db_session):
        """Si pas de donnees a la date cible, retourne une erreur."""
        service = VerificationService(db_session)
        result = service.verify_at_date(VerificationRequest(
            target_date="2020-01-01",
        ))
        assert result.predicted_action == "erreur"
        assert result.price_at_date == 0

    def test_verify_returns_prediction(self, db_session):
        """Avec des donnees suffisantes, retourne une prediction."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.verify_at_date(VerificationRequest(
            target_date="2019-08-01",  # Jour 212 (suffisamment de warmup)
            history_days=200,
            horizons=[7, 30],
        ))

        assert result.price_at_date > 0
        assert result.predicted_action in ["acheter", "vendre", "attendre", "erreur"]
        assert result.predicted_score >= -100
        assert result.predicted_score <= 100

    def test_verify_returns_outcomes(self, db_session):
        """Les outcomes correspondent aux horizons demandes."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.verify_at_date(VerificationRequest(
            target_date="2019-08-01",
            horizons=[7, 30, 90],
        ))

        assert len(result.outcomes) == 3
        assert result.outcomes[0].horizon_days == 7
        assert result.outcomes[1].horizon_days == 30
        assert result.outcomes[2].horizon_days == 90

    def test_outcomes_have_actual_data(self, db_session):
        """Chaque outcome contient le prix reel, la variation et les metriques v1.2."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.verify_at_date(VerificationRequest(
            target_date="2019-06-01",
            horizons=[7],
        ))

        outcome = result.outcomes[0]
        assert outcome.end_price > 0
        assert outcome.actual_direction in ["hausse", "baisse", "stable", "inconnu"]
        assert isinstance(outcome.correct, bool)
        assert len(outcome.detail) > 0
        # Metriques v1.2
        assert 0 <= outcome.quality_score <= 100
        assert isinstance(outcome.directional_match, bool)

    def test_prediction_score_is_bounded(self, db_session):
        """Le score predit est toujours entre -100 et +100."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.verify_at_date(VerificationRequest(
            target_date="2019-07-15",
            horizons=[30],
        ))

        assert -100 <= result.predicted_score <= 100

    def test_meta_contains_technical_info(self, db_session):
        """Les metadonnees contiennent les infos techniques et la volatilite."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.verify_at_date(VerificationRequest(
            target_date="2019-08-01",
            horizons=[7],
        ))

        assert "technical_score" in result.meta
        assert "sentiment_available" in result.meta
        assert "recent_volatility" in result.meta


# =============================================================================
# Tests _is_prediction_correct
# =============================================================================

class TestPredictionCorrectness:
    """Tests pour la logique de verification des predictions (v1.2 amelioree avec volatilite adaptative)."""

    # --- Acheter ---

    def test_buy_hausse_is_correct(self, db_session):
        """Acheter + hausse = CORRECT."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct("acheter", "hausse", 5.0) is True

    def test_buy_baisse_is_incorrect(self, db_session):
        """Acheter + baisse franche = INCORRECT."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct("acheter", "baisse", -5.0) is False

    def test_buy_stable_is_correct(self, db_session):
        """Acheter + stable (petit mouvement) = CORRECT (pas de baisse franche)."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct("acheter", "stable", 0.5) is True

    def test_buy_stable_slight_negative_is_correct(self, db_session):
        """Acheter + stable avec -1% = CORRECT (stable, pas baisse)."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct("acheter", "stable", -1.0) is True

    # --- Vendre ---

    def test_sell_baisse_is_correct(self, db_session):
        """Vendre + baisse = CORRECT."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct("vendre", "baisse", -8.0) is True

    def test_sell_hausse_is_incorrect(self, db_session):
        """Vendre + hausse franche = INCORRECT."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct("vendre", "hausse", 10.0) is False

    def test_sell_stable_is_correct(self, db_session):
        """Vendre + stable = CORRECT (pas de hausse franche)."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct("vendre", "stable", -0.5) is True

    # --- Attendre : score neutre (entre -5 et +5) avec volatilite ---

    def test_hold_stable_is_correct(self, db_session):
        """Attendre (score neutre) + stable = CORRECT."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct(
            "attendre", "stable", 1.5, predicted_score=0, horizon_days=7, volatility=3.0,
        ) is True

    def test_hold_neutral_moderate_move_7d_is_correct(self, db_session):
        """Attendre (score neutre) + mouvement modere 7j = CORRECT (dans la norme de volatilite)."""
        service = VerificationService(db_session)
        # Avec vol=3%, seuil neutre 7j = max(8, 3*sqrt(7)*1.8) ≈ 14.3%
        assert service._is_prediction_correct(
            "attendre", "hausse", 12.0, predicted_score=0, horizon_days=7, volatility=3.0,
        ) is True

    def test_hold_neutral_extreme_move_7d_is_incorrect(self, db_session):
        """Attendre (score neutre) + mouvement extreme 7j = INCORRECT."""
        service = VerificationService(db_session)
        # Avec vol=3%, seuil neutre 7j ≈ 14.3% → 20% depasse
        assert service._is_prediction_correct(
            "attendre", "hausse", 20.0, predicted_score=0, horizon_days=7, volatility=3.0,
        ) is False

    def test_hold_neutral_30d_normal_move_is_correct(self, db_session):
        """Attendre (score neutre) + mouvement normal 30j = CORRECT."""
        service = VerificationService(db_session)
        # Avec vol=3%, seuil neutre 30j = max(8, 3*sqrt(30)*1.8) ≈ 29.6%
        assert service._is_prediction_correct(
            "attendre", "hausse", 25.0, predicted_score=-2, horizon_days=30, volatility=3.0,
        ) is True

    def test_hold_neutral_90d_normal_move_is_correct(self, db_session):
        """Attendre (score neutre) + mouvement normal 90j = CORRECT."""
        service = VerificationService(db_session)
        # Avec vol=3%, seuil neutre 90j = max(8, 3*sqrt(90)*1.8) ≈ 51.2%
        assert service._is_prediction_correct(
            "attendre", "hausse", 40.0, predicted_score=0, horizon_days=90, volatility=3.0,
        ) is True

    def test_hold_neutral_90d_extreme_is_incorrect(self, db_session):
        """Attendre (score neutre) + mouvement extreme 90j = INCORRECT."""
        service = VerificationService(db_session)
        # Avec vol=3%, seuil neutre 90j ≈ 51.2% → 55% depasse
        assert service._is_prediction_correct(
            "attendre", "hausse", 55.0, predicted_score=0, horizon_days=90, volatility=3.0,
        ) is False

    # --- Attendre : score avec penchant directionnel ---

    def test_hold_bearish_lean_with_baisse_is_correct(self, db_session):
        """Attendre (score -10, penchant baissier) + baisse = CORRECT."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct(
            "attendre", "baisse", -11.0, predicted_score=-10, horizon_days=90, volatility=3.0,
        ) is True

    def test_hold_bearish_lean_with_small_hausse_is_correct(self, db_session):
        """Attendre (score -10) + petite hausse 5% en 30j = CORRECT (tolerant)."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct(
            "attendre", "hausse", 5.0, predicted_score=-10, horizon_days=30, volatility=3.0,
        ) is True

    def test_hold_bearish_lean_with_big_hausse_is_incorrect(self, db_session):
        """Attendre (score -10) + forte hausse 25% en 30j = INCORRECT (depasse tolerance)."""
        service = VerificationService(db_session)
        # Avec vol=3%, tolerance 30j = max(5, 3*sqrt(30)*1.0) ≈ 16.4%
        assert service._is_prediction_correct(
            "attendre", "hausse", 25.0, predicted_score=-10, horizon_days=30, volatility=3.0,
        ) is False

    def test_hold_bullish_lean_with_hausse_is_correct(self, db_session):
        """Attendre (score +15) + hausse = CORRECT (penchant confirme)."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct(
            "attendre", "hausse", 12.0, predicted_score=15, horizon_days=30, volatility=3.0,
        ) is True

    def test_hold_bullish_lean_with_big_baisse_is_incorrect(self, db_session):
        """Attendre (score +15) + forte baisse en 30j = INCORRECT."""
        service = VerificationService(db_session)
        # Avec vol=3%, tolerance 30j ≈ 16.4% → 20% depasse
        assert service._is_prediction_correct(
            "attendre", "hausse", -20.0, predicted_score=15, horizon_days=30, volatility=3.0,
        ) is False

    # --- Cas reel : score neutre, volatilite adaptative ---

    def test_real_case_2020_hold_7d_hausse_12pct(self, db_session):
        """Cas reel: attendre (score -4) + hausse 12% en 7j = CORRECT (dans la norme)."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct(
            "attendre", "hausse", 11.9, predicted_score=-4, horizon_days=7, volatility=3.0,
        ) is True

    def test_real_case_2020_hold_30d_hausse_30pct_high_vol(self, db_session):
        """Cas reel: attendre (score -4) + hausse 30% en 30j, volatilite elevee = CORRECT."""
        service = VerificationService(db_session)
        # Avec vol=5% (haute volatilite), seuil neutre 30j = max(8, 5*sqrt(30)*1.8) ≈ 49.3%
        assert service._is_prediction_correct(
            "attendre", "hausse", 29.9, predicted_score=-4, horizon_days=30, volatility=5.0,
        ) is True

    def test_real_case_2020_hold_90d_baisse_11pct(self, db_session):
        """Cas reel: attendre (score -4) + baisse 11% en 90j = CORRECT."""
        service = VerificationService(db_session)
        assert service._is_prediction_correct(
            "attendre", "baisse", -11.0, predicted_score=-4, horizon_days=90, volatility=3.0,
        ) is True

    # --- Directional match ---

    def test_directional_match_positive(self, db_session):
        """Score positif + hausse = directional match."""
        service = VerificationService(db_session)
        assert service._check_directional_match(20, 5.0) is True

    def test_directional_match_negative(self, db_session):
        """Score negatif + baisse = directional match."""
        service = VerificationService(db_session)
        assert service._check_directional_match(-15, -8.0) is True

    def test_directional_match_neutral_small_move(self, db_session):
        """Score neutre + petit mouvement = match."""
        service = VerificationService(db_session)
        assert service._check_directional_match(2, 3.0) is True

    def test_directional_no_match(self, db_session):
        """Score positif + baisse = pas de match."""
        service = VerificationService(db_session)
        assert service._check_directional_match(20, -10.0) is False

    # --- Quality score ---

    def test_quality_score_buy_with_hausse_is_high(self, db_session):
        """Acheter + forte hausse → qualite elevee."""
        quality = VerificationService._compute_prediction_quality(
            "acheter", 50, 15.0, horizon_days=7, volatility=3.0,
        )
        assert quality >= 60

    def test_quality_score_buy_with_baisse_is_low(self, db_session):
        """Acheter + forte baisse → qualite basse."""
        quality = VerificationService._compute_prediction_quality(
            "acheter", 50, -15.0, horizon_days=7, volatility=3.0,
        )
        assert quality <= 40

    def test_quality_score_hold_stable_is_moderate(self, db_session):
        """Attendre + marche stable → qualite moderee a bonne."""
        quality = VerificationService._compute_prediction_quality(
            "attendre", 0, 2.0, horizon_days=7, volatility=3.0,
        )
        assert 40 <= quality <= 85

    # --- Volatilite adaptative ---

    def test_adaptive_thresholds_high_volatility(self, db_session):
        """Haute volatilite → seuils plus larges."""
        service = VerificationService(db_session)
        dir_thresh, neutral_thresh = service._get_adaptive_thresholds(30, 5.0)
        assert dir_thresh > 5.0  # Plus large qu'avec vol=3%
        assert neutral_thresh > 20.0

    def test_adaptive_thresholds_low_volatility(self, db_session):
        """Basse volatilite → seuils plus serres."""
        service = VerificationService(db_session)
        dir_thresh, neutral_thresh = service._get_adaptive_thresholds(30, 1.0)
        assert dir_thresh < 5.0  # Plus serre qu'avec vol=3%

    def test_adaptive_thresholds_none_uses_default(self, db_session):
        """Pas de volatilite → utilise le defaut (3%)."""
        service = VerificationService(db_session)
        dir_thresh, neutral_thresh = service._get_adaptive_thresholds(30, None)
        assert dir_thresh > 0
        assert neutral_thresh > 0


# =============================================================================
# Tests WalkForward
# =============================================================================

class TestWalkForward:
    """Tests pour l'analyse walk-forward."""

    def test_walk_forward_no_data(self, db_session):
        """Walk-forward sans donnees retourne 0 points."""
        service = VerificationService(db_session)
        result = service.walk_forward(WalkForwardConfig(
            start_date="2020-01-01",
            end_date="2020-06-01",
            step_days=30,
        ))
        assert result.total_points == 0

    def test_walk_forward_with_data(self, db_session):
        """Walk-forward avec donnees retourne des points."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.walk_forward(WalkForwardConfig(
            start_date="2019-08-01",
            end_date="2019-12-01",
            step_days=30,
            horizons=[7, 30],
        ))

        assert result.total_points > 0
        assert len(result.accuracy_by_horizon) == 2
        assert result.duration_seconds >= 0

    def test_walk_forward_accuracy_structure(self, db_session):
        """Les metriques d'accuracy sont bien structurees (v1.2 avec metriques avancees)."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.walk_forward(WalkForwardConfig(
            start_date="2019-08-01",
            end_date="2019-11-01",
            step_days=30,
            horizons=[7],
        ))

        if result.accuracy_by_horizon:
            acc = result.accuracy_by_horizon[0]
            assert acc.horizon_days == 7
            assert 0 <= acc.accuracy_pct <= 100
            assert acc.total_points >= 0
            assert acc.correct + acc.incorrect == acc.total_points
            # Metriques v1.2
            assert 0 <= acc.directional_accuracy_pct <= 100
            assert 0 <= acc.avg_quality_score <= 100
            assert 0 <= acc.profitable_direction_pct <= 100
            assert acc.high_confidence_count >= 0

    def test_walk_forward_has_summary(self, db_session):
        """Le walk-forward genere un resume."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.walk_forward(WalkForwardConfig(
            start_date="2019-08-01",
            end_date="2019-10-01",
            step_days=30,
            horizons=[7],
        ))

        assert len(result.summary) > 0

    def test_walk_forward_points_have_outcomes(self, db_session):
        """Chaque point du walk-forward a des outcomes."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.walk_forward(WalkForwardConfig(
            start_date="2019-08-01",
            end_date="2019-10-01",
            step_days=30,
            horizons=[7, 30],
        ))

        for point in result.points:
            assert len(point.outcomes) <= 2  # 7j et 30j


# =============================================================================
# Tests Schemas
# =============================================================================

class TestSchemas:
    """Tests pour les schemas de verification."""

    def test_history_load_config_defaults(self):
        config = HistoryLoadConfig()
        assert config.symbol == "BTC/USD"
        assert config.timeframe == "1d"
        assert config.start_date == "2017-08-17"

    def test_verification_request_defaults(self):
        req = VerificationRequest(target_date="2020-01-01")
        assert req.symbol == "BTC/USD"
        assert req.timeframe == "1d"
        assert req.history_days == 200
        assert req.horizons == [7, 30, 90]

    def test_walk_forward_config_defaults(self):
        config = WalkForwardConfig(
            start_date="2018-01-01",
            end_date="2025-12-31",
        )
        assert config.step_days == 30
        assert config.horizons == [7, 30, 90]

    def test_horizon_outcome_model(self):
        outcome = HorizonOutcome(
            horizon_days=30,
            end_date="2020-02-01",
            end_price=9500,
            actual_change_pct=5.4,
            actual_direction="hausse",
            predicted_action="acheter",
            predicted_score=42,
            correct=True,
            quality_score=75.0,
            directional_match=True,
            detail="Test",
        )
        assert outcome.correct is True
        assert outcome.quality_score == 75.0
        assert outcome.directional_match is True

    def test_horizon_accuracy_model(self):
        acc = HorizonAccuracy(
            horizon_days=30,
            total_points=10,
            correct=7,
            incorrect=3,
            accuracy_pct=70.0,
            directional_accuracy_pct=75.0,
            avg_quality_score=62.5,
            high_confidence_accuracy_pct=80.0,
            high_confidence_count=5,
            profitable_direction_pct=72.0,
        )
        assert acc.accuracy_pct == 70.0
        assert acc.directional_accuracy_pct == 75.0
        assert acc.avg_quality_score == 62.5

    def test_history_range_response_model(self):
        resp = HistoryRangeResponse(
            symbol="BTC/USD",
            timeframe="1d",
            has_data=True,
            total_candles=3000,
            min_date="2017-08-17T00:00:00+00:00",
            max_date="2026-04-04T00:00:00+00:00",
        )
        assert resp.has_data is True


# =============================================================================
# Tests Endpoints HTTP
# =============================================================================

class TestEndpoints:
    """Tests pour les endpoints API de verification."""

    def test_get_history_range_no_data(self, client):
        """GET /backtest/history/range sans donnees."""
        response = client.get("/backtest/history/range?symbol=BTC/USD&timeframe=1d")
        assert response.status_code == 200
        data = response.json()
        assert data["has_data"] is False

    def test_get_history_range_with_data(self, client, db_session):
        """GET /backtest/history/range avec donnees."""
        _seed_candles(db_session, days=50)
        response = client.get("/backtest/history/range?symbol=BTC/USD&timeframe=1d")
        assert response.status_code == 200
        data = response.json()
        assert data["has_data"] is True
        assert data["total_candles"] == 50

    def test_verify_no_data(self, client):
        """POST /backtest/verify sans donnees retourne erreur gracieuse."""
        response = client.post("/backtest/verify", json={
            "target_date": "2020-01-01",
            "horizons": [7],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["predicted_action"] == "erreur"

    def test_verify_with_data(self, client, db_session):
        """POST /backtest/verify avec donnees retourne une prediction."""
        _seed_candles(db_session, days=400)
        response = client.post("/backtest/verify", json={
            "target_date": "2019-08-01",
            "horizons": [7, 30],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["price_at_date"] > 0
        assert len(data["outcomes"]) == 2

    def test_walk_forward_endpoint(self, client, db_session):
        """POST /backtest/walk-forward retourne des resultats avec metriques v1.2."""
        _seed_candles(db_session, days=400)
        response = client.post("/backtest/walk-forward", json={
            "start_date": "2019-08-01",
            "end_date": "2019-10-01",
            "step_days": 30,
            "horizons": [7],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_points"] >= 0
        assert "accuracy_by_horizon" in data
        assert "summary" in data
        assert "overall_quality_score" in data


# =============================================================================
# Tests HistoryLoader (mock Binance)
# =============================================================================

class TestHistoryLoaderEndpoint:
    """Tests pour l'endpoint de chargement d'historique (avec mock Binance)."""

    def test_load_history_endpoint_structure(self, client, db_session):
        """POST /backtest/history/load avec mock retourne la bonne structure."""
        from datetime import datetime, timezone

        mock_candles = [
            {
                "timestamp": datetime(2020, 1, 1, tzinfo=timezone.utc),
                "open": 7200, "high": 7300, "low": 7100,
                "close": 7250, "volume": 1000,
            },
            {
                "timestamp": datetime(2020, 1, 2, tzinfo=timezone.utc),
                "open": 7250, "high": 7400, "low": 7200,
                "close": 7350, "volume": 1100,
            },
        ]

        async def mock_get_ohlcv(**kwargs):
            return mock_candles

        with patch(
            "app.services.history_loader_service.BinanceService"
        ) as MockBinance:
            instance = MockBinance.return_value
            instance.get_ohlcv = mock_get_ohlcv

            response = client.post("/backtest/history/load", json={
                "symbol": "BTC/USD",
                "timeframe": "1d",
                "start_date": "2020-01-01",
                "end_date": "2020-01-03",
            })

            assert response.status_code == 200
            data = response.json()
            assert "fetched" in data
            assert "inserted" in data
            assert data["fetched"] == 2


# =============================================================================
# Tests Intégrité de l'historique
# =============================================================================

class TestHistoryIntegrity:
    """Tests pour check_integrity — détection des trous dans l'historique."""

    def test_integrity_no_data(self, db_session):
        """Sans données, retourne grade UNKNOWN."""
        service = VerificationService(db_session)
        result = service.check_integrity("BTC/USD", "1d")
        assert result.quality_grade == "UNKNOWN"
        assert result.total_candles == 0

    def test_integrity_complete_data(self, db_session):
        """Avec données complètes, retourne grade EXCELLENT."""
        # Seed 100 jours consécutifs sans trou
        _seed_candles(db_session, days=100)
        service = VerificationService(db_session)
        result = service.check_integrity("BTC/USD", "1d")

        assert result.quality_grade == "EXCELLENT"
        assert result.completeness_pct >= 99
        assert result.total_candles == 100
        assert len(result.gaps) == 0

    def test_integrity_with_gaps(self, db_session):
        """Avec des trous, détecte les jours manquants."""
        # Créer des candles avec un trou de 5 jours au milieu
        base_date = datetime(2019, 1, 1, tzinfo=timezone.utc)
        candles = []
        for i in range(100):
            # Skip les jours 30 à 34 (5 jours de trou)
            if 30 <= i <= 34:
                continue
            ts = base_date + timedelta(days=i)
            candles.append(Candle(
                symbol="BTC/USD", timeframe="1d", timestamp=ts,
                open_price=10000, high_price=10100, low_price=9900,
                close_price=10050, volume=1000, source="test",
            ))
        db_session.add_all(candles)
        db_session.commit()

        service = VerificationService(db_session)
        result = service.check_integrity("BTC/USD", "1d")

        assert result.missing_candles == 5
        assert len(result.gaps) >= 1
        assert result.quality_grade in ("GOOD", "EXCELLENT")
        assert result.completeness_pct < 100

    def test_integrity_critical_gaps(self, db_session):
        """Avec beaucoup de trous, retourne grade CRITICAL ou WARNING."""
        # Seed seulement tous les 3 jours sur 100 jours → ~33% complet
        base_date = datetime(2019, 1, 1, tzinfo=timezone.utc)
        candles = []
        for i in range(0, 100, 3):
            ts = base_date + timedelta(days=i)
            candles.append(Candle(
                symbol="BTC/USD", timeframe="1d", timestamp=ts,
                open_price=10000, high_price=10100, low_price=9900,
                close_price=10050, volume=1000, source="test",
            ))
        db_session.add_all(candles)
        db_session.commit()

        service = VerificationService(db_session)
        result = service.check_integrity("BTC/USD", "1d")

        assert result.quality_grade == "CRITICAL"
        assert result.missing_candles > 50
        assert result.completeness_pct < 50

    def test_integrity_response_has_min_max_date(self, db_session):
        """Le résultat contient les dates min/max."""
        _seed_candles(db_session, days=50)
        service = VerificationService(db_session)
        result = service.check_integrity("BTC/USD", "1d")
        assert result.min_date is not None
        assert result.max_date is not None

    def test_integrity_different_timeframes(self, db_session):
        """L'intégrité est vérifiée par timeframe sans mélanger."""
        _seed_candles(db_session, timeframe="1d", days=50)
        service = VerificationService(db_session)

        daily = service.check_integrity("BTC/USD", "1d")
        hourly = service.check_integrity("BTC/USD", "4h")

        assert daily.total_candles == 50
        assert hourly.total_candles == 0
        assert hourly.quality_grade == "UNKNOWN"


class TestIntegrityEndpoint:
    """Tests pour l'endpoint GET /backtest/history/integrity."""

    def test_integrity_endpoint_no_data(self, client):
        """GET /backtest/history/integrity sans données."""
        response = client.get("/backtest/history/integrity?symbol=BTC/USD&timeframe=1d")
        assert response.status_code == 200
        data = response.json()
        assert data["quality_grade"] == "UNKNOWN"
        assert data["total_candles"] == 0

    def test_integrity_endpoint_with_data(self, client, db_session):
        """GET /backtest/history/integrity avec données."""
        _seed_candles(db_session, days=100)
        response = client.get("/backtest/history/integrity?symbol=BTC/USD&timeframe=1d")
        assert response.status_code == 200
        data = response.json()
        assert data["quality_grade"] in ("EXCELLENT", "GOOD", "WARNING", "CRITICAL")
        assert data["total_candles"] == 100
        assert "completeness_pct" in data
        assert "gaps" in data
        assert "detail" in data


# =============================================================================
# Tests Walk-Forward comparatif (compare_mode)
# =============================================================================

class TestWalkForwardCompare:
    """Tests pour le walk-forward en mode comparatif (technique-only vs technique+sentiment)."""

    def test_walk_forward_without_compare_mode(self, db_session):
        """Sans compare_mode, comparison est None."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.walk_forward(WalkForwardConfig(
            start_date="2019-08-01",
            end_date="2019-10-01",
            step_days=30,
            horizons=[7],
            compare_mode=False,
        ))

        assert result.comparison is None

    def test_walk_forward_with_compare_mode(self, db_session):
        """Avec compare_mode=True, comparison est remplie."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.walk_forward(WalkForwardConfig(
            start_date="2019-08-01",
            end_date="2019-10-01",
            step_days=30,
            horizons=[7],
            compare_mode=True,
        ))

        assert result.comparison is not None
        assert result.comparison.technical_only is not None
        assert result.comparison.with_sentiment is not None
        assert isinstance(result.comparison.sentiment_delta_accuracy_pct, float)
        assert isinstance(result.comparison.sentiment_delta_quality, float)
        assert len(result.comparison.verdict) > 0

    def test_compare_mode_has_accuracy_by_horizon(self, db_session):
        """Le mode comparatif a les accuracy par horizon pour les deux modes."""
        _seed_candles(db_session, days=400)
        service = VerificationService(db_session)

        result = service.walk_forward(WalkForwardConfig(
            start_date="2019-08-01",
            end_date="2019-10-01",
            step_days=30,
            horizons=[7],
            compare_mode=True,
        ))

        comp = result.comparison
        assert len(comp.technical_only.accuracy_by_horizon) > 0
        assert len(comp.with_sentiment.accuracy_by_horizon) > 0

    def test_compare_mode_endpoint(self, client, db_session):
        """POST /backtest/walk-forward avec compare_mode=true retourne comparison."""
        _seed_candles(db_session, days=400)
        response = client.post("/backtest/walk-forward", json={
            "start_date": "2019-08-01",
            "end_date": "2019-10-01",
            "step_days": 30,
            "horizons": [7],
            "compare_mode": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["comparison"] is not None
        assert "technical_only" in data["comparison"]
        assert "with_sentiment" in data["comparison"]
        assert "verdict" in data["comparison"]


# =============================================================================
# Tests : find_interesting_dates
# =============================================================================

def _seed_extreme_candles(db, symbol="BTC/USD", timeframe="1d"):
    """
    Genere 300 candles quotidiennes avec des patterns extremes :
    - Jour 220-230 : crash brutal (-5%/j) → RSI survendu
    - Jour 260-270 : rally (+4%/j) → RSI suracheté
    """
    import math
    base_date = datetime(2019, 1, 1, tzinfo=timezone.utc)
    price = 10000.0

    candles = []
    for i in range(300):
        ts = base_date + timedelta(days=i)

        # Phase normale : +0.2%/j avec bruit
        if 220 <= i <= 230:
            # Crash : -5%/j
            daily_change = 0.95
        elif 260 <= i <= 270:
            # Rally : +4%/j
            daily_change = 1.04
        elif i % 7 == 6:
            daily_change = 0.99
        else:
            daily_change = 1.002

        price *= daily_change
        price = max(100, price)

        # High/Low plus larges pendant les crashes/rallies
        hl_spread = 0.03 if (220 <= i <= 230 or 260 <= i <= 270) else 0.01

        candles.append(Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            open_price=round(price * (1 - hl_spread * 0.5), 2),
            high_price=round(price * (1 + hl_spread), 2),
            low_price=round(price * (1 - hl_spread), 2),
            close_price=round(price, 2),
            volume=1000.0 + i * 10,
            source="test",
        ))

    db.add_all(candles)
    db.commit()
    return candles


class TestFindInterestingDates:
    """Tests pour VerificationService.find_interesting_dates."""

    def test_no_data_returns_empty(self, db_session):
        """Sans données, retourne une liste vide."""
        service = VerificationService(db_session)
        result = service.find_interesting_dates(timeframe="1d")

        assert result.dates == []
        assert result.total_found == 0
        assert result.duration_seconds >= 0

    def test_insufficient_data_returns_empty(self, db_session):
        """Avec trop peu de candles (< 200), retourne vide."""
        _seed_minimal_candles(db_session)
        service = VerificationService(db_session)
        result = service.find_interesting_dates(timeframe="1d")

        assert result.dates == []
        assert result.total_scanned < 200

    def test_finds_extreme_dates(self, db_session):
        """Avec données extremes, trouve des dates interessantes."""
        _seed_extreme_candles(db_session)
        service = VerificationService(db_session)

        result = service.find_interesting_dates(
            timeframe="1d",
            min_strength=0.6,
            max_results=20,
            step_days=1,
        )

        assert result.total_scanned > 0
        assert result.total_found >= 0  # Peut trouver ou non selon les calculs

        # Si des dates sont trouvées, vérifier la structure
        if result.dates:
            item = result.dates[0]
            assert 0 < item.interest_score <= 100
            assert item.price > 0
            assert len(item.date) >= 10
            assert item.dominant_direction in ("bullish", "bearish", "mixed")
            assert len(item.signals) > 0
            assert len(item.label) > 0

            # Les signals doivent avoir la bonne structure
            sig = item.signals[0]
            assert sig.indicator in ("rsi", "macd", "sma", "bollinger")
            assert sig.direction in ("bullish", "bearish", "neutral")
            assert 0 <= sig.strength <= 1
            assert len(sig.message) > 0

    def test_max_results_respected(self, db_session):
        """Le nombre de résultats est limité par max_results."""
        _seed_extreme_candles(db_session)
        service = VerificationService(db_session)

        result = service.find_interesting_dates(
            timeframe="1d",
            min_strength=0.3,  # Seuil bas pour beaucoup de résultats
            max_results=5,
            step_days=1,
        )

        assert len(result.dates) <= 5

    def test_sorted_by_interest_score(self, db_session):
        """Les dates sont triées par score d'intérêt décroissant."""
        _seed_extreme_candles(db_session)
        service = VerificationService(db_session)

        result = service.find_interesting_dates(
            timeframe="1d",
            min_strength=0.3,
            max_results=20,
            step_days=1,
        )

        if len(result.dates) >= 2:
            scores = [d.interest_score for d in result.dates]
            assert scores == sorted(scores, reverse=True)

    def test_duration_tracked(self, db_session):
        """Le temps de scan est mesuré."""
        _seed_extreme_candles(db_session)
        service = VerificationService(db_session)

        result = service.find_interesting_dates(timeframe="1d", step_days=5)
        assert result.duration_seconds >= 0
        assert result.timeframe == "1d"

    def test_high_min_strength_filters_more(self, db_session):
        """Un seuil de force élevé filtre plus de dates."""
        _seed_extreme_candles(db_session)
        service = VerificationService(db_session)

        low_thresh = service.find_interesting_dates(
            timeframe="1d", min_strength=0.3, step_days=1,
        )
        high_thresh = service.find_interesting_dates(
            timeframe="1d", min_strength=0.9, step_days=1,
        )

        assert high_thresh.total_found <= low_thresh.total_found


class TestInterestingDatesEndpoint:
    """Tests endpoint HTTP GET /backtest/interesting-dates."""

    def test_endpoint_returns_200(self, client):
        """L'endpoint retourne 200 même sans données."""
        resp = client.get("/backtest/interesting-dates?timeframe=1d")
        assert resp.status_code == 200
        data = resp.json()
        assert "dates" in data
        assert "total_scanned" in data
        assert "total_found" in data
        assert "duration_seconds" in data

    def test_endpoint_with_data(self, client, db_session):
        """L'endpoint retourne des résultats avec des données."""
        _seed_extreme_candles(db_session)
        resp = client.get(
            "/backtest/interesting-dates?timeframe=1d&min_strength=0.3&step_days=1&max_results=10"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["dates"], list)
        assert data["timeframe"] == "1d"
        assert data["min_strength"] == 0.3

    def test_endpoint_custom_params(self, client):
        """L'endpoint accepte les paramètres personnalisés."""
        resp = client.get(
            "/backtest/interesting-dates?symbol=BTC/USD&timeframe=4h&min_strength=0.5&max_results=5&step_days=7"
        )
        assert resp.status_code == 200
