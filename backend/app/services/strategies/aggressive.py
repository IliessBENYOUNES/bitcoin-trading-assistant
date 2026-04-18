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
    description = "Aggressive swing — trend-following, hold plus long, gros mouvements"

    MIN_SCORE = 25           # Relévé de 15→25 : ne prendre que les bons signaux
    MIN_TREND_CONFIDENCE = 60  # Relévé de 40→60 : trend bien confirmé seulement

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
        # Levier réduit : 1.5x max (avant 3x → frais x3 pour des gains minuscules)
        if context.confidence >= 80:
            leverage = 1.5
        else:
            leverage = 1.0

        # Position plus petite → frais plus bas → breakeven plus facile
        # $1000 × 1.5x = $1500 effectif → frais RT = $4.65 au lieu de $23.25
        # [v2.0.30] micro_sl désactivé (0.0) — audit : les swings aggressive ont
        # besoin d'encore plus de respiration que le scalping (mouvements 1-2%).
        # Le SL classique 1.5% reste le seul filet de perte, ce qui est cohérent
        # avec un horizon de 2min-48h.
        return StrategyParams(
            stop_loss_pct=1.5,              # Élargi 1.0→1.5% (laisse respirer le trade)
            take_profit_pct=2.0,            # Élargi 1.0→2.0% (vise des vrais mouvements)
            position_size_usd=1000.0,       # Réduit 2500→1000 (frais proportionnels)
            leverage=leverage,
            trailing_activation_pct=0.60,   # Élargi 0.25→0.60% (ne pas couper trop tôt)
            trailing_drop_ratio=0.30,       # Garde 70% du pic (20→30% de recul toléré)
            micro_sl_pct=0.0,               # [v2.0.30] DÉSACTIVÉ (était 0.50)
            max_hold_seconds=172800,        # 48h
            min_hold_seconds=120,           # 2min minimum (avant 60s)
            stale_negative_seconds=900,     # 15 min en perte → sortie (avant 10 min)
        )
