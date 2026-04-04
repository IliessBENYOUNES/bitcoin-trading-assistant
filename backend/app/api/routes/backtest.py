"""
Routes pour le backtesting.

Endpoints :
- POST /backtest/run : Lance un backtest avec les parametres donnes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.backtest_service import BacktestService
from app.schemas.backtest import BacktestConfig

router = APIRouter(
    prefix="/backtest",
    tags=["Backtesting"]
)


@router.post(
    "/run",
    response_model=dict,
    summary="Lancer un backtest",
    description=(
        "Rejoue le moteur de decision sur l'historique de candles "
        "en simulant des positions achat/vente. Retourne les metriques "
        "de performance, la liste des trades et la courbe d'equity."
    ),
)
def run_backtest(
    config: BacktestConfig,
    db: Session = Depends(get_db),
) -> dict:
    """
    Lance un backtest complet.

    Le backtest itere sur les candles historiques, evalue la decision
    a chaque pas de temps, et simule les trades.

    Parametres (body JSON) :
    - symbol : Paire (defaut: BTC/USD)
    - timeframe : Intervalle (defaut: 4h)
    - start_days_ago : Nombre de jours d'historique (1-365, defaut: 30)
    - initial_capital : Capital de depart en USD (defaut: 10000)
    """
    service = BacktestService(db)
    try:
        return service.run(config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur backtest: {str(e)}")

