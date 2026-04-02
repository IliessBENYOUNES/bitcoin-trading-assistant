"""
Routes pour le moteur de décision.

Endpoint :
- GET /market/decision : Retourne la décision combinée (signaux + sentiment → scénarios + recommandation)
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.services.decision_service import DecisionService

router = APIRouter(
    prefix="/market",
    tags=["Decision Engine"]
)


@router.get(
    "/decision",
    response_model=dict,
    summary="Moteur de décision (signaux + sentiment → scénarios + recommandation)",
    description=(
        "Combine les signaux techniques (RSI, MACD, SMA, Bollinger) et le sentiment "
        "des news crypto pour produire des scénarios multi-outcome (Hausse / Stable / Baisse) "
        "avec probabilités, et une recommandation explicable (Acheter / Vendre / Attendre)."
    ),
)
def get_decision(
    symbol: str = Query(default="BTC/USD"),
    timeframe: str = Query(default="4h"),
    history_days: Optional[float] = Query(default=None, ge=0.0625, le=365),
    days: Optional[float] = Query(default=None, ge=0.0625, le=365),  # alias toléré
    end_ts: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """
    Retourne la décision de trading basée sur l'analyse combinée.

    Le moteur évalue 8 règles combinant indicateurs techniques et sentiment,
    puis produit 3 scénarios avec probabilités et une recommandation d'action
    avec explication en français.

    Paramètres :
    - symbol : Paire de trading (défaut: BTC/USD)
    - timeframe : Intervalle (1m à 1w, défaut: 4h)
    - history_days / days : Fenêtre d'historique en jours (supporte les fractions)
    - end_ts : Timestamp de fin optionnel (pour backtest)
    """
    effective_days = history_days if history_days is not None else (days if days is not None else 7)

    service = DecisionService(db)
    try:
        return service.analyze(
            symbol=symbol,
            timeframe=timeframe,
            history_days=effective_days,
            end_ts=end_ts,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

