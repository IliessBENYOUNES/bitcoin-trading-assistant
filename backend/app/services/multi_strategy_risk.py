"""
MultiStrategyRiskLayer — Couche de risque globale pour le multi-strategy engine.

Gère :
1. Anti-collision long/short (pas de hedge implicite)
2. Limite d'exposition totale (somme des positions)
3. Limite par stratégie (1 position max par stratégie)
4. Corrélation temporelle (pas de rafale d'entrées)
5. Drawdown global (kill switch multi-stratégie)

EXPÉRIMENTAL — utilisé uniquement par ExperimentalPaperTradingService.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.services.strategies.base import StrategySignal

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    """Résultat de la vérification de risque."""
    approved: bool = True
    reason: str = ""
    exposure_usd: float = 0.0
    exposure_pct: float = 0.0


@dataclass
class ExposureSnapshot:
    """État de l'exposition à un instant T."""
    total_exposure_usd: float = 0.0
    total_exposure_pct: float = 0.0
    long_exposure_usd: float = 0.0
    short_exposure_usd: float = 0.0
    num_positions: int = 0
    strategies_active: list[str] = field(default_factory=list)
    net_direction: str = "neutral"  # "long", "short", "neutral"


class MultiStrategyRiskLayer:
    """
    Couche de risque globale pour le multi-strategy engine.

    Vérifie chaque signal AVANT ouverture de position.
    """

    def __init__(
        self,
        max_total_exposure_pct: float = 80.0,    # Max 80% du capital exposé
        max_single_position_pct: float = 30.0,    # Max 30% du capital par position
        max_simultaneous_positions: int = 3,       # Max 3 positions simultanées
        max_same_direction: int = 2,               # Max 2 positions même direction
        min_entry_interval_seconds: float = 5.0,   # 5s entre deux entrées (permet multi-slot)
        max_drawdown_kill_pct: float = 5.0,        # Kill switch à -5%
    ):
        self.max_total_exposure_pct = max_total_exposure_pct
        self.max_single_position_pct = max_single_position_pct
        self.max_simultaneous_positions = max_simultaneous_positions
        self.max_same_direction = max_same_direction
        self.min_entry_interval_seconds = min_entry_interval_seconds
        self.max_drawdown_kill_pct = max_drawdown_kill_pct

        # Historique des entrées (pour anti-rafale)
        self._last_entry_time: Optional[datetime] = None

    def check_signal(
        self,
        signal: StrategySignal,
        position_size_usd: float,
        capital: float,
        open_positions: list[dict],
        drawdown_pct: float = 0.0,
        now: Optional[datetime] = None,
    ) -> RiskCheckResult:
        """
        Vérifie si un signal peut être approuvé.

        Args:
            signal: Signal de la stratégie
            position_size_usd: Taille de position demandée
            capital: Capital courant
            open_positions: Positions ouvertes
            drawdown_pct: Drawdown actuel en %
            now: Timestamp actuel

        Returns:
            RiskCheckResult avec approved=True/False
        """
        now = now or datetime.now(timezone.utc)

        # 1. Kill switch drawdown
        if drawdown_pct >= self.max_drawdown_kill_pct:
            return RiskCheckResult(
                approved=False,
                reason=f"Kill switch multi-strategy : drawdown {drawdown_pct:.1f}% "
                       f">= {self.max_drawdown_kill_pct}%",
            )

        # 2. Max positions simultanées
        if len(open_positions) >= self.max_simultaneous_positions:
            return RiskCheckResult(
                approved=False,
                reason=f"Max positions atteint ({len(open_positions)}"
                       f"/{self.max_simultaneous_positions})",
            )

        # 3. Anti-collision long/short (pas de hedge implicite)
        for pos in open_positions:
            if pos.get("direction") != signal.direction:
                return RiskCheckResult(
                    approved=False,
                    reason=f"Anti-collision : {signal.direction} bloqué, "
                           f"position {pos.get('direction')} déjà ouverte "
                           f"(stratégie {pos.get('strategy_type', '?')})",
                )

        # 4. Max même direction
        same_dir_count = sum(
            1 for pos in open_positions
            if pos.get("direction") == signal.direction
        )
        if same_dir_count >= self.max_same_direction:
            return RiskCheckResult(
                approved=False,
                reason=f"Max {signal.direction} atteint ({same_dir_count}"
                       f"/{self.max_same_direction})",
            )

        # 5. Pas de doublon de stratégie
        for pos in open_positions:
            if pos.get("strategy_type") == signal.strategy_type:
                return RiskCheckResult(
                    approved=False,
                    reason=f"Stratégie {signal.strategy_type} déjà en cours",
                )

        # 6. Exposition totale
        exposure = self.get_exposure(open_positions, capital)
        new_exposure_pct = ((exposure.total_exposure_usd + position_size_usd)
                           / capital * 100) if capital > 0 else 100

        if new_exposure_pct > self.max_total_exposure_pct:
            return RiskCheckResult(
                approved=False,
                reason=f"Exposition totale {new_exposure_pct:.1f}% "
                       f"> {self.max_total_exposure_pct}%",
                exposure_usd=exposure.total_exposure_usd,
                exposure_pct=new_exposure_pct,
            )

        # 7. Taille par position
        position_pct = (position_size_usd / capital * 100) if capital > 0 else 100
        if position_pct > self.max_single_position_pct:
            return RiskCheckResult(
                approved=False,
                reason=f"Position trop grande : {position_pct:.1f}% "
                       f"> {self.max_single_position_pct}%",
            )

        # 8. Anti-rafale (cooldown entre entrées)
        if self._last_entry_time is not None:
            elapsed = (now - self._last_entry_time).total_seconds()
            if elapsed < self.min_entry_interval_seconds:
                return RiskCheckResult(
                    approved=False,
                    reason=f"Cooldown global : {elapsed:.0f}s < "
                           f"{self.min_entry_interval_seconds}s",
                )

        return RiskCheckResult(
            approved=True,
            exposure_usd=exposure.total_exposure_usd + position_size_usd,
            exposure_pct=new_exposure_pct,
        )

    def record_entry(self, now: Optional[datetime] = None):
        """Enregistre une entrée (pour le cooldown anti-rafale)."""
        self._last_entry_time = now or datetime.now(timezone.utc)

    @staticmethod
    def get_exposure(
        open_positions: list[dict],
        capital: float,
    ) -> ExposureSnapshot:
        """Calcule l'exposition actuelle."""
        total = 0.0
        long_exp = 0.0
        short_exp = 0.0
        strategies = []

        for pos in open_positions:
            size = pos.get("position_size_usd", 0) or 0
            leverage = pos.get("leverage", 1) or 1
            effective = size * leverage
            total += effective

            if pos.get("direction") == "long":
                long_exp += effective
            else:
                short_exp += effective

            st = pos.get("strategy_type", "unknown")
            if st not in strategies:
                strategies.append(st)

        exposure_pct = (total / capital * 100) if capital > 0 else 0

        if long_exp > short_exp:
            net_dir = "long"
        elif short_exp > long_exp:
            net_dir = "short"
        else:
            net_dir = "neutral"

        return ExposureSnapshot(
            total_exposure_usd=round(total, 2),
            total_exposure_pct=round(exposure_pct, 2),
            long_exposure_usd=round(long_exp, 2),
            short_exposure_usd=round(short_exp, 2),
            num_positions=len(open_positions),
            strategies_active=strategies,
            net_direction=net_dir,
        )
