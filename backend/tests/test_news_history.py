"""
Tests pour le module NewsHistory — Persistance des news RSS en base.

Couvre :
- Modèle NewsHistory (création, contrainte unique, colonnes)
- Service NewsHistoryService (persist, query, range, coverage)
- Score de sentiment (article individuel, agrégation quotidienne)
- Endpoints API (/news/history/*)
- Dédoublonnage (idempotence)
"""

import json
import pytest
from datetime import datetime, timezone, timedelta

from app.models.news_history import NewsHistory
from app.services.news_history_service import (
    NewsHistoryService,
    compute_article_score,
)
from app.schemas.news import NewsItem, SentimentType, ImpactLevel


# ============================================================
# Helpers
# ============================================================

def _make_news_entry(
    db_session,
    title="Test Article",
    url="https://example.com/test",
    source="CoinTelegraph",
    sentiment="positive",
    impact="medium",
    published_at=None,
):
    """Helper pour insérer un article en base."""
    if published_at is None:
        published_at = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)

    score = compute_article_score(sentiment, impact)
    entry = NewsHistory(
        title=title,
        url=url,
        source=source,
        description=f"Description of {title}",
        published_at=published_at,
        sentiment=sentiment,
        impact=impact,
        sentiment_score=score,
        keywords=json.dumps(["bitcoin", "crypto"]),
    )
    db_session.add(entry)
    db_session.commit()
    return entry


# ============================================================
# Tests du modèle NewsHistory
# ============================================================

class TestNewsHistoryModel:
    """Tests du modèle SQLAlchemy NewsHistory."""

    def test_create_news_entry(self, db_session):
        """Création d'un article en base."""
        entry = _make_news_entry(db_session, title="BTC breaks $100k")
        assert entry.id is not None
        assert entry.title == "BTC breaks $100k"
        assert entry.sentiment == "positive"

    def test_news_entry_repr(self, db_session):
        """Le repr est lisible."""
        entry = _make_news_entry(db_session, title="Bitcoin surges past all-time high")
        repr_str = repr(entry)
        assert "NewsHistory" in repr_str
        assert "CoinTelegraph" in repr_str

    def test_multiple_sources(self, db_session):
        """Plusieurs sources peuvent coexister."""
        _make_news_entry(db_session, title="Art 1", url="https://a.com/1", source="CoinTelegraph")
        _make_news_entry(db_session, title="Art 2", url="https://b.com/2", source="CoinDesk")
        _make_news_entry(db_session, title="Art 3", url="https://c.com/3", source="Bitcoin Magazine")

        count = db_session.query(NewsHistory).count()
        assert count == 3

    def test_nullable_url(self, db_session):
        """URL peut être null (certains RSS n'en ont pas)."""
        entry = NewsHistory(
            title="No URL article",
            url=None,
            source="Test",
            sentiment="neutral",
            impact="low",
            sentiment_score=0.0,
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(entry)
        db_session.commit()
        assert entry.id is not None


# ============================================================
# Tests du scoring de sentiment
# ============================================================

class TestArticleScoring:
    """Tests du calcul de score de sentiment par article."""

    def test_positive_high(self):
        assert compute_article_score("positive", "high") == 75

    def test_positive_medium(self):
        assert compute_article_score("positive", "medium") == 50

    def test_positive_low(self):
        assert compute_article_score("positive", "low") == 25

    def test_negative_high(self):
        assert compute_article_score("negative", "high") == -75

    def test_negative_medium(self):
        assert compute_article_score("negative", "medium") == -50

    def test_negative_low(self):
        assert compute_article_score("negative", "low") == -25

    def test_neutral_any(self):
        assert compute_article_score("neutral", "high") == 0
        assert compute_article_score("neutral", "medium") == 0
        assert compute_article_score("neutral", "low") == 0

    def test_invalid_sentiment(self):
        """Un sentiment invalide retourne 0."""
        assert compute_article_score("unknown", "high") == 0.0

    def test_invalid_impact(self):
        """Un impact invalide retourne 0."""
        assert compute_article_score("positive", "critical") == 0.0


# ============================================================
# Tests du service NewsHistoryService
# ============================================================

class TestNewsHistoryServicePersist:
    """Tests de la persistance des news en base."""

    def test_persist_with_mock_news(self, db_session, monkeypatch):
        """Persiste les news mockées en base."""
        mock_items = [
            NewsItem(
                title="BTC surges to 100k",
                url="https://example.com/btc-100k",
                source="CoinTelegraph",
                published_at=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                sentiment=SentimentType.POSITIVE,
                impact=ImpactLevel.HIGH,
                keywords=["surge", "ath"],
            ),
            NewsItem(
                title="SEC investigates exchange",
                url="https://example.com/sec-investigation",
                source="CoinDesk",
                published_at=datetime(2024, 6, 15, 11, 0, tzinfo=timezone.utc),
                sentiment=SentimentType.NEGATIVE,
                impact=ImpactLevel.MEDIUM,
                keywords=["sec", "investigation"],
            ),
        ]

        # Mock le fetch_all_news pour retourner nos articles
        monkeypatch.setattr(
            "app.services.news_history_service.NewsService.fetch_all_news",
            lambda self: mock_items,
        )

        service = NewsHistoryService(db_session)
        result = service.persist_current_news()

        assert result["inserted"] == 2
        assert result["skipped"] == 0
        assert result["total_in_db"] == 2

    def test_persist_idempotent(self, db_session, monkeypatch):
        """Relancer la persistance ne crée pas de doublons."""
        mock_items = [
            NewsItem(
                title="BTC update",
                url="https://example.com/btc-update",
                source="CoinTelegraph",
                published_at=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                sentiment=SentimentType.POSITIVE,
                impact=ImpactLevel.LOW,
                keywords=["update"],
            ),
        ]

        monkeypatch.setattr(
            "app.services.news_history_service.NewsService.fetch_all_news",
            lambda self: mock_items,
        )

        service = NewsHistoryService(db_session)

        # Premier appel
        r1 = service.persist_current_news()
        assert r1["inserted"] == 1

        # Deuxième appel — même news → skipped
        r2 = service.persist_current_news()
        assert r2["inserted"] == 0
        assert r2["skipped"] == 1
        assert r2["total_in_db"] == 1

    def test_persist_empty_news(self, db_session, monkeypatch):
        """Aucune news à persister → résultat vide."""
        monkeypatch.setattr(
            "app.services.news_history_service.NewsService.fetch_all_news",
            lambda self: [],
        )

        service = NewsHistoryService(db_session)
        result = service.persist_current_news()

        assert result["inserted"] == 0
        assert result["total_fetched"] == 0


class TestNewsHistoryServiceQuery:
    """Tests des requêtes de sentiment historique."""

    def test_daily_sentiment_positive_day(self, db_session):
        """Jour avec articles positifs → score > 0."""
        date = datetime(2024, 6, 15, tzinfo=timezone.utc)
        _make_news_entry(db_session, title="A1", url="https://a.com/1",
                         sentiment="positive", impact="high", published_at=date)
        _make_news_entry(db_session, title="A2", url="https://a.com/2",
                         sentiment="positive", impact="medium",
                         published_at=date + timedelta(hours=2))

        service = NewsHistoryService(db_session)
        score = service.get_daily_sentiment("2024-06-15", tolerance_days=0)

        assert score is not None
        assert score > 0

    def test_daily_sentiment_negative_day(self, db_session):
        """Jour avec articles négatifs → score < 0."""
        date = datetime(2024, 6, 15, tzinfo=timezone.utc)
        _make_news_entry(db_session, title="Bad news 1", url="https://a.com/b1",
                         sentiment="negative", impact="high", published_at=date)
        _make_news_entry(db_session, title="Bad news 2", url="https://a.com/b2",
                         sentiment="negative", impact="medium",
                         published_at=date + timedelta(hours=1))

        service = NewsHistoryService(db_session)
        score = service.get_daily_sentiment("2024-06-15", tolerance_days=0)

        assert score is not None
        assert score < 0

    def test_daily_sentiment_no_articles(self, db_session):
        """Aucun article → None."""
        service = NewsHistoryService(db_session)
        score = service.get_daily_sentiment("2020-01-01")
        assert score is None

    def test_daily_sentiment_mixed(self, db_session):
        """Mélange positif/négatif → score entre -100 et +100."""
        date = datetime(2024, 6, 15, tzinfo=timezone.utc)
        _make_news_entry(db_session, title="Good", url="https://a.com/g",
                         sentiment="positive", impact="high", published_at=date)
        _make_news_entry(db_session, title="Bad", url="https://a.com/b",
                         sentiment="negative", impact="low", published_at=date)

        service = NewsHistoryService(db_session)
        score = service.get_daily_sentiment("2024-06-15", tolerance_days=0)

        assert score is not None
        assert -100 <= score <= 100

    def test_get_articles_at_date(self, db_session):
        """Récupère les articles autour d'une date."""
        date = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        _make_news_entry(db_session, title="Article du jour", url="https://a.com/adj",
                         published_at=date)

        service = NewsHistoryService(db_session)
        articles = service.get_articles_at_date("2024-06-15")

        assert len(articles) == 1
        assert articles[0]["title"] == "Article du jour"

    def test_get_articles_empty(self, db_session):
        """Pas d'article à cette date → liste vide."""
        service = NewsHistoryService(db_session)
        articles = service.get_articles_at_date("2020-01-01")
        assert articles == []

    def test_tolerance_days(self, db_session):
        """Les articles proches sont inclus avec la tolérance."""
        date = datetime(2024, 6, 14, 12, 0, tzinfo=timezone.utc)
        _make_news_entry(db_session, title="Yesterday article", url="https://a.com/ya",
                         published_at=date)

        service = NewsHistoryService(db_session)

        # Tolérance 0 → pas trouvé (c'est le 14, on cherche le 15)
        articles_strict = service.get_articles_at_date("2024-06-15", tolerance_days=0)
        assert len(articles_strict) == 0

        # Tolérance 1 → trouvé
        articles_tolerant = service.get_articles_at_date("2024-06-15", tolerance_days=1)
        assert len(articles_tolerant) == 1


class TestNewsHistoryServiceRange:
    """Tests des métriques range et coverage."""

    def test_range_empty(self, db_session):
        """Base vide → has_data=False."""
        service = NewsHistoryService(db_session)
        result = service.get_range()
        assert result["has_data"] is False
        assert result["total_articles"] == 0

    def test_range_with_data(self, db_session):
        """Base avec données → plage correcte."""
        _make_news_entry(db_session, title="A1", url="https://a.com/1",
                         published_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        _make_news_entry(db_session, title="A2", url="https://a.com/2",
                         published_at=datetime(2024, 6, 30, tzinfo=timezone.utc))

        service = NewsHistoryService(db_session)
        result = service.get_range()

        assert result["has_data"] is True
        assert result["total_articles"] == 2
        assert result["min_date"] is not None
        assert result["max_date"] is not None

    def test_range_by_source(self, db_session):
        """Filtrage par source."""
        _make_news_entry(db_session, title="CT article", url="https://ct.com/1",
                         source="CoinTelegraph")
        _make_news_entry(db_session, title="CD article", url="https://cd.com/1",
                         source="CoinDesk")

        service = NewsHistoryService(db_session)

        ct_range = service.get_range("CoinTelegraph")
        assert ct_range["total_articles"] == 1
        assert ct_range["source"] == "CoinTelegraph"

        all_range = service.get_range()
        assert all_range["total_articles"] == 2

    def test_coverage(self, db_session):
        """Couverture par source."""
        _make_news_entry(db_session, title="A1", url="https://ct.com/1", source="CoinTelegraph")
        _make_news_entry(db_session, title="A2", url="https://cd.com/1", source="CoinDesk")
        _make_news_entry(db_session, title="A3", url="https://cd.com/2", source="CoinDesk")

        service = NewsHistoryService(db_session)
        coverage = service.get_coverage()

        assert coverage["total_articles"] == 3
        assert len(coverage["sources"]) == 2


# ============================================================
# Tests des endpoints API
# ============================================================

class TestNewsHistoryEndpoints:
    """Tests des endpoints /news/history/*."""

    def test_persist_endpoint(self, client, monkeypatch):
        """POST /news/history/persist fonctionne."""
        monkeypatch.setattr(
            "app.services.news_history_service.NewsService.fetch_all_news",
            lambda self: [
                NewsItem(
                    title="Test article",
                    url="https://test.com/1",
                    source="CoinTelegraph",
                    published_at=datetime(2024, 6, 15, tzinfo=timezone.utc),
                    sentiment=SentimentType.POSITIVE,
                    impact=ImpactLevel.MEDIUM,
                    keywords=["test"],
                ),
            ],
        )

        resp = client.post("/news/history/persist")
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 1

    def test_range_endpoint_empty(self, client):
        """GET /news/history/range retourne has_data=false si vide."""
        resp = client.get("/news/history/range")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_data"] is False

    def test_range_endpoint_with_data(self, client, monkeypatch):
        """GET /news/history/range retourne les stats après persist."""
        monkeypatch.setattr(
            "app.services.news_history_service.NewsService.fetch_all_news",
            lambda self: [
                NewsItem(
                    title="Article 1",
                    url="https://test.com/a1",
                    source="CoinTelegraph",
                    published_at=datetime(2024, 6, 15, tzinfo=timezone.utc),
                    sentiment=SentimentType.POSITIVE,
                    impact=ImpactLevel.LOW,
                ),
            ],
        )

        # Persister d'abord
        client.post("/news/history/persist")

        # Puis vérifier range
        resp = client.get("/news/history/range")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_data"] is True
        assert data["total_articles"] == 1

    def test_coverage_endpoint(self, client):
        """GET /news/history/coverage fonctionne."""
        resp = client.get("/news/history/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert "total_articles" in data

    def test_at_date_endpoint_empty(self, client):
        """GET /news/history/at-date avec base vide."""
        resp = client.get("/news/history/at-date?date=2024-01-15")
        assert resp.status_code == 200
        data = resp.json()
        assert data["article_count"] == 0
        assert data["daily_sentiment_score"] is None

    def test_at_date_endpoint_with_data(self, client, monkeypatch):
        """GET /news/history/at-date retourne articles et score."""
        monkeypatch.setattr(
            "app.services.news_history_service.NewsService.fetch_all_news",
            lambda self: [
                NewsItem(
                    title="Bullish article",
                    url="https://test.com/bull",
                    source="CoinTelegraph",
                    published_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                    sentiment=SentimentType.POSITIVE,
                    impact=ImpactLevel.HIGH,
                    keywords=["bullish"],
                ),
            ],
        )

        # Persister
        client.post("/news/history/persist")

        # Requêter
        resp = client.get("/news/history/at-date?date=2024-01-15")
        assert resp.status_code == 200
        data = resp.json()
        assert data["article_count"] == 1
        assert data["daily_sentiment_score"] is not None
        assert data["daily_sentiment_score"] > 0

