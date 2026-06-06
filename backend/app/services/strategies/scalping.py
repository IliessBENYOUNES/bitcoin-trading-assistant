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
    # [v2.1.0] MIN_SCORE 20→28 : l'audit (831 trades MAIN) montre que la bande de
    # score la plus rentable est 30-50 ; en-dessous de ~28 le WR net est aléatoire et
    # les frais dominent. Le gate global MAX_ABS_COMBINED_SCORE=55 borne le haut.
    # Scalping ne tire donc plus que dans la bande utile [28, 55].
    MIN_SCORE = 28
    MIN_VOLUME_RATIO = 0.0  # Désactivé (volume_sma_20 absent sur les candles 30m fallback)

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

        # Direction basée sur le score
        if combined_score > 0:
            direction = "long"
        else:
            direction = "short"

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
        # Position réduite : $800 × 1.0x = $800 effectif → frais RT = $2.48
        # Il faut capturer > 0.62% pour être rentable → target 0.80% OK
        # [v2.0.30] micro_sl désactivé (0.0) — même rationale que master :
        # les micro coupures arrivent avant que le trade puisse se développer.
        # Le SL classique 0.40% reste comme filet de sécurité.
        return StrategyParams(
            stop_loss_pct=0.40,             # Élargi 0.20→0.40% (0.20 = micro bruit)
            take_profit_pct=0.80,           # Gardé à 0.80% (bon ratio risque/gain)
            position_size_usd=800.0,        # Réduit 2500→800 (frais $2.48 au lieu de $11.62)
            leverage=1.0,                   # Pas de levier (levier amplifie les frais)
            trailing_activation_pct=0.30,   # Élargi 0.10→0.30% (laisser le trade respirer)
            trailing_drop_ratio=0.25,       # Garde 75% du pic
            micro_sl_pct=0.0,               # [v2.0.30] DÉSACTIVÉ (était 0.20)
            max_hold_seconds=7200,          # 2h max
            min_hold_seconds=60,            # 1min minimum (avant 30s)
            stale_negative_seconds=300,     # 5min en perte → sortie (avant 3min)
        )
