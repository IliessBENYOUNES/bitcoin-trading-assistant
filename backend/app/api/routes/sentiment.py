"""
Endpoints API pour le sentiment historique.

Endpoints :
- POST /sentiment/history/load     — Charger le Fear & Greed Index depuis Alternative.me
- GET  /sentiment/history/range    — Plage de dates disponible
- GET  /sentiment/history/coverage — Couverture globale (toutes sources)
- GET  /sentiment/history/at-date  — Sentiment à une date donnée
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.sentiment_history_service import SentimentHistoryService
from app.schemas.sentiment import (
    SentimentLoadConfig,
    SentimentLoadResponse,
    SentimentRangeResponse,
    SentimentAtDateResponse,
    SentimentCoverageResponse,
)

router = APIRouter(prefix="/sentiment", tags=["Sentiment Historique"])


@router.post("/history/load", response_model=SentimentLoadResponse)
def load_sentiment_history(
    config: SentimentLoadConfig = None,
    db: Session = Depends(get_db),
):
    """
    Charge le sentiment historique depuis une source externe.

    Par défaut, charge le Fear & Greed Index (Alternative.me) depuis février 2018.
    L'opération est idempotente : relancer ne crée pas de doublons.
    """
    if config is None:
        config = SentimentLoadConfig()
    service = SentimentHistoryService(db)
    return service.load_fear_and_greed(config)


@router.get("/history/range", response_model=SentimentRangeResponse)
def get_sentiment_range(
    source: str = Query(default="fear_and_greed", description="Source de sentiment"),
    db: Session = Depends(get_db),
):
    """Retourne la plage de dates disponible pour une source de sentiment."""
    service = SentimentHistoryService(db)
    return service.get_range(source)


@router.get("/history/coverage", response_model=SentimentCoverageResponse)
def get_sentiment_coverage(
    db: Session = Depends(get_db),
):
    """Résumé de la couverture sentiment disponible (toutes sources)."""
    service = SentimentHistoryService(db)
    return service.get_coverage()


@router.get("/history/at-date", response_model=SentimentAtDateResponse)
def get_sentiment_at_date(
    date: str = Query(..., description="Date ISO (ex: 2020-06-01)"),
    source: str = Query(default="fear_and_greed", description="Source de sentiment"),
    db: Session = Depends(get_db),
):
    """
    Retourne le sentiment à une date donnée (ou le plus proche disponible).

    Utile pour vérifier le sentiment historique à une date de backtest.
    """
    service = SentimentHistoryService(db)
    result = service.get_sentiment_at_date(date, source)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Aucun sentiment disponible autour du {date} pour la source {source}",
        )
    return result

