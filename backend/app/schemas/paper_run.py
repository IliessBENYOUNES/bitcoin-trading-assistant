"""
Schémas Pydantic pour les campagnes de validation (PaperRun).

v1.9.0 — Campagnes de validation avec métriques brut/net et comparaison.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PaperRunCreate(BaseModel):
    """Requête pour démarrer une campagne de validation."""
    name: str = Field(description="Nom de la campagne (ex: 'post-recalibrage-v1.8.1')")
    profile_type: str = Field(default="scalping", description="Profil à utiliser")


class PaperRunResponse(BaseModel):
    """Réponse d'une campagne."""
    id: int
    name: str
    profile_type: str
    status: str
    total_trades: int = 0
    total_ticks: int = 0
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RunMetricsDetail(BaseModel):
    """Métriques détaillées d'un run (brut + net)."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # Brut
    pnl_brut: float = 0.0
    avg_trade_pnl_brut: float = 0.0
    avg_win_brut: float = 0.0
    avg_loss_brut: float = 0.0
    expectancy_brut: float = 0.0
    profit_factor_brut: float = 0.0
    max_drawdown_brut: float = 0.0

    # Net realistic (avec coûts)
    total_costs: float = 0.0
    pnl_net: float = 0.0
    avg_trade_pnl_net: float = 0.0
    expectancy_net: float = 0.0
    profit_factor_net: float = 0.0

    # Par type de sortie
    trailing_stop_exits: int = 0
    stale_exits: int = 0
    momentum_fade_exits: int = 0
    signal_exits: int = 0
    tp_exits: int = 0
    sl_exits: int = 0

    # Par direction
    long_count: int = 0
    short_count: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0
    long_pnl: float = 0.0
    short_pnl: float = 0.0

    # Timing
    avg_duration_minutes: float = 0.0
    avg_delay_between_trades_min: float = 0.0
    median_delay_between_trades_min: float = 0.0


class PaperRunMetrics(BaseModel):
    """Métriques complètes d'une campagne de validation."""
    run: PaperRunResponse
    metrics: RunMetricsDetail


class RunComparison(BaseModel):
    """Comparaison avant/après entre deux runs."""
    before: RunMetricsDetail
    after: RunMetricsDetail
    # Deltas
    delta_win_rate: float = 0.0
    delta_expectancy_brut: float = 0.0
    delta_expectancy_net: float = 0.0
    delta_profit_factor_net: float = 0.0
    delta_avg_delay_min: float = 0.0
    delta_short_count: int = 0
    # Verdict
    verdict: str = "inconnu"  # amélioration_réelle / cosmétique / pas_d_amélioration / régression
    verdict_detail: str = ""

