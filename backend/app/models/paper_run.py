"""
Modèle PaperRun — Campagnes de validation paper trading.

Permet d'identifier et séparer les différentes campagnes de test
(ex: "pré-recalibrage", "post-recalibrage") pour comparaison.

v1.9.0 — Additif, rétrocompatible.
"""

from datetime import datetime
from sqlalchemy import String, Float, DateTime, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PaperRun(Base):
    """Campagne de validation paper trading."""

    __tablename__ = "paper_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Nom de la campagne (ex: "post-recalibrage-v1.8.1")
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Profil utilisé pour cette campagne
    profile_type: Mapped[str] = mapped_column(String(20), nullable=False, default="scalping")

    # Statut : running, completed, aborted
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")

    # Snapshot JSON des paramètres profil au démarrage
    config_snapshot: Mapped[str] = mapped_column(Text, nullable=True)

    # Compteurs (mis à jour au fur et à mesure)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_ticks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<PaperRun(id={self.id}, name='{self.name}', status={self.status}, "
            f"trades={self.total_trades})>"
        )

