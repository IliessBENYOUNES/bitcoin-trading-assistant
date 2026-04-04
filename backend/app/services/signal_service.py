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


# ============================================================
# AGRÉGATION : SCORE COMPOSITE (v1.2 — amélioré avec ADX + Volume)
# ============================================================

def compute_composite_score(signals: list[SignalItem]) -> CompositeScore:
    """
    Agrège les signaux individuels en un score composite.

    Algorithme v1.2 (amélioré ADX + Volume) :
    1. Chaque signal bullish contribue +strength, bearish -strength
    2. L'ADX module la confiance globale :
       - ADX >= 25 : signaux tendanciels (MACD, SMA) sont boostés
       - ADX < 20 : tous les signaux sont atténués (marché sans tendance)
    3. Le volume module aussi la confiance :
       - Volume élevé : boost de +10% du score
       - Volume faible : atténuation de -10% du score
    4. Score normalisé sur -100/+100
    5. Confiance basée sur la convergence ET la force de la tendance
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
    # adx_multiplier : 1.0 = normal, > 1.0 = tendance forte, < 1.0 = range
    adx_value = adx_signal.value if adx_signal else None
    if adx_value is not None:
        if adx_value >= 40:
            adx_multiplier = 1.3  # Tendance très forte : boost les signaux
        elif adx_value >= 25:
            adx_multiplier = 1.1  # Tendance confirmée : léger boost
        elif adx_value >= 20:
            adx_multiplier = 1.0  # Normal
        else:
            adx_multiplier = 0.7  # Pas de tendance : atténue les signaux
    else:
        adx_multiplier = 1.0  # Pas d'ADX disponible, pas de modification

    # Score brut pondéré par la force
    weighted_sum = 0.0
    total_weight = 0.0

    for s in directional_signals:
        weight = s.strength
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

    # Confiance v1.2 : basée sur convergence + ADX + nombre de signaux
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

