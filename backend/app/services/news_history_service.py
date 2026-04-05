"""
Service de persistance des news crypto en base de données.

Ce service gère :
1. La persistance automatique des news RSS collectées par NewsService
2. Le calcul d'un score de sentiment agrégé par jour (pour le walk-forward)
3. La requête d'articles et de sentiment historique à une date donnée

ARCHITECTURE :
- NewsService (existant) collecte via RSS + cache mémoire 5min → temps réel
- NewsHistoryService (nouveau) persiste en DB → historique permanent
- Le scheduler appelle persist_current_news() toutes les 30 minutes

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

    def _count_total(self) -> int:
        """Nombre total d'articles en base."""
        return self.db.query(func.count(NewsHistory.id)).scalar() or 0

