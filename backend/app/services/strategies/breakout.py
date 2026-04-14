"""
BreakoutStrategy — Cassure de range avec volume.

Logique :
- Détecte les cassures de range (prix sort des bornes + volume élevé)
- Suit la direction du breakout
- SL serré juste en dessous/au-dessus de la borne cassée
- TP large (trend-following)

Contextes actifs : breakout, trend début
"""

from app.services.market_context_engine import MarketContext
from app.services.strategies.base import BaseStrategy, StrategySignal, StrategyParams, ExitSignal


class BreakoutStrategy(BaseStrategy):
    name = "breakout"
    description = "Breakout — suit les cassures de range avec volume"

    MIN_BREAKOUT_STRENGTH = 0.2
    MIN_VOLUME_RATIO = 0.0  # Désactivé (volume_sma_20 absent sur candles 30m fallback)

    def evaluate_entry(
        self,
        context: MarketContext,
        decision: dict,
        current_price: float,
        series: list[dict],
    ) -> StrategySignal:
        # Signal prioritaire : breakout détecté par le context engine
        if context.regime == "breakout" and context.breakout_direction:
            if context.breakout_strength < self.MIN_BREAKOUT_STRENGTH:
                return StrategySignal(strategy_type=self.name)

            direction = "long" if context.breakout_direction == "up" else "short"

            return StrategySignal(
                should_enter=True,
                direction=direction,
                strength=min(100, int(context.breakout_strength * 100)),
                reason=f"breakout_{direction} | strength={context.breakout_strength:.2f} | "
                       f"vol={context.volume_ratio:.1f}x | "
                       f"range=[{context.range_low:.0f}-{context.range_high:.0f}]",
                strategy_type=self.name,
            )

        # Signal secondaire : début de trend après un range
        # (le context engine peut classer "trend" si le breakout est confirmé)
        if (context.regime == "trend" and
                context.confidence >= 60):
            direction = "long" if context.trend_direction == "bullish" else "short"

            combined_score = decision.get("combined_score", 0) or 0
            # Le score doit confirmer la direction du trend
            if direction == "long" and combined_score < 0:
                return StrategySignal(strategy_type=self.name)
            if direction == "short" and combined_score > 0:
                return StrategySignal(strategy_type=self.name)

            return StrategySignal(
                should_enter=True,
                direction=direction,
                strength=min(80, context.confidence),
                reason=f"trend_follow_{direction} | confidence={context.confidence} | "
                       f"vol={context.volume_ratio:.1f}x | score={combined_score}",
                strategy_type=self.name,
            )

        return StrategySignal(strategy_type=self.name)

    def evaluate_exit(
        self,
        context: MarketContext,
        trade: object,
        current_price: float,
        unrealized_pnl_pct: float,
    ) -> ExitSignal:
        """Sortie si le breakout s'essouffle (retour en range)."""
        if context.regime == "range" and unrealized_pnl_pct > 0:
            return ExitSignal(
                should_exit=True,
                reason="Breakout essoufflé — retour en régime range, "
                       "sécurisation du profit",
                strategy_type=self.name,
            )
        return ExitSignal(should_exit=False, strategy_type=self.name)

    def get_params(self, context: MarketContext, direction: str) -> StrategyParams:
        # SL juste en dessous de la borne cassée, TP large
        if context.range_width_pct > 0:
            sl_pct = max(0.20, context.range_width_pct * 0.3)
            tp_pct = max(0.50, context.range_width_pct * 1.0)
        else:
            sl_pct = 0.30
            tp_pct = 1.0

        return StrategyParams(
            stop_loss_pct=sl_pct,
            take_profit_pct=tp_pct,
            position_size_usd=1000.0,       # Réduit 2500→1000 (frais proportionnels)
            leverage=1.5,                   # Réduit 2.0→1.5
            trailing_activation_pct=0.40,   # Élargi 0.20→0.40% (laisser le breakout se développer)
            trailing_drop_ratio=0.25,       # Garde 75% du pic
            micro_sl_pct=0.30,              # Élargi 0.10→0.30% (breakout = volatil)
            max_hold_seconds=14400,         # 4h max
            min_hold_seconds=120,           # 2min minimum
            stale_negative_seconds=600,     # 10min (breakout prend du temps)
        )
