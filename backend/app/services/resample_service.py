"""
Resample Service - Agrège les candles RAW vers des timeframes supérieurs.

Transformations :
- 30m -> 1h (2 candles 30m = 1 candle 1h)
- 4h  -> 1d (6 candles 4h = 1 candle 1d)

Règles OHLCV :
- Open  : premier du bucket
- High  : max des highs
- Low   : min des lows
- Close : dernier du bucket
- Volume: somme des volumes
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Candle
from app.utils.db_upsert import upsert_candles

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS - Alignement temporel
# =============================================================================

def normalize_to_utc(dt: datetime) -> datetime:
    """Normalise un datetime en UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def align_to_bucket(dt: datetime, timeframe: str) -> datetime:
    """Aligne un timestamp sur le début de son bucket."""
    dt_utc = normalize_to_utc(dt)

    if timeframe == "1m":
        return dt_utc.replace(second=0, microsecond=0)
    elif timeframe == "3m":
        minute = (dt_utc.minute // 3) * 3
        return dt_utc.replace(minute=minute, second=0, microsecond=0)
    elif timeframe == "5m":
        minute = (dt_utc.minute // 5) * 5
        return dt_utc.replace(minute=minute, second=0, microsecond=0)
    elif timeframe == "15m":
        minute = (dt_utc.minute // 15) * 15
        return dt_utc.replace(minute=minute, second=0, microsecond=0)
    elif timeframe == "30m":
        minute = 0 if dt_utc.minute < 30 else 30
        return dt_utc.replace(minute=minute, second=0, microsecond=0)
    elif timeframe == "1h":
        return dt_utc.replace(minute=0, second=0, microsecond=0)
    elif timeframe == "2h":
        hour = (dt_utc.hour // 2) * 2
        return dt_utc.replace(hour=hour, minute=0, second=0, microsecond=0)
    elif timeframe == "4h":
        hour = (dt_utc.hour // 4) * 4
        return dt_utc.replace(hour=hour, minute=0, second=0, microsecond=0)
    elif timeframe == "6h":
        hour = (dt_utc.hour // 6) * 6
        return dt_utc.replace(hour=hour, minute=0, second=0, microsecond=0)
    elif timeframe == "8h":
        hour = (dt_utc.hour // 8) * 8
        return dt_utc.replace(hour=hour, minute=0, second=0, microsecond=0)
    elif timeframe == "12h":
        hour = (dt_utc.hour // 12) * 12
        return dt_utc.replace(hour=hour, minute=0, second=0, microsecond=0)
    elif timeframe == "1d":
        return dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    elif timeframe == "3d":
        days_since_epoch = (dt_utc - datetime(1970, 1, 1, tzinfo=timezone.utc)).days
        aligned_days = (days_since_epoch // 3) * 3
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return epoch + timedelta(days=aligned_days)
    elif timeframe == "1w":
        days_since_monday = dt_utc.weekday()
        return (dt_utc - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return dt_utc


def get_parent_bucket(dt: datetime, source_tf: str, target_tf: str) -> datetime:
    """Calcule le bucket parent pour un timestamp donné."""
    return align_to_bucket(dt, target_tf)


# =============================================================================
# CORE - Agrégation OHLCV
# =============================================================================

def aggregate_candles(candles: List[Candle]) -> Optional[Dict]:
    """
    Agrège une liste de candles en un seul point OHLCV.

    Returns:
        Dict avec open, high, low, close, volume ou None si liste vide
    """
    if not candles:
        return None

    # Trier par timestamp ASC
    sorted_candles = sorted(candles, key=lambda c: c.timestamp)

    return {
        "open": sorted_candles[0].open_price,
        "high": max(c.high_price for c in sorted_candles),
        "low": min(c.low_price for c in sorted_candles),
        "close": sorted_candles[-1].close_price,
        "volume": sum(c.volume or 0 for c in sorted_candles),
    }


# =============================================================================
# RESAMPLE FUNCTIONS
# =============================================================================

def resample_30m_to_1h(
        db: Session,
        symbol: str = "BTC/USD",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
) -> int:
    """
    Resample 30m -> 1h.

    Args:
        db: Session SQLAlchemy
        symbol: Paire de trading
        start_time: Début de la fenêtre (optionnel)
        end_time: Fin de la fenêtre (optionnel)

    Returns:
        Nombre de candles 1h créés/mis à jour
    """
    return _resample(
        db=db,
        symbol=symbol,
        source_tf="30m",
        target_tf="1h",
        candles_per_bucket=2,
        start_time=start_time,
        end_time=end_time,
    )


def resample_4h_to_1d(
        db: Session,
        symbol: str = "BTC/USD",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
) -> int:
    """
    Resample 4h -> 1d.

    Args:
        db: Session SQLAlchemy
        symbol: Paire de trading
        start_time: Début de la fenêtre (optionnel)
        end_time: Fin de la fenêtre (optionnel)

    Returns:
        Nombre de candles 1d créés/mis à jour
    """
    return _resample(
        db=db,
        symbol=symbol,
        source_tf="4h",
        target_tf="1d",
        candles_per_bucket=6,
        start_time=start_time,
        end_time=end_time,
    )


def resample_30m_to_4h(
        db: Session,
        symbol: str = "BTC/USD",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
) -> int:
    """
    Resample 30m -> 4h.

    Utile quand on a des données 30m sur plusieurs jours (via Binance)
    et qu'on veut générer les candles 4h correspondants.

    Args:
        db: Session SQLAlchemy
        symbol: Paire de trading
        start_time: Début de la fenêtre (optionnel)
        end_time: Fin de la fenêtre (optionnel)

    Returns:
        Nombre de candles 4h créés/mis à jour
    """
    return _resample(
        db=db,
        symbol=symbol,
        source_tf="30m",
        target_tf="4h",
        candles_per_bucket=8,  # 8 candles 30m = 1 candle 4h
        start_time=start_time,
        end_time=end_time,
    )


def resample_1h_to_4h(
        db: Session,
        symbol: str = "BTC/USD",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
) -> int:
    """
    Resample 1h -> 4h.

    Utile quand on a des données 1h et qu'on veut générer les candles 4h.

    Args:
        db: Session SQLAlchemy
        symbol: Paire de trading
        start_time: Début de la fenêtre (optionnel)
        end_time: Fin de la fenêtre (optionnel)

    Returns:
        Nombre de candles 4h créés/mis à jour
    """
    return _resample(
        db=db,
        symbol=symbol,
        source_tf="1h",
        target_tf="4h",
        candles_per_bucket=4,  # 4 candles 1h = 1 candle 4h
        start_time=start_time,
        end_time=end_time,
    )


def resample_all(
        db: Session,
        symbol: str = "BTC/USD",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
) -> Dict[str, int]:
    """
    Lance tous les resamplings disponibles.

    Ordre important : on resample du plus fin vers le plus grossier
    pour que chaque étape puisse s'appuyer sur les données générées
    par l'étape précédente.

    Chaîne : 30m -> 1h -> 4h -> 1d

    Returns:
        Dict avec le nombre de candles créés par timeframe
    """
    results = {}

    # 30m -> 1h
    results["1h"] = resample_30m_to_1h(db, symbol, start_time, end_time)

    # 30m -> 4h (directement depuis 30m, plus précis)
    results["4h_from_30m"] = resample_30m_to_4h(db, symbol, start_time, end_time)

    # 1h -> 4h (complète si on a des 1h sans 30m source)
    results["4h_from_1h"] = resample_1h_to_4h(db, symbol, start_time, end_time)

    # 4h -> 1d
    results["1d"] = resample_4h_to_1d(db, symbol, start_time, end_time)

    logger.info(f"Resample all completed: {results}")
    return results


# =============================================================================
# INTERNAL - Generic resample
# =============================================================================

def _resample(
        db: Session,
        symbol: str,
        source_tf: str,
        target_tf: str,
        candles_per_bucket: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
) -> int:
    """
    Fonction générique de resampling.
    """
    # Construire la requête source
    query = db.query(Candle).filter(
        Candle.symbol == symbol,
        Candle.timeframe == source_tf,
        )

    if start_time:
        query = query.filter(Candle.timestamp >= normalize_to_utc(start_time))
    if end_time:
        query = query.filter(Candle.timestamp <= normalize_to_utc(end_time))

    source_candles = query.order_by(Candle.timestamp.asc()).all()

    if not source_candles:
        logger.info(f"No {source_tf} candles found for resampling to {target_tf}")
        return 0

    # Grouper par bucket cible
    buckets: Dict[datetime, List[Candle]] = {}
    for candle in source_candles:
        bucket_ts = get_parent_bucket(candle.timestamp, source_tf, target_tf)
        if bucket_ts not in buckets:
            buckets[bucket_ts] = []
        buckets[bucket_ts].append(candle)

    # Créer les candles agrégés
    records_to_upsert = []
    for bucket_ts, bucket_candles in buckets.items():
        # Vérifier qu'on a assez de candles pour un bucket complet
        # (optionnel: on peut aussi accepter les buckets partiels)
        agg = aggregate_candles(bucket_candles)
        if agg is None:
            continue

        records_to_upsert.append({
            "symbol": symbol,
            "timeframe": target_tf,
            "timestamp": bucket_ts,
            "open_price": agg["open"],
            "high_price": agg["high"],
            "low_price": agg["low"],
            "close_price": agg["close"],
            "volume": agg["volume"],
            "source": f"resample_{source_tf}",
        })

    if not records_to_upsert:
        return 0

    # Upsert en batch
    count = upsert_candles(
        db=db,
        records=records_to_upsert,
        conflict_keys=["symbol", "timeframe", "timestamp"],
        update_keys=["open_price", "high_price", "low_price", "close_price", "volume", "source"],
    )

    logger.info(f"Resampled {len(source_candles)} {source_tf} -> {count} {target_tf} candles")
    return count
