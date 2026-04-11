"""
Modèle LearningSignal + StrategyFeedback — Couche d'apprentissage explicable.

LearningSignal : un échantillon d'apprentissage par trade fermé, avec les features
contextuelles au moment de l'entrée et le résultat observé.

StrategyFeedback : ajustements de paramètres proposés par le learning, avec
versioning, explicabilité et capacité de rollback.

v1.9.0 — Additif, rétrocompatible. Table dédiée, n'impacte rien d'existant.
"""

from datetime import datetime
from sqlalchemy import String, Float, DateTime, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class LearningSignal(Base):
    """
    Échantillon d'apprentissage généré à la fermeture de chaque trade.

    Stocke le contexte d'entrée + le résultat pour permettre au LearningService
    de calculer des statistiques par pattern et proposer des ajustements.
    """

    __tablename__ = "learning_signal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Lien vers le trade source
    trade_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # --- Features contextuelles au moment de l'entrée ---
    score: Mapped[float] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=True)  # long / short
    slot: Mapped[str] = mapped_column(String(20), nullable=True)
    profile_type: Mapped[str] = mapped_column(String(20), nullable=True)
    leverage: Mapped[float] = mapped_column(Float, nullable=True)
    entry_price: Mapped[float] = mapped_column(Float, nullable=True)

    # Indicateurs au moment de l'entrée (best-effort, nullable)
    rsi_value: Mapped[float] = mapped_column(Float, nullable=True)
    macd_hist: Mapped[float] = mapped_column(Float, nullable=True)
    volatility_atr: Mapped[float] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[float] = mapped_column(Float, nullable=True)

    # Contexte cooldown / intervalle
    time_since_last_trade_min: Mapped[float] = mapped_column(Float, nullable=True)
    cooldown_configured_min: Mapped[float] = mapped_column(Float, nullable=True)

    # Scalping reversal ?
    was_reversal: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)

    # --- Résultat (outcome) ---
    exit_type: Mapped[str] = mapped_column(String(30), nullable=True)
    pnl_brut: Mapped[float] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=True)
    duration_minutes: Mapped[float] = mapped_column(Float, nullable=True)
    was_profitable: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)

    # [v1.9.1] Analyse économique
    cost_estimated: Mapped[float] = mapped_column(Float, nullable=True)
    pnl_net_estimated: Mapped[float] = mapped_column(Float, nullable=True)
    # useful / insignificant / churn / loss_useful / loss_destructive
    usefulness_category: Mapped[str] = mapped_column(String(30), nullable=True)

    # [v2.0.2] Contexte BTC — corrélation prix / trade
    # Tendance BTC à l'entrée (up / down / flat) — direction de la bougie couvrant l'entrée
    btc_trend_at_entry: Mapped[str] = mapped_column(String(10), nullable=True)
    # Variation BTC % entre entry et exit
    btc_move_during_pct: Mapped[float] = mapped_column(Float, nullable=True)
    # Variation BTC % dans la fenêtre post-exit (1 bougie après)
    btc_move_after_exit_pct: Mapped[float] = mapped_column(Float, nullable=True)
    # 1 si le BTC a bougé favorablement après un stale exit
    missed_favorable_move: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    # % du mouvement BTC capturé par ce trade
    capture_efficiency_pct: Mapped[float] = mapped_column(Float, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<LearningSignal(trade={self.trade_id}, dir={self.direction}, "
            f"exit={self.exit_type}, pnl={self.pnl_brut})>"
        )


class StrategyFeedback(Base):
    """
    Ajustement de paramètre proposé ou appliqué par le LearningService.

    Chaque ligne = une recommandation d'ajustement sur un paramètre de trading.
    Le versioning permet de tracer l'historique et de rollback.
    """

    __tablename__ = "strategy_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Quel paramètre est ajusté
    parameter_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # Ex: "buy_threshold", "trailing_stop_pct", "cooldown_minutes"

    # Valeurs
    original_value: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_value: Mapped[float] = mapped_column(Float, nullable=False)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)

    # Bornes de sécurité
    min_allowed: Mapped[float] = mapped_column(Float, nullable=True)
    max_allowed: Mapped[float] = mapped_column(Float, nullable=True)

    # Explication textuelle (explicabilité obligatoire)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Ex: "les setups scalping long avec score 20-25 ont été destructeurs sur 40 trades → seuil relevé"

    # Données sous-jacentes
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate_observed: Mapped[float] = mapped_column(Float, nullable=True)
    avg_pnl_observed: Mapped[float] = mapped_column(Float, nullable=True)

    # Versioning et activation
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    # 0 = recommandation (shadow), 1 = appliqué

    # Mode : "shadow" | "applied" | "rolled_back"
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="shadow")

    # Profil ciblé
    profile_type: Mapped[str] = mapped_column(String(20), nullable=False, default="scalping")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyFeedback({self.parameter_name}: {self.original_value}→{self.suggested_value}, "
            f"mode={self.mode}, v{self.version})>"
        )

