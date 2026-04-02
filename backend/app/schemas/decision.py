"""
Schémas Pydantic pour le moteur de décision.

Le moteur de décision combine :
- Les signaux techniques (score composite -100/+100)
- Le sentiment des news (-100/+100)
en scénarios multi-outcome avec probabilités et recommandations explicables.

SCÉNARIOS : Hausse / Stable / Baisse — avec probabilités normalisées (somme = 1.0)
RECOMMANDATION : Acheter / Vendre / Attendre — avec explication en français
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

from app.schemas.signal import SignalDirection, ConfidenceLevel


class ActionType(str, Enum):
    """Action recommandée par le moteur de décision."""
    BUY = "acheter"
    SELL = "vendre"
    HOLD = "attendre"


class Scenario(BaseModel):
    """
    Un scénario de marché possible avec sa probabilité.

    Exemples :
        - Hausse (65%) : "Les indicateurs convergent vers un momentum haussier"
        - Stable (25%) : "Signaux contradictoires, consolidation probable"
        - Baisse (10%) : "RSI en surachat, risque de correction"
    """
    label: str = Field(..., description="Nom du scénario (Hausse, Stable, Baisse)")
    probability: float = Field(
        ..., ge=0.0, le=1.0,
        description="Probabilité du scénario (0.0 à 1.0)"
    )
    direction: SignalDirection = Field(..., description="Direction du scénario")
    description: str = Field(..., description="Explication du scénario en français")


class RuleResult(BaseModel):
    """
    Résultat de l'évaluation d'une règle du moteur de décision.

    Chaque règle teste une condition combinée (ex: RSI > 70 AND MACD baissier)
    et contribue au score final avec un poids.
    """
    rule_name: str = Field(..., description="Nom de la règle")
    condition: str = Field(..., description="Description de la condition testée")
    satisfied: bool = Field(..., description="La condition est-elle remplie ?")
    weight: float = Field(
        ..., ge=0.0, le=1.0,
        description="Poids de la règle dans le scoring (0.0 à 1.0)"
    )
    detail: str = Field(..., description="Détail du résultat en français")
    direction: SignalDirection = Field(
        ..., description="Direction de la règle si satisfaite"
    )


class Recommendation(BaseModel):
    """
    Recommandation d'action avec explication.

    L'action est déterminée par le scénario dominant et la convergence
    des règles. L'explication fournit le contexte en langage naturel.
    """
    action: ActionType = Field(..., description="Action recommandée")
    confidence: ConfidenceLevel = Field(..., description="Niveau de confiance")
    explanation: str = Field(
        ..., description="Explication en français de la recommandation"
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Liste des raisons principales (puces)"
    )


class DecisionMeta(BaseModel):
    """Métadonnées de la décision."""
    symbol: str
    timeframe: str
    history_days: float
    timestamp: str
    sentiment_available: bool = Field(
        True,
        description="Le sentiment des news était-il disponible pour cette décision ?"
    )
    technical_weight: float = Field(0.7, description="Poids du score technique (0-1)")
    sentiment_weight: float = Field(0.3, description="Poids du sentiment (0-1)")


class DecisionResponse(BaseModel):
    """
    Réponse complète du moteur de décision.

    Combine les scores techniques et sentimentaux en une décision
    structurée avec scénarios, recommandation et règles évaluées.
    """
    meta: DecisionMeta = Field(..., description="Métadonnées")
    scenarios: list[Scenario] = Field(
        ..., description="Scénarios possibles avec probabilités"
    )
    rules_evaluated: list[RuleResult] = Field(
        ..., description="Liste des règles évaluées"
    )
    recommendation: Recommendation = Field(
        ..., description="Recommandation d'action"
    )
    technical_score: int = Field(
        ..., ge=-100, le=100,
        description="Score technique pur (-100 à +100)"
    )
    sentiment_score: int = Field(
        ..., ge=-100, le=100,
        description="Score sentiment (-100 à +100)"
    )
    combined_score: int = Field(
        ..., ge=-100, le=100,
        description="Score combiné pondéré (-100 à +100)"
    )
    summary: str = Field(
        ..., description="Résumé lisible de la décision (1-2 phrases)"
    )

