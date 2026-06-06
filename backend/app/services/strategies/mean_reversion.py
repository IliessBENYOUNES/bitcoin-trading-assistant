"""
MeanReversionStrategy — Retour à la moyenne aux extrêmes du range.

Logique :
- Active UNIQUEMENT quand le prix est aux bords du range (zone high/low)
- LONG quand prix en zone basse (survente → rebond)
- SHORT quand prix en zone haute (surachat → correction)
- Nécessite un contexte de range confirmé

La stratégie s'appuie sur le RSI et la position dans le range
pour détecter les extrêmes.

Contextes actifs : range (zone high → short, zone low → long)
"""

from app.services.market_context_engine import MarketContext
from app.services.strategies.base import (
    BaseStrategy, StrategySignal, StrategyParams, ExitSignal,
)


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"
    description = "Mean reversion — achat en bas de range, vente en haut"

    # Le prix doit être dans les 25% extrêmes du range
    EXTREME_THRESHOLD = 0.25
    # RSI pour confirmer l'extrême
    RSI_OVERSOLD = 35
    RSI_OVERBOUGHT = 65
    # Score minimum de confiance dans le régime range
    MIN_RANGE_CONFIDENCE = 40

    def evaluate_entry(
        self,
        context: MarketContext,
        decision: dict,
        current_price: float,
        series: list[dict],
    ) -> StrategySignal:
        # Uniquement en régime range
        if context.regime != "range":
            return StrategySignal(strategy_type=self.name)

        # Confiance minimum dans le range
        if context.confidence < self.MIN_RANGE_CONFIDENCE:
            return StrategySignal(strategy_type=self.name)

        # Extraire RSI du decision
        rsi = self._extract_rsi(decision)

        # Zone basse → LONG (prix survendu, retour vers le milieu)
        if context.zone == "low" and context.price_position <= self.EXTREME_THRESHOLD:
            if rsi is not None and rsi > self.RSI_OVERSOLD:
                # RSI pas assez bas → signal faible
                strength = 30
            else:
                strength = 70

            return StrategySignal(
                should_enter=True,
                direction="long",
                strength=strength,
                reason=f"mean_rev_long | pos={context.price_position:.0%} | "
                       f"RSI={rsi or '?'} | range=[{context.range_low:.0f}-{context.range_high:.0f}]",
                strategy_type=self.name,
            )

        # Zone haute → SHORT (prix suracheté, retour vers le milieu)
        if context.zone == "high" and context.price_position >= (1 - self.EXTREME_THRESHOLD):
            if rsi is not None and rsi < self.RSI_OVERBOUGHT:
                strength = 30
            else:
                strength = 70

            return StrategySignal(
                should_enter=True,
                direction="short",
                strength=strength,
                reason=f"mean_rev_short | pos={context.price_position:.0%} | "
                       f"RSI={rsi or '?'} | range=[{context.range_low:.0f}-{context.range_high:.0f}]",
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
        """Sortie quand le prix revient au milieu du range (target atteint)."""
        # Si le prix est revenu au milieu du range → objectif atteint
        if context.zone == "mid" and unrealized_pnl_pct > 0:
            return ExitSignal(
                should_exit=True,
                reason="Mean reversion target atteint — prix revenu au mid-range",
                strategy_type=self.name,
            )
        return ExitSignal(should_exit=False, strategy_type=self.name)

    def get_params(self, context: MarketContext, direction: str) -> StrategyParams:
        # [v2.1.0] Géométrie mean-reversion corrigée. On vise le RETOUR vers le milieu
        # du range (TP ≈ 0.7 × demi-range) avec un SL plus serré (0.5 × demi-range)
        # juste au-delà de l'extrême → R:R ≈ 1.4. Le TP reste DÉRIVÉ DU RANGE (pas de
        # plancher artificiel gonflé) : le gate économique (TP ≥ 2× frais = 0.62%)
        # rejette donc automatiquement les ranges trop étroits (< ~1.8% de large),
        # où une réversion ne couvrirait jamais les frais. C'est exactement le filtre
        # voulu : on ne fait du mean-reversion QUE dans des ranges économiquement utiles.
        range_half_pct = context.range_width_pct / 2 if context.range_width_pct > 0 else 0.5

        # $800 × 1.0x = frais RT $2.48
        return StrategyParams(
            stop_loss_pct=max(0.40, range_half_pct * 0.5),   # Serré (protection cassure)
            take_profit_pct=max(0.30, range_half_pct * 0.7), # Réversion vers le milieu
            position_size_usd=800.0,
            leverage=1.0,                   # Pas de levier
            trailing_activation_pct=0.40,   # 0.25→0.40 (au-dessus des frais)
            trailing_drop_ratio=0.25,
            micro_sl_pct=0.0,               # [v2.1.0] DÉSACTIVÉ (cohérent : noise-cut destructeur)
            max_hold_seconds=3600,          # 1h max
            min_hold_seconds=60,
            stale_negative_seconds=600,     # 10 min en perte → sortie
        )

    @staticmethod
    def _extract_rsi(decision: dict) -> float | None:
        """Extrait la valeur RSI du résultat de décision."""
        # Le decision dict contient _series avec les indicateurs
        series = decision.get("_series", [])
        if series:
            latest = series[-1]
            rsi = latest.get("rsi_14") or latest.get("rsi")
            if rsi is not None:
                return float(rsi)
        return None
