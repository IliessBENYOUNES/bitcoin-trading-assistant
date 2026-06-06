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
2. Applique les gates globaux statistiques (v2.0.30) — blocked_hours, min_atr, max_score
3. Sélectionne les stratégies éligibles
4. Collecte les signaux de chaque stratégie
5. Applique le risk layer global (anti-collision)
6. Retourne les signaux approuvés

EXPÉRIMENTAL — n'interfère pas avec le moteur standard.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    # Stratégies primaires en premier, secondaires ensuite
    # Chaque contexte propose 2-3 stratégies pour permettre des positions simultanées
    "range": {
        "low": ["mean_reversion", "scalping", "micro_scalping"],
        "mid": ["scalping", "micro_scalping", "mean_reversion"],
        "high": ["mean_reversion", "scalping", "micro_scalping"],
    },
    "trend": {
        "low": ["aggressive", "breakout", "scalping"],
        "mid": ["aggressive", "breakout", "scalping"],
        "high": ["aggressive", "breakout", "scalping"],
    },
    "breakout": {
        "low": ["breakout", "aggressive"],
        "mid": ["breakout", "aggressive"],
        "high": ["breakout", "aggressive"],
    },
    "unknown": {
        "low": ["scalping", "micro_scalping"],
        "mid": ["scalping", "micro_scalping"],
        "high": ["scalping", "micro_scalping"],
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
    2. Appliquer les gates globaux statistiques (v2.0.30)
    3. Router vers les bonnes stratégies
    4. Collecter les signaux
    5. Appliquer les filtres globaux (anti-collision, max positions)

    === GATES GLOBAUX STATISTIQUES (v2.0.30) ===

    Issus de l'audit comparatif 831 (MAIN) + 46 (EXP) trades du 17/04/2026.
    Ces gates s'appliquent AVANT les stratégies et sont partagés par toutes.
    """

    # [v2.0.30] BLOCKED HOURS UTC — Audit : 13-16h UTC = -$104 cum sur 4j (MAIN).
    # Fenêtre US open + macro releases (NFP/CPI/FOMC). Bruit destructif systémique.
    # Appliqué à toutes les stratégies (micro_scalping, scalping, aggressive, breakout,
    # mean_reversion) car l'analyse des données BTC montre un effet multi-stratégie.
    BLOCKED_HOURS_UTC: set[int] = {13, 14, 15, 16}

    # [v2.0.30] MIN ATR RATIO — Rejet des marchés compressés (chop range).
    # MarketContext.atr_ratio = range / ATR. Audit : aucun trade gagnant n'a eu lieu
    # en range < 1.5x ATR. Les marchés compressés ne peuvent pas capturer 0.62% (2x frais).
    MIN_ATR_RATIO: float = 1.5

    # [v2.0.30] MAX SCORE CAP — Corrélation |score| vs pnl_pct = -0.134 (p=0.0001).
    # Les scores >50 arrivent en retard (signal déjà digéré par le marché).
    # S'applique aux stratégies qui utilisent combined_score (scalping, aggressive, breakout,
    # mean_reversion). Pas à micro_scalping qui utilise micro_trend_score.
    MAX_ABS_COMBINED_SCORE: int = 55

    # [v2.0.30] BREAKEVEN MIN PEAK FEE MULTIPLE — Multiple des frais au-dessus duquel
    # le breakeven peut se déclencher. Évite les fermetures breakeven à net nul.
    # Ce paramètre est consommé par le paper_trading_service au moment de la fermeture.
    BREAKEVEN_MIN_PEAK_FEE_MULTIPLE: float = 2.0

    # [v2.1.0] GATE ÉCONOMIQUE PRÉ-TRADE — LA pièce manquante du plan d'audit (§5.2.D).
    # Aucune position ne s'ouvre si son take-profit (capture attendue) ne couvre pas
    # AU MOINS MIN_EV_MULTIPLE × les frais round-trip. Avec le preset "realistic"
    # (frais RT = 0.31%) et MIN_EV_MULTIPLE=2.0 → TP minimum requis = 0.62%.
    # Rationale (audit 17+23+27/04) : 21 trades brut+ devenus net-, ratio frais/|brut|
    # de 17×. Tant qu'un trade visait < 2× frais, il était structurellement perdant
    # même gagné. Ce gate rend mathématiquement impossible un trade fee-négatif.
    MIN_EV_MULTIPLE: float = 2.0

    # [v2.1.0] Preset de coûts utilisé par le gate (aligné sur _close_position EXP).
    COST_PRESET: str = "realistic"

    # [v2.1.0] CAP STRATÉGIES ÉLIGIBLES — L'audit du run 13/04 montre 3 stratégies
    # (aggressive+breakout+scalping) ouvrant en parallèle dans le même trend, ce qui
    # TRIPLE les frais sur un seul mouvement corrélé. On ne garde que les 2 stratégies
    # PRIORITAIRES de chaque contexte (diversité réelle, pas redondance corrélée).
    MAX_ELIGIBLE_STRATEGIES: int = 2

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
        max_simultaneous: int = 3,
        skip_global_gates: bool = False,
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

        # ─── [v2.0.30] GATES GLOBAUX STATISTIQUES ───────────────────────────
        # Les 3 gates ci-dessous refusent l'OUVERTURE de toute nouvelle position.
        # Ils n'affectent pas les positions ouvertes (sorties normales conservées).
        # skip_global_gates=True est utilisé UNIQUEMENT par les tests unitaires
        # qui veulent vérifier la logique de routing sans interférence temporelle.
        _combined_score_saturated = False

        if not skip_global_gates:
            # [v2.0.30] Gate horaire : fenêtre US open (13-16h UTC) destructive systémique.
            current_hour_utc = datetime.now(timezone.utc).hour
            if current_hour_utc in self.BLOCKED_HOURS_UTC:
                result.rejected_reasons.append(
                    f"[v2.0.30] Blocked hour UTC {current_hour_utc}h — audit 17/04 : "
                    f"heures {sorted(self.BLOCKED_HOURS_UTC)} = -$104 cum sur 4j"
                )
                return result

            # [v2.0.30] Gate structure : range compressé = impossible de couvrir 2x frais.
            if context.atr_ratio < self.MIN_ATR_RATIO:
                result.rejected_reasons.append(
                    f"[v2.0.30] Range compressé ({context.atr_ratio:.2f}x ATR "
                    f"< {self.MIN_ATR_RATIO:.2f}) — amplitude insuffisante pour frais RT"
                )
                return result

            # [v2.0.30] Gate scoring : cap |score| car corrélation négative score↔pnl.
            # S'applique aux stratégies qui consomment combined_score. Micro_scalping
            # utilise micro_trend_score et n'est pas concernée ici.
            combined_score = decision.get("combined_score", 0) or 0
            if abs(combined_score) > self.MAX_ABS_COMBINED_SCORE:
                result.rejected_reasons.append(
                    f"[v2.0.30] Score {combined_score} saturé (> {self.MAX_ABS_COMBINED_SCORE}) "
                    f"— signal probablement déjà consommé. Micro-scalping reste éligible."
                )
                # On ne return pas : micro_scalping peut encore entrer si son signal propre est valide.
                # On désactivera combined_score pour les autres stratégies via un flag.
                _combined_score_saturated = True

        # 2. Déterminer les stratégies éligibles
        eligible = self._get_eligible_strategies(context)
        # [v2.0.30] Si score saturé, ne garder que micro_scalping (qui n'utilise pas combined_score)
        if _combined_score_saturated:
            eligible = [s for s in eligible if s == "micro_scalping"]
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

        # 7. [v2.1.0] GATE ÉCONOMIQUE PRÉ-TRADE (universel) — refuse tout signal dont
        # le TP ne couvre pas MIN_EV_MULTIPLE × les frais round-trip. C'est la garantie
        # structurelle qu'aucun trade fee-négatif ne peut s'ouvrir. Pour les stratégies
        # à TP dérivé du range (mean_reversion, breakout), ce gate filtre les ranges
        # trop étroits ; pour les stratégies à TP fixe (scalping, aggressive,
        # micro_scalping) il agit comme filet de sécurité contre toute régression.
        if not skip_global_gates:
            from app.services.trading_cost_service import get_cost_model
            cost_model = get_cost_model(self.COST_PRESET)
            econ_approved: list[StrategySignal] = []
            for signal in approved:
                params = result.params_map.get(signal.strategy_type)
                if params is None:
                    continue
                viability = cost_model.estimate_economic_viability(
                    position_size_usd=params.position_size_usd,
                    leverage=params.leverage,
                    expected_capture_pct=params.take_profit_pct,
                    min_ev_multiple=self.MIN_EV_MULTIPLE,
                )
                if viability["is_viable"]:
                    econ_approved.append(signal)
                else:
                    result.rejected_reasons.append(
                        f"[v2.1.0] Gate éco {signal.strategy_type}: "
                        f"{viability['rejection_reason']}"
                    )
                    # Le params_map garde l'entrée pour le debug mais le signal sort.
            approved = econ_approved
            result.approved_signals = approved

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

    @classmethod
    def _get_eligible_strategies(cls, context: MarketContext) -> list[str]:
        """
        Retourne les stratégies éligibles pour le contexte donné.

        [v2.1.0] Cap à MAX_ELIGIBLE_STRATEGIES (2) : on ne garde que les stratégies
        PRIORITAIRES du contexte. Ouvrir 3 stratégies corrélées sur le même mouvement
        triplait les frais pour une seule thèse (audit run 13/04).
        """
        regime_map = CONTEXT_STRATEGY_MAP.get(context.regime, {})
        eligible = regime_map.get(context.zone, regime_map.get("mid", ["scalping"]))
        return eligible[: cls.MAX_ELIGIBLE_STRATEGIES]

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
