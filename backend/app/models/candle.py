"""
Modèle Candle : représente un chandelier (bougie) OHLCV.

OHLCV = Open, High, Low, Close, Volume
C'est le format standard des données de marché financier.

Chaque ligne représente une période de temps (1min, 5min, 1h, 1d...).

Équivalent Java JPA :
    @Entity
    @Table(name = "candles")
    public class Candle { ... }
"""

from datetime import datetime
from sqlalchemy import String, Float, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Candle(Base):
    """
    Table des chandeliers (bougies) OHLCV.
    
    Stocke l'historique des prix pour l'analyse technique.
    """
    
    # Nom de la table en base de données
    __tablename__ = "candles"
    
    # ============================================================
    # COLONNES
    # ============================================================
    
    # Clé primaire auto-incrémentée
    # Utilisation de Integer au lieu de BigInteger pour compatibilité SQLite
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    
    # Symbole de la paire (ex: "BTC/USD", "BTC/EUR")
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    
    # Intervalle de temps (ex: "1m", "5m", "1h", "1d")
    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False
    )
    
    # Timestamp de début de la bougie
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    
    # Prix d'ouverture (premier prix de la période)
    open_price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )
    
    # Prix le plus haut de la période
    high_price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )
    
    # Prix le plus bas de la période
    low_price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )
    
    # Prix de fermeture (dernier prix de la période)
    close_price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )
    
    # Volume échangé pendant la période
    volume: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )
    
    # Source des données (ex: "manual", "coingecko", "binance")
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual"
    )
    
    # Date d'insertion en base (pour audit)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    
    # ============================================================
    # INDEX
    # ============================================================
    # Index unique pour éviter les doublons
    # Une seule bougie par (symbol, timeframe, timestamp)
    
    __table_args__ = (
        Index(
            "ix_candles_symbol_timeframe_timestamp",
            "symbol",
            "timeframe",
            "timestamp",
            unique=True
        ),
    )
    
    def __repr__(self) -> str:
        """Représentation textuelle pour le debug."""
        return (
            f"<Candle(symbol={self.symbol}, timeframe={self.timeframe}, "
            f"timestamp={self.timestamp}, close={self.close_price})>"
        )