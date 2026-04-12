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
    "stale_negative_exit_minutes": (3, 30),  # [v1.9.5] stale exit pour positions en perte
    "cooldown_minutes": (0.5, 30),
    "min_score": (3, 50),
    "max_leverage": (1.0, 5.0),
    "profit_take_pct": (0.1, 5.0),
    "loss_cut_pct": (0.1, 5.0),
    "min_hold_seconds": (0, 120),  # 0 à 2 minutes max
    "short_min_score": (0, 50),    # [v1.9.3] score min pour ouvrir un short
    "short_exit_score_threshold": (5, 40),  # [v1.9.3] seuil signal contraire short
    "short_min_hold_seconds": (0, 180),     # [v1.9.3] min hold spécifique short (3 min max)
    "momentum_fade_retention": (0.2, 0.8),  # [v1.9.5] rétention du pic pour momentum fade
    "min_market_quality": (0, 80),           # [v1.9.8] qualité marché minimum
    "min_volume_ratio": (0.0, 2.0),          # [v1.9.8] ratio volume minimum
    "min_micro_trend_long": (0, 5),          # [v2.0.4] gate micro-tendance pour longs
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

        # [v2.0.2] Calcul du contexte BTC (best-effort, non bloquant)
        btc_ctx = self._compute_btc_context(trade)

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
            # [v2.0.2] Contexte BTC
            btc_trend_at_entry=btc_ctx.get("trend"),
            btc_move_during_pct=btc_ctx.get("move_during"),
            btc_move_after_exit_pct=btc_ctx.get("move_after"),
            missed_favorable_move=1 if btc_ctx.get("missed_favorable") else 0,
            capture_efficiency_pct=btc_ctx.get("capture_eff"),
            # [v2.0.16] Candle directions pour apprentissage ML
            entry_candle_direction=getattr(trade, "entry_candle_direction", None),
            exit_candle_direction=getattr(trade, "exit_candle_direction", None),
            # [v2.0.18] Délai de reversal (secondes entre changement de couleur et sortie)
            reversal_delay_seconds=getattr(trade, "reversal_delay_seconds", None),
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

    def _compute_btc_context(self, trade: PaperTrade) -> dict:
        """
        [v2.0.2] Calcule le contexte BTC autour d'un trade (best-effort).

        Retourne un dict avec :
        - trend: "up" / "down" / "flat"
        - move_during: variation BTC % pendant le trade
        - move_after: variation BTC % après la sortie (1 bougie)
        - missed_favorable: True si stale exit avec mouvement BTC favorable après
        - capture_eff: % du mouvement BTC capturé par ce trade
        """
        try:
            from app.models.candle import Candle

            entry_ts = trade.entry_ts
            exit_ts = trade.exit_ts or entry_ts

            # Chercher des bougies 1h, fallback 4h
            candle = None
            for tf in ("1h", "4h"):
                candle = (
                    self.db.query(Candle)
                    .filter(
                        Candle.timeframe == tf,
                        Candle.timestamp <= entry_ts,
                    )
                    .order_by(Candle.timestamp.desc())
                    .first()
                )
                if candle:
                    break

            result = {}

            # Trend à l'entrée
            if candle and candle.open_price > 0:
                move = (candle.close_price - candle.open_price) / candle.open_price * 100
                if move > 0.02:
                    result["trend"] = "up"
                elif move < -0.02:
                    result["trend"] = "down"
                else:
                    result["trend"] = "flat"

            # BTC move pendant le trade
            if trade.entry_price and trade.exit_price and trade.entry_price > 0:
                move_during = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                result["move_during"] = round(move_during, 4)

                # Capture efficiency
                trade_pnl_pct = trade.pnl_pct or 0
                if abs(move_during) > 0.001:
                    if trade.direction == "long" and move_during > 0:
                        result["capture_eff"] = round(min(100, abs(trade_pnl_pct / move_during * 100)), 1)
                    elif trade.direction == "short" and move_during < 0:
                        result["capture_eff"] = round(min(100, abs(trade_pnl_pct / move_during * 100)), 1)
                    else:
                        result["capture_eff"] = 0.0

            # BTC move après la sortie (1 bougie suivante)
            next_candle = None
            for tf in ("1h", "4h"):
                next_candle = (
                    self.db.query(Candle)
                    .filter(
                        Candle.timeframe == tf,
                        Candle.timestamp > exit_ts,
                    )
                    .order_by(Candle.timestamp.asc())
                    .first()
                )
                if next_candle:
                    break

            if next_candle and next_candle.open_price > 0:
                after_move = (next_candle.close_price - next_candle.open_price) / next_candle.open_price * 100
                result["move_after"] = round(after_move, 4)

                # Missed favorable move (stale exit + BTC favorable après)
                if trade.status == "closed_stale":
                    is_favorable = (
                        (trade.direction == "long" and after_move > 0.1)
                        or (trade.direction == "short" and after_move < -0.1)
                    )
                    if is_favorable:
                        result["missed_favorable"] = True

            return result

        except Exception as e:
            logger.debug(f"BTC context computation failed (non-blocking): {e}")
            return {}

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

        # Pattern 7 : [v2.0.17] Cohérence candle direction entrée → sortie
        # C'est le pattern le plus important pour le scalping : si la couleur de
        # la bougie change entre l'entrée et la sortie, ça indique que le momentum
        # s'est retourné pendant le trade — souvent corrélé avec des pertes.
        #
        # 4 combinaisons possibles :
        #   same_aligned   = entrée et sortie même couleur, alignée avec la direction
        #                    (ex: long + green→green = prix montait à l'entrée ET à la sortie)
        #   same_counter   = même couleur mais contre la direction
        #                    (ex: long + red→red = prix descendait tout du long)
        #   reversed_favor = changement de couleur favorable
        #                    (ex: long + red→green = reversal qui a payé)
        #   reversed_against = changement de couleur défavorable
        #                    (ex: long + green→red = momentum perdu)
        candle_groups = {
            "same_aligned": [],
            "same_counter": [],
            "reversed_favor": [],
            "reversed_against": [],
        }
        for s in samples:
            if not s.entry_candle_direction or not s.exit_candle_direction or not s.direction:
                continue
            same_color = s.entry_candle_direction == s.exit_candle_direction
            # "aligned" = la bougie de sortie va dans le sens du trade
            exit_favorable = (
                (s.direction == "long" and s.exit_candle_direction == "green")
                or (s.direction == "short" and s.exit_candle_direction == "red")
            )
            if same_color and exit_favorable:
                candle_groups["same_aligned"].append(s)
            elif same_color and not exit_favorable:
                candle_groups["same_counter"].append(s)
            elif not same_color and exit_favorable:
                candle_groups["reversed_favor"].append(s)
            else:
                candle_groups["reversed_against"].append(s)

        candle_labels = {
            "same_aligned": "Même couleur, alignée (momentum conservé ✅)",
            "same_counter": "Même couleur, contre direction (piégé dans le contre-courant)",
            "reversed_favor": "Changement favorable (reversal gagnant)",
            "reversed_against": "Changement défavorable (momentum perdu ❌)",
        }
        for key, group in candle_groups.items():
            if len(group) < 2:
                continue
            wins = sum(1 for s in group if s.was_profitable)
            wr = wins / len(group) * 100
            avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
            avg_dur = sum(s.duration_minutes for s in group if s.duration_minutes is not None) / max(1, sum(1 for s in group if s.duration_minutes is not None))
            impact = "positif" if avg_pnl > 0 else ("négatif" if avg_pnl < -0.1 else "neutre")
            patterns.append(PatternInsight(
                pattern_name=f"candle_{key}",
                description=(
                    f"🕯️ {candle_labels[key]} : {len(group)} trades, "
                    f"WR {wr:.0f}%, PnL moy {avg_pnl:.2f}, durée moy {avg_dur:.1f}min"
                ),
                sample_count=len(group),
                win_rate=round(wr, 1),
                avg_pnl=round(avg_pnl, 2),
                impact=impact,
            ))

        # Méta-pattern : same color (toutes) vs reversed (toutes)
        all_same = candle_groups["same_aligned"] + candle_groups["same_counter"]
        all_reversed = candle_groups["reversed_favor"] + candle_groups["reversed_against"]
        if len(all_same) >= 2 and len(all_reversed) >= 2:
            same_wr = sum(1 for s in all_same if s.was_profitable) / len(all_same) * 100
            same_pnl = sum(s.pnl_brut for s in all_same if s.pnl_brut) / len(all_same)
            rev_wr = sum(1 for s in all_reversed if s.was_profitable) / len(all_reversed) * 100
            rev_pnl = sum(s.pnl_brut for s in all_reversed if s.pnl_brut) / len(all_reversed)
            delta_wr = same_wr - rev_wr
            delta_pnl = same_pnl - rev_pnl
            impact = "positif" if delta_pnl > 0.2 else ("négatif" if delta_pnl < -0.2 else "neutre")
            patterns.append(PatternInsight(
                pattern_name="candle_consistency_vs_reversal",
                description=(
                    f"🔑 MÊME COULEUR ({len(all_same)} trades, WR {same_wr:.0f}%, PnL {same_pnl:.2f}) "
                    f"vs CHANGEMENT ({len(all_reversed)} trades, WR {rev_wr:.0f}%, PnL {rev_pnl:.2f}) "
                    f"→ Δ WR {delta_wr:+.0f}pts, Δ PnL {delta_pnl:+.2f}"
                ),
                sample_count=len(all_same) + len(all_reversed),
                win_rate=round(same_wr, 1),
                avg_pnl=round(delta_pnl, 2),
                impact=impact,
            ))

        # Pattern 8 : [v2.0.17] Croisement durée × cohérence candle
        # Trades courts (< 2min) avec même couleur vs trades longs avec changement
        # L'hypothèse : un scalp rapide qui reste dans le momentum = optimal
        candle_with_dur = [
            s for s in samples
            if s.entry_candle_direction and s.exit_candle_direction
            and s.duration_minutes is not None and s.direction
        ]
        if len(candle_with_dur) >= 4:
            fast_same = [
                s for s in candle_with_dur
                if s.duration_minutes < 2
                and s.entry_candle_direction == s.exit_candle_direction
            ]
            fast_reversed = [
                s for s in candle_with_dur
                if s.duration_minutes < 2
                and s.entry_candle_direction != s.exit_candle_direction
            ]
            slow_reversed = [
                s for s in candle_with_dur
                if s.duration_minutes >= 2
                and s.entry_candle_direction != s.exit_candle_direction
            ]
            for label, group, desc_prefix in [
                ("fast_same_candle", fast_same, "⚡ Scalp rapide (<2min) + même couleur"),
                ("fast_reversed_candle", fast_reversed, "⚡ Scalp rapide (<2min) + changement couleur"),
                ("slow_reversed_candle", slow_reversed, "🐌 Trade lent (≥2min) + changement couleur"),
            ]:
                if len(group) < 2:
                    continue
                wins = sum(1 for s in group if s.was_profitable)
                wr = wins / len(group) * 100
                avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
                impact = "positif" if avg_pnl > 0 else ("négatif" if avg_pnl < -0.1 else "neutre")
                patterns.append(PatternInsight(
                    pattern_name=f"duration_candle_{label}",
                    description=(
                        f"{desc_prefix} : {len(group)} trades, WR {wr:.0f}%, PnL moy {avg_pnl:.2f}"
                    ),
                    sample_count=len(group),
                    win_rate=round(wr, 1),
                    avg_pnl=round(avg_pnl, 2),
                    impact=impact,
                ))

        # Pattern 9 : [v2.0.18] Analyse du délai de reversal
        # Corrèle le temps entre le changement de couleur et la sortie effective
        # avec la performance du trade. Un délai court = bonne réactivité.
        reversal_trades = [
            s for s in samples
            if s.reversal_delay_seconds is not None and s.reversal_delay_seconds > 0
        ]
        if len(reversal_trades) >= 2:
            # Découper en fast (< 5s) et slow (≥ 5s) reversals
            fast_reversal = [s for s in reversal_trades if s.reversal_delay_seconds < 5]
            slow_reversal = [s for s in reversal_trades if s.reversal_delay_seconds >= 5]
            for label, group, desc in [
                ("fast_reversal", fast_reversal, "⚡ Reversal rapide (<5s)"),
                ("slow_reversal", slow_reversal, "🐌 Reversal lent (≥5s)"),
            ]:
                if len(group) < 2:
                    continue
                wins = sum(1 for s in group if s.was_profitable)
                wr = wins / len(group) * 100
                avg_pnl = sum(s.pnl_brut for s in group if s.pnl_brut) / len(group)
                avg_delay = sum(s.reversal_delay_seconds for s in group) / len(group)
                impact = "positif" if avg_pnl > 0 else ("négatif" if avg_pnl < -0.1 else "neutre")
                patterns.append(PatternInsight(
                    pattern_name=f"reversal_delay_{label}",
                    description=(
                        f"⏱️ {desc} : {len(group)} trades, WR {wr:.0f}%, "
                        f"PnL moy {avg_pnl:.2f}, délai moy {avg_delay:.1f}s"
                    ),
                    sample_count=len(group),
                    win_rate=round(wr, 1),
                    avg_pnl=round(avg_pnl, 2),
                    impact=impact,
                ))

            # Méta-pattern : comparer les trades avec reversal vs sans reversal
            non_reversal_trades = [
                s for s in samples
                if s.reversal_delay_seconds is None or s.reversal_delay_seconds == 0
            ]
            if len(non_reversal_trades) >= 2:
                rev_wr = sum(1 for s in reversal_trades if s.was_profitable) / len(reversal_trades) * 100
                rev_pnl = sum(s.pnl_brut for s in reversal_trades if s.pnl_brut) / len(reversal_trades)
                no_rev_wr = sum(1 for s in non_reversal_trades if s.was_profitable) / len(non_reversal_trades) * 100
                no_rev_pnl = sum(s.pnl_brut for s in non_reversal_trades if s.pnl_brut) / len(non_reversal_trades)
                impact = "positif" if rev_pnl > no_rev_pnl else ("négatif" if rev_pnl < no_rev_pnl - 0.2 else "neutre")
                patterns.append(PatternInsight(
                    pattern_name="reversal_exit_vs_normal",
                    description=(
                        f"🔄 Sortie reversal ({len(reversal_trades)} trades, WR {rev_wr:.0f}%, PnL {rev_pnl:.2f}) "
                        f"vs sortie normale ({len(non_reversal_trades)} trades, WR {no_rev_wr:.0f}%, PnL {no_rev_pnl:.2f})"
                    ),
                    sample_count=len(reversal_trades) + len(non_reversal_trades),
                    win_rate=round(rev_wr, 1),
                    avg_pnl=round(rev_pnl - no_rev_pnl, 2),
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

        # ================================================================
        # [v1.9.5] SUGGESTIONS DE STABILITÉ — Détection d'oscillation et déséquilibres
        # ================================================================

        # Suggestion 10 : Déséquilibre directionnel excessif
        # Si > 80% des trades vont dans une seule direction, le moteur est captif.
        long_samples_all = [s for s in samples if s.direction == "long"]
        short_samples_all = [s for s in samples if s.direction == "short"]
        long_pct = len(long_samples_all) / len(samples) * 100 if samples else 0
        if long_pct >= 85:
            suggestions.append(self._create_feedback(
                parameter_name="short_min_score",
                original_value=getattr(params, "short_min_score", 30) or 30,
                suggested_value=max((getattr(params, "short_min_score", 30) or 30) - 5, 15),
                reason=(
                    f"Déséquilibre directionnel : {long_pct:.0f}% de longs. "
                    f"Le moteur est captif d'une seule direction. "
                    f"Abaisser le seuil short pour permettre la diversification."
                ),
                sample_size=len(samples),
                win_rate_observed=0,
                avg_pnl_observed=0,
                profile_type=profile_type,
                version=version,
            ))
        elif long_pct <= 15 and len(samples) >= 10:
            suggestions.append(self._create_feedback(
                parameter_name="short_min_score",
                original_value=getattr(params, "short_min_score", 30) or 30,
                suggested_value=min((getattr(params, "short_min_score", 30) or 30) + 5, 50),
                reason=(
                    f"Déséquilibre directionnel : seulement {long_pct:.0f}% de longs. "
                    f"Le moteur est captif du short. "
                    f"Relever le seuil short pour rééquilibrer."
                ),
                sample_size=len(samples),
                win_rate_observed=0,
                avg_pnl_observed=0,
                profile_type=profile_type,
                version=version,
            ))

        # Suggestion 11 : Ratio gain/perte asymétrique (pertes >> gains)
        wins_samp = [s for s in samples if s.pnl_brut is not None and s.pnl_brut > 0]
        losses_samp = [s for s in samples if s.pnl_brut is not None and s.pnl_brut < 0]
        if len(wins_samp) >= 3 and len(losses_samp) >= 3:
            avg_win = sum(s.pnl_brut for s in wins_samp) / len(wins_samp)
            avg_loss = abs(sum(s.pnl_brut for s in losses_samp) / len(losses_samp))
            rr_ratio = avg_win / avg_loss if avg_loss > 0 else 999
            if rr_ratio < 0.4:
                current_sl = params.loss_cut_pct or 0.35
                suggested_sl = max(current_sl - 0.05, SAFETY_BOUNDS["loss_cut_pct"][0])
                suggestions.append(self._create_feedback(
                    parameter_name="loss_cut_pct",
                    original_value=current_sl,
                    suggested_value=round(suggested_sl, 2),
                    reason=(
                        f"Ratio R:R effectif très déséquilibré ({rr_ratio:.2f}:1). "
                        f"Gain moyen {avg_win:.2f} vs perte moyenne {avg_loss:.2f}. "
                        f"Resserrer le SL pour réduire les grosses pertes."
                    ),
                    sample_size=len(wins_samp) + len(losses_samp),
                    win_rate_observed=len(wins_samp) / len(samples) * 100,
                    avg_pnl_observed=rr_ratio,
                    profile_type=profile_type,
                    version=version,
                ))

        # Suggestion 12 : Un type de sortie domine de façon destructrice
        exit_counter = defaultdict(list)
        for s in samples:
            if s.exit_type:
                exit_counter[s.exit_type].append(s.pnl_brut or 0)
        for exit_type, pnls in exit_counter.items():
            if len(pnls) >= 3:
                exit_pct = len(pnls) / len(samples) * 100
                avg_pnl_exit = sum(pnls) / len(pnls)
                if exit_pct >= 40 and avg_pnl_exit < -1.0:
                    # Un type de sortie destructrice domine
                    suggestions.append(self._create_feedback(
                        parameter_name="stale_exit_minutes",  # proxy
                        original_value=getattr(params, "stale_exit_minutes", 15) or 15,
                        suggested_value=max((getattr(params, "stale_exit_minutes", 15) or 15) - 2, SAFETY_BOUNDS["stale_exit_minutes"][0]),
                        reason=(
                            f"Sortie '{exit_type}' domine ({exit_pct:.0f}%) avec PnL moyen {avg_pnl_exit:.2f}. "
                            f"Ce type de sortie est destructeur et étouffe le moteur."
                        ),
                        sample_size=len(pnls),
                        win_rate_observed=sum(1 for p in pnls if p >= 0) / len(pnls) * 100,
                        avg_pnl_observed=avg_pnl_exit,
                        profile_type=profile_type,
                        version=version,
                    ))

        # ================================================================
        # [v1.9.8] SUGGESTIONS MARKET STRUCTURE — Rejection du bruit
        # ================================================================

        # Suggestion 13 : Stale-négatif comme mode d'échec dominant
        # Si > 40% des trades finissent en stale avec PnL négatif, le moteur
        # prend des trades sans impulsion suffisante.
        stale_neg = [
            s for s in samples
            if s.exit_type == "closed_stale"
            and s.pnl_brut is not None and s.pnl_brut < 0
        ]
        if len(stale_neg) >= 5 and len(samples) >= 10:
            stale_neg_pct = len(stale_neg) / len(samples) * 100
            stale_neg_avg = sum(s.pnl_brut for s in stale_neg) / len(stale_neg)
            if stale_neg_pct > 30:
                current_neg_min = getattr(params, "stale_negative_exit_minutes", None) or 5
                # Suggestion : réduire le temps stale négatif OU relever la qualité marché
                suggestions.append(self._create_feedback(
                    parameter_name="stale_negative_exit_minutes",
                    original_value=current_neg_min,
                    suggested_value=max(current_neg_min - 1, SAFETY_BOUNDS["stale_negative_exit_minutes"][0]),
                    reason=(
                        f"{stale_neg_pct:.0f}% des trades finissent en stale négatif "
                        f"({len(stale_neg)}/{len(samples)}) avec PnL moyen {stale_neg_avg:.2f}. "
                        f"Le moteur entre sans impulsion suffisante. "
                        f"Réduire le délai stale négatif pour couper plus vite. "
                        f"Envisager aussi de relever min_market_quality."
                    ),
                    sample_size=len(stale_neg),
                    win_rate_observed=0,
                    avg_pnl_observed=stale_neg_avg,
                    profile_type=profile_type,
                    version=version,
                ))

        # Suggestion 14 : Longs scalping à score homogène et perdants
        # Si les scores d'entrée des longs sont très groupés (écart-type < 3)
        # et que le WR est < 40%, le moteur ne hiérarchise pas les setups.
        long_scalp = [
            s for s in samples
            if s.direction == "long" and s.profile_type == "scalping"
        ]
        if len(long_scalp) >= 10:
            scores = [s.score for s in long_scalp if s.score is not None]
            if len(scores) >= 10:
                mean_sc = sum(scores) / len(scores)
                variance_sc = sum((sc - mean_sc) ** 2 for sc in scores) / len(scores)
                std_sc = variance_sc ** 0.5
                wr_long = sum(1 for s in long_scalp if s.was_profitable) / len(long_scalp) * 100
                if std_sc < 3.0 and wr_long < 40:
                    suggestions.append(self._create_feedback(
                        parameter_name="min_market_quality",
                        original_value=getattr(params, "min_market_quality", 0) or 0,
                        suggested_value=min((getattr(params, "min_market_quality", 0) or 0) + 10, 50),
                        reason=(
                            f"Longs scalping à score homogène (σ={std_sc:.1f}, moy={mean_sc:.0f}) "
                            f"avec WR {wr_long:.0f}% sur {len(long_scalp)} trades. "
                            f"Le moteur ne hiérarchise pas les setups. "
                            f"Relever min_market_quality pour exiger plus de structure."
                        ),
                        sample_size=len(long_scalp),
                        win_rate_observed=wr_long,
                        avg_pnl_observed=sum(s.pnl_brut or 0 for s in long_scalp) / len(long_scalp),
                        profile_type=profile_type,
                        version=version,
                    ))

        # ================================================================
        # [v2.0.17] SUGGESTIONS CANDLE DIRECTION — Le pattern le plus prédictif
        # ================================================================
        # Analyse la cohérence de couleur de bougie entrée→sortie.
        # Si les trades où la couleur change (momentum perdu) sont massivement
        # perdants, on suggère de couper plus vite (stale exit) ou de relever
        # le min_hold pour éviter les sorties-éclair qui rattrapent un reversal.

        # Filtrer les échantillons avec candle direction renseignée
        candle_samples = [
            s for s in samples
            if s.entry_candle_direction and s.exit_candle_direction and s.direction
        ]

        if len(candle_samples) >= 5:
            # Trades avec changement de couleur défavorable
            # = la bougie de sortie va CONTRE la direction du trade
            reversed_against = [
                s for s in candle_samples
                if s.entry_candle_direction != s.exit_candle_direction
                and not (
                    (s.direction == "long" and s.exit_candle_direction == "green")
                    or (s.direction == "short" and s.exit_candle_direction == "red")
                )
            ]
            # Trades avec même couleur tout du long
            same_color = [
                s for s in candle_samples
                if s.entry_candle_direction == s.exit_candle_direction
            ]

            # Suggestion 15 : Si les reversals défavorables sont massivement perdants
            if len(reversed_against) >= 3:
                rev_wr = sum(1 for s in reversed_against if s.was_profitable) / len(reversed_against) * 100
                rev_avg = sum(s.pnl_brut for s in reversed_against if s.pnl_brut) / len(reversed_against)
                rev_avg_dur = sum(
                    s.duration_minutes for s in reversed_against if s.duration_minutes is not None
                ) / max(1, sum(1 for s in reversed_against if s.duration_minutes is not None))

                if rev_wr < 35 and rev_avg < -0.1:
                    # Le momentum se retourne pendant le trade → couper plus vite
                    current_stale = getattr(params, "stale_negative_exit_minutes", None) or 5
                    suggested_stale = max(current_stale - 1, SAFETY_BOUNDS["stale_negative_exit_minutes"][0])

                    same_avg = sum(s.pnl_brut for s in same_color if s.pnl_brut) / max(1, len(same_color))
                    suggestions.append(self._create_feedback(
                        parameter_name="stale_negative_exit_minutes",
                        original_value=current_stale,
                        suggested_value=suggested_stale,
                        reason=(
                            f"🕯️ PATTERN CANDLE CRITIQUE : {len(reversed_against)} trades avec changement "
                            f"de couleur défavorable ont un WR de {rev_wr:.0f}% et un PnL moyen de "
                            f"{rev_avg:.2f} (durée moy {rev_avg_dur:.1f}min). "
                            f"En comparaison, les {len(same_color)} trades à couleur stable ont un PnL "
                            f"moyen de {same_avg:.2f}. "
                            f"Le momentum se retourne pendant le trade → couper les positions "
                            f"perdantes plus rapidement."
                        ),
                        sample_size=len(reversed_against),
                        win_rate_observed=rev_wr,
                        avg_pnl_observed=rev_avg,
                        profile_type=profile_type,
                        version=version,
                    ))

            # Suggestion 16 : Si les trades contre-tendance à l'entrée sont destructeurs
            # (ex: long ouvert sur bougie rouge = entrée contre le momentum)
            entry_counter = [
                s for s in candle_samples
                if (s.direction == "long" and s.entry_candle_direction == "red")
                or (s.direction == "short" and s.entry_candle_direction == "green")
            ]
            entry_aligned = [
                s for s in candle_samples
                if (s.direction == "long" and s.entry_candle_direction == "green")
                or (s.direction == "short" and s.entry_candle_direction == "red")
            ]

            if len(entry_counter) >= 3 and len(entry_aligned) >= 3:
                counter_wr = sum(1 for s in entry_counter if s.was_profitable) / len(entry_counter) * 100
                counter_avg = sum(s.pnl_brut for s in entry_counter if s.pnl_brut) / len(entry_counter)
                aligned_wr = sum(1 for s in entry_aligned if s.was_profitable) / len(entry_aligned) * 100
                aligned_avg = sum(s.pnl_brut for s in entry_aligned if s.pnl_brut) / len(entry_aligned)

                # Si entrer contre le momentum est nettement pire
                if counter_wr < aligned_wr - 15 and counter_avg < aligned_avg:
                    current_mt = getattr(params, "min_micro_trend_long", 0) or 0
                    suggested_mt = min(current_mt + 1, SAFETY_BOUNDS["min_micro_trend_long"][1])
                    suggestions.append(self._create_feedback(
                        parameter_name="min_micro_trend_long",
                        original_value=current_mt,
                        suggested_value=suggested_mt,
                        reason=(
                            f"🕯️ ENTRÉE CONTRE-TENDANCE DESTRUCTRICE : {len(entry_counter)} trades "
                            f"ouverts contre le momentum (bougie opposée) ont un WR de {counter_wr:.0f}% "
                            f"et PnL moy {counter_avg:.2f}. "
                            f"Les {len(entry_aligned)} trades alignés avec le momentum ont un WR de "
                            f"{aligned_wr:.0f}% et PnL moy {aligned_avg:.2f}. "
                            f"Écart WR : {aligned_wr - counter_wr:.0f}pts. "
                            f"Relever min_micro_trend_long pour exiger un momentum confirmé avant d'entrer."
                        ),
                        sample_size=len(entry_counter) + len(entry_aligned),
                        win_rate_observed=counter_wr,
                        avg_pnl_observed=counter_avg,
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
    # [v2.0.4] LEARN FROM RUNTIME — Apprentissage basé sur les tick logs
    # ================================================================

    def learn_from_runtime(self, profile_type: str = "scalping") -> list[StrategyFeedback]:
        """
        Analyse les TickActivityLog pour identifier les gates sur-bloquants
        et générer des suggestions d'assouplissement basées sur les données runtime.

        Contrairement à suggest_adjustments() qui se base sur les LearningSignal
        (trades fermés), cette méthode analyse les REFUS de trades (ticks sans ouverture)
        pour identifier les paramètres qui bloquent trop.

        Retourne les suggestions créées en mode shadow.
        """
        from app.models.tick_activity_log import TickActivityLog
        from app.models.paper_account import PaperAccount

        account = self.db.query(PaperAccount).first()
        if account is None:
            return []

        # Charger les ticks du profil
        ticks = (
            self.db.query(TickActivityLog)
            .filter(
                TickActivityLog.account_id == account.id,
                TickActivityLog.profile_type == profile_type,
            )
            .order_by(TickActivityLog.timestamp.asc())
            .all()
        )

        if len(ticks) < 10:
            logger.info(f"Pas assez de ticks runtime pour le learning ({len(ticks)}/10)")
            return []

        params = PROFILE_PRESETS.get(profile_type)
        if params is None:
            return []

        suggestions = []
        version = self._next_version()

        # Ventilation des refus par raison
        reason_counts = defaultdict(list)
        for t in ticks:
            if t.reason_no_trade:
                reason_counts[t.reason_no_trade].append(t)

        total_ticks = len(ticks)
        total_holds = sum(len(v) for v in reason_counts.values())

        # Suggestion 15 : Gate micro-trend sur-bloquant
        # Si > 50% des refus sont micro_trend_insufficient, et que les ticks
        # rejetés avaient un score d'entrée > buy_threshold (le moteur VEUT trader),
        # alors le gate micro-trend est trop restrictif.
        mt_rejected = reason_counts.get("micro_trend_insufficient", [])
        if len(mt_rejected) >= 10 and total_holds > 0:
            mt_pct = len(mt_rejected) / total_holds * 100
            # Score moyen quand bloqué par micro-trend
            mt_scores = [
                t.decision_score for t in mt_rejected
                if t.decision_score is not None
            ]
            avg_mt_score = sum(mt_scores) / len(mt_scores) if mt_scores else 0
            # Si le score moyen est bien au-dessus du seuil d'entrée
            buy_th = getattr(params, "buy_threshold", 30) or 30
            score_above_threshold = avg_mt_score > buy_th

            if mt_pct > 50 and score_above_threshold:
                current_mt = getattr(params, "min_micro_trend_long", 2) or 2
                # Vérifier les micro_trend_score dans les ticks rejetés
                mt_values = [
                    t.micro_trend_score for t in mt_rejected
                    if t.micro_trend_score is not None
                ]
                # Proposer d'abaisser de 1 si possible
                suggested = max(current_mt - 1, 0)

                # Compter combien de ticks auraient passé avec le nouveau seuil
                would_pass = sum(
                    1 for v in mt_values if v >= suggested
                ) if suggested < current_mt else 0
                pass_pct = would_pass / len(mt_values) * 100 if mt_values else 0

                suggestions.append(self._create_feedback(
                    parameter_name="min_micro_trend_long",
                    original_value=current_mt,
                    suggested_value=suggested,
                    reason=(
                        f"{mt_pct:.0f}% des refus runtime sont micro_trend_insufficient "
                        f"({len(mt_rejected)}/{total_holds}). "
                        f"Score moyen des ticks rejetés: {avg_mt_score:.0f} (seuil={buy_th}). "
                        f"Le moteur veut trader mais le gate micro-trend bloque. "
                        f"Abaisser de {current_mt}→{suggested} déverrouillerait {pass_pct:.0f}% "
                        f"des ticks rejetés."
                    ),
                    sample_size=len(mt_rejected),
                    win_rate_observed=0,
                    avg_pnl_observed=0,
                    profile_type=profile_type,
                    version=version,
                ))

        # Suggestion 16 : Un gate domine > 70% des refus sur des ticks buy/sell
        # Si un seul gate bloque > 70% des ticks avec decision_action=acheter|vendre,
        # c'est un goulot d'étranglement trop restrictif.
        for reason, rejected_ticks in reason_counts.items():
            if reason == "micro_trend_insufficient":
                continue  # Déjà traité par suggestion 15

            if total_holds == 0:
                continue

            reason_pct = len(rejected_ticks) / total_holds * 100
            # Vérifier que ces ticks avaient une action d'achat/vente
            buy_sell_in_rejected = [
                t for t in rejected_ticks
                if t.decision_action in ("acheter", "vendre")
            ]

            if reason_pct > 70 and len(buy_sell_in_rejected) >= 5:
                # Mapper la raison vers un paramètre
                param_map = {
                    "score_too_low": "min_score",
                    "market_quality_low": "min_market_quality",
                    "economic_viability_low": "min_ev_multiple",
                    "structural_proof_insufficient": "min_structural_proofs",
                    "cooldown_active": "cooldown_minutes",
                }
                param_name = param_map.get(reason)
                if param_name is None:
                    continue

                current_val = getattr(params, param_name, None)
                if current_val is None:
                    continue

                # Proposer un assouplissement de 10-20%
                if isinstance(current_val, (int, float)):
                    suggested = current_val * 0.85  # -15%
                    suggestions.append(self._create_feedback(
                        parameter_name=param_name,
                        original_value=current_val,
                        suggested_value=round(suggested, 2),
                        reason=(
                            f"Le gate '{reason}' bloque {reason_pct:.0f}% des refus runtime "
                            f"({len(rejected_ticks)}/{total_holds}). "
                            f"Dont {len(buy_sell_in_rejected)} ticks avec un signal buy/sell actif. "
                            f"Le paramètre {param_name}={current_val} est un goulot d'étranglement. "
                            f"Proposer un assouplissement à {suggested:.2f}."
                        ),
                        sample_size=len(buy_sell_in_rejected),
                        win_rate_observed=0,
                        avg_pnl_observed=0,
                        profile_type=profile_type,
                        version=version,
                    ))

        # Sauvegarder les suggestions runtime en mode shadow
        for fb in suggestions:
            self.db.add(fb)
        if suggestions:
            self.db.commit()

        return suggestions

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

