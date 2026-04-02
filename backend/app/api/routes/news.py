"""
Routes API pour les news et le sentiment.

Endpoints :
- GET /news           : Liste des articles récents avec sentiment et impact
- GET /news/sentiment : Résumé du sentiment global uniquement
"""

from fastapi import APIRouter, Query
from app.services.news_service import NewsService
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

