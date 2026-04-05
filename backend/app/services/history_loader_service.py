"""
Service de chargement d'historique profond depuis Binance.

Charge des annees de donnees OHLCV (2017→maintenant) en une seule operation,
via la pagination automatique de BinanceService.get_ohlcv().

Les donnees sont stockees en base via upsert (idempotent : relancer ne cree
pas de doublons).
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.services.binance_service import BinanceService
from app.models.candle import Candle
from app.utils.db_upsert import upsert_candles
from app.schemas.verification import HistoryLoadConfig, HistoryLoadResponse

logger = logging.getLogger(__name__)


class HistoryLoaderService:
    """
    Charge l'historique profond BTC depuis Binance.

    Supporte le chargement delta : si des données existent déjà en base,
    ne télécharge que le manquant (depuis la dernière candle).

    Usage :
        service = HistoryLoaderService(db_session)
        result = await service.load(HistoryLoadConfig(
            symbol="BTC/USD",
            timeframe="1d",
            start_date="2017-08-17",
        ))
    """

    def __init__(self, db: Session):
        self.db = db
        self.binance = BinanceService(timeout=60.0)

    def _get_latest_timestamp(self, symbol: str, timeframe: str) -> datetime | None:
        """Retourne le timestamp de la dernière candle en base, ou None."""
        return (
            self.db.query(func.max(Candle.timestamp))
            .filter(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
            )
            .scalar()
        )

    async def load(self, config: HistoryLoadConfig) -> HistoryLoadResponse:
        """
        Charge l'historique depuis Binance et le stocke en base.

        DELTA LOADING : si des données existent déjà en base, ne télécharge
        que le delta (depuis la dernière candle - petit overlap de sécurité).
        Cela réduit le temps de ~20s à ~1s lors des mises à jour.

        Binance BTCUSDT est disponible depuis le 17 aout 2017.
        Pour le timeframe 1d, cela represente ~3200 candles (quelques requetes).
        Pour le timeframe 4h, ~19 000 candles (~20 requetes).
        """
        t0 = time.time()

        # Parser les dates demandées
        original_start_dt = datetime.fromisoformat(config.start_date).replace(tzinfo=timezone.utc)
        if config.end_date:
            end_dt = datetime.fromisoformat(config.end_date).replace(tzinfo=timezone.utc)
        else:
            end_dt = datetime.now(timezone.utc)

        # Delta loading : vérifier ce qui est déjà en base
        # On recule de 2 candles en overlap pour capturer les éventuelles
        # candles incomplètes (la dernière candle peut être en cours)
        latest_in_db = self._get_latest_timestamp(config.symbol, config.timeframe)
        start_dt = original_start_dt

        if latest_in_db is not None:
            # Assurer que le timestamp est aware
            if latest_in_db.tzinfo is None:
                latest_in_db = latest_in_db.replace(tzinfo=timezone.utc)

            # Overlap de sécurité : 2 périodes en arrière
            overlap = self._get_overlap(config.timeframe)
            delta_start = latest_in_db - overlap

            if delta_start > original_start_dt:
                start_dt = delta_start
                logger.info(
                    f"HistoryLoader: delta mode — DB a des données jusqu'à "
                    f"{latest_in_db.isoformat()}, fetch depuis {start_dt.isoformat()} "
                    f"(au lieu de {original_start_dt.isoformat()})"
                )

        # Calculer le nombre de jours pour BinanceService
        delta_days = (end_dt - start_dt).days

        logger.info(
            f"HistoryLoader: chargement {config.symbol} {config.timeframe} "
            f"du {start_dt.date()} au {end_dt.date()} ({delta_days} jours)"
            f"{' [DELTA]' if latest_in_db and start_dt > original_start_dt else ' [FULL]'}"
        )

        # Fetch depuis Binance (pagination automatique)
        raw_candles = await self.binance.get_ohlcv(
            symbol=config.symbol,
            timeframe=config.timeframe,
            days=delta_days,
            start_time=start_dt,
            end_time=end_dt,
        )

        if not raw_candles:
            return HistoryLoadResponse(
                fetched=0,
                inserted=0,
                symbol=config.symbol,
                timeframe=config.timeframe,
                start_ts=start_dt.isoformat(),
                end_ts=end_dt.isoformat(),
                duration_seconds=round(time.time() - t0, 2),
            )

        # Convertir en format DB
        records = []
        for c in raw_candles:
            records.append({
                "symbol": config.symbol,
                "timeframe": config.timeframe,
                "timestamp": c["timestamp"],
                "open_price": c["open"],
                "high_price": c["high"],
                "low_price": c["low"],
                "close_price": c["close"],
                "volume": c["volume"],
                "source": "binance",
            })

        # Upsert en base par batches de 500 (eviter des requetes trop grosses)
        batch_size = 500
        total_inserted = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            total_inserted += upsert_candles(self.db, batch)

        duration = round(time.time() - t0, 2)

        logger.info(
            f"HistoryLoader: {len(raw_candles)} candles fetched, "
            f"{total_inserted} upserted in {duration}s"
        )

        actual_start = raw_candles[0]["timestamp"]
        actual_end = raw_candles[-1]["timestamp"]

        return HistoryLoadResponse(
            fetched=len(raw_candles),
            inserted=total_inserted,
            symbol=config.symbol,
            timeframe=config.timeframe,
            start_ts=actual_start.isoformat() if isinstance(actual_start, datetime) else str(actual_start),
            end_ts=actual_end.isoformat() if isinstance(actual_end, datetime) else str(actual_end),
            duration_seconds=duration,
        )

    @staticmethod
    def _get_overlap(timeframe: str) -> timedelta:
        """
        Retourne un overlap de sécurité de 2 périodes pour le delta loading.
        Cela permet de capturer les candles potentiellement incomplètes.
        """
        overlap_map = {
            "1m": timedelta(minutes=2),
            "5m": timedelta(minutes=10),
            "15m": timedelta(minutes=30),
            "30m": timedelta(hours=1),
            "1h": timedelta(hours=2),
            "4h": timedelta(hours=8),
            "1d": timedelta(days=2),
            "1w": timedelta(weeks=2),
        }
        return overlap_map.get(timeframe, timedelta(hours=8))

