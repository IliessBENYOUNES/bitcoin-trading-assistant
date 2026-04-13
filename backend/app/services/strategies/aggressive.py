"""
AggressiveStrategy — Stratégie agressive swing (adaptée du profil existant).

Reprend la logique du profil aggressive :
- Timeframe 1h, levier jusqu'à 3x
- Seuils d'entrée bas (profite des signaux moyens)
- SAS obligatoire, micro SL 0.15%

Contextes actifs : trend (suit la tendance avec levier)
"""

from app.services.market_context_engine import MarketContext
from app.services.strategies.base import BaseStrategy, StrategySignal, StrategyParams


class AggressiveStrategy(BaseStrategy):
    name = "aggressive"
    description = "Aggressive swing — trend-following avec levier"

    MIN_SCORE = 15
    MIN_TREND_CONFIDENCE = 40

    def evaluate_entry(
        self,
        context: MarketContext,
        decision: dict,
        current_price: float,
        series: list[dict],
    ) -> StrategySignal:
        combined_score = decision.get("combined_score", 0) or 0
        abs_score = abs(combined_score)

        if abs_score < self.MIN_SCORE:
            return StrategySignal(strategy_type=self.name)

        # En trend : suit la direction du trend
        if context.regime == "trend" and context.confidence >= self.MIN_TREND_CONFIDENCE:
            if context.trend_direction == "bullish" and combined_score > 0:
                return StrategySignal(
                    should_enter=True,
                    direction="long",
                    strength=abs_score,
                    reason=f"aggressive_long | trend_bullish | score={combined_score} | "
                           f"confidence={context.confidence}",
                    strategy_type=self.name,
                )
            if context.trend_direction == "bearish" and combined_score < 0:
                return StrategySignal(
                    should_enter=True,
                    direction="short",
                    strength=abs_score,
                    reason=f"aggressive_short | trend_bearish | score={combined_score} | "
                           f"confidence={context.confidence}",
                    strategy_type=self.name,
                )

        # En breakout : suit le breakout
        if context.regime == "breakout" and context.breakout_direction:
            direction = "long" if context.breakout_direction == "up" else "short"
            if (direction == "long" and combined_score > 0) or \
               (direction == "short" and combined_score < 0):
                return StrategySignal(
                    should_enter=True,
                    direction=direction,
                    strength=min(90, abs_score + 20),
                    reason=f"aggressive_{direction} | breakout_{context.breakout_direction} | "
                           f"score={combined_score}",
                    strategy_type=self.name,
                )

        return StrategySignal(strategy_type=self.name)

    def get_params(self, context: MarketContext, direction: str) -> StrategyParams:
        # Levier adaptatif selon la confiance
        if context.confidence >= 70:
            leverage = 3.0
        elif context.confidence >= 50:
            leverage = 2.0
        else:
            leverage = 1.5

        return StrategyParams(
            stop_loss_pct=1.0,
            take_profit_pct=1.0,
            position_size_usd=2500.0,
            leverage=leverage,
            trailing_activation_pct=0.25,
            trailing_drop_ratio=0.20,
            micro_sl_pct=0.15,
            max_hold_seconds=172800,  # 48h
            min_hold_seconds=60,
            stale_negative_seconds=600,  # 10 min en perte → sortie
        )
