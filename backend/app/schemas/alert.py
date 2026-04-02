"""
Schémas Pydantic pour les alertes.

Types de condition supportés :
- price    : prix close (above/below)
- rsi      : RSI(14) (above/below)
- macd_hist: histogramme MACD (above/below)
- score    : score composite signal (above/below)

Opérateurs :
- above : valeur >= seuil → déclenche
- below : valeur <= seuil → déclenche
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class ConditionType(str, Enum):
    PRICE = "price"
    RSI = "rsi"
    MACD_HIST = "macd_hist"
    SCORE = "score"


class Operator(str, Enum):
    ABOVE = "above"
    BELOW = "below"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    DISABLED = "disabled"


class AlertCreate(BaseModel):
    """Schéma pour créer une alerte."""
    symbol: str = Field(default="BTC/USD", max_length=20)
    timeframe: str = Field(default="4h", max_length=10)
    condition_type: ConditionType
    operator: Operator
    threshold: float
    message: Optional[str] = None
    recurring: bool = False


class AlertUpdate(BaseModel):
    """Schéma pour modifier une alerte (tous les champs optionnels)."""
    condition_type: Optional[ConditionType] = None
    operator: Optional[Operator] = None
    threshold: Optional[float] = None
    message: Optional[str] = None
    status: Optional[AlertStatus] = None
    recurring: Optional[bool] = None


class AlertResponse(BaseModel):
    """Schéma de réponse pour une alerte."""
    id: int
    symbol: str
    timeframe: str
    condition_type: str
    operator: str
    threshold: float
    message: Optional[str]
    status: str
    recurring: bool
    created_at: Optional[datetime]
    triggered_at: Optional[datetime]
    triggered_value: Optional[float]

    model_config = {"from_attributes": True}


class AlertNotification(BaseModel):
    """Notification émise quand une alerte se déclenche."""
    alert_id: int
    condition_type: str
    operator: str
    threshold: float
    current_value: float
    message: str
    triggered_at: datetime


class AlertCheckResponse(BaseModel):
    """Réponse du check d'alertes (endpoint polling)."""
    checked: int = Field(description="Nombre d'alertes évaluées")
    triggered: int = Field(description="Nombre d'alertes déclenchées")
    notifications: list[AlertNotification] = Field(
        default_factory=list,
        description="Notifications pour les alertes déclenchées"
    )

