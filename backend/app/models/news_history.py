"""
Modèle NewsHistory : stocke les articles de news crypto en base de données.

Ce modèle permet de :
1. Conserver un historique complet des news collectées via RSS
2. Constituer un corpus de sentiment "news" exploitable en backtest
3. Préparer le terrain pour le ML (v3.0+) avec des articles annotés

Sources actuelles :
- CoinTelegraph RSS (gratuit)
- CoinDesk RSS (gratuit)
- Bitcoin Magazine RSS (gratuit)
- CryptoCompare News API (gratuit, tier free — ajouté v1.2.3b)

Chaque article est stocké avec son sentiment (positive/negative/neutral),
son impact (high/medium/low), et les mots-clés détectés.
Le dédoublonnage se fait sur l'URL (unique par source).
"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class NewsHistory(Base):
    """
    Table de l'historique des news crypto.

    Stocke chaque article avec son analyse de sentiment,
    dédoublonné par URL pour garantir l'idempotence.
    """

    __tablename__ = "news_history"

    # Clé primaire auto-incrémentée
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # Titre de l'article
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # URL de l'article (unique pour le dédoublonnage)
    url: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
    )

    # Source (CoinTelegraph, CoinDesk, Bitcoin Magazine, CryptoCompare)
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Description / résumé de l'article
    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    # Date de publication
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Sentiment classifié (positive/negative/neutral)
    sentiment: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="neutral",
    )

    # Niveau d'impact (high/medium/low)
    impact: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="low",
    )

    # Score de sentiment individuel normalisé -100 à +100
    # positive → +50, negative → -50, neutral → 0
    # Pondéré par impact : high ×1.5, medium ×1.0, low ×0.5
    sentiment_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    # Mots-clés détectés (JSON array sérialisé)
    keywords: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    # Date d'insertion en base
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Index unique sur l'URL pour le dédoublonnage
    # Si URL est null, on utilise (source, title, published_at)
    __table_args__ = (
        Index(
            "ix_news_history_url",
            "url",
            unique=True,
            sqlite_where=url.isnot(None),  # Index partiel : seulement quand url n'est pas null
        ),
        Index(
            "ix_news_history_source_date",
            "source",
            "published_at",
        ),
        Index(
            "ix_news_history_published_at",
            "published_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<NewsHistory(title={self.title[:40]}..., source={self.source}, "
            f"sentiment={self.sentiment}, impact={self.impact}, "
            f"published_at={self.published_at})>"
        )

