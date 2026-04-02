"""
Service de collecte et analyse de news crypto.

Ce service :
1. Collecte des news depuis des flux RSS gratuits (CoinTelegraph, CoinDesk, Bitcoin Magazine)
2. Classifie le sentiment de chaque article (keyword-based, pas de ML)
3. Évalue le niveau d'impact (high/medium/low)
4. Agrège en un score de sentiment global (-100 à +100)

SOURCES :
- CoinTelegraph RSS : https://cointelegraph.com/rss
- CoinDesk RSS      : https://www.coindesk.com/arc/outboundfeeds/rss/
- Bitcoin Magazine   : https://bitcoinmagazine.com/feed

RÉSILIENCE :
- Timeout 10s par source
- Fallback à liste vide si une source échoue
- Cache mémoire TTL 5 minutes (évite de surcharger les sources)
"""

import time
import logging
from typing import Optional
from datetime import datetime, timezone

import httpx

from app.schemas.news import (
    NewsItem,
    NewsSentimentSummary,
    NewsResponse,
    SentimentType,
    ImpactLevel,
)

logger = logging.getLogger(__name__)

# ============================================================
# LISTES DE MOTS-CLÉS POUR LE SENTIMENT
# ============================================================

# Mots-clés bullish (haussiers)
BULLISH_KEYWORDS = [
    "bull", "bullish", "surge", "surges", "rally", "rallies",
    "soar", "soars", "pump", "moon", "breakout", "ath", "all-time high",
    "adopt", "adoption", "approve", "approved", "approval",
    "institutional", "etf approved", "mainstream",
    "growth", "gain", "gains", "record", "highs", "uptrend",
    "optimism", "optimistic", "recovery", "recover",
    "upgrade", "partnership", "launch", "launches",
    "accumulate", "accumulation", "buy signal",
    "support", "strong", "momentum", "breakthrough",
]

# Mots-clés bearish (baissiers)
BEARISH_KEYWORDS = [
    "bear", "bearish", "crash", "crashes", "dump", "dumps",
    "plunge", "plunges", "drop", "drops", "decline", "declines",
    "ban", "bans", "banned", "restrict", "restriction",
    "hack", "hacked", "exploit", "vulnerability", "theft",
    "fraud", "scam", "ponzi", "rug pull", "rugpull",
    "sec lawsuit", "lawsuit", "regulation crackdown", "crackdown",
    "sell-off", "selloff", "capitulation", "panic",
    "fear", "fud", "warning", "risk", "collapse",
    "bankrupt", "bankruptcy", "insolvency", "default",
    "investigation", "sanction", "sanctions",
    "downturn", "correction", "bearish signal",
]

# Mots-clés de haute importance (impact élevé)
HIGH_IMPACT_KEYWORDS = [
    "sec", "etf", "fed", "federal reserve", "regulation",
    "hack", "exploit", "billion", "institutional",
    "ban", "banned", "government", "central bank",
    "halving", "fork", "bankruptcy", "collapse",
    "approval", "reject", "rejected",
    "sanctions", "treasury", "congress",
    "emergency", "crisis", "war",
]

# Mots-clés d'impact moyen
MEDIUM_IMPACT_KEYWORDS = [
    "partnership", "upgrade", "launch", "update",
    "exchange", "listing", "delist", "whale",
    "protocol", "network", "adoption", "million",
    "market cap", "volume", "liquidity",
    "defi", "nft", "layer 2", "lightning",
]


# ============================================================
# CLASSIFIEUR DE SENTIMENT (keyword-based)
# ============================================================

def classify_sentiment(text: str | None) -> SentimentType:
    """
    Classifie le sentiment d'un texte en positif/négatif/neutre.

    Approche keyword-based simple :
    1. Normalise le texte en minuscules
    2. Compte les occurrences de mots bullish et bearish
    3. Si bullish > bearish → positive, sinon negative, sinon neutral
    """
    if not text:
        return SentimentType.NEUTRAL

    text_lower = text.lower()

    bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
    bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)

    if bullish_count > bearish_count:
        return SentimentType.POSITIVE
    elif bearish_count > bullish_count:
        return SentimentType.NEGATIVE
    else:
        return SentimentType.NEUTRAL


def score_impact(text: str | None) -> ImpactLevel:
    """
    Évalue le niveau d'impact d'un article.

    Détection de mots-clés :
    - Mots high_impact → HIGH
    - Mots medium_impact → MEDIUM
    - Sinon → LOW
    """
    if not text:
        return ImpactLevel.LOW

    text_lower = text.lower()

    # Chercher d'abord les mots de haute importance
    high_count = sum(1 for kw in HIGH_IMPACT_KEYWORDS if kw in text_lower)
    if high_count >= 2:
        return ImpactLevel.HIGH

    medium_count = sum(1 for kw in MEDIUM_IMPACT_KEYWORDS if kw in text_lower)
    if high_count >= 1 or medium_count >= 2:
        return ImpactLevel.MEDIUM

    if medium_count >= 1:
        return ImpactLevel.MEDIUM

    return ImpactLevel.LOW


def extract_keywords(text: str | None) -> list[str]:
    """Extrait les mots-clés pertinents trouvés dans le texte."""
    if not text:
        return []

    text_lower = text.lower()
    found = []

    for kw in BULLISH_KEYWORDS + BEARISH_KEYWORDS + HIGH_IMPACT_KEYWORDS:
        if kw in text_lower and kw not in found:
            found.append(kw)

    return found[:10]  # Limiter à 10 mots-clés max


# ============================================================
# PARSEUR RSS SIMPLE (sans dépendance feedparser)
# On parse le XML manuellement pour éviter une dépendance
# ============================================================

def _parse_rss_items(xml_text: str, source: str) -> list[dict]:
    """
    Parse simplement les items d'un flux RSS XML.

    On utilise un parsing basique sans dépendance externe.
    Extrait : title, link, description, pubDate
    """
    items = []
    # Découpe par <item> ... </item>
    parts = xml_text.split("<item>")

    for part in parts[1:]:  # Skip le header avant le premier <item>
        end_idx = part.find("</item>")
        if end_idx == -1:
            continue
        item_xml = part[:end_idx]

        title = _extract_xml_tag(item_xml, "title")
        link = _extract_xml_tag(item_xml, "link")
        description = _extract_xml_tag(item_xml, "description")
        pub_date = _extract_xml_tag(item_xml, "pubDate")

        if title:
            items.append({
                "title": title,
                "url": link,
                "description": description,
                "pub_date": pub_date,
                "source": source,
            })

    return items


def _extract_xml_tag(xml: str, tag: str) -> str | None:
    """Extrait le contenu d'un tag XML simple (pas de namespaces)."""
    # Gère CDATA : <title><![CDATA[...]]></title>
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"

    start_idx = xml.find(start_tag)
    if start_idx == -1:
        return None

    start_idx += len(start_tag)
    end_idx = xml.find(end_tag, start_idx)
    if end_idx == -1:
        return None

    content = xml[start_idx:end_idx].strip()

    # Nettoyer CDATA
    if content.startswith("<![CDATA["):
        content = content[9:]
    if content.endswith("]]>"):
        content = content[:-3]

    # Nettoyer les tags HTML basiques
    import re
    content = re.sub(r'<[^>]+>', '', content).strip()

    return content if content else None


def _parse_pub_date(date_str: str | None) -> datetime | None:
    """Parse une date RFC 822 (format RSS standard)."""
    if not date_str:
        return None

    # Formats courants dans les flux RSS
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",      # "Mon, 01 Apr 2026 12:00:00 +0000"
        "%a, %d %b %Y %H:%M:%S GMT",       # "Mon, 01 Apr 2026 12:00:00 GMT"
        "%Y-%m-%dT%H:%M:%S%z",             # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",              # ISO 8601 UTC
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return None


# ============================================================
# CACHE MÉMOIRE (TTL 5 minutes)
# ============================================================

_cache: dict[str, tuple[float, list[NewsItem]]] = {}
_CACHE_TTL = 300  # 5 minutes


def _get_cached(key: str) -> list[NewsItem] | None:
    """Récupère les news du cache si non expirées."""
    if key in _cache:
        ts, items = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return items
        del _cache[key]
    return None


def _set_cache(key: str, items: list[NewsItem]) -> None:
    """Stocke les news dans le cache."""
    _cache[key] = (time.time(), items)


def clear_cache() -> None:
    """Vide le cache (utile pour les tests)."""
    _cache.clear()


# ============================================================
# SOURCES RSS
# ============================================================

RSS_SOURCES = [
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
    },
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    },
    {
        "name": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/feed",
    },
]


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

class NewsService:
    """
    Service de collecte et analyse de news crypto.

    Usage :
        service = NewsService()
        result = service.get_news_with_sentiment(limit=20)
    """

    def __init__(self, timeout: float = 10.0):
        """
        Initialise le service.

        Args:
            timeout: Timeout HTTP en secondes par source RSS
        """
        self.timeout = timeout

    def fetch_from_source(self, source_name: str, source_url: str) -> list[NewsItem]:
        """
        Collecte les news depuis une source RSS.

        Résilient : retourne une liste vide en cas d'erreur.
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    source_url,
                    headers={"User-Agent": "BTC-Insight/0.9"},
                    follow_redirects=True,
                )
                response.raise_for_status()

            raw_items = _parse_rss_items(response.text, source_name)
            news_items = []

            for raw in raw_items:
                # Combiner titre + description pour l'analyse
                full_text = f"{raw.get('title', '')} {raw.get('description', '')}"

                sentiment = classify_sentiment(full_text)
                impact = score_impact(full_text)
                keywords = extract_keywords(full_text)
                pub_date = _parse_pub_date(raw.get("pub_date"))

                item = NewsItem(
                    title=raw["title"],
                    url=raw.get("url"),
                    source=source_name,
                    published_at=pub_date,
                    sentiment=sentiment,
                    impact=impact,
                    keywords=keywords,
                    description=raw.get("description"),
                )
                news_items.append(item)

            logger.info(f"Fetched {len(news_items)} news from {source_name}")
            return news_items

        except Exception as e:
            logger.warning(f"Failed to fetch news from {source_name}: {e}")
            return []

    def fetch_all_news(self) -> list[NewsItem]:
        """
        Collecte les news depuis toutes les sources RSS.

        Utilise le cache si disponible.
        """
        cache_key = "all_news"
        cached = _get_cached(cache_key)
        if cached is not None:
            logger.debug("Returning cached news")
            return cached

        all_items: list[NewsItem] = []

        for source in RSS_SOURCES:
            items = self.fetch_from_source(source["name"], source["url"])
            all_items.extend(items)

        # Trier par date (plus récentes en premier)
        all_items.sort(
            key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        _set_cache(cache_key, all_items)
        return all_items

    def compute_sentiment_summary(
        self, items: list[NewsItem]
    ) -> NewsSentimentSummary:
        """
        Calcule un résumé de sentiment à partir d'une liste d'articles.

        Le score global (-100 à +100) est basé sur la balance entre
        articles positifs et négatifs, pondérée par l'impact.
        """
        if not items:
            return NewsSentimentSummary()

        positive_count = sum(1 for i in items if i.sentiment == SentimentType.POSITIVE)
        negative_count = sum(1 for i in items if i.sentiment == SentimentType.NEGATIVE)
        neutral_count = sum(1 for i in items if i.sentiment == SentimentType.NEUTRAL)

        # Score pondéré par l'impact
        # HIGH = 3 points, MEDIUM = 2, LOW = 1
        impact_weight = {
            ImpactLevel.HIGH: 3,
            ImpactLevel.MEDIUM: 2,
            ImpactLevel.LOW: 1,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for item in items:
            w = impact_weight[item.impact]
            total_weight += w
            if item.sentiment == SentimentType.POSITIVE:
                weighted_sum += w
            elif item.sentiment == SentimentType.NEGATIVE:
                weighted_sum -= w

        # Normaliser sur -100/+100
        if total_weight > 0:
            raw_score = weighted_sum / total_weight  # -1 à +1
        else:
            raw_score = 0.0

        sentiment_score = int(round(raw_score * 100))
        sentiment_score = max(-100, min(100, sentiment_score))

        # Sentiment global
        if sentiment_score > 15:
            overall = SentimentType.POSITIVE
        elif sentiment_score < -15:
            overall = SentimentType.NEGATIVE
        else:
            overall = SentimentType.NEUTRAL

        return NewsSentimentSummary(
            total_articles=len(items),
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            overall_sentiment=overall,
            sentiment_score=sentiment_score,
        )

    def get_news_with_sentiment(
        self,
        limit: int = 20,
        sentiment_filter: str | None = None,
    ) -> NewsResponse:
        """
        Méthode principale : collecte les news et retourne avec analyse.

        Args:
            limit: Nombre max d'articles à retourner
            sentiment_filter: Filtrer par sentiment (positive/negative/neutral)

        Returns:
            NewsResponse avec items, summary et meta
        """
        all_items = self.fetch_all_news()

        # Filtrer par sentiment si demandé
        if sentiment_filter:
            all_items = [
                i for i in all_items
                if i.sentiment.value == sentiment_filter
            ]

        # Limiter
        limited_items = all_items[:limit]

        # Calculer le résumé sur les items filtrés
        summary = self.compute_sentiment_summary(limited_items)

        return NewsResponse(
            items=limited_items,
            summary=summary,
            meta={
                "sources": [s["name"] for s in RSS_SOURCES],
                "total_fetched": len(all_items),
                "limit": limit,
                "sentiment_filter": sentiment_filter,
                "cached": _get_cached("all_news") is not None,
            },
        )

    def get_sentiment_only(self) -> NewsSentimentSummary:
        """
        Retourne uniquement le résumé du sentiment (pas les articles).

        Utile pour l'intégration dans le score composite.
        """
        all_items = self.fetch_all_news()
        return self.compute_sentiment_summary(all_items)

