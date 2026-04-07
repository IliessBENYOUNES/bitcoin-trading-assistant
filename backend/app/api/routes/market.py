"""
Routes pour les données de marché (chandeliers OHLCV).

Endpoints :
- GET  /market/candles       : Récupérer les chandeliers depuis la BDD
- POST /market/candles/fetch : Récupérer depuis CoinGecko et stocker en BDD
- GET  /market/price         : Prix actuel
- GET  /market/info          : Informations de marché complètes
- GET  /market/candles/gaps  : Détecter les trous et la fraîcheur des données

DÉFINITIONS ROLLING 7 JOURS :
=============================
Deux métriques distinctes sont calculées :

1. COMPLÉTUDE (anchored on max_ts)
   - Fenêtre : [max_ts - 7 jours, max_ts]
   - Question : "La série est-elle sans trous jusqu'au dernier candle stocké ?"
   - Status : OK (0 gaps) | GAPS_DETECTED (>0 gaps)

2. FRAÎCHEUR (anchored on NOW)
   - Métrique : data_lag = NOW() - max_ts
   - Question : "Les données sont-elles à jour ?"
   - Status : FRESH (lag < 1 bucket) | STALE (lag >= 1 bucket) | VERY_STALE (lag > 2 buckets)

STATUS GLOBAL :
- OK         : Complète ET Fraîche
- STALE      : Complète mais pas fraîche
- GAPS       : Des trous dans la série
- STALE+GAPS : Pas fraîche ET des trous
"""
from app.services.indicator_service import IndicatorService
from app.services.signal_service import SignalService

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.database import get_db
from app.models import Candle
from app.schemas import CandleResponse, CandleListResponse
from app.services.coingecko_service import CoinGeckoService
from app.services.data_source_router import DataSourceRouter
from app.services.price_service import PriceService
from app.services.resample_service import resample_30m_to_1h, resample_30m_to_4h, resample_4h_to_1d
from app.utils.time_buckets import align_to_bucket as utils_align_to_bucket
import httpx

# Router avec préfixe /market
router = APIRouter(
    prefix="/market",
    tags=["Market Data"]
)

# Instance du service CoinGecko (réutilisée pour OHLC fallback uniquement)
coingecko_service = CoinGeckoService()

# Service de prix unifié (Binance prioritaire, CoinGecko fallback)
# Cohérent avec le WebSocket frontend et les données candles
price_service = PriceService()

@router.get(
    "/indicators",
    response_model=dict,
    summary="Indicateurs techniques (RSI, MACD, SMA, Bollinger)",
    description="Calcule et retourne une série d'indicateurs techniques alignée sur les candles."
)
def get_indicators(
        symbol: str = Query(default="BTC/USD"),
        timeframe: str = Query(default="4h"),
        history_days: Optional[float] = Query(default=None, ge=0.0625, le=365),
        days: Optional[float] = Query(default=None, ge=0.0625, le=365),  # alias toléré
        end_ts: Optional[datetime] = Query(default=None),
        include_candles: bool = Query(default=False),
        db: Session = Depends(get_db),
) -> dict:
    effective_days = history_days if history_days is not None else (days if days is not None else 7)

    service = IndicatorService(db)
    try:
        return service.calculate(
            symbol=symbol,
            timeframe=timeframe,
            history_days=effective_days,
            end_ts=end_ts,
            include_candles=include_candles,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/signals",
    response_model=dict,
    summary="Signaux de trading (interprétation des indicateurs)",
    description="Interprète RSI, MACD, SMA et Bollinger en signaux structurés avec score composite -100/+100.",
)
def get_signals(
        symbol: str = Query(default="BTC/USD"),
        timeframe: str = Query(default="4h"),
        history_days: Optional[float] = Query(default=None, ge=0.0625, le=365),
        days: Optional[float] = Query(default=None, ge=0.0625, le=365),  # alias toléré
        end_ts: Optional[datetime] = Query(default=None),
        db: Session = Depends(get_db),
) -> dict:
    """
    Retourne les signaux de trading basés sur les indicateurs techniques.

    Chaque indicateur est interprété en un signal (bullish/bearish/neutral)
    avec une force et un message explicatif. Un score composite agrège
    l'ensemble en une note de -100 (très baissier) à +100 (très haussier).
    """
    effective_days = history_days if history_days is not None else (days if days is not None else 7)

    service = SignalService(db)
    try:
        return service.analyze(
            symbol=symbol,
            timeframe=timeframe,
            history_days=effective_days,
            end_ts=end_ts,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def get_timeframe_hours(timeframe: str) -> float:
    """Convertit un timeframe en nombre d'heures."""
    mapping = {
        "1m": 1 / 60,
        "3m": 3 / 60,
        "5m": 5 / 60,
        "15m": 15 / 60,
        "30m": 0.5,
        "1h": 1,
        "2h": 2,
        "4h": 4,
        "6h": 6,
        "8h": 8,
        "12h": 12,
        "1d": 24,
        "3d": 72,
        "1w": 168,
        "4d": 96,
    }
    return mapping.get(timeframe, 4)


def normalize_to_utc(dt: datetime) -> datetime:
    """
    Normalise un datetime en UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    else:
        return dt.astimezone(timezone.utc)


def get_rolling_window_from_max_ts(max_ts: datetime, days: int, timeframe: str) -> tuple[datetime, datetime]:
    """
    Calcule les bornes d'une fenêtre rolling ANCRÉE SUR max_ts (pour complétude).

    Args:
        max_ts: Timestamp du dernier candle en base
        days: Nombre de jours de la fenêtre
        timeframe: Intervalle (ex: "4h")

    Returns:
        (start_ts, end_ts) où end_ts = max_ts aligné sur bucket
    """
    tf_hours = get_timeframe_hours(timeframe)

    # Aligner max_ts sur le bucket (devrait déjà l'être, mais par sécurité)
    max_ts_utc = normalize_to_utc(max_ts)
    if timeframe in ("3d", "1w"):
        # Pour 3d/1w, on aligne en jours
        end_ts = max_ts_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    elif tf_hours >= 1:
        hour_floor = max_ts_utc.replace(minute=0, second=0, microsecond=0)
        bucket_hour = (hour_floor.hour // int(tf_hours)) * int(tf_hours)
        end_ts = hour_floor.replace(hour=bucket_hour)
    else:
        # Sub-hourly: 1m, 3m, 5m, 15m, 30m
        tf_minutes = int(tf_hours * 60)
        minute_floor = max_ts_utc.replace(second=0, microsecond=0)
        bucket_minute = (minute_floor.minute // tf_minutes) * tf_minutes
        end_ts = minute_floor.replace(minute=bucket_minute)

    # Calculer start_ts
    total_hours = days * 24
    start_ts = end_ts - timedelta(hours=total_hours)

    return start_ts, end_ts


def get_rolling_window_from_now(days: int, timeframe: str) -> tuple[datetime, datetime]:
    """
    Calcule les bornes d'une fenêtre rolling ANCRÉE SUR NOW (pour fraîcheur/affichage).

    Returns:
        (start_ts, end_ts) où end_ts = dernier bucket complet avant maintenant
    """
    now_utc = datetime.now(timezone.utc)
    tf_hours = get_timeframe_hours(timeframe)

    # Aligner end_ts sur le dernier bucket complet
    if timeframe in ("3d", "1w"):
        # Pour 3d/1w, on aligne en jours
        end_ts = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    elif tf_hours >= 1:
        hour_floor = now_utc.replace(minute=0, second=0, microsecond=0)
        hours_since_midnight = hour_floor.hour
        bucket_hour = (hours_since_midnight // int(tf_hours)) * int(tf_hours)
        end_ts = hour_floor.replace(hour=bucket_hour)
    else:
        # Sub-hourly: 1m, 3m, 5m, 15m, 30m
        tf_minutes = int(tf_hours * 60)
        minute_floor = now_utc.replace(second=0, microsecond=0)
        bucket_minute = (minute_floor.minute // tf_minutes) * tf_minutes
        end_ts = minute_floor.replace(minute=bucket_minute)

    # Calculer start_ts
    total_hours = days * 24
    start_ts = end_ts - timedelta(hours=total_hours)

    return start_ts, end_ts


def calculate_freshness_status(data_lag_hours: float, tf_hours: float) -> str:
    """
    Détermine le status de fraîcheur basé sur le lag.

    - FRESH      : lag < 1 bucket
    - STALE      : 1 bucket <= lag < 2 buckets
    - VERY_STALE : lag >= 2 buckets
    """
    if data_lag_hours < tf_hours:
        return "FRESH"
    elif data_lag_hours < (tf_hours * 2):
        return "STALE"
    else:
        return "VERY_STALE"


@router.get(
    "/candles",
    response_model=CandleListResponse,
    summary="Récupérer les chandeliers depuis la base de données",
    description="Retourne les chandeliers OHLCV stockés localement avec filtrage rolling optionnel"
)
def get_candles(
        symbol: str = Query(default="BTC/USD", description="Paire de trading"),
        timeframe: str = Query(default="4h", description="Intervalle de temps"),
        limit: int = Query(default=100, ge=1, le=1000, description="Nombre max de résultats"),
        days: Optional[float] = Query(default=None, ge=0.0625, le=365, description="Fenêtre rolling en jours (supporte les fractions, ex: 0.25 = 6h)"),
        anchor: str = Query(default="max_ts", pattern="^(max_ts|now)$", description="Ancrage: max_ts (complétude) ou now (fraîcheur)"),
        db: Session = Depends(get_db)
) -> dict:
    """
    Récupère les chandeliers depuis la base de données locale.

    Paramètre 'anchor' :
    - max_ts : fenêtre ancrée sur le dernier candle (pour complétude)
    - now    : fenêtre ancrée sur maintenant (pour fraîcheur/affichage temps réel)
    """
    # Construire la requête de base
    query = (
        db.query(Candle)
        .filter(Candle.symbol == symbol)
        .filter(Candle.timeframe == timeframe)
    )

    # Déterminer les bornes de filtrage
    effective_start_ts = None
    effective_end_ts = None
    expected_count = None

    if days:
        tf_hours = get_timeframe_hours(timeframe)

        if anchor == "max_ts":
            # Ancrage sur max_ts (complétude)
            max_ts_result = db.query(func.max(Candle.timestamp)).filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe
            ).scalar()

            if max_ts_result:
                effective_start_ts, effective_end_ts = get_rolling_window_from_max_ts(
                    max_ts_result, days, timeframe
                )
        else:
            # Ancrage sur now (fraîcheur)
            effective_start_ts, effective_end_ts = get_rolling_window_from_now(days, timeframe)

        if effective_start_ts and effective_end_ts:
            query = query.filter(Candle.timestamp >= effective_start_ts)
            query = query.filter(Candle.timestamp <= effective_end_ts)

            # Calculer le nombre attendu
            total_hours = days * 24
            expected_count = int(total_hours / tf_hours) + 1

    # Compter le total en base (sans filtrage de dates)
    total_in_db = (
        db.query(func.count(Candle.id))
        .filter(Candle.symbol == symbol)
        .filter(Candle.timeframe == timeframe)
        .scalar()
    )

    # Exécuter la requête avec tri et limite
    candles = (
        query
        .order_by(desc(Candle.timestamp))
        .limit(limit)
        .all()
    )

    # Convertir en réponse
    candle_responses = [
        CandleResponse.model_validate(candle)
        for candle in candles
    ]

    return {
        "data": candle_responses,
        "count": len(candle_responses),
        "symbol": symbol,
        "timeframe": timeframe,
        "total_in_db": total_in_db,
        "expected_count": expected_count,
        "anchor": anchor,
        "start_ts": effective_start_ts.isoformat() if effective_start_ts else None,
        "end_ts": effective_end_ts.isoformat() if effective_end_ts else None,
    }


@router.get(
    "/candles/gaps",
    response_model=dict,
    summary="Analyser complétude et fraîcheur des données",
    description="""
    Analyse la qualité des données selon deux axes :
    
    1. COMPLÉTUDE (ancrée sur max_ts) : La série est-elle sans trous ?
    2. FRAÎCHEUR (ancrée sur NOW) : Les données sont-elles à jour ?
    """
)
def detect_gaps(
        symbol: str = Query(default="BTC/USD", description="Paire de trading"),
        timeframe: str = Query(default="4h", description="Intervalle de temps"),
        days: float = Query(default=7, ge=0.0625, le=90, description="Fenêtre en jours (supporte les fractions)"),
        db: Session = Depends(get_db)
) -> dict:
    """
    Analyse complète de la qualité des données.

    Retourne :
    - completeness : analyse des trous (ancrée sur max_ts)
    - freshness    : analyse du retard (ancrée sur NOW)
    - global_status: OK | STALE | GAPS | STALE+GAPS
    """
    tf_hours = get_timeframe_hours(timeframe)
    now_utc = datetime.now(timezone.utc)

    # ================================================================
    # ÉTAPE 1 : Récupérer max_ts et min_ts
    # ================================================================
    stats = db.query(
        func.max(Candle.timestamp).label("max_ts"),
        func.min(Candle.timestamp).label("min_ts"),
        func.count(Candle.id).label("total_count")
    ).filter(
        Candle.symbol == symbol,
        Candle.timeframe == timeframe
    ).first()

    if not stats or not stats.max_ts:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "days": days,
            "error": "Aucune donnée en base",
            "global_status": "NO_DATA"
        }

    max_ts = normalize_to_utc(stats.max_ts)
    min_ts = normalize_to_utc(stats.min_ts)
    total_count = stats.total_count

    # ================================================================
    # ÉTAPE 2 : FRAÎCHEUR (ancrée sur NOW)
    # ================================================================
    data_lag = now_utc - max_ts
    data_lag_hours = data_lag.total_seconds() / 3600
    freshness_status = calculate_freshness_status(data_lag_hours, tf_hours)

    # ================================================================
    # ÉTAPE 3 : COMPLÉTUDE (ancrée sur max_ts)
    # ================================================================
    start_ts, end_ts = get_rolling_window_from_max_ts(max_ts, days, timeframe)

    # Générer les buckets attendus
    expected_buckets: list[datetime] = []
    current = start_ts
    while current <= end_ts:
        expected_buckets.append(current)
        current += timedelta(hours=tf_hours)

    # Récupérer les buckets existants dans la fenêtre
    existing_candles = db.query(Candle.timestamp).filter(
        Candle.symbol == symbol,
        Candle.timeframe == timeframe,
        Candle.timestamp >= start_ts,
        Candle.timestamp <= end_ts
    ).all()

    # Normaliser en UTC et aligner sur le bucket du timeframe pour comparaison
    existing_utc: set[datetime] = set()
    for (ts,) in existing_candles:
        ts_utc = utils_align_to_bucket(normalize_to_utc(ts), timeframe)
        existing_utc.add(ts_utc)

    # Trouver les trous
    missing: list[str] = []
    for expected in expected_buckets:
        expected_normalized = utils_align_to_bucket(expected, timeframe)
        if expected_normalized not in existing_utc:
            missing.append(expected.isoformat())

    completeness_status = "OK" if len(missing) == 0 else "GAPS_DETECTED"

    # ================================================================
    # ÉTAPE 4 : STATUS GLOBAL
    # ================================================================
    if completeness_status == "OK" and freshness_status == "FRESH":
        global_status = "OK"
    elif completeness_status == "OK" and freshness_status in ("STALE", "VERY_STALE"):
        global_status = "STALE"
    elif completeness_status == "GAPS_DETECTED" and freshness_status == "FRESH":
        global_status = "GAPS"
    else:
        global_status = "STALE+GAPS"

    # ================================================================
    # RÉPONSE
    # ================================================================
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "days": days,
        "now_utc": now_utc.isoformat(),

        # Fraîcheur (ancrée sur NOW)
        "freshness": {
            "max_ts": max_ts.isoformat(),
            "data_lag": str(data_lag),
            "data_lag_hours": round(data_lag_hours, 2),
            "threshold_hours": tf_hours,
            "status": freshness_status
        },

        # Complétude (ancrée sur max_ts)
        "completeness": {
            "window_start": start_ts.isoformat(),
            "window_end": end_ts.isoformat(),
            "expected_count": len(expected_buckets),
            "actual_count": len(existing_candles),
            "missing_count": len(missing),
            "missing_timestamps": missing[:10],
            "status": completeness_status
        },

        # Stats globales
        "stats": {
            "total_in_db": total_count,
            "min_ts": min_ts.isoformat(),
            "max_ts": max_ts.isoformat(),
            "span_days": round((max_ts - min_ts).total_seconds() / 86400, 1)
        },

        # Status global
        "global_status": global_status
    }


@router.post(
    "/candles/fetch",
    response_model=dict,
    summary="Récupérer les données depuis Binance/CoinGecko",
    description=(
        "Appelle l'API Binance (prioritaire) ou CoinGecko (fallback) "
        "et stocke les chandeliers en base de données. "
        "Supporte toutes les combinaisons timeframe × jours."
    )
)
async def fetch_candles(
        symbol: str = Query(default="BTC/USD", description="Paire de trading"),
        days: float = Query(default=7, ge=0.0625, le=365, description="Nombre de jours d'historique (supporte les fractions)"),
        timeframe: Optional[str] = Query(
            default=None,
            description="Timeframe explicite (30m, 1h, 4h, 1d). Si absent, auto-détection selon days."
        ),
        db: Session = Depends(get_db)
) -> dict:
    """
    Récupère les données OHLCV et les stocke en base.

    Utilise Binance comme source principale (OHLCV natif, volume réel,
    toute granularité) avec CoinGecko en fallback.

    Si timeframe n'est pas spécifié, auto-détection selon days :
    - days <= 2 : 30m
    - days <= 30 : 4h
    - days > 30 : 4d (legacy CoinGecko)
    """
    try:
        # Déterminer le timeframe
        if timeframe is None:
            if days <= 2:
                timeframe = "30m"
            elif days <= 30:
                timeframe = "4h"
            else:
                timeframe = "4d"

        # Valider le timeframe
        valid_timeframes = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "4d"}
        if timeframe not in valid_timeframes:
            raise HTTPException(
                status_code=422,
                detail=f"Timeframe '{timeframe}' non supporté. Valeurs: {valid_timeframes}"
            )

        # Utiliser DataSourceRouter (Binance prioritaire, CoinGecko fallback)
        router = DataSourceRouter()
        ohlc_data = await router.get_candles(
            symbol=symbol, timeframe=timeframe, days=days
        )

        if not ohlc_data:
            raise HTTPException(
                status_code=502,
                detail="Aucune donnée reçue (Binance + CoinGecko)"
            )

        # Insérer les données en base
        inserted = 0
        duplicates = 0
        updated = 0

        for candle_data in ohlc_data:
            # Normaliser le timestamp en UTC
            ts = candle_data["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            # Vérifier si cette bougie existe déjà
            ts_min = ts - timedelta(minutes=5)
            ts_max = ts + timedelta(minutes=5)

            existing = db.query(Candle).filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= ts_min,
                Candle.timestamp <= ts_max
            ).first()

            if existing:
                if (existing.close_price != candle_data["close"] or
                        existing.high_price != candle_data["high"] or
                        existing.low_price != candle_data["low"]):
                    existing.open_price = candle_data["open"]
                    existing.high_price = candle_data["high"]
                    existing.low_price = candle_data["low"]
                    existing.close_price = candle_data["close"]
                    existing.volume = candle_data["volume"]
                    updated += 1
                else:
                    duplicates += 1
                continue

            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open_price=candle_data["open"],
                high_price=candle_data["high"],
                low_price=candle_data["low"],
                close_price=candle_data["close"],
                volume=candle_data["volume"],
                source="binance"
            )

            db.add(candle)
            inserted += 1

        db.commit()

        # Resample en chaîne si nécessaire
        resample_results = {}
        if timeframe == "30m":
            # 30m → 1h, 30m → 4h, puis 4h → 1d
            resample_results["1h"] = resample_30m_to_1h(db=db, symbol=symbol)
            resample_results["4h"] = resample_30m_to_4h(db=db, symbol=symbol)
            resample_results["1d"] = resample_4h_to_1d(db=db, symbol=symbol)
            db.commit()
        elif timeframe == "4h":
            # 4h → 1d
            resample_results["1d"] = resample_4h_to_1d(db=db, symbol=symbol)
            db.commit()

        tf_hours = get_timeframe_hours(timeframe)
        expected = int((days * 24) / tf_hours) + 1 if tf_hours > 0 else 0

        return {
            "message": "Données récupérées avec succès",
            "symbol": symbol,
            "timeframe": timeframe,
            "days": days,
            "fetched": len(ohlc_data),
            "inserted": inserted,
            "updated": updated,
            "duplicates": duplicates,
            "expected_theoretical": expected,
            "coverage_pct": round((len(ohlc_data) / expected) * 100, 1) if expected > 0 else 0,
            "resample": resample_results if resample_results else None,
        }

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur lors de l'appel à CoinGecko: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne: {str(e)}"
        )


@router.get(
    "/price",
    response_model=dict,
    summary="Prix actuel (Binance temps réel)"
)
async def get_current_price(
        symbol: str = Query(default="BTC/USD", description="Paire de trading"),
        db: Session = Depends(get_db),
) -> dict:
    """
    Prix actuel via Binance REST API (même source que le WebSocket frontend).
    Fallback CoinGecko puis DB si Binance indisponible.
    """
    price = await price_service.get_price(symbol=symbol, db=db)

    if price is None:
        raise HTTPException(
            status_code=502,
            detail="Impossible de récupérer le prix (Binance + CoinGecko indisponibles)"
        )

    # Essayer d'obtenir les stats 24h de Binance
    ticker = await price_service.get_ticker_24h(symbol=symbol)

    result = {
        "symbol": symbol,
        "price": price,
        "source": "binance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Ajouter les stats 24h si disponibles
    if ticker:
        result["change_24h_pct"] = ticker["change_24h_pct"]
        result["high_24h"] = ticker["high_24h"]
        result["low_24h"] = ticker["low_24h"]
        result["volume_24h"] = ticker["volume_24h"]

    return result


@router.get(
    "/info",
    response_model=dict,
    summary="Informations de marché"
)
async def get_market_info(
        symbol: str = Query(default="BTC/USD", description="Paire de trading")
) -> dict:
    market_data = await coingecko_service.get_market_data(symbol)

    if market_data is None:
        raise HTTPException(
            status_code=502,
            detail="Impossible de récupérer les données depuis CoinGecko"
        )

    return market_data