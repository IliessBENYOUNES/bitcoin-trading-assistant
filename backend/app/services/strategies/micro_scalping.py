"""
MicroScalpingStrategy — Micro-scalping basé sur les ticks.

Stratégie ultra-rapide basée sur le momentum tick-by-tick :
- Ne regarde pas les indicateurs techniques classiques
- Se base sur la direction des ticks récents (5-15 secondes)
- Entrée quand N ticks consécutifs dans la même direction
- Sortie très rapide (micro SL serré, trailing agressif)

Contextes actifs : range_mid (zone neutre = mouvement brownien tradeable)
"""

from app.services.market_context_engine import MarketContext
from app.services.strategies.base import BaseStrategy, StrategySignal, StrategyParams


class MicroScalpingStrategy(BaseStrategy):
    name = "micro_scalping"
    description = "Micro-scalping tick-based — momentum ultra-court"

    # Seuils spécifiques
    # [v2.1.0] MIN_MICRO_TREND 3→5 : sur 5m le micro_trend sature à ±10 ; à ≥3 c'est
    # du bruit brownien (le "random walk" identifié comme destructeur dans l'audit).
    # ≥5 = micro-mouvement directionnel réel, condition nécessaire pour viser 0.65%.
    MIN_MICRO_TREND = 5
    MAX_VOLATILITY_FOR_MICRO = "high"  # Pas de micro en haute volatilité

    def evaluate_entry(
        self,
        context: MarketContext,
        decision: dict,
        current_price: float,
        series: list[dict],
    ) -> StrategySignal:
        # Pas de micro-scalping en haute volatilité (trop risqué)
        if context.volatility == "high":
            return StrategySignal(strategy_type=self.name)

        # Le micro-scalping se base sur le micro-trend, pas le score global
        micro_trend = context.micro_trend_score

        if abs(micro_trend) < self.MIN_MICRO_TREND:
            return StrategySignal(strategy_type=self.name)

        direction = "long" if micro_trend > 0 else "short"

        # Bonus : volume au-dessus de la moyenne confirme le mouvement
        strength = min(100, abs(micro_trend) * 15)
        if context.volume_ratio >= 1.2:
            strength = min(100, strength + 15)

        return StrategySignal(
            should_enter=True,
            direction=direction,
            strength=strength,
            reason=f"micro_scalp_{direction} | micro_trend={micro_trend:+d} | "
                   f"vol_ratio={context.volume_ratio:.1f}",
            strategy_type=self.name,
        )

    def get_params(self, context: MarketContext, direction: str) -> StrategyParams:
        # Petites positions, sortie rapide mais pas trop serrée
        # $500 × 1.0x = frais RT $1.55 → il faut capturer > 0.31%
        # [v2.0.30] micro_sl désactivé (0.0) — audit master : micro_sl = destructeur net
        # (184 coupures, -$364 cum sur scalping). Le SL classique à 0.25% reste actif
        # comme filet. Les trades ont besoin de respirer pour atteindre TP 0.50%.
        # [v2.1.0] TP 0.50→0.65 : avec frais RT 0.31%, un TP 0.50% ne dégage que
        # 0.19% net (net $0.95 sur $500) — sous le seuil 2× frais du gate éco, donc
        # systématiquement rejeté. 0.65% (≈ 2.1× frais) franchit le gate et laisse
        # un net franc (~$1.70). SL 0.30 → R:R 2.2.
        return StrategyParams(
            stop_loss_pct=0.30,       # 0.25→0.30 (au-dessus du coût d'entrée 0.155%)
            take_profit_pct=0.65,     # 0.50→0.65 (franchit le gate éco 2× frais)
            position_size_usd=500.0,  # frais RT $1.55
            leverage=1.0,             # Pas de levier
            trailing_activation_pct=0.30,   # 0.15→0.30 (laisse le micro-move respirer)
            trailing_drop_ratio=0.25,       # 25% de recul = sortie
            micro_sl_pct=0.0,         # DÉSACTIVÉ (audit : micro_sl = destructeur net)
            max_hold_seconds=600,     # 10 min max
            min_hold_seconds=30,      # 30s min
            stale_negative_seconds=120, # 2min en perte → sortie
        )
