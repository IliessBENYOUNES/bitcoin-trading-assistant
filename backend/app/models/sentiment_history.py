"""
Modèle SentimentHistory : stocke le sentiment historique quotidien.

Sources de données :
- Fear & Greed Index (Alternative.me) : score 0-100, depuis février 2018
- CryptoCompare News (free tier) : titres + catégories, depuis 2015

Le sentiment historique permet au moteur de décision de fonctionner
en mode COMPLET (technique + sentiment) lors des backtests historiques,
au lieu du mode dégradé 100% technique.
"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SentimentHistory(Base):
    """
    Table du sentiment historique quotidien.

    Stocke un score de sentiment par jour et par source,
    normalisé sur une échelle -100 à +100 pour compatibilité
    avec le moteur de décision existant.
    """

    __tablename__ = "sentiment_history"

    # Clé primaire auto-incrémentée
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # Date du point de données (un par jour)
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Source du sentiment (ex: "fear_and_greed", "cryptocompare_news")
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Score brut tel que fourni par la source
    # Fear & Greed : 0-100 (0=peur extrême, 100=avidité extrême)
    raw_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    # Score normalisé -100 à +100 pour compatibilité avec le moteur de décision
    # Formule Fear & Greed : (raw - 50) * 2 → 0=neutre, -100=peur extrême, +100=avidité extrême
    normalized_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    # Label textuel (ex: "Extreme Fear", "Greed", "Neutral")
    label: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
    )

    # Données brutes JSON de la source (pour traçabilité)
    raw_data: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    # Date d'insertion en base
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Index unique : un seul point par (date, source)
    __table_args__ = (
        Index(
            "ix_sentiment_history_date_source",
            "date",
            "source",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SentimentHistory(date={self.date}, source={self.source}, "
            f"raw={self.raw_score}, norm={self.normalized_score}, label={self.label})>"
        )

