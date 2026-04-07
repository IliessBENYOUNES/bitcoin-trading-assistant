"""
Routes pour le Risk Management Engine.

Endpoints :
- GET    /risk/config            : Configuration de risque courante
- POST   /risk/config            : Créer/mettre à jour la config
- PUT    /risk/config            : Mise à jour partielle
- GET    /risk/status            : État temps réel (exposition, perte, kill switch)
- POST   /risk/evaluate          : Évaluer un trade proposé
- POST   /risk/kill-switch/activate    : Activer le kill switch
- POST   /risk/kill-switch/deactivate  : Désactiver le kill switch
- POST   /risk/record-loss       : Enregistrer une perte
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.schemas.risk import (
    RiskConfigCreate,
    RiskConfigUpdate,
    RiskConfigResponse,
    RiskEvaluation,
    RiskStatus,
)
from app.services.risk_service import RiskService

router = APIRouter(
    prefix="/risk",
    tags=["Risk Management"],
)


# ============================================================
# CONFIGURATION
# ============================================================

@router.get(
    "/config",
    response_model=RiskConfigResponse,
    summary="Configuration de risque courante",
)
def get_risk_config(
    db: Session = Depends(get_db),
) -> RiskConfigResponse:
    """Retourne la configuration de risque courante (crée les défauts si vide)."""
    service = RiskService(db)
    config = service.get_config()
    return RiskConfigResponse(
        id=config.id,
        stop_loss_type=config.stop_loss_type,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        max_position_pct=config.max_position_pct,
        total_portfolio_value=config.total_portfolio_value,
        max_daily_loss_pct=config.max_daily_loss_pct,
        daily_loss_current=config.daily_loss_current,
        kill_switch_active=config.kill_switch_active,
        kill_switch_triggered_at=(
            config.kill_switch_triggered_at.isoformat()
            if config.kill_switch_triggered_at else None
        ),
        kill_switch_reason=config.kill_switch_reason,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.post(
    "/config",
    response_model=RiskConfigResponse,
    summary="Créer/mettre à jour la configuration de risque",
)
def create_or_update_risk_config(
    data: RiskConfigCreate,
    db: Session = Depends(get_db),
) -> RiskConfigResponse:
    """Crée ou met à jour la configuration de risque."""
    service = RiskService(db)
    config = service.create_or_update_config(data)
    return RiskConfigResponse(
        id=config.id,
        stop_loss_type=config.stop_loss_type,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        max_position_pct=config.max_position_pct,
        total_portfolio_value=config.total_portfolio_value,
        max_daily_loss_pct=config.max_daily_loss_pct,
        daily_loss_current=config.daily_loss_current,
        kill_switch_active=config.kill_switch_active,
        kill_switch_triggered_at=(
            config.kill_switch_triggered_at.isoformat()
            if config.kill_switch_triggered_at else None
        ),
        kill_switch_reason=config.kill_switch_reason,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.put(
    "/config",
    response_model=RiskConfigResponse,
    summary="Mise à jour partielle de la configuration",
)
def update_risk_config(
    data: RiskConfigUpdate,
    db: Session = Depends(get_db),
) -> RiskConfigResponse:
    """Met à jour partiellement la configuration de risque."""
    service = RiskService(db)
    config = service.update_config(data)
    return RiskConfigResponse(
        id=config.id,
        stop_loss_type=config.stop_loss_type,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        max_position_pct=config.max_position_pct,
        total_portfolio_value=config.total_portfolio_value,
        max_daily_loss_pct=config.max_daily_loss_pct,
        daily_loss_current=config.daily_loss_current,
        kill_switch_active=config.kill_switch_active,
        kill_switch_triggered_at=(
            config.kill_switch_triggered_at.isoformat()
            if config.kill_switch_triggered_at else None
        ),
        kill_switch_reason=config.kill_switch_reason,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


# ============================================================
# STATUS
# ============================================================

@router.get(
    "/status",
    response_model=RiskStatus,
    summary="État temps réel du risk engine",
)
def get_risk_status(
    db: Session = Depends(get_db),
) -> RiskStatus:
    """Retourne l'état temps réel : exposition, perte journalière, kill switch."""
    service = RiskService(db)
    return service.get_status()


# ============================================================
# TRADE EVALUATION
# ============================================================

@router.post(
    "/evaluate",
    response_model=RiskEvaluation,
    summary="Évaluer un trade proposé",
)
def evaluate_trade(
    action: str = Query(..., description="Action proposée (acheter, vendre, attendre)"),
    price: float = Query(..., gt=0, description="Prix courant de l'actif"),
    atr: Optional[float] = Query(default=None, gt=0, description="ATR optionnel pour stop-loss dynamique"),
    db: Session = Depends(get_db),
) -> RiskEvaluation:
    """Évalue si un trade proposé respecte les règles de risque."""
    service = RiskService(db)
    return service.evaluate_trade(
        proposed_action=action,
        current_price=price,
        atr_value=atr,
    )


# ============================================================
# KILL SWITCH
# ============================================================

@router.post(
    "/kill-switch/activate",
    response_model=RiskConfigResponse,
    summary="Activer le kill switch",
)
def activate_kill_switch(
    reason: str = Query(default="Activation manuelle", description="Raison du kill switch"),
    db: Session = Depends(get_db),
) -> RiskConfigResponse:
    """Active le kill switch — bloque toutes les opérations de trading."""
    service = RiskService(db)
    config = service.activate_kill_switch(reason=reason)
    return RiskConfigResponse(
        id=config.id,
        stop_loss_type=config.stop_loss_type,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        max_position_pct=config.max_position_pct,
        total_portfolio_value=config.total_portfolio_value,
        max_daily_loss_pct=config.max_daily_loss_pct,
        daily_loss_current=config.daily_loss_current,
        kill_switch_active=config.kill_switch_active,
        kill_switch_triggered_at=(
            config.kill_switch_triggered_at.isoformat()
            if config.kill_switch_triggered_at else None
        ),
        kill_switch_reason=config.kill_switch_reason,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.post(
    "/kill-switch/deactivate",
    response_model=RiskConfigResponse,
    summary="Désactiver le kill switch",
)
def deactivate_kill_switch(
    db: Session = Depends(get_db),
) -> RiskConfigResponse:
    """Désactive le kill switch — autorise à nouveau les opérations."""
    service = RiskService(db)
    config = service.deactivate_kill_switch()
    return RiskConfigResponse(
        id=config.id,
        stop_loss_type=config.stop_loss_type,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        max_position_pct=config.max_position_pct,
        total_portfolio_value=config.total_portfolio_value,
        max_daily_loss_pct=config.max_daily_loss_pct,
        daily_loss_current=config.daily_loss_current,
        kill_switch_active=config.kill_switch_active,
        kill_switch_triggered_at=(
            config.kill_switch_triggered_at.isoformat()
            if config.kill_switch_triggered_at else None
        ),
        kill_switch_reason=config.kill_switch_reason,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


# ============================================================
# RECORD LOSS
# ============================================================

@router.post(
    "/reset-daily-loss",
    summary="Réinitialiser le compteur de perte journalière",
)
def reset_daily_loss(
    db: Session = Depends(get_db),
) -> dict:
    """
    Remet le compteur de perte journalière à zéro.
    Désactive le kill switch s'il a été déclenché par la limite de perte.
    """
    service = RiskService(db)
    config = service.reset_daily_loss()
    daily_limit = config.total_portfolio_value * config.max_daily_loss_pct / 100
    return {
        "daily_loss_current": 0.0,
        "daily_limit_usd": round(daily_limit, 2),
        "kill_switch_active": config.kill_switch_active,
        "message": "Compteur de perte journalière remis à zéro",
    }


@router.post(
    "/record-loss",
    summary="Enregistrer une perte",
)
def record_loss(
    amount: float = Query(..., gt=0, description="Montant de la perte en USD"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Enregistre une perte dans le compteur journalier.
    Déclenche le kill switch si la limite est atteinte.
    """
    service = RiskService(db)
    limit_reached = service.record_loss(amount)
    config = service.get_config()
    return {
        "recorded": amount,
        "daily_loss_current": round(config.daily_loss_current, 2),
        "daily_limit_usd": round(config.total_portfolio_value * config.max_daily_loss_pct / 100, 2),
        "limit_reached": limit_reached,
        "kill_switch_active": config.kill_switch_active,
    }

