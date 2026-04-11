"""
Schémas Pydantic pour l'audit de corrélation runtime.

Corrèle chaque trade fermé avec le mouvement réel du BTC
pour identifier les tendances ratées, les sorties prématurées,
et l'efficacité de capture du moteur.

v2.0.2
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class BtcContext(BaseModel):
    """Contexte BTC autour d'un trade (avant, pendant, après)."""
    price_at_entry: Optional[float] = None
    price_at_exit: Optional[float] = None
    # Trend à l'entrée (direction de la bougie couvrant l'entrée)
    trend_at_entry: Optional[str] = None  # "up" | "down" | "flat"
    # Variation BTC pendant le trade (entry→exit)
    btc_move_during_pct: Optional[float] = None
    # Variation BTC dans la fenêtre post-exit (1 bougie après la sortie)
    btc_move_after_exit_pct: Optional[float] = None
    # Prix 1 bougie après la sortie
    price_after_exit: Optional[float] = None
    # Si le trade est sorti trop tôt et a raté un mouvement favorable
    missed_favorable_move: bool = False
    missed_move_pct: Optional[float] = None


class TradeCorrelation(BaseModel):
    """Un trade enrichi avec son contexte BTC."""
    # Trade data
    trade_id: int
    slot: Optional[str] = None
    direction: str
    status: str  # exit type
    entry_price: float
    exit_price: Optional[float] = None
    entry_ts: datetime
    exit_ts: Optional[datetime] = None
    duration_minutes: Optional[float] = None
    decision_score: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    leverage: float = 1.0
    # BTC context
    btc_context: BtcContext = Field(default_factory=BtcContext)
    # Capture efficiency: how much of BTC's movement this trade captured
    capture_efficiency_pct: Optional[float] = None
    # Verdict court sur ce trade
    verdict: str = ""


class MissedMovement(BaseModel):
    """Un mouvement BTC significatif non capturé par un trade."""
    start_ts: datetime
    end_ts: datetime
    start_price: float
    end_price: float
    move_pct: float
    direction: str  # "up" | "down"
    duration_minutes: float
    # Quel slot aurait pu le capter
    nearest_trade_before_id: Optional[int] = None
    nearest_trade_after_id: Optional[int] = None
    gap_minutes: Optional[float] = None  # temps entre trades


class CorrelationSummary(BaseModel):
    """Statistiques globales de corrélation marché / décisions."""
    total_trades: int = 0
    total_candles_analyzed: int = 0
    candle_timeframe_used: Optional[str] = None
    # Mouvement BTC total disponible (somme des abs des mouvements par bougie)
    total_btc_movement_available_pct: float = 0.0
    # Mouvement capturé par les trades
    total_btc_movement_captured_pct: float = 0.0
    # Ratio de capture global
    capture_ratio_pct: float = 0.0
    # Missed movements
    missed_movements_count: int = 0
    missed_movements_total_pct: float = 0.0
    # Stale exits prématurés
    premature_stale_count: int = 0
    premature_stale_avg_missed_pct: float = 0.0
    # Trades par contexte d'entrée
    entries_during_uptrend: int = 0
    entries_during_downtrend: int = 0
    entries_during_flat: int = 0
    # Verdicts
    stale_verdict: str = ""
    capture_verdict: str = ""
    timing_verdict: str = ""


class RuntimeCorrelationResponse(BaseModel):
    """Réponse complète de l'audit de corrélation runtime."""
    trades: list[TradeCorrelation] = []
    missed_movements: list[MissedMovement] = []
    summary: CorrelationSummary = Field(default_factory=CorrelationSummary)

