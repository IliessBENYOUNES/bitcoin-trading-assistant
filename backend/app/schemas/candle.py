"""
Schémas Pydantic pour les chandeliers.

Les schémas sont l'équivalent des DTOs (Data Transfer Objects) :
- Définissent la structure des données entrantes (requêtes)
- Définissent la structure des données sortantes (réponses)
- Valident automatiquement les données

POURQUOI SÉPARER Model ET Schema ?
- Model (SQLAlchemy) = structure en BASE DE DONNÉES
- Schema (Pydantic) = structure pour l'API

Équivalent Java  : classes DTO distinctes des @Entity
Équivalent Node  : interfaces TypeScript ou Joi schemas
"""

from datetime import datetime
from pydantic import BaseModel, Field


class CandleBase(BaseModel):
    """
    Champs communs à tous les schémas Candle.
    Classe de base dont les autres héritent.
    """
    
    symbol: str = Field(
        ...,  # ... = champ obligatoire
        min_length=1,
        max_length=20,
        examples=["BTC/USD"],
        description="Paire de trading"
    )
    
    timeframe: str = Field(
        ...,
        min_length=1,
        max_length=10,
        examples=["1h"],
        description="Intervalle de temps (1m, 5m, 1h, 1d)"
    )
    
    timestamp: datetime = Field(
        ...,
        description="Date/heure de début de la bougie"
    )
    
    open_price: float = Field(
        ...,
        gt=0,  # gt = greater than (supérieur à 0)
        description="Prix d'ouverture"
    )
    
    high_price: float = Field(
        ...,
        gt=0,
        description="Prix le plus haut"
    )
    
    low_price: float = Field(
        ...,
        gt=0,
        description="Prix le plus bas"
    )
    
    close_price: float = Field(
        ...,
        gt=0,
        description="Prix de fermeture"
    )
    
    volume: float = Field(
        ...,
        ge=0,  # ge = greater or equal (>= 0)
        description="Volume échangé"
    )
    
    source: str = Field(
        default="manual",
        max_length=50,
        examples=["manual", "coingecko", "binance"],
        description="Source des données"
    )


class CandleCreate(CandleBase):
    """
    Schéma pour CRÉER une bougie (requête POST).
    Hérite tous les champs de CandleBase.
    """
    pass


class CandleResponse(CandleBase):
    """
    Schéma pour RETOURNER une bougie (réponse GET).
    Ajoute l'ID et la date de création.
    """
    
    id: int = Field(..., description="Identifiant unique")
    created_at: datetime = Field(..., description="Date d'insertion en base")
    
    class Config:
        """
        from_attributes=True permet de créer un CandleResponse
        directement depuis un objet SQLAlchemy Candle.
        """
        from_attributes = True


class CandleListResponse(BaseModel):
    """
    Schéma pour retourner une liste de bougies avec métadonnées.
    """
    
    data: list[CandleResponse] = Field(
        ...,
        description="Liste des bougies"
    )
    
    count: int = Field(
        ...,
        description="Nombre de bougies retournées"
    )
    
    symbol: str | None = Field(
        None,
        description="Filtre symbole appliqué"
    )
    
    timeframe: str | None = Field(
        None,
        description="Filtre timeframe appliqué"
    )
