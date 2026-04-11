"""
Schémas Pydantic pour la Learning Layer — apprentissage explicable.

v1.9.0 — Additif, rétrocompatible.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LearningSignalItem(BaseModel):
    """Un échantillon d'apprentissage."""
    id: int
    trade_id: int
    score: Optional[float] = None
    confidence: Optional[str] = None
    direction: Optional[str] = None
    slot: Optional[str] = None
    profile_type: Optional[str] = None
    leverage: Optional[float] = None
    entry_price: Optional[float] = None
    exit_type: Optional[str] = None
    pnl_brut: Optional[float] = None
    pnl_pct: Optional[float] = None
    duration_minutes: Optional[float] = None
    was_profitable: bool = False
    was_reversal: bool = False
    time_since_last_trade_min: Optional[float] = None
    # [v1.9.1] Analyse économique
    cost_estimated: Optional[float] = None
    pnl_net_estimated: Optional[float] = None
    usefulness_category: Optional[str] = None  # useful / insignificant / churn / loss_useful / loss_destructive
    # [v2.0.2] Contexte BTC
    btc_trend_at_entry: Optional[str] = None
    btc_move_during_pct: Optional[float] = None
    btc_move_after_exit_pct: Optional[float] = None
    missed_favorable_move: bool = False
    capture_efficiency_pct: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StrategyFeedbackItem(BaseModel):
    """Un ajustement de paramètre (shadow ou appliqué)."""
    id: int
    parameter_name: str
    original_value: float
    suggested_value: float
    current_value: float
    min_allowed: Optional[float] = None
    max_allowed: Optional[float] = None
    reason: str
    sample_size: int = 0
    win_rate_observed: Optional[float] = None
    avg_pnl_observed: Optional[float] = None
    version: int = 1
    is_active: bool = False
    mode: str = "shadow"
    profile_type: str = "scalping"
    created_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LearningDatasetStats(BaseModel):
    """Statistiques du dataset d'apprentissage."""
    total_samples: int = 0
    samples_profitable: int = 0
    samples_unprofitable: int = 0
    avg_pnl: float = 0.0
    # Par direction
    long_samples: int = 0
    short_samples: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0
    # Par exit type
    exit_type_distribution: dict = {}
    # [v1.9.1] Analyse économique
    avg_cost_per_trade: float = 0.0
    avg_pnl_net: float = 0.0
    trades_useful: int = 0
    trades_insignificant: int = 0
    trades_churn: int = 0
    pct_economically_useful: float = 0.0
    min_economic_move_pct: float = 0.0  # Seuil calculé du cost model
    # [v1.9.3] Stats short spécifiques
    short_trades_useful: int = 0
    short_trades_insignificant: int = 0
    short_trades_churn: int = 0
    pct_short_economically_useful: float = 0.0
    # Couverture
    oldest_sample: Optional[str] = None
    newest_sample: Optional[str] = None


class PatternInsight(BaseModel):
    """Un pattern identifié par le learning."""
    pattern_name: str
    description: str
    sample_count: int
    win_rate: float
    avg_pnl: float
    impact: str  # "positif" | "négatif" | "neutre"


class LearningAnalysisResponse(BaseModel):
    """Réponse complète de l'analyse d'apprentissage."""
    dataset_stats: LearningDatasetStats
    patterns: list[PatternInsight] = []
    suggested_adjustments: list[StrategyFeedbackItem] = []
    active_adjustments: list[StrategyFeedbackItem] = []
    # Mode
    learning_enabled: bool = False
    mode: str = "shadow"  # shadow | active


class LearningVersionHistory(BaseModel):
    """Historique des versions d'ajustements."""
    versions: list[StrategyFeedbackItem] = []
    current_version: int = 0

