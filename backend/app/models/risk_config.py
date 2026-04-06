"""
Modèle RiskConfig : configuration de la gestion du risque.

Stocke les paramètres de gestion du risque pour le trading :
- Stop-loss / Take-profit
- Limites d'exposition (% max portefeuille par position)
- Limite de perte journalière
- Kill switch (arrêt d'urgence)

Ce modèle est un singleton de facto : une seule ligne de configuration
dans la table. On utilise un id fixe (1) pour simplifier.
"""

from datetime import datetime, date
from sqlalchemy import String, Float, DateTime, Integer, Boolean, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class RiskConfig(Base):
    """Table de configuration du risk management (singleton)."""

    __tablename__ = "risk_config"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # --- Stop-loss ---
    # Type de stop-loss : fixed (% fixe), trailing (suiveur), atr (basé sur ATR)
    stop_loss_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="fixed"
    )
    # Pourcentage de stop-loss (ex: 5.0 = 5%)
    stop_loss_pct: Mapped[float] = mapped_column(
        Float, nullable=False, default=5.0
    )

    # --- Take-profit ---
    # Pourcentage de take-profit (ex: 10.0 = 10%)
    take_profit_pct: Mapped[float] = mapped_column(
        Float, nullable=False, default=10.0
    )

    # --- Position sizing ---
    # % max du portefeuille par position (ex: 25.0 = 25%)
    max_position_pct: Mapped[float] = mapped_column(
        Float, nullable=False, default=25.0
    )

    # Valeur totale du portefeuille en USD
    total_portfolio_value: Mapped[float] = mapped_column(
        Float, nullable=False, default=10000.0
    )

    # --- Daily loss limit ---
    # Perte journalière max en % du portefeuille (ex: 3.0 = 3%)
    max_daily_loss_pct: Mapped[float] = mapped_column(
        Float, nullable=False, default=3.0
    )
    # Perte cumulée du jour en USD (remise à zéro chaque jour)
    daily_loss_current: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    # Date du dernier reset du compteur de perte journalière
    daily_loss_reset_date: Mapped[date] = mapped_column(
        Date, nullable=True
    )

    # --- Kill switch ---
    # Si True, TOUTES les opérations de trading sont bloquées
    kill_switch_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Date/heure du déclenchement du kill switch (NULL si jamais déclenché)
    kill_switch_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Raison du déclenchement du kill switch
    kill_switch_reason: Mapped[str] = mapped_column(
        String(200), nullable=True
    )

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<RiskConfig(id={self.id}, SL={self.stop_loss_pct}% {self.stop_loss_type}, "
            f"TP={self.take_profit_pct}%, max_pos={self.max_position_pct}%, "
            f"kill_switch={'ON' if self.kill_switch_active else 'OFF'})>"
        )

