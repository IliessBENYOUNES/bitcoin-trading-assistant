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
    "aggressive": TradingProfileParams(
        profile_type=TradingProfileType.aggressive,
        label="Aggressive",
        description="Plus de trades, seuils permissifs. Borné par risk engine. Comparaison uniquement.",
        min_score=10,
        min_confidence="low",
        min_scenario_dominance=0.38,
        max_trades_per_day=15,
        cooldown_minutes=15,
        max_position_duration_hours=48,
        profit_take_pct=1.0,
        loss_cut_pct=1.0,
        loss_cut_score_threshold=10,
        leverage_enabled=True,
        max_leverage=3.0,
        stale_exit_minutes=180,
    ),
    "scalping": TradingProfileParams(
        profile_type=TradingProfileType.scalping,
        label="Scalping",
        description="Haute fréquence intraday — petits mouvements, sorties rapides, réentrée contextuelle.",
        min_score=20,   # [v1.9.5] 15→20 : relève le plancher de qualité, filtre les longs médiocres
        min_confidence="low",
        min_scenario_dominance=0.35,
        max_trades_per_day=50,
        cooldown_minutes=2,           # base cooldown, overridden par smart cooldown
        max_position_duration_hours=2,
        # [v1.9.5] TP élargi de 0.5%→0.6% et SL resserré de 0.35%→0.25%.
        # Le R:R effectif était de ~0.3:1 (gains $1-4 via trailing/momentum vs pertes $8.75 via SL).
        # Nouveau R:R théorique : 0.6/0.25 = 2.4:1.
        # Nouveau R:R effectif estimé : ≈1:1 (gains trailing ~$3-5 vs pertes SL ~$6.25).
        # L'objectif est de RÉDUIRE les grosses pertes, pas d'augmenter les gains.
        profit_take_pct=0.6,
        loss_cut_pct=0.25,
        loss_cut_score_threshold=5,
        leverage_enabled=True,
        max_leverage=1.5,
        # Analyse sur timeframe court (15m au lieu de 4h)
        analysis_timeframe="15m",
        # [v1.9.5] Seuils de décision relevés : 20→25 buy, 15→20 sell.
        # Le moteur ouvrait trop de longs médiocres (score 71 systématique).
        # Des seuils plus hauts empêchent les longs faibles qui finissent en stale/SL.
        buy_threshold=25,
        sell_threshold=20,
        # [v1.9.5] Sorties rapides — stale 15 min pour positions plates,
        # MAIS positions en perte sortent plus vite (stale_negative_exit_minutes=8).
        momentum_fade_enabled=True,
        stale_exit_minutes=15,
        stale_negative_exit_minutes=8,  # [v1.9.5] positions en perte → sortie plus rapide
        # [v1.9.5] Trailing stop recalibré pour éviter les activations sur micro-peaks.
        # Activation relevée de 0.08→0.15% : ne s'active que quand le trade a un vrai gain.
        # Trailing resserré de 0.12→0.10% : une fois activé, protège mieux les gains.
        # Avant : activait à 0.08% → trade #208 a eu un peak de 0.093% → trailing activé →
        # position retourne à -0.042% → perte. Avec 0.15%, ce trade n'aurait pas activé.
        trailing_stop_activation_pct=0.15,
        trailing_stop_pct=0.10,
        # [v1.9.5] Momentum fade moins agressif : rétention 55% au lieu de 40%.
        # Avant : sortait quand le PnL tombait sous 40% du pic (perdu 60% des gains).
        # Maintenant : sort quand le PnL tombe sous 55% du pic (perdu 45% des gains).
        # Cela laisse les trades qui oscillent continuer plutôt que prendre $1.
        momentum_fade_retention=0.55,
        # Smart cooldown
        smart_cooldown_enabled=True,
        min_cooldown_minutes=0.5,
        max_cooldown_minutes=5.0,
        # [v1.9.1] Protection anti-micro-PnL
        min_hold_seconds=30,
        # Seuil économique
        min_economic_pnl_pct=0.15,
        # [v1.9.5] Short rebalancé — la v1.9.4 avait sur-corrigé :
        # short_min_score=40 + 2-convergence = quasi aucun short en marché haussier.
        # Résultat = 100% longs, une seule direction = pas de diversification.
        # La règle des 2 oscillateurs convergents (v1.9.4) est suffisante comme filtre.
        # Le score minimum n'a pas besoin d'être aussi haut en complément.
        short_min_score=30,           # [v1.9.5] 40→30 (2-convergence suffit comme filtre)
        # [v1.9.5] Seuil de signal contraire short rebalancé : 35→25.
        # 35 était trop haut (en haussier, score >35 est quasi-permanent → shorts
        # ne pouvaient jamais se fermer sur signal). 25 est un compromis :
        # pas aussi bas que l'ancien 10 (qui tuait les shorts), pas aussi haut que 35.
        short_exit_score_threshold=25, # [v1.9.5] 35→25 (compromis entre 10 et 35)
        # [v1.9.5] Min hold short réduit de 90→60s.
        # 90s empêchait les shorts de capter les courts pullbacks.
        short_min_hold_seconds=60,     # [v1.9.5] 90→60 (pullbacks rapides à capter)
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

