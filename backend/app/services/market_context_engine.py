"""
MarketContextEngine — Détection du régime de marché.

Analyse la série de candles pour déterminer le contexte :
- RANGE : marché latéral, bornes identifiables
- TREND : marché directionnel (up ou down)
- BREAKOUT : cassure d'un range avec volume

Fournit aussi :
- La zone dans le range (low / mid / high)
- La direction du trend (bullish / bearish / neutral)
- La volatilité relative (low / normal / high)
- Un score de confiance (0-100)

EXPÉRIMENTAL — utilisé uniquement par le Multi-Strategy Engine.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MarketContext:
    """Résultat complet de l'analyse de contexte."""
    # Régime principal
    regime: str = "unknown"  # "range", "trend", "breakout", "unknown"
    # Direction du trend (si applicable)
    trend_direction: str = "neutral"  # "bullish", "bearish", "neutral"
    # Zone dans le range (si range)
    zone: str = "mid"  # "low", "mid", "high"
    # Volatilité relative
    volatility: str = "normal"  # "low", "normal", "high"
    # Score de confiance dans le régime détecté (0-100)
    confidence: int = 50
    # Métriques sous-jacentes
    range_high: float = 0.0
    range_low: float = 0.0
    range_width_pct: float = 0.0
    atr_ratio: float = 1.0  # range / ATR
    price_position: float = 0.5  # 0.0 = bas, 1.0 = haut
    micro_trend_score: int = 0
    volume_ratio: float = 1.0
    ema_slope: float = 0.0  # Pente de l'EMA courte (normalisée)
    # Breakout
    breakout_direction: Optional[str] = None  # "up" / "down" si breakout
    breakout_strength: float = 0.0
    # Raisons lisibles
    reasons: list = field(default_factory=list)


class MarketContextEngine:
    """
    Moteur de détection du contexte de marché.

    Combine plusieurs signaux pour classifier le régime :
    1. Range width vs ATR → range ou trend
    2. EMA slope → direction
    3. Volume spike + price breakout → breakout
    4. Micro-trend → confirmation

    Usage :
        engine = MarketContextEngine()
        ctx = engine.analyze(series)
        if ctx.regime == "range" and ctx.zone == "low":
            # Mean reversion long
    """

    # Seuils de classification
    RANGE_ATR_MAX = 2.5          # range/ATR < 2.5 → probable range
    TREND_ATR_MIN = 3.0          # range/ATR > 3.0 → probable trend
    BREAKOUT_VOLUME_MIN = 1.8    # volume/SMA20 > 1.8 → breakout candidat
    BREAKOUT_PRICE_MOVE_PCT = 0.3  # mouvement > 0.3% sur dernière candle
    EMA_SLOPE_TREND_MIN = 0.02   # pente EMA normalisée > 0.02% → trend
    MICRO_TREND_STRONG = 4       # abs(micro_trend) >= 4 → trend confirmé
    LOOKBACK = 20                # candles pour le range
    EMA_PERIOD = 9               # EMA courte pour la pente

    @classmethod
    def analyze(cls, series: list[dict]) -> MarketContext:
        """
        Analyse la série de candles et retourne le contexte de marché.

        Args:
            series: Liste de dicts avec 'open', 'close', 'high', 'low',
                    'volume', 'volume_sma_20', 'atr_14', optionnel 'ema_9'.
        """
        if not series or len(series) < 10:
            return MarketContext(
                regime="unknown",
                confidence=0,
                reasons=["Données insuffisantes (< 10 candles)"],
            )

        lookback = min(cls.LOOKBACK, len(series))
        recent = series[-lookback:]
        latest = series[-1]
        prev = series[-2]

        close = latest.get("close", 0)
        if close <= 0:
            return MarketContext(regime="unknown", confidence=0,
                                reasons=["Prix indisponible"])

        reasons = []

        # ─────────────────────────────────────────────────────────────
        # 1. Range calculation
        # ─────────────────────────────────────────────────────────────
        highs = [c.get("high") or c.get("close", 0) for c in recent]
        lows = [c.get("low") or c.get("close", 0) for c in recent]
        range_high = max(highs) if highs else close
        range_low = min(lows) if lows else close
        range_width = range_high - range_low
        range_width_pct = (range_width / close * 100) if close > 0 else 0

        # Price position in range
        if range_width > 0:
            price_position = (close - range_low) / range_width
        else:
            price_position = 0.5

        # Zone classification
        if price_position >= 0.75:
            zone = "high"
        elif price_position <= 0.25:
            zone = "low"
        else:
            zone = "mid"

        # ─────────────────────────────────────────────────────────────
        # 2. ATR ratio (range vs volatility)
        # ─────────────────────────────────────────────────────────────
        atr = latest.get("atr_14")
        if atr and atr > 0:
            atr_ratio = range_width / atr
        else:
            atr_ratio = 2.0

        # ─────────────────────────────────────────────────────────────
        # 3. Volume ratio
        # ─────────────────────────────────────────────────────────────
        volume = latest.get("volume", 0) or 0
        volume_sma = latest.get("volume_sma_20", 0) or 0
        volume_ratio = volume / volume_sma if volume_sma > 0 else 1.0

        # ─────────────────────────────────────────────────────────────
        # 4. EMA slope (trend direction)
        # ─────────────────────────────────────────────────────────────
        ema_slope = cls._compute_ema_slope(series)

        # ─────────────────────────────────────────────────────────────
        # 5. Micro-trend
        # ─────────────────────────────────────────────────────────────
        micro_trend = cls._compute_micro_trend(series, lookback=5)

        # ─────────────────────────────────────────────────────────────
        # 6. Volatility classification
        # ─────────────────────────────────────────────────────────────
        if atr_ratio >= 4.0:
            volatility = "high"
        elif atr_ratio <= 1.5:
            volatility = "low"
        else:
            volatility = "normal"

        # ─────────────────────────────────────────────────────────────
        # 7. Breakout detection
        # ─────────────────────────────────────────────────────────────
        breakout_dir, breakout_strength = cls._detect_breakout(
            latest, prev, range_high, range_low, volume_ratio, close
        )

        # ─────────────────────────────────────────────────────────────
        # 8. Regime classification (decision tree)
        # ─────────────────────────────────────────────────────────────
        regime, trend_direction, confidence = cls._classify_regime(
            atr_ratio=atr_ratio,
            ema_slope=ema_slope,
            micro_trend=micro_trend,
            volume_ratio=volume_ratio,
            breakout_dir=breakout_dir,
            breakout_strength=breakout_strength,
            price_position=price_position,
            reasons=reasons,
        )

        return MarketContext(
            regime=regime,
            trend_direction=trend_direction,
            zone=zone,
            volatility=volatility,
            confidence=confidence,
            range_high=round(range_high, 2),
            range_low=round(range_low, 2),
            range_width_pct=round(range_width_pct, 4),
            atr_ratio=round(atr_ratio, 2),
            price_position=round(price_position, 4),
            micro_trend_score=micro_trend,
            volume_ratio=round(volume_ratio, 2),
            ema_slope=round(ema_slope, 6),
            breakout_direction=breakout_dir,
            breakout_strength=round(breakout_strength, 4),
            reasons=reasons,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def _compute_ema_slope(cls, series: list[dict]) -> float:
        """Calcule la pente normalisée de l'EMA courte sur les 3 dernières candles."""
        if len(series) < 4:
            return 0.0

        # Utiliser ema_9 si disponible, sinon fallback sur close
        ema_key = "ema_9"
        values = []
        for c in series[-4:]:
            val = c.get(ema_key) or c.get("close", 0)
            if val and val > 0:
                values.append(val)

        if len(values) < 3:
            return 0.0

        # Pente moyenne sur 3 périodes, normalisée par le prix
        slopes = [(values[i] - values[i - 1]) / values[i - 1] * 100
                  for i in range(1, len(values))]
        return sum(slopes) / len(slopes)

    @classmethod
    def _compute_micro_trend(cls, series: list[dict], lookback: int = 5) -> int:
        """Score micro-tendance : higher-highs/higher-lows → positif, inverse → négatif."""
        n = min(lookback, len(series) - 1)
        if n < 2:
            return 0

        score = 0
        recent = series[-(n + 1):]
        for i in range(1, len(recent)):
            curr_h = recent[i].get("high") or recent[i].get("close", 0)
            prev_h = recent[i - 1].get("high") or recent[i - 1].get("close", 0)
            curr_l = recent[i].get("low") or recent[i].get("close", 0)
            prev_l = recent[i - 1].get("low") or recent[i - 1].get("close", 0)

            if curr_h > prev_h:
                score += 1
            elif curr_h < prev_h:
                score -= 1
            if curr_l > prev_l:
                score += 1
            elif curr_l < prev_l:
                score -= 1

        return score

    @classmethod
    def _detect_breakout(
        cls, latest: dict, prev: dict,
        range_high: float, range_low: float,
        volume_ratio: float, close: float,
    ) -> tuple[Optional[str], float]:
        """
        Détecte un breakout (cassure de range avec volume).

        Returns:
            (direction, strength) — direction = "up"/"down"/None
        """
        if close <= 0:
            return None, 0.0

        prev_close = prev.get("close", 0) or 0
        if prev_close <= 0:
            return None, 0.0

        # Mouvement de la dernière candle
        move_pct = abs(close - prev_close) / prev_close * 100

        # Breakout up : prix proche du range_high + volume + mouvement
        if (close >= range_high * 0.998 and
                volume_ratio >= cls.BREAKOUT_VOLUME_MIN and
                move_pct >= cls.BREAKOUT_PRICE_MOVE_PCT and
                close > prev_close):
            strength = min(1.0, (volume_ratio - 1.0) * move_pct)
            return "up", strength

        # Breakout down
        if (close <= range_low * 1.002 and
                volume_ratio >= cls.BREAKOUT_VOLUME_MIN and
                move_pct >= cls.BREAKOUT_PRICE_MOVE_PCT and
                close < prev_close):
            strength = min(1.0, (volume_ratio - 1.0) * move_pct)
            return "down", strength

        return None, 0.0

    @classmethod
    def _classify_regime(
        cls, *,
        atr_ratio: float,
        ema_slope: float,
        micro_trend: int,
        volume_ratio: float,
        breakout_dir: Optional[str],
        breakout_strength: float,
        price_position: float,
        reasons: list,
    ) -> tuple[str, str, int]:
        """
        Classifie le régime de marché.

        Returns:
            (regime, trend_direction, confidence)
        """
        # ── BREAKOUT (priorité max) ───────────────────────────────
        if breakout_dir is not None and breakout_strength >= 0.3:
            direction = "bullish" if breakout_dir == "up" else "bearish"
            confidence = min(90, int(50 + breakout_strength * 40))
            reasons.append(
                f"BREAKOUT {breakout_dir} détecté (force={breakout_strength:.2f}, "
                f"volume={volume_ratio:.1f}x)"
            )
            return "breakout", direction, confidence

        # ── TREND (range large + EMA slope + micro-trend) ────────
        trend_signals = 0
        trend_dir_votes = []

        if atr_ratio >= cls.TREND_ATR_MIN:
            trend_signals += 1
            reasons.append(f"Range large ({atr_ratio:.1f}x ATR) → trend probable")

        if abs(ema_slope) >= cls.EMA_SLOPE_TREND_MIN:
            trend_signals += 1
            trend_dir_votes.append("bullish" if ema_slope > 0 else "bearish")
            reasons.append(f"EMA slope {ema_slope:+.3f}% → directionnel")

        if abs(micro_trend) >= cls.MICRO_TREND_STRONG:
            trend_signals += 1
            trend_dir_votes.append("bullish" if micro_trend > 0 else "bearish")
            reasons.append(f"Micro-trend fort ({micro_trend:+d}) → trend confirmé")

        if trend_signals >= 2:
            # Majorité bullish/bearish
            if trend_dir_votes:
                bullish_count = trend_dir_votes.count("bullish")
                bearish_count = trend_dir_votes.count("bearish")
                if bullish_count > bearish_count:
                    direction = "bullish"
                elif bearish_count > bullish_count:
                    direction = "bearish"
                else:
                    direction = "bullish" if ema_slope > 0 else "bearish"
            else:
                direction = "bullish" if micro_trend > 0 else "bearish"

            confidence = min(85, 40 + trend_signals * 15)
            return "trend", direction, confidence

        # ── RANGE (range étroit + pas de trend clair) ─────────────
        if atr_ratio <= cls.RANGE_ATR_MAX:
            reasons.append(
                f"Range étroit ({atr_ratio:.1f}x ATR), EMA plate "
                f"({ema_slope:+.3f}%) → range"
            )
            direction = "neutral"
            confidence = min(80, 40 + int((cls.RANGE_ATR_MAX - atr_ratio) * 20))
            return "range", direction, confidence

        # ── TRANSITION / UNCERTAIN ────────────────────────────────
        # Entre range et trend → faible confiance
        if abs(ema_slope) >= cls.EMA_SLOPE_TREND_MIN * 0.5:
            direction = "bullish" if ema_slope > 0 else "bearish"
        else:
            direction = "neutral"

        reasons.append(
            f"Régime mixte (ATR ratio={atr_ratio:.1f}, slope={ema_slope:+.3f}%, "
            f"micro={micro_trend:+d}) → prudence"
        )
        return "range", direction, 30  # Par défaut range avec faible confiance
