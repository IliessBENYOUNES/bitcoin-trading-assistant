"""
Schémas Pydantic pour le diagnostic de fréquence de trading.

v1.6 — Diagnostic "pourquoi le bot trade trop peu" + opportunités manquées.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Raisons de non-trade classées
# ─────────────────────────────────────────────────────────────────────────────

class NonTradeRankedReason(BaseModel):
    """Une raison de non-trade avec son classement."""
    rank: int
    reason: str
    label: str
    count: int
    pct: float
    category: str = "signal"  # signal | risk | structural | frequency


class PositionDurationStats(BaseModel):
    """Statistiques sur la durée des positions."""
    total_closed: int = 0
    avg_duration_hours: float = 0.0
    median_duration_hours: float = 0.0
    min_duration_hours: float = 0.0
    max_duration_hours: float = 0.0
    pct_under_1h: float = 0.0
    pct_1h_to_4h: float = 0.0
    pct_4h_to_24h: float = 0.0
    pct_over_24h: float = 0.0
    ticks_blocked_by_open_position: int = 0
    pct_ticks_blocked_by_position: float = 0.0


class ProfileComparisonRow(BaseModel):
    """Comparaison d'un profil sur les données réelles."""
    profile: str
    total_trades: int = 0
    trades_per_day: float = 0.0
    win_rate: float = 0.0
    net_pnl: float = 0.0
    expectancy: float = 0.0
    avg_duration_hours: float = 0.0
    max_drawdown_pct: float = 0.0
    # Simulated: combien de ticks auraient passé les filtres de CE profil
    simulated_entries: int = 0
    simulated_entries_per_day: float = 0.0
    top_block_reason: str = ""
    top_block_pct: float = 0.0


class RiskBrakeAnalysis(BaseModel):
    """Analyse du risk engine comme frein."""
    total_ticks: int = 0
    ticks_blocked_by_risk: int = 0
    pct_blocked_by_risk: float = 0.0
    ticks_kill_switch: int = 0
    ticks_daily_loss: int = 0
    ticks_leverage_reduced: int = 0
    ticks_leverage_forced_x1: int = 0
    # Comparaison signal vs risk vs structural
    pct_signal_filter: float = 0.0   # decision_wait + score_too_low
    pct_risk_filter: float = 0.0     # risk_blocked + daily_loss + kill_switch
    pct_structural: float = 0.0      # position_already_open + cooldown + max_trades


class CooldownDiagnostic(BaseModel):
    """Diagnostic détaillé du cooldown entre trades."""
    # Config
    cooldown_configured_min: float = 0.0
    smart_cooldown_enabled: bool = False
    # Délais réels observés
    avg_delay_between_trades_min: float = 0.0
    median_delay_between_trades_min: float = 0.0
    min_delay_min: float = 0.0
    max_delay_min: float = 0.0
    # Impact
    ticks_blocked_by_cooldown: int = 0
    pct_blocked_by_cooldown: float = 0.0
    # Distribution des délais (buckets)
    delay_under_2min: int = 0
    delay_2_to_5min: int = 0
    delay_5_to_15min: int = 0
    delay_15_to_60min: int = 0
    delay_over_60min: int = 0
    # Signaux perdus pendant cooldown
    signals_lost_during_cooldown: int = 0
    # Ratio théorique vs réel
    cooldown_efficiency: str = ""  # "Le cooldown bloque 15% des ticks, dont 30% avaient un signal exploitable"


class DiagnosticResponse(BaseModel):
    """Réponse complète du diagnostic de fréquence."""
    # Résumé
    total_ticks: int = 0
    total_trades: int = 0
    tick_to_trade_pct: float = 0.0
    avg_trades_per_day: float = 0.0
    analysis_days: float = 0.0

    # Top raisons de non-trade (classées)
    top_non_trade_reasons: list[NonTradeRankedReason] = []

    # Durée des positions
    position_duration: PositionDurationStats = PositionDurationStats()

    # Comparaison par profil
    profile_comparison: list[ProfileComparisonRow] = []

    # Risk engine comme frein
    risk_brake: RiskBrakeAnalysis = RiskBrakeAnalysis()

    # [v1.9] Diagnostic cooldown
    cooldown: CooldownDiagnostic = CooldownDiagnostic()

    # Verdict synthétique
    main_bottleneck: str = "unknown"
    bottleneck_detail: str = ""
    recommendations: list[str] = []


# ─────────────────────────────────────────────────────────────────────────────
# Opportunités manquées
# ─────────────────────────────────────────────────────────────────────────────

class MissedOpportunityItem(BaseModel):
    """Un exemple d'opportunité manquée."""
    tick_timestamp: str
    btc_price_at_tick: float
    decision_action: Optional[str] = None
    decision_score: Optional[float] = None
    reason_no_trade: str
    profile_at_tick: str
    # Mouvement observé après le tick
    price_after_5m: Optional[float] = None
    price_after_15m: Optional[float] = None
    price_after_30m: Optional[float] = None
    best_move_pct: float = 0.0
    best_move_window: str = ""
    was_exploitable: bool = False


class MissedOpportunitySummary(BaseModel):
    """Synthèse des opportunités manquées."""
    total_non_trade_ticks_analyzed: int = 0
    ticks_with_favorable_move: int = 0
    pct_missed: float = 0.0
    avg_missed_move_pct: float = 0.0
    # Ventilation par seuil
    missed_above_010_pct: int = 0
    missed_above_020_pct: int = 0
    missed_above_030_pct: int = 0
    missed_above_050_pct: int = 0
    # Ventilation par raison
    missed_by_reason: list[NonTradeRankedReason] = []
    # Exemples
    top_examples: list[MissedOpportunityItem] = []
    # Avertissement
    warning: str = "Ces chiffres sont ex-post et incluent potentiellement des faux positifs (bruit). Ils surestiment les gains réels exploitables."


# ─────────────────────────────────────────────────────────────────────────────
# Analyse levier
# ─────────────────────────────────────────────────────────────────────────────

class LeverageAnalysisResponse(BaseModel):
    """Comparaison trades avec/sans levier."""
    total_leveraged_trades: int = 0
    total_unleveraged_trades: int = 0
    # PnL avec levier (réel)
    pnl_with_leverage: float = 0.0
    # PnL sans levier (simulé: PnL / leverage)
    pnl_without_leverage: float = 0.0
    # Delta
    leverage_benefit: float = 0.0
    # Win rates
    win_rate_leveraged: float = 0.0
    win_rate_unleveraged: float = 0.0
    # Trades amplifiés
    trades_amplified_positive: int = 0
    trades_amplified_negative: int = 0
    # Fréquence impact
    trades_refused_by_leverage: int = 0
    trades_reduced_by_risk: int = 0

