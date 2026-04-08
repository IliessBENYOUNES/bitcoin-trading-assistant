"""
Schémas Pydantic pour le modèle de coûts de trading.

Ces schémas sont utilisés pour la transparence des métriques brut/net
dans le paper trading, le backtest et l'audit de vérité.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class CostPresetType(str, Enum):
    """Presets de coûts disponibles."""
    OPTIMISTIC = "optimistic"
    REALISTIC = "realistic"
    STRESSED = "stressed"


class TradingCostConfig(BaseModel):
    """Configuration du modèle de coûts."""
    maker_fee_pct: float = Field(..., description="Frais maker en %")
    taker_fee_pct: float = Field(..., description="Frais taker en %")
    spread_pct: float = Field(..., description="Spread estimé en %")
    slippage_pct: float = Field(..., description="Slippage estimé en %")
    name: str = Field(..., description="Nom du preset")
    round_trip_cost_pct: float = Field(..., description="Coût total aller-retour en %")


class TradingCostImpact(BaseModel):
    """Impact des coûts sur un PnL individuel."""
    gross_pnl: float = Field(..., description="PnL brut (sans frais)")
    total_costs: float = Field(..., description="Coûts totaux en USD")
    net_pnl: float = Field(..., description="PnL net (après frais)")
    cost_drag_pct: float = Field(..., description="Drag des coûts en % du capital")


class CostAuditMetrics(BaseModel):
    """Métriques brut/net complètes pour un ensemble de trades."""
    total_trades: int = Field(default=0, description="Nombre de trades")
    gross_pnl: float = Field(default=0, description="PnL brut total")
    total_costs: float = Field(default=0, description="Coûts totaux")
    net_pnl: float = Field(default=0, description="PnL net total")
    cost_drag_pct: float = Field(default=0, description="Drag moyen des coûts en %")
    gross_expectancy: float = Field(default=0, description="Expectancy brute par trade")
    net_expectancy: float = Field(default=0, description="Expectancy nette par trade")
    gross_profit_factor: float = Field(default=0, description="Profit factor brut")
    net_profit_factor: float = Field(default=0, description="Profit factor net")
    gross_avg_trade: float = Field(default=0, description="PnL moyen brut par trade")
    net_avg_trade: float = Field(default=0, description="PnL moyen net par trade")
    gross_win_rate: float = Field(default=0, description="Win rate brut (%)")
    net_win_rate: float = Field(default=0, description="Win rate net (%)")
    cost_model: str = Field(default="realistic", description="Nom du cost model utilisé")


class CostPresetsResponse(BaseModel):
    """Réponse listant les presets disponibles."""
    presets: list[TradingCostConfig] = Field(default_factory=list)

