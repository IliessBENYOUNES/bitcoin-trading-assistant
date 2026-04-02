"""
Schémas Pydantic pour les signaux de trading.

Chaque indicateur technique est interprété en un SignalItem
qui donne une direction (bullish/bearish/neutral), une force
et une explication lisible.

Un CompositeScore agrège tous les signaux en un score -100/+100
avec un niveau de confiance et un consensus.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class SignalDirection(str, Enum):
    """Direction d'un signal."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ConfidenceLevel(str, Enum):
    """Niveau de confiance du score composite."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SignalItem(BaseModel):
    """
    Un signal individuel issu d'un indicateur technique.

    Exemples :
        - RSI en surachat (72) → bearish, strength=0.7
        - MACD croisé haussier → bullish, strength=0.8
        - Prix au-dessus de SMA50 → bullish, strength=0.5
    """
    indicator: str = Field(
        ...,
        description="Nom de l'indicateur (rsi, macd, sma, bollinger)"
    )
    direction: SignalDirection = Field(
        ...,
        description="Direction du signal"
    )
    strength: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="Force du signal (0=faible, 1=très fort)"
    )
    value: Optional[float] = Field(
        None,
        description="Valeur brute de l'indicateur (ex: RSI=72)"
    )
    message: str = Field(
        ...,
        description="Explication lisible du signal"
    )


class CompositeScore(BaseModel):
    """
    Score composite agrégé de tous les signaux.

    - score: -100 (très baissier) à +100 (très haussier)
    - confidence: basé sur le nombre de signaux convergents
    - consensus: tous d'accord, majorité, ou divisé
    """
    score: int = Field(
        ...,
        ge=-100, le=100,
        description="Score agrégé de -100 (bearish) à +100 (bullish)"
    )
    direction: SignalDirection = Field(
        ...,
        description="Direction dominante"
    )
    confidence: ConfidenceLevel = Field(
        ...,
        description="Niveau de confiance"
    )
    consensus: str = Field(
        ...,
        description="Degré de convergence (unanimous, majority, divided)"
    )
    bullish_count: int = Field(
        ...,
        description="Nombre de signaux haussiers"
    )
    bearish_count: int = Field(
        ...,
        description="Nombre de signaux baissiers"
    )
    neutral_count: int = Field(
        ...,
        description="Nombre de signaux neutres"
    )


class SignalResponse(BaseModel):
    """
    Réponse complète de l'endpoint /market/signals.

    Contient les signaux individuels, le score composite,
    et les métadonnées de contexte.
    """
    meta: dict = Field(
        ...,
        description="Métadonnées (symbol, timeframe, timestamps, statuts)"
    )
    signals: list[SignalItem] = Field(
        ...,
        description="Liste des signaux individuels"
    )
    composite: CompositeScore = Field(
        ...,
        description="Score composite agrégé"
    )
    summary: str = Field(
        ...,
        description="Résumé lisible de l'analyse (1-2 phrases)"
    )

