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
) -> Optional[SignalItem]:
    """
    Interprète le MACD(12,26,9) en signal.

    Logique :
    - MACD > Signal ET hist > 0 : Bullish (croisé haussier confirmé)
    - MACD < Signal ET hist < 0 : Bearish (croisé baissier confirmé)
    - Sinon : Neutre
    - La force dépend de l'amplitude de l'histogramme
    """
    if macd is None or macd_signal is None:
        return None

    hist = macd_hist if macd_hist is not None else (macd - macd_signal)
    diff = macd - macd_signal

    # Calculer la force basée sur l'écart relatif
    # On normalise par une heuristique : un écart de 500+ est fort pour BTC
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


# ============================================================
# AGRÉGATION : SCORE COMPOSITE
# ============================================================

def compute_composite_score(signals: list[SignalItem]) -> CompositeScore:
    """
    Agrège les signaux individuels en un score composite.

    Algorithme :
    1. Chaque signal bullish contribue +strength, bearish -strength
    2. Score brut = somme pondérée / nombre de signaux
    3. Normalisé sur -100/+100
    4. Confiance basée sur la convergence
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

    bullish_count = sum(1 for s in signals if s.direction == SignalDirection.BULLISH)
    bearish_count = sum(1 for s in signals if s.direction == SignalDirection.BEARISH)
    neutral_count = sum(1 for s in signals if s.direction == SignalDirection.NEUTRAL)

    # Score brut pondéré par la force
    weighted_sum = 0.0
    total_weight = 0.0

    for s in signals:
        weight = s.strength
        if s.direction == SignalDirection.BULLISH:
            weighted_sum += weight
        elif s.direction == SignalDirection.BEARISH:
            weighted_sum -= weight
        # Les neutres ne contribuent pas au score mais au poids
        total_weight += weight

    # Normaliser sur -100/+100
    if total_weight > 0:
        raw_score = weighted_sum / total_weight  # -1 à +1
    else:
        raw_score = 0.0

    score = int(round(raw_score * 100))
    score = max(-100, min(100, score))

    # Direction
    if score > 10:
        direction = SignalDirection.BULLISH
    elif score < -10:
        direction = SignalDirection.BEARISH
    else:
        direction = SignalDirection.NEUTRAL

    # Consensus
    total = len(signals)
    dominant = max(bullish_count, bearish_count, neutral_count)

    if dominant == total:
        consensus = "unanimous"
    elif dominant >= total * 0.75:
        consensus = "strong_majority"
    elif dominant >= total * 0.5:
        consensus = "majority"
    else:
        consensus = "divided"

    # Confiance : basée sur convergence + nombre de signaux
    if consensus in ("unanimous", "strong_majority") and total >= 3:
        confidence = ConfidenceLevel.HIGH
    elif consensus in ("unanimous", "strong_majority", "majority") and total >= 2:
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
        history_days: int = 7,
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

        macd_signal = interpret_macd(
            latest.get("macd"),
            latest.get("macd_signal"),
            latest.get("macd_hist"),
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

