"""Tests pour le système d'alertes (v0.8)."""
import pytest
from datetime import datetime, timezone, timedelta
from app.models.alert import Alert
from app.models.candle import Candle
from app.services.alert_service import (
    AlertService, _get_current_value, _evaluate_condition, _build_message,
)


class TestEvaluateCondition:
    def test_above_true(self):
        assert _evaluate_condition("above", 75.0, 70.0) is True

    def test_above_equal(self):
        assert _evaluate_condition("above", 70.0, 70.0) is True

    def test_above_false(self):
        assert _evaluate_condition("above", 65.0, 70.0) is False

    def test_below_true(self):
        assert _evaluate_condition("below", 25.0, 30.0) is True

    def test_below_equal(self):
        assert _evaluate_condition("below", 30.0, 30.0) is True

    def test_below_false(self):
        assert _evaluate_condition("below", 35.0, 30.0) is False

    def test_unknown_operator(self):
        assert _evaluate_condition("unknown", 50.0, 50.0) is False


class TestGetCurrentValue:
    def test_price(self):
        assert _get_current_value("price", {"close": 67000.0}, None) == 67000.0

    def test_rsi(self):
        assert _get_current_value("rsi", {"rsi_14": 72.5}, None) == 72.5

    def test_macd_hist(self):
        assert _get_current_value("macd_hist", {"macd_hist": -59.2}, None) == -59.2

    def test_score(self):
        assert _get_current_value("score", {}, {"composite": {"score": -45}}) == -45

    def test_score_no_signal(self):
        assert _get_current_value("score", {}, None) is None

    def test_unknown_type(self):
        assert _get_current_value("unknown", {"close": 100}, None) is None

    def test_missing_key(self):
        assert _get_current_value("rsi", {}, None) is None


class TestBuildMessage:
    def test_custom_message(self, db_session):
        alert = Alert(condition_type="price", operator="above", threshold=70000.0, message="Custom")
        assert _build_message(alert, 71000.0) == "Custom"

    def test_price_message(self, db_session):
        alert = Alert(condition_type="price", operator="above", threshold=70000.0)
        msg = _build_message(alert, 71000.0)
        assert "au-dessus" in msg

    def test_rsi_message(self, db_session):
        alert = Alert(condition_type="rsi", operator="above", threshold=70.0)
        msg = _build_message(alert, 72.5)
        assert "RSI" in msg

    def test_score_message(self, db_session):
        alert = Alert(condition_type="score", operator="below", threshold=-50.0)
        msg = _build_message(alert, -65.0)
        assert "Score" in msg


class TestAlertServiceCRUD:
    def test_create_alert(self, db_session):
        service = AlertService(db_session)
        alert = service.create(condition_type="price", operator="above", threshold=70000.0)
        assert alert.id is not None
        assert alert.status == "active"

    def test_get_all_empty(self, db_session):
        assert AlertService(db_session).get_all() == []

    def test_get_all_with_alerts(self, db_session):
        s = AlertService(db_session)
        s.create(condition_type="price", operator="above", threshold=70000.0)
        s.create(condition_type="rsi", operator="below", threshold=30.0)
        assert len(s.get_all()) == 2

    def test_get_active(self, db_session):
        s = AlertService(db_session)
        a1 = s.create(condition_type="price", operator="above", threshold=70000.0)
        a2 = s.create(condition_type="rsi", operator="below", threshold=30.0)
        s.update(a2.id, status="disabled")
        assert len(s.get_active()) == 1

    def test_get_by_id(self, db_session):
        s = AlertService(db_session)
        a = s.create(condition_type="price", operator="above", threshold=70000.0)
        assert s.get_by_id(a.id).id == a.id

    def test_get_by_id_not_found(self, db_session):
        assert AlertService(db_session).get_by_id(999) is None

    def test_update_alert(self, db_session):
        s = AlertService(db_session)
        a = s.create(condition_type="price", operator="above", threshold=70000.0)
        assert s.update(a.id, threshold=75000.0).threshold == 75000.0

    def test_update_not_found(self, db_session):
        assert AlertService(db_session).update(999, threshold=100.0) is None

    def test_delete_alert(self, db_session):
        s = AlertService(db_session)
        a = s.create(condition_type="price", operator="above", threshold=70000.0)
        assert s.delete(a.id) is True
        assert s.get_by_id(a.id) is None

    def test_delete_not_found(self, db_session):
        assert AlertService(db_session).delete(999) is False

    def test_filter_by_symbol(self, db_session):
        s = AlertService(db_session)
        s.create(symbol="BTC/USD", condition_type="price", operator="above", threshold=70000.0)
        s.create(symbol="ETH/USD", condition_type="price", operator="above", threshold=4000.0)
        assert len(s.get_all(symbol="BTC/USD")) == 1


def _insert_candles(db, count=25, base_price=67000.0, trend=100.0):
    base_ts = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(count):
        db.add(Candle(
            symbol="BTC/USD", timeframe="4h",
            timestamp=base_ts + timedelta(hours=4 * i),
            open_price=base_price + i * trend,
            high_price=base_price + 500 + i * trend,
            low_price=base_price - 300 + i * trend,
            close_price=base_price + 200 + i * trend,
            volume=1000.0, source="test",
        ))
    db.commit()


class TestCheckAlerts:
    def test_check_no_alerts(self, db_session):
        assert AlertService(db_session).check_alerts()["triggered"] == 0

    def test_check_no_data(self, db_session):
        s = AlertService(db_session)
        s.create(condition_type="price", operator="above", threshold=70000.0)
        assert s.check_alerts()["triggered"] == 0

    def test_check_price_above_triggered(self, db_session):
        _insert_candles(db_session, count=25)
        s = AlertService(db_session)
        s.create(condition_type="price", operator="above", threshold=69000.0, timeframe="4h")
        r = s.check_alerts(timeframe="4h")
        assert r["triggered"] == 1
        assert len(r["notifications"]) == 1

    def test_check_price_below_not_triggered(self, db_session):
        _insert_candles(db_session, count=25)
        s = AlertService(db_session)
        s.create(condition_type="price", operator="below", threshold=60000.0, timeframe="4h")
        assert s.check_alerts(timeframe="4h")["triggered"] == 0

    def test_triggered_sets_status(self, db_session):
        _insert_candles(db_session, count=25)
        s = AlertService(db_session)
        a = s.create(condition_type="price", operator="above", threshold=69000.0, timeframe="4h")
        s.check_alerts(timeframe="4h")
        assert s.get_by_id(a.id).status == "triggered"

    def test_recurring_stays_active(self, db_session):
        _insert_candles(db_session, count=25)
        s = AlertService(db_session)
        a = s.create(condition_type="price", operator="above", threshold=69000.0, timeframe="4h", recurring=True)
        s.check_alerts(timeframe="4h")
        assert s.get_by_id(a.id).status == "active"

    def test_disabled_ignored(self, db_session):
        _insert_candles(db_session, count=25)
        s = AlertService(db_session)
        a = s.create(condition_type="price", operator="above", threshold=69000.0, timeframe="4h")
        s.update(a.id, status="disabled")
        assert s.check_alerts(timeframe="4h")["triggered"] == 0

    def test_wrong_timeframe_ignored(self, db_session):
        _insert_candles(db_session, count=25)
        s = AlertService(db_session)
        s.create(condition_type="price", operator="above", threshold=69000.0, timeframe="1h")
        assert s.check_alerts(timeframe="4h")["triggered"] == 0


class TestAlertEndpoints:
    def test_list_empty(self, client):
        assert client.get("/alerts").status_code == 200

    def test_create_alert(self, client):
        r = client.post("/alerts", json={"condition_type": "price", "operator": "above", "threshold": 70000.0})
        assert r.status_code == 201
        assert r.json()["status"] == "active"

    def test_create_and_list(self, client):
        client.post("/alerts", json={"condition_type": "price", "operator": "above", "threshold": 70000.0})
        client.post("/alerts", json={"condition_type": "rsi", "operator": "below", "threshold": 30.0})
        assert len(client.get("/alerts").json()) == 2

    def test_get_alert(self, client):
        aid = client.post("/alerts", json={"condition_type": "price", "operator": "above", "threshold": 70000.0}).json()["id"]
        assert client.get(f"/alerts/{aid}").status_code == 200

    def test_get_not_found(self, client):
        assert client.get("/alerts/999").status_code == 404

    def test_update_alert(self, client):
        aid = client.post("/alerts", json={"condition_type": "price", "operator": "above", "threshold": 70000.0}).json()["id"]
        assert client.put(f"/alerts/{aid}", json={"threshold": 75000.0}).json()["threshold"] == 75000.0

    def test_update_not_found(self, client):
        assert client.put("/alerts/999", json={"threshold": 100.0}).status_code == 404

    def test_delete_alert(self, client):
        aid = client.post("/alerts", json={"condition_type": "price", "operator": "above", "threshold": 70000.0}).json()["id"]
        assert client.delete(f"/alerts/{aid}").status_code == 204

    def test_delete_not_found(self, client):
        assert client.delete("/alerts/999").status_code == 404

    def test_check_endpoint(self, client):
        r = client.post("/alerts/check?timeframe=4h")
        assert r.status_code == 200
        assert "triggered" in r.json()

    def test_notifications_endpoint(self, client):
        assert client.get("/alerts/notifications").json() == []

