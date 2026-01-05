"""
Package des schémas Pydantic (DTOs pour l'API).

Les schémas définissent la structure des requêtes et réponses de l'API.
"""

from app.schemas.candle import (
    CandleBase,
    CandleCreate,
    CandleResponse,
    CandleListResponse,
)

__all__ = [
    "CandleBase",
    "CandleCreate",
    "CandleResponse",
    "CandleListResponse",
]
