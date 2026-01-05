"""
Routes pour les données de marché (chandeliers OHLCV).

Endpoints :
- GET  /market/candles       : Récupérer les chandeliers depuis la BDD
- POST /market/candles/fetch : Récupérer depuis CoinGecko et stocker en BDD
- GET  /market/price         : Prix actuel
- GET  /market/info          : Informations de marché complètes
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timezone

from app.database import get_db
from app.models import Candle
from app.schemas import CandleResponse, CandleListResponse
from app.services.coingecko_service import CoinGeckoService

# Router avec préfixe /market
router = APIRouter(
    prefix="/market",
    tags=["Market Data"]
)

# Instance du service CoinGecko (réutilisée)
coingecko_service = CoinGeckoService()


@router.get(
    "/candles",
    response_model=CandleListResponse,
    summary="Récupérer les chandeliers depuis la base de données",
    description="Retourne les chandeliers OHLCV stockés localement"
)
def get_candles(
    symbol: str = Query(default="BTC/USD", description="Paire de trading"),
    timeframe: str = Query(default="4h", description="Intervalle de temps"),
    limit: int = Query(default=100, ge=1, le=1000, description="Nombre max de résultats"),
    db: Session = Depends(get_db)
) -> CandleListResponse:
    """
    Récupère les chandeliers depuis la base de données locale.
    
    Les résultats sont triés du plus récent au plus ancien.
    """
    query = (
        db.query(Candle)
        .filter(Candle.symbol == symbol)
        .filter(Candle.timeframe == timeframe)
        .order_by(desc(Candle.timestamp))
        .limit(limit)
    )
    
    candles = query.all()
    
    candle_responses = [
        CandleResponse.model_validate(candle)
        for candle in candles
    ]
    
    return CandleListResponse(
        data=candle_responses,
        count=len(candle_responses),
        symbol=symbol,
        timeframe=timeframe
    )


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
    
    Note sur les intervalles (timeframes) :
    - 1-2 jours   → chandeliers de 30 minutes (timeframe="30m")
    - 3-30 jours  → chandeliers de 4 heures (timeframe="4h")
    - 31+ jours   → chandeliers de 4 jours (timeframe="4d")
    
    Returns:
        {
            "message": "...",
            "symbol": "BTC/USD",
            "fetched": 42,
            "inserted": 35,
            "duplicates": 7
        }
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
        
        for candle_data in ohlc_data:
            # Vérifier si cette bougie existe déjà
            existing = db.query(Candle).filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp == candle_data["timestamp"]
            ).first()
            
            if existing:
                duplicates += 1
                continue
            
            # Créer la nouvelle bougie
            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=candle_data["timestamp"],
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
        
        return {
            "message": f"Données récupérées avec succès",
            "symbol": symbol,
            "timeframe": timeframe,
            "days": days,
            "fetched": len(ohlc_data),
            "inserted": inserted,
            "duplicates": duplicates
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
    """
    Récupère le prix actuel d'une crypto.
    
    Returns:
        {"symbol": "BTC/USD", "price": 42000.00, "timestamp": "..."}
    """
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
    """
    Récupère les informations de marché complètes.
    
    Inclut : prix, market cap, volume, variations sur 24h/7d/30d, ATH, etc.
    """
    market_data = await coingecko_service.get_market_data(symbol)
    
    if market_data is None:
        raise HTTPException(
            status_code=502,
            detail="Impossible de récupérer les données depuis CoinGecko"
        )
    
    return market_data