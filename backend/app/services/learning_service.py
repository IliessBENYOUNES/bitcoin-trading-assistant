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
    "min_hold_seconds": (0, 120),  # 0 à 2 minutes max
    "short_min_score": (0, 50),    # [v1.9.3] score min pour ouvrir un short
    "short_exit_score_threshold": (5, 40),  # [v1.9.3] seuil signal contraire short
    "short_min_hold_seconds": (0, 180),     # [v1.9.3] min hold spécifique short (3 min max)
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

        [v1.9.1] Calcule aussi le coût estimé, le PnL net et la catégorie
        d'utilité économique (useful / insignificant / churn / loss_useful / loss_destructive).
        """
        if trade is None or trade.pnl is None:
            return None

        duration_min = trade.duration_hours * 60 if trade.duration_hours else None

        # [v1.9.1] Calcul coût et PnL net
        cost_estimated = 0.0
        pnl_net = trade.pnl
        try:
            from app.services.trading_cost_service import get_cost_model
            cost_model = get_cost_model("realistic")
            size = (trade.position_size_usd or 0) * (trade.leverage or 1.0)
            cost_estimated = cost_model.round_trip_cost_usd(size)
            pnl_net = trade.pnl - cost_estimated
        except Exception:
            cost_estimated = 0.0
            pnl_net = trade.pnl

        # [v1.9.1] Catégorie d'utilité économique
        usefulness = self._classify_usefulness(
            pnl_brut=trade.pnl,
            pnl_net=pnl_net,
            pnl_pct=trade.pnl_pct,
            duration_min=duration_min,
        )

        sample = LearningSignal(
            trade_id=trade.id,
            score=trade.decision_score,
            confidence=None,
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
            cost_estimated=round(cost_estimated, 4),
            pnl_net_estimated=round(pnl_net, 4),
            usefulness_category=usefulness,
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

    @staticmethod
    def _classify_usefulness(
        pnl_brut: float,
        pnl_net: float,
        pnl_pct: Optional[float],
        duration_min: Optional[float],
    ) -> str:
        """
        Classifie un trade en catégorie d'utilité économique.

        Categories :
        - useful : gagnant net avec un mouvement significatif
        - insignificant : gagnant brut mais PnL net quasi nul (< coûts)
        - churn : trade très court et flat (bruit pur)
        - loss_useful : perte bien coupée (loss cut correcte)
        - loss_destructive : perte importante qui aurait pu être évitée
        """
        # Churn : trade < 1 minute et PnL % < 0.05%
        if duration_min is not None and duration_min < 1.0:
            if pnl_pct is not None and abs(pnl_pct) < 0.05:
                return "churn"

        # Trade brut positif
        if pnl_brut >= 0:
            if pnl_net > 0.5:
                return "useful"
            elif pnl_net > 0:
                return "insignificant"
            else:
                # Brut positif mais net négatif → insignifiant (coûts > gains)
                return "insignificant"
        else:
            # Trade perdant
            if pnl_pct is not None and pnl_pct > -0.3:
                return "loss_useful"  # Perte bien coupée
            else:
                return "loss_destructive"  # Grosse perte

    # ================================================================
    # ANALYSE ET SUGGESTIONS
    # ================================================================

    def get_dataset_stats(self) -> LearningDatasetStats:
        """Statistiques globales du dataset d'apprentissage."""
        total = self.db.query(func.count(LearningSignal.id)).scalar() or 0
        if total == 0:
            # Calculer le seuil économique même sans données
            min_move = 0.0
            try:
                from app.services.trading_cost_service import get_cost_model
                cm = get_cost_model("realistic")
                min_move = cm.round_trip_cost_pct()
            except Exception:
                pass
            return LearningDatasetStats(min_economic_move_pct=round(min_move, 3))

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

        # [v1.9.1] Métriques économiques
        avg_cost = self.db.query(func.avg(LearningSignal.cost_estimated)).scalar() or 0
        avg_pnl_net = self.db.query(func.avg(LearningSignal.pnl_net_estimated)).scalar() or 0

        # Comptes par catégorie d'utilité
        useful_count = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.usefulness_category == "useful"
        ).scalar() or 0
        insignificant_count = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.usefulness_category == "insignificant"
        ).scalar() or 0
        churn_count = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.usefulness_category == "churn"
        ).scalar() or 0

        pct_useful = round(useful_count / total * 100, 1) if total > 0 else 0

        # [v1.9.3] Stats short spécifiques par catégorie d'utilité
        short_useful = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.direction == "short",
            LearningSignal.usefulness_category == "useful",
        ).scalar() or 0
        short_insignificant = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.direction == "short",
            LearningSignal.usefulness_category == "insignificant",
        ).scalar() or 0
        short_churn = self.db.query(func.count(LearningSignal.id)).filter(
            LearningSignal.direction == "short",
            LearningSignal.usefulness_category == "churn",
        ).scalar() or 0
        pct_short_useful = round(short_useful / shorts * 100, 1) if shorts > 0 else 0

        # Seuil économique minimum
        min_move = 0.0
        try:
            from app.services.trading_cost_service import get_cost_model
            cm = get_cost_model("realistic")
            min_move = cm.round_trip_cost_pct()
        except Exception:
            pass

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
            avg_cost_per_trade=round(float(avg_cost), 2),
            avg_pnl_net=round(float(avg_pnl_net), 2),
            trades_useful=useful_count,
            trades_insignificant=insignificant_count,
            trades_churn=churn_count,
            pct_economically_useful=pct_useful,
            min_economic_move_pct=round(min_move, 3),
            short_trades_useful=short_useful,
            short_trades_insignificant=short_insignificant,
            short_trades_churn=short_churn,
            pct_short_economically_useful=pct_short_useful,
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

        # Pattern 5 : [v1.9.1] Par catégorie d'utilité économique
        for category in ["useful", "insignificant", "churn", "loss_useful", "loss_destructive"]:
            group = [s for s in samples if s.usefulness_category == category]
            if len(group) < 2:
                continue
            wins = sum(1 for s in group if s.was_profitable)
            wr = wins / len(group) * 100
            avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
            avg_net = sum(s.pnl_net_estimated for s in group if s.pnl_net_estimated is not None) / len(group) if any(s.pnl_net_estimated is not None for s in group) else avg_pnl
            impact = "positif" if avg_net > 0.5 else ("négatif" if avg_net < -0.5 else "neutre")
            patterns.append(PatternInsight(
                pattern_name=f"economic_{category}",
                description=(
                    f"Catégorie '{category}' : {len(group)} trades ({len(group)/len(samples)*100:.0f}%), "
                    f"PnL brut moy {avg_pnl:.2f}, PnL NET moy {avg_net:.2f}"
                ),
                sample_count=len(group),
                win_rate=round(wr, 1),
                avg_pnl=round(avg_net, 2),
                impact=impact,
            ))

        # Pattern 6 : [v1.9.1] Par bucket de durée
        dur_buckets = [
            (0, 1, "< 1min"),
            (1, 5, "1-5min"),
            (5, 15, "5-15min"),
            (15, 60, "15-60min"),
            (60, 999999, "> 60min"),
        ]
        for lo, hi, label in dur_buckets:
            group = [s for s in samples if s.duration_minutes is not None and lo <= s.duration_minutes < hi]
            if len(group) < 2:
                continue
            wins = sum(1 for s in group if s.was_profitable)
            wr = wins / len(group) * 100
            avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
            avg_net = sum(s.pnl_net_estimated for s in group if s.pnl_net_estimated is not None) / len(group) if any(s.pnl_net_estimated is not None for s in group) else avg_pnl
            impact = "positif" if avg_net > 0.5 else ("négatif" if avg_net < -0.5 else "neutre")
            patterns.append(PatternInsight(
                pattern_name=f"duration_{label.replace(' ', '').replace('<', 'lt').replace('>', 'gt')}",
                description=(
                    f"Durée {label} : {len(group)} trades, WR {wr:.0f}%, "
                    f"PnL brut moy {avg_pnl:.2f}, NET moy {avg_net:.2f}"
                ),
                sample_count=len(group),
                win_rate=round(wr, 1),
                avg_pnl=round(avg_net, 2),
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

        # Suggestion 4 : [v1.9.1] Taux de churn trop élevé → allonger le cooldown
        churn_trades = [s for s in samples if s.usefulness_category == "churn"]
        if len(churn_trades) >= 3 and len(samples) >= 10:
            churn_pct = len(churn_trades) / len(samples) * 100
            if churn_pct > 20:
                current_val = params.cooldown_minutes or 2
                suggested = min(current_val + 1, SAFETY_BOUNDS["cooldown_minutes"][1])
                suggestions.append(self._create_feedback(
                    parameter_name="cooldown_minutes",
                    original_value=current_val,
                    suggested_value=suggested,
                    reason=(
                        f"{churn_pct:.0f}% des trades sont du churn ({len(churn_trades)}/{len(samples)}) "
                        f"— trades < 1 min avec PnL quasi nul → allonger le cooldown base"
                    ),
                    sample_size=len(churn_trades),
                    win_rate_observed=0,
                    avg_pnl_observed=0,
                    profile_type=profile_type,
                    version=version,
                ))

        # Suggestion 5 : [v1.9.1] Trop de trades insignifiants → élargir le TP
        insignif_trades = [s for s in samples if s.usefulness_category == "insignificant"]
        if len(insignif_trades) >= 3 and len(samples) >= 10:
            insignif_pct = len(insignif_trades) / len(samples) * 100
            if insignif_pct > 30:
                current_val = params.profit_take_pct or 0.5
                suggested = min(current_val + 0.1, SAFETY_BOUNDS["profit_take_pct"][1])
                avg_insignif_pnl = sum(s.pnl_brut for s in insignif_trades if s.pnl_brut) / len(insignif_trades)
                suggestions.append(self._create_feedback(
                    parameter_name="profit_take_pct",
                    original_value=current_val,
                    suggested_value=round(suggested, 2),
                    reason=(
                        f"{insignif_pct:.0f}% des trades sont insignifiants (brut positif mais net ~ 0) "
                        f"avec PnL brut moyen {avg_insignif_pnl:.2f} — les gains ne dépassent pas les coûts "
                        f"→ élargir le TP pour capturer des mouvements plus grands"
                    ),
                    sample_size=len(insignif_trades),
                    win_rate_observed=100,
                    avg_pnl_observed=avg_insignif_pnl,
                    profile_type=profile_type,
                    version=version,
                ))

        # Suggestion 6 : [v1.9.1] Signal contraire ferme trop vite → allonger min_hold
        signal_exits = [s for s in samples if s.exit_type == "closed_signal"]
        if len(signal_exits) >= 5:
            fast_signal = [s for s in signal_exits if s.duration_minutes is not None and s.duration_minutes < 1]
            if len(fast_signal) >= 3:
                fast_avg = sum(s.pnl_brut for s in fast_signal if s.pnl_brut) / len(fast_signal)
                if fast_avg < 0.5:
                    suggestions.append(self._create_feedback(
                        parameter_name="min_hold_seconds",
                        original_value=getattr(params, "min_hold_seconds", 0) or 0,
                        suggested_value=45,
                        reason=(
                            f"{len(fast_signal)} trades fermés par signal contraire en < 1 min "
                            f"avec PnL brut moyen {fast_avg:.2f} — la sortie-éclair détruit la valeur "
                            f"→ allonger le min_hold pour laisser les trades respirer"
                        ),
                        sample_size=len(fast_signal),
                        win_rate_observed=sum(1 for s in fast_signal if s.was_profitable) / len(fast_signal) * 100,
                        avg_pnl_observed=fast_avg,
                        profile_type=profile_type,
                        version=version,
                    ))

        # Suggestion 7 : [v1.9.3] Trop de shorts insignifiants → relever short_min_score
        short_samples = [s for s in samples if s.direction == "short"]
        if len(short_samples) >= 5:
            short_insignif = [
                s for s in short_samples
                if s.usefulness_category in ("insignificant", "churn")
            ]
            short_insignif_pct = len(short_insignif) / len(short_samples) * 100
            if short_insignif_pct > 50:
                current_val = getattr(params, "short_min_score", 0) or 0
                suggested = min(current_val + 5, 50)
                avg_net = sum(
                    s.pnl_net_estimated for s in short_insignif
                    if s.pnl_net_estimated is not None
                ) / len(short_insignif) if short_insignif else 0
                suggestions.append(self._create_feedback(
                    parameter_name="short_min_score",
                    original_value=current_val,
                    suggested_value=suggested,
                    reason=(
                        f"{short_insignif_pct:.0f}% des shorts sont insignifiants/churn "
                        f"({len(short_insignif)}/{len(short_samples)}) avec PnL net moyen {avg_net:.2f} "
                        f"→ relever le seuil de score minimum pour les shorts"
                    ),
                    sample_size=len(short_insignif),
                    win_rate_observed=0,
                    avg_pnl_observed=avg_net,
                    profile_type=profile_type,
                    version=version,
                ))

        # Suggestion 8 : [v1.9.3] Shorts trop courts → allonger short_min_hold
        if len(short_samples) >= 5:
            short_fast = [
                s for s in short_samples
                if s.duration_minutes is not None and s.duration_minutes < 2
            ]
            if len(short_fast) >= 3:
                fast_net = sum(
                    s.pnl_net_estimated for s in short_fast
                    if s.pnl_net_estimated is not None
                ) / len(short_fast) if short_fast else 0
                if fast_net < 0:
                    current_val = getattr(params, "short_min_hold_seconds", 0) or 0
                    suggestions.append(self._create_feedback(
                        parameter_name="short_min_hold_seconds",
                        original_value=current_val,
                        suggested_value=min(current_val + 30, SAFETY_BOUNDS["min_hold_seconds"][1]),
                        reason=(
                            f"{len(short_fast)} shorts durent < 2 min avec PnL net moyen {fast_net:.2f} "
                            f"→ allonger le min_hold spécifique aux shorts"
                        ),
                        sample_size=len(short_fast),
                        win_rate_observed=sum(1 for s in short_fast if s.was_profitable) / len(short_fast) * 100,
                        avg_pnl_observed=fast_net,
                        profile_type=profile_type,
                        version=version,
                    ))

        # Suggestion 9 : [v1.9.3] Signal contraire trop dominant sur shorts
        short_signal_exits = [
            s for s in short_samples if s.exit_type == "closed_signal"
        ]
        if len(short_signal_exits) >= 3 and len(short_samples) >= 5:
            signal_pct = len(short_signal_exits) / len(short_samples) * 100
            if signal_pct > 50:
                signal_net = sum(
                    s.pnl_net_estimated for s in short_signal_exits
                    if s.pnl_net_estimated is not None
                ) / len(short_signal_exits) if short_signal_exits else 0
                current_th = getattr(params, "short_exit_score_threshold", 10) or 10
                suggestions.append(self._create_feedback(
                    parameter_name="short_exit_score_threshold",
                    original_value=current_th,
                    suggested_value=min(current_th + 5, 40),
                    reason=(
                        f"{signal_pct:.0f}% des shorts fermés par signal contraire "
                        f"({len(short_signal_exits)}/{len(short_samples)}) avec PnL net moyen {signal_net:.2f} "
                        f"→ relever le seuil pour que le moteur exige un vrai retournement"
                    ),
                    sample_size=len(short_signal_exits),
                    win_rate_observed=sum(1 for s in short_signal_exits if s.was_profitable) / len(short_signal_exits) * 100,
                    avg_pnl_observed=signal_net,
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

