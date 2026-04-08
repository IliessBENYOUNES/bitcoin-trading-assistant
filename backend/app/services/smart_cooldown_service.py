"""
SmartCooldownService — Cooldown intelligent et contextuel.

Au lieu d'un cooldown fixe (ex: 2 min), ce service calcule un cooldown
dynamique basé sur le contexte du dernier trade :

- Trade coupé très vite (stale, trailing flat) → cooldown réduit
- Grosse perte → cooldown allongé
- Signal haute qualité → cooldown réduit
- Haute volatilité → cooldown allongé

Le cooldown est toujours borné entre [min_cooldown, max_cooldown].

v1.9.0 — Additif. Désactivable via smart_cooldown_enabled=False.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Bornes de sécurité absolues (ne peuvent jamais être dépassées)
ABSOLUTE_MIN_COOLDOWN = 0.5   # 30 secondes minimum
ABSOLUTE_MAX_COOLDOWN = 30.0  # 30 minutes maximum


class SmartCooldownService:
    """
    Calcule un cooldown dynamique basé sur le contexte.

    Usage :
        cooldown = SmartCooldownService.compute_cooldown(
            base_cooldown=2,
            last_exit_type="closed_trailing_stop",
            last_pnl=-0.5,
            last_duration_min=3.0,
            signal_score=45,
        )
    """

    # Multiplicateurs par type de sortie
    EXIT_MULTIPLIERS = {
        # Sorties rapides/flat → cooldown réduit (le slot est libre, on réessaie vite)
        "closed_stale": 0.5,
        "closed_trailing_stop": 0.7,
        "closed_momentum_fade": 0.6,
        # Sorties normales → cooldown standard
        "closed_signal": 1.0,
        "closed_tp": 0.8,    # TP touché = bon trade, on peut réentrer vite
        "closed_expired": 1.0,
        "closed_manual": 1.0,
        # SL touché = prudence
        "closed_sl": 1.5,
    }

    @classmethod
    def compute_cooldown(
        cls,
        base_cooldown: float,
        last_exit_type: Optional[str] = None,
        last_pnl: Optional[float] = None,
        last_pnl_pct: Optional[float] = None,
        last_duration_min: Optional[float] = None,
        signal_score: Optional[float] = None,
        min_cooldown: float = 0.5,
        max_cooldown: float = 10.0,
    ) -> float:
        """
        Calcule le cooldown dynamique en minutes.

        Args:
            base_cooldown: Cooldown de base configuré dans le profil (minutes)
            last_exit_type: Type de sortie du dernier trade
            last_pnl: PnL brut du dernier trade en USD
            last_pnl_pct: PnL % du dernier trade
            last_duration_min: Durée du dernier trade en minutes
            signal_score: Score absolu du signal actuel (optionnel)
            min_cooldown: Borne minimale (minutes)
            max_cooldown: Borne maximale (minutes)

        Returns:
            Cooldown en minutes (float), borné entre min et max.
        """
        multiplier = 1.0

        # 1. Multiplicateur par type de sortie
        if last_exit_type:
            exit_mult = cls.EXIT_MULTIPLIERS.get(last_exit_type, 1.0)
            multiplier *= exit_mult

        # 2. Ajustement par PnL du dernier trade
        if last_pnl is not None:
            if last_pnl >= 0:
                # Trade gagnant → on peut réentrer plus vite
                multiplier *= 0.8
            else:
                # Trade perdant → prudence proportionnelle à la perte
                if last_pnl_pct is not None and last_pnl_pct < -0.2:
                    # Grosse perte (> 0.2%) → cooldown allongé
                    multiplier *= 1.5
                elif last_pnl_pct is not None and last_pnl_pct < -0.1:
                    # Perte modérée → légère prudence
                    multiplier *= 1.2

        # 3. Trade très court et flat → signal de bruit, ALLONGER le cooldown
        # [v1.9.1] Changement de philosophie : un trade très court et flat est du BRUIT.
        # Il ne faut PAS réentrer vite après du bruit — c'est du churn.
        # Avant : multiplier *= 0.5 (réentrait très vite = plus de churn)
        # Maintenant : multiplier *= 1.5 (attend plus longtemps pour un vrai signal)
        if last_duration_min is not None and last_duration_min < 2.0:
            if last_pnl_pct is not None and abs(last_pnl_pct) < 0.05:
                # Scratch : trade < 2min et PnL quasi nul → c'est du bruit
                multiplier *= 1.5

        # 4. Signal fort actuel → cooldown réduit si setup qualitativement bon
        if signal_score is not None and abs(signal_score) > 50:
            multiplier *= 0.7

        # Calcul final
        computed = base_cooldown * multiplier

        # Borner entre min et max configurés
        computed = max(min_cooldown, min(max_cooldown, computed))
        # Bornes de sécurité absolues
        computed = max(ABSOLUTE_MIN_COOLDOWN, min(ABSOLUTE_MAX_COOLDOWN, computed))

        return round(computed, 1)

    @classmethod
    def explain_cooldown(
        cls,
        base_cooldown: float,
        computed_cooldown: float,
        last_exit_type: Optional[str] = None,
        last_pnl: Optional[float] = None,
    ) -> str:
        """
        Génère une explication textuelle du cooldown calculé.

        Returns:
            Explication lisible (ex: "Cooldown réduit de 2.0→1.0 min car trailing flat")
        """
        if abs(computed_cooldown - base_cooldown) < 0.1:
            return f"Cooldown standard : {computed_cooldown:.1f} min"

        direction = "réduit" if computed_cooldown < base_cooldown else "allongé"
        reasons = []

        if last_exit_type:
            mult = cls.EXIT_MULTIPLIERS.get(last_exit_type, 1.0)
            if mult < 1.0:
                reasons.append(f"sortie rapide ({last_exit_type})")
            elif mult > 1.0:
                reasons.append(f"sortie risquée ({last_exit_type})")

        if last_pnl is not None:
            if last_pnl >= 0:
                reasons.append("trade gagnant")
            else:
                reasons.append(f"perte {last_pnl:.2f} USD")

        reason_str = ", ".join(reasons) if reasons else "contexte"
        return (
            f"Cooldown {direction} de {base_cooldown:.1f}→{computed_cooldown:.1f} min "
            f"car {reason_str}"
        )

