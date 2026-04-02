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

from app.schemas.signal import (
    SignalItem,
    SignalDirection,
    ConfidenceLevel,
    CompositeScore,
    SignalResponse,
)

from app.schemas.alert import (
    AlertCreate,
    AlertUpdate,
    AlertResponse,
    AlertNotification,
    AlertCheckResponse,
)

__all__ = [
    "CandleBase",
    "CandleCreate",
    "CandleResponse",
    "CandleListResponse",
    "SignalItem",
    "SignalDirection",
    "ConfidenceLevel",
    "CompositeScore",
    "SignalResponse",
    "AlertCreate",
    "AlertUpdate",
    "AlertResponse",
    "AlertNotification",
    "AlertCheckResponse",
]
