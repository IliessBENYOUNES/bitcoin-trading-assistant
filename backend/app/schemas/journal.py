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
    scalping = "scalping"
    auto = "auto"


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
    # [v1.6] Timeframe d'analyse (None = 4h par défaut)
    analysis_timeframe: Optional[str] = Field(default=None, description="Timeframe pour le DecisionService (None=4h)")
    # [v1.6] Seuils de décision personnalisés (None = globaux BUY_THRESHOLD/SELL_THRESHOLD)
    buy_threshold: Optional[int] = Field(default=None, description="Score min pour BUY (None=global 25)")
    sell_threshold: Optional[int] = Field(default=None, description="Score min absolu pour SELL (None=global 20)")
    # [v1.6] Sorties rapides
    momentum_fade_enabled: bool = Field(default=False, description="Sortie si le momentum s'essouffle")
    stale_exit_minutes: Optional[int] = Field(default=None, description="Sortie si position stagnante > N min")
    # [v1.7.2] Trailing stop sur profit — sort dès que le PnL recule depuis le pic
    trailing_stop_pct: Optional[float] = Field(
        default=None,
        description="% de recul depuis le pic de PnL pour déclencher le trailing stop (ex: 0.05 = 0.05%)"
    )
    trailing_stop_activation_pct: Optional[float] = Field(
        default=None,
        description="% minimum de profit avant activation du trailing stop (ex: 0.03 = 0.03%)"
    )
    # [v1.9] Smart cooldown — cooldown contextuel au lieu d'un cooldown fixe
    smart_cooldown_enabled: bool = Field(default=False, description="Active le cooldown intelligent contextuel")
    min_cooldown_minutes: Optional[float] = Field(default=None, description="Borne min du cooldown intelligent (minutes)")
    max_cooldown_minutes: Optional[float] = Field(default=None, description="Borne max du cooldown intelligent (minutes)")
    # [v1.9.1] Protection anti-micro-PnL
    # Durée minimale de détention avant que les sorties par signal soient autorisées.
    # Empêche les "fermetures éclair" à 0.00$ qui churnent sans valeur.
    min_hold_seconds: Optional[int] = Field(default=None, description="Durée min en secondes avant sortie signal (None=pas de minimum)")
    # Seuil de mouvement économique minimum : en dessous, le trade n'a presque aucune
    # chance de survivre au cost model realistic. Utilisé pour le learning et les stats.
    min_economic_pnl_pct: Optional[float] = Field(default=None, description="Mouvement % minimum pour qu'un trade soit économiquement utile")
    # [v1.9.3] Score minimum spécifique pour ouvrir un SHORT (mean reversion).
    # Plus exigeant que min_score général car les shorts scalping doivent
    # justifier économiquement le risque contrarian.
    short_min_score: Optional[int] = Field(default=None, description="Score abs minimum pour ouvrir un short scalping (None=pas de filtre)")
    # [v1.9.3] Seuil de score contraire pour fermer un SHORT.
    # Défaut élevé pour laisser les shorts respirer au lieu de les couper
    # dès que le moteur principal redevient légèrement bullish.
    short_exit_score_threshold: Optional[int] = Field(default=None, description="Score abs min pour que 'signal contraire' ferme un short (None=10)")
    # [v1.9.3] Min hold spécifique aux shorts (peut être plus long que le min_hold général).
    short_min_hold_seconds: Optional[int] = Field(default=None, description="Durée min en sec avant sortie signal sur SHORT (None=min_hold_seconds)")
    # [v1.9.5] Momentum fade retention — pourcentage du pic de PnL en dessous duquel on sort.
    # Ex: 0.55 signifie qu'on sort si le PnL tombe sous 55% du pic (recul de 45%).
    # Plus cette valeur est haute, plus on coupe tôt les gains qui s'essoufflent.
    # None = utilise le hardcodé 0.4 (valeur historique).
    momentum_fade_retention: Optional[float] = Field(default=None, description="Seuil de rétention du pic PnL pour momentum fade (0.0-1.0, None=0.4)")
    # [v1.9.5] Stale exit asymétrique — positions en perte sortent plus vite.
    # Si la position est en PnL négatif depuis stale_negative_exit_minutes, on sort.
    # Plus rapide que stale_exit_minutes (qui attend que la position soit "plate").
    stale_negative_exit_minutes: Optional[int] = Field(default=None, description="Minutes avant sortie stale si PnL est négatif (None=stale_exit_minutes)")
    # [v1.9.8] Market quality gating — no-trade zone basée sur la structure de marché.
    # Le moteur vérifie la qualité du marché (range, volume, micro-tendance) avant d'ouvrir.
    # Un marché bruité/sans volume/en tight range est une no-trade zone.
    min_market_quality: Optional[int] = Field(default=None, description="Score qualité marché minimum pour ouvrir (0-100, None=pas de filtre)")
    min_volume_ratio: Optional[float] = Field(default=None, description="Ratio volume/SMA20 minimum pour ouvrir (None=pas de filtre)")
    # [v1.9.8] Filtre long quality — conditions supplémentaires pour les longs scalping.
    # Les longs médiocres qui finissent en stale négatif sont le problème principal.
    long_quality_filter: bool = Field(default=False, description="Active le filtre de qualité pour les longs scalping")
    # [v2.0.0] Economic viability gate — refuse les trades dont la capture attendue
    # ne couvre pas les frais. C'est le garde-fou fondamental du pivot stratégique :
    # plus aucun trade de poussière qui semble gagnant en brut mais perd en net.
    economic_gate_enabled: bool = Field(default=False, description="Active le gate de viabilité économique pré-entrée")
    min_ev_multiple: float = Field(default=2.0, description="Multiplicateur minimum : capture attendue ≥ N × coût RT")
    # [v2.0.0] Capture attendue estimée en % — basée sur le trailing stop
    # et la structure de marché, pas sur le TP théorique (qui n'est jamais atteint).
    expected_capture_pct: Optional[float] = Field(default=None, description="Capture réaliste attendue en % (None=trailing_stop_activation_pct)")
    # [v2.0.0] Momentum fade mode — contrôle du principal destructeur de valeur.
    # "enabled" = comportement actuel (défaut pour les anciens profils)
    # "restricted" = ne se déclenche que si le pic dépasse un seuil d'amplitude minimum
    # "disabled" = momentum fade complètement désactivé
    momentum_fade_mode: str = Field(default="enabled", description="Mode momentum fade: enabled/restricted/disabled")
    # [v2.0.0] Amplitude minimum du pic pour déclencher momentum fade en mode restricted.
    # Ex: 0.30 = le pic doit valoir au moins 0.30% ($7.50 sur $2500) pour que le
    # momentum fade soit autorisé. Sinon on laisse le trailing stop gérer.
    momentum_fade_min_amplitude_pct: Optional[float] = Field(default=None, description="Amplitude % minimum du pic pour momentum fade restricted")
    # [v2.0.0] Nombre minimum de preuves structurelles pour ouvrir en scalping.
    # Les preuves sont : price_position favorable, volume confirmé, micro-trend,
    # breakout récent. Sans preuve, pas d'entrée.
    min_structural_proofs: int = Field(default=0, description="Nombre minimum de signaux structurels pour ouvrir (0=désactivé)")
    # [v2.0.3] Gate micro-tendance obligatoire pour les longs scalping.
    # L'audit runtime montre 91% de closed_stale = entrées sur bruit sans tendance.
    # Exiger micro_trend_score ≥ N pour ouvrir un long filtre le bruit directionnel.
    # None = pas de filtre. 2 = tendance légère minimum. 3 = tendance claire.
    min_micro_trend_long: Optional[int] = Field(default=None, description="micro_trend_score minimum pour ouvrir un long (None=pas de filtre)")


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

