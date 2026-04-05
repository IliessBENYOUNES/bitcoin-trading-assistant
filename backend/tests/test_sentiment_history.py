"""
Tests pour le module de sentiment historique (v1.2).

Couvre :
1. Modèle SentimentHistory (création, contraintes)
2. Normalisation Fear & Greed (0-100 → -100/+100)
3. Service : chargement (mock API), requête par date, plage, couverture
4. Intégration avec le DecisionService (sentiment historique en mode backtest)
5. Endpoints API (/sentiment/history/*)
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.models.sentiment_history import SentimentHistory
from app.services.sentiment_history_service import (
    SentimentHistoryService,
    FEAR_AND_GREED_SOURCE,
)
from app.schemas.sentiment import (
    SentimentLoadConfig,
    SentimentLoadResponse,
    SentimentRangeResponse,
    SentimentAtDateResponse,
    SentimentCoverageResponse,
)


# ============================================================
# HELPERS
# ============================================================

def _insert_sentiment_point(db, date_str, raw_score, source="fear_and_greed", label="Neutral"):
    """Helper pour insérer un point de sentiment en base."""
    dt = datetime.fromisoformat(date_str).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    normalized = (raw_score - 50) * 2
    entry = SentimentHistory(
        date=dt,
        source=source,
        raw_score=raw_score,
        normalized_score=normalized,
        label=label,
        raw_data=json.dumps({"value": str(int(raw_score)), "value_classification": label}),
    )
    db.add(entry)
    db.commit()
    return entry


def _insert_multiple_sentiment(db, points):
    """Insère plusieurs points de sentiment. points = [(date_str, raw_score, label), ...]"""
    for date_str, raw_score, label in points:
        _insert_sentiment_point(db, date_str, raw_score, label=label)


# ============================================================
# MODÈLE
# ============================================================

class TestSentimentHistoryModel:
    """Tests du modèle SQLAlchemy SentimentHistory."""

    def test_create_sentiment_point(self, db_session):
        """Création d'un point de sentiment en base."""
        entry = _insert_sentiment_point(db_session, "2020-06-01", 45.0, label="Fear")
        assert entry.id is not None
        assert entry.raw_score == 45.0
        assert entry.normalized_score == -10.0  # (45-50)*2
        assert entry.label == "Fear"
        assert entry.source == "fear_and_greed"

    def test_unique_constraint_date_source(self, db_session):
        """Un seul point par (date, source)."""
        _insert_sentiment_point(db_session, "2020-06-01", 45.0)
        with pytest.raises(Exception):
            _insert_sentiment_point(db_session, "2020-06-01", 50.0)

    def test_different_sources_same_date(self, db_session):
        """Deux sources différentes peuvent avoir un point à la même date."""
        _insert_sentiment_point(db_session, "2020-06-01", 45.0, source="fear_and_greed")
        _insert_sentiment_point(db_session, "2020-06-01", 60.0, source="cryptocompare_news")
        count = db_session.query(SentimentHistory).count()
        assert count == 2

    def test_repr(self, db_session):
        """Représentation textuelle du modèle."""
        entry = _insert_sentiment_point(db_session, "2020-06-01", 45.0)
        repr_str = repr(entry)
        assert "SentimentHistory" in repr_str
        assert "fear_and_greed" in repr_str


# ============================================================
# NORMALISATION
# ============================================================

class TestNormalization:
    """Tests de la normalisation Fear & Greed → -100/+100."""

    def test_normalize_extreme_fear(self):
        """0 (peur extrême) → -100."""
        assert SentimentHistoryService.normalize_fear_and_greed(0) == -100.0

    def test_normalize_neutral(self):
        """50 (neutre) → 0."""
        assert SentimentHistoryService.normalize_fear_and_greed(50) == 0.0

    def test_normalize_extreme_greed(self):
        """100 (avidité extrême) → +100."""
        assert SentimentHistoryService.normalize_fear_and_greed(100) == 100.0

    def test_normalize_fear(self):
        """25 (peur) → -50."""
        assert SentimentHistoryService.normalize_fear_and_greed(25) == -50.0

    def test_normalize_greed(self):
        """75 (avidité) → +50."""
        assert SentimentHistoryService.normalize_fear_and_greed(75) == 50.0

    def test_normalize_boundary_values(self):
        """Valeurs limites et intermédiaires."""
        assert SentimentHistoryService.normalize_fear_and_greed(10) == -80.0
        assert SentimentHistoryService.normalize_fear_and_greed(90) == 80.0
        assert SentimentHistoryService.normalize_fear_and_greed(50) == 0.0


# ============================================================
# SERVICE : REQUÊTE PAR DATE
# ============================================================

class TestGetSentimentAtDate:
    """Tests de get_sentiment_at_date."""

    def test_exact_match(self, db_session):
        """Correspondance exacte à la date demandée."""
        _insert_sentiment_point(db_session, "2020-06-01", 25.0, label="Extreme Fear")
        service = SentimentHistoryService(db_session)
        result = service.get_sentiment_at_date("2020-06-01")
        assert result is not None
        assert result.exact_match is True
        assert result.raw_score == 25.0
        assert result.normalized_score == -50.0
        assert result.label == "Extreme Fear"

    def test_approximate_match(self, db_session):
        """Correspondance approximative dans la fenêtre de tolérance."""
        _insert_sentiment_point(db_session, "2020-06-02", 30.0, label="Fear")
        service = SentimentHistoryService(db_session)
        result = service.get_sentiment_at_date("2020-06-01")
        assert result is not None
        assert result.exact_match is False
        assert result.raw_score == 30.0

    def test_no_match(self, db_session):
        """Aucun point disponible dans la fenêtre."""
        _insert_sentiment_point(db_session, "2020-01-01", 50.0)
        service = SentimentHistoryService(db_session)
        result = service.get_sentiment_at_date("2020-06-01")
        assert result is None

    def test_closest_point_selected(self, db_session):
        """Sélectionne le point le plus proche de la date demandée."""
        _insert_sentiment_point(db_session, "2020-05-30", 20.0, label="Extreme Fear")
        _insert_sentiment_point(db_session, "2020-06-02", 80.0, label="Extreme Greed")
        service = SentimentHistoryService(db_session)
        result = service.get_sentiment_at_date("2020-06-01")
        assert result is not None
        # 2020-06-02 est plus proche de 2020-06-01 que 2020-05-30
        assert result.raw_score == 80.0

    def test_get_normalized_score_shortcut(self, db_session):
        """Méthode raccourci pour le DecisionService."""
        _insert_sentiment_point(db_session, "2020-06-01", 75.0)
        service = SentimentHistoryService(db_session)
        score = service.get_normalized_score_at_date("2020-06-01")
        assert score == 50.0  # (75-50)*2

    def test_get_normalized_score_not_found(self, db_session):
        """Retourne None si aucun sentiment disponible."""
        service = SentimentHistoryService(db_session)
        score = service.get_normalized_score_at_date("2020-06-01")
        assert score is None


# ============================================================
# SERVICE : PLAGE DE DATES
# ============================================================

class TestGetRange:
    """Tests de get_range."""

    def test_empty_db(self, db_session):
        """Plage vide quand pas de données."""
        service = SentimentHistoryService(db_session)
        result = service.get_range()
        assert result.has_data is False
        assert result.total_points == 0

    def test_with_data(self, db_session):
        """Plage correcte avec des données."""
        _insert_multiple_sentiment(db_session, [
            ("2020-01-01", 30.0, "Fear"),
            ("2020-06-01", 50.0, "Neutral"),
            ("2020-12-31", 80.0, "Extreme Greed"),
        ])
        service = SentimentHistoryService(db_session)
        result = service.get_range()
        assert result.has_data is True
        assert result.total_points == 3
        assert result.min_date is not None
        assert result.max_date is not None


# ============================================================
# SERVICE : COUVERTURE GLOBALE
# ============================================================

class TestGetCoverage:
    """Tests de get_coverage."""

    def test_empty_db(self, db_session):
        """Couverture vide."""
        service = SentimentHistoryService(db_session)
        result = service.get_coverage()
        assert result.total_points == 0
        assert len(result.sources) == 0

    def test_single_source(self, db_session):
        """Couverture avec une source."""
        _insert_multiple_sentiment(db_session, [
            ("2020-01-01", 30.0, "Fear"),
            ("2020-06-01", 50.0, "Neutral"),
        ])
        service = SentimentHistoryService(db_session)
        result = service.get_coverage()
        assert result.total_points == 2
        assert len(result.sources) == 1
        assert result.sources[0].source == "fear_and_greed"

    def test_multiple_sources(self, db_session):
        """Couverture avec plusieurs sources."""
        _insert_sentiment_point(db_session, "2020-01-01", 30.0, source="fear_and_greed")
        _insert_sentiment_point(db_session, "2020-01-01", 60.0, source="cryptocompare_news")
        service = SentimentHistoryService(db_session)
        result = service.get_coverage()
        assert result.total_points == 2
        assert len(result.sources) == 2


# ============================================================
# SERVICE : CHARGEMENT FEAR & GREED (Mock API)
# ============================================================

class TestLoadFearAndGreed:
    """Tests du chargement Fear & Greed avec mock de l'API Alternative.me."""

    @patch("app.services.sentiment_history_service.httpx.get")
    def test_load_success(self, mock_get, db_session):
        """Chargement réussi avec données mockées."""
        # Simuler la réponse de l'API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"value": "25", "value_classification": "Extreme Fear", "timestamp": "1580515200"},  # 2020-02-01
                {"value": "50", "value_classification": "Neutral", "timestamp": "1580601600"},  # 2020-02-02
                {"value": "75", "value_classification": "Greed", "timestamp": "1580688000"},  # 2020-02-03
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        service = SentimentHistoryService(db_session)
        result = service.load_fear_and_greed()

        assert result.fetched == 3
        assert result.inserted == 3
        assert result.updated == 0
        assert result.skipped == 0
        assert result.total_in_db == 3
        assert result.source == "fear_and_greed"

    @patch("app.services.sentiment_history_service.httpx.get")
    def test_load_idempotent(self, mock_get, db_session):
        """Relancer le chargement ne crée pas de doublons."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"value": "25", "value_classification": "Extreme Fear", "timestamp": "1580515200"},
                {"value": "50", "value_classification": "Neutral", "timestamp": "1580601600"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        service = SentimentHistoryService(db_session)

        # Premier chargement
        r1 = service.load_fear_and_greed()
        assert r1.inserted == 2

        # Deuxième chargement (identique)
        r2 = service.load_fear_and_greed()
        assert r2.inserted == 0
        assert r2.skipped == 2
        assert r2.total_in_db == 2

    @patch("app.services.sentiment_history_service.httpx.get")
    def test_load_update_changed_value(self, mock_get, db_session):
        """Si la valeur a changé, le point est mis à jour."""
        # Premier chargement
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"value": "25", "value_classification": "Extreme Fear", "timestamp": "1580515200"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        service = SentimentHistoryService(db_session)
        r1 = service.load_fear_and_greed()
        assert r1.inserted == 1

        # Deuxième chargement avec valeur modifiée
        mock_response.json.return_value = {
            "data": [
                {"value": "30", "value_classification": "Fear", "timestamp": "1580515200"},
            ]
        }
        r2 = service.load_fear_and_greed()
        assert r2.updated == 1
        assert r2.inserted == 0

    @patch("app.services.sentiment_history_service.httpx.get")
    def test_load_api_error(self, mock_get, db_session):
        """Gestion propre des erreurs API."""
        import httpx as httpx_module
        mock_get.side_effect = httpx_module.HTTPError("Connection refused")

        service = SentimentHistoryService(db_session)
        result = service.load_fear_and_greed()
        assert result.fetched == 0
        assert result.inserted == 0

    @patch("app.services.sentiment_history_service.httpx.get")
    def test_load_empty_response(self, mock_get, db_session):
        """Gestion d'une réponse vide."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        service = SentimentHistoryService(db_session)
        result = service.load_fear_and_greed()
        assert result.fetched == 0

    @patch("app.services.sentiment_history_service.httpx.get")
    def test_load_with_date_filter(self, mock_get, db_session):
        """Filtrage par date lors du chargement."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"value": "25", "value_classification": "Extreme Fear", "timestamp": "1577836800"},  # 2020-01-01
                {"value": "50", "value_classification": "Neutral", "timestamp": "1590969600"},  # 2020-06-01
                {"value": "75", "value_classification": "Greed", "timestamp": "1609459200"},  # 2021-01-01
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        service = SentimentHistoryService(db_session)
        config = SentimentLoadConfig(
            source="fear_and_greed",
            start_date="2020-03-01",
            end_date="2020-09-01",
        )
        result = service.load_fear_and_greed(config)

        # Seul le point du 2020-06-01 devrait passer le filtre
        assert result.inserted == 1

    @patch("app.services.sentiment_history_service.httpx.get")
    def test_load_skips_invalid_timestamp(self, mock_get, db_session):
        """Les points sans timestamp valide sont ignorés."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"value": "25", "value_classification": "Extreme Fear", "timestamp": "0"},
                {"value": "50", "value_classification": "Neutral", "timestamp": "1580601600"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        service = SentimentHistoryService(db_session)
        result = service.load_fear_and_greed()
        assert result.inserted == 1


# ============================================================
# INTÉGRATION AVEC DECISION SERVICE
# ============================================================

class TestDecisionServiceSentimentIntegration:
    """Tests d'intégration : le DecisionService utilise le sentiment historique."""

    def _seed_candles_and_sentiment(self, db_session):
        """Seed des candles 1d + sentiment pour tester l'intégration."""
        from app.models import Candle

        # Créer 250 jours de candles pour avoir assez de contexte
        base_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        price = 7000.0
        for i in range(300):
            dt = base_date + timedelta(days=i)
            # Prix simulé avec tendance haussière légère
            close = price + (i * 10) + ((-1) ** i * 50)
            candle = Candle(
                symbol="BTC/USD",
                timeframe="1d",
                timestamp=dt,
                open_price=close - 50,
                high_price=close + 100,
                low_price=close - 100,
                close_price=close,
                volume=1000.0 + i * 10,
                source="test",
            )
            db_session.add(candle)

        # Sentiment : quelques points Fear & Greed
        _insert_sentiment_point(db_session, "2020-06-01", 25.0, label="Extreme Fear")
        _insert_sentiment_point(db_session, "2020-06-15", 40.0, label="Fear")
        _insert_sentiment_point(db_session, "2020-07-01", 55.0, label="Greed")
        _insert_sentiment_point(db_session, "2020-07-15", 70.0, label="Greed")
        _insert_sentiment_point(db_session, "2020-08-01", 85.0, label="Extreme Greed")
        db_session.commit()

    def test_decision_uses_historical_sentiment(self, db_session):
        """Le DecisionService utilise le sentiment historique quand end_ts est fourni."""
        self._seed_candles_and_sentiment(db_session)

        from app.services.decision_service import DecisionService
        service = DecisionService(db_session)

        end_ts = datetime(2020, 6, 1, tzinfo=timezone.utc)
        result = service.analyze(
            symbol="BTC/USD",
            timeframe="1d",
            history_days=200,
            end_ts=end_ts,
        )

        # Le sentiment devrait être disponible (Fear & Greed stocké)
        meta = result["meta"]
        assert meta["sentiment_available"] is True
        # Le score de sentiment devrait refléter "Extreme Fear" (25 → -50 normalisé)
        assert result["sentiment_score"] == -50

    def test_decision_without_historical_sentiment(self, db_session):
        """Sans sentiment en base, le mode dégradé fonctionne."""
        from app.models import Candle

        # Candles sans sentiment
        base_date = datetime(2019, 1, 1, tzinfo=timezone.utc)
        for i in range(250):
            dt = base_date + timedelta(days=i)
            candle = Candle(
                symbol="BTC/USD",
                timeframe="1d",
                timestamp=dt,
                open_price=3500,
                high_price=3600,
                low_price=3400,
                close_price=3500 + i,
                volume=1000.0,
                source="test",
            )
            db_session.add(candle)
        db_session.commit()

        from app.services.decision_service import DecisionService
        service = DecisionService(db_session)

        end_ts = datetime(2019, 6, 1, tzinfo=timezone.utc)
        result = service.analyze(
            symbol="BTC/USD",
            timeframe="1d",
            history_days=100,
            end_ts=end_ts,
        )

        # Mode dégradé : sentiment pas disponible
        assert result["meta"]["sentiment_available"] is False
        assert result["sentiment_score"] == 0

    def test_decision_real_time_still_uses_rss(self, db_session):
        """En mode temps réel (pas de end_ts), le RSS est toujours utilisé."""
        from app.services.decision_service import DecisionService
        from app.models import Candle

        # Seed candles récentes
        base_date = datetime.now(timezone.utc) - timedelta(days=30)
        for i in range(30):
            dt = base_date + timedelta(days=i)
            candle = Candle(
                symbol="BTC/USD",
                timeframe="1d",
                timestamp=dt,
                open_price=50000,
                high_price=51000,
                low_price=49000,
                close_price=50000 + i * 100,
                volume=5000.0,
                source="test",
            )
            db_session.add(candle)
        db_session.commit()

        service = DecisionService(db_session)

        # Mocker le NewsService pour vérifier qu'il est appelé
        with patch.object(service.news_service, "get_sentiment_only") as mock_news:
            from app.schemas.news import NewsSentimentSummary, SentimentType
            mock_news.return_value = NewsSentimentSummary(
                total_articles=10,
                positive_count=5,
                negative_count=2,
                neutral_count=3,
                overall_sentiment=SentimentType.POSITIVE,
                sentiment_score=30,
            )

            result = service.analyze(
                symbol="BTC/USD",
                timeframe="1d",
                history_days=7,
                # PAS de end_ts → mode temps réel
            )

            # Le RSS devrait avoir été appelé
            mock_news.assert_called_once()
            assert result["sentiment_score"] == 30


# ============================================================
# ENDPOINTS API
# ============================================================

class TestSentimentEndpoints:
    """Tests des endpoints /sentiment/history/*."""

    def test_range_empty(self, client):
        """GET /sentiment/history/range retourne une plage vide."""
        resp = client.get("/sentiment/history/range")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_data"] is False
        assert data["total_points"] == 0

    def test_coverage_empty(self, client):
        """GET /sentiment/history/coverage retourne une couverture vide."""
        resp = client.get("/sentiment/history/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_points"] == 0

    def test_at_date_not_found(self, client):
        """GET /sentiment/history/at-date retourne 404 si pas de données."""
        resp = client.get("/sentiment/history/at-date", params={"date": "2020-06-01"})
        assert resp.status_code == 404

    def test_at_date_found(self, client, db_session):
        """GET /sentiment/history/at-date retourne le sentiment à une date."""
        _insert_sentiment_point(db_session, "2020-06-01", 25.0, label="Extreme Fear")
        resp = client.get("/sentiment/history/at-date", params={"date": "2020-06-01"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["raw_score"] == 25.0
        assert data["normalized_score"] == -50.0
        assert data["exact_match"] is True

    @patch("app.services.sentiment_history_service.httpx.get")
    def test_load_endpoint(self, mock_get, client):
        """POST /sentiment/history/load charge le sentiment."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"value": "50", "value_classification": "Neutral", "timestamp": "1580601600"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        resp = client.post("/sentiment/history/load", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["fetched"] == 1
        assert data["inserted"] == 1
        assert data["source"] == "fear_and_greed"

    def test_range_with_data(self, client, db_session):
        """GET /sentiment/history/range retourne la plage après chargement."""
        _insert_multiple_sentiment(db_session, [
            ("2020-01-01", 30.0, "Fear"),
            ("2020-12-31", 70.0, "Greed"),
        ])
        resp = client.get("/sentiment/history/range")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_data"] is True
        assert data["total_points"] == 2

    def test_coverage_with_data(self, client, db_session):
        """GET /sentiment/history/coverage retourne la couverture."""
        _insert_multiple_sentiment(db_session, [
            ("2020-01-01", 30.0, "Fear"),
            ("2020-06-01", 50.0, "Neutral"),
        ])
        resp = client.get("/sentiment/history/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_points"] == 2
        assert len(data["sources"]) == 1


# ============================================================
# SCHEMAS PYDANTIC
# ============================================================

class TestSentimentSchemas:
    """Tests de validation des schémas Pydantic."""

    def test_load_config_defaults(self):
        """SentimentLoadConfig avec valeurs par défaut."""
        config = SentimentLoadConfig()
        assert config.source == "fear_and_greed"
        assert config.start_date is None
        assert config.end_date is None

    def test_load_response(self):
        """SentimentLoadResponse sérialisation."""
        resp = SentimentLoadResponse(
            source="fear_and_greed",
            fetched=100,
            inserted=95,
            updated=3,
            skipped=2,
            total_in_db=2900,
            duration_seconds=1.5,
        )
        assert resp.source == "fear_and_greed"
        assert resp.fetched == 100

    def test_at_date_response(self):
        """SentimentAtDateResponse sérialisation."""
        resp = SentimentAtDateResponse(
            date="2020-06-01",
            source="fear_and_greed",
            raw_score=25.0,
            normalized_score=-50.0,
            label="Extreme Fear",
            exact_match=True,
        )
        assert resp.normalized_score == -50.0

    def test_coverage_response_empty(self):
        """SentimentCoverageResponse vide."""
        resp = SentimentCoverageResponse()
        assert resp.total_points == 0
        assert len(resp.sources) == 0

