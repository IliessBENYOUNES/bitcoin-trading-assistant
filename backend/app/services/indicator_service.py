"""
Service de calcul des indicateurs techniques.

Ce service :
1. Charge les candles depuis la base de données
2. Convertit en DataFrame pandas (ordre chronologique ASC)
3. Calcule les indicateurs techniques via pandas-ta-classic
4. Retourne une liste de dicts avec null pour les NaN

INDICATEURS CALCULÉS :
- RSI(14)           : Relative Strength Index
- MACD(12,26,9)     : Moving Average Convergence Divergence
- SMA(20,50,200)    : Simple Moving Averages
- Bollinger(20,2)   : Bandes de Bollinger

LOGIQUE DE FENÊTRE :
- end_ts : paramètre fourni (aligné bucket) OU max_ts en base
- start_ts : end_ts - history_days
- Ancrage sur complétude (pas sur NOW)
"""

import numpy as np
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Candle
from app.utils import (
    VALID_TIMEFRAMES,
    get_timeframe_hours,
    is_valid_timeframe,
    normalize_to_utc,
    align_to_bucket,
    calculate_freshness_status,
    calculate_global_status,
    nan_to_none,
)


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

class IndicatorService:
    """
    Service pour calculer les indicateurs techniques.

    Usage :
        service = IndicatorService(db_session)
        result = service.calculate(
            symbol="BTC/USD",
            timeframe="4h",
            history_days=7,
            end_ts=None,
            include_candles=False
        )
    """

    def __init__(self, db: Session):
        """Initialise le service avec une session DB."""
        self.db = db

    def _get_max_ts(self, symbol: str, timeframe: str) -> Optional[datetime]:
        """Récupère le timestamp maximum en base."""
        result = self.db.query(func.max(Candle.timestamp)).filter(
            Candle.symbol == symbol,
            Candle.timeframe == timeframe
        ).scalar()

        if result:
            return normalize_to_utc(result)
        return None

    def _load_candles(
            self,
            symbol: str,
            timeframe: str,
            start_ts: datetime,
            end_ts: datetime
    ) -> list[Candle]:
        """Charge les candles depuis la DB, triés ASC."""
        candles = self.db.query(Candle).filter(
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp >= start_ts,
            Candle.timestamp <= end_ts
        ).order_by(Candle.timestamp.asc()).all()

        return candles

    def _candles_to_dataframe(self, candles: list[Candle]) -> pd.DataFrame:
        """Convertit une liste de Candle en DataFrame pandas."""
        data = []
        for c in candles:
            data.append({
                "timestamp": normalize_to_utc(c.timestamp),
                "open": c.open_price,
                "high": c.high_price,
                "low": c.low_price,
                "close": c.close_price,
                "volume": c.volume,
            })

        df = pd.DataFrame(data)

        if df.empty:
            return df

        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcule tous les indicateurs techniques sur le DataFrame."""
        if df.empty:
            return df

        # RSI(14) — warmup contractuel
        RSI_LEN = 14
        rsi = ta.rsi(df["close"], length=RSI_LEN)

        if rsi is not None:
            rsi = rsi.copy()
            warmup = min(RSI_LEN, len(rsi))
            rsi.iloc[:warmup] = np.nan
            df["rsi_14"] = rsi
        else:
            df["rsi_14"] = np.nan

        # MACD(12, 26, 9)
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            df["macd"] = macd.iloc[:, 0] if macd.shape[1] > 0 else None
            df["macd_hist"] = macd.iloc[:, 1] if macd.shape[1] > 1 else None
            df["macd_signal"] = macd.iloc[:, 2] if macd.shape[1] > 2 else None
        else:
            df["macd"] = None
            df["macd_signal"] = None
            df["macd_hist"] = None

        # SMA(20, 50, 200)
        sma20 = ta.sma(df["close"], length=20)
        sma50 = ta.sma(df["close"], length=50)
        sma200 = ta.sma(df["close"], length=200)

        df["sma_20"] = sma20 if sma20 is not None else None
        df["sma_50"] = sma50 if sma50 is not None else None
        df["sma_200"] = sma200 if sma200 is not None else None

        # Bollinger Bands(20, 2)
        bbands = ta.bbands(df["close"], length=20, std=2)
        if bbands is not None and not bbands.empty:
            df["bb_lower"] = bbands.iloc[:, 0] if bbands.shape[1] > 0 else None
            df["bb_mid"] = bbands.iloc[:, 1] if bbands.shape[1] > 1 else None
            df["bb_upper"] = bbands.iloc[:, 2] if bbands.shape[1] > 2 else None
        else:
            df["bb_lower"] = None
            df["bb_mid"] = None
            df["bb_upper"] = None

        # ADX(14) — Average Directional Index : mesure la FORCE de la tendance
        # ADX > 25 = tendance forte, ADX < 20 = pas de tendance (range)
        # Essentiel pour filtrer les faux signaux en marche lateraux
        ADX_LEN = 14
        adx_result = ta.adx(df["high"], df["low"], df["close"], length=ADX_LEN)
        if adx_result is not None and not adx_result.empty:
            # pandas_ta adx() retourne : ADX, DMP (+DI), DMN (-DI)
            df["adx_14"] = adx_result.iloc[:, 0] if adx_result.shape[1] > 0 else None
            df["plus_di"] = adx_result.iloc[:, 1] if adx_result.shape[1] > 1 else None
            df["minus_di"] = adx_result.iloc[:, 2] if adx_result.shape[1] > 2 else None
        else:
            df["adx_14"] = None
            df["plus_di"] = None
            df["minus_di"] = None

        # Volume SMA(20) — pour confirmer les mouvements par le volume
        # Un signal technique sans confirmation volume est moins fiable
        if "volume" in df.columns:
            vol_sma = ta.sma(df["volume"], length=20)
            df["volume_sma_20"] = vol_sma if vol_sma is not None else None
        else:
            df["volume_sma_20"] = None

        return df

    def _check_completeness(
            self,
            candles_count: int,
            start_ts: datetime,
            end_ts: datetime,
            timeframe: str
    ) -> tuple[str, int, int]:
        """Vérifie la complétude de la série."""
        tf_hours = get_timeframe_hours(timeframe)
        total_hours = (end_ts - start_ts).total_seconds() / 3600
        expected_count = int(total_hours / tf_hours) + 1

        missing_count = max(0, expected_count - candles_count)

        if missing_count == 0:
            return "OK", expected_count, 0
        else:
            return "GAPS_DETECTED", expected_count, missing_count

    def _dataframe_to_series(
            self,
            df: pd.DataFrame,
            include_candles: bool
    ) -> list[dict]:
        """Convertit le DataFrame en liste de dicts pour JSON."""
        series = []

        indicator_cols = [
            "rsi_14", "macd", "macd_signal", "macd_hist",
            "sma_20", "sma_50", "sma_200",
            "bb_mid", "bb_upper", "bb_lower",
            "adx_14", "plus_di", "minus_di",
            "volume_sma_20",
        ]

        for _, row in df.iterrows():
            point = {
                "ts": row["timestamp"].isoformat(),
                "close": nan_to_none(row["close"]),
            }

            if include_candles:
                point["open"] = nan_to_none(row["open"])
                point["high"] = nan_to_none(row["high"])
                point["low"] = nan_to_none(row["low"])
                point["volume"] = nan_to_none(row["volume"])

            for col in indicator_cols:
                if col in df.columns:
                    point[col] = nan_to_none(row[col])
                else:
                    point[col] = None

            series.append(point)

        return series

    def calculate(
            self,
            symbol: str = "BTC/USD",
            timeframe: str = "4h",
            history_days: float = 7,
            end_ts: Optional[datetime] = None,
            include_candles: bool = False
    ) -> dict:
        """Calcule les indicateurs techniques."""
        # Validation timeframe
        if not is_valid_timeframe(timeframe):
            raise ValueError(
                f"Timeframe invalide: {timeframe}. "
                f"Valides: {list(VALID_TIMEFRAMES.keys())}"
            )

        tf_hours = get_timeframe_hours(timeframe)
        now_ts = datetime.now(timezone.utc)

        # Récupérer max_ts en base
        max_ts = self._get_max_ts(symbol, timeframe)

        if max_ts is None:
            return {
                "meta": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "history_days": history_days,
                    "error": "Aucune donnée en base pour ce symbol/timeframe",
                    "now_ts": now_ts.isoformat(),
                    "max_ts": None,
                    "global_status": "NO_DATA"
                },
                "series": [],
                "latest": None
            }

        # Déterminer effective_end_ts
        if end_ts is not None:
            effective_end_ts = normalize_to_utc(end_ts)
            effective_end_ts = align_to_bucket(effective_end_ts, timeframe)
            effective_end_ts = min(effective_end_ts, max_ts)
        else:
            effective_end_ts = align_to_bucket(max_ts, timeframe)

        # Calculer start_ts
        start_ts = effective_end_ts - timedelta(days=history_days)

        # Charger les candles
        candles = self._load_candles(symbol, timeframe, start_ts, effective_end_ts)

        # Convertir en DataFrame
        df = self._candles_to_dataframe(candles)

        # Vérifier complétude
        completeness_status, expected_count, missing_count = self._check_completeness(
            len(candles), start_ts, effective_end_ts, timeframe
        )

        # Calculer fraîcheur
        data_lag = now_ts - max_ts
        data_lag_hours = round(data_lag.total_seconds() / 3600, 2)
        freshness_status = calculate_freshness_status(data_lag_hours, timeframe)

        # Calculer status global
        global_status = calculate_global_status(completeness_status, freshness_status)

        # Calculer indicateurs si données présentes
        if not df.empty:
            df = self._calculate_indicators(df)

        # Convertir en série JSON
        series = self._dataframe_to_series(df, include_candles)

        # Extraire latest (dernier point)
        latest = series[-1] if series else None

        # Construire la réponse
        return {
            "meta": {
                "symbol": symbol,
                "timeframe": timeframe,
                "history_days": history_days,
                "start_ts": start_ts.isoformat(),
                "end_ts": effective_end_ts.isoformat(),
                "now_ts": now_ts.isoformat(),
                "max_ts": max_ts.isoformat(),
                "count": len(series),
                "expected_count": expected_count,
                "missing_count": missing_count,
                "data_lag_hours": data_lag_hours,
                "freshness_status": freshness_status,
                "completeness_status": completeness_status,
                "global_status": global_status
            },
            "series": series,
            "latest": latest
        }