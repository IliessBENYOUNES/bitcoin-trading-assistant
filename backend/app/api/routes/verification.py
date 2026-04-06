"""
Routes pour la verification historique (Time-Travel Backtest).

Endpoints :
- POST /backtest/history/load   : Charger l'historique profond depuis Binance
- GET  /backtest/history/range  : Plage de dates disponible en base
- POST /backtest/verify         : Verification ponctuelle a une date
- POST /backtest/walk-forward   : Analyse walk-forward complete
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.history_loader_service import HistoryLoaderService
from app.services.verification_service import VerificationService
from app.schemas.verification import (
    HistoryLoadConfig,
    HistoryLoadResponse,
    HistoryRangeResponse,
    HistoryIntegrityResponse,
    VerificationRequest,
    VerificationResult,
    WalkForwardConfig,
    WalkForwardResult,
    InterestingDatesResponse,
)

router = APIRouter(
    prefix="/backtest",
    tags=["Verification Historique"]
)


@router.post(
    "/history/load",
    response_model=HistoryLoadResponse,
    summary="Charger l'historique profond depuis Binance",
    description=(
        "Telecharge les donnees OHLCV historiques depuis Binance (2017→maintenant) "
        "et les stocke en base. Idempotent : relancer ne cree pas de doublons. "
        "Pour timeframe=1d, environ 3200 candles (~5s). "
        "Pour timeframe=4h, environ 19000 candles (~30s)."
    ),
)
async def load_history(
    config: HistoryLoadConfig,
    db: Session = Depends(get_db),
) -> HistoryLoadResponse:
    """Charge l'historique BTC depuis Binance."""
    service = HistoryLoaderService(db)
    try:
        return await service.load(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur chargement: {str(e)}")


@router.get(
    "/history/range",
    response_model=HistoryRangeResponse,
    summary="Plage de dates disponible en base",
    description="Retourne la date min/max et le nombre de candles disponibles.",
)
def get_history_range(
    symbol: str = "BTC/USD",
    timeframe: str = "1d",
    db: Session = Depends(get_db),
) -> HistoryRangeResponse:
    """Retourne la plage de dates chargee en base."""
    service = VerificationService(db)
    return service.get_history_range(symbol, timeframe)


@router.get(
    "/history/integrity",
    response_model=HistoryIntegrityResponse,
    summary="Verification d'integrite de l'historique",
    description=(
        "Analyse la completude de l'historique charge : detecte les jours manquants, "
        "calcule un pourcentage de completude, et attribue un grade de qualite "
        "(EXCELLENT, GOOD, WARNING, CRITICAL). "
        "Important : les indicateurs techniques (SMA200) sont fausses si >5% de trous."
    ),
)
def check_history_integrity(
    symbol: str = "BTC/USD",
    timeframe: str = "1d",
    db: Session = Depends(get_db),
) -> HistoryIntegrityResponse:
    """Verifie l'integrite de l'historique charge."""
    service = VerificationService(db)
    return service.check_integrity(symbol, timeframe)


@router.post(
    "/verify",
    response_model=VerificationResult,
    summary="Verification ponctuelle a une date",
    description=(
        "Se positionne a une date passee, execute le moteur de decision "
        "avec UNIQUEMENT les donnees anterieures, puis compare la prediction "
        "avec ce qui s'est reellement passe aux horizons demandes (7j, 30j, 90j). "
        "Le sentiment n'est pas disponible en historique — le moteur fonctionne "
        "en mode degrade (100% technique)."
    ),
)
def verify_at_date(
    request: VerificationRequest,
    db: Session = Depends(get_db),
) -> VerificationResult:
    """Verification ponctuelle a une date donnee."""
    service = VerificationService(db)
    try:
        return service.verify_at_date(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur verification: {str(e)}")


@router.get(
    "/interesting-dates",
    response_model=InterestingDatesResponse,
    summary="Trouver les dates avec des signaux techniques forts",
    description=(
        "Scanne l'historique charge et identifie les dates ou les indicateurs "
        "techniques montrent des signaux forts (RSI en survente/surachat, "
        "croisements MACD marqués, prix hors bandes de Bollinger, etc.). "
        "Utile pour tester le modele sur des situations a fort potentiel."
    ),
)
def get_interesting_dates(
    symbol: str = "BTC/USD",
    timeframe: str = "1d",
    min_strength: float = 0.7,
    max_results: int = 20,
    step_days: float = 3.0,
    db: Session = Depends(get_db),
) -> InterestingDatesResponse:
    """Identifie les dates avec des signaux techniques forts."""
    service = VerificationService(db)
    try:
        return service.find_interesting_dates(
            symbol=symbol,
            timeframe=timeframe,
            min_strength=min_strength,
            max_results=max_results,
            step_days=step_days,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur scan: {str(e)}")


@router.post(
    "/walk-forward",
    response_model=WalkForwardResult,
    summary="Analyse walk-forward complete",
    description=(
        "Execute verify_at_date a intervalles reguliers sur une plage de dates, "
        "puis agrege les resultats pour mesurer la precision globale du modele. "
        "Si compare_mode=true, execute aussi en mode 100% technique et compare "
        "avec le mode technique+sentiment pour mesurer l'apport du sentiment. "
        "Attention : peut prendre plusieurs minutes selon la plage et le pas."
    ),
)
def walk_forward(
    config: WalkForwardConfig,
    db: Session = Depends(get_db),
) -> WalkForwardResult:
    """Analyse walk-forward : precision du modele sur une periode."""
    service = VerificationService(db)
    try:
        return service.walk_forward(config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur walk-forward: {str(e)}")

