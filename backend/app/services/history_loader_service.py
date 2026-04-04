"""
Service de chargement d'historique profond depuis Binance.

Charge des annees de donnees OHLCV (2017→maintenant) en une seule operation,
via la pagination automatique de BinanceService.get_ohlcv().

Les donnees sont stockees en base via upsert (idempotent : relancer ne cree
pas de doublons).
"""

import time
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.services.binance_service import BinanceService
from app.utils.db_upsert import upsert_candles
from app.schemas.verification import HistoryLoadConfig, HistoryLoadResponse

logger = logging.getLogger(__name__)


class HistoryLoaderService:
    """
    Charge l'historique profond BTC depuis Binance.

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

    async def load(self, config: HistoryLoadConfig) -> HistoryLoadResponse:
        """
        Charge l'historique depuis Binance et le stocke en base.

        Binance BTCUSDT est disponible depuis le 17 aout 2017.
        Pour le timeframe 1d, cela represente ~3200 candles (quelques requetes).
        Pour le timeframe 4h, ~19 000 candles (~20 requetes).
        """
        t0 = time.time()

        # Parser les dates
        start_dt = datetime.fromisoformat(config.start_date).replace(tzinfo=timezone.utc)
        if config.end_date:
            end_dt = datetime.fromisoformat(config.end_date).replace(tzinfo=timezone.utc)
        else:
            end_dt = datetime.now(timezone.utc)

        # Calculer le nombre de jours pour BinanceService
        delta_days = (end_dt - start_dt).days

        logger.info(
            f"HistoryLoader: chargement {config.symbol} {config.timeframe} "
            f"du {config.start_date} au {end_dt.date()} ({delta_days} jours)"
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

