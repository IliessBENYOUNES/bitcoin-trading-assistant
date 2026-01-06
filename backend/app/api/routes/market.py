"""
Routes pour les données de marché (chandeliers OHLCV).

Endpoints :
- GET  /market/candles       : Récupérer les chandeliers depuis la BDD
- POST /market/candles/fetch : Récupérer depuis CoinGecko et stocker en BDD
- GET  /market/price         : Prix actuel
- GET  /market/info          : Informations de marché complètes
- GET  /market/candles/gaps  : Détecter les trous dans les données
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.database import get_db
from app.models import Candle
from app.schemas import CandleResponse, CandleListResponse
from app.services.coingecko_service import CoinGeckoService
import httpx

# Router avec préfixe /market
router = APIRouter(
    prefix="/market",
    tags=["Market Data"]
)

# Instance du service CoinGecko (réutilisée)
coingecko_service = CoinGeckoService()


def get_timeframe_hours(timeframe: str) -> float:
    """Convertit un timeframe en nombre d'heures."""
    mapping = {
        "30m": 0.5,
        "1h": 1,
        "4h": 4,
        "1d": 24,
        "4d": 96,
    }
    return mapping.get(timeframe, 4)


def get_rolling_window(days: int, timeframe: str) -> tuple[datetime, datetime]:
    """
    Calcule les bornes d'une fenêtre rolling alignée sur les buckets.

    Returns:
        (start_ts, end_ts) en UTC, alignés sur les buckets du timeframe
    """
    now_utc = datetime.now(timezone.utc)
    tf_hours = get_timeframe_hours(timeframe)

    # Aligner end_ts sur le dernier bucket complet
    if tf_hours >= 1:
        hour_floor = now_utc.replace(minute=0, second=0, microsecond=0)
        hours_since_midnight = hour_floor.hour
        bucket_hour = (hours_since_midnight // int(tf_hours)) * int(tf_hours)
        end_ts = hour_floor.replace(hour=bucket_hour)
    else:
        minute_floor = now_utc.replace(second=0, microsecond=0)
        if minute_floor.minute >= 30:
            end_ts = minute_floor.replace(minute=30)
        else:
            end_ts = minute_floor.replace(minute=0)

    # Calculer start_ts
    total_hours = days * 24
    start_ts = end_ts - timedelta(hours=total_hours)

    return start_ts, end_ts


def normalize_to_utc(dt: datetime) -> datetime:
    """
    Normalise un datetime en UTC.
    Gère les cas où tzinfo est None ou est une autre timezone.
    """
    if dt.tzinfo is None:
        # Assumer UTC si pas de timezone
        return dt.replace(tzinfo=timezone.utc)
    else:
        # Convertir en UTC
        return dt.astimezone(timezone.utc)


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
        days: Optional[int] = Query(default=None, ge=1, le=365, description="Fenêtre rolling en jours (optionnel)"),
        start_ts: Optional[datetime] = Query(default=None, description="Timestamp de début (optionnel, ISO 8601)"),
        end_ts: Optional[datetime] = Query(default=None, description="Timestamp de fin (optionnel, ISO 8601)"),
        db: Session = Depends(get_db)
) -> dict:
    """
    Récupère les chandeliers depuis la base de données locale.

    Modes de filtrage (par priorité) :
    1. Si start_ts et/ou end_ts fournis : filtrage explicite
    2. Si days fourni : calcul automatique de la fenêtre rolling alignée
    3. Sinon : retourne les X derniers (limit)
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

    if start_ts or end_ts:
        # Mode 1 : filtrage explicite
        if start_ts:
            effective_start_ts = normalize_to_utc(start_ts)
            query = query.filter(Candle.timestamp >= effective_start_ts)
        if end_ts:
            effective_end_ts = normalize_to_utc(end_ts)
            query = query.filter(Candle.timestamp <= effective_end_ts)
    elif days:
        # Mode 2 : fenêtre rolling
        effective_start_ts, effective_end_ts = get_rolling_window(days, timeframe)
        query = query.filter(Candle.timestamp >= effective_start_ts)
        query = query.filter(Candle.timestamp <= effective_end_ts)

        # Calculer le nombre attendu
        tf_hours = get_timeframe_hours(timeframe)
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
        "start_ts": effective_start_ts.isoformat() if effective_start_ts else None,
        "end_ts": effective_end_ts.isoformat() if effective_end_ts else None,
    }


@router.get(
    "/candles/gaps",
    response_model=dict,
    summary="Détecter les trous dans les données",
    description="Identifie les timestamps manquants sur une fenêtre donnée"
)
def detect_gaps(
        symbol: str = Query(default="BTC/USD", description="Paire de trading"),
        timeframe: str = Query(default="4h", description="Intervalle de temps"),
        days: int = Query(default=7, ge=1, le=90, description="Fenêtre en jours"),
        db: Session = Depends(get_db)
) -> dict:
    """
    Détecte les trous (timestamps manquants) dans les données.

    IMPORTANT: Compare les timestamps en UTC pour éviter les problèmes de timezone.
    """
    start_ts, end_ts = get_rolling_window(days, timeframe)
    tf_hours = get_timeframe_hours(timeframe)

    # Générer les buckets attendus (en UTC)
    expected_buckets: list[datetime] = []
    current = start_ts
    while current <= end_ts:
        expected_buckets.append(current)
        current += timedelta(hours=tf_hours)

    # Récupérer les buckets existants
    existing_candles = db.query(Candle.timestamp).filter(
        Candle.symbol == symbol,
        Candle.timeframe == timeframe,
        Candle.timestamp >= start_ts,
        Candle.timestamp <= end_ts
    ).all()

    # Normaliser TOUS les timestamps existants en UTC pour comparaison
    existing_utc: set[datetime] = set()
    for (ts,) in existing_candles:
        # Convertir en UTC et arrondir à l'heure pour éliminer les microsecondes
        ts_utc = normalize_to_utc(ts).replace(minute=0, second=0, microsecond=0)
        existing_utc.add(ts_utc)

    # Trouver les trous
    missing: list[str] = []
    for expected in expected_buckets:
        expected_normalized = expected.replace(minute=0, second=0, microsecond=0)
        if expected_normalized not in existing_utc:
            missing.append(expected.isoformat())

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "days": days,
        "start_ts": start_ts.isoformat(),
        "end_ts": end_ts.isoformat(),
        "expected_count": len(expected_buckets),
        "actual_count": len(existing_candles),
        "missing_count": len(missing),
        "missing_timestamps": missing,
        "status": "OK" if len(missing) == 0 else "GAPS_DETECTED",
        # Debug info
        "debug_existing_sample": [normalize_to_utc(ts).isoformat() for (ts,) in existing_candles[:3]] if existing_candles else []
    }


@router.post(
    "/candles/fetch",
    response_model=dict,
    summary="Récupérer les données depuis CoinGecko",
    description="Appelle l'API CoinGecko et stocke les chandeliers en base de données"
)
async def fetch_candles(
        symbol: str = Query(default="BTC/USD", description="Paire de trading"),
        days: int = Query(default=7, ge=1, le=365, description="Nombre de jours d'historique"),
        db: Session = Depends(get_db)
) -> dict:
    """
    Récupère les données OHLC depuis CoinGecko et les stocke en base.
    """
    try:
        # Appel à l'API CoinGecko
        ohlc_data = await coingecko_service.get_ohlc(symbol=symbol, days=days)

        if not ohlc_data:
            raise HTTPException(
                status_code=502,
                detail="Aucune donnée reçue de CoinGecko"
            )

        # Déterminer le timeframe selon le nombre de jours
        if days <= 2:
            timeframe = "30m"
        elif days <= 30:
            timeframe = "4h"
        else:
            timeframe = "4d"

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
            # Utiliser une fenêtre de tolérance de 5 minutes pour gérer les décalages
            ts_min = ts - timedelta(minutes=5)
            ts_max = ts + timedelta(minutes=5)

            existing = db.query(Candle).filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= ts_min,
                Candle.timestamp <= ts_max
            ).first()

            if existing:
                # Mettre à jour si les valeurs ont changé
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

            # Créer la nouvelle bougie
            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open_price=candle_data["open"],
                high_price=candle_data["high"],
                low_price=candle_data["low"],
                close_price=candle_data["close"],
                volume=candle_data["volume"],
                source="coingecko"
            )

            db.add(candle)
            inserted += 1

        # Sauvegarder en base
        db.commit()

        # Calculer les stats
        tf_hours = get_timeframe_hours(timeframe)
        expected = int((days * 24) / tf_hours) + 1

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
            "coverage_pct": round((len(ohlc_data) / expected) * 100, 1) if expected > 0 else 0
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
    summary="Prix actuel",
    description="Retourne le prix actuel depuis CoinGecko"
)
async def get_current_price(
        symbol: str = Query(default="BTC/USD", description="Paire de trading")
) -> dict:
    """Récupère le prix actuel d'une crypto."""
    price = await coingecko_service.get_current_price(symbol)

    if price is None:
        raise HTTPException(
            status_code=502,
            detail="Impossible de récupérer le prix depuis CoinGecko"
        )

    return {
        "symbol": symbol,
        "price": price,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get(
    "/info",
    response_model=dict,
    summary="Informations de marché",
    description="Retourne les informations complètes de marché"
)
async def get_market_info(
        symbol: str = Query(default="BTC/USD", description="Paire de trading")
) -> dict:
    """Récupère les informations de marché complètes."""
    market_data = await coingecko_service.get_market_data(symbol)

    if market_data is None:
        raise HTTPException(
            status_code=502,
            detail="Impossible de récupérer les données depuis CoinGecko"
        )

    return market_data
