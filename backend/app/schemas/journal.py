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
    cooldown_minutes: float = Field(description="Minutes de cooldown entre deux trades")
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
    # [v2.0.9] Trailing stop RELATIF — protège les gains proportionnellement au pic.
    # Au lieu de couper sur un recul ABSOLU (0.06% = identique que le pic soit 0.10% ou 0.50%),
    # on coupe quand le gain a reculé de X% PAR RAPPORT À SA VALEUR AU PIC.
    # Ex: trailing_stop_drop_ratio=0.30 → on sort quand le gain descend sous 70% du pic.
    # Peak=0.12% → exit sous 0.084%. Peak=0.50% → exit sous 0.35%.
    # Si activé (not None), REMPLACE le trailing_stop_pct absolu.
    trailing_stop_drop_ratio: Optional[float] = Field(
        default=None,
        description="Ratio de recul relatif au pic (0.30 = sortie quand gain < 70% du pic). Remplace trailing_stop_pct si défini."
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
    # [v2.0.12] GAIN EROSION STOP — Protection des gains dès le premier dollar.
    # Si le gain a existé (peak > 0) et qu'il s'érode de plus de X% du pic → sortie immédiate.
    # Priorité AVANT le breakeven et le stale exit. Comble le trou entre trailing (qui exige
    # un seuil d'activation) et breakeven (qui attend PnL ≤ 0 pour fermer).
    # Ex: gain_erosion_ratio=0.30 → sort quand le gain tombe sous 70% du pic.
    # Peak +$1.00 → exit si gain < $0.70 (érosion > 30%).
    # None = désactivé (profils classiques).
    gain_erosion_ratio: Optional[float] = Field(default=None, description="Ratio d'érosion max du gain avant sortie (0.30 = sort si gain < 70% du pic). None=désactivé.")
    # [v2.0.13] TICK MOMENTUM CONFIRMATION — Gate d'entrée par micro price-action.
    # Au lieu d'un cooldown fixe aveugle, on analyse les derniers ticks (~10 sec)
    # pour confirmer que le prix va dans la direction du trade AVANT d'ouvrir.
    # SHORT → prix doit être en baisse. LONG → prix doit être en hausse.
    # Si le momentum ne confirme pas → pas d'entrée (on attend le prochain tick).
    # Élimine les shorts qui entrent à contre-courant et restent négatifs 2 min.
    tick_momentum_enabled: bool = Field(default=False, description="Activer la confirmation de direction par tick momentum avant entrée")
    tick_momentum_window_seconds: float = Field(default=30.0, description="Fenêtre d'analyse des ticks en secondes (défaut: 30)")
    tick_momentum_min_ticks: int = Field(default=3, description="Nombre minimum de ticks requis dans la fenêtre pour décider")
    # [v2.0.14] CANDLE DIRECTION OVERRIDE — Le tick momentum DÉTERMINE la direction du trade.
    # Au lieu de suivre le score technique (lagging 15 min), on utilise la direction réelle
    # du prix sur les dernières ~30 secondes :
    # - Prix monte → LONG (même si le score dit "vendre")
    # - Prix descend → SHORT (même si le score dit "acheter")
    # - Prix flat → pas de trade (attendre)
    # Élimine le biais 100% short quand les indicateurs restent bearish en marché ranging.
    tick_momentum_override_direction: bool = Field(default=False, description="Utiliser la direction tick momentum comme signal primaire (True=la bougie décide, pas le score)")
    # [v2.0.14] Score minimum réduit quand l'override est actif.
    # Normalement min_score=30, mais avec l'override on n'utilise le score que comme
    # filtre de qualité (le marché est-il actif ?). Un seuil plus bas permet de ne pas
    # rater les opportunités quand le score est modéré mais le prix bouge clairement.
    tick_momentum_min_score: int = Field(default=10, description="Score minimum quand tick momentum override est actif (remplace min_score)")
    # [v2.0.18] CANDLE REVERSAL EXIT — Sortie active quand la couleur de bougie change.
    # Si le prix changeait de direction (ex: bougie verte → rouge) pendant une position,
    # on sort immédiatement au lieu d'attendre le SL/trailing/stale.
    # Basé sur l'observation que les trades profitables gardent la même couleur de pastille
    # à l'entrée et à la sortie (même momentum), tandis que les perdants changent de couleur.
    candle_reversal_exit_enabled: bool = Field(default=False, description="Sortie active quand la couleur de bougie s'inverse par rapport à l'entrée")
    # Nombre minimum de secondes de reversal avant de déclencher la sortie.
    # Évite les sorties sur bruit : le prix doit avoir changé de direction depuis
    # au moins N secondes avant qu'on coupe.
    candle_reversal_min_seconds: float = Field(default=3.0, description="Durée min (sec) de reversal avant exit (évite le bruit)")
    # Fenêtre d'analyse pour détecter le reversal (en secondes).
    candle_reversal_window_seconds: float = Field(default=15.0, description="Fenêtre d'analyse tick momentum pour détecter le reversal")
    # [v2.0.22] SAS D'ENTRÉE SÉCURISÉ — Validation pré-entrée par observation.
    # Quand tous les gates passent, au lieu d'ouvrir immédiatement, le système
    # crée une entrée VIRTUELLE et observe le PnL pendant quelques secondes.
    # Si le PnL virtuel reste négatif → l'entrée est annulée (jamais de trade perdant dès le départ).
    # Si le PnL virtuel devient positif et le reste → l'entrée réelle est confirmée.
    # Corrige le problème des entrées destructrices sur changement de bougie :
    # ex. trade #620 qui perd $15.27 en 36 secondes.
    entry_sas_enabled: bool = Field(default=False, description="Active le SAS d'entrée sécurisé (observation avant ouverture)")
    # Durée maximale du SAS en secondes. Si le PnL n'est pas confirmé positif avant ce délai,
    # l'entrée est annulée (timeout). Doit être > entry_sas_min_positive_seconds.
    entry_sas_duration_seconds: float = Field(default=15.0, description="Durée max du SAS en secondes avant annulation (timeout)")
    # Durée minimale de PnL positif continu avant confirmation de l'entrée.
    # Le prix doit aller dans notre direction pendant au moins N secondes consécutives.
    entry_sas_min_positive_seconds: float = Field(default=10.0, description="Durée min de PnL positif avant confirmation de l'entrée réelle")
    # Prudence renforcée aux extrémités de range : si le prix est en haut de range (>70%)
    # et qu'on veut un LONG, ou en bas de range (<30%) et qu'on veut un SHORT,
    # le SAS est plus exigeant (annulation immédiate si PnL négatif sur un seul tick).
    entry_sas_range_caution: bool = Field(default=True, description="Prudence renforcée aux extrémités de range (haut→pas de long, bas→pas de short)")
    # [v2.0.23] MICRO STOP LOSS — Sortie immédiate dès que le PnL latent dépasse
    # un seuil négatif ultra-serré. Contrairement au loss_cut_pct (0.20%, vérifié
    # avec le score), le micro stop loss ferme IMMÉDIATEMENT, sans condition.
    # Ex: 0.01 = on sort dès que le PnL < -0.01% (= -$0.25 sur $2500).
    # Philosophie : on préfère perdre $0.25 que risquer -$21 sur un retournement.
    # None = désactivé (profils classiques qui utilisent le SL normal).
    micro_stop_loss_pct: Optional[float] = Field(default=None, description="% PnL négatif max avant sortie immédiate (ex: 0.01 = -0.01%). None=désactivé.")
    # [v2.0.26] TREND ALIGNMENT FILTER — Bloque les SHORTs via tick_override quand
    # le score technique est fortement bullish (marché en hausse).
    # L'analyse de 92 trades (v2.0.25) montre que les shorts scalping perdent -$8.93
    # (47% WR) quand le score est à +64/+65 (bullish) car le marché monte globalement.
    # Le tick_override ouvre un short quand la bougie 30s est rouge, mais le score dit
    # "acheter" → le short est fermé 36-72s plus tard par "signal contraire" en perte.
    # Ce seuil bloque les shorts override quand score > threshold. Ex: 50 = si le score
    # technique est > +50 (nettement bullish), pas de short. None = filtre désactivé.
    # Ne bloque PAS les shorts non-override (mean_reversion) ni les LONGs.
    trend_alignment_score_threshold: Optional[float] = Field(default=None, description="Score au-dessus duquel les SHORTs tick_override sont bloqués. None=désactivé.")


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

