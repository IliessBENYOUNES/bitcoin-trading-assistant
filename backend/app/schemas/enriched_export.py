"""
Schémas Pydantic pour l'export enrichi et l'analyse de tendances ratées.

Export minute par minute : BTC price + décisions moteur + positions + PnL.
Corrélation avancée : tendances ratées, sorties prématurées, gate blocking analysis.

v2.0.4
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class EnrichedTickRow(BaseModel):
    """Une ligne de l'export enrichi — un tick avec tout son contexte."""
    timestamp: datetime
    btc_price: Optional[float] = None
    btc_variation_pct: Optional[float] = None  # variation depuis le tick précédent

    # Slot / profil
    slot: Optional[str] = None
    profile_type: Optional[str] = None

    # Décision moteur
    decision_action: Optional[str] = None  # acheter / vendre / attendre
    decision_score: Optional[float] = None
    decision_confidence: Optional[str] = None
    action_taken: str = "hold"  # opened_long, hold, closed_tp, etc.

    # Raison de non-trade
    reason_no_trade: Optional[str] = None
    reason_detail: Optional[str] = None
    rejection_category: Optional[str] = None

    # Position ouverte
    had_open_position: bool = False
    unrealized_pnl: Optional[float] = None

    # Événement de trade
    is_entry: bool = False
    is_exit: bool = False
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_type: Optional[str] = None
    trade_pnl: Optional[float] = None
    trade_pnl_pct: Optional[float] = None
    trade_direction: Optional[str] = None

    # Market quality context
    market_quality_score: Optional[int] = None
    micro_trend_score: Optional[int] = None
    volume_ratio: Optional[float] = None

    # Indicateur de mouvement raté (calculé post-hoc)
    missed_move_flag: bool = False
    missed_move_pct: Optional[float] = None


class GateBlockDistribution(BaseModel):
    """Distribution des refus par gate pour un slot/profil."""
    gate_name: str
    block_count: int
    block_pct: float
    avg_score_when_blocked: Optional[float] = None
    # Combien de mouvements favorables ont été ratés à cause de ce gate
    favorable_moves_missed: int = 0
    favorable_move_avg_pct: Optional[float] = None


class MissedTrendAnalysis(BaseModel):
    """Analyse d'une tendance BTC ratée par le moteur."""
    start_ts: datetime
    end_ts: datetime
    start_price: float
    end_price: float
    move_pct: float
    direction: str  # "up" | "down"
    duration_minutes: float
    # Pourquoi le moteur n'a pas tradé
    dominant_blocking_gate: Optional[str] = None
    ticks_during_trend: int = 0
    avg_score_during_trend: Optional[float] = None


class EnrichedExportSummary(BaseModel):
    """Résumé de l'export enrichi."""
    total_ticks: int = 0
    total_entries: int = 0
    total_exits: int = 0
    total_holds: int = 0

    # Gate blocking analysis
    gate_distribution: list[GateBlockDistribution] = []
    dominant_gate: Optional[str] = None
    dominant_gate_pct: Optional[float] = None

    # Missed trends
    missed_trends: list[MissedTrendAnalysis] = []
    total_missed_move_pct: float = 0.0

    # Période
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    btc_move_total_pct: Optional[float] = None


class EnrichedExportResponse(BaseModel):
    """Réponse complète de l'export enrichi."""
    ticks: list[EnrichedTickRow] = []
    summary: EnrichedExportSummary = Field(default_factory=EnrichedExportSummary)

