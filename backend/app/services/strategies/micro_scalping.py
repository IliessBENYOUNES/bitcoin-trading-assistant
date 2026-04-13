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
        # Ultra-serré : petites positions, sortie rapide
        return StrategyParams(
            stop_loss_pct=0.10,       # 0.10% SL (très serré)
            take_profit_pct=0.30,     # 0.30% TP
            position_size_usd=1500.0, # Plus petite taille
            leverage=1.0,             # Pas de levier
            trailing_activation_pct=0.05,   # Trailing dès 0.05%
            trailing_drop_ratio=0.20,       # 20% de recul = sortie
            micro_sl_pct=0.03,        # Micro SL à 0.03% (ultra-serré)
            max_hold_seconds=300,     # 5 min max
            min_hold_seconds=10,      # 10s min
            stale_negative_seconds=60, # 1min en perte → sortie
        )
