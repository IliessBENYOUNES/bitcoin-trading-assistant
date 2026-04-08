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

from app.schemas.backtest import (
    TradeDirection,
    BacktestConfig,
    BacktestTradeItem,
    BacktestMetrics,
    EquityPoint,
    BacktestMeta,
    BacktestResponse,
)

from app.schemas.verification import (
    HistoryLoadConfig,
    HistoryLoadResponse,
    HistoryRangeResponse,
    HorizonOutcome,
    VerificationRequest,
    VerificationResult,
    WalkForwardConfig,
    WalkForwardResult,
    HorizonAccuracy,
    WalkForwardComparison,
    WalkForwardSummaryStats,
    HistoryIntegrityGap,
    HistoryIntegrityResponse,
    InterestingSignalDetail,
    InterestingDateItem,
    InterestingDatesResponse,
)

from app.schemas.sentiment import (
    SentimentLoadConfig,
    SentimentLoadResponse,
    SentimentRangeResponse,
    SentimentAtDateResponse,
    SentimentHistoryPoint,
    SentimentCoverageResponse,
)

from app.schemas.risk import (
    StopLossType,
    RiskConfigCreate,
    RiskConfigUpdate,
    RiskConfigResponse,
    RiskEvaluation,
    RiskStatus,
)

from app.schemas.paper_trading import (
    PaperAccountCreate,
    PaperAccountResponse,
    PaperTradeResponse,
    PaperTradeListResponse,
    PaperMetrics,
    PaperStatus,
    PaperTickResult,
)

from app.schemas.journal import (
    TradingProfileType,
    TradingProfileParams,
    TradingProfileResponse,
    TradingProfileSetRequest,
    JournalPeriodSummary,
    JournalDaySummary,
    JournalActivityStats,
    NonTradeReasonItem,
    JournalNonTradeReasons,
    JournalResponse,
    DurationBucket,
    TradingStyleResult,
    LeverageRecommendation,
)

from app.schemas.trading_cost import (
    CostPresetType,
    TradingCostConfig,
    TradingCostImpact,
    CostAuditMetrics,
    CostPresetsResponse,
)

__all__ = [
    # ...existing exports...
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
    "TradeDirection",
    "BacktestConfig",
    "BacktestTradeItem",
    "BacktestMetrics",
    "EquityPoint",
    "BacktestMeta",
    "BacktestResponse",
    "HistoryLoadConfig",
    "HistoryLoadResponse",
    "HistoryRangeResponse",
    "HorizonOutcome",
    "VerificationRequest",
    "VerificationResult",
    "WalkForwardConfig",
    "WalkForwardResult",
    "HorizonAccuracy",
    "WalkForwardComparison",
    "WalkForwardSummaryStats",
    "HistoryIntegrityGap",
    "HistoryIntegrityResponse",
    "InterestingSignalDetail",
    "InterestingDateItem",
    "InterestingDatesResponse",
    "SentimentLoadConfig",
    "SentimentLoadResponse",
    "SentimentRangeResponse",
    "SentimentAtDateResponse",
    "SentimentHistoryPoint",
    "SentimentCoverageResponse",
    "StopLossType",
    "RiskConfigCreate",
    "RiskConfigUpdate",
    "RiskConfigResponse",
    "RiskEvaluation",
    "RiskStatus",
    "PaperAccountCreate",
    "PaperAccountResponse",
    "PaperTradeResponse",
    "PaperTradeListResponse",
    "PaperMetrics",
    "PaperStatus",
    "PaperTickResult",
    # v1.5 — Journal, Profils, Levier, Style
    "TradingProfileType",
    "TradingProfileParams",
    "TradingProfileResponse",
    "TradingProfileSetRequest",
    "JournalPeriodSummary",
    "JournalDaySummary",
    "JournalActivityStats",
    "NonTradeReasonItem",
    "JournalNonTradeReasons",
    "JournalResponse",
    "DurationBucket",
    "TradingStyleResult",
    "LeverageRecommendation",
    # v1.8 — Trading Cost Model
    "CostPresetType",
    "TradingCostConfig",
    "TradingCostImpact",
    "CostAuditMetrics",
    "CostPresetsResponse",
]
