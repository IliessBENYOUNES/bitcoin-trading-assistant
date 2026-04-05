"""
 Service de verification historique — "Time-Travel Backtest" (v1.2 ameliore).

Ce service :
1. Se positionne a n'importe quelle date passee
2. Execute le moteur de decision avec UNIQUEMENT les donnees anterieures
3. Compare la prediction avec ce qui s'est reellement passe
4. Peut repeter ca sur des dizaines/centaines de dates (walk-forward)

AMELIORATIONS v1.2 :
- Seuils de volatilite ADAPTATIFS (calcules sur la volatilite recente)
- Score de qualite de prediction (0-100) au lieu de binaire correct/incorrect
- Accuracy directionnelle (signe du score vs direction reelle)
- Metriques detaillees par niveau de confiance
- Evaluation proportionnelle a la magnitude du mouvement

NOTE IMPORTANTE : Le sentiment (news) n'est pas disponible en historique.
Le moteur de decision fonctionne en mode degrade (100% technique).
C'est un test de la qualite des indicateurs techniques uniquement.
"""

import time
import math
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
    HistoryIntegrityGap,
    HistoryIntegrityResponse,
    WalkForwardComparison,
    WalkForwardSummaryStats,
)

logger = logging.getLogger(__name__)


class VerificationService:
    """
    Service de verification historique v1.2.

    Ameliorations par rapport a v1.1 :
    - Seuils adaptatifs bases sur la volatilite recente (au lieu de fixes)
    - Score de qualite 0-100 (au lieu de binaire correct/incorrect)
    - Directional accuracy (signe du score vs direction reelle)
    - Metriques par confiance (precision des signaux forts vs faibles)
    """

    def __init__(self, db: Session):
        self.db = db
        self.decision_service = DecisionService(db)

    @staticmethod
    def _ensure_aware(dt: datetime) -> datetime:
        """Assure qu'un datetime est timezone-aware (UTC)."""
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
        """Recupere le prix de cloture a une date donnee."""
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

        closest = min(candles, key=lambda c: abs((self._ensure_aware(c[1]) - target_date).total_seconds()))
        return closest[0]

    def _get_closest_price_at(
        self, symbol: str, timeframe: str, target_date: datetime
    ) -> tuple[Optional[float], Optional[str]]:
        """Recupere le prix et la date exacte de la candle la plus proche."""
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

        closest = min(candles, key=lambda c: abs((self._ensure_aware(c[1]) - target_date).total_seconds()))
        ts = closest[1]
        return closest[0], (ts.isoformat() if isinstance(ts, datetime) else str(ts))

    # ================================================================
    # VOLATILITE ADAPTATIVE
    # ================================================================

    def _compute_recent_volatility(
        self, symbol: str, timeframe: str, target_date: datetime, lookback_days: int = 30
    ) -> Optional[float]:
        """
        Calcule la volatilite recente (ecart-type des rendements journaliers)
        sur les `lookback_days` precedant `target_date`.

        Retourne la volatilite en % (ex: 3.5 = 3.5% de volatilite quotidienne).
        Cela sert a adapter les seuils hausse/baisse/stable a la realite du marche
        au lieu d'utiliser des seuils fixes.
        """
        window_start = target_date - timedelta(days=lookback_days + 5)

        candles = (
            self.db.query(Candle.close_price, Candle.timestamp)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= window_start,
                Candle.timestamp <= target_date,
            )
            .order_by(Candle.timestamp.asc())
            .all()
        )

        if len(candles) < 10:
            return None

        # Calculer les rendements quotidiens
        prices = [c[0] for c in candles]
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                ret = (prices[i] - prices[i - 1]) / prices[i - 1] * 100
                returns.append(ret)

        if len(returns) < 5:
            return None

        # Ecart-type des rendements = volatilite
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        volatility = math.sqrt(variance)

        return round(volatility, 4)

    def _get_adaptive_thresholds(
        self, horizon_days: int, daily_volatility: Optional[float]
    ) -> tuple[float, float]:
        """
        Calcule les seuils adaptatifs hausse/baisse et le seuil neutre
        bases sur la volatilite recente.

        Retourne (direction_threshold, neutral_threshold).
        - direction_threshold : seuil pour classifier hausse/baisse
        - neutral_threshold : seuil pour le "attendre" neutre

        La logique : pour un horizon de H jours, le mouvement attendu
        est environ volatilite_quotidienne * sqrt(H) (marche aleatoire).
        On utilise 0.5x ce mouvement comme seuil de direction,
        et 1.5x comme seuil neutre (mouvement "trop fort" pour ignorer).
        """
        if daily_volatility is None or daily_volatility <= 0:
            # Fallback sur les seuils par defaut (volatilite typique BTC ~3%)
            daily_volatility = 3.0

        # Mouvement attendu sous marche aleatoire : vol * sqrt(horizon)
        expected_move = daily_volatility * math.sqrt(horizon_days)

        # Seuil de direction : 40% du mouvement attendu
        # (un mouvement < 40% de la norme est "stable")
        direction_threshold = max(1.5, expected_move * 0.4)

        # Seuil neutre : 1.8x du mouvement attendu
        # (si le modele dit "neutre" et le marche bouge > 1.8x la norme, c'est incorrect)
        neutral_threshold = max(5.0, expected_move * 1.8)

        return round(direction_threshold, 2), round(neutral_threshold, 2)

    # ================================================================
    # VERIFICATION PONCTUELLE
    # ================================================================

    def verify_at_date(self, request: VerificationRequest) -> VerificationResult:
        """
        Verification ponctuelle a une date donnee.

        1. Execute le moteur de decision avec end_ts = target_date
        2. Pour chaque horizon, compare prediction vs realite
        3. Calcule un score de qualite pour chaque horizon
        """
        target_dt = datetime.fromisoformat(request.target_date).replace(
            tzinfo=timezone.utc
        )

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

        # Calculer la volatilite recente pour les seuils adaptatifs
        recent_volatility = self._compute_recent_volatility(
            request.symbol, request.timeframe, target_dt
        )

        # Evaluer chaque horizon
        outcomes: list[HorizonOutcome] = []
        for horizon in request.horizons:
            horizon_dt = target_dt + timedelta(days=horizon)

            horizon_price, horizon_date_str = self._get_closest_price_at(
                request.symbol, request.timeframe, horizon_dt
            )

            if horizon_price is None:
                outcomes.append(HorizonOutcome(
                    horizon_days=horizon,
                    end_date=horizon_dt.isoformat(),
                    end_price=0,
                    actual_change_pct=0,
                    actual_direction="inconnu",
                    predicted_action=predicted_action,
                    predicted_score=combined_score,
                    correct=False,
                    quality_score=0.0,
                    directional_match=False,
                    detail=f"Pas de donnees disponibles a {horizon}j",
                ))
                continue

            # Calculer la variation reelle
            actual_change_pct = (horizon_price - price_at_date) / price_at_date * 100

            # Seuils adaptatifs bases sur la volatilite recente
            dir_threshold, neutral_threshold = self._get_adaptive_thresholds(
                horizon, recent_volatility
            )

            # Determiner la direction reelle avec seuils adaptatifs
            if actual_change_pct > dir_threshold:
                actual_direction = "hausse"
            elif actual_change_pct < -dir_threshold:
                actual_direction = "baisse"
            else:
                actual_direction = "stable"

            # Verifier si le signe du score correspond a la direction reelle
            directional_match = self._check_directional_match(
                combined_score, actual_change_pct
            )

            # Determiner si la prediction etait correcte (logique amelioree v1.2)
            correct = self._is_prediction_correct(
                predicted_action, actual_direction, actual_change_pct,
                predicted_score=combined_score, horizon_days=horizon,
                volatility=recent_volatility,
            )

            # Calculer le score de qualite (0-100)
            quality_score = self._compute_prediction_quality(
                predicted_action, combined_score, actual_change_pct,
                horizon_days=horizon, volatility=recent_volatility,
            )

            # Construire l'explication
            detail = self._build_outcome_detail(
                predicted_action, combined_score,
                actual_direction, actual_change_pct,
                horizon, correct, quality_score,
                dir_threshold,
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
                quality_score=round(quality_score, 1),
                directional_match=directional_match,
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
                "recent_volatility": recent_volatility,
            },
        )

    # ================================================================
    # DIRECTIONAL MATCH — Le signe du score correspond-il a la direction ?
    # ================================================================

    @staticmethod
    def _check_directional_match(score: int, actual_change_pct: float) -> bool:
        """
        Verifie si le signe du score correspond a la direction reelle.

        C'est la metrique la plus simple et la plus honnete :
        - Score > 0 et hausse → match
        - Score < 0 et baisse → match
        - Score ~0 et mouvement faible → match
        - Sinon → pas de match
        """
        if abs(score) <= 5 and abs(actual_change_pct) < 5:
            # Score neutre + petit mouvement = OK (le modele n'avait pas d'avis)
            return True
        if score > 5 and actual_change_pct > 0:
            return True
        if score < -5 and actual_change_pct < 0:
            return True
        if abs(score) <= 5:
            # Score neutre mais gros mouvement → pas de match
            return False
        return False

    # ================================================================
    # PREDICTION CORRECTE — Logique amelioree v1.2
    # ================================================================

    def _is_prediction_correct(
        self, predicted_action: str, actual_direction: str, actual_change_pct: float,
        predicted_score: int = 0, horizon_days: int = 7,
        volatility: Optional[float] = None,
    ) -> bool:
        """
        Determine si la prediction etait correcte.

        Logique v1.2 amelioree :
        - Utilise des seuils ADAPTATIFS bases sur la volatilite recente
        - "Acheter" est correct si la realite montre une hausse OU stable
          (mais INCORRECT si baisse au-dela du seuil adaptatif)
        - "Vendre" symetrique
        - "Attendre" utilise la logique du score directionnel + seuils adaptatifs
        """
        if predicted_action == ActionType.BUY.value:
            # Acheter = conviction haussiere
            # Correct si la realite n'est pas une baisse franche
            return actual_direction != "baisse"

        elif predicted_action == ActionType.SELL.value:
            # Vendre = conviction baissiere
            # Correct si la realite n'est pas une hausse franche
            return actual_direction != "hausse"

        else:
            # "Attendre" = score entre -25 et +25 (signal insuffisant)
            return self._is_hold_correct(
                predicted_score, actual_change_pct, actual_direction,
                horizon_days, volatility
            )

    def _is_hold_correct(
        self,
        score: int,
        actual_change_pct: float,
        actual_direction: str,
        horizon_days: int,
        volatility: Optional[float] = None,
    ) -> bool:
        """
        Evalue la justesse d'une prediction "attendre" (v1.2 avec volatilite adaptative).

        "Attendre" signifie que le modele n'avait pas assez de signal pour
        recommander acheter ou vendre. Le score (-25 a +25) indique un penchant.

        Logique v1.2 :
        1. Calcule la tolerance en fonction de la volatilite RECENTE
           (pas de seuils fixes arbitraires)
        2. Si le score a un penchant et la realite va dans ce sens → CORRECT
        3. Si le score a un penchant contraire mais mouvement < tolerance → CORRECT
        4. Si le score est neutre → CORRECT sauf mouvement > neutral_threshold
        """
        tolerance = self._get_adaptive_hold_tolerance(horizon_days, volatility)
        neutral_threshold = self._get_adaptive_neutral_threshold(horizon_days, volatility)

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
            # Score vraiment neutre (-5 a +5)
            # Correct sauf mouvement extreme que le modele aurait du detecter
            return abs(actual_change_pct) < neutral_threshold

    def _get_adaptive_hold_tolerance(
        self, horizon_days: int, volatility: Optional[float] = None
    ) -> float:
        """
        Marge d'erreur pour un penchant "attendre" — ADAPTATIVE.

        Basee sur la volatilite recente au lieu de seuils fixes.
        Tolerance = volatilite_quotidienne * sqrt(horizon) * facteur
        """
        if volatility is None or volatility <= 0:
            volatility = 3.0  # Fallback BTC typique

        # Mouvement attendu sur l'horizon
        expected_move = volatility * math.sqrt(horizon_days)

        # On tolere 1.0x le mouvement attendu quand le modele dit "attendre"
        # mais a un penchant directionnel
        return max(5.0, round(expected_move * 1.0, 2))

    def _get_adaptive_neutral_threshold(
        self, horizon_days: int, volatility: Optional[float] = None
    ) -> float:
        """
        Seuil de mouvement acceptable quand le modele est neutre (~score 0).
        ADAPTATIF base sur la volatilite recente.

        Un score neutre ne predit pas la stabilite — il dit "pas assez de signal".
        Mais si le marche bouge enormement, le modele aurait du detecter quelque chose.
        """
        if volatility is None or volatility <= 0:
            volatility = 3.0

        expected_move = volatility * math.sqrt(horizon_days)

        # On tolere 1.8x le mouvement attendu pour un score neutre
        # Au-dela, le modele aurait du donner un signal
        return max(8.0, round(expected_move * 1.8, 2))

    # ================================================================
    # SCORE DE QUALITE — 0 a 100
    # ================================================================

    @staticmethod
    def _compute_prediction_quality(
        predicted_action: str,
        score: int,
        actual_change_pct: float,
        horizon_days: int = 7,
        volatility: Optional[float] = None,
    ) -> float:
        """
        Calcule un score de qualite de la prediction de 0 a 100.

        Au lieu d'un simple correct/incorrect, on mesure COMMENT la prediction
        se compare a la realite :

        - 100 = prediction parfaite (acheter + forte hausse, vendre + forte baisse)
        - 75  = bonne prediction (direction correcte)
        - 50  = prediction neutre/acceptable (attendre + mouvement modere)
        - 25  = prediction mediocre (mauvaise direction mais faible)
        - 0   = prediction terrible (acheter + forte baisse)

        Le score de qualite tient compte de :
        1. L'alignement directionnel (score vs mouvement)
        2. La magnitude relative (un petit score qui "loupe" un gros mouvement = mauvais)
        3. La proportionnalite (fort score + fort mouvement dans le meme sens = excellent)
        """
        if volatility is None or volatility <= 0:
            volatility = 3.0

        expected_move = volatility * math.sqrt(horizon_days)
        if expected_move <= 0:
            expected_move = 5.0

        # 1. Alignement directionnel (0-50 points)
        if predicted_action == ActionType.BUY.value:
            # Acheter : qualite proportionnelle a la hausse
            if actual_change_pct > 0:
                dir_score = min(50.0, 30.0 + (actual_change_pct / expected_move) * 20.0)
            else:
                # Penalite proportionnelle a la baisse
                dir_score = max(0.0, 30.0 + (actual_change_pct / expected_move) * 30.0)
        elif predicted_action == ActionType.SELL.value:
            # Vendre : qualite proportionnelle a la baisse
            if actual_change_pct < 0:
                dir_score = min(50.0, 30.0 + (abs(actual_change_pct) / expected_move) * 20.0)
            else:
                dir_score = max(0.0, 30.0 - (actual_change_pct / expected_move) * 30.0)
        else:
            # Attendre : qualite proportionnelle a la stabilite
            abs_change = abs(actual_change_pct)
            if abs_change < expected_move * 0.5:
                dir_score = 40.0  # Marche stable, bon "attendre"
            elif abs_change < expected_move * 1.0:
                dir_score = 30.0  # Mouvement modere
            elif abs_change < expected_move * 1.5:
                dir_score = 20.0  # Le modele a rate un mouvement
            else:
                dir_score = 10.0  # Gros mouvement rate

            # Bonus si le penchant du score est dans le bon sens
            if score > 5 and actual_change_pct > 0:
                dir_score += 10.0
            elif score < -5 and actual_change_pct < 0:
                dir_score += 10.0
            elif abs(score) <= 5:
                dir_score += 5.0  # Pas de penchant = acceptable

        # 2. Proportionnalite score/mouvement (0-30 points)
        # Score normalise (0-100) vs mouvement normalise par volatilite
        abs_score = abs(score)
        norm_move = abs(actual_change_pct) / expected_move

        if predicted_action in (ActionType.BUY.value, ActionType.SELL.value):
            # Pour buy/sell, on veut un fort score ET un fort mouvement
            if (score > 0 and actual_change_pct > 0) or (score < 0 and actual_change_pct < 0):
                prop_score = min(30.0, (abs_score / 50.0) * 15.0 + norm_move * 15.0)
            else:
                prop_score = max(0.0, 15.0 - norm_move * 10.0)
        else:
            # Pour attendre, un score faible ET un mouvement faible = bien
            if abs_score < 15 and norm_move < 1.0:
                prop_score = 25.0
            elif abs_score < 25 and norm_move < 1.5:
                prop_score = 15.0
            else:
                prop_score = 5.0

        # 3. Bonus/malus confiance (0-20 points)
        if abs_score > 40:
            # Fort score = haute conviction, la penalite/bonus est amplifie
            if (score > 0 and actual_change_pct > 0) or (score < 0 and actual_change_pct < 0):
                conf_score = 20.0  # Haute conviction correcte = excellent
            else:
                conf_score = 0.0  # Haute conviction incorrecte = terrible
        elif abs_score > 20:
            if (score > 0 and actual_change_pct > 0) or (score < 0 and actual_change_pct < 0):
                conf_score = 15.0
            else:
                conf_score = 5.0
        else:
            conf_score = 10.0  # Faible conviction = score moyen

        quality = dir_score + prop_score + conf_score
        return max(0.0, min(100.0, quality))

    # ================================================================
    # DETAIL DU VERDICT
    # ================================================================

    def _build_outcome_detail(
        self,
        predicted_action: str,
        score: int,
        actual_direction: str,
        actual_change: float,
        horizon: int,
        correct: bool,
        quality_score: float,
        dir_threshold: float = 2.0,
    ) -> str:
        """Construit l'explication du verdict avec score de qualite."""
        action_label = {
            "acheter": "ACHETER",
            "vendre": "VENDRE",
            "attendre": "ATTENDRE",
        }.get(predicted_action, predicted_action.upper())

        verdict = "✅ CORRECT" if correct else "❌ INCORRECT"
        quality_label = (
            "excellent" if quality_score >= 75 else
            "bon" if quality_score >= 55 else
            "moyen" if quality_score >= 35 else
            "faible"
        )

        lean = ""
        if predicted_action == "attendre" and abs(score) > 5:
            lean_dir = "haussier" if score > 0 else "baissier"
            lean = f", penchant {lean_dir}"

        return (
            f"Prediction: {action_label} (score {score:+d}{lean}) → "
            f"Realite a {horizon}j: {actual_direction} ({actual_change:+.1f}%, seuil ±{dir_threshold:.1f}%) "
            f"— {verdict} (qualite: {quality_score:.0f}/100 = {quality_label})"
        )

    # ================================================================
    # INTÉGRITÉ DE L'HISTORIQUE
    # ================================================================

    def check_integrity(
        self, symbol: str = "BTC/USD", timeframe: str = "1d"
    ) -> HistoryIntegrityResponse:
        """
        Vérifie l'intégrité de l'historique chargé.

        Détecte les jours manquants entre min_date et max_date.
        Retourne un grade de qualité et la liste des trous.
        """
        range_info = self.get_history_range(symbol, timeframe)

        if not range_info.has_data:
            return HistoryIntegrityResponse(
                symbol=symbol,
                timeframe=timeframe,
                quality_grade="UNKNOWN",
                detail="Aucune donnée en base pour ce symbole/timeframe.",
            )

        # Récupérer toutes les dates de candles
        candle_dates = (
            self.db.query(Candle.timestamp)
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
            )
            .order_by(Candle.timestamp.asc())
            .all()
        )

        dates_set = set()
        for (ts,) in candle_dates:
            if isinstance(ts, datetime):
                # Normaliser à minuit UTC
                d = ts.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            else:
                d = ts
            dates_set.add(d.date() if isinstance(d, datetime) else d)

        # Calculer les dates attendues
        min_ts = candle_dates[0][0]
        max_ts = candle_dates[-1][0]

        if isinstance(min_ts, datetime):
            min_date = min_ts.replace(tzinfo=timezone.utc).date()
        else:
            min_date = min_ts

        if isinstance(max_ts, datetime):
            max_date = max_ts.replace(tzinfo=timezone.utc).date()
        else:
            max_date = max_ts

        # Pour timeframe 1d, on attend une candle par jour
        # Pour les autres timeframes, adapter le calcul
        step = self._get_timeframe_step(timeframe)
        expected_dates = set()
        current = min_date
        while current <= max_date:
            expected_dates.add(current)
            current += step

        # Trouver les trous
        missing_dates = sorted(expected_dates - dates_set)
        total_expected = len(expected_dates)
        total_actual = len(dates_set)
        missing_count = len(missing_dates)

        # Regrouper les trous consécutifs en plages
        gaps = self._group_consecutive_gaps(missing_dates)

        # Calculer la complétude
        completeness_pct = (total_actual / total_expected * 100) if total_expected > 0 else 0

        # Déterminer le grade
        if completeness_pct >= 99:
            grade = "EXCELLENT"
        elif completeness_pct >= 95:
            grade = "GOOD"
        elif completeness_pct >= 85:
            grade = "WARNING"
        else:
            grade = "CRITICAL"

        # Description lisible
        detail = (
            f"{total_actual}/{total_expected} candles ({completeness_pct:.1f}% complet). "
        )
        if missing_count == 0:
            detail += "Aucun trou detecte — historique parfait."
        elif missing_count <= 5:
            detail += f"{missing_count} jour(s) manquant(s) — impact negligeable sur les indicateurs."
        elif missing_count <= 20:
            detail += (
                f"{missing_count} jours manquants dans {len(gaps)} trou(s). "
                "Impact modere : les SMA longues (200j) peuvent etre legerement affectees."
            )
        else:
            detail += (
                f"{missing_count} jours manquants dans {len(gaps)} trou(s). "
                "⚠️ Impact significatif : les indicateurs techniques risquent d'etre fausses. "
                "Recommandation : recharger l'historique."
            )

        return HistoryIntegrityResponse(
            symbol=symbol,
            timeframe=timeframe,
            total_candles=total_actual,
            expected_candles=total_expected,
            missing_candles=missing_count,
            completeness_pct=round(completeness_pct, 2),
            gaps=gaps,
            min_date=str(min_date),
            max_date=str(max_date),
            quality_grade=grade,
            detail=detail,
        )

    @staticmethod
    def _get_timeframe_step(timeframe: str) -> timedelta:
        """Retourne le pas temporel pour un timeframe donné."""
        mapping = {
            "1m": timedelta(minutes=1),
            "3m": timedelta(minutes=3),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "2h": timedelta(hours=2),
            "4h": timedelta(hours=4),
            "6h": timedelta(hours=6),
            "8h": timedelta(hours=8),
            "12h": timedelta(hours=12),
            "1d": timedelta(days=1),
            "3d": timedelta(days=3),
            "1w": timedelta(weeks=1),
        }
        return mapping.get(timeframe, timedelta(days=1))

    @staticmethod
    def _group_consecutive_gaps(missing_dates: list) -> list[HistoryIntegrityGap]:
        """Regroupe les dates manquantes consécutives en plages."""
        if not missing_dates:
            return []

        gaps = []
        group_start = missing_dates[0]
        prev = missing_dates[0]

        for d in missing_dates[1:]:
            if (d - prev).days <= 1:
                prev = d
            else:
                gaps.append(HistoryIntegrityGap(
                    start_date=str(group_start),
                    end_date=str(prev),
                    missing_days=(prev - group_start).days + 1,
                ))
                group_start = d
                prev = d

        # Dernier groupe
        gaps.append(HistoryIntegrityGap(
            start_date=str(group_start),
            end_date=str(prev),
            missing_days=(prev - group_start).days + 1,
        ))

        return gaps

    # ================================================================
    # WALK-FORWARD
    # ================================================================

    def walk_forward(self, config: WalkForwardConfig) -> WalkForwardResult:
        """
        Analyse walk-forward : repete verify_at_date a intervalles reguliers.

        Si compare_mode=True, execute aussi en mode technique-only et compare.
        """
        t0 = time.time()

        start_dt = datetime.fromisoformat(config.start_date).replace(
            tzinfo=timezone.utc
        )
        end_dt = datetime.fromisoformat(config.end_date).replace(
            tzinfo=timezone.utc
        )

        target_dates: list[datetime] = []
        current = start_dt
        while current <= end_dt:
            target_dates.append(current)
            current += timedelta(days=config.step_days)

        logger.info(
            f"WalkForward: {len(target_dates)} points de verification "
            f"({config.start_date} → {config.end_date}, pas={config.step_days}j)"
        )

        # Run principal (avec sentiment si disponible en base)
        points = self._run_walk_forward_points(target_dates, config)

        accuracy_by_horizon = self._compute_accuracy(points, config.horizons)

        # Score qualite global
        all_quality_scores = []
        for acc in accuracy_by_horizon:
            if acc.total_points > 0:
                all_quality_scores.append(acc.avg_quality_score)
        overall_quality = (
            sum(all_quality_scores) / len(all_quality_scores)
            if all_quality_scores else 0.0
        )

        # Mode comparatif : technique-only vs technique+sentiment
        comparison = None
        if config.compare_mode:
            comparison = self._run_comparison(target_dates, config, points, accuracy_by_horizon, overall_quality)

        duration = round(time.time() - t0, 2)
        summary = self._build_walk_forward_summary(
            points, accuracy_by_horizon, duration, overall_quality
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
            overall_quality_score=round(overall_quality, 1),
            comparison=comparison,
        )

    def _run_walk_forward_points(
        self,
        target_dates: list[datetime],
        config: WalkForwardConfig,
        force_technical_only: bool = False,
    ) -> list[VerificationResult]:
        """Execute les points de verification walk-forward."""
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
                if force_technical_only:
                    result = self._verify_technical_only(request)
                else:
                    result = self.verify_at_date(request)
                if result.price_at_date > 0:
                    points.append(result)
            except Exception as e:
                logger.warning(f"WalkForward: erreur a {target_dt.date()}: {e}")
                continue

        return points

    def _verify_technical_only(self, request: VerificationRequest) -> VerificationResult:
        """
        Verification en mode 100% technique (force_technical_only).

        Crée un DecisionService temporaire qui ignore le sentiment historique
        en passant une date très ancienne où aucun sentiment n'existe.
        """
        target_dt = datetime.fromisoformat(request.target_date).replace(
            tzinfo=timezone.utc
        )

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

        # Exécuter le moteur de décision en forçant le mode sans sentiment
        # On utilise le DecisionService normal mais on patche temporairement
        # le sentiment_history_service pour qu'il retourne toujours None
        original_method = self.decision_service.sentiment_history_service.get_normalized_score_at_date

        try:
            # Forcer le mode technique-only en faisant échouer le lookup sentiment
            self.decision_service.sentiment_history_service.get_normalized_score_at_date = (
                lambda *args, **kwargs: None
            )
            decision = self.decision_service.analyze(
                symbol=request.symbol,
                timeframe=request.timeframe,
                history_days=request.history_days,
                end_ts=target_dt,
            )
        except Exception as e:
            logger.warning(f"Decision technique-only echouee a {request.target_date}: {e}")
            return VerificationResult(
                target_date=request.target_date,
                price_at_date=price_at_date,
                predicted_action="erreur",
                predicted_summary=f"Erreur moteur de decision: {str(e)}",
                outcomes=[],
                meta={"error": str(e)},
            )
        finally:
            # Restaurer la méthode originale
            self.decision_service.sentiment_history_service.get_normalized_score_at_date = original_method

        # Même logique que verify_at_date pour construire les outcomes
        recommendation = decision.get("recommendation", {})
        predicted_action = recommendation.get("action", "attendre")
        predicted_confidence = recommendation.get("confidence", "low")
        combined_score = decision.get("combined_score", 0)
        summary = decision.get("summary", "")

        scenarios = decision.get("scenarios", [])
        dominant_label = scenarios[0].get("label", "") if scenarios else ""
        dominant_prob = scenarios[0].get("probability", 0.0) if scenarios else 0.0

        recent_volatility = self._compute_recent_volatility(
            request.symbol, request.timeframe, target_dt
        )

        outcomes: list[HorizonOutcome] = []
        for horizon in request.horizons:
            horizon_dt = target_dt + timedelta(days=horizon)
            horizon_price, horizon_date_str = self._get_closest_price_at(
                request.symbol, request.timeframe, horizon_dt
            )

            if horizon_price is None:
                outcomes.append(HorizonOutcome(
                    horizon_days=horizon,
                    end_date=horizon_dt.isoformat(),
                    end_price=0, actual_change_pct=0,
                    actual_direction="inconnu", predicted_action=predicted_action,
                    predicted_score=combined_score, correct=False,
                    quality_score=0.0, directional_match=False,
                    detail=f"Pas de donnees disponibles a {horizon}j",
                ))
                continue

            actual_change_pct = (horizon_price - price_at_date) / price_at_date * 100
            dir_threshold, neutral_threshold = self._get_adaptive_thresholds(horizon, recent_volatility)

            if actual_change_pct > dir_threshold:
                actual_direction = "hausse"
            elif actual_change_pct < -dir_threshold:
                actual_direction = "baisse"
            else:
                actual_direction = "stable"

            directional_match = self._check_directional_match(combined_score, actual_change_pct)
            correct = self._is_prediction_correct(
                predicted_action, actual_direction, actual_change_pct,
                predicted_score=combined_score, horizon_days=horizon, volatility=recent_volatility,
            )
            quality_score = self._compute_prediction_quality(
                predicted_action, combined_score, actual_change_pct,
                horizon_days=horizon, volatility=recent_volatility,
            )
            detail = self._build_outcome_detail(
                predicted_action, combined_score, actual_direction, actual_change_pct,
                horizon, correct, quality_score, dir_threshold,
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
                quality_score=round(quality_score, 1),
                directional_match=directional_match,
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
                "sentiment_available": False,
                "rules_satisfied": sum(
                    1 for r in decision.get("rules_evaluated", []) if r.get("satisfied")
                ),
                "recent_volatility": recent_volatility,
                "mode": "technical_only",
            },
        )

    def _run_comparison(
        self,
        target_dates: list[datetime],
        config: WalkForwardConfig,
        with_sentiment_points: list[VerificationResult],
        with_sentiment_accuracy: list[HorizonAccuracy],
        with_sentiment_quality: float,
    ) -> WalkForwardComparison:
        """
        Exécute un walk-forward technique-only et compare avec le run sentiment.

        Retourne un WalkForwardComparison avec le delta de précision.
        """
        logger.info("WalkForward compare_mode: lancement du run technique-only...")

        # Run technique-only
        tech_points = self._run_walk_forward_points(target_dates, config, force_technical_only=True)
        tech_accuracy = self._compute_accuracy(tech_points, config.horizons)

        tech_quality_scores = []
        for acc in tech_accuracy:
            if acc.total_points > 0:
                tech_quality_scores.append(acc.avg_quality_score)
        tech_overall_quality = (
            sum(tech_quality_scores) / len(tech_quality_scores)
            if tech_quality_scores else 0.0
        )

        # Construire les stats résumées
        tech_stats = self._build_summary_stats(tech_points, tech_accuracy, tech_overall_quality)
        sentiment_stats = self._build_summary_stats(
            with_sentiment_points, with_sentiment_accuracy, with_sentiment_quality
        )

        # Calculer les deltas
        delta_accuracy = sentiment_stats.overall_accuracy_pct - tech_stats.overall_accuracy_pct
        delta_quality = sentiment_stats.overall_quality_score - tech_stats.overall_quality_score

        # Verdict lisible
        if delta_accuracy > 2:
            verdict = (
                f"✅ Le sentiment historique AMÉLIORE la précision de +{delta_accuracy:.1f}% "
                f"(qualité +{delta_quality:.1f} points). "
                f"Le modèle technique+sentiment ({sentiment_stats.overall_accuracy_pct:.0f}%) "
                f"surpasse le modèle technique seul ({tech_stats.overall_accuracy_pct:.0f}%)."
            )
        elif delta_accuracy < -2:
            verdict = (
                f"⚠️ Le sentiment historique DÉGRADE la précision de {delta_accuracy:.1f}% "
                f"(qualité {delta_quality:.1f} points). "
                f"Le modèle technique seul ({tech_stats.overall_accuracy_pct:.0f}%) "
                f"est meilleur que technique+sentiment ({sentiment_stats.overall_accuracy_pct:.0f}%)."
            )
        else:
            verdict = (
                f"➡️ Impact marginal du sentiment (delta {delta_accuracy:+.1f}%). "
                f"Technique seul: {tech_stats.overall_accuracy_pct:.0f}%, "
                f"technique+sentiment: {sentiment_stats.overall_accuracy_pct:.0f}%."
            )

        return WalkForwardComparison(
            technical_only=tech_stats,
            with_sentiment=sentiment_stats,
            sentiment_delta_accuracy_pct=round(delta_accuracy, 2),
            sentiment_delta_quality=round(delta_quality, 2),
            verdict=verdict,
        )

    def _build_summary_stats(
        self,
        points: list[VerificationResult],
        accuracy_by_horizon: list[HorizonAccuracy],
        overall_quality: float,
    ) -> WalkForwardSummaryStats:
        """Construit les stats résumées d'un walk-forward."""
        total_correct = 0
        total_points = 0
        total_directional = 0
        total_profitable = 0

        for acc in accuracy_by_horizon:
            total_correct += acc.correct
            total_points += acc.total_points
            # Weighted sum for directional and profitable
            if acc.total_points > 0:
                total_directional += acc.directional_accuracy_pct * acc.total_points / 100
                total_profitable += acc.profitable_direction_pct * acc.total_points / 100

        overall_accuracy = (total_correct / total_points * 100) if total_points > 0 else 0
        dir_accuracy = (total_directional / total_points * 100) if total_points > 0 else 0
        prof_pct = (total_profitable / total_points * 100) if total_points > 0 else 0

        return WalkForwardSummaryStats(
            total_points=len(points),
            overall_accuracy_pct=round(overall_accuracy, 1),
            overall_quality_score=round(overall_quality, 1),
            directional_accuracy_pct=round(dir_accuracy, 1),
            profitable_direction_pct=round(prof_pct, 1),
            accuracy_by_horizon=accuracy_by_horizon,
        )

    def _compute_accuracy(
        self, points: list[VerificationResult], horizons: list[int]
    ) -> list[HorizonAccuracy]:
        """Calcule la precision par horizon avec metriques avancees v1.2."""
        results: list[HorizonAccuracy] = []

        for horizon in horizons:
            correct_count = 0
            incorrect_count = 0
            total_score = 0
            total_change = 0
            buy_count = 0
            sell_count = 0
            hold_count = 0

            # Metriques v1.2
            directional_matches = 0
            total_quality = 0.0
            high_conf_correct = 0
            high_conf_total = 0
            profitable_count = 0

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

                    # Metriques v1.2
                    if outcome.directional_match:
                        directional_matches += 1

                    total_quality += outcome.quality_score

                    # High confidence = |score| > 25
                    if abs(outcome.predicted_score) > 25:
                        high_conf_total += 1
                        if outcome.correct:
                            high_conf_correct += 1

                    # Profitable = si on avait suivi le signal
                    is_profitable = (
                        (outcome.predicted_action == "acheter" and outcome.actual_change_pct > 0) or
                        (outcome.predicted_action == "vendre" and outcome.actual_change_pct < 0) or
                        (outcome.predicted_action == "attendre" and abs(outcome.actual_change_pct) < 10)
                    )
                    if is_profitable:
                        profitable_count += 1

            total = correct_count + incorrect_count
            accuracy = (correct_count / total * 100) if total > 0 else 0
            avg_score = total_score / total if total > 0 else 0
            avg_change = total_change / total if total > 0 else 0

            # Metriques v1.2
            dir_accuracy = (directional_matches / total * 100) if total > 0 else 0
            avg_quality = total_quality / total if total > 0 else 0
            high_conf_accuracy = (
                (high_conf_correct / high_conf_total * 100)
                if high_conf_total > 0 else 0
            )
            profitable_pct = (profitable_count / total * 100) if total > 0 else 0

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
                directional_accuracy_pct=round(dir_accuracy, 1),
                avg_quality_score=round(avg_quality, 1),
                high_confidence_accuracy_pct=round(high_conf_accuracy, 1),
                high_confidence_count=high_conf_total,
                profitable_direction_pct=round(profitable_pct, 1),
            ))

        return results

    def _build_walk_forward_summary(
        self,
        points: list[VerificationResult],
        accuracy_by_horizon: list[HorizonAccuracy],
        duration: float,
        overall_quality: float,
    ) -> str:
        """Resume lisible de l'analyse walk-forward v1.2."""
        if not points:
            return "Aucun point de verification genere."

        parts = [f"{len(points)} points analyses"]

        for acc in accuracy_by_horizon:
            if acc.total_points > 0:
                parts.append(
                    f"Horizon {acc.horizon_days}j: {acc.accuracy_pct:.0f}% correct "
                    f"({acc.correct}/{acc.total_points}), "
                    f"dir. {acc.directional_accuracy_pct:.0f}%, "
                    f"qualite {acc.avg_quality_score:.0f}/100"
                )
                if acc.high_confidence_count > 0:
                    parts.append(
                        f"  → Signaux forts: {acc.high_confidence_accuracy_pct:.0f}% "
                        f"({acc.high_confidence_count} signaux)"
                    )

        parts.append(f"Qualite globale: {overall_quality:.0f}/100")
        parts.append(f"({duration:.1f}s)")
        return " | ".join(parts)

