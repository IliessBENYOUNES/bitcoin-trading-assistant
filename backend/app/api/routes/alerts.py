"""
Routes pour les alertes.

Endpoints :
- GET    /alerts           : Lister les alertes (filtre optionnel par symbol/status)
- POST   /alerts           : Créer une alerte
- GET    /alerts/{id}      : Récupérer une alerte
- PUT    /alerts/{id}      : Modifier une alerte
- DELETE /alerts/{id}      : Supprimer une alerte
- POST   /alerts/check     : Évaluer toutes les alertes actives (polling)
- GET    /alerts/notifications : Récupérer les alertes récemment déclenchées
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.alert import Alert
from app.schemas.alert import (
    AlertCreate,
    AlertUpdate,
    AlertResponse,
    AlertCheckResponse,
)
from app.services.alert_service import AlertService

router = APIRouter(
    prefix="/alerts",
    tags=["Alerts"],
)


@router.get(
    "",
    response_model=list[AlertResponse],
    summary="Lister les alertes",
)
def list_alerts(
    symbol: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AlertResponse]:
    """Retourne toutes les alertes, avec filtres optionnels."""
    service = AlertService(db)
    alerts = service.get_all(symbol=symbol)
    if status:
        alerts = [a for a in alerts if a.status == status]
    return alerts


@router.post(
    "",
    response_model=AlertResponse,
    status_code=201,
    summary="Créer une alerte",
)
def create_alert(
    data: AlertCreate,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Crée une nouvelle alerte."""
    service = AlertService(db)
    alert = service.create(**data.model_dump())
    return alert


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Récupérer une alerte",
)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Récupère une alerte par ID."""
    service = AlertService(db)
    alert = service.get_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return alert


@router.put(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Modifier une alerte",
)
def update_alert(
    alert_id: int,
    data: AlertUpdate,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Modifie une alerte existante."""
    service = AlertService(db)
    # Ne passer que les champs explicitement fournis
    update_data = data.model_dump(exclude_unset=True)
    alert = service.update(alert_id, **update_data)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return alert


@router.delete(
    "/{alert_id}",
    status_code=204,
    summary="Supprimer une alerte",
)
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Supprime une alerte."""
    service = AlertService(db)
    deleted = service.delete(alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")


@router.post(
    "/check",
    response_model=AlertCheckResponse,
    summary="Évaluer les alertes actives",
)
def check_alerts(
    symbol: str = Query(default="BTC/USD"),
    timeframe: str = Query(default="4h"),
    db: Session = Depends(get_db),
) -> AlertCheckResponse:
    """
    Évalue toutes les alertes actives contre les données de marché actuelles.

    Utilisé en polling par le frontend pour détecter les déclenchements.
    """
    service = AlertService(db)
    return service.check_alerts(symbol=symbol, timeframe=timeframe)


@router.get(
    "/notifications",
    response_model=list[AlertResponse],
    summary="Alertes récemment déclenchées",
)
def get_notifications(
    symbol: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AlertResponse]:
    """Retourne les alertes récemment déclenchées (status=triggered)."""
    service = AlertService(db)
    alerts = service.get_all(symbol=symbol)
    return [a for a in alerts if a.status == "triggered"]

