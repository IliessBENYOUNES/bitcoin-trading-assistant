"""
Client CryptoCompare News API — Récupération de news crypto historiques.

API CryptoCompare News (free tier) :
- URL : https://min-api.cryptocompare.com/data/v2/news/
- Gratuit : 100k requêtes/mois, pas de clé API requise
- Historique : depuis 2015, paginable via paramètre lTs (last timestamp)
- Retourne : title, body, url, source, published_on (unix), categories

PAGINATION :
- Sans lTs → les news les plus récentes
- Avec lTs=<unix_timestamp> → les news AVANT ce timestamp
- On pagine en arrière en utilisant le published_on du dernier article de chaque page

INTÉGRATION :
- Les news CryptoCompare sont converties en NewsItem (même format que les RSS)
- Sentiment et impact sont calculés par classify_sentiment() / score_impact()
- Le dédoublonnage se fait par URL dans NewsHistoryService
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.schemas.news import NewsItem, SentimentType, ImpactLevel
from app.services.news_service import classify_sentiment, score_impact, extract_keywords

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES
# ============================================================

CRYPTOCOMPARE_NEWS_URL = "https://min-api.cryptocompare.com/data/v2/news/"
CRYPTOCOMPARE_SOURCE = "CryptoCompare"
CRYPTOCOMPARE_TIMEOUT = 15  # secondes
CRYPTOCOMPARE_PAGE_DELAY = 0.25  # secondes entre les pages (rate limiting)


# ============================================================
# SERVICE
# ============================================================

class CryptoCompareService:
    """
    Client pour l'API CryptoCompare News.

    Usage :
        service = CryptoCompareService()
        items, next_lts = service.fetch_news_page()  # Page récente
        items, next_lts = service.fetch_news_page(lTs=1609459200)  # Avant cette date
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = CRYPTOCOMPARE_TIMEOUT):
        """
        Initialise le client.

        Args:
            api_key: Clé API optionnelle (le free tier fonctionne sans clé)
            timeout: Timeout HTTP en secondes
        """
        self.api_key = api_key
        self.timeout = timeout

    def _build_headers(self) -> dict:
        """Construit les headers HTTP (avec clé API si fournie)."""
        headers = {"User-Agent": "BTC-Insight/1.2"}
        if self.api_key:
            headers["authorization"] = f"Apikey {self.api_key}"
        return headers

    def fetch_news_page(
        self,
        lTs: Optional[int] = None,
        categories: str = "BTC",
        lang: str = "EN",
    ) -> tuple[list[NewsItem], Optional[int]]:
        """
        Récupère une page de news depuis CryptoCompare.

        Args:
            lTs: Timestamp Unix pour paginer en arrière (None = page la plus récente)
            categories: Catégories à filtrer (défaut: BTC)
            lang: Langue (défaut: EN)

        Returns:
            Tuple (liste de NewsItem, next_lTs pour la page suivante ou None)
        """
        params = {
            "lang": lang,
            "categories": categories,
        }
        if lTs is not None:
            params["lTs"] = lTs

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    CRYPTOCOMPARE_NEWS_URL,
                    params=params,
                    headers=self._build_headers(),
                )
                response.raise_for_status()
                data = response.json()

        except httpx.HTTPError as e:
            logger.warning(f"CryptoCompare HTTP error: {e}")
            return [], None
        except Exception as e:
            logger.warning(f"CryptoCompare unexpected error: {e}")
            return [], None

        raw_articles = data.get("Data", [])

        if not raw_articles:
            return [], None

        items = []
        min_published_on = None

        for raw in raw_articles:
            item = self._parse_article(raw)
            if item is not None:
                items.append(item)

            # Trouver le timestamp le plus ancien pour la pagination
            published_on = raw.get("published_on", 0)
            if published_on and (min_published_on is None or published_on < min_published_on):
                min_published_on = published_on

        # next_lTs = timestamp le plus ancien de cette page (pour paginer en arrière)
        next_lTs = min_published_on if min_published_on else None

        logger.debug(
            f"CryptoCompare: {len(items)} articles parsed "
            f"(lTs={lTs}, next_lTs={next_lTs})"
        )

        return items, next_lTs

    def _parse_article(self, raw: dict) -> Optional[NewsItem]:
        """
        Parse un article brut CryptoCompare en NewsItem.

        Champs CryptoCompare :
        - title: titre
        - body: texte complet (peut être long)
        - url: URL de l'article
        - source_info.name: nom de la source originale
        - published_on: timestamp Unix
        - categories: catégories séparées par |
        """
        title = raw.get("title", "").strip()
        if not title:
            return None

        url = raw.get("url", "").strip()
        if not url:
            return None

        # Corps de l'article (on prend un extrait pour le sentiment)
        body = raw.get("body", "") or ""
        # Limiter la description à 500 caractères
        description = body[:500].strip() if body else None

        # Source originale (sous-source de CryptoCompare)
        source_info = raw.get("source_info", {})
        original_source = source_info.get("name", "unknown") if isinstance(source_info, dict) else "unknown"

        # Date de publication
        published_on = raw.get("published_on", 0)
        published_at = None
        if published_on:
            try:
                published_at = datetime.fromtimestamp(int(published_on), tz=timezone.utc)
            except (ValueError, OSError):
                pass

        # Analyse sentiment sur titre + description (comme pour le RSS)
        full_text = f"{title} {description or ''}"
        sentiment = classify_sentiment(full_text)
        impact = score_impact(full_text)
        keywords = extract_keywords(full_text)

        return NewsItem(
            title=title,
            url=url,
            source=CRYPTOCOMPARE_SOURCE,
            published_at=published_at,
            sentiment=sentiment,
            impact=impact,
            keywords=keywords,
            description=f"[{original_source}] {description}" if description else f"[{original_source}]",
        )

    def fetch_all_recent(self, max_pages: int = 1) -> list[NewsItem]:
        """
        Récupère les news les plus récentes (1 ou plusieurs pages).

        Args:
            max_pages: Nombre de pages à récupérer (défaut: 1)

        Returns:
            Liste de NewsItem triée par date (plus récentes en premier)
        """
        all_items: list[NewsItem] = []
        next_lts = None

        for page in range(max_pages):
            items, next_lts = self.fetch_news_page(lTs=next_lts)
            if not items:
                break
            all_items.extend(items)

            if next_lts is None:
                break

            if page < max_pages - 1:
                time.sleep(CRYPTOCOMPARE_PAGE_DELAY)

        # Trier par date (plus récentes en premier)
        all_items.sort(
            key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        return all_items

