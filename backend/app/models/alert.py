"""
Modèle Alert : représente une alerte configurable par l'utilisateur.

Une alerte surveille une condition sur le marché (prix, RSI, MACD, score)
et se déclenche quand la condition est remplie.

Chaque alerte a :
- Une condition (type + opérateur + seuil)
- Un état (active, triggered, disabled)
- Un historique de déclenchement (triggered_at, triggered_value)
"""

from datetime import datetime
from sqlalchemy import String, Float, DateTime, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Alert(Base):
    """Table des alertes configurées par l'utilisateur."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # Symbole surveillé (ex: "BTC/USD")
    symbol: Mapped[str] = mapped_column(
        String(20), nullable=False, default="BTC/USD"
    )

    # Timeframe pour l'évaluation (ex: "4h")
    timeframe: Mapped[str] = mapped_column(
        String(10), nullable=False, default="4h"
    )

    # Type de condition : price, rsi, macd_hist, score
    condition_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    # Opérateur de comparaison : above, below, cross_above, cross_below
    operator: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    # Valeur seuil
    threshold: Mapped[float] = mapped_column(
        Float, nullable=False
    )

    # Message personnalisé (optionnel)
    message: Mapped[str] = mapped_column(
        Text, nullable=True
    )

    # État : active, triggered, disabled
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )

    # Si True, l'alerte se réarme après déclenchement (sinon one-shot)
    recurring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Valeur au moment du déclenchement
    triggered_value: Mapped[float] = mapped_column(
        Float, nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<Alert(id={self.id}, {self.condition_type} {self.operator} {self.threshold}, "
            f"status={self.status})>"
        )

