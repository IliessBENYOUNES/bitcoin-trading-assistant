"""
Schémas Pydantic pour le Risk Management Engine.

Le risk engine évalue si un trade proposé respecte les limites de risque :
- Stop-loss / Take-profit calculés
- Position sizing (% max du portefeuille)
- Perte journalière max
- Kill switch
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class StopLossType(str, Enum):
    """Type de stop-loss."""
    FIXED = "fixed"         # % fixe du prix d'entrée
    TRAILING = "trailing"   # % suiveur (suit le prix à la hausse)
    ATR = "atr"             # Basé sur l'ATR (Average True Range)


class RiskConfigCreate(BaseModel):
    """Schéma pour créer/mettre à jour la configuration de risque."""
    stop_loss_type: StopLossType = Field(
        default=StopLossType.FIXED,
        description="Type de stop-loss (fixed, trailing, atr)"
    )
    stop_loss_pct: float = Field(
        default=5.0, ge=0.1, le=50.0,
        description="Stop-loss en % (0.1 à 50)"
    )
    take_profit_pct: float = Field(
        default=10.0, ge=0.1, le=100.0,
        description="Take-profit en % (0.1 à 100)"
    )
    max_position_pct: float = Field(
        default=25.0, ge=1.0, le=100.0,
        description="% max du portefeuille par position (1 à 100)"
    )
    total_portfolio_value: float = Field(
        default=10000.0, ge=0.0,
        description="Valeur totale du portefeuille en USD"
    )
    max_daily_loss_pct: float = Field(
        default=3.0, ge=0.1, le=50.0,
        description="Perte journalière max en % du portefeuille"
    )


class RiskConfigUpdate(BaseModel):
    """Schéma pour mettre à jour partiellement la configuration de risque."""
    stop_loss_type: Optional[StopLossType] = None
    stop_loss_pct: Optional[float] = Field(default=None, ge=0.1, le=50.0)
    take_profit_pct: Optional[float] = Field(default=None, ge=0.1, le=100.0)
    max_position_pct: Optional[float] = Field(default=None, ge=1.0, le=100.0)
    total_portfolio_value: Optional[float] = Field(default=None, ge=0.0)
    max_daily_loss_pct: Optional[float] = Field(default=None, ge=0.1, le=50.0)


class RiskConfigResponse(BaseModel):
    """Réponse avec la configuration de risque complète."""
    id: int
    stop_loss_type: str
    stop_loss_pct: float
    take_profit_pct: float
    max_position_pct: float
    total_portfolio_value: float
    max_daily_loss_pct: float
    daily_loss_current: float
    kill_switch_active: bool
    kill_switch_triggered_at: Optional[str] = None
    kill_switch_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class RiskEvaluation(BaseModel):
    """
    Résultat de l'évaluation d'un trade proposé par le risk engine.

    Le risk engine vérifie :
    1. Le kill switch n'est pas actif
    2. La perte journalière n'est pas dépassée
    3. La taille de position est dans les limites
    Et calcule :
    - Le prix de stop-loss
    - Le prix de take-profit
    - La taille max de position
    """
    allowed: bool = Field(
        ..., description="Le trade est-il autorisé par le risk engine ?"
    )
    original_action: str = Field(
        ..., description="Action originale proposée (acheter/vendre/attendre)"
    )
    adjusted_action: str = Field(
        ..., description="Action ajustée par le risk engine (peut devenir 'attendre' si bloqué)"
    )
    stop_loss_price: Optional[float] = Field(
        None, description="Prix de stop-loss calculé"
    )
    take_profit_price: Optional[float] = Field(
        None, description="Prix de take-profit calculé"
    )
    max_position_size_usd: Optional[float] = Field(
        None, description="Taille max de la position en USD"
    )
    risk_reward_ratio: Optional[float] = Field(
        None, description="Ratio risque/récompense"
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Raisons de la décision du risk engine"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Avertissements (sans bloquer le trade)"
    )


class RiskStatus(BaseModel):
    """
    État temps réel du risk engine.

    Donne une vue d'ensemble de l'exposition au risque.
    """
    config: RiskConfigResponse = Field(
        ..., description="Configuration de risque courante"
    )
    kill_switch_active: bool = Field(
        ..., description="Kill switch actif ?"
    )
    daily_loss_current: float = Field(
        ..., description="Perte cumulée du jour en USD"
    )
    daily_loss_limit_usd: float = Field(
        ..., description="Limite de perte journalière en USD"
    )
    daily_loss_pct: float = Field(
        ..., description="Perte du jour en % du portefeuille"
    )
    daily_loss_remaining_usd: float = Field(
        ..., description="Marge restante avant kill switch en USD"
    )
    max_position_size_usd: float = Field(
        ..., description="Taille max de position en USD"
    )
    risk_level: str = Field(
        ..., description="Niveau de risque global : safe, caution, danger, blocked"
    )
    detail: str = Field(
        ..., description="Description lisible de l'état du risque"
    )

