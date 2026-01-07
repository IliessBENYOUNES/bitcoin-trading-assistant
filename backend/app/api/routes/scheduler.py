"""
Routes pour le scheduler.

Endpoints:
- GET /scheduler/status : État du scheduler
"""

from fastapi import APIRouter

from app.tasks.scheduler import get_status

router = APIRouter(
    prefix="/scheduler",
    tags=["Scheduler"]
)


@router.get(
    "/status",
    summary="État du scheduler",
    description="""
    Retourne l'état actuel du scheduler automatique.
    
    Champs:
    - enabled: si le scheduler est configuré pour tourner
    - running: si le scheduler est actuellement actif
    - interval_minutes: intervalle entre les jobs
    - symbol: paire tradée
    - days: nombre de jours d'historique
    - last_run_time: dernier run (UTC ISO8601)
    - next_run_time: prochain run prévu (UTC ISO8601)
    - last_result: résultat du dernier run (success/error + détails)
    """
)
def scheduler_status() -> dict:
    """Retourne l'état du scheduler."""
    return get_status()
