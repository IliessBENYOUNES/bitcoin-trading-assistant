"""
Schemas Pydantic pour le module de verification historique (Time-Travel Backtest).

Ce module permet de :
1. Charger l'historique profond BTC depuis Binance (2017→maintenant)
2. Se positionner a n'importe quelle date et obtenir la recommandation du modele
3. Comparer la prediction avec ce qui s'est reellement passe (7j, 30j, 90j)
4. Executer une analyse walk-forward pour mesurer la precision du modele
"""

from pydantic import BaseModel, Field
from typing import Optional


class HistoryLoadConfig(BaseModel):
    """Configuration pour le chargement d'historique profond."""
    symbol: str = Field(default="BTC/USD", description="Paire de trading")
    timeframe: str = Field(default="1d", description="Timeframe (1d recommande, 4h possible)")
    start_date: str = Field(
        default="2017-08-17",
        description="Date de debut (ISO, ex: 2017-08-17 = debut Binance BTCUSDT)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Date de fin (ISO, defaut = maintenant)"
    )


class HistoryLoadResponse(BaseModel):
    """Reponse du chargement d'historique."""
    fetched: int = Field(default=0, description="Nombre de candles recuperees depuis Binance")
    inserted: int = Field(default=0, description="Nombre de candles inserees en base")
    symbol: str = ""
    timeframe: str = ""
    start_ts: str = ""
    end_ts: str = ""
    duration_seconds: float = 0.0


class HistoryRangeResponse(BaseModel):
    """Plage de dates disponible en base pour un symbol/timeframe."""
    symbol: str
    timeframe: str
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    total_candles: int = 0
    has_data: bool = False


class HorizonOutcome(BaseModel):
    """Resultat reel pour un horizon donne (7j, 30j, 90j)."""
    horizon_days: int = Field(..., description="Horizon en jours (ex: 7, 30, 90)")
    end_date: str = Field(..., description="Date de fin de l'horizon")
    end_price: float = Field(..., description="Prix a la fin de l'horizon")
    actual_change_pct: float = Field(..., description="Variation reelle en %")
    actual_direction: str = Field(..., description="hausse, baisse ou stable")
    predicted_action: str = Field(..., description="Action predite (acheter/vendre/attendre)")
    predicted_score: int = Field(default=0, description="Score combine predit")
    correct: bool = Field(..., description="Prediction correcte (direction concordante)")
    quality_score: float = Field(
        default=0.0,
        ge=0.0, le=100.0,
        description="Score de qualite de la prediction (0=terrible, 100=parfait)"
    )
    directional_match: bool = Field(
        default=False,
        description="Le signe du score predit correspond a la direction reelle du marche"
    )
    detail: str = Field(default="", description="Explication du verdict")


class VerificationRequest(BaseModel):
    """Requete de verification a une date donnee."""
    target_date: str = Field(..., description="Date a laquelle se positionner (ISO, ex: 2020-01-01)")
    symbol: str = Field(default="BTC/USD", description="Paire de trading")
    timeframe: str = Field(default="1d", description="Timeframe des candles")
    history_days: float = Field(
        default=200,
        ge=30, le=1000,
        description="Jours de contexte pour les indicateurs"
    )
    horizons: list[int] = Field(
        default=[7, 30, 90],
        description="Horizons de verification en jours (ex: [7, 30, 90])"
    )


class VerificationResult(BaseModel):
    """Resultat d'une verification a une date donnee."""
    target_date: str
    price_at_date: float
    predicted_action: str = Field(..., description="acheter / vendre / attendre")
    predicted_confidence: str = Field(default="low", description="high / medium / low")
    predicted_score: int = Field(default=0, description="Score combine -100 a +100")
    predicted_summary: str = Field(default="", description="Resume de la decision")
    dominant_scenario: str = Field(default="", description="Scenario dominant (Hausse/Stable/Baisse)")
    dominant_probability: float = Field(default=0.0, description="Probabilite du scenario dominant")
    outcomes: list[HorizonOutcome] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class WalkForwardConfig(BaseModel):
    """Configuration pour l'analyse walk-forward."""
    start_date: str = Field(..., description="Date de debut (ISO, ex: 2018-01-01)")
    end_date: str = Field(..., description="Date de fin (ISO, ex: 2025-12-31)")
    step_days: int = Field(
        default=30,
        ge=1, le=365,
        description="Pas entre chaque verification (jours)"
    )
    symbol: str = Field(default="BTC/USD", description="Paire de trading")
    timeframe: str = Field(default="1d", description="Timeframe des candles")
    history_days: float = Field(default=200, ge=30, le=1000, description="Contexte indicateurs")
    horizons: list[int] = Field(
        default=[7, 30, 90],
        description="Horizons de verification"
    )


class HorizonAccuracy(BaseModel):
    """Precision du modele pour un horizon donne."""
    horizon_days: int
    total_points: int = 0
    correct: int = 0
    incorrect: int = 0
    accuracy_pct: float = 0.0
    avg_predicted_score: float = 0.0
    avg_actual_change_pct: float = 0.0
    buy_signals: int = 0
    sell_signals: int = 0
    hold_signals: int = 0
    # Metriques avancees v1.2
    directional_accuracy_pct: float = Field(
        default=0.0,
        description="% ou le signe du score predit correspond a la direction reelle"
    )
    avg_quality_score: float = Field(
        default=0.0,
        description="Score qualite moyen (0-100) sur tous les points"
    )
    high_confidence_accuracy_pct: float = Field(
        default=0.0,
        description="Precision uniquement sur les predictions a forte confiance (|score| > 25)"
    )
    high_confidence_count: int = Field(
        default=0,
        description="Nombre de predictions a forte confiance"
    )
    profitable_direction_pct: float = Field(
        default=0.0,
        description="% de predictions ou suivre le signal aurait ete profitable"
    )


class WalkForwardResult(BaseModel):
    """Resultat complet de l'analyse walk-forward."""
    total_points: int = 0
    start_date: str = ""
    end_date: str = ""
    step_days: int = 0
    accuracy_by_horizon: list[HorizonAccuracy] = Field(default_factory=list)
    points: list[VerificationResult] = Field(default_factory=list)
    summary: str = Field(default="", description="Resume lisible de l'analyse")
    duration_seconds: float = 0.0
    overall_quality_score: float = Field(
        default=0.0,
        description="Score qualite global moyen (0-100) sur tous les horizons"
    )

