"""
Tests pour le système de news et sentiment (v0.9).

Organisation :
- TestSentimentClassifier     : Classification keyword-based
- TestImpactScoring           : Évaluation du niveau d'impact
- TestExtractKeywords         : Extraction de mots-clés
- TestRssParser               : Parsing XML RSS
- TestNewsSentimentSummary    : Agrégation du sentiment
- TestNewsServiceResilience   : Gestion des erreurs et cache
- TestNewsEndpoints           : Routes /news et /news/sentiment
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.services.news_service import (
    classify_sentiment,
    score_impact,
    extract_keywords,
    _parse_rss_items,
    _parse_pub_date,
    _extract_xml_tag,
    NewsService,
    clear_cache,
)
from app.schemas.news import (
    SentimentType,
    ImpactLevel,
    NewsItem,
    NewsSentimentSummary,
    NewsResponse,
)


# ============================================================
# CLASSIFICATION DE SENTIMENT
# ============================================================

class TestSentimentClassifier:
    """Tests pour classify_sentiment (keyword-based)."""

    def test_bullish_text_returns_positive(self):
        """Un texte avec des mots haussiers retourne positive."""
        text = "Bitcoin surges to new all-time high amid rally"
        assert classify_sentiment(text) == SentimentType.POSITIVE

    def test_bearish_text_returns_negative(self):
        """Un texte avec des mots baissiers retourne negative."""
        text = "Bitcoin crashes as SEC crackdown fears cause panic sell-off"
        assert classify_sentiment(text) == SentimentType.NEGATIVE

    def test_neutral_text_returns_neutral(self):
        """Un texte sans mots-clés forts retourne neutral."""
        text = "Bitcoin price moves sideways during the weekend"
        assert classify_sentiment(text) == SentimentType.NEUTRAL

    def test_none_returns_neutral(self):
        """None retourne neutral."""
        assert classify_sentiment(None) == SentimentType.NEUTRAL

    def test_empty_string_returns_neutral(self):
        """Chaîne vide retourne neutral."""
        assert classify_sentiment("") == SentimentType.NEUTRAL

    def test_mixed_text_majority_wins(self):
        """Si plus de mots bullish que bearish, retourne positive."""
        text = "ETF approved, adoption grows and rally continues despite some risk"
        result = classify_sentiment(text)
        # "approved", "adoption", "rally" (3 bullish) > "risk" (1 bearish)
        assert result == SentimentType.POSITIVE

    def test_case_insensitive(self):
        """La classification est insensible à la casse."""
        text = "BITCOIN SURGES AMID BULLISH MOMENTUM"
        assert classify_sentiment(text) == SentimentType.POSITIVE

    def test_equal_counts_returns_neutral(self):
        """Même nombre de mots bullish/bearish retourne neutral."""
        text = "rally amid crash"  # 1 bullish (rally), 1 bearish (crash)
        assert classify_sentiment(text) == SentimentType.NEUTRAL

    def test_bearish_dominant(self):
        """Texte fortement baissier."""
        text = "Massive hack exploit leads to fraud investigation and bankruptcy"
        assert classify_sentiment(text) == SentimentType.NEGATIVE

    def test_adoption_keyword(self):
        """Le mot 'adoption' est bullish."""
        text = "Major institutional adoption of Bitcoin continues"
        assert classify_sentiment(text) == SentimentType.POSITIVE


# ============================================================
# SCORING D'IMPACT
# ============================================================

class TestImpactScoring:
    """Tests pour score_impact."""

    def test_high_impact_sec_etf(self):
        """Article mentionnant SEC et ETF → HIGH."""
        text = "SEC considers Bitcoin ETF approval"
        assert score_impact(text) == ImpactLevel.HIGH

    def test_high_impact_hack(self):
        """Article mentionnant hack et exploit → HIGH."""
        text = "Major hack exploit discovered in billion dollar protocol"
        assert score_impact(text) == ImpactLevel.HIGH

    def test_medium_impact_exchange(self):
        """Article mentionnant exchange et listing → MEDIUM."""
        text = "New exchange listing for Bitcoin protocol upgrade"
        assert score_impact(text) == ImpactLevel.MEDIUM

    def test_low_impact_generic(self):
        """Article générique sans mots-clés spéciaux → LOW."""
        text = "Bitcoin looks steady this morning"
        assert score_impact(text) == ImpactLevel.LOW

    def test_none_returns_low(self):
        """None retourne LOW."""
        assert score_impact(None) == ImpactLevel.LOW

    def test_empty_returns_low(self):
        """Chaîne vide retourne LOW."""
        assert score_impact("") == ImpactLevel.LOW

    def test_single_high_keyword(self):
        """Un seul mot high → MEDIUM (il faut 2+ pour HIGH)."""
        text = "SEC reviews crypto"
        assert score_impact(text) == ImpactLevel.MEDIUM


# ============================================================
# EXTRACTION DE MOTS-CLÉS
# ============================================================

class TestExtractKeywords:
    """Tests pour extract_keywords."""

    def test_extracts_bullish_keywords(self):
        """Extrait les mots-clés bullish."""
        text = "Bitcoin rally and surge continue"
        keywords = extract_keywords(text)
        assert "rally" in keywords
        assert "surge" in keywords

    def test_extracts_bearish_keywords(self):
        """Extrait les mots-clés bearish."""
        text = "Market crash amid panic selling"
        keywords = extract_keywords(text)
        assert "crash" in keywords
        assert "panic" in keywords

    def test_none_returns_empty(self):
        """None retourne liste vide."""
        assert extract_keywords(None) == []

    def test_max_10_keywords(self):
        """Limite à 10 mots-clés maximum."""
        text = "bull surge rally adopt approve growth gain record moon breakout pump optimism recovery"
        keywords = extract_keywords(text)
        assert len(keywords) <= 10

    def test_no_duplicates(self):
        """Pas de doublons dans les mots-clés."""
        text = "bull bull bull rally rally"
        keywords = extract_keywords(text)
        assert len(keywords) == len(set(keywords))


# ============================================================
# PARSING RSS
# ============================================================

class TestRssParser:
    """Tests pour le parsing RSS XML."""

    def test_parse_simple_rss(self):
        """Parse un flux RSS simple."""
        xml = """
        <rss><channel>
        <item>
            <title>Bitcoin News</title>
            <link>https://example.com/1</link>
            <description>Some description</description>
            <pubDate>Mon, 01 Apr 2026 12:00:00 +0000</pubDate>
        </item>
        <item>
            <title>ETH Update</title>
            <link>https://example.com/2</link>
        </item>
        </channel></rss>
        """
        items = _parse_rss_items(xml, "Test")
        assert len(items) == 2
        assert items[0]["title"] == "Bitcoin News"
        assert items[0]["url"] == "https://example.com/1"
        assert items[0]["source"] == "Test"

    def test_parse_cdata_title(self):
        """Parse un titre enveloppé dans CDATA."""
        xml = """
        <item>
            <title><![CDATA[Bitcoin ETF Approved!]]></title>
            <link>https://example.com</link>
        </item>
        """
        items = _parse_rss_items(xml, "Test")
        assert len(items) == 1
        assert items[0]["title"] == "Bitcoin ETF Approved!"

    def test_parse_empty_rss(self):
        """Flux RSS vide retourne liste vide."""
        items = _parse_rss_items("<rss><channel></channel></rss>", "Test")
        assert items == []

    def test_extract_xml_tag(self):
        """Extraction d'un tag XML simple."""
        assert _extract_xml_tag("<title>Hello</title>", "title") == "Hello"
        assert _extract_xml_tag("<desc>World</desc>", "title") is None

    def test_parse_pub_date_rfc822(self):
        """Parse une date RFC 822."""
        date = _parse_pub_date("Mon, 01 Apr 2026 12:00:00 +0000")
        assert date is not None
        assert date.year == 2026
        assert date.month == 4

    def test_parse_pub_date_invalid(self):
        """Date invalide retourne None."""
        assert _parse_pub_date("not a date") is None
        assert _parse_pub_date(None) is None


# ============================================================
# RÉSUMÉ DU SENTIMENT
# ============================================================

class TestNewsSentimentSummary:
    """Tests pour le calcul du résumé de sentiment."""

    def test_all_positive_returns_positive(self):
        """Tous les articles positifs → score positif."""
        service = NewsService()
        items = [
            NewsItem(title="Bull", source="T", sentiment=SentimentType.POSITIVE, impact=ImpactLevel.LOW),
            NewsItem(title="Rally", source="T", sentiment=SentimentType.POSITIVE, impact=ImpactLevel.LOW),
            NewsItem(title="Moon", source="T", sentiment=SentimentType.POSITIVE, impact=ImpactLevel.LOW),
        ]
        summary = service.compute_sentiment_summary(items)
        assert summary.overall_sentiment == SentimentType.POSITIVE
        assert summary.sentiment_score > 0
        assert summary.positive_count == 3

    def test_all_negative_returns_negative(self):
        """Tous les articles négatifs → score négatif."""
        service = NewsService()
        items = [
            NewsItem(title="Crash", source="T", sentiment=SentimentType.NEGATIVE, impact=ImpactLevel.LOW),
            NewsItem(title="Dump", source="T", sentiment=SentimentType.NEGATIVE, impact=ImpactLevel.LOW),
        ]
        summary = service.compute_sentiment_summary(items)
        assert summary.overall_sentiment == SentimentType.NEGATIVE
        assert summary.sentiment_score < 0
        assert summary.negative_count == 2

    def test_mixed_returns_neutral(self):
        """Mix équilibré → neutre."""
        service = NewsService()
        items = [
            NewsItem(title="Bull", source="T", sentiment=SentimentType.POSITIVE, impact=ImpactLevel.LOW),
            NewsItem(title="Bear", source="T", sentiment=SentimentType.NEGATIVE, impact=ImpactLevel.LOW),
        ]
        summary = service.compute_sentiment_summary(items)
        assert summary.sentiment_score == 0

    def test_empty_returns_default(self):
        """Pas d'articles → résumé par défaut."""
        service = NewsService()
        summary = service.compute_sentiment_summary([])
        assert summary.total_articles == 0
        assert summary.sentiment_score == 0

    def test_high_impact_weighs_more(self):
        """Un article HIGH impact a plus de poids."""
        service = NewsService()
        items = [
            NewsItem(title="Crash", source="T", sentiment=SentimentType.NEGATIVE, impact=ImpactLevel.HIGH),
            NewsItem(title="Up", source="T", sentiment=SentimentType.POSITIVE, impact=ImpactLevel.LOW),
            NewsItem(title="Up", source="T", sentiment=SentimentType.POSITIVE, impact=ImpactLevel.LOW),
        ]
        summary = service.compute_sentiment_summary(items)
        # HIGH=3 pts négatif, 2*LOW=2 pts positif → net -1/5 = -20 → negative
        assert summary.sentiment_score < 0

    def test_score_bounded(self):
        """Le score est toujours entre -100 et +100."""
        service = NewsService()
        items = [
            NewsItem(title="X", source="T", sentiment=SentimentType.POSITIVE, impact=ImpactLevel.HIGH)
            for _ in range(50)
        ]
        summary = service.compute_sentiment_summary(items)
        assert -100 <= summary.sentiment_score <= 100


# ============================================================
# RÉSILIENCE DU SERVICE
# ============================================================

class TestNewsServiceResilience:
    """Tests de résilience du service news."""

    def setup_method(self):
        """Vide le cache avant chaque test."""
        clear_cache()

    @patch("app.services.news_service.httpx.Client")
    def test_source_failure_returns_empty(self, mock_client_class):
        """Si une source échoue, retourne liste vide (pas de crash)."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        service = NewsService()
        items = service.fetch_from_source("Test", "https://fail.example.com/rss")
        assert items == []

    @patch("app.services.news_service.httpx.Client")
    def test_all_sources_fail_returns_empty_response(self, mock_client_class):
        """Si toutes les sources échouent, retourne réponse vide."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        service = NewsService()
        result = service.get_news_with_sentiment()
        assert isinstance(result, NewsResponse)
        assert len(result.items) == 0
        assert result.summary.total_articles == 0

    def test_cache_works(self):
        """Le cache évite de refaire les requêtes."""
        service = NewsService()

        # Simuler des données en cache
        from app.services.news_service import _set_cache
        cached_items = [
            NewsItem(title="Cached", source="Cache", sentiment=SentimentType.NEUTRAL),
        ]
        _set_cache("all_news", cached_items)

        # Pas besoin de mock HTTP, le cache sera utilisé
        items = service.fetch_all_news()
        assert len(items) == 1
        assert items[0].title == "Cached"

    def test_clear_cache(self):
        """clear_cache vide bien le cache."""
        from app.services.news_service import _set_cache, _get_cached
        _set_cache("test", [])
        assert _get_cached("test") is not None
        clear_cache()
        assert _get_cached("test") is None


# ============================================================
# ENDPOINTS
# ============================================================

class TestNewsEndpoints:
    """Tests des routes /news et /news/sentiment."""

    @patch("app.services.news_service.httpx.Client")
    def test_get_news_returns_200(self, mock_client_class, client):
        """GET /news retourne 200."""
        clear_cache()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.text = """
        <rss><channel>
        <item><title>Bitcoin rally continues</title><link>https://ex.com</link></item>
        </channel></rss>
        """
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = client.get("/news")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "summary" in data
        assert "meta" in data

    @patch("app.services.news_service.httpx.Client")
    def test_get_news_sentiment_returns_200(self, mock_client_class, client):
        """GET /news/sentiment retourne 200."""
        clear_cache()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.text = "<rss><channel></channel></rss>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = client.get("/news/sentiment")
        assert response.status_code == 200
        data = response.json()
        assert "total_articles" in data
        assert "sentiment_score" in data
        assert "overall_sentiment" in data

    @patch("app.services.news_service.httpx.Client")
    def test_get_news_with_limit(self, mock_client_class, client):
        """GET /news?limit=5 respecte la limite."""
        clear_cache()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        # Créer 10 items
        items_xml = "".join(
            f'<item><title>News {i}</title><link>https://ex.com/{i}</link></item>'
            for i in range(10)
        )
        mock_response = MagicMock()
        mock_response.text = f"<rss><channel>{items_xml}</channel></rss>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = client.get("/news?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 5

    @patch("app.services.news_service.httpx.Client")
    def test_get_news_with_sentiment_filter(self, mock_client_class, client):
        """GET /news?sentiment=positive filtre correctement."""
        clear_cache()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.text = """
        <rss><channel>
        <item><title>Bitcoin surges with bullish rally momentum</title><link>https://ex.com/1</link></item>
        <item><title>Market crash dump panic</title><link>https://ex.com/2</link></item>
        </channel></rss>
        """
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = client.get("/news?sentiment=positive")
        assert response.status_code == 200
        data = response.json()
        # Tous les items retournés doivent être positifs
        for item in data["items"]:
            assert item["sentiment"] == "positive"

    def test_get_news_invalid_sentiment_filter(self, client):
        """GET /news?sentiment=invalid retourne 422."""
        response = client.get("/news?sentiment=invalid")
        assert response.status_code == 422


