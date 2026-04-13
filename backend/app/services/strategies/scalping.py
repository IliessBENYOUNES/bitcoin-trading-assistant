"""
ScalpingStrategy — Scalping classique adapté au multi-strategy.

Reprend la logique du profil scalping existant :
- Timeframe 5m, signaux rapides
- SAS obligatoire, micro SL, trailing serré
- Fonctionne en range mid et trend modéré

Contextes actifs : range_mid, trend modéré
"""

from app.services.market_context_engine import MarketContext
from app.services.strategies.base import BaseStrategy, StrategySignal, StrategyParams


class ScalpingStrategy(BaseStrategy):
    name = "scalping"
    description = "Scalping classique — signaux 5m, SAS, micro SL"

    # Seuils
    MIN_SCORE = 10
    MIN_VOLUME_RATIO = 0.8

    def evaluate_entry(
        self,
        context: MarketContext,
        decision: dict,
        current_price: float,
        series: list[dict],
    ) -> StrategySignal:
        combined_score = decision.get("combined_score", 0) or 0
        abs_score = abs(combined_score)

        # Pas de signal suffisant
        if abs_score < self.MIN_SCORE:
            return StrategySignal(strategy_type=self.name)

        # Volume minimum
        if context.volume_ratio < self.MIN_VOLUME_RATIO:
            return StrategySignal(strategy_type=self.name)

        # Direction basée sur le score
        if combined_score > 0:
            direction = "long"
        else:
            direction = "short"

        # En range mid : accepter les deux directions
        # En trend : suivre le trend uniquement
        if context.regime == "trend":
            if context.trend_direction == "bullish" and direction == "short":
                return StrategySignal(strategy_type=self.name)
            if context.trend_direction == "bearish" and direction == "long":
                return StrategySignal(strategy_type=self.name)

        return StrategySignal(
            should_enter=True,
            direction=direction,
            strength=abs_score,
            reason=f"scalping_{direction} | score={combined_score} | "
                   f"regime={context.regime} | zone={context.zone}",
            strategy_type=self.name,
        )

    def get_params(self, context: MarketContext, direction: str) -> StrategyParams:
        # Paramètres serrés pour le scalping
        return StrategyParams(
            stop_loss_pct=0.20,
            take_profit_pct=0.80,
            position_size_usd=2500.0,
            leverage=1.5,
            trailing_activation_pct=0.10,
            trailing_drop_ratio=0.15,
            micro_sl_pct=0.05,
            max_hold_seconds=7200,  # 2h max
            min_hold_seconds=30,
            stale_negative_seconds=180,  # 3min en perte → sortie
        )
