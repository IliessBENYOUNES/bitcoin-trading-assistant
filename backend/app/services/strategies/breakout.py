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
    # [v2.1.0] Signal secondaire "trend-follow" DURCI. C'était le sur-déclencheur n°1 :
    # il entrait dès regime="trend" + confidence≥60 (que le classifier accorde avec
    # seulement 2 signaux faibles), captant de faux trends → 83% de sorties stale et
    # le plus gros des pertes du run 25-27/04. On exige maintenant un trend bien
    # confirmé (confidence≥70) ET une vraie magnitude de score (|score|≥30).
    TREND_FOLLOW_MIN_CONFIDENCE = 70
    TREND_FOLLOW_MIN_SCORE = 30

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
        # [v2.1.0] Durci : confidence≥70 ET |score|≥30 (était confidence≥60 + simple
        # accord de signe → captait de faux trends).
        if (context.regime == "trend" and
                context.confidence >= self.TREND_FOLLOW_MIN_CONFIDENCE):
            direction = "long" if context.trend_direction == "bullish" else "short"

            combined_score = decision.get("combined_score", 0) or 0
            # Le score doit confirmer la direction du trend AVEC une vraie magnitude.
            if abs(combined_score) < self.TREND_FOLLOW_MIN_SCORE:
                return StrategySignal(strategy_type=self.name)
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
        # [v2.1.0] TP = "measured move" (≈ 1× la largeur du range cassé), SL serré juste
        # derrière la borne. Le TP reste DÉRIVÉ DU RANGE (plancher 0.40% abaissé de
        # 0.50%) : le gate économique (≥0.62%) rejette donc les cassures de ranges trop
        # étroits, dont le mouvement mesuré ne couvrirait pas 2× les frais. On ne suit
        # que les breakouts dont l'amplitude attendue est économiquement réelle.
        if context.range_width_pct > 0:
            sl_pct = max(0.25, context.range_width_pct * 0.3)   # 0.20→0.25 (> coût entrée)
            tp_pct = max(0.40, context.range_width_pct * 1.0)   # plancher 0.50→0.40 (gate filtre)
        else:
            sl_pct = 0.30
            tp_pct = 1.0

        return StrategyParams(
            stop_loss_pct=sl_pct,
            take_profit_pct=tp_pct,
            position_size_usd=1000.0,       # frais RT $4.65 à 1.5x
            leverage=1.5,
            trailing_activation_pct=0.40,   # laisser le breakout se développer
            trailing_drop_ratio=0.25,       # Garde 75% du pic
            micro_sl_pct=0.0,               # [v2.1.0] DÉSACTIVÉ (cohérence : pas de noise-cut)
            max_hold_seconds=14400,         # 4h max
            min_hold_seconds=120,           # 2min minimum
            stale_negative_seconds=600,     # 10min (breakout prend du temps)
        )
