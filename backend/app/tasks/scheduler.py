"""
Scheduler APScheduler pour automatiser la récupération des candles.

Compat objectifs:
- Backward compatible avec l'ancien contrat (tests legacy):
  - scheduler_state: enabled/running/interval_minutes/symbol/days/last_run_time/next_run_time/last_result
  - _read_config() -> enabled, interval_minutes, symbol, days
  - _timeframe_from_days(days) -> "30m" si days<=2, "4h" si days<=30, sinon ValueError (message contient "non supporté")
  - fetch_candles_job() choisit le timeframe selon cfg["days"] (NE DOIT PAS exécuter 4h + 30m en série)

- Mode "dual jobs" (PHASE 2B):
  - JOB_4H: fetch days=7 -> stock 4h -> resample 1d
  - JOB_30M: fetch days=1 -> stock 30m -> resample 1h
  - /scheduler/status expose aussi un bloc "jobs" { "4h": {...}, "30m": {...} }

Variables d'environnement (via Pydantic Settings):
- scheduler_enabled: bool
- scheduler_interval_minutes: int              (interval job 4h / legacy)
- scheduler_interval_30m_minutes: int          (interval job 30m, si présent)
- scheduler_symbol: str
- scheduler_days: int                          (legacy: pilote fetch_candles_job)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Dict

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.database import SessionLocal
from app.models import Candle
from app.services.coingecko_service import CoinGeckoService
from app.services.data_source_router import DataSourceRouter
from app.services.resample_service import (
    resample_4h_to_1d, resample_30m_to_1h,
    resample_30m_to_4h, resample_1h_to_4h,
)
from app.utils import normalize_to_utc, align_to_bucket

logger = logging.getLogger(__name__)

# IDs
JOB_ID_LEGACY = "fetch_candles_job"
JOB_ID_4H = "fetch_candles_4h_job"
JOB_ID_30M = "fetch_candles_30m_job"
JOB_ID_NEWS = "fetch_news_job"

# =========================
# State thread-safe
# =========================
_state_lock = threading.Lock()

# ⚠️ On garde le format legacy + on ajoute jobs
scheduler_state: dict[str, Any] = {
    # legacy fields
    "enabled": False,
    "running": False,
    "interval_minutes": None,
    "symbol": None,
    "days": None,
    "last_run_time": None,
    "next_run_time": None,
    "last_result": None,

    # dual jobs fields
    "jobs": {
        "4h": {
            "interval_minutes": None,
            "days": 7,
            "last_run_time": None,
            "next_run_time": None,
            "last_result": None,
        },
        "30m": {
            "interval_minutes": None,
            "days": 1,
            "last_run_time": None,
            "next_run_time": None,
            "last_result": None,
        },
        "news": {
            "interval_minutes": None,
            "last_run_time": None,
            "next_run_time": None,
            "last_result": None,
        },
    },
}

_scheduler: Optional[BackgroundScheduler] = None


# =========================
# Small coercion helpers (MagicMock-safe)
# =========================
def _as_int(value: Any, default: int) -> int:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)) and value is not None:
            return int(value)
    except Exception:
        pass
    return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _as_str(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


# =========================
# Config from Pydantic Settings
# =========================
def _read_config() -> dict[str, Any]:
    """
    Lit la configuration via get_settings().

    IMPORTANT:
    - Doit rester compatible avec tests legacy (interval_minutes + days)
    - Doit aussi exposer interval_minutes_30m si présent
    """
    settings = get_settings()

    enabled = _as_bool(getattr(settings, "scheduler_enabled", False), False)
    interval_minutes = _as_int(getattr(settings, "scheduler_interval_minutes", 240), 240)
    symbol = _as_str(getattr(settings, "scheduler_symbol", "BTC/USD"), "BTC/USD")
    days = _as_int(getattr(settings, "scheduler_days", 7), 7)

    # Guardrails legacy
    if interval_minutes < 1:
        interval_minutes = 1
    if days > 30:
        days = 30

    # Dual-job interval (may not exist)
    raw_30m = getattr(settings, "scheduler_interval_30m_minutes", None)
    interval_minutes_30m = _as_int(raw_30m, 30)
    if interval_minutes_30m < 1:
        interval_minutes_30m = 1

    # News job interval
    raw_news = getattr(settings, "scheduler_interval_news_minutes", None)
    interval_minutes_news = _as_int(raw_news, 10)
    if interval_minutes_news < 1:
        interval_minutes_news = 1

    return {
        # legacy
        "enabled": enabled,
        "interval_minutes": interval_minutes,
        "symbol": symbol,
        "days": days,
        # dual jobs
        "interval_minutes_4h": interval_minutes,     # reuse
        "interval_minutes_30m": interval_minutes_30m,
        "days_4h": 7,    # fixed policy for job 4h
        "days_30m": 1,   # fixed policy for job 30m (never 2 to avoid CoinGecko quirks)
        "dual_jobs": raw_30m is not None,            # if the setting exists, we enable dual scheduling
        # news job
        "interval_minutes_news": interval_minutes_news,
    }


# =========================
# State management
# =========================
def _set_state(**kwargs: Any) -> None:
    with _state_lock:
        scheduler_state.update(kwargs)


def _set_job_state(job_type: str, **kwargs: Any) -> None:
    with _state_lock:
        if job_type in scheduler_state["jobs"]:
            scheduler_state["jobs"][job_type].update(kwargs)


def get_status() -> dict[str, Any]:
    """
    Retourne:
    - les champs legacy (pour compat)
    - + jobs (4h/30m)
    """
    with _state_lock:

        def iso(dt: Any) -> Any:
            if isinstance(dt, datetime):
                return dt.astimezone(timezone.utc).isoformat()
            return dt

        def format_job(job_data: dict) -> dict:
            result = {
                "interval_minutes": job_data["interval_minutes"],
                "last_run_time": iso(job_data["last_run_time"]),
                "next_run_time": iso(job_data["next_run_time"]),
                "last_result": job_data["last_result"],
            }
            # Ajouter "days" seulement pour les jobs candles (pas pour news)
            if "days" in job_data:
                result["days"] = job_data["days"]
            return result

        return {
            # legacy
            "enabled": scheduler_state["enabled"],
            "running": scheduler_state["running"],
            "interval_minutes": scheduler_state["interval_minutes"],
            "symbol": scheduler_state["symbol"],
            "days": scheduler_state["days"],
            "last_run_time": iso(scheduler_state["last_run_time"]),
            "next_run_time": iso(scheduler_state["next_run_time"]),
            "last_result": scheduler_state["last_result"],
            # dual
            "jobs": {
                "4h": format_job(scheduler_state["jobs"]["4h"]),
                "30m": format_job(scheduler_state["jobs"]["30m"]),
                "news": format_job(scheduler_state["jobs"]["news"]),
            },
        }


# =========================
# Timeframe policy (legacy)
# =========================
def _timeframe_from_days(days: int) -> str:
    if days <= 2:
        return "30m"
    if days <= 30:
        return "4h"
    raise ValueError("days > 30 non supporté")


# =========================
# Fetch + store (async)
# =========================
async def _fetch_and_store(db, symbol: str, days: int, timeframe: str) -> dict[str, Any]:
    """
    Fetch via DataSourceRouter (Binance prioritaire, CoinGecko fallback)
    + upsert in DB.

    timeframe is explicit (no auto-detection here).
    Returns min_ts/max_ts for resample window.
    """
    router = DataSourceRouter()
    ohlc_data = await router.get_candles(
        symbol=symbol, timeframe=timeframe, days=days
    )

    if not ohlc_data:
        raise RuntimeError("CoinGecko: aucune donnée OHLC reçue")

    inserted = 0
    updated = 0
    duplicates = 0
    min_ts: Optional[datetime] = None
    max_ts: Optional[datetime] = None

    for candle_data in ohlc_data:
        ts = normalize_to_utc(candle_data["timestamp"])
        ts = align_to_bucket(ts, timeframe)

        if min_ts is None or ts < min_ts:
            min_ts = ts
        if max_ts is None or ts > max_ts:
            max_ts = ts

        existing = db.query(Candle).filter(
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp == ts
        ).first()

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
            if (
                    existing.open_price != candle_data["open"]
                    or existing.high_price != candle_data["high"]
                    or existing.low_price != candle_data["low"]
                    or existing.close_price != candle_data["close"]
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

        db.add(Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            open_price=candle_data["open"],
            high_price=candle_data["high"],
            low_price=candle_data["low"],
            close_price=candle_data["close"],
            volume=candle_data["volume"],
            source="scheduler",
        ))
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
        "min_ts": min_ts,
        "max_ts": max_ts,
    }


def _run_coroutine(coro):
    return asyncio.run(coro)


def _build_resample_contract(resample_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Contract stable: always provide both keys.
    """
    result = {"1d": 0, "1h": 0}
    if isinstance(resample_data, dict):
        result.update(resample_data)
    return result


def _run_resample_4h_to_1d(db, symbol: str, min_ts: Optional[datetime], max_ts: Optional[datetime]) -> Dict[str, Any]:
    try:
        if min_ts is None or max_ts is None:
            return {"1d": 0, "skipped": True}

        start_time = min_ts.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = (max_ts + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        count_1d = resample_4h_to_1d(db=db, symbol=symbol, start_time=start_time, end_time=end_time)
        return {"1d": count_1d}
    except Exception as e:
        return {"1d": 0, "error": str(e)}


def _run_resample_30m_to_1h(db, symbol: str, min_ts: Optional[datetime], max_ts: Optional[datetime]) -> Dict[str, Any]:
    try:
        if min_ts is None or max_ts is None:
            return {"1h": 0, "skipped": True}

        start_time = min_ts.replace(minute=0, second=0, microsecond=0)
        end_time = (max_ts + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        count_1h = resample_30m_to_1h(db=db, symbol=symbol, start_time=start_time, end_time=end_time)
        return {"1h": count_1h}
    except Exception as e:
        return {"1h": 0, "error": str(e)}


def _run_resample_30m_to_4h(db, symbol: str, min_ts: Optional[datetime], max_ts: Optional[datetime]) -> Dict[str, Any]:
    """Resample 30m → 4h pour compléter la chaîne de données."""
    try:
        if min_ts is None or max_ts is None:
            return {"4h": 0, "skipped": True}

        start_time = min_ts.replace(hour=(min_ts.hour // 4) * 4, minute=0, second=0, microsecond=0)
        end_time = (max_ts + timedelta(hours=4)).replace(
            hour=((max_ts.hour // 4) * 4), minute=0, second=0, microsecond=0
        )

        count_4h = resample_30m_to_4h(db=db, symbol=symbol, start_time=start_time, end_time=end_time)
        return {"4h": count_4h}
    except Exception as e:
        return {"4h": 0, "error": str(e)}


def _update_next_run_time_legacy() -> None:
    global _scheduler
    if _scheduler is None:
        return
    job = _scheduler.get_job(JOB_ID_LEGACY)
    if job and job.next_run_time:
        _set_state(next_run_time=job.next_run_time.astimezone(timezone.utc))


def _update_next_run_time(job_type: str, job_id: str) -> None:
    global _scheduler
    if _scheduler is None:
        return
    job = _scheduler.get_job(job_id)
    if job and job.next_run_time:
        _set_job_state(job_type, next_run_time=job.next_run_time.astimezone(timezone.utc))


# =========================
# Legacy job (ONE job based on cfg.days)
# =========================
def fetch_candles_job() -> None:
    """
    Legacy: un seul flow déterminé par cfg["days"].
    IMPORTANT: ne doit PAS exécuter 4h puis 30m en série.
    """
    cfg = _read_config()
    symbol = cfg["symbol"]
    days = cfg["days"]
    timeframe = _timeframe_from_days(days)

    start = time.perf_counter()
    now = datetime.now(timezone.utc)
    db = None

    try:
        db = SessionLocal()
        result = _run_coroutine(_fetch_and_store(db, symbol=symbol, days=days, timeframe=timeframe))
        db.commit()

        # Resample selon timeframe
        if timeframe == "4h":
            resample_data = _run_resample_4h_to_1d(db, symbol, result.get("min_ts"), result.get("max_ts"))
        else:
            resample_data = _run_resample_30m_to_1h(db, symbol, result.get("min_ts"), result.get("max_ts"))
        db.commit()

        result["resample"] = _build_resample_contract(resample_data)
        result.pop("min_ts", None)
        result.pop("max_ts", None)

        result["duration_seconds"] = round(time.perf_counter() - start, 3)

        _set_state(last_run_time=now, last_result=result)

    except Exception as e:
        if db is not None:
            db.rollback()
        _set_state(
            last_run_time=now,
            last_result={"status": "error", "error": str(e), "duration_seconds": round(time.perf_counter() - start, 3)},
        )
    finally:
        if db is not None:
            db.close()
        _update_next_run_time_legacy()


# =========================
# Dual jobs (PHASE 2B)
# =========================
def fetch_candles_4h_job() -> None:
    cfg = _read_config()
    symbol = cfg["symbol"]
    days = cfg["days_4h"]
    timeframe = "4h"

    start = time.perf_counter()
    now = datetime.now(timezone.utc)
    db = None

    try:
        db = SessionLocal()
        result = _run_coroutine(_fetch_and_store(db, symbol=symbol, days=days, timeframe=timeframe))
        db.commit()

        resample_data = _run_resample_4h_to_1d(db, symbol, result.get("min_ts"), result.get("max_ts"))
        db.commit()

        result["resample"] = _build_resample_contract(resample_data)
        result.pop("min_ts", None)
        result.pop("max_ts", None)
        result["duration_seconds"] = round(time.perf_counter() - start, 3)

        _set_job_state("4h", last_run_time=now, last_result=result)
        # optionnel: on met à jour aussi le legacy "last_result" pour visibilité
        _set_state(last_run_time=now, last_result=result)

    except Exception as e:
        if db is not None:
            db.rollback()
        err = {"status": "error", "error": str(e), "duration_seconds": round(time.perf_counter() - start, 3), "resample": {"1d": 0, "1h": 0}}
        _set_job_state("4h", last_run_time=now, last_result=err)
        _set_state(last_run_time=now, last_result=err)
    finally:
        if db is not None:
            db.close()
        _update_next_run_time("4h", JOB_ID_4H)


def fetch_candles_30m_job() -> None:
    cfg = _read_config()
    symbol = cfg["symbol"]
    days = cfg["days_30m"]
    timeframe = "30m"

    start = time.perf_counter()
    now = datetime.now(timezone.utc)
    db = None

    try:
        db = SessionLocal()
        result = _run_coroutine(_fetch_and_store(db, symbol=symbol, days=days, timeframe=timeframe))
        db.commit()

        # Resample chaîne complète : 30m → 1h, 30m → 4h
        resample_data = _run_resample_30m_to_1h(db, symbol, result.get("min_ts"), result.get("max_ts"))
        resample_4h_data = _run_resample_30m_to_4h(db, symbol, result.get("min_ts"), result.get("max_ts"))
        db.commit()

        # Merge resample results
        resample_data.update(resample_4h_data)
        result["resample"] = _build_resample_contract(resample_data)
        result.pop("min_ts", None)
        result.pop("max_ts", None)
        result["duration_seconds"] = round(time.perf_counter() - start, 3)

        _set_job_state("30m", last_run_time=now, last_result=result)
        _set_state(last_run_time=now, last_result=result)

    except Exception as e:
        if db is not None:
            db.rollback()
        err = {"status": "error", "error": str(e), "duration_seconds": round(time.perf_counter() - start, 3), "resample": {"1d": 0, "1h": 0}}
        _set_job_state("30m", last_run_time=now, last_result=err)
        _set_state(last_run_time=now, last_result=err)
    finally:
        if db is not None:
            db.close()
        _update_next_run_time("30m", JOB_ID_30M)


# =========================
# News persistence job
# =========================
def fetch_news_job() -> None:
    """
    Persiste les news RSS en base toutes les N minutes.

    Appelle NewsHistoryService.persist_current_news() qui :
    1. Fetche les RSS via NewsService (avec cache mémoire 5min)
    2. Upsert les articles en DB (dédoublonnage par URL)
    3. Retourne les stats (inserted/updated/skipped)

    Ce job est synchrone (pas de _run_coroutine nécessaire).
    """
    start = time.perf_counter()
    now = datetime.now(timezone.utc)
    db = None

    try:
        db = SessionLocal()

        from app.services.news_history_service import NewsHistoryService
        service = NewsHistoryService(db)
        result = service.persist_current_news()

        result["status"] = "success"
        result["duration_seconds"] = round(time.perf_counter() - start, 3)

        _set_job_state("news", last_run_time=now, last_result=result)
        logger.info(f"News job OK: {result.get('inserted', 0)} inserted, {result.get('total_in_db', 0)} total in DB ({result['duration_seconds']}s)")

    except Exception as e:
        if db is not None:
            db.rollback()
        err = {
            "status": "error",
            "error": str(e),
            "duration_seconds": round(time.perf_counter() - start, 3),
        }
        _set_job_state("news", last_run_time=now, last_result=err)
        logger.error(f"News job error: {e}")
    finally:
        if db is not None:
            db.close()
        _update_next_run_time("news", JOB_ID_NEWS)


# =========================
# Lifecycle control
# =========================
def start_scheduler() -> None:
    """
    - Si dual_jobs=True => schedule 2 jobs candles (4h + 30m)
    - Sinon => schedule legacy fetch_candles_job
    - Toujours schedule le job news (indépendant des candles)
    """
    cfg = _read_config()

    # State init (legacy + jobs)
    _set_state(
        enabled=cfg["enabled"],
        interval_minutes=cfg["interval_minutes"],
        symbol=cfg["symbol"],
        days=cfg["days"],
    )
    _set_job_state("4h", interval_minutes=cfg["interval_minutes_4h"], days=cfg["days_4h"])
    _set_job_state("30m", interval_minutes=cfg["interval_minutes_30m"], days=cfg["days_30m"])
    _set_job_state("news", interval_minutes=cfg["interval_minutes_news"])

    if not cfg["enabled"]:
        return

    global _scheduler
    if _scheduler is not None and getattr(_scheduler, "running", False):
        return

    scheduler = BackgroundScheduler(timezone=timezone.utc)

    if cfg["dual_jobs"]:
        scheduler.add_job(
            fetch_candles_4h_job,
            trigger=IntervalTrigger(minutes=cfg["interval_minutes_4h"]),
            id=JOB_ID_4H,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        scheduler.add_job(
            fetch_candles_30m_job,
            trigger=IntervalTrigger(minutes=cfg["interval_minutes_30m"]),
            id=JOB_ID_30M,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
    else:
        scheduler.add_job(
            fetch_candles_job,
            trigger=IntervalTrigger(minutes=cfg["interval_minutes"]),
            id=JOB_ID_LEGACY,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )

    # Job News RSS — toujours activé quand le scheduler est enabled
    # Persiste les news RSS en base toutes les N minutes
    scheduler.add_job(
        fetch_news_job,
        trigger=IntervalTrigger(minutes=cfg["interval_minutes_news"]),
        id=JOB_ID_NEWS,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.start()
    _scheduler = scheduler
    _set_state(running=True)

    # set next runs
    if cfg["dual_jobs"]:
        _update_next_run_time("4h", JOB_ID_4H)
        _update_next_run_time("30m", JOB_ID_30M)
        # for legacy top-level next_run_time, we expose next 4h job by default
        job = scheduler.get_job(JOB_ID_4H)
        if job and job.next_run_time:
            _set_state(next_run_time=job.next_run_time.astimezone(timezone.utc))
    else:
        _update_next_run_time_legacy()

    _update_next_run_time("news", JOB_ID_NEWS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        _set_state(running=False)
        return
    try:
        _scheduler.shutdown(wait=False)
    finally:
        _scheduler = None
        _set_state(running=False, next_run_time=None)
        _set_job_state("4h", next_run_time=None)
        _set_job_state("30m", next_run_time=None)
        _set_job_state("news", next_run_time=None)
