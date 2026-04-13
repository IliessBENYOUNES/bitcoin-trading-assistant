"""
MultiStrategyEngine — Orchestrateur multi-stratégie.

Route les stratégies actives en fonction du contexte de marché :

| Contexte      | Stratégies actives               |
|---------------|----------------------------------|
| Range mid     | scalping + micro_scalping        |
| Range edges   | mean_reversion                   |
| Trend         | breakout + aggressive            |
| Breakout      | breakout only                    |

Chaque tick :
1. Analyse le contexte de marché (MarketContextEngine)
2. Sélectionne les stratégies éligibles
3. Collecte les signaux de chaque stratégie
4. Applique le risk layer global (anti-collision)
5. Retourne les signaux approuvés

EXPÉRIMENTAL — n'interfère pas avec le moteur standard.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.services.market_context_engine import MarketContext, MarketContextEngine
from app.services.strategies.base import BaseStrategy, StrategySignal, StrategyParams
from app.services.strategies.scalping import ScalpingStrategy
from app.services.strategies.micro_scalping import MicroScalpingStrategy
from app.services.strategies.mean_reversion import MeanReversionStrategy
from app.services.strategies.breakout import BreakoutStrategy
from app.services.strategies.aggressive import AggressiveStrategy

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Routing table : contexte → stratégies
# ─────────────────────────────────────────────────────────────────────────────

CONTEXT_STRATEGY_MAP: dict[str, dict[str, list[str]]] = {
    # regime → zone → [strategies]
    "range": {
        "low": ["mean_reversion", "scalping"],
        "mid": ["scalping", "micro_scalping"],
        "high": ["mean_reversion", "scalping"],
    },
    "trend": {
        "low": ["aggressive", "breakout"],
        "mid": ["aggressive", "breakout"],
        "high": ["aggressive", "breakout"],
    },
    "breakout": {
        "low": ["breakout"],
        "mid": ["breakout"],
        "high": ["breakout"],
    },
    "unknown": {
        "low": ["scalping"],
        "mid": ["scalping"],
        "high": ["scalping"],
    },
}


@dataclass
class OrchestratorResult:
    """Résultat d'un tick de l'orchestrateur."""
    context: MarketContext
    eligible_strategies: list[str] = field(default_factory=list)
    signals: list[StrategySignal] = field(default_factory=list)
    approved_signals: list[StrategySignal] = field(default_factory=list)
    rejected_reasons: list[str] = field(default_factory=list)
    params_map: dict[str, StrategyParams] = field(default_factory=dict)


class MultiStrategyEngine:
    """
    Orchestrateur central du multi-strategy engine.

    Responsable de :
    1. Analyser le contexte de marché
    2. Router vers les bonnes stratégies
    3. Collecter les signaux
    4. Appliquer les filtres globaux
    """

    def __init__(self):
        # Instancier toutes les stratégies
        self._strategies: dict[str, BaseStrategy] = {
            "scalping": ScalpingStrategy(),
            "micro_scalping": MicroScalpingStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "breakout": BreakoutStrategy(),
            "aggressive": AggressiveStrategy(),
        }

    @property
    def strategies(self) -> dict[str, BaseStrategy]:
        return self._strategies

    def evaluate_tick(
        self,
        series: list[dict],
        decision: dict,
        current_price: float,
        open_positions: list[dict] | None = None,
        max_simultaneous: int = 2,
    ) -> OrchestratorResult:
        """
        Évalue un tick et retourne les signaux approuvés.

        Args:
            series: Série de candles avec indicateurs
            decision: Résultat du DecisionService
            current_price: Prix BTC actuel
            open_positions: Positions ouvertes actuelles
                            [{"strategy_type": str, "direction": str, ...}]
            max_simultaneous: Nombre max de positions simultanées

        Returns:
            OrchestratorResult avec contexte, signaux et approbations
        """
        open_positions = open_positions or []
        result = OrchestratorResult(context=MarketContext())

        # 1. Analyser le contexte
        context = MarketContextEngine.analyze(series)
        result.context = context

        # 2. Déterminer les stratégies éligibles
        eligible = self._get_eligible_strategies(context)
        result.eligible_strategies = eligible

        if not eligible:
            result.rejected_reasons.append(
                f"Aucune stratégie éligible pour {context.regime}/{context.zone}"
            )
            return result

        # 3. Collecter les signaux de chaque stratégie éligible
        signals: list[StrategySignal] = []
        for strategy_name in eligible:
            strategy = self._strategies.get(strategy_name)
            if strategy is None:
                continue
            signal = strategy.evaluate_entry(context, decision, current_price, series)
            if signal.should_enter:
                signals.append(signal)

        result.signals = signals

        if not signals:
            return result

        # 4. Trier par force décroissante (meilleur signal en premier)
        signals.sort(key=lambda s: s.strength, reverse=True)

        # 5. Appliquer les filtres globaux
        approved = self._apply_global_filters(
            signals, context, open_positions, max_simultaneous, result,
        )
        result.approved_signals = approved

        # 6. Calculer les params pour chaque signal approuvé
        for signal in approved:
            strategy = self._strategies.get(signal.strategy_type)
            if strategy:
                params = strategy.get_params(context, signal.direction)
                result.params_map[signal.strategy_type] = params

        return result

    def evaluate_exits(
        self,
        series: list[dict],
        open_positions: list[dict],
        current_price: float,
    ) -> list[tuple[dict, str]]:
        """
        Évalue les sorties stratégiques pour les positions ouvertes.

        Returns:
            Liste de (position, exit_reason) pour les positions à fermer.
        """
        if not open_positions:
            return []

        context = MarketContextEngine.analyze(series)
        exits = []

        for pos in open_positions:
            strategy_type = pos.get("strategy_type", "")
            strategy = self._strategies.get(strategy_type)
            if strategy is None:
                continue

            entry_price = pos.get("entry_price", 0)
            if entry_price <= 0:
                continue

            direction = pos.get("direction", "long")
            if direction == "long":
                unrealized_pct = (current_price - entry_price) / entry_price * 100
            else:
                unrealized_pct = (entry_price - current_price) / entry_price * 100

            exit_signal = strategy.evaluate_exit(
                context, pos, current_price, unrealized_pct,
            )
            if exit_signal.should_exit:
                exits.append((pos, exit_signal.reason))

        return exits

    # ─────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_eligible_strategies(context: MarketContext) -> list[str]:
        """Retourne les stratégies éligibles pour le contexte donné."""
        regime_map = CONTEXT_STRATEGY_MAP.get(context.regime, {})
        return regime_map.get(context.zone, regime_map.get("mid", ["scalping"]))

    @staticmethod
    def _apply_global_filters(
        signals: list[StrategySignal],
        context: MarketContext,
        open_positions: list[dict],
        max_simultaneous: int,
        result: OrchestratorResult,
    ) -> list[StrategySignal]:
        """
        Filtre global anti-collision et limite d'exposition.

        Règles :
        1. Pas plus de max_simultaneous positions ouvertes
        2. Pas de collision long/short sur le même actif
        3. Pas de doublon de stratégie (une seule position par stratégie)
        4. Pas plus de 2 stratégies différentes simultanément
        """
        approved = []

        # Stratégies déjà occupées
        occupied_strategies = {
            pos.get("strategy_type") for pos in open_positions
        }
        # Directions ouvertes
        open_directions = {
            pos.get("direction") for pos in open_positions
        }
        # Nombre de positions ouvertes
        current_count = len(open_positions)

        for signal in signals:
            # Limite de positions simultanées
            if current_count + len(approved) >= max_simultaneous:
                result.rejected_reasons.append(
                    f"Max positions atteint ({max_simultaneous})"
                )
                break

            # Pas de doublon de stratégie
            if signal.strategy_type in occupied_strategies:
                result.rejected_reasons.append(
                    f"Stratégie {signal.strategy_type} déjà occupée"
                )
                continue

            # Anti-collision long/short
            opposite = "short" if signal.direction == "long" else "long"
            if opposite in open_directions:
                result.rejected_reasons.append(
                    f"Anti-collision : {signal.direction} bloqué, "
                    f"position {opposite} déjà ouverte"
                )
                continue

            approved.append(signal)
            # Marquer cette stratégie et direction comme occupées
            occupied_strategies.add(signal.strategy_type)
            open_directions.add(signal.direction)

        return approved

    def get_strategy_info(self) -> list[dict]:
        """Retourne les infos de toutes les stratégies."""
        return [
            {
                "name": s.name,
                "description": s.description,
            }
            for s in self._strategies.values()
        ]
