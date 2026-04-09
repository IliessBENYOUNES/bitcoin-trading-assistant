"""
Service d'interprétation des indicateurs techniques en signaux.

Ce service :
1. Récupère les indicateurs via IndicatorService
2. Interprète chaque indicateur en un signal structuré (direction, force, message)
3. Agrège les signaux en un score composite -100/+100
4. Génère un résumé lisible

INTERPRÉTEURS :
- RSI(14)           : Surachat (>70), survente (<30), zones intermédiaires
- MACD(12,26,9)     : Croisement ligne/signal, position histogramme
- SMA(20,50,200)    : Position du prix par rapport aux moyennes mobiles
- Bollinger(20,2)   : Position du prix dans les bandes

SCORE COMPOSITE :
- Chaque signal bullish contribue +strength, bearish -strength
- Score normalisé sur -100/+100
- Confiance basée sur la convergence des signaux
"""

from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.indicator_service import IndicatorService
from app.schemas.signal import (
    SignalItem,
    SignalDirection,
    CompositeScore,
    ConfidenceLevel,
    SignalResponse,
)


# ============================================================
# INTERPRÉTEURS INDIVIDUELS
# ============================================================

def interpret_rsi(rsi: Optional[float]) -> Optional[SignalItem]:
    """
    Interprète le RSI(14) en signal.

    Zones :
    - >= 80 : Fortement suracheté → bearish fort
    - >= 70 : Suracheté → bearish modéré
    - <= 20 : Fortement survendu → bullish fort
    - <= 30 : Survendu → bullish modéré
    - 30-45 : Légèrement baissier
    - 55-70 : Légèrement haussier
    - 45-55 : Neutre
    """
    if rsi is None:
        return None

    if rsi >= 80:
        return SignalItem(
            indicator="rsi",
            direction=SignalDirection.BEARISH,
            strength=0.9,
            value=round(rsi, 2),
            message=f"RSI fortement suracheté ({rsi:.0f}) — pression vendeuse élevée",
        )
    elif rsi >= 70:
        return SignalItem(
            indicator="rsi",
            direction=SignalDirection.BEARISH,
            strength=0.7,
            value=round(rsi, 2),
            message=f"RSI en surachat ({rsi:.0f}) — zone de prudence haussière",
        )
    elif rsi <= 20:
        return SignalItem(
            indicator="rsi",
            direction=SignalDirection.BULLISH,
            strength=0.9,
            value=round(rsi, 2),
            message=f"RSI fortement survendu ({rsi:.0f}) — rebond probable",
        )
    elif rsi <= 30:
        return SignalItem(
            indicator="rsi",
            direction=SignalDirection.BULLISH,
            strength=0.7,
            value=round(rsi, 2),
            message=f"RSI en survente ({rsi:.0f}) — opportunité d'achat possible",
        )
    elif rsi <= 45:
        return SignalItem(
            indicator="rsi",
            direction=SignalDirection.BEARISH,
            strength=0.3,
            value=round(rsi, 2),
            message=f"RSI légèrement baissier ({rsi:.0f})",
        )
    elif rsi >= 55:
        return SignalItem(
            indicator="rsi",
            direction=SignalDirection.BULLISH,
            strength=0.3,
            value=round(rsi, 2),
            message=f"RSI légèrement haussier ({rsi:.0f})",
        )
    else:
        return SignalItem(
            indicator="rsi",
            direction=SignalDirection.NEUTRAL,
            strength=0.1,
            value=round(rsi, 2),
            message=f"RSI neutre ({rsi:.0f}) — pas de signal clair",
        )


def interpret_macd(
    macd: Optional[float],
    macd_signal: Optional[float],
    macd_hist: Optional[float],
    close: Optional[float] = None,
) -> Optional[SignalItem]:
    """
    Interprète le MACD(12,26,9) en signal.

    Logique :
    - MACD > Signal ET hist > 0 : Bullish (croisé haussier confirmé)
    - MACD < Signal ET hist < 0 : Bearish (croisé baissier confirmé)
    - Sinon : Neutre
    - La force dépend de l'amplitude RELATIVE de l'histogramme (% du prix)

    NOTE v1.2 : On utilise des seuils en % du prix au lieu de seuils absolus.
    Cela corrige un biais majeur : a $3000 un MACD diff de 50 = 1.67%,
    a $100000 un MACD diff de 50 = 0.05%. Les seuils absolus rendaient
    le MACD toujours "fort" aux prix eleves et toujours "faible" aux prix bas.
    """
    if macd is None or macd_signal is None:
        return None

    hist = macd_hist if macd_hist is not None else (macd - macd_signal)
    diff = macd - macd_signal

    # Normaliser par le prix pour des seuils adaptatifs
    # Si pas de close disponible, fallback sur seuils absolus classiques
    if close and close > 0:
        pct_diff = abs(diff) / close * 100  # en % du prix
        # Seuils en % du prix (calibres sur BTC historique)
        if pct_diff > 1.5:
            strength = 0.9
        elif pct_diff > 0.8:
            strength = 0.7
        elif pct_diff > 0.3:
            strength = 0.5
        elif pct_diff > 0.1:
            strength = 0.3
        else:
            strength = 0.1
    else:
        # Fallback seuils absolus (compatibilite)
        abs_diff = abs(diff)
        if abs_diff > 500:
            strength = 0.9
        elif abs_diff > 200:
            strength = 0.7
        elif abs_diff > 50:
            strength = 0.5
        elif abs_diff > 10:
            strength = 0.3
        else:
            strength = 0.1

    if diff > 0 and hist > 0:
        return SignalItem(
            indicator="macd",
            direction=SignalDirection.BULLISH,
            strength=strength,
            value=round(diff, 2),
            message=f"MACD croisé haussier (diff: {diff:+.0f}, hist: {hist:+.0f})",
        )
    elif diff < 0 and hist < 0:
        return SignalItem(
            indicator="macd",
            direction=SignalDirection.BEARISH,
            strength=strength,
            value=round(diff, 2),
            message=f"MACD croisé baissier (diff: {diff:+.0f}, hist: {hist:+.0f})",
        )
    elif diff > 0:
        return SignalItem(
            indicator="macd",
            direction=SignalDirection.BULLISH,
            strength=max(0.1, strength - 0.2),
            value=round(diff, 2),
            message=f"MACD au-dessus du signal mais histogramme négatif (transition)",
        )
    elif diff < 0:
        return SignalItem(
            indicator="macd",
            direction=SignalDirection.BEARISH,
            strength=max(0.1, strength - 0.2),
            value=round(diff, 2),
            message=f"MACD sous le signal mais histogramme positif (transition)",
        )
    else:
        return SignalItem(
            indicator="macd",
            direction=SignalDirection.NEUTRAL,
            strength=0.1,
            value=0.0,
            message="MACD et Signal alignés — pas de divergence",
        )


def interpret_sma(
    close: Optional[float],
    sma_20: Optional[float],
    sma_50: Optional[float],
    sma_200: Optional[float],
) -> Optional[SignalItem]:
    """
    Interprète la position du prix par rapport aux SMA.

    Logique :
    - Prix > SMA20 > SMA50 > SMA200 : Forte tendance haussière
    - Prix > SMA20 et SMA50         : Tendance haussière modérée
    - Prix > SMA20                   : Léger biais haussier
    - Prix < SMA20 < SMA50 < SMA200 : Forte tendance baissière
    - etc. (miroir)
    """
    if close is None or sma_20 is None:
        return None

    above_20 = close > sma_20
    above_50 = close > sma_50 if sma_50 is not None else None
    above_200 = close > sma_200 if sma_200 is not None else None

    # Compter les SMA au-dessus/dessous
    score = 0
    count = 0

    if above_20:
        score += 1
    else:
        score -= 1
    count += 1

    if above_50 is not None:
        if above_50:
            score += 1
        else:
            score -= 1
        count += 1

    if above_200 is not None:
        if above_200:
            score += 1
        else:
            score -= 1
        count += 1

    # Déterminer la direction et la force
    if score == count:
        # Au-dessus de toutes les SMA
        direction = SignalDirection.BULLISH
        strength = min(0.9, 0.4 + count * 0.2)
        parts = []
        parts.append(f"SMA20 ({sma_20:,.0f})")
        if sma_50 is not None:
            parts.append(f"SMA50 ({sma_50:,.0f})")
        if sma_200 is not None:
            parts.append(f"SMA200 ({sma_200:,.0f})")
        message = f"Prix ({close:,.0f}) au-dessus de {', '.join(parts)} — tendance haussière"
    elif score == -count:
        # En dessous de toutes les SMA
        direction = SignalDirection.BEARISH
        strength = min(0.9, 0.4 + count * 0.2)
        parts = []
        parts.append(f"SMA20 ({sma_20:,.0f})")
        if sma_50 is not None:
            parts.append(f"SMA50 ({sma_50:,.0f})")
        if sma_200 is not None:
            parts.append(f"SMA200 ({sma_200:,.0f})")
        message = f"Prix ({close:,.0f}) sous {', '.join(parts)} — tendance baissière"
    elif score > 0:
        direction = SignalDirection.BULLISH
        strength = 0.4
        message = f"Prix ({close:,.0f}) au-dessus de certaines SMA — biais haussier modéré"
    elif score < 0:
        direction = SignalDirection.BEARISH
        strength = 0.4
        message = f"Prix ({close:,.0f}) sous certaines SMA — biais baissier modéré"
    else:
        direction = SignalDirection.NEUTRAL
        strength = 0.1
        message = f"Prix ({close:,.0f}) entre les SMA — pas de tendance claire"

    return SignalItem(
        indicator="sma",
        direction=direction,
        strength=strength,
        value=round(close, 2),
        message=message,
    )


def interpret_bollinger(
    close: Optional[float],
    bb_upper: Optional[float],
    bb_mid: Optional[float],
    bb_lower: Optional[float],
) -> Optional[SignalItem]:
    """
    Interprète la position du prix dans les bandes de Bollinger.

    Logique :
    - Prix >= bb_upper : Suracheté (bearish)
    - Prix <= bb_lower : Survendu (bullish)
    - Prix entre mid et upper : Légèrement haussier
    - Prix entre lower et mid : Légèrement baissier
    """
    if close is None or bb_upper is None or bb_lower is None or bb_mid is None:
        return None

    # Calculer la position relative dans les bandes (0=lower, 1=upper)
    band_width = bb_upper - bb_lower
    if band_width <= 0:
        return SignalItem(
            indicator="bollinger",
            direction=SignalDirection.NEUTRAL,
            strength=0.1,
            value=round(close, 2),
            message="Bandes de Bollinger trop serrées — pas de signal",
        )

    position = (close - bb_lower) / band_width  # 0 à 1 (peut dépasser)

    if close >= bb_upper:
        strength = min(0.9, 0.6 + (position - 1.0) * 0.5)
        return SignalItem(
            indicator="bollinger",
            direction=SignalDirection.BEARISH,
            strength=round(strength, 2),
            value=round(close, 2),
            message=f"Prix ({close:,.0f}) au-dessus de la bande supérieure ({bb_upper:,.0f}) — suracheté",
        )
    elif close <= bb_lower:
        strength = min(0.9, 0.6 + (0.0 - position) * 0.5)
        return SignalItem(
            indicator="bollinger",
            direction=SignalDirection.BULLISH,
            strength=round(strength, 2),
            value=round(close, 2),
            message=f"Prix ({close:,.0f}) sous la bande inférieure ({bb_lower:,.0f}) — survendu",
        )
    elif close > bb_mid:
        strength = round(0.1 + (position - 0.5) * 0.6, 2)
        return SignalItem(
            indicator="bollinger",
            direction=SignalDirection.BULLISH,
            strength=min(0.5, max(0.1, strength)),
            value=round(close, 2),
            message=f"Prix ({close:,.0f}) dans la moitié supérieure des bandes — légèrement haussier",
        )
    elif close < bb_mid:
        strength = round(0.1 + (0.5 - position) * 0.6, 2)
        return SignalItem(
            indicator="bollinger",
            direction=SignalDirection.BEARISH,
            strength=min(0.5, max(0.1, strength)),
            value=round(close, 2),
            message=f"Prix ({close:,.0f}) dans la moitié inférieure des bandes — légèrement baissier",
        )
    else:
        return SignalItem(
            indicator="bollinger",
            direction=SignalDirection.NEUTRAL,
            strength=0.1,
            value=round(close, 2),
            message=f"Prix ({close:,.0f}) au milieu des bandes de Bollinger",
        )


def interpret_adx(
    adx: Optional[float],
    plus_di: Optional[float] = None,
    minus_di: Optional[float] = None,
) -> Optional[SignalItem]:
    """
    Interprète l'ADX(14) — Average Directional Index.

    L'ADX mesure la FORCE de la tendance, pas sa direction.
    Le croisement DI+/DI- indique la direction.

    Logique :
    - ADX >= 40 : Tendance très forte → confirme la direction DI
    - ADX >= 25 : Tendance forte → signal modéré dans la direction DI
    - ADX 20-25 : Tendance faible émergente
    - ADX < 20  : Pas de tendance (range) → réduit la fiabilité des autres signaux

    L'ADX est crucial pour filtrer les faux signaux :
    quand ADX < 20, RSI et MACD donnent beaucoup de faux positifs.
    """
    if adx is None:
        return None

    # Déterminer la direction via DI+/DI-
    if plus_di is not None and minus_di is not None:
        di_bullish = plus_di > minus_di
    else:
        di_bullish = True  # Défaut neutre si pas de DI

    if adx >= 40:
        direction = SignalDirection.BULLISH if di_bullish else SignalDirection.BEARISH
        return SignalItem(
            indicator="adx",
            direction=direction,
            strength=0.8,
            value=round(adx, 2),
            message=f"ADX très élevé ({adx:.0f}) — tendance {'haussière' if di_bullish else 'baissière'} très forte",
        )
    elif adx >= 25:
        direction = SignalDirection.BULLISH if di_bullish else SignalDirection.BEARISH
        return SignalItem(
            indicator="adx",
            direction=direction,
            strength=0.5,
            value=round(adx, 2),
            message=f"ADX ({adx:.0f}) indique une tendance {'haussière' if di_bullish else 'baissière'} confirmée",
        )
    elif adx >= 20:
        direction = SignalDirection.BULLISH if di_bullish else SignalDirection.BEARISH
        return SignalItem(
            indicator="adx",
            direction=direction,
            strength=0.2,
            value=round(adx, 2),
            message=f"ADX ({adx:.0f}) — tendance faible émergente",
        )
    else:
        # ADX < 20 : pas de tendance → neutre
        # Ce signal neutre est important : il réduit la confiance du composite
        return SignalItem(
            indicator="adx",
            direction=SignalDirection.NEUTRAL,
            strength=0.1,
            value=round(adx, 2),
            message=f"ADX bas ({adx:.0f}) — marché sans tendance, signaux peu fiables",
        )


def interpret_volume_trend(
    volume: Optional[float],
    volume_sma: Optional[float],
) -> Optional[SignalItem]:
    """
    Interprète le rapport volume/volume_SMA(20).

    Un mouvement de prix confirmé par le volume est plus fiable.
    Un mouvement sans volume est suspect.

    Logique :
    - Volume > 1.5x SMA → forte confirmation (ne donne pas de direction seul)
    - Volume > 1.2x SMA → confirmation modérée
    - Volume < 0.5x SMA → volume anormalement bas → signal neutre/méfiance
    - Sinon → volume normal, pas de signal additionnel

    NOTE : L'interpréteur volume retourne toujours NEUTRAL car il ne
    donne pas de direction. Il agit comme un modificateur de confiance
    pour les autres signaux via le score composite.
    """
    if volume is None or volume_sma is None or volume_sma <= 0:
        return None

    ratio = volume / volume_sma

    if ratio > 2.0:
        return SignalItem(
            indicator="volume",
            direction=SignalDirection.NEUTRAL,
            strength=0.05,  # Faible poids direct, mais la meta sera utilisée
            value=round(ratio, 2),
            message=f"Volume très élevé ({ratio:.1f}x SMA20) — mouvement significatif confirmé",
        )
    elif ratio > 1.5:
        return SignalItem(
            indicator="volume",
            direction=SignalDirection.NEUTRAL,
            strength=0.05,
            value=round(ratio, 2),
            message=f"Volume supérieur à la moyenne ({ratio:.1f}x SMA20) — confirmation",
        )
    elif ratio < 0.5:
        return SignalItem(
            indicator="volume",
            direction=SignalDirection.NEUTRAL,
            strength=0.05,
            value=round(ratio, 2),
            message=f"Volume très faible ({ratio:.1f}x SMA20) — méfiance sur le mouvement",
        )
    else:
        # Volume normal → pas de signal particulier
        return None


def interpret_stoch_rsi(
    k: Optional[float],
    d: Optional[float],
) -> Optional[SignalItem]:
    """
    Interprète le Stochastic RSI (14,14,3,3).

    Le StochRSI est plus sensible que le RSI classique pour détecter
    les retournements à court terme, surtout DANS les tendances.
    Le RSI classique peut rester suracheté pendant des semaines en
    bull run ; le StochRSI oscille plus et détecte les micro-corrections.

    Logique :
    - K >= 90 : Extrêmement suracheté → bearish fort
    - K >= 80 et D >= 80 : Suracheté confirmé → bearish modéré
    - K <= 10 : Extrêmement survendu → bullish fort
    - K <= 20 et D <= 20 : Survendu confirmé → bullish modéré
    - Croisement K au-dessus de D (en zone basse) : bullish
    - Croisement K en-dessous de D (en zone haute) : bearish
    """
    if k is None:
        return None

    # Normaliser K entre 0 et 100 (pandas_ta retourne 0-100)
    k_val = max(0, min(100, k))
    d_val = max(0, min(100, d)) if d is not None else None

    if k_val >= 90:
        return SignalItem(
            indicator="stoch_rsi",
            direction=SignalDirection.BEARISH,
            strength=0.8,
            value=round(k_val, 2),
            message=f"StochRSI extrêmement suracheté (K={k_val:.0f}) — retournement probable",
        )
    elif k_val >= 80 and d_val is not None and d_val >= 75:
        return SignalItem(
            indicator="stoch_rsi",
            direction=SignalDirection.BEARISH,
            strength=0.6,
            value=round(k_val, 2),
            message=f"StochRSI suracheté (K={k_val:.0f}, D={d_val:.0f}) — prudence",
        )
    elif k_val <= 10:
        return SignalItem(
            indicator="stoch_rsi",
            direction=SignalDirection.BULLISH,
            strength=0.8,
            value=round(k_val, 2),
            message=f"StochRSI extrêmement survendu (K={k_val:.0f}) — rebond probable",
        )
    elif k_val <= 20 and d_val is not None and d_val <= 25:
        return SignalItem(
            indicator="stoch_rsi",
            direction=SignalDirection.BULLISH,
            strength=0.6,
            value=round(k_val, 2),
            message=f"StochRSI survendu (K={k_val:.0f}, D={d_val:.0f}) — opportunité",
        )
    elif d_val is not None and k_val > d_val and k_val < 40:
        # Croisement haussier en zone basse → signal d'achat
        strength = 0.5 if k_val < 25 else 0.3
        return SignalItem(
            indicator="stoch_rsi",
            direction=SignalDirection.BULLISH,
            strength=strength,
            value=round(k_val, 2),
            message=f"StochRSI croisement haussier (K={k_val:.0f} > D={d_val:.0f}) en zone basse",
        )
    elif d_val is not None and k_val < d_val and k_val > 60:
        # Croisement baissier en zone haute → signal de vente
        strength = 0.5 if k_val > 75 else 0.3
        return SignalItem(
            indicator="stoch_rsi",
            direction=SignalDirection.BEARISH,
            strength=strength,
            value=round(k_val, 2),
            message=f"StochRSI croisement baissier (K={k_val:.0f} < D={d_val:.0f}) en zone haute",
        )
    else:
        # Zone neutre → pas de signal particulier
        return None


def interpret_ema_cross(
    ema_9: Optional[float],
    ema_21: Optional[float],
    prev_ema_9: Optional[float],
    prev_ema_21: Optional[float],
    close: Optional[float] = None,
) -> Optional[SignalItem]:
    """
    Interprète le croisement EMA(9) / EMA(21).

    Le croisement EMA rapide/lente est un signal de tendance classique
    plus réactif que les SMA. Il capture les changements de momentum
    1 à 3 candles plus tôt que le croisement SMA(20)/SMA(50).

    Logique :
    - EMA9 > EMA21 alors que prev_EMA9 <= prev_EMA21 : Golden cross → bullish
    - EMA9 < EMA21 alors que prev_EMA9 >= prev_EMA21 : Death cross → bearish
    - EMA9 > EMA21 (position) : biais haussier
    - EMA9 < EMA21 (position) : biais baissier
    - Force proportionnelle à l'écart relatif EMA9-EMA21
    """
    if ema_9 is None or ema_21 is None:
        return None

    diff = ema_9 - ema_21

    # Calculer l'écart en % du prix pour une force normalisée
    ref_price = close if close and close > 0 else ema_21
    if ref_price and ref_price > 0:
        pct_diff = abs(diff) / ref_price * 100
    else:
        pct_diff = 0

    # Détecter les croisements (si on a les valeurs précédentes)
    is_crossover_up = False
    is_crossover_down = False
    if prev_ema_9 is not None and prev_ema_21 is not None:
        prev_diff = prev_ema_9 - prev_ema_21
        if diff > 0 and prev_diff <= 0:
            is_crossover_up = True
        elif diff < 0 and prev_diff >= 0:
            is_crossover_down = True

    if is_crossover_up:
        # Golden cross EMA : signal fort
        strength = min(0.8, 0.6 + pct_diff * 0.2)
        return SignalItem(
            indicator="ema_cross",
            direction=SignalDirection.BULLISH,
            strength=round(strength, 2),
            value=round(diff, 2),
            message=f"EMA9 croise EMA21 à la hausse — golden cross ({pct_diff:.2f}%)",
        )
    elif is_crossover_down:
        # Death cross EMA : signal fort
        strength = min(0.8, 0.6 + pct_diff * 0.2)
        return SignalItem(
            indicator="ema_cross",
            direction=SignalDirection.BEARISH,
            strength=round(strength, 2),
            value=round(diff, 2),
            message=f"EMA9 croise EMA21 à la baisse — death cross ({pct_diff:.2f}%)",
        )
    elif diff > 0:
        # Position haussière (pas de croisement récent)
        if pct_diff > 1.0:
            strength = 0.5
        elif pct_diff > 0.3:
            strength = 0.3
        else:
            strength = 0.15
        return SignalItem(
            indicator="ema_cross",
            direction=SignalDirection.BULLISH,
            strength=strength,
            value=round(diff, 2),
            message=f"EMA9 ({ema_9:,.0f}) > EMA21 ({ema_21:,.0f}) — momentum haussier",
        )
    elif diff < 0:
        # Position baissière
        if pct_diff > 1.0:
            strength = 0.5
        elif pct_diff > 0.3:
            strength = 0.3
        else:
            strength = 0.15
        return SignalItem(
            indicator="ema_cross",
            direction=SignalDirection.BEARISH,
            strength=strength,
            value=round(diff, 2),
            message=f"EMA9 ({ema_9:,.0f}) < EMA21 ({ema_21:,.0f}) — momentum baissier",
        )
    else:
        return None


# ============================================================
# AGRÉGATION : SCORE COMPOSITE (v1.3 — régime-based weighting)
# ============================================================

# Multiplicateurs de pondération par régime de marché.
# En tendance forte (ADX ≥ 25), les indicateurs de tendance (MACD, SMA, EMA)
# sont plus fiables. En range (ADX < 20), les oscillateurs (RSI, Bollinger,
# StochRSI) sont plus fiables. Ce sont des biais mathématiquement justifiés.
REGIME_WEIGHTS = {
    "trending": {
        # Indicateurs de tendance boostés
        "macd": 1.3, "sma": 1.3, "ema_cross": 1.4,
        # Oscillateurs réduits (faux signaux fréquents en tendance)
        "rsi": 0.6, "bollinger": 0.6, "stoch_rsi": 0.7,
    },
    "ranging": {
        # Indicateurs de tendance réduits (whipsaws)
        "macd": 0.6, "sma": 0.6, "ema_cross": 0.5,
        # Oscillateurs boostés (fonctionnent bien en range)
        "rsi": 1.3, "bollinger": 1.3, "stoch_rsi": 1.4,
    },
}


def compute_composite_score(signals: list[SignalItem]) -> CompositeScore:
    """
    Agrège les signaux individuels en un score composite.

    Algorithme v1.3 (régime-based weighting) :
    1. Identifie le régime de marché via l'ADX :
       - ADX >= 25 : trending → booste les indicateurs de tendance
       - ADX < 20 : ranging → booste les oscillateurs
       - ADX 20-25 ou absent : neutre → pas de modification
    2. Chaque signal directional contribue ±strength × regime_multiplier
    3. L'ADX et le volume agissent comme modificateurs globaux
    4. Score normalisé sur -100/+100
    5. Confiance basée sur convergence + ADX + nombre de signaux
    """
    if not signals:
        return CompositeScore(
            score=0,
            direction=SignalDirection.NEUTRAL,
            confidence=ConfidenceLevel.LOW,
            consensus="no_data",
            bullish_count=0,
            bearish_count=0,
            neutral_count=0,
        )

    # Séparer l'ADX et le volume des signaux directionnels
    adx_signal = None
    volume_signal = None
    directional_signals: list[SignalItem] = []

    for s in signals:
        if s.indicator == "adx":
            adx_signal = s
        elif s.indicator == "volume":
            volume_signal = s
        else:
            directional_signals.append(s)

    # Compter sur les signaux directionnels uniquement
    bullish_count = sum(1 for s in directional_signals if s.direction == SignalDirection.BULLISH)
    bearish_count = sum(1 for s in directional_signals if s.direction == SignalDirection.BEARISH)
    neutral_count = sum(1 for s in directional_signals if s.direction == SignalDirection.NEUTRAL)

    # Déterminer le régime de marché via ADX
    adx_value = adx_signal.value if adx_signal else None
    if adx_value is not None:
        if adx_value >= 40:
            adx_multiplier = 1.3  # Tendance très forte : boost les signaux
            regime = "trending"
        elif adx_value >= 25:
            adx_multiplier = 1.1  # Tendance confirmée : léger boost
            regime = "trending"
        elif adx_value >= 20:
            adx_multiplier = 1.0  # Normal
            regime = None  # Zone de transition, pas de biais
        else:
            adx_multiplier = 0.7  # Pas de tendance : atténue les signaux
            regime = "ranging"
    else:
        adx_multiplier = 1.0
        regime = None  # Pas d'ADX disponible → pas de biais de régime

    # Score brut pondéré par la force + régime
    weighted_sum = 0.0
    total_weight = 0.0

    for s in directional_signals:
        weight = s.strength

        # Appliquer le multiplicateur de régime si disponible
        if regime and s.indicator in REGIME_WEIGHTS.get(regime, {}):
            weight *= REGIME_WEIGHTS[regime][s.indicator]

        if s.direction == SignalDirection.BULLISH:
            weighted_sum += weight
        elif s.direction == SignalDirection.BEARISH:
            weighted_sum -= weight
        # Les neutres ne contribuent pas au score mais au poids total
        total_weight += weight

    # Ajouter la contribution de l'ADX (il confirme la direction)
    if adx_signal and adx_signal.direction != SignalDirection.NEUTRAL:
        adx_weight = adx_signal.strength * 0.5  # Poids modéré
        if adx_signal.direction == SignalDirection.BULLISH:
            weighted_sum += adx_weight
        else:
            weighted_sum -= adx_weight
        total_weight += adx_weight

    # Normaliser sur -100/+100
    if total_weight > 0:
        raw_score = weighted_sum / total_weight  # -1 à +1
    else:
        raw_score = 0.0

    # Appliquer le multiplicateur ADX
    raw_score *= adx_multiplier

    # Appliquer le modificateur volume
    if volume_signal and volume_signal.value is not None:
        vol_ratio = volume_signal.value
        if vol_ratio > 1.5:
            # Fort volume confirme le mouvement : boost de 10%
            raw_score *= 1.1
        elif vol_ratio < 0.5:
            # Faible volume : atténue le signal de 15%
            raw_score *= 0.85

    # [v1.9.5] Convergence boost amélioré — meilleure discrimination des scores.
    # Le boost original (v1.9.3) appliquait un facteur de 0.4 qui ne cassait
    # pas assez l'homogénéité 71/72. Le facteur est porté à 0.5 pour étirer
    # davantage les scores extrêmes. La compression pour signaux divisés
    # est renforcée (0.85→0.75) pour mieux pénaliser les setups ambigus.
    total_directional = bullish_count + bearish_count + neutral_count
    if total_directional >= 3:
        dominant_count = max(bullish_count, bearish_count)
        unanimity = dominant_count / total_directional if total_directional > 0 else 0
        if unanimity >= 0.75 and abs(raw_score) >= 0.5:
            # Les indicateurs convergent fortement → boost exponentiel
            # Plus raw_score est élevé, plus le boost amplifie (non-linéaire)
            sign = 1 if raw_score >= 0 else -1
            # [v1.9.5] Boost de 12.5-30% (facteur 0.5 au lieu de 0.4)
            boost_factor = 1.0 + (unanimity - 0.5) * abs(raw_score) * 0.5
            raw_score = sign * min(1.0, abs(raw_score) * boost_factor)
        elif unanimity < 0.4 and total_directional >= 4:
            # [v1.9.5] Signaux très divisés → compression renforcée (0.75 au lieu de 0.85)
            # Un setup ambigu ne mérite pas un score de 70.
            raw_score *= 0.75

    score = int(round(raw_score * 100))
    score = max(-100, min(100, score))

    # Direction
    if score > 10:
        direction = SignalDirection.BULLISH
    elif score < -10:
        direction = SignalDirection.BEARISH
    else:
        direction = SignalDirection.NEUTRAL

    # Consensus (basé sur les signaux directionnels uniquement)
    total_dir = len(directional_signals)
    if total_dir == 0:
        consensus = "no_data"
    else:
        dominant = max(bullish_count, bearish_count, neutral_count)
        if dominant == total_dir:
            consensus = "unanimous"
        elif dominant >= total_dir * 0.75:
            consensus = "strong_majority"
        elif dominant >= total_dir * 0.5:
            consensus = "majority"
        else:
            consensus = "divided"

    # Confiance v1.3 : basée sur convergence + ADX + nombre de signaux
    if consensus in ("unanimous", "strong_majority") and total_dir >= 3:
        if adx_value is not None and adx_value >= 25:
            confidence = ConfidenceLevel.HIGH  # Convergence + tendance confirmée
        else:
            confidence = ConfidenceLevel.MEDIUM  # Convergence mais pas de tendance ADX
    elif consensus in ("unanimous", "strong_majority", "majority") and total_dir >= 2:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW

    return CompositeScore(
        score=score,
        direction=direction,
        confidence=confidence,
        consensus=consensus,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        neutral_count=neutral_count,
    )


# ============================================================
# GÉNÉRATEUR DE RÉSUMÉ
# ============================================================

def generate_summary(
    signals: list[SignalItem],
    composite: CompositeScore,
) -> str:
    """
    Génère un résumé lisible de l'analyse.

    Exemple : "RSI en surachat (72), MACD croisé baissier → Score -65 (baissier, confiance haute)"
    """
    if not signals:
        return "Données insuffisantes pour générer des signaux."

    # Prendre les 2 signaux les plus forts
    sorted_signals = sorted(signals, key=lambda s: s.strength, reverse=True)
    top_signals = sorted_signals[:2]

    parts = [s.message.split("—")[0].strip() for s in top_signals]
    signal_text = ", ".join(parts)

    direction_text = {
        SignalDirection.BULLISH: "haussier",
        SignalDirection.BEARISH: "baissier",
        SignalDirection.NEUTRAL: "neutre",
    }[composite.direction]

    confidence_text = {
        ConfidenceLevel.HIGH: "confiance haute",
        ConfidenceLevel.MEDIUM: "confiance moyenne",
        ConfidenceLevel.LOW: "confiance basse",
    }[composite.confidence]

    return f"{signal_text} → Score {composite.score:+d} ({direction_text}, {confidence_text})"


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

class SignalService:
    """
    Service pour interpréter les indicateurs techniques en signaux.

    Usage :
        service = SignalService(db_session)
        result = service.analyze(
            symbol="BTC/USD",
            timeframe="4h",
            history_days=7,
        )
    """

    def __init__(self, db: Session):
        """Initialise le service avec une session DB."""
        self.db = db
        self.indicator_service = IndicatorService(db)

    def analyze(
        self,
        symbol: str = "BTC/USD",
        timeframe: str = "4h",
        history_days: float = 7,
        end_ts: Optional[datetime] = None,
    ) -> dict:
        """
        Analyse complète : indicateurs → signaux → score composite.

        Retourne un dict compatible avec SignalResponse.
        """
        # Récupérer les indicateurs
        indicator_result = self.indicator_service.calculate(
            symbol=symbol,
            timeframe=timeframe,
            history_days=history_days,
            end_ts=end_ts,
            include_candles=False,
        )

        meta = indicator_result["meta"]
        latest = indicator_result.get("latest")

        # Si pas de données, retourner une réponse vide
        if latest is None or meta.get("global_status") == "NO_DATA":
            empty_composite = CompositeScore(
                score=0,
                direction=SignalDirection.NEUTRAL,
                confidence=ConfidenceLevel.LOW,
                consensus="no_data",
                bullish_count=0,
                bearish_count=0,
                neutral_count=0,
            )
            return {
                "meta": meta,
                "signals": [],
                "composite": empty_composite.model_dump(),
                "summary": "Aucune donnée disponible pour analyser.",
            }

        # Interpréter chaque indicateur
        signals: list[SignalItem] = []

        rsi_signal = interpret_rsi(latest.get("rsi_14"))
        if rsi_signal:
            signals.append(rsi_signal)

        # MACD v1.2 : on passe le close pour des seuils en % du prix
        macd_signal = interpret_macd(
            latest.get("macd"),
            latest.get("macd_signal"),
            latest.get("macd_hist"),
            close=latest.get("close"),
        )
        if macd_signal:
            signals.append(macd_signal)

        sma_signal = interpret_sma(
            latest.get("close"),
            latest.get("sma_20"),
            latest.get("sma_50"),
            latest.get("sma_200"),
        )
        if sma_signal:
            signals.append(sma_signal)

        bollinger_signal = interpret_bollinger(
            latest.get("close"),
            latest.get("bb_upper"),
            latest.get("bb_mid"),
            latest.get("bb_lower"),
        )
        if bollinger_signal:
            signals.append(bollinger_signal)

        # ADX v1.2 : filtre de tendance (essentiel pour réduire les faux signaux)
        adx_signal = interpret_adx(
            latest.get("adx_14"),
            latest.get("plus_di"),
            latest.get("minus_di"),
        )
        if adx_signal:
            signals.append(adx_signal)

        # Volume v1.2 : confirmation par le volume
        volume_signal = interpret_volume_trend(
            latest.get("volume"),
            latest.get("volume_sma_20"),
        )
        if volume_signal:
            signals.append(volume_signal)

        # Stochastic RSI v1.3 : meilleure détection overbought/oversold
        stoch_rsi_signal = interpret_stoch_rsi(
            latest.get("stoch_rsi_k"),
            latest.get("stoch_rsi_d"),
        )
        if stoch_rsi_signal:
            signals.append(stoch_rsi_signal)

        # EMA Cross v1.3 : croisement EMA(9)/EMA(21) rapide
        # On a besoin des valeurs précédentes pour détecter les croisements
        prev_point = indicator_result.get("series", [None, None])
        if isinstance(prev_point, list) and len(prev_point) >= 2:
            prev = prev_point[-2]
        else:
            prev = None

        ema_cross_signal = interpret_ema_cross(
            latest.get("ema_9"),
            latest.get("ema_21"),
            prev.get("ema_9") if prev else None,
            prev.get("ema_21") if prev else None,
            close=latest.get("close"),
        )
        if ema_cross_signal:
            signals.append(ema_cross_signal)

        # Calculer le score composite
        composite = compute_composite_score(signals)

        # Générer le résumé
        summary = generate_summary(signals, composite)

        return {
            "meta": meta,
            "signals": [s.model_dump() for s in signals],
            "composite": composite.model_dump(),
            "summary": summary,
        }

