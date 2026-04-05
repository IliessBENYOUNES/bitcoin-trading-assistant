"""
Service de sentiment historique — chargement et requête.

Ce service gère :
1. Le chargement du Fear & Greed Index depuis Alternative.me (gratuit, depuis fév. 2018)
2. Le stockage en base via upsert idempotent
3. La requête de sentiment à une date donnée (pour le DecisionService en mode backtest)

API Alternative.me Fear & Greed :
- URL : https://api.alternative.me/fng/?limit=0&format=json
- Gratuit, pas de clé API requise
- Retourne tous les points depuis février 2018 en une seule requête
- Format : { data: [ { value: "25", value_classification: "Extreme Fear", timestamp: "1517443200" }, ... ] }

NORMALISATION :
- Fear & Greed brut : 0-100 (0=peur extrême, 100=avidité extrême)
- Score normalisé : -100 à +100 (compatible avec le moteur de décision)
- Formule : (raw - 50) * 2
  → 0 raw = -100 normalized (peur extrême)
  → 50 raw = 0 normalized (neutre)
  → 100 raw = +100 normalized (avidité extrême)
"""

import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.sentiment_history import SentimentHistory
from app.schemas.sentiment import (
    SentimentLoadConfig,
    SentimentLoadResponse,
    SentimentRangeResponse,
    SentimentAtDateResponse,
    SentimentCoverageResponse,
)

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES
# ============================================================

FEAR_AND_GREED_API_URL = "https://api.alternative.me/fng/"
FEAR_AND_GREED_SOURCE = "fear_and_greed"
FEAR_AND_GREED_TIMEOUT = 30  # secondes

# Mapping des labels Fear & Greed
FEAR_AND_GREED_LABELS = {
    "Extreme Fear": "Peur extrême",
    "Fear": "Peur",
    "Neutral": "Neutre",
    "Greed": "Avidité",
    "Extreme Greed": "Avidité extrême",
}


# ============================================================
# SERVICE
# ============================================================

class SentimentHistoryService:
    """
    Service de gestion du sentiment historique.

    Usage :
        service = SentimentHistoryService(db_session)
        result = service.load_fear_and_greed()  # Charge tout l'historique
        sentiment = service.get_sentiment_at_date("2020-06-01")  # Score à une date
    """

    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # NORMALISATION
    # ================================================================

    @staticmethod
    def normalize_fear_and_greed(raw_score: float) -> float:
        """
        Normalise un score Fear & Greed (0-100) en score -100/+100.

        0 (peur extrême) → -100
        50 (neutre)      → 0
        100 (avidité)    → +100
        """
        return round((raw_score - 50) * 2, 1)

    # ================================================================
    # CHARGEMENT FEAR & GREED
    # ================================================================

    def load_fear_and_greed(
        self, config: Optional[SentimentLoadConfig] = None
    ) -> SentimentLoadResponse:
        """
        Charge l'historique complet du Fear & Greed Index depuis Alternative.me.

        L'API retourne TOUS les points en une seule requête (~2900 jours).
        On fait un upsert idempotent : relancer ne crée pas de doublons.
        """
        t0 = time.time()

        if config is None:
            config = SentimentLoadConfig(source=FEAR_AND_GREED_SOURCE)

        # Récupérer les données depuis l'API
        # limit=0 = tous les points disponibles
        try:
            response = httpx.get(
                FEAR_AND_GREED_API_URL,
                params={"limit": 0, "format": "json"},
                timeout=FEAR_AND_GREED_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Erreur HTTP Fear & Greed API: {e}")
            return SentimentLoadResponse(
                source=FEAR_AND_GREED_SOURCE,
                duration_seconds=round(time.time() - t0, 2),
            )
        except Exception as e:
            logger.error(f"Erreur inattendue Fear & Greed API: {e}")
            return SentimentLoadResponse(
                source=FEAR_AND_GREED_SOURCE,
                duration_seconds=round(time.time() - t0, 2),
            )

        raw_points = data.get("data", [])
        if not raw_points:
            logger.warning("Fear & Greed API: aucune donnée retournée")
            return SentimentLoadResponse(
                source=FEAR_AND_GREED_SOURCE,
                fetched=0,
                duration_seconds=round(time.time() - t0, 2),
            )

        logger.info(f"Fear & Greed API: {len(raw_points)} points récupérés")

        # Filtrer par dates si spécifié
        start_dt = None
        end_dt = None
        if config.start_date:
            start_dt = datetime.fromisoformat(config.start_date).replace(tzinfo=timezone.utc)
        if config.end_date:
            end_dt = datetime.fromisoformat(config.end_date).replace(tzinfo=timezone.utc)

        # Upsert en base
        inserted = 0
        updated = 0
        skipped = 0

        for point in raw_points:
            try:
                raw_score = float(point.get("value", 0))
                timestamp_unix = int(point.get("timestamp", 0))
                label = point.get("value_classification", "")

                if timestamp_unix == 0:
                    continue

                point_date = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
                # Normaliser à minuit UTC
                point_date = point_date.replace(hour=0, minute=0, second=0, microsecond=0)

                # Filtrage par date
                if start_dt and point_date < start_dt:
                    continue
                if end_dt and point_date > end_dt:
                    continue

                normalized = self.normalize_fear_and_greed(raw_score)

                # Upsert : chercher si le point existe déjà
                existing = (
                    self.db.query(SentimentHistory)
                    .filter(
                        SentimentHistory.date == point_date,
                        SentimentHistory.source == FEAR_AND_GREED_SOURCE,
                    )
                    .first()
                )

                if existing:
                    if existing.raw_score != raw_score:
                        existing.raw_score = raw_score
                        existing.normalized_score = normalized
                        existing.label = label
                        existing.raw_data = json.dumps(point)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    new_entry = SentimentHistory(
                        date=point_date,
                        source=FEAR_AND_GREED_SOURCE,
                        raw_score=raw_score,
                        normalized_score=normalized,
                        label=label,
                        raw_data=json.dumps(point),
                    )
                    self.db.add(new_entry)
                    inserted += 1

            except Exception as e:
                logger.warning(f"Erreur traitement point Fear & Greed: {e}")
                continue

        # Commit en une seule transaction
        self.db.commit()

        # Récupérer le total en base
        total_in_db = (
            self.db.query(func.count(SentimentHistory.id))
            .filter(SentimentHistory.source == FEAR_AND_GREED_SOURCE)
            .scalar()
        ) or 0

        # Plage de dates
        min_date = (
            self.db.query(func.min(SentimentHistory.date))
            .filter(SentimentHistory.source == FEAR_AND_GREED_SOURCE)
            .scalar()
        )
        max_date = (
            self.db.query(func.max(SentimentHistory.date))
            .filter(SentimentHistory.source == FEAR_AND_GREED_SOURCE)
            .scalar()
        )

        duration = round(time.time() - t0, 2)

        logger.info(
            f"Fear & Greed: {inserted} insérés, {updated} mis à jour, "
            f"{skipped} identiques ({duration}s)"
        )

        return SentimentLoadResponse(
            source=FEAR_AND_GREED_SOURCE,
            fetched=len(raw_points),
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            total_in_db=total_in_db,
            date_range_start=min_date.isoformat() if min_date else None,
            date_range_end=max_date.isoformat() if max_date else None,
            duration_seconds=duration,
        )

    # ================================================================
    # REQUÊTE DE SENTIMENT À UNE DATE
    # ================================================================

    def get_sentiment_at_date(
        self,
        target_date: str,
        source: str = FEAR_AND_GREED_SOURCE,
        tolerance_days: int = 3,
    ) -> Optional[SentimentAtDateResponse]:
        """
        Récupère le sentiment le plus proche d'une date donnée.

        Cherche d'abord une correspondance exacte, puis dans une fenêtre
        de ±tolerance_days.

        Args:
            target_date: Date ISO (ex: "2020-06-01")
            source: Source de sentiment
            tolerance_days: Marge de tolérance en jours

        Returns:
            SentimentAtDateResponse ou None si aucun point trouvé
        """
        target_dt = datetime.fromisoformat(target_date).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )

        # 1. Chercher une correspondance exacte
        exact = (
            self.db.query(SentimentHistory)
            .filter(
                SentimentHistory.date == target_dt,
                SentimentHistory.source == source,
            )
            .first()
        )

        if exact:
            return SentimentAtDateResponse(
                date=target_date,
                source=source,
                raw_score=exact.raw_score,
                normalized_score=exact.normalized_score,
                label=exact.label,
                exact_match=True,
                actual_date=exact.date.isoformat() if isinstance(exact.date, datetime) else str(exact.date),
            )

        # 2. Chercher le point le plus proche dans la fenêtre
        window_start = target_dt - timedelta(days=tolerance_days)
        window_end = target_dt + timedelta(days=tolerance_days)

        candidates = (
            self.db.query(SentimentHistory)
            .filter(
                SentimentHistory.source == source,
                SentimentHistory.date >= window_start,
                SentimentHistory.date <= window_end,
            )
            .all()
        )

        if not candidates:
            return None

        # Trouver le plus proche
        def _ensure_aware(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        closest = min(
            candidates,
            key=lambda c: abs((_ensure_aware(c.date) - target_dt).total_seconds()),
        )

        return SentimentAtDateResponse(
            date=target_date,
            source=source,
            raw_score=closest.raw_score,
            normalized_score=closest.normalized_score,
            label=closest.label,
            exact_match=False,
            actual_date=closest.date.isoformat() if isinstance(closest.date, datetime) else str(closest.date),
        )

    # ================================================================
    # SENTIMENT NORMALISÉ POUR LE DECISION SERVICE
    # ================================================================

    def get_normalized_score_at_date(
        self, target_date: str, source: str = FEAR_AND_GREED_SOURCE
    ) -> Optional[float]:
        """
        Retourne le score normalisé (-100/+100) à une date donnée.

        Méthode simplifiée utilisée par le DecisionService en mode backtest.
        Retourne None si aucun sentiment disponible.
        """
        result = self.get_sentiment_at_date(target_date, source)
        if result is None:
            return None
        return result.normalized_score

    # ================================================================
    # PLAGE DE DATES DISPONIBLE
    # ================================================================

    def get_range(self, source: str = FEAR_AND_GREED_SOURCE) -> SentimentRangeResponse:
        """Retourne la plage de dates disponible pour une source."""
        min_date = (
            self.db.query(func.min(SentimentHistory.date))
            .filter(SentimentHistory.source == source)
            .scalar()
        )
        max_date = (
            self.db.query(func.max(SentimentHistory.date))
            .filter(SentimentHistory.source == source)
            .scalar()
        )
        total = (
            self.db.query(func.count(SentimentHistory.id))
            .filter(SentimentHistory.source == source)
            .scalar()
        ) or 0

        return SentimentRangeResponse(
            source=source,
            min_date=min_date.isoformat() if min_date else None,
            max_date=max_date.isoformat() if max_date else None,
            total_points=total,
            has_data=total > 0,
        )

    # ================================================================
    # COUVERTURE GLOBALE
    # ================================================================

    def get_coverage(self) -> SentimentCoverageResponse:
        """Résumé de la couverture sentiment disponible (toutes sources)."""
        # Lister les sources distinctes
        sources = (
            self.db.query(SentimentHistory.source)
            .distinct()
            .all()
        )

        source_ranges = []
        total = 0
        earliest = None
        latest = None

        for (source_name,) in sources:
            range_resp = self.get_range(source_name)
            source_ranges.append(range_resp)
            total += range_resp.total_points

            if range_resp.min_date:
                if earliest is None or range_resp.min_date < earliest:
                    earliest = range_resp.min_date
            if range_resp.max_date:
                if latest is None or range_resp.max_date > latest:
                    latest = range_resp.max_date

        return SentimentCoverageResponse(
            sources=source_ranges,
            total_points=total,
            earliest_date=earliest,
            latest_date=latest,
        )

