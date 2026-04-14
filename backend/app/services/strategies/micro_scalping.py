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
    MIN_MICRO_TREND = 3  # abs(micro_trend) >= 3 pour un signal
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
        return StrategyParams(
            stop_loss_pct=0.25,       # Élargi 0.10→0.25%
            take_profit_pct=0.50,     # Élargi 0.30→0.50%
            position_size_usd=500.0,  # Réduit 1500→500 (frais $1.55 au lieu de $4.65)
            leverage=1.0,             # Pas de levier
            trailing_activation_pct=0.15,   # Élargi 0.05→0.15%
            trailing_drop_ratio=0.25,       # 25% de recul = sortie
            micro_sl_pct=0.10,        # Élargi 0.03→0.10%
            max_hold_seconds=600,     # 10 min max (était 5)
            min_hold_seconds=30,      # 30s min (était 10)
            stale_negative_seconds=120, # 2min en perte → sortie (était 1min)
        )
