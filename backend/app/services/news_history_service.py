"""
Service de persistance des news crypto en base de données.

Ce service gère :
1. La persistance automatique des news RSS collectées par NewsService
2. La persistance des news CryptoCompare (historique depuis 2015, gratuit)
3. Le calcul d'un score de sentiment agrégé par jour (pour le walk-forward)
4. La requête d'articles et de sentiment historique à une date donnée

ARCHITECTURE :
- NewsService (existant) collecte via RSS + cache mémoire 5min → temps réel
- CryptoCompareService (v1.2.3b) collecte via API JSON → historique profond
- NewsHistoryService persiste en DB → historique permanent
- Le scheduler appelle persist_current_news() + persist_cryptocompare_recent()

SCORE DE SENTIMENT PAR ARTICLE :
- positive + high impact → +75
- positive + medium impact → +50
- positive + low impact → +25
- negative + high impact → -75
- negative + medium impact → -50
- negative + low impact → -25
- neutral → 0

SCORE QUOTIDIEN AGRÉGÉ :
- Moyenne pondérée des scores individuels, normalisée -100/+100
- Compatible avec le moteur de décision existant
"""

import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.news_history import NewsHistory
from app.services.news_service import NewsService, classify_sentiment, score_impact, extract_keywords
from app.schemas.news import SentimentType, ImpactLevel, NewsItem

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES
# ============================================================

# Score de sentiment par article : sentiment × impact
SENTIMENT_SCORES = {
    (SentimentType.POSITIVE, ImpactLevel.HIGH): 75,
    (SentimentType.POSITIVE, ImpactLevel.MEDIUM): 50,
    (SentimentType.POSITIVE, ImpactLevel.LOW): 25,
    (SentimentType.NEGATIVE, ImpactLevel.HIGH): -75,
    (SentimentType.NEGATIVE, ImpactLevel.MEDIUM): -50,
    (SentimentType.NEGATIVE, ImpactLevel.LOW): -25,
    (SentimentType.NEUTRAL, ImpactLevel.HIGH): 0,
    (SentimentType.NEUTRAL, ImpactLevel.MEDIUM): 0,
    (SentimentType.NEUTRAL, ImpactLevel.LOW): 0,
}

# Poids par impact pour l'agrégation quotidienne
IMPACT_WEIGHTS = {
    ImpactLevel.HIGH: 3.0,
    ImpactLevel.MEDIUM: 2.0,
    ImpactLevel.LOW: 1.0,
    # Fallback pour les strings bruts
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}


# ============================================================
# UTILITAIRES
# ============================================================

def compute_article_score(sentiment: str, impact: str) -> float:
    """
    Calcule le score de sentiment d'un article individuel.

    Args:
        sentiment: "positive", "negative", "neutral"
        impact: "high", "medium", "low"

    Returns:
        Score entre -75 et +75
    """
    try:
        sent_enum = SentimentType(sentiment)
        imp_enum = ImpactLevel(impact)
        return float(SENTIMENT_SCORES.get((sent_enum, imp_enum), 0))
    except (ValueError, KeyError):
        return 0.0


# ============================================================
# SERVICE
# ============================================================

class NewsHistoryService:
    """
    Service de persistance et requête des news historiques.

    Usage :
        service = NewsHistoryService(db_session)
        result = service.persist_current_news()  # Persiste les news RSS actuelles
        score = service.get_daily_sentiment("2024-01-15")  # Score agrégé d'un jour
    """

    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # PERSISTANCE DES NEWS RSS
    # ================================================================

    def persist_current_news(self) -> dict:
        """
        Collecte les news depuis les sources RSS et les persiste en base.

        Utilise le NewsService existant pour le fetch, puis fait un upsert
        en base dédoublonné par URL.

        Returns:
            dict avec inserted, updated, skipped, total_in_db
        """
        t0 = time.time()

        # Collecter les news via le service existant
        news_service = NewsService()
        items = news_service.fetch_all_news()

        if not items:
            logger.info("NewsHistoryService: aucune news à persister")
            return {
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "total_fetched": 0,
                "total_in_db": self._count_total(),
                "duration_seconds": round(time.time() - t0, 2),
            }

        inserted = 0
        updated = 0
        skipped = 0

        for item in items:
            try:
                result = self._upsert_news_item(item)
                if result == "inserted":
                    inserted += 1
                elif result == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.warning(f"Erreur persistance news '{item.title[:50]}': {e}")
                continue

        # Commit en une seule transaction
        self.db.commit()

        total_in_db = self._count_total()
        duration = round(time.time() - t0, 2)

        logger.info(
            f"NewsHistory: {inserted} insérés, {updated} mis à jour, "
            f"{skipped} identiques sur {len(items)} articles ({duration}s). "
            f"Total en base: {total_in_db}"
        )

        return {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "total_fetched": len(items),
            "total_in_db": total_in_db,
            "duration_seconds": duration,
        }

    def _upsert_news_item(self, item: NewsItem) -> str:
        """
        Upsert un article en base. Dédoublonne par URL.

        Returns:
            "inserted", "updated" ou "skipped"
        """
        sentiment_str = item.sentiment.value if isinstance(item.sentiment, SentimentType) else str(item.sentiment)
        impact_str = item.impact.value if isinstance(item.impact, ImpactLevel) else str(item.impact)
        article_score = compute_article_score(sentiment_str, impact_str)
        keywords_json = json.dumps(item.keywords) if item.keywords else None

        # Chercher par URL si disponible
        existing = None
        if item.url:
            existing = (
                self.db.query(NewsHistory)
                .filter(NewsHistory.url == item.url)
                .first()
            )

        # Fallback : chercher par (source, title) si pas d'URL
        if existing is None and not item.url:
            existing = (
                self.db.query(NewsHistory)
                .filter(
                    NewsHistory.source == item.source,
                    NewsHistory.title == item.title,
                )
                .first()
            )

        if existing:
            # Vérifier si le contenu a changé
            if (existing.sentiment == sentiment_str and
                    existing.impact == impact_str and
                    existing.description == item.description):
                return "skipped"

            # Mettre à jour
            existing.sentiment = sentiment_str
            existing.impact = impact_str
            existing.sentiment_score = article_score
            existing.description = item.description
            existing.keywords = keywords_json
            return "updated"

        # Insérer
        new_entry = NewsHistory(
            title=item.title,
            url=item.url,
            source=item.source,
            description=item.description,
            published_at=item.published_at,
            sentiment=sentiment_str,
            impact=impact_str,
            sentiment_score=article_score,
            keywords=keywords_json,
        )
        self.db.add(new_entry)
        return "inserted"

    # ================================================================
    # SCORE DE SENTIMENT QUOTIDIEN AGRÉGÉ
    # ================================================================

    def get_daily_sentiment(
        self,
        target_date: str,
        tolerance_days: int = 3,
    ) -> Optional[float]:
        """
        Calcule le score de sentiment agrégé pour une date donnée.

        Agrège les articles du jour (±tolérance) en un score -100/+100,
        compatible avec le moteur de décision.

        Args:
            target_date: Date ISO (ex: "2024-01-15")
            tolerance_days: Fenêtre de recherche autour de la date

        Returns:
            Score normalisé -100/+100, ou None si aucun article trouvé
        """
        target_dt = datetime.fromisoformat(target_date).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )

        # Chercher les articles dans la fenêtre
        window_start = target_dt - timedelta(days=tolerance_days)
        window_end = target_dt + timedelta(days=tolerance_days + 1)  # +1 pour inclure la fin de la journée

        articles = (
            self.db.query(NewsHistory)
            .filter(
                NewsHistory.published_at >= window_start,
                NewsHistory.published_at < window_end,
            )
            .all()
        )

        if not articles:
            return None

        # Calculer le score pondéré par impact
        weighted_sum = 0.0
        total_weight = 0.0

        for article in articles:
            weight = IMPACT_WEIGHTS.get(article.impact, 1.0)
            weighted_sum += article.sentiment_score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        # Normaliser sur -100/+100
        raw_score = weighted_sum / total_weight
        # Les scores articles vont de -75 à +75, on normalise vers -100/+100
        normalized = max(-100.0, min(100.0, raw_score * (100.0 / 75.0)))

        return round(normalized, 1)

    # ================================================================
    # REQUÊTES D'ARTICLES HISTORIQUES
    # ================================================================

    def get_articles_at_date(
        self,
        target_date: str,
        tolerance_days: int = 1,
    ) -> list[dict]:
        """
        Récupère les articles autour d'une date donnée.

        Returns:
            Liste de dicts avec title, source, sentiment, impact, published_at
        """
        target_dt = datetime.fromisoformat(target_date).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )

        window_start = target_dt - timedelta(days=tolerance_days)
        window_end = target_dt + timedelta(days=tolerance_days + 1)

        articles = (
            self.db.query(NewsHistory)
            .filter(
                NewsHistory.published_at >= window_start,
                NewsHistory.published_at < window_end,
            )
            .order_by(NewsHistory.published_at.desc())
            .all()
        )

        return [
            {
                "title": a.title,
                "source": a.source,
                "sentiment": a.sentiment,
                "impact": a.impact,
                "sentiment_score": a.sentiment_score,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "url": a.url,
            }
            for a in articles
        ]

    # ================================================================
    # PLAGE ET STATISTIQUES
    # ================================================================

    def get_range(self, source: Optional[str] = None) -> dict:
        """Retourne la plage de dates et le nombre d'articles en base."""
        query = self.db.query(NewsHistory)
        if source:
            query = query.filter(NewsHistory.source == source)

        min_date = self.db.query(func.min(NewsHistory.published_at))
        max_date = self.db.query(func.max(NewsHistory.published_at))
        count = self.db.query(func.count(NewsHistory.id))

        if source:
            min_date = min_date.filter(NewsHistory.source == source)
            max_date = max_date.filter(NewsHistory.source == source)
            count = count.filter(NewsHistory.source == source)

        min_d = min_date.scalar()
        max_d = max_date.scalar()
        total = count.scalar() or 0

        return {
            "source": source or "all",
            "min_date": min_d.isoformat() if min_d else None,
            "max_date": max_d.isoformat() if max_d else None,
            "total_articles": total,
            "has_data": total > 0,
        }

    def get_coverage(self) -> dict:
        """Couverture par source."""
        sources = (
            self.db.query(NewsHistory.source)
            .distinct()
            .all()
        )

        source_ranges = []
        total = 0

        for (source_name,) in sources:
            range_info = self.get_range(source_name)
            source_ranges.append(range_info)
            total += range_info["total_articles"]

        return {
            "sources": source_ranges,
            "total_articles": total,
        }

    # ================================================================
    # CHARGEMENT CRYPTOCOMPARE NEWS HISTORIQUES (v1.2.3b)
    # ================================================================

    def load_cryptocompare_history(
        self,
        start_year: int = 2015,
        max_pages: int = 100,
        categories: str = "BTC",
    ) -> dict:
        """
        Charge les news historiques depuis CryptoCompare et les persiste en base.

        Pagination en arrière via lTs (last timestamp).
        S'arrête quand :
        - Les articles sont antérieurs à start_year
        - Il n'y a plus d'articles
        - max_pages est atteint

        DELTA LOADING : commence à partir du plus ancien article CryptoCompare
        déjà en base, pour ne charger que ce qui manque.

        Args:
            start_year: Année de départ (défaut: 2015)
            max_pages: Maximum de pages à charger (garde-fou)
            categories: Catégories CryptoCompare (défaut: BTC)

        Returns:
            dict avec inserted, skipped, total_fetched, pages_loaded, etc.
        """
        from app.services.cryptocompare_service import (
            CryptoCompareService,
            CRYPTOCOMPARE_SOURCE,
            CRYPTOCOMPARE_PAGE_DELAY,
        )

        t0 = time.time()

        # Delta loading : trouver le plus ancien article CryptoCompare en base
        oldest_in_db = (
            self.db.query(func.min(NewsHistory.published_at))
            .filter(NewsHistory.source == CRYPTOCOMPARE_SOURCE)
            .scalar()
        )

        # Déterminer le lTs de départ
        start_lts = None
        if oldest_in_db is not None:
            # Commencer juste avant le plus ancien article existant
            start_lts = int(oldest_in_db.timestamp())
            logger.info(
                f"CryptoCompare: delta mode — DB a des données depuis "
                f"{oldest_in_db.date()}, pagination à partir de lTs={start_lts}"
            )
        else:
            logger.info("CryptoCompare: full mode — premier chargement")

        # Limite de date : s'arrêter avant start_year
        stop_timestamp = int(datetime(start_year, 1, 1, tzinfo=timezone.utc).timestamp())

        client = CryptoCompareService()
        total_fetched = 0
        total_inserted = 0
        total_skipped = 0
        pages_loaded = 0
        next_lts = start_lts

        for page in range(max_pages):
            items, new_lts = client.fetch_news_page(
                lTs=next_lts, categories=categories
            )

            if not items:
                logger.info(f"CryptoCompare: page {page + 1} vide, arrêt")
                break

            pages_loaded += 1
            total_fetched += len(items)

            # Persister chaque article via _upsert_news_item
            page_inserted = 0
            reached_start = False

            for item in items:
                # Vérifier si on a dépassé start_year
                if item.published_at and item.published_at.timestamp() < stop_timestamp:
                    reached_start = True
                    continue

                result = self._upsert_news_item(item)
                if result == "inserted":
                    page_inserted += 1
                    total_inserted += 1
                else:
                    total_skipped += 1

            # Commit par page (pas par article) pour la performance
            self.db.commit()

            logger.info(
                f"CryptoCompare page {page + 1}: "
                f"{page_inserted} insérés / {len(items)} articles"
            )

            # Conditions d'arrêt
            if reached_start:
                logger.info(
                    f"CryptoCompare: atteint l'année {start_year}, arrêt"
                )
                break

            if new_lts is None or (next_lts is not None and new_lts >= next_lts):
                logger.info("CryptoCompare: plus de pagination possible, arrêt")
                break

            next_lts = new_lts

            # Rate limiting entre les pages
            if page < max_pages - 1:
                time.sleep(CRYPTOCOMPARE_PAGE_DELAY)

        total_in_db = self._count_total()
        cc_count = self._count_by_source(CRYPTOCOMPARE_SOURCE)
        duration = round(time.time() - t0, 2)

        logger.info(
            f"CryptoCompare historique: {total_inserted} insérés, "
            f"{total_skipped} déjà en base, {pages_loaded} pages chargées "
            f"({duration}s). Total CryptoCompare: {cc_count}, Total DB: {total_in_db}"
        )

        return {
            "source": CRYPTOCOMPARE_SOURCE,
            "pages_loaded": pages_loaded,
            "total_fetched": total_fetched,
            "inserted": total_inserted,
            "skipped": total_skipped,
            "total_cryptocompare": cc_count,
            "total_in_db": total_in_db,
            "duration_seconds": duration,
        }

    def persist_cryptocompare_recent(self) -> dict:
        """
        Persiste les news CryptoCompare les plus récentes (1 page).

        Utilisé par le scheduler pour enrichir le corpus en continu.
        Plus léger que load_cryptocompare_history() (une seule requête).

        Returns:
            dict avec inserted, skipped, total_in_db
        """
        from app.services.cryptocompare_service import (
            CryptoCompareService,
            CRYPTOCOMPARE_SOURCE,
        )

        t0 = time.time()

        client = CryptoCompareService()
        items = client.fetch_all_recent(max_pages=1)

        if not items:
            logger.info("CryptoCompare recent: aucune news")
            return {
                "source": CRYPTOCOMPARE_SOURCE,
                "inserted": 0,
                "skipped": 0,
                "total_fetched": 0,
                "total_in_db": self._count_total(),
                "duration_seconds": round(time.time() - t0, 2),
            }

        inserted = 0
        skipped = 0

        for item in items:
            result = self._upsert_news_item(item)
            if result == "inserted":
                inserted += 1
            else:
                skipped += 1

        self.db.commit()

        total_in_db = self._count_total()
        duration = round(time.time() - t0, 2)

        logger.info(
            f"CryptoCompare recent: {inserted} insérés, "
            f"{skipped} déjà en base sur {len(items)} articles ({duration}s)"
        )

        return {
            "source": CRYPTOCOMPARE_SOURCE,
            "inserted": inserted,
            "skipped": skipped,
            "total_fetched": len(items),
            "total_in_db": total_in_db,
            "duration_seconds": duration,
        }

    # ================================================================
    # UTILITAIRES INTERNES
    # ================================================================

    def _count_total(self) -> int:
        """Nombre total d'articles en base."""
        return self.db.query(func.count(NewsHistory.id)).scalar() or 0

    def _count_by_source(self, source: str) -> int:
        """Nombre d'articles en base pour une source donnée."""
        return (
            self.db.query(func.count(NewsHistory.id))
            .filter(NewsHistory.source == source)
            .scalar()
        ) or 0

