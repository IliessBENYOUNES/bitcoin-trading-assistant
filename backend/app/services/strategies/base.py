"""
BaseStrategy — Classe abstraite pour toutes les stratégies.

Chaque stratégie reçoit le contexte de marché + les données de décision
et retourne un signal d'entrée ou de sortie.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.services.market_context_engine import MarketContext


@dataclass
class StrategySignal:
    """Signal émis par une stratégie."""
    # Doit-on entrer ?
    should_enter: bool = False
    # Direction : "long" ou "short"
    direction: str = "long"
    # Force du signal (0-100)
    strength: int = 0
    # Raison lisible
    reason: str = ""
    # Stratégie qui a émis le signal
    strategy_type: str = ""


@dataclass
class ExitSignal:
    """Signal de sortie émis par une stratégie."""
    should_exit: bool = False
    reason: str = ""
    strategy_type: str = ""


@dataclass
class StrategyParams:
    """Paramètres de position pour une stratégie."""
    # Stop-loss en % du prix d'entrée
    stop_loss_pct: float = 1.0
    # Take-profit en % du prix d'entrée
    take_profit_pct: float = 1.0
    # Taille de position en USD (sera ajusté par le risk layer)
    position_size_usd: float = 2500.0
    # Levier
    leverage: float = 1.0
    # Trailing stop activation (% de gain avant activation)
    trailing_activation_pct: float = 0.10
    # Trailing stop drop ratio (% de recul max depuis le pic)
    trailing_drop_ratio: float = 0.15
    # Micro stop loss (% de perte max avant sortie immédiate)
    micro_sl_pct: float = 0.05
    # Durée max en secondes
    max_hold_seconds: float = 7200
    # Durée min en secondes (anti-churn)
    min_hold_seconds: float = 30
    # Stale exit : fermer après N secondes si PnL négatif
    stale_negative_seconds: float = 180


class BaseStrategy(ABC):
    """
    Interface commune pour toutes les stratégies de trading.

    Chaque stratégie décide indépendamment d'entrer ou non,
    basée sur le contexte de marché et les signaux techniques.
    """

    # Nom unique de la stratégie
    name: str = "base"
    # Description
    description: str = "Stratégie de base"

    @abstractmethod
    def evaluate_entry(
        self,
        context: MarketContext,
        decision: dict,
        current_price: float,
        series: list[dict],
    ) -> StrategySignal:
        """
        Évalue si la stratégie doit ouvrir une position.

        Args:
            context: Contexte de marché (régime, zone, volatilité)
            decision: Résultat du DecisionService (scores, rules, recommendation)
            current_price: Prix BTC actuel
            series: Série de candles brutes

        Returns:
            StrategySignal avec should_enter=True/False + direction + raison
        """
        ...

    @abstractmethod
    def get_params(self, context: MarketContext, direction: str) -> StrategyParams:
        """
        Retourne les paramètres de position (SL, TP, sizing, trailing).

        Args:
            context: Contexte de marché
            direction: "long" ou "short"

        Returns:
            StrategyParams adaptés au contexte
        """
        ...

    def evaluate_exit(
        self,
        context: MarketContext,
        trade: object,
        current_price: float,
        unrealized_pnl_pct: float,
    ) -> ExitSignal:
        """
        Évalue si la stratégie doit fermer une position existante.

        Implémentation par défaut : pas de sortie stratégique
        (les sorties SL/TP/trailing sont gérées par le moteur).

        Override pour des sorties spécifiques (ex: breakout qui s'essouffle).
        """
        return ExitSignal(should_exit=False, strategy_type=self.name)
