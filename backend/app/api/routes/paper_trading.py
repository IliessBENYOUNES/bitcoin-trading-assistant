"""
Routes API Paper Trading.

Endpoints pour la simulation de trading en temps réel :
- GET  /paper/account  — État du compte
- POST /paper/account/reset — Reset du compte
- GET  /paper/status   — Statut complet (compte + position + métriques)
- POST /paper/tick     — Exécuter un tick manuellement
- GET  /paper/trades   — Journal des trades
- GET  /paper/metrics  — Métriques de performance
- POST /paper/close    — Fermeture manuelle de la position ouverte
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.paper_trading_service import PaperTradingService
from app.schemas.paper_trading import (
    PaperAccountCreate,
    PaperAccountResponse,
    PaperTradeResponse,
    PaperTradeListResponse,
    PaperMetrics,
    PaperStatus,
    PaperTickResult,
)

router = APIRouter(prefix="/paper", tags=["Paper Trading"])


@router.get("/account", response_model=PaperAccountResponse)
def get_account(db: Session = Depends(get_db)):
    """Retourne le compte paper trading (crée un compte par défaut si absent)."""
    service = PaperTradingService(db)
    account = service.get_or_create_account()
    resp = PaperAccountResponse.model_validate(account)
    # Ajouter la position ouverte si elle existe
    open_pos = service.get_open_position()
    if open_pos:
        resp.open_position = PaperTradeResponse.model_validate(open_pos)
    return resp


@router.post("/account", response_model=PaperAccountResponse)
def create_or_update_account(
    config: PaperAccountCreate,
    db: Session = Depends(get_db),
):
    """
    Crée ou met à jour le compte paper trading.
    Permet de configurer le capital initial et la durée max des positions.
    """
    service = PaperTradingService(db)
    account = service.get_or_create_account(config.initial_capital)
    # Mettre à jour les paramètres
    account.max_open_duration_hours = config.max_open_duration_hours
    if not account.is_active:
        account.is_active = True
    db.commit()
    db.refresh(account)
    return PaperAccountResponse.model_validate(account)


@router.post("/account/reset", response_model=PaperAccountResponse)
def reset_account(
    config: PaperAccountCreate = PaperAccountCreate(),
    db: Session = Depends(get_db),
):
    """
    Reset complet du compte paper : supprime tous les trades,
    remet le capital à la valeur initiale.
    """
    service = PaperTradingService(db)
    account = service.reset_account(config.initial_capital)
    account.max_open_duration_hours = config.max_open_duration_hours
    db.commit()
    db.refresh(account)
    return PaperAccountResponse.model_validate(account)


@router.get("/status", response_model=PaperStatus)
def get_status(db: Session = Depends(get_db)):
    """
    Statut complet du paper trading :
    - Compte (capital, PnL)
    - Position ouverte (si active)
    - Métriques de performance
    - État du scheduler paper trading
    """
    service = PaperTradingService(db)
    return service.get_status()


@router.post("/tick", response_model=PaperTickResult)
def manual_tick(db: Session = Depends(get_db)):
    """
    Exécute un tick manuellement (utile pour debug/test).

    Le tick :
    1. Récupère le prix courant
    2. Vérifie les SL/TP/expiration de la position ouverte
    3. Si pas de position → consulte le moteur de décision
    4. Ouvre/ferme des positions selon les résultats
    """
    service = PaperTradingService(db)
    return service.tick()


@router.get("/trades", response_model=PaperTradeListResponse)
def get_trades(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str = Query(default=None, description="Filtre: open, closed, closed_tp, closed_sl, etc."),
    db: Session = Depends(get_db),
):
    """Liste des trades paper avec pagination et filtres."""
    service = PaperTradingService(db)
    trades, total = service.get_trades(limit=limit, offset=offset, status_filter=status)
    return PaperTradeListResponse(
        trades=[PaperTradeResponse.model_validate(t) for t in trades],
        total=total,
    )


@router.get("/metrics", response_model=PaperMetrics)
def get_metrics(db: Session = Depends(get_db)):
    """
    Métriques de performance du paper trading :
    Win rate, PnL, Sharpe, drawdown, profit factor, buy & hold comparison.
    """
    service = PaperTradingService(db)
    return service.get_metrics()


@router.post("/close", response_model=PaperTradeResponse)
def close_position(
    reason: str = Query(default="Fermeture manuelle", max_length=200),
    db: Session = Depends(get_db),
):
    """Ferme manuellement la position ouverte."""
    service = PaperTradingService(db)
    trade = service.close_position_manual(reason)
    if trade is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail="Aucune position ouverte à fermer"
        )
    return PaperTradeResponse.model_validate(trade)

