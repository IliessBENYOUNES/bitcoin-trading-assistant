"""
Schemas Pydantic pour le sentiment historique.

Couvre les opérations :
1. Chargement du Fear & Greed Index depuis Alternative.me
2. Chargement des news CryptoCompare (free tier)
3. Requête de sentiment à une date donnée
4. Résumé de la couverture sentiment disponible
"""

from pydantic import BaseModel, Field
from typing import Optional


class SentimentLoadConfig(BaseModel):
    """Configuration pour le chargement du sentiment historique."""
    source: str = Field(
        default="fear_and_greed",
        description="Source de sentiment (fear_and_greed, cryptocompare_news)"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Date de début (ISO, défaut = début de la source)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Date de fin (ISO, défaut = aujourd'hui)"
    )


class SentimentLoadResponse(BaseModel):
    """Réponse du chargement de sentiment historique."""
    source: str = ""
    fetched: int = Field(default=0, description="Points récupérés depuis l'API")
    inserted: int = Field(default=0, description="Points insérés en base (nouveaux)")
    updated: int = Field(default=0, description="Points mis à jour")
    skipped: int = Field(default=0, description="Points déjà présents (identiques)")
    total_in_db: int = Field(default=0, description="Total de points en base après chargement")
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    duration_seconds: float = 0.0


class SentimentRangeResponse(BaseModel):
    """Plage de dates disponible pour une source de sentiment."""
    source: str
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    total_points: int = 0
    has_data: bool = False


class SentimentAtDateResponse(BaseModel):
    """Sentiment à une date donnée (le plus proche disponible)."""
    date: str
    source: str
    raw_score: float = Field(description="Score brut de la source")
    normalized_score: float = Field(description="Score normalisé -100 à +100")
    label: Optional[str] = Field(default=None, description="Label textuel (ex: Extreme Fear)")
    exact_match: bool = Field(
        default=True,
        description="True si la date exacte est trouvée, False si approximation"
    )
    actual_date: Optional[str] = Field(
        default=None,
        description="Date réelle du point de données (si différente de la requête)"
    )


class SentimentHistoryPoint(BaseModel):
    """Un point de sentiment historique."""
    date: str
    source: str
    raw_score: float
    normalized_score: float
    label: Optional[str] = None


class SentimentCoverageResponse(BaseModel):
    """Résumé de la couverture sentiment disponible (toutes sources)."""
    sources: list[SentimentRangeResponse] = Field(default_factory=list)
    total_points: int = 0
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None

