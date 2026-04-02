"""
Schémas Pydantic pour les news et le sentiment.

Types de sentiment :
- positive : article avec tonalité haussière
- negative : article avec tonalité baissière
- neutral  : article informatif sans tonalité claire

Niveaux d'impact :
- high   : nouvelles réglementaires, institutionnelles, hacks majeurs
- medium : évolutions de marché, partenariats, mises à jour protocole
- low    : articles généraux, opinions, analyses
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class SentimentType(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class ImpactLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NewsItem(BaseModel):
    """Un article de news crypto."""
    title: str
    url: Optional[str] = None
    source: str = "unknown"
    published_at: Optional[datetime] = None
    sentiment: SentimentType = SentimentType.NEUTRAL
    impact: ImpactLevel = ImpactLevel.LOW
    keywords: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class NewsSentimentSummary(BaseModel):
    """Résumé du sentiment global des news."""
    total_articles: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    overall_sentiment: SentimentType = SentimentType.NEUTRAL
    sentiment_score: int = Field(
        default=0,
        description="Score de sentiment global (-100 à +100)",
        ge=-100,
        le=100,
    )


class NewsResponse(BaseModel):
    """Réponse complète de l'endpoint /news."""
    items: list[NewsItem] = Field(default_factory=list)
    summary: NewsSentimentSummary = Field(default_factory=NewsSentimentSummary)
    meta: dict = Field(default_factory=dict)

