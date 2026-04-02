"""
Service de vérification des alertes.

Évalue chaque alerte active contre les données de marché courantes
et déclenche les notifications quand les conditions sont remplies.

Conditions supportées :
- price    : compare close_price au seuil
- rsi      : compare RSI(14) au seuil
- macd_hist: compare histogramme MACD au seuil
- score    : compare score composite signal au seuil
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.services.indicator_service import IndicatorService
from app.services.signal_service import SignalService
from app.schemas.alert import AlertNotification


def _get_current_value(
    condition_type: str,
    latest_indicators: dict,
    signal_result: Optional[dict],
) -> Optional[float]:
    """
    Extrait la valeur courante pour un type de condition.

    Args:
        condition_type: "price", "rsi", "macd_hist", "score"
        latest_indicators: dict avec les dernières valeurs d'indicateurs
        signal_result: résultat de SignalService.analyze()

    Returns:
        La valeur courante ou None si indisponible.
    """
    if condition_type == "price":
        return latest_indicators.get("close")
    elif condition_type == "rsi":
        return latest_indicators.get("rsi_14")
    elif condition_type == "macd_hist":
        return latest_indicators.get("macd_hist")
    elif condition_type == "score":
        if signal_result and "composite" in signal_result:
            return signal_result["composite"].get("score")
    return None


def _evaluate_condition(
    operator: str,
    current_value: float,
    threshold: float,
) -> bool:
    """
    Évalue si la condition est remplie.

    Args:
        operator: "above" ou "below"
        current_value: valeur courante de l'indicateur
        threshold: seuil configuré

    Returns:
        True si la condition est remplie.
    """
    if operator == "above":
        return current_value >= threshold
    elif operator == "below":
        return current_value <= threshold
    return False


def _build_message(alert: Alert, current_value: float) -> str:
    """Construit le message de notification."""
    if alert.message:
        return alert.message

    type_labels = {
        "price": "Prix",
        "rsi": "RSI(14)",
        "macd_hist": "MACD Histogramme",
        "score": "Score composite",
    }
    op_labels = {
        "above": "au-dessus de",
        "below": "en dessous de",
    }

    type_label = type_labels.get(alert.condition_type, alert.condition_type)
    op_label = op_labels.get(alert.operator, alert.operator)

    if alert.condition_type == "price":
        return f"{type_label} ({current_value:,.0f}) {op_label} {alert.threshold:,.0f}"
    elif alert.condition_type == "score":
        return f"{type_label} ({current_value:+.0f}) {op_label} {alert.threshold:+.0f}"
    else:
        return f"{type_label} ({current_value:.2f}) {op_label} {alert.threshold:.2f}"


class AlertService:
    """
    Service pour gérer et évaluer les alertes.

    Usage :
        service = AlertService(db)
        result = service.check_alerts(symbol="BTC/USD", timeframe="4h")
    """

    def __init__(self, db: Session):
        self.db = db

    def get_all(self, symbol: Optional[str] = None) -> list[Alert]:
        """Retourne toutes les alertes, optionnellement filtrées par symbole."""
        query = self.db.query(Alert)
        if symbol:
            query = query.filter(Alert.symbol == symbol)
        return query.order_by(Alert.created_at.desc()).all()

    def get_active(self, symbol: Optional[str] = None) -> list[Alert]:
        """Retourne les alertes actives."""
        query = self.db.query(Alert).filter(Alert.status == "active")
        if symbol:
            query = query.filter(Alert.symbol == symbol)
        return query.all()

    def get_by_id(self, alert_id: int) -> Optional[Alert]:
        """Retourne une alerte par ID."""
        return self.db.query(Alert).filter(Alert.id == alert_id).first()

    def create(self, **kwargs) -> Alert:
        """Crée une nouvelle alerte."""
        alert = Alert(**kwargs)
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def update(self, alert_id: int, **kwargs) -> Optional[Alert]:
        """Met à jour une alerte existante."""
        alert = self.get_by_id(alert_id)
        if not alert:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(alert, key):
                setattr(alert, key, value)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def delete(self, alert_id: int) -> bool:
        """Supprime une alerte. Retourne True si supprimée."""
        alert = self.get_by_id(alert_id)
        if not alert:
            return False
        self.db.delete(alert)
        self.db.commit()
        return True

    def check_alerts(
        self,
        symbol: str = "BTC/USD",
        timeframe: str = "4h",
    ) -> dict:
        """
        Évalue toutes les alertes actives contre les données de marché.

        1. Récupère les indicateurs et signaux
        2. Pour chaque alerte active, évalue la condition
        3. Si remplie : marque triggered, génère notification
        4. Si recurring : réarme à active après trigger

        Returns:
            dict avec checked, triggered, notifications
        """
        now = datetime.now(timezone.utc)

        # Récupérer les données de marché
        indicator_service = IndicatorService(self.db)
        indicator_result = indicator_service.calculate(
            symbol=symbol, timeframe=timeframe, history_days=7,
            include_candles=False,
        )
        latest = indicator_result.get("latest")

        # Récupérer le score composite
        signal_service = SignalService(self.db)
        signal_result = signal_service.analyze(
            symbol=symbol, timeframe=timeframe, history_days=7,
        )

        # Si pas de données, ne rien faire
        if latest is None:
            return {"checked": 0, "triggered": 0, "notifications": []}

        # Évaluer chaque alerte active
        active_alerts = self.get_active(symbol=symbol)
        notifications: list[AlertNotification] = []
        triggered_count = 0

        for alert in active_alerts:
            # Ignorer si timeframe ne correspond pas
            if alert.timeframe != timeframe:
                continue

            current_value = _get_current_value(
                alert.condition_type, latest, signal_result,
            )

            if current_value is None:
                continue

            if _evaluate_condition(alert.operator, current_value, alert.threshold):
                # Condition remplie → trigger
                triggered_count += 1

                alert.status = "triggered"
                alert.triggered_at = now
                alert.triggered_value = current_value

                notification = AlertNotification(
                    alert_id=alert.id,
                    condition_type=alert.condition_type,
                    operator=alert.operator,
                    threshold=alert.threshold,
                    current_value=current_value,
                    message=_build_message(alert, current_value),
                    triggered_at=now,
                )
                notifications.append(notification)

                # Si recurring, réarmer immédiatement
                if alert.recurring:
                    alert.status = "active"

        self.db.commit()

        return {
            "checked": len(active_alerts),
            "triggered": triggered_count,
            "notifications": [n.model_dump() for n in notifications],
        }

