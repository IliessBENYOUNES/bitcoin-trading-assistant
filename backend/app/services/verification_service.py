"""
Service de verification historique — "Time-Travel Backtest".

Ce service :
1. Se positionne a n'importe quelle date passee
2. Execute le moteur de decision avec UNIQUEMENT les donnees anterieures
3. Compare la prediction avec ce qui s'est reellement passe
4. Peut repeter ca sur des dizaines/centaines de dates (walk-forward)

NOTE IMPORTANTE : Le sentiment (news) n'est pas disponible en historique.
Le moteur de decision fonctionne en mode degrade (100% technique).
C'est un test de la qualite des indicateurs techniques uniquement.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Candle
from app.services.decision_service import DecisionService
from app.schemas.decision import ActionType
from app.schemas.verification import (
    VerificationRequest,
    VerificationResult,
    HorizonOutcome,
    WalkForwardConfig,
    WalkForwardResult,
    HorizonAccuracy,
    HistoryRangeResponse,
)

logger = logging.getLogger(__name__)


class VerificationService:
    """
    Service de verification historique.

    Usage :
        service = VerificationService(db_session)

        # Verification ponctuelle
        result = service.verify_at_date(VerificationRequest(
            target_date="2020-01-01",
            horizons=[7, 30, 90],
        ))

        # Walk-forward
        result = service.walk_forward(WalkForwardConfig(
            start_date="2018-01-01",
            end_date="2025-12-31",
            step_days=30,
        ))
    """

    def __init__(self, db: Session):
        self.db = db
        self.decision_service = DecisionService(db)

    @staticmethod
    def _ensure_aware(dt: datetime) -> datetime:
        """Assure qu'un datetime est timezone-aware (UTC).
        SQLite retourne des naive datetimes, PostgreSQL des aware.
        On normalise tout en UTC pour pouvoir soustraire."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def get_history_range(
        self, symbol: str = "BTC/USD", timeframe: str = "1d"
    ) -> HistoryRangeResponse:
        """Retourne la plage de dates disponible en base."""
        min_ts = self.db.query(func.min(Candle.timestamp)).filter(
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
        ).scalar()

        max_ts = self.db.query(func.max(Candle.timestamp)).filter(
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
        ).scalar()

        total = self.db.query(func.count(Candle.id)).filter(
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
        ).scalar() or 0

        return HistoryRangeResponse(
            symbol=symbol,
            timeframe=timeframe,
            min_date=min_ts.isoformat() if min_ts else None,
            max_date=max_ts.isoformat() if max_ts else None,
            total_candles=total,
            has_data=total > 0,
        )

    def _get_close_price_at(
        self, symbol: str, timeframe: str, target_date: datetime
    ) -> Optional[float]:
        """
        Recupere le prix de cloture a une date donnee.
        Si pas de candle exacte, cherche la plus proche dans les 2 jours.

        NOTE : On utilise un tri Python au lieu de julianday() SQL
        pour compatibilite SQLite + PostgreSQL.
        """
        # D'abord essayer exact match
        candle = (
            self.db.query(Candle.close_price)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp == target_date,
            )
            .first()
        )
        if candle:
            return candle[0]

        # Sinon, la candle la plus proche dans une fenetre de +/- 2 jours
        window_start = target_date - timedelta(days=2)
        window_end = target_date + timedelta(days=2)

        candles = (
            self.db.query(Candle.close_price, Candle.timestamp)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= window_start,
                Candle.timestamp <= window_end,
            )
            .all()
        )
        if not candles:
            return None

        # Tri par proximite temporelle en Python (cross-database)
        closest = min(candles, key=lambda c: abs((self._ensure_aware(c[1]) - target_date).total_seconds()))
        return closest[0]

    def _get_closest_price_at(
        self, symbol: str, timeframe: str, target_date: datetime
    ) -> tuple[Optional[float], Optional[str]]:
        """
        Recupere le prix et la date exacte de la candle la plus proche.
        Retourne (price, date_iso) ou (None, None).

        NOTE : On utilise un tri Python au lieu de julianday() SQL
        pour compatibilite SQLite + PostgreSQL.
        """
        window_start = target_date - timedelta(days=3)
        window_end = target_date + timedelta(days=3)

        candles = (
            self.db.query(Candle.close_price, Candle.timestamp)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= window_start,
                Candle.timestamp <= window_end,
            )
            .all()
        )
        if not candles:
            return None, None

        # Tri par proximite temporelle en Python (cross-database)
        closest = min(candles, key=lambda c: abs((self._ensure_aware(c[1]) - target_date).total_seconds()))
        ts = closest[1]
        return closest[0], (ts.isoformat() if isinstance(ts, datetime) else str(ts))

    def verify_at_date(self, request: VerificationRequest) -> VerificationResult:
        """
        Verification ponctuelle a une date donnee.

        1. Execute le moteur de decision avec end_ts = target_date
        2. Pour chaque horizon, compare prediction vs realite
        """
        target_dt = datetime.fromisoformat(request.target_date).replace(
            tzinfo=timezone.utc
        )

        # Recuperer le prix a la date cible
        price_at_date = self._get_close_price_at(
            request.symbol, request.timeframe, target_dt
        )
        if price_at_date is None:
            return VerificationResult(
                target_date=request.target_date,
                price_at_date=0,
                predicted_action="erreur",
                predicted_summary="Aucune donnee disponible a cette date",
                outcomes=[],
                meta={"error": "no_data_at_target_date"},
            )

        # Executer le moteur de decision avec end_ts (pas de look-ahead)
        try:
            decision = self.decision_service.analyze(
                symbol=request.symbol,
                timeframe=request.timeframe,
                history_days=request.history_days,
                end_ts=target_dt,
            )
        except Exception as e:
            logger.warning(f"Decision echouee a {request.target_date}: {e}")
            return VerificationResult(
                target_date=request.target_date,
                price_at_date=price_at_date,
                predicted_action="erreur",
                predicted_summary=f"Erreur moteur de decision: {str(e)}",
                outcomes=[],
                meta={"error": str(e)},
            )

        # Extraire la prediction
        recommendation = decision.get("recommendation", {})
        predicted_action = recommendation.get("action", "attendre")
        predicted_confidence = recommendation.get("confidence", "low")
        combined_score = decision.get("combined_score", 0)
        summary = decision.get("summary", "")

        # Scenario dominant
        scenarios = decision.get("scenarios", [])
        dominant_label = ""
        dominant_prob = 0.0
        if scenarios:
            dominant_label = scenarios[0].get("label", "")
            dominant_prob = scenarios[0].get("probability", 0.0)

        # Evaluer chaque horizon
        outcomes: list[HorizonOutcome] = []
        for horizon in request.horizons:
            horizon_dt = target_dt + timedelta(days=horizon)

            horizon_price, horizon_date_str = self._get_closest_price_at(
                request.symbol, request.timeframe, horizon_dt
            )

            if horizon_price is None:
                # Pas de donnees a cet horizon (trop recent ou gap)
                outcomes.append(HorizonOutcome(
                    horizon_days=horizon,
                    end_date=horizon_dt.isoformat(),
                    end_price=0,
                    actual_change_pct=0,
                    actual_direction="inconnu",
                    predicted_action=predicted_action,
                    predicted_score=combined_score,
                    correct=False,
                    detail=f"Pas de donnees disponibles a {horizon}j",
                ))
                continue

            # Calculer la variation reelle
            actual_change_pct = (horizon_price - price_at_date) / price_at_date * 100

            # Determiner la direction reelle
            if actual_change_pct > 2:
                actual_direction = "hausse"
            elif actual_change_pct < -2:
                actual_direction = "baisse"
            else:
                actual_direction = "stable"

            # Determiner si la prediction etait correcte
            correct = self._is_prediction_correct(
                predicted_action, actual_direction, actual_change_pct,
                predicted_score=combined_score, horizon_days=horizon,
            )

            # Construire l'explication
            detail = self._build_outcome_detail(
                predicted_action, combined_score,
                actual_direction, actual_change_pct,
                horizon, correct,
            )

            outcomes.append(HorizonOutcome(
                horizon_days=horizon,
                end_date=horizon_date_str or horizon_dt.isoformat(),
                end_price=round(horizon_price, 2),
                actual_change_pct=round(actual_change_pct, 2),
                actual_direction=actual_direction,
                predicted_action=predicted_action,
                predicted_score=combined_score,
                correct=correct,
                detail=detail,
            ))

        return VerificationResult(
            target_date=request.target_date,
            price_at_date=round(price_at_date, 2),
            predicted_action=predicted_action,
            predicted_confidence=predicted_confidence,
            predicted_score=combined_score,
            predicted_summary=summary,
            dominant_scenario=dominant_label,
            dominant_probability=dominant_prob,
            outcomes=outcomes,
            meta={
                "technical_score": decision.get("technical_score", 0),
                "sentiment_available": decision.get("meta", {}).get("sentiment_available", False),
                "rules_satisfied": sum(
                    1 for r in decision.get("rules_evaluated", []) if r.get("satisfied")
                ),
            },
        )

    def _is_prediction_correct(
        self, predicted_action: str, actual_direction: str, actual_change_pct: float,
        predicted_score: int = 0, horizon_days: int = 7,
    ) -> bool:
        """
        Determine si la prediction etait correcte.

        Logique amelioree (v1.1.2) :
        - Utilise le SCORE directionnel, pas seulement l'action
        - Adapte les seuils a l'horizon temporel (BTC est tres volatil)
        - "Attendre" = pas assez de signal → on evalue le penchant du score

        Exemples :
        - acheter + hausse = CORRECT
        - vendre + baisse = CORRECT
        - attendre (score -4) + baisse = CORRECT (penchant baissier valide)
        - attendre (score -4) + forte hausse 30j = depasse le seuil → INCORRECT
        - attendre (score 0) + mouvement normal pour l'horizon = CORRECT
        """
        if predicted_action == ActionType.BUY.value:
            # Acheter = conviction haussiere (score > +25)
            # Correct si la realite n'est pas une baisse franche (> 2%)
            return actual_direction != "baisse"

        elif predicted_action == ActionType.SELL.value:
            # Vendre = conviction baissiere (score < -25)
            # Correct si la realite n'est pas une hausse franche (> 2%)
            return actual_direction != "hausse"

        else:
            # "Attendre" = score entre -25 et +25 (signal insuffisant pour agir)
            # Le score indique le penchant directionnel du modele
            return self._is_hold_correct(
                predicted_score, actual_change_pct, actual_direction, horizon_days
            )

    def _is_hold_correct(
        self,
        score: int,
        actual_change_pct: float,
        actual_direction: str,
        horizon_days: int,
    ) -> bool:
        """
        Evalue la justesse d'une prediction "attendre".

        "Attendre" signifie que le modele n'avait pas assez de signal pour
        recommander acheter ou vendre. Le score (-25 a +25) indique toutefois
        un penchant directionnel.

        Logique :
        1. Si le score a un penchant et la realite va dans ce sens → CORRECT
        2. Si le score a un penchant contraire mais le mouvement est faible → CORRECT
        3. Si le score est neutre → CORRECT sauf mouvement extreme pour l'horizon
        """
        tolerance = self._get_hold_tolerance(horizon_days)
        neutral_threshold = self._get_neutral_threshold(horizon_days)

        if score > 5:
            # Penchant haussier leger
            if actual_change_pct >= 0:
                return True  # Direction confirmee
            # Petite baisse toleree (le modele n'etait pas confiant)
            return abs(actual_change_pct) < tolerance

        elif score < -5:
            # Penchant baissier leger
            if actual_change_pct <= 0:
                return True  # Direction confirmee
            # Petite hausse toleree
            return actual_change_pct < tolerance

        else:
            # Score vraiment neutre (-5 a +5) → "je ne sais pas"
            # Correct sauf mouvement extreme que le modele aurait du detecter
            return abs(actual_change_pct) < neutral_threshold

    @staticmethod
    def _get_hold_tolerance(horizon_days: int) -> float:
        """Marge d'erreur acceptable pour un penchant directionnel 'attendre'."""
        # Le modele penche dans une direction mais dit "attendre"
        # On tolere un mouvement contraire modere
        if horizon_days <= 7:
            return 10.0
        elif horizon_days <= 30:
            return 18.0
        elif horizon_days <= 90:
            return 25.0
        else:
            return 35.0

    @staticmethod
    def _get_neutral_threshold(horizon_days: int) -> float:
        """Seuil de mouvement acceptable quand le modele est neutre (~score 0)."""
        # BTC est volatil : un score neutre ne predit pas la stabilite,
        # il dit "pas assez de signal". On adapte a l'horizon.
        if horizon_days <= 7:
            return 20.0   # ±20% en 7j est "normal" pour BTC
        elif horizon_days <= 30:
            return 35.0   # ±35% en 30j
        elif horizon_days <= 90:
            return 50.0   # ±50% en 90j
        else:
            return 60.0   # ±60% au-dela

    def _build_outcome_detail(
        self,
        predicted_action: str,
        score: int,
        actual_direction: str,
        actual_change: float,
        horizon: int,
        correct: bool,
    ) -> str:
        """Construit l'explication du verdict."""
        action_label = {
            "acheter": "ACHETER",
            "vendre": "VENDRE",
            "attendre": "ATTENDRE",
        }.get(predicted_action, predicted_action.upper())

        verdict = "✅ CORRECT" if correct else "❌ INCORRECT"

        # Ajouter le penchant directionnel pour "attendre"
        lean = ""
        if predicted_action == "attendre" and abs(score) > 5:
            lean_dir = "haussier" if score > 0 else "baissier"
            lean = f", penchant {lean_dir}"

        return (
            f"Prediction: {action_label} (score {score:+d}{lean}) → "
            f"Realite a {horizon}j: {actual_direction} ({actual_change:+.1f}%) "
            f"— {verdict}"
        )

    def walk_forward(self, config: WalkForwardConfig) -> WalkForwardResult:
        """
        Analyse walk-forward : repete verify_at_date a intervalles reguliers.

        Parcourt la plage [start_date → end_date] avec un pas de step_days,
        et agrege les resultats pour mesurer la precision globale du modele.
        """
        t0 = time.time()

        start_dt = datetime.fromisoformat(config.start_date).replace(
            tzinfo=timezone.utc
        )
        end_dt = datetime.fromisoformat(config.end_date).replace(
            tzinfo=timezone.utc
        )

        # Generer les dates cibles
        target_dates: list[datetime] = []
        current = start_dt
        while current <= end_dt:
            target_dates.append(current)
            current += timedelta(days=config.step_days)

        logger.info(
            f"WalkForward: {len(target_dates)} points de verification "
            f"({config.start_date} → {config.end_date}, pas={config.step_days}j)"
        )

        # Executer la verification a chaque date
        points: list[VerificationResult] = []
        for i, target_dt in enumerate(target_dates):
            if (i + 1) % 10 == 0:
                logger.info(f"WalkForward: point {i + 1}/{len(target_dates)}")

            request = VerificationRequest(
                target_date=target_dt.isoformat(),
                symbol=config.symbol,
                timeframe=config.timeframe,
                history_days=config.history_days,
                horizons=config.horizons,
            )

            try:
                result = self.verify_at_date(request)
                # Ignorer les points sans donnees
                if result.price_at_date > 0:
                    points.append(result)
            except Exception as e:
                logger.warning(f"WalkForward: erreur a {target_dt.date()}: {e}")
                continue

        # Agreger les resultats par horizon
        accuracy_by_horizon = self._compute_accuracy(points, config.horizons)

        duration = round(time.time() - t0, 2)
        summary = self._build_walk_forward_summary(
            points, accuracy_by_horizon, duration
        )

        return WalkForwardResult(
            total_points=len(points),
            start_date=config.start_date,
            end_date=config.end_date,
            step_days=config.step_days,
            accuracy_by_horizon=accuracy_by_horizon,
            points=points,
            summary=summary,
            duration_seconds=duration,
        )

    def _compute_accuracy(
        self, points: list[VerificationResult], horizons: list[int]
    ) -> list[HorizonAccuracy]:
        """Calcule la precision par horizon."""
        results: list[HorizonAccuracy] = []

        for horizon in horizons:
            correct_count = 0
            incorrect_count = 0
            total_score = 0
            total_change = 0
            buy_count = 0
            sell_count = 0
            hold_count = 0

            for point in points:
                for outcome in point.outcomes:
                    if outcome.horizon_days != horizon:
                        continue
                    if outcome.actual_direction == "inconnu":
                        continue

                    if outcome.correct:
                        correct_count += 1
                    else:
                        incorrect_count += 1

                    total_score += outcome.predicted_score
                    total_change += outcome.actual_change_pct

                    if outcome.predicted_action == "acheter":
                        buy_count += 1
                    elif outcome.predicted_action == "vendre":
                        sell_count += 1
                    else:
                        hold_count += 1

            total = correct_count + incorrect_count
            accuracy = (correct_count / total * 100) if total > 0 else 0
            avg_score = total_score / total if total > 0 else 0
            avg_change = total_change / total if total > 0 else 0

            results.append(HorizonAccuracy(
                horizon_days=horizon,
                total_points=total,
                correct=correct_count,
                incorrect=incorrect_count,
                accuracy_pct=round(accuracy, 1),
                avg_predicted_score=round(avg_score, 1),
                avg_actual_change_pct=round(avg_change, 1),
                buy_signals=buy_count,
                sell_signals=sell_count,
                hold_signals=hold_count,
            ))

        return results

    def _build_walk_forward_summary(
        self,
        points: list[VerificationResult],
        accuracy_by_horizon: list[HorizonAccuracy],
        duration: float,
    ) -> str:
        """Resume lisible de l'analyse walk-forward."""
        if not points:
            return "Aucun point de verification genere."

        parts = [f"{len(points)} points analyses"]

        for acc in accuracy_by_horizon:
            if acc.total_points > 0:
                parts.append(
                    f"Horizon {acc.horizon_days}j: {acc.accuracy_pct:.0f}% "
                    f"({acc.correct}/{acc.total_points})"
                )

        parts.append(f"({duration:.1f}s)")
        return " | ".join(parts)

