"""
Modèle TickActivityLog — Journal d'activité de chaque tick paper trading.

Enregistre CHAQUE tick du paper trading (y compris les non-trades)
pour permettre :
- Analyse de fréquence (ticks → trades ratio)
- Diagnostic des raisons de non-trade
- Agrégations journalières/horaires
- Comparaison de profils
- Qualification du style de trading

Table additive : n'affecte pas les tables existantes.
"""

from datetime import datetime
from sqlalchemy import String, Float, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TickActivityLog(Base):
    """Log d'activité pour chaque tick du paper trading."""

    __tablename__ = "tick_activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("paper_account.id"), nullable=False
    )

    # --- Contexte du tick ---
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    btc_price: Mapped[float] = mapped_column(Float, nullable=True)

    # --- Décision prise ---
    # "opened_long", "opened_short", "closed_tp", "closed_sl", "closed_signal",
    # "closed_expired", "closed_manual", "hold", "blocked", "no_decision",
    # "inactive", "no_price"
    action_taken: Mapped[str] = mapped_column(String(30), nullable=False)

    # --- Score et action du moteur de décision ---
    decision_score: Mapped[float] = mapped_column(Float, nullable=True)
    decision_action: Mapped[str] = mapped_column(String(20), nullable=True)
    decision_confidence: Mapped[str] = mapped_column(String(20), nullable=True)

    # --- Raison de non-trade (si pas d'ouverture) ---
    # Catégories : score_too_low, confidence_too_low, scenario_weak,
    #   sentiment_contradictory, adx_too_low, volume_insufficient,
    #   position_already_open, risk_blocked, daily_loss_protection,
    #   kill_switch_active, cooldown_active, max_trades_reached,
    #   decision_wait, no_decision_available, inactive, no_price, other
    reason_no_trade: Mapped[str] = mapped_column(String(50), nullable=True)
    reason_detail: Mapped[str] = mapped_column(String(500), nullable=True)

    # --- Profil de trading actif au moment du tick ---
    profile_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="conservative"
    )

    # --- Levier ---
    leverage_recommended: Mapped[float] = mapped_column(Float, nullable=True)
    leverage_final: Mapped[float] = mapped_column(Float, nullable=True)
    leverage_reason: Mapped[str] = mapped_column(String(200), nullable=True)

    # --- Position ouverte (si existante au moment du tick) ---
    had_open_position: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0
    )
    # PnL latent de la position ouverte à ce tick
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=True)

    # --- Trade associé (si un trade a été ouvert ou fermé) ---
    trade_id: Mapped[int] = mapped_column(Integer, nullable=True)

    # --- [v1.9.9] Quality gate trace — audit runtime ---
    # Persiste les métriques de qualité marché pour chaque tick.
    # Permet l'audit a posteriori : pourquoi un trade a été autorisé ou refusé.
    market_quality_score: Mapped[int] = mapped_column(Integer, nullable=True)
    volume_ratio: Mapped[float] = mapped_column(Float, nullable=True)
    price_position_pct: Mapped[float] = mapped_column(Float, nullable=True)
    range_width_atr: Mapped[float] = mapped_column(Float, nullable=True)
    micro_trend_score: Mapped[int] = mapped_column(Integer, nullable=True)
    vwap_distance_pct: Mapped[float] = mapped_column(Float, nullable=True)
    quality_gate_passed: Mapped[bool] = mapped_column(Integer, nullable=True)  # 0/1
    quality_gate_reason: Mapped[str] = mapped_column(String(500), nullable=True)

    # --- [v2.0.0] Economic viability gate trace ---
    # Persiste l'évaluation économique pré-entrée pour chaque tick.
    # Permet de prouver qu'un trade a été refusé car non-viable après frais.
    estimated_round_trip_cost: Mapped[float] = mapped_column(Float, nullable=True)
    min_capture_required_pct: Mapped[float] = mapped_column(Float, nullable=True)
    economic_gate_passed: Mapped[bool] = mapped_column(Integer, nullable=True)  # 0/1
    # [v2.0.0] Catégorie de rejet — permet l'agrégation des raisons de refus.
    # Valeurs : "economic", "structure", "volume", "no_trade_zone", "cooldown",
    #           "score", "risk", "max_trades", None (si pas de rejet)
    rejection_category: Mapped[str] = mapped_column(String(30), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TickActivityLog(id={self.id}, action={self.action_taken}, "
            f"price={self.btc_price}, profile={self.profile_type})>"
        )

