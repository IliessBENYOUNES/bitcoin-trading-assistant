"""
Schémas Pydantic pour le Journal d'Évaluation Paper Trading,
les Profils de Trading, le Levier Automatique et la Qualification de Style.

v1.5 — Additif, rétrocompatible.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# Profils de Trading
# ─────────────────────────────────────────────────────────────────────────────

class TradingProfileType(str, Enum):
    conservative = "conservative"
    balanced = "balanced"
    aggressive = "aggressive"


class TradingProfileParams(BaseModel):
    """Paramètres d'un profil de trading."""
    profile_type: TradingProfileType
    label: str
    description: str
    # Seuils d'entrée
    min_score: int = Field(description="Score composite minimum pour ouvrir")
    min_confidence: str = Field(description="Confiance minimum (low/medium/high)")
    min_scenario_dominance: float = Field(description="Probabilité min du scénario dominant")
    # Fréquence
    max_trades_per_day: int = Field(description="Nombre max de trades par jour")
    cooldown_minutes: int = Field(description="Minutes de cooldown entre deux trades")
    max_position_duration_hours: float = Field(description="Durée max position (heures)")
    # Sorties
    profit_take_pct: float = Field(description="% PnL latent pour prise de profit rapide")
    loss_cut_pct: float = Field(description="% PnL latent pour coupe de perte")
    loss_cut_score_threshold: int = Field(description="Score en dessous duquel on coupe sur perte")
    # Levier
    leverage_enabled: bool = Field(description="Levier auto activé pour ce profil")
    max_leverage: float = Field(description="Levier maximum autorisé")


class TradingProfileResponse(BaseModel):
    """Profil de trading actif + paramètres."""
    active_profile: TradingProfileType
    params: TradingProfileParams


class TradingProfileSetRequest(BaseModel):
    """Requête pour changer de profil."""
    profile: TradingProfileType


# ─────────────────────────────────────────────────────────────────────────────
# Journal d'Évaluation — Filtres
# ─────────────────────────────────────────────────────────────────────────────

class JournalDateFilter(BaseModel):
    """Filtre temporel pour le journal."""
    date_from: Optional[str] = None
    date_to: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Journal — Vue synthétique de la période
# ─────────────────────────────────────────────────────────────────────────────

class JournalPeriodSummary(BaseModel):
    """Synthèse des métriques sur une plage de dates."""
    date_from: str
    date_to: str
    # Ticks
    total_ticks: int = 0
    # Trades
    total_trades: int = 0
    trades_per_day: float = 0.0
    trades_per_hour_avg: float = 0.0
    # Performance
    win_rate: float = 0.0
    pnl_realized: float = 0.0
    pnl_latent: Optional[float] = None
    pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    sharpe: Optional[float] = None
    max_drawdown_pct: float = 0.0
    # Séries
    best_streak: int = 0
    worst_streak: int = 0
    # Durées
    avg_position_duration_hours: float = 0.0
    # Benchmark
    buy_hold_pct: float = 0.0
    delta_vs_buy_hold: float = 0.0
    # Verdict
    verdict: str = "N/A"  # prometteur / mitigé / faible / critique


# ─────────────────────────────────────────────────────────────────────────────
# Journal — Vue journalière
# ─────────────────────────────────────────────────────────────────────────────

class JournalDaySummary(BaseModel):
    """Résumé d'un jour de paper trading."""
    date: str
    total_ticks: int = 0
    total_trades: int = 0
    pnl_realized: float = 0.0
    pnl_pct: float = 0.0
    win_rate: float = 0.0
    drawdown_pct: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    avg_position_duration_hours: float = 0.0
    verdict: str = "N/A"


# ─────────────────────────────────────────────────────────────────────────────
# Journal — Vue activité / fréquence
# ─────────────────────────────────────────────────────────────────────────────

class JournalActivityStats(BaseModel):
    """Statistiques d'activité et fréquence de trading."""
    total_ticks: int = 0
    ticks_with_signal: int = 0
    ticks_opened: int = 0
    ticks_closed: int = 0
    ticks_hold: int = 0
    ticks_blocked_risk: int = 0
    ticks_ignored_signal: int = 0
    ticks_position_held: int = 0
    ticks_exit_tp: int = 0
    ticks_exit_sl: int = 0
    ticks_exit_signal: int = 0
    ticks_exit_expired: int = 0
    tick_to_trade_ratio: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Journal — Raisons de non-trade
# ─────────────────────────────────────────────────────────────────────────────

class NonTradeReasonItem(BaseModel):
    """Agrégation d'une raison de non-trade."""
    reason: str
    label: str
    count: int = 0
    pct: float = 0.0


class JournalNonTradeReasons(BaseModel):
    """Distribution des raisons de non-trade."""
    total_non_trade_ticks: int = 0
    reasons: list[NonTradeReasonItem] = []


# ─────────────────────────────────────────────────────────────────────────────
# Journal — Réponse complète
# ─────────────────────────────────────────────────────────────────────────────

class JournalResponse(BaseModel):
    """Réponse complète du journal d'évaluation."""
    period: JournalPeriodSummary
    daily: list[JournalDaySummary] = []
    activity: JournalActivityStats
    non_trade_reasons: JournalNonTradeReasons
    profile_type: str = "conservative"


# ─────────────────────────────────────────────────────────────────────────────
# Qualification du style de trading
# ─────────────────────────────────────────────────────────────────────────────

class DurationBucket(BaseModel):
    """Bucket de distribution des durées de position."""
    label: str  # "< 1min", "1-5min", "5-15min", "15-60min", "1h+"
    count: int = 0
    pct: float = 0.0


class TradingStyleResult(BaseModel):
    """Qualification du style de trading."""
    total_closed_trades: int = 0
    duration_distribution: list[DurationBucket] = []
    dominant_style: str = "N/A"  # scalping-like, intraday, swing_intraday
    avg_duration_minutes: float = 0.0
    median_duration_minutes: float = 0.0
    # Observabilité micro-temporelle
    signals_strong_per_hour: float = 0.0
    signals_ignored_per_hour: float = 0.0
    exits_fast_count: int = 0  # < 5min
    exits_slow_count: int = 0  # > 1h


# ─────────────────────────────────────────────────────────────────────────────
# Levier automatique — Résultat de recommandation
# ─────────────────────────────────────────────────────────────────────────────

class LeverageRecommendation(BaseModel):
    """Recommandation de levier automatique."""
    recommended: float = 1.0
    final: float = 1.0
    max_allowed: float = 1.0
    risk_adjusted: bool = False
    reasons: list[str] = []
    factors: dict = {}  # Détail des facteurs utilisés

