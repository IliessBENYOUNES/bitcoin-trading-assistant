"""
Service de gestion des profils de trading.

Fournit 3 profils prédéfinis (Conservative, Balanced, Aggressive)
qui pilotent les seuils d'entrée, la fréquence, le levier et les sorties.

Conservative = baseline existante (aucun changement de comportement).
Balanced = compromis fréquence / qualité.
Aggressive = plus de trades, toujours borné par le risk engine.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_account import PaperAccount
from app.schemas.journal import (
    TradingProfileType,
    TradingProfileParams,
    TradingProfileResponse,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Presets — Paramètres hard-coded par profil
# Les valeurs Conservative reproduisent le comportement existant (baseline).
# ─────────────────────────────────────────────────────────────────────────────

PROFILE_PRESETS: dict[str, TradingProfileParams] = {
    "conservative": TradingProfileParams(
        profile_type=TradingProfileType.conservative,
        label="Conservative",
        description="Très sélectif — qualité prioritaire. Baseline de référence.",
        min_score=35,
        min_confidence="medium",
        min_scenario_dominance=0.50,
        max_trades_per_day=3,
        cooldown_minutes=120,
        max_position_duration_hours=168,
        profit_take_pct=2.0,
        loss_cut_pct=1.5,
        loss_cut_score_threshold=30,
        leverage_enabled=False,
        max_leverage=1.0,
    ),
    "balanced": TradingProfileParams(
        profile_type=TradingProfileType.balanced,
        label="Balanced",
        description="Compromis fréquence / qualité — seuils plus souples.",
        min_score=20,
        min_confidence="low",
        min_scenario_dominance=0.42,
        max_trades_per_day=8,
        cooldown_minutes=45,
        max_position_duration_hours=72,
        profit_take_pct=1.5,
        loss_cut_pct=1.2,
        loss_cut_score_threshold=20,
        leverage_enabled=True,
        max_leverage=2.0,
    ),
    # [v2.0.29] REFONTE AGGRESSIVE — Gate économique + paramètres ajustés pour frais.
    # AUDIT 17/04/2026 :
    # - 30 trades aggressive en 4 jours, gross +$31.58, mais frais simulés $333 → net -$302
    # - EXP : 44 trades aggressive, 22 gross+ mais ALL net- sauf 2
    # - Les 2 seuls trades net+ avaient mouvement > 0.36% et durée > 4 min
    # CONCLUSION : l'aggressive doit être plus sélectif et le gate économique obligatoire.
    "aggressive": TradingProfileParams(
        profile_type=TradingProfileType.aggressive,
        label="Aggressive",
        description="Swing intraday v2.0.29 — gate économique, pas de levier, seuils relevés.",
        # [v2.0.29] Score minimum relevé 10→20 : l'audit montre que les scores 10-20
        # ne prédisent rien sur le 1h. Les scores 30-50 sont les plus rentables dans le main.
        min_score=20,
        min_confidence="low",
        min_scenario_dominance=0.42,
        max_trades_per_day=10,
        # [v2.0.29] Cooldown 5→15 min : réduire la fréquence, laisser le signal 1h évoluer
        cooldown_minutes=15,
        max_position_duration_hours=48,
        # [v2.0.29] TP maintenu à 1.0% : les swings 1h atteignent 1% en quelques heures
        profit_take_pct=1.0,
        loss_cut_pct=1.0,
        loss_cut_score_threshold=10,
        # [v2.0.29] Levier réduit x3→x1 : le levier amplifie les frais.
        # Le trade EXP #83 (x3) : gross +$6.11, frais $23.25, net -$17.14.
        # Le trade EXP #99 (x1.5) : gross +$17.27, frais $11.63, net +$5.65.
        # Seul x1 garantit que les frais restent à $7.75.
        leverage_enabled=False,
        max_leverage=1.0,
        analysis_timeframe="1h",
        buy_threshold=20,
        sell_threshold=15,
        stale_exit_minutes=180,
        stale_negative_exit_minutes=60,
        # [v2.0.29] Trailing activation 0.25→0.50% : ne protéger que les gains
        # qui couvrent largement les frais. 0.50% = $12.50 brut > $7.75 frais.
        trailing_stop_activation_pct=0.50,
        trailing_stop_drop_ratio=0.20,
        # [v2.0.29] Gain erosion DÉSACTIVÉ : sortait sur des peaks de 0.02-0.03%
        # = $0.40 brut = $-7.35 net. Catastrophique avec les frais.
        gain_erosion_ratio=None,
        min_market_quality=25,
        # [v2.0.30] Volume ratio relevé 0.5→0.8 — aligné avec scalping. L'audit montre que
        # le volume faible (< SMA20) est systématiquement un signal de futur chop.
        min_volume_ratio=0.8,
        # [v2.0.29] Gate économique ACTIVÉ : obligatoire maintenant que les frais
        # sont intégrés. Chaque trade doit pouvoir couvrir 2× les frais.
        economic_gate_enabled=True,
        expected_capture_pct=0.80,
        min_ev_multiple=2.0,
        momentum_fade_mode="enabled",
        entry_sas_enabled=True,
        entry_sas_duration_seconds=10.0,
        entry_sas_min_positive_seconds=5.0,
        entry_sas_range_caution=True,
        # [v2.0.29] Micro SL élargi 0.15→0.30% : les swings 1h ont besoin de
        # respiration. 0.30% = $7.50 + frais $7.75 = max $15.25 par trade raté.
        micro_stop_loss_pct=0.30,
        smart_cooldown_enabled=True,
        min_cooldown_minutes=5.0,
        max_cooldown_minutes=15.0,
        # [v2.0.30] MAX SCORE CAP — audit r=-0.134 significatif. Les scores >50 sur les
        # swings 1h aggressive arrivent trop tard (signal déjà digéré). Cap à 55 pour
        # laisser une marge d'écart de mesure tout en éliminant le cluster destructeur.
        max_score=55,
        # [v2.0.30] Blocked hours UTC — US open + macro. Audit MAIN: -$104 cum sur 14-16h.
        blocked_hours_utc=[13, 14, 15, 16],
        # [v2.0.30] Breakeven peak min = 2× frais = 0.62%.
        breakeven_min_peak_fee_multiple=2.0,
        # [v2.0.30] Min range/ATR — rejette les chop ranges où 0.62% est inatteignable.
        min_range_atr=1.5,
        # [v2.0.31] OPPOSITE SIGNAL EXIT DÉSACTIVÉ — Audit 23/04/2026 (run du 18/04, 51 trades MAIN) :
        # 50/51 trades fermés via "Signal contraire" → +$0.04 brut → -$7.71 net systématique.
        # WR brut 67% → WR net 0%. Cette règle est le principal destructeur de valeur en mode auto.
        # SL/TP/trailing/stale gèrent les sorties ; le score n'a plus le droit de fermer.
        opposite_signal_exit_enabled=False,
        # [v2.0.31] min_hold_seconds=300 explicite : protège contre la re-résolution du profil
        # en mode auto qui pouvait précédemment basculer sur des params sans min_hold.
        min_hold_seconds=300,
        short_min_hold_seconds=300,
    ),
    # [v2.0.29] REFONTE COMPLETE — Scalping transformé en "swing court".
    # AUDIT 17/04/2026 :
    # - 797 trades scalping en 4 jours, durée moyenne 82s, PnL brut -$101
    # - Avec frais simulés (0.31% RT) : PnL net -$5,839 (catastrophe)
    # - 98.8% des trades ont un mouvement < 0.31% (bruit)
    # - Les trades > 5 min sont SEULS rentables (+$63 brut)
    # CONCLUSION : le micro-scalping sub-minute est non-viable avec frais.
    # Le slot scalping devient un "swing court" (5-30 min, mouvements > 0.5%).
    "scalping": TradingProfileParams(
        profile_type=TradingProfileType.scalping,
        label="Scalping",
        description="Swing court v2.0.29 — trades 5-30 min, mouvements > 0.5%, frais intégrés.",
        # [v2.0.29] Score relevé 30→40 : filtrer les signaux faibles
        min_score=40,
        min_confidence="low",
        min_scenario_dominance=0.40,
        max_trades_per_day=50,
        # [v2.0.29] Cooldown 0.5→5 min : réduire la fréquence de 200 à ~20 trades/jour
        cooldown_minutes=5,
        max_position_duration_hours=2,
        # [v2.0.29] TP élargi 0.8→1.5% : couvrir les frais (0.31%) avec marge
        profit_take_pct=1.5,
        # [v2.0.29] SL élargi 0.20→0.50% : laisser le trade respirer
        # Avec frais : perte max par trade = 0.50% + 0.31% = 0.81% = $20.25 sur $2500
        loss_cut_pct=0.50,
        loss_cut_score_threshold=10,
        # [v2.0.29] Levier désactivé : le levier amplifie les frais sans amplifier
        # les gains sur des mouvements de 0.3-1.0%. Le trade EXP #83 illustre :
        # gross +$6.11 à x3, frais $23.25, net -$17.14.
        leverage_enabled=False,
        max_leverage=1.0,
        analysis_timeframe="15m",
        # [v2.0.29] Seuils d'achat/vente relevés
        buy_threshold=40,
        sell_threshold=30,
        # [v2.0.29] Momentum fade DÉSACTIVÉ : destructeur de valeur identifié.
        # Sort à +$1.59 avg quand le coût RT est $7.75 → perte nette systématique.
        momentum_fade_enabled=False,
        # [v2.0.29] Stale exit allongé 5→30 min : laisser les trades se développer
        # L'audit montre que les trades rentables durent 5-30 min.
        stale_exit_minutes=30,
        # [v2.0.29] Stale négatif allongé 2→10 min : plus de patience
        stale_negative_exit_minutes=10,
        # [v2.0.29] Trailing activation 0.04→0.40% : ne protéger que les gains
        # qui couvrent les frais. 0.40% = $10 brut > $7.75 frais = net positif.
        trailing_stop_activation_pct=0.40,
        trailing_stop_pct=0.20,
        # [v2.0.29] Drop ratio 0.15→0.25 : garder 75% du gain
        trailing_stop_drop_ratio=0.25,
        # [v2.0.29] Gain erosion DÉSACTIVÉ : empêche les trades de se développer.
        # L'érosion sortait à +$0.12-$0.50, net négatif après frais.
        gain_erosion_ratio=None,
        # [v2.0.29] Tick momentum : GARDER la détection mais DÉSACTIVER l'override direction.
        # Le score technique décide la direction, le tick momentum filtre la qualité.
        tick_momentum_enabled=True,
        tick_momentum_window_seconds=30.0,
        tick_momentum_min_ticks=3,
        tick_momentum_override_direction=False,  # [v2.0.29] Le SCORE décide, pas le tick
        tick_momentum_min_score=30,
        # [v2.0.29] Candle reversal DÉSACTIVÉ : sort sur des retournements de 1 tick
        # (5 secondes), créant du churn. Avec des trades de 5-30 min, les micro-reversals
        # sont du bruit qu'il faut ignorer.
        candle_reversal_exit_enabled=False,
        smart_cooldown_enabled=True,
        min_cooldown_minutes=2.0,
        max_cooldown_minutes=10.0,
        # [v2.0.29] Durée minimum 30→300 sec (5 min) : les trades < 5 min perdent
        min_hold_seconds=300,
        min_economic_pnl_pct=0.15,
        short_min_score=40,
        short_exit_score_threshold=40,
        short_min_hold_seconds=300,
        min_market_quality=50,
        min_volume_ratio=0.8,
        long_quality_filter=True,
        # [v2.0.29] Gate économique renforcé : 1.5→2.0x les frais
        economic_gate_enabled=True,
        min_ev_multiple=2.0,
        # [v2.0.29] Capture attendue 0.50→0.80% : alignée sur le TP réaliste
        expected_capture_pct=0.80,
        min_structural_proofs=2,
        min_micro_trend_long=0,
        # SAS d'entrée maintenu — protège contre les mauvaises entrées
        entry_sas_enabled=True,
        entry_sas_duration_seconds=15.0,
        entry_sas_min_positive_seconds=10.0,
        entry_sas_range_caution=True,
        # [v2.0.30] MICRO SL DÉSACTIVÉ — audit: 184 coupures à -$1.98 avg = -$364 cumulés
        # sur scalping MAIN. Le micro_sl à 0.20% coupe avant que le trade puisse se
        # développer. Le SL classique à 0.50% (=$12.50) reste actif et suffit comme filet.
        # Les trades doivent avoir le droit de respirer pour atteindre le TP 1.5%.
        micro_stop_loss_pct=None,
        trend_alignment_score_threshold=50,
        # [v2.0.30] MAX SCORE CAP — audit: bande score 60-80 représente 85% des trades MAIN
        # et a WR 48% (aléatoire). Bande 20-50 a WR 55-65%. Cap à 50 pour canaliser les
        # entrées vers la zone à edge statistique avéré.
        max_score=50,
        # [v2.0.30] Blocked hours UTC — fenêtre US open macro (NFP/CPI/FOMC).
        blocked_hours_utc=[13, 14, 15, 16],
        # [v2.0.30] Breakeven peak min = 2× frais = 0.62%. Empêche les breakevens sur peak
        # < 0.31% (identifiés comme 100% net-loss dans l'audit EXP : 18 trades, -$111 cum).
        breakeven_min_peak_fee_multiple=2.0,
        # [v2.0.30] Min range/ATR 1.5 — rejette les marchés compressés où aucun trade
        # scalping ne peut capturer > 0.62% (nécessaire pour couvrir 2× frais).
        min_range_atr=1.5,
        # [v2.0.31] OPPOSITE SIGNAL EXIT DÉSACTIVÉ — Audit 23/04/2026 (run scalping MAIN) :
        # tous les trades scalping étaient fermés via "Signal contraire" pour des trades
        # qui auraient autrement atteint le TP ou le breakeven structurel. Le score est
        # un signal d'OUVERTURE, pas un signal de fermeture sur des positions de 5-30 min.
        opposite_signal_exit_enabled=False,
    ),
}


class TradingProfileService:
    """
    Service de gestion des profils de trading.

    Usage :
        service = TradingProfileService(db)
        params = service.get_active_params()  # Retourne les seuils actifs
        service.set_profile("balanced")
    """

    def __init__(self, db: Session):
        self.db = db

    # Valeurs acceptées pour set_profile (les 4 presets + auto)
    VALID_PROFILES = list(PROFILE_PRESETS.keys()) + ["auto"]

    def get_active_profile(self) -> TradingProfileResponse:
        """Retourne le profil actif et ses paramètres.
        Quand le profil est "auto", retourne les params conservative comme placeholder.
        Les vrais paramètres sont résolus dynamiquement à chaque tick via auto_select_profile().
        """
        account = self.db.query(PaperAccount).first()
        profile_name = "conservative"
        if account and hasattr(account, "active_profile") and account.active_profile:
            profile_name = account.active_profile

        # En mode auto, on retourne les params conservative comme placeholder
        # Le vrai profil est résolu per-tick par auto_select_profile()
        if profile_name == "auto":
            return TradingProfileResponse(
                active_profile=TradingProfileType.auto,
                params=PROFILE_PRESETS["conservative"],
            )

        params = PROFILE_PRESETS.get(profile_name, PROFILE_PRESETS["conservative"])
        return TradingProfileResponse(
            active_profile=TradingProfileType(profile_name),
            params=params,
        )

    def get_active_params(self) -> TradingProfileParams:
        """Retourne directement les paramètres du profil actif."""
        return self.get_active_profile().params

    def is_auto_mode(self) -> bool:
        """Vérifie si le profil actif est en mode auto."""
        account = self.db.query(PaperAccount).first()
        if account and hasattr(account, "active_profile") and account.active_profile:
            return account.active_profile == "auto"
        return False

    def set_profile(self, profile_type: str) -> TradingProfileResponse:
        """
        Change le profil de trading actif.

        [v1.6.1] Si une position ouverte existe sous un profil DIFFÉRENT,
        elle est automatiquement fermée. Cela évite le goulot d'étranglement
        "position blocking" quand on passe de conservative (positions longues)
        à scalping (positions courtes).
        """
        if profile_type not in self.VALID_PROFILES:
            raise ValueError(f"Profil inconnu : {profile_type}. Valides : {self.VALID_PROFILES}")

        account = self.db.query(PaperAccount).first()
        old_profile = None
        if account is None:
            # Créer un compte par défaut si absent
            account = PaperAccount(active_profile=profile_type)
            self.db.add(account)
        else:
            old_profile = account.active_profile
            account.active_profile = profile_type

        # [v1.6.1] Fermer la position ouverte si le profil change
        # pour ne pas bloquer le nouveau profil avec une vieille position
        if old_profile and old_profile != profile_type and old_profile != "auto":
            from app.services.paper_trading_service import PaperTradingService
            pts = PaperTradingService(self.db)
            open_pos = pts.get_open_position()
            if open_pos is not None:
                reason = f"Changement de profil : {old_profile} → {profile_type}"
                pts.close_position_manual(reason)
                logger.info(f"🔄 Position fermée automatiquement : {reason}")

        self.db.commit()
        self.db.refresh(account)
        logger.info(f"Profil de trading changé → {profile_type}")
        return self.get_active_profile()

    @staticmethod
    def auto_select_profile(score: float, confidence: str) -> str:
        """
        Sélectionne automatiquement le profil optimal en fonction de la force du signal.

        Logique :
        - Score ≥ 50 ET confiance "high" → aggressive (opportunité forte)
        - Score ≥ 30 ET confiance ≥ "medium" → balanced (opportunité correcte)
        - Score ≥ 10 → scalping (opportunité modeste mais exploitable)
        - Sinon → conservative (prudence par défaut)

        Args:
            score: Score composite du moteur de décision (valeur absolue utilisée)
            confidence: Niveau de confiance ("low", "medium", "high")

        Returns:
            Nom du profil résolu ("conservative", "balanced", "aggressive" ou "scalping")
        """
        abs_score = abs(score)
        confidence_level = {"low": 0, "medium": 1, "high": 2}.get(confidence, 0)

        # Opportunité forte → agressif
        if abs_score >= 50 and confidence_level >= 2:
            return "aggressive"

        # Opportunité correcte → équilibré
        if abs_score >= 30 and confidence_level >= 1:
            return "balanced"

        # Opportunité modeste → scalping
        if abs_score >= 10:
            return "scalping"

        # Par défaut → conservateur
        return "conservative"

    @staticmethod
    def get_all_presets() -> list[TradingProfileParams]:
        """Retourne tous les presets disponibles."""
        return list(PROFILE_PRESETS.values())

