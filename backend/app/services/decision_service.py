"""
Moteur de décision — transforme les signaux et le sentiment en recommandations.

Ce service :
1. Récupère les signaux techniques via SignalService
2. Récupère le sentiment des news via NewsService
3. Évalue un ensemble de règles combinées
4. Produit des scénarios (Hausse / Stable / Baisse) avec probabilités
5. Génère une recommandation explicable en français

PONDÉRATION :
- Score technique : 70% (par défaut)
- Score sentiment : 30% (par défaut)
- En mode dégradé (news indisponibles) : 100% technique

RÈGLES :
Chaque règle teste une condition combinée (ex: RSI > 70 AND MACD baissier)
et contribue à l'évaluation finale. Les règles ne sont pas des automates :
elles informent la décision, mais c'est le score combiné qui détermine l'action.
"""

import logging
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.services.signal_service import SignalService
from app.services.news_service import NewsService
from app.services.sentiment_history_service import SentimentHistoryService
from app.services.news_history_service import NewsHistoryService
from app.schemas.signal import SignalDirection, ConfidenceLevel
from app.schemas.decision import (
    Scenario,
    RuleResult,
    Recommendation,
    DecisionMeta,
    DecisionResponse,
    ActionType,
)

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES
# ============================================================

# Pondération par défaut (technique vs sentiment)
TECHNICAL_WEIGHT = 0.70
SENTIMENT_WEIGHT = 0.30

# Seuils de déclenchement des actions BUY/SELL
# Asymétriques volontairement : le marché Bitcoin a un biais haussier structurel,
# ce qui rend les signaux bearish plus rares. Un seuil SELL plus bas compense
# ce biais et permet d'ouvrir des shorts quand les conditions le justifient.
BUY_THRESHOLD = 25
SELL_THRESHOLD = 20  # en valeur absolue (score < -20 → SELL)

# Nombre minimum de règles bearish satisfaites pour forcer un SELL par confluence
# Même si le score absolu ne franchit pas SELL_THRESHOLD, une forte convergence
# des indicateurs baissiers justifie une position short.
SELL_CONFLUENCE_MIN = 3

# Pondération pour la combinaison des sources de sentiment historique
# Fear & Greed Index : indice agrégé (marché global), disponible depuis 2018
# News History : articles individuels (granulaire mais bruité), disponible quand chargé
FNG_HIST_WEIGHT = 0.60
NEWS_HIST_WEIGHT = 0.40


# ============================================================
# DÉFINITION DES RÈGLES
# ============================================================
# Chaque règle est un dict avec :
# - name: identifiant unique
# - condition_desc: description lisible de la condition
# - direction: bullish ou bearish (si la règle est satisfaite)
# - weight: importance de la règle (0.0 à 1.0)
# - evaluate: fonction(signals_data, sentiment_data) -> (satisfied, detail)

def _eval_rsi_overbought(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """RSI en surachat → signal baissier."""
    rsi_signal = _find_signal(signals_data, "rsi")
    if rsi_signal and rsi_signal.get("direction") == "bearish" and rsi_signal.get("strength", 0) >= 0.7:
        return True, f"RSI en surachat (force {rsi_signal['strength']:.0%})"
    return False, "RSI pas en zone de surachat"


def _eval_rsi_oversold(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """RSI en survente → signal haussier."""
    rsi_signal = _find_signal(signals_data, "rsi")
    if rsi_signal and rsi_signal.get("direction") == "bullish" and rsi_signal.get("strength", 0) >= 0.7:
        return True, f"RSI en survente (force {rsi_signal['strength']:.0%})"
    return False, "RSI pas en zone de survente"


def _eval_macd_bullish(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """MACD croisé haussier confirmé → signal haussier."""
    macd_signal = _find_signal(signals_data, "macd")
    if macd_signal and macd_signal.get("direction") == "bullish" and macd_signal.get("strength", 0) >= 0.5:
        return True, f"MACD croisé haussier (force {macd_signal['strength']:.0%})"
    return False, "MACD pas en croisement haussier fort"


def _eval_macd_bearish(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """MACD croisé baissier confirmé → signal baissier."""
    macd_signal = _find_signal(signals_data, "macd")
    if macd_signal and macd_signal.get("direction") == "bearish" and macd_signal.get("strength", 0) >= 0.5:
        return True, f"MACD croisé baissier (force {macd_signal['strength']:.0%})"
    return False, "MACD pas en croisement baissier fort"


def _eval_sma_trend_up(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """Prix au-dessus de toutes les SMA → tendance haussière."""
    sma_signal = _find_signal(signals_data, "sma")
    if sma_signal and sma_signal.get("direction") == "bullish" and sma_signal.get("strength", 0) >= 0.6:
        return True, "Prix au-dessus des moyennes mobiles clés"
    return False, "Prix pas clairement au-dessus des SMA"


def _eval_sma_trend_down(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """Prix en dessous de toutes les SMA → tendance baissière."""
    sma_signal = _find_signal(signals_data, "sma")
    if sma_signal and sma_signal.get("direction") == "bearish" and sma_signal.get("strength", 0) >= 0.6:
        return True, "Prix sous les moyennes mobiles clés"
    return False, "Prix pas clairement sous les SMA"


def _eval_sentiment_positive(signals_data: dict, sentiment_data: dict) -> tuple[bool, str]:
    """Sentiment des news positif avec convergence technique haussière."""
    score = sentiment_data.get("sentiment_score", 0)
    tech_score = signals_data.get("composite", {}).get("score", 0)
    if score > 20 and tech_score > 10:
        return True, f"Sentiment positif ({score:+d}) converge avec technique haussière ({tech_score:+d})"
    return False, "Pas de convergence sentiment positif + technique haussière"


def _eval_sentiment_negative(signals_data: dict, sentiment_data: dict) -> tuple[bool, str]:
    """Sentiment des news négatif avec convergence technique baissière."""
    score = sentiment_data.get("sentiment_score", 0)
    tech_score = signals_data.get("composite", {}).get("score", 0)
    if score < -20 and tech_score < -10:
        return True, f"Sentiment négatif ({score:+d}) converge avec technique baissière ({tech_score:+d})"
    return False, "Pas de convergence sentiment négatif + technique baissière"


def _eval_ema_crossover_bullish(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """EMA9 croise EMA21 à la hausse → signal haussier rapide."""
    ema_signal = _find_signal(signals_data, "ema_cross")
    if ema_signal and ema_signal.get("direction") == "bullish" and ema_signal.get("strength", 0) >= 0.5:
        return True, f"EMA golden cross (force {ema_signal['strength']:.0%})"
    return False, "Pas de croisement EMA haussier"


def _eval_ema_crossover_bearish(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """EMA9 croise EMA21 à la baisse → signal baissier rapide."""
    ema_signal = _find_signal(signals_data, "ema_cross")
    if ema_signal and ema_signal.get("direction") == "bearish" and ema_signal.get("strength", 0) >= 0.5:
        return True, f"EMA death cross (force {ema_signal['strength']:.0%})"
    return False, "Pas de croisement EMA baissier"


def _eval_stochrsi_oversold(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """StochRSI en zone extrême de survente → signal haussier."""
    stoch_signal = _find_signal(signals_data, "stoch_rsi")
    if stoch_signal and stoch_signal.get("direction") == "bullish" and stoch_signal.get("strength", 0) >= 0.6:
        return True, f"StochRSI survendu (force {stoch_signal['strength']:.0%})"
    return False, "StochRSI pas en survente extrême"


def _eval_stochrsi_overbought(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """StochRSI en zone extrême de surachat → signal baissier."""
    stoch_signal = _find_signal(signals_data, "stoch_rsi")
    if stoch_signal and stoch_signal.get("direction") == "bearish" and stoch_signal.get("strength", 0) >= 0.6:
        return True, f"StochRSI suracheté (force {stoch_signal['strength']:.0%})"
    return False, "StochRSI pas en surachat extrême"


def _eval_multi_confluence_bullish(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """Confluence multi-indicateurs haussière (≥ 3 signaux bullish forts).
    La confluence est le signal le plus fiable : quand plusieurs indicateurs
    indépendants convergent, la probabilité de succès augmente significativement."""
    strong_bullish = []
    for signal in signals_data.get("signals", []):
        if (signal.get("direction") == "bullish"
                and signal.get("strength", 0) >= 0.5
                and signal.get("indicator") not in ("volume", "adx")):
            strong_bullish.append(signal.get("indicator", "?"))

    if len(strong_bullish) >= 3:
        names = ", ".join(strong_bullish[:4])
        return True, f"Confluence haussière forte ({len(strong_bullish)} indicateurs: {names})"
    return False, f"Pas assez de confluence haussière ({len(strong_bullish)}/3 min)"


def _eval_multi_confluence_bearish(signals_data: dict, _sentiment: dict) -> tuple[bool, str]:
    """Confluence multi-indicateurs baissière (≥ 3 signaux bearish forts)."""
    strong_bearish = []
    for signal in signals_data.get("signals", []):
        if (signal.get("direction") == "bearish"
                and signal.get("strength", 0) >= 0.5
                and signal.get("indicator") not in ("volume", "adx")):
            strong_bearish.append(signal.get("indicator", "?"))

    if len(strong_bearish) >= 3:
        names = ", ".join(strong_bearish[:4])
        return True, f"Confluence baissière forte ({len(strong_bearish)} indicateurs: {names})"
    return False, f"Pas assez de confluence baissière ({len(strong_bearish)}/3 min)"


# Liste des règles par défaut
DEFAULT_RULES = [
    {
        "name": "rsi_overbought",
        "condition_desc": "RSI ≥ 70 (surachat fort)",
        "direction": SignalDirection.BEARISH,
        "weight": 0.8,
        "evaluate": _eval_rsi_overbought,
    },
    {
        "name": "rsi_oversold",
        "condition_desc": "RSI ≤ 30 (survente forte)",
        "direction": SignalDirection.BULLISH,
        "weight": 0.8,
        "evaluate": _eval_rsi_oversold,
    },
    {
        "name": "macd_bullish_cross",
        "condition_desc": "MACD croisé haussier confirmé (force ≥ 50%)",
        "direction": SignalDirection.BULLISH,
        "weight": 0.7,
        "evaluate": _eval_macd_bullish,
    },
    {
        "name": "macd_bearish_cross",
        "condition_desc": "MACD croisé baissier confirmé (force ≥ 50%)",
        "direction": SignalDirection.BEARISH,
        "weight": 0.7,
        "evaluate": _eval_macd_bearish,
    },
    {
        "name": "sma_trend_up",
        "condition_desc": "Prix au-dessus des SMA clés (tendance haussière)",
        "direction": SignalDirection.BULLISH,
        "weight": 0.6,
        "evaluate": _eval_sma_trend_up,
    },
    {
        "name": "sma_trend_down",
        "condition_desc": "Prix sous les SMA clés (tendance baissière)",
        "direction": SignalDirection.BEARISH,
        "weight": 0.6,
        "evaluate": _eval_sma_trend_down,
    },
    {
        "name": "ema_crossover_bullish",
        "condition_desc": "EMA9 croise EMA21 à la hausse (golden cross rapide)",
        "direction": SignalDirection.BULLISH,
        "weight": 0.7,
        "evaluate": _eval_ema_crossover_bullish,
    },
    {
        "name": "ema_crossover_bearish",
        "condition_desc": "EMA9 croise EMA21 à la baisse (death cross rapide)",
        "direction": SignalDirection.BEARISH,
        "weight": 0.7,
        "evaluate": _eval_ema_crossover_bearish,
    },
    {
        "name": "stochrsi_oversold",
        "condition_desc": "StochRSI en zone de survente extrême",
        "direction": SignalDirection.BULLISH,
        "weight": 0.6,
        "evaluate": _eval_stochrsi_oversold,
    },
    {
        "name": "stochrsi_overbought",
        "condition_desc": "StochRSI en zone de surachat extrême",
        "direction": SignalDirection.BEARISH,
        "weight": 0.6,
        "evaluate": _eval_stochrsi_overbought,
    },
    {
        "name": "multi_confluence_bullish",
        "condition_desc": "≥ 3 indicateurs convergent en haussier (confluence forte)",
        "direction": SignalDirection.BULLISH,
        "weight": 0.9,
        "evaluate": _eval_multi_confluence_bullish,
    },
    {
        "name": "multi_confluence_bearish",
        "condition_desc": "≥ 3 indicateurs convergent en baissier (confluence forte)",
        "direction": SignalDirection.BEARISH,
        "weight": 0.9,
        "evaluate": _eval_multi_confluence_bearish,
    },
    {
        "name": "sentiment_convergence_bullish",
        "condition_desc": "Sentiment positif + technique haussière",
        "direction": SignalDirection.BULLISH,
        "weight": 0.5,
        "evaluate": _eval_sentiment_positive,
    },
    {
        "name": "sentiment_convergence_bearish",
        "condition_desc": "Sentiment négatif + technique baissière",
        "direction": SignalDirection.BEARISH,
        "weight": 0.5,
        "evaluate": _eval_sentiment_negative,
    },
]


# ============================================================
# HELPERS
# ============================================================

def _find_signal(signals_data: dict, indicator_name: str) -> Optional[dict]:
    """Trouve un signal par nom d'indicateur dans les données de signaux."""
    for signal in signals_data.get("signals", []):
        if signal.get("indicator") == indicator_name:
            return signal
    return None


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

class DecisionService:
    """
    Moteur de décision combinant signaux techniques et sentiment.

    Usage :
        service = DecisionService(db_session)
        result = service.analyze(
            symbol="BTC/USD",
            timeframe="4h",
            history_days=7,
        )
    """

    def __init__(self, db: Session):
        """Initialise le service avec une session DB."""
        self.db = db
        self.signal_service = SignalService(db)
        self.news_service = NewsService()
        self.sentiment_history_service = SentimentHistoryService(db)
        self.news_history_service = NewsHistoryService(db)

    def evaluate_rules(
        self,
        signals_data: dict,
        sentiment_data: dict,
        rules: list[dict] | None = None,
    ) -> list[RuleResult]:
        """
        Évalue un ensemble de règles combinées.

        Args:
            signals_data: Résultat de SignalService.analyze()
            sentiment_data: Résultat de NewsService.get_sentiment_only()
            rules: Liste des règles (défaut: DEFAULT_RULES)

        Returns:
            Liste de RuleResult (une par règle évaluée)
        """
        if rules is None:
            rules = DEFAULT_RULES

        results: list[RuleResult] = []

        for rule in rules:
            try:
                satisfied, detail = rule["evaluate"](signals_data, sentiment_data)
            except Exception as e:
                logger.warning(f"Erreur évaluation règle {rule['name']}: {e}")
                satisfied = False
                detail = f"Erreur d'évaluation: {str(e)}"

            results.append(RuleResult(
                rule_name=rule["name"],
                condition=rule["condition_desc"],
                satisfied=satisfied,
                weight=rule["weight"],
                detail=detail,
                direction=rule["direction"],
            ))

        return results

    def compute_scenarios(
        self,
        combined_score: int,
        rules: list[RuleResult],
    ) -> list[Scenario]:
        """
        Calcule 3 scénarios (Hausse / Stable / Baisse) avec probabilités.

        L'algorithme :
        1. Convertit le score combiné (-100/+100) en probabilité de base
        2. Ajuste selon les règles satisfaites
        3. Normalise pour que la somme = 1.0

        Args:
            combined_score: Score combiné -100 à +100
            rules: Résultat de evaluate_rules()

        Returns:
            3 scénarios ordonnés par probabilité décroissante
        """
        # Score normalisé sur 0-1 (0 = très baissier, 1 = très haussier)
        normalized = (combined_score + 100) / 200  # 0.0 à 1.0

        # Probabilités de base dérivées du score
        # On utilise une distribution soft : le score pousse vers une direction
        # mais ne donne jamais 0% aux autres scénarios
        raw_bullish = 0.15 + normalized * 0.55       # 0.15 à 0.70
        raw_bearish = 0.15 + (1 - normalized) * 0.55  # 0.15 à 0.70
        raw_stable = 0.20                              # Base stable

        # Ajustement basé sur les règles satisfaites
        bullish_boost = 0.0
        bearish_boost = 0.0

        for rule in rules:
            if rule.satisfied:
                if rule.direction == SignalDirection.BULLISH:
                    bullish_boost += rule.weight * 0.08
                elif rule.direction == SignalDirection.BEARISH:
                    bearish_boost += rule.weight * 0.08

        raw_bullish += bullish_boost
        raw_bearish += bearish_boost

        # Normaliser la somme à 1.0
        total = raw_bullish + raw_bearish + raw_stable
        p_bullish = round(raw_bullish / total, 2)
        p_bearish = round(raw_bearish / total, 2)
        p_stable = round(1.0 - p_bullish - p_bearish, 2)

        # Garantir des valeurs positives
        p_stable = max(0.02, p_stable)
        p_bullish = max(0.02, p_bullish)
        p_bearish = max(0.02, p_bearish)

        # Re-normaliser après les max()
        total = p_bullish + p_bearish + p_stable
        p_bullish = round(p_bullish / total, 2)
        p_bearish = round(p_bearish / total, 2)
        p_stable = round(1.0 - p_bullish - p_bearish, 2)

        # Descriptions des scénarios
        bullish_rules = [r for r in rules if r.satisfied and r.direction == SignalDirection.BULLISH]
        bearish_rules = [r for r in rules if r.satisfied and r.direction == SignalDirection.BEARISH]

        bullish_desc = self._build_scenario_description(
            "hausse", combined_score, bullish_rules
        )
        bearish_desc = self._build_scenario_description(
            "baisse", combined_score, bearish_rules
        )
        stable_desc = "Signaux contradictoires ou insuffisants — consolidation probable"
        if not bullish_rules and not bearish_rules:
            stable_desc = "Aucune règle décisive satisfaite — marché indécis"

        scenarios = [
            Scenario(
                label="Hausse",
                probability=p_bullish,
                direction=SignalDirection.BULLISH,
                description=bullish_desc,
            ),
            Scenario(
                label="Stable",
                probability=p_stable,
                direction=SignalDirection.NEUTRAL,
                description=stable_desc,
            ),
            Scenario(
                label="Baisse",
                probability=p_bearish,
                direction=SignalDirection.BEARISH,
                description=bearish_desc,
            ),
        ]

        # Trier par probabilité décroissante
        scenarios.sort(key=lambda s: s.probability, reverse=True)

        return scenarios

    def _build_scenario_description(
        self,
        direction: str,
        combined_score: int,
        matching_rules: list[RuleResult],
    ) -> str:
        """Construit la description d'un scénario."""
        if not matching_rules:
            if direction == "hausse":
                return f"Score combiné modérément positif ({combined_score:+d})" if combined_score > 0 else "Peu d'éléments en faveur d'une hausse"
            else:
                return f"Score combiné modérément négatif ({combined_score:+d})" if combined_score < 0 else "Peu d'éléments en faveur d'une baisse"

        details = [r.detail for r in matching_rules[:3]]
        return " — ".join(details)

    def generate_recommendation(
        self,
        scenarios: list[Scenario],
        rules: list[RuleResult],
        combined_score: int,
    ) -> Recommendation:
        """
        Génère une recommandation d'action basée sur les scénarios et règles.

        Logique :
        - Score > +25 ET scénario Hausse dominant → Acheter
        - Score < -25 ET scénario Baisse dominant → Vendre
        - Sinon → Attendre

        La confiance dépend de la convergence des règles.
        """
        # Trouver le scénario dominant
        dominant = scenarios[0] if scenarios else None

        # Compter les règles satisfaites par direction
        bullish_satisfied = sum(1 for r in rules if r.satisfied and r.direction == SignalDirection.BULLISH)
        bearish_satisfied = sum(1 for r in rules if r.satisfied and r.direction == SignalDirection.BEARISH)
        total_satisfied = bullish_satisfied + bearish_satisfied

        # Déterminer l'action
        # Seuils asymétriques BUY=+25 / SELL=-20 : le biais haussier structurel
        # de Bitcoin rend les signaux bearish plus rares. Un seuil SELL plus bas
        # compense ce biais et permet d'ouvrir des shorts.
        # Chemin additionnel par confluence : ≥3 règles bearish + score négatif → SELL
        # même si le seuil -20 n'est pas atteint, la convergence des indicateurs
        # est un signal fiable pour shorter.
        if combined_score > BUY_THRESHOLD and dominant and dominant.direction == SignalDirection.BULLISH:
            action = ActionType.BUY
        elif combined_score < -SELL_THRESHOLD and dominant and dominant.direction == SignalDirection.BEARISH:
            action = ActionType.SELL
        elif bearish_satisfied >= SELL_CONFLUENCE_MIN and combined_score < 0:
            # Confluence bearish forte : plusieurs indicateurs convergent
            # vers une baisse même si le score absolu est modéré
            action = ActionType.SELL
        else:
            action = ActionType.HOLD

        # Déterminer la confiance
        if total_satisfied >= 4 and abs(combined_score) > 50:
            confidence = ConfidenceLevel.HIGH
        elif total_satisfied >= 2 and abs(combined_score) > 25:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        # Construire l'explication
        reasons: list[str] = []
        for r in rules:
            if r.satisfied:
                reasons.append(r.detail)

        if not reasons:
            reasons.append("Aucune règle décisive satisfaite")

        # Explication principale
        explanation = self._build_explanation(action, combined_score, confidence, dominant)

        return Recommendation(
            action=action,
            confidence=confidence,
            explanation=explanation,
            reasons=reasons,
        )

    def _build_explanation(
        self,
        action: ActionType,
        combined_score: int,
        confidence: ConfidenceLevel,
        dominant: Optional[Scenario],
    ) -> str:
        """Construit l'explication de la recommandation en français."""
        action_labels = {
            ActionType.BUY: "Acheter",
            ActionType.SELL: "Vendre",
            ActionType.HOLD: "Attendre",
        }
        confidence_labels = {
            ConfidenceLevel.HIGH: "élevée",
            ConfidenceLevel.MEDIUM: "modérée",
            ConfidenceLevel.LOW: "faible",
        }

        action_label = action_labels[action]
        conf_label = confidence_labels[confidence]

        if action == ActionType.BUY:
            return (
                f"Recommandation : {action_label} — Score combiné {combined_score:+d}, "
                f"confiance {conf_label}. "
                f"Le scénario dominant ({dominant.label}, {dominant.probability:.0%}) "
                f"est soutenu par la convergence des indicateurs techniques et du sentiment."
                if dominant else f"Recommandation : {action_label} — Score {combined_score:+d}."
            )
        elif action == ActionType.SELL:
            return (
                f"Recommandation : {action_label} — Score combiné {combined_score:+d}, "
                f"confiance {conf_label}. "
                f"Le scénario dominant ({dominant.label}, {dominant.probability:.0%}) "
                f"indique une pression vendeuse convergente."
                if dominant else f"Recommandation : {action_label} — Score {combined_score:+d}."
            )
        else:
            return (
                f"Recommandation : {action_label} — Score combiné {combined_score:+d}, "
                f"confiance {conf_label}. "
                f"Les signaux sont insuffisamment convergents pour recommander une action."
            )

    def analyze(
        self,
        symbol: str = "BTC/USD",
        timeframe: str = "4h",
        history_days: float = 7,
        end_ts: Optional[datetime] = None,
    ) -> dict:
        """
        Analyse complète : signaux + sentiment → décision.

        Point d'entrée principal du moteur de décision.

        AMÉLIORATION v1.2 :
        Quand end_ts est fourni (mode backtest/vérification historique),
        le service cherche le sentiment historique (Fear & Greed Index)
        stocké en base au lieu d'appeler le RSS temps réel.
        Cela permet un backtest COMPLET (technique + sentiment).

        Returns:
            Dict compatible avec DecisionResponse
        """
        now_ts = datetime.now(timezone.utc)

        # 1. Récupérer les signaux techniques
        signals_data = self.signal_service.analyze(
            symbol=symbol,
            timeframe=timeframe,
            history_days=history_days,
            end_ts=end_ts,
        )
        technical_score = signals_data.get("composite", {}).get("score", 0)

        # 2. Récupérer le sentiment
        # Mode historique (end_ts fourni) : utiliser le sentiment stocké en base
        # Mode temps réel (end_ts absent) : utiliser le RSS comme avant
        sentiment_available = True
        sentiment_score = 0
        sentiment_data: dict = {}
        sentiment_source = "live_rss"

        if end_ts is not None:
            # Mode historique : chercher le Fear & Greed Index en base
            sentiment_score, sentiment_available, sentiment_source = (
                self._get_historical_sentiment(end_ts)
            )
            sentiment_data = {"sentiment_score": sentiment_score}
        else:
            # Mode temps réel : RSS comme avant
            try:
                sentiment_summary = self.news_service.get_sentiment_only()
                sentiment_score = sentiment_summary.sentiment_score
                sentiment_data = sentiment_summary.model_dump()
            except Exception as e:
                logger.warning(f"Sentiment indisponible, mode dégradé: {e}")
                sentiment_available = False
                sentiment_data = {"sentiment_score": 0}

        # 3. Calculer le score combiné
        if sentiment_available:
            combined_score = int(round(
                technical_score * TECHNICAL_WEIGHT + sentiment_score * SENTIMENT_WEIGHT
            ))
        else:
            # Mode dégradé : 100% technique
            combined_score = technical_score

        combined_score = max(-100, min(100, combined_score))

        # 4. Évaluer les règles
        rule_results = self.evaluate_rules(signals_data, sentiment_data)

        # 5. Calculer les scénarios
        scenarios = self.compute_scenarios(combined_score, rule_results)

        # 6. Générer la recommandation
        recommendation = self.generate_recommendation(
            scenarios, rule_results, combined_score
        )

        # 7. Générer le résumé
        summary = self._build_summary(
            combined_score, technical_score, sentiment_score,
            sentiment_available, recommendation, scenarios
        )

        return {
            "meta": DecisionMeta(
                symbol=symbol,
                timeframe=timeframe,
                history_days=history_days,
                timestamp=now_ts.isoformat(),
                sentiment_available=sentiment_available,
                sentiment_source=sentiment_source,
                technical_weight=TECHNICAL_WEIGHT,
                sentiment_weight=SENTIMENT_WEIGHT if sentiment_available else 0.0,
            ).model_dump(),
            "scenarios": [s.model_dump() for s in scenarios],
            "rules_evaluated": [r.model_dump() for r in rule_results],
            "recommendation": recommendation.model_dump(),
            "technical_score": technical_score,
            "sentiment_score": sentiment_score,
            "combined_score": combined_score,
            "summary": summary,
        }

    def _get_historical_sentiment(
        self, end_ts: datetime
    ) -> tuple[int, bool, str]:
        """
        Récupère le sentiment historique combiné pour une date donnée.

        Combine deux sources (si disponibles) :
        1. Fear & Greed Index (SentimentHistoryService) — indice agrégé marché
        2. News History (NewsHistoryService) — articles individuels avec sentiment

        Pondération :
        - Les deux sources disponibles → FNG_HIST_WEIGHT × FGI + NEWS_HIST_WEIGHT × News
        - Une seule source → utilisée à 100%
        - Aucune source → (0, False, "none")

        Returns:
            (sentiment_score, sentiment_available, source_label)
        """
        date_str = end_ts.strftime("%Y-%m-%d")

        # Source 1 : Fear & Greed Index
        fng_score = None
        try:
            fng_score = self.sentiment_history_service.get_normalized_score_at_date(date_str)
        except Exception as e:
            logger.warning(f"Erreur récupération Fear & Greed historique: {e}")

        # Source 2 : News History (articles stockés en base)
        news_score = None
        try:
            news_score = self.news_history_service.get_daily_sentiment(date_str)
        except Exception as e:
            logger.warning(f"Erreur récupération news history sentiment: {e}")

        # Combinaison des sources
        if fng_score is not None and news_score is not None:
            # Les deux sources disponibles → moyenne pondérée
            combined = fng_score * FNG_HIST_WEIGHT + news_score * NEWS_HIST_WEIGHT
            score = int(round(combined))
            score = max(-100, min(100, score))
            source = "fear_and_greed+news_history"
            logger.debug(
                f"Sentiment historique combiné à {date_str}: "
                f"FGI={fng_score:.1f} ({FNG_HIST_WEIGHT:.0%}) + "
                f"News={news_score:.1f} ({NEWS_HIST_WEIGHT:.0%}) → {score}"
            )
            return score, True, source

        elif fng_score is not None:
            # Seulement Fear & Greed
            score = int(round(fng_score))
            score = max(-100, min(100, score))
            logger.debug(f"Sentiment historique à {date_str}: Fear&Greed seul={score}")
            return score, True, "fear_and_greed_historical"

        elif news_score is not None:
            # Seulement News History
            score = int(round(news_score))
            score = max(-100, min(100, score))
            logger.debug(f"Sentiment historique à {date_str}: News seul={score}")
            return score, True, "news_history"

        else:
            logger.debug(f"Pas de sentiment historique disponible pour {date_str}")
            return 0, False, "none"

    def _build_summary(
        self,
        combined_score: int,
        technical_score: int,
        sentiment_score: int,
        sentiment_available: bool,
        recommendation: Recommendation,
        scenarios: list[Scenario],
    ) -> str:
        """Construit le résumé lisible de la décision."""
        dominant = scenarios[0] if scenarios else None
        action_emoji = {
            ActionType.BUY: "🟢",
            ActionType.SELL: "🔴",
            ActionType.HOLD: "⚪",
        }

        emoji = action_emoji.get(recommendation.action, "⚪")
        action_label = recommendation.action.value.capitalize()

        parts = [f"{emoji} {action_label}"]
        parts.append(f"Score combiné {combined_score:+d} (technique {technical_score:+d}")

        if sentiment_available:
            parts[-1] += f", sentiment {sentiment_score:+d})"
        else:
            parts[-1] += ", sentiment indisponible)"

        if dominant:
            parts.append(f"Scénario dominant : {dominant.label} ({dominant.probability:.0%})")

        return " — ".join(parts)

