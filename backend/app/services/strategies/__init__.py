"""
Strategies — Modules de stratégie pour le Multi-Strategy Engine.

Chaque stratégie implémente BaseStrategy et définit :
- should_enter() : conditions d'entrée
- should_exit() : conditions de sortie
- get_params() : paramètres de position (SL, TP, sizing)

EXPÉRIMENTAL — ces stratégies ne sont pas utilisées par le moteur standard.
"""

from app.services.strategies.base import BaseStrategy, StrategySignal, StrategyParams
from app.services.strategies.scalping import ScalpingStrategy
from app.services.strategies.micro_scalping import MicroScalpingStrategy
from app.services.strategies.mean_reversion import MeanReversionStrategy
from app.services.strategies.breakout import BreakoutStrategy
from app.services.strategies.aggressive import AggressiveStrategy

__all__ = [
    "BaseStrategy",
    "StrategySignal",
    "StrategyParams",
    "ScalpingStrategy",
    "MicroScalpingStrategy",
    "MeanReversionStrategy",
    "BreakoutStrategy",
    "AggressiveStrategy",
]
