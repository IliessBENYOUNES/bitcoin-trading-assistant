"""
LearningService — Couche d'apprentissage explicable.

Analyse les LearningSignal stockés pour :
1. Identifier les patterns gagnants / perdants
2. Suggérer des ajustements de paramètres
3. Expliquer chaque suggestion
4. Fonctionner en mode shadow (recommandation) avant application

Pas de ML opaque. Statistiques descriptives simples, bornées, réversibles.

v1.9.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.learning import LearningSignal, StrategyFeedback
from app.models.paper_account import PaperTrade, PaperAccount
from app.services.trading_profile_service import PROFILE_PRESETS
from app.schemas.learning import (
    LearningDatasetStats,
    PatternInsight,
    LearningAnalysisResponse,
    StrategyFeedbackItem,
    LearningVersionHistory,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Bornes de sécurité absolues — ne peuvent JAMAIS être dépassées
# ═══════════════════════════════════════════════════════════════════════════
SAFETY_BOUNDS = {
    "buy_threshold": (5, 60),
    "sell_threshold": (5, 60),
    "trailing_stop_activation_pct": (0.02, 0.5),
    "trailing_stop_pct": (0.03, 0.5),
    "stale_exit_minutes": (3, 60),
    "cooldown_minutes": (0.5, 30),
    "min_score": (3, 50),
    "max_leverage": (1.0, 5.0),
    "profit_take_pct": (0.1, 5.0),
    "loss_cut_pct": (0.1, 5.0),
}

# Nombre minimum d'échantillons pour qu'un pattern soit significatif
MIN_SAMPLES = 10


class LearningService:
    """
    Service d'apprentissage explicable basé sur les données en base.

    Fonctionnement :
    1. record_sample() — enregistre un LearningSignal à chaque fermeture de trade
    2. analyze() — analyse les patterns et suggère des ajustements
    3. get_suggestions() — retourne les ajustements en mode shadow
    4. apply_adjustment() — promeut un ajustement (avec rollback possible)
    """

    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # ENREGISTREMENT DES ÉCHANTILLONS
    # ================================================================

    def record_sample(
        self,
        trade: PaperTrade,
        time_since_last_trade_min: Optional[float] = None,
        cooldown_configured_min: Optional[float] = None,
        was_reversal: bool = False,
    ) -> Optional[LearningSignal]:
        """
        Enregistre un échantillon d'apprentissage à la fermeture d'un trade.

        Appelé par PaperTradingService._close_position().
        """
        if trade is None or trade.pnl is None:
            return None

        duration_min = trade.duration_hours * 60 if trade.duration_hours else None

        sample = LearningSignal(
            trade_id=trade.id,
            score=trade.decision_score,
            confidence=None,  # sera enrichi si disponible
            direction=trade.direction,
            slot=trade.slot,
            profile_type=trade.profile_type,
            leverage=trade.leverage,
            entry_price=trade.entry_price,
            exit_type=trade.status,
            pnl_brut=trade.pnl,
            pnl_pct=trade.pnl_pct,
            duration_minutes=duration_min,
            was_profitable=1 if trade.pnl >= 0 else 0,
            was_reversal=1 if was_reversal else 0,
            time_since_last_trade_min=time_since_last_trade_min,
            cooldown_configured_min=cooldown_configured_min,
        )
        self.db.add(sample)
        try:
            self.db.commit()
            self.db.refresh(sample)
            return sample
        except Exception as e:
            logger.error(f"Erreur enregistrement LearningSignal: {e}")
            self.db.rollback()
            return None

    # ================================================================
    # ANALYSE ET SUGGESTIONS
    # ================================================================

    def get_dataset_stats(self) -> LearningDatasetStats:
        """Statistiques globales du dataset d'apprentissage."""
        total = self.db.query(func.count(LearningSignal.id)).scalar() or 0
        if total == 0:
            return LearningDatasetStats()

        profitable = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.was_profitable == 1
        ).scalar() or 0

        avg_pnl = self.db.query(func.avg(LearningSignal.pnl_brut)).scalar() or 0

        longs = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.direction == "long"
        ).scalar() or 0
        shorts = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.direction == "short"
        ).scalar() or 0

        long_wins = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.direction == "long",
            LearningSignal.was_profitable == 1,
        ).scalar() or 0
        short_wins = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.direction == "short",
            LearningSignal.was_profitable == 1,
        ).scalar() or 0

        # Exit type distribution
        exit_types = (
            self.db.query(LearningSignal.exit_type, func.count(LearningSignal.id))
            .group_by(LearningSignal.exit_type)
            .all()
        )
        exit_dist = {et: count for et, count in exit_types if et}

        oldest = self.db.query(func.min(LearningSignal.created_at)).scalar()
        newest = self.db.query(func.max(LearningSignal.created_at)).scalar()

        return LearningDatasetStats(
            total_samples=total,
            samples_profitable=profitable,
            samples_unprofitable=total - profitable,
            avg_pnl=round(float(avg_pnl), 2),
            long_samples=longs,
            short_samples=shorts,
            long_win_rate=round(long_wins / longs * 100, 1) if longs > 0 else 0,
            short_win_rate=round(short_wins / shorts * 100, 1) if shorts > 0 else 0,
            exit_type_distribution=exit_dist,
            oldest_sample=oldest.isoformat() if oldest else None,
            newest_sample=newest.isoformat() if newest else None,
        )

    def analyze_patterns(self) -> list[PatternInsight]:
        """
        Identifie les patterns gagnants et perdants.

        Analyse les échantillons par :
        - Direction (long vs short)
        - Type de sortie
        - Tranche de score
        - Durée
        - Reversal vs tendance
        """
        samples = self.db.query(LearningSignal).all()
        if len(samples) < MIN_SAMPLES:
            return []

        patterns = []

        # Pattern 1 : Par type de sortie
        by_exit = defaultdict(list)
        for s in samples:
            if s.exit_type:
                by_exit[s.exit_type].append(s)

        for exit_type, group in by_exit.items():
            if len(group) < 3:
                continue
            wins = sum(1 for s in group if s.was_profitable)
            wr = wins / len(group) * 100
            avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
            impact = "positif" if avg_pnl > 0 else ("négatif" if avg_pnl < -0.5 else "neutre")
            patterns.append(PatternInsight(
                pattern_name=f"exit_{exit_type}",
                description=f"Sorties {exit_type} : {len(group)} trades, WR {wr:.0f}%, PnL moy {avg_pnl:.2f}",
                sample_count=len(group),
                win_rate=round(wr, 1),
                avg_pnl=round(avg_pnl, 2),
                impact=impact,
            ))

        # Pattern 2 : Par tranche de score
        score_buckets = [(0, 30, "faible"), (30, 50, "moyen"), (50, 80, "fort"), (80, 200, "très_fort")]
        for lo, hi, label in score_buckets:
            group = [s for s in samples if s.score is not None and lo <= abs(s.score) < hi]
            if len(group) < 3:
                continue
            wins = sum(1 for s in group if s.was_profitable)
            wr = wins / len(group) * 100
            avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
            impact = "positif" if avg_pnl > 0 else ("négatif" if avg_pnl < -0.5 else "neutre")
            patterns.append(PatternInsight(
                pattern_name=f"score_{label}",
                description=f"Score {label} ({lo}-{hi}) : {len(group)} trades, WR {wr:.0f}%, PnL moy {avg_pnl:.2f}",
                sample_count=len(group),
                win_rate=round(wr, 1),
                avg_pnl=round(avg_pnl, 2),
                impact=impact,
            ))

        # Pattern 3 : Reversal vs tendance
        reversals = [s for s in samples if s.was_reversal]
        trends = [s for s in samples if not s.was_reversal]
        for label, group in [("reversal", reversals), ("tendance", trends)]:
            if len(group) < 3:
                continue
            wins = sum(1 for s in group if s.was_profitable)
            wr = wins / len(group) * 100
            avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
            impact = "positif" if avg_pnl > 0 else ("négatif" if avg_pnl < -0.5 else "neutre")
            patterns.append(PatternInsight(
                pattern_name=f"type_{label}",
                description=f"{label.capitalize()} : {len(group)} trades, WR {wr:.0f}%, PnL moy {avg_pnl:.2f}",
                sample_count=len(group),
                win_rate=round(wr, 1),
                avg_pnl=round(avg_pnl, 2),
                impact=impact,
            ))

        # Pattern 4 : Long vs Short
        for direction in ["long", "short"]:
            group = [s for s in samples if s.direction == direction]
            if len(group) < 3:
                continue
            wins = sum(1 for s in group if s.was_profitable)
            wr = wins / len(group) * 100
            avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
            impact = "positif" if avg_pnl > 0 else ("négatif" if avg_pnl < -0.5 else "neutre")
            patterns.append(PatternInsight(
                pattern_name=f"direction_{direction}",
                description=f"{direction.upper()} : {len(group)} trades, WR {wr:.0f}%, PnL moy {avg_pnl:.2f}",
                sample_count=len(group),
                win_rate=round(wr, 1),
                avg_pnl=round(avg_pnl, 2),
                impact=impact,
            ))

        return sorted(patterns, key=lambda p: abs(p.avg_pnl), reverse=True)

    def suggest_adjustments(self, profile_type: str = "scalping") -> list[StrategyFeedback]:
        """
        Génère des suggestions d'ajustements basées sur les patterns.

        Mode shadow : les suggestions ne sont PAS appliquées automatiquement.
        Elles sont stockées en base pour inspection et promotion manuelle.
        """
        samples = self.db.query(LearningSignal).filter(
            LearningSignal.profile_type == profile_type
        ).all()

        if len(samples) < MIN_SAMPLES:
            logger.info(f"Pas assez d'échantillons pour le learning ({len(samples)}/{MIN_SAMPLES})")
            return []

        params = PROFILE_PRESETS.get(profile_type)
        if params is None:
            return []

        suggestions = []
        version = self._next_version()

        # Suggestion 1 : Trailing stop — si la majorité des trailing stops sont perdants
        trailing_trades = [s for s in samples if s.exit_type == "closed_trailing_stop"]
        if len(trailing_trades) >= 5:
            trailing_wr = sum(1 for t in trailing_trades if t.was_profitable) / len(trailing_trades) * 100
            trailing_avg = sum(t.pnl_brut for t in trailing_trades if t.pnl_brut) / len(trailing_trades)
            if trailing_wr < 40 and trailing_avg < 0:
                current_val = params.trailing_stop_pct or 0.12
                suggested = min(current_val * 1.3, SAFETY_BOUNDS["trailing_stop_pct"][1])
                suggestions.append(self._create_feedback(
                    parameter_name="trailing_stop_pct",
                    original_value=current_val,
                    suggested_value=round(suggested, 3),
                    reason=(
                        f"Le trailing stop a un WR de {trailing_wr:.0f}% et un PnL moyen de "
                        f"{trailing_avg:.2f} sur {len(trailing_trades)} trades → élargir le trail"
                    ),
                    sample_size=len(trailing_trades),
                    win_rate_observed=trailing_wr,
                    avg_pnl_observed=trailing_avg,
                    profile_type=profile_type,
                    version=version,
                ))

        # Suggestion 2 : Stale exit — si les stale exits sont globalement positifs
        stale_trades = [s for s in samples if s.exit_type == "closed_stale"]
        if len(stale_trades) >= 5:
            stale_wr = sum(1 for t in stale_trades if t.was_profitable) / len(stale_trades) * 100
            stale_avg = sum(t.pnl_brut for t in stale_trades if t.pnl_brut) / len(stale_trades)
            current_val = params.stale_exit_minutes or 12
            if stale_wr > 60 and stale_avg > 0:
                # Stale exit sauve de l'argent → ne pas toucher ou réduire légèrement
                pass
            elif stale_wr < 40:
                suggested = min(current_val + 3, SAFETY_BOUNDS["stale_exit_minutes"][1])
                suggestions.append(self._create_feedback(
                    parameter_name="stale_exit_minutes",
                    original_value=current_val,
                    suggested_value=suggested,
                    reason=(
                        f"Le stale exit a un WR de {stale_wr:.0f}% sur {len(stale_trades)} trades "
                        f"→ augmenter le délai pour laisser plus de temps"
                    ),
                    sample_size=len(stale_trades),
                    win_rate_observed=stale_wr,
                    avg_pnl_observed=stale_avg,
                    profile_type=profile_type,
                    version=version,
                ))

        # Suggestion 3 : Buy threshold — si les trades à score bas sont destructeurs
        low_score = [s for s in samples if s.score is not None and abs(s.score) < 30]
        if len(low_score) >= 5:
            low_wr = sum(1 for t in low_score if t.was_profitable) / len(low_score) * 100
            low_avg = sum(t.pnl_brut for t in low_score if t.pnl_brut) / len(low_score)
            if low_wr < 45 and low_avg < 0:
                current_val = params.buy_threshold or 20
                suggested = min(current_val + 5, SAFETY_BOUNDS["buy_threshold"][1])
                suggestions.append(self._create_feedback(
                    parameter_name="buy_threshold",
                    original_value=current_val,
                    suggested_value=suggested,
                    reason=(
                        f"Les trades avec score < 30 ont un WR de {low_wr:.0f}% et PnL moy {low_avg:.2f} "
                        f"sur {len(low_score)} trades → relever le seuil d'entrée"
                    ),
                    sample_size=len(low_score),
                    win_rate_observed=low_wr,
                    avg_pnl_observed=low_avg,
                    profile_type=profile_type,
                    version=version,
                ))

        # Sauvegarder les suggestions en mode shadow
        for fb in suggestions:
            self.db.add(fb)
        if suggestions:
            self.db.commit()

        return suggestions

    def get_active_adjustments(self) -> list[StrategyFeedback]:
        """Retourne les ajustements actuellement appliqués."""
        return (
            self.db.query(StrategyFeedback)
            .filter(StrategyFeedback.is_active == 1)
            .order_by(StrategyFeedback.applied_at.desc())
            .all()
        )

    def get_shadow_suggestions(self) -> list[StrategyFeedback]:
        """Retourne les suggestions en mode shadow (non appliquées)."""
        return (
            self.db.query(StrategyFeedback)
            .filter(StrategyFeedback.mode == "shadow")
            .order_by(StrategyFeedback.created_at.desc())
            .all()
        )

    def promote_adjustment(self, feedback_id: int) -> Optional[StrategyFeedback]:
        """Promeut une suggestion shadow → applied."""
        fb = self.db.query(StrategyFeedback).filter(StrategyFeedback.id == feedback_id).first()
        if fb is None:
            return None
        fb.mode = "applied"
        fb.is_active = 1
        fb.applied_at = datetime.now(timezone.utc)
        fb.current_value = fb.suggested_value
        self.db.commit()
        self.db.refresh(fb)
        logger.info(f"✅ Ajustement promu : {fb.parameter_name} → {fb.suggested_value}")
        return fb

    def rollback_adjustment(self, feedback_id: int) -> Optional[StrategyFeedback]:
        """Annule un ajustement appliqué → rolled_back."""
        fb = self.db.query(StrategyFeedback).filter(StrategyFeedback.id == feedback_id).first()
        if fb is None:
            return None
        fb.mode = "rolled_back"
        fb.is_active = 0
        fb.current_value = fb.original_value
        self.db.commit()
        self.db.refresh(fb)
        logger.info(f"⏪ Ajustement rollback : {fb.parameter_name} → {fb.original_value}")
        return fb

    def get_version_history(self) -> LearningVersionHistory:
        """Retourne l'historique des versions d'ajustements."""
        all_fb = (
            self.db.query(StrategyFeedback)
            .order_by(StrategyFeedback.version.desc(), StrategyFeedback.created_at.desc())
            .all()
        )
        items = [StrategyFeedbackItem.model_validate(fb) for fb in all_fb]
        current = max((fb.version for fb in all_fb), default=0)
        return LearningVersionHistory(versions=items, current_version=current)

    def analyze(self, profile_type: str = "scalping") -> LearningAnalysisResponse:
        """Analyse complète : stats + patterns + suggestions."""
        stats = self.get_dataset_stats()
        patterns = self.analyze_patterns()
        suggestions = self.suggest_adjustments(profile_type)
        active = self.get_active_adjustments()

        return LearningAnalysisResponse(
            dataset_stats=stats,
            patterns=patterns,
            suggested_adjustments=[StrategyFeedbackItem.model_validate(s) for s in suggestions],
            active_adjustments=[StrategyFeedbackItem.model_validate(a) for a in active],
            learning_enabled=True,
            mode="shadow",
        )

    # ================================================================
    # HELPERS
    # ================================================================

    def _next_version(self) -> int:
        """Retourne le prochain numéro de version."""
        max_v = self.db.query(func.max(StrategyFeedback.version)).scalar()
        return (max_v or 0) + 1

    def _create_feedback(
        self,
        parameter_name: str,
        original_value: float,
        suggested_value: float,
        reason: str,
        sample_size: int,
        win_rate_observed: float,
        avg_pnl_observed: float,
        profile_type: str,
        version: int,
    ) -> StrategyFeedback:
        """Crée un StrategyFeedback borné par les safety bounds."""
        bounds = SAFETY_BOUNDS.get(parameter_name, (0, 1000))
        clamped = max(bounds[0], min(bounds[1], suggested_value))

        return StrategyFeedback(
            parameter_name=parameter_name,
            original_value=original_value,
            suggested_value=round(clamped, 4),
            current_value=original_value,
            min_allowed=bounds[0],
            max_allowed=bounds[1],
            reason=reason,
            sample_size=sample_size,
            win_rate_observed=round(win_rate_observed, 1),
            avg_pnl_observed=round(avg_pnl_observed, 2),
            version=version,
            is_active=0,
            mode="shadow",
            profile_type=profile_type,
        )

