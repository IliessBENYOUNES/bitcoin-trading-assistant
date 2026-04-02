"""
Utilitaires de gestion du temps et des buckets.

Ce module centralise toute la logique de :
- Normalisation des timestamps en UTC
- Alignement des timestamps sur les buckets de timeframe
- Validation des timeframes
- Calcul de statuts (fraîcheur, complétude, global)

TIMEFRAMES SUPPORTÉS (Binance) :
- 1m  : 1 minute
- 3m  : 3 minutes
- 5m  : 5 minutes
- 15m : 15 minutes
- 30m : 30 minutes
- 1h  : 1 heure
- 2h  : 2 heures
- 4h  : 4 heures
- 6h  : 6 heures
- 8h  : 8 heures
- 12h : 12 heures
- 1d  : 1 jour (24 heures)
- 3d  : 3 jours (72 heures)
- 1w  : 1 semaine (168 heures)
"""

from datetime import datetime, timezone, timedelta
from typing import Any
import pandas as pd


# ============================================================
# CONSTANTES
# ============================================================

VALID_TIMEFRAMES: dict[str, float] = {
    "1m": 1 / 60,
    "3m": 3 / 60,
    "5m": 5 / 60,
    "15m": 15 / 60,
    "30m": 0.5,
    "1h": 1.0,
    "2h": 2.0,
    "4h": 4.0,
    "6h": 6.0,
    "8h": 8.0,
    "12h": 12.0,
    "1d": 24.0,
    "3d": 72.0,
    "1w": 168.0,
}

FRESHNESS_THRESHOLD_BUCKETS = 1
STALE_THRESHOLD_BUCKETS = 2


# ============================================================
# FONCTIONS PUBLIQUES
# ============================================================

def get_timeframe_hours(timeframe: str) -> float:
    """Retourne la durée d'un timeframe en heures."""
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(
            f"Timeframe invalide: '{timeframe}'. "
            f"Valides: {list(VALID_TIMEFRAMES.keys())}"
        )
    return VALID_TIMEFRAMES[timeframe]


def is_valid_timeframe(timeframe: str) -> bool:
    """Vérifie si un timeframe est valide."""
    return timeframe in VALID_TIMEFRAMES


def normalize_to_utc(dt: datetime) -> datetime:
    """Normalise un datetime en UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    else:
        return dt.astimezone(timezone.utc)


def align_to_bucket(dt: datetime, timeframe: str) -> datetime:
    """
    Aligne un datetime au bucket inférieur (floor) du timeframe.

    Exemples (timeframe=4h) :
        14:35 UTC → 12:00 UTC
        23:59 UTC → 20:00 UTC

    Exemples (timeframe=30m) :
        14:35 UTC → 14:30 UTC
        14:15 UTC → 14:00 UTC
    """
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(
            f"Timeframe invalide: '{timeframe}'. "
            f"Valides: {list(VALID_TIMEFRAMES.keys())}"
        )

    dt_utc = normalize_to_utc(dt)
    tf_hours = VALID_TIMEFRAMES[timeframe]

    # Sub-hourly timeframes (minutes)
    if timeframe == "1m":
        return dt_utc.replace(second=0, microsecond=0)

    elif timeframe == "3m":
        bucket_minute = (dt_utc.minute // 3) * 3
        return dt_utc.replace(minute=bucket_minute, second=0, microsecond=0)

    elif timeframe == "5m":
        bucket_minute = (dt_utc.minute // 5) * 5
        return dt_utc.replace(minute=bucket_minute, second=0, microsecond=0)

    elif timeframe == "15m":
        bucket_minute = (dt_utc.minute // 15) * 15
        return dt_utc.replace(minute=bucket_minute, second=0, microsecond=0)

    elif timeframe == "30m":
        if dt_utc.minute >= 30:
            return dt_utc.replace(minute=30, second=0, microsecond=0)
        else:
            return dt_utc.replace(minute=0, second=0, microsecond=0)

    # Hourly timeframes
    elif timeframe == "1h":
        return dt_utc.replace(minute=0, second=0, microsecond=0)

    elif timeframe == "2h":
        bucket_hour = (dt_utc.hour // 2) * 2
        return dt_utc.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)

    elif timeframe == "4h":
        bucket_hour = (dt_utc.hour // 4) * 4
        return dt_utc.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)

    elif timeframe == "6h":
        bucket_hour = (dt_utc.hour // 6) * 6
        return dt_utc.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)

    elif timeframe == "8h":
        bucket_hour = (dt_utc.hour // 8) * 8
        return dt_utc.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)

    elif timeframe == "12h":
        bucket_hour = (dt_utc.hour // 12) * 12
        return dt_utc.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)

    # Daily+ timeframes
    elif timeframe == "1d":
        return dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    elif timeframe == "3d":
        # Aligner sur des blocs de 3 jours depuis epoch (lundi 1er jan 1970)
        days_since_epoch = (dt_utc - datetime(1970, 1, 1, tzinfo=timezone.utc)).days
        aligned_days = (days_since_epoch // 3) * 3
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return epoch + timedelta(days=aligned_days)

    elif timeframe == "1w":
        # Aligner sur le lundi 00:00 UTC
        days_since_monday = dt_utc.weekday()  # 0=Monday
        return (dt_utc - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    # Fallback
    return dt_utc.replace(minute=0, second=0, microsecond=0)


def get_rolling_window(
        anchor_ts: datetime,
        days: float,
        timeframe: str
) -> tuple[datetime, datetime]:
    """
    Calcule les bornes d'une fenêtre rolling.

    Returns:
        (start_ts, end_ts) tuple de datetimes UTC alignés
    """
    end_ts = align_to_bucket(anchor_ts, timeframe)
    start_ts = end_ts - timedelta(days=days)
    return start_ts, end_ts


def calculate_expected_count(
        start_ts: datetime,
        end_ts: datetime,
        timeframe: str
) -> int:
    """Calcule le nombre attendu de buckets (bornes inclusives)."""
    tf_hours = get_timeframe_hours(timeframe)
    total_hours = (end_ts - start_ts).total_seconds() / 3600
    return int(total_hours / tf_hours) + 1


def calculate_freshness_status(data_lag_hours: float, timeframe: str) -> str:
    """
    Détermine le status de fraîcheur.

    - FRESH      : lag < 1 bucket
    - STALE      : 1 bucket <= lag < 2 buckets
    - VERY_STALE : lag >= 2 buckets
    """
    tf_hours = get_timeframe_hours(timeframe)

    if data_lag_hours < tf_hours * FRESHNESS_THRESHOLD_BUCKETS:
        return "FRESH"
    elif data_lag_hours < tf_hours * STALE_THRESHOLD_BUCKETS:
        return "STALE"
    else:
        return "VERY_STALE"


def calculate_global_status(completeness_status: str, freshness_status: str) -> str:
    """
    Calcule le status global : GAPS > STALE > OK
    """
    if completeness_status == "GAPS_DETECTED":
        return "GAPS"
    elif freshness_status in ("STALE", "VERY_STALE"):
        return "STALE"
    else:
        return "OK"


def nan_to_none(value: Any) -> Any:
    """Convertit NaN/NaT pandas en None pour JSON."""
    if pd.isna(value):
        return None
    if isinstance(value, float):
        return round(value, 2)
    return value