"""
Scheduler APScheduler pour automatiser la récupération des candles.

Objectifs:
- Activable/désactivable via env
- Une session DB par exécution (safe)
- State in-memory thread-safe (last_run, next_run, last_result)
- Ne dépend pas du contexte FastAPI (pas de Depends)

Variables d'environnement:
- SCHEDULER_ENABLED: true/false
- SCHEDULER_INTERVAL_MINUTES: intervalle entre les jobs (default: 240 = 4h)
- SCHEDULER_SYMBOL: paire à fetcher (default: BTC/USD)
- SCHEDULER_DAYS: nombre de jours d'historique (default: 7, max: 30)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.database import SessionLocal
from app.models import Candle
from app.services.coingecko_service import CoinGeckoService
from app.utils import normalize_to_utc, align_to_bucket

# Logger
logger = logging.getLogger(__name__)

JOB_ID = "fetch_candles_job"


# =========================
# State thread-safe
# =========================
_state_lock = threading.Lock()

scheduler_state: dict[str, Any] = {
    "enabled": False,
    "running": False,
    "interval_minutes": None,
    "symbol": None,
    "days": None,
    "last_run_time": None,
    "next_run_time": None,
    "last_result": None,
}

_scheduler: Optional[BackgroundScheduler] = None


# =========================
# Config from Pydantic Settings
# =========================
def _read_config() -> dict[str, Any]:
    """Lit la configuration du scheduler depuis Pydantic Settings."""
    settings = get_settings()

    enabled = settings.scheduler_enabled
    interval_minutes = settings.scheduler_interval_minutes
    symbol = settings.scheduler_symbol
    days = settings.scheduler_days

    # Garde-fous
    if interval_minutes < 1:
        interval_minutes = 1
    if days > 30:
        days = 30  # Limite pour éviter timeframe 4d

    return {
        "enabled": enabled,
        "interval_minutes": interval_minutes,
        "symbol": symbol,
        "days": days,
    }


# =========================
# State management
# =========================
def _set_state(**kwargs: Any) -> None:
    """Met à jour l'état du scheduler (thread-safe)."""
    with _state_lock:
        scheduler_state.update(kwargs)


def get_status() -> dict[str, Any]:
    """Retourne l'état actuel du scheduler."""
    with _state_lock:
        def iso(dt: Any) -> Any:
            if isinstance(dt, datetime):
                return dt.astimezone(timezone.utc).isoformat()
            return dt

        return {
            "enabled": scheduler_state["enabled"],
            "running": scheduler_state["running"],
            "interval_minutes": scheduler_state["interval_minutes"],
            "symbol": scheduler_state["symbol"],
            "days": scheduler_state["days"],
            "last_run_time": iso(scheduler_state["last_run_time"]),
            "next_run_time": iso(scheduler_state["next_run_time"]),
            "last_result": scheduler_state["last_result"],
        }


# =========================
# Job logic
# =========================
def _timeframe_from_days(days: int) -> str:
    """
    Détermine le timeframe en fonction du nombre de jours.

    Compatible avec le contrat des indicateurs:
    - <=2j => 30m
    - <=30j => 4h
    """
    if days <= 2:
        return "30m"
    if days <= 30:
        return "4h"
    raise ValueError(
        "SCHEDULER_DAYS > 30 non supporté "
        "(standardise un timeframe 1d avant)."
    )


async def _fetch_and_store(db, symbol: str, days: int) -> dict[str, Any]:
    """
    Récupère les données CoinGecko (async) puis upsert en DB.

    Utilise la même logique d'alignement que les indicateurs.
    """
    timeframe = _timeframe_from_days(days)

    service = CoinGeckoService()
    ohlc_data = await service.get_ohlc(symbol=symbol, days=days)

    if not ohlc_data:
        raise RuntimeError("CoinGecko: aucune donnée OHLC reçue")

    inserted = 0
    updated = 0
    duplicates = 0

    for candle_data in ohlc_data:
        ts = candle_data["timestamp"]
        ts = normalize_to_utc(ts)
        ts = align_to_bucket(ts, timeframe)

        # Match exact sur timestamp aligné
        existing = db.query(Candle).filter(
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp == ts
        ).first()

        # Fallback legacy: +/- 5 min
        if existing is None:
            ts_min = ts - timedelta(minutes=5)
            ts_max = ts + timedelta(minutes=5)
            existing = db.query(Candle).filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= ts_min,
                Candle.timestamp <= ts_max
            ).first()

        if existing:
            # Update seulement si changement réel
            if (
                    existing.close_price != candle_data["close"]
                    or existing.high_price != candle_data["high"]
                    or existing.low_price != candle_data["low"]
                    or existing.open_price != candle_data["open"]
                    or existing.volume != candle_data["volume"]
            ):
                existing.open_price = candle_data["open"]
                existing.high_price = candle_data["high"]
                existing.low_price = candle_data["low"]
                existing.close_price = candle_data["close"]
                existing.volume = candle_data["volume"]
                updated += 1
            else:
                duplicates += 1
            continue

        # Insert
        candle = Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            open_price=candle_data["open"],
            high_price=candle_data["high"],
            low_price=candle_data["low"],
            close_price=candle_data["close"],
            volume=candle_data["volume"],
            source="scheduler"
        )
        db.add(candle)
        inserted += 1

    return {
        "status": "success",
        "symbol": symbol,
        "days": days,
        "timeframe": timeframe,
        "fetched": len(ohlc_data),
        "inserted": inserted,
        "updated": updated,
        "duplicates": duplicates,
    }


def _run_coroutine(coro):
    """Wrapper pour exécuter une coroutine (facilite les tests)."""
    return asyncio.run(coro)


def fetch_candles_job() -> None:
    """
    Job APScheduler (sync) — exécute l'async via asyncio.run.

    Crée sa propre session DB, la ferme dans finally.
    """
    cfg = _read_config()
    symbol = cfg["symbol"]
    days = cfg["days"]

    start = time.perf_counter()
    db = None
    now = datetime.now(timezone.utc)

    logger.info(f"🔄 Scheduler job démarré: {symbol}, {days} jours")

    try:
        db = SessionLocal()
        result = _run_coroutine(_fetch_and_store(db, symbol=symbol, days=days))
        db.commit()

        duration = round(time.perf_counter() - start, 3)
        result["duration_seconds"] = duration

        _set_state(
            last_run_time=now,
            last_result=result,
        )

        logger.info(
            f"✅ Scheduler job terminé: "
            f"fetched={result['fetched']}, "
            f"inserted={result['inserted']}, "
            f"updated={result['updated']}, "
            f"duplicates={result['duplicates']}, "
            f"duration={duration}s"
        )

    except Exception as e:
        if db is not None:
            db.rollback()

        duration = round(time.perf_counter() - start, 3)
        _set_state(
            last_run_time=now,
            last_result={
                "status": "error",
                "error": str(e),
                "duration_seconds": duration,
            },
        )

        logger.error(f"❌ Scheduler job erreur: {e}")

    finally:
        if db is not None:
            db.close()

        # Update next_run_time si scheduler actif
        global _scheduler
        if _scheduler is not None:
            job = _scheduler.get_job(JOB_ID)
            if job and job.next_run_time:
                _set_state(
                    next_run_time=job.next_run_time.astimezone(timezone.utc)
                )


# =========================
# Lifecycle control
# =========================
def start_scheduler() -> None:
    """
    Démarre le scheduler si activé. Idempotent.
    """
    cfg = _read_config()

    # MAJ état de config immédiatement
    _set_state(
        enabled=cfg["enabled"],
        interval_minutes=cfg["interval_minutes"],
        symbol=cfg["symbol"],
        days=cfg["days"],
    )

    if not cfg["enabled"]:
        logger.info("🕐 Scheduler désactivé (SCHEDULER_ENABLED=false)")
        return

    global _scheduler
    if _scheduler is not None and getattr(_scheduler, "running", False):
        logger.warning("⚠️ Scheduler déjà démarré")
        return

    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.add_job(
        fetch_candles_job,
        trigger=IntervalTrigger(minutes=cfg["interval_minutes"]),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.start()

    job = scheduler.get_job(JOB_ID)
    next_run = (
        job.next_run_time.astimezone(timezone.utc)
        if job and job.next_run_time
        else None
    )

    _scheduler = scheduler
    _set_state(
        running=True,
        next_run_time=next_run,
    )

    logger.info(
        f"🕐 Scheduler démarré: "
        f"interval={cfg['interval_minutes']}min, "
        f"symbol={cfg['symbol']}, "
        f"days={cfg['days']}, "
        f"next_run={next_run}"
    )


def stop_scheduler() -> None:
    """
    Arrête le scheduler si actif. Idempotent.
    """
    global _scheduler
    if _scheduler is None:
        _set_state(running=False)
        return

    try:
        _scheduler.shutdown(wait=False)
        logger.info("🛑 Scheduler arrêté")
    finally:
        _scheduler = None
        _set_state(running=False, next_run_time=None)