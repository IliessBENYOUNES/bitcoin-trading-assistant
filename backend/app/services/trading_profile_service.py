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

    # Valeurs acceptées pour set_profile (les 3 presets + auto)
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
        """Change le profil de trading actif (conservative, balanced, aggressive, auto)."""
        if profile_type not in self.VALID_PROFILES:
            raise ValueError(f"Profil inconnu : {profile_type}. Valides : {self.VALID_PROFILES}")

        account = self.db.query(PaperAccount).first()
        if account is None:
            # Créer un compte par défaut si absent
            account = PaperAccount(active_profile=profile_type)
            self.db.add(account)
        else:
            account.active_profile = profile_type
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
        - Sinon → conservative (prudence par défaut)

        Args:
            score: Score composite du moteur de décision (valeur absolue utilisée)
            confidence: Niveau de confiance ("low", "medium", "high")

        Returns:
            Nom du profil résolu ("conservative", "balanced" ou "aggressive")
        """
        abs_score = abs(score)
        confidence_level = {"low": 0, "medium": 1, "high": 2}.get(confidence, 0)

        # Opportunité forte → agressif
        if abs_score >= 50 and confidence_level >= 2:
            return "aggressive"

        # Opportunité correcte → équilibré
        if abs_score >= 30 and confidence_level >= 1:
            return "balanced"

        # Par défaut → conservateur
        return "conservative"

    @staticmethod
    def get_all_presets() -> list[TradingProfileParams]:
        """Retourne tous les presets disponibles."""
        return list(PROFILE_PRESETS.values())

