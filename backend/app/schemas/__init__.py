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

from app.schemas.news import (
    SentimentType,
    ImpactLevel,
    NewsItem,
    NewsSentimentSummary,
    NewsResponse,
)

from app.schemas.decision import (
    ActionType,
    Scenario,
    RuleResult,
    Recommendation,
    DecisionMeta,
    DecisionResponse,
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
    "SentimentType",
    "ImpactLevel",
    "NewsItem",
    "NewsSentimentSummary",
    "NewsResponse",
    "ActionType",
    "Scenario",
    "RuleResult",
    "Recommendation",
    "DecisionMeta",
    "DecisionResponse",
]
