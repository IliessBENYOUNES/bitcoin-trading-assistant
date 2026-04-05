"""
Routes API pour les news et le sentiment.

Endpoints :
- GET  /news                   : Liste des articles récents avec sentiment et impact
- GET  /news/sentiment         : Résumé du sentiment global uniquement
- POST /news/history/persist   : Persister les news RSS actuelles en base
- GET  /news/history/range     : Plage de dates des news en base
- GET  /news/history/coverage  : Couverture par source
- GET  /news/history/at-date   : Articles et sentiment agrégé à une date
"""

from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.news_service import NewsService
from app.services.news_history_service import NewsHistoryService
from app.schemas.news import NewsResponse, NewsSentimentSummary

router = APIRouter(prefix="/news", tags=["News"])


@router.get("", response_model=NewsResponse)
def get_news(
    limit: int = Query(default=20, ge=1, le=100, description="Nombre max d'articles"),
    sentiment: str | None = Query(
        default=None,
        description="Filtrer par sentiment (positive/negative/neutral)",
        pattern="^(positive|negative|neutral)$",
    ),
):
    """
    Récupère les news crypto récentes avec analyse de sentiment.

    Chaque article est classifié (positive/negative/neutral) avec un niveau
    d'impact (high/medium/low). Le résumé inclut un score global -100/+100.
    """
    service = NewsService()
    return service.get_news_with_sentiment(limit=limit, sentiment_filter=sentiment)


@router.get("/sentiment", response_model=NewsSentimentSummary)
def get_news_sentiment():
    """
    Récupère uniquement le résumé du sentiment global.

    Utile pour intégrer le sentiment dans d'autres analyses
    sans récupérer tous les articles.
    """
    service = NewsService()
    return service.get_sentiment_only()


# ============================================================
# NEWS HISTORY — Persistance en base
# ============================================================


@router.post(
    "/history/persist",
    summary="Persister les news RSS actuelles en base",
    description=(
        "Collecte les news depuis les 3 sources RSS (CoinTelegraph, CoinDesk, "
        "Bitcoin Magazine), les analyse (sentiment + impact), et les stocke en base. "
        "Idempotent : relancer ne crée pas de doublons (dédoublonnage par URL)."
    ),
)
def persist_news(db: Session = Depends(get_db)):
    """Persiste les news RSS actuelles en base de données."""
    service = NewsHistoryService(db)
    return service.persist_current_news()


@router.get(
    "/history/range",
    summary="Plage de dates des news en base",
    description="Retourne la date min/max et le nombre d'articles stockés en base.",
)
def get_news_history_range(
    source: str | None = Query(
        default=None,
        description="Filtrer par source (CoinTelegraph, CoinDesk, Bitcoin Magazine)",
    ),
    db: Session = Depends(get_db),
):
    """Retourne la plage de dates des news en base."""
    service = NewsHistoryService(db)
    return service.get_range(source)


@router.get(
    "/history/coverage",
    summary="Couverture par source",
    description="Résumé de la couverture par source (articles, plages de dates).",
)
def get_news_history_coverage(db: Session = Depends(get_db)):
    """Retourne la couverture des news en base par source."""
    service = NewsHistoryService(db)
    return service.get_coverage()


@router.get(
    "/history/at-date",
    summary="Articles et sentiment à une date",
    description=(
        "Retourne les articles stockés autour d'une date donnée, "
        "ainsi que le score de sentiment agrégé de cette journée."
    ),
)
def get_news_at_date(
    date: str = Query(
        ...,
        description="Date ISO (ex: 2024-01-15)",
    ),
    tolerance_days: int = Query(
        default=1,
        ge=0, le=7,
        description="Fenêtre de recherche autour de la date (jours)",
    ),
    db: Session = Depends(get_db),
):
    """Retourne les articles et le sentiment agrégé à une date."""
    service = NewsHistoryService(db)
    articles = service.get_articles_at_date(date, tolerance_days)
    daily_score = service.get_daily_sentiment(date, tolerance_days)

    return {
        "date": date,
        "tolerance_days": tolerance_days,
        "daily_sentiment_score": daily_score,
        "article_count": len(articles),
        "articles": articles,
    }


