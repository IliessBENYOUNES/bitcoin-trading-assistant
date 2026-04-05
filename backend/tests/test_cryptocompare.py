"""
Tests pour le module CryptoCompare — Client API News + intégration NewsHistoryService.

Couvre :
- CryptoCompareService : parsing d'articles, fetch de pages, multi-pages
- Intégration avec NewsHistoryService : load_cryptocompare_history, persist_cryptocompare_recent
- Delta loading (ne recharger que ce qui manque)
- Endpoint API POST /news/history/load-cryptocompare
"""

import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.services.cryptocompare_service import (
    CryptoCompareService,
    CRYPTOCOMPARE_SOURCE,
    CRYPTOCOMPARE_NEWS_URL,
)
from app.services.news_history_service import NewsHistoryService
from app.models.news_history import NewsHistory
from app.schemas.news import NewsItem, SentimentType, ImpactLevel


# ============================================================
# Helpers — Données brutes CryptoCompare
# ============================================================

def _make_raw_article(
    title="Bitcoin hits new ATH",
    body="Bitcoin surged past all previous records today.",
    url="https://cryptocompare.com/news/btc-ath",
    source_name="CoinDesk",
    published_on=1700000000,
    categories="BTC|Blockchain",
):
    """Crée un dict au format brut de l'API CryptoCompare."""
    return {
        "title": title,
        "body": body,
        "url": url,
        "source_info": {"name": source_name},
        "published_on": published_on,
        "categories": categories,
    }


def _make_cc_response(articles, message="Success"):
    """Crée une réponse JSON au format CryptoCompare."""
    return {"Message": message, "Data": articles}


def _make_httpx_response(data, status_code=200):
    """Crée un objet response mock pour httpx."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


# ============================================================
# Tests de CryptoCompareService — Parsing
# ============================================================

class TestCryptoCompareServiceParsing:
    """Tests du parsing d'articles bruts CryptoCompare."""

    def test_parse_valid_article(self):
        """Un article brut valide est parsé en NewsItem."""
        service = CryptoCompareService()
        raw = _make_raw_article(
            title="BTC breaks $100k",
            body="Major milestone for Bitcoin as it crosses the six-figure mark.",
            url="https://cc.com/btc-100k",
            source_name="Bloomberg",
            published_on=1700000000,
        )

        item = service._parse_article(raw)

        assert item is not None
        assert item.title == "BTC breaks $100k"
        assert item.url == "https://cc.com/btc-100k"
        assert item.source == CRYPTOCOMPARE_SOURCE
        assert "[Bloomberg]" in item.description
        assert item.published_at is not None
        assert item.sentiment in [SentimentType.POSITIVE, SentimentType.NEGATIVE, SentimentType.NEUTRAL]

    def test_parse_article_no_title_returns_none(self):
        """Un article sans titre est ignoré."""
        service = CryptoCompareService()
        raw = _make_raw_article(title="", url="https://cc.com/test")

        item = service._parse_article(raw)
        assert item is None

    def test_parse_article_no_url_returns_none(self):
        """Un article sans URL est ignoré."""
        service = CryptoCompareService()
        raw = _make_raw_article(url="")

        item = service._parse_article(raw)
        assert item is None

    def test_parse_article_truncates_description(self):
        """La description est tronquée à 500 caractères."""
        service = CryptoCompareService()
        long_body = "A" * 1000
        raw = _make_raw_article(body=long_body)

        item = service._parse_article(raw)

        assert item is not None
        # description = "[source] " + body[:500]
        # La partie body dans la description ne dépasse pas 500 chars
        body_part = item.description.split("] ", 1)[1] if "] " in item.description else item.description
        assert len(body_part) <= 500

    def test_parse_article_empty_body(self):
        """Un article sans body est quand même parsé."""
        service = CryptoCompareService()
        raw = _make_raw_article(body="")

        item = service._parse_article(raw)
        assert item is not None
        assert item.title == "Bitcoin hits new ATH"

    def test_parse_article_missing_source_info(self):
        """Un article sans source_info utilise 'unknown'."""
        service = CryptoCompareService()
        raw = _make_raw_article()
        raw["source_info"] = None

        item = service._parse_article(raw)
        assert item is not None
        assert "[unknown]" in item.description

    def test_parse_article_invalid_timestamp(self):
        """Un timestamp invalide ne crash pas."""
        service = CryptoCompareService()
        raw = _make_raw_article(published_on=0)

        item = service._parse_article(raw)
        assert item is not None
        # published_on=0 → published_at=None (falsy check)
        assert item.published_at is None


# ============================================================
# Tests de CryptoCompareService — fetch_news_page
# ============================================================

class TestCryptoCompareServiceFetchPage:
    """Tests de fetch_news_page avec HTTP mocké."""

    def test_fetch_page_success(self):
        """Une page réussie retourne des NewsItem + next_lTs."""
        articles = [
            _make_raw_article(
                title=f"Article {i}",
                url=f"https://cc.com/art{i}",
                published_on=1700000000 - i * 3600,
            )
            for i in range(3)
        ]
        response_data = _make_cc_response(articles)

        service = CryptoCompareService()

        with patch("app.services.cryptocompare_service.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.return_value = _make_httpx_response(response_data)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client

            items, next_lts = service.fetch_news_page()

        assert len(items) == 3
        assert all(isinstance(i, NewsItem) for i in items)
        # next_lTs = le plus ancien published_on
        assert next_lts == 1700000000 - 2 * 3600

    def test_fetch_page_empty_data(self):
        """Une page vide retourne ([], None)."""
        response_data = _make_cc_response([])

        service = CryptoCompareService()

        with patch("app.services.cryptocompare_service.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.return_value = _make_httpx_response(response_data)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client

            items, next_lts = service.fetch_news_page()

        assert items == []
        assert next_lts is None

    def test_fetch_page_http_error(self):
        """Une erreur HTTP retourne ([], None)."""
        import httpx

        service = CryptoCompareService()

        with patch("app.services.cryptocompare_service.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.HTTPError("Connection timeout")
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client

            items, next_lts = service.fetch_news_page()

        assert items == []
        assert next_lts is None

    def test_fetch_page_passes_lts_param(self):
        """Le paramètre lTs est transmis dans les params HTTP."""
        response_data = _make_cc_response([])

        service = CryptoCompareService()

        with patch("app.services.cryptocompare_service.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.return_value = _make_httpx_response(response_data)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client

            service.fetch_news_page(lTs=1609459200)

            # Vérifier que lTs est dans les params
            call_kwargs = mock_client.get.call_args
            params = call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))
            assert params.get("lTs") == 1609459200

    def test_fetch_page_with_api_key(self):
        """Un client avec clé API envoie le header Authorization."""
        response_data = _make_cc_response([])

        service = CryptoCompareService(api_key="my-secret-key")

        with patch("app.services.cryptocompare_service.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.return_value = _make_httpx_response(response_data)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_client

            service.fetch_news_page()

            call_kwargs = mock_client.get.call_args
            headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
            assert headers.get("authorization") == "Apikey my-secret-key"


# ============================================================
# Tests de CryptoCompareService — fetch_all_recent
# ============================================================

class TestCryptoCompareServiceFetchAllRecent:
    """Tests de fetch_all_recent (multi-pages)."""

    def test_single_page(self):
        """Avec max_pages=1, un seul appel à fetch_news_page."""
        service = CryptoCompareService()
        items = [
            NewsItem(
                title="Art 1",
                url="https://cc.com/1",
                source=CRYPTOCOMPARE_SOURCE,
                published_at=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                sentiment=SentimentType.NEUTRAL,
                impact=ImpactLevel.LOW,
            ),
        ]

        with patch.object(service, "fetch_news_page", return_value=(items, None)):
            result = service.fetch_all_recent(max_pages=1)

        assert len(result) == 1

    def test_multi_page_pagination(self):
        """Pagination multi-pages fonctionne et retourne les résultats triés."""
        service = CryptoCompareService()

        page1_items = [
            NewsItem(
                title="Recent",
                url="https://cc.com/recent",
                source=CRYPTOCOMPARE_SOURCE,
                published_at=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
                sentiment=SentimentType.POSITIVE,
                impact=ImpactLevel.MEDIUM,
            ),
        ]
        page2_items = [
            NewsItem(
                title="Older",
                url="https://cc.com/older",
                source=CRYPTOCOMPARE_SOURCE,
                published_at=datetime(2024, 6, 14, 12, 0, tzinfo=timezone.utc),
                sentiment=SentimentType.NEGATIVE,
                impact=ImpactLevel.LOW,
            ),
        ]

        call_count = 0

        def mock_fetch(lTs=None, categories="BTC", lang="EN"):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return page1_items, 1718452800  # next_lts
            elif call_count == 2:
                return page2_items, None  # fin
            return [], None

        with patch.object(service, "fetch_news_page", side_effect=mock_fetch):
            with patch("app.services.cryptocompare_service.time.sleep"):
                result = service.fetch_all_recent(max_pages=3)

        assert len(result) == 2
        # Tri décroissant par date
        assert result[0].title == "Recent"
        assert result[1].title == "Older"

    def test_stops_on_empty_page(self):
        """S'arrête quand une page est vide."""
        service = CryptoCompareService()

        with patch.object(service, "fetch_news_page", return_value=([], None)):
            result = service.fetch_all_recent(max_pages=5)

        assert len(result) == 0


# ============================================================
# Tests d'intégration — load_cryptocompare_history
# ============================================================

class TestLoadCryptoCompareHistory:
    """Tests de NewsHistoryService.load_cryptocompare_history avec DB réelle."""

    def test_load_inserts_articles(self, db_session, monkeypatch):
        """Le chargement historique insère les articles en base."""
        articles = [
            _make_raw_article(
                title=f"Article {i}",
                url=f"https://cc.com/hist{i}",
                published_on=1700000000 - i * 86400,
            )
            for i in range(3)
        ]

        def mock_fetch_page(self_svc, lTs=None, categories="BTC"):
            if lTs is None:
                items = []
                for raw in articles:
                    service = CryptoCompareService()
                    item = service._parse_article(raw)
                    if item:
                        items.append(item)
                return items, 1700000000 - 2 * 86400
            return [], None

        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_news_page",
            mock_fetch_page,
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        service = NewsHistoryService(db_session)
        result = service.load_cryptocompare_history(max_pages=2)

        assert result["inserted"] == 3
        assert result["pages_loaded"] == 1
        assert result["source"] == CRYPTOCOMPARE_SOURCE
        assert result["total_cryptocompare"] == 3

    def test_load_idempotent(self, db_session, monkeypatch):
        """Recharger les mêmes articles ne crée pas de doublons."""
        articles = [
            _make_raw_article(
                title="Same article",
                url="https://cc.com/same",
                published_on=1700000000,
            ),
        ]

        call_count = [0]

        def mock_fetch_page(self_svc, lTs=None, categories="BTC"):
            call_count[0] += 1
            if call_count[0] <= 2:  # Deux appels (un par load)
                items = []
                for raw in articles:
                    s = CryptoCompareService()
                    item = s._parse_article(raw)
                    if item:
                        items.append(item)
                return items, None
            return [], None

        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_news_page",
            mock_fetch_page,
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        service = NewsHistoryService(db_session)

        # Premier chargement
        r1 = service.load_cryptocompare_history(max_pages=1)
        assert r1["inserted"] == 1

        # Deuxième chargement — même URL → skipped
        r2 = service.load_cryptocompare_history(max_pages=1)
        assert r2["inserted"] == 0
        assert r2["skipped"] >= 1
        assert r2["total_cryptocompare"] == 1

    def test_load_stops_at_start_year(self, db_session, monkeypatch):
        """Le chargement s'arrête quand on atteint start_year."""
        # Articles avec dates en 2014 (avant start_year=2015)
        old_ts = int(datetime(2014, 6, 1, tzinfo=timezone.utc).timestamp())
        articles = [
            _make_raw_article(
                title="Very old article",
                url="https://cc.com/old",
                published_on=old_ts,
            ),
        ]

        def mock_fetch_page(self_svc, lTs=None, categories="BTC"):
            items = []
            for raw in articles:
                s = CryptoCompareService()
                item = s._parse_article(raw)
                if item:
                    items.append(item)
            return items, old_ts - 86400

        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_news_page",
            mock_fetch_page,
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        service = NewsHistoryService(db_session)
        result = service.load_cryptocompare_history(start_year=2015, max_pages=5)

        # L'article de 2014 est filtré
        assert result["inserted"] == 0
        assert result["pages_loaded"] == 1  # S'arrête après la première page

    def test_load_stops_when_no_more_pages(self, db_session, monkeypatch):
        """Le chargement s'arrête quand next_lTs est None."""
        articles = [
            _make_raw_article(
                title="Last page article",
                url="https://cc.com/last",
                published_on=1700000000,
            ),
        ]

        def mock_fetch_page(self_svc, lTs=None, categories="BTC"):
            if lTs is None:
                items = []
                for raw in articles:
                    s = CryptoCompareService()
                    item = s._parse_article(raw)
                    if item:
                        items.append(item)
                return items, None  # Pas de page suivante
            return [], None

        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_news_page",
            mock_fetch_page,
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        service = NewsHistoryService(db_session)
        result = service.load_cryptocompare_history(max_pages=10)

        assert result["pages_loaded"] == 1
        assert result["inserted"] == 1

    def test_load_delta_mode(self, db_session, monkeypatch):
        """Le delta loading démarre depuis le plus ancien article existant."""
        # Pré-insérer un article CryptoCompare en base
        existing = NewsHistory(
            title="Already in DB",
            url="https://cc.com/existing",
            source=CRYPTOCOMPARE_SOURCE,
            published_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            sentiment="positive",
            impact="medium",
            sentiment_score=50.0,
        )
        db_session.add(existing)
        db_session.commit()

        captured_lts = []

        def mock_fetch_page(self_svc, lTs=None, categories="BTC"):
            captured_lts.append(lTs)
            return [], None

        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_news_page",
            mock_fetch_page,
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        service = NewsHistoryService(db_session)
        service.load_cryptocompare_history(max_pages=1)

        # Le premier appel doit avoir lTs (mode delta activé)
        assert len(captured_lts) >= 1
        # En mode delta, lTs n'est pas None
        assert captured_lts[0] is not None
        # Le timestamp doit correspondre approximativement au 2024-01-15
        # (tolérance de ±24h pour les différences de timezone SQLite)
        expected_ts = int(datetime(2024, 1, 15, tzinfo=timezone.utc).timestamp())
        assert abs(captured_lts[0] - expected_ts) < 86400  # ±1 jour


# ============================================================
# Tests d'intégration — persist_cryptocompare_recent
# ============================================================

class TestPersistCryptoCompareRecent:
    """Tests de NewsHistoryService.persist_cryptocompare_recent."""

    def test_persist_recent_success(self, db_session, monkeypatch):
        """Persiste les news récentes CryptoCompare."""
        mock_items = [
            NewsItem(
                title="Fresh CC article",
                url="https://cc.com/fresh",
                source=CRYPTOCOMPARE_SOURCE,
                published_at=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                sentiment=SentimentType.POSITIVE,
                impact=ImpactLevel.HIGH,
                keywords=["bitcoin", "surge"],
            ),
        ]

        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_all_recent",
            lambda self, max_pages=1: mock_items,
        )

        service = NewsHistoryService(db_session)
        result = service.persist_cryptocompare_recent()

        assert result["source"] == CRYPTOCOMPARE_SOURCE
        assert result["inserted"] == 1
        assert result["total_fetched"] == 1

    def test_persist_recent_deduplication(self, db_session, monkeypatch):
        """Le dédoublonnage par URL fonctionne pour CryptoCompare."""
        mock_items = [
            NewsItem(
                title="CC article",
                url="https://cc.com/dedup-test",
                source=CRYPTOCOMPARE_SOURCE,
                published_at=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                sentiment=SentimentType.NEUTRAL,
                impact=ImpactLevel.LOW,
            ),
        ]

        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_all_recent",
            lambda self, max_pages=1: mock_items,
        )

        service = NewsHistoryService(db_session)

        r1 = service.persist_cryptocompare_recent()
        assert r1["inserted"] == 1

        r2 = service.persist_cryptocompare_recent()
        assert r2["inserted"] == 0
        assert r2["skipped"] == 1

    def test_persist_recent_empty(self, db_session, monkeypatch):
        """Aucune news → résultat vide."""
        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_all_recent",
            lambda self, max_pages=1: [],
        )

        service = NewsHistoryService(db_session)
        result = service.persist_cryptocompare_recent()

        assert result["inserted"] == 0
        assert result["total_fetched"] == 0


# ============================================================
# Tests du service — Headers et configuration
# ============================================================

class TestCryptoCompareServiceConfig:
    """Tests de configuration du client CryptoCompare."""

    def test_default_config(self):
        """Configuration par défaut (pas de clé API, timeout standard)."""
        service = CryptoCompareService()
        assert service.api_key is None
        assert service.timeout == 15

    def test_custom_api_key(self):
        """Clé API custom dans les headers."""
        service = CryptoCompareService(api_key="test-key-123")
        headers = service._build_headers()
        assert headers["authorization"] == "Apikey test-key-123"
        assert "User-Agent" in headers

    def test_no_api_key_no_auth_header(self):
        """Sans clé API, pas de header Authorization."""
        service = CryptoCompareService()
        headers = service._build_headers()
        assert "authorization" not in headers
        assert "User-Agent" in headers

    def test_custom_timeout(self):
        """Timeout custom."""
        service = CryptoCompareService(timeout=30)
        assert service.timeout == 30


# ============================================================
# Tests des endpoints API
# ============================================================

class TestCryptoCompareEndpoint:
    """Tests de l'endpoint POST /news/history/load-cryptocompare."""

    def test_load_endpoint_success(self, client, monkeypatch):
        """POST /news/history/load-cryptocompare retourne 200."""
        mock_items = [
            NewsItem(
                title="CC API test article",
                url="https://cc.com/api-test",
                source=CRYPTOCOMPARE_SOURCE,
                published_at=datetime(2024, 6, 15, tzinfo=timezone.utc),
                sentiment=SentimentType.POSITIVE,
                impact=ImpactLevel.MEDIUM,
                keywords=["test"],
            ),
        ]

        def mock_fetch_page(self_svc, lTs=None, categories="BTC"):
            if lTs is None:
                return mock_items, None
            return [], None

        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_news_page",
            mock_fetch_page,
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        resp = client.post("/news/history/load-cryptocompare")
        assert resp.status_code == 200
        data = resp.json()
        assert "inserted" in data
        assert "pages_loaded" in data
        assert "source" in data
        assert data["source"] == CRYPTOCOMPARE_SOURCE

    def test_load_endpoint_with_params(self, client, monkeypatch):
        """POST /news/history/load-cryptocompare accepte start_year et max_pages."""
        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_news_page",
            lambda self, lTs=None, categories="BTC": ([], None),
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        resp = client.post("/news/history/load-cryptocompare?start_year=2020&max_pages=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pages_loaded"] == 0  # Aucune page retournée
        assert data["inserted"] == 0

    def test_load_endpoint_returns_structure(self, client, monkeypatch):
        """La réponse contient tous les champs attendus."""
        monkeypatch.setattr(
            "app.services.cryptocompare_service.CryptoCompareService.fetch_news_page",
            lambda self, lTs=None, categories="BTC": ([], None),
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        resp = client.post("/news/history/load-cryptocompare")
        assert resp.status_code == 200
        data = resp.json()

        expected_keys = {
            "source", "pages_loaded", "total_fetched",
            "inserted", "skipped", "total_cryptocompare",
            "total_in_db", "duration_seconds",
        }
        assert expected_keys.issubset(set(data.keys()))

