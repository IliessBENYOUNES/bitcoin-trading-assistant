"""
Schémas Pydantic pour le Paper Trading.

Définit les structures de requête/réponse pour :
- Compte paper (création, reset, status)
- Trades paper (journal, détails)
- Métriques de performance (live)
- Résultat d'un tick (action prise par le robot)
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Configuration du compte
# ─────────────────────────────────────────────────────────────────────────────

class PaperAccountCreate(BaseModel):
    """Configuration pour créer/reset un compte paper."""
    initial_capital: float = Field(default=10000.0, ge=100, le=10_000_000)
    max_open_duration_hours: float = Field(default=168.0, ge=1, le=8760)
    max_open_positions: int = Field(default=1, ge=1, le=10,
                                    description="Nombre max de positions simultanées (1=mono, >1=multi-slot)")


# ─────────────────────────────────────────────────────────────────────────────
# Réponse trade
# ─────────────────────────────────────────────────────────────────────────────

class PaperTradeResponse(BaseModel):
    """Un trade paper (ouvert ou fermé)."""
    id: int
    account_id: int
    status: str
    direction: str
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss_price: float
    take_profit_price: float
    highest_price_since_entry: Optional[float] = None
    lowest_price_since_entry: Optional[float] = None
    position_size_usd: float
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    entry_reason: str
    exit_reason: Optional[str] = None
    decision_score: Optional[float] = None
    entry_ts: datetime
    exit_ts: Optional[datetime] = None
    duration_hours: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    slot: Optional[str] = None  # v1.7 — slot multi-position

    model_config = {"from_attributes": True}


class PaperTradeListResponse(BaseModel):
    """Liste paginée de trades."""
    trades: list[PaperTradeResponse]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# Réponse compte
# ─────────────────────────────────────────────────────────────────────────────

class PaperAccountResponse(BaseModel):
    """État du compte paper trading."""
    id: int
    initial_capital: float
    current_capital: float
    total_pnl: float
    total_pnl_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe_ratio: Optional[float] = None
    is_active: bool
    max_open_duration_hours: float
    max_open_positions: int = 1  # v1.7
    btc_price_at_start: Optional[float] = None
    peak_capital: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    open_position: Optional[PaperTradeResponse] = None  # rétrocompat
    open_positions: list[PaperTradeResponse] = []  # v1.7 multi-slot

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Métriques
# ─────────────────────────────────────────────────────────────────────────────

class PaperMetrics(BaseModel):
    """Métriques de performance agrégées."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    net_pnl: float = 0.0
    net_pnl_pct: float = 0.0
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: float = 0.0
    avg_trade_pnl: float = 0.0
    avg_trade_duration_hours: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    profit_factor: float = 0.0
    buy_hold_pnl_pct: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Statut complet
# ─────────────────────────────────────────────────────────────────────────────

class PaperStatus(BaseModel):
    """État complet du paper trading (compte + position + métriques)."""
    account: PaperAccountResponse
    open_position: Optional[PaperTradeResponse] = None  # rétrocompat
    open_positions: list[PaperTradeResponse] = []  # v1.7 multi-slot
    metrics: PaperMetrics
    is_running: bool = False
    last_check_ts: Optional[str] = None
    current_btc_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Résultat d'un tick
# ─────────────────────────────────────────────────────────────────────────────

class SlotTickResult(BaseModel):
    """Résultat d'un tick pour un slot individuel."""
    slot: str
    action_taken: str
    detail: str
    profile_type: str
    position_opened: Optional[PaperTradeResponse] = None
    position_closed: Optional[PaperTradeResponse] = None


class PaperTickResult(BaseModel):
    """Résultat d'une itération du paper trading."""
    action_taken: str  # "opened_long", "closed_tp", "closed_sl", "closed_signal", "closed_expired", "hold", "blocked"
    detail: str
    position_opened: Optional[PaperTradeResponse] = None
    position_closed: Optional[PaperTradeResponse] = None
    current_price: float
    timestamp: str
    decision_score: Optional[float] = None
    decision_action: Optional[str] = None
    risk_allowed: Optional[bool] = None
    # v1.5 — Levier et profil
    leverage_used: Optional[float] = None
    profile_type: Optional[str] = None
    non_trade_reason: Optional[str] = None
    # v1.7 — Multi-slot
    slot_results: list[SlotTickResult] = []

