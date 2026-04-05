"""
Routes API pour le scheduler.
"""

from fastapi import APIRouter

from app.tasks.scheduler import get_status, fetch_candles_4h_job, fetch_candles_30m_job, fetch_news_job

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
def scheduler_status():
    """
    Retourne l'état du scheduler avec les 3 jobs.

    Response:
    {
        "enabled": bool,
        "running": bool,
        "symbol": str,
        "jobs": {
            "4h": { ... },
            "30m": { ... },
            "news": {
                "interval_minutes": int,
                "last_run_time": str|null,
                "next_run_time": str|null,
                "last_result": dict|null
            }
        }
    }
    """
    return get_status()


@router.post("/trigger/4h")
def trigger_4h_job():
    """Déclenche manuellement le job 4H."""
    fetch_candles_4h_job()
    return {"status": "triggered", "job": "4h"}


@router.post("/trigger/30m")
def trigger_30m_job():
    """Déclenche manuellement le job 30M."""
    fetch_candles_30m_job()
    return {"status": "triggered", "job": "30m"}


@router.post("/trigger/news")
def trigger_news_job():
    """Déclenche manuellement la persistance des news RSS."""
    fetch_news_job()
    return {"status": "triggered", "job": "news"}
