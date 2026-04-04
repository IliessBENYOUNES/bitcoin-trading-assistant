"""
Schemas Pydantic pour le module de backtesting.

Le backtesting rejoue le moteur de decision sur l'historique de candles
en simulant des positions achat/vente pour calculer des metriques de performance.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class TradeDirection(str, Enum):
    """Direction d'un trade simule."""
    BUY = "buy"
    SELL = "sell"


class BacktestConfig(BaseModel):
    """Configuration d'un backtest."""
    symbol: str = Field(default="BTC/USD", description="Paire de trading")
    timeframe: str = Field(default="4h", description="Timeframe des candles")
    start_days_ago: float = Field(
        default=30, ge=1, le=365,
        description="Debut du backtest (N jours dans le passe)"
    )
    initial_capital: float = Field(
        default=10000.0, gt=0,
        description="Capital initial en USD"
    )


class BacktestTradeItem(BaseModel):
    """Un trade simule dans le backtest."""
    entry_ts: str = Field(..., description="Timestamp d'entree ISO")
    exit_ts: Optional[str] = Field(None, description="Timestamp de sortie ISO")
    direction: TradeDirection = Field(..., description="Direction du trade")
    entry_price: float = Field(..., description="Prix d'entree")
    exit_price: Optional[float] = Field(None, description="Prix de sortie")
    pnl: float = Field(default=0.0, description="Profit/Loss en USD")
    pnl_pct: float = Field(default=0.0, description="Profit/Loss en %")
    reason_entry: str = Field(default="", description="Raison de l'entree")
    reason_exit: str = Field(default="", description="Raison de la sortie")
    duration_hours: float = Field(default=0.0, description="Duree du trade en heures")


class BacktestMetrics(BaseModel):
    """Metriques de performance du backtest."""
    total_trades: int = Field(default=0, description="Nombre total de trades")
    winning_trades: int = Field(default=0, description="Trades gagnants")
    losing_trades: int = Field(default=0, description="Trades perdants")
    win_rate: float = Field(default=0.0, description="Taux de reussite (0-1)")
    net_pnl: float = Field(default=0.0, description="PnL net en USD")
    net_pnl_pct: float = Field(default=0.0, description="PnL net en %")
    profit_factor: float = Field(
        default=0.0,
        description="Ratio gains bruts / pertes brutes"
    )
    max_drawdown_pct: float = Field(
        default=0.0,
        description="Drawdown maximum en %"
    )
    avg_trade_pnl: float = Field(default=0.0, description="PnL moyen par trade en USD")
    avg_trade_duration_hours: float = Field(
        default=0.0, description="Duree moyenne des trades en heures"
    )
    sharpe_ratio: float = Field(
        default=0.0,
        description="Ratio de Sharpe (rendement/risque)"
    )
    buy_and_hold_pnl_pct: float = Field(
        default=0.0,
        description="PnL Buy & Hold en % (benchmark)"
    )
    overfitting_warning: bool = Field(
        default=False,
        description="True si risque de suroptimisation detecte"
    )


class EquityPoint(BaseModel):
    """Un point de la courbe d'equity."""
    ts: str = Field(..., description="Timestamp ISO")
    capital: float = Field(..., description="Capital a cet instant")
    drawdown_pct: float = Field(default=0.0, description="Drawdown courant en %")


class BacktestMeta(BaseModel):
    """Metadonnees du backtest."""
    symbol: str
    timeframe: str
    start_ts: str
    end_ts: str
    initial_capital: float
    candles_analyzed: int = 0
    decisions_made: int = 0
    duration_seconds: float = 0.0


class BacktestResponse(BaseModel):
    """Reponse complete d'un backtest."""
    meta: BacktestMeta
    metrics: BacktestMetrics
    trades: list[BacktestTradeItem] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    summary: str = Field(default="", description="Resume lisible du backtest")

