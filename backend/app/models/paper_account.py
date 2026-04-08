"""
Modèles Paper Trading : compte virtuel + journal de trades.

PaperAccount est un singleton (comme RiskConfig) : une seule ligne.
PaperTrade enregistre chaque trade simulé (ouverture, fermeture, PnL).

Le paper trading simule le trading en conditions réelles sans argent réel.
"""

from datetime import datetime
from sqlalchemy import String, Float, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PaperAccount(Base):
    """Compte paper trading (singleton — une seule ligne en DB)."""

    __tablename__ = "paper_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Capital ---
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)
    current_capital: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)

    # --- Performance cumulée ---
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, nullable=True)

    # --- Configuration ---
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_open_duration_hours: Mapped[float] = mapped_column(Float, nullable=False, default=168.0)

    # Profil de trading actif (conservative, balanced, aggressive) — v1.5
    active_profile: Mapped[str] = mapped_column(
        String(20), nullable=False, default="conservative"
    )

    # [v1.7] Nombre max de positions ouvertes simultanément
    # 1 = comportement mono-position (rétrocompatible)
    # >1 = mode multi-slot (1 position par slot/profil)
    max_open_positions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    # Prix BTC au moment du reset/création (pour calcul buy & hold)
    btc_price_at_start: Mapped[float] = mapped_column(Float, nullable=True)

    # Plus haut capital atteint (pour calcul drawdown)
    peak_capital: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        onupdate=datetime.utcnow, nullable=False
    )

    # Relation vers les trades
    trades: Mapped[list["PaperTrade"]] = relationship(
        "PaperTrade", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<PaperAccount(id={self.id}, capital={self.current_capital:.2f}, "
            f"pnl={self.total_pnl:.2f}, trades={self.total_trades}, "
            f"active={'ON' if self.is_active else 'OFF'})>"
        )


class PaperTrade(Base):
    """Trade paper (journal de chaque position simulée)."""

    __tablename__ = "paper_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("paper_account.id"), nullable=False
    )

    # --- Position ---
    # Status : open, closed_tp, closed_sl, closed_signal, closed_expired, closed_manual
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    # Direction : long (achat) ou short (vente)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, default="long")

    # --- Prix ---
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=True)
    stop_loss_price: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit_price: Mapped[float] = mapped_column(Float, nullable=False)

    # Pour le trailing stop : plus haut prix atteint depuis l'entrée (long)
    highest_price_since_entry: Mapped[float] = mapped_column(Float, nullable=True)
    # Pour le trailing stop : plus bas prix atteint depuis l'entrée (short)
    lowest_price_since_entry: Mapped[float] = mapped_column(Float, nullable=True)

    # --- Sizing ---
    position_size_usd: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Levier (v1.5 — additif, default 1.0 = comportement identique à l'existant) ---
    leverage: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    effective_size_usd: Mapped[float] = mapped_column(Float, nullable=True)
    leverage_reason: Mapped[str] = mapped_column(String(200), nullable=True)

    # --- Profil de trading au moment de l'entrée (v1.5) ---
    profile_type: Mapped[str] = mapped_column(String(20), nullable=True)

    # --- Slot multi-position (v1.7) ---
    # Identifie à quel "slot" (profil parallèle) cette position appartient.
    # Chaque slot ne peut avoir qu'une seule position ouverte.
    # None = mono-position (rétrocompatible)
    slot: Mapped[str] = mapped_column(String(20), nullable=True)

    # --- PnL ---
    pnl: Mapped[float] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=True)

    # --- Raisons ---
    entry_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    exit_reason: Mapped[str] = mapped_column(String(500), nullable=True)
    decision_score: Mapped[float] = mapped_column(Float, nullable=True)

    # --- Timestamps ---
    entry_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    exit_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_hours: Mapped[float] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        onupdate=datetime.utcnow, nullable=False
    )

    # Relation inverse
    account: Mapped["PaperAccount"] = relationship(
        "PaperAccount", back_populates="trades"
    )

    def __repr__(self) -> str:
        pnl_str = f"{self.pnl:+.2f}" if self.pnl is not None else "open"
        return (
            f"<PaperTrade(id={self.id}, {self.direction} @ {self.entry_price:.0f}, "
            f"status={self.status}, pnl={pnl_str})>"
        )

