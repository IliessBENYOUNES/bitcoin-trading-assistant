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
    # [v2.0.24] Rebalancé : le SAS (v2.0.22) et le micro SL (v2.0.23) protègent
    # contre le churn et les pertes. Le cooldown n'a plus besoin d'être punitif.
    # Multiplicateurs réduits globalement pour favoriser la réactivité.
    EXIT_MULTIPLIERS = {
        # Sorties stale → cooldown légèrement allongé (était 2.0, réduit à 1.3)
        # Le SAS empêchera la réentrée si le marché est défavorable
        "closed_stale": 1.3,
        "closed_trailing_stop": 0.5,
        "closed_momentum_fade": 0.5,
        # Sorties normales → cooldown standard
        "closed_signal": 0.8,
        "closed_tp": 0.5,    # TP touché = bon trade, réentrer rapidement
        "closed_expired": 1.0,
        "closed_manual": 1.0,
        # SL touché = un peu de prudence, mais le SAS protège
        "closed_sl": 1.2,
        # [v2.0.23] Micro SL = sortie ultra-rapide, la position était à peine
        # ouverte → réentrer vite, le SAS filtrera si le marché est mauvais
        "closed_micro_sl": 0.7,
        # Breakeven, gain erosion = pas de perte → réentrer vite
        "closed_breakeven": 0.6,
        "closed_gain_erosion": 0.6,
        # Candle reversal = momentum changé mais pas catastrophique
        "closed_candle_reversal": 0.8,
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

        # [v2.0.24] Pénalité stale négatif réduite : le SAS filtre en amont.
        # Multiplicateur réduit de 3.0→1.5. Le SAS empêchera la réentrée sur un
        # marché défavorable, donc pas besoin de bloquer longtemps par le cooldown.
        stale_negative = (
            last_exit_type == "closed_stale"
            and last_pnl is not None
            and last_pnl < 0
        )
        if stale_negative:
            multiplier = multiplier / cls.EXIT_MULTIPLIERS.get("closed_stale", 1.0) * 1.5

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
        # [v1.9.9] Ne s'applique PAS si déjà un stale (pénalité stale est plus forte).
        if (last_duration_min is not None and last_duration_min < 2.0
                and last_exit_type != "closed_stale"):
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

        # [v2.0.24] Plancher stale négatif réduit de 2.0→0.5 min (30 sec).
        # Le SAS (15s d'observation virtuelle) protège contre la réentrée immédiate
        # dans un marché défavorable. Cooldown 30s + SAS 15s = 45s de protection totale.
        STALE_NEGATIVE_FLOOR = 0.5
        if stale_negative:
            computed = max(STALE_NEGATIVE_FLOOR, computed)

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

