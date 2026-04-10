"""
MarketStructureService — Évaluation de la qualité de marché.

Ce service analyse la structure de marché à partir de la série de candles
pour déterminer si les conditions sont favorables au trading :

1. Position du prix dans le range récent (haut/bas/milieu)
2. Largeur du range vs ATR (tight = choppy, wide = directionnel)
3. Confirmation volume (volume/SMA20)
4. Micro-tendance (higher-highs/higher-lows)
5. VWAP approché (sum(close*volume)/sum(volume))

Le résultat est un score de qualité 0-100 :
- < 30 : no-trade zone (marché sans edge)
- 30-50 : qualité faible (prudence)
- > 50 : marché tradeable

PHILOSOPHIE : Ce service ne donne pas de direction, il évalue si le marché
offre un edge structurel suffisant pour que le moteur de signaux soit fiable.
Un RSI bullish dans un tight range sans volume n'est pas un vrai signal.

v1.9.8
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MarketQuality:
    """Résultat de l'évaluation de qualité de marché."""
    # Position du prix dans le range récent (0.0 = bas, 1.0 = haut)
    price_position_pct: float = 0.5
    # Largeur du range / ATR (< 1.5 = tight, > 3.0 = directionnel)
    range_width_atr: float = 2.0
    # Ratio volume / SMA20
    volume_ratio: float = 1.0
    # Score de micro-tendance (-5 à +5)
    micro_trend_score: int = 0
    # Distance du prix au VWAP approché en %
    vwap_distance_pct: float = 0.0
    # Score de qualité agrégé (0-100)
    quality_score: int = 50
    # Raisons lisibles
    reasons: list = None
    # Zone de prix : "high", "low", "mid" (indécis)
    price_zone: str = "mid"

    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []


class MarketStructureService:
    """
    Évalue la qualité de marché pour le gating d'entrée.

    Usage :
        service = MarketStructureService()
        quality = service.assess_quality(series)
        if quality.quality_score < 30:
            # no-trade zone
    """

    # Nombre de candles pour le range récent
    LOOKBACK = 20
    # Nombre de candles pour la micro-tendance
    MICRO_TREND_LOOKBACK = 5

    @classmethod
    def assess_quality(cls, series: list[dict]) -> MarketQuality:
        """
        Évalue la qualité du marché à partir de la série d'indicateurs.

        Args:
            series: Liste de dicts avec au minimum 'close', 'high', 'low',
                    'volume', 'volume_sma_20', 'atr_14'.

        Returns:
            MarketQuality avec le score de qualité et les métriques.
        """
        if not series or len(series) < 5:
            return MarketQuality(
                quality_score=25,
                reasons=["Données insuffisantes pour évaluer la structure de marché"],
            )

        # Prendre les N dernières candles pour le range
        lookback = min(cls.LOOKBACK, len(series))
        recent = series[-lookback:]
        latest = series[-1]

        close = latest.get("close")
        if close is None or close <= 0:
            return MarketQuality(
                quality_score=25,
                reasons=["Prix courant indisponible"],
            )

        reasons = []
        quality_components = []

        # ────────────────────────────────────────────────────────────
        # 1. Position du prix dans le range récent
        # ────────────────────────────────────────────────────────────
        highs = [c.get("high") or c.get("close", 0) for c in recent if c.get("high") or c.get("close")]
        lows = [c.get("low") or c.get("close", 0) for c in recent if c.get("low") or c.get("close")]

        high_n = max(highs) if highs else close
        low_n = min(lows) if lows else close
        range_n = high_n - low_n

        if range_n > 0:
            price_position = (close - low_n) / range_n
        else:
            price_position = 0.5

        # Zone de prix
        if price_position >= 0.7:
            price_zone = "high"
        elif price_position <= 0.3:
            price_zone = "low"
        else:
            price_zone = "mid"

        # Score de position : extrêmes = bien (momentum ou survente), milieu = mauvais
        # Un trade au milieu du range n'a pas de direction claire
        if price_position >= 0.75 or price_position <= 0.25:
            position_score = 70  # Bon : prix aux extrêmes
            reasons.append(f"Prix en zone {price_zone} ({price_position:.0%}) — momentum ou réaction")
        elif price_position >= 0.6 or price_position <= 0.4:
            position_score = 50  # Acceptable
            reasons.append(f"Prix en zone modérée ({price_position:.0%})")
        else:
            position_score = 20  # Mauvais : milieu du range
            reasons.append(f"Prix coincé au milieu du range ({price_position:.0%}) — zone indécise")

        quality_components.append(("position", position_score, 0.20))

        # ────────────────────────────────────────────────────────────
        # 2. Largeur du range vs ATR (détection tight range)
        # ────────────────────────────────────────────────────────────
        atr = latest.get("atr_14")
        if atr and atr > 0 and range_n > 0:
            range_atr = range_n / atr
        else:
            range_atr = 2.0  # Défaut neutre

        if range_atr >= 3.0:
            range_score = 80  # Marché directionnel
            reasons.append(f"Range large ({range_atr:.1f}x ATR) — marché directionnel")
        elif range_atr >= 2.0:
            range_score = 60  # Normal
            reasons.append(f"Range normal ({range_atr:.1f}x ATR)")
        elif range_atr >= 1.5:
            range_score = 35  # Tight
            reasons.append(f"Range étroit ({range_atr:.1f}x ATR) — marché compressé")
        else:
            range_score = 15  # Très tight — no-trade zone
            reasons.append(f"Range très étroit ({range_atr:.1f}x ATR) — bruit pur, no-trade")

        quality_components.append(("range", range_score, 0.25))

        # ────────────────────────────────────────────────────────────
        # 3. Confirmation volume
        # ────────────────────────────────────────────────────────────
        volume = latest.get("volume")
        volume_sma = latest.get("volume_sma_20")
        if volume and volume_sma and volume_sma > 0:
            vol_ratio = volume / volume_sma
        else:
            vol_ratio = 1.0  # Défaut neutre si pas de données volume

        if vol_ratio >= 1.5:
            volume_score = 85  # Volume fort — confirmation
            reasons.append(f"Volume fort ({vol_ratio:.1f}x SMA20) — mouvement confirmé")
        elif vol_ratio >= 1.0:
            volume_score = 60  # Volume normal
        elif vol_ratio >= 0.7:
            volume_score = 35  # Volume faible
            reasons.append(f"Volume faible ({vol_ratio:.1f}x SMA20) — manque de conviction")
        else:
            volume_score = 10  # Volume très faible — no-trade
            reasons.append(f"Volume très faible ({vol_ratio:.1f}x SMA20) — pas de participation")

        quality_components.append(("volume", volume_score, 0.25))

        # ────────────────────────────────────────────────────────────
        # 4. Micro-tendance (higher-highs / higher-lows)
        # ────────────────────────────────────────────────────────────
        mt_lookback = min(cls.MICRO_TREND_LOOKBACK, len(series) - 1)
        micro_score_val = 0

        if mt_lookback >= 2:
            recent_mt = series[-(mt_lookback + 1):]
            for i in range(1, len(recent_mt)):
                curr_h = recent_mt[i].get("high") or recent_mt[i].get("close", 0)
                prev_h = recent_mt[i - 1].get("high") or recent_mt[i - 1].get("close", 0)
                curr_l = recent_mt[i].get("low") or recent_mt[i].get("close", 0)
                prev_l = recent_mt[i - 1].get("low") or recent_mt[i - 1].get("close", 0)

                if curr_h > prev_h:
                    micro_score_val += 1  # Higher high
                elif curr_h < prev_h:
                    micro_score_val -= 1  # Lower high

                if curr_l > prev_l:
                    micro_score_val += 1  # Higher low
                elif curr_l < prev_l:
                    micro_score_val -= 1  # Lower low

        # Normaliser le micro-trend score
        abs_micro = abs(micro_score_val)
        if abs_micro >= 6:
            trend_score = 80  # Forte micro-tendance
            direction = "haussière" if micro_score_val > 0 else "baissière"
            reasons.append(f"Micro-tendance {direction} forte ({micro_score_val:+d})")
        elif abs_micro >= 3:
            trend_score = 55  # Micro-tendance modérée
        elif abs_micro >= 1:
            trend_score = 35  # Faible tendance
        else:
            trend_score = 15  # Pas de tendance — choppy
            reasons.append(f"Pas de micro-tendance ({micro_score_val:+d}) — marché choppy")

        quality_components.append(("micro_trend", trend_score, 0.20))

        # ────────────────────────────────────────────────────────────
        # 5. VWAP approché
        # ────────────────────────────────────────────────────────────
        vwap_distance = 0.0
        try:
            sum_cv = 0.0
            sum_v = 0.0
            for c in recent:
                c_close = c.get("close", 0) or 0
                c_vol = c.get("volume", 0) or 0
                if c_close > 0 and c_vol > 0:
                    sum_cv += c_close * c_vol
                    sum_v += c_vol
            if sum_v > 0:
                vwap_approx = sum_cv / sum_v
                vwap_distance = (close - vwap_approx) / close * 100
        except Exception:
            vwap_distance = 0.0

        # Le VWAP est un filtre de position : loin du VWAP = situation extrême
        abs_vwap_dist = abs(vwap_distance)
        if abs_vwap_dist >= 1.0:
            vwap_score = 70  # Loin du VWAP — mouvement significatif
        elif abs_vwap_dist >= 0.3:
            vwap_score = 50  # Normal
        else:
            vwap_score = 30  # Très proche du VWAP — pas de direction
            reasons.append(f"Prix très proche du VWAP ({vwap_distance:+.2f}%) — pas de direction")

        quality_components.append(("vwap", vwap_score, 0.10))

        # ────────────────────────────────────────────────────────────
        # Score agrégé pondéré
        # ────────────────────────────────────────────────────────────
        weighted_sum = sum(score * weight for _, score, weight in quality_components)
        total_weight = sum(weight for _, _, weight in quality_components)
        quality_score = int(round(weighted_sum / total_weight)) if total_weight > 0 else 50
        quality_score = max(0, min(100, quality_score))

        return MarketQuality(
            price_position_pct=round(price_position, 4),
            range_width_atr=round(range_atr, 2),
            volume_ratio=round(vol_ratio, 2),
            micro_trend_score=micro_score_val,
            vwap_distance_pct=round(vwap_distance, 4),
            quality_score=quality_score,
            reasons=reasons,
            price_zone=price_zone,
        )

    @classmethod
    def is_no_trade_zone(cls, quality: MarketQuality, min_quality: int = 30) -> bool:
        """
        Détermine si le marché est en no-trade zone.

        Args:
            quality: Résultat de assess_quality()
            min_quality: Score minimum pour trader (défaut: 30)

        Returns:
            True si le marché est en no-trade zone.
        """
        return quality.quality_score < min_quality

    @classmethod
    def is_long_quality_sufficient(
        cls,
        quality: MarketQuality,
        min_quality: int = 40,
        min_volume_ratio: float = 0.8,
    ) -> tuple[bool, str]:
        """
        Vérifie si la qualité est suffisante pour ouvrir un long scalping.

        Conditions :
        1. Quality score >= min_quality
        2. Volume ratio >= min_volume_ratio
        3. Pas dans le milieu du range (price_zone != "mid" ou micro_trend > 0)

        Returns:
            (is_sufficient, reason_if_rejected)
        """
        if quality.quality_score < min_quality:
            return False, (
                f"Qualité marché insuffisante ({quality.quality_score}/100 < {min_quality}) — "
                f"{'; '.join(quality.reasons[:2])}"
            )

        if quality.volume_ratio < min_volume_ratio:
            return False, (
                f"Volume insuffisant ({quality.volume_ratio:.2f}x < {min_volume_ratio}x SMA20)"
            )

        # Le milieu du range est acceptable si il y a une micro-tendance
        if quality.price_zone == "mid" and quality.micro_trend_score <= 0:
            return False, (
                f"Prix au milieu du range ({quality.price_position_pct:.0%}) "
                f"sans micro-tendance haussière ({quality.micro_trend_score:+d})"
            )

        return True, ""

